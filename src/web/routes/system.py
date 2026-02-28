"""System routes — health, service status, cron status, database stats."""

import os
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request

from src.web.services import system_service

router = APIRouter()


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def _get_cron_status() -> list[dict]:
    """Parse installed cron jobs and their last-run status."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []

        jobs = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Only include our cron jobs
            if "QUANT_SUITE_CRON" not in line and "quant_suite" not in line.lower():
                continue
            jobs.append({
                "schedule": " ".join(line.split()[:5]),
                "command": " ".join(line.split()[5:]),
                "raw": line,
            })
        return jobs
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _get_db_stats() -> dict:
    """Get basic database statistics."""
    from src.db.database import get_db
    from src.db.models import (
        Company, Sector, ThesisRecord, DecisionRecord,
        LearningRecord, SignalProvenanceRecord, AgentRun,
        ProcessEvent, LLMInteraction, AutonomyCheck,
    )

    stats = {}
    try:
        with get_db() as session:
            stats["companies"] = session.query(Company).count()
            stats["sectors"] = session.query(Sector).count()
            stats["theses"] = session.query(ThesisRecord).count()
            stats["decisions"] = session.query(DecisionRecord).count()
            stats["learnings"] = session.query(LearningRecord).count()
            stats["signals"] = session.query(SignalProvenanceRecord).count()
            stats["agent_runs"] = session.query(AgentRun).count()
            stats["process_events"] = session.query(ProcessEvent).count()
            stats["llm_interactions"] = session.query(LLMInteraction).count()
            stats["autonomy_checks"] = session.query(AutonomyCheck).count()
    except Exception as exc:
        stats["error"] = str(exc)

    # Database file size
    db_path = _results_dir() / "athena.db"
    if db_path.exists():
        size_bytes = db_path.stat().st_size
        if size_bytes < 1024 * 1024:
            stats["db_size"] = f"{size_bytes / 1024:.1f} KB"
        else:
            stats["db_size"] = f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        stats["db_size"] = "N/A"

    return stats


def _get_service_status() -> list[dict]:
    """Check status of background services."""
    services = []

    # Check if LiveDaemon PID file exists
    pid_file = _results_dir() / "live" / "daemon.pid"
    daemon_running = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            daemon_running = True
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    services.append({
        "name": "LiveDaemon",
        "description": "State update daemon (5 min cycle)",
        "status": "running" if daemon_running else "stopped",
    })

    # Check for news daemon
    news_pid = _results_dir() / "live" / "news_daemon.pid"
    news_running = False
    if news_pid.exists():
        try:
            pid = int(news_pid.read_text().strip())
            os.kill(pid, 0)
            news_running = True
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    services.append({
        "name": "NewsDaemon",
        "description": "RSS/news collection (30 min cycle)",
        "status": "running" if news_running else "stopped",
    })

    # Check for collection daemon
    coll_pid = _results_dir() / "live" / "collection_daemon.pid"
    coll_running = False
    if coll_pid.exists():
        try:
            pid = int(coll_pid.read_text().strip())
            os.kill(pid, 0)
            coll_running = True
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    services.append({
        "name": "CollectionDaemon",
        "description": "Alt-data collection (variable schedule)",
        "status": "running" if coll_running else "stopped",
    })

    return services


@router.get("/")
async def system_dashboard(request: Request):
    """System health dashboard: services, cron, DB stats."""
    templates = request.app.state.templates

    services = _get_service_status()
    cron_jobs = _get_cron_status()
    db_stats = _get_db_stats()
    autonomy_data = system_service.get_autonomy_status()
    autonomy = autonomy_data.get("recent_checks", [None])[0] if autonomy_data.get("recent_checks") else None

    # Disk usage for results directory
    results = _results_dir()
    disk_usage = {}
    if results.exists():
        try:
            result = subprocess.run(
                ["du", "-sh", str(results)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                disk_usage["total"] = result.stdout.split()[0]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            disk_usage["total"] = "N/A"

    return templates.TemplateResponse(
        request,
        "system/index.html",
        {
            "active_page": "system",
            "services": services,
            "cron_jobs": cron_jobs,
            "db_stats": db_stats,
            "autonomy": autonomy,
            "disk_usage": disk_usage,
            "now": datetime.utcnow().isoformat(),
        },
    )
