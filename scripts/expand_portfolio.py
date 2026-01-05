#!/usr/bin/env python3
"""
Venezuela Thesis - Expanded Portfolio Deployment

Deploys capital across all identified opportunities from comprehensive research:
- Tier 1: Core Venezuela thesis (oilfield services, refiners)
- Tier 2: Tanker/shipping plays
- Tier 3: Canadian heavy crude (China pivot)
- Tier 4: Cuba domino plays
- Tier 5: Defense logistics/reconstruction
- Tier 6: Gold/critical minerals
- Tier 7: EM/distressed debt exposure

Usage:
    PYTHONPATH=. python scripts/expand_portfolio.py
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/home/nock/quant_results/paper_trading")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Position:
    """Position configuration."""
    symbol: str
    allocation: float  # Percentage of portfolio
    thesis: str
    tier: str
    target_pct: float
    stop_pct: float
    confidence: float  # 0-1


# COMPREHENSIVE PORTFOLIO BASED ON ALL RESEARCH
EXPANDED_PORTFOLIO = {
    # ============================================================
    # TIER 1: CORE VENEZUELA THESIS (Already have - skip these)
    # ============================================================
    # SLB, VLO, HAL, XLE, FRO, GLD - Already deployed

    # ============================================================
    # TIER 1B: ADDITIONAL CORE PLAYS
    # ============================================================
    "BKR": Position(
        symbol="BKR",
        allocation=0.03,
        thesis="Baker Hughes - Big Four oilfield services, Venezuela equipment",
        tier="1B",
        target_pct=0.25,
        stop_pct=-0.15,
        confidence=0.70,
    ),
    "WFRD": Position(
        symbol="WFRD",
        allocation=0.02,
        thesis="Weatherford - In-country equipment, restructuring play",
        tier="1B",
        target_pct=0.30,
        stop_pct=-0.20,
        confidence=0.60,
    ),
    "PBF": Position(
        symbol="PBF",
        allocation=0.03,
        thesis="PBF Energy - Heavy crude refiner, margin expansion",
        tier="1B",
        target_pct=0.25,
        stop_pct=-0.15,
        confidence=0.65,
    ),
    "PSX": Position(
        symbol="PSX",
        allocation=0.03,
        thesis="Phillips 66 - Gulf Coast refining, Venezuelan crude feedstock",
        tier="1B",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.70,
    ),
    "MPC": Position(
        symbol="MPC",
        allocation=0.02,
        thesis="Marathon Petroleum - Refining capacity for heavy crude",
        tier="1B",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.65,
    ),

    # ============================================================
    # TIER 2: TANKER/SHIPPING PLAYS
    # Shadow fleet disruption, mainstream tanker rates elevated
    # ============================================================
    "STNG": Position(
        symbol="STNG",
        allocation=0.03,
        thesis="Scorpio Tankers - Product tanker rates elevated",
        tier="2",
        target_pct=0.25,
        stop_pct=-0.15,
        confidence=0.65,
    ),
    "DHT": Position(
        symbol="DHT",
        allocation=0.02,
        thesis="DHT Holdings - VLCC tanker rates, shadow fleet disruption",
        tier="2",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.60,
    ),
    "EURN": Position(
        symbol="EURN",
        allocation=0.02,
        thesis="Euronav - Crude tanker exposure, rate elevation",
        tier="2",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.60,
    ),
    "INSW": Position(
        symbol="INSW",
        allocation=0.02,
        thesis="International Seaways - Diversified tanker fleet",
        tier="2",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.60,
    ),

    # ============================================================
    # TIER 3: CANADIAN HEAVY CRUDE (China Pivot)
    # China loses 80% discount Venezuelan supplier, pivots to Canada
    # ============================================================
    "CNQ": Position(
        symbol="CNQ",
        allocation=0.03,
        thesis="Canadian Natural Resources - Heavy crude, China pivot",
        tier="3",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.65,
    ),
    "SU": Position(
        symbol="SU",
        allocation=0.03,
        thesis="Suncor Energy - Oil sands, heavy crude premium",
        tier="3",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.65,
    ),
    "IMO": Position(
        symbol="IMO",
        allocation=0.02,
        thesis="Imperial Oil - Canadian heavy crude, Exxon subsidiary",
        tier="3",
        target_pct=0.18,
        stop_pct=-0.10,
        confidence=0.60,
    ),

    # ============================================================
    # TIER 4: CUBA DOMINO PLAYS
    # If Cuba opens, cruise/hotel/travel stocks rally
    # ============================================================
    "RCL": Position(
        symbol="RCL",
        allocation=0.02,
        thesis="Royal Caribbean - Cuba cruise routes if sanctions lift",
        tier="4",
        target_pct=0.25,
        stop_pct=-0.15,
        confidence=0.55,
    ),
    "CCL": Position(
        symbol="CCL",
        allocation=0.02,
        thesis="Carnival - Cuba cruise exposure, had routes before 2019",
        tier="4",
        target_pct=0.25,
        stop_pct=-0.15,
        confidence=0.55,
    ),
    "NCLH": Position(
        symbol="NCLH",
        allocation=0.01,
        thesis="Norwegian Cruise - Cuba route optionality",
        tier="4",
        target_pct=0.25,
        stop_pct=-0.15,
        confidence=0.50,
    ),
    "MAR": Position(
        symbol="MAR",
        allocation=0.02,
        thesis="Marriott - Cuba hotel development if regime falls",
        tier="4",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.55,
    ),

    # ============================================================
    # TIER 5: DEFENSE LOGISTICS/RECONSTRUCTION
    # KBR got $39.5B in Iraq - similar opportunity
    # ============================================================
    "KBR": Position(
        symbol="KBR",
        allocation=0.03,
        thesis="KBR - Iraq reconstruction veteran, $39.5B contracts precedent",
        tier="5",
        target_pct=0.25,
        stop_pct=-0.15,
        confidence=0.70,
    ),
    "FLR": Position(
        symbol="FLR",
        allocation=0.02,
        thesis="Fluor Corporation - Infrastructure/engineering reconstruction",
        tier="5",
        target_pct=0.25,
        stop_pct=-0.15,
        confidence=0.65,
    ),
    "PSN": Position(
        symbol="PSN",
        allocation=0.02,
        thesis="Parsons Corporation - Government infrastructure contracts",
        tier="5",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.60,
    ),
    "J": Position(
        symbol="J",
        allocation=0.02,
        thesis="Jacobs Engineering - Government solutions, reconstruction",
        tier="5",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.60,
    ),

    # ============================================================
    # TIER 6: GOLD/CRITICAL MINERALS
    # Venezuela has 8,000+ tons untapped gold, coltan, rare earths
    # ============================================================
    "GDX": Position(
        symbol="GDX",
        allocation=0.03,
        thesis="VanEck Gold Miners ETF - Gold safe haven + Venezuela reserves",
        tier="6",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.65,
    ),
    "GOLD": Position(
        symbol="GOLD",
        allocation=0.02,
        thesis="Barrick Gold - Major miner, potential Venezuela access",
        tier="6",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.60,
    ),
    "NEM": Position(
        symbol="NEM",
        allocation=0.02,
        thesis="Newmont - Gold miner, LatAm exposure",
        tier="6",
        target_pct=0.18,
        stop_pct=-0.10,
        confidence=0.60,
    ),
    "REMX": Position(
        symbol="REMX",
        allocation=0.01,
        thesis="VanEck Rare Earth ETF - Coltan, rare earth access",
        tier="6",
        target_pct=0.25,
        stop_pct=-0.15,
        confidence=0.50,
    ),

    # ============================================================
    # TIER 7: EM/DISTRESSED DEBT EXPOSURE
    # Venezuelan bonds doubled (11->33 cents), could hit 50-60
    # ============================================================
    "EMB": Position(
        symbol="EMB",
        allocation=0.02,
        thesis="iShares EM Bond ETF - Some Venezuelan exposure",
        tier="7",
        target_pct=0.15,
        stop_pct=-0.10,
        confidence=0.55,
    ),
    "VWOB": Position(
        symbol="VWOB",
        allocation=0.02,
        thesis="Vanguard EM Govt Bond - Venezuelan bond exposure",
        tier="7",
        target_pct=0.15,
        stop_pct=-0.10,
        confidence=0.55,
    ),
    "EWZ": Position(
        symbol="EWZ",
        allocation=0.02,
        thesis="Brazil ETF - LatAm contagion play, could go either way",
        tier="7",
        target_pct=0.15,
        stop_pct=-0.10,
        confidence=0.50,
    ),

    # ============================================================
    # TIER 8: BROADER ENERGY SECTOR
    # General energy exposure for thesis validation
    # ============================================================
    "OIH": Position(
        symbol="OIH",
        allocation=0.02,
        thesis="VanEck Oil Services ETF - Broad oilfield services exposure",
        tier="8",
        target_pct=0.20,
        stop_pct=-0.12,
        confidence=0.65,
    ),
    "XOP": Position(
        symbol="XOP",
        allocation=0.02,
        thesis="SPDR Oil & Gas Exploration ETF - E&P exposure",
        tier="8",
        target_pct=0.18,
        stop_pct=-0.12,
        confidence=0.60,
    ),
    "IEO": Position(
        symbol="IEO",
        allocation=0.01,
        thesis="iShares US Oil & Gas Exploration ETF - E&P plays",
        tier="8",
        target_pct=0.18,
        stop_pct=-0.12,
        confidence=0.55,
    ),
}


def get_client():
    """Initialize Alpaca client."""
    with open("/home/nock/projects/quant_suite/config/credentials.yaml") as f:
        creds = yaml.safe_load(f)
    return TradingClient(
        creds["alpaca"]["api_key"],
        creds["alpaca"]["secret_key"],
        paper=True
    )


def get_current_positions(client):
    """Get current positions as dict."""
    positions = client.get_all_positions()
    return {p.symbol: float(p.market_value) for p in positions}


def deploy_expanded_portfolio(client, use_cash_only: bool = True):
    """Deploy expanded portfolio positions."""
    account = client.get_account()
    current_positions = get_current_positions(client)

    # Calculate available capital
    if use_cash_only:
        available_capital = float(account.cash)
    else:
        available_capital = float(account.portfolio_value)

    print("\n" + "=" * 80)
    print("VENEZUELA THESIS - EXPANDED PORTFOLIO DEPLOYMENT")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"\nAccount Value: ${float(account.portfolio_value):,.2f}")
    print(f"Available Cash: ${float(account.cash):,.2f}")
    print(f"Current Positions: {len(current_positions)}")
    print(f"\nNew positions to deploy: {len(EXPANDED_PORTFOLIO)}")

    # Calculate total allocation for new positions
    total_new_allocation = sum(p.allocation for p in EXPANDED_PORTFOLIO.values())
    print(f"Total new allocation: {total_new_allocation:.0%}")

    # Get current prices and calculate shares
    orders = []
    total_to_deploy = 0

    print("\n" + "-" * 80)
    print(f"{'Tier':<4} {'Symbol':<6} {'Alloc':<6} {'$Amount':<10} {'Thesis':<50}")
    print("-" * 80)

    for symbol, position in sorted(EXPANDED_PORTFOLIO.items(), key=lambda x: (x[1].tier, x[0])):
        # Skip if already have position
        if symbol in current_positions:
            print(f"{position.tier:<4} {symbol:<6} {position.allocation:.0%}    SKIP       Already have position")
            continue

        # Calculate dollar amount
        dollar_amount = available_capital * position.allocation

        if dollar_amount < 10:  # Minimum order
            print(f"{position.tier:<4} {symbol:<6} {position.allocation:.0%}    ${dollar_amount:<7.0f}  Too small")
            continue

        thesis_short = position.thesis[:48] + ".." if len(position.thesis) > 50 else position.thesis
        print(f"{position.tier:<4} {symbol:<6} {position.allocation:.0%}    ${dollar_amount:<7.0f}  {thesis_short}")

        orders.append({
            "symbol": symbol,
            "notional": round(dollar_amount, 2),
            "position": position,
        })
        total_to_deploy += dollar_amount

    print("-" * 80)
    print(f"Total to deploy: ${total_to_deploy:,.2f}")

    # Execute orders
    print("\n" + "=" * 80)
    print("EXECUTING ORDERS")
    print("=" * 80)

    executed_orders = []
    failed_orders = []

    for order_info in orders:
        symbol = order_info["symbol"]
        notional = order_info["notional"]
        position = order_info["position"]

        try:
            # Use notional (dollar amount) orders
            order = client.submit_order(MarketOrderRequest(
                symbol=symbol,
                notional=notional,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            ))

            executed_orders.append({
                "symbol": symbol,
                "notional": notional,
                "order_id": str(order.id),
                "status": str(order.status),
                "tier": position.tier,
                "thesis": position.thesis,
                "target": position.target_pct,
                "stop": position.stop_pct,
            })
            print(f"[OK] {symbol}: ${notional:,.0f} - {order.status}")

        except Exception as e:
            failed_orders.append({
                "symbol": symbol,
                "notional": notional,
                "error": str(e),
            })
            print(f"[FAIL] {symbol}: {e}")

    # Summary
    print("\n" + "=" * 80)
    print("DEPLOYMENT SUMMARY")
    print("=" * 80)
    print(f"Executed: {len(executed_orders)} orders")
    print(f"Failed: {len(failed_orders)} orders")
    print(f"Total deployed: ${sum(o['notional'] for o in executed_orders):,.2f}")

    # Save deployment log
    deployment_log = {
        "timestamp": datetime.now().isoformat(),
        "deployment_type": "expanded_portfolio",
        "account_value": float(account.portfolio_value),
        "cash_available": float(account.cash),
        "total_deployed": sum(o['notional'] for o in executed_orders),
        "executed_orders": executed_orders,
        "failed_orders": failed_orders,
        "positions_by_tier": {},
    }

    # Group by tier
    for order in executed_orders:
        tier = order["tier"]
        if tier not in deployment_log["positions_by_tier"]:
            deployment_log["positions_by_tier"][tier] = []
        deployment_log["positions_by_tier"][tier].append(order["symbol"])

    log_file = OUTPUT_DIR / f"expanded_deployment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, "w") as f:
        json.dump(deployment_log, f, indent=2)
    logger.info(f"Saved deployment log to {log_file}")

    return executed_orders, failed_orders


def print_portfolio_thesis():
    """Print thesis summary by tier."""
    print("\n" + "=" * 80)
    print("PORTFOLIO THESIS BY TIER")
    print("=" * 80)

    tiers = {}
    for symbol, pos in EXPANDED_PORTFOLIO.items():
        if pos.tier not in tiers:
            tiers[pos.tier] = []
        tiers[pos.tier].append((symbol, pos))

    tier_names = {
        "1B": "Additional Core Venezuela",
        "2": "Tanker/Shipping",
        "3": "Canadian Heavy Crude (China Pivot)",
        "4": "Cuba Domino",
        "5": "Defense Logistics/Reconstruction",
        "6": "Gold/Critical Minerals",
        "7": "EM/Distressed Debt",
        "8": "Broader Energy",
    }

    for tier in sorted(tiers.keys()):
        tier_total = sum(p.allocation for _, p in tiers[tier])
        print(f"\n### Tier {tier}: {tier_names.get(tier, 'Unknown')} ({tier_total:.0%} allocation)")
        print("-" * 60)
        for symbol, pos in tiers[tier]:
            print(f"  {symbol}: {pos.thesis}")
            print(f"       Target: {pos.target_pct:+.0%} | Stop: {pos.stop_pct:.0%} | Conf: {pos.confidence:.0%}")


def main():
    """Deploy expanded portfolio."""
    print("=" * 80)
    print("EXPANDED PORTFOLIO DEPLOYMENT")
    print("Based on comprehensive Venezuela thesis research")
    print("=" * 80)

    # Print thesis summary
    print_portfolio_thesis()

    # Connect and deploy
    client = get_client()
    executed, failed = deploy_expanded_portfolio(client)

    print("\n" + "=" * 80)
    print("DEPLOYMENT COMPLETE")
    print("=" * 80)
    print(f"\nTotal new positions: {len(executed)}")
    print(f"Total symbols now: {len(EXPANDED_PORTFOLIO) + 6}")  # +6 for existing
    print(f"\nUse monitor_loop.py to track performance")

    return executed, failed


if __name__ == "__main__":
    main()
