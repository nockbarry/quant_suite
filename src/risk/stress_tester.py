"""Portfolio Stress Tester.

Monte Carlo simulation engine with predefined crisis scenarios.
Computes portfolio VaR, expected shortfall, and cross-thesis correlation.

Scenarios:
- Ceasefire Flash Crash: energy -15%, gold -12%, tankers -20%, tech +10%
- Kharg Oil Terminal Strike: energy +20%, gold +8%, VIX +40%
- FOMC Dovish Surprise: gold -3%, financials +5%, tech +8%
- FOMC Hawkish + Oil Spike: gold -10%, energy +8%, tech -5%
- Gold Liquidation Crisis: gold -15%, miners -20%, energy +3%
- India-Iran Deal: energy -8%, tankers -12%, EM +5%

Usage:
    from src.risk.stress_tester import PortfolioStressTester
    tester = PortfolioStressTester()
    report = tester.run_full_report()
    print(f"95% VaR: {report.var_95_pct:.1f}%")
"""

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class ScenarioDefinition:
    """A predefined crisis scenario with sector-level shocks."""

    name: str
    description: str
    shocks: dict  # {sector_or_symbol: pct_impact}  e.g. {"energy": -0.15}
    probability: str  # "high", "medium", "low"


@dataclass
class ScenarioResult:
    """Result of applying a single scenario to the portfolio."""

    scenario_name: str
    portfolio_impact_pct: float
    portfolio_impact_usd: float
    worst_position: str
    worst_position_loss_usd: float
    best_position: str
    best_position_gain_usd: float
    positions_affected: int


@dataclass
class StressTestReport:
    """Full stress test output with scenarios, VaR, and recommendations."""

    timestamp: str
    portfolio_equity: float
    cash: float
    position_count: int
    scenario_results: list  # List of ScenarioResult dicts
    var_95_pct: float  # 1-day 95% Value at Risk as % of equity
    var_99_pct: float  # 1-day 99% VaR
    expected_shortfall_pct: float  # Conditional VaR (avg loss beyond 95% VaR)
    concentration_risk_score: float  # 0-1, higher = more concentrated (HHI-based)
    sector_weights: dict  # {sector: weight_pct}
    cross_thesis_correlations: dict  # {thesis_pair: correlation}  (future)
    max_single_sector_exposure_pct: float
    max_single_position_pct: float
    recommendations: list  # List of string recommendations


# ─── Predefined Scenarios ───────────────────────────────────────────

