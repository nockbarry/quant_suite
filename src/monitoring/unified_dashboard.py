"""
Unified Orchestration Dashboard for Automated Trading Firm.

The "mission control" view combining:
- Agent activity (Claude Code, subagents)
- Data pipeline health & quality
- Research cycle status
- Signal health & convergences
- Portfolio monitoring & thesis exposure
- Upcoming catalysts
- System alerts

This is what you look at to see "the automated trading firm in action".
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.paths import paths

import yaml

logger = logging.getLogger(__name__)


class SystemMode(str, Enum):
    """System operating mode."""
    LIVE = "live"
    PAPER = "paper"
    RESEARCH = "research"
    MAINTENANCE = "maintenance"


@dataclass
class UnifiedSystemStatus:
    """Complete system status snapshot."""
    timestamp: datetime
    mode: SystemMode

    # Agent layer
    session_active: bool
    session_duration_minutes: float
    agents_running: int
    agents_completed_today: int
    decisions_made_today: int
    total_tokens_today: int

    # Data layer
    data_quality_score: float
    feeds_healthy: int
    feeds_degraded: int
    feeds_critical: int
    stale_sources: list[str]

    # Research layer
    research_active: bool
    experiments_today: int
    insights_today: int
    strategies_validated: int

    # Signal layer
    signals_healthy: int
    signals_degraded: int
    active_signals_count: int

    # Portfolio layer
    portfolio_value: float
    daily_pnl: float
    daily_pnl_pct: float
    positions_count: int
    max_concentration: float

    # Risk layer
    drawdown: float
    pdt_trades_used: int
    risk_status: str  # ok, warning, critical

    # System layer
    cron_jobs_ok: int
    cron_jobs_failed: int
    disk_space_pct: float

    # Fields with defaults (must come after non-defaults)
    # Data sources (NEW - with content summaries)
    data_sources: dict[str, dict] = field(default_factory=dict)
    # Top signals (NEW - actionable signals)
    top_signals: list[dict] = field(default_factory=list)
    convergences: list[dict] = field(default_factory=list)
    market_regime: str = "unknown"
    regime_signals: list[str] = field(default_factory=list)
    # Thesis exposure (NEW)
    thesis_exposure: dict[str, dict] = field(default_factory=dict)
    # Catalysts (NEW)
    upcoming_catalysts: list[dict] = field(default_factory=list)
    # Active alerts
    active_alerts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "mode": self.mode.value,
            "agent_layer": {
                "session_active": self.session_active,
                "session_duration_minutes": round(self.session_duration_minutes, 1),
                "agents_running": self.agents_running,
                "agents_completed_today": self.agents_completed_today,
                "decisions_made_today": self.decisions_made_today,
                "total_tokens_today": self.total_tokens_today,
            },
            "data_layer": {
                "quality_score": round(self.data_quality_score, 1),
                "feeds_healthy": self.feeds_healthy,
                "feeds_degraded": self.feeds_degraded,
                "feeds_critical": self.feeds_critical,
                "stale_sources": self.stale_sources,
                "sources": self.data_sources,
            },
            "research_layer": {
                "active": self.research_active,
                "experiments_today": self.experiments_today,
                "insights_today": self.insights_today,
                "strategies_validated": self.strategies_validated,
            },
            "signal_layer": {
                "healthy": self.signals_healthy,
                "degraded": self.signals_degraded,
                "active_count": self.active_signals_count,
                "top_signals": self.top_signals[:5],
                "convergences": self.convergences,
                "regime": self.market_regime,
                "regime_signals": self.regime_signals,
            },
            "portfolio_layer": {
                "value": round(self.portfolio_value, 2),
                "daily_pnl": round(self.daily_pnl, 2),
                "daily_pnl_pct": round(self.daily_pnl_pct, 4),
                "positions": self.positions_count,
                "max_concentration": round(self.max_concentration, 4),
                "thesis_exposure": self.thesis_exposure,
            },
            "catalysts": self.upcoming_catalysts[:10],
            "risk_layer": {
                "drawdown": round(self.drawdown, 4),
                "pdt_trades_used": self.pdt_trades_used,
                "status": self.risk_status,
            },
            "system_layer": {
                "cron_ok": self.cron_jobs_ok,
                "cron_failed": self.cron_jobs_failed,
                "disk_space_pct": round(self.disk_space_pct, 1),
                "active_alerts": len(self.active_alerts),
            },
        }


class UnifiedDashboard:
    """
    Unified dashboard aggregating all monitoring systems.

    Provides a single view of the entire automated trading operation.
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or paths.base
        self.live_dir = self.results_dir / "live"
        self.logs_dir = self.results_dir / "logs"
        self.theses_dir = self.results_dir / "theses"

        # Lazy imports to avoid circular dependencies
        self._ops_dashboard = None
        self._agent_monitor = None
        self._data_quality = None
        self._freshness_tracker = None
        self._signal_aggregator = None

    async def get_unified_status(self) -> UnifiedSystemStatus:
        """Get complete system status."""
        # Gather all status concurrently
        ops_health = await self._get_ops_health()
        agent_status = self._get_agent_status()
        data_quality = await self._get_data_quality()
        research_status = self._get_research_status()
        signal_status = self._get_signal_status()
        portfolio_status = self._get_portfolio_status()
        risk_status = self._get_risk_status()

        # NEW: Get enhanced data from freshness tracker and signal aggregator
        data_sources = self._get_data_freshness()
        signal_summary = self._get_signal_summary()
        thesis_exposure = self._get_thesis_exposure(portfolio_status.get("positions_data", []))
        catalysts = signal_summary.get("catalysts", [])

        return UnifiedSystemStatus(
            timestamp=datetime.now(),
            mode=self._detect_mode(),
            # Agent layer
            session_active=agent_status.get("session_active", False),
            session_duration_minutes=agent_status.get("duration_minutes", 0),
            agents_running=agent_status.get("running", 0),
            agents_completed_today=agent_status.get("completed_today", 0),
            decisions_made_today=agent_status.get("decisions_today", 0),
            total_tokens_today=agent_status.get("tokens_today", 0),
            # Data layer
            data_quality_score=data_quality.get("score", 0),
            feeds_healthy=ops_health.get("data_feeds_healthy", 0),
            feeds_degraded=ops_health.get("data_feeds_degraded", 0),
            feeds_critical=ops_health.get("data_feeds_critical", 0),
            stale_sources=data_quality.get("stale", []),
            data_sources=data_sources,
            # Research layer
            research_active=research_status.get("active", False),
            experiments_today=research_status.get("experiments", 0),
            insights_today=research_status.get("insights", 0),
            strategies_validated=research_status.get("validated", 0),
            # Signal layer
            signals_healthy=signal_status.get("healthy", 0),
            signals_degraded=signal_status.get("degraded", 0),
            active_signals_count=signal_status.get("active", 0),
            top_signals=signal_summary.get("top_signals", []),
            convergences=signal_summary.get("convergences", []),
            market_regime=signal_summary.get("regime", "unknown"),
            regime_signals=signal_summary.get("regime_signals", []),
            # Portfolio layer
            portfolio_value=portfolio_status.get("value", 0),
            daily_pnl=portfolio_status.get("daily_pnl", 0),
            daily_pnl_pct=portfolio_status.get("daily_pnl_pct", 0),
            positions_count=portfolio_status.get("positions", 0),
            max_concentration=portfolio_status.get("max_concentration", 0),
            thesis_exposure=thesis_exposure,
            # Catalysts
            upcoming_catalysts=catalysts,
            # Risk layer
            drawdown=risk_status.get("drawdown", 0),
            pdt_trades_used=risk_status.get("pdt_used", 0),
            risk_status=risk_status.get("status", "unknown"),
            # System layer
            cron_jobs_ok=ops_health.get("cron_healthy", 0),
            cron_jobs_failed=ops_health.get("cron_failed", 0),
            disk_space_pct=self._get_disk_space(),
            active_alerts=ops_health.get("alerts", []),
        )

    def _detect_mode(self) -> SystemMode:
        """Detect current operating mode."""
        # Check for mode indicator file
        mode_file = self.live_dir / "mode.txt"
        if mode_file.exists():
            mode = mode_file.read_text().strip().lower()
            try:
                return SystemMode(mode)
            except ValueError:
                pass

        # Default to paper during development
        return SystemMode.PAPER

    async def _get_ops_health(self) -> dict:
        """Get operations health status."""
        try:
            from src.monitoring.ops_dashboard import OperationsDashboard

            if self._ops_dashboard is None:
                self._ops_dashboard = OperationsDashboard(self.results_dir)

            health = await self._ops_dashboard.get_system_health()
            return health.summary
        except Exception as e:
            logger.error(f"Error getting ops health: {e}")
            return {}

    def _get_agent_status(self) -> dict:
        """Get agent activity status from both in-memory and log file."""
        try:
            # Read from activity log file (includes daemon activities)
            activity_log = self.results_dir / "logs" / "agent_activity.jsonl"
            today = datetime.now().date().isoformat()

            running = 0
            completed_today = 0
            market_checks_today = 0
            recent_alerts = []

            if activity_log.exists():
                with open(activity_log) as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            timestamp = record.get("timestamp", "")
                            event_type = record.get("type", "")

                            # Only count today's activity
                            if not timestamp.startswith(today):
                                continue

                            if event_type == "agent_start":
                                if record.get("status") == "running":
                                    running += 1
                            elif event_type == "agent_complete":
                                completed_today += 1
                                running = max(0, running - 1)
                            elif event_type == "market_check":
                                market_checks_today += 1
                                alerts = record.get("alerts", [])
                                if alerts:
                                    recent_alerts = alerts  # Keep most recent
                        except (json.JSONDecodeError, ValueError):
                            continue

            # Also check in-memory monitor for live Claude Code sessions
            from src.monitoring.agent_monitor import get_agent_monitor
            if self._agent_monitor is None:
                self._agent_monitor = get_agent_monitor()

            summary = self._agent_monitor.get_session_summary()
            session_active = summary.get("status") != "no_active_session"

            if session_active:
                running += summary.get("agents", {}).get("running", 0)
                completed_today += summary.get("agents", {}).get("completed", 0)

            return {
                "session_active": session_active or running > 0,
                "duration_minutes": summary.get("duration_minutes", 0) if session_active else 0,
                "running": running,
                "completed_today": completed_today,
                "decisions_today": summary.get("decisions_made", 0) if session_active else 0,
                "tokens_today": summary.get("total_tokens", 0) if session_active else 0,
                "market_checks_today": market_checks_today,
                "recent_alerts": recent_alerts,
            }
        except Exception as e:
            logger.error(f"Error getting agent status: {e}")
            return {"session_active": False}

    async def _get_data_quality(self) -> dict:
        """Get data quality status."""
        try:
            from src.monitoring.data_quality import get_data_quality_monitor

            if self._data_quality is None:
                self._data_quality = get_data_quality_monitor()

            results = await self._data_quality.check_all_sources()
            summary = self._data_quality.get_quality_summary(results)

            stale = [
                name for name, r in results.items()
                if r.freshness_minutes > 60
            ]

            return {
                "score": summary.get("overall_score", 0),
                "stale": stale,
            }
        except Exception as e:
            logger.error(f"Error getting data quality: {e}")
            return {"score": 0, "stale": []}

    def _get_research_status(self) -> dict:
        """Get research cycle status."""
        try:
            tracker_file = self.results_dir / "research" / "session_tracker.json"
            if not tracker_file.exists():
                return {}

            with open(tracker_file) as f:
                data = json.load(f)

            today = datetime.now().date().isoformat()

            experiments = data.get("experiments", [])
            insights = data.get("insights", [])

            experiments_today = sum(
                1 for e in experiments
                if e.get("completed_at", "").startswith(today)
            )
            insights_today = sum(
                1 for i in insights
                if i.get("discovered_at", "").startswith(today)
            )

            return {
                "active": data.get("active_experiments", 0) > 0,
                "experiments": experiments_today,
                "insights": insights_today,
                "validated": data.get("strategies_validated", 0),
            }
        except Exception as e:
            logger.error(f"Error getting research status: {e}")
            return {}

    def _get_signal_status(self) -> dict:
        """Get signal health status."""
        try:
            health_file = self.live_dir / "signal_health.json"
            if not health_file.exists():
                return {}

            with open(health_file) as f:
                data = json.load(f)

            signals = data.get("signals", {})
            healthy = degraded = 0

            for metrics in signals.values():
                ic = metrics.get("ic_overall", 0)
                if ic >= 0.02:
                    healthy += 1
                else:
                    degraded += 1

            # Count active signals
            state_file = self.live_dir / "state.json"
            active = 0
            if state_file.exists():
                with open(state_file) as f:
                    state = json.load(f)
                    active = len(state.get("signals", {}).get("watchlist", []))

            return {
                "healthy": healthy,
                "degraded": degraded,
                "active": active,
            }
        except Exception as e:
            logger.error(f"Error getting signal status: {e}")
            return {}

    def _get_portfolio_status(self) -> dict:
        """Get portfolio status from unified state."""
        try:
            state_file = self.live_dir / "state.json"
            if not state_file.exists():
                return {}

            with open(state_file) as f:
                state = json.load(f)

            portfolio = state.get("portfolio", {})

            # Positions are at top level in state.json
            positions = state.get("positions", [])
            # Equity is the total value
            total_value = portfolio.get("equity", 0)

            max_concentration = 0
            if positions and total_value > 0:
                max_concentration = max(
                    p.get("market_value", 0) / total_value
                    for p in positions
                ) if positions else 0

            return {
                "value": total_value,
                "daily_pnl": portfolio.get("day_pnl", 0),
                "daily_pnl_pct": portfolio.get("day_pnl_pct", 0) / 100,  # Convert to decimal
                "positions": len(positions),
                "max_concentration": max_concentration,
            }
        except Exception as e:
            logger.error(f"Error getting portfolio status: {e}")
            return {}

    def _get_risk_status(self) -> dict:
        """Get risk status."""
        try:
            state_file = self.live_dir / "state.json"
            if not state_file.exists():
                return {}

            with open(state_file) as f:
                state = json.load(f)

            portfolio = state.get("portfolio", {})

            drawdown = 0
            total_value = portfolio.get("total_value", 0)
            peak_value = portfolio.get("peak_value", total_value)
            if peak_value > 0:
                drawdown = (total_value - peak_value) / peak_value

            # PDT status
            pdt_file = self.results_dir / "pdt_status.json"
            pdt_used = 0
            if pdt_file.exists():
                with open(pdt_file) as f:
                    pdt = json.load(f)
                    pdt_used = pdt.get("trades_used", 0)

            # Determine risk status
            daily_pnl_pct = portfolio.get("daily_pnl_pct", 0)
            if drawdown < -0.15 or daily_pnl_pct < -0.05:
                status = "critical"
            elif drawdown < -0.10 or daily_pnl_pct < -0.03:
                status = "warning"
            else:
                status = "ok"

            return {
                "drawdown": drawdown,
                "pdt_used": pdt_used,
                "status": status,
            }
        except Exception as e:
            logger.error(f"Error getting risk status: {e}")
            return {}

    def _get_disk_space(self) -> float:
        """Get available disk space percentage."""
        try:
            import os
            statvfs = os.statvfs(str(self.results_dir))
            return statvfs.f_bavail / statvfs.f_blocks * 100
        except Exception:
            return 100.0

    def _get_data_freshness(self) -> dict[str, dict]:
        """Get data source freshness with content summaries."""
        try:
            from src.monitoring.data_freshness_tracker import get_data_freshness_tracker

            if self._freshness_tracker is None:
                self._freshness_tracker = get_data_freshness_tracker()

            summary = self._freshness_tracker.get_freshness_summary()

            # Convert to dict format for status
            sources = {}
            for name, status in summary.sources.items():
                sources[name] = {
                    "fresh": status.fresh,
                    "last_update": status.last_update_ago,
                    "top_signal": status.top_signal,
                    "signal_count": status.signal_count,
                    "status": status.status,
                    "category": status.category,
                }

            return sources
        except Exception as e:
            logger.error(f"Error getting data freshness: {e}")
            return {}

    def _get_signal_summary(self) -> dict:
        """Get aggregated signals from all sources."""
        try:
            from src.monitoring.signal_summary import get_signal_aggregator

            if self._signal_aggregator is None:
                self._signal_aggregator = get_signal_aggregator()

            summary = self._signal_aggregator.get_signal_summary()

            return {
                "regime": summary.regime,
                "regime_signals": summary.regime_signals,
                "top_signals": [
                    {
                        "type": s.type,
                        "symbol": s.symbol,
                        "direction": s.direction,
                        "strength": round(s.strength, 2),
                        "description": s.description[:80],
                    }
                    for s in summary.top_signals[:10]
                ],
                "convergences": [
                    {
                        "symbol": c.symbol,
                        "direction": c.direction,
                        "signal_count": len(c.signals),
                        "score": round(c.convergence_score, 2),
                        "description": c.description,
                    }
                    for c in summary.convergences
                ],
                "catalysts": [
                    {
                        "date": c.date.strftime("%Y-%m-%d"),
                        "type": c.type,
                        "symbol": c.symbol,
                        "event": c.event[:50],
                        "impact": c.impact,
                        "exposure": c.exposure,
                    }
                    for c in summary.catalysts[:15]
                ],
            }
        except Exception as e:
            logger.error(f"Error getting signal summary: {e}")
            return {}

    def _get_thesis_exposure(self, positions: list[dict]) -> dict[str, dict]:
        """Calculate portfolio exposure by thesis."""
        try:
            # Load all active theses
            theses = {}
            if self.theses_dir.exists():
                for thesis_file in self.theses_dir.glob("*.yaml"):
                    try:
                        with open(thesis_file) as f:
                            thesis = yaml.safe_load(f)
                            if thesis.get("status") == "active":
                                thesis_id = thesis.get("id", thesis_file.stem)
                                theses[thesis_id] = thesis
                    except Exception as e:
                        logger.debug(f"Error loading thesis {thesis_file}: {e}")

            # Build symbol -> thesis mapping
            symbol_thesis = {}
            for thesis_id, thesis in theses.items():
                for symbol in thesis.get("positions", []):
                    symbol_thesis[symbol] = (thesis_id, thesis.get("name", "Unknown"))

            # Calculate exposure by thesis
            exposure = {}
            if not positions:
                # Try to load positions from state if not provided
                state_file = self.live_dir / "state.json"
                if state_file.exists():
                    with open(state_file) as f:
                        state = json.load(f)
                        positions = state.get("positions", [])

            for pos in positions:
                symbol = pos.get("symbol", "")
                if symbol in symbol_thesis:
                    thesis_id, thesis_name = symbol_thesis[symbol]
                    if thesis_name not in exposure:
                        exposure[thesis_name] = {
                            "thesis_id": thesis_id,
                            "value": 0,
                            "day_pnl": 0,
                            "positions": 0,
                            "symbols": [],
                        }

                    exposure[thesis_name]["value"] += pos.get("market_value", 0)
                    exposure[thesis_name]["day_pnl"] += pos.get("day_pnl", 0)
                    exposure[thesis_name]["positions"] += 1
                    exposure[thesis_name]["symbols"].append(symbol)

            # Calculate percentages
            total_value = sum(e["value"] for e in exposure.values())
            for name in exposure:
                if total_value > 0:
                    exposure[name]["pct"] = round(exposure[name]["value"] / total_value * 100, 1)
                else:
                    exposure[name]["pct"] = 0

            return exposure
        except Exception as e:
            logger.error(f"Error getting thesis exposure: {e}")
            return {}

    def print_dashboard(self, status: UnifiedSystemStatus) -> None:
        """Print dashboard to console."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            from rich.text import Text
            from rich.columns import Columns
            from rich.layout import Layout

            console = Console()

            # Header
            header = Text()
            header.append("UNIFIED TRADING DASHBOARD ", style="bold cyan")
            header.append("| ", style="dim")
            header.append(f"{status.timestamp.strftime('%Y-%m-%d %H:%M:%S')} ", style="white")
            header.append("| Mode: ", style="dim")

            mode_colors = {
                SystemMode.LIVE: "red",
                SystemMode.PAPER: "yellow",
                SystemMode.RESEARCH: "blue",
                SystemMode.MAINTENANCE: "dim",
            }
            header.append(status.mode.value.upper(), style=f"bold {mode_colors.get(status.mode, 'white')}")

            console.print(Panel(header, border_style="cyan"))

            # Create panels
            panels = []

            # Agent Layer
            agent_text = Text()
            agent_text.append(f"Session: ", style="dim")
            agent_text.append("ACTIVE" if status.session_active else "INACTIVE",
                            style="green" if status.session_active else "yellow")
            agent_text.append(f" ({status.session_duration_minutes:.0f}m)\n", style="dim")
            agent_text.append(f"Agents Running: ", style="dim")
            agent_text.append(f"{status.agents_running}\n", style="cyan")
            agent_text.append(f"Completed Today: ", style="dim")
            agent_text.append(f"{status.agents_completed_today}\n", style="white")
            agent_text.append(f"Decisions Made: ", style="dim")
            agent_text.append(f"{status.decisions_made_today}\n", style="white")
            agent_text.append(f"Tokens Used: ", style="dim")
            agent_text.append(f"{status.total_tokens_today:,}", style="white")
            panels.append(Panel(agent_text, title="Agent Layer", border_style="magenta", width=30))

            # Data Layer
            data_text = Text()
            data_text.append(f"Quality Score: ", style="dim")
            score_color = "green" if status.data_quality_score >= 85 else "yellow" if status.data_quality_score >= 70 else "red"
            data_text.append(f"{status.data_quality_score:.0f}%\n", style=score_color)
            data_text.append(f"Feeds: ", style="dim")
            data_text.append(f"{status.feeds_healthy} healthy", style="green")
            data_text.append(f", {status.feeds_degraded} degraded", style="yellow")
            data_text.append(f", {status.feeds_critical} critical\n", style="red")
            if status.stale_sources:
                data_text.append(f"Stale: ", style="dim")
                data_text.append(f"{', '.join(status.stale_sources[:3])}", style="yellow")
            panels.append(Panel(data_text, title="Data Layer", border_style="blue", width=35))

            # Research Layer
            research_text = Text()
            research_text.append(f"Status: ", style="dim")
            research_text.append("ACTIVE" if status.research_active else "IDLE",
                               style="green" if status.research_active else "dim")
            research_text.append(f"\nExperiments Today: ", style="dim")
            research_text.append(f"{status.experiments_today}\n", style="white")
            research_text.append(f"Insights Found: ", style="dim")
            research_text.append(f"{status.insights_today}\n", style="cyan")
            research_text.append(f"Strategies Validated: ", style="dim")
            research_text.append(f"{status.strategies_validated}", style="white")
            panels.append(Panel(research_text, title="Research Layer", border_style="green", width=30))

            console.print(Columns(panels))

            # Second row
            panels2 = []

            # Portfolio Layer
            portfolio_text = Text()
            portfolio_text.append(f"Value: ", style="dim")
            portfolio_text.append(f"${status.portfolio_value:,.2f}\n", style="bold white")
            portfolio_text.append(f"Daily P&L: ", style="dim")
            pnl_color = "green" if status.daily_pnl >= 0 else "red"
            portfolio_text.append(f"${status.daily_pnl:+,.2f} ({status.daily_pnl_pct:+.2%})\n", style=pnl_color)
            portfolio_text.append(f"Positions: ", style="dim")
            portfolio_text.append(f"{status.positions_count}\n", style="white")
            portfolio_text.append(f"Max Concentration: ", style="dim")
            conc_color = "green" if status.max_concentration < 0.20 else "yellow" if status.max_concentration < 0.25 else "red"
            portfolio_text.append(f"{status.max_concentration:.1%}", style=conc_color)
            panels2.append(Panel(portfolio_text, title="Portfolio", border_style="cyan", width=30))

            # Risk Layer
            risk_text = Text()
            risk_text.append(f"Status: ", style="dim")
            risk_colors = {"ok": "green", "warning": "yellow", "critical": "red"}
            risk_text.append(status.risk_status.upper(), style=risk_colors.get(status.risk_status, "white"))
            risk_text.append(f"\nDrawdown: ", style="dim")
            dd_color = "green" if status.drawdown > -0.10 else "yellow" if status.drawdown > -0.15 else "red"
            risk_text.append(f"{status.drawdown:.2%}\n", style=dd_color)
            risk_text.append(f"PDT Trades: ", style="dim")
            pdt_color = "green" if status.pdt_trades_used < 3 else "red"
            risk_text.append(f"{status.pdt_trades_used}/3", style=pdt_color)
            panels2.append(Panel(risk_text, title="Risk", border_style="yellow", width=25))

            # Signal Layer
            signal_text = Text()
            signal_text.append(f"Healthy: ", style="dim")
            signal_text.append(f"{status.signals_healthy}\n", style="green")
            signal_text.append(f"Degraded: ", style="dim")
            signal_text.append(f"{status.signals_degraded}\n", style="yellow")
            signal_text.append(f"Active Signals: ", style="dim")
            signal_text.append(f"{status.active_signals_count}", style="cyan")
            panels2.append(Panel(signal_text, title="Signals", border_style="magenta", width=20))

            # System Layer
            system_text = Text()
            system_text.append(f"Cron: ", style="dim")
            system_text.append(f"{status.cron_jobs_ok} ok", style="green")
            system_text.append(f", {status.cron_jobs_failed} failed\n", style="red" if status.cron_jobs_failed > 0 else "green")
            system_text.append(f"Disk: ", style="dim")
            disk_color = "green" if status.disk_space_pct > 20 else "yellow" if status.disk_space_pct > 10 else "red"
            system_text.append(f"{status.disk_space_pct:.0f}% free\n", style=disk_color)
            system_text.append(f"Alerts: ", style="dim")
            alert_style = "red" if status.active_alerts else "green"
            system_text.append(f"{len(status.active_alerts)}", style=alert_style)
            panels2.append(Panel(system_text, title="System", border_style="dim", width=20))

            console.print(Columns(panels2))

            # Third row: Signals and Regime
            panels3 = []

            # Market Regime
            regime_text = Text()
            regime_text.append(f"Regime: ", style="dim")
            regime_colors = {"risk_on": "green", "risk_off": "red", "neutral": "yellow", "volatile": "magenta"}
            regime_text.append(status.market_regime.upper(), style=f"bold {regime_colors.get(status.market_regime, 'white')}")
            regime_text.append("\n")
            for sig in status.regime_signals[:3]:
                regime_text.append(f"  - {sig}\n", style="dim")
            panels3.append(Panel(regime_text, title="Market Regime", border_style="cyan", width=35))

            # Top Signals
            signals_text = Text()
            for sig in status.top_signals[:4]:
                direction_color = "green" if sig.get("direction") == "bullish" else "red"
                signals_text.append(f"[{sig.get('type', 'UNK')[:4]}] ", style="dim")
                signals_text.append(f"{sig.get('symbol') or 'MKT'}: ", style="cyan")
                signals_text.append(f"{sig.get('description', '')[:40]}\n", style=direction_color)
            if not status.top_signals:
                signals_text.append("No actionable signals", style="dim")
            panels3.append(Panel(signals_text, title="Top Signals", border_style="green", width=50))

            console.print(Columns(panels3))

            # Fourth row: Convergences and Catalysts
            panels4 = []

            # Convergences (3+ aligned signals)
            if status.convergences:
                conv_text = Text()
                for conv in status.convergences[:3]:
                    direction_color = "green" if conv.get("direction") == "bullish" else "red"
                    conv_text.append(f"{conv.get('symbol')}: ", style="bold cyan")
                    conv_text.append(f"{conv.get('signal_count')} signals ", style=direction_color)
                    conv_text.append(f"({conv.get('score', 0):.0%})\n", style="white")
                panels4.append(Panel(conv_text, title="Convergences", border_style="magenta", width=30))

            # Upcoming Catalysts
            if status.upcoming_catalysts:
                cat_text = Text()
                for cat in status.upcoming_catalysts[:4]:
                    impact_color = {"high": "red", "medium": "yellow", "low": "dim"}.get(cat.get("impact", "low"), "white")
                    cat_text.append(f"{cat.get('date', '')}: ", style="dim")
                    if cat.get("symbol"):
                        cat_text.append(f"{cat.get('symbol')} ", style="cyan")
                    cat_text.append(f"{cat.get('event', '')[:30]}\n", style=impact_color)
                panels4.append(Panel(cat_text, title="Catalysts", border_style="yellow", width=40))

            if panels4:
                console.print(Columns(panels4))

            # Fifth row: Thesis Exposure (if any)
            if status.thesis_exposure:
                thesis_text = Text()
                for name, exp in sorted(status.thesis_exposure.items(), key=lambda x: -x[1].get("value", 0))[:5]:
                    pnl = exp.get("day_pnl", 0)
                    pnl_color = "green" if pnl >= 0 else "red"
                    thesis_text.append(f"{name[:25]:<25} ", style="white")
                    thesis_text.append(f"${exp.get('value', 0):>10,.0f} ", style="cyan")
                    thesis_text.append(f"({exp.get('pct', 0):>5.1f}%) ", style="dim")
                    thesis_text.append(f"P&L: ${pnl:>+8,.0f}\n", style=pnl_color)
                console.print(Panel(thesis_text, title="Thesis Exposure", border_style="blue"))

            # Data Sources (show top signals from each source)
            if status.data_sources:
                sources_text = Text()
                for name, src in sorted(status.data_sources.items(), key=lambda x: -x[1].get("signal_count", 0))[:6]:
                    status_color = {"healthy": "green", "stale": "yellow", "error": "red"}.get(src.get("status", ""), "white")
                    sources_text.append(f"[{src.get('status', 'UNK')[:3]}] ", style=status_color)
                    sources_text.append(f"{name[:12]:<12} ", style="white")
                    sources_text.append(f"({src.get('last_update', 'N/A')}) ", style="dim")
                    signal_text = src.get("top_signal", "")[:35] if src.get("top_signal") else "No signal"
                    sources_text.append(f"{signal_text}\n", style="cyan" if src.get("signal_count", 0) > 0 else "dim")
                console.print(Panel(sources_text, title="Data Sources", border_style="blue"))

            # Alerts (if any)
            if status.active_alerts:
                alerts_text = Text()
                for alert in status.active_alerts[:5]:
                    level = alert.get("level", "info")
                    level_style = {"critical": "red", "warning": "yellow", "info": "blue"}.get(level, "white")
                    alerts_text.append(f"[{level.upper()}] ", style=level_style)
                    alerts_text.append(f"{alert.get('title', 'Alert')}: ", style="white")
                    alerts_text.append(f"{alert.get('message', '')}\n", style="dim")

                console.print(Panel(alerts_text, title="Active Alerts", border_style="red"))

        except ImportError:
            # Fallback to basic print
            print("\n" + "=" * 60)
            print(f"UNIFIED DASHBOARD - {status.timestamp}")
            print(f"Mode: {status.mode.value}")
            print("=" * 60)
            print(json.dumps(status.to_dict(), indent=2))

    def save_status(self, status: UnifiedSystemStatus) -> Path:
        """Save status to file."""
        output_path = self.live_dir / "unified_status.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(status.to_dict(), f, indent=2)

        return output_path


async def main():
    """Run unified dashboard."""
    import argparse

    parser = argparse.ArgumentParser(description="Unified Trading Dashboard")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--save", action="store_true", help="Save to file")
    parser.add_argument("--watch", action="store_true", help="Watch mode (refresh every 30s)")

    args = parser.parse_args()

    dashboard = UnifiedDashboard()

    if args.watch:
        try:
            while True:
                status = await dashboard.get_unified_status()
                if args.json:
                    print(json.dumps(status.to_dict(), indent=2))
                else:
                    # Clear screen
                    print("\033[2J\033[H", end="")
                    dashboard.print_dashboard(status)
                    print("\nRefreshing in 30s... (Ctrl+C to exit)")

                if args.save:
                    dashboard.save_status(status)

                await asyncio.sleep(30)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        status = await dashboard.get_unified_status()
        if args.json:
            print(json.dumps(status.to_dict(), indent=2))
        else:
            dashboard.print_dashboard(status)

        if args.save:
            path = dashboard.save_status(status)
            print(f"\nSaved to: {path}")


if __name__ == "__main__":
    asyncio.run(main())
