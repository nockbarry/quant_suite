#!/usr/bin/env python3
"""
Fetch minute-level OHLCV data from Alpaca for Venezuela thesis testing.

Usage:
    PYTHONPATH=. python scripts/fetch_minute_data.py
    PYTHONPATH=. python scripts/fetch_minute_data.py --symbols SLB VLO --days 5
"""

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Venezuela thesis target symbols
VENEZUELA_SYMBOLS = [
    "SLB",   # Schlumberger - oilfield services, 15 rigs in Venezuela
    "VLO",   # Valero - heavy crude refiner
    "HAL",   # Halliburton - oilfield services
    "XLE",   # Energy sector ETF
    "GLD",   # Gold - safe haven
    "USO",   # Oil proxy
    "OIH",   # Oil services ETF
    "FRO",   # Frontline - tanker
    "STNG",  # Scorpio Tankers
]

# Output directory
OUTPUT_DIR = Path("/home/nock/quant_results/minute_data")


def load_credentials() -> dict:
    """Load Alpaca credentials from config."""
    config_path = Path("/home/nock/projects/quant_suite/config/credentials.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config["alpaca"]


def fetch_minute_bars(
    symbols: list[str],
    days: int = 7,
    api_key: str = None,
    secret_key: str = None,
) -> dict[str, pd.DataFrame]:
    """
    Fetch minute-level bars from Alpaca.

    Args:
        symbols: List of stock symbols
        days: Number of days of history
        api_key: Alpaca API key
        secret_key: Alpaca secret key

    Returns:
        Dict mapping symbol to DataFrame with OHLCV data
    """
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    # Initialize client
    client = StockHistoricalDataClient(
        api_key=api_key,
        secret_key=secret_key,
    )

    # Calculate date range
    end = datetime.now()
    start = end - timedelta(days=days)

    logger.info(f"Fetching {days} days of minute data for {len(symbols)} symbols")
    logger.info(f"Date range: {start.date()} to {end.date()}")

    # Fetch bars
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
    )

    bars = client.get_stock_bars(request)

    # Convert to DataFrames - handle BarSet response
    results = {}

    # The BarSet has a data attribute that's a dict
    bar_data = bars.data if hasattr(bars, 'data') else bars

    for symbol in symbols:
        try:
            if symbol in bar_data:
                symbol_bars = bar_data[symbol]
                if symbol_bars:
                    data = []
                    for bar in symbol_bars:
                        data.append({
                            "timestamp": bar.timestamp,
                            "open": float(bar.open),
                            "high": float(bar.high),
                            "low": float(bar.low),
                            "close": float(bar.close),
                            "volume": int(bar.volume),
                            "vwap": float(bar.vwap) if bar.vwap else None,
                            "trade_count": int(bar.trade_count) if bar.trade_count else None,
                        })
                    df = pd.DataFrame(data)
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df = df.set_index("timestamp")
                    results[symbol] = df
                    logger.info(f"  {symbol}: {len(df)} bars")
                else:
                    logger.warning(f"  {symbol}: No data returned")
            else:
                logger.warning(f"  {symbol}: Not in response")
        except Exception as e:
            logger.warning(f"  {symbol}: Error processing - {e}")

    return results


def save_minute_data(data: dict[str, pd.DataFrame], output_dir: Path) -> None:
    """Save minute data to parquet files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for symbol, df in data.items():
        # Save full dataset
        filepath = output_dir / f"{symbol}_minute.parquet"
        df.to_parquet(filepath)
        logger.info(f"Saved {symbol}: {filepath}")

        # Also save by date for quick lookups
        for date, group in df.groupby(df.index.date):
            date_str = date.strftime("%Y%m%d")
            date_filepath = output_dir / f"{symbol}_{date_str}.parquet"
            group.to_parquet(date_filepath)


def load_minute_data(symbol: str, output_dir: Path = OUTPUT_DIR) -> pd.DataFrame:
    """Load minute data for a symbol."""
    filepath = output_dir / f"{symbol}_minute.parquet"
    if filepath.exists():
        return pd.read_parquet(filepath)
    return pd.DataFrame()


def get_summary_stats(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Generate summary statistics for fetched data."""
    stats = []
    for symbol, df in data.items():
        if not df.empty:
            stats.append({
                "symbol": symbol,
                "bars": len(df),
                "start": df.index.min(),
                "end": df.index.max(),
                "latest_close": df["close"].iloc[-1],
                "avg_volume": df["volume"].mean(),
                "avg_range_pct": ((df["high"] - df["low"]) / df["low"] * 100).mean(),
            })
    return pd.DataFrame(stats)


def main():
    parser = argparse.ArgumentParser(description="Fetch minute data from Alpaca")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=VENEZUELA_SYMBOLS,
        help="Symbols to fetch",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Days of history to fetch",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory",
    )
    args = parser.parse_args()

    # Load credentials
    creds = load_credentials()
    logger.info(f"Using Alpaca {'paper' if creds.get('paper', True) else 'live'} trading")

    # Fetch data
    data = fetch_minute_bars(
        symbols=args.symbols,
        days=args.days,
        api_key=creds["api_key"],
        secret_key=creds["secret_key"],
    )

    if not data:
        logger.error("No data fetched!")
        return

    # Save data
    save_minute_data(data, args.output)

    # Print summary
    stats = get_summary_stats(data)
    print("\n" + "=" * 60)
    print("MINUTE DATA SUMMARY")
    print("=" * 60)
    print(stats.to_string(index=False))
    print("=" * 60)

    # Print latest prices for Venezuela thesis
    print("\nLATEST PRICES (Venezuela Thesis Targets):")
    print("-" * 40)
    for symbol in ["SLB", "VLO", "HAL", "GLD", "XLE"]:
        if symbol in data and not data[symbol].empty:
            latest = data[symbol]["close"].iloc[-1]
            print(f"  {symbol}: ${latest:.2f}")

    print(f"\nData saved to: {args.output}")
    print("Ready for Monday paper trading!")


if __name__ == "__main__":
    main()
