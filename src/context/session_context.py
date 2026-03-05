"""
SessionContext — accumulates context events during a Claude session and
attaches them to decisions.

Usage:
    from src.context.session_context import SessionContext

    ctx = SessionContext.get()
    ctx.add_web_search("Iran sanctions news", "US-Israel strike killed Khamenei...", ["XLE", "USO"])
    ctx.add_news_item("Oil spikes on Hormuz disruption", "Reuters", ["USO", "XLE"], sentiment="bearish")

    # When making a decision, snapshot the relevant context:
    enriched = ctx.snapshot_for_decision("XLE", window_minutes=30)
    # enriched is a dict ready to merge into DecisionRecord.context

    # After decision is saved, persist events as ProcessEvent rows:
    ctx.persist_to_db(decision_id="abc123", symbol="XLE")
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Max detail size per event (bytes) to avoid bloating DB
_MAX_DETAIL_LEN = 2048


@dataclass
class ContextEvent:
    """A single context event captured during a session."""

    timestamp: datetime
    event_type: str  # web_search, news_item, operator_obs, agent_output, market_snapshot, reasoning
    source: str  # "websearch", "news:reuters", "operator:check_5", "agent:critic", etc.
    symbols: list[str]  # Symbols this event is relevant to (empty = global)
    summary: str  # One-line summary
    detail: str  # Full content (JSON or text, truncated to _MAX_DETAIL_LEN)
    metadata: dict = field(default_factory=dict)  # Flexible: query, url, agent_id, etc.

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "source": self.source,
            "symbols": self.symbols,
            "summary": self.summary,
            "detail": self.detail[:_MAX_DETAIL_LEN],
            "metadata": self.metadata,
        }


class SessionContext:
    """Accumulates context events and attaches them to decisions.

    Singleton — call ``SessionContext.get()`` to obtain the session-wide
    instance.  Events are kept in memory and flushed to the DB when
    ``persist_to_db`` is called (typically right after a decision is logged).
    """

    _instance: Optional["SessionContext"] = None

    @classmethod
    def get(cls) -> "SessionContext":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton — clears events and resets for a new session.

        After reset, the next ``get()`` call returns a fresh instance.
        The old reference is also cleared so callers who kept it don't
        accidentally add events to an orphaned object.
        """
        if cls._instance is not None:
            cls._instance.events.clear()
            cls._instance.session_id = ""
        cls._instance = None

    def __init__(self) -> None:
        self.events: list[ContextEvent] = []
        self.session_id: str = ""  # Optionally set from Claude Code session id

    # ------------------------------------------------------------------
    # Event capture methods
    # ------------------------------------------------------------------

    def add_web_search(
        self,
        query: str,
        results_summary: str,
        symbols: list[str] | None = None,
    ) -> None:
        """Record a web search and its findings."""
        self.events.append(ContextEvent(
            timestamp=datetime.utcnow(),
            event_type="web_search",
            source="websearch",
            symbols=symbols or [],
            summary=f"Search: {query}",
            detail=results_summary[:_MAX_DETAIL_LEN],
            metadata={"query": query},
        ))

    def add_news_item(
        self,
        headline: str,
        source: str,
        symbols: list[str],
        sentiment: str = "",
        relevance: str = "",
        url: str = "",
    ) -> None:
        """Record a news item that was read and evaluated."""
        self.events.append(ContextEvent(
            timestamp=datetime.utcnow(),
            event_type="news_item",
            source=f"news:{source}",
            symbols=symbols,
            summary=headline,
            detail=headline,
            metadata={"sentiment": sentiment, "relevance": relevance, "url": url},
        ))

    def add_operator_observation(
        self,
        observation_summary: str,
        portfolio_snapshot: dict,
        alerts: list[str],
    ) -> None:
        """Record an operator check observation."""
        detail = json.dumps(
            {"portfolio": portfolio_snapshot, "alerts": alerts},
            default=str,
        )
        self.events.append(ContextEvent(
            timestamp=datetime.utcnow(),
            event_type="operator_obs",
            source="operator",
            symbols=[],
            summary=observation_summary[:200],
            detail=detail[:_MAX_DETAIL_LEN],
            metadata={"alert_count": len(alerts)},
        ))

    def add_agent_output(
        self,
        agent_type: str,
        agent_id: str,
        summary: str,
        key_findings: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> None:
        """Record output from a subagent (research, critic, etc.)."""
        detail = json.dumps(
            {"agent_type": agent_type, "findings": key_findings or []},
            default=str,
        )
        self.events.append(ContextEvent(
            timestamp=datetime.utcnow(),
            event_type="agent_output",
            source=f"agent:{agent_type}",
            symbols=symbols or [],
            summary=summary[:200],
            detail=detail[:_MAX_DETAIL_LEN],
            metadata={"agent_id": agent_id},
        ))

    def add_market_snapshot(self, snapshot: dict) -> None:
        """Record market state: SPY, VIX, sector ETFs, key prices."""
        self.events.append(ContextEvent(
            timestamp=datetime.utcnow(),
            event_type="market_snapshot",
            source="market",
            symbols=[],
            summary="Market snapshot captured",
            detail=json.dumps(snapshot, default=str)[:_MAX_DETAIL_LEN],
            metadata={},
        ))

    def add_reasoning_step(
        self,
        step: str,
        content: str,
        symbols: list[str] | None = None,
    ) -> None:
        """Record a key reasoning step (adversarial check, pre-mortem, etc.)."""
        self.events.append(ContextEvent(
            timestamp=datetime.utcnow(),
            event_type="reasoning",
            source=f"reasoning:{step}",
            symbols=symbols or [],
            summary=f"{step}: {content[:100]}",
            detail=content[:_MAX_DETAIL_LEN],
            metadata={"step": step},
        ))

    # ------------------------------------------------------------------
    # Snapshot & persistence
    # ------------------------------------------------------------------

    def snapshot_for_decision(
        self,
        symbol: str,
        window_minutes: int = 30,
    ) -> dict:
        """Return all context events relevant to a symbol within a time window.

        Returns a dict suitable for merging into DecisionRecord.context.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)

        # Events matching: symbol in event.symbols, or global events (empty symbols)
        relevant = [
            e for e in self.events
            if e.timestamp >= cutoff
            and (not e.symbols or symbol in e.symbols)
        ]

        def _collect(event_type: str) -> list[dict]:
            return [e.to_dict() for e in relevant if e.event_type == event_type]

        # Market snapshot — take the most recent one
        market_snapshots = _collect("market_snapshot")
        market_snapshot = market_snapshots[-1] if market_snapshots else None

        return {
            "session_id": self.session_id,
            "context_captured_at": datetime.utcnow().isoformat(),
            "market_snapshot": market_snapshot,
            "web_searches": _collect("web_search"),
            "news_items": _collect("news_item"),
            "operator_observations": _collect("operator_obs"),
            "agent_outputs": _collect("agent_output"),
            "reasoning_steps": _collect("reasoning"),
        }

    def persist_to_db(self, decision_id: str, symbol: str, window_minutes: int = 30) -> int:
        """Write context events as ProcessEvent records linked to decision_id.

        Returns the number of events persisted.
        """
        try:
            from src.db.write_api import athena_db
        except Exception as exc:
            logger.warning(f"Cannot import athena_db for context persistence: {exc}")
            return 0

        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        relevant = [
            e for e in self.events
            if e.timestamp >= cutoff
            and (not e.symbols or symbol in e.symbols)
        ]

        count = 0
        for event in relevant:
            try:
                athena_db.log_event(
                    event_type=event.event_type,
                    source=event.source,
                    title=event.summary[:300],
                    detail=event.detail,
                    symbol=symbol,
                    severity="info",
                    decision_id=decision_id,
                )
                count += 1
            except Exception as exc:
                logger.debug(f"Failed to persist context event: {exc}")

        logger.info(f"Persisted {count} context events for decision {decision_id}")
        return count

    # ------------------------------------------------------------------
    # Cross-process persistence
    # ------------------------------------------------------------------

    _SHARED_CONTEXT_PATH = Path.home() / "quant_results" / "scheduler" / "shared_context.jsonl"

    def flush_to_shared(self, session_type: str = "") -> int:
        """Append current events to shared JSONL file for cross-process access.

        Returns the number of events flushed.
        """
        path = self._SHARED_CONTEXT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)

        # Daily rotation: if file exists and is from a previous date, truncate
        if path.exists():
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                if mtime.date() < datetime.now().date():
                    path.unlink()
            except Exception:
                pass

        count = 0
        try:
            with open(path, "a") as f:
                for event in self.events:
                    record = event.to_dict()
                    record["session_type"] = session_type
                    f.write(json.dumps(record, default=str) + "\n")
                    count += 1
        except Exception as exc:
            logger.warning(f"Failed to flush context to shared file: {exc}")

        return count

    def load_shared_context(self, hours: float = 4.0) -> int:
        """Load recent events from shared JSONL into this session's context.

        Returns the number of events loaded.
        """
        path = self._SHARED_CONTEXT_PATH
        if not path.exists():
            return 0

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        loaded = 0

        try:
            for line in path.read_text().strip().split("\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    ts = datetime.fromisoformat(data["timestamp"])
                    if ts >= cutoff:
                        self.events.append(ContextEvent(
                            timestamp=ts,
                            event_type=data["event_type"],
                            source=data["source"],
                            symbols=data.get("symbols", []),
                            summary=data.get("summary", ""),
                            detail=data.get("detail", ""),
                            metadata=data.get("metadata", {}),
                        ))
                        loaded += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
        except Exception as exc:
            logger.warning(f"Failed to load shared context: {exc}")

        if loaded:
            logger.info(f"Loaded {loaded} shared context events from last {hours}h")
        return loaded

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def event_count(self) -> int:
        return len(self.events)

    def clear(self) -> None:
        """Clear all accumulated events."""
        self.events.clear()

    def get_symbols_mentioned(self) -> set[str]:
        """Return all symbols mentioned across events."""
        symbols: set[str] = set()
        for e in self.events:
            symbols.update(e.symbols)
        return symbols
