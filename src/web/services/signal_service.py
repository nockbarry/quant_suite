"""Signal service — re-exports provenance_service with route-expected name."""

from src.web.services.provenance_service import (
    list_signals,
    get_signal,
    get_signal_decisions,
    list_convergences,
    get_convergence,
    group_by_symbol,
)

__all__ = [
    "list_signals",
    "get_signal",
    "get_signal_decisions",
    "list_convergences",
    "get_convergence",
    "group_by_symbol",
]
