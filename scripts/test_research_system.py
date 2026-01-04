#!/usr/bin/env python3
"""
Comprehensive Test Suite for Research System Enhancements

Tests all new components and generates documentation artifacts.
"""

import asyncio
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

# Output directory
OUTPUT_DIR = Path.home() / "quant_results" / "system_tests"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Test results accumulator
TEST_RESULTS = {
    "timestamp": datetime.now().isoformat(),
    "tests": {},
    "summary": {},
}


def log_test(name: str, passed: bool, details: dict = None):
    """Log a test result."""
    TEST_RESULTS["tests"][name] = {
        "passed": passed,
        "details": details or {},
        "timestamp": datetime.now().isoformat(),
    }
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")


def save_artifact(name: str, data: any, format: str = "json"):
    """Save an artifact to the output directory."""
    path = OUTPUT_DIR / f"{name}.{format}"

    if format == "json":
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    elif format == "csv":
        if isinstance(data, pd.DataFrame):
            data.to_csv(path)
        else:
            pd.DataFrame(data).to_csv(path)
    elif format == "md":
        with open(path, "w") as f:
            f.write(data)

    print(f"  Saved: {path}")
    return path


# =============================================================================
# TEST 1: Research Dashboard
# =============================================================================

def test_research_dashboard():
    """Test the ResearchDashboard component."""
    print("\n" + "=" * 60)
    print("TEST 1: Research Dashboard")
    print("=" * 60)

    from workflows.research.research_dashboard import ResearchDashboard

    dashboard = ResearchDashboard()

    # Test get_status
    try:
        status = dashboard.get_status()
        log_test("get_status()", True, {
            "total_experiments": status["total_experiments"],
            "total_successes": status["total_successes"],
            "coverage_pct": status["coverage_pct"],
        })
        save_artifact("dashboard_status", status)
    except Exception as e:
        log_test("get_status()", False, {"error": str(e)})

    # Test coverage matrix
    try:
        matrix = dashboard.get_coverage_matrix()
        log_test("get_coverage_matrix()", True, {
            "shape": list(matrix.shape),
            "strategies": len(matrix.index),
            "symbols": len(matrix.columns),
        })
        save_artifact("coverage_matrix", matrix, "csv")
    except Exception as e:
        log_test("get_coverage_matrix()", False, {"error": str(e)})

    # Test learning curve
    try:
        curve = dashboard.get_learning_curve()
        log_test("get_learning_curve()", True, {
            "data_points": len(curve),
        })
        if not curve.empty:
            save_artifact("learning_curve", curve, "csv")
    except Exception as e:
        log_test("get_learning_curve()", False, {"error": str(e)})

    # Test export summary
    try:
        summary = dashboard.export_research_summary()
        log_test("export_research_summary()", True, {
            "length": len(summary),
        })
        save_artifact("research_summary", summary, "md")
    except Exception as e:
        log_test("export_research_summary()", False, {"error": str(e)})

    # Test strategy analysis
    try:
        perf = dashboard.get_strategy_performance("bollinger_reversal")
        log_test("get_strategy_performance()", True, perf)
        save_artifact("strategy_performance_bollinger", perf)
    except Exception as e:
        log_test("get_strategy_performance()", False, {"error": str(e)})

    return status


# =============================================================================
# TEST 2: Knowledge Base Deduplication
# =============================================================================

def test_deduplication():
    """Test deduplication features in KnowledgeBase."""
    print("\n" + "=" * 60)
    print("TEST 2: Knowledge Base Deduplication")
    print("=" * 60)

    from workflows.research.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()

    # Test check_before_experiment - already tested
    try:
        check = kb.check_before_experiment(
            "bollinger_reversal", "QCOM", {"period": 20, "num_std": 2.0}
        )
        log_test("check_before_experiment (existing)", True, check)
    except Exception as e:
        log_test("check_before_experiment (existing)", False, {"error": str(e)})

    # Test check_before_experiment - new experiment
    try:
        check = kb.check_before_experiment(
            "momentum_20d", "TSLA", {"lookback": 20}
        )
        log_test("check_before_experiment (new)", True, check)
    except Exception as e:
        log_test("check_before_experiment (new)", False, {"error": str(e)})

    # Test find_similar_experiments
    try:
        similar = kb.find_similar_experiments(
            "bollinger_reversal", "QCOM", {"period": 20}
        )
        log_test("find_similar_experiments()", True, {
            "similar_count": len(similar),
        })
    except Exception as e:
        log_test("find_similar_experiments()", False, {"error": str(e)})

    # Test get_promising_variations
    try:
        variations = kb.get_promising_variations(10)
        log_test("get_promising_variations()", True, {
            "suggestions": len(variations),
        })
        save_artifact("promising_variations", variations)
    except Exception as e:
        log_test("get_promising_variations()", False, {"error": str(e)})

    # Test summarize_failures
    try:
        summary = kb.summarize_failures()
        log_test("summarize_failures()", True, {
            "total_failures": summary["total_failures"],
            "avoid_strategies": summary["avoid_strategies"][:5],
        })
        save_artifact("failure_summary", summary)
    except Exception as e:
        log_test("summarize_failures()", False, {"error": str(e)})


