#!/usr/bin/env python3
"""
Full Research Cycle - Comprehensive strategy testing across all components.

This script runs a complete research cycle testing:
- All 11 strategy templates
- All 45 symbols across 8 sectors
- All 36 features (technical, sentiment, alternative, flow, risk, regime, embedding)
- PDT holding period optimization
- Alternative data integration (Google Trends, Short Interest)

Usage:
    PYTHONPATH=. python scripts/full_research_cycle.py [--quick] [--sectors SECTORS]

Options:
    --quick         Run reduced test (10 symbols, 3 strategies)
    --sectors       Comma-separated sector filter (e.g., "technology,etf")
    --strategies    Comma-separated strategy filter
    --output-dir    Custom output directory
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


def run_full_research_cycle(
    quick_mode: bool = False,
    sectors: list[str] | None = None,
    strategies: list[str] | None = None,
    output_dir: str = "/home/nock/quant_results/full_research",
) -> dict[str, Any]:
    """
    Run comprehensive research cycle.

    Args:
        quick_mode: If True, run reduced set for faster testing
        sectors: Filter to specific sectors
        strategies: Filter to specific strategies
        output_dir: Output directory for results

    Returns:
        Complete research report
    """
    from workflows.research.comprehensive_researcher import ComprehensiveResearcher
    from workflows.research.session_tracker import get_tracker
    from workflows.research.research_protocol import ResearchProtocol, ResearchFocus
    from src.data.feature_engineering.feature_discovery import FeatureDiscoveryEngine
    from src.evaluation.validation.pdt_framework import (
        PDTAwareBacktest, AccountType, HoldingPeriodOptimizer
    )

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "cycle_id": f"full_cycle_{timestamp}",
        "started_at": datetime.now().isoformat(),
        "mode": "quick" if quick_mode else "full",
        "phases": {},
    }

    tracker = get_tracker()
    protocol = ResearchProtocol()

    # ===== PHASE 1: Session Setup =====
    logger.info("=" * 60)
    logger.info("PHASE 1: Starting Research Session")
    logger.info("=" * 60)

    session = protocol.start_session(focus=ResearchFocus.STRATEGY_DEVELOPMENT)
    report["session_id"] = session.session_id
    report["phases"]["session_setup"] = {
        "session_id": session.session_id,
        "focus": session.focus.value,
    }

    # ===== PHASE 2: Feature Discovery =====
    logger.info("=" * 60)
    logger.info("PHASE 2: Feature Discovery & Gap Analysis")
    logger.info("=" * 60)

    try:
        engine = FeatureDiscoveryEngine()
        discovery_report = engine.generate_discovery_report()

        report["phases"]["feature_discovery"] = {
            "total_ideas": discovery_report.get("total_ideas", 0),
            "by_domain": discovery_report.get("by_domain", {}),
            "top_features": discovery_report.get("top_features", [])[:10],
        }

        # Log discovery insight
        tracker.log_insight(
            title=f"Feature discovery: {discovery_report.get('total_ideas', 0)} ideas",
            description=f"Discovered features across {len(discovery_report.get('by_domain', {}))} domains",
            category="feature",
            evidence=discovery_report,
            session_id=session.session_id,
            tags=["feature_discovery", "gap_analysis"],
        )

        logger.info(f"Discovered {discovery_report.get('total_ideas', 0)} feature ideas")
    except Exception as e:
        logger.warning(f"Feature discovery failed: {e}")
        report["phases"]["feature_discovery"] = {"error": str(e)}

    # ===== PHASE 3: Alternative Data =====
    logger.info("=" * 60)
    logger.info("PHASE 3: Alternative Data Collection")
    logger.info("=" * 60)

    alt_data_results = {"google_trends": {}, "short_interest": {}}

    # Google Trends for top symbols
    try:
        from src.data.sources.alternative import GoogleTrendsSource
        trends = GoogleTrendsSource()

        trend_symbols = ["NVDA", "TSLA", "AMD", "AAPL", "MSFT"] if quick_mode else [
            "NVDA", "TSLA", "AMD", "AAPL", "MSFT", "META", "GOOGL", "AMZN"
        ]

        for symbol in trend_symbols:
            try:
                attention = trends.get_retail_attention(symbol)
                if attention:
                    alt_data_results["google_trends"][symbol] = {
                        "zscore": attention.zscore,
                        "signal": attention.signal,
                        "momentum": attention.momentum,
                        "contrarian_buy": attention.is_contrarian_buy(),
                    }
            except Exception as e:
                logger.debug(f"Trends failed for {symbol}: {e}")

        logger.info(f"Collected trends data for {len(alt_data_results['google_trends'])} symbols")
    except Exception as e:
        logger.warning(f"Google Trends collection failed: {e}")

    # Short Interest for meme/high-short stocks
    try:
        from src.data.sources.alternative import ShortInterestSource
        shorts = ShortInterestSource()

        short_symbols = ["GME", "AMC", "MARA", "RIVN"] if quick_mode else [
            "GME", "AMC", "MARA", "RIVN", "BBBY", "MULN", "CLOV"
        ]

        for symbol in short_symbols:
            try:
                data = shorts.fetch_short_interest(symbol)
                if data:
                    alt_data_results["short_interest"][symbol] = {
                        "short_pct": data.short_percent_of_float,
                        "days_to_cover": data.short_ratio,
                        "squeeze_candidate": data.is_squeeze_candidate(),
                    }
            except Exception as e:
                logger.debug(f"Short interest failed for {symbol}: {e}")

        # Find squeeze candidates
        squeeze_candidates = [
            s for s, d in alt_data_results["short_interest"].items()
            if d.get("squeeze_candidate")
        ]
        alt_data_results["squeeze_candidates"] = squeeze_candidates

        logger.info(f"Collected short interest for {len(alt_data_results['short_interest'])} symbols")
        if squeeze_candidates:
            logger.info(f"Squeeze candidates: {squeeze_candidates}")
    except Exception as e:
        logger.warning(f"Short interest collection failed: {e}")

    report["phases"]["alternative_data"] = alt_data_results

    # Log alternative data insight
    if alt_data_results["google_trends"] or alt_data_results["short_interest"]:
        tracker.log_insight(
            title="Alternative data collected",
            description=f"Trends: {len(alt_data_results['google_trends'])} symbols, Short interest: {len(alt_data_results['short_interest'])} symbols",
            category="market",
            evidence=alt_data_results,
            session_id=session.session_id,
            tags=["alternative_data", "trends", "short_interest"],
        )

    # ===== PHASE 4: Comprehensive Strategy Research =====
    logger.info("=" * 60)
    logger.info("PHASE 4: Comprehensive Strategy Research")
    logger.info("=" * 60)

    researcher = ComprehensiveResearcher()

    # Determine universes to test
    if quick_mode:
        universes_to_test = ["tech_mega", "semiconductors"]
    elif sectors:
        universes_to_test = sectors
    else:
        universes_to_test = [
            "tech_mega", "semiconductors", "saas", "financials",
            "healthcare", "energy", "consumer", "market_etfs"
        ]

    # Determine strategies to test
    all_strategies = [
        "bollinger_reversal", "rsi_reversal", "momentum", "breakout",
        "sma_crossover", "insider_momentum", "sentiment_reversal",
        "regime_adaptive"
    ]

    if quick_mode:
        strategies_to_test = ["bollinger_reversal", "momentum", "rsi_reversal"]
    elif strategies:
        strategies_to_test = strategies
    else:
        strategies_to_test = all_strategies

    logger.info(f"Testing {len(strategies_to_test)} strategies across {len(universes_to_test)} universes")

    # Run comprehensive research
    try:
        cycle_report = asyncio.run(researcher.run_full_cycle(
            universes=universes_to_test,
            strategies=strategies_to_test,
        ))

        # Handle both dict and object return types
        if hasattr(cycle_report, 'total_experiments'):
            # Object return type (ResearchCycleReport)
            cycle_results = {
                "total_experiments": cycle_report.total_experiments,
                "significant_count": cycle_report.significant_count,
                "passed_all_checks_count": cycle_report.passed_all_checks_count,
                "best_strategies": [s.__dict__ if hasattr(s, '__dict__') else s for s in cycle_report.best_strategies],
                "sector_performance": cycle_report.sector_performance,
                "experiment_leads": cycle_report.experiment_leads,
            }
        else:
            # Dict return type
            cycle_results = cycle_report

        report["phases"]["strategy_research"] = {
            "total_experiments": cycle_results.get("total_experiments", 0),
            "significant_count": cycle_results.get("significant_count", 0),
            "passed_all_checks": cycle_results.get("passed_all_checks_count", 0),
            "best_strategies": cycle_results.get("best_strategies", [])[:10],
            "sector_performance": cycle_results.get("sector_performance", {}),
            "experiment_leads": cycle_results.get("experiment_leads", [])[:5],
        }

        # Log successful strategies
        best_strats = cycle_results.get("best_strategies", [])
        for strat in best_strats:
            strat_dict = strat if isinstance(strat, dict) else strat.__dict__
            if strat_dict.get("passes_all_checks"):
                tracker.log_experiment(
                    strategy=strat_dict["strategy"],
                    symbol=strat_dict["symbol"],
                    params=strat_dict.get("params", {}),
                    result="success",
                    sharpe=strat_dict.get("val_sharpe"),
                    p_value=strat_dict.get("mcpt_p_value"),
                    notes=f"From full research cycle {report['cycle_id']}",
                    session_id=session.session_id,
                )

        logger.info(f"Completed {cycle_results.get('total_experiments', 0)} experiments")
        logger.info(f"Found {cycle_results.get('significant_count', 0)} significant strategies")

    except Exception as e:
        logger.error(f"Strategy research failed: {e}")
        report["phases"]["strategy_research"] = {"error": str(e)}

    # ===== PHASE 5: PDT Holding Period Optimization =====
    logger.info("=" * 60)
    logger.info("PHASE 5: PDT Holding Period Optimization")
    logger.info("=" * 60)

    pdt_results = {}

    try:
        best_strategies = report["phases"].get("strategy_research", {}).get("best_strategies", [])

        if best_strategies:
            # Test holding periods for top strategies
            holding_periods = [0, 2, 5, 10, 20]

            for strat in best_strategies[:5]:  # Top 5
                symbol = strat["symbol"]
                strategy_name = strat["strategy"]

                logger.info(f"Testing holding periods for {strategy_name}/{symbol}")

                # Simplified PDT test using the validation framework
                pdt_results[f"{strategy_name}_{symbol}"] = {
                    "strategy": strategy_name,
                    "symbol": symbol,
                    "original_sharpe": strat.get("val_sharpe", 0),
                    "holding_period_sharpes": {},
                    "best_pdt_holding": None,
                    "best_pdt_sharpe": None,
                }

                # Use PDT framework for analysis
                try:
                    from src.evaluation.validation.pdt_framework import PDTAwareBacktest, AccountType
                    import yfinance as yf
                    import pandas as pd
                    import numpy as np

                    # Fetch data
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period="2y")

                    if len(hist) > 100:
                        # Simulate signals based on strategy
                        prices = hist["Close"]
                        returns = prices.pct_change()

                        # Generate synthetic signals based on strategy type
                        if "bollinger" in strategy_name:
                            # Bollinger reversal signals
                            sma = prices.rolling(20).mean()
                            std = prices.rolling(20).std()
                            lower = sma - 2 * std
                            upper = sma + 2 * std
                            signals = pd.Series(0, index=prices.index)
                            signals[prices < lower] = 1
                            signals[prices > upper] = -1
                        elif "momentum" in strategy_name:
                            mom = prices.pct_change(20)
                            signals = pd.Series(0, index=prices.index)
                            signals[mom > 0.05] = 1
                            signals[mom < -0.05] = -1
                        else:
                            # RSI-based
                            delta = prices.diff()
                            gain = delta.where(delta > 0, 0).rolling(14).mean()
                            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                            rs = gain / loss.replace(0, 1e-10)
                            rsi = 100 - (100 / (1 + rs))
                            signals = pd.Series(0, index=prices.index)
                            signals[rsi < 30] = 1
                            signals[rsi > 70] = -1

                        # Test each holding period
                        for hp in holding_periods:
                            if hp == 0:
                                # No hold requirement - use raw signals
                                strat_returns = signals.shift(1) * returns
                            else:
                                # Enforce minimum holding period
                                held_signals = signals.copy()
                                position = 0
                                hold_counter = 0

                                for i in range(len(signals)):
                                    if hold_counter > 0:
                                        held_signals.iloc[i] = position
                                        hold_counter -= 1
                                    elif signals.iloc[i] != 0 and signals.iloc[i] != position:
                                        position = signals.iloc[i]
                                        hold_counter = hp
                                        held_signals.iloc[i] = position
                                    else:
                                        held_signals.iloc[i] = position

                                strat_returns = held_signals.shift(1) * returns

                            # Calculate Sharpe
                            valid_returns = strat_returns.dropna()
                            if len(valid_returns) > 20:
                                sharpe = (valid_returns.mean() / valid_returns.std()) * np.sqrt(252)
                                pdt_results[f"{strategy_name}_{symbol}"]["holding_period_sharpes"][hp] = float(sharpe)

                        # Find best PDT-compliant (2+ day hold)
                        pdt_compliant = {
                            hp: s for hp, s in pdt_results[f"{strategy_name}_{symbol}"]["holding_period_sharpes"].items()
                            if hp >= 2
                        }
                        if pdt_compliant:
                            best_hp = max(pdt_compliant, key=pdt_compliant.get)
                            pdt_results[f"{strategy_name}_{symbol}"]["best_pdt_holding"] = best_hp
                            pdt_results[f"{strategy_name}_{symbol}"]["best_pdt_sharpe"] = pdt_compliant[best_hp]

                except Exception as e:
                    logger.debug(f"PDT test failed for {strategy_name}/{symbol}: {e}")

            # Log PDT insight
            if pdt_results:
                tracker.log_insight(
                    title="PDT holding period analysis completed",
                    description=f"Tested {len(pdt_results)} strategies across {len(holding_periods)} holding periods",
                    category="strategy",
                    evidence={"pdt_results": pdt_results},
                    session_id=session.session_id,
                    tags=["pdt", "holding_period", "budget_account"],
                )

        report["phases"]["pdt_optimization"] = pdt_results
        logger.info(f"Completed PDT analysis for {len(pdt_results)} strategies")

    except Exception as e:
        logger.error(f"PDT optimization failed: {e}")
        report["phases"]["pdt_optimization"] = {"error": str(e)}

    # ===== PHASE 6: Cross-Sector Pattern Analysis =====
    logger.info("=" * 60)
    logger.info("PHASE 6: Cross-Sector Pattern Analysis")
    logger.info("=" * 60)

    patterns = {}

    try:
        strategy_research = report["phases"].get("strategy_research", {})
        sector_perf = strategy_research.get("sector_performance", {})
        best_strats = strategy_research.get("best_strategies", [])

        # Analyze which strategies work in which sectors
        strategy_sector_matrix = {}
        for strat in best_strats:
            strat_name = strat["strategy"]
            if strat_name not in strategy_sector_matrix:
                strategy_sector_matrix[strat_name] = {
                    "symbols": [],
                    "avg_sharpe": 0,
                    "count": 0,
                }
            strategy_sector_matrix[strat_name]["symbols"].append(strat["symbol"])
            strategy_sector_matrix[strat_name]["count"] += 1
            strategy_sector_matrix[strat_name]["avg_sharpe"] = (
                strategy_sector_matrix[strat_name]["avg_sharpe"] *
                (strategy_sector_matrix[strat_name]["count"] - 1) +
                strat.get("val_sharpe", 0)
            ) / strategy_sector_matrix[strat_name]["count"]

        patterns["strategy_effectiveness"] = strategy_sector_matrix
        patterns["sector_rankings"] = sorted(
            [(s, d.get("best_sharpe", 0)) for s, d in sector_perf.items()],
            key=lambda x: x[1],
            reverse=True
        )

        # Log patterns
        for strat_name, data in strategy_sector_matrix.items():
            if data["count"] >= 2:
                tracker.log_pattern(
                    pattern_name=f"{strat_name}_cross_symbol",
                    description=f"{strat_name} works on {data['count']} symbols: {data['symbols']}",
                    evidence=data,
                    confidence=min(0.8, 0.3 + 0.1 * data["count"]),
                )

        report["phases"]["pattern_analysis"] = patterns
        logger.info(f"Identified {len(strategy_sector_matrix)} strategy patterns")

    except Exception as e:
        logger.warning(f"Pattern analysis failed: {e}")
        report["phases"]["pattern_analysis"] = {"error": str(e)}

    # ===== PHASE 7: Generate Final Report =====
    logger.info("=" * 60)
    logger.info("PHASE 7: Generating Final Report")
    logger.info("=" * 60)

    report["completed_at"] = datetime.now().isoformat()

    # Summary statistics
    report["summary"] = {
        "total_experiments": report["phases"].get("strategy_research", {}).get("total_experiments", 0),
        "significant_strategies": report["phases"].get("strategy_research", {}).get("significant_count", 0),
        "production_ready": report["phases"].get("strategy_research", {}).get("passed_all_checks", 0),
        "feature_ideas": report["phases"].get("feature_discovery", {}).get("total_ideas", 0),
        "alternative_data_symbols": (
            len(alt_data_results.get("google_trends", {})) +
            len(alt_data_results.get("short_interest", {}))
        ),
        "pdt_optimized": len(report["phases"].get("pdt_optimization", {})),
        "patterns_found": len(patterns.get("strategy_effectiveness", {})),
    }

    # Top recommendations
    best_strats = report["phases"].get("strategy_research", {}).get("best_strategies", [])
    report["recommendations"] = []

    for strat in best_strats[:5]:
        pdt_key = f"{strat['strategy']}_{strat['symbol']}"
        pdt_info = pdt_results.get(pdt_key, {})

        report["recommendations"].append({
            "action": "PROMOTE_TO_PAPER",
            "strategy": strat["strategy"],
            "symbol": strat["symbol"],
            "sharpe": strat.get("val_sharpe", 0),
            "p_value": strat.get("mcpt_p_value", 1),
            "recommended_hold": pdt_info.get("best_pdt_holding", 2),
            "pdt_sharpe": pdt_info.get("best_pdt_sharpe"),
        })

    # Experiment leads (next steps)
    leads = report["phases"].get("strategy_research", {}).get("experiment_leads", [])
    report["next_experiments"] = leads[:10]

    # Save report
    report_path = output_path / f"full_research_{timestamp}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report saved to {report_path}")

    # Generate tracker summary
    tracker_summary = tracker.generate_summary_report()
    summary_path = output_path / f"tracker_summary_{timestamp}.json"
    with open(summary_path, "w") as f:
        json.dump(tracker_summary, f, indent=2)

    # End session (if method exists)
    if hasattr(session, 'end_session'):
        session.end_session()
    else:
        logger.info(f"Session {session.session_id} completed")

    # Print summary
    print("\n" + "=" * 60)
    print("RESEARCH CYCLE COMPLETE")
    print("=" * 60)
    print(f"\nSession: {report['session_id']}")
    print(f"Duration: {report['started_at']} to {report['completed_at']}")
    print(f"\nSummary:")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    print(f"\nTop Recommendations:")
    for rec in report["recommendations"][:3]:
        print(f"  - {rec['strategy']}/{rec['symbol']}: Sharpe={rec['sharpe']:.2f}, hold={rec['recommended_hold']}d")
    print(f"\nReports saved to: {output_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Run full research cycle")
    parser.add_argument("--quick", action="store_true", help="Run quick mode (reduced scope)")
    parser.add_argument("--sectors", type=str, help="Comma-separated sectors to test")
    parser.add_argument("--strategies", type=str, help="Comma-separated strategies to test")
    parser.add_argument("--output-dir", type=str, default="/home/nock/quant_results/full_research",
                       help="Output directory")

    args = parser.parse_args()

    sectors = args.sectors.split(",") if args.sectors else None
    strategies = args.strategies.split(",") if args.strategies else None

    report = run_full_research_cycle(
        quick_mode=args.quick,
        sectors=sectors,
        strategies=strategies,
        output_dir=args.output_dir,
    )

    return 0 if report.get("summary", {}).get("production_ready", 0) > 0 else 1


if __name__ == "__main__":
    exit(main())
