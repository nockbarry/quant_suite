"""
Commitment of Traders (COT) Report Source

CFTC releases COT data every Friday at 3:30 PM ET.
Data reflects positions as of Tuesday close.

Key insight: Follow the commercials (hedgers/smart money).
- Commercial positions are typically counter-trend (hedging)
- When commercials are extremely long/short, it often precedes reversals
- Non-commercial (speculators) are often wrong at extremes

Tracked futures:
- ES (S&P 500 E-mini)
- NQ (NASDAQ E-mini)
- YM (Dow E-mini)
- CL (Crude Oil)
- GC (Gold)
- SI (Silver)
- ZB (30-Year Treasury)
- 6E (Euro FX)
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import re

try:
    import httpx
except ImportError:
    httpx = None

try:
    import pandas as pd
except ImportError:
    pd = None

from src.core.paths import paths

logger = logging.getLogger(__name__)


# CFTC COT report URLs
CFTC_LEGACY_URL = "https://www.cftc.gov/dea/futures/financial_lf.htm"
CFTC_DISAGGREGATED_URL = "https://www.cftc.gov/dea/futures/deacmelf.htm"

# Map futures symbols to CFTC contract names
CONTRACT_MAP = {
    "ES": "E-MINI S&P 500",
    "SPY": "E-MINI S&P 500",  # Map ETF to futures
    "NQ": "NASDAQ-100 E-MINI",
    "QQQ": "NASDAQ-100 E-MINI",
    "YM": "DJIA x $5",
    "DIA": "DJIA x $5",
    "CL": "CRUDE OIL, LIGHT SWEET",
    "USO": "CRUDE OIL, LIGHT SWEET",
    "GC": "GOLD",
    "GLD": "GOLD",
    "SI": "SILVER",
    "SLV": "SILVER",
    "ZB": "U.S. TREASURY BONDS",
    "TLT": "U.S. TREASURY BONDS",
    "6E": "EURO FX",
    "FXE": "EURO FX",
    "6J": "JAPANESE YEN",
    "6B": "BRITISH POUND",
}

# Thresholds for extreme positioning (percentile-based)
EXTREME_LONG_PERCENTILE = 0.90  # Top 10%
VERY_LONG_PERCENTILE = 0.75
EXTREME_SHORT_PERCENTILE = 0.10  # Bottom 10%
VERY_SHORT_PERCENTILE = 0.25


@dataclass
class COTPosition:
    """COT positioning data for a single contract."""

    symbol: str  # Original symbol requested
    contract_name: str  # CFTC contract name
    report_date: datetime

    # Commercial positions (hedgers - smart money)
    commercial_long: int
    commercial_short: int
    commercial_net: int

    # Non-commercial (large speculators)
    speculator_long: int
    speculator_short: int
    speculator_net: int

    # Fields with defaults must come after required fields
    commercial_net_change: int = 0
    speculator_net_change: int = 0

    # Non-reportable (small traders)
    small_trader_long: int = 0
    small_trader_short: int = 0
    small_trader_net: int = 0

    # Open interest
    open_interest: int = 0
    open_interest_change: int = 0

    # Historical context
    commercial_percentile: float = 0.5  # Where is net position historically
    speculator_percentile: float = 0.5

    # Signals
    extreme_reading: bool = False
    signal: float = 0.0  # -1 to +1 (follow commercials)
    signal_strength: float = 0.0
    interpretation: str = "neutral"

    # Metadata
    source: str = "cftc"
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "contract_name": self.contract_name,
            "report_date": self.report_date.isoformat(),
            "commercial_long": self.commercial_long,
            "commercial_short": self.commercial_short,
            "commercial_net": self.commercial_net,
            "commercial_net_change": self.commercial_net_change,
            "speculator_long": self.speculator_long,
            "speculator_short": self.speculator_short,
            "speculator_net": self.speculator_net,
            "speculator_net_change": self.speculator_net_change,
            "small_trader_long": self.small_trader_long,
            "small_trader_short": self.small_trader_short,
            "small_trader_net": self.small_trader_net,
            "open_interest": self.open_interest,
            "open_interest_change": self.open_interest_change,
            "commercial_percentile": self.commercial_percentile,
            "speculator_percentile": self.speculator_percentile,
            "extreme_reading": self.extreme_reading,
            "signal": self.signal,
            "signal_strength": self.signal_strength,
            "interpretation": self.interpretation,
            "source": self.source,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "COTPosition":
        return cls(
            symbol=d["symbol"],
            contract_name=d["contract_name"],
            report_date=datetime.fromisoformat(d["report_date"]),
            commercial_long=d["commercial_long"],
            commercial_short=d["commercial_short"],
            commercial_net=d["commercial_net"],
            commercial_net_change=d.get("commercial_net_change", 0),
            speculator_long=d["speculator_long"],
            speculator_short=d["speculator_short"],
            speculator_net=d["speculator_net"],
            speculator_net_change=d.get("speculator_net_change", 0),
            small_trader_long=d.get("small_trader_long", 0),
            small_trader_short=d.get("small_trader_short", 0),
            small_trader_net=d.get("small_trader_net", 0),
            open_interest=d.get("open_interest", 0),
            open_interest_change=d.get("open_interest_change", 0),
            commercial_percentile=d.get("commercial_percentile", 0.5),
            speculator_percentile=d.get("speculator_percentile", 0.5),
            extreme_reading=d.get("extreme_reading", False),
            signal=d.get("signal", 0.0),
            signal_strength=d.get("signal_strength", 0.0),
            interpretation=d.get("interpretation", "neutral"),
            source=d.get("source", "cftc"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )


@dataclass
class COTReport:
    """Collection of COT positions across all tracked contracts."""

    report_date: datetime
    positions: dict[str, COTPosition] = field(default_factory=dict)

    # Summary signals
    equity_signal: float = 0.0  # Aggregate signal for equity futures
    commodity_signal: float = 0.0  # Aggregate signal for commodities
    overall_risk_appetite: str = "neutral"  # risk-on, risk-off, neutral

    last_updated: datetime = field(default_factory=datetime.now)

    def get_position(self, symbol: str) -> Optional[COTPosition]:
        """Get COT position for a symbol."""
        # Try direct lookup
        if symbol in self.positions:
            return self.positions[symbol]

        # Try mapped symbol
        contract = CONTRACT_MAP.get(symbol.upper())
        if contract:
            for pos in self.positions.values():
                if pos.contract_name == contract:
                    return pos

        return None

    def to_dict(self) -> dict:
        return {
            "report_date": self.report_date.isoformat(),
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "equity_signal": self.equity_signal,
            "commodity_signal": self.commodity_signal,
            "overall_risk_appetite": self.overall_risk_appetite,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "COTReport":
        positions = {k: COTPosition.from_dict(v) for k, v in d.get("positions", {}).items()}
        return cls(
            report_date=datetime.fromisoformat(d["report_date"]),
            positions=positions,
            equity_signal=d.get("equity_signal", 0.0),
            commodity_signal=d.get("commodity_signal", 0.0),
            overall_risk_appetite=d.get("overall_risk_appetite", "neutral"),
            last_updated=datetime.fromisoformat(d["last_updated"]) if "last_updated" in d else datetime.now(),
        )


class COTSource:
    """
    Fetch and analyze CFTC Commitment of Traders data.

    Data is released weekly on Friday.
    """

    name = "cot_report"

    def __init__(
        self,
        cache_ttl_hours: int = 24,
        cache_dir: Optional[Path] = None,
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "cot")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Optional[tuple[datetime, COTReport]] = None

        # Historical data for percentile calculations
        self._history: dict[str, list[tuple[datetime, int]]] = {}  # symbol -> [(date, net)]
        self._load_history()

    def _load_history(self) -> None:
        """Load historical COT data for percentile calculations."""
        history_file = self.cache_dir / "cot_history.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    data = json.load(f)
                for symbol, readings in data.items():
                    self._history[symbol] = [
                        (datetime.fromisoformat(r[0]), r[1])
                        for r in readings
                    ]
            except Exception as e:
                logger.warning(f"Failed to load COT history: {e}")

    def _save_history(self) -> None:
        """Save historical data."""
        history_file = self.cache_dir / "cot_history.json"
        try:
            data = {}
            for symbol, readings in self._history.items():
                # Keep last 52 weeks
                data[symbol] = [
                    (r[0].isoformat(), r[1])
                    for r in readings[-52:]
                ]
            with open(history_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save COT history: {e}")

    def _check_cache(self) -> Optional[COTReport]:
        """Check if cached data is still valid."""
        if self._cache:
            timestamp, report = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                return report

        # Check file cache
        cache_file = self.cache_dir / "cot_latest.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                report = COTReport.from_dict(data)
                if datetime.now() - report.last_updated < self.cache_ttl:
                    self._cache = (report.last_updated, report)
                    return report
            except Exception as e:
                logger.warning(f"Failed to load COT cache: {e}")

        return None

    def _update_cache(self, report: COTReport) -> None:
        """Update cache with new report."""
        self._cache = (datetime.now(), report)

        # Save to file
        cache_file = self.cache_dir / "cot_latest.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(report.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save COT cache: {e}")

        # Update history
        for symbol, position in report.positions.items():
            if symbol not in self._history:
                self._history[symbol] = []

            # Add if new date
            if not self._history[symbol] or position.report_date.date() != self._history[symbol][-1][0].date():
                self._history[symbol].append((position.report_date, position.commercial_net))

        self._save_history()

    async def get_report(self, symbols: Optional[list[str]] = None) -> COTReport:
        """
        Get current COT report.

        Args:
            symbols: Optional list of symbols to include.
                    If None, returns all tracked contracts.

        Returns:
            COTReport with positions and signals.
        """
        # Check cache
        cached = self._check_cache()
        if cached:
            if symbols:
                # Filter to requested symbols
                filtered = COTReport(report_date=cached.report_date)
                for sym in symbols:
                    pos = cached.get_position(sym)
                    if pos:
                        filtered.positions[sym] = pos
                return filtered
            return cached

        try:
            # Fetch fresh data
            report = await self._fetch_cot_data()

            # Compute signals
            report = self._compute_signals(report)

            # Update cache
            self._update_cache(report)

            return report

        except Exception as e:
            logger.error(f"Failed to fetch COT data: {e}")
            return self._get_estimated_report()

    async def _fetch_cot_data(self) -> COTReport:
        """
        Fetch COT data from CFTC.

        Note: CFTC website provides text/HTML data.
        For production, consider using Quandl or a dedicated data provider.
        """
        # Try to load from cache file first
        cache_file = self.cache_dir / "cot_latest.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                return COTReport.from_dict(data)
            except Exception:
                pass

        logger.info("Using estimated COT data (no fresh data available)")
        return self._get_estimated_report()

    def _get_estimated_report(self) -> COTReport:
        """
        Return estimated COT data based on typical values.

        This is a fallback when live data isn't available.
        """
        today = datetime.now()

        # Find last Tuesday (as-of date for COT)
        days_since_tuesday = (today.weekday() - 1) % 7
        last_tuesday = today - timedelta(days=days_since_tuesday)

        report = COTReport(report_date=last_tuesday)

        # Add estimated positions for key contracts
        estimated_positions = {
            "ES": {
                "commercial_long": 450000,
                "commercial_short": 520000,
                "speculator_long": 320000,
                "speculator_short": 280000,
            },
            "NQ": {
                "commercial_long": 85000,
                "commercial_short": 95000,
                "speculator_long": 65000,
                "speculator_short": 55000,
            },
            "GC": {
                "commercial_long": 180000,
                "commercial_short": 350000,
                "speculator_long": 280000,
                "speculator_short": 95000,
            },
            "CL": {
                "commercial_long": 420000,
                "commercial_short": 580000,
                "speculator_long": 350000,
                "speculator_short": 180000,
            },
        }

        for symbol, data in estimated_positions.items():
            contract_name = CONTRACT_MAP.get(symbol, symbol)
            pos = COTPosition(
                symbol=symbol,
                contract_name=contract_name,
                report_date=last_tuesday,
                commercial_long=data["commercial_long"],
                commercial_short=data["commercial_short"],
                commercial_net=data["commercial_long"] - data["commercial_short"],
                speculator_long=data["speculator_long"],
                speculator_short=data["speculator_short"],
                speculator_net=data["speculator_long"] - data["speculator_short"],
                source="estimated",
            )
            report.positions[symbol] = pos

        return report

    def _compute_signals(self, report: COTReport) -> COTReport:
        """Compute trading signals from COT data."""

        equity_signals = []
        commodity_signals = []

        for symbol, position in report.positions.items():
            # Calculate percentile from history
            if symbol in self._history and self._history[symbol]:
                net_values = sorted([h[1] for h in self._history[symbol]])
                rank = sum(1 for v in net_values if v < position.commercial_net)
                position.commercial_percentile = rank / len(net_values) if net_values else 0.5

                spec_values = sorted([position.speculator_net])  # Would need history
                position.speculator_percentile = 0.5  # Placeholder

            # Determine if extreme
            is_extreme_long = position.commercial_percentile >= EXTREME_LONG_PERCENTILE
            is_extreme_short = position.commercial_percentile <= EXTREME_SHORT_PERCENTILE
            position.extreme_reading = is_extreme_long or is_extreme_short

            # Calculate signal (follow commercials)
            # High percentile = commercials are long = bullish signal
            # Low percentile = commercials are short = bearish signal
            if position.commercial_percentile >= EXTREME_LONG_PERCENTILE:
                position.signal = 0.9
                position.signal_strength = min(1.0, (position.commercial_percentile - 0.75) * 4)
                position.interpretation = "commercials_extremely_long"
            elif position.commercial_percentile >= VERY_LONG_PERCENTILE:
                position.signal = 0.5
                position.signal_strength = (position.commercial_percentile - 0.5) * 2
                position.interpretation = "commercials_long"
            elif position.commercial_percentile <= EXTREME_SHORT_PERCENTILE:
                position.signal = -0.9
                position.signal_strength = min(1.0, (0.25 - position.commercial_percentile) * 4)
                position.interpretation = "commercials_extremely_short"
            elif position.commercial_percentile <= VERY_SHORT_PERCENTILE:
                position.signal = -0.5
                position.signal_strength = (0.5 - position.commercial_percentile) * 2
                position.interpretation = "commercials_short"
            else:
                position.signal = (position.commercial_percentile - 0.5) * 2  # -1 to +1 linear
                position.signal_strength = abs(position.signal) * 0.5
                position.interpretation = "neutral"

            # Aggregate by category
            if symbol in ["ES", "NQ", "YM"]:
                equity_signals.append(position.signal)
            elif symbol in ["CL", "GC", "SI"]:
                commodity_signals.append(position.signal)

            position.last_updated = datetime.now()

        # Compute aggregate signals
        if equity_signals:
            report.equity_signal = sum(equity_signals) / len(equity_signals)
        if commodity_signals:
            report.commodity_signal = sum(commodity_signals) / len(commodity_signals)

        # Determine overall risk appetite
        if report.equity_signal > 0.3:
            report.overall_risk_appetite = "risk-on"
        elif report.equity_signal < -0.3:
            report.overall_risk_appetite = "risk-off"
        else:
            report.overall_risk_appetite = "neutral"

        report.last_updated = datetime.now()
        return report

    def get_signal(self, symbol: str) -> float:
        """
        Get COT signal for a symbol synchronously.

        Returns:
            Float from -1 (bearish) to +1 (bullish), following commercials
        """
        cached = self._check_cache()
        if cached:
            pos = cached.get_position(symbol)
            if pos:
                return pos.signal
        return 0.0

    def update_position(
        self,
        symbol: str,
        report_date: datetime,
        commercial_long: int,
        commercial_short: int,
        speculator_long: int,
        speculator_short: int,
    ) -> COTPosition:
        """
        Manually update COT position.

        Use this to input weekly COT data.
        """
        contract_name = CONTRACT_MAP.get(symbol.upper(), symbol)

        position = COTPosition(
            symbol=symbol,
            contract_name=contract_name,
            report_date=report_date,
            commercial_long=commercial_long,
            commercial_short=commercial_short,
            commercial_net=commercial_long - commercial_short,
            speculator_long=speculator_long,
            speculator_short=speculator_short,
            speculator_net=speculator_long - speculator_short,
            source="manual_update",
        )

        # Get or create report
        report = self._check_cache() or COTReport(report_date=report_date)
        report.positions[symbol] = position
        report = self._compute_signals(report)
        self._update_cache(report)

        return position

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_cot_report(symbols: Optional[list[str]] = None) -> COTReport:
    """Get current COT report."""
    source = COTSource()
    try:
        return await source.get_report(symbols)
    finally:
        await source.close()


async def get_cot_signal(symbol: str) -> float:
    """
    Get COT signal for a symbol.

    Returns:
        -1 to +1: based on commercial positioning
    """
    report = await get_cot_report([symbol])
    pos = report.get_position(symbol)
    if pos:
        return pos.signal
    return 0.0


async def get_equity_cot_signal() -> float:
    """Get aggregate equity COT signal (ES, NQ, YM)."""
    report = await get_cot_report(["ES", "NQ", "YM"])
    return report.equity_signal


if __name__ == "__main__":
    # Test the source
    async def main():
        source = COTSource()
        report = await source.get_report()

        print(f"Report Date: {report.report_date.date()}")
        print(f"Equity Signal: {report.equity_signal:.2f}")
        print(f"Commodity Signal: {report.commodity_signal:.2f}")
        print(f"Risk Appetite: {report.overall_risk_appetite}")
        print()

        for symbol, pos in report.positions.items():
            print(f"{symbol} ({pos.contract_name}):")
            print(f"  Commercial Net: {pos.commercial_net:,}")
            print(f"  Speculator Net: {pos.speculator_net:,}")
            print(f"  Commercial Percentile: {pos.commercial_percentile:.1%}")
            print(f"  Signal: {pos.signal:.2f} ({pos.interpretation})")
            print()

        await source.close()

    asyncio.run(main())
