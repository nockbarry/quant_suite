"""
Strategy Promoter

Semi-automatic workflow to promote validated strategies from research to production.

Process:
1. Scan knowledge base for strategies meeting promotion criteria
2. Generate YAML config entries for candidates
3. Store pending promotions for review
4. User approves via CLI command
5. Approved strategies added to validated_strategies.yaml

Criteria for promotion:
- MCPT p-value < 0.05
- Out-of-sample Sharpe > 0.5
- Min 2 successful symbol validations (optional)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from workflows.research.knowledge_base import KnowledgeBase, StrategyResult

logger = logging.getLogger(__name__)


# Strategy class mapping - maps knowledge base strategy names to class names
STRATEGY_CLASS_MAP = {
    "rsi_reversal": "RSIReversalStrategy",
    "rsi_mean_reversion": "RSIReversalStrategy",
    "insider_technical": "InsiderTechnicalStrategy",
    "insider_confluence": "InsiderTechnicalStrategy",
    "volatility_breakout": "VolatilityBreakoutStrategy",
    "vol_breakout": "VolatilityBreakoutStrategy",
    "momentum": "MomentumStrategy",
    "trend_following": "TrendFollowingStrategy",
    "mean_reversion": "MeanReversionStrategy",
    "bollinger_reversal": "BollingerReversalStrategy",
}

# Feature requirements by strategy type
STRATEGY_FEATURES = {
    "RSIReversalStrategy": ["rsi", "returns", "mean_reversion"],
    "InsiderTechnicalStrategy": ["rsi", "bollinger_bands", "volume_features", "returns", "volatility"],
    "VolatilityBreakoutStrategy": ["atr", "volatility", "returns", "volume_features"],
    "MomentumStrategy": ["momentum", "returns", "trend_features"],
    "TrendFollowingStrategy": ["trend_features", "macd", "returns"],
    "MeanReversionStrategy": ["mean_reversion", "rsi", "bollinger_bands"],
    "BollingerReversalStrategy": ["bollinger_bands", "rsi", "returns"],
}


@dataclass
class PromotionCandidate:
    """A strategy candidate for promotion to production."""

    strategy_name: str
    class_name: str
    description: str
    symbols: list[str]
    features: list[str]
    parameters: dict[str, Any]
    best_sharpe: float
    best_p_value: float
    validation_count: int
    validation_dates: list[str]
    source_results: list[dict]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"  # pending, approved, rejected

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PromotionCandidate":
        return cls(**d)

    def to_yaml_config(self) -> dict:
        """Generate YAML config entry for this candidate."""
        # Normalize strategy name for config key
        config_key = self.strategy_name.lower().replace(" ", "_").replace("-", "_")

        return {
            config_key: {
                "enabled": True,
                "class": self.class_name,
                "description": self.description,
                "validation": {
                    "sharpe": round(self.best_sharpe, 2),
                    "p_value": round(self.best_p_value, 4),
                    "validated_on": self.symbols[0] if self.symbols else "N/A",
                    "validation_date": self.validation_dates[-1] if self.validation_dates else "",
                },
                "universe": self.symbols,
                "features": self.features,
                "parameters": self.parameters,
                "risk": {
                    "max_position_pct": 0.15,
                    "stop_loss_pct": 0.05,
                    "take_profit_pct": 0.10,
                    "min_hold_days": 2,
                    "max_hold_days": 20,
                },
                "schedule": {
                    "signal_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                    "execute_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                },
            }
        }


class StrategyPromoter:
    """
    Manages promotion of validated strategies from research to production.

    Semi-automatic workflow with approval gate.
    """

    # Default promotion thresholds
    MIN_P_VALUE = 0.05
    MIN_SHARPE = 0.5
    MIN_VALIDATIONS = 1  # Minimum successful symbol validations

    def __init__(
        self,
        knowledge_base: KnowledgeBase | None = None,
        config_path: Path | None = None,
        pending_path: Path | None = None,
    ):
        """
        Initialize strategy promoter.

        Args:
            knowledge_base: KnowledgeBase instance to scan
            config_path: Path to validated_strategies.yaml
            pending_path: Path to store pending promotions
        """
        self.kb = knowledge_base or KnowledgeBase()

        # Default paths
        project_root = Path(__file__).parent.parent.parent
        self.config_path = config_path or (project_root / "config" / "strategies" / "validated_strategies.yaml")
        self.pending_path = pending_path or (Path.home() / "quant_results" / "promotions" / "pending.json")

        # Ensure directories exist
        self.pending_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing pending promotions
        self.pending: list[PromotionCandidate] = []
        self._load_pending()

    def _load_pending(self) -> None:
        """Load pending promotions from disk."""
        if self.pending_path.exists():
            data = json.loads(self.pending_path.read_text())
            self.pending = [PromotionCandidate.from_dict(c) for c in data.get("candidates", [])]

    def _save_pending(self) -> None:
        """Save pending promotions to disk."""
        self.pending_path.write_text(json.dumps({
            "candidates": [c.to_dict() for c in self.pending],
            "updated_at": datetime.now().isoformat(),
        }, indent=2))

    def scan_for_candidates(
        self,
        min_p_value: float | None = None,
        min_sharpe: float | None = None,
        min_validations: int | None = None,
    ) -> list[PromotionCandidate]:
        """
        Scan knowledge base for strategies meeting promotion criteria.

        Args:
            min_p_value: Maximum p-value threshold (default: 0.05)
            min_sharpe: Minimum Sharpe ratio (default: 0.5)
            min_validations: Minimum successful validations (default: 1)

        Returns:
            List of PromotionCandidate objects
        """
        min_p = min_p_value if min_p_value is not None else self.MIN_P_VALUE
        min_s = min_sharpe if min_sharpe is not None else self.MIN_SHARPE
        min_v = min_validations if min_validations is not None else self.MIN_VALIDATIONS

        # Get successful strategies from knowledge base
        successes = self.kb.get_successful_strategies(min_sharpe=min_s)

        # Filter by p-value
        successes = [s for s in successes if s.p_value <= min_p]

        if not successes:
            logger.info("No strategies meet promotion criteria")
            return []

        # Group by strategy name
        by_strategy: dict[str, list[StrategyResult]] = {}
        for result in successes:
            name = result.strategy_name
            if name not in by_strategy:
                by_strategy[name] = []
            by_strategy[name].append(result)

        # Load current config to check what's already enabled
        current_strategies = self._load_current_strategies()

        candidates = []
        for strategy_name, results in by_strategy.items():
            # Check minimum validations
            if len(results) < min_v:
                logger.debug(f"Skipping {strategy_name}: only {len(results)} validations")
                continue

            # Check if already in production
            config_key = strategy_name.lower().replace(" ", "_").replace("-", "_")
            if config_key in current_strategies:
                logger.debug(f"Skipping {strategy_name}: already in production config")
                continue

            # Check if already pending
            if any(p.strategy_name == strategy_name and p.status == "pending" for p in self.pending):
                logger.debug(f"Skipping {strategy_name}: already pending")
                continue

            # Build candidate
            candidate = self._build_candidate(strategy_name, results)
            if candidate:
                candidates.append(candidate)
                logger.info(f"Found candidate: {strategy_name} (Sharpe={candidate.best_sharpe:.2f}, p={candidate.best_p_value:.4f})")

        return candidates

    def _build_candidate(
        self,
        strategy_name: str,
        results: list[StrategyResult],
    ) -> PromotionCandidate | None:
        """Build a PromotionCandidate from strategy results."""
        # Find best result
        best = max(results, key=lambda r: r.val_sharpe)

        # Collect all validated symbols
        symbols = list(set(r.symbol for r in results))

        # Collect validation dates
        dates = [r.timestamp.split("T")[0] for r in results]

        # Map to class name
        class_name = STRATEGY_CLASS_MAP.get(
            strategy_name.lower().replace(" ", "_").replace("-", "_"),
            f"{strategy_name.title().replace('_', '').replace(' ', '')}Strategy"
        )

        # Get features for this strategy type
        features = STRATEGY_FEATURES.get(class_name, ["rsi", "returns", "volatility"])

        # Build description
        description = f"Validated on {len(symbols)} symbol(s): {', '.join(symbols[:3])}"
        if len(symbols) > 3:
            description += f" and {len(symbols) - 3} more"

        # Merge parameters from best result
        params = best.params.copy() if best.params else {}

        # Source results for audit
        source_results = [
            {
                "symbol": r.symbol,
                "train_sharpe": r.train_sharpe,
                "val_sharpe": r.val_sharpe,
                "p_value": r.p_value,
                "timestamp": r.timestamp,
            }
            for r in results
        ]

        return PromotionCandidate(
            strategy_name=strategy_name,
            class_name=class_name,
            description=description,
            symbols=symbols,
            features=features,
            parameters=params,
            best_sharpe=best.val_sharpe,
            best_p_value=best.p_value,
            validation_count=len(results),
            validation_dates=dates,
            source_results=source_results,
        )

    def _load_current_strategies(self) -> set[str]:
        """Load currently enabled strategies from config."""
        if not self.config_path.exists():
            return set()

        with open(self.config_path) as f:
            config = yaml.safe_load(f)

        return set(config.get("strategies", {}).keys())

    def add_candidates(self, candidates: list[PromotionCandidate]) -> int:
        """
        Add candidates to pending list.

        Args:
            candidates: List of candidates to add

        Returns:
            Number of candidates added
        """
        added = 0
        for candidate in candidates:
            # Check for duplicates
            if any(p.strategy_name == candidate.strategy_name and p.status == "pending"
                   for p in self.pending):
                continue

            self.pending.append(candidate)
            added += 1

        self._save_pending()
        return added

    def get_pending(self) -> list[PromotionCandidate]:
        """Get all pending candidates."""
        return [c for c in self.pending if c.status == "pending"]

    def approve(self, strategy_name: str) -> bool:
        """
        Approve a pending candidate for promotion.

        Args:
            strategy_name: Name of strategy to approve

        Returns:
            True if approved, False if not found
        """
        for candidate in self.pending:
            if candidate.strategy_name == strategy_name and candidate.status == "pending":
                candidate.status = "approved"
                self._save_pending()
                logger.info(f"Approved: {strategy_name}")
                return True

        return False

    def reject(self, strategy_name: str) -> bool:
        """
        Reject a pending candidate.

        Args:
            strategy_name: Name of strategy to reject

        Returns:
            True if rejected, False if not found
        """
        for candidate in self.pending:
            if candidate.strategy_name == strategy_name and candidate.status == "pending":
                candidate.status = "rejected"
                self._save_pending()
                logger.info(f"Rejected: {strategy_name}")
                return True

        return False

    def approve_all(self) -> int:
        """
        Approve all pending candidates.

        Returns:
            Number of candidates approved
        """
        count = 0
        for candidate in self.pending:
            if candidate.status == "pending":
                candidate.status = "approved"
                count += 1

        self._save_pending()
        return count

    def promote_approved(self) -> int:
        """
        Add all approved candidates to production config.

        Returns:
            Number of strategies promoted
        """
        approved = [c for c in self.pending if c.status == "approved"]

        if not approved:
            logger.info("No approved candidates to promote")
            return 0

        # Load current config
        if self.config_path.exists():
            with open(self.config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {"strategies": {}}

        if "strategies" not in config:
            config["strategies"] = {}

        promoted = 0
        for candidate in approved:
            yaml_entry = candidate.to_yaml_config()
            config_key = list(yaml_entry.keys())[0]

            # Add to config
            config["strategies"][config_key] = yaml_entry[config_key]
            promoted += 1

            logger.info(f"Promoted to config: {candidate.strategy_name}")

        # Update config comment
        config_str = yaml.dump(config, default_flow_style=False, sort_keys=False)

        # Add header comment
        header = f"""# Validated Trading Strategies Configuration
