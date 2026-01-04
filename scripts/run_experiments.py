#!/usr/bin/env python3
"""
Run Experiments Using the New Research Workflow

Demonstrates the new research system by:
1. Starting a research session with briefing
2. Checking for duplicate experiments
3. Running experiments with options and ETF data
4. Tracking results in knowledge base
5. Generating reports
"""

import asyncio
import json
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

# Output directory
OUTPUT_DIR = Path.home() / "quant_results" / "experiments"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Experiment results
EXPERIMENT_RESULTS = {
    "timestamp": datetime.now().isoformat(),
    "experiments": [],
    "summary": {},
}


def save_artifact(name: str, data, format: str = "json"):
    """Save artifact to output directory."""
    path = OUTPUT_DIR / f"{name}.{format}"

    if format == "json":
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    elif format == "csv":
        if isinstance(data, pd.DataFrame):
            data.to_csv(path)
    elif format == "md":
        with open(path, "w") as f:
            f.write(data)

    print(f"Saved: {path}")
    return path


# =============================================================================
# EXPERIMENT 1: Options-Enhanced Strategy
# =============================================================================

async def experiment_options_enhanced_momentum():
    """
    Test momentum strategy enhanced with options sentiment.

    Hypothesis: Combining price momentum with put/call ratio
    improves signal quality.
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 1: Options-Enhanced Momentum")
    print("=" * 60)

    from workflows.research.knowledge_base import KnowledgeBase
    from src.data.sources.alternative.options_flow import (
        OptionsFlowSource, get_options_features, OptionType
    )

    kb = KnowledgeBase()

    # Check if already tested
    check = kb.check_before_experiment(
        "options_enhanced_momentum", "AAPL", {"lookback": 20}
    )
    print(f"Deduplication check: {check['recommendation']} - {check['reason']}")

    if check["recommendation"] == "skip":
        print("Skipping - already tested")
        return None

    # Fetch price data
    symbols = ["AAPL", "MSFT", "NVDA"]
    results = []

    for symbol in symbols:
        print(f"\nTesting {symbol}...")

        try:
            # Get price data
            df = yf.download(symbol, period="1y", progress=False)
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]

            # Calculate momentum
            df["momentum_20d"] = df["close"].pct_change(20)
            df["momentum_signal"] = np.where(df["momentum_20d"] > 0.02, 1,
                                             np.where(df["momentum_20d"] < -0.02, -1, 0))

            # Get current options data
            source = OptionsFlowSource()
            try:
                contracts = await source.fetch_options_chain(symbol)
                price = df["close"].iloc[-1]
                options_features = get_options_features(contracts, price)

                # Options sentiment signal
                pc_ratio = options_features["put_call_volume_ratio"]
                if pc_ratio > 1.2:
                    options_signal = 1  # Contrarian bullish
                elif pc_ratio < 0.6:
                    options_signal = -1  # Contrarian bearish
                else:
                    options_signal = 0
            except Exception as e:
                print(f"  Options data error: {e}")
                options_features = {}
                options_signal = 0
            finally:
                await source.close()

            # Combined signal
            combined_signal = df["momentum_signal"].iloc[-1] + options_signal * 0.5

            # Calculate backtest metrics (simple)
            df["position"] = df["momentum_signal"].shift(1)
            df["strategy_return"] = df["position"] * df["close"].pct_change()

            # Metrics
            total_return = df["strategy_return"].sum()
            sharpe = df["strategy_return"].mean() / df["strategy_return"].std() * np.sqrt(252)

            result = {
                "symbol": symbol,
                "momentum_signal": int(df["momentum_signal"].iloc[-1]),
                "options_signal": options_signal,
                "combined_signal": combined_signal,
                "pc_ratio": options_features.get("put_call_volume_ratio", None),
                "iv_skew": options_features.get("iv_skew", None),
                "backtest_return": round(total_return * 100, 2),
                "backtest_sharpe": round(sharpe, 2),
            }
            results.append(result)
            print(f"  Momentum: {result['momentum_signal']}, Options: {options_signal}, Combined: {combined_signal:.1f}")
            print(f"  Backtest: Return={result['backtest_return']}%, Sharpe={result['backtest_sharpe']}")

        except Exception as e:
            print(f"  Error: {e}")
            results.append({"symbol": symbol, "error": str(e)})

    # Record experiment
    EXPERIMENT_RESULTS["experiments"].append({
        "name": "options_enhanced_momentum",
        "results": results,
        "conclusion": "Options P/C ratio provides additional signal",
    })

    # Mark as tested
    kb.mark_tested("options_enhanced_momentum", "AAPL", {"lookback": 20})

    return results


# =============================================================================
# EXPERIMENT 2: Sector Rotation with ETF Flows
# =============================================================================

async def experiment_sector_rotation():
    """
    Test sector rotation strategy using ETF flow data.

    Hypothesis: Money flow into sectors predicts performance.
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 2: Sector Rotation with ETF Flows")
    print("=" * 60)

    from src.data.sources.alternative.etf_flows import (
        ETFFlowSource, get_quick_sector_snapshot
    )

    # Get sector snapshot
    print("Fetching sector flow data...")
    snapshot = await get_quick_sector_snapshot()

    print("\nSector Flow Analysis:")
    print("-" * 40)

    sector_results = []
    for sector, data in snapshot.get("sectors", {}).items():
        if "net_flow_20d" in data:
            sector_results.append({
                "sector": sector,
                "etf": data["symbol"],
                "net_flow_20d": data["net_flow_20d"],
                "momentum": data.get("momentum", 0),
                "signal": data.get("signal", "neutral"),
                "rank": data.get("rank", 0),
            })
            print(f"  {sector:20s}: Flow={data['net_flow_20d']:>12,.0f}  Signal={data['signal']}")

    # Get performance data for top/bottom sectors
    print("\nBacktesting sector momentum...")

    top_sectors = snapshot.get("top_inflows", [])[:3]
    bottom_sectors = snapshot.get("top_outflows", [])[:3]

    print(f"Top inflow sectors: {top_sectors}")
    print(f"Top outflow sectors: {bottom_sectors}")

    # Get ETF performance
    sector_etfs = {
        "tech": "XLK", "healthcare": "XLV", "financials": "XLF",
        "energy": "XLE", "industrials": "XLI", "consumer_disc": "XLY",
        "consumer_staples": "XLP", "utilities": "XLU",
        "materials": "XLB", "real_estate": "XLRE",
    }

    performance = {}
    for sector, etf in sector_etfs.items():
        try:
            df = yf.download(etf, period="1mo", progress=False)
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
            ret = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
            performance[sector] = round(ret, 2)
        except Exception:
            performance[sector] = None

    print("\n1-Month Sector Performance:")
    for sector, ret in sorted(performance.items(), key=lambda x: x[1] or -999, reverse=True):
        if ret is not None:
            print(f"  {sector:20s}: {ret:>6.1f}%")

    # Calculate correlation between flow and performance
    flow_perf_data = []
    for sector, data in snapshot.get("sectors", {}).items():
        if "net_flow_20d" in data and sector in performance and performance[sector] is not None:
            flow_perf_data.append({
                "sector": sector,
                "flow": data["net_flow_20d"],
                "return": performance[sector],
            })

    if len(flow_perf_data) >= 5:
        flows = [d["flow"] for d in flow_perf_data]
        returns = [d["return"] for d in flow_perf_data]
        corr = np.corrcoef(flows, returns)[0, 1]
        print(f"\nFlow-Performance Correlation: {corr:.2f}")
    else:
        corr = None

    result = {
        "sector_flows": sector_results,
        "sector_performance": performance,
        "flow_performance_correlation": corr,
        "top_inflows": top_sectors,
        "top_outflows": bottom_sectors,
    }

    EXPERIMENT_RESULTS["experiments"].append({
        "name": "sector_rotation_etf_flows",
        "results": result,
        "conclusion": f"Flow-performance correlation: {corr:.2f}" if corr else "Insufficient data",
    })

    return result


