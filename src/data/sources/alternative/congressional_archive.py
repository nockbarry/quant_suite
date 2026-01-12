"""Congressional trades historical archiver and backfill.

Collects and archives congressional trading data from free sources:
1. House Stock Watcher (housestockwatcher.com) - JSON/CSV API
2. Senate Stock Watcher (senatestockwatcher.com) - JSON/CSV API
3. GitHub repositories with historical data
4. SEC EDGAR (original source)

This module handles:
- Daily collection and archival of new trades
- Historical backfill from GitHub repositories
- Deduplication and data quality checks
- Export to various formats (JSON, CSV, Parquet)

Usage:
    from src.data.sources.alternative.congressional_archive import CongressionalArchiver

    archiver = CongressionalArchiver()

    # Download historical data from GitHub
    await archiver.backfill_from_github()

    # Collect new trades (daily cron job)
    await archiver.collect_daily()

    # Get all historical trades
    trades_df = archiver.load_all_trades()
"""

import asyncio
import gzip
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class CongressionalTradeRecord:
    """Unified trade record format for archival."""

    # Core identifiers
    politician: str
    symbol: str
    trade_type: str  # purchase, sale, sale_partial, sale_full, exchange

    # Dates
    transaction_date: datetime
    disclosure_date: datetime

    # Value
    amount_low: float
    amount_high: float

    # Optional metadata
    chamber: str = ""  # house, senate
    party: str = ""
    state: str = ""
    district: str = ""
    owner: str = ""  # self, spouse, joint, child
    asset_description: str = ""
    committees: list[str] = field(default_factory=list)

    # Data source tracking
    source: str = ""  # github, rss, sec_edgar
    collected_at: datetime = field(default_factory=datetime.now)

    @property
    def amount_estimate(self) -> float:
        """Geometric mean of amount range."""
        if self.amount_low > 0 and self.amount_high > 0:
            return (self.amount_low * self.amount_high) ** 0.5
        return (self.amount_low + self.amount_high) / 2

    @property
    def filing_delay_days(self) -> int:
        """Days between transaction and disclosure."""
        return (self.disclosure_date - self.transaction_date).days

    @property
    def unique_key(self) -> str:
        """Unique identifier for deduplication."""
        return f"{self.politician}_{self.symbol}_{self.transaction_date.date()}_{self.trade_type}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "politician": self.politician,
            "symbol": self.symbol,
            "trade_type": self.trade_type,
            "transaction_date": self.transaction_date.isoformat(),
            "disclosure_date": self.disclosure_date.isoformat(),
            "amount_low": self.amount_low,
            "amount_high": self.amount_high,
            "amount_estimate": self.amount_estimate,
            "filing_delay_days": self.filing_delay_days,
            "chamber": self.chamber,
            "party": self.party,
            "state": self.state,
            "district": self.district,
            "owner": self.owner,
            "asset_description": self.asset_description,
            "committees": self.committees,
            "source": self.source,
            "collected_at": self.collected_at.isoformat(),
        }


# Amount range mapping from disclosure forms
AMOUNT_RANGES = {
    "$1,001 - $15,000": (1001, 15000),
    "$15,001 - $50,000": (15001, 50000),
    "$50,001 - $100,000": (50001, 100000),
    "$100,001 - $250,000": (100001, 250000),
    "$250,001 - $500,000": (250001, 500000),
    "$500,001 - $1,000,000": (500001, 1000000),
    "$1,000,001 - $5,000,000": (1000001, 5000000),
    "$5,000,001 - $25,000,000": (5000001, 25000000),
    "$25,000,001 - $50,000,000": (25000001, 50000000),
    "Over $50,000,000": (50000001, 100000000),
}


def parse_amount_range(amount_str: str) -> tuple[float, float]:
    """Parse amount range string to (low, high) tuple."""
    if not amount_str:
        return (0, 0)

    # Direct match
    if amount_str in AMOUNT_RANGES:
        return AMOUNT_RANGES[amount_str]

    # Try key matching
    for key, val in AMOUNT_RANGES.items():
        if key in amount_str:
            return val

    # Try to extract numbers
    import re
    numbers = re.findall(r'[\d,]+', amount_str)
    if len(numbers) >= 2:
        low = float(numbers[0].replace(',', ''))
        high = float(numbers[1].replace(',', ''))
        return (low, high)
    elif len(numbers) == 1:
        val = float(numbers[0].replace(',', ''))
        return (val, val)

    return (0, 0)


