"""
Comprehensive Monitoring Dashboard for Automated Trading Firm.

Extends the unified dashboard with:
1. Market theme tracking with historical changes
2. Detailed operations status (crons, schedules, last runs)
3. Enhanced portfolio view by thesis, sector, and risk exposure
4. Layer-by-layer system status with health indicators

Maintains historical snapshots to show how things change over time.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.paths import paths

import yaml

logger = logging.getLogger(__name__)


class MarketTheme(str, Enum):
    """Market theme classifications."""
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    ROTATION_TECH = "tech_leadership"
    ROTATION_DEFENSIVE = "defensive_rotation"
    ROTATION_CYCLICAL = "cyclical_rotation"
    VOLATILITY_EXPANSION = "vol_expansion"
    VOLATILITY_COMPRESSION = "vol_compression"
    SECTOR_DIVERGENCE = "sector_divergence"
    BROAD_RALLY = "broad_rally"
    BROAD_SELLOFF = "broad_selloff"


@dataclass
class MarketThemeSnapshot:
    """Single snapshot of market themes."""
    timestamp: datetime
    primary_theme: str
    secondary_themes: list[str]
    theme_signals: list[str]  # What's driving the theme
    sector_leaders: list[str]  # Top performing sectors
    sector_laggards: list[str]  # Worst performing sectors
    vix: float
    spy_change_pct: float
    breadth_ratio: float  # Advancing / Declining
    fear_greed: int

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "primary_theme": self.primary_theme,
            "secondary_themes": self.secondary_themes,
            "theme_signals": self.theme_signals,
            "sector_leaders": self.sector_leaders,
            "sector_laggards": self.sector_laggards,
            "vix": self.vix,
            "spy_change_pct": self.spy_change_pct,
            "breadth_ratio": self.breadth_ratio,
            "fear_greed": self.fear_greed,
        }


@dataclass
class CronJobDetail:
    """Detailed cron job status."""
    name: str
    description: str
    schedule_cron: str  # Raw cron expression
    schedule_human: str  # Human readable "Every 5 min Mon-Fri"
    script_path: str
    log_file: str
    last_run: datetime | None
    last_run_ago: str
    last_status: str  # "success", "error", "unknown"
    last_duration_sec: float | None
    next_scheduled: datetime | None
    runs_today: int
    errors_today: int
    enabled: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "schedule_cron": self.schedule_cron,
            "schedule_human": self.schedule_human,
            "script_path": self.script_path,
            "log_file": self.log_file,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_run_ago": self.last_run_ago,
            "last_status": self.last_status,
            "last_duration_sec": self.last_duration_sec,
            "next_scheduled": self.next_scheduled.isoformat() if self.next_scheduled else None,
            "runs_today": self.runs_today,
            "errors_today": self.errors_today,
            "enabled": self.enabled,
        }


@dataclass
class PositionDetail:
    """Enhanced position detail."""
    symbol: str
    quantity: float
    avg_cost: float
    market_price: float
    market_value: float
    day_pnl: float
    day_pnl_pct: float
    total_pnl: float
    total_pnl_pct: float
    weight_pct: float  # % of portfolio
    thesis_name: str | None
    sector: str | None
    days_held: int
    signals_aligned: int  # Number of signals supporting this position
    risk_score: float  # 0-1, higher = more risk
    notes: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "market_price": self.market_price,
            "market_value": round(self.market_value, 2),
            "day_pnl": round(self.day_pnl, 2),
            "day_pnl_pct": round(self.day_pnl_pct, 4),
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 4),
            "weight_pct": round(self.weight_pct, 2),
            "thesis_name": self.thesis_name,
            "sector": self.sector,
            "days_held": self.days_held,
            "signals_aligned": self.signals_aligned,
            "risk_score": round(self.risk_score, 2),
            "notes": self.notes,
        }


@dataclass
class ThesisExposure:
    """Thesis-level exposure summary."""
    thesis_id: str
    thesis_name: str
    conviction: int
    value: float
    weight_pct: float
    day_pnl: float
    total_pnl: float
    position_count: int
    symbols: list[str]
    top_performer: str | None
    worst_performer: str | None
    signposts_triggered: int
    days_active: int
    status: str  # "on_track", "at_risk", "exceeding"

    def to_dict(self) -> dict:
        return {
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "conviction": self.conviction,
            "value": round(self.value, 2),
            "weight_pct": round(self.weight_pct, 2),
            "day_pnl": round(self.day_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "position_count": self.position_count,
            "symbols": self.symbols,
            "top_performer": self.top_performer,
            "worst_performer": self.worst_performer,
            "signposts_triggered": self.signposts_triggered,
            "days_active": self.days_active,
            "status": self.status,
        }


@dataclass
class LayerStatus:
    """Status of a single system layer."""
    name: str
    status: str  # "healthy", "degraded", "critical", "unknown"
    health_score: float  # 0-100
    components: dict[str, str]  # Component name -> status
    metrics: dict[str, Any]  # Key metrics for this layer
    last_update: datetime | None
    last_update_ago: str
    alerts: list[str]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "health_score": round(self.health_score, 1),
            "components": self.components,
            "metrics": self.metrics,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "last_update_ago": self.last_update_ago,
            "alerts": self.alerts,
        }


@dataclass
class ClaudeActivity:
    """Claude Code's current activity status."""
    session_active: bool
    session_id: str | None
    session_duration_min: float
    agents_running: int
    agents_completed_today: int
    agents_failed_today: int
    decisions_today: int
    tokens_used_today: int
    running_agents: list[dict]  # Currently executing agents
    recent_completions: list[dict]  # Last 5 completed agents
    recent_decisions: list[dict]  # Last 5 decisions
    active_research_cycle: dict | None
    action_items: list[dict]  # From operator loop
    research_suggestions: list[str]

    def to_dict(self) -> dict:
        return {
            "session_active": self.session_active,
            "session_id": self.session_id,
            "session_duration_min": round(self.session_duration_min, 1),
            "agents_running": self.agents_running,
            "agents_completed_today": self.agents_completed_today,
            "agents_failed_today": self.agents_failed_today,
            "decisions_today": self.decisions_today,
            "tokens_used_today": self.tokens_used_today,
            "running_agents": self.running_agents,
            "recent_completions": self.recent_completions,
            "recent_decisions": self.recent_decisions,
            "active_research_cycle": self.active_research_cycle,
            "action_items": self.action_items,
            "research_suggestions": self.research_suggestions,
        }


