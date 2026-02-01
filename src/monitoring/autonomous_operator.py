#!/usr/bin/env python3
"""Autonomous Operator - Claude-centric trading orchestration.

This module provides the infrastructure for Claude to operate as the central
trading orchestrator with:
1. Extended session support (hours, not minutes)
2. Execution authority with safety rails
3. Rules engine integration
4. Session state persistence for context handoff
5. Human oversight via alerts

The philosophy: Claude IS the edge. Infrastructure serves Claude.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionAuthority(Enum):
    """Levels of execution authority for Claude."""
    FULL = "full"           # Execute any trade within risk limits
    THESIS_ONLY = "thesis"  # Only execute trades for active theses
    APPROVED = "approved"   # Only execute pre-approved rules
    NOTIFY = "notify"       # Don't execute, just notify
    DISABLED = "disabled"   # No execution, monitoring only


class TradeType(Enum):
    """Types of trades for authority checking."""
    THESIS_ADD = "thesis_add"         # Adding to thesis position
    THESIS_TRIM = "thesis_trim"       # Trimming thesis position
    THESIS_EXIT = "thesis_exit"       # Exiting thesis (signpost hit)
    STOP_LOSS = "stop_loss"           # Stop loss triggered
    TAKE_PROFIT = "take_profit"       # Take profit triggered
    REBALANCE = "rebalance"           # Portfolio rebalancing
    OPPORTUNISTIC = "opportunistic"   # Non-thesis opportunity
    RISK_REDUCTION = "risk_reduction" # Reducing risk exposure


@dataclass
class SafetyRails:
    """Safety constraints for autonomous operation."""
    max_single_trade_pct: float = 5.0       # Max 5% of portfolio per trade
    max_daily_trades: int = 10              # Max trades per day
    max_daily_loss_pct: float = 3.0         # Stop trading if down 3%
    max_position_pct: float = 15.0          # Max single position size
    max_sector_pct: float = 40.0            # Max sector concentration
    require_thesis: bool = False            # Require thesis for all trades
    blocked_symbols: list = field(default_factory=list)
    allowed_hours: tuple = (9, 16)          # Trading hours (ET)

    def to_dict(self):
        return asdict(self)


@dataclass
class SessionState:
    """Persistent state for session continuity."""
    session_id: str
    started_at: datetime
    last_check_at: datetime
    check_count: int = 0
    trades_today: int = 0
    daily_pnl_pct: float = 0.0

    # What Claude has done this session
    decisions_made: list = field(default_factory=list)
    trades_executed: list = field(default_factory=list)
    alerts_sent: list = field(default_factory=list)
    research_spawned: list = field(default_factory=list)

    # What Claude should remember
    focus_areas: list = field(default_factory=list)
    pending_actions: list = field(default_factory=list)
    observations: list = field(default_factory=list)

    # Authority and safety
    authority: ExecutionAuthority = ExecutionAuthority.THESIS_ONLY
    safety_rails: SafetyRails = field(default_factory=SafetyRails)

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "last_check_at": self.last_check_at.isoformat(),
            "check_count": self.check_count,
            "trades_today": self.trades_today,
            "daily_pnl_pct": self.daily_pnl_pct,
            "decisions_made": self.decisions_made,
            "trades_executed": self.trades_executed,
            "alerts_sent": self.alerts_sent,
            "research_spawned": self.research_spawned,
            "focus_areas": self.focus_areas,
            "pending_actions": self.pending_actions,
            "observations": self.observations[-20:],  # Keep last 20
            "authority": self.authority.value,
            "safety_rails": self.safety_rails.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        return cls(
            session_id=data["session_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            last_check_at=datetime.fromisoformat(data["last_check_at"]),
            check_count=data.get("check_count", 0),
            trades_today=data.get("trades_today", 0),
            daily_pnl_pct=data.get("daily_pnl_pct", 0.0),
            decisions_made=data.get("decisions_made", []),
            trades_executed=data.get("trades_executed", []),
            alerts_sent=data.get("alerts_sent", []),
            research_spawned=data.get("research_spawned", []),
            focus_areas=data.get("focus_areas", []),
            pending_actions=data.get("pending_actions", []),
            observations=data.get("observations", []),
            authority=ExecutionAuthority(data.get("authority", "thesis")),
            safety_rails=SafetyRails(**data.get("safety_rails", {})),
        )


@dataclass
class TradeProposal:
    """A trade Claude wants to execute."""
    symbol: str
    action: str  # BUY, SELL, CLOSE
    quantity: Optional[int] = None
    size_pct: Optional[float] = None  # % of portfolio
    trade_type: TradeType = TradeType.THESIS_ADD
    thesis_id: Optional[str] = None
    reasoning: str = ""
    confidence: float = 0.5
    urgency: str = "normal"  # low, normal, high, immediate

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "action": self.action,
            "quantity": self.quantity,
            "size_pct": self.size_pct,
            "trade_type": self.trade_type.value,
            "thesis_id": self.thesis_id,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "urgency": self.urgency,
        }


@dataclass
class ExecutionResult:
    """Result of attempting to execute a trade."""
    success: bool
    symbol: str
    action: str
    quantity: Optional[int] = None
    fill_price: Optional[float] = None
    message: str = ""
    blocked_by: Optional[str] = None  # Safety rail that blocked

    def to_dict(self):
        return asdict(self)


class AutonomousOperator:
    """
    Claude's autonomous operating infrastructure.

    This class provides the tools Claude needs to:
    1. Maintain session state across checks
    2. Execute trades within safety rails
    3. Track what's been done for session continuity
    4. Hand off context between Claude sessions
    """

    STATE_FILE = Path.home() / "quant_results" / "live" / "operator_session.json"

    def __init__(
        self,
        authority: ExecutionAuthority = ExecutionAuthority.THESIS_ONLY,
        safety_rails: Optional[SafetyRails] = None,
    ):
        self.authority = authority
        self.safety_rails = safety_rails or SafetyRails()
        self.session: Optional[SessionState] = None

    def start_session(self, resume: bool = True) -> SessionState:
        """Start or resume an operator session."""
        if resume and self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE) as f:
                    data = json.load(f)
                self.session = SessionState.from_dict(data)

                # Check if session is from today
                if self.session.started_at.date() == datetime.now().date():
                    logger.info(f"Resumed session {self.session.session_id}")
                    return self.session
            except Exception as e:
                logger.warning(f"Could not resume session: {e}")

        # Start new session
        self.session = SessionState(
            session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now(),
            last_check_at=datetime.now(),
            authority=self.authority,
            safety_rails=self.safety_rails,
        )
        self._save_session()
        logger.info(f"Started new session {self.session.session_id}")
        return self.session

    def _save_session(self):
        """Persist session state."""
        if self.session:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.session.to_dict(), f, indent=2)

    def record_check(self, observations: list[str] = None):
        """Record that a check was performed."""
        if self.session:
            self.session.check_count += 1
            self.session.last_check_at = datetime.now()
            if observations:
                self.session.observations.extend(observations)
            self._save_session()

    def record_decision(self, decision: dict):
        """Record a decision made by Claude."""
        if self.session:
            decision["timestamp"] = datetime.now().isoformat()
            self.session.decisions_made.append(decision)
            self._save_session()

    def record_trade(self, result: ExecutionResult):
        """Record an executed trade."""
        if self.session:
            trade_record = result.to_dict()
            trade_record["timestamp"] = datetime.now().isoformat()
            self.session.trades_executed.append(trade_record)
            if result.success:
                self.session.trades_today += 1
            self._save_session()

    def set_focus(self, areas: list[str]):
        """Set focus areas for the session."""
        if self.session:
            self.session.focus_areas = areas
            self._save_session()

    def add_pending_action(self, action: dict):
        """Add a pending action to track."""
        if self.session:
            action["added_at"] = datetime.now().isoformat()
            self.session.pending_actions.append(action)
            self._save_session()

    def complete_pending_action(self, action_id: str):
        """Mark a pending action as complete."""
        if self.session:
            self.session.pending_actions = [
                a for a in self.session.pending_actions
                if a.get("id") != action_id
            ]
            self._save_session()

    def check_trade_allowed(
        self,
        proposal: TradeProposal,
        portfolio_value: float,
        current_positions: dict,
        daily_pnl_pct: float,
    ) -> tuple[bool, str]:
        """
        Check if a trade is allowed under current authority and safety rails.

        Returns (allowed, reason).
        """
        rails = self.safety_rails

        # Check authority level
        if self.authority == ExecutionAuthority.DISABLED:
            return False, "Execution disabled"

        if self.authority == ExecutionAuthority.NOTIFY:
            return False, "Notify-only mode"

        if self.authority == ExecutionAuthority.APPROVED:
            # Only allow stop loss and signpost exits
            if proposal.trade_type not in [TradeType.STOP_LOSS, TradeType.THESIS_EXIT]:
                return False, "Only pre-approved trades allowed"

        if self.authority == ExecutionAuthority.THESIS_ONLY:
            # Require thesis linkage
            if not proposal.thesis_id and proposal.trade_type not in [
                TradeType.STOP_LOSS, TradeType.RISK_REDUCTION
            ]:
                return False, "Thesis required for this trade"

        # Check safety rails
        if proposal.symbol in rails.blocked_symbols:
            return False, f"{proposal.symbol} is blocked"

        # Check trading hours
        now = datetime.now()
        if not (rails.allowed_hours[0] <= now.hour < rails.allowed_hours[1]):
            if proposal.urgency != "immediate":
                return False, f"Outside trading hours ({rails.allowed_hours[0]}-{rails.allowed_hours[1]} ET)"

        # Check daily trade limit
        if self.session and self.session.trades_today >= rails.max_daily_trades:
            return False, f"Daily trade limit reached ({rails.max_daily_trades})"

        # Check daily loss limit
        if daily_pnl_pct < -rails.max_daily_loss_pct:
            if proposal.action == "BUY":
                return False, f"Daily loss limit reached ({rails.max_daily_loss_pct}%)"

        # Check trade size
        if proposal.size_pct and proposal.size_pct > rails.max_single_trade_pct:
            return False, f"Trade size {proposal.size_pct}% exceeds limit {rails.max_single_trade_pct}%"

        # Check position concentration (for buys)
        if proposal.action == "BUY" and proposal.symbol in current_positions:
            current_pct = (current_positions[proposal.symbol] / portfolio_value) * 100
            add_pct = proposal.size_pct or 0
            if current_pct + add_pct > rails.max_position_pct:
                return False, f"Would exceed position limit {rails.max_position_pct}%"

        return True, "Trade allowed"

    async def execute_trade(
        self,
        proposal: TradeProposal,
        portfolio_value: float,
        current_positions: dict,
        daily_pnl_pct: float,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """
        Execute a trade proposal with safety checks.

        Args:
            proposal: The trade to execute
            portfolio_value: Current portfolio value
            current_positions: Dict of symbol -> market_value
            daily_pnl_pct: Today's P&L percentage
            dry_run: If True, check but don't execute

        Returns:
            ExecutionResult with success/failure details
        """
        # Check if allowed
        allowed, reason = self.check_trade_allowed(
            proposal, portfolio_value, current_positions, daily_pnl_pct
        )

        if not allowed:
            return ExecutionResult(
                success=False,
                symbol=proposal.symbol,
                action=proposal.action,
                message=reason,
                blocked_by=reason,
            )

        if dry_run:
            return ExecutionResult(
                success=True,
                symbol=proposal.symbol,
                action=proposal.action,
                message="Dry run - would execute",
            )

        # Calculate quantity if using percentage
        quantity = proposal.quantity
        if not quantity and proposal.size_pct:
            # Need to get current price - this would call broker
            # For now, return that we need quantity
            return ExecutionResult(
                success=False,
                symbol=proposal.symbol,
                action=proposal.action,
                message="Quantity required for execution",
            )

        # Execute via quick_trade script
        try:
            import subprocess

            cmd = [
                "python3", "scripts/quick_trade.py",
                proposal.action.lower(),
                proposal.symbol,
            ]
            if quantity:
                cmd.append(str(quantity))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd="/home/nock/projects/quant_suite",
                env={"PYTHONPATH": "/home/nock/projects/quant_suite"},
                timeout=30,
            )

            if result.returncode == 0:
                exec_result = ExecutionResult(
                    success=True,
                    symbol=proposal.symbol,
                    action=proposal.action,
                    quantity=quantity,
                    message=result.stdout.strip()[:200],
                )
            else:
                exec_result = ExecutionResult(
                    success=False,
                    symbol=proposal.symbol,
                    action=proposal.action,
                    message=result.stderr.strip()[:200] or "Execution failed",
                )

            self.record_trade(exec_result)
            return exec_result

        except Exception as e:
            return ExecutionResult(
                success=False,
                symbol=proposal.symbol,
                action=proposal.action,
                message=f"Execution error: {str(e)}",
            )

    def get_session_summary(self) -> str:
        """Get a summary of the current session for Claude's context."""
        if not self.session:
            return "No active session"

        duration = datetime.now() - self.session.started_at
        hours = duration.total_seconds() / 3600

        summary = f"""
=== OPERATOR SESSION SUMMARY ===
Session ID: {self.session.session_id}
Duration: {hours:.1f} hours
Checks: {self.session.check_count}
Authority: {self.session.authority.value.upper()}

Trades Today: {self.session.trades_today}
Daily P&L: {self.session.daily_pnl_pct:+.2f}%

Focus Areas:
{chr(10).join('  - ' + f for f in self.session.focus_areas) or '  (none set)'}

Pending Actions:
{chr(10).join('  - ' + a.get('description', str(a)) for a in self.session.pending_actions[:5]) or '  (none)'}

Recent Trades:
{chr(10).join('  - ' + t.get('symbol', '') + ' ' + t.get('action', '') for t in self.session.trades_executed[-5:]) or '  (none)'}

Recent Observations:
{chr(10).join('  - ' + o for o in self.session.observations[-5:]) or '  (none)'}
================================
"""
        return summary

    def get_handoff_context(self) -> dict:
        """
        Get context for handing off to a new Claude session.

        This is what the next Claude session needs to continue seamlessly.
        """
        if not self.session:
            return {"error": "No active session"}

        return {
            "session_id": self.session.session_id,
            "session_duration_hours": (datetime.now() - self.session.started_at).total_seconds() / 3600,
            "trades_today": self.session.trades_today,
            "daily_pnl_pct": self.session.daily_pnl_pct,
            "authority": self.session.authority.value,
            "focus_areas": self.session.focus_areas,
            "pending_actions": self.session.pending_actions,
            "recent_trades": self.session.trades_executed[-10:],
            "recent_decisions": self.session.decisions_made[-10:],
            "key_observations": self.session.observations[-10:],
            "safety_rails": self.session.safety_rails.to_dict(),
        }


# Singleton instance
_operator: Optional[AutonomousOperator] = None


def get_autonomous_operator(
    authority: ExecutionAuthority = ExecutionAuthority.THESIS_ONLY,
) -> AutonomousOperator:
    """Get the global autonomous operator instance."""
    global _operator
    if _operator is None:
        _operator = AutonomousOperator(authority=authority)
    return _operator


def start_autonomous_session(
    authority: ExecutionAuthority = ExecutionAuthority.THESIS_ONLY,
    resume: bool = True,
) -> SessionState:
    """Convenience function to start/resume an autonomous session."""
    operator = get_autonomous_operator(authority)
    return operator.start_session(resume=resume)
