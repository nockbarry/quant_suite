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
]