@dataclass
class ComprehensiveStatus:
    """Complete comprehensive status snapshot."""
    timestamp: datetime

    # Claude's activity (NEW - shows what Claude is doing)
    claude_activity: ClaudeActivity | None

    # Market themes (current + history)
    current_theme: MarketThemeSnapshot | None
    theme_history: list[MarketThemeSnapshot]  # Last 24h of snapshots
    theme_change_summary: str  # "Tech leading -> Defensive rotation over 6h"

    # Operations (cron jobs)
    cron_jobs: list[CronJobDetail]
    crons_healthy: int
    crons_with_errors: int
    crons_stale: int  # Haven't run when expected
    next_scheduled_job: str
    next_scheduled_time: str

    # Portfolio detail
    positions: list[PositionDetail]
    thesis_exposures: list[ThesisExposure]
    sector_breakdown: dict[str, float]  # Sector -> weight %
    portfolio_value: float
    cash_available: float
    day_pnl: float
    day_pnl_pct: float
    max_position_weight: float
    concentration_warning: bool

    # Layer-by-layer status
    layers: dict[str, LayerStatus]
    overall_health: float  # 0-100 score

    # System info
    disk_space_pct: float
    memory_pct: float
    active_alerts: list[dict]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "claude_activity": self.claude_activity.to_dict() if self.claude_activity else None,
            "market_themes": {
                "current": self.current_theme.to_dict() if self.current_theme else None,
                "history": [t.to_dict() for t in self.theme_history[-12:]],  # Last 12 snapshots
                "change_summary": self.theme_change_summary,
            },
            "operations": {
                "cron_jobs": [c.to_dict() for c in self.cron_jobs],
                "crons_healthy": self.crons_healthy,
                "crons_with_errors": self.crons_with_errors,
                "crons_stale": self.crons_stale,
                "next_scheduled": {
                    "job": self.next_scheduled_job,
                    "time": self.next_scheduled_time,
                },
            },
            "portfolio": {
                "value": round(self.portfolio_value, 2),
                "cash": round(self.cash_available, 2),
                "day_pnl": round(self.day_pnl, 2),
                "day_pnl_pct": round(self.day_pnl_pct, 4),
                "positions": [p.to_dict() for p in self.positions],
                "thesis_exposures": [t.to_dict() for t in self.thesis_exposures],
                "sector_breakdown": {k: round(v, 2) for k, v in self.sector_breakdown.items()},
                "max_position_weight": round(self.max_position_weight, 2),
                "concentration_warning": self.concentration_warning,
            },
            "layers": {name: layer.to_dict() for name, layer in self.layers.items()},
            "overall_health": round(self.overall_health, 1),
            "system": {
                "disk_space_pct": round(self.disk_space_pct, 1),
                "memory_pct": round(self.memory_pct, 1),
                "active_alerts": self.active_alerts,
            },
        }


