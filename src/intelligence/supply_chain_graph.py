"""
Supply Chain Graph — propagate document signals to downstream beneficiaries.

Milestone v3. v0 priors are hand-coded heuristics; v4 will replace them with
empirical decay factors derived from historical lead-lag analysis.

Critical design rule: every propagated signal carries a `root_signal_id`
identifying its source document. ThesisSuggester.find_convergences()
deduplicates by root before counting toward the convergence threshold —
so one MSFT earnings call cannot manufacture fake convergence by fanning
out to NVDA + MU + TSM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Edge:
    """Directed edge: when `source` reports a signal, propagate to `target`."""
    target: str
    relation: str          # human label: "ai_capex_to_gpu", "gpu_to_hbm", etc.
    decay: float           # confidence multiplier per hop, 0..1
    notes: str = ""


@dataclass
class InferredSignal:
    """An inferred signal produced by SupplyChainGraph.propagate()."""
    target_symbol: str
    direction: str
    inferred_confidence: float
    propagation_path: list[str]   # e.g. ["MSFT", "NVDA", "MU"]
    propagation_hops: int
    relation_chain: list[str]     # ["ai_capex_to_gpu", "gpu_to_hbm"]
    driver_text: str
    root_signal_id: str
    root_symbol: str

    def to_dict(self) -> dict:
        return {
            "target_symbol": self.target_symbol,
            "direction": self.direction,
            "inferred_confidence": self.inferred_confidence,
            "propagation_path": list(self.propagation_path),
            "propagation_hops": self.propagation_hops,
            "relation_chain": list(self.relation_chain),
            "driver_text": self.driver_text,
            "root_signal_id": self.root_signal_id,
            "root_symbol": self.root_symbol,
        }


# ---------------------------------------------------------------------------
# v0 priors — uncalibrated heuristics. v4 replaces these with empirical
# constants derived from historical capex-announcement → downstream-return
# regressions. Drop any edge whose information coefficient < 0.15.
# ---------------------------------------------------------------------------
SUPPLY_CHAIN_V0: dict[str, list[Edge]] = {
    # Hyperscalers → GPU compute
    "MSFT":  [Edge("NVDA", relation="ai_capex_to_gpu", decay=0.70,
                   notes="Microsoft Azure GPU buildout drives NVDA datacenter revenue")],
    "GOOGL": [Edge("NVDA", relation="ai_capex_to_gpu", decay=0.60,
                   notes="GCP TPU mix dampens direct flow vs MSFT/META")],
    "AMZN":  [Edge("NVDA", relation="ai_capex_to_gpu", decay=0.60,
                   notes="AWS Trainium/Inferentia mix dampens direct flow")],
    "META":  [Edge("NVDA", relation="ai_capex_to_gpu", decay=0.65)],
    "ORCL":  [Edge("NVDA", relation="ai_capex_to_gpu", decay=0.55)],
    # GPU demand → memory + foundry
    "NVDA":  [
        Edge("MU",  relation="gpu_to_hbm",     decay=0.65,
             notes="HBM3E is sole-sourced from MU/SK Hynix/Samsung; MU is US-listed proxy"),
        Edge("TSM", relation="fabless_to_fab", decay=0.75,
             notes="NVDA dies fabbed at TSMC; growth tracks N3/N4/CoWoS capacity"),
    ],
    # Foundry → fabless customers
    "TSM":   [
        Edge("AMD",  relation="foundry_customer", decay=0.65),
        Edge("QCOM", relation="foundry_customer", decay=0.60),
        Edge("AVGO", relation="foundry_customer", decay=0.55),
    ],
    # Foundry → litho
    "TSM_litho": [Edge("ASML", relation="fab_to_litho", decay=0.55)],
}


class SupplyChainGraph:
    """Walks the supply chain graph to produce InferredSignal objects.

    propagate() is BFS bounded by max_hops. Confidence is multiplied by
    edge decay at each hop. Direction is preserved (bullish stays bullish);
    inverse relationships should be modeled as negative-direction edges
    (not implemented in v0 — all edges are positive).

    Edge source priority (first found wins):
      1. `edges=` constructor arg (test isolation)
      2. Calibrated graph at ~/quant_results/calibration/supply_chain_v1.json
         (written by scripts/calibrate_supply_chain.py — empirical decay
         factors derived from historical event-study IC measurements)
      3. SUPPLY_CHAIN_V0 priors (uncalibrated heuristics)
    """

    DEFAULT_MAX_HOPS = 2
    # Drop inferred signals below this confidence — pure noise floor.
    MIN_INFERRED_CONFIDENCE = 0.40

    def __init__(
        self,
        edges: Optional[dict[str, list[Edge]]] = None,
        calibration_path: Optional["Path"] = None,
    ):
        if edges is not None:
            self.edges = edges
            self.source = "injected"
            return
        loaded = self._try_load_calibrated(calibration_path)
        if loaded is not None:
            self.edges, self.source = loaded, "calibrated"
            logger.info(
                f"SupplyChainGraph loaded {sum(len(v) for v in self.edges.values())} "
                f"calibrated edges across {len(self.edges)} source symbols"
            )
        else:
            self.edges = SUPPLY_CHAIN_V0
            self.source = "v0_priors"

    @staticmethod
    def _try_load_calibrated(
        path: Optional["Path"] = None,
    ) -> Optional[dict[str, list["Edge"]]]:
        """Load the calibrated graph file if it exists; return None otherwise.

        IMPORTANT: an empty calibrated graph (graph={}) is a meaningful result —
        it means calibration ran and determined NO edges are reliable. We
        return that empty dict (not None) so propagation is a no-op rather
        than silently falling back to v0 priors that calibration just rejected.
        Returning None means the calibration file is missing or unreadable.
        """
        try:
            from src.core.paths import paths as _paths
            cal_path = path or (_paths.base / "calibration" / "supply_chain_v1.json")
            if not cal_path.exists():
                return None
            import json as _json
            payload = _json.loads(cal_path.read_text())
            if "graph" not in payload:
                # Malformed file
                logger.warning(f"calibration file missing 'graph' key: {cal_path}")
                return None
            graph_dict = payload["graph"] or {}
            out: dict[str, list[Edge]] = {}
            for src, edges_list in graph_dict.items():
                out[src] = [
                    Edge(
                        target=e["target"],
                        relation=e.get("relation", ""),
                        decay=float(e["decay"]),
                        notes=e.get("notes", ""),
                    )
                    for e in edges_list
                ]
            return out  # may be empty dict — that's a valid "no edges survive" result
        except Exception as e:
            logger.warning(f"failed to load calibrated graph: {e}")
            return None

    def propagate(
        self,
        root_symbol: str,
        direction: str,
        confidence: float,
        root_signal_id: str,
        driver_text: str = "",
        max_hops: int = DEFAULT_MAX_HOPS,
    ) -> list[InferredSignal]:
        """Walk downstream from root_symbol, return InferredSignal per hit.

        Cycle detection: a target already in the propagation path is skipped
        (prevents infinite loops and double-counting).
        """
        if direction not in ("bullish", "bearish", "neutral"):
            raise ValueError(f"Bad direction {direction!r}")
        if confidence <= 0:
            return []
        if not root_symbol:
            return []

        results: list[InferredSignal] = []

        # Frontier = list of (path, relation_chain, current_confidence)
        frontier = [
            ([root_symbol], [], confidence),
        ]

        while frontier:
            path, relations, conf = frontier.pop(0)
            if len(path) - 1 >= max_hops:
                continue
            current_node = path[-1]
            outgoing = self.edges.get(current_node, [])
            for edge in outgoing:
                if edge.target in path:
                    continue  # cycle guard
                new_conf = conf * edge.decay
                if new_conf < self.MIN_INFERRED_CONFIDENCE:
                    continue
                new_path = path + [edge.target]
                new_relations = relations + [edge.relation]
                results.append(InferredSignal(
                    target_symbol=edge.target,
                    direction=direction,
                    inferred_confidence=round(new_conf, 4),
                    propagation_path=new_path,
                    propagation_hops=len(new_path) - 1,
                    relation_chain=new_relations,
                    driver_text=self._build_driver_text(driver_text, new_path, edge),
                    root_signal_id=root_signal_id,
                    root_symbol=root_symbol,
                ))
                # Continue BFS one more hop
                frontier.append((new_path, new_relations, new_conf))

        return results

    @staticmethod
    def _build_driver_text(root_driver: str, path: list[str], edge: Edge) -> str:
        chain = " → ".join(path)
        prefix = f"Inferred via {chain} ({edge.relation})"
        if root_driver:
            return f"{prefix}: {root_driver[:160]}"
        return prefix


# ---------------------------------------------------------------------------
# Helper: write inferred signals to the SignalProvenanceTracker
# ---------------------------------------------------------------------------

def write_inferred_signals(
    inferred: list[InferredSignal],
    tracker=None,
) -> list:
    """Persist InferredSignals as SignalProvenance records.

    Returns the list of created SignalProvenance objects. Failures are logged
    but don't abort the batch.
    """
    if not inferred:
        return []
    from src.knowledge.signal_provenance import (
        SignalSource,
        get_provenance_tracker,
    )
    tracker = tracker or get_provenance_tracker()
    created = []
    for sig in inferred:
        try:
            provenance = tracker.create_signal(
                source=SignalSource.INFERRED,
                symbol=sig.target_symbol,
                confidence=sig.inferred_confidence,
                direction=sig.direction,
                description=sig.driver_text,
                detection_method=f"supply_chain:{'>'.join(sig.relation_chain)}",
                metadata={
                    "root_symbol": sig.root_symbol,
                    "relation_chain": sig.relation_chain,
                },
                root_signal_id=sig.root_signal_id,
                propagation_path=sig.propagation_path,
                propagation_hops=sig.propagation_hops,
            )
            created.append(provenance)
        except Exception as e:
            logger.exception(
                f"Failed to write inferred signal for {sig.target_symbol}: {e}"
            )
    return created
