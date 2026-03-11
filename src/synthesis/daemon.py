"""Live Daemon - Continuously updates unified state.

Background process that:
1. Runs during market hours (or on-demand)
2. Pulls from all existing components
3. Builds UnifiedState
4. Writes to ~/quant_results/live/state.json
5. Updates every 5 minutes (configurable)

Usage:
    # One-shot update
    daemon = LiveDaemon()
    state = await daemon.update_now()

    # Continuous monitoring
    daemon = LiveDaemon()
    await daemon.start(interval_minutes=5)
    # ... later
    await daemon.stop()

    # CLI
    python -m src.synthesis.daemon --interval 5
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import json

from src.core.paths import paths
from .state import (
    UnifiedState,
    MarketSnapshot,
    PortfolioSnapshot,
    PositionSnapshot,
    RiskSnapshot,
    SentimentSnapshot,
    CalendarEvent,
    ResearchIndex,
    ThesisSummary,
    PendingDecision,
    LearningSummary,
    AlertSnapshot,
    # NEW: Pre-computed data structures (P0/P1)
    ThesisPositionDetail,
    ThesisPerformance,
    ConcentrationAnalysis,
    PeriodPerformance,
    SoldPositionTrack,
    SoldTracking,
    ProfitTierStatus,
    TodayOrder,
    TodayOrders,
    DataValidation,
    # NEW: P2 features (Added 2026-01-10)
    SignpostAlert,
    NewsUrgencyAlert,
    ConvictionDecayResult,
    PortfolioHistorySnapshot,
    PortfolioHistory,
)
from .signals import SignalAggregator, AggregatedSignal

logger = logging.getLogger(__name__)


class LiveDaemon:
    """
    Daemon that maintains the unified state file.

    Integrates with existing components:
    - market_breadth.py for market context
    - sentiment.py for sentiment indicators
    - position_monitor.py for risk metrics
    - alert_manager.py for active alerts
    - calendar_manager.py for upcoming events
    - decision_logger.py for pending decisions
    - SignalAggregator for watchlist signals
    """

    DEFAULT_WATCHLIST = [
        "SPY", "QQQ", "IWM",  # Indices
        "XLE", "XLF", "XLK",  # Sectors
        "AAPL", "MSFT", "NVDA", "GOOGL", "META",  # Tech
        "SLB", "HAL", "OXY",  # Energy
    ]

    def __init__(
        self,
        watchlist: Optional[list[str]] = None,
        output_path: Optional[Path] = None,
    ):
        """Initialize daemon.

        Args:
            watchlist: Symbols to track signals for.
                      If None, loads from config/watchlist.yaml or uses DEFAULT_WATCHLIST.
            output_path: Where to write state.json.
                        Defaults to paths.live_state.
        """
        self.watchlist = watchlist or self._load_watchlist()
        self.output_path = output_path or paths.live_state
        self.signal_aggregator = SignalAggregator(watchlist=self.watchlist)

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._sector_cache: dict[str, str] = {}  # Cache for yfinance sector lookups

    def _load_watchlist(self) -> list[str]:
        """Load watchlist from config file or use defaults.

        Loads from config/watchlist.yaml if it exists, otherwise uses DEFAULT_WATCHLIST.
        """
        config_path = paths.base / "config" / "watchlist.yaml"
        if config_path.exists():
            try:
                import yaml
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                symbols = config.get("symbols", [])
                if symbols:
                    logger.info(f"Loaded {len(symbols)} symbols from watchlist config")
                    return symbols
            except Exception as e:
                logger.warning(f"Could not load watchlist config: {e}")
        return self.DEFAULT_WATCHLIST

    async def start(self, interval_minutes: int = 5) -> None:
        """Start continuous state updates.

        Args:
            interval_minutes: Update interval.
        """
        if self._running:
            logger.warning("Daemon already running")
            return

        self._running = True
        logger.info(f"Starting live daemon with {interval_minutes}m interval")

        async def _loop():
            while self._running:
                try:
                    await self.update_now()
                except Exception as e:
                    logger.error(f"Update failed: {e}")

                await asyncio.sleep(interval_minutes * 60)

        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        """Stop the daemon."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Live daemon stopped")

    async def update_now(self) -> UnifiedState:
        """
        Generate and write current unified state.

        Returns:
            The generated UnifiedState.
        """
        logger.info("Updating unified state...")
        now = datetime.now()

        # Track component freshness for validation
        component_timestamps = {}
        missing_components = []
        warnings = []

        # Determine if market is open
        market_open = self._is_market_open(now)

        # Gather all components with error tracking
        try:
            market = await self._get_market_snapshot()
            component_timestamps['market'] = now
        except Exception as e:
            logger.error(f"Failed to get market snapshot: {e}")
            market = self._get_default_market_snapshot()
            missing_components.append('market')

        try:
            sentiment = await self._get_sentiment_snapshot()
            component_timestamps['sentiment'] = now
        except Exception as e:
            logger.error(f"Failed to get sentiment: {e}")
            sentiment = self._get_default_sentiment_snapshot()
            missing_components.append('sentiment')

        try:
            portfolio = await self._get_portfolio_snapshot()
            component_timestamps['portfolio'] = now
        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            portfolio = self._get_default_portfolio_snapshot()
            missing_components.append('portfolio')

        try:
            positions = await self._get_positions()
            component_timestamps['positions'] = now
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            positions = []
            missing_components.append('positions')

        # Fix: Update portfolio.total_positions from actual positions count
        if positions and hasattr(portfolio, 'total_positions'):
            portfolio.total_positions = len(positions)
            # Also compute market exposure
            if portfolio.equity > 0:
                total_market_value = sum(
                    abs(float(getattr(p, 'market_value', 0) or 0))
                    for p in positions
                )
                portfolio.market_exposure_pct = round(
                    (total_market_value / portfolio.equity) * 100, 2
                )

        try:
            risk = await self._get_risk_snapshot()
            component_timestamps['risk'] = now
        except Exception as e:
            logger.error(f"Failed to get risk: {e}")
            risk = self._get_default_risk_snapshot()
            missing_components.append('risk')

        signals = self._get_signals()
        theses = await self._get_theses()
        pending = await self._get_pending_decisions()
        learnings = await self._get_recent_learnings()
        alerts = await self._get_alerts()
        events = await self._get_calendar_events()
        research = self._get_research_index()

        # NEW: Compute pre-computed data
        thesis_performance = await self._compute_thesis_performance(positions, theses, portfolio.equity)
        concentration = self._compute_concentration(positions, theses, portfolio.equity)
        period_performance = await self._compute_period_performance(portfolio, market)
        sold_tracking = await self._compute_sold_tracking()
        profit_tiers = self._compute_profit_tiers(positions)
        today_orders = await self._get_today_orders()

        # NEW: Data validation
        validation = self._validate_data(
            now, component_timestamps, missing_components, warnings,
            market, portfolio, positions
        )

        # NEW: P2 features - Signpost alerts, news urgency, conviction decay, portfolio history
        signpost_alerts = await self._check_signpost_alerts(theses)
        news_urgency_alerts = await self._check_news_urgency(positions, theses)
        conviction_decay = await self._compute_conviction_decay(theses)
        portfolio_history = await self._compute_portfolio_history(portfolio)

        # NEW: Alternative signals from disconnected data sources (Added 2026-01-19)
        alternative_signals = await self._get_alternative_signals()

        # NEW: Thesis-matched news events for Claude session consumption
        news_events = self._get_thesis_matched_news(limit=20)

        # Build state
        state = UnifiedState(
            timestamp=now,
            market_open=market_open,
            last_updated_by="daemon",
            market=market,
            sentiment=sentiment,
            portfolio=portfolio,
            positions=positions,
            risk=risk,
            watchlist_signals={s: sig.to_dict() for s, sig in signals.items()},
            theses=theses,
            pending_decisions=pending,
            recent_learnings=learnings,
            alerts=alerts,
            upcoming_events=events,
            research=research,
            # NEW: Pre-computed data (P0/P1)
            thesis_performance=thesis_performance,
            concentration=concentration,
            period_performance=period_performance,
            sold_tracking=sold_tracking,
            profit_tiers=profit_tiers,
            today_orders=today_orders,
            validation=validation,
            # NEW: P2 features
            signpost_alerts=signpost_alerts,
            news_urgency_alerts=news_urgency_alerts,
            conviction_decay=conviction_decay,
            portfolio_history=portfolio_history,
            # NEW: Alternative signals (Added 2026-01-19)
            alternative_signals=alternative_signals,
            # NEW: Thesis-matched news events
            news_events=news_events,
        )

        # Generate summaries
        state.summary = state.get_summary()
        state.summary_text = self._generate_summary_text(state)

        # Write to file
        state.to_file(self.output_path)
        logger.info(f"State updated at {now.isoformat()}")

        return state

    def _is_market_open(self, now: datetime) -> bool:
        """Check if US market is currently open."""
        # Simple check - doesn't account for holidays
        weekday = now.weekday()
        if weekday >= 5:  # Saturday/Sunday
            return False

        # Market hours: 9:30 AM - 4:00 PM ET
        hour = now.hour
        minute = now.minute
        time_minutes = hour * 60 + minute

        market_open = 9 * 60 + 30  # 9:30 AM
        market_close = 16 * 60  # 4:00 PM

        return market_open <= time_minutes <= market_close

    async def _get_market_snapshot(self) -> MarketSnapshot:
        """Get market context from market_breadth.py."""
        now = datetime.now()

        try:
            from src.data.pipeline.market_breadth import MarketBreadthAnalyzer

            analyzer = MarketBreadthAnalyzer()
            breadth = analyzer.get_breadth()

            if breadth:
                # Extract VIX from nested vix_analysis object
                vix_val = breadth.vix_analysis.vix if breadth.vix_analysis else 0.0
                vix_change = breadth.vix_analysis.vix_change_pct if breadth.vix_analysis else 0.0

                # Calculate regime confidence from strength attribute
                strength_map = {"strong": 0.9, "moderate": 0.6, "weak": 0.3}
                regime_conf = strength_map.get(breadth.strength, 0.5)

                return MarketSnapshot(
                    timestamp=now,
                    spy_price=breadth.spy_price,
                    spy_change_pct=breadth.spy_change_pct,
                    qqq_price=breadth.qqq_price,
                    qqq_change_pct=breadth.qqq_change_pct,
                    vix=vix_val,
                    vix_change_pct=vix_change,
                    advance_decline_ratio=breadth.advance_decline_ratio,
                    new_highs=0,  # Not available in MarketBreadth
                    new_lows=0,   # Not available in MarketBreadth
                    leading_sectors=breadth.leading_sectors[:3],
                    lagging_sectors=breadth.lagging_sectors[:3],
                    rotation_theme=breadth.rotation_theme,
                    regime=breadth.regime,
                    regime_confidence=regime_conf,
                )
        except Exception as e:
            logger.warning(f"Market breadth unavailable: {e}")

        # Return placeholder if unavailable
        return MarketSnapshot(
            timestamp=now,
            spy_price=0.0,
            spy_change_pct=0.0,
            qqq_price=0.0,
            qqq_change_pct=0.0,
            vix=0.0,
            vix_change_pct=0.0,
            advance_decline_ratio=1.0,
            new_highs=0,
            new_lows=0,
            leading_sectors=[],
            lagging_sectors=[],
            rotation_theme="unknown",
            regime="unknown",
            regime_confidence=0.0,
        )

    async def _get_sentiment_snapshot(self) -> SentimentSnapshot:
        """Get sentiment from sentiment.py."""
        now = datetime.now()

        try:
            from src.data.pipeline.sentiment import SentimentAnalyzer

            analyzer = SentimentAnalyzer()
            indicators = analyzer.get_sentiment()

            if indicators:
                # Map composite_sentiment (-1 to 1) to overall label
                comp = indicators.composite_sentiment
                if comp > 0.3:
                    overall = "bullish"
                elif comp < -0.3:
                    overall = "bearish"
                else:
                    overall = "neutral"

                # Map contrarian_signal
                contrarian = indicators.contrarian_signal if indicators.contrarian_signal != "none" else None

                return SentimentSnapshot(
                    timestamp=now,
                    fear_greed_value=indicators.fear_greed.value if indicators.fear_greed else 50.0,
                    fear_greed_label=indicators.fear_greed.label if indicators.fear_greed else "neutral",
                    put_call_ratio=indicators.put_call.total_pc_ratio if indicators.put_call else 1.0,
                    put_call_signal=indicators.put_call.signal if indicators.put_call else "neutral",
                    vix_term_structure=indicators.vix_structure.structure if indicators.vix_structure else "unknown",
                    overall_sentiment=overall,
                    contrarian_signal=contrarian,
                )
        except Exception as e:
            logger.warning(f"Sentiment unavailable: {e}")

        return SentimentSnapshot(
            timestamp=now,
            fear_greed_value=50.0,
            fear_greed_label="neutral",
            put_call_ratio=1.0,
            put_call_signal="neutral",
            vix_term_structure="unknown",
            overall_sentiment="neutral",
            contrarian_signal=None,
        )

    async def _get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Get portfolio state from Alpaca."""
        now = datetime.now()

        try:
            from alpaca.trading.client import TradingClient
            import yaml

            # Load credentials
            creds_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
            with open(creds_path) as f:
                creds = yaml.safe_load(f)

            trading = TradingClient(
                creds['alpaca']['api_key'],
                creds['alpaca']['secret_key'],
                paper=True
            )

            account = trading.get_account()
            if account:
                equity = float(account.equity)
                last_equity = float(account.last_equity)
                day_pl = equity - last_equity

                return PortfolioSnapshot(
                    timestamp=now,
                    equity=equity,
                    cash=float(account.cash),
                    buying_power=float(account.buying_power),
                    day_pnl=day_pl,
                    day_pnl_pct=(day_pl / last_equity) * 100 if last_equity > 0 else 0,
                    total_positions=0,  # Will be set from positions
                    market_exposure_pct=0.0,  # Will be computed
                    day_trades_remaining=3,  # Alpaca doesn't expose this directly
                    pdt_restricted=getattr(account, 'pattern_day_trader', False),
                )
        except Exception as e:
            logger.warning(f"Portfolio unavailable: {e}")

        return PortfolioSnapshot(
            timestamp=now,
            equity=0.0,
            cash=0.0,
            buying_power=0.0,
            day_pnl=0.0,
            day_pnl_pct=0.0,
            total_positions=0,
            market_exposure_pct=0.0,
            day_trades_remaining=3,
            pdt_restricted=False,
        )

    def _lookup_thesis_for_symbol(self, symbol: str) -> str | None:
        """Find the thesis ID for a position symbol. Cached per update cycle."""
        if not hasattr(self, '_thesis_symbol_map'):
            self._thesis_symbol_map = {}
            try:
                from src.knowledge.thesis import ThesisTracker
                tracker = ThesisTracker(paths.theses)
                for thesis in tracker.get_active_theses():
                    for pos_sym in (thesis.positions or []):
                        self._thesis_symbol_map[pos_sym] = thesis.id
            except Exception as e:
                logger.debug(f"Thesis lookup init failed: {e}")
        # Handle options: "SLB 250321C00050000" → "SLB"
        base = symbol.split()[0] if ' ' in symbol else symbol
        return self._thesis_symbol_map.get(base) or self._thesis_symbol_map.get(symbol)

    async def _get_positions(self) -> list[PositionSnapshot]:
        """Get current positions from Alpaca."""
        # Clear thesis cache so it's rebuilt fresh each update cycle
        if hasattr(self, '_thesis_symbol_map'):
            del self._thesis_symbol_map
        positions = []

        try:
            from alpaca.trading.client import TradingClient
            import yaml

            # Load credentials
            creds_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
            with open(creds_path) as f:
                creds = yaml.safe_load(f)

            trading = TradingClient(
                creds['alpaca']['api_key'],
                creds['alpaca']['secret_key'],
                paper=True
            )

            alpaca_positions = trading.get_all_positions()
            for p in alpaca_positions:
                positions.append(PositionSnapshot(
                    symbol=p.symbol,
                    quantity=int(float(p.qty)),
                    avg_cost=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    market_value=float(p.market_value),
                    unrealized_pnl=float(p.unrealized_pl),
                    unrealized_pnl_pct=float(p.unrealized_plpc) * 100,
                    day_pnl=float(p.unrealized_intraday_pl),
                    day_pnl_pct=float(p.unrealized_intraday_plpc) * 100,
                    weight_pct=0.0,  # Compute later
                    sector=self._get_sector(p.symbol),
                    days_held=0,  # Would need trade history
                    thesis_id=self._lookup_thesis_for_symbol(p.symbol),
                    distance_to_stop_pct=None,
                    distance_to_target_pct=None,
                ))
        except Exception as e:
            logger.warning(f"Positions unavailable: {e}")

        return positions

    async def _get_risk_snapshot(self) -> RiskSnapshot:
        """Get risk metrics from position_monitor.py."""
        now = datetime.now()

        try:
            from src.risk.position_monitor import PositionRiskMonitor

            monitor = PositionRiskMonitor()
            risk = monitor.get_portfolio_risk()

            if risk:
                # Map actual PortfolioRisk attributes to RiskSnapshot
                var_1d = risk.portfolio_var_1d_95
                var_pct = (var_1d / risk.total_value) * 100 if risk.total_value > 0 else 0.0
                max_sector = max(risk.sector_concentration.values()) if risk.sector_concentration else 0.0

                # Determine correlation risk level
                if risk.avg_correlation > 0.7:
                    corr_risk = "high"
                elif risk.avg_correlation > 0.4:
                    corr_risk = "medium"
                else:
                    corr_risk = "low"

                return RiskSnapshot(
                    timestamp=now,
                    portfolio_var_1d=var_1d,
                    portfolio_var_pct=var_pct,
                    max_position_weight=risk.largest_position_pct,
                    max_sector_weight=max_sector,
                    correlation_risk=corr_risk,
                    concentration_warning=risk.warnings[0] if risk.warnings else None,
                    limit_breaches=risk.violations,
                )
        except Exception as e:
            logger.warning(f"Risk metrics unavailable: {e}")

        return RiskSnapshot(
            timestamp=now,
            portfolio_var_1d=0.0,
            portfolio_var_pct=0.0,
            max_position_weight=0.0,
            max_sector_weight=0.0,
            correlation_risk="unknown",
            concentration_warning=None,
            limit_breaches=[],
        )

    def _get_signals(self) -> dict[str, AggregatedSignal]:
        """Get aggregated signals for watchlist."""
        try:
            return self.signal_aggregator.aggregate(self.watchlist)
        except ImportError as e:
            logger.warning(f"Signal aggregator module not available: {e}")
            return {}
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Signal computation error: {e}")
            return {}
        except Exception as e:
            # Catch-all for external API failures (yfinance, etc.)
            logger.warning(f"Signal aggregation failed (external): {e}")
            return {}

    async def _get_theses(self) -> list[ThesisSummary]:
        """Get active theses from thesis tracker."""
        theses = []

        try:
            from src.knowledge.thesis import ThesisTracker

            tracker = ThesisTracker(paths.theses)
            active = tracker.get_active_theses()

            for t in active:
                theses.append(ThesisSummary(
                    id=t.id,
                    name=t.name,
                    status=t.status,
                    conviction=t.conviction,
                    positions=t.positions,
                    next_signpost=t.signposts[0].description if t.signposts else None,
                    days_active=(datetime.now() - t.created).days,
                ))
        except ImportError as e:
            logger.debug(f"Thesis tracker module not available: {e}")
        except (FileNotFoundError, json.JSONDecodeError, KeyError, AttributeError) as e:
            logger.warning(f"Failed to load theses: {e}")

        return theses

    async def _get_pending_decisions(self) -> list[PendingDecision]:
        """Get decisions awaiting outcomes."""
        pending = []

        try:
            from src.decision.decision_logger import DecisionLogger, DecisionStatus

            logger_instance = DecisionLogger()

            # Get recent decisions that are executed but not closed
            for i in range(7):  # Look back 7 days
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                filepath = paths.decisions / f"decisions_{date}.json"

                if filepath.exists():
                    with open(filepath, "r") as f:
                        data = json.load(f)

                    for d in data.get("decisions", []):
                        status = d.get("status", "pending")
                        if status in ["executed", "filled"]:
                            pending.append(PendingDecision(
                                id=d["id"],
                                symbol=d["symbol"],
                                action=d["action"],
                                timestamp=d["timestamp"],
                                confidence=d["confidence"],
                                entry_price=d.get("execution_price"),
                                current_price=0.0,  # Would need to fetch
                                unrealized_pnl_pct=0.0,
                                thesis_id=d.get("thesis_id"),
                                days_held=i,
                            ))
        except Exception as e:
            logger.debug(f"Decision logger not available: {e}")

        return pending

    async def _get_recent_learnings(self) -> list[LearningSummary]:
        """Get recent learnings from learning log."""
        learnings = []

        try:
            from src.knowledge.learnings import LearningLog

            log = LearningLog(paths.learnings)
            recent = log.get_recent(days=30)

            for l in recent[:10]:  # Top 10
                learnings.append(LearningSummary(
                    id=l.id,
                    date=l.created.strftime("%Y-%m-%d"),
                    symbol=l.symbol,
                    outcome=l.outcome,
                    pnl_pct=l.pnl_pct,
                    key_learning=l.what_i_learned[:100],  # Truncate
                    tags=l.tags,
                ))
        except Exception as e:
            logger.debug(f"Learning log not available: {e}")

        return learnings

    async def _get_alerts(self) -> list[AlertSnapshot]:
        """Get active alerts from alert manager."""
        alerts = []

        try:
            from src.alerts.alert_manager import AlertManager

            manager = AlertManager()
            active = manager.get_active_alerts()

            for a in active:
                alerts.append(AlertSnapshot(
                    id=a.id,
                    alert_type=a.alert_type.value,
                    symbol=a.symbol,
                    message=a.message,
                    priority=a.priority.value,
                    triggered_at=a.triggered_at.isoformat() if a.triggered_at else "",
                    acknowledged=a.acknowledged,
                ))
        except Exception as e:
            logger.debug(f"Alert manager not available: {e}")

        return alerts

    async def _get_calendar_events(self) -> list[CalendarEvent]:
        """Get upcoming calendar events."""
        events = []

        try:
            from src.data.calendars.calendar_manager import CalendarManager

            manager = CalendarManager()
            upcoming = manager.get_upcoming_events(days=7)

            for e in upcoming[:10]:  # Top 10
                events.append(CalendarEvent(
                    date=e.date.strftime("%Y-%m-%d"),
                    time=e.time,
                    event_type=e.event_type,
                    symbol=e.symbol,
                    description=e.description,
                    importance=e.importance,
                    expected_impact=e.expected_impact,
                ))
        except Exception as e:
            logger.debug(f"Calendar manager not available: {e}")

        return events

    def _get_research_index(self) -> ResearchIndex:
        """Get index of available pre-computed research files."""
        research_dir = paths.live_research
        now = datetime.now()

        features_file = research_dir / "features.json"
        signals_file = research_dir / "signals.json"
        alt_data_file = research_dir / "alt_data.json"
        screens_file = research_dir / "screens.json"

        # Check if files exist and are fresh (within 24h)
        available = all([
            features_file.exists(),
            signals_file.exists(),
            alt_data_file.exists(),
            screens_file.exists(),
        ])

        if available:
            # Check freshness
            oldest = min(
                features_file.stat().st_mtime,
                signals_file.stat().st_mtime,
                alt_data_file.stat().st_mtime,
                screens_file.stat().st_mtime,
            )
            age_hours = (now.timestamp() - oldest) / 3600
            if age_hours > 24:
                available = False

        return ResearchIndex(
            last_updated=now,
            features_file=str(features_file),
            signals_file=str(signals_file),
            alt_data_file=str(alt_data_file),
            screens_file=str(screens_file),
            available=available,
        )

    # Static sector mapping for common symbols
    SECTOR_MAP = {
        # Energy
        "SLB": "Energy", "HAL": "Energy", "OXY": "Energy", "XOM": "Energy", "CVX": "Energy",
        "XLE": "Energy", "VLO": "Energy", "MPC": "Energy", "PSX": "Energy", "OIH": "Energy",
        "FRO": "Energy", "STNG": "Energy", "DHT": "Energy", "INSW": "Energy", "COP": "Energy",
        "EOG": "Energy", "PXD": "Energy", "DVN": "Energy", "HES": "Energy",
        # Technology
        "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology", "GOOG": "Technology",
        "META": "Technology", "NVDA": "Technology", "AMD": "Technology", "XLK": "Technology",
        "INTC": "Technology", "AVGO": "Technology", "QCOM": "Technology", "MU": "Technology",
        "MRVL": "Technology", "TSM": "Technology", "ASML": "Technology", "AMAT": "Technology",
        # Financials
        "JPM": "Financials", "BAC": "Financials", "GS": "Financials", "XLF": "Financials",
        "WFC": "Financials", "C": "Financials", "MS": "Financials", "BLK": "Financials",
        # Utilities / Power
        "CEG": "Utilities", "NEE": "Utilities", "VST": "Utilities", "ETR": "Utilities",
        "CCJ": "Utilities", "OKLO": "Utilities", "XLU": "Utilities", "SO": "Utilities",
        "DUK": "Utilities", "AEP": "Utilities",
        # Industrials / Defense
        "GD": "Industrials", "NOC": "Industrials", "LMT": "Industrials", "LHX": "Industrials",
        "RTX": "Industrials", "BA": "Industrials", "CAT": "Industrials", "HON": "Industrials",
        "UPS": "Industrials", "XLI": "Industrials",
        # Consumer Discretionary
        "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary", "HD": "Consumer Discretionary",
        "NKE": "Consumer Discretionary", "SBUX": "Consumer Discretionary", "XLY": "Consumer Discretionary",
        # Consumer Staples
        "WMT": "Consumer Staples", "PG": "Consumer Staples", "KO": "Consumer Staples",
        "PEP": "Consumer Staples", "COST": "Consumer Staples", "XLP": "Consumer Staples",
        # Healthcare
        "JNJ": "Healthcare", "UNH": "Healthcare", "PFE": "Healthcare", "ABBV": "Healthcare",
        "MRK": "Healthcare", "LLY": "Healthcare", "XLV": "Healthcare",
        # Communication Services
        "NFLX": "Communication Services", "DIS": "Communication Services", "VZ": "Communication Services",
        "T": "Communication Services", "CMCSA": "Communication Services", "XLC": "Communication Services",
        # Materials
        "LIN": "Materials", "APD": "Materials", "SHW": "Materials", "FCX": "Materials",
        "NEM": "Materials", "XLB": "Materials",
        # Real Estate
        "AMT": "Real Estate", "PLD": "Real Estate", "CCI": "Real Estate", "XLRE": "Real Estate",
        # Broad Market ETFs
        "SPY": "Broad Market", "QQQ": "Broad Market", "IWM": "Broad Market", "DIA": "Broad Market",
        "VTI": "Broad Market", "VOO": "Broad Market",
        # Commodities
        "GLD": "Commodities", "SLV": "Commodities", "USO": "Commodities", "UNG": "Commodities",
        # Fixed Income
        "TLT": "Fixed Income", "IEF": "Fixed Income", "BND": "Fixed Income",
        # Volatility
        "VXX": "Volatility", "UVXY": "Volatility", "SVXY": "Volatility",
    }

    def _get_sector(self, symbol: str) -> str:
        """Get sector for a symbol with yfinance fallback.

        First checks static mapping, then cache, then fetches from yfinance.
        """
        # Check static mapping first
        if symbol in self.SECTOR_MAP:
            return self.SECTOR_MAP[symbol]

        # Check cache
        if symbol in self._sector_cache:
            return self._sector_cache[symbol]

        # Fetch from yfinance and cache
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info
            sector = info.get("sector", "Unknown")
            if sector and sector != "Unknown":
                self._sector_cache[symbol] = sector
                return sector
        except Exception as e:
            logger.debug(f"Could not fetch sector for {symbol}: {e}")

        return "Unknown"

    # =========================================================================
    # NEW: Pre-computed data computation methods
    # =========================================================================

    def _get_default_market_snapshot(self) -> MarketSnapshot:
        """Return default market snapshot when API fails."""
        return MarketSnapshot(
            timestamp=datetime.now(),
            spy_price=0.0,
            spy_change_pct=0.0,
            qqq_price=0.0,
            qqq_change_pct=0.0,
            vix=0.0,
            vix_change_pct=0.0,
            advance_decline_ratio=1.0,
            new_highs=0,
            new_lows=0,
            leading_sectors=[],
            lagging_sectors=[],
            rotation_theme="unknown",
            regime="unknown",
            regime_confidence=0.0,
        )

    def _get_default_sentiment_snapshot(self) -> SentimentSnapshot:
        """Return default sentiment snapshot when API fails."""
        return SentimentSnapshot(
            timestamp=datetime.now(),
            fear_greed_value=50.0,
            fear_greed_label="neutral",
            put_call_ratio=1.0,
            put_call_signal="neutral",
            vix_term_structure="unknown",
            overall_sentiment="neutral",
            contrarian_signal=None,
        )

    def _get_default_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Return default portfolio snapshot when API fails."""
        return PortfolioSnapshot(
            timestamp=datetime.now(),
            equity=0.0,
            cash=0.0,
            buying_power=0.0,
            day_pnl=0.0,
            day_pnl_pct=0.0,
            total_positions=0,
            market_exposure_pct=0.0,
            day_trades_remaining=3,
            pdt_restricted=False,
        )

    def _get_default_risk_snapshot(self) -> RiskSnapshot:
        """Return default risk snapshot when API fails."""
        return RiskSnapshot(
            timestamp=datetime.now(),
            portfolio_var_1d=0.0,
            portfolio_var_pct=0.0,
            max_position_weight=0.0,
            max_sector_weight=0.0,
            correlation_risk="unknown",
            concentration_warning=None,
            limit_breaches=[],
        )

    async def _compute_thesis_performance(
        self,
        positions: list[PositionSnapshot],
        theses: list[ThesisSummary],
        portfolio_equity: float,
    ) -> dict[str, ThesisPerformance]:
        """Compute performance for each thesis by aggregating positions."""
        result = {}

        if not portfolio_equity or portfolio_equity <= 0:
            return result

        # Load full thesis data to get position lists
        try:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)
        except Exception as e:
            logger.warning(f"Could not load thesis tracker: {e}")
            return result

        for thesis_summary in theses:
            try:
                thesis = tracker.get_thesis(thesis_summary.id)
                if not thesis:
                    continue

                # Find positions that belong to this thesis
                thesis_positions = []
                total_value = 0.0
                total_cost = 0.0
                total_day_pnl = 0.0

                for pos in positions:
                    # Check if position symbol matches thesis positions (handle options)
                    base_symbol = pos.symbol.split()[0] if ' ' in pos.symbol else pos.symbol
                    if base_symbol in thesis.positions or pos.symbol in thesis.positions:
                        cost_basis = pos.avg_cost * pos.quantity
                        thesis_positions.append(ThesisPositionDetail(
                            symbol=pos.symbol,
                            quantity=pos.quantity,
                            market_value=pos.market_value,
                            cost_basis=cost_basis,
                            unrealized_pnl=pos.unrealized_pnl,
                            unrealized_pnl_pct=pos.unrealized_pnl_pct,
                            day_pnl=pos.day_pnl,
                            weight_in_thesis_pct=0.0,  # Computed below
                            weight_in_portfolio_pct=(pos.market_value / portfolio_equity * 100) if portfolio_equity > 0 else 0.0,
                        ))
                        total_value += pos.market_value
                        total_cost += cost_basis
                        total_day_pnl += pos.day_pnl

                # Update weight_in_thesis_pct
                if total_value > 0:
                    for tp in thesis_positions:
                        tp.weight_in_thesis_pct = (tp.market_value / total_value) * 100

                # Find best/worst performers
                best_performer = None
                best_pnl_pct = float('-inf')
                worst_performer = None
                worst_pnl_pct = float('inf')

                for tp in thesis_positions:
                    if tp.unrealized_pnl_pct > best_pnl_pct:
                        best_pnl_pct = tp.unrealized_pnl_pct
                        best_performer = tp.symbol
                    if tp.unrealized_pnl_pct < worst_pnl_pct:
                        worst_pnl_pct = tp.unrealized_pnl_pct
                        worst_performer = tp.symbol

                total_pnl = total_value - total_cost
                total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0
                day_pnl_pct = (total_day_pnl / (total_value - total_day_pnl) * 100) if (total_value - total_day_pnl) > 0 else 0.0

                result[thesis_summary.id] = ThesisPerformance(
                    thesis_id=thesis_summary.id,
                    thesis_name=thesis_summary.name,
                    conviction=thesis_summary.conviction,
                    status=thesis_summary.status,
                    total_value=total_value,
                    total_cost=total_cost,
                    total_pnl=total_pnl,
                    total_pnl_pct=total_pnl_pct,
                    day_pnl=total_day_pnl,
                    day_pnl_pct=day_pnl_pct,
                    weight_in_portfolio_pct=(total_value / portfolio_equity * 100) if portfolio_equity > 0 else 0.0,
                    position_count=len(thesis_positions),
                    positions=thesis_positions,
                    best_performer=best_performer,
                    best_performer_pnl_pct=best_pnl_pct if best_pnl_pct != float('-inf') else 0.0,
                    worst_performer=worst_performer,
                    worst_performer_pnl_pct=worst_pnl_pct if worst_pnl_pct != float('inf') else 0.0,
                    divergence_pct=(best_pnl_pct - worst_pnl_pct) if (best_pnl_pct != float('-inf') and worst_pnl_pct != float('inf')) else 0.0,
                )
            except Exception as e:
                logger.warning(f"Error computing thesis performance for {thesis_summary.id}: {e}")

        return result

    def _compute_concentration(
        self,
        positions: list[PositionSnapshot],
        theses: list[ThesisSummary],
        portfolio_equity: float,
    ) -> Optional[ConcentrationAnalysis]:
        """Compute concentration risk analysis."""
        if not positions or not portfolio_equity or portfolio_equity <= 0:
            return None

        # Compute by sector
        by_sector: dict[str, float] = {}
        for pos in positions:
            sector = pos.sector or self._get_sector(pos.symbol)
            weight = (pos.market_value / portfolio_equity) * 100
            by_sector[sector] = by_sector.get(sector, 0.0) + weight

        # Compute by thesis
        by_thesis: dict[str, float] = {}
        for thesis in theses:
            total_weight = 0.0
            for pos in positions:
                base_symbol = pos.symbol.split()[0] if ' ' in pos.symbol else pos.symbol
                if base_symbol in thesis.positions or pos.symbol in thesis.positions:
                    total_weight += (pos.market_value / portfolio_equity) * 100
            if total_weight > 0:
                by_thesis[thesis.name] = total_weight

        # Find largest position
        largest_pos = ""
        largest_pct = 0.0
        for pos in positions:
            weight = (pos.market_value / portfolio_equity) * 100
            if weight > largest_pct:
                largest_pct = weight
                largest_pos = pos.symbol

        # Check limits and generate warnings
        warnings = []
        limit_breaches = []

        # Position limit: 15%
        if largest_pct > 15.0:
            limit_breaches.append(f"Position {largest_pos} at {largest_pct:.1f}% exceeds 15% limit")
        elif largest_pct > 12.0:
            warnings.append(f"Position {largest_pos} at {largest_pct:.1f}% approaching 15% limit")

        # Thesis limit: 35%
        for thesis_name, weight in by_thesis.items():
            if weight > 35.0:
                limit_breaches.append(f"Thesis '{thesis_name}' at {weight:.1f}% exceeds 35% limit")
            elif weight > 30.0:
                warnings.append(f"Thesis '{thesis_name}' at {weight:.1f}% approaching 35% limit")

        # Sector limit: 40%
        for sector, weight in by_sector.items():
            if weight > 40.0:
                limit_breaches.append(f"Sector {sector} at {weight:.1f}% exceeds 40% limit")
            elif weight > 35.0:
                warnings.append(f"Sector {sector} at {weight:.1f}% approaching 40% limit")

        return ConcentrationAnalysis(
            by_thesis=by_thesis,
            by_sector=by_sector,
            largest_position=largest_pos,
            largest_position_pct=largest_pct,
            warnings=warnings,
            limit_breaches=limit_breaches,
        )

    async def _compute_period_performance(
        self,
        portfolio: PortfolioSnapshot,
        market: MarketSnapshot,
    ) -> Optional[PeriodPerformance]:
        """Compute period performance vs benchmarks using actual portfolio history."""
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            import yaml

            creds_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
            with open(creds_path) as f:
                creds = yaml.safe_load(f)

            data_client = StockHistoricalDataClient(
                creds['alpaca']['api_key'],
                creds['alpaca']['secret_key'],
            )

            # Get SPY data for comparison
            end = datetime.now()
            month_ago = end - timedelta(days=30)

            request = StockBarsRequest(
                symbol_or_symbols="SPY",
                timeframe=TimeFrame.Day,
                start=month_ago,
                end=end,
            )

            bars = data_client.get_stock_bars(request)
            spy_bars = bars["SPY"]

            if len(spy_bars) < 2:
                return None

            # Calculate SPY returns
            spy_today = spy_bars[-1].close
            spy_yesterday = spy_bars[-2].close if len(spy_bars) >= 2 else spy_bars[-1].open
            spy_week_start = spy_bars[-5].close if len(spy_bars) >= 5 else spy_bars[0].close
            spy_month_start = spy_bars[0].close

            spy_today_pct = ((spy_today - spy_yesterday) / spy_yesterday) * 100
            spy_week_pct = ((spy_today - spy_week_start) / spy_week_start) * 100
            spy_month_pct = ((spy_today - spy_month_start) / spy_month_start) * 100

            # Get actual portfolio P&L from portfolio history
            today_pnl = portfolio.day_pnl
            today_pnl_pct = portfolio.day_pnl_pct

            # Load portfolio history for accurate week/month returns
            week_pnl, week_pnl_pct = self._calculate_period_pnl_from_history(5, portfolio.equity)
            month_pnl, month_pnl_pct = self._calculate_period_pnl_from_history(20, portfolio.equity)

            return PeriodPerformance(
                today_pnl=today_pnl,
                today_pnl_pct=today_pnl_pct,
                week_pnl=week_pnl,
                week_pnl_pct=week_pnl_pct,
                month_pnl=month_pnl,
                month_pnl_pct=month_pnl_pct,
                spy_today_pct=spy_today_pct,
                spy_week_pct=spy_week_pct,
                spy_month_pct=spy_month_pct,
                vs_spy_today=today_pnl_pct - spy_today_pct,
                vs_spy_week=week_pnl_pct - spy_week_pct,
                vs_spy_month=month_pnl_pct - spy_month_pct,
            )
        except Exception as e:
            logger.warning(f"Could not compute period performance: {e}")
            return None

    def _calculate_period_pnl_from_history(
        self, trading_days: int, current_equity: float
    ) -> tuple[float, float]:
        """Calculate actual P&L from portfolio history.

        Args:
            trading_days: Number of trading days to look back (5 for week, 20 for month)
            current_equity: Current portfolio equity

        Returns:
            Tuple of (pnl_dollars, pnl_percent)
        """
        try:
            history_path = paths.live / "portfolio_history.json"
            if not history_path.exists():
                logger.debug("Portfolio history not found, using zero for period P&L")
                return 0.0, 0.0

            with open(history_path) as f:
                history_data = json.load(f)

            snapshots = history_data.get("snapshots", [])
            if len(snapshots) < trading_days:
                # Not enough history, compute from available data
                if len(snapshots) < 2:
                    return 0.0, 0.0
                start_equity = snapshots[0].get("equity", current_equity)
            else:
                # Use data from trading_days ago
                idx = len(snapshots) - trading_days
                start_equity = snapshots[idx].get("equity", current_equity)

            if start_equity <= 0:
                return 0.0, 0.0

            pnl = current_equity - start_equity
            pnl_pct = (pnl / start_equity) * 100

            return pnl, pnl_pct

        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Could not load portfolio history: {e}")
            return 0.0, 0.0

    async def _compute_sold_tracking(self) -> Optional[SoldTracking]:
        """Track opportunity cost of sold positions."""
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestQuoteRequest
            import yaml

            creds_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
            with open(creds_path) as f:
                creds = yaml.safe_load(f)

            trading = TradingClient(
                creds['alpaca']['api_key'],
                creds['alpaca']['secret_key'],
                paper=True
            )

            data_client = StockHistoricalDataClient(
                creds['alpaca']['api_key'],
                creds['alpaca']['secret_key'],
            )

            # Get filled sell orders from past 30 days
            since = datetime.now(timezone.utc) - timedelta(days=30)
            request = GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                after=since,
            )

            orders = trading.get_orders(filter=request)
            sell_orders = [o for o in orders if o.side.value == 'sell' and o.filled_qty and float(o.filled_qty) > 0]

            sold_positions = []
            total_opportunity_cost = 0.0
            biggest_miss = None
            biggest_miss_amount = 0.0
            biggest_avoided = None
            biggest_avoided_amount = 0.0

            # Group by symbol
            symbol_sells: dict[str, list] = {}
            for order in sell_orders:
                symbol = order.symbol
                if symbol not in symbol_sells:
                    symbol_sells[symbol] = []
                symbol_sells[symbol].append(order)

            # Get current prices for sold symbols
            if symbol_sells:
                try:
                    quote_request = StockLatestQuoteRequest(symbol_or_symbols=list(symbol_sells.keys()))
                    quotes = data_client.get_stock_latest_quote(quote_request)
                except Exception as e:
                    logger.warning(f"Could not get quotes for sold symbols: {e}")
                    quotes = {}

                for symbol, orders_list in symbol_sells.items():
                    current_price = quotes.get(symbol)
                    if not current_price:
                        continue

                    current_price_val = (current_price.ask_price + current_price.bid_price) / 2

                    for order in orders_list:
                        sell_price = float(order.filled_avg_price) if order.filled_avg_price else 0.0
                        sell_qty = int(float(order.filled_qty))
                        sell_total = sell_price * sell_qty
                        current_value = current_price_val * sell_qty
                        opp_cost = current_value - sell_total
                        opp_cost_pct = (opp_cost / sell_total) * 100 if sell_total > 0 else 0.0

                        sell_date = order.filled_at.strftime("%Y-%m-%d") if order.filled_at else ""
                        days_since = (datetime.now(timezone.utc) - order.filled_at).days if order.filled_at else 0

                        sold_positions.append(SoldPositionTrack(
                            symbol=symbol,
                            sell_date=sell_date,
                            sell_price=sell_price,
                            sell_quantity=sell_qty,
                            sell_total=sell_total,
                            current_price=current_price_val,
                            current_value_if_held=current_value,
                            opportunity_cost=opp_cost,
                            opportunity_cost_pct=opp_cost_pct,
                            days_since_sale=days_since,
                        ))

                        total_opportunity_cost += opp_cost

                        if opp_cost > biggest_miss_amount:
                            biggest_miss_amount = opp_cost
                            biggest_miss = symbol
                        if opp_cost < biggest_avoided_amount:
                            biggest_avoided_amount = opp_cost
                            biggest_avoided = symbol

            return SoldTracking(
                sold_positions=sold_positions,
                total_opportunity_cost=total_opportunity_cost,
                biggest_miss=biggest_miss,
                biggest_miss_amount=biggest_miss_amount,
                biggest_avoided=biggest_avoided,
                biggest_avoided_amount=abs(biggest_avoided_amount) if biggest_avoided_amount < 0 else 0.0,
            )
        except Exception as e:
            logger.warning(f"Could not compute sold tracking: {e}")
            return None

    def _compute_profit_tiers(self, positions: list[PositionSnapshot]) -> dict[str, ProfitTierStatus]:
        """Compute profit tier status for each position."""
        result = {}

        for pos in positions:
            gain_pct = pos.unrealized_pnl_pct

            tier_10 = gain_pct >= 10.0
            tier_15 = gain_pct >= 15.0
            tier_20 = gain_pct >= 20.0

            # Determine recommended action
            recommended = None
            next_tier = None

            if gain_pct >= 20.0:
                recommended = "Consider taking additional 25% profit (Tier 3)"
                next_tier = 25.0
            elif gain_pct >= 15.0:
                recommended = "Consider taking 25% profit (Tier 2)"
                next_tier = 20.0
            elif gain_pct >= 10.0:
                recommended = "Consider taking 25% profit (Tier 1)"
                next_tier = 15.0
            elif gain_pct >= 7.0:
                next_tier = 10.0
            elif gain_pct >= 0:
                next_tier = 10.0

            result[pos.symbol] = ProfitTierStatus(
                symbol=pos.symbol,
                current_gain_pct=gain_pct,
                tier_10_triggered=tier_10,
                tier_15_triggered=tier_15,
                tier_20_triggered=tier_20,
                shares_remaining_pct=100.0,  # Would need to track original position
                recommended_action=recommended,
                next_tier_pct=next_tier,
            )

        return result

    async def _get_today_orders(self) -> Optional[TodayOrders]:
        """Get today's orders from Alpaca."""
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            import yaml

            creds_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
            with open(creds_path) as f:
                creds = yaml.safe_load(f)

            trading = TradingClient(
                creds['alpaca']['api_key'],
                creds['alpaca']['secret_key'],
                paper=True
            )

            # Get orders from today
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

            request = GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                after=today_start,
            )

            alpaca_orders = trading.get_orders(filter=request)

            orders = []
            total_buys = 0.0
            total_sells = 0.0

            for order in alpaca_orders:
                if not order.filled_qty or float(order.filled_qty) == 0:
                    continue

                qty = int(float(order.filled_qty))
                price = float(order.filled_avg_price) if order.filled_avg_price else 0.0
                total = qty * price
                action = order.side.value.upper()

                if action == "BUY":
                    total_buys += total
                else:
                    total_sells += total

                orders.append(TodayOrder(
                    time=order.filled_at.strftime("%H:%M") if order.filled_at else "",
                    action=action,
                    symbol=order.symbol,
                    quantity=qty,
                    price=price,
                    total=total,
                    order_id=str(order.id),
                ))

            return TodayOrders(
                orders=orders,
                total_buys=total_buys,
                total_sells=total_sells,
                net_flow=total_buys - total_sells,
                order_count=len(orders),
            )
        except Exception as e:
            logger.warning(f"Could not get today's orders: {e}")
            return None

    def _validate_data(
        self,
        now: datetime,
        component_timestamps: dict[str, datetime],
        missing_components: list[str],
        warnings: list[str],
        market: MarketSnapshot,
        portfolio: PortfolioSnapshot,
        positions: list[PositionSnapshot],
    ) -> DataValidation:
        """Validate data freshness and completeness."""
        stale_components = []
        stale_threshold_minutes = 15.0

        # Check component freshness
        market_age = (now - component_timestamps.get('market', now)).total_seconds() / 60
        portfolio_age = (now - component_timestamps.get('portfolio', now)).total_seconds() / 60
        positions_age = (now - component_timestamps.get('positions', now)).total_seconds() / 60

        if market_age > stale_threshold_minutes:
            stale_components.append('market')
        if portfolio_age > stale_threshold_minutes:
            stale_components.append('portfolio')
        if positions_age > stale_threshold_minutes:
            stale_components.append('positions')

        # Validate data quality
        if market.spy_price == 0.0 and 'market' not in missing_components:
            warnings.append("Market data returned zero SPY price")
            missing_components.append('market')

        if portfolio.equity == 0.0 and 'portfolio' not in missing_components:
            warnings.append("Portfolio returned zero equity")
            missing_components.append('portfolio')

        # Overall validity
        is_valid = len(missing_components) == 0 and len(stale_components) == 0

        return DataValidation(
            is_valid=is_valid,
            last_successful_update=now.isoformat(),
            stale_components=stale_components,
            missing_components=missing_components,
            warnings=warnings,
            market_age_minutes=market_age,
            portfolio_age_minutes=portfolio_age,
            positions_age_minutes=positions_age,
        )

    def _generate_summary_text(self, state: UnifiedState) -> str:
        """Generate human-readable summary text for efficient Claude consumption."""
        lines = []

        # Header
        lines.append(f"=== PORTFOLIO STATUS @ {state.timestamp.strftime('%H:%M ET')} ===")
        lines.append("")

        # Quick stats
        lines.append(f"Account: ${state.portfolio.equity:,.0f} | Day P&L: ${state.portfolio.day_pnl:+,.0f} ({state.portfolio.day_pnl_pct:+.2f}%)")
        lines.append(f"Market: {state.market.regime} | VIX: {state.market.vix:.1f} | Sentiment: {state.sentiment.overall_sentiment}")
        lines.append("")

        # Validation warnings
        if state.validation and not state.validation.is_valid:
            lines.append("⚠️ DATA WARNINGS:")
            for w in state.validation.warnings:
                lines.append(f"  - {w}")
            for m in state.validation.missing_components:
                lines.append(f"  - Missing: {m}")
            lines.append("")

        # Concentration warnings
        if state.concentration:
            if state.concentration.limit_breaches:
                lines.append("🚨 LIMIT BREACHES:")
                for breach in state.concentration.limit_breaches:
                    lines.append(f"  - {breach}")
                lines.append("")
            if state.concentration.warnings:
                lines.append("⚠️ CONCENTRATION WARNINGS:")
                for w in state.concentration.warnings:
                    lines.append(f"  - {w}")
                lines.append("")

        # Thesis performance
        if state.thesis_performance:
            lines.append("THESIS PERFORMANCE:")
            for thesis_id, perf in state.thesis_performance.items():
                emoji = "📈" if perf.total_pnl > 0 else "📉"
                lines.append(f"  {emoji} {perf.thesis_name}: ${perf.total_value:,.0f} ({perf.weight_in_portfolio_pct:.1f}%)")
                lines.append(f"     P&L: ${perf.total_pnl:+,.0f} ({perf.total_pnl_pct:+.1f}%) | Day: ${perf.day_pnl:+,.0f}")
                if perf.best_performer:
                    lines.append(f"     Best: {perf.best_performer} ({perf.best_performer_pnl_pct:+.1f}%) | Worst: {perf.worst_performer} ({perf.worst_performer_pnl_pct:+.1f}%)")
            lines.append("")

        # Profit tier alerts
        if state.profit_tiers:
            actionable = [(s, p) for s, p in state.profit_tiers.items() if p.recommended_action]
            if actionable:
                lines.append("💰 PROFIT-TAKING OPPORTUNITIES:")
                for symbol, tier in actionable:
                    lines.append(f"  - {symbol}: {tier.current_gain_pct:+.1f}% → {tier.recommended_action}")
                lines.append("")

        # Sold position tracking
        if state.sold_tracking and state.sold_tracking.sold_positions:
            lines.append(f"SOLD POSITION TRACKING (30d): Total Opportunity Cost: ${state.sold_tracking.total_opportunity_cost:+,.0f}")
            if state.sold_tracking.biggest_miss:
                lines.append(f"  Biggest miss: {state.sold_tracking.biggest_miss} (${state.sold_tracking.biggest_miss_amount:+,.0f})")
            if state.sold_tracking.biggest_avoided:
                lines.append(f"  Best avoided: {state.sold_tracking.biggest_avoided} (saved ${state.sold_tracking.biggest_avoided_amount:,.0f})")
            lines.append("")

        # Today's activity
        if state.today_orders and state.today_orders.order_count > 0:
            lines.append(f"TODAY'S ORDERS: {state.today_orders.order_count} orders")
            lines.append(f"  Buys: ${state.today_orders.total_buys:,.0f} | Sells: ${state.today_orders.total_sells:,.0f} | Net: ${state.today_orders.net_flow:+,.0f}")
            lines.append("")

        # Active alerts
        if state.alerts:
            lines.append("ACTIVE ALERTS:")
            for alert in state.alerts[:5]:
                lines.append(f"  [{alert.priority}] {alert.symbol}: {alert.message}")
            lines.append("")

        # Top positions
        if state.positions:
            lines.append(f"TOP POSITIONS ({len(state.positions)} total):")
            sorted_pos = sorted(state.positions, key=lambda x: x.market_value, reverse=True)[:5]
            for pos in sorted_pos:
                emoji = "📈" if pos.unrealized_pnl > 0 else "📉"
                lines.append(f"  {emoji} {pos.symbol}: ${pos.market_value:,.0f} ({pos.weight_pct:.1f}%) | P&L: {pos.unrealized_pnl_pct:+.1f}%")
            lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # NEW: P2 Features (Added 2026-01-10)
    # =========================================================================

    async def _check_signpost_alerts(self, theses: list[ThesisSummary]) -> list[SignpostAlert]:
        """Check for recently triggered signposts."""
        alerts = []
        try:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)

            for thesis_summary in theses:
                thesis = tracker.get_thesis(thesis_summary.id)
                if not thesis:
                    continue

                # Check for signposts triggered in last 24 hours
                for signpost in thesis.signposts:
                    if signpost.status == "triggered" and signpost.triggered_at:
                        triggered_time = signpost.triggered_at
                        if isinstance(triggered_time, str):
                            triggered_time = datetime.fromisoformat(triggered_time)

                        hours_ago = (datetime.now() - triggered_time).total_seconds() / 3600

                        if hours_ago <= 24:
                            # Recent signpost trigger
                            urgency = "high" if hours_ago <= 1 else "medium" if hours_ago <= 4 else "low"
                            outcome = signpost.outcome or "neutral"

                            if outcome == "bullish":
                                action = f"Consider adding to {', '.join(thesis.positions[:3])}"
                            elif outcome == "bearish":
                                action = f"Review exposure to {', '.join(thesis.positions[:3])}"
                            else:
                                action = "Monitor thesis positions"

                            alerts.append(SignpostAlert(
                                thesis_id=thesis.id,
                                thesis_name=thesis.name,
                                signpost_description=signpost.description,
                                triggered_at=triggered_time.isoformat(),
                                outcome=outcome,
                                news_headline="Signpost condition met",
                                news_source="thesis_tracker",
                                recommended_action=action,
                                urgency=urgency,
                            ))
        except Exception as e:
            logger.warning(f"Could not check signpost alerts: {e}")

        return alerts

    async def _check_news_urgency(
        self,
        positions: list[PositionSnapshot],
        theses: list[ThesisSummary],
    ) -> list[NewsUrgencyAlert]:
        """Check for urgent news affecting positions or theses.

        Uses thesis_matches from enriched news items (populated by
        cron_news_collect_fast.py via thesis keyword index) as primary
        matching method, falling back to symbol regex for unmatched items.
        """
        alerts = []

        # Urgent keywords that trigger immediate review
        urgent_keywords = {
            "critical": ["acquisition", "merger", "bankruptcy", "fda approval", "ceo resign"],
            "high": ["earnings", "contract win", "guidance", "downgrade", "upgrade", "lawsuit"],
            "medium": ["partnership", "expansion", "layoffs", "regulation", "investigation"],
        }

        try:
            news_path = paths.live / "news_cache.json"
            if not news_path.exists():
                return alerts

            with open(news_path) as f:
                news_data = json.load(f)

            position_symbols = {p.symbol for p in positions}
            thesis_names_by_id = {t.id: t.name for t in theses}
            thesis_symbols = set()
            thesis_names_by_sym = {}
            for t in theses:
                thesis_symbols.update(t.positions)
                for sym in t.positions:
                    thesis_names_by_sym[sym] = t.name

            cutoff = datetime.now() - timedelta(hours=4)

            for item in news_data.get("items", []):
                item_time = datetime.fromisoformat(item.get("timestamp", "2000-01-01"))
                # Strip timezone info for comparison with naive datetime.now()
                if item_time.tzinfo is not None:
                    item_time = item_time.replace(tzinfo=None)
                if item_time < cutoff:
                    continue

                headline = item.get("headline", "").lower()
                symbols = item.get("symbols", [])
                thesis_matches = item.get("thesis_matches", {})

                # Primary: use thesis_matches from enriched news
                affected_theses_from_matches = []
                if thesis_matches:
                    for tid, match in thesis_matches.items():
                        if match.get("relevance", 0) >= 0.3:
                            name = match.get("name") or thesis_names_by_id.get(tid, "")
                            if name:
                                affected_theses_from_matches.append(name)

                # Fallback: symbol-based matching
                affected_pos = [s for s in symbols if s in position_symbols]
                affected_theses_from_sym = [
                    thesis_names_by_sym[s] for s in symbols if s in thesis_symbols
                ]

                # Merge thesis matches
                affected_theses = list(set(
                    affected_theses_from_matches + [t for t in affected_theses_from_sym if t]
                ))

                if not affected_pos and not affected_theses:
                    continue

                # Determine urgency
                urgency = None
                category = "other"
                for level, keywords in urgent_keywords.items():
                    for kw in keywords:
                        if kw in headline:
                            urgency = level
                            if kw in ["acquisition", "merger"]:
                                category = "acquisition"
                            elif kw in ["earnings", "guidance"]:
                                category = "earnings"
                            elif kw in ["fda approval"]:
                                category = "fda"
                            elif kw in ["contract win"]:
                                category = "contract"
                            elif kw in ["regulation", "lawsuit", "investigation"]:
                                category = "policy"
                            break
                    if urgency:
                        break

                # Items with thesis matches but no urgent keyword get "medium"
                if not urgency and affected_theses:
                    urgency = "medium"
                    category = "thesis_related"

                if urgency:
                    sentiment = "neutral"
                    positive_words = ["win", "approval", "beat", "upgrade", "growth"]
                    negative_words = ["miss", "downgrade", "lawsuit", "resign", "bankruptcy"]
                    for pw in positive_words:
                        if pw in headline:
                            sentiment = "bullish"
                            break
                    for nw in negative_words:
                        if nw in headline:
                            sentiment = "bearish"
                            break

                    # Use direction from thesis match if available
                    if sentiment == "neutral" and thesis_matches:
                        for match in thesis_matches.values():
                            d = match.get("direction", "neutral")
                            if d in ("bullish", "bearish"):
                                sentiment = d
                                break

                    if sentiment == "bullish":
                        action = "Review for adding to affected positions"
                    elif sentiment == "bearish":
                        action = "Review risk exposure, consider reducing"
                    else:
                        action = "Monitor for price action"

                    alerts.append(NewsUrgencyAlert(
                        timestamp=item.get("timestamp", ""),
                        headline=item.get("headline", ""),
                        source=item.get("source", "unknown"),
                        urgency=urgency,
                        affected_symbols=affected_pos,
                        affected_theses=affected_theses,
                        category=category,
                        sentiment=sentiment,
                        recommended_action=action,
                    ))

        except Exception as e:
            logger.warning(f"Could not check news urgency: {e}")

        return alerts

    def _get_thesis_matched_news(self, limit: int = 20) -> list[dict]:
        """Get recent thesis-matched news items for state.json consumption.

        Returns the last N news items that have thesis_matches populated,
        for direct reading by Claude sessions.
        """
        try:
            news_path = paths.live / "news_cache.json"
            if not news_path.exists():
                return []

            with open(news_path) as f:
                news_data = json.load(f)

            matched = []
            for item in news_data.get("items", []):
                thesis_matches = item.get("thesis_matches", {})
                if thesis_matches:
                    matched.append({
                        "timestamp": item.get("timestamp", ""),
                        "headline": item.get("headline", ""),
                        "source": item.get("source", ""),
                        "thesis_matches": thesis_matches,
                        "is_urgent": item.get("is_urgent", False),
                    })
                if len(matched) >= limit:
                    break

            return matched

        except Exception as e:
            logger.debug(f"Could not get thesis matched news: {e}")
            return []

    async def _compute_conviction_decay(self, theses: list[ThesisSummary]) -> list[ConvictionDecayResult]:
        """Compute conviction decay for theses based on age and activity."""
        results = []

        decay_rules = {
            "no_signpost_30d": 10,      # No signpost in 30 days: -10%
            "thesis_age_90d": 5,        # Thesis >90 days old: -5%
            "thesis_age_180d": 10,      # Thesis >180 days old: additional -10%
            "bearish_signpost": 15,     # Bearish signpost triggered: -15%
        }

        try:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)

            for thesis_summary in theses:
                thesis = tracker.get_thesis(thesis_summary.id)
                if not thesis:
                    continue

                original_conviction = thesis.conviction
                total_decay = 0.0
                decay_reasons = []
                now = datetime.now()

                # Calculate days since creation
                created = thesis.created
                if isinstance(created, str):
                    created = datetime.fromisoformat(created)
                days_since_creation = (now - created).days

                # Calculate days since last signpost trigger
                last_trigger = None
                has_bearish = False
                for signpost in thesis.signposts:
                    if signpost.status == "triggered" and signpost.triggered_at:
                        trigger_time = signpost.triggered_at
                        if isinstance(trigger_time, str):
                            trigger_time = datetime.fromisoformat(trigger_time)
                        if last_trigger is None or trigger_time > last_trigger:
                            last_trigger = trigger_time
                        if signpost.outcome == "bearish":
                            has_bearish = True

                days_since_last_signpost = (now - last_trigger).days if last_trigger else days_since_creation

                # Apply decay rules
                if days_since_last_signpost > 30:
                    total_decay += decay_rules["no_signpost_30d"]
                    decay_reasons.append(f"No signpost activity in {days_since_last_signpost} days")

                if days_since_creation > 180:
                    total_decay += decay_rules["thesis_age_180d"]
                    decay_reasons.append(f"Thesis is {days_since_creation} days old (>180 days)")
                elif days_since_creation > 90:
                    total_decay += decay_rules["thesis_age_90d"]
                    decay_reasons.append(f"Thesis is {days_since_creation} days old (>90 days)")

                if has_bearish:
                    total_decay += decay_rules["bearish_signpost"]
                    decay_reasons.append("Bearish signpost was triggered")

                # Calculate current conviction after decay
                current_conviction = max(0, original_conviction - total_decay)

                # Determine status
                if current_conviction >= 60:
                    status = "healthy"
                elif current_conviction >= 40:
                    status = "warning"
                elif current_conviction >= 20:
                    status = "critical"
                else:
                    status = "auto_paused"

                results.append(ConvictionDecayResult(
                    thesis_id=thesis.id,
                    thesis_name=thesis.name,
                    original_conviction=original_conviction,
                    current_conviction=current_conviction,
                    decay_applied=total_decay,
                    decay_reasons=decay_reasons,
                    days_since_last_signpost=days_since_last_signpost,
                    days_since_creation=days_since_creation,
                    status=status,
                ))

        except Exception as e:
            logger.warning(f"Could not compute conviction decay: {e}")

        return results

    async def _compute_portfolio_history(self, portfolio: PortfolioSnapshot) -> Optional[PortfolioHistory]:
        """Compute portfolio history for accurate period returns."""
        try:
            # Portfolio history file
            history_path = paths.live / "portfolio_history.json"

            # Load existing history or create new
            if history_path.exists():
                with open(history_path) as f:
                    history_data = json.load(f)
                snapshots = [PortfolioHistorySnapshot.from_dict(s) for s in history_data.get("snapshots", [])]
            else:
                snapshots = []

            # Add today's snapshot if not already present
            today = datetime.now().strftime("%Y-%m-%d")
            today_exists = any(s.date == today for s in snapshots)

            if not today_exists and portfolio.equity > 0:
                # Get SPY price
                spy_price = 0.0
                spy_pct = 0.0
                try:
                    from alpaca.data.historical import StockHistoricalDataClient
                    from alpaca.data.requests import StockLatestQuoteRequest
                    import yaml

                    creds_path = Path(__file__).parent.parent.parent / "config" / "credentials.yaml"
                    with open(creds_path) as f:
                        creds = yaml.safe_load(f)

                    data_client = StockHistoricalDataClient(
                        creds['alpaca']['api_key'],
                        creds['alpaca']['secret_key'],
                    )

                    quote = data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols="SPY"))
                    if quote and "SPY" in quote:
                        spy_price = (quote["SPY"].ask_price + quote["SPY"].bid_price) / 2

                    # Get yesterday's SPY for daily return
                    if len(snapshots) > 0:
                        prev_spy = snapshots[-1].spy_close
                        if prev_spy > 0 and spy_price > 0:
                            spy_pct = ((spy_price - prev_spy) / prev_spy) * 100
                except Exception as e:
                    logger.warning(f"Could not get SPY price for history: {e}")

                snapshots.append(PortfolioHistorySnapshot(
                    date=today,
                    equity=portfolio.equity,
                    cash=portfolio.cash,
                    positions_value=portfolio.equity - portfolio.cash,
                    day_pnl=portfolio.day_pnl,
                    day_pnl_pct=portfolio.day_pnl_pct,
                    spy_close=spy_price,
                    spy_pct=spy_pct,
                ))

                # Keep only last 60 days
                snapshots = snapshots[-60:]

                # Save updated history
                history_data = {"snapshots": [s.to_dict() for s in snapshots]}
                history_path.parent.mkdir(parents=True, exist_ok=True)
                with open(history_path, "w") as f:
                    json.dump(history_data, f, indent=2)

            # Compute period returns
            week_start_equity = portfolio.equity
            week_pnl = 0.0
            week_pnl_pct = 0.0
            week_spy_pct = 0.0

            month_start_equity = portfolio.equity
            month_pnl = 0.0
            month_pnl_pct = 0.0
            month_spy_pct = 0.0

            if len(snapshots) >= 5:
                # Week (5 trading days ago)
                week_idx = max(0, len(snapshots) - 5)
                week_start_equity = snapshots[week_idx].equity
                week_pnl = portfolio.equity - week_start_equity
                week_pnl_pct = (week_pnl / week_start_equity * 100) if week_start_equity > 0 else 0

                # Sum SPY returns for the week
                for s in snapshots[week_idx:]:
                    week_spy_pct += s.spy_pct

            if len(snapshots) >= 20:
                # Month (20 trading days ago)
                month_idx = max(0, len(snapshots) - 20)
                month_start_equity = snapshots[month_idx].equity
                month_pnl = portfolio.equity - month_start_equity
                month_pnl_pct = (month_pnl / month_start_equity * 100) if month_start_equity > 0 else 0

                # Sum SPY returns for the month
                for s in snapshots[month_idx:]:
                    month_spy_pct += s.spy_pct

            return PortfolioHistory(
                snapshots=snapshots[-10:],  # Only keep last 10 in state.json
                week_start_equity=week_start_equity,
                week_pnl=week_pnl,
                week_pnl_pct=week_pnl_pct,
                month_start_equity=month_start_equity,
                month_pnl=month_pnl,
                month_pnl_pct=month_pnl_pct,
                week_spy_pct=week_spy_pct,
                month_spy_pct=month_spy_pct,
                vs_spy_week=week_pnl_pct - week_spy_pct,
                vs_spy_month=month_pnl_pct - month_spy_pct,
            )

        except Exception as e:
            logger.warning(f"Could not compute portfolio history: {e}")
            return None

    async def _get_alternative_signals(self) -> Optional[dict]:
        """Get alternative signals from disconnected data sources.

        This connects the previously unused data sources to the unified state:
        - Weather → Energy signals (HDD anomalies → nat gas)
        - FDA Calendar → Binary event alerts
        - Short Interest + Social → Squeeze candidates
        - Research Insights → Actionable recommendations
        - WSB/Stocktwits → Social signals (early alpha, trending)
        - Finviz → Screen results (momentum, squeeze, insider buying)
        - Congressional → Notable political trades

        Added: 2026-01-19 per SYSTEM_COHESION_AUDIT.md
        Enhanced: 2026-03-05 — added social, screen, congressional signals
        """
        result = {}

        # Original alternative signals
        try:
            from src.synthesis.alternative_signals import AlternativeSignalGenerator

            generator = AlternativeSignalGenerator()
            signals = await generator.generate_all()
            result = signals.to_dict()
        except ImportError as e:
            logger.warning(f"Alternative signals module not available: {e}")
        except Exception as e:
            logger.warning(f"Could not generate alternative signals: {e}")

        # Augment with cached social/screen/congressional data
        result.update(self._read_social_signals())

        # Market movers from cron_market_movers.py
        result.update(self._read_market_movers())

        return result if result else None

    def _read_social_signals(self) -> dict:
        """Read cached social, screen, and congressional data files.

        These files are written by collect_all_data.py collectors.
        We read the cached results rather than re-fetching to stay fast.
        """
        import json
        signals = {}

        # WSB early signals
        try:
            wsb_file = paths.base / "social" / "wsb_signals.json"
            if wsb_file.exists():
                with open(wsb_file) as f:
                    wsb_data = json.load(f)
                # File format: {"updated_at": ..., "early_signals": [...], "trending_signals": [...]}
                early = wsb_data.get("early_signals", []) if isinstance(wsb_data, dict) else []
                trending = wsb_data.get("trending_signals", []) if isinstance(wsb_data, dict) else []
                signals["social_wsb"] = {
                    "early_signals": early[:10],
                    "trending_signals": trending[:10],
                    "updated_at": wsb_data.get("updated_at") if isinstance(wsb_data, dict) else None,
                }
        except Exception as e:
            logger.debug(f"Could not read WSB signals: {e}")

        # Stocktwits trending
        try:
            st_file = paths.base / "social" / "stocktwits_cache.json"
            if st_file.exists():
                with open(st_file) as f:
                    st_data = json.load(f)
                trending = st_data.get("trending", [])[:10] if isinstance(st_data, dict) else []
                signals["social_stocktwits"] = {
                    "trending": trending,
                    "total_symbols": len(st_data.get("symbols", {})) if isinstance(st_data, dict) else 0,
                }
        except Exception as e:
            logger.debug(f"Could not read Stocktwits data: {e}")

        # Finviz screens
        try:
            finviz_file = paths.base / "scraped_data" / "finviz" / "screens_latest.json"
            if finviz_file.exists():
                with open(finviz_file) as f:
                    finviz_data = json.load(f)
                # Extract top screens with symbols (context-efficient)
                screens_summary = {}
                for screen_name, screen_data in finviz_data.get("screens", {}).items():
                    if isinstance(screen_data, dict) and screen_data.get("symbols"):
                        screens_summary[screen_name] = {
                            "symbols": screen_data["symbols"][:10],
                            "count": screen_data.get("symbol_count", len(screen_data["symbols"])),
                        }
                signals["screens_finviz"] = screens_summary
        except Exception as e:
            logger.debug(f"Could not read Finviz screens: {e}")

        # Congressional trades (from collection history)
        try:
            cong_file = paths.base / "logs" / "congressional_collection_history.json"
            if cong_file.exists():
                with open(cong_file) as f:
                    history = json.load(f)
                if history and isinstance(history, list):
                    last = history[-1]
                    notable = last.get("result", {}).get("notable_trades", [])
                    signals["congressional"] = {
                        "notable_trades": notable[:10] if isinstance(notable, list) else [],
                        "last_collected": last.get("timestamp"),
                    }
        except Exception as e:
            logger.debug(f"Could not read congressional data: {e}")

        return signals

    def _read_market_movers(self) -> dict:
        """Read cached market mover scan results from cron_market_movers.py output."""
        signals = {}
        try:
            movers_file = paths.base / "live" / "market_movers_latest.json"
            if movers_file.exists():
                with open(movers_file) as f:
                    data = json.load(f)
                signals["market_movers"] = {
                    "timestamp": data.get("timestamp"),
                    "universe_size": data.get("universe_size", 0),
                    "movers_found": data.get("movers_found", 0),
                    "top_gainers": [
                        {"symbol": m["symbol"], "change_1d": m["change_1d_pct"],
                         "trigger": m["trigger"], "context_score": m["context_score"]}
                        for m in data.get("gainers", [])[:5]
                    ],
                    "top_losers": [
                        {"symbol": m["symbol"], "change_1d": m["change_1d_pct"],
                         "trigger": m["trigger"], "context_score": m["context_score"]}
                        for m in data.get("losers", [])[:5]
                    ],
                    "top_context": [
                        {"symbol": m["symbol"], "change_1d": m.get("change_1d_pct", 0),
                         "context_score": m["context_score"],
                         "thesis_alignment": m.get("thesis_alignment")}
                        for m in data.get("top_context", [])[:5]
                    ],
                }
        except Exception as e:
            logger.debug(f"Could not read market movers: {e}")
        return signals


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Live State Daemon")
    parser.add_argument("--interval", type=int, default=5, help="Update interval in minutes")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    daemon = LiveDaemon()

    if args.once:
        state = await daemon.update_now()
        print(state.get_summary())
    else:
        await daemon.start(interval_minutes=args.interval)
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await daemon.stop()


if __name__ == "__main__":
    asyncio.run(main())
