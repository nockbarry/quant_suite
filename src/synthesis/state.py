"""Unified State - The ONE file to read for everything.

This module defines the central state schema that aggregates all market data,
portfolio state, signals, theses, decisions, and learnings into a single file.

The LiveDaemon writes to ~/quant_results/live/state.json continuously.
Claude reads this file once to get all current context.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    """Current market context from market_breadth.py."""

    timestamp: datetime
    spy_price: float
    spy_change_pct: float
    qqq_price: float
    qqq_change_pct: float
    vix: float
    vix_change_pct: float

    # Breadth
    advance_decline_ratio: float
    new_highs: int
    new_lows: int

    # Sectors (top 3 leaders, bottom 3 laggards)
    leading_sectors: list[str]
    lagging_sectors: list[str]
    rotation_theme: str  # e.g., "risk-on rotation to growth"

    # Regime
    regime: str  # risk-on, risk-off, transitioning
    regime_confidence: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "spy_price": self.spy_price,
            "spy_change_pct": self.spy_change_pct,
            "qqq_price": self.qqq_price,
            "qqq_change_pct": self.qqq_change_pct,
            "vix": self.vix,
            "vix_change_pct": self.vix_change_pct,
            "advance_decline_ratio": self.advance_decline_ratio,
            "new_highs": self.new_highs,
            "new_lows": self.new_lows,
            "leading_sectors": self.leading_sectors,
            "lagging_sectors": self.lagging_sectors,
            "rotation_theme": self.rotation_theme,
            "regime": self.regime,
            "regime_confidence": self.regime_confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MarketSnapshot":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            spy_price=data["spy_price"],
            spy_change_pct=data["spy_change_pct"],
            qqq_price=data["qqq_price"],
            qqq_change_pct=data["qqq_change_pct"],
            vix=data["vix"],
            vix_change_pct=data["vix_change_pct"],
            advance_decline_ratio=data["advance_decline_ratio"],
            new_highs=data["new_highs"],
            new_lows=data["new_lows"],
            leading_sectors=data["leading_sectors"],
            lagging_sectors=data["lagging_sectors"],
            rotation_theme=data["rotation_theme"],
            regime=data["regime"],
            regime_confidence=data["regime_confidence"],
        )


@dataclass
class SentimentSnapshot:
    """Current sentiment indicators from sentiment.py."""

    timestamp: datetime
    fear_greed_value: float  # 0-100
    fear_greed_label: str  # extreme_fear, fear, neutral, greed, extreme_greed
    put_call_ratio: float
    put_call_signal: str  # bullish, bearish, neutral
    vix_term_structure: str  # contango, backwardation, flat
    overall_sentiment: str  # bullish, bearish, neutral
    contrarian_signal: Optional[str]  # buy, sell, or None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "fear_greed_value": self.fear_greed_value,
            "fear_greed_label": self.fear_greed_label,
            "put_call_ratio": self.put_call_ratio,
            "put_call_signal": self.put_call_signal,
            "vix_term_structure": self.vix_term_structure,
            "overall_sentiment": self.overall_sentiment,
            "contrarian_signal": self.contrarian_signal,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SentimentSnapshot":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            fear_greed_value=data["fear_greed_value"],
            fear_greed_label=data["fear_greed_label"],
            put_call_ratio=data["put_call_ratio"],
            put_call_signal=data["put_call_signal"],
            vix_term_structure=data["vix_term_structure"],
            overall_sentiment=data["overall_sentiment"],
            contrarian_signal=data.get("contrarian_signal"),
        )


@dataclass
class PositionSnapshot:
    """Current position state."""

    symbol: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    day_pnl: float
    day_pnl_pct: float
    weight_pct: float  # Portfolio weight

    # Context
    sector: str
    days_held: int
    thesis_id: Optional[str]  # Link to thesis if any

    # Risk
    distance_to_stop_pct: Optional[float]
    distance_to_target_pct: Optional[float]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "day_pnl": self.day_pnl,
            "day_pnl_pct": self.day_pnl_pct,
            "weight_pct": self.weight_pct,
            "sector": self.sector,
            "days_held": self.days_held,
            "thesis_id": self.thesis_id,
            "distance_to_stop_pct": self.distance_to_stop_pct,
            "distance_to_target_pct": self.distance_to_target_pct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PositionSnapshot":
        return cls(
            symbol=data["symbol"],
            quantity=data["quantity"],
            avg_cost=data["avg_cost"],
            current_price=data["current_price"],
            market_value=data["market_value"],
            unrealized_pnl=data["unrealized_pnl"],
            unrealized_pnl_pct=data["unrealized_pnl_pct"],
            day_pnl=data["day_pnl"],
            day_pnl_pct=data["day_pnl_pct"],
            weight_pct=data["weight_pct"],
            sector=data["sector"],
            days_held=data["days_held"],
            thesis_id=data.get("thesis_id"),
            distance_to_stop_pct=data.get("distance_to_stop_pct"),
            distance_to_target_pct=data.get("distance_to_target_pct"),
        )


@dataclass
class PortfolioSnapshot:
    """Current portfolio state from Alpaca."""

    timestamp: datetime
    equity: float
    cash: float
    buying_power: float
    day_pnl: float
    day_pnl_pct: float
    total_positions: int
    market_exposure_pct: float  # Long exposure as % of equity

    # PDT
    day_trades_remaining: int
    pdt_restricted: bool

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity": self.equity,
            "cash": self.cash,
            "buying_power": self.buying_power,
            "day_pnl": self.day_pnl,
            "day_pnl_pct": self.day_pnl_pct,
            "total_positions": self.total_positions,
            "market_exposure_pct": self.market_exposure_pct,
            "day_trades_remaining": self.day_trades_remaining,
            "pdt_restricted": self.pdt_restricted,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PortfolioSnapshot":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            equity=data["equity"],
            cash=data["cash"],
            buying_power=data["buying_power"],
            day_pnl=data["day_pnl"],
            day_pnl_pct=data["day_pnl_pct"],
            total_positions=data["total_positions"],
            market_exposure_pct=data["market_exposure_pct"],
            day_trades_remaining=data["day_trades_remaining"],
            pdt_restricted=data["pdt_restricted"],
        )


@dataclass
class RiskSnapshot:
    """Portfolio risk metrics from position_monitor.py."""

    timestamp: datetime
    portfolio_var_1d: float  # 1-day VaR at 95%
    portfolio_var_pct: float
    max_position_weight: float
    max_sector_weight: float
    correlation_risk: str  # low, medium, high
    concentration_warning: Optional[str]
    limit_breaches: list[str]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "portfolio_var_1d": self.portfolio_var_1d,
            "portfolio_var_pct": self.portfolio_var_pct,
            "max_position_weight": self.max_position_weight,
            "max_sector_weight": self.max_sector_weight,
            "correlation_risk": self.correlation_risk,
            "concentration_warning": self.concentration_warning,
            "limit_breaches": self.limit_breaches,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RiskSnapshot":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            portfolio_var_1d=data["portfolio_var_1d"],
            portfolio_var_pct=data["portfolio_var_pct"],
            max_position_weight=data["max_position_weight"],
            max_sector_weight=data["max_sector_weight"],
            correlation_risk=data["correlation_risk"],
            concentration_warning=data.get("concentration_warning"),
            limit_breaches=data.get("limit_breaches", []),
        )


@dataclass
class CalendarEvent:
    """Upcoming market event."""

    date: str  # YYYY-MM-DD
    time: Optional[str]  # HH:MM ET
    event_type: str  # earnings, economic, fed, options_expiry
    symbol: Optional[str]  # For earnings
    description: str
    importance: str  # high, medium, low
    expected_impact: Optional[str]

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "time": self.time,
            "event_type": self.event_type,
            "symbol": self.symbol,
            "description": self.description,
            "importance": self.importance,
            "expected_impact": self.expected_impact,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CalendarEvent":
        return cls(
            date=data["date"],
            time=data.get("time"),
            event_type=data["event_type"],
            symbol=data.get("symbol"),
            description=data["description"],
            importance=data["importance"],
            expected_impact=data.get("expected_impact"),
        )


@dataclass
class ResearchIndex:
    """Pointers to pre-computed research files."""

    last_updated: datetime
    features_file: str
    signals_file: str
    alt_data_file: str
    screens_file: str
    available: bool  # Whether files exist and are fresh

    def to_dict(self) -> dict:
        return {
            "last_updated": self.last_updated.isoformat(),
            "features_file": self.features_file,
            "signals_file": self.signals_file,
            "alt_data_file": self.alt_data_file,
            "screens_file": self.screens_file,
            "available": self.available,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResearchIndex":
        return cls(
            last_updated=datetime.fromisoformat(data["last_updated"]),
            features_file=data["features_file"],
            signals_file=data["signals_file"],
            alt_data_file=data["alt_data_file"],
            screens_file=data["screens_file"],
            available=data["available"],
        )


@dataclass
class ThesisSummary:
    """Summary of an active thesis for unified state."""

    id: str
    name: str
    status: str  # active, at_risk, validated
    conviction: float
    positions: list[str]
    next_signpost: Optional[str]
    days_active: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "conviction": self.conviction,
            "positions": self.positions,
            "next_signpost": self.next_signpost,
            "days_active": self.days_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThesisSummary":
        return cls(
            id=data["id"],
            name=data["name"],
            status=data["status"],
            conviction=data["conviction"],
            positions=data["positions"],
            next_signpost=data.get("next_signpost"),
            days_active=data["days_active"],
        )


@dataclass
class PendingDecision:
    """Decision awaiting outcome."""

    id: str
    symbol: str
    action: str
    timestamp: str
    confidence: float
    entry_price: Optional[float]
    current_price: float
    unrealized_pnl_pct: float
    thesis_id: Optional[str]
    days_held: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "action": self.action,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "thesis_id": self.thesis_id,
            "days_held": self.days_held,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PendingDecision":
        return cls(
            id=data["id"],
            symbol=data["symbol"],
            action=data["action"],
            timestamp=data["timestamp"],
            confidence=data["confidence"],
            entry_price=data.get("entry_price"),
            current_price=data["current_price"],
            unrealized_pnl_pct=data["unrealized_pnl_pct"],
            thesis_id=data.get("thesis_id"),
            days_held=data["days_held"],
        )


@dataclass
class LearningSummary:
    """Summary of a recent learning."""

    id: str
    date: str
    symbol: str
    outcome: str  # win, loss, scratch
    pnl_pct: float
    key_learning: str
    tags: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "symbol": self.symbol,
            "outcome": self.outcome,
            "pnl_pct": self.pnl_pct,
            "key_learning": self.key_learning,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LearningSummary":
        return cls(
            id=data["id"],
            date=data["date"],
            symbol=data["symbol"],
            outcome=data["outcome"],
            pnl_pct=data["pnl_pct"],
            key_learning=data["key_learning"],
            tags=data["tags"],
        )


@dataclass
class AlertSnapshot:
    """Active alert."""

    id: str
    alert_type: str
    symbol: str
    message: str
    priority: str
    triggered_at: str
    acknowledged: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "symbol": self.symbol,
            "message": self.message,
            "priority": self.priority,
            "triggered_at": self.triggered_at,
            "acknowledged": self.acknowledged,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AlertSnapshot":
        return cls(
            id=data["id"],
            alert_type=data["alert_type"],
            symbol=data["symbol"],
            message=data["message"],
            priority=data["priority"],
            triggered_at=data["triggered_at"],
            acknowledged=data["acknowledged"],
        )


@dataclass
class UnifiedState:
    """
    The ONE file to read for everything.

    This is the central state object that aggregates all data sources.
    Written to ~/quant_results/live/state.json by the LiveDaemon.
    """

    # Metadata
    timestamp: datetime
    market_open: bool
    last_updated_by: str  # daemon, manual, skill

    # Market Context
    market: MarketSnapshot
    sentiment: SentimentSnapshot

    # Portfolio
    portfolio: PortfolioSnapshot
    positions: list[PositionSnapshot]
    risk: RiskSnapshot

    # Signals (keyed by symbol)
    watchlist_signals: dict[str, dict]  # symbol -> AggregatedSignal.to_dict()

    # Theses
    theses: list[ThesisSummary]

    # Decisions
    pending_decisions: list[PendingDecision]

    # Learnings
    recent_learnings: list[LearningSummary]

    # Alerts
    alerts: list[AlertSnapshot]

    # Calendar
    upcoming_events: list[CalendarEvent]

    # Research
    research: ResearchIndex

    # Summary for quick LLM consumption
    summary: str = ""

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "market_open": self.market_open,
            "last_updated_by": self.last_updated_by,
            "market": self.market.to_dict(),
            "sentiment": self.sentiment.to_dict(),
            "portfolio": self.portfolio.to_dict(),
            "positions": [p.to_dict() for p in self.positions],
            "risk": self.risk.to_dict(),
            "watchlist_signals": self.watchlist_signals,
            "theses": [t.to_dict() for t in self.theses],
            "pending_decisions": [d.to_dict() for d in self.pending_decisions],
            "recent_learnings": [l.to_dict() for l in self.recent_learnings],
            "alerts": [a.to_dict() for a in self.alerts],
            "upcoming_events": [e.to_dict() for e in self.upcoming_events],
            "research": self.research.to_dict(),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedState":
        """Deserialize from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            market_open=data["market_open"],
            last_updated_by=data["last_updated_by"],
            market=MarketSnapshot.from_dict(data["market"]),
            sentiment=SentimentSnapshot.from_dict(data["sentiment"]),
            portfolio=PortfolioSnapshot.from_dict(data["portfolio"]),
            positions=[PositionSnapshot.from_dict(p) for p in data["positions"]],
            risk=RiskSnapshot.from_dict(data["risk"]),
            watchlist_signals=data["watchlist_signals"],
            theses=[ThesisSummary.from_dict(t) for t in data["theses"]],
            pending_decisions=[PendingDecision.from_dict(d) for d in data["pending_decisions"]],
            recent_learnings=[LearningSummary.from_dict(l) for l in data["recent_learnings"]],
            alerts=[AlertSnapshot.from_dict(a) for a in data["alerts"]],
            upcoming_events=[CalendarEvent.from_dict(e) for e in data["upcoming_events"]],
            research=ResearchIndex.from_dict(data["research"]),
            summary=data.get("summary", ""),
        )

    def to_file(self, path: Path) -> None:
        """Write state to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Wrote unified state to {path}")

    @classmethod
    def load(cls, path: Optional[Path] = None) -> Optional["UnifiedState"]:
        """Load state from JSON file."""
        if path is None:
            from src.core.paths import paths
            path = paths.live_state

        if not path.exists():
            logger.warning(f"State file not found: {path}")
            return None

        try:
            with open(path, "r") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None

    def get_summary(self) -> str:
        """Generate LLM-ready markdown summary."""
        lines = [
            f"# Market State - {self.timestamp.strftime('%Y-%m-%d %H:%M ET')}",
            "",
            "## Market",
            f"- SPY: ${self.market.spy_price:.2f} ({self.market.spy_change_pct:+.2f}%)",
            f"- VIX: {self.market.vix:.1f} ({self.market.vix_change_pct:+.1f}%)",
            f"- Regime: **{self.market.regime}** ({self.market.regime_confidence:.0%} confidence)",
            f"- Sentiment: {self.sentiment.overall_sentiment} (Fear/Greed: {self.sentiment.fear_greed_value:.0f})",
            "",
            "## Portfolio",
            f"- Equity: ${self.portfolio.equity:,.0f}",
            f"- Day P&L: ${self.portfolio.day_pnl:+,.0f} ({self.portfolio.day_pnl_pct:+.2f}%)",
            f"- Exposure: {self.portfolio.market_exposure_pct:.0f}%",
            f"- Day Trades Remaining: {self.portfolio.day_trades_remaining}",
            "",
        ]

        if self.positions:
            lines.append("## Positions")
            for p in self.positions:
                lines.append(
                    f"- **{p.symbol}**: {p.quantity} @ ${p.avg_cost:.2f} → "
                    f"${p.current_price:.2f} ({p.unrealized_pnl_pct:+.1f}%)"
                )
            lines.append("")

        if self.theses:
            lines.append("## Active Theses")
            for t in self.theses:
                lines.append(f"- **{t.name}** ({t.conviction:.0f}% conviction): {', '.join(t.positions)}")
            lines.append("")

        if self.alerts:
            lines.append("## Active Alerts")
            for a in self.alerts:
                lines.append(f"- [{a.priority}] {a.symbol}: {a.message}")
            lines.append("")

        if self.pending_decisions:
            lines.append("## Pending Decisions")
            for d in self.pending_decisions:
                lines.append(
                    f"- {d.symbol} {d.action} (conf: {d.confidence:.0%}, "
                    f"P&L: {d.unrealized_pnl_pct:+.1f}%, {d.days_held}d held)"
                )
            lines.append("")

        if self.upcoming_events:
            lines.append("## Upcoming Events")
            for e in self.upcoming_events[:5]:  # Top 5
                lines.append(f"- {e.date}: {e.description} [{e.importance}]")
            lines.append("")

        return "\n".join(lines)
