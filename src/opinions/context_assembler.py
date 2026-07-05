"""Assembles compact per-symbol context for the LLM opinion prompt.

Integrates 11 data sources into one-line-per-symbol context:
1. state.json: price, RSI, composite, support/resistance, positions
2. news_cache.json: thesis-matched headlines
3. strategic_context.json: developing patterns, momentum, upcoming catalysts
4. signal_engines.json: crisis alpha + conviction velocity
5. signal_digest.json: multi-source convergences
6. alternative_signals: analyst targets, squeeze candidates, Finviz screens, WSB
7. prediction_market_signals.json: Polymarket/Kalshi probabilities
8. cross_reference_alerts.json: red flags (conviction divergence, etc.)
9. commodity files: fertilizer/shipping/LNG/Hormuz ratios
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class OpinionContextAssembler:
    """Builds compact per-symbol context lines for batched opinion capture.

    Each symbol gets a one-line context like:
        MU: $103.50 RSI=45 comp=-0.2 thesis=HBM@98% s=98/r=112 tgt=$178@60%up
            cv=REDUCE/-20pp news='HBM3E up 40%' scr=earn_win

    Total batch for 80 symbols: ~5000-8000 chars (~1500-2000 tokens).
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path(
            os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results"))
        )
        self._state: Optional[dict] = None
        self._news_cache: Optional[dict] = None
        self._strategic_context: Optional[dict] = None
        self._signal_engines: Optional[dict] = None
        self._signal_digest: Optional[dict] = None
        self._prediction_markets: Optional[dict] = None
        self._cross_ref_alerts: Optional[dict] = None
        self._commodity_data: Optional[dict] = None

    def assemble_batch(self, universe: list[dict], blind: bool = False) -> tuple[str, dict]:
        """Build the full context string for all symbols.

        Args:
            universe: symbol entries (dicts with at least "symbol").
            blind: strip advocacy signals — thesis names/conviction, held
                position P&L/weight, conviction velocity. Used by the blind
                probability elicitation (src/probability/blind_forecast.py):
                confidence stated inside a context that argues for a position
                is anti-calibrated, so the sizing forecast must never see the
                narrative. Market facts (price, RSI, news, catalysts) stay.

        Returns:
            (context_lines: str, market_summary: dict)
        """
        self._load_all()

        market = self._market_summary()
        lines = []
        for sym_entry in universe:
            line = self._symbol_context(sym_entry, blind=blind)
            if line:
                lines.append(line)

        return "\n".join(lines), market

    def _load_all(self) -> None:
        """Load all data sources from disk."""
        live = self.results_dir / "live"
        sched = self.results_dir / "scheduler"

        self._state = self._load_json(live / "state.json")
        self._news_cache = self._load_json(live / "news_cache.json")
        self._strategic_context = self._load_json(sched / "strategic_context.json")
        self._signal_engines = self._load_json(live / "signal_engines.json")
        self._signal_digest = self._load_json(sched / "signal_digest.json")
        self._prediction_markets = self._load_json(live / "prediction_market_signals.json")
        self._cross_ref_alerts = self._load_json(live / "cross_reference_alerts.json")

        # Commodity data (multiple files merged)
        self._commodity_data = {}
        for fname in ("fertilizer_prices.json", "shipping_rates.json",
                       "lng_prices.json", "hormuz_status.json"):
            data = self._load_json(live / fname)
            if data:
                self._commodity_data.update(data)

        # Pre-build lookup indexes for efficiency
        self._build_lookups()

    def _load_json(self, path: Path) -> dict:
        """Load a JSON file, returning empty dict on any error."""
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _build_lookups(self) -> None:
        """Pre-build per-symbol lookup indexes from aggregate data."""
        # Crisis alpha: symbol → {hit_rate, entry, rsi, vix}
        self._crisis_alpha: dict[str, dict] = {}
        for sig in self._signal_engines.get("crisis_alpha", []):
            sym = sig.get("symbol", "")
            if sym:
                self._crisis_alpha[sym] = sig

        # Conviction velocity: thesis_name → {direction, velocity_3d, symbols}
        self._conv_velocity: dict[str, dict] = {}
        for sig in self._signal_engines.get("conviction_velocity", []):
            for sym in sig.get("symbols", []):
                self._conv_velocity[sym] = sig

        # Convergences: symbol → {direction, source_count}
        self._convergences: dict[str, dict] = {}
        for conv in self._signal_digest.get("convergences", []):
            sym = conv.get("symbol", "")
            if sym:
                self._convergences[sym] = conv

        # Analyst targets: symbol → {mean_target, upside_pct}
        self._analyst: dict[str, dict] = {}
        alt = self._state.get("alternative_signals", {})
        for sig in alt.get("analyst_signals", []):
            sym = sig.get("symbol", "")
            if sym:
                self._analyst[sym] = sig

        # Squeeze candidates: symbol → {short_pct, squeeze_score}
        self._squeeze: dict[str, dict] = {}
        for sq in alt.get("squeeze_candidates", []):
            sym = sq.get("symbol", sq.get("ticker", ""))
            if sym:
                self._squeeze[sym] = sq

        # Finviz screen membership: symbol → set of screen names
        self._screens: dict[str, set] = {}
        screens = alt.get("screens_finviz", {})
        for screen_name, screen_data in screens.items():
            if isinstance(screen_data, dict):
                for sym in screen_data.get("symbols", []):
                    self._screens.setdefault(sym, set()).add(screen_name)
            elif isinstance(screen_data, list):
                for sym in screen_data:
                    self._screens.setdefault(sym, set()).add(screen_name)

        # WSB signals: symbol → {mention_count, growth_rate, sentiment}
        self._wsb: dict[str, dict] = {}
        wsb_data = alt.get("social_wsb", {})
        for sig in wsb_data.get("early_signals", []):
            sym = sig.get("symbol", "")
            if sym:
                self._wsb.setdefault(sym, {}).update(sig)
                self._wsb[sym]["wsb_type"] = "early"
        for sig in wsb_data.get("trending_signals", []):
            sym = sig.get("symbol", "")
            if sym:
                self._wsb.setdefault(sym, {}).update(sig)
                self._wsb[sym]["wsb_type"] = "trending"

        # Prediction markets: symbol → {probability, direction, detail}
        self._pred_markets: dict[str, dict] = {}
        for sig in self._prediction_markets.get("signals", []):
            for sym in sig.get("matched_thesis_symbols", []):
                self._pred_markets[sym] = sig

        # Cross-ref alerts: symbol → {type, severity}
        self._alerts: dict[str, dict] = {}
        for alert in self._cross_ref_alerts.get("alerts", []):
            severity = alert.get("severity", "")
            if severity in ("red_flag", "warning"):
                for sym in alert.get("symbols", []):
                    self._alerts[sym] = alert

        # Upcoming catalysts: symbol → {date, event}
        self._catalysts: dict[str, dict] = {}
        for cat in self._strategic_context.get("upcoming_catalysts", []):
            for sym in cat.get("affected", cat.get("symbols", [])):
                if sym not in self._catalysts:  # Keep first (soonest)
                    self._catalysts[sym] = cat

    def _market_summary(self) -> dict:
        """Extract market-level context including Hormuz disruption."""
        market = self._state.get("market", {})
        portfolio = self._state.get("portfolio", {})

        summary = {
            "spy_price": market.get("spy_price", 0),
            "spy_change": market.get("spy_change_pct", 0),
            "vix": market.get("vix", 0),
            "regime": market.get("regime", "unknown"),
            "sentiment": market.get("overall_sentiment", ""),
            "equity": portfolio.get("equity", 0),
            "day_pnl_pct": portfolio.get("day_pnl_pct", 0),
        }

        # Add Hormuz disruption level (global context for energy names)
        hormuz_pct = self._commodity_data.get("disruption_level_pct")
        if hormuz_pct:
            summary["hormuz_disruption"] = hormuz_pct

        return summary

    def _symbol_context(self, sym_entry: dict, blind: bool = False) -> str:
        """Build one-line context for a single symbol."""
        symbol = sym_entry["symbol"]
        parts = [f"{symbol}:"]

        # --- Core: price, RSI, composite, support/resistance ---
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

        support = signals.get("support")
        resistance = signals.get("resistance")
        if support and resistance:
            parts.append(f"s={support:.0f}/r={resistance:.0f}")

        # --- Thesis context (advocacy — stripped in blind mode) ---
        if not blind and sym_entry.get("thesis_name") and sym_entry.get("conviction"):
            tname = sym_entry["thesis_name"][:15].rstrip()
            parts.append(f"thesis={tname}@{sym_entry['conviction']}%")

        # --- Position data (if held; advocacy — stripped in blind mode) ---
        if not blind:
            for pos in self._state.get("positions", []):
                if pos.get("symbol") == symbol:
                    pnl_pct = pos.get("unrealized_pnl_pct", 0)
                    weight = pos.get("weight_pct", 0)
                    parts.append(f"held={pnl_pct:+.1f}%/{weight:.1f}%w")
                    break

        # --- NEW: Analyst targets (sell-side consensus) ---
        analyst = self._analyst.get(symbol, {})
        mean_tgt = analyst.get("mean_target")
        upside = analyst.get("target_upside_pct")
        if mean_tgt and upside:
            parts.append(f"tgt=${mean_tgt:.0f}@{upside:.0f}%up")

        # --- NEW: Crisis alpha signal (highest IC) ---
        crisis = self._crisis_alpha.get(symbol)
        if crisis:
            hr = crisis.get("hit_rate", 0)
            entry = crisis.get("entry", 0)
            parts.append(f"crisis_alpha={hr:.0%}@{entry:.0f}")

        # --- NEW: Conviction velocity (derived from thesis conviction —
        # advocacy, stripped in blind mode) ---
        cv = None if blind else self._conv_velocity.get(symbol)
        if cv:
            direction = cv.get("direction", "")
            vel = cv.get("velocity_3d", 0)
            if direction and vel:
                parts.append(f"cv={direction}/{vel:+.0f}pp")

        # --- NEW: Signal convergence ---
        conv = self._convergences.get(symbol)
        if conv:
            c_dir = conv.get("direction", "")
            c_src = conv.get("source_count", 0)
            parts.append(f"conv={c_dir}({c_src}src)")

        # --- NEW: Upcoming catalyst ---
        cat = self._catalysts.get(symbol)
        if cat:
            c_date = cat.get("date", "")
            c_event = cat.get("event", "")[:20]
            if c_date:
                parts.append(f"cat={c_event}@{c_date}")

        # --- NEW: Prediction market ---
        pm = self._pred_markets.get(symbol)
        if pm:
            prob = pm.get("current_probability", 0)
            pm_dir = pm.get("signal_direction", "")
            if prob:
                parts.append(f"pm={pm_dir}({prob:.0%})")

        # --- NEW: Cross-reference alert ---
        alert = self._alerts.get(symbol)
        if alert:
            a_type = alert.get("alert_type", "")[:20]
            # conviction_price_divergence is derived from thesis conviction —
            # advocacy, not market fact; blind mode must not see it
            if not (blind and "conviction" in a_type.lower()):
                parts.append(f"ALERT={a_type}")

        # --- NEW: Commodity ratios (for thesis-linked commodity names) ---
        self._add_commodity_context(symbol, parts)

        # --- NEW: Finviz screen membership (priority-1 only) ---
        screens = self._screens.get(symbol, set())
        priority_screens = screens & {"momentum_leaders", "volume_breakouts",
                                       "earnings_winners", "insider_buying"}
        if priority_screens:
            parts.append(f"scr={','.join(s[:8] for s in priority_screens)}")

        # --- NEW: WSB signal ---
        wsb = self._wsb.get(symbol)
        if wsb:
            wsb_type = wsb.get("wsb_type", "")
            mentions = wsb.get("mention_count", 0)
            if mentions >= 5:
                parts.append(f"wsb={wsb_type}({mentions})")

        # --- News headline (last, as it's the longest tag) ---
        headline = self._get_recent_news(symbol)
        if headline:
            parts.append(f"news='{headline[:35]}'")

        # --- Key driver ---
        driver = self._get_key_driver(sym_entry)
        if driver:
            parts.append(f"drv='{driver[:25]}'")

        # Mover info from universe
        if sym_entry.get("extra"):
            parts.append(sym_entry["extra"])

        return " ".join(parts)

    def _add_commodity_context(self, symbol: str, parts: list) -> None:
        """Add commodity-specific ratios for relevant symbols."""
        if not self._commodity_data:
            return

        commodity_map = {
            "CF": ("cf_ung_ratio", "cf_change_5d"),
            "MOS": ("mos_change_5d",),
            "NTR": ("ntr_change_5d",),
            "FRO": ("bno_bdry_ratio",),
            "DHT": ("bno_bdry_ratio",),
            "ZIM": ("bdry_change_5d",),
            "LNG": ("lng_ung_ratio",),
            "FLNG": ("lng_ung_ratio",),
            "UNG": ("ung_change_5d",),
            "USO": ("brent_wti_spread_pct",),
            "BNO": ("bno_change_5d",),
        }

        keys = commodity_map.get(symbol, ())
        tags = []
        for key in keys:
            val = self._commodity_data.get(key)
            if val is not None:
                if "ratio" in key:
                    tags.append(f"{key.split('_')[0]}r={val:.2f}")
                elif "change" in key:
                    tags.append(f"5d={val:+.1f}%")
                elif "spread" in key:
                    tags.append(f"spread={val:.1f}%")
        if tags:
            parts.append(" ".join(tags))

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

        # Fall back to news_cache items
        items = self._news_cache.get("items", [])
        for item in reversed(items[-50:]):
            syms = item.get("symbols", [])
            if symbol in syms:
                return item.get("headline", "")
            thesis_matches = item.get("thesis_matches", {})
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
