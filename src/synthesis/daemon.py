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
from datetime import datetime, timedelta
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
            output_path: Where to write state.json.
                        Defaults to paths.live_state.
        """
        self.watchlist = watchlist or self.DEFAULT_WATCHLIST
        self.output_path = output_path or paths.live_state
        self.signal_aggregator = SignalAggregator(watchlist=self.watchlist)

        self._running = False
        self._task: Optional[asyncio.Task] = None

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

        # Determine if market is open
        market_open = self._is_market_open(now)

        # Gather all components
        market = await self._get_market_snapshot()
        sentiment = await self._get_sentiment_snapshot()
        portfolio = await self._get_portfolio_snapshot()
        positions = await self._get_positions()
        risk = await self._get_risk_snapshot()
        signals = self._get_signals()
        theses = await self._get_theses()
        pending = await self._get_pending_decisions()
        learnings = await self._get_recent_learnings()
        alerts = await self._get_alerts()
        events = await self._get_calendar_events()
        research = self._get_research_index()

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
        )

        # Generate summary
        state.summary = state.get_summary()

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
                return MarketSnapshot(
                    timestamp=now,
                    spy_price=breadth.spy_price,
                    spy_change_pct=breadth.spy_change_pct,
                    qqq_price=breadth.qqq_price,
                    qqq_change_pct=breadth.qqq_change_pct,
                    vix=breadth.vix,
                    vix_change_pct=breadth.vix_change_pct,
                    advance_decline_ratio=breadth.advance_decline_ratio,
                    new_highs=breadth.new_highs,
                    new_lows=breadth.new_lows,
                    leading_sectors=breadth.leading_sectors[:3],
                    lagging_sectors=breadth.lagging_sectors[:3],
                    rotation_theme=breadth.rotation_theme,
                    regime=breadth.regime,
                    regime_confidence=breadth.regime_confidence,
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
                return SentimentSnapshot(
                    timestamp=now,
                    fear_greed_value=indicators.fear_greed.value,
                    fear_greed_label=indicators.fear_greed.label,
                    put_call_ratio=indicators.put_call.ratio,
                    put_call_signal=indicators.put_call.signal,
                    vix_term_structure=indicators.vix_structure.structure,
                    overall_sentiment=indicators.overall_sentiment,
                    contrarian_signal=indicators.contrarian_signal,
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
            from src.execution.alpaca_client import get_account

            account = await get_account()
            if account:
                equity = float(account.equity)
                day_pl = float(account.equity) - float(account.last_equity)

                return PortfolioSnapshot(
                    timestamp=now,
                    equity=equity,
                    cash=float(account.cash),
                    buying_power=float(account.buying_power),
                    day_pnl=day_pl,
                    day_pnl_pct=(day_pl / float(account.last_equity)) * 100 if float(account.last_equity) > 0 else 0,
                    total_positions=0,  # Will be set from positions
                    market_exposure_pct=0.0,  # Will be computed
                    day_trades_remaining=account.daytrade_count if hasattr(account, 'daytrade_count') else 3,
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

    async def _get_positions(self) -> list[PositionSnapshot]:
        """Get current positions from Alpaca."""
        positions = []

        try:
            from src.execution.alpaca_client import get_positions

            alpaca_positions = await get_positions()
            for p in alpaca_positions:
                positions.append(PositionSnapshot(
                    symbol=p.symbol,
                    quantity=int(p.qty),
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
                    thesis_id=None,  # Would need to look up
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
                return RiskSnapshot(
                    timestamp=now,
                    portfolio_var_1d=risk.var_1d,
                    portfolio_var_pct=risk.var_pct,
                    max_position_weight=risk.max_position_weight,
                    max_sector_weight=risk.max_sector_weight,
                    correlation_risk=risk.correlation_risk,
                    concentration_warning=risk.concentration_warning,
                    limit_breaches=risk.limit_breaches,
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
        except Exception as e:
            logger.warning(f"Signal aggregation failed: {e}")
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
        except Exception as e:
            logger.debug(f"Thesis tracker not available: {e}")

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

    def _get_sector(self, symbol: str) -> str:
        """Get sector for a symbol."""
        # Simple sector mapping - could be expanded
        sector_map = {
            "SLB": "Energy", "HAL": "Energy", "OXY": "Energy", "XOM": "Energy", "CVX": "Energy",
            "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology", "META": "Technology",
            "NVDA": "Technology", "AMD": "Technology",
            "JPM": "Financials", "BAC": "Financials", "GS": "Financials",
            "XLE": "Energy", "XLF": "Financials", "XLK": "Technology",
        }
        return sector_map.get(symbol, "Unknown")


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
