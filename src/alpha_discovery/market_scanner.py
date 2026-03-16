"""
Market Inefficiency Scanner

Scans for market inefficiencies and alpha opportunities:
- Analyst coverage gaps (low coverage = slow information)
- Retail sentiment divergence (retail wrong = opportunity)
- Cross-market correlations (DRAM → semiconductors)
- Information velocity (how fast does news hit price?)
- Momentum anomalies
- Mean reversion opportunities

Ranks opportunities by expected edge and testability.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from src.core.paths import paths
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Try importing optional dependencies
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    yf = None


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class InefficiencyType(Enum):
    """Types of market inefficiencies."""
    LOW_COVERAGE = "low_coverage"  # Low analyst coverage
    SENTIMENT_DIVERGENCE = "sentiment_divergence"  # Retail vs price
    CROSS_MARKET_LAG = "cross_market_lag"  # Lead-lag relationships
    MOMENTUM_ANOMALY = "momentum_anomaly"  # Momentum not priced
    MEAN_REVERSION = "mean_reversion"  # Overextended moves
    VOLUME_DIVERGENCE = "volume_divergence"  # Volume vs price
    SECTOR_ROTATION = "sector_rotation"  # Sector momentum
    EVENT_DRIFT = "event_drift"  # Post-event drift


@dataclass
class InefficiencySignal:
    """A detected market inefficiency."""

    id: str
    symbol: str
    inefficiency_type: InefficiencyType
    strength: float  # 0-1, higher = stronger signal
    direction: Literal["long", "short", "neutral"]
    expected_edge: float  # Expected alpha (annualized)
    confidence: float  # 0-1
    description: str
    detected_at: datetime

    # Supporting data
    evidence: dict = field(default_factory=dict)
    suggested_strategy: str = ""
    test_methodology: str = ""

    # Priority for research
    research_priority: float = 0.0  # Computed from strength * confidence

    def __post_init__(self):
        self.research_priority = self.strength * self.confidence

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "symbol": self.symbol,
            "inefficiency_type": self.inefficiency_type.value,
            "strength": self.strength,
            "direction": self.direction,
            "expected_edge": self.expected_edge,
            "confidence": self.confidence,
            "description": self.description,
            "detected_at": self.detected_at.isoformat(),
            "evidence": self.evidence,
            "suggested_strategy": self.suggested_strategy,
            "test_methodology": self.test_methodology,
            "research_priority": self.research_priority,
        }
        return d


@dataclass
class MarketScanResult:
    """Result of a market scan."""

    scan_time: datetime
    symbols_scanned: int
    inefficiencies_found: list[InefficiencySignal]
    top_opportunities: list[InefficiencySignal]  # Ranked by priority
    market_summary: dict

    def to_dict(self) -> dict:
        return {
            "scan_time": self.scan_time.isoformat(),
            "symbols_scanned": self.symbols_scanned,
            "inefficiencies_found": len(self.inefficiencies_found),
            "top_opportunities": [o.to_dict() for o in self.top_opportunities],
            "market_summary": self.market_summary,
        }


# =============================================================================
# MARKET SCANNER
# =============================================================================

class MarketScanner:
    """
    Scan for market inefficiencies and opportunities.

    Implements multiple screening strategies to find alpha.
    """

    # Default symbol universes
    UNIVERSES = {
        "tech_mega": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
        "semiconductors": ["NVDA", "AMD", "INTC", "TSM", "ASML", "MU", "QCOM", "AVGO", "MRVL", "AMAT"],
        "midcap_tech": ["CRWD", "SNOW", "DDOG", "ZS", "PANW", "NET", "PLTR", "U"],
        "commodities": ["GLD", "SLV", "USO", "CPER", "DBA"],
        "financials": ["JPM", "BAC", "GS", "MS", "V", "MA", "AXP"],
        "healthcare": ["UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY"],
        "industrials": ["CAT", "DE", "BA", "HON", "UPS", "FDX"],
        "energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
    }

    def __init__(
        self,
        cache_dir: Path | None = None,
    ):
        self.cache_dir = cache_dir or paths.base / "scanner"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._price_cache: dict[str, pd.DataFrame] = {}
        self._scan_history: list[MarketScanResult] = []

    async def _get_price_data(
        self,
        symbol: str,
        days: int = 252,
    ) -> pd.DataFrame | None:
        """Fetch price data with caching."""
        cache_key = f"{symbol}_{days}"

        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            cache_age = datetime.now() - cached.index[-1].to_pydatetime().replace(tzinfo=None)
            if cache_age < timedelta(hours=6):
                return cached

        if not HAS_YFINANCE:
            logger.warning("yfinance not installed")
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{days}d")
            if hist.empty:
                return None

            hist.index = pd.to_datetime(hist.index).tz_localize(None)
            self._price_cache[cache_key] = hist
            return hist
        except Exception as e:
            logger.warning(f"Failed to fetch {symbol}: {e}")
            return None

    # =========================================================================
    # INEFFICIENCY SCANNERS
    # =========================================================================

    async def scan_momentum_anomalies(
        self,
        symbols: list[str],
        lookback_days: int = 60,
    ) -> list[InefficiencySignal]:
        """
        Scan for momentum anomalies.

        Stocks with strong recent momentum that may continue or reverse.
        """
        signals = []
        now = datetime.now()

        for symbol in symbols:
            data = await self._get_price_data(symbol, lookback_days + 20)
            if data is None or len(data) < lookback_days:
                continue

            # Calculate returns
            returns = data["Close"].pct_change().dropna()
            momentum = (data["Close"].iloc[-1] / data["Close"].iloc[-lookback_days] - 1) * 100

            # Calculate momentum relative to volatility
            volatility = returns.std() * np.sqrt(252) * 100
            momentum_zscore = momentum / max(volatility, 1)

            # Strong momentum (continuation opportunity)
            if abs(momentum_zscore) > 2.0:
                direction = "long" if momentum_zscore > 0 else "short"
                strength = min(abs(momentum_zscore) / 4, 1.0)

                signals.append(InefficiencySignal(
                    id=f"mom_{symbol}_{now.timestamp()}",
                    symbol=symbol,
                    inefficiency_type=InefficiencyType.MOMENTUM_ANOMALY,
                    strength=strength,
                    direction=direction,
                    expected_edge=abs(momentum) * 0.3 / 100,  # Expect 30% of momentum to continue
                    confidence=0.5 + strength * 0.3,
                    description=f"{symbol}: {momentum:.1f}% {lookback_days}d momentum, z-score={momentum_zscore:.2f}",
                    detected_at=now,
                    evidence={
                        "momentum_pct": momentum,
                        "momentum_zscore": momentum_zscore,
                        "volatility": volatility,
                        "lookback_days": lookback_days,
                    },
                    suggested_strategy="momentum" if direction == "long" else "momentum_short",
                    test_methodology="Test continuation over next 20-60 days",
                ))

        return signals

    async def scan_mean_reversion(
        self,
        symbols: list[str],
        lookback_days: int = 20,
    ) -> list[InefficiencySignal]:
        """
        Scan for mean reversion opportunities.

        Stocks that are overextended and may revert.
        """
        signals = []
        now = datetime.now()

        for symbol in symbols:
            data = await self._get_price_data(symbol, lookback_days * 5)
            if data is None or len(data) < lookback_days * 2:
                continue

            # Calculate deviation from moving average
            ma = data["Close"].rolling(lookback_days).mean()
            std = data["Close"].rolling(lookback_days).std()
            zscore = (data["Close"].iloc[-1] - ma.iloc[-1]) / std.iloc[-1]

            # RSI-like momentum
            delta = data["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]

            # Overextended condition
            if abs(zscore) > 2.0 or current_rsi < 25 or current_rsi > 75:
                # Mean reversion signal (trade against the trend)
                direction = "long" if zscore < 0 or current_rsi < 30 else "short"
                strength = min(abs(zscore) / 3, 1.0)

                signals.append(InefficiencySignal(
                    id=f"mr_{symbol}_{now.timestamp()}",
                    symbol=symbol,
                    inefficiency_type=InefficiencyType.MEAN_REVERSION,
                    strength=strength,
                    direction=direction,
                    expected_edge=abs(zscore) * 0.02,  # 2% per z-score
                    confidence=0.6 if abs(zscore) > 2.5 else 0.5,
                    description=f"{symbol}: z-score={zscore:.2f}, RSI={current_rsi:.0f}",
                    detected_at=now,
                    evidence={
                        "zscore": zscore,
                        "rsi": current_rsi,
                        "ma": ma.iloc[-1],
                        "price": data["Close"].iloc[-1],
                    },
                    suggested_strategy="bollinger_reversal" if direction == "long" else "bollinger_short",
                    test_methodology="Test reversion to MA over 5-20 days",
                ))

        return signals

    async def scan_volume_divergence(
        self,
        symbols: list[str],
        lookback_days: int = 20,
    ) -> list[InefficiencySignal]:
        """
        Scan for volume-price divergences.

        Price moving without volume (weak move) or volume without price (accumulation/distribution).
        """
        signals = []
        now = datetime.now()

        for symbol in symbols:
            data = await self._get_price_data(symbol, lookback_days * 3)
            if data is None or len(data) < lookback_days * 2:
                continue

            # Calculate price change and volume change
            price_change = data["Close"].pct_change(lookback_days).iloc[-1]
            avg_volume = data["Volume"].rolling(lookback_days * 2).mean().iloc[-1]
            recent_volume = data["Volume"].tail(lookback_days).mean()
            volume_ratio = recent_volume / avg_volume

            # Divergence: big price move on low volume or high volume on low price move
            if abs(price_change) > 0.1 and volume_ratio < 0.7:
                # Price move without volume support - potential reversal
                direction = "short" if price_change > 0 else "long"
                strength = min(abs(price_change) * 3, 1.0)

                signals.append(InefficiencySignal(
                    id=f"vol_{symbol}_{now.timestamp()}",
                    symbol=symbol,
                    inefficiency_type=InefficiencyType.VOLUME_DIVERGENCE,
                    strength=strength,
                    direction=direction,
                    expected_edge=abs(price_change) * 0.5,
                    confidence=0.5,
                    description=f"{symbol}: {price_change*100:.1f}% move on {volume_ratio:.1%} volume",
                    detected_at=now,
                    evidence={
                        "price_change": price_change,
                        "volume_ratio": volume_ratio,
                    },
                    suggested_strategy="volume_divergence",
                    test_methodology="Test for reversal or continuation based on volume confirmation",
                ))

            elif abs(price_change) < 0.03 and volume_ratio > 1.5:
                # High volume without price move - accumulation/distribution
                # Need more analysis to determine direction
                signals.append(InefficiencySignal(
                    id=f"vol_{symbol}_{now.timestamp()}",
                    symbol=symbol,
                    inefficiency_type=InefficiencyType.VOLUME_DIVERGENCE,
                    strength=0.6,
                    direction="neutral",
                    expected_edge=0.05,
                    confidence=0.4,
                    description=f"{symbol}: High volume ({volume_ratio:.1%}) with flat price",
                    detected_at=now,
                    evidence={
                        "price_change": price_change,
                        "volume_ratio": volume_ratio,
                    },
                    suggested_strategy="volume_breakout",
                    test_methodology="Monitor for breakout direction",
                ))

        return signals

    async def scan_sector_rotation(
        self,
        lookback_days: int = 20,
    ) -> list[InefficiencySignal]:
        """
        Scan for sector rotation opportunities.

        Identify sectors gaining/losing momentum relative to SPY.
        """
        signals = []
        now = datetime.now()

        # Sector ETFs
        sectors = {
            "XLK": "Technology",
            "XLF": "Financials",
            "XLE": "Energy",
            "XLV": "Healthcare",
            "XLI": "Industrials",
            "XLY": "Consumer Discretionary",
            "XLP": "Consumer Staples",
            "XLU": "Utilities",
            "XLB": "Materials",
            "XLRE": "Real Estate",
        }

        # Get SPY as benchmark
        spy_data = await self._get_price_data("SPY", lookback_days * 2)
        if spy_data is None:
            return signals

        spy_return = spy_data["Close"].pct_change(lookback_days).iloc[-1]

        for etf, sector_name in sectors.items():
            data = await self._get_price_data(etf, lookback_days * 2)
            if data is None:
                continue

            sector_return = data["Close"].pct_change(lookback_days).iloc[-1]
            relative_return = sector_return - spy_return

            # Significant outperformance or underperformance
            if abs(relative_return) > 0.05:  # 5% relative move
                direction = "long" if relative_return > 0 else "short"
                strength = min(abs(relative_return) * 5, 1.0)

                signals.append(InefficiencySignal(
                    id=f"sector_{etf}_{now.timestamp()}",
                    symbol=etf,
                    inefficiency_type=InefficiencyType.SECTOR_ROTATION,
                    strength=strength,
                    direction=direction,
                    expected_edge=abs(relative_return) * 0.3,
                    confidence=0.5,
                    description=f"{sector_name} ({etf}): {relative_return*100:+.1f}% vs SPY",
                    detected_at=now,
                    evidence={
                        "sector_return": sector_return,
                        "spy_return": spy_return,
                        "relative_return": relative_return,
                    },
                    suggested_strategy="sector_momentum" if direction == "long" else "sector_short",
                    test_methodology="Test continuation of relative performance",
                ))

        return signals

    # =========================================================================
    # MAIN SCANNING METHODS
    # =========================================================================

    async def scan_all(
        self,
        universes: list[str] | None = None,
        include_sectors: bool = True,
    ) -> MarketScanResult:
        """
        Run all scans and aggregate results.

        Args:
            universes: List of universe names to scan, or None for all
            include_sectors: Whether to scan sector rotation

        Returns:
            Complete scan result with ranked opportunities
        """
        now = datetime.now()
        all_signals: list[InefficiencySignal] = []

        # Collect symbols
        if universes is None:
            universes = list(self.UNIVERSES.keys())

        symbols = set()
        for universe in universes:
            if universe in self.UNIVERSES:
                symbols.update(self.UNIVERSES[universe])

        symbols = list(symbols)
        logger.info(f"Scanning {len(symbols)} symbols across {len(universes)} universes")

        # Run all scans
        momentum_signals = await self.scan_momentum_anomalies(symbols)
        all_signals.extend(momentum_signals)
        logger.info(f"Found {len(momentum_signals)} momentum signals")

        reversion_signals = await self.scan_mean_reversion(symbols)
        all_signals.extend(reversion_signals)
        logger.info(f"Found {len(reversion_signals)} mean reversion signals")

        volume_signals = await self.scan_volume_divergence(symbols)
        all_signals.extend(volume_signals)
        logger.info(f"Found {len(volume_signals)} volume divergence signals")

        if include_sectors:
            sector_signals = await self.scan_sector_rotation()
            all_signals.extend(sector_signals)
            logger.info(f"Found {len(sector_signals)} sector rotation signals")

        # Rank by research priority
        ranked = sorted(all_signals, key=lambda x: x.research_priority, reverse=True)

        # Create market summary
        long_count = sum(1 for s in all_signals if s.direction == "long")
        short_count = sum(1 for s in all_signals if s.direction == "short")

        summary = {
            "total_signals": len(all_signals),
            "long_signals": long_count,
            "short_signals": short_count,
            "neutral_signals": len(all_signals) - long_count - short_count,
            "avg_expected_edge": sum(s.expected_edge for s in all_signals) / max(len(all_signals), 1),
            "by_type": {},
        }

        for t in InefficiencyType:
            count = sum(1 for s in all_signals if s.inefficiency_type == t)
            summary["by_type"][t.value] = count

        result = MarketScanResult(
            scan_time=now,
            symbols_scanned=len(symbols),
            inefficiencies_found=all_signals,
            top_opportunities=ranked[:20],
            market_summary=summary,
        )

        self._scan_history.append(result)
        return result

    async def scan_universe(
        self,
        universe: str,
    ) -> MarketScanResult:
        """Scan a specific universe."""
        if universe not in self.UNIVERSES:
            raise ValueError(f"Unknown universe: {universe}")

        return await self.scan_all(universes=[universe], include_sectors=False)

    def get_research_priorities(
        self,
        n: int = 10,
    ) -> list[dict]:
        """
        Get top research priorities from recent scans.

        Returns list of research suggestions.
        """
        if not self._scan_history:
            return []

        latest = self._scan_history[-1]

        priorities = []
        for signal in latest.top_opportunities[:n]:
            priorities.append({
                "symbol": signal.symbol,
                "type": signal.inefficiency_type.value,
                "direction": signal.direction,
                "priority": signal.research_priority,
                "expected_edge": signal.expected_edge,
                "suggested_strategy": signal.suggested_strategy,
                "test_methodology": signal.test_methodology,
                "description": signal.description,
            })

        return priorities

    def list_universes(self) -> dict[str, list[str]]:
        """List available universes."""
        return self.UNIVERSES.copy()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def quick_scan(
    symbols: list[str] | None = None,
) -> list[InefficiencySignal]:
    """Quick scan of default or provided symbols."""
    scanner = MarketScanner()

    if symbols is None:
        symbols = scanner.UNIVERSES["tech_mega"] + scanner.UNIVERSES["semiconductors"]

    # Just run momentum and mean reversion
    momentum = await scanner.scan_momentum_anomalies(symbols)
    reversion = await scanner.scan_mean_reversion(symbols)

    all_signals = momentum + reversion
    return sorted(all_signals, key=lambda x: x.research_priority, reverse=True)


async def get_opportunities() -> list[dict]:
    """Get current market opportunities."""
    scanner = MarketScanner()
    result = await scanner.scan_all()
    return scanner.get_research_priorities(10)
