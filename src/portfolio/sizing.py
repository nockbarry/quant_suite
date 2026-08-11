"""Conviction-driven position sizing — the ladder, finally wired in.

This is deliberately NOT a subclass of src.risk.position_sizing.PositionSizer:
that ABC is signal-coupled (calculate(signal, portfolio, price)) and works one
symbol at a time, whereas sizing here is thesis-level (conviction -> capital
budget -> split across vehicles). Forcing the ABC would be cargo-cult.

Design decision (re-architecture #3): conviction DRIVES size; calibration is
only a sanity bound applied later by the builder. The old behavior — where
calibrated_max_position_pct squashed every high-conviction position to 3-5%
because the calibration curve is inverted — is exactly what we're removing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConvictionSizer:
    """Maps thesis conviction (0-100) to a capital budget, split across vehicles.

    LADDER entries are (min_conviction, budget_fraction_of_equity), highest
    threshold first. A thesis at 75% conviction gets the 65%-tier budget.
    """

    # (min_conviction, fraction of total equity for the whole thesis)
    LADDER: tuple[tuple[float, float], ...] = (
        (80.0, 0.30),
        (65.0, 0.20),
        (50.0, 0.12),
        (35.0, 0.06),
        (0.0, 0.0),
    )

    # Probability ladder: thresholds are CALIBRATED P(direction correct),
    # not conviction. The opinion curve's well-populated bins land at
    # 0.47-0.73 actual, so discrimination has to happen inside a narrow
    # band — 62% calibrated edge over ~10d is genuinely strong. Thresholds
    # get retuned against opinion_calibration.json percentiles during the
    # ATHENA_PROB_SIZING shadow window.
    PROB_LADDER: tuple[tuple[float, float], ...] = (
        (0.62, 0.30),
        (0.58, 0.20),
        (0.54, 0.12),
        (0.50, 0.06),
        (0.0, 0.0),
    )

    def thesis_budget(self, conviction: float) -> float:
        """Fraction of total equity to allocate to a thesis at this conviction."""
        c = max(0.0, min(100.0, float(conviction)))
        for threshold, budget in self.LADDER:
            if c >= threshold:
                return budget
        return 0.0

    def thesis_budget_from_prob(self, p_direction: float) -> float:
        """Budget from a CALIBRATED probability (ATHENA_PROB_SIZING path).

        Conviction is demoted to governance under this path — it gates
        eligibility and reviews, never size.
        """
        p = max(0.0, min(1.0, float(p_direction)))
        for threshold, budget in self.PROB_LADDER:
            if p >= threshold:
                return budget
        return 0.0

    def vehicle_weights(self, budget: float, symbols: list[str]) -> dict[str, float]:
        """Split a thesis budget across its vehicles.

        Phase 2: equal weight (auditable). Concentration tilt toward
        outperformers is a later refinement (TRADING_PATTERNS rule 3:
        start equal, concentrate only after 10%+ outperformance).
        """
        syms = [s for s in dict.fromkeys(symbols) if s]  # dedupe, preserve order
        if not syms or budget <= 0:
            return {}
        per = budget / len(syms)
        return {s: per for s in syms}
