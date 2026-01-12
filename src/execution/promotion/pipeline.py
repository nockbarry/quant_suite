"""Automated Strategy Promotion Pipeline.

Manages the lifecycle of trading strategies from backtest through
paper trading to live trading with automated gates at each stage.

Pipeline stages:
1. BACKTEST - Initial strategy development and testing
2. MCPT_VALIDATION - Statistical validation with permutation testing
3. PAPER_TRADING - Live paper trading to verify real-world performance
4. PAPER_REVIEW - Evaluate paper trading results
5. LIVE_PENDING - Ready for live trading, pending human approval
6. LIVE_TRADING - Active in live trading
7. RETIRED - No longer active

Each transition requires passing specific gates:
- MCPT p-value < 0.05 to advance from MCPT_VALIDATION
- 20+ paper trading days with Sharpe > 0.5 to advance to LIVE_PENDING
- Human approval required to advance to LIVE_TRADING
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Any
import json
import logging

from src.core.paths import paths

logger = logging.getLogger(__name__)


class PromotionStage(str, Enum):
    """Strategy promotion lifecycle stages."""

    BACKTEST = "backtest"
    MCPT_VALIDATION = "mcpt_validation"
    PAPER_TRADING = "paper_trading"
    PAPER_REVIEW = "paper_review"
    LIVE_PENDING = "live_pending"  # Ready for live, awaiting approval
    LIVE_TRADING = "live_trading"
    RETIRED = "retired"

    def next(self) -> Optional["PromotionStage"]:
        """Get the next stage in the pipeline."""
        order = [
            PromotionStage.BACKTEST,
            PromotionStage.MCPT_VALIDATION,
            PromotionStage.PAPER_TRADING,
            PromotionStage.PAPER_REVIEW,
            PromotionStage.LIVE_PENDING,
            PromotionStage.LIVE_TRADING,
        ]
        try:
            idx = order.index(self)
            if idx + 1 < len(order):
                return order[idx + 1]
        except ValueError:
            pass
        return None


@dataclass
class PromotionGates:
    """Gate requirements for stage transitions."""

    # MCPT validation gates
    min_sharpe: float = 1.0
    max_p_value: float = 0.05
    min_trades_backtest: int = 30

    # Paper trading gates
    min_paper_days: int = 20
    min_paper_sharpe: float = 0.5
    max_paper_drawdown: float = 15.0  # percentage
    min_paper_trades: int = 10

    # Live trading gates
    require_human_approval: bool = True
    max_single_position_pct: float = 15.0
    max_sector_concentration_pct: float = 40.0

    def to_dict(self) -> dict:
        return {
            "min_sharpe": self.min_sharpe,
            "max_p_value": self.max_p_value,
            "min_trades_backtest": self.min_trades_backtest,
            "min_paper_days": self.min_paper_days,
            "min_paper_sharpe": self.min_paper_sharpe,
            "max_paper_drawdown": self.max_paper_drawdown,
            "min_paper_trades": self.min_paper_trades,
            "require_human_approval": self.require_human_approval,
            "max_single_position_pct": self.max_single_position_pct,
            "max_sector_concentration_pct": self.max_sector_concentration_pct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromotionGates":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class PromotionCandidate:
    """A strategy being tracked through the promotion pipeline."""

    strategy_name: str
    symbol: str
    current_stage: PromotionStage = PromotionStage.BACKTEST

    # Backtest metrics
    backtest_sharpe: Optional[float] = None
    backtest_sortino: Optional[float] = None
    backtest_max_drawdown: Optional[float] = None
    backtest_total_return: Optional[float] = None
    backtest_trades: int = 0
    backtest_win_rate: Optional[float] = None
    backtest_date: Optional[datetime] = None

    # MCPT validation metrics
    mcpt_p_value: Optional[float] = None
    mcpt_validated: bool = False
    mcpt_date: Optional[datetime] = None

    # Paper trading metrics
    paper_start_date: Optional[datetime] = None
    paper_days: int = 0
    paper_pnl: float = 0.0
    paper_pnl_pct: float = 0.0
    paper_sharpe: Optional[float] = None
    paper_max_drawdown: Optional[float] = None
    paper_trades: int = 0
    paper_win_rate: Optional[float] = None

    # Live trading
    promoted_to_live: bool = False
    promotion_date: Optional[datetime] = None
    live_start_date: Optional[datetime] = None
    live_pnl: float = 0.0
    live_trades: int = 0

    # Status tracking
    rejection_reason: Optional[str] = None
    rejection_date: Optional[datetime] = None
    notes: list[str] = field(default_factory=list)

    # Human approval
    approved_by: Optional[str] = None
    approval_date: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        """Check if candidate is still active in pipeline."""
        return self.current_stage not in [PromotionStage.RETIRED]

    @property
    def days_in_current_stage(self) -> int:
        """Days spent in current stage."""
        if self.current_stage == PromotionStage.PAPER_TRADING:
            return self.paper_days
        return 0

    def add_note(self, note: str) -> None:
        """Add a timestamped note."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.notes.append(f"[{timestamp}] {note}")

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "current_stage": self.current_stage.value,
            "backtest_sharpe": self.backtest_sharpe,
            "backtest_sortino": self.backtest_sortino,
            "backtest_max_drawdown": self.backtest_max_drawdown,
            "backtest_total_return": self.backtest_total_return,
            "backtest_trades": self.backtest_trades,
            "backtest_win_rate": self.backtest_win_rate,
            "backtest_date": self.backtest_date.isoformat() if self.backtest_date else None,
            "mcpt_p_value": self.mcpt_p_value,
            "mcpt_validated": self.mcpt_validated,
            "mcpt_date": self.mcpt_date.isoformat() if self.mcpt_date else None,
            "paper_start_date": self.paper_start_date.isoformat() if self.paper_start_date else None,
            "paper_days": self.paper_days,
            "paper_pnl": self.paper_pnl,
            "paper_pnl_pct": self.paper_pnl_pct,
            "paper_sharpe": self.paper_sharpe,
            "paper_max_drawdown": self.paper_max_drawdown,
            "paper_trades": self.paper_trades,
            "paper_win_rate": self.paper_win_rate,
            "promoted_to_live": self.promoted_to_live,
            "promotion_date": self.promotion_date.isoformat() if self.promotion_date else None,
            "live_start_date": self.live_start_date.isoformat() if self.live_start_date else None,
            "live_pnl": self.live_pnl,
            "live_trades": self.live_trades,
            "rejection_reason": self.rejection_reason,
            "rejection_date": self.rejection_date.isoformat() if self.rejection_date else None,
            "notes": self.notes,
            "approved_by": self.approved_by,
            "approval_date": self.approval_date.isoformat() if self.approval_date else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromotionCandidate":
        return cls(
            strategy_name=data["strategy_name"],
            symbol=data["symbol"],
            current_stage=PromotionStage(data.get("current_stage", "backtest")),
            backtest_sharpe=data.get("backtest_sharpe"),
            backtest_sortino=data.get("backtest_sortino"),
            backtest_max_drawdown=data.get("backtest_max_drawdown"),
            backtest_total_return=data.get("backtest_total_return"),
            backtest_trades=data.get("backtest_trades", 0),
            backtest_win_rate=data.get("backtest_win_rate"),
            backtest_date=datetime.fromisoformat(data["backtest_date"]) if data.get("backtest_date") else None,
            mcpt_p_value=data.get("mcpt_p_value"),
            mcpt_validated=data.get("mcpt_validated", False),
            mcpt_date=datetime.fromisoformat(data["mcpt_date"]) if data.get("mcpt_date") else None,
            paper_start_date=datetime.fromisoformat(data["paper_start_date"]) if data.get("paper_start_date") else None,
            paper_days=data.get("paper_days", 0),
            paper_pnl=data.get("paper_pnl", 0.0),
            paper_pnl_pct=data.get("paper_pnl_pct", 0.0),
            paper_sharpe=data.get("paper_sharpe"),
            paper_max_drawdown=data.get("paper_max_drawdown"),
            paper_trades=data.get("paper_trades", 0),
            paper_win_rate=data.get("paper_win_rate"),
            promoted_to_live=data.get("promoted_to_live", False),
            promotion_date=datetime.fromisoformat(data["promotion_date"]) if data.get("promotion_date") else None,
            live_start_date=datetime.fromisoformat(data["live_start_date"]) if data.get("live_start_date") else None,
            live_pnl=data.get("live_pnl", 0.0),
            live_trades=data.get("live_trades", 0),
            rejection_reason=data.get("rejection_reason"),
            rejection_date=datetime.fromisoformat(data["rejection_date"]) if data.get("rejection_date") else None,
            notes=data.get("notes", []),
            approved_by=data.get("approved_by"),
            approval_date=datetime.fromisoformat(data["approval_date"]) if data.get("approval_date") else None,
        )


