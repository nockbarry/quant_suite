#!/usr/bin/env python3
"""
Historical Data Collection Script

Collects 6 months of historical data for backtesting:
- VIX spot and term structure estimates
- Market breadth indicators
- Major ETF prices (SPY, QQQ, IWM)
- Sector ETF prices
- Put/call estimates from historical VIX levels
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Required: pip install yfinance pandas")
    sys.exit(1)

from src.core.paths import paths


def collect_vix_history(months: int = 6) -> dict:
    """Collect VIX historical data."""
    print(f"Collecting {months} months of VIX data...")

    vix = yf.Ticker("^VIX")
    hist = vix.history(period=f"{months}mo")

    if hist.empty:
        print("  No VIX data returned")
        return {}

    records = []
    for date, row in hist.iterrows():
        spot = float(row["Close"])

        # Estimate term structure based on VIX level
        # High VIX -> flatter/backwardation, Low VIX -> steeper contango
        if spot > 30:
            slope = -0.05  # Backwardation
            structure = "backwardation"
        elif spot > 25:
            slope = 0.0  # Flat
            structure = "flat"
        elif spot < 15:
            slope = 0.12  # Steep contango
            structure = "steep_contango"
        else:
            slope = 0.05  # Normal contango
            structure = "contango"

        records.append({
            "date": date.strftime("%Y-%m-%d"),
            "vix_spot": spot,
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "slope_estimate": slope,
            "structure": structure,
            "signal": -0.8 if structure == "steep_contango" else (-0.4 if structure == "contango" else (0.5 if structure == "backwardation" else 0.0))
        })

    print(f"  Collected {len(records)} days of VIX data")
    return {"vix": records}


def collect_etf_history(months: int = 6) -> dict:
    """Collect major ETF price history."""
    print(f"Collecting {months} months of ETF data...")

    etfs = {
        "SPY": "S&P 500",
        "QQQ": "NASDAQ 100",
        "IWM": "Russell 2000",
        "DIA": "Dow Jones",
        "TLT": "20+ Year Treasury",
        "GLD": "Gold",
        "USO": "Oil",
        "XLF": "Financials",
        "XLE": "Energy",
        "XLK": "Technology",
        "XLV": "Healthcare",
        "XLI": "Industrials",
        "XLP": "Consumer Staples",
        "XLY": "Consumer Discretionary",
    }

    all_data = {}

    for symbol, name in etfs.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{months}mo")

            if hist.empty:
                continue

            records = []
            for date, row in hist.iterrows():
                records.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                })

            all_data[symbol] = {
                "name": name,
                "records": records
            }
            print(f"  {symbol}: {len(records)} days")

        except Exception as e:
            print(f"  {symbol}: Error - {e}")

    return {"etfs": all_data}


def collect_market_breadth_history(months: int = 6) -> dict:
    """Estimate historical market breadth from sector performance."""
    print(f"Estimating {months} months of market breadth...")

    # Get SPY for dates
    spy = yf.Ticker("SPY")
    spy_hist = spy.history(period=f"{months}mo")

    if spy_hist.empty:
        return {}

    # Get sector ETFs
    sectors = ["XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLU", "XLRE", "XLB", "XLC"]
    sector_data = {}

    for sym in sectors:
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period=f"{months}mo")
            if not hist.empty:
                sector_data[sym] = hist["Close"]
        except:
            pass

    if len(sector_data) < 5:
        print("  Not enough sector data")
        return {}

    # Create breadth estimates
    records = []
    for date in spy_hist.index:
        date_str = date.strftime("%Y-%m-%d")

        # Count sectors above their 20-day MA
        advancing = 0
        for sym, data in sector_data.items():
            if date in data.index:
                try:
                    current = data.loc[date]
                    ma20 = data.loc[:date].tail(20).mean()
                    if current > ma20:
                        advancing += 1
                except:
                    pass

        pct_advancing = advancing / len(sector_data) if sector_data else 0.5

        # Estimate breadth signal
        if pct_advancing > 0.8:
            signal = "strong"
            breadth_signal = 0.8
        elif pct_advancing > 0.6:
            signal = "healthy"
            breadth_signal = 0.4
        elif pct_advancing > 0.4:
            signal = "neutral"
            breadth_signal = 0.0
        elif pct_advancing > 0.2:
            signal = "weak"
            breadth_signal = -0.4
        else:
            signal = "very_weak"
            breadth_signal = -0.8

        records.append({
            "date": date_str,
            "pct_advancing": round(pct_advancing, 2),
            "signal": signal,
            "breadth_signal": breadth_signal,
        })

    print(f"  Collected {len(records)} days of breadth estimates")
    return {"breadth": records}


def save_historical_data(data: dict, filename: str):
    """Save data to JSON file."""
    history_dir = paths.live / "historical_data"
    history_dir.mkdir(parents=True, exist_ok=True)

    filepath = history_dir / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {filepath}")


def collect_put_call_history(months: int = 6) -> dict:
    """Estimate historical put/call ratios from SPY options."""
    print(f"Estimating {months} months of put/call data...")

    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(period=f"{months}mo")

        if hist.empty:
            print("  No SPY data returned")
            return {}

        records = []
        for date, row in hist.iterrows():
            # Estimate P/C based on market behavior
            close = float(row["Close"])
            prev_close = hist["Close"].shift(1).loc[date] if len(hist) > 1 else close

            if pd.notna(prev_close):
                daily_return = (close - prev_close) / prev_close
            else:
                daily_return = 0

            # P/C tends to be higher on down days (fear)
            if daily_return < -0.02:
                pc_ratio = 1.3 + abs(daily_return) * 10
            elif daily_return < -0.01:
                pc_ratio = 1.1
            elif daily_return > 0.02:
                pc_ratio = 0.6
            elif daily_return > 0.01:
                pc_ratio = 0.8
            else:
                pc_ratio = 0.95

            records.append({
                "date": date.strftime("%Y-%m-%d"),
                "estimated_pc_ratio": round(pc_ratio, 2),
                "daily_return": round(daily_return * 100, 2),
                "signal": "bullish" if pc_ratio > 1.2 else "bearish" if pc_ratio < 0.7 else "neutral"
            })

        print(f"  Collected {len(records)} days of P/C estimates")
        return {"put_call": records}

    except Exception as e:
        print(f"  Error: {e}")
        return {}


def collect_short_interest_history(symbols: list, months: int = 6) -> dict:
    """Collect short interest for key stocks."""
    print(f"Collecting short interest data for {len(symbols)} symbols...")

    all_data = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            short_pct = info.get("shortPercentOfFloat", 0)
            short_ratio = info.get("shortRatio", 0)

            all_data[symbol] = {
                "short_percent_of_float": short_pct,
                "short_ratio": short_ratio,
                "shares_short": info.get("sharesShort", 0),
                "timestamp": datetime.now().isoformat()
            }
            print(f"  {symbol}: {short_pct:.1%} short")

        except Exception as e:
            print(f"  {symbol}: Error - {e}")

    print(f"  Collected short interest for {len(all_data)} symbols")
    return {"short_interest": all_data}


def collect_volatility_history(months: int = 6) -> dict:
    """Collect IV and HV history for key indices."""
    print(f"Collecting {months} months of volatility data...")

    symbols = ["SPY", "QQQ", "IWM"]
    all_data = {}

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{months}mo")

            if hist.empty:
                continue

            records = []
            for i, (date, row) in enumerate(hist.iterrows()):
                # Calculate 20-day realized volatility
                if i >= 20:
                    returns = hist["Close"].iloc[i-20:i].pct_change().dropna()
                    hv_20 = float(returns.std() * (252 ** 0.5) * 100)
                else:
                    hv_20 = 15.0

                records.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "close": float(row["Close"]),
                    "hv_20d": round(hv_20, 2),
                })

            all_data[symbol] = records
            print(f"  {symbol}: {len(records)} days")

        except Exception as e:
            print(f"  {symbol}: Error - {e}")

    print(f"  Collected volatility for {len(all_data)} symbols")
    return {"volatility": all_data}


def main():
    print("=" * 60)
    print("  COMPREHENSIVE HISTORICAL DATA COLLECTION")
    print("  Collecting 6 months of data for backtesting")
    print("=" * 60)

    months = 6

    # Collect VIX history
    vix_data = collect_vix_history(months)
    if vix_data:
        save_historical_data(vix_data, "vix_history_6mo.json")

    # Collect ETF history
    etf_data = collect_etf_history(months)
    if etf_data:
        save_historical_data(etf_data, "etf_history_6mo.json")

    # Collect breadth estimates
    breadth_data = collect_market_breadth_history(months)
    if breadth_data:
        save_historical_data(breadth_data, "breadth_history_6mo.json")

    # Collect put/call estimates
    pc_data = collect_put_call_history(months)
    if pc_data:
        save_historical_data(pc_data, "put_call_history_6mo.json")

    # Collect short interest for key stocks
    short_symbols = ["GME", "AMC", "TSLA", "NVDA", "AAPL", "META", "AMZN"]
    short_data = collect_short_interest_history(short_symbols, months)
    if short_data:
        save_historical_data(short_data, "short_interest_snapshot.json")

    # Collect volatility history
    vol_data = collect_volatility_history(months)
    if vol_data:
        save_historical_data(vol_data, "volatility_history_6mo.json")

    # Generate summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    summary = {
        "collection_date": datetime.now().isoformat(),
        "period_months": months,
        "vix_records": len(vix_data.get("vix", [])),
        "etfs_collected": len(etf_data.get("etfs", {})),
        "breadth_records": len(breadth_data.get("breadth", [])),
        "put_call_records": len(pc_data.get("put_call", [])),
        "short_interest_symbols": len(short_data.get("short_interest", {})),
        "volatility_symbols": len(vol_data.get("volatility", {})),
    }

    print(f"VIX records: {summary['vix_records']}")
    print(f"ETFs collected: {summary['etfs_collected']}")
    print(f"Breadth records: {summary['breadth_records']}")
    print(f"Put/Call records: {summary['put_call_records']}")
    print(f"Short interest symbols: {summary['short_interest_symbols']}")
    print(f"Volatility symbols: {summary['volatility_symbols']}")

    save_historical_data(summary, "collection_summary.json")

    print("\nHistorical data collection complete!")
    print(f"Data saved to: {paths.live / 'historical_data'}")


if __name__ == "__main__":
    main()