# =============================================================================
# TEST 3: Session Context
# =============================================================================

def test_session_context():
    """Test SessionContext for cross-session continuity."""
    print("\n" + "=" * 60)
    print("TEST 3: Session Context")
    print("=" * 60)

    from workflows.research.session_context import SessionContext

    context = SessionContext()

    # Test save and load
    try:
        test_state = {
            "focus_strategy": "test_strategy",
            "focus_symbols": ["AAPL", "MSFT"],
            "notes": "Testing session context",
            "next_steps": ["Run more tests", "Analyze results"],
        }
        context.save_session_state(test_state)
        loaded = context.load_last_session()

        passed = (
            loaded["focus_strategy"] == test_state["focus_strategy"] and
            loaded["focus_symbols"] == test_state["focus_symbols"]
        )
        log_test("save/load session state", passed, loaded)
    except Exception as e:
        log_test("save/load session state", False, {"error": str(e)})

    # Test get_briefing
    try:
        briefing = context.get_briefing()
        log_test("get_briefing()", True, {
            "length": len(briefing),
        })
        save_artifact("session_briefing", briefing, "md")
    except Exception as e:
        log_test("get_briefing()", False, {"error": str(e)})

    # Test session history
    try:
        history = context.get_session_history(5)
        log_test("get_session_history()", True, {
            "history_count": len(history),
        })
    except Exception as e:
        log_test("get_session_history()", False, {"error": str(e)})


# =============================================================================
# TEST 4: Options Data Fetching
# =============================================================================

async def test_options_data():
    """Test options data fetching from Yahoo Finance."""
    print("\n" + "=" * 60)
    print("TEST 4: Options Data Fetching (Yahoo Finance)")
    print("=" * 60)

    from src.data.sources.alternative.options_flow import (
        OptionsFlowSource, get_put_call_ratio, calculate_max_pain,
        get_options_features, OptionType
    )

    symbols_to_test = ["AAPL", "MSFT", "SPY"]
    options_results = {}

    source = OptionsFlowSource()

    try:
        for symbol in symbols_to_test:
            try:
                # Fetch options chain
                contracts = await source.fetch_options_chain(symbol)

                if contracts:
                    calls = [c for c in contracts if c.option_type == OptionType.CALL]
                    puts = [c for c in contracts if c.option_type == OptionType.PUT]

                    # Get current price estimate
                    price = source._estimate_underlying_price(contracts)

                    # Extract features
                    features = get_options_features(contracts, price)

                    options_results[symbol] = {
                        "total_contracts": len(contracts),
                        "calls": len(calls),
                        "puts": len(puts),
                        "estimated_price": price,
                        "features": features,
                    }

                    log_test(f"fetch_options_chain({symbol})", True, {
                        "contracts": len(contracts),
                    })
                else:
                    log_test(f"fetch_options_chain({symbol})", False, {
                        "error": "No contracts returned"
                    })

            except Exception as e:
                log_test(f"fetch_options_chain({symbol})", False, {"error": str(e)})

        save_artifact("options_data_test", options_results)

    finally:
        await source.close()

    # Test put/call ratio
    try:
        pc_ratio = await get_put_call_ratio("AAPL")
        log_test("get_put_call_ratio()", True, pc_ratio)
        options_results["AAPL_pc_ratio"] = pc_ratio
    except Exception as e:
        log_test("get_put_call_ratio()", False, {"error": str(e)})

    # Test max pain
    try:
        max_pain = await calculate_max_pain("AAPL")
        log_test("calculate_max_pain()", True, max_pain)
        options_results["AAPL_max_pain"] = max_pain
    except Exception as e:
        log_test("calculate_max_pain()", False, {"error": str(e)})

    save_artifact("options_full_results", options_results)
    return options_results


# =============================================================================
# TEST 5: ETF Flow Estimation
# =============================================================================

