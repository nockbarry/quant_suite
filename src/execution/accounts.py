"""Multi-account management for paper and live trading.

Supports three trading tiers:
1. LIVE - Real money ($200-500), strict risk limits
2. PAPER - Alpaca paper trading (~$100k), thesis testing
3. TRACKING - Paper positions (PaperPositionTracker), no broker

Usage:
    from src.execution.accounts import AccountManager, TradingAccount

    # Get a specific account
    manager = AccountManager()
    live_broker = await manager.get_broker(TradingAccount.LIVE)
    paper_broker = await manager.get_broker(TradingAccount.PAPER)

    # Get account-specific risk limits
    limits = manager.get_risk_limits(TradingAccount.LIVE)
    # limits.max_position_pct = 0.10 (10% of $500 = $50 max per position)
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional
import logging
import yaml

logger = logging.getLogger(__name__)


class TradingAccount(str, Enum):
    """Trading account types."""
    LIVE = "live"      # Real money
    PAPER = "paper"    # Alpaca paper trading
    TRACKING = "tracking"  # Paper positions (no broker)


@dataclass
class RiskLimits:
    """Risk limits for an account."""
    max_position_pct: float  # Max % of portfolio per position
    max_position_usd: float  # Max $ per position (hard cap)
    max_daily_loss_pct: float  # Max daily loss before halt
    max_sector_pct: float  # Max sector concentration
    require_approval: bool  # Require human approval for trades
    allow_options: bool  # Allow options trading
    min_cash_pct: float  # Minimum cash reserve


# Default risk limits per account type
DEFAULT_LIMITS = {
    TradingAccount.LIVE: RiskLimits(
        max_position_pct=0.15,  # 15% max per position
        max_position_usd=75.0,  # $75 hard cap (15% of $500)
        max_daily_loss_pct=0.10,  # 10% daily loss limit
        max_sector_pct=0.40,  # 40% sector max
        require_approval=True,  # Always require approval for live
        allow_options=False,  # No options with small account
        min_cash_pct=0.20,  # Keep 20% cash
    ),
    TradingAccount.PAPER: RiskLimits(
        max_position_pct=0.15,
        max_position_usd=15000.0,
        max_daily_loss_pct=0.05,
        max_sector_pct=0.45,
        require_approval=False,
        allow_options=True,
        min_cash_pct=0.05,
    ),
    TradingAccount.TRACKING: RiskLimits(
        max_position_pct=0.20,
        max_position_usd=50000.0,
        max_daily_loss_pct=1.0,  # No limit for tracking
        max_sector_pct=1.0,
        require_approval=False,
        allow_options=True,
        min_cash_pct=0.0,
    ),
}


@dataclass
class AccountInfo:
    """Account configuration and state."""
    account_type: TradingAccount
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    is_paper: bool = True
    enabled: bool = True
    description: str = ""


class AccountManager:
    """
    Manages multiple trading accounts.

    Handles:
    - Credential loading for each account type
    - Broker instantiation with correct settings
    - Risk limit enforcement
    - Account-specific storage paths
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize account manager.

        Args:
            config_path: Path to credentials.yaml
        """
        self.config_path = config_path or (
            Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
        )
        self._accounts: dict[TradingAccount, AccountInfo] = {}
        self._brokers: dict[TradingAccount, any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load account configurations from credentials file."""
        if not self.config_path.exists():
            logger.warning(f"Credentials file not found: {self.config_path}")
            return

        with open(self.config_path) as f:
            config = yaml.safe_load(f)

        # Load paper account (default alpaca config)
        alpaca = config.get("alpaca", {})
        self._accounts[TradingAccount.PAPER] = AccountInfo(
            account_type=TradingAccount.PAPER,
            api_key=alpaca.get("api_key"),
            secret_key=alpaca.get("secret_key"),
            is_paper=True,
            enabled=True,
            description="Alpaca paper trading account",
        )

        # Load live account (if configured)
        alpaca_live = config.get("alpaca_live", {})
        if alpaca_live.get("api_key"):
            self._accounts[TradingAccount.LIVE] = AccountInfo(
                account_type=TradingAccount.LIVE,
                api_key=alpaca_live.get("api_key"),
                secret_key=alpaca_live.get("secret_key"),
                is_paper=False,
                enabled=alpaca_live.get("enabled", False),
                description="Alpaca live trading account",
            )
        else:
            # Use same keys as paper but with live endpoint
            self._accounts[TradingAccount.LIVE] = AccountInfo(
                account_type=TradingAccount.LIVE,
                api_key=alpaca.get("api_key"),
                secret_key=alpaca.get("secret_key"),
                is_paper=False,
                enabled=config.get("live_trading_enabled", False),
                description="Alpaca live trading (same keys as paper)",
            )

        # Tracking account doesn't need credentials
        self._accounts[TradingAccount.TRACKING] = AccountInfo(
            account_type=TradingAccount.TRACKING,
            is_paper=True,
            enabled=True,
            description="Paper position tracking (no broker)",
        )

    async def get_broker(self, account: TradingAccount):
        """Get broker instance for an account.

        Args:
            account: Which account to get broker for

        Returns:
            Connected AlpacaBroker instance

        Raises:
            ValueError: If account is TRACKING (no broker) or not enabled
        """
        if account == TradingAccount.TRACKING:
            raise ValueError("TRACKING account has no broker - use PaperPositionTracker")

        account_info = self._accounts.get(account)
        if not account_info:
            raise ValueError(f"Account {account} not configured")

        if not account_info.enabled and account == TradingAccount.LIVE:
            raise ValueError(
                "Live trading not enabled. Set 'live_trading_enabled: true' in credentials.yaml"
            )

        # Return cached broker if exists
        if account in self._brokers:
            return self._brokers[account]

        # Create new broker
        from src.execution.broker.alpaca import AlpacaBroker

        broker = AlpacaBroker(
            api_key=account_info.api_key,
            secret_key=account_info.secret_key,
            paper=account_info.is_paper,
        )
        await broker.connect()

        self._brokers[account] = broker
        logger.info(f"Connected to {account.value} account")

        return broker

    async def close_all(self) -> None:
        """Close all broker connections."""
        for account, broker in self._brokers.items():
            try:
                await broker.disconnect()
                logger.info(f"Disconnected from {account.value}")
            except Exception as e:
                logger.error(f"Error disconnecting {account.value}: {e}")
        self._brokers.clear()

    def get_risk_limits(self, account: TradingAccount) -> RiskLimits:
        """Get risk limits for an account."""
        return DEFAULT_LIMITS.get(account, DEFAULT_LIMITS[TradingAccount.PAPER])

    def get_storage_path(self, account: TradingAccount) -> Path:
        """Get storage directory for an account.

        Returns:
            Path like ~/quant_results/accounts/live/
        """
        base = Path.home() / "quant_results" / "accounts" / account.value
        base.mkdir(parents=True, exist_ok=True)
        return base

    def is_enabled(self, account: TradingAccount) -> bool:
        """Check if an account is enabled."""
        info = self._accounts.get(account)
        return info.enabled if info else False

    def get_account_info(self, account: TradingAccount) -> Optional[AccountInfo]:
        """Get account configuration."""
        return self._accounts.get(account)

    def validate_trade(
        self,
        account: TradingAccount,
        symbol: str,
        value: float,
        portfolio_value: float,
        sector: Optional[str] = None,
        sector_exposure: float = 0.0,
        is_option: bool = False,
    ) -> tuple[bool, str]:
        """
        Validate a trade against account risk limits.

        Args:
            account: Account to trade in
            symbol: Symbol to trade
            value: Dollar value of trade
            portfolio_value: Current portfolio value
            sector: Sector of the symbol
            sector_exposure: Current exposure to this sector
            is_option: Whether this is an options trade

        Returns:
            (is_valid, reason) tuple
        """
        limits = self.get_risk_limits(account)

        # Check options allowed
        if is_option and not limits.allow_options:
            return False, f"Options not allowed on {account.value} account"

        # Check position size (% of portfolio)
        position_pct = value / portfolio_value if portfolio_value > 0 else 1.0
        if position_pct > limits.max_position_pct:
            return False, f"Position {position_pct:.1%} exceeds limit {limits.max_position_pct:.1%}"

        # Check position size (absolute $)
        if value > limits.max_position_usd:
            return False, f"Position ${value:.0f} exceeds limit ${limits.max_position_usd:.0f}"

        # Check sector concentration
        if sector_exposure + position_pct > limits.max_sector_pct:
            return False, f"Sector exposure {sector_exposure + position_pct:.1%} would exceed {limits.max_sector_pct:.1%}"

        return True, "OK"


# Convenience function for quick access
def get_account_manager() -> AccountManager:
    """Get a configured AccountManager instance."""
    return AccountManager()


async def get_broker_for_account(account: TradingAccount):
    """Quick helper to get a broker for an account type."""
    manager = AccountManager()
    return await manager.get_broker(account)
