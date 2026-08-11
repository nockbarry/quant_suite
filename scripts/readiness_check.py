#!/usr/bin/env python3
"""Athena System Readiness Check — Diagnose and fix issues across all subsystems.

Checks:
1. Cron jobs installed and current
2. Sentinel health (running, responsive)
3. Operator session health (running, not stale)
4. state.json freshness and completeness (positions, signals, convergences)
5. Data collection pipeline (RSS, Finviz, WSB, signals)
6. Cross-session information flow (artifact provenance, freshness)
7. Prediction scoring loop (scorable predictions, baselines)
8. Strategic context (hypotheses, patterns, catalysts)
9. Session scheduling (all sessions running on time)
10. Database integrity (tables, row counts, orphans)
11. Credential validation (Alpaca, data sources)

Usage:
    python3 scripts/readiness_check.py              # Full check
    python3 scripts/readiness_check.py --fix        # Auto-fix what's fixable
    python3 scripts/readiness_check.py --category cron  # Check specific category
    python3 scripts/readiness_check.py --quick      # Fast checks only (no network)

Cron (optional):
    0 5 * * 1-5 cd /home/nock/projects/quant_suite && PYTHONPATH=. python3 scripts/readiness_check.py --fix >> ~/quant_results/logs/readiness.log 2>&1
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.core.paths import paths

RESULTS_DIR = paths.base
SCHEDULER_DIR = RESULTS_DIR / "scheduler"
LOG_DIR = RESULTS_DIR / "logs"
STATE_FILE = paths.live_state
DB_FILE = RESULTS_DIR / "athena.db"


class Check:
    """Single readiness check result."""

    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.status = "unknown"  # pass, warn, fail, fixed
        self.message = ""
        self.fix_applied = ""

    def passed(self, msg: str = "OK"):
        self.status = "pass"
        self.message = msg
        return self

    def warn(self, msg: str):
        self.status = "warn"
        self.message = msg
        return self

    def fail(self, msg: str):
        self.status = "fail"
        self.message = msg
        return self

    def fixed(self, msg: str, fix: str):
        self.status = "fixed"
        self.message = msg
        self.fix_applied = fix
        return self


def icon(status: str) -> str:
    return {"pass": "[OK]", "warn": "[!!]", "fail": "[XX]", "fixed": "[FX]", "unknown": "[??]"}[status]


# ===== CRON CHECKS =====

def check_cron_installed() -> list[Check]:
    checks = []

    c = Check("Data cron (QUANT_SUITE_TRADING)", "cron")
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if "QUANT_SUITE_TRADING" in result.stdout:
            lines = [l for l in result.stdout.split("\n") if "QUANT_SUITE_TRADING" in l]
            c.passed(f"{len(lines)} data cron entries installed")
        else:
            c.fail("Data cron not installed — run: ./scripts/setup_cron.sh install")
    except Exception as e:
        c.fail(f"Can't read crontab: {e}")
    checks.append(c)

    c = Check("Cron drift vs setup_cron.sh", "cron")
    try:
        r = subprocess.run(
            [str(PROJECT_DIR / "scripts" / "setup_cron.sh"), "diff"],
            capture_output=True, text=True, cwd=str(PROJECT_DIR), timeout=30,
        )
        if r.returncode == 0:
            c.passed("live crontab matches setup_cron.sh")
        else:
            # Drift = the exact failure mode that silently killed 6 engines in Jun.
            drift_lines = [l for l in r.stdout.split("\n") if l.strip().startswith(("-", "+"))]
            c.fail(f"crontab drift ({len(drift_lines)} lines) — run setup_cron.sh install_all or mirror the edit")
    except Exception as e:
        c.warn(f"Drift check failed to run: {e}")
    checks.append(c)

    c = Check("Auto cron (QUANT_SUITE_AUTO)", "cron")
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if "QUANT_SUITE_AUTO" in result.stdout:
            lines = [l for l in result.stdout.split("\n") if "QUANT_SUITE_AUTO" in l]
            c.passed(f"{len(lines)} auto cron entries installed")

            # Check for expected entries
            expected = [
                "morning-briefing", "operator-start", "trade-decision",
                "eod-review", "sentinel-start", "sentinel-stop",
                "evening-research", "internal-review", "signal-scan",
            ]
            cron_text = result.stdout
            missing = [e for e in expected if e not in cron_text]
            if missing:
                c.warn(f"Auto cron installed but missing: {', '.join(missing)}")
        else:
            c.fail("Auto cron not installed — run: ./scripts/setup_cron.sh install_auto")
    except Exception as e:
        c.fail(f"Can't read crontab: {e}")
    checks.append(c)

    return checks


def fix_cron(auto_fix: bool) -> list[Check]:
    if not auto_fix:
        return []
    checks = []
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    drift = subprocess.run(
        [str(PROJECT_DIR / "scripts" / "setup_cron.sh"), "diff"],
        capture_output=True, text=True, cwd=str(PROJECT_DIR), timeout=30,
    )
    if (
        "QUANT_SUITE_AUTO" not in result.stdout
        or "evening-research" not in result.stdout
        or drift.returncode != 0
    ):
        c = Check("Reinstall auto cron", "cron")
        r = subprocess.run(
            [str(PROJECT_DIR / "scripts" / "setup_cron.sh"), "install_all"],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        if r.returncode == 0:
            c.fixed("Auto cron reinstalled with all entries", "setup_cron.sh install_all")
        else:
            c.fail(f"Cron install failed: {r.stderr[:200]}")
        checks.append(c)
    return checks


# ===== SENTINEL CHECKS =====

def check_sentinel() -> list[Check]:
    checks = []

    c = Check("Sentinel process", "sentinel")
    try:
        result = subprocess.run(
            ["pgrep", "-f", "sentinel.py"],
            capture_output=True, text=True,
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            c.passed(f"Running (PID {pids[0]})")
        else:
            # Check if market hours
            now = datetime.now()
            if now.weekday() < 5 and 5 <= now.hour <= 17:
                c.fail("Not running during market hours")
            else:
                c.passed("Not running (outside market hours)")
    except Exception as e:
        c.fail(f"Can't check: {e}")
    checks.append(c)

    c = Check("Situation board freshness", "sentinel")
    board_file = SCHEDULER_DIR / "situation_board.json"
    if board_file.exists():
        age_min = (time.time() - board_file.stat().st_mtime) / 60
        try:
            with open(board_file) as f:
                board = json.load(f)
            obs_count = len(board.get("today_observations", []))
            board_date = board.get("date", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if board_date != today:
                c.warn(f"Board date is {board_date}, not today ({today})")
            elif age_min > 10 and datetime.now().hour < 17:
                c.warn(f"Board {age_min:.0f}min old ({obs_count} observations)")
            else:
                c.passed(f"{age_min:.0f}min old, {obs_count} observations")
        except Exception as e:
            c.fail(f"Can't read board: {e}")
    else:
        c.warn("No situation board file")
    checks.append(c)

    return checks


# ===== OPERATOR CHECKS =====

def check_operator() -> list[Check]:
    checks = []

    c = Check("Operator session", "operator")
    lock_file = SCHEDULER_DIR / "locks" / "operator.lock"
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
            result = subprocess.run(
                ["ps", "-o", "stat=,etime=", "-p", str(pid)],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                stat, etime = result.stdout.strip().split(None, 1)
                if stat[0] in ("T", "Z"):
                    c.fail(f"Operator stuck (state={stat}, uptime={etime})")
                else:
                    c.passed(f"Running (PID {pid}, uptime={etime.strip()})")
            else:
                c.warn("Lock exists but process dead (stale lock)")
        except Exception as e:
            c.warn(f"Lock check error: {e}")
    else:
        now = datetime.now()
        if now.weekday() < 5 and 8 <= now.hour < 16:
            c.warn("No operator lock during market hours")
        else:
            c.passed("Not running (outside market hours)")
    checks.append(c)

    # Check for the "stale task" bug
    c = Check("Operator not stale-tasked", "operator")
    today = datetime.now().strftime("%Y%m%d")
    op_log = LOG_DIR / f"claude_operator_{today}.log"
    if op_log.exists():
        content = op_log.read_text()
        if "Stale task" in content:
            c.fail("Operator hit 'Stale task' bug today — session was wasted")
        elif "operator_check" in content.lower() or "operator-session" in content.lower():
            c.passed("Operator produced real output")
        elif len(content) < 500:
            c.warn(f"Operator log suspiciously small ({len(content)} bytes)")
        else:
            c.passed(f"Operator log {len(content)} bytes")
    else:
        c.passed("No operator log today (may not have run yet)")
    checks.append(c)

    return checks


# ===== STATE.JSON CHECKS =====

def check_state() -> list[Check]:
    checks = []

    c = Check("state.json exists and fresh", "state")
    if STATE_FILE.exists():
        age_min = (time.time() - STATE_FILE.stat().st_mtime) / 60
        now = datetime.now()
        if now.weekday() < 5 and 6 <= now.hour <= 17 and age_min > 10:
            c.warn(f"state.json {age_min:.0f}min old during market hours")
        else:
            c.passed(f"{age_min:.0f}min old")
    else:
        c.fail("state.json does not exist")
    checks.append(c)

    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
        except Exception as e:
            checks.append(Check("state.json valid JSON", "state").fail(str(e)))
            return checks

        # Portfolio positions
        c = Check("state.json has positions", "state")
        portfolio = state.get("portfolio", {})
        total_pos = portfolio.get("total_positions", 0)
        positions = state.get("positions", [])
        if total_pos > 0 and len(positions) > 0:
            c.passed(f"{total_pos} positions ({len(positions)} detailed)")
        elif total_pos == 0 and portfolio.get("equity", 0) > 50000:
            c.fail(f"total_positions=0 but equity=${portfolio.get('equity', 0):,.0f} — daemon serialization bug")
        elif len(positions) == 0 and portfolio.get("equity", 0) > 50000:
            c.fail(f"positions array empty but equity=${portfolio.get('equity', 0):,.0f} — daemon bug")
        else:
            c.passed(f"{total_pos} positions")
        checks.append(c)

        # Signals
        c = Check("state.json has signals", "state")
        sigs = state.get("aggregated_signals", {})
        convergences = len(sigs.get("convergences", []))
        top_signals = len(sigs.get("top_signals", []))
        if convergences == 0 and top_signals == 0:
            c.warn("No convergences or top signals in state")
        else:
            c.passed(f"{convergences} convergences, {top_signals} top signals")
        checks.append(c)

        # News
        c = Check("state.json has news", "state")
        news = state.get("news_events", [])
        urgency = state.get("news_urgency_alerts", [])
        if len(news) == 0 and len(urgency) == 0:
            c.warn("No news events in state")
        else:
            c.passed(f"{len(news)} news events, {len(urgency)} urgency alerts")
        checks.append(c)

    return checks


# ===== DATA PIPELINE CHECKS =====

def check_data_pipeline() -> list[Check]:
    checks = []

    sources = {
        "RSS news cache": RESULTS_DIR / "live" / "news_cache.json",
        "Finviz screens": RESULTS_DIR / "scraped_data" / "finviz" / "screens_latest.json",
        "Signal digest": RESULTS_DIR / "scheduler" / "signal_digest.json",
        "Market movers": RESULTS_DIR / "live" / "market_movers_latest.json",
        "Social WSB": RESULTS_DIR / "social" / "wsb.db",
    }

    for name, path in sources.items():
        c = Check(f"Data: {name}", "data")
        if path.exists():
            age_hours = (time.time() - path.stat().st_mtime) / 3600
            size_kb = path.stat().st_size / 1024
            if age_hours > 24 and datetime.now().weekday() < 5:
                c.warn(f"{age_hours:.1f}h old, {size_kb:.0f}KB")
            else:
                c.passed(f"{age_hours:.1f}h old, {size_kb:.0f}KB")
        else:
            c.warn(f"File missing: {path}")
        checks.append(c)

    return checks


# ===== JOB SLO CHECKS =====
#
# One row per scheduled job: (job name, artifact path or glob, window, max_age_hours, critical).
# Prefer real output artifacts over `>>`-redirect logs where they exist —
# a log proves the cron fired, an artifact proves it succeeded.
#
# window semantics:
#   intraday — evaluated only 10:00-17:00 on weekdays (jobs that run all day)
#   daily    — evaluated any time on weekdays; Monday gets +48h weekend grace
#   weekly   — evaluated any time; max_age should already span the week
#
# A MISSING artifact is a warn (job may never have run on this install);
# a STALE artifact on a critical row is a fail — that's the "silently dead
# for a month" class this table exists to catch.

JOB_SLOS = [
    # (job, path-or-glob, window, max_age_hours, critical)
    ("collect_all_data",  "logs/collection.log",                      "intraday", 2.0,  True),
    ("signal_digest",     "scheduler/signal_digest.json",             "intraday", 2.0,  True),
    ("build_target",      "logs/build_target.log",                    "daily",    26,   True),
    ("reconcile",         "logs/reconcile.log",                       "daily",    26,   True),
    ("auto_execute",      "logs/auto_execute.log",                    "daily",    26,   True),
    ("prediction_scorer", "logs/prediction_scorer.log",               "daily",    26,   True),
    ("opinion_scorer",    "intelligence/opinion_calibration.json",    "daily",    30,   True),
    ("belief_update",     "intelligence/calibration.json",            "daily",    30,   True),
    ("thesis_maintenance","logs/thesis_maintenance.jsonl",            "daily",    26,   True),
    ("realized_pnl",      "logs/realized_pnl.log",                    "daily",    26,   True),
    ("cross_reference",   "live/cross_reference_alerts.json",         "daily",    26,   True),
    ("bug_monitor",       "logs/bug_monitor.log",                     "daily",    30,   True),
    ("corporate_actions", "live/corporate_actions.json",              "daily",    26,   True),
    ("morning_briefing",  "briefings/briefing_*.json",                "daily",    30,   False),
    ("eod_review",        "eod_reviews/review_*.json",                "daily",    30,   False),
    ("stress_test",       "risk_reports/stress_test_latest.json",     "weekly",   216,  True),
    ("meta_observer",     "parallel/meta_report_latest.json",         "weekly",   216,  True),
    ("benchmark",         "benchmarks/benchmark_latest.json",         "weekly",   216,  True),
    ("log_cleanup",       "logs/log_cleanup.log",                     "weekly",   216,  False),
]


def _newest_mtime(path_or_glob: str) -> float | None:
    """Newest mtime for a path (or glob) relative to RESULTS_DIR; None if nothing exists."""
    base = RESULTS_DIR
    if "*" in path_or_glob:
        matches = list(base.glob(path_or_glob))
        if not matches:
            return None
        return max(p.stat().st_mtime for p in matches)
    p = base / path_or_glob
    return p.stat().st_mtime if p.exists() else None


def check_job_slos() -> list[Check]:
    """Assert every scheduled job's artifact is fresh — catches silently-dead crons."""
    checks = []
    now = datetime.now()
    is_weekday = now.weekday() < 5
    monday_grace = 48 if now.weekday() == 0 else 0

    for job, artifact, window, max_age, critical in JOB_SLOS:
        c = Check(f"SLO: {job}", "slo")

        if window == "intraday" and not (is_weekday and 10 <= now.hour < 17):
            continue  # outside evaluation window — no signal either way
        if window == "daily" and not is_weekday:
            continue

        mtime = _newest_mtime(artifact)
        if mtime is None:
            c.warn(f"{artifact} missing — job may never have run")
            checks.append(c)
            continue

        age_h = (time.time() - mtime) / 3600
        limit = max_age + (monday_grace if window == "daily" else 0)
        if age_h <= limit:
            c.passed(f"{age_h:.1f}h old (limit {limit:.0f}h)")
        elif critical:
            c.fail(f"{artifact} is {age_h:.1f}h old (limit {limit:.0f}h) — job dead?")
        else:
            c.warn(f"{artifact} is {age_h:.1f}h old (limit {limit:.0f}h)")
        checks.append(c)

    return checks