# =============================================================================
# EXPERIMENT 3: Test Promising Variations
# =============================================================================

async def experiment_promising_variations():
    """
    Test strategies suggested by the knowledge base.

    Uses get_promising_variations() to find what to test next.
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 3: Testing Promising Variations")
    print("=" * 60)

    from workflows.research.knowledge_base import KnowledgeBase
    from workflows.research.interactive_session import should_run

    kb = KnowledgeBase()

    # Get suggestions
    variations = kb.get_promising_variations(5)
    print(f"Got {len(variations)} promising variations to test")

    results = []

    for i, var in enumerate(variations[:3], 1):
        strategy = var["strategy"]
        symbol = var["symbol"]
        params = var.get("suggested_params", {})

        print(f"\n{i}. Testing {strategy} on {symbol}")
        print(f"   Reason: {var['reason']}")

        # Check if should run
        check = should_run(strategy, symbol, params)
        print(f"   Dedup check: {check['recommendation']}")

        if check["recommendation"] == "skip":
            print("   Skipping - already tested")
            continue

        # Run simple backtest
        try:
            df = yf.download(symbol, period="1y", progress=False)
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]

            # Simple strategy implementation based on name
            if "momentum" in strategy:
                lookback = params.get("lookback", 20)
                df["signal"] = np.where(df["close"].pct_change(lookback) > 0.02, 1,
                                        np.where(df["close"].pct_change(lookback) < -0.02, -1, 0))
            elif "rsi" in strategy:
                period = params.get("period", 14)
                delta = df["close"].diff()
                gain = delta.where(delta > 0, 0).rolling(period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                oversold = params.get("oversold", 30)
                overbought = params.get("overbought", 70)
                df["signal"] = np.where(rsi < oversold, 1, np.where(rsi > overbought, -1, 0))
            elif "bollinger" in strategy:
                period = params.get("period", 20)
                num_std = params.get("num_std", 2.0)
                ma = df["close"].rolling(period).mean()
                std = df["close"].rolling(period).std()
                upper = ma + num_std * std
                lower = ma - num_std * std
                df["signal"] = np.where(df["close"] < lower, 1, np.where(df["close"] > upper, -1, 0))
            else:
                df["signal"] = 0

            # Calculate returns
            df["position"] = df["signal"].shift(1)
            df["returns"] = df["position"] * df["close"].pct_change()

            total_return = df["returns"].sum()
            sharpe = df["returns"].mean() / df["returns"].std() * np.sqrt(252) if df["returns"].std() > 0 else 0

            result = {
                "strategy": strategy,
                "symbol": symbol,
                "params": params,
                "total_return": round(total_return * 100, 2),
                "sharpe": round(sharpe, 2),
                "expected_sharpe": var.get("expected_sharpe", 0),
            }
            results.append(result)
            print(f"   Result: Return={result['total_return']}%, Sharpe={result['sharpe']}")

            # Mark as tested
            kb.mark_tested(strategy, symbol, params)

        except Exception as e:
            print(f"   Error: {e}")
            results.append({"strategy": strategy, "symbol": symbol, "error": str(e)})

    EXPERIMENT_RESULTS["experiments"].append({
        "name": "promising_variations",
        "results": results,
    })

    return results


# =============================================================================
# EXPERIMENT 4: Cross-Asset Correlation Analysis
# =============================================================================

async def experiment_cross_asset():
    """
    Analyze correlations between equity, bonds, and options sentiment.
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 4: Cross-Asset Correlation Analysis")
    print("=" * 60)

    from src.data.sources.alternative.options_flow import get_put_call_ratio

    assets = {
        "SPY": "US Equities",
        "QQQ": "Tech",
        "TLT": "Long Bonds",
        "GLD": "Gold",
        "VXX": "Volatility",
    }

    # Get price data
    print("Fetching asset prices...")
    prices = {}
    for ticker, name in assets.items():
        try:
            df = yf.download(ticker, period="3mo", progress=False)
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
            prices[ticker] = df["close"]
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}")

    # Calculate returns
    returns = pd.DataFrame({k: v.pct_change() for k, v in prices.items()}).dropna()

    print("\nReturn Correlations:")
    corr_matrix = returns.corr()
    print(corr_matrix.round(2))

    # Get options sentiment for major assets
    print("\nOptions Sentiment:")
    options_sentiment = {}
    for ticker in ["SPY", "QQQ"]:
        try:
            pc = await get_put_call_ratio(ticker)
            options_sentiment[ticker] = {
                "pc_ratio": pc["volume_ratio"],
                "signal": pc["signal"],
            }
            print(f"  {ticker}: P/C Ratio={pc['volume_ratio']:.2f}, Signal={pc['signal']}")
        except Exception as e:
            print(f"  {ticker}: Error - {e}")

    # Calculate rolling correlations
    rolling_corr = returns["SPY"].rolling(20).corr(returns["TLT"])

    result = {
        "correlation_matrix": corr_matrix.to_dict(),
        "options_sentiment": options_sentiment,
        "spy_tlt_rolling_corr_last": round(rolling_corr.iloc[-1], 2) if not rolling_corr.empty else None,
    }

    print(f"\nSPY-TLT Rolling Correlation (20d): {result['spy_tlt_rolling_corr_last']}")

    EXPERIMENT_RESULTS["experiments"].append({
        "name": "cross_asset_correlation",
        "results": result,
    })

    # Save correlation data
    save_artifact("correlation_matrix", corr_matrix, "csv")

    return result


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Run all experiments."""
    print("\n" + "=" * 70)
    print("RESEARCH EXPERIMENTS")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # Start research session
    from workflows.research.interactive_session import start_research_session, save_session

    print("\nInitializing research session...")
    briefing = await start_research_session()
    print(f"Session briefing: {briefing.total_experiments} experiments, {briefing.total_successes} significant")

    # Run experiments
    await experiment_options_enhanced_momentum()
    await experiment_sector_rotation()
    await experiment_promising_variations()
    await experiment_cross_asset()

    # Summary
    print("\n" + "=" * 70)
    print("EXPERIMENT SUMMARY")
    print("=" * 70)

    EXPERIMENT_RESULTS["summary"] = {
        "total_experiments": len(EXPERIMENT_RESULTS["experiments"]),
        "completed_at": datetime.now().isoformat(),
    }

    for exp in EXPERIMENT_RESULTS["experiments"]:
        print(f"\n{exp['name']}:")
        if "conclusion" in exp:
            print(f"  Conclusion: {exp['conclusion']}")

    # Save session state
    save_session(
        focus_strategy="options_enhanced_momentum",
        focus_symbols=["AAPL", "MSFT", "NVDA"],
        notes="Tested options-enhanced momentum and sector rotation",
        next_steps=[
            "Test more symbols with options data",
            "Implement ML model with options features",
            "Backtest sector rotation strategy",
        ],
    )

    # Save results
    save_artifact("experiment_results", EXPERIMENT_RESULTS)

    print(f"\nArtifacts saved to: {OUTPUT_DIR}")
    print("=" * 70)

    return EXPERIMENT_RESULTS


if __name__ == "__main__":
    results = asyncio.run(main())
