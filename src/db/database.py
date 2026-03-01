"""Database connection management for Athena.

Provides both sync (for daemon/scripts) and async (for FastAPI) access
to SQLite at ~/quant_results/athena.db.
"""

import logging
import os
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

from src.db.models import Base


def _get_db_path() -> Path:
    results_dir = os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results"))
    return Path(results_dir) / "athena.db"


def _get_db_url(async_mode: bool = False) -> str:
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if async_mode:
        return f"sqlite+aiosqlite:///{db_path}"
    return f"sqlite:///{db_path}"


# --- Sync engine (for daemon, scripts, migration) ---

_sync_engine = None
_SyncSessionLocal = None


def _enable_wal(dbapi_connection, connection_record):
    """Enable WAL mode for better concurrent read/write performance."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            _get_db_url(),
            echo=False,
            pool_pre_ping=True,
        )
        event.listen(_sync_engine, "connect", _enable_wal)
    return _sync_engine


def get_sync_session_factory():
    global _SyncSessionLocal
    if _SyncSessionLocal is None:
        _SyncSessionLocal = sessionmaker(bind=get_sync_engine())
    return _SyncSessionLocal


def init_db():
    """Create all tables if they don't exist (includes new junction tables)."""
    engine = get_sync_engine()
    Base.metadata.create_all(engine)
    ensure_columns()


def ensure_columns():
    """Add new columns to existing tables (safe for repeated calls)."""
    engine = get_sync_engine()
    _new_columns = [
        ("agent_runs", "artifacts", "TEXT", "'{}'"),
        ("agent_runs", "session_id", "VARCHAR(100)", "NULL"),
        ("agent_runs", "heartbeat_at", "DATETIME", "NULL"),
        ("agent_runs", "pid", "INTEGER", "NULL"),
    ]
    with engine.connect() as conn:
        for table, col, col_type, default in _new_columns:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}"
                ))
                conn.commit()
                logger.info(f"Added column {table}.{col}")
            except Exception:
                conn.rollback()  # Column already exists


@contextmanager
def get_db():
    """Sync session context manager for daemon/script use."""
    factory = get_sync_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --- Async engine (for FastAPI) ---

_async_engine = None
_AsyncSessionLocal = None


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        _async_engine = create_async_engine(
            _get_db_url(async_mode=True),
            echo=False,
        )
    return _async_engine


def get_async_session_factory():
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        from sqlalchemy.ext.asyncio import async_sessionmaker
        _AsyncSessionLocal = async_sessionmaker(
            bind=get_async_engine(),
            expire_on_commit=False,
        )
    return _AsyncSessionLocal


@asynccontextmanager
async def get_async_db():
    """Async session context manager for FastAPI use."""
    factory = get_async_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_async_db():
    """Create all tables asynchronously."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
