"""Situation Board — same-day shared memory for the Athena swarm.

All Claude sessions and the Sentinel read/write this file. It provides:
- Market snapshot (updated every 30s by Sentinel)
- Today's observations from all agents
- Analysis requests (Sentinel → Analyst)
- Decisions made today
- Portfolio alerts
- Regime context

Auto-resets when the date changes.

File: ~/quant_results/scheduler/situation_board.json
"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from src.core.paths import paths

logger = logging.getLogger(__name__)

BOARD_PATH = paths.base / "scheduler" / "situation_board.json"

# Dedup window: skip if same source+text within this many seconds
DEDUP_WINDOW_SECONDS = 300


def _empty_board() -> dict:
    """Create a fresh board for today."""
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "last_updated": datetime.now().isoformat(),
        "market_snapshot": {
            "spy": 0,
            "spy_change": 0,
            "vix": 0,
            "vix_change_1h": 0,
            "regime": "unknown",
            "sector_leaders": [],
            "sector_laggards": [],
        },
        "today_observations": [],
        "active_analyses": [],
        "decisions_today": [],
        "portfolio_alerts": [],
        "regime_context": {
            "current": "unknown",
            "vix_trend_5d": "unknown",
            "interpretation": "",
        },
    }


class SituationBoard:
    """Same-day shared memory read/written by all sessions and the Sentinel.

    Usage:
        board = SituationBoard.load_or_create()
        board.add_observation("analyst", "assessment", "CF convergence is strong", symbols=["CF"])
        board.save()
    """

    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def load(cls) -> "SituationBoard":
        """Load current board. Returns empty board if file missing or date changed."""
        if not BOARD_PATH.exists():
            return cls(_empty_board())

        try:
            with open(BOARD_PATH) as f:
                data = json.load(f)

            # Auto-reset if date changed
            today = datetime.now().strftime("%Y-%m-%d")
            if data.get("date") != today:
                logger.info(f"Date changed ({data.get('date')} → {today}), resetting board")
                return cls(_empty_board())

            return cls(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Error loading situation board: {e}")
            return cls(_empty_board())

    @classmethod
    def load_or_create(cls) -> "SituationBoard":
        """Load existing board or create fresh one for today."""
        board = cls.load()
        if not BOARD_PATH.exists():
            board.save()
        return board

    def add_observation(
        self,
        source: str,
        obs_type: str,
        text: str,
        symbols: list[str] | None = None,
        thesis: str | None = None,
        action: str | None = None,
    ):
        """Append an observation to today's board.

        Args:
            source: Who wrote this (sentinel, analyst, morning-briefing, trade-decision, etc.)
            obs_type: Type of observation (news, convergence, assessment, decision, alert, session_complete)
            text: Human-readable description
            symbols: Affected ticker symbols
            thesis: Related thesis name
            action: Suggested action (recommend_trade, monitor, dismiss)
        """
        # Dedup: skip if same source+text within window
        now = datetime.now()
        for obs in self.data["today_observations"][-20:]:
            if obs.get("source") == source and obs.get("text") == text:
                try:
                    obs_time = datetime.fromisoformat(f"{self.data['date']}T{obs['time']}:00")
                    if (now - obs_time).total_seconds() < DEDUP_WINDOW_SECONDS:
                        return
                except (ValueError, KeyError):
                    pass

        observation = {
            "time": now.strftime("%H:%M"),
            "source": source,
            "type": obs_type,
            "text": text,
        }
        if symbols:
            observation["symbols"] = symbols
        if thesis:
            observation["thesis"] = thesis
        if action:
            observation["action"] = action

        self.data["today_observations"].append(observation)

        # Keep last 200 observations max
        if len(self.data["today_observations"]) > 200:
            self.data["today_observations"] = self.data["today_observations"][-200:]

    def add_decision(
        self,
        symbol: str,
        action: str,
        confidence: float,
        status: str,
        reasoning_summary: str,
    ):
        """Record a trade decision on the board."""
        self.data["decisions_today"].append({
            "symbol": symbol,
            "action": action,
            "confidence": round(confidence, 2),
            "status": status,
            "reasoning_summary": reasoning_summary,
            "timestamp": datetime.now().isoformat(),
        })

    def update_market_snapshot(self, state: dict):
        """Update market snapshot from state.json data.

        Args:
            state: The full state.json dict
        """
        market = state.get("market", {})
        portfolio = state.get("portfolio", {})

        snapshot = self.data["market_snapshot"]
        snapshot["spy"] = market.get("spy_price", market.get("spy", 0))
        snapshot["spy_change"] = market.get("spy_change_pct", 0)
        snapshot["vix"] = market.get("vix", 0)

        # VIX change from last snapshot
        old_vix = snapshot.get("_prev_vix", snapshot["vix"])
        snapshot["vix_change_1h"] = round(snapshot["vix"] - old_vix, 2)
        snapshot["_prev_vix"] = snapshot["vix"]

        snapshot["regime"] = market.get("rotation_theme", market.get("regime", "unknown"))

        # Sector leaders/laggards from state
        sectors = state.get("alternative_signals", {}).get("sector_rotation", {})
        if isinstance(sectors, dict):
            sector_data = sectors.get("sector_strengths", {})
            if sector_data:
                sorted_sectors = sorted(sector_data.items(), key=lambda x: x[1], reverse=True)
                snapshot["sector_leaders"] = [
                    f"{s[0]} {s[1]:+.1f}%" for s in sorted_sectors[:3]
                ]
                snapshot["sector_laggards"] = [
                    f"{s[0]} {s[1]:+.1f}%" for s in sorted_sectors[-3:]
                ]

        self.data["market_snapshot"] = snapshot

    def update_portfolio_alerts(self, state: dict):
        """Update portfolio alerts from position data."""
        alerts = []
        positions = state.get("positions", [])

        for pos in positions:
            symbol = pos.get("symbol", "UNK")
            pnl_pct = pos.get("unrealized_pnl_pct", 0)
            day_pnl_pct = pos.get("day_pnl_pct", 0)

            # Stop approaching (-12% or worse)
            if pnl_pct <= -12:
                alerts.append({
                    "symbol": symbol,
                    "type": "stop_approaching",
                    "current_pnl": f"{pnl_pct:.1f}%",
                    "stop_level": "-15%",
                    "thesis": pos.get("thesis_name", ""),
                })

            # Big daily movers (5%+ either direction)
            if abs(day_pnl_pct) >= 5:
                direction = "up" if day_pnl_pct > 0 else "down"
                alerts.append({
                    "symbol": symbol,
                    "type": f"big_mover_{direction}",
                    "current_pnl": f"{day_pnl_pct:+.1f}% today",
                    "thesis": pos.get("thesis_name", ""),
                })

        # Concentration warnings
        portfolio = state.get("portfolio", {})
        equity = portfolio.get("equity", 1)
        if equity > 0:
            for pos in positions:
                market_value = abs(pos.get("market_value", 0))
                pct = (market_value / equity) * 100
                if pct > 9:
                    alerts.append({
                        "symbol": pos.get("symbol", "UNK"),
                        "type": "concentration",
                        "current_pnl": f"{pct:.1f}% of portfolio",
                        "stop_level": "10% max",
                        "thesis": pos.get("thesis_name", ""),
                    })

        self.data["portfolio_alerts"] = alerts

    def update_regime_context(self, regime: str, interpretation: str = ""):
        """Update regime context."""
        self.data["regime_context"]["current"] = regime
        if interpretation:
            self.data["regime_context"]["interpretation"] = interpretation

    def add_analysis_request(self, trigger: str, context: str) -> str:
        """Queue an analysis request for the next Analyst session.

        Args:
            trigger: What triggered the request (convergence, urgent_news, vix_spike, etc.)
            context: Description of what needs analysis

        Returns:
            The analysis request ID
        """
        analysis_id = f"a_{uuid.uuid4().hex[:8]}"
        self.data["active_analyses"].append({
            "id": analysis_id,
            "trigger": trigger,
            "status": "pending",
            "context": context,
            "requested_at": datetime.now().isoformat(),
        })

        # Keep max 20 analysis requests
        if len(self.data["active_analyses"]) > 20:
            # Remove oldest consumed ones first
            consumed = [a for a in self.data["active_analyses"] if a["status"] == "consumed"]
            pending = [a for a in self.data["active_analyses"] if a["status"] != "consumed"]
            self.data["active_analyses"] = pending[-20:]

        return analysis_id

    def get_pending_analyses(self) -> list[dict]:
        """Get unconsumed analysis requests."""
        return [
            a for a in self.data.get("active_analyses", [])
            if a.get("status") == "pending"
        ]

    def consume_analysis(self, analysis_id: str):
        """Mark an analysis as consumed."""
        for a in self.data.get("active_analyses", []):
            if a.get("id") == analysis_id:
                a["status"] = "consumed"
                a["consumed_at"] = datetime.now().isoformat()
                break

    def save(self):
        """Write board to disk atomically (write tmp + rename)."""
        self.data["last_updated"] = datetime.now().isoformat()
        self.data["date"] = datetime.now().strftime("%Y-%m-%d")

        BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = BOARD_PATH.with_suffix(".tmp")

        try:
            with open(tmp_path, "w") as f:
                json.dump(self.data, f, indent=2, default=str)
            os.rename(str(tmp_path), str(BOARD_PATH))
        except OSError as e:
            logger.error(f"Error saving situation board: {e}")
            # Clean up temp file
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def get_summary(self) -> str:
        """One-paragraph summary for Claude session injection.

        Returns a concise text block that can be appended to system prompts.
        """
        parts = []

        # Market state
        snap = self.data.get("market_snapshot", {})
        if snap.get("spy"):
            parts.append(
                f"Market: SPY {snap['spy']:.0f} ({snap.get('spy_change', 0):+.1f}%), "
                f"VIX {snap.get('vix', 0):.1f}, regime={snap.get('regime', '?')}"
            )

        # Today's key observations (last 5)
        obs = self.data.get("today_observations", [])
        if obs:
            recent = obs[-5:]
            obs_texts = [f"[{o['time']}] {o['source']}: {o['text'][:80]}" for o in recent]
            parts.append(f"Today ({len(obs)} observations): " + " | ".join(obs_texts))

        # Decisions
        decisions = self.data.get("decisions_today", [])
        if decisions:
            dec_texts = [f"{d['symbol']} {d['action']}" for d in decisions]
            parts.append(f"Decisions today: {', '.join(dec_texts)}")

        # Alerts
        alerts = self.data.get("portfolio_alerts", [])
        if alerts:
            alert_texts = [f"{a['symbol']} {a['type']}" for a in alerts[:3]]
            parts.append(f"Alerts: {', '.join(alert_texts)}")

        # Pending analyses
        pending = self.get_pending_analyses()
        if pending:
            parts.append(f"Pending analyses: {len(pending)} ({', '.join(p['trigger'] for p in pending[:3])})")

        return " || ".join(parts) if parts else "No situation board data yet."