async def test_etf_flows():
    """Test ETF flow estimation from Yahoo Finance."""
    print("\n" + "=" * 60)
    print("TEST 5: ETF Flow Estimation (Yahoo Finance)")
    print("=" * 60)

    from src.data.sources.alternative.etf_flows import (
        ETFFlowSource, estimate_etf_flows, get_quick_sector_snapshot,
        get_etf_flow_features
    )

    etf_results = {}

    source = ETFFlowSource()

    try:
        # Test single ETF flow
        etfs_to_test = ["SPY", "QQQ", "XLK", "XLF", "TLT"]

        for etf in etfs_to_test:
            try:
                flows = await source.fetch_flow_history(etf, 20)

                if flows:
                    features = get_etf_flow_features(flows)
                    net_flow = sum(f.estimated_flow for f in flows)

                    etf_results[etf] = {
                        "days": len(flows),
                        "net_flow": round(net_flow, 2),
                        "features": features,
                    }

                    log_test(f"fetch_flow_history({etf})", True, {
                        "days": len(flows),
                        "net_flow": round(net_flow, 2),
                    })
                else:
                    log_test(f"fetch_flow_history({etf})", False, {
                        "error": "No flows returned"
                    })

            except Exception as e:
                log_test(f"fetch_flow_history({etf})", False, {"error": str(e)})

    finally:
        await source.close()

    # Test sector snapshot
    try:
        snapshot = await get_quick_sector_snapshot()
        log_test("get_quick_sector_snapshot()", True, {
            "sectors": len(snapshot.get("sectors", {})),
            "top_inflows": snapshot.get("top_inflows", []),
        })
        save_artifact("sector_snapshot", snapshot)
        etf_results["sector_snapshot"] = snapshot
    except Exception as e:
        log_test("get_quick_sector_snapshot()", False, {"error": str(e)})

    # Test multi-ETF estimation
    try:
        df = await estimate_etf_flows(["SPY", "QQQ", "IWM"], days=10)
        log_test("estimate_etf_flows()", True, {
            "rows": len(df),
        })
        if not df.empty:
            save_artifact("etf_flows_data", df, "csv")
    except Exception as e:
        log_test("estimate_etf_flows()", False, {"error": str(e)})

    save_artifact("etf_flow_results", etf_results)
    return etf_results


# =============================================================================
# TEST 6: Interactive Session Protocol
# =============================================================================

async def test_interactive_session():
    """Test the interactive session protocol."""
    print("\n" + "=" * 60)
    print("TEST 6: Interactive Session Protocol")
    print("=" * 60)

    from workflows.research.interactive_session import (
        start_research_session, what_works, what_failed,
        what_is_tested, should_run, get_next_experiments
    )

    # Test session start
    try:
        briefing = await start_research_session()
        log_test("start_research_session()", True, {
            "total_experiments": briefing.total_experiments,
            "total_successes": briefing.total_successes,
            "suggested_count": len(briefing.suggested_experiments),
        })
        save_artifact("session_start_briefing", {
            "total_experiments": briefing.total_experiments,
            "total_successes": briefing.total_successes,
            "significant_strategies": briefing.significant_strategies[:10],
            "suggested_experiments": briefing.suggested_experiments[:10],
            "untested_combinations": briefing.untested_combinations[:20],
        })
    except Exception as e:
        log_test("start_research_session()", False, {"error": str(e)})

    # Test what_works
    try:
        works = what_works()
        log_test("what_works()", True, {"count": len(works)})
    except Exception as e:
        log_test("what_works()", False, {"error": str(e)})

    # Test what_failed
    try:
        failed = what_failed()
        log_test("what_failed()", True, {
            "total": failed["total_failures"],
        })
    except Exception as e:
        log_test("what_failed()", False, {"error": str(e)})

    # Test what_is_tested
    try:
        tested = what_is_tested()
        log_test("what_is_tested()", True, {
            "coverage": tested["coverage_pct"],
        })
    except Exception as e:
        log_test("what_is_tested()", False, {"error": str(e)})

    # Test should_run
    try:
        check = should_run("momentum_20d", "TSLA")
        log_test("should_run()", True, check)
    except Exception as e:
        log_test("should_run()", False, {"error": str(e)})

    # Test get_next_experiments
    try:
        next_exp = get_next_experiments(5)
        log_test("get_next_experiments()", True, {
            "suggestions": len(next_exp),
        })
    except Exception as e:
        log_test("get_next_experiments()", False, {"error": str(e)})


# =============================================================================
# TEST 7: Experiment Templates
# =============================================================================

