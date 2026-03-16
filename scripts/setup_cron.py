#!/usr/bin/env python3
"""Setup cron jobs for automated trading infrastructure.

This script configures all scheduled tasks:
1. Research prep (6:00 AM ET weekdays)
2. News collection (every 4 hours)
3. Congressional data collection (6:00 AM ET daily)
4. Live daemon health check (every 5 minutes)
5. EOD data snapshot (5:00 PM ET weekdays)

Usage:
    PYTHONPATH=. python scripts/setup_cron.py --install
    PYTHONPATH=. python scripts/setup_cron.py --show
    PYTHONPATH=. python scripts/setup_cron.py --remove
"""

import argparse
import subprocess
import os
from pathlib import Path

# Base paths
PROJECT_DIR = Path(__file__).parent.parent.absolute()

import os
RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))
LOGS_DIR = RESULTS_DIR / "logs"

# Cron job definitions (all times in system timezone, adjust for ET if needed)
CRON_JOBS = [
    {
        "name": "research_prep",
        "schedule": "0 6 * * 1-5",  # 6:00 AM weekdays
        "command": f"cd {PROJECT_DIR} && PYTHONPATH=. python3 scripts/research_prep.py",
        "log": "research_prep.log",
        "description": "Pre-market research preparation",
    },
    {
        "name": "news_collect",
        "schedule": "0 */4 * * *",  # Every 4 hours
        "command": f"cd {PROJECT_DIR} && PYTHONPATH=. python3 scripts/cron_news_collect.py",
        "log": "news_collect.log",
        "description": "News and events collection",
    },
    {
        "name": "congressional_collect",
        "schedule": "30 6 * * *",  # 6:30 AM daily
        "command": f"cd {PROJECT_DIR} && PYTHONPATH=. python3 scripts/cron_congressional_collect.py",
        "log": "congressional.log",
        "description": "Congressional trades collection",
    },
    {
        "name": "insider_collect",
        "schedule": "0 7 * * *",  # 7:00 AM daily
        "command": f"cd {PROJECT_DIR} && PYTHONPATH=. python3 scripts/cron_insider_collect.py",
        "log": "insider_collect.log",
        "description": "Insider trading data collection",
    },
    {
        "name": "live_daemon_check",
        "schedule": "*/5 * * * 1-5",  # Every 5 min weekdays
        "command": f"cd {PROJECT_DIR} && PYTHONPATH=. python3 -c \"from src.synthesis.daemon import LiveDaemon; import asyncio; asyncio.run(LiveDaemon().update_now())\"",
        "log": "daemon.log",
        "description": "Live daemon state update",
    },
    {
        "name": "eod_snapshot",
        "schedule": "0 17 * * 1-5",  # 5:00 PM weekdays
        "command": f"cd {PROJECT_DIR} && PYTHONPATH=. python3 scripts/eod_snapshot.py",
        "log": "eod_snapshot.log",
        "description": "End-of-day data snapshot",
    },
    {
        "name": "concentration_check",
        "schedule": "*/15 9-16 * * 1-5",  # Every 15 min during market hours
        "command": f"cd {PROJECT_DIR} && PYTHONPATH=. python3 scripts/cron_concentration_check.py",
        "log": "concentration_check.log",
        "description": "Portfolio concentration limit monitoring",
    },
]


def get_crontab_marker():
    """Return marker for identifying our cron jobs."""
    return "# QUANT_SUITE_CRON"


def format_cron_line(job: dict) -> str:
    """Format a cron job as a crontab line."""
    log_path = LOGS_DIR / job["log"]
    return (
        f"{job['schedule']} {job['command']} >> {log_path} 2>&1 "
        f"{get_crontab_marker()} {job['name']}"
    )


