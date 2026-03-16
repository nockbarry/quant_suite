#!/usr/bin/env python3
"""
Research: Sentiment Momentum as Trading Signal

Hypothesis: Changes in sentiment (momentum) are more predictive than sentiment levels.

Tests:
1. Sentiment level vs forward returns
2. Sentiment momentum (5d, 10d, 20d change) vs forward returns
3. Information coefficient analysis
4. Strategy performance comparison
"""

import sys
from pathlib import Path
import logging
from datetime import datetime, timedelta
import json
import uuid

import pandas as pd
import numpy as np
from scipy.stats import spearmanr, pearsonr
import yfinance as yf

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows.research.session_tracker import ResearchSessionTracker
from src.monitoring import log_agent_start, log_agent_complete

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def calculate_sentiment_proxy(df: pd.DataFrame) -> pd.Series:
    """
    Calculate sentiment proxy from price/volume data.

    Using RSI and volume trends as a proxy for market sentiment.
    In production, would use actual sentiment data sources.
    """
    # Calculate RSI as sentiment proxy (0-100 -> -1 to 1)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # Normalize RSI to -1 to 1 range (sentiment scale)
    sentiment = (rsi - 50) / 50

    # Add volume trend component
    volume_ma = df['Volume'].rolling(20).mean()
    volume_ratio = df['Volume'] / volume_ma
    volume_sentiment = (volume_ratio - 1).clip(-1, 1)

    # Combine (70% RSI, 30% volume)
    combined_sentiment = 0.7 * sentiment + 0.3 * volume_sentiment

    return combined_sentiment.fillna(0)


def calculate_momentum(series: pd.Series, periods: int) -> pd.Series:
    """Calculate momentum (change) over N periods."""
    return series - series.shift(periods)


def calculate_ic(signal: pd.Series, forward_returns: pd.Series) -> dict:
    """
    Calculate Information Coefficient (IC).

    IC measures correlation between signal and future returns.
    Good signals have |IC| > 0.02-0.05
    """
    # Remove NaN values
    valid_mask = signal.notna() & forward_returns.notna()
    signal_clean = signal[valid_mask]
    returns_clean = forward_returns[valid_mask]

    if len(signal_clean) < 30:
        return {"pearson_ic": 0.0, "spearman_ic": 0.0, "n_obs": len(signal_clean)}

    # Calculate both Pearson and Spearman correlation
    pearson_ic, pearson_p = pearsonr(signal_clean, returns_clean)
    spearman_ic, spearman_p = spearmanr(signal_clean, returns_clean)

    return {
        "pearson_ic": pearson_ic,
        "pearson_pvalue": pearson_p,
        "spearman_ic": spearman_ic,
        "spearman_pvalue": spearman_p,
        "n_obs": len(signal_clean)
    }


def calculate_hit_rate(signal: pd.Series, forward_returns: pd.Series) -> dict:
    """
    Calculate hit rate: % of time signal direction matches return direction.

    Good signals have hit rate > 55%
    """
    valid_mask = signal.notna() & forward_returns.notna()
    signal_clean = signal[valid_mask]
    returns_clean = forward_returns[valid_mask]

    if len(signal_clean) < 30:
        return {"hit_rate": 0.5, "n_obs": len(signal_clean)}

    # Check if signal and return have same sign
    same_sign = (signal_clean * returns_clean) > 0
    hit_rate = same_sign.sum() / len(same_sign)

    # Calculate hit rate for strong signals (top/bottom quartile)
    q75 = signal_clean.quantile(0.75)
    q25 = signal_clean.quantile(0.25)

    strong_bullish = signal_clean > q75
    strong_bearish = signal_clean < q25

    strong_bullish_hit = 0.5
    strong_bearish_hit = 0.5

    if strong_bullish.sum() > 0:
        strong_bullish_hit = (returns_clean[strong_bullish] > 0).sum() / strong_bullish.sum()

    if strong_bearish.sum() > 0:
        strong_bearish_hit = (returns_clean[strong_bearish] < 0).sum() / strong_bearish.sum()

    return {
        "hit_rate": hit_rate,
        "strong_bullish_hit_rate": strong_bullish_hit,
        "strong_bearish_hit_rate": strong_bearish_hit,
        "n_obs": len(signal_clean)
    }


