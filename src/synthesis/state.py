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

from src.core.paths import paths

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
    contrarian_signal: Optional[str] = None  # buy, sell, or None

    # NEW: Enhanced VIX term structure
    vix_1m: Optional[float] = None
    vix_3m: Optional[float] = None
    vix_slope: Optional[float] = None  # (longer - shorter) / shorter
    vix_regime: Optional[str] = None  # "steep_contango", "contango", "flat", "backwardation"

    # NEW: Retail sentiment (AAII)
    aaii_bullish: Optional[float] = None  # % bullish
    aaii_bearish: Optional[float] = None  # % bearish
    aaii_signal: Optional[str] = None  # "extreme_bullish", "bullish", "neutral", "bearish", "extreme_bearish"

    # NEW: Advisor sentiment (Investors Intelligence)
    newsletter_bulls: Optional[float] = None  # % bulls
    newsletter_signal: Optional[str] = None  # bullish, bearish, neutral

    # NEW: COT summary (Commitment of Traders)
    cot_sp500_commercial_net: Optional[int] = None  # Commercial net position
    cot_signal: Optional[str] = None  # "bullish" (follow commercials), "bearish", "neutral"

    # NEW: Fed expectations
    fed_prob_cut: Optional[float] = None  # Probability of rate cut at next meeting
    fed_prob_hike: Optional[float] = None  # Probability of rate hike
    fed_path_signal: Optional[str] = None  # "hawkish", "dovish", "neutral"

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
            # NEW: Enhanced VIX
            "vix_1m": self.vix_1m,
            "vix_3m": self.vix_3m,
            "vix_slope": self.vix_slope,
            "vix_regime": self.vix_regime,
            # NEW: Retail sentiment
            "aaii_bullish": self.aaii_bullish,
            "aaii_bearish": self.aaii_bearish,
            "aaii_signal": self.aaii_signal,
            # NEW: Advisor sentiment
            "newsletter_bulls": self.newsletter_bulls,
            "newsletter_signal": self.newsletter_signal,
            # NEW: COT
            "cot_sp500_commercial_net": self.cot_sp500_commercial_net,
            "cot_signal": self.cot_signal,
            # NEW: Fed
            "fed_prob_cut": self.fed_prob_cut,
            "fed_prob_hike": self.fed_prob_hike,
            "fed_path_signal": self.fed_path_signal,
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
            # NEW: Enhanced VIX
            vix_1m=data.get("vix_1m"),
            vix_3m=data.get("vix_3m"),
            vix_slope=data.get("vix_slope"),
            vix_regime=data.get("vix_regime"),
            # NEW: Retail sentiment
            aaii_bullish=data.get("aaii_bullish"),
            aaii_bearish=data.get("aaii_bearish"),
            aaii_signal=data.get("aaii_signal"),
            # NEW: Advisor sentiment
            newsletter_bulls=data.get("newsletter_bulls"),
            newsletter_signal=data.get("newsletter_signal"),
            # NEW: COT
            cot_sp500_commercial_net=data.get("cot_sp500_commercial_net"),
            cot_signal=data.get("cot_signal"),
            # NEW: Fed
            fed_prob_cut=data.get("fed_prob_cut"),
            fed_prob_hike=data.get("fed_prob_hike"),
            fed_path_signal=data.get("fed_path_signal"),
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
    thesis_id: Optional[str] = None  # Link to thesis if any

    # Risk
    distance_to_stop_pct: Optional[float] = None
    distance_to_target_pct: Optional[float] = None

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
    concentration_warning: Optional[str] = None
    limit_breaches: list[str] = field(default_factory=list)

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
    event_type: str  # earnings, economic, fed, options_expiry
    description: str
    importance: str  # high, medium, low
    time: Optional[str] = None  # HH:MM ET
    symbol: Optional[str] = None  # For earnings
    expected_impact: Optional[str] = None

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
            event_type=data["event_type"],
            description=data["description"],
            importance=data["importance"],
            time=data.get("time"),
            symbol=data.get("symbol"),
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
    days_active: int
    next_signpost: Optional[str] = None

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
            days_active=data["days_active"],
            next_signpost=data.get("next_signpost"),
        )


