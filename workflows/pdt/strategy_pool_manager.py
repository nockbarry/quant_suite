"""
Strategy Pool Manager for PDT-Aware Trading.

Maintains separate strategy pools for budget accounts (<$25k) and
full accounts (>$25k) with different trading constraints.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
import json
import yaml


class PoolType(Enum):
    """Strategy pool types."""
    BUDGET = "budget"  # <$25k, PDT restrictions
    FULL = "full"      # >$25k, no restrictions


@dataclass
class PoolConstraints:
    """Constraints for a strategy pool."""
    min_hold_days: int
    max_day_trades_per_5_days: int
    max_position_pct: float
    max_single_stock_pct: float = 0.25
    require_stop_loss: bool = True
    stop_loss_pct: float = 0.05

    @classmethod
    def budget_constraints(cls) -> "PoolConstraints":
        """Default constraints for budget accounts."""
        return cls(
            min_hold_days=2,
            max_day_trades_per_5_days=3,
            max_position_pct=0.20,
            max_single_stock_pct=0.20,
            require_stop_loss=True,
            stop_loss_pct=0.05,
        )

    @classmethod
    def full_constraints(cls) -> "PoolConstraints":
        """Default constraints for full accounts."""
        return cls(
            min_hold_days=0,
            max_day_trades_per_5_days=999,  # Unlimited
            max_position_pct=0.25,
            max_single_stock_pct=0.25,
            require_stop_loss=True,
            stop_loss_pct=0.05,
        )


@dataclass
class PoolStrategy:
    """Strategy in a pool with its configuration."""
    strategy_name: str
    symbol: str
    holding_days: int
    sharpe: float
    p_value: float
    validated_at: datetime
    promoted_at: datetime | None = None
    status: str = "pending"  # pending, active, paused, removed
    params: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "holding_days": self.holding_days,
            "sharpe": self.sharpe,
            "p_value": self.p_value,
            "validated_at": self.validated_at.isoformat(),
            "promoted_at": self.promoted_at.isoformat() if self.promoted_at else None,
            "status": self.status,
            "params": self.params,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PoolStrategy":
        return cls(
            strategy_name=data["strategy_name"],
            symbol=data["symbol"],
            holding_days=data["holding_days"],
            sharpe=data["sharpe"],
            p_value=data["p_value"],
            validated_at=datetime.fromisoformat(data["validated_at"]),
            promoted_at=datetime.fromisoformat(data["promoted_at"]) if data.get("promoted_at") else None,
            status=data.get("status", "pending"),
            params=data.get("params", {}),
            notes=data.get("notes", ""),
        )


class StrategyPoolManager:
    """
    Maintain separate pools for budget vs full accounts.

    Budget Pool (<$25k):
    - Min 2-day holding period for PDT compliance
    - Max 3 day trades per 5 days
    - Swing trading focus

    Full Pool (>$25k):
    - No holding period restrictions
    - Unrestricted day trading
    - Can use day trading strategies
    """

    def __init__(self, config_path: str | None = None):
        self.config_path = Path(
            config_path or "/home/nock/projects/quant_suite/config/strategies/strategy_pools.yaml"
        )
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        self.budget_pool: list[PoolStrategy] = []
        self.full_pool: list[PoolStrategy] = []
        self.budget_constraints = PoolConstraints.budget_constraints()
        self.full_constraints = PoolConstraints.full_constraints()

        self._load_pools()

    def _load_pools(self) -> None:
        """Load pools from YAML config."""
        if not self.config_path.exists():
            self._save_pools()
            return

        try:
            with open(self.config_path) as f:
                data = yaml.safe_load(f) or {}

            # Load constraints
            if "budget_pool" in data and "constraints" in data["budget_pool"]:
                c = data["budget_pool"]["constraints"]
                self.budget_constraints = PoolConstraints(
                    min_hold_days=c.get("min_hold_days", 2),
                    max_day_trades_per_5_days=c.get("max_day_trades_per_5_days", 3),
                    max_position_pct=c.get("max_position_pct", 0.20),
                )

            if "full_pool" in data and "constraints" in data["full_pool"]:
                c = data["full_pool"]["constraints"]
                self.full_constraints = PoolConstraints(
                    min_hold_days=c.get("min_hold_days", 0),
                    max_day_trades_per_5_days=c.get("max_day_trades_per_5_days", 999),
                    max_position_pct=c.get("max_position_pct", 0.25),
                )

            # Load strategies
            if "budget_pool" in data and "strategies" in data["budget_pool"]:
                for s in data["budget_pool"]["strategies"]:
                    self.budget_pool.append(PoolStrategy.from_dict(s))

            if "full_pool" in data and "strategies" in data["full_pool"]:
                for s in data["full_pool"]["strategies"]:
                    self.full_pool.append(PoolStrategy.from_dict(s))

        except Exception as e:
            print(f"Warning: Could not load pools: {e}")

    def _save_pools(self) -> None:
        """Save pools to YAML config."""
        data = {
            "# Strategy Pools Configuration": None,
            "# Managed by StrategyPoolManager": None,
            "# Last updated": datetime.now().isoformat(),
            "budget_pool": {
                "description": "Strategies for accounts <$25k with PDT restrictions",
                "constraints": {
                    "min_hold_days": self.budget_constraints.min_hold_days,
                    "max_day_trades_per_5_days": self.budget_constraints.max_day_trades_per_5_days,
                    "max_position_pct": self.budget_constraints.max_position_pct,
                    "max_single_stock_pct": self.budget_constraints.max_single_stock_pct,
                    "require_stop_loss": self.budget_constraints.require_stop_loss,
                    "stop_loss_pct": self.budget_constraints.stop_loss_pct,
                },
                "strategies": [s.to_dict() for s in self.budget_pool],
            },
            "full_pool": {
                "description": "Strategies for accounts >=$25k without PDT restrictions",
                "constraints": {
                    "min_hold_days": self.full_constraints.min_hold_days,
                    "max_day_trades_per_5_days": self.full_constraints.max_day_trades_per_5_days,
                    "max_position_pct": self.full_constraints.max_position_pct,
                    "max_single_stock_pct": self.full_constraints.max_single_stock_pct,
                    "require_stop_loss": self.full_constraints.require_stop_loss,
                    "stop_loss_pct": self.full_constraints.stop_loss_pct,
                },
                "strategies": [s.to_dict() for s in self.full_pool],
            },
        }

        # Clean up the None comment values
        clean_data = {k: v for k, v in data.items() if v is not None}

        with open(self.config_path, "w") as f:
            yaml.dump(clean_data, f, default_flow_style=False, sort_keys=False)

    def add_to_budget_pool(
        self,
        strategy_name: str,
        symbol: str,
        holding_days: int,
        sharpe: float,
        p_value: float,
        params: dict | None = None,
        notes: str = "",
    ) -> PoolStrategy:
        """
        Add a strategy to the budget pool.

        Args:
            strategy_name: Name of the strategy
            symbol: Trading symbol
            holding_days: PDT-compliant holding period (must be >= 2)
            sharpe: Backtest Sharpe ratio
            p_value: MCPT p-value
            params: Strategy parameters
            notes: Optional notes

        Returns:
            PoolStrategy added to the pool
        """
        # Validate holding period
        if holding_days < self.budget_constraints.min_hold_days:
            raise ValueError(
                f"Holding days {holding_days} < min {self.budget_constraints.min_hold_days} for budget pool"
            )

        # Check for duplicates
        existing = self._find_in_pool(strategy_name, symbol, self.budget_pool)
        if existing:
            # Update existing
            existing.holding_days = holding_days
            existing.sharpe = sharpe
            existing.p_value = p_value
            existing.validated_at = datetime.now()
            existing.params = params or existing.params
            existing.notes = notes or existing.notes
            self._save_pools()
            return existing

        strategy = PoolStrategy(
            strategy_name=strategy_name,
            symbol=symbol,
            holding_days=holding_days,
            sharpe=sharpe,
            p_value=p_value,
            validated_at=datetime.now(),
            params=params or {},
            notes=notes,
        )
        self.budget_pool.append(strategy)
        self._save_pools()
        return strategy

    def add_to_full_pool(
        self,
        strategy_name: str,
        symbol: str,
        sharpe: float,
        p_value: float,
        holding_days: int = 0,
        params: dict | None = None,
        notes: str = "",
    ) -> PoolStrategy:
        """
        Add a strategy to the full pool.

        Args:
            strategy_name: Name of the strategy
            symbol: Trading symbol
            sharpe: Backtest Sharpe ratio
            p_value: MCPT p-value
            holding_days: Optional holding period (can be 0)
            params: Strategy parameters
            notes: Optional notes

        Returns:
            PoolStrategy added to the pool
        """
        # Check for duplicates
        existing = self._find_in_pool(strategy_name, symbol, self.full_pool)
        if existing:
            # Update existing
            existing.holding_days = holding_days
            existing.sharpe = sharpe
            existing.p_value = p_value
            existing.validated_at = datetime.now()
            existing.params = params or existing.params
            existing.notes = notes or existing.notes
            self._save_pools()
            return existing

        strategy = PoolStrategy(
            strategy_name=strategy_name,
            symbol=symbol,
            holding_days=holding_days,
            sharpe=sharpe,
            p_value=p_value,
            validated_at=datetime.now(),
            params=params or {},
            notes=notes,
        )
        self.full_pool.append(strategy)
        self._save_pools()
        return strategy

    def _find_in_pool(
        self,
        strategy_name: str,
        symbol: str,
        pool: list[PoolStrategy]
    ) -> PoolStrategy | None:
        """Find a strategy in a pool."""
        for s in pool:
            if s.strategy_name == strategy_name and s.symbol == symbol:
                return s
        return None

    def get_strategies_for_account(self, account_value: float) -> list[PoolStrategy]:
        """
        Return appropriate strategies based on account size.

        Args:
            account_value: Current account value

        Returns:
            List of strategies appropriate for the account size
        """
        if account_value >= 25000:
            # Full account gets both pools
            return self.full_pool + self.budget_pool
        else:
            # Budget account only gets budget pool
            return self.budget_pool

    def get_active_strategies(self, pool_type: PoolType) -> list[PoolStrategy]:
        """Get active strategies from a pool."""
        pool = self.budget_pool if pool_type == PoolType.BUDGET else self.full_pool
        return [s for s in pool if s.status == "active"]

    def promote_strategy(
        self,
        strategy_name: str,
        symbol: str,
        pool_type: PoolType
    ) -> bool:
        """
        Promote a strategy to active status.

        Returns True if successful.
        """
        pool = self.budget_pool if pool_type == PoolType.BUDGET else self.full_pool
        strategy = self._find_in_pool(strategy_name, symbol, pool)

        if not strategy:
            return False

        strategy.status = "active"
        strategy.promoted_at = datetime.now()
        self._save_pools()
        return True

    def pause_strategy(
        self,
        strategy_name: str,
        symbol: str,
        pool_type: PoolType
    ) -> bool:
        """Pause a strategy (stop trading but keep in pool)."""
        pool = self.budget_pool if pool_type == PoolType.BUDGET else self.full_pool
        strategy = self._find_in_pool(strategy_name, symbol, pool)

        if not strategy:
            return False

        strategy.status = "paused"
        self._save_pools()
        return True

    def remove_strategy(
        self,
        strategy_name: str,
        symbol: str,
        pool_type: PoolType
    ) -> bool:
        """Remove a strategy from the pool."""
        pool = self.budget_pool if pool_type == PoolType.BUDGET else self.full_pool
        strategy = self._find_in_pool(strategy_name, symbol, pool)

        if not strategy:
            return False

        pool.remove(strategy)
        self._save_pools()
        return True

    def get_pool_summary(self) -> dict:
        """Get summary of both pools."""
        return {
            "budget_pool": {
                "count": len(self.budget_pool),
                "active": len([s for s in self.budget_pool if s.status == "active"]),
                "pending": len([s for s in self.budget_pool if s.status == "pending"]),
                "paused": len([s for s in self.budget_pool if s.status == "paused"]),
                "constraints": {
                    "min_hold_days": self.budget_constraints.min_hold_days,
                    "max_day_trades": self.budget_constraints.max_day_trades_per_5_days,
                },
                "strategies": [
                    f"{s.strategy_name}/{s.symbol} ({s.status})"
                    for s in self.budget_pool
                ],
            },
            "full_pool": {
                "count": len(self.full_pool),
                "active": len([s for s in self.full_pool if s.status == "active"]),
                "pending": len([s for s in self.full_pool if s.status == "pending"]),
                "paused": len([s for s in self.full_pool if s.status == "paused"]),
                "constraints": {
                    "min_hold_days": self.full_constraints.min_hold_days,
                    "max_day_trades": "unlimited",
                },
                "strategies": [
                    f"{s.strategy_name}/{s.symbol} ({s.status})"
                    for s in self.full_pool
                ],
            },
        }

    def generate_promotion_report(self, candidates: list[dict]) -> str:
        """
        Generate a report of promotion candidates for human review.

        Args:
            candidates: List of dicts with strategy/symbol/sharpe/p_value/hold_days

        Returns:
            Markdown formatted report
        """
        lines = [
            "# Strategy Promotion Candidates",
            "",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Budget Pool Candidates (PDT-Compliant)",
            "",
            "| Strategy | Symbol | Sharpe | p-value | Hold Days | Approve |",
            "|----------|--------|--------|---------|-----------|---------|",
        ]

        for c in candidates:
            if c.get("hold_days", 0) >= 2:
                lines.append(
                    f"| {c['strategy']} | {c['symbol']} | {c['sharpe']:.2f} | "
                    f"{c['p_value']:.4f} | {c['hold_days']}d | [ ] |"
                )

        lines.extend([
            "",
            "## Full Pool Candidates (Day Trading OK)",
            "",
            "| Strategy | Symbol | Sharpe | p-value | Hold Days | Approve |",
            "|----------|--------|--------|---------|-----------|---------|",
        ])

        for c in candidates:
            if c.get("hold_days", 0) < 2:
                lines.append(
                    f"| {c['strategy']} | {c['symbol']} | {c['sharpe']:.2f} | "
                    f"{c['p_value']:.4f} | {c['hold_days']}d | [ ] |"
                )

        lines.extend([
            "",
            "## Instructions",
            "",
            "1. Review each candidate's backtest results",
            "2. Mark [x] next to strategies to approve",
            "3. Run promotion command for approved strategies",
            "",
        ])

        return "\n".join(lines)