def test_experiment_templates():
    """Test experiment templates."""
    print("\n" + "=" * 60)
    print("TEST 7: Experiment Templates")
    print("=" * 60)

    from workflows.research.experiment_templates import (
        EXPERIMENT_TEMPLATES, suggest_experiments, get_default_param_grid,
        create_single_test, create_sweep, get_template_info
    )

    # Test template listing
    try:
        template_info = {
            name: get_template_info(name)
            for name in EXPERIMENT_TEMPLATES.keys()
        }
        log_test("EXPERIMENT_TEMPLATES", True, {
            "count": len(template_info),
        })
        save_artifact("experiment_templates", template_info)
    except Exception as e:
        log_test("EXPERIMENT_TEMPLATES", False, {"error": str(e)})

    # Test suggest_experiments
    try:
        suggestions = suggest_experiments(5)
        log_test("suggest_experiments()", True, {
            "count": len(suggestions),
        })
        suggestion_data = [
            {"template": s.template, "params": s.params}
            for s in suggestions
        ]
        save_artifact("experiment_suggestions", suggestion_data)
    except Exception as e:
        log_test("suggest_experiments()", False, {"error": str(e)})

    # Test param grids
    try:
        grids = {
            strategy: get_default_param_grid(strategy)
            for strategy in ["momentum_20d", "rsi_reversal", "bollinger_reversal", "macd"]
        }
        log_test("get_default_param_grid()", True, {
            "strategies": len(grids),
        })
        save_artifact("param_grids", grids)
    except Exception as e:
        log_test("get_default_param_grid()", False, {"error": str(e)})

    # Test config creation
    try:
        config1 = create_single_test("momentum_20d", "AAPL", lookback=20)
        config2 = create_sweep(strategy="bollinger_reversal")

        validation_errors = config1.validate()
        log_test("create_single_test()", len(validation_errors) == 0, {
            "params": config1.params,
        })
    except Exception as e:
        log_test("create_single_test()", False, {"error": str(e)})


# =============================================================================
# TEST 8: Data-Strategy Mapping
# =============================================================================

def test_data_strategy_mapping():
    """Test data-strategy mapping."""
    print("\n" + "=" * 60)
    print("TEST 8: Data-Strategy Mapping")
    print("=" * 60)

    from workflows.research.data_strategy_map import (
        get_strategies_for_data, get_data_requirements,
        check_data_availability, get_available_strategies,
        get_unavailable_strategies, get_data_source_status
    )

    # Test data source status
    try:
        status = get_data_source_status()
        log_test("get_data_source_status()", True, {
            "sources": len(status),
        })
        save_artifact("data_source_status", status)
    except Exception as e:
        log_test("get_data_source_status()", False, {"error": str(e)})

    # Test strategies for data
    try:
        options_strats = get_strategies_for_data("options")
        price_strats = get_strategies_for_data("price_yahoo")
        log_test("get_strategies_for_data()", True, {
            "options_strategies": len(options_strats),
            "price_strategies": len(price_strats),
        })
    except Exception as e:
        log_test("get_strategies_for_data()", False, {"error": str(e)})

    # Test data requirements
    try:
        reqs = {
            "momentum_20d": [str(r) for r in get_data_requirements("momentum_20d")],
            "put_call_contrarian": [str(r) for r in get_data_requirements("put_call_contrarian")],
            "multi_signal": [str(r) for r in get_data_requirements("multi_signal")],
        }
        log_test("get_data_requirements()", True, reqs)
    except Exception as e:
        log_test("get_data_requirements()", False, {"error": str(e)})

    # Test availability check
    try:
        checks = {
            strategy: check_data_availability(strategy)
            for strategy in ["momentum_20d", "options_flow_momentum", "reddit_sentiment"]
        }
        log_test("check_data_availability()", True, {
            s: c["can_run"] for s, c in checks.items()
        })
        save_artifact("data_availability_checks", checks)
    except Exception as e:
        log_test("check_data_availability()", False, {"error": str(e)})

    # Test available/unavailable strategies
    try:
        available = get_available_strategies()
        unavailable = get_unavailable_strategies()
        log_test("get_available_strategies()", True, {
            "available": len(available),
            "unavailable": len(unavailable),
        })
        save_artifact("strategy_availability", {
            "available": available,
            "unavailable": [(s, m) for s, m in unavailable],
        })
    except Exception as e:
        log_test("get_available_strategies()", False, {"error": str(e)})


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("COMPREHENSIVE RESEARCH SYSTEM TEST SUITE")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # Run synchronous tests
    dashboard_status = test_research_dashboard()
    test_deduplication()
    test_session_context()
    test_experiment_templates()
    test_data_strategy_mapping()

    # Run async tests
    options_results = await test_options_data()
    etf_results = await test_etf_flows()
    await test_interactive_session()

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    total = len(TEST_RESULTS["tests"])
    passed = sum(1 for t in TEST_RESULTS["tests"].values() if t["passed"])
    failed = total - passed

    TEST_RESULTS["summary"] = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": f"{passed/total*100:.1f}%",
    }

    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass Rate: {passed/total*100:.1f}%")

    if failed > 0:
        print("\nFailed Tests:")
        for name, result in TEST_RESULTS["tests"].items():
            if not result["passed"]:
                print(f"  - {name}: {result['details'].get('error', 'Unknown')}")

    # Save final results
    save_artifact("test_results", TEST_RESULTS)

    print(f"\nArtifacts saved to: {OUTPUT_DIR}")
    print("=" * 70)

    return TEST_RESULTS


if __name__ == "__main__":
    results = asyncio.run(main())