# ===== PREDICTION LOOP CHECKS =====

def check_predictions() -> list[Check]:
    checks = []

    if not DB_FILE.exists():
        return [Check("Database exists", "predictions").fail("athena.db not found")]

    import sqlite3
    conn = sqlite3.connect(str(DB_FILE))

    c = Check("Prediction scoring active", "predictions")
    try:
        total = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        open_count = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='open'").fetchone()[0]
        hit = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='hit'").fetchone()[0]
        miss = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='miss'").fetchone()[0]
        scored = hit + miss
        if scored == 0:
            c.warn(f"{total} predictions, 0 scored — scoring loop not producing results")
        else:
            rate = hit / scored * 100
            c.passed(f"{total} total, {scored} scored ({rate:.0f}% hit), {open_count} open")
    except Exception as e:
        c.fail(f"Query failed: {e}")
    checks.append(c)

    # Short-horizon predictions
    c = Check("Short-horizon predictions (3-day)", "predictions")
    try:
        short = conn.execute(
            "SELECT COUNT(*) FROM predictions WHERE timeframe_days <= 3"
        ).fetchone()[0]
        if short == 0:
            c.warn("No 3-day predictions — fast feedback loop not active")
        else:
            c.passed(f"{short} short-horizon predictions exist")
    except Exception as e:
        c.fail(str(e))
    checks.append(c)

    # Predictions resolving soon
    c = Check("Predictions resolving this week", "predictions")
    try:
        week_end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        soon = conn.execute(
            f"SELECT COUNT(*) FROM predictions WHERE status='open' AND resolve_by <= '{week_end}'"
        ).fetchone()[0]
        if soon == 0:
            c.warn("No predictions resolving this week — belief updater has no new data")
        else:
            c.passed(f"{soon} predictions will resolve within 7 days")
    except Exception as e:
        c.fail(str(e))
    checks.append(c)

    conn.close()
    return checks


