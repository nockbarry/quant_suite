"""Athena Web Dashboard — FastAPI application.

Run with:
    PYTHONPATH=. uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from src.db.database import init_async_db, ensure_columns
from src.web.auth import AuthMiddleware
from src.web.config import web_config
from src.web.routes.websocket import set_main_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup, import CLI sessions, recover stale agents."""
    import logging
    _logger = logging.getLogger(__name__)

    await init_async_db()
    ensure_columns()
    set_main_loop(asyncio.get_running_loop())

    # Auto-import CLI sessions on startup
    try:
        from src.web.services.session_scanner import import_all_cli_sessions
        count = import_all_cli_sessions()
        if count > 0:
            _logger.info(f"Auto-imported {count} CLI sessions on startup")
    except Exception as e:
        _logger.warning(f"CLI session auto-import failed: {e}")

    # Recover stale agent runs
    try:
        from src.db.write_api import athena_db
        recovered = athena_db.recover_stale_agents(max_age_hours=4)
        if recovered > 0:
            _logger.info(f"Recovered {recovered} stale agent runs on startup")
    except Exception as e:
        _logger.warning(f"Stale agent recovery failed: {e}")

    # Periodic recovery task (every 5 minutes)
    async def _periodic_recovery():
        while True:
            await asyncio.sleep(300)  # 5 minutes
            try:
                from src.db.write_api import athena_db
                recovered = athena_db.recover_stale_agents(max_age_hours=4, heartbeat_timeout_minutes=10)
                if recovered > 0:
                    _logger.info(f"Periodic recovery: recovered {recovered} stale agents")
            except Exception as e:
                _logger.debug(f"Periodic recovery check failed: {e}")

    recovery_task = asyncio.create_task(_periodic_recovery())

    yield

    # Cancel periodic task on shutdown
    recovery_task.cancel()
    try:
        await recovery_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Athena Trading Dashboard",
    description="Project Athena observability and management",
    version="1.0.0",
    lifespan=lifespan,
)

# Auth middleware (only active if token is configured)
app.add_middleware(AuthMiddleware)

# Static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Make templates available to route modules
app.state.templates = templates

# Register routes
from src.web.routes import dashboard, knowledge, theses, learnings, decisions
from src.web.routes import agents, flows, llm, signals, data_sources
from src.web.routes import reports, system, upload, api, websocket, tasks, portfolio, research
from src.web.routes import documents, intelligence

app.include_router(dashboard.router)
app.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
app.include_router(theses.router, prefix="/theses", tags=["theses"])
app.include_router(learnings.router, prefix="/learnings", tags=["learnings"])
app.include_router(decisions.router, prefix="/decisions", tags=["decisions"])
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(flows.router, prefix="/flows", tags=["flows"])
app.include_router(llm.router, prefix="/llm", tags=["llm"])
app.include_router(signals.router, prefix="/signals", tags=["signals"])
app.include_router(data_sources.router, prefix="/data", tags=["data"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(system.router, prefix="/system", tags=["system"])
app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(websocket.router, tags=["websocket"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
app.include_router(research.router, prefix="/research", tags=["research"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"])
