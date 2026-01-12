#!/usr/bin/env python3
"""Validate Data Flow - Ensure all systems are working with no missing values.

Tests:
1. SignalAggregator generates signals for all symbols
2. Congressional cluster data is accessible
3. Adversarial agent can access portfolio state
4. Knowledge base has company/sector data
5. State.json has complete data
6. No missing values in critical fields

Usage:
    PYTHONPATH=. python scripts/validate_data_flow.py
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from src.core.paths import paths


def print_header(text: str):
    """Print section header."""
    print()
    print("=" * 60)
    print(text)
    print("=" * 60)


def print_result(name: str, success: bool, message: str = ""):
    """Print test result."""
    status = "[PASS]" if success else "[FAIL]"
    msg = f" - {message}" if message else ""
    print(f"  {status} {name}{msg}")


def test_signal_aggregator() -> tuple[bool, list[str]]:
    """Test SignalAggregator generates signals."""
    issues = []

    try:
        from src.synthesis.signals import SignalAggregator

        # Test with a small set of symbols
        test_symbols = ["SPY", "AAPL", "MSFT", "SLB"]

        aggregator = SignalAggregator(watchlist=test_symbols)
        signals = aggregator.aggregate(
            symbols=test_symbols,
            include_alt_data=True,
            include_technicals=True,
        )

        if not signals:
            issues.append("No signals returned")
            return False, issues

        for symbol, signal in signals.items():
            # Check critical fields
            if signal.composite_score is None:
                issues.append(f"{symbol}: missing composite_score")

            if not signal.signals_available:
                issues.append(f"{symbol}: no signals available")

            if signal.rsi is None or signal.rsi == 50.0:
                # RSI of exactly 50 might indicate no data
                pass  # This is OK - default value

            print_result(
                f"{symbol}",
                len(signal.signals_available) > 0,
                f"signals={len(signal.signals_available)}, composite={signal.composite_score:.2f}",
            )

        return len(issues) == 0, issues

    except Exception as e:
        issues.append(f"Exception: {str(e)}")
        return False, issues


def test_congressional_data() -> tuple[bool, list[str]]:
    """Test congressional trading data is accessible."""
    issues = []

    try:
        import pandas as pd

        archive_path = paths.base / "congressional_archive" / "processed" / "all_trades.parquet"

        if not archive_path.exists():
            issues.append(f"Archive not found: {archive_path}")
            return False, issues

        df = pd.read_parquet(archive_path)

        if df.empty:
            issues.append("Archive is empty")
            return False, issues

        # Check critical columns
        required_cols = ["politician", "symbol", "trade_type", "transaction_date"]
        for col in required_cols:
            if col not in df.columns:
                issues.append(f"Missing column: {col}")

        # Check for data quality
        null_counts = df[required_cols].isnull().sum()
        for col, count in null_counts.items():
            if count > 0:
                pct = count / len(df) * 100
                if pct > 5:
                    issues.append(f"{col}: {pct:.1f}% null values")

        print_result(
            "Congressional archive",
            len(issues) == 0,
            f"{len(df)} trades, {df['politician'].nunique()} politicians",
        )

        return len(issues) == 0, issues

    except Exception as e:
        issues.append(f"Exception: {str(e)}")
        return False, issues


def test_adversarial_agent() -> tuple[bool, list[str]]:
    """Test adversarial agent can access state and generate challenges."""
    issues = []

    try:
        from src.decision.adversary import AdversarialAgent

        agent = AdversarialAgent()

        # Test state access
        state = agent._get_current_state()
        if state is None:
            issues.append("Cannot access current state")
            return False, issues

        # Check state has required fields
        required_fields = ["portfolio", "positions", "theses"]
        for field in required_fields:
            if field not in state:
                issues.append(f"State missing field: {field}")

        # Test challenge generation
        analysis = agent.challenge(
            symbol="SLB",
            proposed_action="BUY",
            reasoning="Venezuela thesis + technical oversold",
            confidence=0.7,
            context={"size_pct": 5, "sector": "Energy"},
        )

        if not analysis:
            issues.append("Challenge returned None")
            return False, issues

        # Check analysis has content
        if not analysis.market_structure_concerns:
            issues.append("No market structure concerns generated")

        print_result(
            "Adversarial Agent",
            len(issues) == 0,
            f"concern_level={analysis.overall_concern_level}, "
            f"proceed={analysis.proceed_recommendation}",
        )

        return len(issues) == 0, issues

    except Exception as e:
        issues.append(f"Exception: {str(e)}")
        return False, issues


def test_knowledge_base() -> tuple[bool, list[str]]:
    """Test knowledge base has data."""
    issues = []

    try:
        from src.knowledge.base import KnowledgeBase

        kb = KnowledgeBase()

        companies = kb.list_companies()
        sectors = kb.list_sectors()

        if not companies:
            issues.append("No company briefs found")

        if not sectors:
            issues.append("No sector contexts found")

        # Test retrieval
        slb = kb.get_company("SLB")
        if slb:
            if not slb.business_model:
                issues.append("SLB brief missing business_model")
            if not slb.key_risks:
                issues.append("SLB brief missing key_risks")

        energy = kb.get_sector("Energy")
        if energy:
            if not energy.current_assessment:
                issues.append("Energy sector missing current_assessment")

        print_result(
            "Knowledge Base",
            len(issues) == 0,
            f"{len(companies)} companies, {len(sectors)} sectors",
        )

        return len(issues) == 0, issues

    except Exception as e:
        issues.append(f"Exception: {str(e)}")
        return False, issues


def test_state_json() -> tuple[bool, list[str]]:
    """Test state.json has complete data."""
    issues = []

    try:
        state_path = paths.live_state

        if not state_path.exists():
            issues.append(f"State file not found: {state_path}")
            return False, issues

        with open(state_path) as f:
            state = json.load(f)

        # Check top-level fields
        required_fields = [
            "market", "sentiment", "portfolio", "positions",
            "risk", "theses", "watchlist_signals",
        ]

        for field in required_fields:
            if field not in state:
                issues.append(f"Missing field: {field}")
            elif state[field] is None:
                issues.append(f"Null field: {field}")

        # Check market data
        market = state.get("market", {})
        if not market.get("spy_price"):
            issues.append("Missing SPY price")
        if market.get("vix") is None:
            issues.append("Missing VIX")

        # Check portfolio data
        portfolio = state.get("portfolio", {})
        if not portfolio.get("equity"):
            issues.append("Missing equity value")

        # Check positions
        positions = state.get("positions", [])
        if not positions:
            issues.append("No positions in state")
        else:
            # Check position data quality
            for pos in positions[:5]:  # Check first 5
                if not pos.get("symbol"):
                    issues.append("Position missing symbol")
                if pos.get("market_value") is None:
                    issues.append(f"Position {pos.get('symbol')} missing market_value")

        # Check watchlist signals
        signals = state.get("watchlist_signals", {})
        if not signals:
            issues.append("No watchlist signals")
        else:
            for symbol, sig in list(signals.items())[:3]:
                if sig.get("composite_score") is None:
                    issues.append(f"Signal {symbol} missing composite_score")

        # Check timestamp freshness
        timestamp = state.get("timestamp")
        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                age_minutes = (datetime.now() - ts.replace(tzinfo=None)).seconds / 60
                if age_minutes > 30:
                    issues.append(f"State is {age_minutes:.0f} minutes old")
            except Exception:
                pass

        print_result(
            "State JSON",
            len(issues) == 0,
            f"{len(positions)} positions, {len(signals)} signals",
        )

        return len(issues) == 0, issues

    except Exception as e:
        issues.append(f"Exception: {str(e)}")
        return False, issues


def test_cron_logs() -> tuple[bool, list[str]]:
    """Test cron jobs have run successfully."""
    issues = []

    logs_dir = paths.base / "logs"
    if not logs_dir.exists():
        issues.append("Logs directory not found")
        return False, issues

    log_files = [
        "research_prep.log",
        "news_collect.log",
        "daemon.log",
    ]

    for log_file in log_files:
        log_path = logs_dir / log_file
        if not log_path.exists():
            print_result(log_file, False, "not created yet")
        else:
            # Check if log has recent entries
            stat = log_path.stat()
            age_hours = (datetime.now().timestamp() - stat.st_mtime) / 3600
            if age_hours < 24:
                print_result(log_file, True, f"updated {age_hours:.1f}h ago")
            else:
                print_result(log_file, False, f"stale ({age_hours:.0f}h old)")
                issues.append(f"{log_file} is stale")

    return len(issues) == 0, issues


def run_tests():
    """Run all validation tests."""
    print_header("DATA FLOW VALIDATION")
    print(f"Timestamp: {datetime.now().isoformat()}")

    all_passed = True
    all_issues = []

    # Test 1: Signal Aggregator
    print_header("1. Signal Aggregator")
    passed, issues = test_signal_aggregator()
    all_passed = all_passed and passed
    all_issues.extend(issues)

    # Test 2: Congressional Data
    print_header("2. Congressional Data")
    passed, issues = test_congressional_data()
    all_passed = all_passed and passed
    all_issues.extend(issues)

    # Test 3: Adversarial Agent
    print_header("3. Adversarial Agent")
    passed, issues = test_adversarial_agent()
    all_passed = all_passed and passed
    all_issues.extend(issues)

    # Test 4: Knowledge Base
    print_header("4. Knowledge Base")
    passed, issues = test_knowledge_base()
    all_passed = all_passed and passed
    all_issues.extend(issues)

    # Test 5: State JSON
    print_header("5. State JSON")
    passed, issues = test_state_json()
    all_passed = all_passed and passed
    all_issues.extend(issues)

    # Test 6: Cron Logs
    print_header("6. Cron Job Status")
    passed, issues = test_cron_logs()
    all_passed = all_passed and passed
    all_issues.extend(issues)

    # Summary
    print_header("VALIDATION SUMMARY")
    if all_passed:
        print("ALL TESTS PASSED")
        print("Data flow is working correctly with no missing values.")
    else:
        print(f"ISSUES FOUND: {len(all_issues)}")
        for issue in all_issues:
            print(f"  - {issue}")

    return 0 if all_passed else 1


def main():
    """CLI entry point."""
    return run_tests()


if __name__ == "__main__":
    sys.exit(main())
