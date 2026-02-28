"""System service — re-exports health_service with route-expected name."""

from src.web.services.health_service import (
    get_system_health,
    get_autonomy_status,
    get_db_stats,
)

__all__ = [
    "get_system_health",
    "get_autonomy_status",
    "get_db_stats",
]