def get_current_crontab() -> str:
    """Get current crontab contents."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        return result.stdout
    except Exception:
        return ""


def install_cron_jobs():
    """Install all cron jobs."""
    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Get current crontab
    current = get_current_crontab()

    # Remove existing quant_suite jobs
    lines = [
        line for line in current.split("\n")
        if get_crontab_marker() not in line and line.strip()
    ]

    # Add header
    lines.append("")
    lines.append(f"{get_crontab_marker()} === START ===")

    # Add new jobs
    for job in CRON_JOBS:
        lines.append(f"# {job['description']}")
        lines.append(format_cron_line(job))
        lines.append("")

    lines.append(f"{get_crontab_marker()} === END ===")
    lines.append("")

    # Install new crontab
    new_crontab = "\n".join(lines)

    process = subprocess.Popen(
        ["crontab", "-"],
        stdin=subprocess.PIPE,
        text=True,
    )
    process.communicate(input=new_crontab)

    if process.returncode == 0:
        print("Cron jobs installed successfully!")
        print()
        show_cron_jobs()
    else:
        print("Failed to install cron jobs")
        return 1

    return 0


def show_cron_jobs():
    """Show configured cron jobs."""
    print("=" * 60)
    print("QUANT SUITE SCHEDULED JOBS")
    print("=" * 60)
    print()

    for job in CRON_JOBS:
        print(f"Job: {job['name']}")
        print(f"  Schedule: {job['schedule']}")
        print(f"  Description: {job['description']}")
        print(f"  Log: {LOGS_DIR / job['log']}")
        print()

    print("=" * 60)
    print("Current crontab:")
    print("=" * 60)
    current = get_current_crontab()
    quant_lines = [
        line for line in current.split("\n")
        if get_crontab_marker() in line or "QUANT_SUITE" in line
    ]
    if quant_lines:
        for line in quant_lines:
            print(line)
    else:
        print("No quant_suite cron jobs currently installed.")
    print()


def remove_cron_jobs():
    """Remove all quant_suite cron jobs."""
    current = get_current_crontab()

    # Remove quant_suite jobs
    lines = [
        line for line in current.split("\n")
        if get_crontab_marker() not in line
        and "# QUANT_SUITE" not in line
        and line.strip()
    ]

    # Install cleaned crontab
    new_crontab = "\n".join(lines) + "\n"

    process = subprocess.Popen(
        ["crontab", "-"],
        stdin=subprocess.PIPE,
        text=True,
    )
    process.communicate(input=new_crontab)

    if process.returncode == 0:
        print("Cron jobs removed successfully!")
    else:
        print("Failed to remove cron jobs")
        return 1

    return 0


def create_eod_snapshot_script():
    """Create the EOD snapshot script if it doesn't exist."""
    script_path = PROJECT_DIR / "scripts" / "eod_snapshot.py"
    if not script_path.exists():
        content = '''#!/usr/bin/env python3
"""End-of-day snapshot - Archive state and performance data."""

import json
import shutil
from datetime import datetime
from pathlib import Path

from src.core.paths import paths


def main():
    """Create EOD snapshot."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Create daily archive directory
    archive_dir = paths.base / "daily_archives" / today
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Copy state.json
    state_file = paths.live_state
    if state_file.exists():
        shutil.copy(state_file, archive_dir / "state.json")
        print(f"Archived state.json to {archive_dir}")

    # Create summary
    summary = {
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "archived_files": [],
    }

    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)

        portfolio = state.get("portfolio", {})
        summary["equity"] = portfolio.get("equity", 0)
        summary["cash"] = portfolio.get("cash", 0)
        summary["positions_count"] = len(state.get("positions", []))
        summary["theses_count"] = len(state.get("theses", []))
        summary["archived_files"].append("state.json")

    # Save summary
    with open(archive_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"EOD snapshot complete: {archive_dir}")


if __name__ == "__main__":
    main()
'''
        with open(script_path, "w") as f:
            f.write(content)
        os.chmod(script_path, 0o755)
        print(f"Created {script_path}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Setup cron jobs for quant_suite")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install", action="store_true", help="Install cron jobs")
    group.add_argument("--show", action="store_true", help="Show cron jobs")
    group.add_argument("--remove", action="store_true", help="Remove cron jobs")

    args = parser.parse_args()

    if args.install:
        create_eod_snapshot_script()
        return install_cron_jobs()
    elif args.show:
        show_cron_jobs()
        return 0
    elif args.remove:
        return remove_cron_jobs()


if __name__ == "__main__":
    exit(main())