def parse_trade_type(type_str: str) -> str:
    """Normalize trade type string."""
    if not type_str:
        return "unknown"

    type_lower = type_str.lower()
    if "purchase" in type_lower or "buy" in type_lower:
        return "purchase"
    elif "sale_full" in type_lower or "full" in type_lower:
        return "sale_full"
    elif "sale_partial" in type_lower or "partial" in type_lower:
        return "sale_partial"
    elif "sale" in type_lower or "sell" in type_lower:
        return "sale"
    elif "exchange" in type_lower:
        return "exchange"
    return "unknown"


class CongressionalArchiver:
    """Archive and manage historical congressional trading data."""

    # GitHub data sources
    GITHUB_SOURCES = {
        "house_all_transactions": {
            "url": "https://raw.githubusercontent.com/noodleslove/House-of-Representative-Analysis-I/main/data/all_transactions.csv",
            "format": "csv",
            "chamber": "house",
        },
        "house_committees": {
            "url": "https://raw.githubusercontent.com/adrianmross/congress_trades_dashboard/main/data/inputs/house_committees.csv",
            "format": "csv",
            "type": "metadata",
        },
    }

    def __init__(self, archive_dir: Path | None = None):
        """Initialize archiver.

        Args:
            archive_dir: Directory for storing archived data.
                        Defaults to ~/quant_results/congressional_archive/
        """
        self.archive_dir = archive_dir or paths.base / "congressional_archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        self.raw_dir = self.archive_dir / "raw"
        self.processed_dir = self.archive_dir / "processed"
        self.daily_dir = self.archive_dir / "daily"

        for d in [self.raw_dir, self.processed_dir, self.daily_dir]:
            d.mkdir(exist_ok=True)

        self._client: httpx.AsyncClient | None = None
        self._committee_data: pd.DataFrame | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=60.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "QuantSuite/1.0 Congressional Research",
                    "Accept": "text/csv, application/json, */*",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def backfill_from_github(self) -> dict[str, Any]:
        """
        Download historical data from GitHub repositories.

        Returns:
            Summary of downloaded data.
        """
        logger.info("Starting GitHub backfill...")
        results = {}

        client = await self._get_client()

        for source_name, source_info in self.GITHUB_SOURCES.items():
            try:
                logger.info(f"Downloading {source_name}...")
                resp = await client.get(source_info["url"])
                resp.raise_for_status()

                # Save raw file
                ext = "csv" if source_info["format"] == "csv" else "json"
                raw_path = self.raw_dir / f"{source_name}.{ext}"
                with open(raw_path, "wb") as f:
                    f.write(resp.content)

                # Parse if it's transaction data
                if source_info.get("type") != "metadata":
                    if source_info["format"] == "csv":
                        df = pd.read_csv(raw_path)
                        results[source_name] = {
                            "rows": len(df),
                            "path": str(raw_path),
                        }
                        logger.info(f"  Downloaded {len(df)} rows")
                    else:
                        data = resp.json()
                        results[source_name] = {
                            "records": len(data) if isinstance(data, list) else 1,
                            "path": str(raw_path),
                        }
                else:
                    results[source_name] = {"path": str(raw_path), "type": "metadata"}

            except Exception as e:
                logger.error(f"Error downloading {source_name}: {e}")
                results[source_name] = {"error": str(e)}

        # Process downloaded data into unified format
        await self._process_raw_data()

        return results

    async def _process_raw_data(self) -> None:
        """Process raw downloaded data into unified format."""
        logger.info("Processing raw data...")

        all_trades = []

        # Process House transactions
        house_path = self.raw_dir / "house_all_transactions.csv"
        if house_path.exists():
            df = pd.read_csv(house_path)
            logger.info(f"Processing {len(df)} House transactions...")

            for _, row in df.iterrows():
                try:
                    # Parse dates
                    trans_date = pd.to_datetime(row.get("transaction_date"))
                    disc_date = pd.to_datetime(row.get("disclosure_date"), format="%m/%d/%Y")

                    # Parse amount
                    amount_low, amount_high = parse_amount_range(str(row.get("amount", "")))

                    trade = CongressionalTradeRecord(
                        politician=str(row.get("representative", "")).replace("Hon. ", ""),
                        symbol=str(row.get("ticker", "")).upper(),
                        trade_type=parse_trade_type(str(row.get("type", ""))),
                        transaction_date=trans_date,
                        disclosure_date=disc_date,
                        amount_low=amount_low,
                        amount_high=amount_high,
                        chamber="house",
                        district=str(row.get("district", "")),
                        owner=str(row.get("owner", "")),
                        asset_description=str(row.get("asset_description", "")),
                        source="github_noodleslove",
                    )

                    if trade.symbol and len(trade.symbol) <= 10:
                        all_trades.append(trade)

                except Exception as e:
                    logger.debug(f"Error processing row: {e}")

        # Deduplicate
        seen_keys = set()
        unique_trades = []
        for trade in all_trades:
            if trade.unique_key not in seen_keys:
                seen_keys.add(trade.unique_key)
                unique_trades.append(trade)

        logger.info(f"Processed {len(unique_trades)} unique trades")

        # Save to parquet
        if unique_trades:
            df = pd.DataFrame([t.to_dict() for t in unique_trades])
            parquet_path = self.processed_dir / "all_trades.parquet"
            df.to_parquet(parquet_path, index=False)
            logger.info(f"Saved to {parquet_path}")

            # Also save as JSON for easier inspection
            json_path = self.processed_dir / "all_trades.json"
            with open(json_path, "w") as f:
                json.dump([t.to_dict() for t in unique_trades], f, indent=2)

    def load_all_trades(self) -> pd.DataFrame:
        """Load all archived trades."""
        parquet_path = self.processed_dir / "all_trades.parquet"
        if parquet_path.exists():
            return pd.read_parquet(parquet_path)

        # Fall back to daily files
        daily_files = sorted(self.daily_dir.glob("*.parquet"))
        if daily_files:
            dfs = [pd.read_parquet(f) for f in daily_files]
            return pd.concat(dfs, ignore_index=True)

        return pd.DataFrame()

    def get_summary(self) -> dict[str, Any]:
        """Get summary of archived data."""
        df = self.load_all_trades()

        if df.empty:
            return {"status": "empty", "message": "No archived data. Run backfill_from_github() first."}

        return {
            "total_trades": len(df),
            "unique_politicians": df["politician"].nunique(),
            "unique_symbols": df["symbol"].nunique(),
            "date_range": {
                "earliest": df["transaction_date"].min(),
                "latest": df["transaction_date"].max(),
            },
            "by_chamber": df["chamber"].value_counts().to_dict(),
            "by_trade_type": df["trade_type"].value_counts().to_dict(),
            "top_traders": df["politician"].value_counts().head(10).to_dict(),
            "top_symbols": df["symbol"].value_counts().head(10).to_dict(),
        }

    async def collect_daily(self) -> dict[str, Any]:
        """
        Collect new trades (designed for daily cron job).

        Note: This requires external API access which may be blocked
        in restricted environments.
        """
        from src.data.sources.alternative.congressional_trades import (
            CongressionalTradesSource,
        )

        source = CongressionalTradesSource()
        try:
            trades = await source.fetch_recent_trades(days=7)

            if not trades:
                return {"status": "no_trades", "message": "No new trades found"}

            # Convert to records
            records = []
            for t in trades:
                record = CongressionalTradeRecord(
                    politician=t.politician,
                    symbol=t.symbol,
                    trade_type=t.trade_type.value,
                    transaction_date=t.transaction_date,
                    disclosure_date=t.disclosure_date,
                    amount_low=t.amount_low,
                    amount_high=t.amount_high,
                    chamber=t.chamber.value,
                    party=t.party or "",
                    state=t.state or "",
                    asset_description=t.asset_description or "",
                    source="rss_live",
                )
                records.append(record)

            # Save daily file
            date_str = datetime.now().strftime("%Y-%m-%d")
            daily_path = self.daily_dir / f"trades_{date_str}.parquet"

            df = pd.DataFrame([r.to_dict() for r in records])
            df.to_parquet(daily_path, index=False)

            return {
                "status": "success",
                "trades_collected": len(records),
                "path": str(daily_path),
            }

        finally:
            await source.close()


async def run_backfill():
    """Run historical backfill."""
    archiver = CongressionalArchiver()
    try:
        results = await archiver.backfill_from_github()
        print("\nBackfill Results:")
        print(json.dumps(results, indent=2))

        print("\nArchive Summary:")
        summary = archiver.get_summary()
        print(json.dumps(summary, indent=2, default=str))
    finally:
        await archiver.close()


if __name__ == "__main__":
    asyncio.run(run_backfill())