SCENARIOS = [
    ScenarioDefinition(
        name="Ceasefire Flash Crash",
        description="Diplomatic breakthrough leads to rapid energy/commodity unwind. "
                    "Oil drops $15, tanker rates collapse, gold gives back war premium, "
                    "tech rotates in on lower rates expectation.",
        shocks={
            "energy": -0.15, "gold": -0.12, "tankers": -0.20,
            "fertilizer": -0.10, "tech": 0.10, "defense": -0.03,
            "volatility": -0.25, "em": 0.04, "em_debt": 0.03,
        },
        probability="medium",
    ),
    ScenarioDefinition(
        name="Kharg Oil Terminal Strike",
        description="US/Israel strikes Iran's Kharg Island oil terminal (90% of Iran exports). "
                    "Brent to $130+, gold spikes, tanker rates surge, tech sells off on "
                    "inflation/rate fears.",
        shocks={
            "energy": 0.20, "gold": 0.08, "tankers": 0.15,
            "fertilizer": 0.12, "defense": 0.05, "tech": -0.08,
            "volatility": 0.40, "materials": 0.05, "em": -0.06,
            "em_debt": -0.04, "consumer": -0.05, "utilities": -0.02,
        },
        probability="medium",
    ),
    ScenarioDefinition(
        name="FOMC Dovish Surprise",
        description="Fed signals rate cuts despite oil-driven inflation. Markets rally "
                    "on easing expectations. Gold dips (real rates narrative), tech/growth "
                    "jumps, financials benefit from yield curve steepening.",
        shocks={
            "gold": -0.03, "financials": 0.05, "tech": 0.08,
            "energy": -0.02, "reits": 0.06, "consumer": 0.04,
            "em": 0.05, "em_debt": 0.04, "volatility": -0.15,
        },
        probability="low",
    ),
    ScenarioDefinition(
        name="FOMC Hawkish + Oil Spike",
        description="Fed holds rates or signals hikes while oil spikes on supply disruption. "
                    "Stagflation setup: gold liquidated on real-rate fears despite inflation, "
                    "energy surges, tech sells off on higher-for-longer. "
                    "Based on March 2026 actual: gold -10.3%, oil +8%.",
        shocks={
            "gold": -0.10, "energy": 0.08, "tech": -0.05,
            "financials": -0.03, "tankers": 0.05, "fertilizer": 0.06,
            "defense": 0.02, "volatility": 0.20, "consumer": -0.04,
            "em": -0.04, "em_debt": -0.03, "utilities": -0.02,
        },
        probability="medium",
    ),
    ScenarioDefinition(
        name="Gold Liquidation Crisis",
        description="2011-style gold crash: margin calls, ETF liquidation, momentum unwind. "
                    "Gold miners drop 1.3-1.5x of gold move. Energy benefits from rotation "
                    "into hard commodities with supply constraints. "
                    "Based on March 2026 FOMC + ceasefire combo.",
        shocks={
            "gold": -0.15, "energy": 0.03, "tech": 0.02,
            "financials": 0.01, "tankers": 0.02, "defense": 0.01,
            "volatility": 0.15, "materials": -0.05, "consumer": 0.01,
        },
        probability="low",
    ),
    ScenarioDefinition(
        name="India-Iran Bilateral Deal",
        description="Modi brokers partial Hormuz passage agreement for Indian tankers. "
                    "Crude spreads narrow, tanker premium collapses, EM benefits from "
                    "reduced energy costs.",
        shocks={
            "energy": -0.08, "tankers": -0.12, "fertilizer": -0.06,
            "em": 0.05, "gold": -0.02, "defense": -0.02,
            "materials": 0.02,
        },
        probability="low",
    ),
    ScenarioDefinition(
        name="Hormuz Full Closure",
        description="Iran closes Strait of Hormuz with naval mines. 21% global oil "
                    "and 33% fertilizer transits cut. Oil $150+, food crisis, "
                    "global recession risk.",
        shocks={
            "energy": 0.35, "gold": 0.15, "tankers": 0.30,
            "fertilizer": 0.25, "defense": 0.08, "tech": -0.15,
            "volatility": 0.60, "consumer": -0.12, "financials": -0.08,
            "em": -0.10, "em_debt": -0.08, "utilities": -0.05,
            "materials": 0.05,
        },
        probability="low",
    ),
    ScenarioDefinition(
        name="Broad Market Correction -10%",
        description="Systematic sell-off driven by recession fears. All risk assets "
                    "decline, gold and vol spike as safe havens.",
        shocks={
            "energy": -0.12, "tech": -0.14, "financials": -0.10,
            "consumer": -0.10, "defense": -0.06, "tankers": -0.08,
            "materials": -0.12, "em": -0.15, "em_debt": -0.08,
            "gold": 0.05, "volatility": 0.50, "utilities": -0.04,
            "fertilizer": -0.08,
        },
        probability="low",
    ),
]

# ─── Symbol → Sector Mapping ────────────────────────────────────────

