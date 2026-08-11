"""WebSearch / WebFetch cache with 24h TTL.

A thin JSON-backed key-value store used by evening-research and other skills
to de-dupe WebSearch / WebFetch queries across and within sessions. Same-day
re-queries (which are common when multiple sessions research the same
portfolio symbols) resolve from cache instead of hitting the network.

Usage
-----
    from src.research.websearch_cache import WebSearchCache

    cache = WebSearchCache()
    hit = cache.get("iran oil sanctions")
    if hit:
        use(hit["results"])
    else:
        results = do_web_search("iran oil sanctions")
        cache.set("iran oil sanctions", results)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class CachedEntry:
    query: str
    stored_at: str
    results: Any  # WebSearch/WebFetch payload as returned by the tool


class WebSearchCache:
    """JSON-backed WebSearch/WebFetch cache with TTL."""

    DEFAULT_TTL_HOURS = 24

    def __init__(self, path: Optional[Path] = None, ttl_hours: float = DEFAULT_TTL_HOURS):
        self.path = path or (paths.live / "websearch_cache.json")
        self.ttl = timedelta(hours=ttl_hours)

    @staticmethod
    def _norm(query: str) -> str:
        return " ".join(query.lower().split())

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.warning(f"WebSearchCache save failed: {e}")

    def _expired(self, stored_at: str) -> bool:
        try:
            t = datetime.fromisoformat(stored_at)
        except (ValueError, TypeError):
            return True
        return datetime.now() - t > self.ttl

    def get(self, query: str) -> Optional[dict]:
        """Return cached entry dict or None if miss / expired."""
        key = self._norm(query)
        data = self._load()
        entry = data.get(key)
        if not entry:
            return None
        if self._expired(entry.get("stored_at", "")):
            return None
        return entry

    def set(self, query: str, results: Any) -> None:
        key = self._norm(query)
        data = self._load()
        data[key] = {
            "query": query,
            "stored_at": datetime.now().isoformat(),
            "results": results,
        }
        data = self._prune(data)
        self._save(data)

    def _prune(self, data: dict) -> dict:
        """Drop expired entries on write to keep the file from unbounded growth."""
        return {
            k: v
            for k, v in data.items()
            if not self._expired(v.get("stored_at", ""))
        }

    def stats(self) -> dict:
        data = self._load()
        live = sum(1 for v in data.values() if not self._expired(v.get("stored_at", "")))
        return {
            "path": str(self.path),
            "total_entries": len(data),
            "live_entries": live,
            "expired_entries": len(data) - live,
            "ttl_hours": self.ttl.total_seconds() / 3600,
        }