@dataclass
class PendingDecision:
    """Decision awaiting outcome."""

    id: str
    symbol: str
    action: str
    timestamp: str
    confidence: float
    current_price: float
    unrealized_pnl_pct: float
    days_held: int
    entry_price: Optional[float] = None
    thesis_id: Optional[str] = None

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
            current_price=data["current_price"],
            unrealized_pnl_pct=data["unrealized_pnl_pct"],
            days_held=data["days_held"],
            entry_price=data.get("entry_price"),
            thesis_id=data.get("thesis_id"),
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


# ============================================================================
# NEW: Pre-computed data structures for efficient Claude queries
# ============================================================================

@dataclass
class ThesisPositionDetail:
    """Individual position within a thesis."""
    symbol: str
    quantity: int
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    day_pnl: float
    weight_in_thesis_pct: float
    weight_in_portfolio_pct: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "market_value": self.market_value,
            "cost_basis": self.cost_basis,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "day_pnl": self.day_pnl,
            "weight_in_thesis_pct": self.weight_in_thesis_pct,
            "weight_in_portfolio_pct": self.weight_in_portfolio_pct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThesisPositionDetail":
        return cls(**data)


@dataclass
class ThesisPerformance:
    """Pre-computed performance for a single thesis."""
    thesis_id: str
    thesis_name: str
    conviction: float
    status: str
    total_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    day_pnl: float
    day_pnl_pct: float
    weight_in_portfolio_pct: float
    position_count: int
    positions: list[ThesisPositionDetail]

    # Divergence tracking
    best_performer: Optional[str] = None
    best_performer_pnl_pct: float = 0.0
    worst_performer: Optional[str] = None
    worst_performer_pnl_pct: float = 0.0
    divergence_pct: float = 0.0  # Spread between best and worst

    def to_dict(self) -> dict:
        return {
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "conviction": self.conviction,
            "status": self.status,
            "total_value": self.total_value,
            "total_cost": self.total_cost,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "day_pnl": self.day_pnl,
            "day_pnl_pct": self.day_pnl_pct,
            "weight_in_portfolio_pct": self.weight_in_portfolio_pct,
            "position_count": self.position_count,
            "positions": [p.to_dict() for p in self.positions],
            "best_performer": self.best_performer,
            "best_performer_pnl_pct": self.best_performer_pnl_pct,
            "worst_performer": self.worst_performer,
            "worst_performer_pnl_pct": self.worst_performer_pnl_pct,
            "divergence_pct": self.divergence_pct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThesisPerformance":
        positions = [ThesisPositionDetail.from_dict(p) for p in data.get("positions", [])]
        return cls(
            thesis_id=data["thesis_id"],
            thesis_name=data["thesis_name"],
            conviction=data["conviction"],
            status=data["status"],
            total_value=data["total_value"],
            total_cost=data["total_cost"],
            total_pnl=data["total_pnl"],
            total_pnl_pct=data["total_pnl_pct"],
            day_pnl=data["day_pnl"],
            day_pnl_pct=data["day_pnl_pct"],
            weight_in_portfolio_pct=data["weight_in_portfolio_pct"],
            position_count=data["position_count"],
            positions=positions,
            best_performer=data.get("best_performer"),
            best_performer_pnl_pct=data.get("best_performer_pnl_pct", 0.0),
            worst_performer=data.get("worst_performer"),
            worst_performer_pnl_pct=data.get("worst_performer_pnl_pct", 0.0),
            divergence_pct=data.get("divergence_pct", 0.0),
        )


@dataclass
class ConcentrationAnalysis:
    """Pre-computed concentration risk analysis."""
    by_thesis: dict[str, float]  # thesis_name -> weight %
    by_sector: dict[str, float]  # sector -> weight %
    largest_position: str
    largest_position_pct: float
    warnings: list[str]
    limit_breaches: list[str]

    # Limits for reference
    max_single_position_limit: float = 15.0
    max_thesis_limit: float = 35.0
    max_sector_limit: float = 40.0

    def to_dict(self) -> dict:
        return {
            "by_thesis": self.by_thesis,
            "by_sector": self.by_sector,
            "largest_position": self.largest_position,
            "largest_position_pct": self.largest_position_pct,
            "warnings": self.warnings,
            "limit_breaches": self.limit_breaches,
            "max_single_position_limit": self.max_single_position_limit,
            "max_thesis_limit": self.max_thesis_limit,
            "max_sector_limit": self.max_sector_limit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConcentrationAnalysis":
        return cls(
            by_thesis=data["by_thesis"],
            by_sector=data["by_sector"],
            largest_position=data["largest_position"],
            largest_position_pct=data["largest_position_pct"],
            warnings=data["warnings"],
            limit_breaches=data["limit_breaches"],
            max_single_position_limit=data.get("max_single_position_limit", 15.0),
            max_thesis_limit=data.get("max_thesis_limit", 35.0),
            max_sector_limit=data.get("max_sector_limit", 40.0),
        )


@dataclass
class PeriodPerformance:
    """Pre-computed period returns."""
    today_pnl: float
    today_pnl_pct: float
    week_pnl: float
    week_pnl_pct: float
    month_pnl: float
    month_pnl_pct: float

    # Benchmark comparison
    spy_today_pct: float
    spy_week_pct: float
    spy_month_pct: float
    vs_spy_today: float  # Our return - SPY return
    vs_spy_week: float
    vs_spy_month: float

    def to_dict(self) -> dict:
        return {
            "today_pnl": self.today_pnl,
            "today_pnl_pct": self.today_pnl_pct,
            "week_pnl": self.week_pnl,
            "week_pnl_pct": self.week_pnl_pct,
            "month_pnl": self.month_pnl,
            "month_pnl_pct": self.month_pnl_pct,
            "spy_today_pct": self.spy_today_pct,
            "spy_week_pct": self.spy_week_pct,
            "spy_month_pct": self.spy_month_pct,
            "vs_spy_today": self.vs_spy_today,
            "vs_spy_week": self.vs_spy_week,
            "vs_spy_month": self.vs_spy_month,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PeriodPerformance":
        return cls(**data)


@dataclass
class SoldPositionTrack:
    """Tracking for a sold position."""
    symbol: str
    sell_date: str
    sell_price: float
    sell_quantity: int
    sell_total: float
    current_price: float
    current_value_if_held: float
    opportunity_cost: float  # Positive = missed gain, Negative = avoided loss
    opportunity_cost_pct: float
    days_since_sale: int
    thesis_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "sell_date": self.sell_date,
            "sell_price": self.sell_price,
            "sell_quantity": self.sell_quantity,
            "sell_total": self.sell_total,
            "current_price": self.current_price,
            "current_value_if_held": self.current_value_if_held,
            "opportunity_cost": self.opportunity_cost,
            "opportunity_cost_pct": self.opportunity_cost_pct,
            "days_since_sale": self.days_since_sale,
            "thesis_id": self.thesis_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SoldPositionTrack":
        return cls(**data)


@dataclass
class SoldTracking:
    """Aggregate sold position tracking."""
    sold_positions: list[SoldPositionTrack]
    total_opportunity_cost: float
    biggest_miss: Optional[str]  # Symbol with biggest missed gain
    biggest_miss_amount: float
    biggest_avoided: Optional[str]  # Symbol with biggest avoided loss
    biggest_avoided_amount: float

    def to_dict(self) -> dict:
        return {
            "sold_positions": [p.to_dict() for p in self.sold_positions],
            "total_opportunity_cost": self.total_opportunity_cost,
            "biggest_miss": self.biggest_miss,
            "biggest_miss_amount": self.biggest_miss_amount,
            "biggest_avoided": self.biggest_avoided,
            "biggest_avoided_amount": self.biggest_avoided_amount,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SoldTracking":
        positions = [SoldPositionTrack.from_dict(p) for p in data.get("sold_positions", [])]
        return cls(
            sold_positions=positions,
            total_opportunity_cost=data["total_opportunity_cost"],
            biggest_miss=data.get("biggest_miss"),
            biggest_miss_amount=data.get("biggest_miss_amount", 0.0),
            biggest_avoided=data.get("biggest_avoided"),
            biggest_avoided_amount=data.get("biggest_avoided_amount", 0.0),
        )


@dataclass
class ProfitTierStatus:
    """Profit tier tracking for a position."""
    symbol: str
    current_gain_pct: float
    tier_10_triggered: bool
    tier_15_triggered: bool
    tier_20_triggered: bool
    shares_remaining_pct: float  # What % of original position remains
    recommended_action: Optional[str] = None  # e.g., "Take 25% profit at tier 10"
    next_tier_pct: Optional[float] = None  # Next profit tier to watch

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_gain_pct": self.current_gain_pct,
            "tier_10_triggered": self.tier_10_triggered,
            "tier_15_triggered": self.tier_15_triggered,
            "tier_20_triggered": self.tier_20_triggered,
            "shares_remaining_pct": self.shares_remaining_pct,
            "recommended_action": self.recommended_action,
            "next_tier_pct": self.next_tier_pct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProfitTierStatus":
        return cls(**data)


@dataclass
class TodayOrder:
    """Single order from today."""
    time: str
    action: str  # BUY or SELL
    symbol: str
    quantity: int
    price: float
    total: float
    order_id: str

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "action": self.action,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "price": self.price,
            "total": self.total,
            "order_id": self.order_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TodayOrder":
        return cls(**data)


@dataclass
class TodayOrders:
    """Aggregate of today's orders."""
    orders: list[TodayOrder]
    total_buys: float
    total_sells: float
    net_flow: float
    order_count: int

    def to_dict(self) -> dict:
        return {
            "orders": [o.to_dict() for o in self.orders],
            "total_buys": self.total_buys,
            "total_sells": self.total_sells,
            "net_flow": self.net_flow,
            "order_count": self.order_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TodayOrders":
        orders = [TodayOrder.from_dict(o) for o in data.get("orders", [])]
        return cls(
            orders=orders,
            total_buys=data["total_buys"],
            total_sells=data["total_sells"],
            net_flow=data["net_flow"],
            order_count=data["order_count"],
        )


@dataclass
class DataValidation:
    """Data quality validation results."""
    is_valid: bool
    last_successful_update: str
    stale_components: list[str]  # Components with stale data
    missing_components: list[str]  # Components that failed to load
    warnings: list[str]

    # Component freshness (minutes since last update)
    market_age_minutes: float
    portfolio_age_minutes: float
    positions_age_minutes: float

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "last_successful_update": self.last_successful_update,
            "stale_components": self.stale_components,
            "missing_components": self.missing_components,
            "warnings": self.warnings,
            "market_age_minutes": self.market_age_minutes,
            "portfolio_age_minutes": self.portfolio_age_minutes,
            "positions_age_minutes": self.positions_age_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DataValidation":
        return cls(**data)


# ============================================================================
# NEW: News Urgency and Signpost Alerts (Added 2026-01-10)
# ============================================================================


@dataclass
class SignpostAlert:
    """Alert when a thesis signpost is triggered by news."""
    thesis_id: str
    thesis_name: str
    signpost_description: str
    triggered_at: str
    outcome: str  # bullish, bearish, neutral
    news_headline: str
    news_source: str
    recommended_action: str
    urgency: str  # high, medium, low

    def to_dict(self) -> dict:
        return {
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "signpost_description": self.signpost_description,
            "triggered_at": self.triggered_at,
            "outcome": self.outcome,
            "news_headline": self.news_headline,
            "news_source": self.news_source,
            "recommended_action": self.recommended_action,
            "urgency": self.urgency,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignpostAlert":
        return cls(**data)


@dataclass
class NewsUrgencyAlert:
    """Urgent news that may require immediate action."""
    timestamp: str
    headline: str
    source: str
    urgency: str  # critical, high, medium
    affected_symbols: list[str]
    affected_theses: list[str]
    category: str  # earnings, acquisition, fda, contract, policy, other
    sentiment: str  # bullish, bearish, neutral
    recommended_action: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "headline": self.headline,
            "source": self.source,
            "urgency": self.urgency,
            "affected_symbols": self.affected_symbols,
            "affected_theses": self.affected_theses,
            "category": self.category,
            "sentiment": self.sentiment,
            "recommended_action": self.recommended_action,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NewsUrgencyAlert":
        return cls(**data)


# ============================================================================
# NEW: Conviction Decay (Added 2026-01-10)
# ============================================================================


@dataclass
class ConvictionDecayResult:
    """Result of conviction decay calculation for a thesis."""
    thesis_id: str
    thesis_name: str
    original_conviction: float
    current_conviction: float
    decay_applied: float
    decay_reasons: list[str]
    days_since_last_signpost: int
    days_since_creation: int
    status: str  # healthy, warning, critical, auto_paused

    def to_dict(self) -> dict:
        return {
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "original_conviction": self.original_conviction,
            "current_conviction": self.current_conviction,
            "decay_applied": self.decay_applied,
            "decay_reasons": self.decay_reasons,
            "days_since_last_signpost": self.days_since_last_signpost,
            "days_since_creation": self.days_since_creation,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConvictionDecayResult":
        return cls(**data)


# ============================================================================
# NEW: Historical Portfolio Tracking (Added 2026-01-10)
# ============================================================================


@dataclass
class PortfolioHistorySnapshot:
    """Single point in portfolio history."""
    date: str
    equity: float
    cash: float
    positions_value: float
    day_pnl: float
    day_pnl_pct: float
    spy_close: float
    spy_pct: float

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "equity": self.equity,
            "cash": self.cash,
            "positions_value": self.positions_value,
            "day_pnl": self.day_pnl,
            "day_pnl_pct": self.day_pnl_pct,
            "spy_close": self.spy_close,
            "spy_pct": self.spy_pct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PortfolioHistorySnapshot":
        return cls(**data)


@dataclass
class PortfolioHistory:
    """Historical portfolio data for accurate period returns."""
    snapshots: list[PortfolioHistorySnapshot]

    # Computed period returns
    week_start_equity: float
    week_pnl: float
    week_pnl_pct: float
    month_start_equity: float
    month_pnl: float
    month_pnl_pct: float

    # vs SPY
    week_spy_pct: float
    month_spy_pct: float
    vs_spy_week: float
    vs_spy_month: float

    def to_dict(self) -> dict:
        return {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "week_start_equity": self.week_start_equity,
            "week_pnl": self.week_pnl,
            "week_pnl_pct": self.week_pnl_pct,
            "month_start_equity": self.month_start_equity,
            "month_pnl": self.month_pnl,
            "month_pnl_pct": self.month_pnl_pct,
            "week_spy_pct": self.week_spy_pct,
            "month_spy_pct": self.month_spy_pct,
            "vs_spy_week": self.vs_spy_week,
            "vs_spy_month": self.vs_spy_month,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PortfolioHistory":
        snapshots = [PortfolioHistorySnapshot.from_dict(s) for s in data.get("snapshots", [])]
        return cls(
            snapshots=snapshots,
            week_start_equity=data.get("week_start_equity", 0.0),
            week_pnl=data.get("week_pnl", 0.0),
            week_pnl_pct=data.get("week_pnl_pct", 0.0),
            month_start_equity=data.get("month_start_equity", 0.0),
            month_pnl=data.get("month_pnl", 0.0),
            month_pnl_pct=data.get("month_pnl_pct", 0.0),
            week_spy_pct=data.get("week_spy_pct", 0.0),
            month_spy_pct=data.get("month_spy_pct", 0.0),
            vs_spy_week=data.get("vs_spy_week", 0.0),
            vs_spy_month=data.get("vs_spy_month", 0.0),
        )


@dataclass
class UnifiedState:
    """
    The ONE file to read for everything.

    This is the central state object that aggregates all data sources.
    Written to ~/quant_results/live/state.json by the LiveDaemon.

    ENHANCED: Now includes pre-computed thesis performance, concentration
    analysis, and human-readable summary to eliminate the need for Claude
    to generate Python code for standard queries.
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

    # NEW: Pre-computed data for efficient queries
    thesis_performance: dict[str, ThesisPerformance] = field(default_factory=dict)
    concentration: Optional[ConcentrationAnalysis] = None
    period_performance: Optional[PeriodPerformance] = None
    sold_tracking: Optional[SoldTracking] = None
    profit_tiers: dict[str, ProfitTierStatus] = field(default_factory=dict)
    today_orders: Optional[TodayOrders] = None
    validation: Optional[DataValidation] = None

    # Human-readable summary text (THE key efficiency gain)
    summary_text: str = ""

    # NEW: P2 features (Added 2026-01-10)
    signpost_alerts: list[SignpostAlert] = field(default_factory=list)
    news_urgency_alerts: list[NewsUrgencyAlert] = field(default_factory=list)
    conviction_decay: list[ConvictionDecayResult] = field(default_factory=list)
    portfolio_history: Optional[PortfolioHistory] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON."""
        result = {
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
            # NEW: Pre-computed data
            "thesis_performance": {k: v.to_dict() for k, v in self.thesis_performance.items()},
            "concentration": self.concentration.to_dict() if self.concentration else None,
            "period_performance": self.period_performance.to_dict() if self.period_performance else None,
            "sold_tracking": self.sold_tracking.to_dict() if self.sold_tracking else None,
            "profit_tiers": {k: v.to_dict() for k, v in self.profit_tiers.items()},
            "today_orders": self.today_orders.to_dict() if self.today_orders else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "summary_text": self.summary_text,
            # NEW: P2 features
            "signpost_alerts": [a.to_dict() for a in self.signpost_alerts],
            "news_urgency_alerts": [a.to_dict() for a in self.news_urgency_alerts],
            "conviction_decay": [d.to_dict() for d in self.conviction_decay],
            "portfolio_history": self.portfolio_history.to_dict() if self.portfolio_history else None,
        }
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedState":
        """Deserialize from dictionary."""
        # Parse new optional fields
        thesis_perf = {}
        if data.get("thesis_performance"):
            thesis_perf = {k: ThesisPerformance.from_dict(v) for k, v in data["thesis_performance"].items()}

        concentration = None
        if data.get("concentration"):
            concentration = ConcentrationAnalysis.from_dict(data["concentration"])

        period_perf = None
        if data.get("period_performance"):
            period_perf = PeriodPerformance.from_dict(data["period_performance"])

        sold_tracking = None
        if data.get("sold_tracking"):
            sold_tracking = SoldTracking.from_dict(data["sold_tracking"])

        profit_tiers = {}
        if data.get("profit_tiers"):
            profit_tiers = {k: ProfitTierStatus.from_dict(v) for k, v in data["profit_tiers"].items()}

        today_orders = None
        if data.get("today_orders"):
            today_orders = TodayOrders.from_dict(data["today_orders"])

        validation = None
        if data.get("validation"):
            validation = DataValidation.from_dict(data["validation"])

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
            # NEW: Pre-computed data
            thesis_performance=thesis_perf,
            concentration=concentration,
            period_performance=period_perf,
            sold_tracking=sold_tracking,
            profit_tiers=profit_tiers,
            today_orders=today_orders,
            validation=validation,
            summary_text=data.get("summary_text", ""),
            # NEW: P2 features
            signpost_alerts=[SignpostAlert.from_dict(a) for a in data.get("signpost_alerts", [])],
            news_urgency_alerts=[NewsUrgencyAlert.from_dict(a) for a in data.get("news_urgency_alerts", [])],
            conviction_decay=[ConvictionDecayResult.from_dict(d) for d in data.get("conviction_decay", [])],
            portfolio_history=PortfolioHistory.from_dict(data["portfolio_history"]) if data.get("portfolio_history") else None,
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
            path = paths.live_state

        if not path.exists():
            logger.warning(f"State file not found: {path}")
            return None

        try:
            with open(path, "r") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            logger.error(f"Malformed JSON in state file {path}: {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Invalid data structure in state file: {e}")
            return None
        except IOError as e:
            logger.error(f"IO error reading state file: {e}")
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
        ]

        # NEW: Enhanced sentiment indicators (if available)
        if self.sentiment.vix_regime:
            lines.append(f"- VIX Structure: {self.sentiment.vix_regime}" +
                        (f" (slope: {self.sentiment.vix_slope:.2f})" if self.sentiment.vix_slope else ""))
        if self.sentiment.aaii_bullish is not None:
            lines.append(f"- AAII: {self.sentiment.aaii_bullish:.1f}% bull / {self.sentiment.aaii_bearish:.1f}% bear" +
                        (f" ({self.sentiment.aaii_signal})" if self.sentiment.aaii_signal else ""))
        if self.sentiment.fed_prob_cut is not None or self.sentiment.fed_prob_hike is not None:
            fed_parts = []
            if self.sentiment.fed_prob_cut:
                fed_parts.append(f"cut: {self.sentiment.fed_prob_cut:.0%}")
            if self.sentiment.fed_prob_hike:
                fed_parts.append(f"hike: {self.sentiment.fed_prob_hike:.0%}")
            if fed_parts:
                lines.append(f"- Fed Expectations: {', '.join(fed_parts)}" +
                            (f" ({self.sentiment.fed_path_signal})" if self.sentiment.fed_path_signal else ""))

        lines.extend([
            "",
            "## Portfolio",
            f"- Equity: ${self.portfolio.equity:,.0f}",
            f"- Day P&L: ${self.portfolio.day_pnl:+,.0f} ({self.portfolio.day_pnl_pct:+.2f}%)",
            f"- Exposure: {self.portfolio.market_exposure_pct:.0f}%",
            f"- Day Trades Remaining: {self.portfolio.day_trades_remaining}",
            "",
        ])

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
