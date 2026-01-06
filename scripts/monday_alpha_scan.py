#!/usr/bin/env python3
"""
Alpha Discovery Scan for Monday, January 6, 2026

Scans for:
1. Momentum anomalies
2. Mean reversion setups
3. Volume divergences
4. Sector rotation opportunities
5. Gap opportunities (weekend moves)

Outputs specific trade ideas with entry/exit levels.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.alpha_discovery.market_scanner import MarketScanner, InefficiencyType

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def calculate_gap_opportunities(scanner: MarketScanner):
    """Identify potential gap opportunities based on Friday close."""
    logger.info("Calculating gap opportunities...")

    gap_signals = []
    symbols = ['SPY', 'QQQ', 'IWM', 'NVDA', 'AMD', 'AAPL', 'MSFT', 'TSLA',
               'META', 'GOOGL', 'AMZN', 'XLE', 'XLF', 'XLK']

    for symbol in symbols:
        data = await scanner._get_price_data(symbol, 60)
        if data is None or len(data) < 20:
            continue

        # Calculate average gap size over past 20 days
        data['Gap'] = (data['Open'] - data['Close'].shift(1)) / data['Close'].shift(1)
        avg_gap = data['Gap'].tail(20).abs().mean()

        # Calculate volatility
        returns = data['Close'].pct_change()
        volatility = returns.std() * np.sqrt(252)

        # Get latest price levels
        friday_close = data['Close'].iloc[-1]
        friday_high = data['High'].iloc[-1]
        friday_low = data['Low'].iloc[-1]

        # Calculate key levels
        atr = data['High'].tail(14) - data['Low'].tail(14)
        atr_value = atr.mean()

        gap_signals.append({
            'symbol': symbol,
            'friday_close': friday_close,
            'friday_high': friday_high,
            'friday_low': friday_low,
            'avg_gap_pct': avg_gap * 100,
            'volatility_annual': volatility * 100,
            'atr': atr_value,
            'support': friday_close - atr_value,
            'resistance': friday_close + atr_value,
        })

    return gap_signals


async def calculate_entry_exit_levels(scanner: MarketScanner, signal):
    """Calculate specific entry, stop, and target levels for a signal."""
    symbol = signal.symbol
    data = await scanner._get_price_data(symbol, 60)

    if data is None or len(data) < 20:
        return None

    current_price = data['Close'].iloc[-1]

    # Calculate ATR for stops and targets
    atr = (data['High'].tail(14) - data['Low'].tail(14)).mean()

    # Calculate support/resistance
    high_20d = data['High'].tail(20).max()
    low_20d = data['Low'].tail(20).min()

    # Mean and std for mean reversion trades
    ma_20 = data['Close'].tail(20).mean()
    std_20 = data['Close'].tail(20).std()

    levels = {
        'current_price': round(current_price, 2),
        'atr': round(atr, 2),
        'support_20d': round(low_20d, 2),
        'resistance_20d': round(high_20d, 2),
        'ma_20': round(ma_20, 2),
        'upper_band': round(ma_20 + 2*std_20, 2),
        'lower_band': round(ma_20 - 2*std_20, 2),
    }

    # Direction-specific levels
    if signal.direction == "long":
        levels['entry'] = round(current_price * 1.002, 2)  # Slight pullback
        levels['stop'] = round(current_price - 1.5*atr, 2)
        levels['target_1'] = round(current_price + atr, 2)
        levels['target_2'] = round(current_price + 2*atr, 2)

        # For mean reversion longs, target the MA
        if signal.inefficiency_type == InefficiencyType.MEAN_REVERSION:
            levels['target_1'] = round(ma_20, 2)
            levels['target_2'] = round(ma_20 + std_20, 2)

    elif signal.direction == "short":
        levels['entry'] = round(current_price * 0.998, 2)  # Slight bounce
        levels['stop'] = round(current_price + 1.5*atr, 2)
        levels['target_1'] = round(current_price - atr, 2)
        levels['target_2'] = round(current_price - 2*atr, 2)

        # For mean reversion shorts, target the MA
        if signal.inefficiency_type == InefficiencyType.MEAN_REVERSION:
            levels['target_1'] = round(ma_20, 2)
            levels['target_2'] = round(ma_20 - std_20, 2)

    return levels


async def generate_trade_report():
    """Generate comprehensive trade report for Monday."""

    print("=" * 80)
    print("ALPHA DISCOVERY SCAN - Monday, January 6, 2026")
    print("=" * 80)
    print(f"Scan Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    scanner = MarketScanner()

    # Define liquid universe for trading
    liquid_symbols = [
        # Indices
        'SPY', 'QQQ', 'IWM', 'DIA',
        # Tech Mega Cap
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA',
        # Semiconductors
        'AMD', 'INTC', 'MU', 'QCOM', 'AVGO', 'MRVL', 'AMAT',
        # Energy
        'XOM', 'CVX', 'COP', 'SLB', 'XLE',
        # Financials
        'JPM', 'BAC', 'GS', 'MS', 'XLF',
        # Sector ETFs
        'XLK', 'XLV', 'XLI', 'XLY',
    ]

    # 1. COMPREHENSIVE MARKET SCAN
    print("Phase 1: Running comprehensive market scan...")
    print("-" * 80)

    result = await scanner.scan_all(
        universes=['tech_mega', 'semiconductors', 'energy', 'financials'],
        include_sectors=True
    )

    print(f"Symbols Scanned: {result.symbols_scanned}")
    print(f"Total Opportunities Found: {len(result.inefficiencies_found)}")
    print()

    # 2. MARKET SUMMARY
    print("=" * 80)
    print("MARKET SUMMARY")
    print("=" * 80)
    print(f"Long Signals: {result.market_summary['long_signals']}")
    print(f"Short Signals: {result.market_summary['short_signals']}")
    print(f"Neutral Signals: {result.market_summary['neutral_signals']}")
    print(f"Average Expected Edge: {result.market_summary['avg_expected_edge']*100:.2f}%")
    print()
    print("By Signal Type:")
    for sig_type, count in result.market_summary['by_type'].items():
        if count > 0:
            print(f"  {sig_type}: {count}")
    print()

    # 3. GAP OPPORTUNITIES
    print("=" * 80)
    print("GAP OPPORTUNITIES (Friday Close Analysis)")
    print("=" * 80)
    gap_signals = await calculate_gap_opportunities(scanner)

    for gap in sorted(gap_signals, key=lambda x: x['volatility_annual'], reverse=True)[:10]:
        print(f"\n{gap['symbol']}:")
        print(f"  Friday Close: ${gap['friday_close']:.2f}")
        print(f"  Support Level: ${gap['support']:.2f}")
        print(f"  Resistance Level: ${gap['resistance']:.2f}")
        print(f"  Avg Gap Size: {gap['avg_gap_pct']:.2f}%")
        print(f"  Annual Volatility: {gap['volatility_annual']:.1f}%")

    print()

    # 4. TOP TRADE IDEAS
    print("=" * 80)
    print("TOP 10 TRADE IDEAS FOR MONDAY")
    print("=" * 80)
    print()

    trade_ideas = []

    for i, signal in enumerate(result.top_opportunities[:10], 1):
        levels = await calculate_entry_exit_levels(scanner, signal)

        if levels is None:
            continue

        trade_idea = {
            'rank': i,
            'signal': signal,
            'levels': levels,
        }
        trade_ideas.append(trade_idea)

        print(f"{i}. {signal.symbol} - {signal.inefficiency_type.value.upper()}")
        print(f"   Direction: {signal.direction.upper()}")
        print(f"   Strength: {signal.strength:.2f} | Confidence: {signal.confidence:.2f}")
        print(f"   Research Priority: {signal.research_priority:.3f}")
        print(f"   Expected Edge: {signal.expected_edge*100:.2f}%")
        print(f"   {signal.description}")
        print()
        print(f"   TRADING PLAN:")
        print(f"   Current Price: ${levels['current_price']}")
        print(f"   Entry: ${levels.get('entry', 'N/A')}")
        print(f"   Stop Loss: ${levels.get('stop', 'N/A')}")
        print(f"   Target 1: ${levels.get('target_1', 'N/A')}")
        print(f"   Target 2: ${levels.get('target_2', 'N/A')}")
        print(f"   Key Levels: MA20=${levels['ma_20']:.2f}, Support=${levels['support_20d']:.2f}, Resistance=${levels['resistance_20d']:.2f}")
        print(f"   Suggested Strategy: {signal.suggested_strategy}")
        print()
        print("-" * 80)

    # 5. SECTOR ROTATION ANALYSIS
    print()
    print("=" * 80)
    print("SECTOR ROTATION ANALYSIS")
    print("=" * 80)

    sector_signals = [s for s in result.inefficiencies_found
                      if s.inefficiency_type == InefficiencyType.SECTOR_ROTATION]

    if sector_signals:
        for signal in sorted(sector_signals, key=lambda x: x.strength, reverse=True):
            print(f"\n{signal.symbol}: {signal.description}")
            print(f"  Direction: {signal.direction.upper()}, Strength: {signal.strength:.2f}")
            print(f"  Expected Edge: {signal.expected_edge*100:.2f}%")
    else:
        print("No significant sector rotation detected.")

    # 6. MOMENTUM VS MEAN REVERSION BREAKDOWN
    print()
    print("=" * 80)
    print("OPPORTUNITY BREAKDOWN")
    print("=" * 80)

    momentum_signals = [s for s in result.inefficiencies_found
                        if s.inefficiency_type == InefficiencyType.MOMENTUM_ANOMALY]
    reversion_signals = [s for s in result.inefficiencies_found
                         if s.inefficiency_type == InefficiencyType.MEAN_REVERSION]
    volume_signals = [s for s in result.inefficiencies_found
                      if s.inefficiency_type == InefficiencyType.VOLUME_DIVERGENCE]

    print(f"\nMomentum Opportunities ({len(momentum_signals)}):")
    for signal in sorted(momentum_signals, key=lambda x: x.research_priority, reverse=True)[:5]:
        print(f"  {signal.symbol}: {signal.direction.upper()}, priority={signal.research_priority:.3f}")

    print(f"\nMean Reversion Opportunities ({len(reversion_signals)}):")
    for signal in sorted(reversion_signals, key=lambda x: x.research_priority, reverse=True)[:5]:
        print(f"  {signal.symbol}: {signal.direction.upper()}, priority={signal.research_priority:.3f}")

    print(f"\nVolume Divergences ({len(volume_signals)}):")
    for signal in sorted(volume_signals, key=lambda x: x.research_priority, reverse=True)[:5]:
        print(f"  {signal.symbol}: {signal.direction.upper()}, priority={signal.research_priority:.3f}")

    # 7. SAVE RESULTS
    output_dir = Path.home() / "quant_results" / "alpha_discovery"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"monday_scan_{timestamp}.json"

    # Prepare serializable output
    output_data = {
        'scan_time': datetime.now().isoformat(),
        'scan_date': '2026-01-06',
        'market_summary': result.market_summary,
        'trade_ideas': [
            {
                'rank': t['rank'],
                'symbol': t['signal'].symbol,
                'type': t['signal'].inefficiency_type.value,
                'direction': t['signal'].direction,
                'description': t['signal'].description,
                'strength': t['signal'].strength,
                'confidence': t['signal'].confidence,
                'expected_edge': t['signal'].expected_edge,
                'levels': t['levels'],
                'suggested_strategy': t['signal'].suggested_strategy,
            }
            for t in trade_ideas
        ],
        'gap_opportunities': gap_signals,
        'all_signals': [s.to_dict() for s in result.inefficiencies_found],
    }

    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2, default=str)

    print()
    print("=" * 80)
    print("ARTIFACTS")
    print("=" * 80)
    print(f"Results saved to: {output_file}")
    print()
    print("=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("1. Review top 3-5 trade ideas for Monday open")
    print("2. Set alerts for entry levels")
    print("3. Prepare orders with stop losses")
    print("4. Monitor overnight developments (futures, international markets)")
    print("5. Pass top opportunities to hypothesis-generator-agent for strategy development")
    print()

    return result


async def main():
    """Main entry point."""
    try:
        await generate_trade_report()
    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
