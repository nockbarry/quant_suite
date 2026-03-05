"""
Data Freshness Tracker - Track data source status WITH content summaries.

Unlike collection_status.json which only tracks success/failure times,
this module surfaces WHAT each source returned - making the dashboard meaningful.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DataSourceStatus:
    """Status of a single data source with content summary."""
    name: str
    category: str  # "insider", "sentiment", "calendar", "options", "regime"
    fresh: bool  # Whether data is within expected freshness window
    last_update: datetime | None
    last_update_ago: str  # Human-readable "2h ago", "1d ago"
    top_signal: str | None  # Most actionable signal from this source
    signal_count: int  # Number of active signals
    status: str  # "healthy", "stale", "error", "no_data"
    error_message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataFreshnessSummary:
    """Summary of all data sources."""
    timestamp: datetime
    total_sources: int
    healthy_sources: int
    stale_sources: int
    error_sources: int
    sources: dict[str, DataSourceStatus] = field(default_factory=dict)
    top_signals_all: list[dict] = field(default_factory=list)  # Aggregated top signals

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_sources": self.total_sources,
            "healthy_sources": self.healthy_sources,
            "stale_sources": self.stale_sources,
            "error_sources": self.error_sources,
            "sources": {
                name: {
                    "fresh": s.fresh,
                    "last_update": s.last_update.isoformat() if s.last_update else None,
                    "last_update_ago": s.last_update_ago,
                    "top_signal": s.top_signal,
                    "signal_count": s.signal_count,
                    "status": s.status,
                    "category": s.category,
                }
                for name, s in self.sources.items()
            },
            "top_signals_all": self.top_signals_all[:10],  # Top 10 signals
        }


class DataFreshnessTracker:
    """
    Tracks data source freshness and extracts actionable content.

    Goes beyond collection_status.json to show WHAT each source returned,
    making the dashboard actually useful for decision-making.
    """

    # Expected freshness windows by source type
    FRESHNESS_WINDOWS = {
        # Real-time sources (should be within 30 min during market hours)
        "vix_structure": timedelta(minutes=30),
        "put_call": timedelta(hours=2),
        "market_breadth": timedelta(minutes=15),

        # Hourly sources
        "fed_futures": timedelta(hours=2),
        "sector_rotation": timedelta(hours=2),

        # 4-hourly sources
        "finviz_screens": timedelta(hours=6),
        "earnings_calendar": timedelta(hours=8),

        # Daily sources
        "congressional": timedelta(hours=36),
        "insider": timedelta(hours=36),
        "aaii_sentiment": timedelta(days=2),
        "economic_calendar": timedelta(days=1),
        "fda_calendar": timedelta(days=1),

        # Weekly sources
        "cot_report": timedelta(days=8),
        "newsletter_sentiment": timedelta(days=8),
    }

    # Source categories
    CATEGORIES = {
        "congressional": "insider",
        "insider": "insider",
        "options_flow": "options",
        "short_interest": "options",
        "put_call": "options",
        "vix_structure": "regime",
        "market_breadth": "regime",
        "sector_rotation": "regime",
        "aaii_sentiment": "sentiment",
        "newsletter_sentiment": "sentiment",
        "finviz_screens": "screens",
        "earnings_calendar": "calendar",
        "economic_calendar": "calendar",
        "fda_calendar": "calendar",
        "fed_futures": "calendar",
        "geopolitical": "geopolitical",
    }

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path.home() / "quant_results"
        self.live_dir = self.results_dir / "live"
        self.logs_dir = self.results_dir / "logs"

    def get_freshness_summary(self) -> DataFreshnessSummary:
        """Get complete freshness summary with content from all sources."""
        sources = {}
        top_signals = []

        # Check each source type
        source_checks = [
            ("congressional", self._check_congressional),
            ("insider", self._check_insider),
            ("vix_structure", self._check_vix_structure),
            ("put_call", self._check_put_call),
            ("aaii_sentiment", self._check_aaii_sentiment),
            ("earnings_calendar", self._check_earnings),
            ("economic_calendar", self._check_economic),
            ("fda_calendar", self._check_fda),
            ("finviz_screens", self._check_finviz),
            ("geopolitical", self._check_geopolitical),
            ("market_breadth", self._check_market_breadth),
        ]

        for name, check_func in source_checks:
            try:
                status = check_func()
                sources[name] = status
                if status.top_signal:
                    top_signals.append({
                        "source": name,
                        "category": status.category,
                        "signal": status.top_signal,
                        "signal_count": status.signal_count,
                        "fresh": status.fresh,
                    })
            except Exception as e:
                logger.error(f"Error checking {name}: {e}")
                sources[name] = DataSourceStatus(
                    name=name,
                    category=self.CATEGORIES.get(name, "other"),
                    fresh=False,
                    last_update=None,
                    last_update_ago="unknown",
                    top_signal=None,
                    signal_count=0,
                    status="error",
                    error_message=str(e),
                )

        # Sort top signals by importance
        top_signals.sort(key=lambda x: (not x["fresh"], -x["signal_count"]))

        healthy = sum(1 for s in sources.values() if s.status == "healthy")
        stale = sum(1 for s in sources.values() if s.status == "stale")
        error = sum(1 for s in sources.values() if s.status == "error")

        return DataFreshnessSummary(
            timestamp=datetime.now(),
            total_sources=len(sources),
            healthy_sources=healthy,
            stale_sources=stale,
            error_sources=error,
            sources=sources,
            top_signals_all=top_signals,
        )

    def _time_ago(self, dt: datetime | None) -> str:
        """Convert datetime to human-readable 'X ago' string."""
        if dt is None:
            return "never"

        delta = datetime.now() - dt
        if delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes}m ago"
        else:
            return "just now"

    def _check_freshness(self, name: str, last_update: datetime | None) -> bool:
        """Check if source is within its freshness window."""
        if last_update is None:
            return False

        window = self.FRESHNESS_WINDOWS.get(name, timedelta(days=1))
        return datetime.now() - last_update <= window

    def _check_congressional(self) -> DataSourceStatus:
        """Check congressional trading data."""
        history_file = self.logs_dir / "congressional_collection_history.json"
        archive_dir = self.results_dir / "congressional_archive"

        last_update = None
        top_signal = None
        signal_count = 0
        details = {}

        # Check collection history
        if history_file.exists():
            try:
                with open(history_file) as f:
                    history = json.load(f)
                if history:
                    last_entry = history[-1]
                    last_update = datetime.fromisoformat(last_entry["timestamp"])
                    result = last_entry.get("result", {})

                    if result.get("status") == "success":
                        trades = result.get("trades_found", 0)
                        if trades > 0:
                            # Get recent notable trades
                            processed_dir = archive_dir / "processed"
                            if processed_dir.exists():
                                recent_files = sorted(processed_dir.glob("*.json"), reverse=True)[:5]
                                for f in recent_files:
                                    try:
                                        with open(f) as fp:
                                            data = json.load(fp)
                                            for trade in data.get("trades", []):
                                                if trade.get("trade_type") == "purchase":
                                                    signal_count += 1
                                                    if not top_signal:
                                                        top_signal = f"{trade.get('politician', 'Unknown')} bought {trade.get('symbol', 'UNK')}"
                                    except:
                                        continue
            except Exception as e:
                logger.error(f"Error reading congressional history: {e}")

        fresh = self._check_freshness("congressional", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        if signal_count == 0:
            top_signal = "No recent congressional activity"

        return DataSourceStatus(
            name="congressional",
            category="insider",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal,
            signal_count=signal_count,
            status=status,
            details=details,
        )

    def _check_insider(self) -> DataSourceStatus:
        """Check insider trading data from Form 4 filings."""
        history_file = self.logs_dir / "insider_collection_history.json"
        archive_dir = self.results_dir / "insider_archive"

        last_update = None
        top_signal = None
        signal_count = 0

        if history_file.exists():
            try:
                with open(history_file) as f:
                    history = json.load(f)
                if history:
                    last_entry = history[-1]
                    last_update = datetime.fromisoformat(last_entry["timestamp"])
                    result = last_entry.get("result", {})

                    txns = result.get("transactions_collected", 0)
                    cluster_buys = result.get("cluster_buying_count", 0)
                    signal_count = cluster_buys if cluster_buys > 0 else txns

                    if cluster_buys > 0:
                        top_signal = f"{cluster_buys} cluster buying signals"
                    elif txns > 0:
                        top_signal = f"{txns} Form 4 filings today"
                    else:
                        top_signal = "No insider activity today"
            except Exception as e:
                logger.error(f"Error reading insider history: {e}")

        fresh = self._check_freshness("insider", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="insider",
            category="insider",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No recent insider data",
            signal_count=signal_count,
            status=status,
        )

    def _check_vix_structure(self) -> DataSourceStatus:
        """Check VIX term structure data."""
        state_file = self.live_dir / "state.json"

        last_update = None
        top_signal = None
        signal_count = 0

        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)

                market = state.get("market", {})
                vix = market.get("vix", 0)
                vix_change = market.get("vix_change_pct", 0)

                if "timestamp" in state:
                    last_update = datetime.fromisoformat(state["timestamp"])
                elif "updated_at" in state:
                    last_update = datetime.fromisoformat(state["updated_at"])

                # Generate signal based on VIX level and change
                if vix > 25:
                    top_signal = f"VIX elevated: {vix:.1f} ({vix_change:+.1f}%)"
                    signal_count = 1
                elif vix > 20:
                    top_signal = f"VIX moderate: {vix:.1f} ({vix_change:+.1f}%)"
                    signal_count = 1 if abs(vix_change) > 10 else 0
                else:
                    top_signal = f"VIX calm: {vix:.1f}"
                    signal_count = 0

            except Exception as e:
                logger.error(f"Error reading VIX from state: {e}")

        fresh = self._check_freshness("vix_structure", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="vix_structure",
            category="regime",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No VIX data",
            signal_count=signal_count,
            status=status,
        )

    def _check_put_call(self) -> DataSourceStatus:
        """Check put/call ratio data."""
        state_file = self.live_dir / "state.json"

        last_update = None
        top_signal = None
        signal_count = 0

        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)

                sentiment = state.get("sentiment", {})
                pc_ratio = sentiment.get("put_call_ratio", 0)
                pc_signal = sentiment.get("put_call_signal", "neutral")

                if "timestamp" in state:
                    last_update = datetime.fromisoformat(state["timestamp"])
                elif "updated_at" in state:
                    last_update = datetime.fromisoformat(state["updated_at"])

                if pc_ratio > 1.2:
                    top_signal = f"Extreme puts: {pc_ratio:.2f} (contrarian bullish)"
                    signal_count = 1
                elif pc_ratio < 0.6:
                    top_signal = f"Extreme calls: {pc_ratio:.2f} (contrarian bearish)"
                    signal_count = 1
                else:
                    top_signal = f"Put/Call neutral: {pc_ratio:.2f}"
                    signal_count = 0

            except Exception as e:
                logger.error(f"Error reading put/call: {e}")

        fresh = self._check_freshness("put_call", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="put_call",
            category="options",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No put/call data",
            signal_count=signal_count,
            status=status,
        )

    def _check_aaii_sentiment(self) -> DataSourceStatus:
        """Check AAII sentiment survey data."""
        state_file = self.live_dir / "state.json"

        last_update = None
        top_signal = None
        signal_count = 0

        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)

                sentiment = state.get("sentiment", {})
                fear_greed = sentiment.get("fear_greed_value", 50)

                if "timestamp" in state:
                    last_update = datetime.fromisoformat(state["timestamp"])
                elif "updated_at" in state:
                    last_update = datetime.fromisoformat(state["updated_at"])

                if fear_greed < 25:
                    top_signal = f"Extreme Fear: {fear_greed} (contrarian bullish)"
                    signal_count = 1
                elif fear_greed > 75:
                    top_signal = f"Extreme Greed: {fear_greed} (contrarian bearish)"
                    signal_count = 1
                else:
                    top_signal = f"Sentiment neutral: {fear_greed}"
                    signal_count = 0

            except Exception as e:
                logger.error(f"Error reading AAII: {e}")

        fresh = self._check_freshness("aaii_sentiment", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="aaii_sentiment",
            category="sentiment",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No sentiment data",
            signal_count=signal_count,
            status=status,
        )

    def _check_earnings(self) -> DataSourceStatus:
        """Check upcoming earnings calendar."""
        state_file = self.live_dir / "state.json"

        last_update = None
        top_signal = None
        signal_count = 0

        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)

                calendar = state.get("upcoming_events", [])
                if "timestamp" in state:
                    last_update = datetime.fromisoformat(state["timestamp"])
                elif "updated_at" in state:
                    last_update = datetime.fromisoformat(state["updated_at"])

                # Count earnings this week
                today = datetime.now().date()
                week_end = today + timedelta(days=7)

                earnings_this_week = []
                for event in calendar:
                    if event.get("type") == "earnings":
                        try:
                            event_date = datetime.fromisoformat(event.get("date", "")).date()
                            if today <= event_date <= week_end:
                                earnings_this_week.append(event.get("symbol", "UNK"))
                        except:
                            continue

                signal_count = len(earnings_this_week)
                if earnings_this_week:
                    top_signal = f"Earnings this week: {', '.join(earnings_this_week[:5])}"
                else:
                    top_signal = "No portfolio earnings this week"

            except Exception as e:
                logger.error(f"Error reading earnings: {e}")

        fresh = self._check_freshness("earnings_calendar", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="earnings_calendar",
            category="calendar",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No earnings data",
            signal_count=signal_count,
            status=status,
        )

    def _check_economic(self) -> DataSourceStatus:
        """Check economic calendar (FOMC, CPI, jobs)."""
        state_file = self.live_dir / "state.json"

        last_update = None
        top_signal = None
        signal_count = 0

        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)

                calendar = state.get("upcoming_events", [])
                if "timestamp" in state:
                    last_update = datetime.fromisoformat(state["timestamp"])
                elif "updated_at" in state:
                    last_update = datetime.fromisoformat(state["updated_at"])

                # Look for high-impact economic events
                today = datetime.now().date()
                week_end = today + timedelta(days=14)

                high_impact_types = {"FOMC", "CPI", "Jobs", "GDP", "Fed", "employment"}
                upcoming = []

                for event in calendar:
                    event_type = event.get("type", "")
                    if any(hi in event_type for hi in high_impact_types):
                        try:
                            event_date = datetime.fromisoformat(event.get("date", "")).date()
                            if today <= event_date <= week_end:
                                upcoming.append(f"{event_type} ({event_date})")
                        except:
                            continue

                signal_count = len(upcoming)
                if upcoming:
                    top_signal = f"Upcoming: {upcoming[0]}"
                else:
                    top_signal = "No major economic events soon"

            except Exception as e:
                logger.error(f"Error reading economic calendar: {e}")

        fresh = self._check_freshness("economic_calendar", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="economic_calendar",
            category="calendar",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No economic data",
            signal_count=signal_count,
            status=status,
        )

    def _check_fda(self) -> DataSourceStatus:
        """Check FDA calendar (PDUFA dates, AdCom)."""
        state_file = self.live_dir / "state.json"

        last_update = None
        top_signal = None
        signal_count = 0

        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)

                calendar = state.get("upcoming_events", [])
                if "timestamp" in state:
                    last_update = datetime.fromisoformat(state["timestamp"])
                elif "updated_at" in state:
                    last_update = datetime.fromisoformat(state["updated_at"])

                # Look for FDA events
                today = datetime.now().date()
                month_end = today + timedelta(days=30)

                fda_events = []
                for event in calendar:
                    event_type = event.get("type", "")
                    if "FDA" in event_type or "PDUFA" in event_type:
                        try:
                            event_date = datetime.fromisoformat(event.get("date", "")).date()
                            if today <= event_date <= month_end:
                                fda_events.append({
                                    "symbol": event.get("symbol", "UNK"),
                                    "date": str(event_date),
                                    "event": event_type,
                                })
                        except:
                            continue

                signal_count = len(fda_events)
                if fda_events:
                    first = fda_events[0]
                    top_signal = f"{first['symbol']} {first['event']} on {first['date']}"
                else:
                    top_signal = "No FDA events in next 30 days"

            except Exception as e:
                logger.error(f"Error reading FDA calendar: {e}")

        fresh = self._check_freshness("fda_calendar", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="fda_calendar",
            category="calendar",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No FDA data",
            signal_count=signal_count,
            status=status,
        )

    def _check_finviz(self) -> DataSourceStatus:
        """Check Finviz stock screens."""
        state_file = self.live_dir / "state.json"

        last_update = None
        top_signal = None
        signal_count = 0

        # Finviz screens are saved by FinvizScreener
        screens_file = self.results_dir / "scraped_data" / "finviz" / "screens_latest.json"
        if not screens_file.exists():
            # Fallback to old location
            screens_file = self.live_dir / "research" / "screens.json"

        if screens_file.exists():
            try:
                with open(screens_file) as f:
                    screens = json.load(f)

                last_update = datetime.fromtimestamp(screens_file.stat().st_mtime)

                # Count actionable screens
                for screen_name, results in screens.items():
                    if isinstance(results, list):
                        signal_count += len(results)

                if signal_count > 0:
                    top_signal = f"{signal_count} stocks passing screens"
                else:
                    top_signal = "No stocks passing screens"

            except Exception as e:
                logger.error(f"Error reading Finviz screens: {e}")

        fresh = self._check_freshness("finviz_screens", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="finviz_screens",
            category="screens",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No screen data",
            signal_count=signal_count,
            status=status,
        )

    def _check_geopolitical(self) -> DataSourceStatus:
        """Check geopolitical risk tracking."""
        # Geopolitical data might be in state or separate file
        state_file = self.live_dir / "state.json"

        last_update = None
        top_signal = None
        signal_count = 0

        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)

                if "timestamp" in state:
                    last_update = datetime.fromisoformat(state["timestamp"])
                elif "updated_at" in state:
                    last_update = datetime.fromisoformat(state["updated_at"])

                # Check for geopolitical mentions in alerts
                alerts = state.get("alerts", [])
                geo_regions = ["Venezuela", "China", "Middle East", "Russia", "Greenland"]

                geo_alerts = []
                for alert in alerts:
                    text = str(alert.get("message", "") + alert.get("title", ""))
                    for region in geo_regions:
                        if region.lower() in text.lower():
                            geo_alerts.append(region)
                            break

                signal_count = len(geo_alerts)
                if geo_alerts:
                    top_signal = f"Geo alerts: {', '.join(set(geo_alerts))}"
                else:
                    top_signal = "No geopolitical alerts"

            except Exception as e:
                logger.error(f"Error reading geopolitical: {e}")

        fresh = self._check_freshness("geopolitical", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="geopolitical",
            category="geopolitical",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No geopolitical data",
            signal_count=signal_count,
            status=status,
        )

    def _check_market_breadth(self) -> DataSourceStatus:
        """Check market breadth data."""
        state_file = self.live_dir / "state.json"

        last_update = None
        top_signal = None
        signal_count = 0

        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)

                market = state.get("market", {})
                if "timestamp" in state:
                    last_update = datetime.fromisoformat(state["timestamp"])
                elif "updated_at" in state:
                    last_update = datetime.fromisoformat(state["updated_at"])

                # Check for breadth data
                advancing = market.get("advancing", 0)
                declining = market.get("declining", 0)
                regime = market.get("regime", "unknown")

                if advancing and declining:
                    ratio = advancing / (declining + 0.01)
                    if ratio > 2:
                        top_signal = f"Strong breadth: {advancing}/{declining} A/D"
                        signal_count = 1
                    elif ratio < 0.5:
                        top_signal = f"Weak breadth: {advancing}/{declining} A/D"
                        signal_count = 1
                    else:
                        top_signal = f"Neutral breadth: {advancing}/{declining}"
                else:
                    top_signal = f"Regime: {regime}"

            except Exception as e:
                logger.error(f"Error reading market breadth: {e}")

        fresh = self._check_freshness("market_breadth", last_update)
        status = "healthy" if fresh else ("stale" if last_update else "no_data")

        return DataSourceStatus(
            name="market_breadth",
            category="regime",
            fresh=fresh,
            last_update=last_update,
            last_update_ago=self._time_ago(last_update),
            top_signal=top_signal or "No breadth data",
            signal_count=signal_count,
            status=status,
        )


# Singleton instance
_tracker: DataFreshnessTracker | None = None


def get_data_freshness_tracker() -> DataFreshnessTracker:
    """Get global tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = DataFreshnessTracker()
    return _tracker


def get_data_freshness() -> DataFreshnessSummary:
    """Convenience function to get freshness summary."""
    return get_data_freshness_tracker().get_freshness_summary()
