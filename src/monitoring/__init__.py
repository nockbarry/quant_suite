"""
Unified Monitoring for Automated Trading Firm.

The "mission control" for watching Claude operate the trading system.

Provides visibility into:
- Agent activity (Claude Code sessions, subagents)
- Data pipeline health & quality
- Signal health (IC tracking)
- Research cycle status
- Portfolio correlations
- ML model health
- System alerts

Usage:
    # Quick unified status
    python -m src.monitoring.unified_dashboard

    # Watch mode (auto-refresh)
    python -m src.monitoring.unified_dashboard --watch

    # Check specific components
    from src.monitoring import check_all
    status = await check_all()
"""

from .ops_dashboard import (
    OperationsDashboard,
    SystemHealth,
    DataFeedStatus,
    SignalHealthStatus,
    ResearchStatus,
    CronJobStatus,
    HealthStatus,
)

from .agent_monitor import (
    AgentActivityMonitor,
    AgentType,
    AgentStatus,
    AgentActivity,
    DecisionRecord,
    ResearchCycle,
    get_agent_monitor,
    log_agent_start,
    log_agent_complete,
    log_decision,
)

from .data_quality import (
    DataQualityMonitor,
    DataQualityLevel,
    DataSourceQuality,
    FieldQuality,
    get_data_quality_monitor,
    check_data_quality,
)

from .unified_dashboard import (
    UnifiedDashboard,
    UnifiedSystemStatus,
    SystemMode,
)

from .comprehensive_dashboard import (
    ComprehensiveDashboard,
    ComprehensiveStatus,
    MarketTheme,
    MarketThemeSnapshot,
    CronJobDetail,
    PositionDetail,
    ThesisExposure,
    LayerStatus,
    ClaudeActivity,
)

from .correlation_monitor import (
    CorrelationMonitor,
    CorrelationLevel,
    CorrelationPair,
    CorrelationCluster,
    PortfolioCorrelationStatus,
    check_portfolio_correlation,
)

from .model_health import (
    ModelHealthMonitor,
    ModelStatus,
    DriftType,
    ModelHealthMetrics,
    OverallModelHealth,
    get_model_health_monitor,
    check_model_health,
)

from .data_freshness_tracker import (
    DataFreshnessTracker,
    DataSourceStatus,
    DataFreshnessSummary,
    get_data_freshness_tracker,
    get_data_freshness,
)

from .signal_summary import (
    SignalAggregator,
    Signal,
    ConvergenceSignal,
    Catalyst,
    SignalSummary,
    get_signal_aggregator,
    get_signal_summary,
    get_top_signals,
    get_convergences,
    get_upcoming_catalysts,
)

from .operator_loop import (
    OperatorLoop,
    OperatorObservation,
    Alert,
    SignpostTrigger,
    AgentCompletion,
    ActionItem,
    get_operator_loop,
    run_operator_check,
)

from .improvement_tracker import (
    ImprovementTracker,
    ImprovementSuggestion,
    WeeklyReviewSummary,
    get_improvement_tracker,
    add_improvement,
)

from .signal_quality_tracker import (
    SignalQualityTracker,
    SignalQuality,
    SignalOutcome,
    get_signal_quality_tracker,
    log_signal_outcome,
    log_decision_signals,
)

from .action_queue import (
    ActionQueue,
    ActionType,
    ActionPriority,
    QueuedAction,
    get_action_queue,
    queue_signpost_trigger,
    queue_convergence,
    queue_stop_loss,
    queue_drawdown_alert,
    queue_rule_triggered,
)

from .autonomous_operator import (
    AutonomousOperator,
    ExecutionAuthority,
    SafetyRails,
    SessionState,
    TradeProposal,
    TradeType,
    ExecutionResult,
    get_autonomous_operator,
    start_autonomous_session,
)

