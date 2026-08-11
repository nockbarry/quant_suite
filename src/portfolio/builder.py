"""TargetPortfolioBuilder — derive a desired portfolio from beliefs.

Pipeline (re-architecture spine):
    active theses -> conviction ladder -> per-thesis budget
    -> equal-weight vehicles -> merge same symbol across theses
    -> [optional calibration sanity bound]
    -> hard risk caps (position, sector)
    -> fold rule adjustments (stop-loss=0, trims)
    -> honor CashPolicy invested band + reserves

The calibration bound is OFF by default in Phase 2. The current calibration
curve is INVERTED (90% conf -> 34% actual), so feeding it in as a cap would
reproduce the exact bug the redesign removes (everything squashed to 3-5%).
A proper opinion-derived bound is wired in Phase 6; until then we let shadow
mode show the true conviction-driven targets, governed only by hard risk caps.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Callable, Optional

from src.portfolio.sizing import ConvictionSizer
from src.portfolio.target import CashPolicy, TargetPortfolio, TargetWeight
from src.risk.limits import RiskLimitsConfig
from src.risk.stress_tester import SYMBOL_SECTOR_MAP

logger = logging.getLogger(__name__)


class TargetPortfolioBuilder:
    """Builds a TargetPortfolio from active theses + risk limits + cash policy."""

    def __init__(
        self,
        tracker,
        config: Optional[RiskLimitsConfig] = None,
        sizer: Optional[ConvictionSizer] = None,
        cash_policy: Optional[CashPolicy] = None,
    ):
        self.tracker = tracker
        self.config = config or RiskLimitsConfig()
        self.sizer = sizer or ConvictionSizer()
        self.cash_policy = cash_policy or CashPolicy()

    @staticmethod
    def _sector(symbol: str) -> str:
        return SYMBOL_SECTOR_MAP.get(symbol, "other")

    def _apply_sector_cap(self, raw: dict[str, TargetWeight]) -> None:
        """Scale down any sector exceeding the cap, proportionally."""
        sector_cap = self.config.max_sector_pct
        by_sector: dict[str, list[TargetWeight]] = defaultdict(list)
        for tw in raw.values():
            by_sector[self._sector(tw.symbol)].append(tw)
        for members in by_sector.values():
            total = sum(m.weight for m in members)
            if total > sector_cap and total > 0:
                scale = sector_cap / total
                for m in members:
                    m.weight *= scale
                    m.bounded_by = m.bounded_by or "sector_cap"

    def _deploy_to_floor(self, raw: dict[str, TargetWeight], min_invested: float) -> None:
        """Grow existing positions pro-rata toward the invested floor.

        Respects the per-position cap; re-applies the sector cap after growth.
        If caps bind before the floor is reached, residual stays as cash (we
        never force allocation beyond risk limits).
        """
        pos_cap = self.config.max_position_pct
        if not raw or min_invested <= 0:
            return
        for _ in range(6):  # iterate so cap-clamped headroom redistributes
            total = sum(w.weight for w in raw.values())
            deficit = min_invested - total
            if deficit <= 1e-6:
                break
            growable = [w for w in raw.values() if w.weight < pos_cap - 1e-9]
            base = sum(w.weight for w in growable)
            if not growable or base <= 0:
                break
            for w in growable:
                w.weight = min(pos_cap, w.weight + deficit * (w.weight / base))
                if w.bounded_by is None:
                    w.bounded_by = "deploy_to_floor"
            self._apply_sector_cap(raw)
            # floor-growth must not violate the correlation-cluster cap either
            if getattr(self, "_clusters", None):
                from src.portfolio.clusters import apply_cluster_cap
                apply_cluster_cap(raw, self._clusters, self.config.max_cluster_pct)

    def build(
        self,
        equity: float,
        today: Optional[date] = None,
        extra_adjustments: Optional[list[TargetWeight]] = None,
        calibration_bound: Optional[Callable[[float], float]] = None,
        correlation_clusters: Optional[list[set]] = None,
        ranking: Optional[list[str]] = None,
        prob_map: Optional[dict] = None,
        prob_sizing: Optional[bool] = None,
    ) -> TargetPortfolio:
        """Derive the target portfolio.

        Args:
            equity: total account equity (for record-keeping; weights are fractions).
            today: date for reserve evaluation (defaults to now).
            extra_adjustments: rule-engine overrides (Phase 5). weight=0 means exit.
            calibration_bound: optional fn conviction(0-1)->max weight. Off in Phase 2.
            correlation_clusters: groups of correlated symbols; each multi-symbol
                cluster's total weight is capped (~50%) — sector caps miss
                cross-sector rate/AI clusters (CCJ+GLD+MU all fell together).
            ranking: ordered thesis ids, best first (from weekly forced ranking).
                Applies a budget tilt 1.2x (top) -> 0.8x (bottom) so ranking
                actually differentiates sizing when conviction is clustered.
            prob_map: symbol -> SymbolProbability from the ProbabilityEstimator.
                When probability sizing is active, thesis budgets come from the
                CALIBRATED probability ladder and conviction is governance-only
                (eligibility >= 35, reviews, exits) — the decision-confidence
                curve is measurably inverted, so raw conviction must not size.
            prob_sizing: force probability sizing on/off; None defers to the
                ATHENA_PROB_SIZING env flag (default off). cron_build_target
                dual-computes both modes during the shadow window.
        """
        today = today or datetime.now().date()
        theses = self.tracker.get_active_theses()

        import os
        if prob_sizing is None:
            prob_sizing = os.environ.get("ATHENA_PROB_SIZING", "0") == "1"
        use_prob = bool(prob_sizing and prob_map)

        # Rank tilt: linear 1.2x (rank 1) -> 0.8x (rank N). Breaks the
        # everything-at-74-80% conviction cluster into differentiated sizing.
        rank_tilt: dict[str, float] = {}
        if ranking and len(ranking) > 1:
            n = len(ranking)
            for i, tid in enumerate(ranking):
                rank_tilt[tid] = 1.2 - 0.4 * (i / (n - 1))

        # 1-3. ladder -> equal vehicle weights -> merge same symbol across theses
        raw: dict[str, TargetWeight] = {}
        sym_conviction: dict[str, float] = {}
        for th in theses:
            if use_prob:
                # Governance gate only: conviction < 35 = thesis not sizable.
                if float(th.conviction or 0) < 35.0:
                    continue
                probs = [
                    prob_map[s].p_direction
                    for s in (th.positions or [])
                    if s in prob_map
                ]
                if probs:
                    p_th = sum(probs) / len(probs)
                    budget = self.sizer.thesis_budget_from_prob(p_th)
                    mode = "probability"
                else:
                    # no estimate for any vehicle — fall back to conviction
                    budget = self.sizer.thesis_budget(th.conviction)
                    mode = "conviction"
            else:
                budget = self.sizer.thesis_budget(th.conviction)
                mode = "conviction"
            budget *= rank_tilt.get(th.id, 1.0)
            vw = self.sizer.vehicle_weights(budget, th.positions)
            for sym, w in vw.items():
                sym_conviction[sym] = max(sym_conviction.get(sym, 0.0), th.conviction)
                p_cal = prob_map[sym].p_direction if (use_prob and sym in prob_map) else None
                if sym in raw:
                    raw[sym].weight += w
                    # provenance: note multi-thesis membership
                    if th.name and th.name not in (raw[sym].thesis_name or ""):
                        raw[sym].thesis_name = f"{raw[sym].thesis_name}+{th.name}"
                else:
                    raw[sym] = TargetWeight(
                        symbol=sym,
                        weight=w,
                        thesis_id=th.id,
                        thesis_name=th.name,
                        source="thesis_ladder",
                        p_calibrated=p_cal,
                        sizing_mode=mode,
                    )

        # 4. optional calibration sanity bound (OFF in Phase 2)
        if calibration_bound is not None:
            for sym, tw in raw.items():
                cap = calibration_bound(sym_conviction.get(sym, 50.0) / 100.0)
                if tw.weight > cap:
                    tw.weight = cap
                    tw.bounded_by = "calibration"

        # 5a. hard per-position cap
        pos_cap = self.config.max_position_pct
        for tw in raw.values():
            if tw.weight > pos_cap:
                tw.weight = pos_cap
                tw.bounded_by = "position_cap"

        # 5b. hard sector cap — scale down any over-weight sector proportionally
        self._apply_sector_cap(raw)

        # 5c. correlation-cluster cap — catches cross-sector correlated bets
        # (rate-sensitive CCJ/GLD/NEE/MU cluster) that sector caps miss.
        self._clusters = correlation_clusters or []
        if self._clusters:
            from src.portfolio.clusters import apply_cluster_cap
            apply_cluster_cap(raw, self._clusters, self.config.max_cluster_pct)

        # 6. fold rule-engine adjustments (Phase 5). weight<=0 removes the symbol.
        for adj in extra_adjustments or []:
            if adj.weight <= 0:
                raw.pop(adj.symbol, None)
            else:
                adj.source = adj.source or "rule_adjustment"
                raw[adj.symbol] = adj

        # 7. honor cash policy: cap total invested at the reserve-adjusted ceiling
        cp = self.cash_policy
        max_inv = cp.max_invested(today)
        total_inv = sum(tw.weight for tw in raw.values())
        if total_inv > max_inv and total_inv > 0:
            scale = max_inv / total_inv
            for tw in raw.values():
                tw.weight *= scale
                tw.bounded_by = tw.bounded_by or "invested_band"
            logger.info(
                f"Scaled invested {total_inv:.1%} -> {max_inv:.1%} "
                f"(reserves held {cp.named_reserve_pct(today):.1%})"
            )

        # 8. auto-deploy untagged excess cash up to the band FLOOR. If conviction
        #    weights underfill the floor and no reserve justifies the cash, grow
        #    existing positions pro-rata (capped) rather than sit on idle cash.
        self._deploy_to_floor(raw, cp.min_invested(today))

        return TargetPortfolio(
            weights=raw,
            cash_policy=cp,
            generated_at=datetime.now(),
            equity_at_build=float(equity),
        )
