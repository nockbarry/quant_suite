#!/usr/bin/env python3
"""Bootstrap thesis objects for secondary Athena instances (beta, gamma).

Reads position data from the instance's state.json, groups by sector/theme,
and creates basic thesis objects via ThesisTracker. Sets initial conviction
based on position size (larger = higher conviction).

Usage:
    QUANT_RESULTS_DIR=~/quant_results_beta ATHENA_INSTANCE=beta \
        PYTHONPATH=. python3 scripts/bootstrap_instance_theses.py

    QUANT_RESULTS_DIR=~/quant_results_gamma ATHENA_INSTANCE=gamma \
        PYTHONPATH=. python3 scripts/bootstrap_instance_theses.py
"""

import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

# Must be set before importing src modules
results_dir = os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results"))
instance_name = os.environ.get("ATHENA_INSTANCE", "default")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from src.core.paths import paths
from src.knowledge.thesis import ThesisTracker
from src.risk.stress_tester import SYMBOL_SECTOR_MAP

# Sector display names and generic thesis templates
SECTOR_THESIS_TEMPLATES = {
    "energy": {
        "name": "Energy Exposure",
        "summary": "Broad energy sector exposure through oil/gas equities and ETFs.",
        "bull_case": "Supply constraints, geopolitical risk premium, rising demand.",
        "bear_case": "Demand destruction, recession, ceasefire/diplomatic resolution.",
    },
    "gold": {
        "name": "Gold / Precious Metals",
        "summary": "Gold and gold miner exposure as inflation hedge and safe haven.",
        "bull_case": "De-dollarization, central bank buying, real rate compression.",
        "bear_case": "Rising real rates, risk-on rotation, ETF liquidation cascade.",
    },
    "tankers": {
        "name": "Tanker / Shipping",
        "summary": "Tanker and shipping equities benefiting from trade rerouting.",
        "bull_case": "Chokepoint disruption, longer voyages, rate spikes.",
        "bear_case": "Peace deal, fleet oversupply, demand decline.",
    },
    "defense": {
        "name": "Defense Spending",
        "summary": "Defense contractors and services benefiting from increased budgets.",
        "bull_case": "Geopolitical escalation, NATO spending mandates, modernization.",
        "bear_case": "Peace dividend, budget sequestration, contract delays.",
    },
    "tech": {
        "name": "Technology / AI",
        "summary": "Technology sector exposure through megacap and semiconductor names.",
        "bull_case": "AI capex cycle, earnings growth, rate cuts.",
        "bear_case": "Valuation compression, regulation, capex slowdown.",
    },
    "fertilizer": {
        "name": "Fertilizer / Agriculture",
        "summary": "Fertilizer producers benefiting from supply disruption and food security.",
        "bull_case": "Hormuz disruption, spring planting demand, food inflation.",
        "bear_case": "Supply normalization, demand destruction, trade deals.",
    },
    "materials": {
        "name": "Materials / Copper / Rare Earth",
        "summary": "Materials sector exposure through copper, rare earth, and industrial metals.",
        "bull_case": "AI infrastructure demand, supply deficits, green transition.",
        "bear_case": "China slowdown, recession, substitution.",
    },
    "utilities": {
        "name": "Utilities / Nuclear",
        "summary": "Utilities and nuclear energy exposure.",
        "bull_case": "AI power demand, nuclear renaissance, rate cuts.",
        "bear_case": "Regulatory risk, rising rates, construction delays.",
    },
    "em": {
        "name": "Emerging Markets",
        "summary": "Emerging market equity exposure.",
        "bull_case": "Commodity tailwinds, USD weakness, reform momentum.",
        "bear_case": "Risk-off, USD strength, political instability.",
    },
    "em_debt": {
        "name": "EM Debt",
        "summary": "Emerging market debt exposure.",
        "bull_case": "Yield premium, improving credit, easing cycle.",
        "bear_case": "USD strength, default risk, capital flight.",
    },
    "consumer": {
        "name": "Consumer / Discretionary",
        "summary": "Consumer discretionary and homebuilder exposure.",
        "bull_case": "Strong employment, rate cuts, pent-up demand.",
        "bear_case": "Recession, inflation squeeze, consumer confidence decline.",
    },
    "financials": {
        "name": "Financials",
        "summary": "Financial sector exposure through banks and brokers.",
        "bull_case": "Yield curve steepening, credit growth, deregulation.",
        "bear_case": "Credit losses, rate compression, recession.",
    },
    "volatility": {
        "name": "Volatility Hedge",
        "summary": "Long volatility positions as portfolio hedge.",
        "bull_case": "Crisis escalation, correlation spike, tail events.",
        "bear_case": "Contango decay, low-vol regime, time decay.",
    },
    "reits": {
        "name": "REITs",
        "summary": "Real estate investment trust exposure.",
        "bull_case": "Rate cuts, occupancy recovery, income demand.",
        "bear_case": "Rising rates, remote work, oversupply.",
    },
    "crypto": {
        "name": "Crypto / Stablecoin",
        "summary": "Crypto infrastructure and stablecoin ecosystem exposure.",
        "bull_case": "Regulatory clarity, institutional adoption, network growth.",
        "bear_case": "Regulatory crackdown, security breach, depegging risk.",
    },
}