from .swarm_monitor import (
    SwarmMonitor,
    SwarmType,
    AgentStatus,
    AgentRun,
    SwarmSignal,
    SignalConvergence,
    SwarmCycle,
    get_swarm_monitor,
    log_agent_signal,
    get_convergences,
)


async def check_all() -> dict:
    """Quick check of all monitoring systems."""
    dashboard = UnifiedDashboard()
    status = await dashboard.get_unified_status()
    return status.to_dict()


__all__ = [
    # Ops dashboard
    "OperationsDashboard",
    "SystemHealth",
    "DataFeedStatus",
    "SignalHealthStatus",
    "ResearchStatus",
    "CronJobStatus",
    "HealthStatus",
    # Agent monitor
    "AgentActivityMonitor",
    "AgentType",
    "AgentStatus",
    "AgentActivity",
    "DecisionRecord",
    "ResearchCycle",
    "get_agent_monitor",
    "log_agent_start",
    "log_agent_complete",
    "log_decision",
    # Data quality
    "DataQualityMonitor",
    "DataQualityLevel",
    "DataSourceQuality",
    "FieldQuality",
    "get_data_quality_monitor",
    "check_data_quality",
    # Unified dashboard
    "UnifiedDashboard",
    "UnifiedSystemStatus",
    "SystemMode",
    # Comprehensive dashboard
    "ComprehensiveDashboard",
    "ComprehensiveStatus",
    "MarketTheme",
    "MarketThemeSnapshot",
    "CronJobDetail",
    "PositionDetail",
    "ThesisExposure",
    "LayerStatus",
    "ClaudeActivity",
    # Correlation
    "CorrelationMonitor",
    "CorrelationLevel",
    "CorrelationPair",
    "CorrelationCluster",
    "PortfolioCorrelationStatus",
    "check_portfolio_correlation",
    # Model health
    "ModelHealthMonitor",
    "ModelStatus",
    "DriftType",
    "ModelHealthMetrics",
    "OverallModelHealth",
    "get_model_health_monitor",
    "check_model_health",
    # Quick access
    "check_all",
    # Data freshness
    "DataFreshnessTracker",
    "DataSourceStatus",
    "DataFreshnessSummary",
    "get_data_freshness_tracker",
    "get_data_freshness",
    # Signal summary
    "SignalAggregator",
    "Signal",
    "ConvergenceSignal",
    "Catalyst",
    "SignalSummary",
    "get_signal_aggregator",
    "get_signal_summary",
    "get_top_signals",
    "get_convergences",
    "get_upcoming_catalysts",
    # Operator loop
    "OperatorLoop",
    "OperatorObservation",
    "Alert",
    "SignpostTrigger",
    "AgentCompletion",
    "ActionItem",
    "get_operator_loop",
    "run_operator_check",
    # Improvement tracker
    "ImprovementTracker",
    "ImprovementSuggestion",
    "WeeklyReviewSummary",
    "get_improvement_tracker",
    "add_improvement",
    # Signal quality
    "SignalQualityTracker",
    "SignalQuality",
    "SignalOutcome",
    "get_signal_quality_tracker",
    "log_signal_outcome",
    "log_decision_signals",
    # Action queue
    "ActionQueue",
    "ActionType",
    "ActionPriority",
    "QueuedAction",
    "get_action_queue",
    "queue_signpost_trigger",
    "queue_convergence",
    "queue_stop_loss",
    "queue_drawdown_alert",
    "queue_rule_triggered",
    # Autonomous operator
    "AutonomousOperator",
    "ExecutionAuthority",
    "SafetyRails",
    "SessionState",
    "TradeProposal",
    "TradeType",
    "ExecutionResult",
    "get_autonomous_operator",
    "start_autonomous_session",
    # Swarm monitor
    "SwarmMonitor",
    "SwarmType",
    "AgentStatus",
    "AgentRun",
    "SwarmSignal",
    "SignalConvergence",
    "SwarmCycle",
    "get_swarm_monitor",
    "log_agent_signal",
    "get_convergences",
]