SYMBOL_SECTOR_MAP = {
    # Energy
    "XLE": "energy", "SLB": "energy", "HAL": "energy", "XOP": "energy",
    "CNQ": "energy", "SU": "energy", "PBF": "energy", "MPC": "energy",
    "PSX": "energy", "BKR": "energy", "IMO": "energy", "GUSH": "energy",
    "ERX": "energy", "IEO": "energy", "WFRD": "energy", "OIH": "energy",
    "BNO": "energy", "USO": "energy",
    # Gold
    "GLD": "gold", "GDX": "gold", "GOLD": "gold", "NEM": "gold",
    "UGL": "gold", "NUGT": "gold", "IAU": "gold",
    # Tankers
    "FRO": "tankers", "DHT": "tankers", "INSW": "tankers", "STNG": "tankers",
    # Defense
    "NOC": "defense", "GD": "defense", "LMT": "defense", "RTX": "defense",
    "LHX": "defense", "KBR": "defense", "J": "defense", "FLR": "defense",
    "PSN": "defense", "EUAD": "defense",
    # Tech
    "NVDA": "tech", "GOOGL": "tech", "MU": "tech", "AMD": "tech",
    "AAPL": "tech", "MSFT": "tech", "META": "tech", "TSM": "tech",
    # Fertilizer
    "CF": "fertilizer", "MOS": "fertilizer", "NTR": "fertilizer",
    # Materials / Copper / Rare Earth
    "FCX": "materials", "COPX": "materials", "REMX": "materials",
    # Utilities / Nuclear
    "NEE": "utilities", "LEU": "utilities", "CCJ": "utilities",
    # EM / Brazil
    "PBR": "em", "ITUB": "em", "EWZ": "em",
    "EMB": "em_debt", "VWOB": "em_debt",
    # Consumer
    "MAR": "consumer", "AXP": "consumer",
    # Financials
    "JPM": "financials", "GS": "financials",
    # Volatility
    "UVXY": "volatility", "VXX": "volatility",
    # REITs
    "O": "reits", "AMT": "reits",
    # Crypto / Stablecoin
    "COIN": "crypto", "MSTR": "crypto",
    # Homebuilders
    "LEN": "consumer", "DHI": "consumer",
}


