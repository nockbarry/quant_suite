"""
Alpha Discovery: News-Driven Opportunity Scan

Scan for specific opportunities based on recent market news:
1. Bank stocks oversold (COF, AXP, SYF) - Trump credit card rate cap
2. TSMC equipment (AMAT, LRCX, KLAC) - Taiwan trade deal
3. Construction materials (VMC, MLM, BLDR) - LA rebuild
4. Gold miners (GDX, NEM, GOLD) - Fed independence threat
5. Venezuela energy plays - Maduro captured

Focus on:
- Technical signals (RSI oversold, momentum)
- Unusual options activity
- Insider buying
- Congressional trades
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.alpha_discovery.market_scanner import MarketScanner, InefficiencyType
from src.core.paths import paths

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# OPPORTUNITY DEFINITIONS
# =============================================================================

OPPORTUNITIES = {
    "bank_oversold": {
        "thesis": "Trump credit card rate cap proposal - banks oversold",
        "rationale": "Rate cap requires Congress, unlikely to pass. Technical oversold bounce.",
        "symbols": ["COF", "AXP", "SYF", "ALLY"],
        "catalyst": "Market overreaction to unlikely legislation",
        "entry_signal": "RSI < 30 or -5%+ in 2 days",
        "risk": "Proposal gains traction in Congress",
    },
    "tsmc_equipment": {
        "thesis": "TSMC equipment beneficiaries - Taiwan trade deal",
        "rationale": "5+ new fabs in Arizona = multi-year equipment orders",
        "symbols": ["AMAT", "LRCX", "KLAC", "ASML", "ENTG"],
        "catalyst": "Taiwan trade deal, fab construction",
        "entry_signal": "Momentum confirmation + options flow",
        "risk": "Fab delays or funding issues",
    },
    "construction_materials": {
        "thesis": "LA wildfire rebuild - construction materials",
        "rationale": "$250B damage, 900 homes under construction, multi-year rebuild",
        "symbols": ["VMC", "MLM", "BLDR", "HD", "LOW"],
        "catalyst": "Wildfire damage + rebuild spending",
        "entry_signal": "Sector momentum + volume confirmation",
        "risk": "Rebuild slower than expected",
    },
    "gold_fed_risk": {
        "thesis": "Gold - Fed independence threat",
        "rationale": "DOJ Powell investigation threatens Fed independence. Banks forecasting $4,500-$5,400 gold.",
        "symbols": ["GDX", "NEM", "GOLD", "AEM", "WPM", "FNV"],
        "catalyst": "Fed independence concerns + safe haven demand",
        "entry_signal": "Gold momentum + miner relative strength",
        "risk": "Investigation dismissed",
    },
    "venezuela_energy": {
        "thesis": "Venezuela energy recovery - Maduro captured",
        "rationale": "Regime change accelerates sanctions relief and oil production",
        "symbols": ["SLB", "HAL", "BKR", "FRO", "STNG", "DHT", "INSW", "TGS", "PBR", "XLE"],
        "catalyst": "Maduro captured, sanctions relief expectations",
        "entry_signal": "Any new beneficiaries beyond current holdings",
        "risk": "Political instability continues",
    },
}


# =============================================================================
# TECHNICAL ANALYSIS
# =============================================================================

async def analyze_technicals(scanner: MarketScanner, symbols: list[str]) -> pd.DataFrame:
    """Analyze technical indicators for symbols."""
    results = []

    for symbol in symbols:
        try:
            data = await scanner._get_price_data(symbol, days=60)
            if data is None or len(data) < 20:
                continue

            # Current price and returns
            current_price = data['Close'].iloc[-1]
            return_1d = (data['Close'].iloc[-1] / data['Close'].iloc[-2] - 1) * 100
            return_5d = (data['Close'].iloc[-1] / data['Close'].iloc[-6] - 1) * 100
            return_20d = (data['Close'].iloc[-1] / data['Close'].iloc[-21] - 1) * 100

            # RSI
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]

            # Volatility
            returns = data['Close'].pct_change()
            volatility = returns.std() * (252 ** 0.5) * 100

            # Volume analysis
            avg_volume = data['Volume'].tail(20).mean()
            recent_volume = data['Volume'].tail(5).mean()
            volume_ratio = recent_volume / avg_volume

            # Bollinger Bands
            ma20 = data['Close'].rolling(20).mean().iloc[-1]
            std20 = data['Close'].rolling(20).std().iloc[-1]
            bb_upper = ma20 + 2 * std20
            bb_lower = ma20 - 2 * std20
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)

            # MACD
            ema12 = data['Close'].ewm(span=12).mean()
            ema26 = data['Close'].ewm(span=26).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9).mean()
            macd_hist = macd.iloc[-1] - signal.iloc[-1]

            results.append({
                'symbol': symbol,
                'price': current_price,
                'return_1d': return_1d,
                'return_5d': return_5d,
                'return_20d': return_20d,
                'rsi': current_rsi,
                'volatility': volatility,
                'volume_ratio': volume_ratio,
                'bb_position': bb_position,
                'macd_hist': macd_hist,
                'oversold': current_rsi < 30,
                'overbought': current_rsi > 70,
                'high_volume': volume_ratio > 1.5,
            })

        except Exception as e:
            logger.warning(f"Failed to analyze {symbol}: {e}")
            continue

    return pd.DataFrame(results)


# =============================================================================
# OPPORTUNITY SCANNER
# =============================================================================

async def scan_opportunity(scanner: MarketScanner, opp_name: str, opp_data: dict):
    """Scan a specific opportunity."""
    print(f"\n{'='*80}")
    print(f"OPPORTUNITY: {opp_name.upper()}")
    print(f"{'='*80}")
    print(f"Thesis: {opp_data['thesis']}")
    print(f"Rationale: {opp_data['rationale']}")
    print(f"Catalyst: {opp_data['catalyst']}")
    print(f"Entry Signal: {opp_data['entry_signal']}")
    print(f"Risk: {opp_data['risk']}")
    print(f"\nSymbols: {', '.join(opp_data['symbols'])}")

    # Technical analysis
    print(f"\n--- Technical Analysis ---")
    technicals = await analyze_technicals(scanner, opp_data['symbols'])

    if technicals.empty:
        print("No technical data available")
        return []

    # Sort by research priority based on opportunity type
    if opp_name == "bank_oversold":
        # Prioritize most oversold
        technicals = technicals.sort_values('rsi')
    elif opp_name in ["tsmc_equipment", "construction_materials"]:
        # Prioritize momentum + volume
        technicals['momentum_score'] = technicals['return_20d'] * technicals['volume_ratio']
        technicals = technicals.sort_values('momentum_score', ascending=False)
    elif opp_name == "gold_fed_risk":
        # Prioritize relative strength
        technicals = technicals.sort_values('return_20d', ascending=False)
    else:
        # General sorting by return
        technicals = technicals.sort_values('return_20d', ascending=False)

    # Print top opportunities
    for _, row in technicals.head(10).iterrows():
        symbol = row['symbol']
        price = row['price']
        rsi = row['rsi']
        ret_5d = row['return_5d']
        ret_20d = row['return_20d']
        vol_ratio = row['volume_ratio']

        print(f"\n{symbol}: ${price:.2f}")
        print(f"  Returns: 5d={ret_5d:+.1f}%, 20d={ret_20d:+.1f}%")
        print(f"  RSI: {rsi:.1f}", end="")
        if row['oversold']:
            print(" [OVERSOLD]", end="")
        if row['overbought']:
            print(" [OVERBOUGHT]", end="")
        print()
        print(f"  Volume Ratio: {vol_ratio:.2f}x", end="")
        if row['high_volume']:
            print(" [HIGH]")
        else:
            print()
        print(f"  BB Position: {row['bb_position']:.2%}")
        print(f"  MACD Hist: {row['macd_hist']:.2f}")

    # Run market scanner on these symbols
    print(f"\n--- Market Inefficiency Scan ---")
    momentum_signals = await scanner.scan_momentum_anomalies(opp_data['symbols'])
    reversion_signals = await scanner.scan_mean_reversion(opp_data['symbols'])
    volume_signals = await scanner.scan_volume_divergence(opp_data['symbols'])

    all_signals = momentum_signals + reversion_signals + volume_signals

    if all_signals:
        print(f"Found {len(all_signals)} inefficiency signals:")
        for sig in sorted(all_signals, key=lambda x: x.research_priority, reverse=True)[:5]:
            print(f"\n  {sig.symbol} - {sig.inefficiency_type.value}")
            print(f"    Direction: {sig.direction.upper()}")
            print(f"    Strength: {sig.strength:.2f}, Confidence: {sig.confidence:.2f}")
            print(f"    Expected Edge: {sig.expected_edge*100:.1f}%")
            print(f"    {sig.description}")
    else:
        print("No significant inefficiency signals detected")

    return all_signals


# =============================================================================
# MAIN SCAN
# =============================================================================

async def main():
    """Run comprehensive news-driven opportunity scan."""
    print("="*80)
    print("ALPHA DISCOVERY: NEWS-DRIVEN OPPORTUNITIES")
    print("="*80)
    print(f"Scan Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")

    scanner = MarketScanner()

    all_signals = []

    # Scan each opportunity
    for opp_name, opp_data in OPPORTUNITIES.items():
        signals = await scan_opportunity(scanner, opp_name, opp_data)
        all_signals.extend(signals)

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total Signals: {len(all_signals)}")

    # Top opportunities across all themes
    print(f"\nTOP 10 OPPORTUNITIES (by priority):")
    ranked = sorted(all_signals, key=lambda x: x.research_priority, reverse=True)

    for i, sig in enumerate(ranked[:10], 1):
        print(f"\n{i}. {sig.symbol} - {sig.inefficiency_type.value}")
        print(f"   Direction: {sig.direction.upper()}")
        print(f"   Priority: {sig.research_priority:.3f}")
        print(f"   Expected Edge: {sig.expected_edge*100:.1f}%")
        print(f"   Suggested Strategy: {sig.suggested_strategy}")
        print(f"   {sig.description}")

    # By theme
    print(f"\n\nBY THEME:")
    theme_counts = {}
    for opp_name, opp_data in OPPORTUNITIES.items():
        symbols = set(opp_data['symbols'])
        count = sum(1 for sig in all_signals if sig.symbol in symbols)
        theme_counts[opp_name] = count
        print(f"  {opp_name}: {count} signals")

    # Export results
    output_dir = paths.quant_results / "alpha_discovery"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"news_scan_{timestamp}.json"

    import json
    scan_result = {
        "scan_time": datetime.now().isoformat(),
        "opportunities": OPPORTUNITIES,
        "total_signals": len(all_signals),
        "theme_counts": theme_counts,
        "top_signals": [sig.to_dict() for sig in ranked[:20]],
    }

    with open(output_file, 'w') as f:
        json.dump(scan_result, f, indent=2)

    print(f"\n\nResults saved to: {output_file}")

    print(f"\n{'='*80}")
    print("NEXT STEPS:")
    print("1. Review top opportunities above")
    print("2. Check for congressional/insider activity on these symbols")
    print("3. Validate with /research agent for promising setups")
    print("4. Use /trade-decision for entry/exit planning")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