class PromotionPipeline:
    """
    Manages strategy promotion from backtest to live trading.

    Tracks candidates through stages with automated gates:
    - BACKTEST -> MCPT_VALIDATION: Submit for statistical validation
    - MCPT_VALIDATION -> PAPER_TRADING: Pass MCPT (p < 0.05, Sharpe > 1.0)
    - PAPER_TRADING -> PAPER_REVIEW: Complete 20+ trading days
    - PAPER_REVIEW -> LIVE_PENDING: Pass paper trading metrics
    - LIVE_PENDING -> LIVE_TRADING: Human approval
    """

    def __init__(
        self,
        candidates_path: Optional[Path] = None,
        gates: Optional[PromotionGates] = None,
    ):
        """Initialize the promotion pipeline.

        Args:
            candidates_path: Path to candidates JSON file
            gates: Gate requirements (defaults to standard gates)
        """
        self.candidates_path = candidates_path or (paths.results / "promotion_candidates.json")
        self.gates = gates or PromotionGates()
        self.candidates: list[PromotionCandidate] = []
        self._load_candidates()

    def add_candidate(
        self,
        strategy_name: str,
        symbol: str,
        backtest_metrics: Optional[dict] = None,
    ) -> PromotionCandidate:
        """Add a new strategy to the pipeline.

        Args:
            strategy_name: Name of the strategy
            symbol: Symbol the strategy trades
            backtest_metrics: Optional initial backtest results

        Returns:
            Created PromotionCandidate
        """
        # Check for existing candidate
        for c in self.candidates:
            if c.strategy_name == strategy_name and c.symbol == symbol:
                logger.warning(f"Candidate {strategy_name}/{symbol} already exists")
                return c

        candidate = PromotionCandidate(
            strategy_name=strategy_name,
            symbol=symbol,
            current_stage=PromotionStage.BACKTEST,
        )

        if backtest_metrics:
            candidate.backtest_sharpe = backtest_metrics.get("sharpe")
            candidate.backtest_sortino = backtest_metrics.get("sortino")
            candidate.backtest_max_drawdown = backtest_metrics.get("max_drawdown")
            candidate.backtest_total_return = backtest_metrics.get("total_return")
            candidate.backtest_trades = backtest_metrics.get("num_trades", 0)
            candidate.backtest_win_rate = backtest_metrics.get("win_rate")
            candidate.backtest_date = datetime.now()

        candidate.add_note(f"Added to pipeline at stage {candidate.current_stage.value}")
        self.candidates.append(candidate)
        self._save_candidates()

        logger.info(f"Added candidate: {strategy_name}/{symbol}")
        return candidate

    def update_backtest_results(
        self,
        strategy_name: str,
        symbol: str,
        metrics: dict,
    ) -> bool:
        """Update backtest results for a candidate.

        Args:
            strategy_name: Strategy name
            symbol: Symbol
            metrics: Backtest metrics dict

        Returns:
            True if updated successfully
        """
        candidate = self.get_candidate(strategy_name, symbol)
        if not candidate:
            return False

        candidate.backtest_sharpe = metrics.get("sharpe")
        candidate.backtest_sortino = metrics.get("sortino")
        candidate.backtest_max_drawdown = metrics.get("max_drawdown")
        candidate.backtest_total_return = metrics.get("total_return")
        candidate.backtest_trades = metrics.get("num_trades", 0)
        candidate.backtest_win_rate = metrics.get("win_rate")
        candidate.backtest_date = datetime.now()

        candidate.add_note(f"Backtest results updated: Sharpe={metrics.get('sharpe', 0):.2f}")
        self._save_candidates()
        return True

    def update_mcpt_results(
        self,
        strategy_name: str,
        symbol: str,
        p_value: float,
    ) -> bool:
        """Update MCPT validation results.

        Args:
            strategy_name: Strategy name
            symbol: Symbol
            p_value: MCPT p-value for Sharpe ratio

        Returns:
            True if updated successfully
        """
        candidate = self.get_candidate(strategy_name, symbol)
        if not candidate:
            return False

        candidate.mcpt_p_value = p_value
        candidate.mcpt_validated = p_value < self.gates.max_p_value
        candidate.mcpt_date = datetime.now()

        if candidate.current_stage == PromotionStage.BACKTEST:
            candidate.current_stage = PromotionStage.MCPT_VALIDATION

        candidate.add_note(f"MCPT validation: p={p_value:.4f}, validated={candidate.mcpt_validated}")
        self._save_candidates()
        return True

    def update_paper_trading(
        self,
        strategy_name: str,
        symbol: str,
        pnl: float,
        pnl_pct: float,
        trades: int,
        sharpe: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        win_rate: Optional[float] = None,
    ) -> bool:
        """Update paper trading results.

        Args:
            strategy_name: Strategy name
            symbol: Symbol
            pnl: Total P&L in dollars
            pnl_pct: Total P&L percentage
            trades: Number of trades
            sharpe: Paper trading Sharpe ratio
            max_drawdown: Maximum drawdown percentage
            win_rate: Win rate

        Returns:
            True if updated successfully
        """
        candidate = self.get_candidate(strategy_name, symbol)
        if not candidate:
            return False

        candidate.paper_pnl = pnl
        candidate.paper_pnl_pct = pnl_pct
        candidate.paper_trades = trades
        candidate.paper_sharpe = sharpe
        candidate.paper_max_drawdown = max_drawdown
        candidate.paper_win_rate = win_rate

        if candidate.paper_start_date:
            candidate.paper_days = (datetime.now() - candidate.paper_start_date).days

        candidate.add_note(f"Paper trading update: ${pnl:.2f} ({pnl_pct:.1f}%), {trades} trades")
        self._save_candidates()
        return True

    def advance_stage(self, strategy_name: str, symbol: str) -> tuple[bool, str]:
        """Try to advance a candidate to the next stage.

        Args:
            strategy_name: Strategy name
            symbol: Symbol

        Returns:
            Tuple of (success, message)
        """
        candidate = self.get_candidate(strategy_name, symbol)
        if not candidate:
            return False, "Candidate not found"

        next_stage = candidate.current_stage.next()
        if not next_stage:
            return False, "Already at final stage"

        # Check gates
        passed, reason = self._check_gates(candidate, next_stage)
        if not passed:
            candidate.rejection_reason = reason
            candidate.rejection_date = datetime.now()
            candidate.add_note(f"Gate failed for {next_stage.value}: {reason}")
            self._save_candidates()
            return False, reason

        # Advance
        old_stage = candidate.current_stage
        candidate.current_stage = next_stage
        candidate.rejection_reason = None  # Clear any previous rejection

        # Stage-specific initialization
        if next_stage == PromotionStage.PAPER_TRADING:
            candidate.paper_start_date = datetime.now()
            candidate.paper_days = 0
            candidate.paper_pnl = 0.0
            candidate.paper_trades = 0

        elif next_stage == PromotionStage.LIVE_TRADING:
            candidate.promoted_to_live = True
            candidate.promotion_date = datetime.now()
            candidate.live_start_date = datetime.now()

        candidate.add_note(f"Advanced from {old_stage.value} to {next_stage.value}")
        self._save_candidates()

        logger.info(f"Advanced {strategy_name}/{symbol} to {next_stage.value}")
        return True, f"Advanced to {next_stage.value}"

    def approve_for_live(
        self,
        strategy_name: str,
        symbol: str,
        approved_by: str,
    ) -> tuple[bool, str]:
        """Approve a candidate for live trading (human gate).

        Args:
            strategy_name: Strategy name
            symbol: Symbol
            approved_by: Name/ID of approver

        Returns:
            Tuple of (success, message)
        """
        candidate = self.get_candidate(strategy_name, symbol)
        if not candidate:
            return False, "Candidate not found"

        if candidate.current_stage != PromotionStage.LIVE_PENDING:
            return False, f"Candidate at {candidate.current_stage.value}, not LIVE_PENDING"

        candidate.approved_by = approved_by
        candidate.approval_date = datetime.now()
        candidate.add_note(f"Approved for live trading by {approved_by}")
        self._save_candidates()

        # Now advance to live
        return self.advance_stage(strategy_name, symbol)

    def retire_candidate(
        self,
        strategy_name: str,
        symbol: str,
        reason: str,
    ) -> bool:
        """Retire a candidate from the pipeline.

        Args:
            strategy_name: Strategy name
            symbol: Symbol
            reason: Reason for retirement

        Returns:
            True if retired successfully
        """
        candidate = self.get_candidate(strategy_name, symbol)
        if not candidate:
            return False

        candidate.current_stage = PromotionStage.RETIRED
        candidate.add_note(f"Retired: {reason}")
        self._save_candidates()

        logger.info(f"Retired {strategy_name}/{symbol}: {reason}")
        return True

    def get_candidate(self, strategy_name: str, symbol: str) -> Optional[PromotionCandidate]:
        """Get a specific candidate."""
        for c in self.candidates:
            if c.strategy_name == strategy_name and c.symbol == symbol:
                return c
        return None

    def get_candidates_at_stage(self, stage: PromotionStage) -> list[PromotionCandidate]:
        """Get all candidates at a specific stage."""
        return [c for c in self.candidates if c.current_stage == stage]

    def get_ready_for_paper(self) -> list[PromotionCandidate]:
        """Get candidates ready to start paper trading."""
        candidates = self.get_candidates_at_stage(PromotionStage.MCPT_VALIDATION)
        return [c for c in candidates if c.mcpt_validated]

    def get_ready_for_live(self) -> list[PromotionCandidate]:
        """Get candidates ready for live trading (pending approval)."""
        return self.get_candidates_at_stage(PromotionStage.LIVE_PENDING)

    def get_active_candidates(self) -> list[PromotionCandidate]:
        """Get all active candidates (not retired)."""
        return [c for c in self.candidates if c.is_active]

    def get_live_candidates(self) -> list[PromotionCandidate]:
        """Get candidates currently in live trading."""
        return self.get_candidates_at_stage(PromotionStage.LIVE_TRADING)

    def _check_gates(
        self,
        candidate: PromotionCandidate,
        target_stage: PromotionStage,
    ) -> tuple[bool, str]:
        """Check if candidate passes gates for target stage.

        Returns:
            Tuple of (passed, reason)
        """
        if target_stage == PromotionStage.MCPT_VALIDATION:
            # Backtest -> MCPT: Need basic backtest results
            if candidate.backtest_sharpe is None:
                return False, "No backtest Sharpe ratio"
            if candidate.backtest_trades < self.gates.min_trades_backtest:
                return False, f"Only {candidate.backtest_trades} trades, need {self.gates.min_trades_backtest}"
            return True, ""

        elif target_stage == PromotionStage.PAPER_TRADING:
            # MCPT -> Paper: Need passing MCPT
            if not candidate.mcpt_validated:
                return False, "Not MCPT validated"
            if candidate.mcpt_p_value is None or candidate.mcpt_p_value > self.gates.max_p_value:
                return False, f"p-value {candidate.mcpt_p_value} > {self.gates.max_p_value}"
            if candidate.backtest_sharpe is None or candidate.backtest_sharpe < self.gates.min_sharpe:
                return False, f"Sharpe {candidate.backtest_sharpe} < {self.gates.min_sharpe}"
            return True, ""

        elif target_stage == PromotionStage.PAPER_REVIEW:
            # Paper -> Review: Need enough paper trading days
            if candidate.paper_days < self.gates.min_paper_days:
                return False, f"Only {candidate.paper_days} paper days, need {self.gates.min_paper_days}"
            if candidate.paper_trades < self.gates.min_paper_trades:
                return False, f"Only {candidate.paper_trades} paper trades, need {self.gates.min_paper_trades}"
            return True, ""

        elif target_stage == PromotionStage.LIVE_PENDING:
            # Review -> Pending: Pass paper trading metrics
            if candidate.paper_sharpe is not None and candidate.paper_sharpe < self.gates.min_paper_sharpe:
                return False, f"Paper Sharpe {candidate.paper_sharpe:.2f} < {self.gates.min_paper_sharpe}"
            if candidate.paper_max_drawdown is not None and candidate.paper_max_drawdown > self.gates.max_paper_drawdown:
                return False, f"Paper drawdown {candidate.paper_max_drawdown:.1f}% > {self.gates.max_paper_drawdown}%"
            return True, ""

        elif target_stage == PromotionStage.LIVE_TRADING:
            # Pending -> Live: Need human approval
            if self.gates.require_human_approval:
                if candidate.approved_by is None:
                    return False, "Requires human approval"
            return True, ""

        return True, ""

    def generate_report(self) -> str:
        """Generate markdown status report."""
        lines = [
            "# Promotion Pipeline Report",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Summary",
            "",
        ]

        # Stage counts
        stage_counts = {}
        for c in self.candidates:
            stage = c.current_stage.value
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        for stage in PromotionStage:
            count = stage_counts.get(stage.value, 0)
            lines.append(f"- {stage.value}: {count}")

        lines.append("")

        # Ready for advancement
        ready_paper = self.get_ready_for_paper()
        ready_live = self.get_ready_for_live()

        if ready_paper:
            lines.append("## Ready for Paper Trading")
            lines.append("")
            for c in ready_paper:
                lines.append(f"- {c.strategy_name}/{c.symbol}: Sharpe={c.backtest_sharpe:.2f}, p={c.mcpt_p_value:.4f}")
            lines.append("")

        if ready_live:
            lines.append("## Ready for Live Trading (Pending Approval)")
            lines.append("")
            for c in ready_live:
                lines.append(f"- {c.strategy_name}/{c.symbol}: Paper {c.paper_days}d, Sharpe={c.paper_sharpe or 0:.2f}")
            lines.append("")

        # Live strategies
        live = self.get_live_candidates()
        if live:
            lines.append("## Currently Live")
            lines.append("")
            lines.append("| Strategy | Symbol | Days Live | P&L | Trades |")
            lines.append("|----------|--------|-----------|-----|--------|")
            for c in live:
                days_live = (datetime.now() - c.live_start_date).days if c.live_start_date else 0
                lines.append(
                    f"| {c.strategy_name} | {c.symbol} | {days_live} | ${c.live_pnl:.0f} | {c.live_trades} |"
                )
            lines.append("")

        return "\n".join(lines)

    def _load_candidates(self) -> None:
        """Load candidates from file."""
        if not self.candidates_path.exists():
            self.candidates = []
            return

        try:
            with open(self.candidates_path, "r") as f:
                data = json.load(f)

            self.candidates = [PromotionCandidate.from_dict(c) for c in data.get("candidates", [])]
            logger.info(f"Loaded {len(self.candidates)} promotion candidates")

        except Exception as e:
            logger.error(f"Error loading candidates: {e}")
            self.candidates = []

    def _save_candidates(self) -> None:
        """Save candidates to file."""
        self.candidates_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "updated_at": datetime.now().isoformat(),
            "gates": self.gates.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
        }

        with open(self.candidates_path, "w") as f:
            json.dump(data, f, indent=2)


def get_promotion_summary() -> dict[str, Any]:
    """Quick utility to get promotion pipeline summary.

    Returns:
        Summary dict
    """
    pipeline = PromotionPipeline()

    stage_counts = {}
    for c in pipeline.candidates:
        stage = c.current_stage.value
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    return {
        "total_candidates": len(pipeline.candidates),
        "stage_counts": stage_counts,
        "ready_for_paper": len(pipeline.get_ready_for_paper()),
        "ready_for_live": len(pipeline.get_ready_for_live()),
        "live_count": len(pipeline.get_live_candidates()),
    }
