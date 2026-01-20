"""Sector Lead-Lag Signal Generator.

Detects sector rotation and lead-lag relationships:
- Semiconductors lead broader tech by 2-4 weeks
- Banks lead in rising rate regimes
- Energy leads inflation prints
- Defensive sectors outperform in late cycle

These are latent knowledge patterns that should be validated but provide
valuable signal in the meantime.

Created: 2026-01-20
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class LeadLagSignal:
    """A lead-lag relationship signal."""

    timestamp: datetime
    leader_symbol: str
    follower_symbol: str
    leader_return_5d: float
    follower_return_5d: float
    expected_follower_move: float  # What we expect follower to do
    confidence: float  # 0-1
    signal_direction: str  # "bullish" or "bearish" for follower
    description: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "leader_symbol": self.leader_symbol,
            "follower_symbol": self.follower_symbol,
            "leader_return_5d": self.leader_return_5d,
            "follower_return_5d": self.follower_return_5d,
            "expected_follower_move": self.expected_follower_move,
            "confidence": self.confidence,
            "signal_direction": self.signal_direction,
            "description": self.description,
        }


@dataclass
class SectorRotationSignal:
    """Sector rotation pattern signal."""

    timestamp: datetime
    rotation_type: str  # "risk_on", "risk_off", "defensive", "cyclical"
    leading_sectors: list[str]
    lagging_sectors: list[str]
    sector_returns: dict[str, float]  # 5-day returns
    confidence: float
    description: str
    affected_symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "rotation_type": self.rotation_type,
            "leading_sectors": self.leading_sectors,
            "lagging_sectors": self.lagging_sectors,
            "sector_returns": self.sector_returns,
            "confidence": self.confidence,
            "description": self.description,
            "affected_symbols": self.affected_symbols,
        }


# Lead-Lag Relationships (from latent knowledge)
LEAD_LAG_PAIRS = {
    # Semis lead tech
    ("SMH", "XLK"): {
        "name": "Semiconductors → Tech",
        "lag_days": 10,  # Average lag
        "correlation": 0.85,
        "description": "Semiconductors typically lead broader tech by 1-2 weeks",
    },
    ("SOXX", "QQQ"): {
        "name": "Semis → Nasdaq",
        "lag_days": 12,
        "correlation": 0.80,
        "description": "Semiconductor ETF leads Nasdaq moves",
    },
    # Financials lead on rates
    ("TLT", "XLF"): {
        "name": "Rates → Banks (Inverse)",
        "lag_days": 5,
        "correlation": -0.60,
        "description": "Bond prices (inverse of rates) predict bank performance",
    },
    # Energy leads inflation
    ("XLE", "TIP"): {
        "name": "Energy → TIPS",
        "lag_days": 20,
        "correlation": 0.50,
        "description": "Energy prices lead inflation expectations",
    },
    # Consumer discretionary vs staples (risk gauge)
    ("XLY", "XLP"): {
        "name": "Discretionary vs Staples",
        "lag_days": 5,
        "correlation": 0.70,
        "description": "XLY/XLP ratio indicates risk appetite",
    },
    # Housing leads materials
    ("XHB", "XLB"): {
        "name": "Housing → Materials",
        "lag_days": 15,
        "correlation": 0.65,
        "description": "Housing activity leads materials demand",
    },
}

# Sector ETFs for rotation analysis
SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Materials": "XLB",
    "Industrials": "XLI",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communications": "XLC",
}

# Defensive vs Cyclical groupings
DEFENSIVE_SECTORS = ["XLU", "XLP", "XLV"]
CYCLICAL_SECTORS = ["XLY", "XLF", "XLI", "XLB", "XLE"]


class SectorLeadLagAnalyzer:
    """Analyze sector lead-lag relationships and rotation patterns."""

    def __init__(self, lookback_days: int = 60):
        self.lookback_days = lookback_days
        self._cache: dict[str, pd.DataFrame] = {}
        self._cache_time: Optional[datetime] = None

    async def _fetch_prices(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        """Fetch price data for symbols."""
        # Check cache (valid for 1 hour)
        if self._cache_time and (datetime.now() - self._cache_time).seconds < 3600:
            missing = [s for s in symbols if s not in self._cache]
            if not missing:
                return {s: self._cache[s] for s in symbols}

        result = {}
        for sym in symbols:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period=f"{self.lookback_days}d")
                if not hist.empty:
                    result[sym] = hist[["Close"]].rename(columns={"Close": "close"})
                    self._cache[sym] = result[sym]
            except Exception as e:
                logger.warning(f"Failed to fetch {sym}: {e}")

        self._cache_time = datetime.now()
        return result

    def _calculate_returns(self, prices: pd.DataFrame, periods: list[int] = None) -> pd.DataFrame:
        """Calculate returns for various periods."""
        if periods is None:
            periods = [1, 5, 10, 20]

        returns = pd.DataFrame(index=prices.index)
        for period in periods:
            returns[f"ret_{period}d"] = prices["close"].pct_change(period)
        return returns

    async def analyze_lead_lag(self) -> list[LeadLagSignal]:
        """Analyze all lead-lag relationships."""
        signals = []

        # Get all symbols we need
        all_symbols = set()
        for (leader, follower) in LEAD_LAG_PAIRS.keys():
            all_symbols.add(leader)
            all_symbols.add(follower)

        prices = await self._fetch_prices(list(all_symbols))

        for (leader, follower), config in LEAD_LAG_PAIRS.items():
            if leader not in prices or follower not in prices:
                continue

            leader_prices = prices[leader]
            follower_prices = prices[follower]

            # Calculate returns
            leader_returns = self._calculate_returns(leader_prices)
            follower_returns = self._calculate_returns(follower_prices)

            if leader_returns.empty or follower_returns.empty:
                continue

            # Get recent leader movement
            leader_5d = leader_returns["ret_5d"].iloc[-1]
            follower_5d = follower_returns["ret_5d"].iloc[-1]

            if pd.isna(leader_5d) or pd.isna(follower_5d):
                continue

            # Calculate historical correlation at lag
            lag_days = config["lag_days"]
            if len(leader_returns) > lag_days + 20:
                # Shift leader returns back by lag_days
                shifted_leader = leader_returns["ret_5d"].shift(lag_days)
                # Calculate correlation with follower
                corr_data = pd.DataFrame({
                    "leader": shifted_leader,
                    "follower": follower_returns["ret_5d"]
                }).dropna()

                if len(corr_data) > 20:
                    actual_corr = corr_data["leader"].corr(corr_data["follower"])
                else:
                    actual_corr = config["correlation"]
            else:
                actual_corr = config["correlation"]

            # Expected follower move based on leader's recent move
            expected_move = leader_5d * actual_corr

            # Generate signal if leader has moved significantly
            if abs(leader_5d) > 0.02:  # 2%+ move
                signal_direction = "bullish" if expected_move > 0 else "bearish"
                confidence = min(1.0, abs(actual_corr) * (1 + abs(leader_5d) * 5))

                signals.append(LeadLagSignal(
                    timestamp=datetime.now(),
                    leader_symbol=leader,
                    follower_symbol=follower,
                    leader_return_5d=leader_5d * 100,  # As percentage
                    follower_return_5d=follower_5d * 100,
                    expected_follower_move=expected_move * 100,
                    confidence=confidence,
                    signal_direction=signal_direction,
                    description=f"{config['name']}: {leader} moved {leader_5d*100:+.1f}%, "
                               f"expect {follower} to follow with {expected_move*100:+.1f}% move "
                               f"(corr: {actual_corr:.2f})",
                ))

        return signals

    async def analyze_sector_rotation(self) -> Optional[SectorRotationSignal]:
        """Analyze current sector rotation pattern."""
        # Fetch all sector ETFs
        prices = await self._fetch_prices(list(SECTOR_ETFS.values()))

        if len(prices) < 5:
            return None

        # Calculate 5-day returns for each sector
        sector_returns = {}
        for sector, etf in SECTOR_ETFS.items():
            if etf in prices:
                returns = self._calculate_returns(prices[etf])
                if not returns.empty and not pd.isna(returns["ret_5d"].iloc[-1]):
                    sector_returns[sector] = returns["ret_5d"].iloc[-1] * 100

        if not sector_returns:
            return None

        # Sort by returns
        sorted_sectors = sorted(sector_returns.items(), key=lambda x: x[1], reverse=True)
        leading = [s[0] for s in sorted_sectors[:3]]
        lagging = [s[0] for s in sorted_sectors[-3:]]

        # Determine rotation type
        leading_etfs = [SECTOR_ETFS[s] for s in leading]
        lagging_etfs = [SECTOR_ETFS[s] for s in lagging]

        # Count defensive vs cyclical
        leading_defensive = len([e for e in leading_etfs if e in DEFENSIVE_SECTORS])
        leading_cyclical = len([e for e in leading_etfs if e in CYCLICAL_SECTORS])
        lagging_defensive = len([e for e in lagging_etfs if e in DEFENSIVE_SECTORS])
        lagging_cyclical = len([e for e in lagging_etfs if e in CYCLICAL_SECTORS])

        if leading_cyclical >= 2 and lagging_defensive >= 2:
            rotation_type = "risk_on"
            description = "Risk-on rotation: Cyclical sectors leading, defensive lagging"
            affected = ["QQQ", "IWM", "SPY"]  # Risk-on assets
        elif leading_defensive >= 2 and lagging_cyclical >= 2:
            rotation_type = "risk_off"
            description = "Risk-off rotation: Defensive sectors leading, cyclical lagging"
            affected = ["TLT", "GLD", "XLU"]  # Safe haven assets
        elif SECTOR_ETFS["Technology"] in leading_etfs:
            rotation_type = "growth"
            description = "Growth rotation: Technology leading"
            affected = ["QQQ", "XLK", "ARKK"]
        elif SECTOR_ETFS["Energy"] in leading_etfs:
            rotation_type = "value"
            description = "Value/Inflation rotation: Energy leading"
            affected = ["XLE", "XLF", "XLV"]
        else:
            rotation_type = "mixed"
            description = "Mixed rotation pattern"
            affected = []

        # Confidence based on dispersion
        returns_list = list(sector_returns.values())
        dispersion = max(returns_list) - min(returns_list)
        confidence = min(1.0, dispersion / 5.0)  # 5% dispersion = high confidence

        return SectorRotationSignal(
            timestamp=datetime.now(),
            rotation_type=rotation_type,
            leading_sectors=leading,
            lagging_sectors=lagging,
            sector_returns=sector_returns,
            confidence=confidence,
            description=description,
            affected_symbols=affected,
        )

    async def get_all_signals(self) -> dict:
        """Get all lead-lag and rotation signals."""
        lead_lag = await self.analyze_lead_lag()
        rotation = await self.analyze_sector_rotation()

        return {
            "timestamp": datetime.now().isoformat(),
            "lead_lag_signals": [s.to_dict() for s in lead_lag],
            "rotation_signal": rotation.to_dict() if rotation else None,
        }


# Convenience function
async def get_sector_signals() -> dict:
    """Quick function to get sector lead-lag signals."""
    analyzer = SectorLeadLagAnalyzer()
    return await analyzer.get_all_signals()


if __name__ == "__main__":
    async def main():
        analyzer = SectorLeadLagAnalyzer()

        print("=== Lead-Lag Signals ===")
        lead_lag = await analyzer.analyze_lead_lag()
        for sig in lead_lag:
            print(f"  {sig.leader_symbol} → {sig.follower_symbol}: {sig.description}")

        print("\n=== Sector Rotation ===")
        rotation = await analyzer.analyze_sector_rotation()
        if rotation:
            print(f"  Type: {rotation.rotation_type}")
            print(f"  Leading: {rotation.leading_sectors}")
            print(f"  Lagging: {rotation.lagging_sectors}")
            print(f"  Description: {rotation.description}")

    asyncio.run(main())
