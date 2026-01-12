#!/usr/bin/env python3
"""Daily Insider Trades Collector.

Designed to run as a daily cron job to archive insider trading activity.

Cron setup (run daily at 7 AM):
    0 7 * * * cd /home/nock/projects/quant_suite && PYTHONPATH=. python3 scripts/cron_insider_collect.py >> /home/nock/quant_results/logs/insider_collect.log 2>&1

Usage:
    PYTHONPATH=. python scripts/cron_insider_collect.py
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.core.paths import paths
from src.data.sources.alternative.insider import InsiderDataSource, find_cluster_buying

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Default watchlist for insider tracking
WATCHLIST = [
    # Major holdings
    "SLB", "HAL", "FRO", "NVDA", "MSFT", "CEG", "GLD",
    # Tech
    "AAPL", "GOOGL", "META", "AMD", "AMZN", "TSLA",
    # Energy
    "XOM", "CVX", "OXY", "XLE",
    # Financials
    "JPM", "BAC", "GS", "XLF",
    # Other
    "SPY", "QQQ", "IWM",
]


async def collect_insider_data():
    """Collect insider trading data and archive it."""
    logger.info("=" * 60)
    logger.info(f"Insider Trades Collection - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    archive_dir = paths.base / "insider_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")

    # Try to load API keys from credentials
    finnhub_key = None
    polygon_key = None
    try:
        creds_path = paths.base.parent / "projects" / "quant_suite" / "config" / "credentials.yaml"
        if creds_path.exists():
            import yaml
            with open(creds_path) as f:
                creds = yaml.safe_load(f)
            finnhub_key = creds.get("finnhub", {}).get("api_key")
            polygon_key = creds.get("polygon", {}).get("api_key")
    except Exception as e:
        logger.debug(f"Could not load credentials: {e}")

    source = InsiderDataSource(
        finnhub_key=finnhub_key,
        polygon_key=polygon_key,
        cache_ttl_minutes=60,
    )

    all_transactions = []
    summaries = []

    try:
        # Collect transactions for each symbol in watchlist
        for symbol in WATCHLIST:
            try:
                logger.info(f"  Fetching insider data for {symbol}...")

                # Get last 90 days of transactions
                end_date = datetime.now()
                start_date = end_date - timedelta(days=90)

                transactions = await source.fetch_transactions(
                    symbol=symbol,
                    start=start_date,
                    end=end_date,
                    limit=100,
                )

                if transactions:
                    for t in transactions:
                        all_transactions.append(t.to_dict())
                    logger.info(f"    Found {len(transactions)} transactions")

                # Get summary
                summary = await source.get_summary(symbol, days=90)
                if summary.total_purchases > 0 or summary.total_sales > 0:
                    summary_dict = summary.to_dict()
                    summaries.append(summary_dict)

                await asyncio.sleep(0.3)  # Rate limiting

            except Exception as e:
                logger.warning(f"  Error fetching {symbol}: {e}")

        # Find cluster buying across broader universe
        logger.info("Scanning for cluster buying patterns...")
        cluster_stocks = await find_cluster_buying(
            symbols=WATCHLIST,
            days=30,
            finnhub_key=finnhub_key,
            polygon_key=polygon_key,
        )

        cluster_buying = [s.to_dict() for s in cluster_stocks]
        logger.info(f"  Found {len(cluster_buying)} stocks with cluster buying")

        # Save to archive
        result = {
            "status": "success",
            "date": today,
            "timestamp": datetime.now().isoformat(),
            "transactions_collected": len(all_transactions),
            "symbols_with_activity": len(summaries),
            "cluster_buying_count": len(cluster_buying),
        }

        # Save transactions as parquet
        if all_transactions:
            df = pd.DataFrame(all_transactions)
            df["collection_date"] = today

            transactions_file = archive_dir / "transactions" / f"{today}.parquet"
            transactions_file.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(transactions_file, index=False)
            result["transactions_path"] = str(transactions_file)
            logger.info(f"Saved transactions to {transactions_file}")

            # Update consolidated archive
            all_trades_path = archive_dir / "all_transactions.parquet"
            if all_trades_path.exists():
                existing = pd.read_parquet(all_trades_path)
                combined = pd.concat([existing, df]).drop_duplicates(
                    subset=["symbol", "insider_name", "transaction_date", "shares"],
                    keep="last"
                )
                combined.to_parquet(all_trades_path, index=False)
            else:
                df.to_parquet(all_trades_path, index=False)
            logger.info(f"Updated consolidated archive: {all_trades_path}")

        # Save summaries
        if summaries:
            summaries_file = archive_dir / "summaries" / f"{today}.json"
            summaries_file.parent.mkdir(parents=True, exist_ok=True)
            with open(summaries_file, "w") as f:
                json.dump(summaries, f, indent=2, default=str)
            result["summaries_path"] = str(summaries_file)
            logger.info(f"Saved summaries to {summaries_file}")

        # Save cluster buying
        if cluster_buying:
            cluster_file = archive_dir / "cluster_buying" / f"{today}.json"
            cluster_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cluster_file, "w") as f:
                json.dump(cluster_buying, f, indent=2, default=str)
            result["cluster_path"] = str(cluster_file)
            logger.info(f"Saved cluster buying to {cluster_file}")

        # Save collection log
        log_dir = paths.base / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / "insider_collection_history.json"
        history = []
        if log_file.exists():
            with open(log_file) as f:
                history = json.load(f)

        history.append({
            "timestamp": datetime.now().isoformat(),
            "result": result,
        })

        # Keep last 90 days of history
        history = history[-90:]

        with open(log_file, "w") as f:
            json.dump(history, f, indent=2)

        logger.info(f"Collection complete: {result['transactions_collected']} transactions")
        return result

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        return {"status": "error", "error": str(e)}

    finally:
        await source.close()


async def get_recent_insider_buys(days: int = 7) -> list[dict]:
    """Helper function to get recent insider buys for SignalAggregator."""
    archive_path = paths.base / "insider_archive" / "all_transactions.parquet"

    if not archive_path.exists():
        return []

    try:
        df = pd.read_parquet(archive_path)

        # Filter to purchases only
        df = df[df["is_purchase"] == True]

        # Filter to recent transactions
        cutoff = datetime.now() - timedelta(days=days)
        df["transaction_date"] = pd.to_datetime(df["transaction_date"])
        df = df[df["transaction_date"] >= cutoff]

        # Sort by value
        df = df.sort_values("value", ascending=False)

        return df.to_dict(orient="records")

    except Exception as e:
        logger.error(f"Error reading insider archive: {e}")
        return []


def main():
    result = asyncio.run(collect_insider_data())
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
