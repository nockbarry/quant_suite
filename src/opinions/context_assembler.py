"""Assembles compact per-symbol context for the LLM opinion prompt."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class OpinionContextAssembler:
    """Builds compact per-symbol context lines for batched opinion capture.

    Each symbol gets a one-line context like:
        MU: $103.50 RSI=45 comp=-0.2 thesis=HBM@98% s=98/r=112 news='HBM3E up 40%'

    Total batch for 80 symbols: ~4000-6000 chars (~1000-1500 tokens).
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path(
            os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results"))
        )
        self._state: Optional[dict] = None
        self._news_cache: Optional[dict] = None
        self._strategic_context: Optional[dict] = None

    def assemble_batch(self, universe: list[dict]) -> tuple[str, dict]:
        """Build the full context string for all symbols.

        Returns:
            (context_lines: str, market_summary: dict)
        """
        self._load_all()

        market = self._market_summary()
        lines = []
        for sym_entry in universe:
            line = self._symbol_context(sym_entry)
            if line:
                lines.append(line)

        return "\n".join(lines), market

    def _load_all(self) -> None:
        """Load state, news, and strategic context from disk."""
        # State
        state_path = self.results_dir / "live" / "state.json"
        if state_path.exists():
            try:
                self._state = json.loads(state_path.read_text())
            except Exception:
                self._state = {}
        else:
            self._state = {}

        # News cache
        news_path = self.results_dir / "live" / "news_cache.json"
        if news_path.exists():
            try:
                self._news_cache = json.loads(news_path.read_text())
            except Exception:
                self._news_cache = {}
        else:
            self._news_cache = {}

        # Strategic context
        ctx_path = self.results_dir / "scheduler" / "strategic_context.json"
        if ctx_path.exists():
            try:
                self._strategic_context = json.loads(ctx_path.read_text())
            except Exception:
                self._strategic_context = {}
        else:
            self._strategic_context = {}

    def _market_summary(self) -> dict:
        """Extract market-level context."""
        market = self._state.get("market", {})
        portfolio = self._state.get("portfolio", {})
        return {
            "spy_price": market.get("spy_price", 0),
            "spy_change": market.get("spy_change_pct", 0),
            "vix": market.get("vix", 0),
            "regime": market.get("regime", "unknown"),
            "sentiment": market.get("overall_sentiment", ""),
            "equity": portfolio.get("equity", 0),
            "day_pnl_pct": portfolio.get("day_pnl_pct", 0),
        }

    def _symbol_context(self, sym_entry: dict) -> str:
        """Build one-line context for a single symbol."""
        symbol = sym_entry["symbol"]
        parts = [f"{symbol}:"]

        # Price and signals from watchlist_signals
        signals = self._state.get("watchlist_signals", {}).get(symbol, {})
        price = signals.get("current_price", 0)
        if price:
            parts.append(f"${price:.2f}")

        rsi = signals.get("rsi")
        if rsi:
            parts.append(f"RSI={rsi:.0f}")

        composite = signals.get("composite_score")
        if composite is not None:
            parts.append(f"comp={composite:+.2f}")

        # Support/resistance
        support = signals.get("support")
        resistance = signals.get("resistance")
        if support and resistance:
            parts.append(f"s={support:.0f}/r={resistance:.0f}")

        # Thesis context
        if sym_entry.get("thesis_name") and sym_entry.get("conviction"):
            # Compact thesis name (first ~15 chars)
            tname = sym_entry["thesis_name"][:15].rstrip()
            parts.append(f"thesis={tname}@{sym_entry['conviction']}%")

        # Position data (if held)
        positions = self._state.get("positions", [])
        for pos in positions:
            if pos.get("symbol") == symbol:
                pnl_pct = pos.get("unrealized_pnl_pct", 0)
                weight = pos.get("weight_pct", 0)
                parts.append(f"held={pnl_pct:+.1f}%/{weight:.1f}%w")
                break

        # Most recent thesis-matched news headline (truncated)
        headline = self._get_recent_news(symbol)
        if headline:
            parts.append(f"news='{headline[:40]}'")

        # Key driver from strategic context developing patterns
        driver = self._get_key_driver(sym_entry)
        if driver:
            parts.append(f"drv='{driver[:30]}'")

        # Mover info
        if sym_entry.get("extra"):
            parts.append(sym_entry["extra"])

        return " ".join(parts)

    def _get_recent_news(self, symbol: str) -> str:
        """Get most recent news headline matching this symbol."""
        if not self._news_cache:
            return ""

        # Check state.news_events first (already thesis-matched)
        news_events = self._state.get("news_events", [])
        for event in reversed(news_events):
            affected = event.get("symbols", event.get("affected_symbols", []))
            if symbol in affected:
                return event.get("headline", event.get("title", ""))

        # Fall back to news_cache items with thesis_matches
        items = self._news_cache.get("items", [])
        for item in reversed(items[-50:]):  # Check last 50 items
            syms = item.get("symbols", [])
            thesis_matches = item.get("thesis_matches", {})
            if symbol in syms:
                return item.get("headline", "")
            # Also check if any thesis match has this symbol
            for tid, match in thesis_matches.items():
                if symbol.lower() in str(match).lower():
                    return item.get("headline", "")

        return ""

    def _get_key_driver(self, sym_entry: dict) -> str:
        """Get key driver from strategic context for this symbol's thesis."""
        if not self._strategic_context:
            return ""

        thesis_name = sym_entry.get("thesis_name", "")
        if not thesis_name:
            return ""

        # Check developing patterns for this thesis
        patterns = self._strategic_context.get("developing_patterns", [])
        for pattern in patterns:
            affected = pattern.get("affected_theses", [])
            if any(thesis_name.lower() in t.lower() for t in affected):
                return pattern.get("interpretation", pattern.get("name", ""))

        # Check thesis momentum
        momentum = self._strategic_context.get("thesis_momentum", {})
        for tname, data in momentum.items():
            if thesis_name.lower() in tname.lower():
                trend = data.get("trend", "")
                if trend and trend not in ("stable",):
                    return f"{trend} momentum"

        return ""
