#!/usr/bin/env python3
"""
Comprehensive Signal Validation Study

Backtests all data sources against 5-day forward returns for the last 12 weeks.
For each signal source, computes:
- Hit rate (% of signals where direction was correct)
- Information Coefficient (correlation between signal and forward return)
- Average return when signal is bullish vs bearish
- Signal frequency
- Statistical significance

Usage:
    python scripts/signal_validation_study.py
    python scripts/signal_validation_study.py --symbols SPY QQQ IWM
    python scripts/signal_validation_study.py --weeks 12 --output report.json
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class SignalValidationResult:
    """Results for a single signal source."""
    source_name: str
    description: str
    signal_count: int
    bullish_signals: int
    bearish_signals: int
    hit_rate: float  # % correct direction
    avg_return_bullish: float  # avg 5-day return after bullish signal
    avg_return_bearish: float  # avg 5-day return after bearish signal
    information_coefficient: float  # correlation signal vs return
    t_statistic: float
    p_value: float
    is_significant: bool  # p < 0.05
    sharpe_ratio: float  # Sharpe of signal-following strategy
    max_drawdown: float
    win_rate: float  # % of trades profitable
    avg_win: float
    avg_loss: float
    profit_factor: float  # gross profit / gross loss
    data_quality: str  # "good", "sparse", "missing"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "description": self.description,
            "signal_count": int(self.signal_count),
            "bullish_signals": int(self.bullish_signals),
            "bearish_signals": int(self.bearish_signals),
            "hit_rate": float(round(self.hit_rate, 4)),
            "avg_return_bullish": float(round(self.avg_return_bullish, 4)),
            "avg_return_bearish": float(round(self.avg_return_bearish, 4)),
            "information_coefficient": float(round(self.information_coefficient, 4)),
            "t_statistic": float(round(self.t_statistic, 4)),
            "p_value": float(round(self.p_value, 4)),
            "is_significant": bool(self.is_significant),
            "sharpe_ratio": float(round(self.sharpe_ratio, 4)),
            "max_drawdown": float(round(self.max_drawdown, 4)),
            "win_rate": float(round(self.win_rate, 4)),
            "avg_win": float(round(self.avg_win, 4)),
            "avg_loss": float(round(self.avg_loss, 4)),
            "profit_factor": float(round(self.profit_factor, 4)),
            "data_quality": self.data_quality,
            "notes": self.notes,
        }


@dataclass
class ValidationStudy:
    """Full validation study results."""
    study_date: datetime
    lookback_weeks: int
    symbols_tested: list[str]
    total_sources: int
    sources_with_data: int
    significant_sources: int
    results: list[SignalValidationResult]
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "study_date": self.study_date.isoformat(),
            "lookback_weeks": self.lookback_weeks,
            "symbols_tested": self.symbols_tested,
            "total_sources": self.total_sources,
            "sources_with_data": self.sources_with_data,
            "significant_sources": self.significant_sources,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
        }


class SignalValidator:
    """Validates signal sources against forward returns."""

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path.home() / "quant_results"
        self.price_cache: dict[str, pd.DataFrame] = {}

    def get_price_data(self, symbols: list[str], weeks: int) -> dict[str, pd.DataFrame]:
        """Fetch price data for symbols."""
        end_date = datetime.now()
        start_date = end_date - timedelta(weeks=weeks + 2)  # Extra buffer for forward returns

        price_data = {}
        for symbol in symbols:
            if symbol in self.price_cache:
                price_data[symbol] = self.price_cache[symbol]
                continue

            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(start=start_date, end=end_date)
                if len(df) > 0:
                    # Remove timezone info for easier joining
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    df['forward_5d_return'] = df['Close'].shift(-5) / df['Close'] - 1
                    df['forward_1d_return'] = df['Close'].shift(-1) / df['Close'] - 1
                    price_data[symbol] = df
                    self.price_cache[symbol] = df
                    logger.info(f"Loaded {len(df)} days of data for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to get data for {symbol}: {e}")

        return price_data

    def compute_metrics(
        self,
        signals: pd.Series,
        returns: pd.Series,
        signal_name: str = ""
    ) -> SignalValidationResult:
        """Compute validation metrics for a signal series."""
        # Align signals and returns
        df = pd.DataFrame({
            'signal': signals,
            'return': returns
        }).dropna()

        if len(df) < 10:
            return SignalValidationResult(
                source_name=signal_name,
                description="",
                signal_count=len(df),
                bullish_signals=0,
                bearish_signals=0,
                hit_rate=0,
                avg_return_bullish=0,
                avg_return_bearish=0,
                information_coefficient=0,
                t_statistic=0,
                p_value=1,
                is_significant=False,
                sharpe_ratio=0,
                max_drawdown=0,
                win_rate=0,
                avg_win=0,
                avg_loss=0,
                profit_factor=0,
                data_quality="sparse",
                notes=f"Only {len(df)} data points"
            )

        # Signal classification
        bullish = df[df['signal'] > 0]
        bearish = df[df['signal'] < 0]
        neutral = df[df['signal'] == 0]

        # Hit rate (signal direction matches return direction)
        hits = ((df['signal'] > 0) & (df['return'] > 0)) | ((df['signal'] < 0) & (df['return'] < 0))
        non_neutral = df[df['signal'] != 0]
        hit_rate = hits[df['signal'] != 0].mean() if len(non_neutral) > 0 else 0

        # Average returns
        avg_return_bullish = bullish['return'].mean() if len(bullish) > 0 else 0
        avg_return_bearish = bearish['return'].mean() if len(bearish) > 0 else 0

        # Information Coefficient (Spearman correlation)
        if len(df) >= 5 and df['signal'].std() > 0:
            ic, ic_pval = stats.spearmanr(df['signal'], df['return'])
            ic = ic if not np.isnan(ic) else 0
        else:
            ic, ic_pval = 0, 1

        # T-test for bullish vs bearish returns
        if len(bullish) >= 3 and len(bearish) >= 3:
            t_stat, p_val = stats.ttest_ind(bullish['return'], bearish['return'])
            t_stat = t_stat if not np.isnan(t_stat) else 0
            p_val = p_val if not np.isnan(p_val) else 1
        else:
            t_stat, p_val = 0, 1

        # Strategy metrics (long when bullish, short when bearish)
        df['strategy_return'] = df['signal'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df['return']

        strategy_returns = df[df['signal'] != 0]['strategy_return']
        if len(strategy_returns) > 0:
            sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252 / 5) if strategy_returns.std() > 0 else 0

            # Win/loss metrics
            wins = strategy_returns[strategy_returns > 0]
            losses = strategy_returns[strategy_returns < 0]
            win_rate = len(wins) / len(strategy_returns) if len(strategy_returns) > 0 else 0
            avg_win = wins.mean() if len(wins) > 0 else 0
            avg_loss = abs(losses.mean()) if len(losses) > 0 else 0
            profit_factor = (wins.sum() / abs(losses.sum())) if len(losses) > 0 and losses.sum() != 0 else 0

            # Max drawdown
            cumulative = (1 + strategy_returns).cumprod()
            rolling_max = cumulative.expanding().max()
            drawdown = (cumulative - rolling_max) / rolling_max
            max_dd = abs(drawdown.min()) if len(drawdown) > 0 else 0
        else:
            sharpe, win_rate, avg_win, avg_loss, profit_factor, max_dd = 0, 0, 0, 0, 0, 0

        return SignalValidationResult(
            source_name=signal_name,
            description="",
            signal_count=len(df),
            bullish_signals=len(bullish),
            bearish_signals=len(bearish),
            hit_rate=hit_rate,
            avg_return_bullish=avg_return_bullish,
            avg_return_bearish=avg_return_bearish,
            information_coefficient=ic,
            t_statistic=t_stat,
            p_value=p_val,
            is_significant=p_val < 0.05,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            data_quality="good" if len(df) >= 30 else "sparse",
        )

    # ============ Individual Signal Source Validators ============

    def validate_put_call_ratio(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate put/call ratio as contrarian signal."""
        history_file = self.results_dir / "live" / "historical_data" / "put_call_history_6mo.json"

        if not history_file.exists():
            return self._missing_result("put_call_ratio", "Put/Call ratio file not found")

        with open(history_file) as f:
            data = json.load(f)

        records = data.get("put_call", [])
        if not records:
            return self._missing_result("put_call_ratio", "No put/call data")

        # Build signal series
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.set_index('date')

        # Contrarian signal: high P/C = bullish, low P/C = bearish
        pc_mean = df['estimated_pc_ratio'].mean()
        pc_std = df['estimated_pc_ratio'].std()
        df['signal'] = (df['estimated_pc_ratio'] - pc_mean) / pc_std  # Z-score
        df['signal'] = -df['signal']  # Contrarian

        # Get SPY returns
        if 'SPY' not in price_data:
            return self._missing_result("put_call_ratio", "No SPY price data")

        spy = price_data['SPY']

        # Align and compute
        aligned = df[['signal']].join(spy[['forward_5d_return']], how='inner')

        result = self.compute_metrics(
            aligned['signal'],
            aligned['forward_5d_return'],
            "put_call_ratio"
        )
        result.description = "Contrarian signal: high P/C ratio = bullish"
        return result

    def validate_vix_structure(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate VIX term structure signal."""
        history_file = self.results_dir / "live" / "historical_data" / "vix_history_6mo.json"

        if not history_file.exists():
            return self._missing_result("vix_structure", "VIX history file not found")

        with open(history_file) as f:
            data = json.load(f)

        records = data.get("vix", [])
        if not records:
            return self._missing_result("vix_structure", "No VIX data")

        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.set_index('date')

        # Signal: contango (positive slope) = bullish, backwardation = bearish
        # Use VIX level as proxy (high VIX = bearish)
        if 'vix_spot' in df.columns:
            vix_mean = df['vix_spot'].mean()
            vix_std = df['vix_spot'].std()
            df['signal'] = -(df['vix_spot'] - vix_mean) / vix_std  # High VIX = bearish
        elif 'vix' in df.columns:
            vix_mean = df['vix'].mean()
            vix_std = df['vix'].std()
            df['signal'] = -(df['vix'] - vix_mean) / vix_std  # High VIX = bearish
        elif 'slope_estimate' in df.columns:
            df['signal'] = df['slope_estimate']  # Positive slope = contango = bullish
        elif 'slope' in df.columns:
            df['signal'] = df['slope']  # Positive slope = contango = bullish
        else:
            return self._missing_result("vix_structure", "No usable VIX columns")

        if 'SPY' not in price_data:
            return self._missing_result("vix_structure", "No SPY price data")

        spy = price_data['SPY']
        aligned = df[['signal']].join(spy[['forward_5d_return']], how='inner')

        result = self.compute_metrics(
            aligned['signal'],
            aligned['forward_5d_return'],
            "vix_structure"
        )
        result.description = "VIX-based signal: high VIX = bearish, contango = bullish"
        return result

    def validate_market_breadth(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate market breadth signal."""
        history_file = self.results_dir / "live" / "historical_data" / "breadth_history_6mo.json"

        if not history_file.exists():
            return self._missing_result("market_breadth", "Breadth history file not found")

        with open(history_file) as f:
            data = json.load(f)

        records = data.get("breadth", [])
        if not records:
            return self._missing_result("market_breadth", "No breadth data")

        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.set_index('date')

        # Use advance/decline ratio or pct_advancing as signal
        if 'pct_advancing' in df.columns:
            # Normalize pct_advancing (0-1 scale) to signal (-1 to +1)
            df['signal'] = (df['pct_advancing'] - 0.5) * 2  # 0.5 = neutral
        elif 'breadth_signal' in df.columns:
            df['signal'] = df['breadth_signal']  # Already a signal
        elif 'adv_dec_ratio' in df.columns:
            df['signal'] = df['adv_dec_ratio'] - 1  # >1 = bullish, <1 = bearish
        elif 'pct_above_200ma' in df.columns:
            df['signal'] = (df['pct_above_200ma'] - 50) / 50  # Normalize around 50%
        else:
            return self._missing_result("market_breadth", "No usable breadth columns")

        if 'SPY' not in price_data:
            return self._missing_result("market_breadth", "No SPY price data")

        spy = price_data['SPY']
        aligned = df[['signal']].join(spy[['forward_5d_return']], how='inner')

        result = self.compute_metrics(
            aligned['signal'],
            aligned['forward_5d_return'],
            "market_breadth"
        )
        result.description = "Market breadth: advance/decline ratio and % above MA"
        return result

    def validate_rsi_oversold(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate RSI oversold/overbought signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 20:
                continue

            # Calculate RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # Signal: oversold (<30) = bullish, overbought (>70) = bearish
            signal = pd.Series(0, index=df.index)
            signal[rsi < 30] = 1  # Oversold = bullish
            signal[rsi > 70] = -1  # Overbought = bearish

            for date in df.index:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("rsi_oversold", f"Only {len(signals)} RSI signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "rsi_oversold"
        )
        result.description = "RSI contrarian: oversold (<30) = bullish, overbought (>70) = bearish"
        return result

    def validate_momentum_20d(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate 20-day momentum signal."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 25:
                continue

            # 20-day momentum
            momentum = df['Close'] / df['Close'].shift(20) - 1

            # Normalize to z-score
            mom_mean = momentum.rolling(60).mean()
            mom_std = momentum.rolling(60).std()
            signal = (momentum - mom_mean) / mom_std
            signal = signal.clip(-3, 3)  # Clip extremes

            for date in df.index[25:]:
                if not pd.isna(signal[date]) and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("momentum_20d", f"Only {len(signals)} momentum signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "momentum_20d"
        )
        result.description = "20-day price momentum (trend following)"
        return result

    def validate_mean_reversion(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate mean reversion signal (distance from 20-day MA)."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 25:
                continue

            # Distance from 20-day MA
            ma20 = df['Close'].rolling(20).mean()
            distance = (df['Close'] - ma20) / ma20

            # Contrarian: far below MA = bullish, far above = bearish
            signal = -distance * 10  # Scale and invert

            for date in df.index[20:]:
                if not pd.isna(signal[date]) and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("mean_reversion", f"Only {len(signals)} signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "mean_reversion"
        )
        result.description = "Mean reversion: far from 20-day MA = expect reversal"
        return result

    def validate_volume_spike(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate volume spike signal."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 25:
                continue

            # Volume relative to 20-day average
            vol_avg = df['Volume'].rolling(20).mean()
            vol_ratio = df['Volume'] / vol_avg

            # Price direction on volume spike
            daily_return = df['Close'] / df['Close'].shift(1) - 1

            # High volume + up day = bullish continuation
            # High volume + down day = bearish continuation
            signal = pd.Series(0, index=df.index)
            high_vol = vol_ratio > 2  # 2x average volume
            signal[high_vol & (daily_return > 0.01)] = 1
            signal[high_vol & (daily_return < -0.01)] = -1

            for date in df.index[20:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("volume_spike", f"Only {len(signals)} volume signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "volume_spike"
        )
        result.description = "Volume spike with direction: high volume confirms trend"
        return result

    def validate_bollinger_bands(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate Bollinger Band breakout/bounce signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 25:
                continue

            # Bollinger Bands
            ma20 = df['Close'].rolling(20).mean()
            std20 = df['Close'].rolling(20).std()
            upper = ma20 + 2 * std20
            lower = ma20 - 2 * std20

            # Position within bands (-1 to +1)
            bb_position = (df['Close'] - ma20) / (2 * std20)

            # Contrarian: touch lower band = bullish, touch upper = bearish
            signal = pd.Series(0, index=df.index)
            signal[bb_position < -0.9] = 1  # Near lower band
            signal[bb_position > 0.9] = -1  # Near upper band

            for date in df.index[20:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("bollinger_bands", f"Only {len(signals)} BB signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "bollinger_bands"
        )
        result.description = "Bollinger Band bounce: touch lower band = bullish"
        return result

    def validate_macd_crossover(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate MACD crossover signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 35:
                continue

            # MACD
            ema12 = df['Close'].ewm(span=12).mean()
            ema26 = df['Close'].ewm(span=26).mean()
            macd = ema12 - ema26
            signal_line = macd.ewm(span=9).mean()

            # Crossover signals (handle NaN properly)
            macd_above = (macd > signal_line).fillna(False)
            macd_above_prev = macd_above.shift(1).fillna(False)
            crossover_up = macd_above & ~macd_above_prev
            crossover_down = ~macd_above & macd_above_prev

            signal = pd.Series(0, index=df.index)
            signal[crossover_up] = 1
            signal[crossover_down] = -1

            for date in df.index[30:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("macd_crossover", f"Only {len(signals)} MACD signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "macd_crossover"
        )
        result.description = "MACD crossover: bullish when MACD crosses above signal"
        return result

    def validate_stochastic_oversold(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate Stochastic oscillator oversold/overbought signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 20:
                continue

            # Stochastic %K
            low14 = df['Low'].rolling(14).min()
            high14 = df['High'].rolling(14).max()
            stoch_k = 100 * (df['Close'] - low14) / (high14 - low14)
            stoch_d = stoch_k.rolling(3).mean()

            # Signal: oversold (<20) = bullish, overbought (>80) = bearish
            signal = pd.Series(0, index=df.index)
            signal[stoch_k < 20] = 1  # Oversold = bullish
            signal[stoch_k > 80] = -1  # Overbought = bearish

            for date in df.index[20:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("stochastic_oversold", f"Only {len(signals)} stochastic signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "stochastic_oversold"
        )
        result.description = "Stochastic contrarian: oversold (<20) = bullish, overbought (>80) = bearish"
        return result

    def validate_atr_breakout(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate ATR-based breakout signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 25:
                continue

            # ATR calculation
            high_low = df['High'] - df['Low']
            high_close = abs(df['High'] - df['Close'].shift(1))
            low_close = abs(df['Low'] - df['Close'].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()

            # Price change relative to ATR
            price_change = df['Close'] - df['Close'].shift(1)
            atr_multiple = price_change / atr

            # Signal: big up move (>2 ATR) = momentum, big down move = bearish continuation
            signal = pd.Series(0, index=df.index)
            signal[atr_multiple > 2] = 1
            signal[atr_multiple < -2] = -1

            for date in df.index[20:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("atr_breakout", f"Only {len(signals)} ATR signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "atr_breakout"
        )
        result.description = "ATR breakout: >2 ATR move signals continuation"
        return result

    def validate_williams_r(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate Williams %R oscillator signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 20:
                continue

            # Williams %R
            high14 = df['High'].rolling(14).max()
            low14 = df['Low'].rolling(14).min()
            williams_r = -100 * (high14 - df['Close']) / (high14 - low14)

            # Signal: oversold (<-80) = bullish, overbought (>-20) = bearish
            signal = pd.Series(0, index=df.index)
            signal[williams_r < -80] = 1  # Oversold
            signal[williams_r > -20] = -1  # Overbought

            for date in df.index[20:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("williams_r", f"Only {len(signals)} Williams %R signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "williams_r"
        )
        result.description = "Williams %R contrarian: oversold (<-80) = bullish"
        return result

    def validate_price_channel_breakout(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate Donchian channel breakout signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 25:
                continue

            # 20-day Donchian channels
            upper = df['High'].rolling(20).max()
            lower = df['Low'].rolling(20).min()

            # Signal: break above upper = bullish, break below lower = bearish
            signal = pd.Series(0, index=df.index)
            signal[df['Close'] > upper.shift(1)] = 1  # Breakout up
            signal[df['Close'] < lower.shift(1)] = -1  # Breakout down

            for date in df.index[20:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("price_channel_breakout", f"Only {len(signals)} channel signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "price_channel_breakout"
        )
        result.description = "Donchian channel breakout: 20-day high/low break"
        return result

    def validate_gap_and_go(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate gap-and-go momentum signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 10:
                continue

            # Gap calculation (open vs previous close)
            gap = (df['Open'] - df['Close'].shift(1)) / df['Close'].shift(1)

            # Gap and first hour continuation (proxy: close vs open on gap day)
            intraday_move = (df['Close'] - df['Open']) / df['Open']

            # Signal: gap up (>2%) + continues up = bullish momentum
            signal = pd.Series(0, index=df.index)
            signal[(gap > 0.02) & (intraday_move > 0)] = 1  # Gap up, continues
            signal[(gap < -0.02) & (intraday_move < 0)] = -1  # Gap down, continues

            for date in df.index[5:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("gap_and_go", f"Only {len(signals)} gap signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "gap_and_go"
        )
        result.description = "Gap-and-go: >2% gap with intraday continuation"
        return result

    def validate_ma_crossover_50_200(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate 50/200 MA golden/death cross signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 210:
                continue

            # Moving averages
            ma50 = df['Close'].rolling(50).mean()
            ma200 = df['Close'].rolling(200).mean()

            # Crossover
            ma50_above = (ma50 > ma200).fillna(False)
            ma50_above_prev = ma50_above.shift(1).fillna(False)
            golden_cross = ma50_above & ~ma50_above_prev
            death_cross = ~ma50_above & ma50_above_prev

            signal = pd.Series(0, index=df.index)
            signal[golden_cross] = 1
            signal[death_cross] = -1

            for date in df.index[200:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 5:
            return self._missing_result("ma_crossover_50_200", f"Only {len(signals)} MA crossover signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "ma_crossover_50_200"
        )
        result.description = "Golden/Death Cross: 50 MA vs 200 MA crossover"
        return result

    def validate_obv_divergence(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate On-Balance Volume divergence signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 25:
                continue

            # OBV calculation
            obv = (df['Volume'] * ((df['Close'] > df['Close'].shift(1)).astype(int) -
                                   (df['Close'] < df['Close'].shift(1)).astype(int))).cumsum()

            # 10-day changes
            price_change_10d = df['Close'].pct_change(10)
            obv_change_10d = obv.pct_change(10)

            # Divergence: price down but OBV up = bullish, price up but OBV down = bearish
            signal = pd.Series(0, index=df.index)
            signal[(price_change_10d < -0.05) & (obv_change_10d > 0.05)] = 1  # Bullish divergence
            signal[(price_change_10d > 0.05) & (obv_change_10d < -0.05)] = -1  # Bearish divergence

            for date in df.index[15:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("obv_divergence", f"Only {len(signals)} OBV divergence signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "obv_divergence"
        )
        result.description = "OBV divergence: price vs volume direction mismatch"
        return result

    def validate_accumulation_distribution(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate Accumulation/Distribution line signals."""
        signals = []
        returns = []

        for symbol, df in price_data.items():
            if len(df) < 25:
                continue

            # A/D Line calculation
            clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'])
            clv = clv.fillna(0)
            ad_line = (clv * df['Volume']).cumsum()

            # 10-day A/D trend
            ad_trend = ad_line - ad_line.shift(10)
            ad_trend_norm = ad_trend / ad_line.rolling(20).std()

            # Strong accumulation (>2 std) = bullish, distribution (<-2 std) = bearish
            signal = pd.Series(0, index=df.index)
            signal[ad_trend_norm > 2] = 1
            signal[ad_trend_norm < -2] = -1

            for date in df.index[25:]:
                if signal[date] != 0 and not pd.isna(df.loc[date, 'forward_5d_return']):
                    signals.append(signal[date])
                    returns.append(df.loc[date, 'forward_5d_return'])

        if len(signals) < 10:
            return self._missing_result("accumulation_distribution", f"Only {len(signals)} A/D signals")

        result = self.compute_metrics(
            pd.Series(signals),
            pd.Series(returns),
            "accumulation_distribution"
        )
        result.description = "A/D Line: strong accumulation = bullish, distribution = bearish"
        return result

    def validate_cot_report(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate Commitment of Traders signal."""
        cot_file = self.results_dir / "scraped_data" / "cot" / "cot_latest.json"

        if not cot_file.exists():
            # Try alternate location
            cot_files = list((self.results_dir / "scraped_data" / "cot").glob("*.json"))
            if not cot_files:
                return self._missing_result("cot_report", "No COT data files found")
            cot_file = cot_files[0]

        try:
            with open(cot_file) as f:
                data = json.load(f)
        except:
            return self._missing_result("cot_report", "Failed to read COT file")

        # COT data is typically a single snapshot, not historical
        # For now, return sparse result
        return SignalValidationResult(
            source_name="cot_report",
            description="Commitment of Traders: follow commercial hedgers",
            signal_count=1,
            bullish_signals=0,
            bearish_signals=0,
            hit_rate=0,
            avg_return_bullish=0,
            avg_return_bearish=0,
            information_coefficient=0,
            t_statistic=0,
            p_value=1,
            is_significant=False,
            sharpe_ratio=0,
            max_drawdown=0,
            win_rate=0,
            avg_win=0,
            avg_loss=0,
            profit_factor=0,
            data_quality="sparse",
            notes="COT data is weekly snapshot, need historical archive for backtest"
        )

    def validate_aaii_sentiment(self, price_data: dict[str, pd.DataFrame]) -> SignalValidationResult:
        """Validate AAII sentiment as contrarian signal."""
        aaii_file = self.results_dir / "scraped_data" / "aaii" / "aaii_latest.json"

        if not aaii_file.exists():
            return self._missing_result("aaii_sentiment", "No AAII data file")

        try:
            with open(aaii_file) as f:
                data = json.load(f)
        except:
            return self._missing_result("aaii_sentiment", "Failed to read AAII file")

        # AAII is also typically current snapshot
        return SignalValidationResult(
            source_name="aaii_sentiment",
            description="AAII contrarian: extreme bullishness = bearish signal",
            signal_count=1,
            bullish_signals=0,
            bearish_signals=0,
            hit_rate=0,
            avg_return_bullish=0,
            avg_return_bearish=0,
            information_coefficient=0,
            t_statistic=0,
            p_value=1,
            is_significant=False,
            sharpe_ratio=0,
            max_drawdown=0,
            win_rate=0,
            avg_win=0,
            avg_loss=0,
            profit_factor=0,
            data_quality="sparse",
            notes="AAII data is weekly snapshot, need historical archive for backtest"
        )

    def _missing_result(self, name: str, reason: str) -> SignalValidationResult:
        """Create result for missing data."""
        return SignalValidationResult(
            source_name=name,
            description="",
            signal_count=0,
            bullish_signals=0,
            bearish_signals=0,
            hit_rate=0,
            avg_return_bullish=0,
            avg_return_bearish=0,
            information_coefficient=0,
            t_statistic=0,
            p_value=1,
            is_significant=False,
            sharpe_ratio=0,
            max_drawdown=0,
            win_rate=0,
            avg_win=0,
            avg_loss=0,
            profit_factor=0,
            data_quality="missing",
            notes=reason
        )

    def run_validation_study(
        self,
        symbols: list[str],
        weeks: int = 12
    ) -> ValidationStudy:
        """Run full validation study across all signal sources."""
        logger.info(f"Starting validation study: {len(symbols)} symbols, {weeks} weeks")

        # Get price data
        price_data = self.get_price_data(symbols, weeks)
        logger.info(f"Loaded price data for {len(price_data)} symbols")

        results = []

        # Market regime signals
        logger.info("Validating market regime signals...")
        results.append(self.validate_put_call_ratio(price_data))
        results.append(self.validate_vix_structure(price_data))
        results.append(self.validate_market_breadth(price_data))

        # Technical signals
        logger.info("Validating technical signals...")
        results.append(self.validate_rsi_oversold(price_data))
        results.append(self.validate_momentum_20d(price_data))
        results.append(self.validate_mean_reversion(price_data))
        results.append(self.validate_volume_spike(price_data))
        results.append(self.validate_bollinger_bands(price_data))
        results.append(self.validate_macd_crossover(price_data))

        # Additional technical signals
        logger.info("Validating additional technical signals...")
        results.append(self.validate_stochastic_oversold(price_data))
        results.append(self.validate_atr_breakout(price_data))
        results.append(self.validate_williams_r(price_data))
        results.append(self.validate_price_channel_breakout(price_data))
        results.append(self.validate_gap_and_go(price_data))
        results.append(self.validate_ma_crossover_50_200(price_data))
        results.append(self.validate_obv_divergence(price_data))
        results.append(self.validate_accumulation_distribution(price_data))

        # Alternative data signals
        logger.info("Validating alternative data signals...")
        results.append(self.validate_cot_report(price_data))
        results.append(self.validate_aaii_sentiment(price_data))

        # Count results
        sources_with_data = sum(1 for r in results if r.data_quality != "missing")
        significant_sources = sum(1 for r in results if r.is_significant)

        # Sort by information coefficient
        results.sort(key=lambda r: abs(r.information_coefficient), reverse=True)

        # Summary statistics
        valid_results = [r for r in results if r.data_quality != "missing"]
        summary = {
            "best_ic": max((r.information_coefficient for r in valid_results), default=0),
            "best_hit_rate": max((r.hit_rate for r in valid_results), default=0),
            "best_sharpe": max((r.sharpe_ratio for r in valid_results), default=0),
            "avg_hit_rate": np.mean([r.hit_rate for r in valid_results]) if valid_results else 0,
            "significant_count": significant_sources,
            "top_performers": [r.source_name for r in results[:3] if r.data_quality != "missing"],
        }

        study = ValidationStudy(
            study_date=datetime.now(),
            lookback_weeks=weeks,
            symbols_tested=symbols,
            total_sources=len(results),
            sources_with_data=sources_with_data,
            significant_sources=significant_sources,
            results=results,
            summary=summary
        )

        return study


def print_results(study: ValidationStudy) -> None:
    """Print formatted results."""
    print("\n" + "=" * 80)
    print("SIGNAL VALIDATION STUDY RESULTS")
    print("=" * 80)
    print(f"\nDate: {study.study_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"Lookback: {study.lookback_weeks} weeks")
    print(f"Symbols: {', '.join(study.symbols_tested[:10])}{'...' if len(study.symbols_tested) > 10 else ''}")
    print(f"\nSources Tested: {study.total_sources}")
    print(f"Sources with Data: {study.sources_with_data}")
    print(f"Statistically Significant (p<0.05): {study.significant_sources}")

    print("\n" + "-" * 80)
    print("RESULTS BY INFORMATION COEFFICIENT")
    print("-" * 80)
    print(f"{'Source':<20} {'IC':>8} {'Hit%':>8} {'Sharpe':>8} {'p-val':>8} {'Sig?':>6} {'Quality':<10}")
    print("-" * 80)

    for r in study.results:
        sig_marker = "***" if r.is_significant else ""
        print(f"{r.source_name:<20} {r.information_coefficient:>8.3f} {r.hit_rate*100:>7.1f}% {r.sharpe_ratio:>8.2f} {r.p_value:>8.3f} {sig_marker:>6} {r.data_quality:<10}")

    print("\n" + "-" * 80)
    print("DETAILED RESULTS FOR TOP PERFORMERS")
    print("-" * 80)

    for r in study.results[:5]:
        if r.data_quality == "missing":
            continue
        print(f"\n{r.source_name.upper()}")
        print(f"  Description: {r.description}")
        print(f"  Signal Count: {r.signal_count} ({r.bullish_signals} bullish, {r.bearish_signals} bearish)")
        print(f"  Hit Rate: {r.hit_rate*100:.1f}%")
        print(f"  Avg Return (Bullish): {r.avg_return_bullish*100:.2f}%")
        print(f"  Avg Return (Bearish): {r.avg_return_bearish*100:.2f}%")
        print(f"  Information Coefficient: {r.information_coefficient:.4f}")
        print(f"  Sharpe Ratio: {r.sharpe_ratio:.2f}")
        print(f"  Win Rate: {r.win_rate*100:.1f}%")
        print(f"  Profit Factor: {r.profit_factor:.2f}")
        print(f"  Statistical Significance: p={r.p_value:.4f} {'(SIGNIFICANT)' if r.is_significant else ''}")
        if r.notes:
            print(f"  Notes: {r.notes}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Best IC: {study.summary.get('best_ic', 0):.4f}")
    print(f"Best Hit Rate: {study.summary.get('best_hit_rate', 0)*100:.1f}%")
    print(f"Best Sharpe: {study.summary.get('best_sharpe', 0):.2f}")
    print(f"Average Hit Rate: {study.summary.get('avg_hit_rate', 0)*100:.1f}%")
    print(f"Significant Sources: {study.summary.get('significant_count', 0)}")
    print(f"Top Performers: {', '.join(study.summary.get('top_performers', []))}")


def main():
    parser = argparse.ArgumentParser(description="Signal Validation Study")
    parser.add_argument("--symbols", nargs="+", default=[
        "SPY", "QQQ", "IWM", "DIA",  # Index ETFs
        "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLU", "XLB", "XLY",  # Sectors
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",  # Mega caps
        "JPM", "BAC", "GS",  # Financials
        "XOM", "CVX", "SLB",  # Energy
        "GLD", "SLV", "GDX",  # Precious metals
    ], help="Symbols to test")
    parser.add_argument("--weeks", type=int, default=12, help="Weeks of history")
    parser.add_argument("--output", type=str, help="Output JSON file")

    args = parser.parse_args()

    validator = SignalValidator()
    study = validator.run_validation_study(args.symbols, args.weeks)

    # Print results
    print_results(study)

    # Save to file
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path.home() / "quant_results" / "validation_reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"signal_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_path, "w") as f:
        json.dump(study.to_dict(), f, indent=2)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
