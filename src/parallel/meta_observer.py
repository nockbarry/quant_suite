"""Meta-Observer — Cross-instance analysis engine.

Reads all Athena instance directories, computes divergence metrics,
and generates improvement recommendations.

Key metrics:
- Thesis overlap (Jaccard similarity): Do instances discover the same theses?
- Position convergence: Which symbols are held across instances?
- Conviction distribution: Mean/std of conviction per shared thesis.
- Performance by consensus: Do 3/3 positions outperform 1/3 positions?
"""
import json
import logging
import statistics
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths
from src.core.instance import instance_config

logger = logging.getLogger(__name__)


@dataclass
class InstanceSnapshot:
    """Point-in-time snapshot of one Athena instance."""
    instance_name: str
    results_dir: str
    equity: float
    cash: float
    positions: list  # [{symbol, market_value, qty, ...}]
    position_symbols: set  # Set of held symbols
    theses: list  # [{id, name, conviction, vehicles, status}]
    thesis_names: set  # Set of thesis names
    decisions_today: list
    prediction_accuracy: float

    def __post_init__(self):
        # Convert to sets if lists were passed
        if isinstance(self.position_symbols, list):
            self.position_symbols = set(self.position_symbols)
        if isinstance(self.thesis_names, list):
            self.thesis_names = set(self.thesis_names)


@dataclass
class CrossInstanceMetrics:
    """Divergence metrics across all instances."""
    timestamp: str
    num_instances: int
    instances: list  # Instance summaries

    # Thesis analysis
    thesis_overlap_jaccard: float  # 0-1, higher = more similar
    shared_theses: list  # Names in ALL instances
    unique_theses: dict  # {instance: [thesis names only in that instance]}
    thesis_conviction_distributions: dict  # {thesis_name: {mean, std, values}}

    # Position analysis
    position_overlap_jaccard: float
    consensus_positions: list  # Symbols held by ALL instances
    divergent_positions: dict  # {instance: [symbols unique to it]}
    position_agreement_rate: float  # % of positions held by 2+ instances

    # Performance
    equity_comparison: dict  # {instance: equity}

    # Recommendations
    recommendations: list


