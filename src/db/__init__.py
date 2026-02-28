"""Database layer for Project Athena.

Provides SQLite-backed storage with SQLAlchemy ORM for the complete
provenance chain: data → signal → convergence → decision → execution → outcome → learning.
"""

from src.db.database import get_db, get_async_db, init_db
from src.db.models import (
    Company,
    Sector,
    ThesisRecord,
    SignpostRecord,
    LearningRecord,
    DecisionRecord,
    SignalProvenanceRecord,
    DecisionSignalLink,
    DecisionConvergence,
    LLMInteraction,
    AgentRun,
    ProcessEvent,
    AutonomyCheck,
)

__all__ = [
    "get_db",
    "get_async_db",
    "init_db",
    "Company",
    "Sector",
    "ThesisRecord",
    "SignpostRecord",
    "LearningRecord",
    "DecisionRecord",
    "SignalProvenanceRecord",
    "DecisionSignalLink",
    "DecisionConvergence",
    "LLMInteraction",
    "AgentRun",
    "ProcessEvent",
    "AutonomyCheck",
]