# ===== STRATEGIC CONTEXT CHECKS =====

def check_strategic_context() -> list[Check]:
    checks = []

    ctx_file = SCHEDULER_DIR / "strategic_context.json"
    c = Check("Strategic context file", "strategy")
    if not ctx_file.exists():
        c.fail("strategic_context.json missing")
        checks.append(c)
        return checks

    try:
        with open(ctx_file) as f:
            ctx = json.load(f)
    except Exception as e:
        c.fail(f"Can't parse: {e}")
        checks.append(c)
        return checks

    age_hours = (time.time() - ctx_file.stat().st_mtime) / 3600
    c.passed(f"{age_hours:.1f}h old")
    checks.append(c)

    # Hypotheses
    c = Check("Research hypotheses", "strategy")
    hypotheses = ctx.get("research_hypotheses", [])
    untested = [h for h in hypotheses if h.get("status") == "untested"]
    if len(hypotheses) == 0:
        c.warn("No hypotheses in strategic context — ideation pipeline inactive")
    else:
        c.passed(f"{len(hypotheses)} hypotheses ({len(untested)} untested)")
    checks.append(c)

    # Patterns
    c = Check("Developing patterns", "strategy")
    patterns = ctx.get("developing_patterns", [])
    if len(patterns) == 0:
        c.warn("No developing patterns tracked")
    else:
        c.passed(f"{len(patterns)} patterns tracked")
    checks.append(c)

    # Catalysts
    c = Check("Upcoming catalysts", "strategy")
    catalysts = ctx.get("upcoming_catalysts", [])
    future = [
        cat for cat in catalysts
        if cat.get("date", "9999") >= datetime.now().strftime("%Y-%m-%d")
    ]
    if len(future) == 0:
        c.warn("No future catalysts tracked")
    else:
        c.passed(f"{len(future)} upcoming catalysts")
    checks.append(c)

    return checks


