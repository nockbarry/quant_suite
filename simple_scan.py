#!/usr/bin/env python3
"""
Simplified January 2026 anomaly scan - runs quickly without async.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

try:
    import yfinance as yf
    import numpy as np
    import pandas as pd
except ImportError as e:
    print(f"Missing dependency: {e}")
    exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Key universes for scanning
TECH_MEGA = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
SEMICONDUCTORS = ["NVDA", "AMD", "INTC", "TSM", "MU", "QCOM", "AVGO"]
FINANCIALS = ["JPM", "BAC", "GS", "MS", "V", "MA"]
HEALTHCARE = ["UNH", "JNJ", "PFE", "ABBV", "LLY"]
INDUSTRIALS = ["CAT", "DE", "BA", "HON"]
ENERGY = ["XOM", "CVX", "COP"]
IWM_PROXY = ["IWM", "VB", "SLV"]  # Small-cap proxies

ALL_SYMBOLS = list(set(TECH_MEGA + SEMICONDUCTORS + FINANCIALS + HEALTHCARE + INDUSTRIALS + ENERGY + IWM_PROXY))

def fetch_data(symbol, period="60d"):
    """Fetch price data for a symbol."""
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period)
        if not data.empty:
            data.index = pd.to_datetime(data.index).tz_localize(None)
            return data
    except Exception as e:
        logger.warning(f"Failed to fetch {symbol}: {e}")
    return None

def calculate_rsi(closes, period=14):
    """Calculate RSI indicator."""
    delta = closes.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def scan_symbol(symbol):
    """Scan single symbol for anomalies."""
    opportunities = []

    data = fetch_data(symbol, "120d")
    if data is None or len(data) < 30:
        return opportunities

    close = data["Close"]

    # 1. MOMENTUM ANOMALY (z-score > 2)
    ret_60d = (close.iloc[-1] / close.iloc[-60] - 1) * 100 if len(close) >= 60 else None
    if ret_60d is not None:
        vol = close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252) * 100
        zscore = ret_60d / max(vol, 1)

        if abs(zscore) > 2.0:
            direction = "long" if zscore > 0 else "short"
            opportunities.append({
                "symbol": symbol,
                "type": "momentum_anomaly",
                "direction": direction,
                "zscore": round(zscore, 2),
                "momentum": round(ret_60d, 2),
                "volatility": round(vol, 2),
                "expected_edge": round(abs(ret_60d) * 0.3 / 100, 4),
                "confidence": round(0.5 + min(abs(zscore), 4) / 4 * 0.3, 2),
                "description": f"{symbol}: {ret_60d:+.1f}% momentum, z-score={zscore:.2f}",
            })

    # 2. MEAN REVERSION (RSI extreme + price deviation)
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    zscore_mr = (close.iloc[-1] - ma20.iloc[-1]) / std20.iloc[-1]
    rsi = calculate_rsi(close, 14)
    current_rsi = rsi.iloc[-1]

    if abs(zscore_mr) > 2.0 or current_rsi < 25 or current_rsi > 75:
        direction = "long" if zscore_mr < 0 or current_rsi < 30 else "short"
        opportunities.append({
            "symbol": symbol,
            "type": "mean_reversion",
            "direction": direction,
            "zscore": round(zscore_mr, 2),
            "rsi": round(current_rsi, 0),
            "expected_edge": round(abs(zscore_mr) * 0.02, 4),
            "confidence": round(0.6 if abs(zscore_mr) > 2.5 else 0.5, 2),
            "description": f"{symbol}: z-score={zscore_mr:.2f}, RSI={current_rsi:.0f}",
        })

    # 3. VOLUME DIVERGENCE (big move on low volume)
    if len(data) >= 20:
        price_change_20 = (close.iloc[-1] / close.iloc[-20] - 1) * 100
        avg_vol_recent = data["Volume"].tail(20).mean()
        avg_vol_prior = data["Volume"].iloc[-40:-20].mean()
        vol_ratio = avg_vol_recent / avg_vol_prior if avg_vol_prior > 0 else 1

        if abs(price_change_20) > 10 and vol_ratio < 0.8:
            direction = "short" if price_change_20 > 0 else "long"
            opportunities.append({
                "symbol": symbol,
                "type": "volume_divergence",
                "direction": direction,
                "price_change": round(price_change_20, 2),
                "volume_ratio": round(vol_ratio, 2),
                "expected_edge": round(abs(price_change_20) * 0.005, 4),
                "confidence": 0.55,
                "description": f"{symbol}: {price_change_20:+.1f}% move on {vol_ratio:.0%} volume",
            })

    # 4. JANUARY EFFECT - Small cap if applicable
    if symbol in ["IWM", "VB"]:
        # Compare to SPY
        spy_data = fetch_data("SPY", "120d")
        if spy_data is not None and len(spy_data) >= 20:
            symbol_ret_20 = (close.iloc[-1] / close.iloc[-20] - 1)
            spy_ret_20 = (spy_data["Close"].iloc[-1] / spy_data["Close"].iloc[-20] - 1)
            relative_perf = (symbol_ret_20 - spy_ret_20) * 100

            if relative_perf > 3:
                opportunities.append({
                    "symbol": symbol,
                    "type": "january_effect_small_cap",
                    "direction": "long",
                    "relative_perf": round(relative_perf, 2),
                    "expected_edge": round(abs(relative_perf) * 0.2 / 100, 4),
                    "confidence": 0.7,
                    "description": f"{symbol} outperforming SPY by {relative_perf:.1f}% (January Effect)",
                })

    return opportunities

# Main scan
logger.info("=" * 80)
logger.info("JANUARY 2026 MARKET ANOMALY SCAN")
logger.info("=" * 80)

all_opportunities = []

logger.info(f"Scanning {len(ALL_SYMBOLS)} symbols...")
for i, symbol in enumerate(ALL_SYMBOLS, 1):
    logger.info(f"[{i}/{len(ALL_SYMBOLS)}] Scanning {symbol}...")
    opps = scan_symbol(symbol)
    all_opportunities.extend(opps)

# Rank by expected alpha
ranked = sorted(
    all_opportunities,
    key=lambda x: x.get("expected_edge", 0) * x.get("confidence", 0),
    reverse=True
)

# Output
output_dir = Path("/home/nock/quant_results/alpha_discovery")
output_dir.mkdir(parents=True, exist_ok=True)

output_data = {
    "scan_timestamp": datetime.now().isoformat(),
    "symbols_scanned": len(ALL_SYMBOLS),
    "opportunities_found": len(all_opportunities),
    "top_opportunities": ranked[:30],
    "summary": {
        "by_type": {},
        "by_direction": {},
    }
}

# Count by type
for opp in all_opportunities:
    opp_type = opp["type"]
    output_data["summary"]["by_type"][opp_type] = output_data["summary"]["by_type"].get(opp_type, 0) + 1

    direction = opp["direction"]
    output_data["summary"]["by_direction"][direction] = output_data["summary"]["by_direction"].get(direction, 0) + 1

# Save JSON
output_file = output_dir / "january_2026_scan.json"
with open(output_file, "w") as f:
    json.dump(output_data, f, indent=2)

logger.info(f"\n{'='*80}")
logger.info("SCAN RESULTS")
logger.info(f"{'='*80}")
logger.info(f"Total opportunities found: {len(all_opportunities)}")
logger.info(f"By type: {output_data['summary']['by_type']}")
logger.info(f"By direction: {output_data['summary']['by_direction']}")

logger.info(f"\n{'='*80}")
logger.info("TOP 20 OPPORTUNITIES")
logger.info(f"{'='*80}")

for i, opp in enumerate(ranked[:20], 1):
    edge = opp.get("expected_edge", 0) * opp.get("confidence", 0)
    logger.info(f"\n{i}. {opp['symbol']} - {opp['type'].upper()}")
    logger.info(f"   Direction: {opp['direction'].upper()}")
    logger.info(f"   Expected Edge: {opp.get('expected_edge', 0)*100:.2f}%")
    logger.info(f"   Confidence: {opp.get('confidence', 0):.0%}")
    logger.info(f"   Description: {opp['description']}")

logger.info(f"\nResults saved to: {output_file}")
print("\nScan complete! Results available at:")
print(f"  {output_file}")
