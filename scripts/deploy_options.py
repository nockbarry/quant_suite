#!/usr/bin/env python3
"""
Venezuela Thesis - Options Portfolio Deployment

Deploys options strategies based on backtest validation:
- Calendar spreads (best performer: +25.9% avg on XLE)
- Diagonal spreads (VLO event: +5.6% avg)
- Call spreads for directional plays
- Strangles for volatility capture
- LEAPS for long-term thesis exposure

Usage:
    PYTHONPATH=. python scripts/deploy_options.py
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    GetOptionContractsRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, AssetClass

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/home/nock/quant_results/paper_trading")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class OptionsStrategy:
    """Options strategy configuration."""
    name: str
    symbol: str
    strategy_type: str  # "call_spread", "put_spread", "calendar", "diagonal", "strangle", "leap"
    thesis: str
    allocation: float  # Dollar amount to allocate
    target_pct: float
    stop_pct: float
    confidence: float
    params: dict  # Strategy-specific parameters


# Options strategies based on backtest results
OPTIONS_STRATEGIES = [
    # ============================================================
    # TIER 1: HIGH CONVICTION DIRECTIONAL (Call Spreads)
    # ============================================================
    OptionsStrategy(
        name="SLB Bull Call Spread",
        symbol="SLB",
        strategy_type="call_spread",
        thesis="Reconstruction leader - 15 rigs already in Venezuela",
        allocation=800,
        target_pct=1.00,  # 100% gain on spread
        stop_pct=-0.50,
        confidence=0.75,
        params={"dte": 60, "width": 5, "delta": 0.40},
    ),
    OptionsStrategy(
        name="HAL Bull Call Spread",
        symbol="HAL",
        strategy_type="call_spread",
        thesis="Oilfield services - well repair contracts",
        allocation=600,
        target_pct=1.00,
        stop_pct=-0.50,
        confidence=0.70,
        params={"dte": 60, "width": 3, "delta": 0.40},
    ),
    OptionsStrategy(
        name="BKR Bull Call Spread",
        symbol="BKR",
        strategy_type="call_spread",
        thesis="Baker Hughes - Big Four oilfield services",
        allocation=500,
        target_pct=0.80,
        stop_pct=-0.50,
        confidence=0.70,
        params={"dte": 45, "width": 5, "delta": 0.45},
    ),

    # ============================================================
    # TIER 2: REFINER PLAYS (Diagonal Spreads - best for gradual moves)
    # ============================================================
    OptionsStrategy(
        name="VLO Diagonal Spread",
        symbol="VLO",
        strategy_type="diagonal",
        thesis="Refiner margin expansion on heavy crude - gradual move",
        allocation=1000,
        target_pct=0.50,
        stop_pct=-0.40,
        confidence=0.80,
        params={"long_dte": 90, "short_dte": 30, "long_delta": 0.70, "short_delta": 0.30},
    ),
    OptionsStrategy(
        name="PSX Diagonal Spread",
        symbol="PSX",
        strategy_type="diagonal",
        thesis="Phillips 66 Gulf Coast refining",
        allocation=700,
        target_pct=0.50,
        stop_pct=-0.40,
        confidence=0.70,
        params={"long_dte": 90, "short_dte": 30, "long_delta": 0.70, "short_delta": 0.30},
    ),
    OptionsStrategy(
        name="MPC Diagonal Spread",
        symbol="MPC",
        strategy_type="diagonal",
        thesis="Marathon Petroleum refining capacity",
        allocation=600,
        target_pct=0.50,
        stop_pct=-0.40,
        confidence=0.65,
        params={"long_dte": 90, "short_dte": 30, "long_delta": 0.70, "short_delta": 0.30},
    ),

    # ============================================================
    # TIER 3: CALENDAR SPREADS (Best backtest: XLE +25.9%)
    # ============================================================
    OptionsStrategy(
        name="XLE Calendar Spread",
        symbol="XLE",
        strategy_type="calendar",
        thesis="Energy sector - best backtested strategy (+25.9% avg)",
        allocation=1200,
        target_pct=0.30,
        stop_pct=-0.25,
        confidence=0.72,
        params={"short_dte": 30, "long_dte": 60, "strike_offset": 0},
    ),
    OptionsStrategy(
        name="OIH Calendar Spread",
        symbol="OIH",
        strategy_type="calendar",
        thesis="Oil services ETF - broad exposure",
        allocation=600,
        target_pct=0.30,
        stop_pct=-0.25,
        confidence=0.65,
        params={"short_dte": 30, "long_dte": 60, "strike_offset": 0},
    ),

    # ============================================================
    # TIER 4: VOLATILITY PLAYS (Strangles for chaos events)
    # ============================================================
    OptionsStrategy(
        name="XLE Strangle",
        symbol="XLE",
        strategy_type="strangle",
        thesis="Energy vol play - ELN attacks, sabotage news spikes vol",
        allocation=800,
        target_pct=0.50,
        stop_pct=-0.40,
        confidence=0.60,
        params={"dte": 45, "put_delta": -0.25, "call_delta": 0.25},
    ),
    OptionsStrategy(
        name="GLD Strangle",
        symbol="GLD",
        strategy_type="strangle",
        thesis="Gold vol play - safe haven spikes on chaos",
        allocation=600,
        target_pct=0.50,
        stop_pct=-0.40,
        confidence=0.55,
        params={"dte": 45, "put_delta": -0.20, "call_delta": 0.20},
    ),

    # ============================================================
    # TIER 5: LEAPS (Long-term thesis conviction)
    # ============================================================
    OptionsStrategy(
        name="SLB LEAPS Call",
        symbol="SLB",
        strategy_type="leap",
        thesis="Long-term reconstruction play - 2+ year horizon",
        allocation=1000,
        target_pct=2.00,  # 200% target on LEAPS
        stop_pct=-0.50,
        confidence=0.75,
        params={"dte": 365, "delta": 0.60},
    ),
    OptionsStrategy(
        name="KBR LEAPS Call",
        symbol="KBR",
        strategy_type="leap",
        thesis="Defense reconstruction - Iraq precedent ($39.5B)",
        allocation=700,
        target_pct=2.00,
        stop_pct=-0.50,
        confidence=0.70,
        params={"dte": 365, "delta": 0.60},
    ),
    OptionsStrategy(
        name="VLO LEAPS Call",
        symbol="VLO",
        strategy_type="leap",
        thesis="Long-term refiner margin thesis",
        allocation=800,
        target_pct=1.50,
        stop_pct=-0.50,
        confidence=0.70,
        params={"dte": 365, "delta": 0.55},
    ),

    # ============================================================
    # TIER 6: CUBA DOMINO OPTIONS (Conditional plays)
    # ============================================================
    OptionsStrategy(
        name="RCL Bull Call Spread",
        symbol="RCL",
        strategy_type="call_spread",
        thesis="Cuba cruise routes if sanctions lift",
        allocation=400,
        target_pct=1.50,
        stop_pct=-0.60,
        confidence=0.55,
        params={"dte": 90, "width": 20, "delta": 0.35},
    ),
    OptionsStrategy(
        name="CCL Bull Call Spread",
        symbol="CCL",
        strategy_type="call_spread",
        thesis="Carnival Cuba exposure",
        allocation=400,
        target_pct=1.50,
        stop_pct=-0.60,
        confidence=0.55,
        params={"dte": 90, "width": 3, "delta": 0.35},
    ),

    # ============================================================
    # TIER 7: TANKER OPTIONS
    # ============================================================
    OptionsStrategy(
        name="FRO Bull Call Spread",
        symbol="FRO",
        strategy_type="call_spread",
        thesis="Frontline tanker rates from shadow fleet disruption",
        allocation=500,
        target_pct=1.00,
        stop_pct=-0.50,
        confidence=0.65,
        params={"dte": 60, "width": 2.5, "delta": 0.40},
    ),
    OptionsStrategy(
        name="STNG Bull Call Spread",
        symbol="STNG",
        strategy_type="call_spread",
        thesis="Scorpio tanker product rates",
        allocation=500,
        target_pct=1.00,
        stop_pct=-0.50,
        confidence=0.65,
        params={"dte": 60, "width": 5, "delta": 0.40},
    ),

    # ============================================================
    # TIER 8: GOLD/MINERALS OPTIONS
    # ============================================================
    OptionsStrategy(
        name="GDX Bull Call Spread",
        symbol="GDX",
        strategy_type="call_spread",
        thesis="Gold miners - Venezuela gold reserves access",
        allocation=500,
        target_pct=0.80,
        stop_pct=-0.50,
        confidence=0.65,
        params={"dte": 60, "width": 5, "delta": 0.40},
    ),
    OptionsStrategy(
        name="GLD LEAPS Call",
        symbol="GLD",
        strategy_type="leap",
        thesis="Long-term gold thesis - safe haven + reserves",
        allocation=600,
        target_pct=1.00,
        stop_pct=-0.50,
        confidence=0.60,
        params={"dte": 365, "delta": 0.50},
    ),

    # ============================================================
    # TIER 9: CANADIAN CRUDE OPTIONS (China Pivot)
    # ============================================================
    OptionsStrategy(
        name="CNQ Bull Call Spread",
        symbol="CNQ",
        strategy_type="call_spread",
        thesis="Canadian Natural - China pivot to Canadian heavy crude",
        allocation=500,
        target_pct=0.80,
        stop_pct=-0.50,
        confidence=0.65,
        params={"dte": 60, "width": 3, "delta": 0.40},
    ),
    OptionsStrategy(
        name="SU Bull Call Spread",
        symbol="SU",
        strategy_type="call_spread",
        thesis="Suncor - Oil sands, heavy crude premium",
        allocation=500,
        target_pct=0.80,
        stop_pct=-0.50,
        confidence=0.65,
        params={"dte": 60, "width": 3, "delta": 0.40},
    ),
]


def get_client():
    """Initialize Alpaca client."""
    with open("/home/nock/projects/quant_suite/config/credentials.yaml") as f:
        creds = yaml.safe_load(f)
    return TradingClient(
        creds["alpaca"]["api_key"],
        creds["alpaca"]["secret_key"],
        paper=True
    )


def get_option_chain(client, symbol: str, expiration_date: datetime) -> list:
    """Get option contracts for a symbol."""
    try:
        request = GetOptionContractsRequest(
            underlying_symbols=[symbol],
            expiration_date_gte=expiration_date.strftime("%Y-%m-%d"),
            expiration_date_lte=(expiration_date + timedelta(days=7)).strftime("%Y-%m-%d"),
        )
        contracts = client.get_option_contracts(request)
        return contracts.option_contracts if contracts else []
    except Exception as e:
        logger.warning(f"Could not get option chain for {symbol}: {e}")
        return []


def find_nearest_strike(contracts: list, target_strike: float, option_type: str) -> Optional[dict]:
    """Find the contract nearest to target strike."""
    filtered = [c for c in contracts if c.type.lower() == option_type.lower()]
    if not filtered:
        return None

    return min(filtered, key=lambda c: abs(float(c.strike_price) - target_strike))


def calculate_target_strike(current_price: float, delta: float, is_call: bool = True) -> float:
    """Estimate strike price from delta (rough approximation)."""
    # Rough approximation: ATM = 0.50 delta, move ~2% per 0.05 delta
    if is_call:
        offset = (0.50 - delta) * 0.40  # % offset from current price
    else:
        offset = (delta + 0.50) * 0.40

    return current_price * (1 + offset)


def deploy_options_portfolio(client):
    """Deploy options strategies."""
    account = client.get_account()

    print("\n" + "=" * 90)
    print("VENEZUELA THESIS - OPTIONS PORTFOLIO DEPLOYMENT")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)
    print(f"\nAccount Value: ${float(account.portfolio_value):,.2f}")
    print(f"Cash Available: ${float(account.cash):,.2f}")
    print(f"\nOptions strategies to deploy: {len(OPTIONS_STRATEGIES)}")

    total_allocation = sum(s.allocation for s in OPTIONS_STRATEGIES)
    print(f"Total options allocation: ${total_allocation:,.2f}")

    # Check if we have enough cash
    cash = float(account.cash)
    if cash < total_allocation:
        print(f"\nWARNING: Not enough cash (${cash:,.2f}) for full deployment (${total_allocation:,.2f})")
        print("Will deploy what we can...")

    executed = []
    failed = []
    simulated = []  # For strategies we can't execute directly

    print("\n" + "-" * 90)
    print(f"{'Strategy':<30} {'Symbol':<6} {'Type':<12} {'Alloc':>8} {'Status'}")
    print("-" * 90)

    for strategy in OPTIONS_STRATEGIES:
        try:
            # Try to get current price
            positions = client.get_all_positions()
            current_price = None
            for pos in positions:
                if pos.symbol == strategy.symbol:
                    current_price = float(pos.current_price)
                    break

            if current_price is None:
                # Need to get quote
                try:
                    from alpaca.data.historical import StockHistoricalDataClient
                    from alpaca.data.requests import StockLatestQuoteRequest

                    with open("/home/nock/projects/quant_suite/config/credentials.yaml") as f:
                        creds = yaml.safe_load(f)
                    data_client = StockHistoricalDataClient(
                        creds["alpaca"]["api_key"],
                        creds["alpaca"]["secret_key"]
                    )
                    quote = data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=[strategy.symbol]))
                    if strategy.symbol in quote:
                        current_price = float(quote[strategy.symbol].ask_price)
                except:
                    current_price = 50.0  # Default fallback

            # Calculate expiration dates
            if strategy.strategy_type == "leap":
                exp_date = datetime.now() + timedelta(days=strategy.params.get("dte", 365))
            else:
                exp_date = datetime.now() + timedelta(days=strategy.params.get("dte", 60))

            # Try to get option contracts
            contracts = get_option_chain(client, strategy.symbol, exp_date)

            if not contracts:
                # Can't get options - simulate the position
                simulated.append({
                    "strategy": strategy.name,
                    "symbol": strategy.symbol,
                    "type": strategy.strategy_type,
                    "allocation": strategy.allocation,
                    "thesis": strategy.thesis,
                    "target": strategy.target_pct,
                    "stop": strategy.stop_pct,
                    "current_price": current_price,
                    "simulated": True,
                    "reason": "Options chain not available",
                })
                print(f"{strategy.name:<30} {strategy.symbol:<6} {strategy.strategy_type:<12} ${strategy.allocation:>7,.0f} SIMULATED")
                continue

            # Execute based on strategy type
            if strategy.strategy_type == "call_spread":
                # Bull call spread: buy lower strike, sell higher strike
                long_strike = calculate_target_strike(current_price, strategy.params["delta"])
                short_strike = long_strike + strategy.params["width"]

                long_contract = find_nearest_strike(contracts, long_strike, "call")
                short_contract = find_nearest_strike(contracts, short_strike, "call")

                if long_contract and short_contract:
                    # Execute spread
                    # Buy long call
                    order1 = client.submit_order(MarketOrderRequest(
                        symbol=long_contract.symbol,
                        qty=1,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY,
                    ))
                    # Sell short call
                    order2 = client.submit_order(MarketOrderRequest(
                        symbol=short_contract.symbol,
                        qty=1,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.DAY,
                    ))

                    executed.append({
                        "strategy": strategy.name,
                        "symbol": strategy.symbol,
                        "type": strategy.strategy_type,
                        "long_contract": long_contract.symbol,
                        "short_contract": short_contract.symbol,
                        "orders": [str(order1.id), str(order2.id)],
                    })
                    print(f"{strategy.name:<30} {strategy.symbol:<6} {strategy.strategy_type:<12} ${strategy.allocation:>7,.0f} EXECUTED")
                else:
                    raise Exception("Could not find appropriate contracts")

            elif strategy.strategy_type == "leap":
                # Single LEAPS call
                strike = calculate_target_strike(current_price, strategy.params["delta"])
                contract = find_nearest_strike(contracts, strike, "call")

                if contract:
                    order = client.submit_order(MarketOrderRequest(
                        symbol=contract.symbol,
                        qty=1,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.DAY,
                    ))
                    executed.append({
                        "strategy": strategy.name,
                        "symbol": strategy.symbol,
                        "type": strategy.strategy_type,
                        "contract": contract.symbol,
                        "order": str(order.id),
                    })
                    print(f"{strategy.name:<30} {strategy.symbol:<6} {strategy.strategy_type:<12} ${strategy.allocation:>7,.0f} EXECUTED")
                else:
                    raise Exception("Could not find LEAPS contract")

            else:
                # Simulate other complex strategies
                simulated.append({
                    "strategy": strategy.name,
                    "symbol": strategy.symbol,
                    "type": strategy.strategy_type,
                    "allocation": strategy.allocation,
                    "thesis": strategy.thesis,
                    "target": strategy.target_pct,
                    "stop": strategy.stop_pct,
                    "current_price": current_price,
                    "simulated": True,
                    "reason": f"{strategy.strategy_type} requires manual execution",
                })
                print(f"{strategy.name:<30} {strategy.symbol:<6} {strategy.strategy_type:<12} ${strategy.allocation:>7,.0f} SIMULATED")

        except Exception as e:
            failed.append({
                "strategy": strategy.name,
                "symbol": strategy.symbol,
                "error": str(e),
            })
            print(f"{strategy.name:<30} {strategy.symbol:<6} {strategy.strategy_type:<12} ${strategy.allocation:>7,.0f} FAILED: {str(e)[:30]}")

    # Summary
    print("\n" + "=" * 90)
    print("DEPLOYMENT SUMMARY")
    print("=" * 90)
    print(f"Executed: {len(executed)}")
    print(f"Simulated: {len(simulated)}")
    print(f"Failed: {len(failed)}")

    # Save deployment log
    deployment = {
        "timestamp": datetime.now().isoformat(),
        "type": "options_deployment",
        "executed": executed,
        "simulated": simulated,
        "failed": failed,
        "total_allocation": total_allocation,
    }

    log_file = OUTPUT_DIR / f"options_deployment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, "w") as f:
        json.dump(deployment, f, indent=2)
    print(f"\nSaved to: {log_file}")

    return executed, simulated, failed


def create_synthetic_options_exposure(client):
    """
    Create synthetic options-like exposure using leveraged ETFs and equity positions.
    This is a fallback when direct options aren't available.
    """
    print("\n" + "=" * 90)
    print("CREATING SYNTHETIC OPTIONS EXPOSURE")
    print("=" * 90)

    # Leveraged/inverse ETFs that provide options-like exposure
    SYNTHETIC_POSITIONS = [
        # 2x/3x Leveraged Energy
        {"symbol": "ERX", "allocation": 500, "thesis": "2x Bull Energy - synthetic call exposure"},
        {"symbol": "GUSH", "allocation": 400, "thesis": "2x Bull Oil & Gas E&P"},

        # Leveraged Gold
        {"symbol": "NUGT", "allocation": 400, "thesis": "2x Bull Gold Miners - synthetic GDX call"},
        {"symbol": "UGL", "allocation": 300, "thesis": "2x Bull Gold - synthetic GLD call"},

        # Small position inverse for hedging (like buying puts)
        {"symbol": "ERY", "allocation": 200, "thesis": "2x Bear Energy - synthetic put hedge"},

        # VIX exposure (vol play like strangles)
        {"symbol": "VXX", "allocation": 300, "thesis": "VIX exposure - chaos event vol play"},
        {"symbol": "UVXY", "allocation": 200, "thesis": "1.5x VIX - amplified vol exposure"},
    ]

    executed = []
    failed = []

    for pos in SYNTHETIC_POSITIONS:
        try:
            order = client.submit_order(MarketOrderRequest(
                symbol=pos["symbol"],
                notional=pos["allocation"],
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            ))
            executed.append({
                "symbol": pos["symbol"],
                "allocation": pos["allocation"],
                "thesis": pos["thesis"],
                "order_id": str(order.id),
                "status": str(order.status),
            })
            print(f"[OK] {pos['symbol']}: ${pos['allocation']:,.0f} - {pos['thesis'][:40]}")
        except Exception as e:
            failed.append({
                "symbol": pos["symbol"],
                "error": str(e),
            })
            print(f"[FAIL] {pos['symbol']}: {e}")

    return executed, failed


def main():
    """Deploy options portfolio."""
    print("=" * 90)
    print("OPTIONS PORTFOLIO DEPLOYMENT")
    print("Based on Venezuela thesis backtest validation")
    print("=" * 90)

    client = get_client()

    # First try direct options
    print("\n[1/2] Attempting direct options deployment...")
    executed, simulated, failed = deploy_options_portfolio(client)

    # If most failed, use synthetic exposure
    if len(executed) < 5:
        print("\n[2/2] Creating synthetic options exposure with leveraged ETFs...")
        synth_executed, synth_failed = create_synthetic_options_exposure(client)

        print("\n" + "=" * 90)
        print("SYNTHETIC EXPOSURE SUMMARY")
        print("=" * 90)
        print(f"Synthetic positions created: {len(synth_executed)}")
        print(f"Failed: {len(synth_failed)}")

    # Print final portfolio summary
    print("\n" + "=" * 90)
    print("FINAL OPTIONS PORTFOLIO")
    print("=" * 90)

    # Print simulated strategies for tracking
    if simulated:
        print("\nSIMULATED STRATEGIES (track manually):")
        print("-" * 90)
        print(f"{'Strategy':<35} {'Symbol':<6} {'Type':<12} {'Alloc':>8} {'Target':>8}")
        print("-" * 90)
        for s in simulated:
            print(f"{s['strategy']:<35} {s['symbol']:<6} {s['type']:<12} ${s['allocation']:>7,.0f} {s['target']:>+7.0%}")

    print("\n" + "=" * 90)
    print("DEPLOYMENT COMPLETE")
    print("=" * 90)

    return executed, simulated, failed


if __name__ == "__main__":
    main()