class ComprehensiveDashboard:
    """
    Comprehensive dashboard with historical tracking and detailed status.

    Features:
    - Market theme tracking over time (shows rotation patterns)
    - Complete cron job inventory with schedule/status
    - Position-by-position portfolio detail
    - Layer-by-layer health status
    """

    # Known cron jobs from setup_cron.sh
    EXPECTED_CRON_JOBS = [
        {
            "name": "trading_day_start",
            "description": "Pre-market prep at 6:00 AM ET",
            "schedule": "0 6 * * 1-5",
            "script": "trading_day.sh start",
            "log": "cron.log",
        },
        {
            "name": "state_update",
            "description": "Update state every 5 min during market hours",
            "schedule": "*/5 6-16 * * 1-5",
            "script": "trading_day.sh update",
            "log": "cron.log",
        },
        {
            "name": "trading_day_end",
            "description": "Stop daemons at 5 PM ET",
            "schedule": "0 17 * * 1-5",
            "script": "trading_day.sh stop",
            "log": "cron.log",
        },
        {
            "name": "squeeze_scan",
            "description": "Daily squeeze scan at 6:30 AM ET",
            "schedule": "30 6 * * 1-5",
            "script": "cron_squeeze_scan.py",
            "log": "squeeze_scan.log",
        },
        {
            "name": "news_collection",
            "description": "News collection every 30 min",
            "schedule": "*/30 6-17 * * 1-5",
            "script": "cron_news_collect_fast.py",
            "log": "news_fast.log",
        },
        {
            "name": "signpost_monitor",
            "description": "Check price signposts every 10 min",
            "schedule": "*/10 9-15 * * 1-5",
            "script": "signpost_monitor.py",
            "log": "signpost.log",
        },
        {
            "name": "scheduled_trades",
            "description": "Execute scheduled trades at 9:31 AM ET",
            "schedule": "31 9 * * 1-5",
            "script": "cron_trade_wrapper.sh",
            "log": "scheduled_trades.log",
        },
        {
            "name": "data_collection",
            "description": "Collect all data sources every 30 min",
            "schedule": "*/30 6-17 * * 1-5",
            "script": "collect_all_data.py",
            "log": "collection.log",
        },
        {
            "name": "sector_rotation",
            "description": "Analyze sector rotation hourly",
            "schedule": "0 7-16 * * 1-5",
            "script": "sector_rotation analysis",
            "log": "sector_rotation.log",
        },
        {
            "name": "legal_geopolitical",
            "description": "Check legal/geopolitical events every 2h",
            "schedule": "0 6,8,10,12,14,16 * * 1-5",
            "script": "legal + geopolitical trackers",
            "log": "legal_geo.log",
        },
        {
            "name": "weekly_review",
            "description": "Weekly improvement review Sunday 6 PM",
            "schedule": "0 18 * * 0",
            "script": "cron_weekly_improvement_review.py",
            "log": "weekly_review.log",
        },
        {
            "name": "signal_archive",
            "description": "Archive daily signals at 5:30 PM ET",
            "schedule": "30 17 * * 1-5",
            "script": "archive_daily_signals.py",
            "log": "signal_archive.log",
        },
        {
            "name": "day_trading_signals",
            "description": "Scan for day trading signals every 5 min",
            "schedule": "*/5 9-15 * * 1-5",
            "script": "run_day_trading_signals.py",
            "log": "day_trading_signals.log",
        },
    ]

    # Sector ETF mappings
    SECTOR_ETFS = {
        "XLK": "Technology",
        "XLF": "Financials",
        "XLE": "Energy",
        "XLV": "Healthcare",
        "XLI": "Industrials",
        "XLY": "Consumer Discretionary",
        "XLP": "Consumer Staples",
        "XLU": "Utilities",
        "XLB": "Materials",
        "XLRE": "Real Estate",
        "XLC": "Communication Services",
        "GLD": "Gold",
        "SLV": "Silver",
        "USO": "Oil",
        "TLT": "Long-Term Treasuries",
    }

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or paths.base
        self.live_dir = self.results_dir / "live"
        self.logs_dir = self.results_dir / "logs"
        self.theses_dir = self.results_dir / "theses"
        self.history_file = self.live_dir / "theme_history.json"
        self.scripts_dir = Path.home() / "projects" / "quant_suite" / "scripts"

    def _get_claude_activity(self) -> ClaudeActivity:
        """Get Claude's current activity from agent monitor and operator loop."""
        now = datetime.now()
        today = now.date()

        # Read agent activity log
        activity_log = self.logs_dir / "agent_activity.jsonl"
        running_agents = []
        recent_completions = []
        recent_decisions = []
        agents_completed_today = 0
        agents_failed_today = 0
        decisions_today = 0
        tokens_today = 0
        session_id = None
        session_start = None

        if activity_log.exists():
            try:
                with open(activity_log) as f:
                    lines = f.readlines()

                # Parse last 200 lines for efficiency
                for line in lines[-200:]:
                    try:
                        record = json.loads(line.strip())
                        timestamp = datetime.fromisoformat(record.get("timestamp", ""))
                        record_date = timestamp.date()

                        if record.get("type") == "agent_start":
                            if record.get("status") == "running":
                                # Check if still running (no completion within 10 lines)
                                running_agents.append({
                                    "agent_id": record.get("agent_id", ""),
                                    "agent_type": record.get("agent_type", "unknown"),
                                    "task": record.get("task", "")[:80],
                                    "started_at": timestamp.isoformat(),
                                    "duration_seconds": (now - timestamp).total_seconds(),
                                })

                            # Track session
                            if record.get("agent_type") == "claude_code":
                                session_id = record.get("agent_id")
                                session_start = timestamp

                        elif record.get("type") == "agent_complete":
                            # Remove from running
                            agent_id = record.get("agent_id", "")
                            running_agents = [a for a in running_agents if a["agent_id"] != agent_id]

                            # Count today's completions
                            if record_date == today:
                                if record.get("status") == "completed":
                                    agents_completed_today += 1
                                elif record.get("status") == "failed":
                                    agents_failed_today += 1
                                tokens_today += record.get("tokens_used", 0)

                            # Recent completions
                            recent_completions.append({
                                "agent_id": agent_id,
                                "agent_type": record.get("agent_type", "unknown"),
                                "status": record.get("status", "completed"),
                                "result": record.get("result_summary", "")[:60],
                                "completed_at": timestamp.isoformat(),
                            })

                        elif record.get("type") == "decision":
                            if record_date == today:
                                decisions_today += 1
                            recent_decisions.append({
                                "symbol": record.get("symbol", ""),
                                "action": record.get("action", ""),
                                "confidence": record.get("confidence", 0),
                                "timestamp": timestamp.isoformat(),
                            })

                    except (json.JSONDecodeError, ValueError):
                        continue

            except Exception as e:
                logger.error(f"Error reading agent activity: {e}")

        # Keep only recent items
        recent_completions = recent_completions[-5:]
        recent_decisions = recent_decisions[-5:]

        # Get action items from operator log
        action_items = []
        research_suggestions = []
        operator_log = self.logs_dir / "operator_log.jsonl"

        if operator_log.exists():
            try:
                with open(operator_log) as f:
                    lines = f.readlines()
                    if lines:
                        # Get most recent observation
                        last_obs = json.loads(lines[-1].strip())
                        action_items = last_obs.get("action_items", [])
                        research_suggestions = [
                            s.get("suggestion", s) if isinstance(s, dict) else s
                            for s in last_obs.get("research_suggestions", [])
                        ]
            except Exception as e:
                logger.error(f"Error reading operator log: {e}")

        # Get active research cycle
        active_research = None
        research_tracker = self.results_dir / "research" / "session_tracker.json"
        if research_tracker.exists():
            try:
                with open(research_tracker) as f:
                    data = json.load(f)
                    cycles = data.get("research_cycles", [])
                    for cycle in reversed(cycles):
                        if cycle.get("status") == "running":
                            active_research = {
                                "cycle_id": cycle.get("cycle_id", ""),
                                "experiments": cycle.get("experiments_run", 0),
                                "insights": cycle.get("insights_found", 0),
                                "best_sharpe": cycle.get("best_sharpe"),
                            }
                            break
            except Exception:
                pass

        # Calculate session duration
        session_duration = 0.0
        if session_start:
            session_duration = (now - session_start).total_seconds() / 60

        return ClaudeActivity(
            session_active=len(running_agents) > 0 or session_start is not None,
            session_id=session_id,
            session_duration_min=session_duration,
            agents_running=len(running_agents),
            agents_completed_today=agents_completed_today,
            agents_failed_today=agents_failed_today,
            decisions_today=decisions_today,
            tokens_used_today=tokens_today,
            running_agents=running_agents[-3:],  # Show last 3 running
            recent_completions=recent_completions,
            recent_decisions=recent_decisions,
            active_research_cycle=active_research,
            action_items=action_items[:5],
            research_suggestions=research_suggestions[:3],
        )

    async def get_comprehensive_status(self) -> ComprehensiveStatus:
        """Get complete system status with all details."""
        now = datetime.now()

        # Get Claude's activity first (shows what Claude is doing)
        claude_activity = self._get_claude_activity()

        # Load state
        state = self._load_json(self.live_dir / "state.json")

        # Get market theme
        current_theme = self._get_current_theme(state)
        theme_history = self._load_theme_history()

        # Save current theme to history
        if current_theme:
            self._save_theme_snapshot(current_theme)

        theme_change = self._analyze_theme_changes(theme_history, current_theme)

        # Get cron status
        cron_jobs = await self._get_cron_details()
        crons_healthy = sum(1 for c in cron_jobs if c.last_status == "success")
        crons_errors = sum(1 for c in cron_jobs if c.last_status == "error")
        crons_stale = sum(1 for c in cron_jobs if c.last_status == "stale")

        # Find next scheduled job
        next_job = None
        next_time = None
        for job in sorted(cron_jobs, key=lambda j: j.next_scheduled or datetime.max):
            if job.next_scheduled and job.next_scheduled > now:
                next_job = job.name
                next_time = job.next_scheduled.strftime("%H:%M")
                break

        # Get portfolio detail
        positions = self._get_position_details(state)
        thesis_exposures = self._get_thesis_exposures(state)
        sector_breakdown = self._get_sector_breakdown(positions)

        portfolio = state.get("portfolio", {})
        portfolio_value = portfolio.get("equity", 0)
        cash = portfolio.get("cash", 0)
        day_pnl = portfolio.get("day_pnl", 0)
        day_pnl_pct = portfolio.get("day_pnl_pct", 0) / 100 if portfolio.get("day_pnl_pct") else 0

        max_weight = max((p.weight_pct for p in positions), default=0)
        concentration_warning = max_weight > 15  # Warn if any position > 15%

        # Get layer status
        layers = await self._get_layer_status(state)
        overall_health = sum(l.health_score for l in layers.values()) / max(len(layers), 1)

        # System metrics
        disk_pct = self._get_disk_space()
        memory_pct = self._get_memory_usage()
        alerts = state.get("alerts", [])

        return ComprehensiveStatus(
            timestamp=now,
            claude_activity=claude_activity,
            current_theme=current_theme,
            theme_history=theme_history,
            theme_change_summary=theme_change,
            cron_jobs=cron_jobs,
            crons_healthy=crons_healthy,
            crons_with_errors=crons_errors,
            crons_stale=crons_stale,
            next_scheduled_job=next_job or "None",
            next_scheduled_time=next_time or "N/A",
            positions=positions,
            thesis_exposures=thesis_exposures,
            sector_breakdown=sector_breakdown,
            portfolio_value=portfolio_value,
            cash_available=cash,
            day_pnl=day_pnl,
            day_pnl_pct=day_pnl_pct,
            max_position_weight=max_weight,
            concentration_warning=concentration_warning,
            layers=layers,
            overall_health=overall_health,
            disk_space_pct=disk_pct,
            memory_pct=memory_pct,
            active_alerts=alerts,
        )

    def _load_json(self, path: Path) -> dict:
        """Load JSON file safely."""
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
        return {}

    def _get_current_theme(self, state: dict) -> MarketThemeSnapshot | None:
        """Determine current market theme from state."""
        market = state.get("market", {})
        sentiment = state.get("sentiment", {})

        if not market:
            return None

        vix = market.get("vix", 15)
        spy_change = market.get("spy_change_pct", 0)

        # Get sector performance
        sectors = market.get("sectors", {})
        sector_perf = [(s, d.get("change_pct", 0)) for s, d in sectors.items() if isinstance(d, dict)]
        sector_perf.sort(key=lambda x: x[1], reverse=True)

        leaders = [s[0] for s in sector_perf[:3]] if sector_perf else []
        laggards = [s[0] for s in sector_perf[-3:]] if sector_perf else []

        # Determine themes
        theme_signals = []
        secondary = []

        # Primary theme determination
        if vix > 25:
            primary = MarketTheme.VOLATILITY_EXPANSION.value
            theme_signals.append(f"VIX elevated: {vix:.1f}")
        elif abs(spy_change) > 1.5:
            if spy_change > 0:
                primary = MarketTheme.BROAD_RALLY.value
                theme_signals.append(f"SPY +{spy_change:.1f}%")
            else:
                primary = MarketTheme.BROAD_SELLOFF.value
                theme_signals.append(f"SPY {spy_change:.1f}%")
        elif leaders and "XLK" in leaders[:2]:
            primary = MarketTheme.ROTATION_TECH.value
            theme_signals.append("Tech leading")
        elif leaders and any(s in leaders[:2] for s in ["XLU", "XLP", "XLV"]):
            primary = MarketTheme.ROTATION_DEFENSIVE.value
            theme_signals.append("Defensive sectors leading")
        elif leaders and any(s in leaders[:2] for s in ["XLI", "XLF", "XLE"]):
            primary = MarketTheme.ROTATION_CYCLICAL.value
            theme_signals.append("Cyclicals leading")
        else:
            primary = MarketTheme.RISK_ON.value if spy_change > 0 else MarketTheme.RISK_OFF.value

        # Secondary themes
        if vix < 15 and primary != MarketTheme.VOLATILITY_COMPRESSION.value:
            secondary.append(MarketTheme.VOLATILITY_COMPRESSION.value)
            theme_signals.append(f"VIX compressed: {vix:.1f}")

        fear_greed = sentiment.get("fear_greed_value", 50)
        if fear_greed < 25:
            secondary.append("extreme_fear")
            theme_signals.append(f"Fear & Greed: {fear_greed}")
        elif fear_greed > 75:
            secondary.append("extreme_greed")
            theme_signals.append(f"Fear & Greed: {fear_greed}")

        # Calculate breadth
        advancing = market.get("advancing", 0)
        declining = market.get("declining", 0)
        breadth = advancing / (declining + 1)

        return MarketThemeSnapshot(
            timestamp=datetime.now(),
            primary_theme=primary,
            secondary_themes=secondary,
            theme_signals=theme_signals,
            sector_leaders=leaders,
            sector_laggards=laggards,
            vix=vix,
            spy_change_pct=spy_change,
            breadth_ratio=breadth,
            fear_greed=fear_greed,
        )

    def _load_theme_history(self) -> list[MarketThemeSnapshot]:
        """Load theme history from file."""
        history = []
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    data = json.load(f)
                    for item in data.get("snapshots", [])[-48:]:  # Last 48 snapshots (24h at 30min intervals)
                        try:
                            history.append(MarketThemeSnapshot(
                                timestamp=datetime.fromisoformat(item["timestamp"]),
                                primary_theme=item["primary_theme"],
                                secondary_themes=item.get("secondary_themes", []),
                                theme_signals=item.get("theme_signals", []),
                                sector_leaders=item.get("sector_leaders", []),
                                sector_laggards=item.get("sector_laggards", []),
                                vix=item.get("vix", 15),
                                spy_change_pct=item.get("spy_change_pct", 0),
                                breadth_ratio=item.get("breadth_ratio", 1),
                                fear_greed=item.get("fear_greed", 50),
                            ))
                        except Exception:
                            continue
            except Exception as e:
                logger.error(f"Error loading theme history: {e}")
        return history

    def _save_theme_snapshot(self, theme: MarketThemeSnapshot) -> None:
        """Save theme snapshot to history."""
        try:
            history = []
            if self.history_file.exists():
                with open(self.history_file) as f:
                    data = json.load(f)
                    history = data.get("snapshots", [])

            # Add new snapshot
            history.append(theme.to_dict())

            # Keep only last 48 snapshots
            history = history[-48:]

            # Save
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w") as f:
                json.dump({"snapshots": history}, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving theme snapshot: {e}")

    def _analyze_theme_changes(
        self,
        history: list[MarketThemeSnapshot],
        current: MarketThemeSnapshot | None,
    ) -> str:
        """Analyze how themes have changed over time."""
        if not history or not current:
            return "Insufficient history for trend analysis"

        # Get themes from last 6h, 12h, 24h
        now = datetime.now()
        themes_6h = [t for t in history if now - t.timestamp < timedelta(hours=6)]
        themes_12h = [t for t in history if now - t.timestamp < timedelta(hours=12)]

        if not themes_6h:
            return "No recent theme data"

        # Count theme occurrences
        theme_counts = {}
        for t in themes_6h:
            theme_counts[t.primary_theme] = theme_counts.get(t.primary_theme, 0) + 1

        # Find dominant theme in recent history
        prev_theme = max(theme_counts.keys(), key=lambda k: theme_counts[k]) if theme_counts else None

        if prev_theme and prev_theme != current.primary_theme:
            return f"{prev_theme.replace('_', ' ').title()} -> {current.primary_theme.replace('_', ' ').title()} (changed in last 6h)"
        elif current.primary_theme:
            duration = len(themes_6h) * 30  # Approximate minutes
            return f"{current.primary_theme.replace('_', ' ').title()} (stable for ~{duration}min)"
        else:
            return "Theme unclear"

    async def _get_cron_details(self) -> list[CronJobDetail]:
        """Get detailed cron job status."""
        jobs = []
        now = datetime.now()
        today = now.date()

        for job_info in self.EXPECTED_CRON_JOBS:
            name = job_info["name"]
            schedule = job_info["schedule"]
            log_file = job_info["log"]

            log_path = self.logs_dir / log_file
            last_run = None
            last_status = "unknown"
            runs_today = 0
            errors_today = 0

            # Check log file
            if log_path.exists():
                try:
                    mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
                    last_run = mtime

                    # Read last lines to check for errors
                    with open(log_path, "rb") as f:
                        f.seek(0, 2)
                        size = f.tell()
                        f.seek(max(0, size - 5000))
                        content = f.read().decode("utf-8", errors="ignore")

                    lines = content.split("\n")
                    today_str = today.isoformat()

                    for line in lines:
                        if today_str in line:
                            runs_today += 1
                            if "error" in line.lower() or "exception" in line.lower():
                                errors_today += 1

                    # Check recent lines for errors
                    recent_lines = lines[-20:]
                    has_error = any("error" in l.lower() or "exception" in l.lower() for l in recent_lines)
                    last_status = "error" if has_error else "success"

                except Exception as e:
                    logger.error(f"Error reading log {log_path}: {e}")

            # Check if stale (should have run but hasn't)
            expected_interval = self._parse_cron_interval(schedule)
            if last_run and expected_interval:
                since_last = now - last_run
                if since_last > expected_interval * 2:
                    last_status = "stale"

            # Calculate next scheduled
            next_scheduled = self._get_next_cron_time(schedule, now)

            jobs.append(CronJobDetail(
                name=name,
                description=job_info["description"],
                schedule_cron=schedule,
                schedule_human=self._cron_to_human(schedule),
                script_path=job_info["script"],
                log_file=str(log_path),
                last_run=last_run,
                last_run_ago=self._time_ago(last_run),
                last_status=last_status,
                last_duration_sec=None,
                next_scheduled=next_scheduled,
                runs_today=runs_today,
                errors_today=errors_today,
                enabled=True,
            ))

        return jobs

    def _parse_cron_interval(self, schedule: str) -> timedelta | None:
        """Parse cron schedule to get expected interval."""
        parts = schedule.split()
        if len(parts) < 5:
            return None

        minute = parts[0]
        hour = parts[1]

        if minute.startswith("*/"):
            mins = int(minute[2:])
            return timedelta(minutes=mins)
        elif hour.startswith("*/"):
            hours = int(hour[2:])
            return timedelta(hours=hours)
        else:
            return timedelta(hours=24)  # Daily

    def _cron_to_human(self, schedule: str) -> str:
        """Convert cron expression to human readable."""
        parts = schedule.split()
        if len(parts) < 5:
            return schedule

        minute, hour, dom, month, dow = parts[:5]

        result = []

        if minute.startswith("*/"):
            result.append(f"Every {minute[2:]} min")
        elif "," in minute:
            result.append(f"At :{minute}")
        elif minute != "*":
            result.append(f"At :{minute.zfill(2)}")

        if hour.startswith("*/"):
            result.append(f"every {hour[2:]}h")
        elif "-" in hour:
            start, end = hour.split("-")
            result.append(f"{start}:00-{end}:00")
        elif "," in hour:
            result.append(f"at {hour}:00")
        elif hour != "*":
            result.append(f"at {hour.zfill(2)}:00")

        if dow == "1-5":
            result.append("Mon-Fri")
        elif dow == "0":
            result.append("Sundays")
        elif dow != "*":
            result.append(f"days {dow}")

        return " ".join(result) if result else schedule

    def _get_next_cron_time(self, schedule: str, now: datetime) -> datetime | None:
        """Estimate next cron execution time."""
        parts = schedule.split()
        if len(parts) < 5:
            return None

        minute = parts[0]
        hour = parts[1]
        dow = parts[4]

        next_time = now

        # Simple estimation for common patterns
        if minute.startswith("*/"):
            interval = int(minute[2:])
            next_min = ((now.minute // interval) + 1) * interval
            if next_min >= 60:
                next_time = next_time.replace(minute=next_min % 60, second=0, microsecond=0)
                next_time += timedelta(hours=1)
            else:
                next_time = next_time.replace(minute=next_min, second=0, microsecond=0)
        elif minute != "*":
            target_min = int(minute.split(",")[0])
            if now.minute >= target_min:
                next_time += timedelta(hours=1)
            next_time = next_time.replace(minute=target_min, second=0, microsecond=0)

        # Check hour constraints
        if "-" in hour:
            start, end = map(int, hour.split("-"))
            if next_time.hour < start:
                next_time = next_time.replace(hour=start)
            elif next_time.hour > end:
                next_time += timedelta(days=1)
                next_time = next_time.replace(hour=start, minute=0)

        return next_time

    def _time_ago(self, dt: datetime | None) -> str:
        """Convert datetime to human-readable 'X ago' string."""
        if dt is None:
            return "never"

        delta = datetime.now() - dt
        if delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes}m ago"
        else:
            return "just now"

    def _get_position_details(self, state: dict) -> list[PositionDetail]:
        """Get detailed position information."""
        positions = []
        raw_positions = state.get("positions", [])
        portfolio = state.get("portfolio", {})
        total_value = portfolio.get("equity", 1)

        # Load theses for mapping
        symbol_thesis = {}
        if self.theses_dir.exists():
            for thesis_file in self.theses_dir.glob("*.yaml"):
                try:
                    with open(thesis_file) as f:
                        thesis = yaml.safe_load(f)
                        if thesis.get("status") == "active":
                            for sym in thesis.get("positions", []):
                                symbol_thesis[sym] = thesis.get("name", "Unknown")
                except:
                    continue

        # Load signals for alignment check
        signals_file = self.live_dir / "research" / "signals.json"
        signals = {}
        if signals_file.exists():
            try:
                with open(signals_file) as f:
                    signals = json.load(f)
            except:
                pass

        for pos in raw_positions:
            symbol = pos.get("symbol", "")
            market_value = pos.get("market_value", 0)

            # Calculate weight
            weight = (market_value / total_value * 100) if total_value > 0 else 0

            # Check signal alignment
            sig_data = signals.get(symbol, {})
            composite = sig_data.get("composite_score", 0) if isinstance(sig_data, dict) else 0
            aligned = 1 if composite > 0.2 else 0

            # Get sector
            sector = self.SECTOR_ETFS.get(symbol)
            if not sector and "-" not in symbol:
                # Try to infer sector (would need more data)
                sector = "Unknown"

            # Calculate risk score (placeholder - would use more data)
            risk_score = min(1.0, weight / 20)  # Higher weight = higher risk

            positions.append(PositionDetail(
                symbol=symbol,
                quantity=pos.get("quantity", 0),
                avg_cost=pos.get("avg_cost", 0),
                market_price=pos.get("current_price", 0),
                market_value=market_value,
                day_pnl=pos.get("day_pnl", 0),
                day_pnl_pct=pos.get("day_pnl_pct", 0) / 100 if pos.get("day_pnl_pct") else 0,
                total_pnl=pos.get("unrealized_pnl", 0),
                total_pnl_pct=pos.get("unrealized_pnl_pct", 0) / 100 if pos.get("unrealized_pnl_pct") else 0,
                weight_pct=weight,
                thesis_name=symbol_thesis.get(symbol),
                sector=sector,
                days_held=pos.get("days_held", 0),
                signals_aligned=aligned,
                risk_score=risk_score,
                notes="",
            ))

        # Sort by weight descending
        positions.sort(key=lambda p: p.weight_pct, reverse=True)
        return positions

    def _get_thesis_exposures(self, state: dict) -> list[ThesisExposure]:
        """Get thesis-level exposure summary."""
        exposures = []
        positions = {p.get("symbol"): p for p in state.get("positions", [])}
        portfolio = state.get("portfolio", {})
        total_value = portfolio.get("equity", 1)

        if not self.theses_dir.exists():
            return exposures

        for thesis_file in self.theses_dir.glob("*.yaml"):
            try:
                with open(thesis_file) as f:
                    thesis = yaml.safe_load(f)

                if thesis.get("status") != "active":
                    continue

                thesis_id = thesis.get("id", thesis_file.stem)
                thesis_name = thesis.get("name", "Unknown")
                conviction = thesis.get("conviction", 50)
                thesis_positions = thesis.get("positions", [])

                # Calculate exposure
                value = 0
                day_pnl = 0
                total_pnl = 0
                symbols = []
                perf_by_symbol = {}

                for sym in thesis_positions:
                    if sym in positions:
                        pos = positions[sym]
                        value += pos.get("market_value", 0)
                        day_pnl += pos.get("day_pnl", 0)
                        total_pnl += pos.get("unrealized_pnl", 0)
                        symbols.append(sym)
                        perf_by_symbol[sym] = pos.get("day_pnl_pct", 0)

                if not symbols:
                    continue

                # Find best/worst performers
                sorted_perf = sorted(perf_by_symbol.items(), key=lambda x: x[1], reverse=True)
                top = sorted_perf[0][0] if sorted_perf else None
                worst = sorted_perf[-1][0] if sorted_perf else None

                # Count signposts triggered
                signposts = thesis.get("signposts", [])
                triggered = sum(1 for s in signposts if s.get("triggered", False))

                # Calculate days active
                created_at = thesis.get("created_at")
                days_active = 0
                if created_at:
                    try:
                        created = datetime.fromisoformat(created_at)
                        days_active = (datetime.now() - created).days
                    except:
                        pass

                # Determine status
                if total_pnl > 0 and day_pnl > 0:
                    status = "exceeding"
                elif total_pnl < 0 and conviction < 50:
                    status = "at_risk"
                else:
                    status = "on_track"

                weight = (value / total_value * 100) if total_value > 0 else 0

                exposures.append(ThesisExposure(
                    thesis_id=thesis_id,
                    thesis_name=thesis_name,
                    conviction=conviction,
                    value=value,
                    weight_pct=weight,
                    day_pnl=day_pnl,
                    total_pnl=total_pnl,
                    position_count=len(symbols),
                    symbols=symbols,
                    top_performer=top,
                    worst_performer=worst,
                    signposts_triggered=triggered,
                    days_active=days_active,
                    status=status,
                ))

            except Exception as e:
                logger.error(f"Error loading thesis {thesis_file}: {e}")

        # Sort by value descending
        exposures.sort(key=lambda e: e.value, reverse=True)
        return exposures

    def _get_sector_breakdown(self, positions: list[PositionDetail]) -> dict[str, float]:
        """Get portfolio breakdown by sector."""
        sectors = {}
        for pos in positions:
            sector = pos.sector or "Unknown"
            sectors[sector] = sectors.get(sector, 0) + pos.weight_pct
        return dict(sorted(sectors.items(), key=lambda x: x[1], reverse=True))

    async def _get_layer_status(self, state: dict) -> dict[str, LayerStatus]:
        """Get status of each system layer."""
        layers = {}
        now = datetime.now()

        # Data Layer
        data_status = await self._check_data_layer(state)
        layers["data"] = data_status

        # Signal Layer
        signal_status = self._check_signal_layer(state)
        layers["signals"] = signal_status

        # Agent Layer
        agent_status = self._check_agent_layer()
        layers["agents"] = agent_status

        # Research Layer
        research_status = self._check_research_layer()
        layers["research"] = research_status

        # Execution Layer
        execution_status = self._check_execution_layer(state)
        layers["execution"] = execution_status

        # Risk Layer
        risk_status = self._check_risk_layer(state)
        layers["risk"] = risk_status

        return layers

    async def _check_data_layer(self, state: dict) -> LayerStatus:
        """Check data layer health."""
        components = {}
        alerts = []
        health = 100

        # Check state freshness
        state_file = self.live_dir / "state.json"
        if state_file.exists():
            mtime = datetime.fromtimestamp(state_file.stat().st_mtime)
            age_min = (datetime.now() - mtime).total_seconds() / 60
            if age_min < 10:
                components["state.json"] = "fresh"
            elif age_min < 30:
                components["state.json"] = "stale"
                health -= 20
            else:
                components["state.json"] = "critical"
                alerts.append(f"State file not updated in {int(age_min)}min")
                health -= 40
        else:
            components["state.json"] = "missing"
            alerts.append("State file missing")
            health -= 50

        # Check data sources from state
        sources_checked = 0
        sources_healthy = 0

        try:
            from src.monitoring.data_freshness_tracker import get_data_freshness
            freshness = get_data_freshness()
            sources_checked = freshness.total_sources
            sources_healthy = freshness.healthy_sources

            if freshness.stale_sources > 3:
                alerts.append(f"{freshness.stale_sources} data sources stale")
                health -= freshness.stale_sources * 5
        except Exception:
            pass

        components["sources"] = f"{sources_healthy}/{sources_checked} healthy"

        status = "healthy" if health >= 80 else "degraded" if health >= 50 else "critical"

        return LayerStatus(
            name="Data Layer",
            status=status,
            health_score=max(0, health),
            components=components,
            metrics={
                "sources_checked": sources_checked,
                "sources_healthy": sources_healthy,
            },
            last_update=datetime.fromtimestamp(state_file.stat().st_mtime) if state_file.exists() else None,
            last_update_ago=self._time_ago(datetime.fromtimestamp(state_file.stat().st_mtime)) if state_file.exists() else "never",
            alerts=alerts,
        )

    def _check_signal_layer(self, state: dict) -> LayerStatus:
        """Check signal layer health."""
        components = {}
        alerts = []
        health = 100

        signals = state.get("signals", {})
        watchlist = signals.get("watchlist", [])

        components["active_signals"] = str(len(watchlist))

        # Check for convergences
        signals_file = self.live_dir / "research" / "signals.json"
        if signals_file.exists():
            try:
                with open(signals_file) as f:
                    sig_data = json.load(f)
                components["symbols_covered"] = str(len(sig_data))
            except:
                pass
        else:
            components["signals.json"] = "missing"
            health -= 20

        status = "healthy" if health >= 80 else "degraded" if health >= 50 else "critical"

        return LayerStatus(
            name="Signal Layer",
            status=status,
            health_score=max(0, health),
            components=components,
            metrics={
                "active_signals": len(watchlist),
            },
            last_update=None,
            last_update_ago="N/A",
            alerts=alerts,
        )

    def _check_agent_layer(self) -> LayerStatus:
        """Check agent layer health."""
        components = {}
        alerts = []
        health = 100

        # Check agent activity log
        activity_log = self.logs_dir / "agent_activity.jsonl"
        today = datetime.now().date().isoformat()

        agents_today = 0
        if activity_log.exists():
            try:
                with open(activity_log) as f:
                    for line in f:
                        if today in line:
                            agents_today += 1
            except:
                pass

        components["agents_today"] = str(agents_today)

        status = "healthy" if agents_today > 0 else "degraded"
        if agents_today == 0:
            health -= 20

        return LayerStatus(
            name="Agent Layer",
            status=status,
            health_score=max(0, health),
            components=components,
            metrics={
                "agents_today": agents_today,
            },
            last_update=datetime.fromtimestamp(activity_log.stat().st_mtime) if activity_log.exists() else None,
            last_update_ago=self._time_ago(datetime.fromtimestamp(activity_log.stat().st_mtime)) if activity_log.exists() else "never",
            alerts=alerts,
        )

    def _check_research_layer(self) -> LayerStatus:
        """Check research layer health."""
        components = {}
        alerts = []
        health = 100

        tracker_file = self.results_dir / "research" / "session_tracker.json"

        if tracker_file.exists():
            try:
                with open(tracker_file) as f:
                    data = json.load(f)

                experiments = len(data.get("experiments", []))
                insights = len(data.get("insights", []))
                validated = data.get("strategies_validated", 0)

                components["experiments"] = str(experiments)
                components["insights"] = str(insights)
                components["validated"] = str(validated)
            except:
                pass
        else:
            components["tracker"] = "missing"
            health -= 10

        status = "healthy" if health >= 80 else "degraded"

        return LayerStatus(
            name="Research Layer",
            status=status,
            health_score=max(0, health),
            components=components,
            metrics={},
            last_update=datetime.fromtimestamp(tracker_file.stat().st_mtime) if tracker_file.exists() else None,
            last_update_ago=self._time_ago(datetime.fromtimestamp(tracker_file.stat().st_mtime)) if tracker_file.exists() else "never",
            alerts=alerts,
        )

    def _check_execution_layer(self, state: dict) -> LayerStatus:
        """Check execution layer health."""
        components = {}
        alerts = []
        health = 100

        portfolio = state.get("portfolio", {})
        positions = state.get("positions", [])

        components["positions"] = str(len(positions))
        components["cash"] = f"${portfolio.get('cash', 0):,.0f}"

        # Check PDT status
        pdt_file = self.results_dir / "pdt_status.json"
        if pdt_file.exists():
            try:
                with open(pdt_file) as f:
                    pdt = json.load(f)
                trades_used = pdt.get("trades_used", 0)
                components["pdt_trades"] = f"{trades_used}/3"
                if trades_used >= 3:
                    alerts.append("PDT limit reached")
                    health -= 30
            except:
                pass

        status = "healthy" if health >= 80 else "degraded" if health >= 50 else "critical"

        return LayerStatus(
            name="Execution Layer",
            status=status,
            health_score=max(0, health),
            components=components,
            metrics={
                "position_count": len(positions),
            },
            last_update=None,
            last_update_ago="N/A",
            alerts=alerts,
        )

    def _check_risk_layer(self, state: dict) -> LayerStatus:
        """Check risk layer health."""
        components = {}
        alerts = []
        health = 100

        portfolio = state.get("portfolio", {})
        positions = state.get("positions", [])
        total_value = portfolio.get("equity", 1)

        # Check concentration
        max_conc = 0
        for pos in positions:
            weight = pos.get("market_value", 0) / total_value * 100 if total_value > 0 else 0
            max_conc = max(max_conc, weight)

        components["max_concentration"] = f"{max_conc:.1f}%"
        if max_conc > 20:
            alerts.append(f"High concentration: {max_conc:.1f}%")
            health -= 20

        # Check drawdown
        day_pnl_pct = portfolio.get("day_pnl_pct", 0)
        if day_pnl_pct < -3:
            alerts.append(f"Large daily loss: {day_pnl_pct:.1f}%")
            health -= 30
        elif day_pnl_pct < -1:
            health -= 10

        components["day_pnl"] = f"{day_pnl_pct:+.2f}%"

        status = "healthy" if health >= 80 else "degraded" if health >= 50 else "critical"

        return LayerStatus(
            name="Risk Layer",
            status=status,
            health_score=max(0, health),
            components=components,
            metrics={
                "max_concentration": max_conc,
                "day_pnl_pct": day_pnl_pct,
            },
            last_update=None,
            last_update_ago="N/A",
            alerts=alerts,
        )

    def _get_disk_space(self) -> float:
        """Get available disk space percentage."""
        try:
            statvfs = os.statvfs(str(self.results_dir))
            return statvfs.f_bavail / statvfs.f_blocks * 100
        except:
            return 100.0

    def _get_memory_usage(self) -> float:
        """Get memory usage percentage."""
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            mem_info = {}
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    mem_info[parts[0].rstrip(":")] = int(parts[1])
            total = mem_info.get("MemTotal", 1)
            available = mem_info.get("MemAvailable", total)
            return (1 - available / total) * 100
        except:
            return 0.0

    def print_dashboard(self, status: ComprehensiveStatus) -> None:
        """Print comprehensive dashboard to console."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            from rich.text import Text
            from rich.columns import Columns

            console = Console()

            # Header
            header = Text()
            header.append("COMPREHENSIVE TRADING DASHBOARD ", style="bold cyan")
            header.append("| ", style="dim")
            header.append(f"{status.timestamp.strftime('%Y-%m-%d %H:%M:%S')} ", style="white")
            header.append("| Health: ", style="dim")
            health_color = "green" if status.overall_health >= 80 else "yellow" if status.overall_health >= 50 else "red"
            header.append(f"{status.overall_health:.0f}%", style=f"bold {health_color}")

            console.print(Panel(header, border_style="cyan"))

            # Claude Activity Section (shows what Claude is doing)
            if status.claude_activity:
                claude = status.claude_activity
                claude_text = Text()

                # Session status
                if claude.session_active:
                    claude_text.append("SESSION ACTIVE", style="bold green")
                    if claude.session_id:
                        claude_text.append(f" ({claude.session_id})", style="dim")
                    claude_text.append(f" | {claude.session_duration_min:.0f}m\n", style="white")
                else:
                    claude_text.append("No active session\n", style="dim")

                # Running agents
                if claude.agents_running > 0:
                    claude_text.append(f"\nRUNNING NOW ({claude.agents_running}):\n", style="bold yellow")
                    for agent in claude.running_agents:
                        duration = agent.get("duration_seconds", 0)
                        mins = int(duration // 60)
                        secs = int(duration % 60)
                        claude_text.append(f"  [{agent.get('agent_type', 'unknown')[:8]}] ", style="cyan")
                        claude_text.append(f"{agent.get('task', '')[:50]} ", style="white")
                        claude_text.append(f"({mins}m {secs}s)\n", style="dim")
                else:
                    claude_text.append("\nNo agents currently running\n", style="dim")

                # Today's stats
                claude_text.append(f"\nTODAY: ", style="bold")
                claude_text.append(f"{claude.agents_completed_today} completed", style="green")
                if claude.agents_failed_today > 0:
                    claude_text.append(f", {claude.agents_failed_today} failed", style="red")
                claude_text.append(f" | {claude.decisions_today} decisions", style="white")
                if claude.tokens_used_today > 0:
                    claude_text.append(f" | {claude.tokens_used_today:,} tokens", style="dim")

                # Recent completions
                if claude.recent_completions:
                    claude_text.append(f"\n\nRECENT:\n", style="bold")
                    for comp in claude.recent_completions[-3:]:
                        status_color = "green" if comp.get("status") == "completed" else "red"
                        claude_text.append(f"  [{comp.get('status', '')[:4]}] ", style=status_color)
                        claude_text.append(f"{comp.get('agent_type', '')}: ", style="cyan")
                        claude_text.append(f"{comp.get('result', '')[:40]}\n", style="dim")

                # Action items from operator loop
                if claude.action_items:
                    claude_text.append(f"\nACTION ITEMS ({len(claude.action_items)}):\n", style="bold magenta")
                    for item in claude.action_items[:3]:
                        priority = item.get("priority", "low")
                        priority_style = "red" if priority == "high" else "yellow" if priority == "medium" else "dim"
                        claude_text.append(f"  [{priority.upper()[:3]}] ", style=priority_style)
                        claude_text.append(f"{item.get('action', '')[:50]}\n", style="white")

                # Research suggestions
                if claude.research_suggestions:
                    claude_text.append(f"\nRESEARCH IDEAS:\n", style="bold blue")
                    for sug in claude.research_suggestions[:2]:
                        claude_text.append(f"  - {sug[:60]}\n", style="dim")

                # Active research cycle
                if claude.active_research_cycle:
                    cycle = claude.active_research_cycle
                    claude_text.append(f"\nACTIVE RESEARCH: ", style="bold green")
                    claude_text.append(f"{cycle.get('experiments', 0)} experiments, ", style="white")
                    claude_text.append(f"{cycle.get('insights', 0)} insights", style="cyan")
                    if cycle.get('best_sharpe'):
                        claude_text.append(f", best Sharpe: {cycle['best_sharpe']:.2f}", style="green")
                    claude_text.append("\n", style="white")

                console.print(Panel(claude_text, title="Claude Activity", border_style="magenta"))

            # Market Theme Section
            if status.current_theme:
                theme = status.current_theme
                theme_text = Text()
                theme_text.append("Primary: ", style="dim")
                theme_text.append(f"{theme.primary_theme.replace('_', ' ').title()}\n", style="bold cyan")
                if theme.secondary_themes:
                    theme_text.append("Secondary: ", style="dim")
                    theme_text.append(f"{', '.join(theme.secondary_themes)}\n", style="yellow")
                theme_text.append("Signals: ", style="dim")
                theme_text.append(f"{' | '.join(theme.theme_signals[:3])}\n", style="white")
                theme_text.append("Leaders: ", style="dim")
                theme_text.append(f"{', '.join(theme.sector_leaders[:3])}", style="green")
                theme_text.append(" | Laggards: ", style="dim")
                theme_text.append(f"{', '.join(theme.sector_laggards[:3])}\n", style="red")
                theme_text.append("Trend: ", style="dim")
                theme_text.append(status.theme_change_summary, style="yellow")

                console.print(Panel(theme_text, title="Market Theme", border_style="cyan"))

            # Operations Section
            ops_text = Text()
            ops_text.append(f"Cron Jobs: ", style="dim")
            ops_text.append(f"{status.crons_healthy} healthy", style="green")
            ops_text.append(f", {status.crons_with_errors} errors", style="red" if status.crons_with_errors > 0 else "green")
            ops_text.append(f", {status.crons_stale} stale", style="yellow" if status.crons_stale > 0 else "green")
            ops_text.append(f"\nNext: ", style="dim")
            ops_text.append(f"{status.next_scheduled_job} at {status.next_scheduled_time}\n", style="white")

            # Show last 5 cron jobs with issues or recently run
            recent_jobs = sorted(
                [j for j in status.cron_jobs if j.last_run],
                key=lambda j: j.last_run,
                reverse=True
            )[:5]

            for job in recent_jobs:
                status_style = "green" if job.last_status == "success" else "red" if job.last_status == "error" else "yellow"
                ops_text.append(f"  [{job.last_status[:3]}] ", style=status_style)
                ops_text.append(f"{job.name}: ", style="white")
                ops_text.append(f"{job.last_run_ago}\n", style="dim")

            console.print(Panel(ops_text, title="Operations", border_style="blue"))

            # Portfolio Summary
            portfolio_text = Text()
            portfolio_text.append(f"Value: ", style="dim")
            portfolio_text.append(f"${status.portfolio_value:,.2f}", style="bold white")
            portfolio_text.append(f" | Cash: ${status.cash_available:,.2f}\n", style="dim")
            portfolio_text.append(f"Day P&L: ", style="dim")
            pnl_color = "green" if status.day_pnl >= 0 else "red"
            portfolio_text.append(f"${status.day_pnl:+,.2f} ({status.day_pnl_pct:+.2%})\n", style=pnl_color)
            portfolio_text.append(f"Positions: {len(status.positions)} | Max Weight: {status.max_position_weight:.1f}%", style="white")
            if status.concentration_warning:
                portfolio_text.append(" [HIGH CONCENTRATION]", style="bold red")

            console.print(Panel(portfolio_text, title="Portfolio", border_style="green"))

            # Positions Table
            if status.positions:
                pos_table = Table(title="Positions", expand=True)
                pos_table.add_column("Symbol", style="cyan", width=8)
                pos_table.add_column("Value", justify="right", width=10)
                pos_table.add_column("Weight", justify="right", width=8)
                pos_table.add_column("Day P&L", justify="right", width=10)
                pos_table.add_column("Total P&L", justify="right", width=10)
                pos_table.add_column("Thesis", width=20)

                for pos in status.positions[:10]:  # Top 10
                    day_style = "green" if pos.day_pnl >= 0 else "red"
                    total_style = "green" if pos.total_pnl >= 0 else "red"
                    pos_table.add_row(
                        pos.symbol,
                        f"${pos.market_value:,.0f}",
                        f"{pos.weight_pct:.1f}%",
                        f"[{day_style}]${pos.day_pnl:+,.0f}[/{day_style}]",
                        f"[{total_style}]${pos.total_pnl:+,.0f}[/{total_style}]",
                        pos.thesis_name or "-",
                    )

                console.print(pos_table)

            # Thesis Exposures
            if status.thesis_exposures:
                thesis_text = Text()
                for exp in status.thesis_exposures:
                    status_color = {"exceeding": "green", "on_track": "white", "at_risk": "red"}.get(exp.status, "white")
                    pnl_color = "green" if exp.day_pnl >= 0 else "red"
                    thesis_text.append(f"{exp.thesis_name[:25]:<25} ", style="white")
                    thesis_text.append(f"${exp.value:>10,.0f} ", style="cyan")
                    thesis_text.append(f"({exp.weight_pct:>5.1f}%) ", style="dim")
                    thesis_text.append(f"[{exp.status}] ", style=status_color)
                    thesis_text.append(f"P&L: ${exp.day_pnl:>+8,.0f}\n", style=pnl_color)

                console.print(Panel(thesis_text, title="Thesis Exposure", border_style="magenta"))

            # Layer Status
            layers_text = Text()
            for name, layer in status.layers.items():
                status_color = {"healthy": "green", "degraded": "yellow", "critical": "red"}.get(layer.status, "white")
                layers_text.append(f"[{layer.status[:3]}] ", style=status_color)
                layers_text.append(f"{layer.name}: ", style="white")
                layers_text.append(f"{layer.health_score:.0f}% ", style=status_color)
                layers_text.append(f"({layer.last_update_ago})\n", style="dim")
                if layer.alerts:
                    for alert in layer.alerts[:2]:
                        layers_text.append(f"  - {alert}\n", style="yellow")

            console.print(Panel(layers_text, title="Layer Status", border_style="yellow"))

            # System
            system_text = Text()
            system_text.append(f"Disk: ", style="dim")
            disk_color = "green" if status.disk_space_pct > 20 else "yellow" if status.disk_space_pct > 10 else "red"
            system_text.append(f"{status.disk_space_pct:.0f}% free", style=disk_color)
            system_text.append(f" | Memory: ", style="dim")
            mem_color = "green" if status.memory_pct < 80 else "yellow" if status.memory_pct < 90 else "red"
            system_text.append(f"{status.memory_pct:.0f}% used", style=mem_color)
            system_text.append(f" | Alerts: ", style="dim")
            alert_color = "green" if not status.active_alerts else "red"
            system_text.append(f"{len(status.active_alerts)}", style=alert_color)

            console.print(Panel(system_text, title="System", border_style="dim"))

        except ImportError:
            # Fallback to basic print
            print("\n" + "=" * 80)
            print(f"COMPREHENSIVE DASHBOARD - {status.timestamp}")
            print(f"Overall Health: {status.overall_health:.0f}%")
            print("=" * 80)
            print(json.dumps(status.to_dict(), indent=2, default=str))

    def save_status(self, status: ComprehensiveStatus) -> Path:
        """Save status to file."""
        output_path = self.live_dir / "comprehensive_status.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(status.to_dict(), f, indent=2, default=str)

        return output_path


async def main():
    """Run comprehensive dashboard."""
    import argparse

    parser = argparse.ArgumentParser(description="Comprehensive Trading Dashboard")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--save", action="store_true", help="Save to file")
    parser.add_argument("--watch", action="store_true", help="Watch mode (refresh every 60s)")

    args = parser.parse_args()

    dashboard = ComprehensiveDashboard()

    if args.watch:
        try:
            while True:
                status = await dashboard.get_comprehensive_status()
                if args.json:
                    print(json.dumps(status.to_dict(), indent=2, default=str))
                else:
                    print("\033[2J\033[H", end="")
                    dashboard.print_dashboard(status)
                    print("\nRefreshing in 60s... (Ctrl+C to exit)")

                if args.save:
                    dashboard.save_status(status)

                await asyncio.sleep(60)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        status = await dashboard.get_comprehensive_status()
        if args.json:
            print(json.dumps(status.to_dict(), indent=2, default=str))
        else:
            dashboard.print_dashboard(status)

        if args.save:
            path = dashboard.save_status(status)
            print(f"\nSaved to: {path}")


if __name__ == "__main__":
    asyncio.run(main())
