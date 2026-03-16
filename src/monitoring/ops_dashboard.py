"""
Operations Dashboard for Automated Trading Firm.

Monitors the SYSTEM itself, not just positions:
- Data feed health and quality
- Signal health (IC tracking)
- Research cycle status
- Agent activity
- Cron job status
- System alerts

This provides visibility into "the automated trading firm in action"
while Claude Code does orchestration and monitoring.
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.paths import paths

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class DataFeedStatus:
    """Status of a data feed/source."""
    name: str
    last_success: datetime | None
    last_error: datetime | None
    consecutive_failures: int
    total_today: int
    errors_today: int
    status: HealthStatus
    last_record_count: int = 0
    message: str = ""

    @property
    def success_rate(self) -> float:
        if self.total_today == 0:
            return 1.0
        return (self.total_today - self.errors_today) / self.total_today

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error.isoformat() if self.last_error else None,
            "consecutive_failures": self.consecutive_failures,
            "total_today": self.total_today,
            "errors_today": self.errors_today,
            "success_rate": self.success_rate,
            "status": self.status.value,
            "last_record_count": self.last_record_count,
            "message": self.message,
        }


@dataclass
class SignalHealthStatus:
    """Status of a signal/feature."""
    name: str
    ic_overall: float
    ic_30d: float
    ic_stability: float
    status: HealthStatus
    last_updated: datetime | None
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ic_overall": self.ic_overall,
            "ic_30d": self.ic_30d,
            "ic_stability": self.ic_stability,
            "status": self.status.value,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "recommendation": self.recommendation,
        }


@dataclass
class ResearchStatus:
    """Status of research activities."""
    active_experiments: int
    completed_today: int
    insights_discovered: int
    strategies_validated: int
    last_cycle: datetime | None
    current_cycle: str | None
    status: HealthStatus

    def to_dict(self) -> dict:
        return {
            "active_experiments": self.active_experiments,
            "completed_today": self.completed_today,
            "insights_discovered": self.insights_discovered,
            "strategies_validated": self.strategies_validated,
            "last_cycle": self.last_cycle.isoformat() if self.last_cycle else None,
            "current_cycle": self.current_cycle,
            "status": self.status.value,
        }


@dataclass
class CronJobStatus:
    """Status of a cron job."""
    name: str
    schedule: str
    last_run: datetime | None
    last_exit_code: int | None
    status: HealthStatus
    next_run: datetime | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "schedule": self.schedule,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_exit_code": self.last_exit_code,
            "status": self.status.value,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "message": self.message,
        }


@dataclass
class SystemHealth:
    """Overall system health status."""
    timestamp: datetime
    overall_status: HealthStatus
    data_feeds: list[DataFeedStatus]
    signals: list[SignalHealthStatus]
    research: ResearchStatus
    cron_jobs: list[CronJobStatus]
    alerts: list[dict]
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_status": self.overall_status.value,
            "data_feeds": [f.to_dict() for f in self.data_feeds],
            "signals": [s.to_dict() for s in self.signals],
            "research": self.research.to_dict(),
            "cron_jobs": [c.to_dict() for c in self.cron_jobs],
            "alerts": self.alerts,
            "summary": self.summary,
        }


class OperationsDashboard:
    """
    Unified operations dashboard for automated trading system.

    Integrates:
    - DataCollectionDaemon status
    - SignalHealthTracker metrics
    - SessionTracker research status
    - Cron job monitoring
    - System alerts
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or paths.base
        self.logs_dir = self.results_dir / "logs"
        self.live_dir = self.results_dir / "live"

        # IC thresholds (from signal_health.py)
        self.IC_HEALTHY = 0.02
        self.IC_DEGRADED = 0.01
        self.IC_BROKEN = 0.005

    async def get_system_health(self) -> SystemHealth:
        """Get comprehensive system health status."""
        data_feeds = await self._get_data_feed_status()
        signals = await self._get_signal_health()
        research = await self._get_research_status()
        cron_jobs = await self._get_cron_status()
        alerts = await self._get_active_alerts()

        # Compute summary
        summary = {
            "data_feeds_healthy": sum(1 for f in data_feeds if f.status == HealthStatus.HEALTHY),
            "data_feeds_degraded": sum(1 for f in data_feeds if f.status == HealthStatus.DEGRADED),
            "data_feeds_critical": sum(1 for f in data_feeds if f.status == HealthStatus.CRITICAL),
            "signals_healthy": sum(1 for s in signals if s.status == HealthStatus.HEALTHY),
            "signals_degraded": sum(1 for s in signals if s.status == HealthStatus.DEGRADED),
            "cron_healthy": sum(1 for c in cron_jobs if c.status == HealthStatus.HEALTHY),
            "cron_failed": sum(1 for c in cron_jobs if c.status == HealthStatus.CRITICAL),
            "active_alerts": len(alerts),
        }

        # Determine overall status
        if summary["data_feeds_critical"] > 2 or summary["cron_failed"] > 1:
            overall = HealthStatus.CRITICAL
        elif summary["data_feeds_degraded"] > 3 or summary["signals_degraded"] > 5:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return SystemHealth(
            timestamp=datetime.now(),
            overall_status=overall,
            data_feeds=data_feeds,
            signals=signals,
            research=research,
            cron_jobs=cron_jobs,
            alerts=alerts,
            summary=summary,
        )

    async def _get_data_feed_status(self) -> list[DataFeedStatus]:
        """Get status of all data feeds from collection daemon."""
        feeds = []

        # Try to load collection status from daemon
        status_file = self.live_dir / "collection_status.json"
        if status_file.exists():
            try:
                with open(status_file) as f:
                    data = json.load(f)
                    for source_name, source_data in data.get("sources", {}).items():
                        last_success = None
                        if source_data.get("last_success"):
                            try:
                                last_success = datetime.fromisoformat(source_data["last_success"])
                            except (ValueError, TypeError):
                                pass

                        last_error = None
                        if source_data.get("last_error"):
                            try:
                                last_error = datetime.fromisoformat(source_data["last_error"])
                            except (ValueError, TypeError):
                                pass

                        consecutive_failures = source_data.get("consecutive_failures", 0)

                        # Determine status
                        if consecutive_failures >= 3:
                            status = HealthStatus.CRITICAL
                        elif consecutive_failures >= 1:
                            status = HealthStatus.DEGRADED
                        elif last_success and (datetime.now() - last_success) > timedelta(hours=24):
                            status = HealthStatus.DEGRADED
                        else:
                            status = HealthStatus.HEALTHY

                        feeds.append(DataFeedStatus(
                            name=source_name,
                            last_success=last_success,
                            last_error=last_error,
                            consecutive_failures=consecutive_failures,
                            total_today=source_data.get("total_collections_today", 0),
                            errors_today=source_data.get("errors_today", 0),
                            status=status,
                            last_record_count=source_data.get("last_record_count", 0),
                        ))
            except Exception as e:
                logger.error(f"Error reading collection status: {e}")

        # Also check key data files directly
        key_feeds = [
            ("unified_state", self.live_dir / "state.json", timedelta(minutes=10)),
            ("congressional", self.results_dir / "cache" / "congressional_trades.json", timedelta(days=1)),
            ("insider", self.results_dir / "cache" / "insider_trades.json", timedelta(days=1)),
            ("news", self.results_dir / "cache" / "news.json", timedelta(hours=6)),
        ]

        existing_names = {f.name for f in feeds}
        for name, path, max_age in key_feeds:
            if name not in existing_names:
                if path.exists():
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                    age = datetime.now() - mtime
                    if age > max_age:
                        status = HealthStatus.DEGRADED
                    else:
                        status = HealthStatus.HEALTHY
                    feeds.append(DataFeedStatus(
                        name=name,
                        last_success=mtime,
                        last_error=None,
                        consecutive_failures=0,
                        total_today=1,
                        errors_today=0,
                        status=status,
                    ))
                else:
                    feeds.append(DataFeedStatus(
                        name=name,
                        last_success=None,
                        last_error=None,
                        consecutive_failures=0,
                        total_today=0,
                        errors_today=0,
                        status=HealthStatus.UNKNOWN,
                        message="File not found",
                    ))

        return feeds

    async def _get_signal_health(self) -> list[SignalHealthStatus]:
        """Get signal health from SignalHealthTracker."""
        signals = []

        # Try to load signal health from file
        health_file = self.live_dir / "signal_health.json"
        if health_file.exists():
            try:
                with open(health_file) as f:
                    data = json.load(f)
                    for signal_name, signal_data in data.get("signals", {}).items():
                        ic_overall = signal_data.get("ic_overall", 0)
                        ic_30d = signal_data.get("ic_30d", 0)
                        ic_stability = signal_data.get("ic_stability", 0)

                        # Determine status based on IC
                        if ic_overall >= self.IC_HEALTHY:
                            status = HealthStatus.HEALTHY
                        elif ic_overall >= self.IC_DEGRADED:
                            status = HealthStatus.DEGRADED
                        else:
                            status = HealthStatus.CRITICAL

                        last_updated = None
                        if signal_data.get("last_updated"):
                            try:
                                last_updated = datetime.fromisoformat(signal_data["last_updated"])
                            except (ValueError, TypeError):
                                pass

                        signals.append(SignalHealthStatus(
                            name=signal_name,
                            ic_overall=ic_overall,
                            ic_30d=ic_30d,
                            ic_stability=ic_stability,
                            status=status,
                            last_updated=last_updated,
                            recommendation=signal_data.get("recommendation", ""),
                        ))
            except Exception as e:
                logger.error(f"Error reading signal health: {e}")

        return signals

    async def _get_research_status(self) -> ResearchStatus:
        """Get research cycle status from session tracker."""
        # Try to load from session tracker
        tracker_file = self.results_dir / "research" / "session_tracker.json"

        if tracker_file.exists():
            try:
                with open(tracker_file) as f:
                    data = json.load(f)

                    # Count today's activity
                    today = datetime.now().date()
                    experiments = data.get("experiments", [])
                    completed_today = sum(
                        1 for e in experiments
                        if e.get("completed_at", "").startswith(today.isoformat())
                    )

                    insights = data.get("insights", [])
                    insights_today = sum(
                        1 for i in insights
                        if i.get("discovered_at", "").startswith(today.isoformat())
                    )

                    last_cycle = None
                    if experiments:
                        try:
                            last_cycle = datetime.fromisoformat(
                                experiments[-1].get("completed_at", "")
                            )
                        except (ValueError, TypeError):
                            pass

                    return ResearchStatus(
                        active_experiments=data.get("active_experiments", 0),
                        completed_today=completed_today,
                        insights_discovered=len(insights),
                        strategies_validated=data.get("strategies_validated", 0),
                        last_cycle=last_cycle,
                        current_cycle=data.get("current_cycle"),
                        status=HealthStatus.HEALTHY if completed_today > 0 else HealthStatus.DEGRADED,
                    )
            except Exception as e:
                logger.error(f"Error reading session tracker: {e}")

        return ResearchStatus(
            active_experiments=0,
            completed_today=0,
            insights_discovered=0,
            strategies_validated=0,
            last_cycle=None,
            current_cycle=None,
            status=HealthStatus.UNKNOWN,
        )

    async def _get_cron_status(self) -> list[CronJobStatus]:
        """Get status of cron jobs from logs."""
        cron_jobs = []

        # Define expected cron jobs and their log files
        expected_jobs = [
            ("unified_state", "daemon.log", "*/5 * * * 1-5"),
            ("congressional", "congressional.log", "30 6 * * *"),
            ("insider", "insider.log", "0 7 * * *"),
            ("news_collect", "news.log", "0 */4 * * *"),
            ("signpost_check", "signpost.log", "0 6-17 * * 1-5"),
            ("paper_review", "paper_trading.log", "30 17 * * 1-5"),
            ("concentration", "concentration.log", "0 */2 * * 1-5"),
        ]

        for job_name, log_file, schedule in expected_jobs:
            log_path = self.logs_dir / log_file

            last_run = None
            last_exit_code = None
            status = HealthStatus.UNKNOWN
            message = ""

            if log_path.exists():
                try:
                    mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
                    last_run = mtime

                    # Check log for errors (read last 10 lines)
                    with open(log_path, "rb") as f:
                        # Seek to end and read last chunk
                        f.seek(0, 2)
                        size = f.tell()
                        f.seek(max(0, size - 2000))
                        content = f.read().decode("utf-8", errors="ignore")

                    lines = content.strip().split("\n")[-10:]

                    # Check for error indicators
                    has_error = any(
                        "error" in line.lower() or "exception" in line.lower() or "failed" in line.lower()
                        for line in lines
                    )

                    if has_error:
                        status = HealthStatus.DEGRADED
                        last_exit_code = 1
                        message = "Errors in recent log"
                    else:
                        status = HealthStatus.HEALTHY
                        last_exit_code = 0

                except Exception as e:
                    message = str(e)
            else:
                message = "Log file not found"

            cron_jobs.append(CronJobStatus(
                name=job_name,
                schedule=schedule,
                last_run=last_run,
                last_exit_code=last_exit_code,
                status=status,
                message=message,
            ))

        return cron_jobs

    async def _get_active_alerts(self) -> list[dict]:
        """Get active system alerts."""
        alerts = []

        # Check for stale unified state
        state_file = self.live_dir / "state.json"
        if state_file.exists():
            mtime = datetime.fromtimestamp(state_file.stat().st_mtime)
            if datetime.now() - mtime > timedelta(minutes=15):
                alerts.append({
                    "level": "warning",
                    "title": "Stale Unified State",
                    "message": f"State file not updated in {int((datetime.now() - mtime).total_seconds() / 60)} minutes",
                    "timestamp": datetime.now().isoformat(),
                })
        else:
            alerts.append({
                "level": "critical",
                "title": "Missing Unified State",
                "message": "No state.json file found",
                "timestamp": datetime.now().isoformat(),
            })

        # Check for disk space
        try:
            statvfs = os.statvfs(str(self.results_dir))
            free_pct = statvfs.f_bavail / statvfs.f_blocks
            if free_pct < 0.10:
                alerts.append({
                    "level": "warning",
                    "title": "Low Disk Space",
                    "message": f"Only {free_pct:.1%} disk space remaining",
                    "timestamp": datetime.now().isoformat(),
                })
        except Exception:
            pass

        # Check alert log file
        alert_file = self.logs_dir / "alerts.log"
        if alert_file.exists():
            try:
                with open(alert_file) as f:
                    lines = f.readlines()[-20:]
                    for line in lines:
                        try:
                            alert = json.loads(line.strip())
                            # Only recent alerts (last hour)
                            alert_time = datetime.fromisoformat(alert.get("timestamp", ""))
                            if datetime.now() - alert_time < timedelta(hours=1):
                                alerts.append(alert)
                        except (json.JSONDecodeError, ValueError):
                            pass
            except Exception:
                pass

        return alerts

    def print_status(self, health: SystemHealth) -> None:
        """Print system health status to console."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            from rich.text import Text
            from rich.columns import Columns

            console = Console()

            # Status color mapping
            status_color_map = {
                HealthStatus.HEALTHY: "green",
                HealthStatus.DEGRADED: "yellow",
                HealthStatus.CRITICAL: "red",
                HealthStatus.UNKNOWN: "dim",
            }

            # Header
            header_color = status_color_map[health.overall_status]

            header = Text()
            header.append("OPERATIONS DASHBOARD ", style="bold cyan")
            header.append("| ", style="dim")
            header.append(f"{health.timestamp.strftime('%Y-%m-%d %H:%M:%S')} ", style="white")
            header.append("| Status: ", style="dim")
            header.append(health.overall_status.value.upper(), style=f"bold {header_color}")

            console.print(Panel(header, border_style="cyan"))

            # Summary
            summary = health.summary
            summary_text = Text()
            summary_text.append(f"Data Feeds: ", style="dim")
            summary_text.append(f"{summary['data_feeds_healthy']} healthy", style="green")
            summary_text.append(f", {summary['data_feeds_degraded']} degraded", style="yellow")
            summary_text.append(f", {summary['data_feeds_critical']} critical", style="red")
            summary_text.append(f" | Signals: ", style="dim")
            summary_text.append(f"{summary['signals_healthy']} healthy", style="green")
            summary_text.append(f", {summary['signals_degraded']} degraded", style="yellow")
            summary_text.append(f" | Cron: ", style="dim")
            summary_text.append(f"{summary['cron_healthy']} ok", style="green")
            summary_text.append(f", {summary['cron_failed']} failed", style="red")
            summary_text.append(f" | Alerts: ", style="dim")
            alert_style = "red" if summary['active_alerts'] > 0 else "green"
            summary_text.append(f"{summary['active_alerts']}", style=alert_style)

            console.print(Panel(summary_text, title="Summary", border_style="blue"))

            # Data Feeds Table
            if health.data_feeds:
                feed_table = Table(title="Data Feeds", expand=True)
                feed_table.add_column("Source", style="cyan", width=20)
                feed_table.add_column("Status", width=10)
                feed_table.add_column("Last Success", width=20)
                feed_table.add_column("Failures", justify="right", width=10)
                feed_table.add_column("Success Rate", justify="right", width=12)

                for feed in health.data_feeds:
                    status_style = status_color_map.get(feed.status, "white")
                    last_success = feed.last_success.strftime("%m/%d %H:%M") if feed.last_success else "Never"
                    feed_table.add_row(
                        feed.name,
                        f"[{status_style}]{feed.status.value}[/{status_style}]",
                        last_success,
                        str(feed.consecutive_failures),
                        f"{feed.success_rate:.0%}",
                    )

                console.print(feed_table)

            # Signals Table (show top 10 + any degraded)
            if health.signals:
                signal_table = Table(title="Signal Health", expand=True)
                signal_table.add_column("Signal", style="cyan", width=25)
                signal_table.add_column("Status", width=10)
                signal_table.add_column("IC Overall", justify="right", width=12)
                signal_table.add_column("IC 30d", justify="right", width=12)
                signal_table.add_column("Stability", justify="right", width=12)

                # Show degraded first, then healthy (limit 10)
                sorted_signals = sorted(health.signals, key=lambda s: (s.status != HealthStatus.HEALTHY, -s.ic_overall))
                for signal in sorted_signals[:10]:
                    status_style = status_color_map.get(signal.status, "white")
                    signal_table.add_row(
                        signal.name,
                        f"[{status_style}]{signal.status.value}[/{status_style}]",
                        f"{signal.ic_overall:.4f}",
                        f"{signal.ic_30d:.4f}",
                        f"{signal.ic_stability:.2f}",
                    )

                console.print(signal_table)

            # Research Status
            research = health.research
            research_text = Text()
            research_text.append(f"Active Experiments: ", style="dim")
            research_text.append(f"{research.active_experiments}\n", style="white")
            research_text.append(f"Completed Today: ", style="dim")
            research_text.append(f"{research.completed_today}\n", style="white")
            research_text.append(f"Total Insights: ", style="dim")
            research_text.append(f"{research.insights_discovered}\n", style="white")
            research_text.append(f"Strategies Validated: ", style="dim")
            research_text.append(f"{research.strategies_validated}\n", style="white")
            if research.last_cycle:
                research_text.append(f"Last Cycle: ", style="dim")
                research_text.append(f"{research.last_cycle.strftime('%m/%d %H:%M')}", style="white")

            console.print(Panel(research_text, title="Research Status", border_style="magenta"))

            # Cron Jobs Table
            if health.cron_jobs:
                cron_table = Table(title="Cron Jobs", expand=True)
                cron_table.add_column("Job", style="cyan", width=20)
                cron_table.add_column("Schedule", width=18)
                cron_table.add_column("Status", width=10)
                cron_table.add_column("Last Run", width=18)
                cron_table.add_column("Message", width=25)

                for job in health.cron_jobs:
                    status_style = status_color_map.get(job.status, "white")
                    last_run = job.last_run.strftime("%m/%d %H:%M") if job.last_run else "Never"
                    cron_table.add_row(
                        job.name,
                        job.schedule,
                        f"[{status_style}]{job.status.value}[/{status_style}]",
                        last_run,
                        job.message[:25] if job.message else "",
                    )

                console.print(cron_table)

            # Active Alerts
            if health.alerts:
                alert_text = Text()
                for alert in health.alerts:
                    level = alert.get("level", "info")
                    level_style = {"critical": "red", "warning": "yellow", "info": "blue"}.get(level, "white")
                    alert_text.append(f"[{level.upper()}] ", style=level_style)
                    alert_text.append(f"{alert.get('title', 'Alert')}: ", style="white")
                    alert_text.append(f"{alert.get('message', '')}\n", style="dim")

                console.print(Panel(alert_text, title="Active Alerts", border_style="red"))

        except ImportError:
            # Fallback to basic printing
            print("\n" + "=" * 60)
            print(f"OPERATIONS DASHBOARD - {health.timestamp}")
            print(f"Overall Status: {health.overall_status.value}")
            print("=" * 60)

            print(f"\nData Feeds: {len(health.data_feeds)}")
            for feed in health.data_feeds:
                print(f"  {feed.name}: {feed.status.value}")

            print(f"\nSignals: {len(health.signals)}")
            for signal in health.signals[:5]:
                print(f"  {signal.name}: IC={signal.ic_overall:.4f} ({signal.status.value})")

            print(f"\nResearch: {health.research.completed_today} experiments today")

            print(f"\nCron Jobs: {len(health.cron_jobs)}")
            for job in health.cron_jobs:
                print(f"  {job.name}: {job.status.value}")

            if health.alerts:
                print(f"\nAlerts: {len(health.alerts)}")
                for alert in health.alerts:
                    print(f"  [{alert.get('level')}] {alert.get('title')}")

            print("=" * 60 + "\n")

    def save_status(self, health: SystemHealth, output_path: Path | None = None) -> Path:
        """Save health status to JSON file."""
        output_path = output_path or self.live_dir / "ops_health.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(health.to_dict(), f, indent=2)

        return output_path


async def main():
    """Run operations dashboard."""
    import argparse

    parser = argparse.ArgumentParser(description="Operations Dashboard")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    parser.add_argument("--save", action="store_true", help="Save status to file")
    parser.add_argument("--results-dir", type=Path, help="Results directory")

    args = parser.parse_args()

    dashboard = OperationsDashboard(results_dir=args.results_dir)
    health = await dashboard.get_system_health()

    if args.json:
        print(json.dumps(health.to_dict(), indent=2))
    else:
        dashboard.print_status(health)

    if args.save:
        path = dashboard.save_status(health)
        print(f"\nSaved to: {path}")


if __name__ == "__main__":
    asyncio.run(main())
