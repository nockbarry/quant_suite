#!/usr/bin/env python3
"""
Implied Volatility Rank Calculator

Calculates IV rank and IV percentile for options analysis.
IV Rank = (Current IV - 52wk Low IV) / (52wk High IV - 52wk Low IV)

Usage:
    from src.data.sources.alternative.iv_rank import IVRankCalculator

    calculator = IVRankCalculator()
    rank_data = calculator.get_iv_rank("SLB")
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from src.core.paths import paths

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = paths.options_analysis


@dataclass
class IVRankResult:
    """Result of IV rank calculation."""
    symbol: str
    timestamp: datetime
    current_iv: float
    iv_rank: float  # 0-100%
    iv_percentile: float  # 0-100%
    iv_52wk_high: float
    iv_52wk_low: float
    iv_30day_avg: float
    atm_call_iv: float | None
    atm_put_iv: float | None
    iv_skew: float | None  # Put IV - Call IV
    signal: str  # "cheap", "expensive", "normal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "current_iv": self.current_iv,
            "iv_rank": self.iv_rank,
            "iv_percentile": self.iv_percentile,
            "iv_52wk_high": self.iv_52wk_high,
            "iv_52wk_low": self.iv_52wk_low,
            "iv_30day_avg": self.iv_30day_avg,
            "atm_call_iv": self.atm_call_iv,
            "atm_put_iv": self.atm_put_iv,
            "iv_skew": self.iv_skew,
            "signal": self.signal,
        }


class IVRankCalculator:
    """Calculate IV rank and percentile for options analysis."""

    def __init__(self, lookback_days: int = 365):
        self.lookback_days = lookback_days
        self.iv_cache: dict[str, pd.DataFrame] = {}

    def _get_historical_iv(self, symbol: str) -> pd.DataFrame:
        """Get historical IV data using yfinance options chain."""
        if symbol in self.iv_cache:
            return self.iv_cache[symbol]

        try:
            ticker = yf.Ticker(symbol)

            # Get current price for ATM calculation
            hist = ticker.history(period="5d")
            if hist.empty:
                raise ValueError(f"No price data for {symbol}")
            current_price = hist["Close"].iloc[-1]

            # Get options chain
            expirations = ticker.options
            if not expirations:
                raise ValueError(f"No options data for {symbol}")

            iv_data = []

            # Sample first 6 expirations for IV data
            for exp in expirations[:6]:
                try:
                    chain = ticker.option_chain(exp)
                    calls = chain.calls
                    puts = chain.puts

                    # Find ATM options (closest to current price)
                    call_iv = None
                    put_iv = None

                    if not calls.empty:
                        calls_sorted = calls.iloc[(calls['strike'] - current_price).abs().argsort()]
                        if len(calls_sorted) > 0:
                            atm_call = calls_sorted.iloc[0]
                            if 'impliedVolatility' in atm_call and pd.notna(atm_call['impliedVolatility']):
                                call_iv = float(atm_call['impliedVolatility'])

                    if not puts.empty:
                        puts_sorted = puts.iloc[(puts['strike'] - current_price).abs().argsort()]
                        if len(puts_sorted) > 0:
                            atm_put = puts_sorted.iloc[0]
                            if 'impliedVolatility' in atm_put and pd.notna(atm_put['impliedVolatility']):
                                put_iv = float(atm_put['impliedVolatility'])

                    if call_iv is not None or put_iv is not None:
                        avg_iv = np.nanmean([v for v in [call_iv, put_iv] if v is not None])
                        iv_data.append({
                            "expiration": exp,
                            "call_iv": call_iv,
                            "put_iv": put_iv,
                            "avg_iv": avg_iv,
                        })

                except Exception as e:
                    logger.debug(f"Error getting chain for {symbol} {exp}: {e}")
                    continue

            if not iv_data:
                raise ValueError(f"No IV data extracted for {symbol}")

            df = pd.DataFrame(iv_data)
            # yfinance returns IV as decimals (0.30 = 30%)
            # Keep as decimals for consistency with realized vol
            self.iv_cache[symbol] = df
            return df

        except Exception as e:
            logger.error(f"Error getting historical IV for {symbol}: {e}")
            raise

    def _estimate_historical_iv_from_returns(self, symbol: str) -> dict:
        """Estimate historical IV range from realized volatility."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")

            if hist.empty or len(hist) < 30:
                raise ValueError(f"Insufficient history for {symbol}")

            # Calculate rolling realized volatility (annualized)
            returns = hist["Close"].pct_change().dropna()

            # 20-day rolling volatility (annualized)
            rolling_vol = returns.rolling(window=20).std() * np.sqrt(252)
            rolling_vol = rolling_vol.dropna()

            if rolling_vol.empty:
                raise ValueError(f"Could not calculate rolling vol for {symbol}")

            # IV typically trades at premium to realized vol (VRP)
            # Estimate IV as realized vol * 1.1 to 1.3
            vrp_factor = 1.15

            return {
                "current_rv": rolling_vol.iloc[-1],
                "rv_52wk_high": rolling_vol.max(),
                "rv_52wk_low": rolling_vol.min(),
                "rv_30day_avg": rolling_vol.tail(30).mean(),
                "estimated_iv_high": rolling_vol.max() * vrp_factor,
                "estimated_iv_low": rolling_vol.min() * vrp_factor,
                "estimated_current_iv": rolling_vol.iloc[-1] * vrp_factor,
            }

        except Exception as e:
            logger.error(f"Error estimating IV from returns for {symbol}: {e}")
            raise

    def get_iv_rank(self, symbol: str) -> IVRankResult:
        """
        Calculate volatility rank for a symbol.

        Uses realized volatility since free options IV data is unreliable.
        Vol Rank = (Current 20d Vol - 52wk Low Vol) / (52wk High Vol - 52wk Low Vol)

        Returns:
            IVRankResult with volatility rank, percentile, and trading signal
        """
        # Get historical realized vol data
        rv_data = self._estimate_historical_iv_from_returns(symbol)

        # Use realized vol (annualized 20-day rolling) as current "IV" proxy
        current_rv = rv_data["current_rv"]
        rv_52wk_high = rv_data["rv_52wk_high"]
        rv_52wk_low = rv_data["rv_52wk_low"]
        rv_30day_avg = rv_data["rv_30day_avg"]

        # Apply volatility risk premium estimate (IV typically 10-20% above RV)
        vrp_factor = 1.15
        current_iv = current_rv * vrp_factor
        iv_52wk_high = rv_52wk_high * vrp_factor
        iv_52wk_low = rv_52wk_low * vrp_factor
        iv_30day_avg = rv_30day_avg * vrp_factor

        # Calculate Vol Rank (where current vol sits in 52-week range)
        if rv_52wk_high > rv_52wk_low:
            vol_rank = (current_rv - rv_52wk_low) / (rv_52wk_high - rv_52wk_low)
            vol_rank = max(0, min(1, vol_rank))  # Clamp to 0-1
        else:
            vol_rank = 0.5

        # Try to get options skew data (less reliable but worth checking)
        atm_call_iv = None
        atm_put_iv = None
        iv_skew = None

        try:
            iv_df = self._get_historical_iv(symbol)
            # Filter out placeholder values (0.00001)
            valid_calls = iv_df["call_iv"].dropna()
            valid_puts = iv_df["put_iv"].dropna()
            valid_calls = valid_calls[valid_calls > 0.01]  # Must be > 1%
            valid_puts = valid_puts[valid_puts > 0.01]

            if not valid_calls.empty:
                atm_call_iv = valid_calls.iloc[0]
            if not valid_puts.empty:
                atm_put_iv = valid_puts.iloc[0]

            if atm_call_iv and atm_put_iv:
                iv_skew = atm_put_iv - atm_call_iv
        except Exception:
            pass  # Options data not available

        # Generate signal based on vol rank
        if vol_rank < 0.30:
            signal = "cheap"  # Low vol = options cheap, good for buying
        elif vol_rank > 0.70:
            signal = "expensive"  # High vol = options expensive, good for selling
        else:
            signal = "normal"

        return IVRankResult(
            symbol=symbol,
            timestamp=datetime.now(),
            current_iv=current_iv,
            iv_rank=vol_rank * 100,  # Convert to percentage
            iv_percentile=vol_rank * 100,
            iv_52wk_high=iv_52wk_high,
            iv_52wk_low=iv_52wk_low,
            iv_30day_avg=iv_30day_avg,
            atm_call_iv=atm_call_iv,
            atm_put_iv=atm_put_iv,
            iv_skew=iv_skew,
            signal=signal,
        )

    def get_iv_ranks_batch(self, symbols: list[str]) -> dict[str, IVRankResult]:
        """Get IV ranks for multiple symbols."""
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.get_iv_rank(symbol)
            except Exception as e:
                logger.error(f"Failed to get IV rank for {symbol}: {e}")
        return results

    def print_iv_report(self, symbols: list[str]) -> None:
        """Print formatted IV rank report."""
        print("\n" + "=" * 80)
        print("IV RANK REPORT")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 80)

        results = self.get_iv_ranks_batch(symbols)

        # Sort by IV rank (cheapest first for buying opportunities)
        sorted_results = sorted(results.values(), key=lambda x: x.iv_rank)

        print(f"\n{'Symbol':<8} {'IV Rank':<10} {'Current IV':<12} {'52wk Range':<20} {'Signal':<12}")
        print("-" * 80)

        for r in sorted_results:
            range_str = f"{r.iv_52wk_low:.1%} - {r.iv_52wk_high:.1%}"
            signal_display = f"[{r.signal.upper()}]" if r.signal != "normal" else r.signal
            print(f"{r.symbol:<8} {r.iv_rank:>6.1f}%    {r.current_iv:>8.1%}    {range_str:<20} {signal_display:<12}")

        # Highlight opportunities
        cheap = [r for r in sorted_results if r.signal == "cheap"]
        expensive = [r for r in sorted_results if r.signal == "expensive"]

        if cheap:
            print("\n[CHEAP OPTIONS - Good for buying]")
            for r in cheap:
                print(f"  {r.symbol}: IV Rank {r.iv_rank:.1f}% - Options are relatively cheap")

        if expensive:
            print("\n[EXPENSIVE OPTIONS - Good for selling]")
            for r in expensive:
                print(f"  {r.symbol}: IV Rank {r.iv_rank:.1f}% - Options are relatively expensive")


def main():
    """Test IV rank calculator with Venezuela thesis symbols."""
    calculator = IVRankCalculator()

    # Venezuela thesis symbols
    symbols = ["SLB", "VLO", "HAL", "XLE", "GLD", "FRO", "STNG", "CNQ"]

    calculator.print_iv_report(symbols)


if __name__ == "__main__":
    main()