class MetaObserver:
    """Cross-instance analysis engine.

    Reads state from all discovered Athena instance directories,
    computes cross-instance divergence metrics, and generates
    actionable improvement recommendations.

    Usage:
        observer = MetaObserver()
        metrics = observer.run()
        print(metrics.recommendations)
    """

    def __init__(self, instance_dirs: list = None):
        """Initialize with explicit instance dirs or auto-discover.

        Args:
            instance_dirs: Explicit list of result directory paths.
                          If None, auto-discovers via instance_config.all_instance_dirs().
        """
        if instance_dirs:
            self.instance_dirs = [Path(d) for d in instance_dirs]
        else:
            self.instance_dirs = instance_config.all_instance_dirs()

        self.report_dir = paths.base / "parallel"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def snapshot_instance(self, instance_dir: Path) -> InstanceSnapshot:
        """Read state from one Athena instance.

        Reads state.json for portfolio/positions and thesis YAML files
        for active theses and conviction levels.

        Args:
            instance_dir: Path to the instance's quant_results directory.

        Returns:
            InstanceSnapshot with current state.
        """
        name = instance_config.instance_name_from_dir(instance_dir)

        # Read state.json
        state_file = instance_dir / "live" / "state.json"
        state = {}
        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read state.json for {name}: {e}")

        portfolio = state.get("portfolio", {})
        positions = state.get("positions", [])

        # Read theses
        theses = self._read_theses(instance_dir)

        # Read today's decisions
        decisions_today = self._read_decisions_today(instance_dir)

        # Read prediction accuracy from intelligence
        prediction_accuracy = self._read_prediction_accuracy(instance_dir)

        return InstanceSnapshot(
            instance_name=name,
            results_dir=str(instance_dir),
            equity=float(portfolio.get("equity", 0)),
            cash=float(portfolio.get("cash", 0)),
            positions=positions,
            position_symbols={
                p.get("symbol", "")
                for p in positions
                if float(p.get("market_value", 0)) > 10
            },
            theses=theses,
            thesis_names={t["name"] for t in theses},
            decisions_today=decisions_today,
            prediction_accuracy=prediction_accuracy,
        )

    def _read_theses(self, instance_dir: Path) -> list:
        """Read active thesis YAML files from an instance directory."""
        theses = []
        thesis_dir = instance_dir / "theses"
        if not thesis_dir.exists():
            return theses

        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML not installed, cannot read theses")
            return theses

        for yf in sorted(thesis_dir.glob("*.yaml")):
            try:
                with open(yf) as f:
                    data = yaml.safe_load(f)
                if data and data.get("status") == "active":
                    vehicles = data.get("positions", [])
                    # Extract vehicle symbols
                    vehicle_symbols = []
                    if isinstance(vehicles, list):
                        for v in vehicles:
                            if isinstance(v, dict):
                                vehicle_symbols.append(v.get("symbol", ""))
                            elif isinstance(v, str):
                                vehicle_symbols.append(v)

                    theses.append({
                        "id": data.get("id", ""),
                        "name": data.get("name", ""),
                        "conviction": data.get("conviction", 0),
                        "vehicles": vehicle_symbols,
                        "status": data.get("status", ""),
                    })
            except Exception as e:
                logger.debug(f"Failed to read thesis {yf.name}: {e}")
                continue

        return theses

    def _read_decisions_today(self, instance_dir: Path) -> list:
        """Read today's trading decisions from an instance."""
        decisions_dir = instance_dir / "decisions"
        if not decisions_dir.exists():
            return []

        today_str = datetime.now().strftime("%Y-%m-%d")
        decisions = []

        for df in decisions_dir.glob(f"*{today_str}*.json"):
            try:
                with open(df) as f:
                    data = json.load(f)
                decisions.append({
                    "action": data.get("action", ""),
                    "symbol": data.get("symbol", ""),
                    "confidence": data.get("confidence", 0),
                    "status": data.get("status", ""),
                })
            except (json.JSONDecodeError, OSError):
                continue

        return decisions

    def _read_prediction_accuracy(self, instance_dir: Path) -> float:
        """Read prediction accuracy from intelligence calibration."""
        cal_file = instance_dir / "intelligence" / "calibration.json"
        if not cal_file.exists():
            return 0.0

        try:
            with open(cal_file) as f:
                data = json.load(f)
            return float(data.get("overall_accuracy", 0))
        except (json.JSONDecodeError, OSError, TypeError):
            return 0.0

    def snapshot_all(self) -> list:
        """Read state from all discovered instances.

        Returns:
            List of InstanceSnapshot objects.
        """
        snapshots = []
        for d in self.instance_dirs:
            try:
                snapshots.append(self.snapshot_instance(d))
            except Exception as e:
                logger.warning(f"Failed to snapshot {d}: {e}")
        return snapshots

    def _jaccard(self, set_a: set, set_b: set) -> float:
        """Jaccard similarity coefficient between two sets.

        Returns 1.0 if both sets are empty (identical),
        0.0 if they have no overlap.
        """
        if not set_a and not set_b:
            return 1.0
        union = set_a | set_b
        if not union:
            return 0.0
        return len(set_a & set_b) / len(union)

    def _pairwise_jaccard_avg(self, sets: list) -> float:
        """Average pairwise Jaccard similarity across a list of sets."""
        if len(sets) < 2:
            return 1.0
        similarities = []
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                similarities.append(self._jaccard(sets[i], sets[j]))
        return sum(similarities) / len(similarities) if similarities else 0.0

    def compute_thesis_overlap(self, snapshots: list) -> tuple:
        """Compute thesis name overlap across instances.

        Returns:
            (avg_jaccard, shared_list, unique_dict)
        """
        if len(snapshots) < 2:
            return 1.0, [], {}

        all_names = [s.thesis_names for s in snapshots]

        avg_jaccard = self._pairwise_jaccard_avg(all_names)

        # Shared: in ALL instances
        shared = set.intersection(*all_names) if all_names else set()

        # Unique to each instance (not in any other instance)
        unique = {}
        for s in snapshots:
            others = [other.thesis_names for other in snapshots if other != s]
            if others:
                others_union = set.union(*others)
                only_here = s.thesis_names - others_union
            else:
                only_here = s.thesis_names
            if only_here:
                unique[s.instance_name] = sorted(only_here)

        return avg_jaccard, sorted(shared), unique

    def compute_position_convergence(self, snapshots: list) -> tuple:
        """Compute position symbol overlap across instances.

        Returns:
            (avg_jaccard, consensus_list, unique_dict, agreement_rate)
        """
        if len(snapshots) < 2:
            return 1.0, [], {}, 1.0

        all_symbols = [s.position_symbols for s in snapshots]

        avg_jaccard = self._pairwise_jaccard_avg(all_symbols)

        # Consensus: held by ALL instances
        consensus = set.intersection(*all_symbols) if all_symbols else set()

        # Unique to each instance
        unique = {}
        for s in snapshots:
            others = [other.position_symbols for other in snapshots if other != s]
            if others:
                others_union = set.union(*others)
                only_here = s.position_symbols - others_union
                if only_here:
                    unique[s.instance_name] = sorted(only_here)

        # Agreement rate: % of all unique symbols held by 2+ instances
        all_union = set.union(*all_symbols) if all_symbols else set()
        if all_union:
            in_multiple = sum(
                1 for sym in all_union
                if sum(1 for s in snapshots if sym in s.position_symbols) >= 2
            )
            agreement_rate = in_multiple / len(all_union)
        else:
            agreement_rate = 0.0

        return avg_jaccard, sorted(consensus), unique, agreement_rate

    def compute_conviction_distributions(self, snapshots: list) -> dict:
        """For shared theses, compute conviction distribution across instances.

        Returns dict keyed by thesis name with mean, std, min, max, and per-instance values.
        Only includes theses present in 2+ instances.
        """
        # Collect convictions per thesis name
        thesis_convictions = {}
        for s in snapshots:
            for t in s.theses:
                name = t["name"]
                if name not in thesis_convictions:
                    thesis_convictions[name] = []
                thesis_convictions[name].append({
                    "instance": s.instance_name,
                    "conviction": t["conviction"],
                })

        # Only report theses in 2+ instances
        distributions = {}
        for name, entries in sorted(thesis_convictions.items()):
            if len(entries) >= 2:
                values = [e["conviction"] for e in entries]
                distributions[name] = {
                    "mean": statistics.mean(values),
                    "std": statistics.stdev(values) if len(values) > 1 else 0.0,
                    "min": min(values),
                    "max": max(values),
                    "values": entries,
                    "n_instances": len(entries),
                }

        return distributions

    def compute_position_matrix(self, snapshots: list) -> list:
        """Build a position-by-instance matrix for the dashboard.

        Returns list of dicts: [{symbol, instances: [bool, ...], count, held_by}]
        sorted by count descending then symbol ascending.
        """
        if not snapshots:
            return []

        # Collect all symbols
        all_symbols = set()
        for s in snapshots:
            all_symbols |= s.position_symbols

        matrix = []
        for sym in sorted(all_symbols):
            holders = [sym in s.position_symbols for s in snapshots]
            count = sum(holders)
            matrix.append({
                "symbol": sym,
                "instances": holders,
                "count": count,
                "held_by": [s.instance_name for s, held in zip(snapshots, holders) if held],
            })

        # Sort: most consensus first, then alphabetical
        matrix.sort(key=lambda x: (-x["count"], x["symbol"]))
        return matrix

    def generate_recommendations(self, thesis_overlap, position_overlap,
                                  conviction_dists, snapshots) -> list:
        """Generate actionable improvement recommendations.

        Analyzes divergence metrics and flags areas where the system
        is path-dependent or inconsistent.
        """
        recs = []

        jaccard_t, shared, unique_t = thesis_overlap
        jaccard_p, consensus_p, unique_p, agreement = position_overlap

        # Thesis overlap check
        if jaccard_t < 0.3:
            recs.append(
                f"Very low thesis overlap ({jaccard_t:.0%}). Thesis creation is highly "
                f"path-dependent. Consider adding more objective thesis criteria or "
                f"standardizing research inputs."
            )
        elif jaccard_t < 0.5:
            recs.append(
                f"Low thesis overlap ({jaccard_t:.0%}). Consider adding more objective "
                f"thesis criteria to reduce path dependence."
            )

        # Position overlap check
        if jaccard_p < 0.3:
            recs.append(
                f"Very low position overlap ({jaccard_p:.0%}). Vehicle selection is "
                f"highly divergent. Standardize vehicle selection per thesis."
            )
        elif jaccard_p < 0.4:
            recs.append(
                f"Low position overlap ({jaccard_p:.0%}). Vehicle selection is divergent. "
                f"Consider standardizing vehicle selection per thesis."
            )

        # Agreement rate
        if agreement < 0.3:
            recs.append(
                f"Only {agreement:.0%} of positions held by 2+ instances. "
                f"Most positions are path-dependent single-instance picks."
            )
        elif agreement < 0.5:
            recs.append(
                f"Only {agreement:.0%} of positions held by 2+ instances. "
                f"Many positions are path-dependent."
            )

        # High conviction variance on shared theses
        high_var_theses = []
        for name, dist in conviction_dists.items():
            if dist["std"] > 15:
                high_var_theses.append(
                    f"'{name}': {dist['mean']:.0f}% +/- {dist['std']:.0f}%"
                )
        if high_var_theses:
            recs.append(
                f"High conviction variance on {len(high_var_theses)} shared theses: "
                + "; ".join(high_var_theses[:3])
                + (f" (and {len(high_var_theses) - 3} more)" if len(high_var_theses) > 3 else "")
                + ". Evidence evaluation is inconsistent."
            )

        # Equity divergence
        equities = [s.equity for s in snapshots if s.equity > 0]
        if len(equities) >= 2 and max(equities) > 0:
            spread = (max(equities) - min(equities)) / max(equities) * 100
            if spread > 20:
                recs.append(
                    f"Large equity spread across instances: {spread:.1f}%. "
                    f"Performance is significantly diverging — investigate root cause."
                )
            elif spread > 10:
                recs.append(
                    f"Equity spread across instances: {spread:.1f}%. "
                    f"Performance is diverging."
                )

        # Prediction accuracy comparison
        accuracies = [(s.instance_name, s.prediction_accuracy) for s in snapshots if s.prediction_accuracy > 0]
        if len(accuracies) >= 2:
            values = [a[1] for a in accuracies]
            if max(values) - min(values) > 10:
                best = max(accuracies, key=lambda x: x[1])
                worst = min(accuracies, key=lambda x: x[1])
                recs.append(
                    f"Prediction accuracy divergence: {best[0]} ({best[1]:.0f}%) vs "
                    f"{worst[0]} ({worst[1]:.0f}%). Study the better-calibrated instance."
                )

        if not recs:
            recs.append(
                "Instances are well-aligned. Low divergence indicates a robust, "
                "reproducible decision process."
            )

        return recs

    def run(self) -> CrossInstanceMetrics:
        """Full analysis pipeline.

        Snapshots all instances, computes all metrics, generates
        recommendations, and saves the report to disk.

        Returns:
            CrossInstanceMetrics with full analysis results.
        """
        snapshots = self.snapshot_all()

        if not snapshots:
            return CrossInstanceMetrics(
                timestamp=datetime.now().isoformat(),
                num_instances=0,
                instances=[],
                thesis_overlap_jaccard=0.0,
                shared_theses=[],
                unique_theses={},
                thesis_conviction_distributions={},
                position_overlap_jaccard=0.0,
                consensus_positions=[],
                divergent_positions={},
                position_agreement_rate=0.0,
                equity_comparison={},
                recommendations=["No instances found."],
            )

        thesis_overlap = self.compute_thesis_overlap(snapshots)
        position_overlap = self.compute_position_convergence(snapshots)
        conviction_dists = self.compute_conviction_distributions(snapshots)
        position_matrix = self.compute_position_matrix(snapshots)
        recommendations = self.generate_recommendations(
            thesis_overlap, position_overlap, conviction_dists, snapshots
        )

        metrics = CrossInstanceMetrics(
            timestamp=datetime.now().isoformat(),
            num_instances=len(snapshots),
            instances=[
                {
                    "name": s.instance_name,
                    "equity": s.equity,
                    "cash": s.cash,
                    "positions": len(s.position_symbols),
                    "theses": len(s.thesis_names),
                    "decisions_today": len(s.decisions_today),
                    "prediction_accuracy": s.prediction_accuracy,
                }
                for s in snapshots
            ],
            thesis_overlap_jaccard=thesis_overlap[0],
            shared_theses=thesis_overlap[1],
            unique_theses=thesis_overlap[2],
            thesis_conviction_distributions=conviction_dists,
            position_overlap_jaccard=position_overlap[0],
            consensus_positions=position_overlap[1],
            divergent_positions=position_overlap[2],
            position_agreement_rate=position_overlap[3],
            equity_comparison={s.instance_name: s.equity for s in snapshots},
            recommendations=recommendations,
        )

        # Save report
        report_file = self.report_dir / f"meta_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_file, "w") as f:
                json.dump(asdict(metrics), f, indent=2, default=str)
            # Also write a latest pointer
            latest_file = self.report_dir / "meta_report_latest.json"
            with open(latest_file, "w") as f:
                json.dump(asdict(metrics), f, indent=2, default=str)
            logger.info(f"Meta-observer report saved: {report_file}")
        except OSError as e:
            logger.warning(f"Failed to save meta report: {e}")

        return metrics
