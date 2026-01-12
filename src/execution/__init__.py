"""Execution layer for order management and broker integration."""

from .approval import (
    ApprovalInterface,
    CLIApprovalInterface,
    InteractiveApprovalSession,
    run_approval_session,
)
from .broker import (
    AccountInfo,
    AlpacaBroker,
    Broker,
    BrokerError,
    BrokerStatus,
    ConnectionError,
    InsufficientFundsError,
    InvalidOrderError,
    MarketClosedError,
    OrderError,
    PaperBroker,
    PaperTradingConfig,
    Quote,
)
from .order_manager import (
    ApprovalStatus,
    OrderManager,
    OrderManagerConfig,
    QueuedProposal,
)
from .pipeline import (
    DailySignalPipeline,
    ExecutionResult,
    ExecutorConfig,
    OrderExecutor,
    PipelineConfig,
    PipelineResult,
    SignalSummary,
)
from .monitoring import (
    Alert,
    AlertChannel,
    AlertLevel,
    AlertRule,
    PortfolioMonitor,
    PortfolioSnapshot,
)
from .orchestrator import (
    DailyReport,
    OrchestratorConfig,
    OrchestratorState,
    ScheduleConfig,
    TradingMode,
    TradingOrchestrator,
    run_paper_trading,
)
from .promotion import (
    PromotionCandidate,
    PromotionGates,
    PromotionPipeline,
    PromotionStage,
    get_promotion_summary,
)

__all__ = [
    # Broker
    "Broker",
    "BrokerStatus",
    "AccountInfo",
    "Quote",
    "AlpacaBroker",
    "PaperBroker",
    "PaperTradingConfig",
    # Errors
    "BrokerError",
    "ConnectionError",
    "OrderError",
    "InsufficientFundsError",
    "InvalidOrderError",
    "MarketClosedError",
    # Order Management
    "OrderManager",
    "OrderManagerConfig",
    "QueuedProposal",
    "ApprovalStatus",
    # Approval
    "ApprovalInterface",
    "CLIApprovalInterface",
    "InteractiveApprovalSession",
    "run_approval_session",
    # Pipeline
    "DailySignalPipeline",
    "PipelineConfig",
    "PipelineResult",
    "SignalSummary",
    "OrderExecutor",
    "ExecutorConfig",
    "ExecutionResult",
    # Monitoring
    "PortfolioMonitor",
    "PortfolioSnapshot",
    "Alert",
    "AlertLevel",
    "AlertRule",
    "AlertChannel",
    # Orchestrator
    "TradingOrchestrator",
    "TradingMode",
    "OrchestratorConfig",
    "OrchestratorState",
    "ScheduleConfig",
    "DailyReport",
    "run_paper_trading",
    # Promotion Pipeline
    "PromotionStage",
    "PromotionCandidate",
    "PromotionPipeline",
    "PromotionGates",
    "get_promotion_summary",
]
