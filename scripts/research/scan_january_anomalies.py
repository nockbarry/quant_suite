#!/usr/bin/env python3
"""
JANUARY 2026 MARKET ANOMALY SCAN
================================
Comprehensive market inefficiency scanner focusing on:
1. January Effect (small caps, tax-loss rebounds)
2. Earnings season positioning
3. Sector rotation signals
4. Options market anomalies
5. Momentum divergences (price vs breadth/volume)
6. Mean reversion setups (oversold quality, overbought junk)

Uses the AlphaDiscovery MarketScanner with regime detection.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/home/nock/quant_results/alpha_discovery/scan_jan_2026.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Import from codebase
from src.alpha_discovery import MarketScanner, InefficiencyType
from src.strategies.regime.regime_classifier import EmpiricalRegimeClassifier

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    logger.warning("yfinance not installed - some features disabled")


# =============================================================================
# JANUARY EFFECT SCANNER
# =============================================================================

class JanuaryEffectScanner:
    """Detects January Effect patterns: small caps, tax-loss rebounds, rotation."""

    # Small-cap ETFs and proxies
    SMALL_CAP_UNIVERSE = {
        "direct_etfs": ["IWM", "VB", "IJH"],  # Russell 2000, Vanguard Small-Cap, Mid-Cap
        "beaten_down_growth": ["COIN", "DASH", "PINS", "SNAP", "SOFI"],
        "tax_loss_targets": ["TSLA", "NVDA", "ARM", "INTC", "NFLX"],  # High-vol mega-caps
        "quality_value": ["JNJ", "PG", "KO", "MCD", "UNH"],  # Defensive
    }

    def __init__(self):
        self.results = []

    async def scan_small_cap_vs_mega(self):
        """Small-cap outperformance in January (January Effect)."""
        try:
            # Get IWM (Russell 2000) and SPY price data
            data_iwm = yf.Ticker("IWM").history(period="60d")
            data_spy = yf.Ticker("SPY").history(period="60d")

            if data_iwm.empty or data_spy.empty:
                logger.warning("Could not fetch IWM/SPY data")
                return

            iwm_ret = data_iwm["Close"].pct_change(20).iloc[-1] * 100
            spy_ret = data_spy["Close"].pct_change(20).iloc[-1] * 100
            relative_perf = iwm_ret - spy_ret

            logger.info(f"IWM 20d return: {iwm_ret:.2f}%")
            logger.info(f"SPY 20d return: {spy_ret:.2f}%")
            logger.info(f"Relative performance: {relative_perf:+.2f}%")

            if relative_perf > 3:
                self.results.append({
                    "signal": "january_effect_small_cap_strength",
                    "description": f"Small-caps (IWM) outperforming mega-caps (SPY) by {relative_perf:.1f}%",
                    "direction": "long_small_cap",
                    "expected_edge": abs(relative_perf) * 0.2 / 100,
                    "confidence": 0.7,
                    "strategy": "long IWM / short SPY pairs trade",
                })
                logger.info(f"January Effect detected: Small caps outperforming")

        except Exception as e:
            logger.error(f"Small-cap scan failed: {e}")

    async def scan_beaten_down_recovery(self):
        """Tax-loss harvesting rebounds at year-end (Dec/Jan)."""
        try:
            symbols = self.SMALL_CAP_UNIVERSE["beaten_down_growth"]
            scanner = MarketScanner()

            for symbol in symbols:
                data = await scanner._get_price_data(symbol, 60)
                if data is None or len(data) < 30:
                    continue

                # Look for 20%+ declines that could be rebounding
                ytd_return = (data["Close"].iloc[-1] / data["Close"].iloc[0] - 1) * 100
                vol_20d = data["Close"].pct_change().rolling(20).std().iloc[-1] * np.sqrt(252) * 100

                if ytd_return < -15 and vol_20d > 40:
                    # Tax-loss harvesting rebound candidate
                    self.results.append({
                        "signal": "tax_loss_rebound",
                        "symbol": symbol,
                        "description": f"{symbol}: Down {ytd_return:.1f}% YTD, high vol {vol_20d:.0f}%, recovery candidate",
                        "direction": "long",
                        "expected_edge": abs(ytd_return) * 0.15 / 100,
                        "confidence": 0.6,
                        "strategy": "mean_reversion on beaten-down growth",
                    })
                    logger.info(f"{symbol}: Tax-loss rebound candidate")

        except Exception as e:
            logger.error(f"Tax-loss rebound scan failed: {e}")


# =============================================================================
# EARNINGS SEASON SCANNER
# =============================================================================

class EarningsSeasonScanner:
    """Identifies earnings season positioning and sentiment extremes."""

    # Rough earnings calendar for Q4 earnings (January/February)
    EARNINGS_CALENDAR = {
        "banks": ["JPM", "BAC", "WFC", "MS", "GS"],  # Early January
        "tech": ["GOOGL", "META", "MSFT", "AAPL", "AMZN"],  # Mid-January
        "semiconductors": ["NVDA", "AMD", "QCOM", "INTC", "MU"],  # Mid-January
        "industrials": ["CAT", "DE", "BA", "HON"],  # Late January
    }

    async def scan_pre_earnings(self):
        """Find stocks trading on sentiment extremes pre-earnings."""
        results = []
        scanner = MarketScanner()

        try:
            for sector, symbols in self.EARNINGS_CALENDAR.items():
                logger.info(f"Scanning {sector} sector pre-earnings")

                for symbol in symbols:
                    data = await scanner._get_price_data(symbol, 60)
                    if data is None or len(data) < 14:
                        continue

                    # RSI to detect sentiment extremes
                    close = data["Close"]
                    delta = close.diff()
                    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]

                    # Volatility
                    vol = close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252) * 100

                    if current_rsi > 70:
                        results.append({
                            "signal": "pre_earnings_overbought",
                            "symbol": symbol,
                            "sector": sector,
                            "description": f"{symbol}: Overbought (RSI={current_rsi:.0f}) ahead of earnings",
                            "direction": "short",
                            "expected_edge": 0.03,
                            "confidence": 0.65,
                            "strategy": "short into overbought earnings",
                        })
                        logger.info(f"{symbol}: Overbought pre-earnings ({rsi.iloc[-1]:.0f})")

                    elif current_rsi < 30:
                        results.append({
                            "signal": "pre_earnings_oversold",
                            "symbol": symbol,
                            "sector": sector,
                            "description": f"{symbol}: Oversold (RSI={current_rsi:.0f}) ahead of earnings",
                            "direction": "long",
                            "expected_edge": 0.03,
                            "confidence": 0.65,
                            "strategy": "long into oversold quality stock",
                        })
                        logger.info(f"{symbol}: Oversold pre-earnings ({rsi.iloc[-1]:.0f})")

        except Exception as e:
            logger.error(f"Earnings scan failed: {e}")

        return results


# =============================================================================
# MOMENTUM DIVERGENCE SCANNER
# =============================================================================

class MomentumDivergenceScanner:
    """Detects price/volume and price/breadth divergences."""

    async def scan_volume_price_divergence(self, symbols: list[str]):
        """Find price moves without volume confirmation."""
        results = []
        scanner = MarketScanner()

        try:
            for symbol in symbols:
                data = await scanner._get_price_data(symbol, 40)
                if data is None or len(data) < 20:
                    continue

                # 5-day price change vs volume ratio
                price_change = data["Close"].pct_change(5).iloc[-1]
                volume_5d_avg = data["Volume"].tail(5).mean()
                volume_20d_avg = data["Volume"].iloc[-30:-10].mean()
                volume_ratio = volume_5d_avg / volume_20d_avg if volume_20d_avg > 0 else 1

                # Large move with low volume = weak move, reversal risk
                if abs(price_change) > 0.05 and volume_ratio < 0.8:
                    direction = "short" if price_change > 0 else "long"
                    self.results.append({
                        "signal": "volume_price_divergence",
                        "symbol": symbol,
                        "description": f"{symbol}: {price_change*100:.1f}% move on {volume_ratio:.1%} volume - weak conviction",
                        "direction": direction,
                        "expected_edge": abs(price_change) * 0.4 / 100,
                        "confidence": 0.6,
                        "strategy": "fade weak moves on low volume",
                    })
                    logger.info(f"{symbol}: Volume-price divergence detected")

        except Exception as e:
            logger.error(f"Volume divergence scan failed: {e}")

        return results


# =============================================================================
# MAIN SCANNING FUNCTION
# =============================================================================

async def run_january_anomaly_scan():
    """Run comprehensive January anomaly scan."""

    logger.info("=" * 80)
    logger.info("JANUARY 2026 MARKET ANOMALY SCAN")
    logger.info("=" * 80)

    scanner = MarketScanner()
    all_opportunities = []

    # Phase 1: Run standard market scanner
    logger.info("\nPhase 1: Running standard market scanner...")
    try:
        scan_result = await scanner.scan_all(
            universes=[
                "tech_mega",
                "semiconductors",
                "midcap_tech",
                "financials",
                "healthcare",
                "industrials",
                "energy",
            ],
            include_sectors=True,
        )

        logger.info(f"Scanned {scan_result.symbols_scanned} symbols")
        logger.info(f"Found {len(scan_result.inefficiencies_found)} total opportunities")
        logger.info(f"\nMarket Summary:")
        for key, val in scan_result.market_summary.items():
            if key != "by_type":
                logger.info(f"  {key}: {val}")

        all_opportunities.extend(scan_result.top_opportunities[:15])

    except Exception as e:
        logger.error(f"Standard scan failed: {e}")

    # Phase 2: January Effect scan
    logger.info("\nPhase 2: Scanning for January Effect patterns...")
    january_scanner = JanuaryEffectScanner()
    try:
        await january_scanner.scan_small_cap_vs_mega()
        await january_scanner.scan_beaten_down_recovery()

        if january_scanner.results:
            logger.info(f"Found {len(january_scanner.results)} January Effect opportunities")

    except Exception as e:
        logger.error(f"January Effect scan failed: {e}")

    # Phase 3: Earnings season scan
    logger.info("\nPhase 3: Scanning for earnings season positioning...")
    earnings_scanner = EarningsSeasonScanner()
    earnings_results = await earnings_scanner.scan_pre_earnings()
    if earnings_results:
        logger.info(f"Found {len(earnings_results)} earnings-related opportunities")

    # Phase 4: Regime detection
    logger.info("\nPhase 4: Detecting market regime...")
    try:
        classifier = EmpiricalRegimeClassifier()
        spy_data = yf.Ticker("SPY").history(period="252d")

        if not spy_data.empty and len(spy_data) >= 50:
            regime = classifier.detect_regime(spy_data["Close"])

            logger.info(f"Current Regime: {regime.combined.value}")
            logger.info(f"  Volatility: {regime.vol_percentile:.0f}th percentile")
            logger.info(f"  Trend Strength: {regime.trend_strength:+.2f}")
            logger.info(f"  Confidence: {regime.confidence:.0%}")

            # Get strategy recommendations for this regime
            recommendations = classifier.get_strategy_recommendations(regime)
            logger.info(f"  Recommended strategies:")
            for rec in recommendations[:3]:
                logger.info(f"    - {rec.strategy}: Sharpe {rec.expected_sharpe:.2f} ({rec.confidence})")

    except Exception as e:
        logger.error(f"Regime detection failed: {e}")

    # Compile results
    logger.info("\n" + "=" * 80)
    logger.info("COMPILATION & RANKING")
    logger.info("=" * 80)

    # Create JSON output
    output_data = {
        "scan_timestamp": datetime.now().isoformat(),
        "opportunities": [],
        "summary": {
            "total_opportunities": 0,
            "by_type": {},
            "long_count": 0,
            "short_count": 0,
        }
    }

    # Add all opportunities to output
    for opp in all_opportunities:
        output_data["opportunities"].append({
            "symbol": opp.symbol,
            "type": opp.inefficiency_type.value,
            "direction": opp.direction,
            "strength": opp.strength,
            "confidence": opp.confidence,
            "expected_edge": f"{opp.expected_edge*100:.2f}%",
            "description": opp.description,
            "suggested_strategy": opp.suggested_strategy,
            "evidence": opp.evidence,
        })

        output_data["summary"]["total_opportunities"] += 1
        if opp.direction == "long":
            output_data["summary"]["long_count"] += 1
        elif opp.direction == "short":
            output_data["summary"]["short_count"] += 1

        opp_type = opp.inefficiency_type.value
        output_data["summary"]["by_type"][opp_type] = output_data["summary"]["by_type"].get(opp_type, 0) + 1

    # Add January Effect results
    for result in january_scanner.results:
        output_data["opportunities"].append({
            "symbol": result.get("symbol", "BROAD"),
            "type": result["signal"],
            "direction": result["direction"],
            "expected_edge": f"{result['expected_edge']*100:.2f}%",
            "confidence": result["confidence"],
            "description": result["description"],
            "strategy": result["strategy"],
        })

    # Add earnings results
    for result in earnings_results:
        output_data["opportunities"].append({
            "symbol": result["symbol"],
            "type": result["signal"],
            "direction": result["direction"],
            "sector": result["sector"],
            "expected_edge": f"{result['expected_edge']*100:.2f}%",
            "confidence": result["confidence"],
            "description": result["description"],
            "strategy": result["strategy"],
        })

    # Output to file
    output_dir = Path("/home/nock/quant_results/alpha_discovery")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "january_2026_anomalies.json"
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info(f"\nResults saved to: {output_file}")
    logger.info(f"Total opportunities found: {len(output_data['opportunities'])}")

    # Print top opportunities
    logger.info("\n" + "=" * 80)
    logger.info("TOP 20 OPPORTUNITIES BY EXPECTED ALPHA")
    logger.info("=" * 80)

    ranked = sorted(
        all_opportunities,
        key=lambda x: (x.expected_edge * x.confidence),
        reverse=True
    )

    for i, opp in enumerate(ranked[:20], 1):
        edge_score = opp.expected_edge * opp.confidence
        logger.info(f"\n{i}. {opp.symbol} - {opp.inefficiency_type.value.upper()}")
        logger.info(f"   Direction: {opp.direction.upper()}")
        logger.info(f"   Expected Edge: {opp.expected_edge*100:.2f}%")
        logger.info(f"   Confidence: {opp.confidence:.0%}")
        logger.info(f"   Edge Score: {edge_score:.4f}")
        logger.info(f"   Strategy: {opp.suggested_strategy}")
        logger.info(f"   Description: {opp.description}")

    logger.info("\n" + "=" * 80)
    logger.info("SCAN COMPLETE")
    logger.info("=" * 80)

    return output_data


if __name__ == "__main__":
    if not HAS_YFINANCE:
        logger.error("yfinance required. Install with: pip install yfinance")
        exit(1)

    result = asyncio.run(run_january_anomaly_scan())