class PortfolioStressTester:
    """Run scenario analysis and Monte Carlo VaR on the portfolio.

    Reads positions from state.json, applies predefined crisis scenarios,
    and runs Monte Carlo simulation for VaR/ES estimates.
    """

    def __init__(self, state_path: Optional[Path] = None, scenarios: Optional[list] = None):
        self.state_path = state_path or paths.live_state
        self.report_dir = paths.risk_reports
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.scenarios = scenarios or SCENARIOS

    def load_portfolio(self) -> tuple:
        """Load positions and portfolio info from state.json.

        Returns:
            (portfolio_dict, positions_list) from state.json
        """
        with open(self.state_path) as f:
            state = json.load(f)
        portfolio = state.get("portfolio", {})
        positions = state.get("positions", [])
        return portfolio, positions

    @staticmethod
    def _get_sector(symbol: str) -> str:
        """Map a symbol to its sector for scenario application."""
        return SYMBOL_SECTOR_MAP.get(symbol, "other")

    def run_scenario(
        self, scenario: ScenarioDefinition, positions: list, equity: float
    ) -> ScenarioResult:
        """Apply scenario shocks to portfolio positions.

        Each position's market value is shocked by its sector's scenario multiplier.
        Returns the aggregate portfolio impact and worst/best positions.
        """
        total_impact = 0.0
        worst_sym = ""
        worst_loss = 0.0
        best_sym = ""
        best_gain = 0.0
        affected = 0

        for pos in positions:
            sym = pos.get("symbol", "")
            mv = float(pos.get("market_value", 0))
            sector = self._get_sector(sym)

            # Check for direct symbol shock first, then sector
            shock = scenario.shocks.get(sym, scenario.shocks.get(sector, 0))

            if shock != 0:
                impact = mv * shock
                total_impact += impact
                affected += 1

                if impact < worst_loss:
                    worst_loss = impact
                    worst_sym = sym
                if impact > best_gain:
                    best_gain = impact
                    best_sym = sym

        return ScenarioResult(
            scenario_name=scenario.name,
            portfolio_impact_pct=round(total_impact / equity * 100, 2) if equity else 0,
            portfolio_impact_usd=round(total_impact, 2),
            worst_position=worst_sym,
            worst_position_loss_usd=round(worst_loss, 2),
            best_position=best_sym,
            best_position_gain_usd=round(best_gain, 2),
            positions_affected=affected,
        )

    def compute_concentration(self, positions: list, equity: float) -> tuple:
        """Compute sector concentration risk score using Herfindahl-Hirschman Index.

        Returns:
            (hhi_score_0_to_1, sector_weights_dict, max_position_pct)
        """
        sector_weights = {}
        max_pos_pct = 0.0

        for pos in positions:
            sector = self._get_sector(pos.get("symbol", ""))
            mv = float(pos.get("market_value", 0))
            sector_weights[sector] = sector_weights.get(sector, 0) + mv

            if equity > 0:
                pos_pct = mv / equity * 100
                if pos_pct > max_pos_pct:
                    max_pos_pct = pos_pct

        if not sector_weights or equity == 0:
            return 0.0, {}, 0.0

        # HHI normalized to 0-1
        weights = [v / equity for v in sector_weights.values()]
        hhi = sum(w ** 2 for w in weights)
        n = max(len(weights), 1)
        if n > 1:
            score = (hhi - 1 / n) / (1 - 1 / n)
        else:
            score = 1.0

        score = min(max(score, 0), 1)

        # Convert to percentage weights for display
        sector_pcts = {
            k: round(v / equity * 100, 1)
            for k, v in sorted(sector_weights.items(), key=lambda x: -x[1])
        }

        return score, sector_pcts, max_pos_pct

    def run_monte_carlo(
        self, positions: list, equity: float, n_simulations: int = 10000
    ) -> dict:
        """Run Monte Carlo simulation using sector-level volatility estimates.

        Uses conservative volatility assumptions calibrated to crisis regimes.
        Returns 95% VaR, 99% VaR, and Expected Shortfall as % of portfolio.
        """
        if not positions or equity == 0:
            return {"var_95": 0.0, "var_99": 0.0, "es": 0.0}

        np.random.seed(42)

        # Build sector weight vector
        sector_weights = {}
        for pos in positions:
            sector = self._get_sector(pos.get("symbol", ""))
            mv = float(pos.get("market_value", 0))
            sector_weights[sector] = sector_weights.get(sector, 0) + mv / equity

        # Crisis-regime daily volatility estimates (annualized / sqrt(252))
        # These are deliberately conservative (high) for stress testing
        sector_vols = {
            "energy": 0.035,
            "gold": 0.020,
            "tankers": 0.045,
            "defense": 0.018,
            "tech": 0.030,
            "fertilizer": 0.032,
            "materials": 0.025,
            "utilities": 0.012,
            "em": 0.028,
            "em_debt": 0.015,
            "consumer": 0.018,
            "financials": 0.022,
            "volatility": 0.080,
            "reits": 0.015,
            "crypto": 0.050,
            "other": 0.020,
        }

        # Add cross-sector correlation via common market factor
        # 50% of each sector's return is from common factor, 50% idiosyncratic
        market_vol = 0.015  # ~1.5% daily market vol in crisis
        common_factor = np.random.normal(0, market_vol, n_simulations)

        portfolio_returns = np.zeros(n_simulations)
        for sector, weight in sector_weights.items():
            vol = sector_vols.get(sector, 0.02)
            # Idiosyncratic component
            idio_vol = vol * 0.7  # 70% idiosyncratic
            idio = np.random.normal(0, idio_vol, n_simulations)
            # Sector return = beta * market + idio
            beta = vol / market_vol * 0.3  # 30% systematic
            sector_return = beta * common_factor + idio
            portfolio_returns += weight * sector_return

        sorted_returns = np.sort(portfolio_returns)
        var_95 = -sorted_returns[int(0.05 * n_simulations)]
        var_99 = -sorted_returns[int(0.01 * n_simulations)]
        tail = sorted_returns[: int(0.05 * n_simulations)]
        es = -np.mean(tail) if len(tail) > 0 else var_95

        return {
            "var_95": round(var_95 * 100, 2),
            "var_99": round(var_99 * 100, 2),
            "es": round(es * 100, 2),
        }

    def _generate_recommendations(
        self,
        scenario_results: list,
        mc: dict,
        conc_score: float,
        sector_pcts: dict,
        max_pos_pct: float,
    ) -> list:
        """Generate actionable recommendations from stress test results."""
        recs = []

        # Concentration warnings
        if conc_score > 0.35:
            recs.append(
                f"HIGH concentration risk (HHI score={conc_score:.2f}). "
                f"Portfolio is heavily concentrated in few sectors."
            )
        elif conc_score > 0.2:
            recs.append(
                f"Moderate concentration risk (HHI score={conc_score:.2f}). "
                f"Consider adding uncorrelated positions."
            )

        # Sector exposure
        for sector, pct in sector_pcts.items():
            if pct > 40:
                recs.append(
                    f"Sector '{sector}' at {pct:.1f}% exceeds 40% threshold. "
                    f"Consider trimming or hedging."
                )

        # Single position
        if max_pos_pct > 10:
            recs.append(
                f"Largest single position at {max_pos_pct:.1f}% exceeds 10% limit."
            )

        # VaR
        if mc["var_95"] > 4:
            recs.append(
                f"1-day 95% VaR is {mc['var_95']:.1f}% — significantly elevated. "
                f"Consider reducing leverage or adding hedges."
            )
        elif mc["var_95"] > 2.5:
            recs.append(
                f"1-day 95% VaR is {mc['var_95']:.1f}% — moderately elevated."
            )

        # Scenario-specific
        for sr in scenario_results:
            impact = sr["portfolio_impact_pct"]
            if impact < -15:
                recs.append(
                    f"CRITICAL: Scenario '{sr['scenario_name']}' shows "
                    f"{impact:+.1f}% portfolio impact. Hedging recommended."
                )
            elif impact < -8:
                recs.append(
                    f"Scenario '{sr['scenario_name']}' has {impact:+.1f}% impact. "
                    f"Monitor closely and consider tail hedges."
                )

        if not recs:
            recs.append("Portfolio risk profile within acceptable parameters.")

        return recs

    def run_full_report(self) -> StressTestReport:
        """Run all scenarios + Monte Carlo + concentration analysis.

        Returns a comprehensive StressTestReport and saves to disk.
        """
        portfolio, positions = self.load_portfolio()
        equity = float(portfolio.get("equity", 0))
        cash = float(portfolio.get("cash", 0))

        logger.info(
            f"Running stress test: equity=${equity:,.0f}, "
            f"cash=${cash:,.0f}, positions={len(positions)}"
        )

        # Scenario analysis
        scenario_results = []
        for scenario in self.scenarios:
            result = self.run_scenario(scenario, positions, equity)
            scenario_results.append(asdict(result))
            logger.info(
                f"  Scenario '{scenario.name}': {result.portfolio_impact_pct:+.1f}% "
                f"(${result.portfolio_impact_usd:+,.0f})"
            )

        # Monte Carlo VaR
        mc = self.run_monte_carlo(positions, equity)
        logger.info(
            f"  Monte Carlo: VaR95={mc['var_95']:.1f}%, "
            f"VaR99={mc['var_99']:.1f}%, ES={mc['es']:.1f}%"
        )

        # Concentration analysis
        conc_score, sector_pcts, max_pos_pct = self.compute_concentration(
            positions, equity
        )
        max_sector_pct = max(sector_pcts.values()) if sector_pcts else 0
        logger.info(
            f"  Concentration: HHI={conc_score:.2f}, "
            f"max sector={max_sector_pct:.1f}%, max position={max_pos_pct:.1f}%"
        )

        # Recommendations
        recs = self._generate_recommendations(
            scenario_results, mc, conc_score, sector_pcts, max_pos_pct
        )

        report = StressTestReport(
            timestamp=datetime.now().isoformat(),
            portfolio_equity=equity,
            cash=cash,
            position_count=len(positions),
            scenario_results=scenario_results,
            var_95_pct=mc["var_95"],
            var_99_pct=mc["var_99"],
            expected_shortfall_pct=mc["es"],
            concentration_risk_score=round(conc_score, 3),
            sector_weights=sector_pcts,
            cross_thesis_correlations={},  # TODO: implement with price history
            max_single_sector_exposure_pct=round(max_sector_pct, 1),
            max_single_position_pct=round(max_pos_pct, 1),
            recommendations=recs,
        )

        # Save report with timestamp
        report_file = self.report_dir / (
            f"stress_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, "w") as f:
            json.dump(asdict(report), f, indent=2)
        logger.info(f"Stress test report saved: {report_file}")

        # Also save as latest for web dashboard
        latest_file = self.report_dir / "stress_test_latest.json"
        with open(latest_file, "w") as f:
            json.dump(asdict(report), f, indent=2)

        return report