def load_state(state_path: Path) -> dict:
    """Load state.json from the instance's results directory."""
    if not state_path.exists():
        logger.error(f"State file not found: {state_path}")
        sys.exit(1)

    with open(state_path) as f:
        return json.load(f)


def group_positions_by_sector(positions: list[dict]) -> dict[str, list[dict]]:
    """Group positions by sector using SYMBOL_SECTOR_MAP."""
    groups = defaultdict(list)
    for pos in positions:
        symbol = pos.get("symbol", "")
        sector = SYMBOL_SECTOR_MAP.get(symbol, "other")
        groups[sector].append(pos)
    return dict(groups)


def compute_conviction(positions: list[dict], total_equity: float) -> float:
    """Compute conviction based on position size relative to portfolio.

    Larger positions imply higher conviction. Maps weight to 40-85 range.
    """
    if total_equity <= 0:
        return 50.0

    total_weight = sum(
        abs(float(pos.get("market_value", 0))) for pos in positions
    ) / total_equity * 100

    # Map: 0-2% -> 40, 2-5% -> 50, 5-10% -> 60, 10-20% -> 70, 20%+ -> 80
    if total_weight >= 20:
        return 80.0
    elif total_weight >= 10:
        return 70.0
    elif total_weight >= 5:
        return 60.0
    elif total_weight >= 2:
        return 50.0
    else:
        return 40.0


def main():
    state_path = paths.live_state
    logger.info(f"Instance: {instance_name}")
    logger.info(f"Results dir: {results_dir}")
    logger.info(f"State file: {state_path}")

    # Load state
    state = load_state(state_path)
    positions = state.get("positions", [])
    portfolio = state.get("portfolio", {})
    equity = float(portfolio.get("equity", 0))

    if not positions:
        logger.warning("No positions found in state.json")
        return

    logger.info(f"Found {len(positions)} positions, equity=${equity:,.0f}")

    # Group by sector
    groups = group_positions_by_sector(positions)
    logger.info(f"Grouped into {len(groups)} sectors: {list(groups.keys())}")

    # Initialize thesis tracker (respects QUANT_RESULTS_DIR via paths)
    tracker = ThesisTracker()

    # Check existing theses to avoid duplicates
    existing = tracker.get_all_theses()
    existing_names = {t.name for t in existing}
    logger.info(f"Existing theses: {len(existing)} ({', '.join(existing_names) or 'none'})")

    created = 0
    skipped = 0

    for sector, sector_positions in sorted(groups.items()):
        template = SECTOR_THESIS_TEMPLATES.get(sector)
        if not template:
            # Create a generic thesis for unknown sectors
            template = {
                "name": f"{sector.title()} Exposure",
                "summary": f"Positions in the {sector} sector.",
                "bull_case": "Sector tailwinds and position fundamentals.",
                "bear_case": "Sector headwinds and macro risk.",
            }

        thesis_name = f"[{instance_name.upper()}] {template['name']}"

        # Skip if thesis already exists
        if thesis_name in existing_names:
            logger.info(f"  SKIP {thesis_name} (already exists)")
            skipped += 1
            continue

        # Compute conviction from position weight
        conviction = compute_conviction(sector_positions, equity)

        # Get symbols in this group
        symbols = [p.get("symbol", "") for p in sector_positions]
        total_value = sum(abs(float(p.get("market_value", 0))) for p in sector_positions)
        weight_pct = (total_value / equity * 100) if equity > 0 else 0

        logger.info(
            f"  CREATE {thesis_name}: "
            f"{len(symbols)} positions, "
            f"${total_value:,.0f} ({weight_pct:.1f}%), "
            f"conviction={conviction:.0f}%"
        )

        thesis = tracker.create_thesis(
            name=thesis_name,
            summary=f"{template['summary']} "
                    f"Instance {instance_name}: {len(symbols)} positions, "
                    f"${total_value:,.0f} ({weight_pct:.1f}% of portfolio).",
            bull_case=template["bull_case"],
            bear_case=template["bear_case"],
            conviction=conviction,
            positions=symbols,
            review_interval_days=14,
        )

        logger.info(f"    -> Thesis ID: {thesis.id}, symbols: {symbols}")
        created += 1

    logger.info(f"\nDone: {created} theses created, {skipped} skipped (already exist)")
    logger.info(f"Total theses now: {len(tracker.get_all_theses())}")


if __name__ == "__main__":
    main()