def backtest_signal(df: pd.DataFrame, signal_col: str, forward_return_col: str) -> dict:
    """
    Simple backtest: long when signal > 0, short when signal < 0.
    """
    # Create positions based on signal
    positions = df[signal_col].apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)

    # Calculate strategy returns
    strategy_returns = positions.shift(1) * df[forward_return_col]
    strategy_returns = strategy_returns.dropna()

    if len(strategy_returns) < 30:
        return {"sharpe": 0.0, "mean_return": 0.0, "n_trades": 0}

    # Calculate metrics
    mean_return = strategy_returns.mean()
    std_return = strategy_returns.std()
    sharpe = (mean_return / std_return * np.sqrt(252)) if std_return > 0 else 0

    # Trade count
    n_trades = (positions.diff() != 0).sum()

    # Win rate
    win_rate = (strategy_returns > 0).sum() / len(strategy_returns)

    return {
        "sharpe": sharpe,
        "mean_return": mean_return * 100,  # Convert to %
        "std_return": std_return * 100,
        "win_rate": win_rate,
        "n_trades": n_trades,
        "n_obs": len(strategy_returns)
    }


def main():
    logger.info("=" * 60)
    logger.info("Sentiment Momentum Research")
    logger.info("=" * 60)

    # Start agent tracking
    agent_id = log_agent_start("research", "Sentiment momentum research")

    tracker = ResearchSessionTracker()

    # Test symbols
    symbols = ["SPY", "QQQ", "AAPL", "TSLA", "MSFT"]

    all_results = {}

    try:
        for symbol in symbols:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Testing {symbol}")
            logger.info(f"{'=' * 60}")

            # Fetch data using yfinance (2 years)
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="2y")

                if df is None or len(df) < 100:
                    logger.warning(f"Insufficient data for {symbol}")
                    continue

                # Calculate sentiment proxy
                df['sentiment'] = calculate_sentiment_proxy(df)

                # Calculate sentiment momentum (changes)
                df['sentiment_mom_5d'] = calculate_momentum(df['sentiment'], 5)
                df['sentiment_mom_10d'] = calculate_momentum(df['sentiment'], 10)
                df['sentiment_mom_20d'] = calculate_momentum(df['sentiment'], 20)

                # Calculate forward returns (5-day)
                df['forward_return_5d'] = df['Close'].pct_change(5).shift(-5)

                # Calculate forward returns (10-day)
                df['forward_return_10d'] = df['Close'].pct_change(10).shift(-10)

                results = {}

                # Test 1: Sentiment level vs forward returns
                logger.info("\n--- Sentiment Level ---")
                ic_level_5d = calculate_ic(df['sentiment'], df['forward_return_5d'])
                ic_level_10d = calculate_ic(df['sentiment'], df['forward_return_10d'])
                hit_level = calculate_hit_rate(df['sentiment'], df['forward_return_5d'])
                backtest_level = backtest_signal(df, 'sentiment', 'forward_return_5d')

                logger.info(f"IC (5d forward): Pearson={ic_level_5d['pearson_ic']:.4f}, Spearman={ic_level_5d['spearman_ic']:.4f}")
                logger.info(f"IC (10d forward): Pearson={ic_level_10d['pearson_ic']:.4f}, Spearman={ic_level_10d['spearman_ic']:.4f}")
                logger.info(f"Hit Rate: {hit_level['hit_rate']:.2%}")
                logger.info(f"Backtest Sharpe: {backtest_level['sharpe']:.2f}")

                results['sentiment_level'] = {
                    'ic_5d': ic_level_5d,
                    'ic_10d': ic_level_10d,
                    'hit_rate': hit_level,
                    'backtest': backtest_level
                }

                # Test 2: Sentiment momentum vs forward returns
                for period in [5, 10, 20]:
                    mom_col = f'sentiment_mom_{period}d'
                    logger.info(f"\n--- Sentiment Momentum ({period}d) ---")

                    ic_mom_5d = calculate_ic(df[mom_col], df['forward_return_5d'])
                    ic_mom_10d = calculate_ic(df[mom_col], df['forward_return_10d'])
                    hit_mom = calculate_hit_rate(df[mom_col], df['forward_return_5d'])
                    backtest_mom = backtest_signal(df, mom_col, 'forward_return_5d')

                    logger.info(f"IC (5d forward): Pearson={ic_mom_5d['pearson_ic']:.4f}, Spearman={ic_mom_5d['spearman_ic']:.4f}")
                    logger.info(f"IC (10d forward): Pearson={ic_mom_10d['pearson_ic']:.4f}, Spearman={ic_mom_10d['spearman_ic']:.4f}")
                    logger.info(f"Hit Rate: {hit_mom['hit_rate']:.2%}")
                    logger.info(f"Backtest Sharpe: {backtest_mom['sharpe']:.2f}")

                    results[f'sentiment_mom_{period}d'] = {
                        'ic_5d': ic_mom_5d,
                        'ic_10d': ic_mom_10d,
                        'hit_rate': hit_mom,
                        'backtest': backtest_mom
                    }

                all_results[symbol] = results

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                continue

        # Aggregate results
        logger.info("\n" + "=" * 60)
        logger.info("AGGREGATED RESULTS")
        logger.info("=" * 60)

        # Average IC across symbols
        metrics = ['sentiment_level', 'sentiment_mom_5d', 'sentiment_mom_10d', 'sentiment_mom_20d']

        summary = {}
        for metric in metrics:
            ics_5d = []
            ics_10d = []
            hit_rates = []
            sharpes = []

            for symbol, results in all_results.items():
                if metric in results:
                    ics_5d.append(abs(results[metric]['ic_5d']['spearman_ic']))
                    ics_10d.append(abs(results[metric]['ic_10d']['spearman_ic']))
                    hit_rates.append(results[metric]['hit_rate']['hit_rate'])
                    sharpes.append(results[metric]['backtest']['sharpe'])

            if ics_5d:
                summary[metric] = {
                    'avg_abs_ic_5d': np.mean(ics_5d),
                    'avg_abs_ic_10d': np.mean(ics_10d),
                    'avg_hit_rate': np.mean(hit_rates),
                    'avg_sharpe': np.mean(sharpes),
                    'n_symbols': len(ics_5d)
                }

        logger.info("\nSignal Comparison:")
        logger.info(f"{'Signal':<25} {'Avg |IC| 5d':<15} {'Avg Hit Rate':<15} {'Avg Sharpe':<12}")
        logger.info("-" * 70)

        for metric, stats in summary.items():
            logger.info(
                f"{metric:<25} "
                f"{stats['avg_abs_ic_5d']:>14.4f} "
                f"{stats['avg_hit_rate']:>14.2%} "
                f"{stats['avg_sharpe']:>11.2f}"
            )

        # Determine winner
        best_signal = max(summary.items(), key=lambda x: x[1]['avg_abs_ic_5d'])

        logger.info("\n" + "=" * 60)
        logger.info("FINDINGS")
        logger.info("=" * 60)

        # Compare momentum vs level
        level_ic = summary['sentiment_level']['avg_abs_ic_5d']
        best_mom = max(
            [(k, v['avg_abs_ic_5d']) for k, v in summary.items() if 'mom' in k],
            key=lambda x: x[1]
        )
        best_mom_signal, best_mom_ic = best_mom

        improvement = (best_mom_ic - level_ic) / level_ic * 100 if level_ic > 0 else 0

        logger.info(f"\nBest Signal: {best_signal[0]}")
        logger.info(f"  IC: {best_signal[1]['avg_abs_ic_5d']:.4f}")
        logger.info(f"  Hit Rate: {best_signal[1]['avg_hit_rate']:.2%}")
        logger.info(f"  Sharpe: {best_signal[1]['avg_sharpe']:.2f}")

        logger.info(f"\nSentiment Level IC: {level_ic:.4f}")
        logger.info(f"Best Momentum IC: {best_mom_ic:.4f} ({best_mom_signal})")
        logger.info(f"Improvement: {improvement:.1f}%")

        # Recommendation
        if best_mom_ic > level_ic * 1.1:  # At least 10% improvement
            recommendation = "YES - Add sentiment momentum to composite"
            confidence = 0.7
        elif best_mom_ic > level_ic:
            recommendation = "MAYBE - Marginal improvement, test further"
            confidence = 0.5
        else:
            recommendation = "NO - Level signal is better than momentum"
            confidence = 0.6

        logger.info(f"\nRecommendation: {recommendation}")

        # Log to session tracker
        insight_id = str(uuid.uuid4())[:8]
        tracker.log_insight(
            id=insight_id,
            title="Sentiment Momentum vs Level",
            description=(
                f"Tested sentiment momentum (change) vs sentiment level as predictive signals. "
                f"Best momentum signal ({best_mom_signal}) achieved IC of {best_mom_ic:.4f} "
                f"vs level IC of {level_ic:.4f} ({improvement:+.1f}% change). "
                f"Recommendation: {recommendation}"
            ),
            category="feature",
            tags=["sentiment", "momentum", "signal-quality", "alternative-data"],
            evidence={
                "sentiment_level_ic": level_ic,
                "best_momentum_signal": best_mom_signal,
                "best_momentum_ic": best_mom_ic,
                "improvement_pct": improvement,
                "avg_hit_rate": best_signal[1]['avg_hit_rate'],
                "avg_sharpe": best_signal[1]['avg_sharpe'],
                "n_symbols_tested": len(all_results),
                "summary": summary
            },
            source_session=agent_id,
            confidence=confidence,
            actionable=True
        )

        # Log experiment
        for symbol in all_results.keys():
            exp_id = str(uuid.uuid4())[:8]
            tracker.log_experiment(
                id=exp_id,
                strategy="sentiment_momentum",
                symbol=symbol,
                params={
                    "momentum_periods": [5, 10, 20],
                    "forward_horizon": 5
                },
                result="success" if best_mom_ic > level_ic else "inconclusive",
                sharpe=all_results[symbol].get('sentiment_mom_10d', {}).get('backtest', {}).get('sharpe'),
                p_value=None,
                notes=f"Sentiment momentum IC: {best_mom_ic:.4f}, Level IC: {level_ic:.4f}",
                session_id=agent_id
            )

        logger.info(f"\nResults logged to session tracker: {tracker.storage_dir}")

        # Save detailed results
        output_file = Path("/home/nock/quant_results/comprehensive_research") / f"sentiment_momentum_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "hypothesis": "Sentiment momentum is more predictive than sentiment level",
                "conclusion": recommendation,
                "confidence": confidence,
                "summary": summary,
                "detailed_results": all_results
            }, f, indent=2, default=str)

        logger.info(f"Detailed results saved to: {output_file}")

        # Complete agent tracking
        log_agent_complete(
            agent_id,
            summary=(
                f"Sentiment momentum research complete. "
                f"Best signal: {best_signal[0]} (IC={best_signal[1]['avg_abs_ic_5d']:.4f}). "
                f"Recommendation: {recommendation}"
            ),
            success=True
        )

    except Exception as e:
        logger.error(f"Research failed: {e}", exc_info=True)
        log_agent_complete(agent_id, summary=f"Failed: {e}", success=False)
        raise


if __name__ == "__main__":
    main()
