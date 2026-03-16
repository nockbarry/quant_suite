"""Market Mover Scanner — identifies significant price moves across a broad universe.

Scans ~400-500 symbols from portfolio, theses, Finviz screens, WSB, and index
constituents. Enriches each mover with context: news headlines, screen membership,
social signals, thesis alignment. Ranks by composite context score.

Usage:
    from src.intelligence.market_movers import MarketMoverScanner

    scanner = MarketMoverScanner()
    scan = scanner.scan()
    print(f"{scan.movers_found} movers from {scan.universe_size} symbols")
    for m in scan.top_context[:5]:
        print(f"  {m.symbol}: {m.change_1d_pct:+.1f}% ctx={m.context_score:.0%}")
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)

RESULTS_DIR = paths.base


@dataclass
class MarketMover:
    """A single symbol with a significant price move and enriched context."""

    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    market_cap_tier: Optional[str] = None

    # Price data
    price: float = 0.0
    change_1d_pct: float = 0.0
    change_5d_pct: float = 0.0
    change_1m_pct: float = 0.0
    volume: int = 0
    avg_volume: int = 0
    volume_ratio: float = 0.0

    # Trigger
    trigger: str = "day_move"
    move_magnitude: float = 0.0

    # Context enrichment
    news_matches: list = field(default_factory=list)
    finviz_screens: list = field(default_factory=list)
    wsb_status: Optional[dict] = None
    thesis_alignment: Optional[dict] = None

    # Scoring
    context_score: float = 0.0
    rank: int = 0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "market_cap_tier": self.market_cap_tier,
            "price": self.price,
            "change_1d_pct": round(self.change_1d_pct, 2),
            "change_5d_pct": round(self.change_5d_pct, 2),
            "change_1m_pct": round(self.change_1m_pct, 2),
            "volume": self.volume,
            "avg_volume": self.avg_volume,
            "volume_ratio": round(self.volume_ratio, 2),
            "trigger": self.trigger,
            "move_magnitude": round(self.move_magnitude, 2),
            "news_matches": self.news_matches,
            "finviz_screens": self.finviz_screens,
            "wsb_status": self.wsb_status,
            "thesis_alignment": self.thesis_alignment,
            "context_score": round(self.context_score, 3),
            "rank": self.rank,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MarketMover":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MarketMoverScan:
    """Full scan result."""

    timestamp: str
    universe_size: int = 0
    movers_found: int = 0
    gainers: list = field(default_factory=list)
    losers: list = field(default_factory=list)
    volume_spikes: list = field(default_factory=list)
    top_context: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "universe_size": self.universe_size,
            "movers_found": self.movers_found,
            "gainers": [m.to_dict() if isinstance(m, MarketMover) else m for m in self.gainers],
            "losers": [m.to_dict() if isinstance(m, MarketMover) else m for m in self.losers],
            "volume_spikes": [m.to_dict() if isinstance(m, MarketMover) else m for m in self.volume_spikes],
            "top_context": [m.to_dict() if isinstance(m, MarketMover) else m for m in self.top_context],
        }


class MarketMoverScanner:
    """Scans a broad universe for significant price moves and enriches with context."""

    DEFAULT_THRESHOLDS = {
        "day_move_pct": 3.0,
        "week_move_pct": 10.0,
        "month_move_pct": 20.0,
        "volume_ratio": 2.0,
        "max_movers": 50,
    }

    INTRADAY_THRESHOLDS = {
        "day_move_pct": 2.0,
        "week_move_pct": 8.0,
        "month_move_pct": 15.0,
        "volume_ratio": 1.5,
        "max_movers": 50,
    }

    def __init__(self, thresholds: Optional[dict] = None, intraday: bool = False):
        base = self.INTRADAY_THRESHOLDS if intraday else self.DEFAULT_THRESHOLDS
        self.thresholds = {**base, **(thresholds or {})}
        self._news_cache = None
        self._finviz_cache = None
        self._wsb_cache = None
        self._thesis_cache = None
        self._metadata_cache = None

    def build_universe(self) -> list[str]:
        """Merge symbols from all sources into a deduplicated universe."""
        symbols = set()

        # 1. Portfolio positions from state.json
        symbols.update(self._load_portfolio_symbols())

        # 2. Thesis vehicle symbols
        thesis_positions = self._load_thesis_positions()
        symbols.update(thesis_positions.keys())

        # 3. Finviz screen symbols
        finviz = self._load_finviz_screens()
        for screen_symbols in finviz.values():
            symbols.update(screen_symbols)

        # 4. WSB trending/early symbols
        wsb = self._load_wsb_signals()
        symbols.update(wsb.keys())

        # 5. SPY/QQQ top holdings
        symbols.update(self._load_index_holdings())

        # 6. Research symbol database
        symbols.update(self._load_research_universe())

        # Filter out invalid symbols
        symbols = {
            s for s in symbols
            if s and isinstance(s, str) and 1 <= len(s) <= 5 and s.isalpha()
        }

        logger.info(f"Universe: {len(symbols)} symbols from all sources")
        return sorted(symbols)

    def fetch_price_changes(self, symbols: list[str]) -> dict[str, dict]:
        """Batch fetch 1d, 5d, 1m returns + volume for all symbols.

        Uses yfinance download() for batch efficiency.
        """
        import yfinance as yf
        import pandas as pd

        result = {}
        if not symbols:
            return result

        # Batch download — 1 month of daily data
        try:
            logger.info(f"Fetching price data for {len(symbols)} symbols...")
            # Split into chunks of 100 to avoid timeout
            all_data = pd.DataFrame()
            for i in range(0, len(symbols), 100):
                chunk = symbols[i:i + 100]
                try:
                    df = yf.download(
                        " ".join(chunk),
                        period="1mo",
                        interval="1d",
                        progress=False,
                        threads=True,
                    )
                    if not df.empty:
                        if all_data.empty:
                            all_data = df
                        else:
                            # Merge multi-level columns
                            all_data = pd.concat([all_data, df], axis=1)
                except Exception as e:
                    logger.warning(f"Chunk {i}-{i + len(chunk)} failed: {e}")

            if all_data.empty:
                logger.warning("No price data returned")
                return result

            # Handle single-symbol vs multi-symbol DataFrame structure
            if isinstance(all_data.columns, pd.MultiIndex):
                available_symbols = list(set(all_data.columns.get_level_values(1)))
            else:
                # Single symbol — wrap it
                available_symbols = symbols[:1] if len(symbols) == 1 else []
                if available_symbols:
                    all_data.columns = pd.MultiIndex.from_product(
                        [all_data.columns, available_symbols]
                    )

            for sym in available_symbols:
                try:
                    close = all_data["Close"][sym].dropna()
                    volume = all_data["Volume"][sym].dropna()

                    if len(close) < 2:
                        continue

                    current = float(close.iloc[-1])
                    prev = float(close.iloc[-2])

                    # 1-day change
                    change_1d = ((current - prev) / prev) * 100 if prev > 0 else 0

                    # 5-day change
                    change_5d = 0.0
                    if len(close) >= 6:
                        ref_5d = float(close.iloc[-6])
                        change_5d = ((current - ref_5d) / ref_5d) * 100 if ref_5d > 0 else 0

                    # 1-month change
                    change_1m = 0.0
                    if len(close) >= 2:
                        ref_1m = float(close.iloc[0])
                        change_1m = ((current - ref_1m) / ref_1m) * 100 if ref_1m > 0 else 0

                    # Volume
                    vol = int(volume.iloc[-1]) if len(volume) > 0 else 0
                    avg_vol = int(volume.mean()) if len(volume) > 0 else 0
                    vol_ratio = vol / avg_vol if avg_vol > 0 else 0

                    result[sym] = {
                        "price": round(current, 2),
                        "change_1d": round(change_1d, 2),
                        "change_5d": round(change_5d, 2),
                        "change_1m": round(change_1m, 2),
                        "volume": vol,
                        "avg_volume": avg_vol,
                        "volume_ratio": round(vol_ratio, 2),
                    }
                except Exception as e:
                    logger.debug(f"Error processing {sym}: {e}")

        except Exception as e:
            logger.error(f"Price fetch failed: {e}")

        logger.info(f"Got price data for {len(result)}/{len(symbols)} symbols")
        return result

    def identify_movers(self, price_data: dict[str, dict]) -> list[dict]:
        """Filter price data for symbols exceeding any threshold."""
        movers = []
        thresholds = self.thresholds

        for sym, data in price_data.items():
            triggers = []

            if abs(data["change_1d"]) >= thresholds["day_move_pct"]:
                triggers.append(("day_move", abs(data["change_1d"])))

            if abs(data["change_5d"]) >= thresholds["week_move_pct"]:
                triggers.append(("week_move", abs(data["change_5d"])))

            if abs(data["change_1m"]) >= thresholds["month_move_pct"]:
                triggers.append(("month_move", abs(data["change_1m"])))

            if data["volume_ratio"] >= thresholds["volume_ratio"]:
                triggers.append(("volume_spike", data["volume_ratio"]))

            if triggers:
                # Pick the strongest trigger
                primary = max(triggers, key=lambda t: t[1])
                movers.append({
                    "symbol": sym,
                    "trigger": primary[0],
                    "move_magnitude": primary[1],
                    **data,
                })

        # Sort by move magnitude descending, cap at max_movers
        movers.sort(key=lambda m: m["move_magnitude"], reverse=True)
        return movers[: thresholds["max_movers"]]

    def enrich_movers(self, raw_movers: list[dict]) -> list[MarketMover]:
        """Add context to each mover from all available data sources."""
        now = datetime.now().isoformat()

        # Load context data (cached per scan)
        news_items = self._load_news_cache()
        finviz = self._load_finviz_screens()
        wsb = self._load_wsb_signals()
        thesis_pos = self._load_thesis_positions()
        metadata = self._load_metadata()

        enriched = []
        for raw in raw_movers:
            sym = raw["symbol"]

            # News matches
            news_matches = self._match_news_to_symbol(sym, news_items)

            # Finviz screen membership
            screens = [name for name, syms in finviz.items() if sym in syms]

            # WSB status
            wsb_info = wsb.get(sym)

            # Thesis alignment
            thesis_info = thesis_pos.get(sym)

            # Metadata
            meta = metadata.get(sym, {})

            mover = MarketMover(
                symbol=sym,
                name=meta.get("name"),
                sector=meta.get("sector"),
                market_cap_tier=meta.get("market_cap_tier"),
                price=raw["price"],
                change_1d_pct=raw["change_1d"],
                change_5d_pct=raw["change_5d"],
                change_1m_pct=raw["change_1m"],
                volume=raw["volume"],
                avg_volume=raw["avg_volume"],
                volume_ratio=raw["volume_ratio"],
                trigger=raw["trigger"],
                move_magnitude=raw["move_magnitude"],
                news_matches=news_matches,
                finviz_screens=screens,
                wsb_status=wsb_info,
                thesis_alignment=thesis_info,
                timestamp=now,
            )
            enriched.append(mover)

        return enriched

    def rank_movers(self, movers: list[MarketMover]) -> list[MarketMover]:
        """Compute context_score and rank by composite signal strength."""
        if not movers:
            return movers

        # Normalize move magnitudes for scoring
        max_magnitude = max(m.move_magnitude for m in movers) or 1.0

        for m in movers:
            score = 0.0

            # Move magnitude (30%)
            score += (m.move_magnitude / max_magnitude) * 0.30

            # News matches (25%, capped)
            news_score = min(len(m.news_matches) * 0.08, 0.25)
            score += news_score

            # Finviz screen membership (15%, capped)
            finviz_score = min(len(m.finviz_screens) * 0.05, 0.15)
            score += finviz_score

            # WSB presence (10%)
            if m.wsb_status:
                phase = m.wsb_status.get("phase", "")
                wsb_score = {"EARLY": 0.10, "GROWING": 0.08, "MAINSTREAM": 0.05}.get(
                    phase, 0.03
                )
                score += wsb_score

            # Thesis alignment (15%)
            if m.thesis_alignment:
                conviction = m.thesis_alignment.get("conviction", 50)
                score += 0.10 + (conviction / 100) * 0.05

            # Volume ratio (5%)
            if m.volume_ratio > 1.0:
                score += min((m.volume_ratio - 1.0) * 0.025, 0.05)

            m.context_score = min(score, 1.0)

        # Sort by context_score descending and assign ranks
        movers.sort(key=lambda m: m.context_score, reverse=True)
        for i, m in enumerate(movers):
            m.rank = i + 1

        return movers

    def scan(self) -> MarketMoverScan:
        """Full pipeline: build universe → fetch prices → identify → enrich → rank."""
        universe = self.build_universe()

        price_data = self.fetch_price_changes(universe)

        raw_movers = self.identify_movers(price_data)

        enriched = self.enrich_movers(raw_movers)

        ranked = self.rank_movers(enriched)

        # Categorize
        gainers = sorted(
            [m for m in ranked if m.change_1d_pct > 0],
            key=lambda m: m.change_1d_pct,
            reverse=True,
        )[:20]

        losers = sorted(
            [m for m in ranked if m.change_1d_pct < 0],
            key=lambda m: m.change_1d_pct,
        )[:20]

        volume_spikes = sorted(
            [m for m in ranked if m.volume_ratio >= 1.5],
            key=lambda m: m.volume_ratio,
            reverse=True,
        )[:20]

        top_context = ranked[:20]

        return MarketMoverScan(
            timestamp=datetime.now().isoformat(),
            universe_size=len(universe),
            movers_found=len(ranked),
            gainers=gainers,
            losers=losers,
            volume_spikes=volume_spikes,
            top_context=top_context,
        )

    # ---- Context Loading Helpers ----

    def _load_portfolio_symbols(self) -> set[str]:
        """Read portfolio position symbols from state.json."""
        try:
            state_file = RESULTS_DIR / "live" / "state.json"
            if state_file.exists():
                with open(state_file) as f:
                    state = json.load(f)
                return {
                    p["symbol"]
                    for p in state.get("positions", [])
                    if p.get("symbol")
                }
        except Exception as e:
            logger.debug(f"Could not read portfolio: {e}")
        return set()

    def _load_thesis_positions(self) -> dict[str, dict]:
        """Read thesis vehicle symbols from YAML files.

        Returns {symbol: {thesis_id, thesis_name, conviction}}.
        """
        if self._thesis_cache is not None:
            return self._thesis_cache

        result = {}
        try:
            theses_dir = RESULTS_DIR / "theses"
            if theses_dir.exists():
                import yaml

                for f in theses_dir.glob("*.yaml"):
                    try:
                        with open(f) as fh:
                            thesis = yaml.safe_load(fh)
                        if thesis and thesis.get("status") == "active":
                            tid = thesis.get("id", f.stem)
                            tname = thesis.get("name", "")
                            conviction = thesis.get("conviction", 50)
                            for sym in thesis.get("positions", []):
                                if sym not in result or conviction > result[sym].get(
                                    "conviction", 0
                                ):
                                    result[sym] = {
                                        "thesis_id": tid,
                                        "thesis_name": tname,
                                        "conviction": conviction,
                                    }
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Could not read theses: {e}")

        self._thesis_cache = result
        return result

    def _load_finviz_screens(self) -> dict[str, list[str]]:
        """Read Finviz screen results. Returns {screen_name: [symbols]}."""
        if self._finviz_cache is not None:
            return self._finviz_cache

        result = {}
        try:
            screens_file = RESULTS_DIR / "scraped_data" / "finviz" / "screens_latest.json"
            if screens_file.exists():
                with open(screens_file) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for screen_name, screen_data in data.items():
                        if isinstance(screen_data, dict):
                            result[screen_name] = screen_data.get("symbols", [])
                        elif isinstance(screen_data, list):
                            result[screen_name] = screen_data
        except Exception as e:
            logger.debug(f"Could not read Finviz screens: {e}")

        self._finviz_cache = result
        return result

    def _load_wsb_signals(self) -> dict[str, dict]:
        """Read WSB signals. Returns {symbol: {phase, mentions, sentiment, ...}}."""
        if self._wsb_cache is not None:
            return self._wsb_cache

        result = {}
        try:
            wsb_file = RESULTS_DIR / "social" / "wsb_signals.json"
            if wsb_file.exists():
                with open(wsb_file) as f:
                    data = json.load(f)
                for signal in data.get("early_signals", []) + data.get(
                    "trending_signals", []
                ):
                    sym = signal.get("symbol")
                    if sym:
                        result[sym] = {
                            "phase": signal.get("current_phase", "UNKNOWN"),
                            "mentions": signal.get("mention_count", 0),
                            "sentiment": signal.get("avg_sentiment", 0),
                            "growth_rate": signal.get("growth_rate", 0),
                            "vintage_days": signal.get("signal_vintage", 0),
                        }
        except Exception as e:
            logger.debug(f"Could not read WSB signals: {e}")

        self._wsb_cache = result
        return result

    def _load_index_holdings(self) -> set[str]:
        """Get SPY/QQQ top holdings as baseline universe."""
        try:
            from src.core.universe_manager import UniverseManager

            um = UniverseManager()
            spy = um.from_etf("SPY")
            qqq = um.from_etf("QQQ")
            return set(spy + qqq)
        except Exception as e:
            logger.debug(f"Could not load index holdings: {e}")
            # Fallback: hardcode top symbols
            return {
                "AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "TSLA",
                "AVGO", "JPM", "UNH", "XOM", "JNJ", "V", "PG", "MA",
                "HD", "COST", "MRK", "ABBV", "CVX", "KO", "PEP",
                "LLY", "BAC", "CRM", "AMD", "NFLX", "ADBE", "WMT", "MCD",
            }

    def _load_research_universe(self) -> set[str]:
        """Load symbols from the research symbol database."""
        try:
            from workflows.research.symbol_universe import SYMBOL_DATABASE

            return set(SYMBOL_DATABASE.keys())
        except Exception as e:
            logger.debug(f"Could not load research universe: {e}")
            return set()

    def _load_news_cache(self) -> list[dict]:
        """Read news cache, filter to last 48 hours."""
        if self._news_cache is not None:
            return self._news_cache

        items = []
        try:
            news_file = RESULTS_DIR / "live" / "news_cache.json"
            if news_file.exists():
                with open(news_file) as f:
                    data = json.load(f)
                cutoff = (datetime.now() - timedelta(hours=48)).isoformat()
                for item in data.get("items", []):
                    ts = item.get("timestamp") or item.get("pubdate", "")
                    if ts >= cutoff or not ts:
                        items.append(item)
        except Exception as e:
            logger.debug(f"Could not read news cache: {e}")

        self._news_cache = items
        return items

    def _load_metadata(self) -> dict[str, dict]:
        """Load asset metadata from UniverseManager cache."""
        if self._metadata_cache is not None:
            return self._metadata_cache

        result = {}
        try:
            import sqlite3

            cache_path = Path.home() / ".quant_cache" / "universe_metadata.db"
            if cache_path.exists():
                with sqlite3.connect(cache_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT symbol, name, sector, market_cap_tier FROM asset_metadata"
                    ).fetchall()
                    for row in rows:
                        result[row["symbol"]] = {
                            "name": row["name"],
                            "sector": row["sector"],
                            "market_cap_tier": row["market_cap_tier"],
                        }
        except Exception as e:
            logger.debug(f"Could not read metadata cache: {e}")

        self._metadata_cache = result
        return result

    def _match_news_to_symbol(self, symbol: str, news_items: list[dict]) -> list[dict]:
        """Match news headlines to a specific symbol."""
        matches = []
        sym_lower = symbol.lower()

        # Get company names for this symbol
        try:
            from src.intelligence.thesis_keywords import SYMBOL_COMPANY_MAP

            aliases = [a.lower() for a in SYMBOL_COMPANY_MAP.get(symbol, [])]
        except ImportError:
            aliases = []

        for item in news_items:
            headline = (item.get("headline") or "").lower()
            if not headline:
                continue

            matched = False

            # Check $TICKER pattern
            if f"${sym_lower}" in headline or f"${symbol}" in (
                item.get("headline") or ""
            ):
                matched = True

            # Check symbol as word boundary
            import re

            if re.search(rf'\b{re.escape(sym_lower)}\b', headline):
                matched = True

            # Check company name aliases
            for alias in aliases:
                if alias in headline:
                    matched = True
                    break

            # Check if item already has symbol extracted
            if symbol in (item.get("symbols") or []):
                matched = True

            if matched:
                matches.append({
                    "headline": item.get("headline", "")[:200],
                    "source": item.get("source", ""),
                    "timestamp": item.get("timestamp") or item.get("pubdate", ""),
                    "thesis_matches": item.get("thesis_matches", {}),
                })

        return matches[:5]  # Cap at 5 per symbol