# ===== CROSS-SESSION FLOW CHECKS =====

def check_cross_session_flow() -> list[Check]:
    checks = []

    c = Check("Cross-session artifact flow", "flow")
    try:
        from src.swarm.artifact_log import check_flow_health

        health = check_flow_health()
        active = health["active"]
        total = health["total"]
        status = health["health"]

        if status == "healthy":
            c.passed(f"{active}/{total} flows active")
        elif status == "degraded":
            missing = [k for k, v in health["flows"].items() if not v]
            c.warn(f"{active}/{total} flows active — missing: {', '.join(missing)}")
        else:
            c.fail(f"No cross-session flows detected in last 24h")
    except Exception as e:
        c.warn(f"Can't check flow health: {e}")
    checks.append(c)

    # Check individual artifact freshness
    artifacts = {
        "EOD review": RESULTS_DIR / "reviews",
        "Morning briefing": RESULTS_DIR / "briefings",
        "Signal digest": SCHEDULER_DIR / "signal_digest.json",
        "Strategic context": SCHEDULER_DIR / "strategic_context.json",
        "Situation board": SCHEDULER_DIR / "situation_board.json",
    }

    for name, path in artifacts.items():
        c = Check(f"Artifact: {name}", "flow")
        if path.is_dir():
            # Find most recent file in directory
            files = sorted(path.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            if not files:
                files = sorted(path.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                age_h = (time.time() - files[0].stat().st_mtime) / 3600
                if age_h > 48 and datetime.now().weekday() < 5:
                    c.warn(f"Latest is {age_h:.0f}h old: {files[0].name}")
                else:
                    c.passed(f"{age_h:.1f}h old: {files[0].name}")
            else:
                c.warn(f"No files in {path}")
        elif path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            if age_h > 24 and datetime.now().weekday() < 5:
                c.warn(f"{age_h:.1f}h old")
            else:
                c.passed(f"{age_h:.1f}h old")
        else:
            c.warn(f"Missing: {path}")
        checks.append(c)

    return checks


# ===== SESSION SCHEDULING CHECKS =====

def check_sessions() -> list[Check]:
    checks = []
    today = datetime.now().strftime("%Y%m%d")

    expected_sessions = {
        "morning-briefing": {"after_hour": 6, "critical": True},
        "trade-decision": {"after_hour": 10, "critical": True},
        "internal-review": {"after_hour": 12, "critical": False},
        "signal-scan": {"after_hour": 10, "critical": False},
        "eod-review": {"after_hour": 16, "critical": True},
        "evening-research": {"after_hour": 17, "critical": False},
    }

    now_hour = datetime.now().hour

    for session_type, config in expected_sessions.items():
        c = Check(f"Session: {session_type}", "sessions")
        log_file = LOG_DIR / f"claude_{session_type}_{today}.log"

        if now_hour < config["after_hour"]:
            c.passed("Not due yet")
        elif log_file.exists():
            size = log_file.stat().st_size
            if size < 100:
                c.warn(f"Log exists but tiny ({size} bytes) — session may have failed")
            else:
                c.passed(f"Ran today ({size} bytes)")
        else:
            if config["critical"]:
                c.fail(f"Should have run by {config['after_hour']}:00 but no log found")
            else:
                c.warn(f"Expected after {config['after_hour']}:00 but no log found")
        checks.append(c)

    return checks


# ===== DATABASE CHECKS =====

def check_database() -> list[Check]:
    checks = []

    c = Check("Database file", "database")
    if not DB_FILE.exists():
        c.fail("athena.db not found")
        checks.append(c)
        return checks

    c.passed(f"{DB_FILE.stat().st_size / (1024*1024):.1f}MB")
    checks.append(c)

    import sqlite3
    conn = sqlite3.connect(str(DB_FILE))

    tables = {
        "decisions": 5,
        "predictions": 5,
        "theses": 5,
        "process_events": 10,
        "documents": 5,
    }

    for table, min_rows in tables.items():
        c = Check(f"Table: {table}", "database")
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count < min_rows:
                c.warn(f"{count} rows (expected >= {min_rows})")
            else:
                c.passed(f"{count} rows")
        except Exception as e:
            c.fail(f"Query failed: {e}")
        checks.append(c)

    conn.close()
    return checks


# ===== CREDENTIAL CHECKS =====

def check_credentials(quick: bool = False) -> list[Check]:
    checks = []

    creds_path = PROJECT_DIR / "config" / "credentials.yaml"
    c = Check("Credentials file", "credentials")
    if not creds_path.exists():
        c.fail("config/credentials.yaml missing")
        checks.append(c)
        return checks

    try:
        import yaml
        with open(creds_path) as f:
            creds = yaml.safe_load(f)

        alpaca = creds.get("alpaca", {})
        if alpaca.get("api_key") and alpaca.get("secret_key"):
            c.passed("Alpaca credentials present")
        else:
            c.fail("Alpaca credentials missing or empty")
    except Exception as e:
        c.fail(f"Can't read credentials: {e}")
    checks.append(c)

    # Test Alpaca connection (skip in quick mode)
    if not quick:
        c = Check("Alpaca API connection", "credentials")
        try:
            from alpaca.trading.client import TradingClient
            client = TradingClient(alpaca["api_key"], alpaca["secret_key"], paper=True)
            account = client.get_account()
            c.passed(f"Connected (equity=${float(account.equity):,.0f}, {len(client.get_all_positions())} positions)")
        except Exception as e:
            c.fail(f"Alpaca connection failed: {e}")
        checks.append(c)

    return checks


# ===== AUTO-FIX ACTIONS =====

def auto_fix(results: list[Check]) -> list[Check]:
    """Apply fixes for known issues."""
    fixes = []

    # Fix 1: Reinstall cron if missing entries
    cron_fails = [c for c in results if c.category == "cron" and c.status in ("fail", "warn")]
    if cron_fails:
        fixes.extend(fix_cron(True))

    # Fix 2: Restart sentinel if dead during market hours
    sentinel_dead = any(
        c.name == "Sentinel process" and c.status == "fail"
        for c in results
    )
    if sentinel_dead:
        c = Check("Restart sentinel", "sentinel")
        try:
            r = subprocess.run(
                [str(PROJECT_DIR / "scripts" / "athena_scheduler.sh"), "sentinel-start"],
                capture_output=True, text=True, cwd=str(PROJECT_DIR),
            )
            if r.returncode == 0:
                c.fixed("Sentinel restarted", "athena_scheduler.sh sentinel-start")
            else:
                c.fail(f"Restart failed: {r.stderr[:200]}")
        except Exception as e:
            c.fail(str(e))
        fixes.append(c)

    # Fix 3: Clean stale operator lock
    stale_op = any(
        c.name == "Operator session" and "stale lock" in c.message
        for c in results
    )
    if stale_op:
        c = Check("Clean stale operator lock", "operator")
        lock = SCHEDULER_DIR / "locks" / "operator.lock"
        lock.unlink(missing_ok=True)
        c.fixed("Removed stale operator lock", "rm operator.lock")
        fixes.append(c)

    # Fix 4: Restart operator if dead during market hours
    op_dead = any(
        c.name == "Operator session" and c.status == "fail"
        for c in results
    )
    now = datetime.now()
    if op_dead and now.weekday() < 5 and 8 <= now.hour < 16:
        c = Check("Restart operator", "operator")
        try:
            r = subprocess.run(
                [str(PROJECT_DIR / "scripts" / "athena_scheduler.sh"), "operator-start"],
                capture_output=True, text=True, cwd=str(PROJECT_DIR),
            )
            if r.returncode == 0:
                c.fixed("Operator restarted", "athena_scheduler.sh operator-start")
            else:
                c.fail(f"Restart failed: {r.stderr[:200]}")
        except Exception as e:
            c.fail(str(e))
        fixes.append(c)

    # Fix 5: Trigger daemon update if positions are 0 but equity is high
    pos_missing = any(
        c.name == "state.json has positions" and c.status == "fail"
        for c in results
    )
    if pos_missing:
        c = Check("Trigger daemon update", "state")
        try:
            r = subprocess.run(
                ["python3", "-c",
                 "import asyncio; from src.synthesis.daemon import LiveDaemon; asyncio.run(LiveDaemon().update_now())"],
                capture_output=True, text=True,
                cwd=str(PROJECT_DIR),
                env={**os.environ, "PYTHONPATH": str(PROJECT_DIR)},
                timeout=60,
            )
            if r.returncode == 0:
                c.fixed("Daemon update triggered", "LiveDaemon().update_now()")
            else:
                c.fail(f"Daemon update failed: {r.stderr[:200]}")
        except Exception as e:
            c.fail(str(e))
        fixes.append(c)

    # Fix 6: Kill any stale oneshot locks (not operator)
    for lock_file in (SCHEDULER_DIR / "locks").glob("*.lock"):
        if lock_file.stem == "operator":
            continue
        age_min = (time.time() - lock_file.stat().st_mtime) / 60
        if age_min > 20:  # Oneshot should never take > 20 min
            try:
                pid = int(lock_file.read_text().strip())
                if not _pid_alive(pid):
                    c = Check(f"Clean stale {lock_file.stem} lock", "sessions")
                    lock_file.unlink(missing_ok=True)
                    c.fixed(f"Removed stale lock ({age_min:.0f}min old)", f"rm {lock_file.name}")
                    fixes.append(c)
            except (ValueError, OSError):
                lock_file.unlink(missing_ok=True)

    # Fix 7: Respawn tmux session if missing
    tmux_missing = subprocess.run(
        ["tmux", "has-session", "-t", "athena-auto"],
        capture_output=True,
    ).returncode != 0
    if tmux_missing and now.weekday() < 5 and 5 <= now.hour <= 17:
        c = Check("Recreate tmux session", "sentinel")
        try:
            r = subprocess.run(
                [str(PROJECT_DIR / "scripts" / "athena_scheduler.sh"), "setup"],
                capture_output=True, text=True, cwd=str(PROJECT_DIR),
            )
            if r.returncode == 0:
                c.fixed("tmux session recreated", "athena_scheduler.sh setup")
            else:
                c.fail(f"Setup failed: {r.stderr[:200]}")
        except Exception as e:
            c.fail(str(e))
        fixes.append(c)

    return fixes


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def spawn_claude_fixer(failures: list[Check]) -> Check | None:
    """Spawn a short Sonnet session to diagnose and fix critical failures.

    Only spawns if:
    - There are critical failures (not just warnings)
    - During market hours
    - No fixer session already running
    - Cooldown: max once per hour
    """
    now = datetime.now()
    if now.weekday() >= 5 or not (6 <= now.hour <= 17):
        return None

    # Check cooldown
    cooldown_file = SCHEDULER_DIR / "readiness_fixer_last.txt"
    if cooldown_file.exists():
        try:
            last_run = datetime.fromisoformat(cooldown_file.read_text().strip())
            if (now - last_run).total_seconds() < 3600:
                return None  # Within cooldown
        except (ValueError, OSError):
            pass

    # Only for critical failures that auto-fix couldn't handle
    critical = [f for f in failures if f.status == "fail"]
    if not critical:
        return None

    # Write cooldown marker
    cooldown_file.parent.mkdir(parents=True, exist_ok=True)
    cooldown_file.write_text(now.isoformat())

    # Build diagnostic prompt
    failure_desc = "; ".join(f"{c.name}: {c.message}" for c in critical[:5])
    prompt = (
        f"READINESS CHECK FAILURES detected at {now.strftime('%H:%M')}. "
        f"Failures: {failure_desc}. "
        f"Read scripts/readiness_check.py and the relevant source files. "
        f"Diagnose root cause and apply minimal fixes. "
        f"Then run: PYTHONPATH=. python3 scripts/readiness_check.py --quick "
        f"to verify the fix worked."
    )

    c = Check("Spawn Claude fixer session", "auto-heal")
    try:
        # Use the scheduler to launch an analyst-type session
        r = subprocess.run(
            [str(PROJECT_DIR / "scripts" / "athena_scheduler.sh"), "oneshot", "analyst"],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
        )
        if r.returncode == 0:
            c.fixed(
                f"Fixer session spawned for {len(critical)} failures",
                "athena_scheduler.sh oneshot analyst"
            )
        else:
            c.fail(f"Fixer spawn failed: {r.stderr[:200]}")
    except Exception as e:
        c.fail(str(e))

    return c


# ===== MAIN =====

def run_checks(category: str | None = None, quick: bool = False) -> list[Check]:
    all_checks = []

    check_fns = [
        ("cron", check_cron_installed),
        ("sentinel", check_sentinel),
        ("operator", check_operator),
        ("state", check_state),
        ("data", check_data_pipeline),
        ("slo", check_job_slos),
        ("flow", check_cross_session_flow),
        ("predictions", check_predictions),
        ("strategy", check_strategic_context),
        ("sessions", check_sessions),
        ("database", check_database),
    ]

    for cat, fn in check_fns:
        if category and cat != category:
            continue
        all_checks.extend(fn())

    # Credentials (may involve network)
    if not category or category == "credentials":
        all_checks.extend(check_credentials(quick=quick))

    return all_checks


def print_results(results: list[Check]):
    current_cat = ""
    pass_count = sum(1 for c in results if c.status == "pass")
    warn_count = sum(1 for c in results if c.status == "warn")
    fail_count = sum(1 for c in results if c.status == "fail")
    fix_count = sum(1 for c in results if c.status == "fixed")

    print(f"\n{'='*70}")
    print(f"  ATHENA READINESS CHECK — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}\n")

    for c in results:
        if c.category != current_cat:
            current_cat = c.category
            print(f"\n  --- {current_cat.upper()} ---")
        status_icon = icon(c.status)
        line = f"  {status_icon} {c.name}: {c.message}"
        if c.fix_applied:
            line += f" (fix: {c.fix_applied})"
        print(line)

    print(f"\n{'='*70}")
    print(f"  SUMMARY: {pass_count} passed, {warn_count} warnings, {fail_count} failures, {fix_count} fixed")
    overall = "READY" if fail_count == 0 else "NOT READY"
    print(f"  STATUS: {overall}")
    print(f"{'='*70}\n")

    # Detailed fix recommendations for failures
    failures = [c for c in results if c.status == "fail"]
    warnings = [c for c in results if c.status == "warn"]
    if failures:
        print("  RECOMMENDED FIXES:")
        for c in failures:
            print(f"    - {c.name}: {c.message}")
        print()

    if warnings:
        print("  WARNINGS TO INVESTIGATE:")
        for c in warnings[:5]:
            print(f"    - {c.name}: {c.message}")
        if len(warnings) > 5:
            print(f"    ... and {len(warnings) - 5} more")
        print()

    return fail_count


def main():
    parser = argparse.ArgumentParser(description="Athena System Readiness Check")
    parser.add_argument("--fix", action="store_true", help="Auto-fix known issues")
    parser.add_argument("--spawn-fixer", action="store_true", help="Spawn Claude session for unfixable failures")
    parser.add_argument("--category", type=str, help="Check specific category only")
    parser.add_argument("--quick", action="store_true", help="Skip network checks")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--alert", action="store_true",
                        help="Send a critical notification (Telegram or ALERTS.md) if failures remain")
    args = parser.parse_args()

    results = run_checks(category=args.category, quick=args.quick)

    if args.fix:
        fixes = auto_fix(results)
        results.extend(fixes)

        # After auto-fix, optionally spawn Claude for remaining failures
        if args.spawn_fixer:
            remaining_failures = [c for c in results if c.status == "fail"]
            if remaining_failures:
                fixer_result = spawn_claude_fixer(remaining_failures)
                if fixer_result:
                    results.append(fixer_result)

    if args.alert:
        failures = [c for c in results if c.status == "fail"]
        if failures:
            try:
                from src.alerts.notify import notify_critical

                body = "\n".join(f"- [{c.category}] {c.name}: {c.message}" for c in failures[:15])
                notify_critical(
                    f"Readiness: {len(failures)} critical failure(s)",
                    body,
                    key="readiness_failures",
                )
            except Exception as e:
                print(f"[alert] notify failed: {e}", file=sys.stderr)

    if args.json:
        output = {
            "timestamp": datetime.now().isoformat(),
            "checks": [
                {
                    "name": c.name,
                    "category": c.category,
                    "status": c.status,
                    "message": c.message,
                    "fix_applied": c.fix_applied,
                }
                for c in results
            ],
            "summary": {
                "pass": sum(1 for c in results if c.status == "pass"),
                "warn": sum(1 for c in results if c.status == "warn"),
                "fail": sum(1 for c in results if c.status == "fail"),
                "fixed": sum(1 for c in results if c.status == "fixed"),
            },
        }
        print(json.dumps(output, indent=2))
        return 0 if output["summary"]["fail"] == 0 else 1

    fail_count = print_results(results)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