# These strategies have passed MCPT validation (p < 0.05)
# Last updated: {datetime.now().strftime("%Y-%m-%d")}
# Auto-promoted {promoted} strategies

"""

        with open(self.config_path, "w") as f:
            f.write(header + config_str)

        # Mark as promoted (remove from pending)
        self.pending = [c for c in self.pending if c.status != "approved"]
        self._save_pending()

        return promoted

    def preview_config(self, candidate: PromotionCandidate) -> str:
        """
        Preview YAML config for a candidate.

        Args:
            candidate: Candidate to preview

        Returns:
            YAML string
        """
        yaml_entry = candidate.to_yaml_config()
        return yaml.dump(yaml_entry, default_flow_style=False, sort_keys=False)

    def summary(self) -> dict:
        """Get summary of promotion state."""
        pending = [c for c in self.pending if c.status == "pending"]
        approved = [c for c in self.pending if c.status == "approved"]
        rejected = [c for c in self.pending if c.status == "rejected"]

        return {
            "pending_count": len(pending),
            "approved_count": len(approved),
            "rejected_count": len(rejected),
            "pending_strategies": [c.strategy_name for c in pending],
            "approved_strategies": [c.strategy_name for c in approved],
            "config_path": str(self.config_path),
        }


def main():
    """CLI for strategy promotion."""
    import argparse

    parser = argparse.ArgumentParser(description="Strategy Promoter CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan for promotion candidates")
    scan_parser.add_argument("--min-sharpe", type=float, default=0.5, help="Minimum Sharpe ratio")
    scan_parser.add_argument("--min-p-value", type=float, default=0.05, help="Maximum p-value")

    # list command
    subparsers.add_parser("list", help="List pending candidates")

    # approve command
    approve_parser = subparsers.add_parser("approve", help="Approve a candidate")
    approve_parser.add_argument("strategy", nargs="?", help="Strategy name (or 'all')")

    # reject command
    reject_parser = subparsers.add_parser("reject", help="Reject a candidate")
    reject_parser.add_argument("strategy", help="Strategy name")

    # promote command
    subparsers.add_parser("promote", help="Promote approved strategies to config")

    # status command
    subparsers.add_parser("status", help="Show promotion status")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    promoter = StrategyPromoter()

    if args.command == "scan":
        print("Scanning knowledge base for promotion candidates...")
        candidates = promoter.scan_for_candidates(
            min_sharpe=args.min_sharpe,
            min_p_value=args.min_p_value,
        )

        if candidates:
            added = promoter.add_candidates(candidates)
            print(f"\nFound {len(candidates)} candidates, added {added} new to pending list:")
            for c in candidates:
                print(f"  - {c.strategy_name}: Sharpe={c.best_sharpe:.2f}, p={c.best_p_value:.4f}, symbols={c.symbols}")
        else:
            print("No new candidates found meeting criteria")

    elif args.command == "list":
        pending = promoter.get_pending()
        if pending:
            print(f"Pending candidates ({len(pending)}):")
            for c in pending:
                print(f"\n  {c.strategy_name}")
                print(f"    Class: {c.class_name}")
                print(f"    Sharpe: {c.best_sharpe:.2f}, p-value: {c.best_p_value:.4f}")
                print(f"    Symbols: {', '.join(c.symbols)}")
                print(f"    Validations: {c.validation_count}")
        else:
            print("No pending candidates")

    elif args.command == "approve":
        if not args.strategy:
            print("Usage: approve <strategy_name> or approve all")
        elif args.strategy.lower() == "all":
            count = promoter.approve_all()
            print(f"Approved {count} strategies")
        else:
            if promoter.approve(args.strategy):
                print(f"Approved: {args.strategy}")
            else:
                print(f"Strategy not found or not pending: {args.strategy}")

    elif args.command == "reject":
        if promoter.reject(args.strategy):
            print(f"Rejected: {args.strategy}")
        else:
            print(f"Strategy not found or not pending: {args.strategy}")

    elif args.command == "promote":
        count = promoter.promote_approved()
        if count:
            print(f"Promoted {count} strategies to {promoter.config_path}")
        else:
            print("No approved strategies to promote. Use 'approve' first.")

    elif args.command == "status":
        summary = promoter.summary()
        print("Strategy Promotion Status")
        print("=" * 40)
        print(f"Pending: {summary['pending_count']}")
        print(f"Approved: {summary['approved_count']}")
        print(f"Rejected: {summary['rejected_count']}")
        print(f"Config: {summary['config_path']}")

        if summary['pending_strategies']:
            print(f"\nPending: {', '.join(summary['pending_strategies'])}")
        if summary['approved_strategies']:
            print(f"Approved: {', '.join(summary['approved_strategies'])}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
