"""Market Breadth and Sector Rotation Analyzer.

Provides real-time analysis of:
- Market indices (SPY, QQQ, IWM)
- Sector ETF performance and rotation
- Advance/decline data
- VIX analysis
- Market regime detection

Usage:
    from src.data.pipeline.market_breadth import MarketBreadthAnalyzer

    analyzer = MarketBreadthAnalyzer()
    breadth = analyzer.get_breadth()
    sectors = analyzer.get_sector_rotation()
    print(analyzer.get_summary())
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from src.core.paths import paths

logger = logging.getLogger(__name__)


# Sector ETF definitions
SECTOR_ETFS = {
    "XLE": "Energy",
    "XLF": "Financials",
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "XLC": "Communication Services",
}

# Major indices
INDEX_ETFS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000",
    "DIA": "Dow Jones",
}


@dataclass
class SectorData:
    """Data for a single sector ETF."""

    symbol: str
    name: str
    price: float
    change_pct: float
    volume: int
    avg_volume: int
    volume_ratio: float
    relative_strength: float  # vs SPY
    rank: int  # 1 = leading, 11 = lagging
    flow_direction: str  # "inflow", "outflow", "neutral"
    week_change_pct: float
    month_change_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "price": round(self.price, 2),
            "change_pct": round(self.change_pct, 2),
            "volume": self.volume,
            "avg_volume": self.avg_volume,
            "volume_ratio": round(self.volume_ratio, 2),
            "relative_strength": round(self.relative_strength, 2),
            "rank": self.rank,
            "flow_direction": self.flow_direction,
            "week_change_pct": round(self.week_change_pct, 2),
            "month_change_pct": round(self.month_change_pct, 2),
        }


@dataclass
class IndexData:
    """Data for a market index."""

    symbol: str
    name: str
    price: float
    change_pct: float
    volume: int
    high: float
    low: float
    open_price: float
    prev_close: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "price": round(self.price, 2),
            "change_pct": round(self.change_pct, 2),
            "volume": self.volume,
            "high": round(self.high, 2),
            "low": round(self.low, 2),
            "open": round(self.open_price, 2),
            "prev_close": round(self.prev_close, 2),
        }


@dataclass
class VIXAnalysis:
    """VIX and volatility analysis."""

    vix: float
    vix_change: float
    vix_change_pct: float
    vix_open: float
    vix_high: float
    vix_low: float
    vix_20d_avg: float
    vix_percentile: float  # vs 1 year
    term_structure: str  # "contango", "backwardation", "flat"
    fear_level: str  # "complacent", "cautious", "fearful", "panic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "vix": round(self.vix, 2),
            "vix_change": round(self.vix_change, 2),
            "vix_change_pct": round(self.vix_change_pct, 2),
            "vix_open": round(self.vix_open, 2),
            "vix_high": round(self.vix_high, 2),
            "vix_low": round(self.vix_low, 2),
            "vix_20d_avg": round(self.vix_20d_avg, 2),
            "vix_percentile": round(self.vix_percentile, 1),
            "term_structure": self.term_structure,
            "fear_level": self.fear_level,
        }


@dataclass
class MarketBreadth:
    """Complete market breadth snapshot."""

    timestamp: datetime

    # Index Data
    indices: list[IndexData] = field(default_factory=list)
    spy_price: float = 0.0
    spy_change_pct: float = 0.0
    qqq_price: float = 0.0
    qqq_change_pct: float = 0.0
    iwm_price: float = 0.0
    iwm_change_pct: float = 0.0

    # Breadth Indicators (estimated from ETF performance)
    estimated_advancers: int = 0
    estimated_decliners: int = 0
    advance_decline_ratio: float = 0.0
    breadth_signal: str = "neutral"  # "strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"

    # Sector Rotation
    sectors: list[SectorData] = field(default_factory=list)
    leading_sectors: list[str] = field(default_factory=list)
    lagging_sectors: list[str] = field(default_factory=list)
    rotation_theme: str = "neutral"  # "risk_on", "risk_off", "defensive", "cyclical"

    # VIX Analysis
    vix_analysis: VIXAnalysis | None = None

    # Market Regime
    regime: str = "unknown"  # "trending_up", "trending_down", "ranging", "volatile"
    bias: str = "neutral"  # "bullish", "bearish", "neutral"
    strength: str = "moderate"  # "strong", "moderate", "weak"

    # Notes
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "indices": [i.to_dict() for i in self.indices],
            "spy_price": self.spy_price,
            "spy_change_pct": self.spy_change_pct,
            "qqq_price": self.qqq_price,
            "qqq_change_pct": self.qqq_change_pct,
            "iwm_price": self.iwm_price,
            "iwm_change_pct": self.iwm_change_pct,
            "estimated_advancers": self.estimated_advancers,
            "estimated_decliners": self.estimated_decliners,
            "advance_decline_ratio": self.advance_decline_ratio,
            "breadth_signal": self.breadth_signal,
            "sectors": [s.to_dict() for s in self.sectors],
            "leading_sectors": self.leading_sectors,
            "lagging_sectors": self.lagging_sectors,
            "rotation_theme": self.rotation_theme,
            "vix_analysis": self.vix_analysis.to_dict() if self.vix_analysis else None,
            "regime": self.regime,
            "bias": self.bias,
            "strength": self.strength,
            "notes": self.notes,
        }

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        lines = [
            f"MARKET BREADTH - {self.timestamp.strftime('%H:%M ET')}",
            "=" * 50,
            "",
            "INDICES:",
        ]

        for idx in self.indices:
            emoji = "🟢" if idx.change_pct > 0 else "🔴" if idx.change_pct < 0 else "⚪"
            lines.append(f"  {emoji} {idx.symbol}: ${idx.price:.2f} ({idx.change_pct:+.2f}%)")

        lines.extend([
            "",
            f"BREADTH: {self.breadth_signal.upper().replace('_', ' ')}",
            f"  A/D Ratio: {self.advance_decline_ratio:.2f}",
        ])

        if self.vix_analysis:
            vix = self.vix_analysis
            lines.extend([
                "",
                f"VIX: {vix.vix:.2f} ({vix.vix_change_pct:+.1f}%)",
                f"  Structure: {vix.term_structure.title()}",
                f"  Fear Level: {vix.fear_level.title()} (percentile: {vix.vix_percentile:.0f})",
            ])

        lines.extend([
            "",
            "SECTOR ROTATION:",
        ])

        # Show top 3 and bottom 3 sectors
        for i, sector in enumerate(self.sectors[:3], 1):
            bars = "█" * int(abs(sector.change_pct) * 5) if sector.change_pct > 0 else ""
            lines.append(f"  {i}. {sector.name:<25} {sector.change_pct:+.2f}% {bars}")

        lines.append("  ...")

        for sector in self.sectors[-3:]:
            bars = "░" * int(abs(sector.change_pct) * 5) if sector.change_pct < 0 else ""
            lines.append(f"  {sector.rank}. {sector.name:<25} {sector.change_pct:+.2f}% {bars}")

        lines.extend([
            "",
            f"Theme: {self.rotation_theme.upper().replace('_', ' ')}",
            f"Regime: {self.regime.upper().replace('_', ' ')}",
            f"Bias: {self.bias.upper()} | Strength: {self.strength.upper()}",
        ])

        if self.notes:
            lines.extend(["", "NOTES:"])
            for note in self.notes[:5]:
                lines.append(f"  - {note}")

        return "\n".join(lines)


class MarketBreadthAnalyzer:
    """
    Market breadth and sector rotation analyzer.

    Provides real-time analysis of market conditions,
    sector rotation, and volatility regime.
    """

    def __init__(self):
        """Initialize analyzer."""
        self._price_cache: dict[str, tuple[datetime, pd.DataFrame]] = {}
        self._cache_ttl = timedelta(minutes=5)

    def _get_price_data(self, symbols: list[str], period: str = "5d") -> dict[str, pd.DataFrame]:
        """Get price data for multiple symbols."""
        result = {}

        for symbol in symbols:
            cache_key = f"{symbol}_{period}"
            if cache_key in self._price_cache:
                cached_time, cached_data = self._price_cache[cache_key]
                if datetime.now() - cached_time < self._cache_ttl:
                    result[symbol] = cached_data
                    continue

            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period)
                if len(hist) > 0:
                    self._price_cache[cache_key] = (datetime.now(), hist)
                    result[symbol] = hist
            except Exception as e:
                logger.warning(f"Failed to get data for {symbol}: {e}")

        return result

    def _calculate_relative_strength(self, symbol_data: pd.DataFrame, spy_data: pd.DataFrame) -> float:
        """Calculate relative strength vs SPY."""
        if len(symbol_data) < 2 or len(spy_data) < 2:
            return 0.0

        symbol_return = (symbol_data["Close"].iloc[-1] / symbol_data["Close"].iloc[0] - 1) * 100
        spy_return = (spy_data["Close"].iloc[-1] / spy_data["Close"].iloc[0] - 1) * 100

        return symbol_return - spy_return

    def get_breadth(self) -> MarketBreadth:
        """
        Get current market breadth snapshot.

        Returns:
            MarketBreadth with full market analysis
        """
        timestamp = datetime.now()

        # Fetch all data
        all_symbols = list(INDEX_ETFS.keys()) + list(SECTOR_ETFS.keys()) + ["^VIX"]
        price_data = self._get_price_data(all_symbols, period="1mo")

        # Process indices
        indices = []
        for symbol, name in INDEX_ETFS.items():
            if symbol in price_data:
                df = price_data[symbol]
                if len(df) > 0:
                    current = df.iloc[-1]
                    prev = df.iloc[-2] if len(df) > 1 else current

                    idx = IndexData(
                        symbol=symbol,
                        name=name,
                        price=float(current["Close"]),
                        change_pct=((current["Close"] / prev["Close"]) - 1) * 100,
                        volume=int(current.get("Volume", 0)),
                        high=float(current["High"]),
                        low=float(current["Low"]),
                        open_price=float(current["Open"]),
                        prev_close=float(prev["Close"]),
                    )
                    indices.append(idx)

        # Get SPY data for reference
        spy_data = price_data.get("SPY")
        spy_price = indices[0].price if indices else 0
        spy_change = indices[0].change_pct if indices else 0

        qqq_idx = next((i for i in indices if i.symbol == "QQQ"), None)
        iwm_idx = next((i for i in indices if i.symbol == "IWM"), None)

        # Process sectors
        sectors = []
        for symbol, name in SECTOR_ETFS.items():
            if symbol in price_data and spy_data is not None:
                df = price_data[symbol]
                if len(df) > 0:
                    current = df.iloc[-1]
                    prev = df.iloc[-2] if len(df) > 1 else current

                    # Calculate period returns
                    day_change = ((current["Close"] / prev["Close"]) - 1) * 100

                    week_change = 0.0
                    if len(df) >= 5:
                        week_change = ((current["Close"] / df.iloc[-5]["Close"]) - 1) * 100

                    month_change = 0.0
                    if len(df) >= 20:
                        month_change = ((current["Close"] / df.iloc[-20]["Close"]) - 1) * 100

                    # Volume analysis
                    volume = int(current.get("Volume", 0))
                    avg_volume = int(df["Volume"].mean()) if "Volume" in df else volume
                    volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

                    # Relative strength
                    rs = self._calculate_relative_strength(df, spy_data)

                    # Flow direction based on volume and price
                    if day_change > 0.5 and volume_ratio > 1.2:
                        flow_direction = "inflow"
                    elif day_change < -0.5 and volume_ratio > 1.2:
                        flow_direction = "outflow"
                    else:
                        flow_direction = "neutral"

                    sectors.append(SectorData(
                        symbol=symbol,
                        name=name,
                        price=float(current["Close"]),
                        change_pct=day_change,
                        volume=volume,
                        avg_volume=avg_volume,
                        volume_ratio=volume_ratio,
                        relative_strength=rs,
                        rank=0,  # Will be set after sorting
                        flow_direction=flow_direction,
                        week_change_pct=week_change,
                        month_change_pct=month_change,
                    ))

        # Sort sectors by today's change and assign ranks
        sectors.sort(key=lambda x: x.change_pct, reverse=True)
        for i, sector in enumerate(sectors, 1):
            sector.rank = i

        # Leading and lagging sectors
        leading = [s.name for s in sectors[:3]]
        lagging = [s.name for s in sectors[-3:]]

        # Determine rotation theme
        rotation_theme = self._determine_rotation_theme(sectors)

        # Estimate breadth from sector performance
        positive_sectors = sum(1 for s in sectors if s.change_pct > 0)
        ad_ratio = positive_sectors / len(sectors) if sectors else 0.5

        # Map to rough breadth estimate (500 stocks assumed)
        estimated_advancers = int(ad_ratio * 500)
        estimated_decliners = 500 - estimated_advancers

        # Breadth signal
        if ad_ratio > 0.7:
            breadth_signal = "strong_bullish"
        elif ad_ratio > 0.55:
            breadth_signal = "bullish"
        elif ad_ratio > 0.45:
            breadth_signal = "neutral"
        elif ad_ratio > 0.3:
            breadth_signal = "bearish"
        else:
            breadth_signal = "strong_bearish"

        # VIX Analysis
        vix_analysis = self._analyze_vix(price_data.get("^VIX"))

        # Market regime
        regime, bias, strength = self._determine_regime(spy_data, vix_analysis, ad_ratio)

        # Generate notes
        notes = self._generate_notes(sectors, vix_analysis, regime, rotation_theme)

        return MarketBreadth(
            timestamp=timestamp,
            indices=indices,
            spy_price=spy_price,
            spy_change_pct=spy_change,
            qqq_price=qqq_idx.price if qqq_idx else 0,
            qqq_change_pct=qqq_idx.change_pct if qqq_idx else 0,
            iwm_price=iwm_idx.price if iwm_idx else 0,
            iwm_change_pct=iwm_idx.change_pct if iwm_idx else 0,
            estimated_advancers=estimated_advancers,
            estimated_decliners=estimated_decliners,
            advance_decline_ratio=ad_ratio,
            breadth_signal=breadth_signal,
            sectors=sectors,
            leading_sectors=leading,
            lagging_sectors=lagging,
            rotation_theme=rotation_theme,
            vix_analysis=vix_analysis,
            regime=regime,
            bias=bias,
            strength=strength,
            notes=notes,
        )

    def _analyze_vix(self, vix_data: pd.DataFrame | None) -> VIXAnalysis | None:
        """Analyze VIX data."""
        if vix_data is None or len(vix_data) == 0:
            return None

        try:
            current = vix_data.iloc[-1]
            prev = vix_data.iloc[-2] if len(vix_data) > 1 else current

            vix = float(current["Close"])
            vix_change = vix - float(prev["Close"])
            vix_change_pct = (vix_change / float(prev["Close"])) * 100

            # 20-day average
            vix_20d = float(vix_data["Close"].tail(20).mean())

            # Percentile (rough estimate)
            all_closes = vix_data["Close"].dropna()
            percentile = (all_closes < vix).sum() / len(all_closes) * 100

            # Fear level
            if vix < 15:
                fear_level = "complacent"
            elif vix < 20:
                fear_level = "cautious"
            elif vix < 30:
                fear_level = "fearful"
            else:
                fear_level = "panic"

            # Term structure (simplified - would need VIX futures for real analysis)
            if vix < vix_20d * 0.9:
                term_structure = "contango"
            elif vix > vix_20d * 1.1:
                term_structure = "backwardation"
            else:
                term_structure = "flat"

            return VIXAnalysis(
                vix=vix,
                vix_change=vix_change,
                vix_change_pct=vix_change_pct,
                vix_open=float(current["Open"]),
                vix_high=float(current["High"]),
                vix_low=float(current["Low"]),
                vix_20d_avg=vix_20d,
                vix_percentile=percentile,
                term_structure=term_structure,
                fear_level=fear_level,
            )

        except Exception as e:
            logger.warning(f"VIX analysis failed: {e}")
            return None

    def _determine_rotation_theme(self, sectors: list[SectorData]) -> str:
        """Determine the sector rotation theme."""
        if not sectors:
            return "neutral"

        # Define sector categories
        cyclical = {"XLY", "XLI", "XLB", "XLF"}  # Consumer Disc, Industrials, Materials, Financials
        defensive = {"XLP", "XLU", "XLV", "XLRE"}  # Staples, Utilities, Healthcare, Real Estate
        growth = {"XLK", "XLC"}  # Technology, Communication
        value = {"XLE", "XLF", "XLI"}  # Energy, Financials, Industrials

        # Count which categories are leading
        leading_symbols = {s.symbol for s in sectors[:4]}
        lagging_symbols = {s.symbol for s in sectors[-4:]}

        cyclical_leading = len(leading_symbols & cyclical)
        defensive_leading = len(leading_symbols & defensive)
        growth_leading = len(leading_symbols & growth)

        cyclical_lagging = len(lagging_symbols & cyclical)
        defensive_lagging = len(lagging_symbols & defensive)

        # Determine theme
        if cyclical_leading >= 2 and defensive_lagging >= 2:
            return "risk_on"
        elif defensive_leading >= 2 and cyclical_lagging >= 2:
            return "defensive"
        elif growth_leading >= 2:
            return "growth"
        elif "XLE" in leading_symbols and "XLK" in lagging_symbols:
            return "cyclical"
        else:
            return "neutral"

    def _determine_regime(
        self,
        spy_data: pd.DataFrame | None,
        vix_analysis: VIXAnalysis | None,
        ad_ratio: float,
    ) -> tuple[str, str, str]:
        """Determine market regime, bias, and strength."""
        regime = "unknown"
        bias = "neutral"
        strength = "moderate"

        if spy_data is None or len(spy_data) < 20:
            return regime, bias, strength

        try:
            closes = spy_data["Close"]

            # Calculate trend
            sma_5 = closes.tail(5).mean()
            sma_20 = closes.tail(20).mean()

            current_price = closes.iloc[-1]

            # Trend direction
            if current_price > sma_5 > sma_20:
                bias = "bullish"
            elif current_price < sma_5 < sma_20:
                bias = "bearish"
            else:
                bias = "neutral"

            # Regime based on price action
            high_20 = spy_data["High"].tail(20).max()
            low_20 = spy_data["Low"].tail(20).min()
            range_pct = (high_20 - low_20) / low_20 * 100

            if vix_analysis and vix_analysis.vix > 25:
                regime = "volatile"
            elif range_pct > 8:
                regime = "trending_up" if bias == "bullish" else "trending_down"
            else:
                regime = "ranging"

            # Strength based on breadth
            if ad_ratio > 0.7 or ad_ratio < 0.3:
                strength = "strong"
            elif ad_ratio > 0.55 or ad_ratio < 0.45:
                strength = "moderate"
            else:
                strength = "weak"

        except Exception as e:
            logger.warning(f"Regime determination failed: {e}")

        return regime, bias, strength

    def _generate_notes(
        self,
        sectors: list[SectorData],
        vix_analysis: VIXAnalysis | None,
        regime: str,
        rotation_theme: str,
    ) -> list[str]:
        """Generate actionable notes."""
        notes = []

        # Sector notes
        if sectors:
            best = sectors[0]
            worst = sectors[-1]

            notes.append(f"Leading: {best.name} ({best.change_pct:+.2f}%)")
            notes.append(f"Lagging: {worst.name} ({worst.change_pct:+.2f}%)")

            # Divergence
            if abs(best.change_pct - worst.change_pct) > 3:
                notes.append("Wide sector divergence - selective market")

        # VIX notes
        if vix_analysis:
            if vix_analysis.fear_level == "panic":
                notes.append("VIX at panic levels - potential capitulation")
            elif vix_analysis.fear_level == "complacent":
                notes.append("VIX very low - potential complacency")

            if vix_analysis.term_structure == "backwardation":
                notes.append("VIX in backwardation - heightened near-term fear")

        # Rotation notes
        if rotation_theme == "defensive":
            notes.append("Money rotating into defensive sectors")
        elif rotation_theme == "risk_on":
            notes.append("Risk-on rotation - cyclicals leading")

        return notes[:5]

    def get_sector_rotation(self) -> list[SectorData]:
        """Get current sector rotation data."""
        breadth = self.get_breadth()
        return breadth.sectors

    def get_vix_analysis(self) -> VIXAnalysis | None:
        """Get current VIX analysis."""
        breadth = self.get_breadth()
        return breadth.vix_analysis

    def get_regime(self) -> str:
        """Get current market regime."""
        breadth = self.get_breadth()
        return breadth.regime

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        breadth = self.get_breadth()
        return breadth.get_summary()

    def check_sector_for_symbol(self, symbol: str) -> dict | None:
        """
        Check how a symbol's sector is performing.

        Args:
            symbol: Stock symbol

        Returns:
            Dict with sector data and relative position
        """
        # Map common symbols to sectors
        symbol_sector_map = {
            # Energy
            "XOM": "XLE", "CVX": "XLE", "SLB": "XLE", "HAL": "XLE", "BKR": "XLE",
            "OXY": "XLE", "COP": "XLE", "VLO": "XLE", "MPC": "XLE", "PSX": "XLE",
            # Technology
            "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AMD": "XLK", "INTC": "XLK",
            "CRM": "XLK", "ORCL": "XLK", "ADBE": "XLK",
            # Financials
            "JPM": "XLF", "BAC": "XLF", "WFC": "XLF", "GS": "XLF", "MS": "XLF",
            # Healthcare
            "JNJ": "XLV", "UNH": "XLV", "PFE": "XLV", "MRK": "XLV", "ABBV": "XLV",
            # Consumer
            "WMT": "XLP", "PG": "XLP", "KO": "XLP", "PEP": "XLP", "COST": "XLP",
            "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY", "NKE": "XLY",
            # Travel/Cruise
            "CCL": "XLY", "RCL": "XLY", "NCLH": "XLY",
        }

        sector_etf = symbol_sector_map.get(symbol.upper())
        if not sector_etf:
            return None

        breadth = self.get_breadth()
        sector_data = next((s for s in breadth.sectors if s.symbol == sector_etf), None)

        if sector_data:
            return {
                "symbol": symbol,
                "sector": sector_data.name,
                "sector_etf": sector_etf,
                "sector_rank": sector_data.rank,
                "sector_change_pct": sector_data.change_pct,
                "is_leading": sector_data.rank <= 3,
                "is_lagging": sector_data.rank >= 9,
                "flow_direction": sector_data.flow_direction,
                "rotation_theme": breadth.rotation_theme,
            }

        return None
