#!/usr/bin/env python3
"""Automated Trade Journal - Track all trades with context and learnings.

Captures:
1. Trade details (entry/exit, size, P&L)
2. Market context at time of trade
3. Thesis/signal that triggered trade
4. Emotional state indicators
5. Post-trade analysis and learnings
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


class TradeType(Enum):
    LONG = "long"
    SHORT = "short"


class TradeStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"


class TradeOutcome(Enum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    OPEN = "open"


@dataclass
class MarketContext:
    """Market conditions at time of trade."""
    spy_price: float
    vix_level: float
    market_regime: str  # bull, bear, sideways
    sector_strength: Optional[str] = None
    recent_catalyst: Optional[str] = None

    def to_dict(self):
        return {
            "spy_price": self.spy_price,
            "vix_level": self.vix_level,
            "market_regime": self.market_regime,
            "sector_strength": self.sector_strength,
            "recent_catalyst": self.recent_catalyst,
        }


@dataclass
class TradeEntry:
    """A single trade entry in the journal."""
    # Identity
    trade_id: str
    symbol: str
    trade_type: TradeType
    status: TradeStatus

    # Entry
    entry_date: datetime
    entry_price: float
    entry_quantity: int
    entry_value: float

    # Exit (if closed)
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_quantity: Optional[int] = None
    exit_value: Optional[float] = None

    # P&L
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0
    unrealized_pnl: float = 0.0
    max_gain: float = 0.0  # Peak unrealized gain
    max_drawdown: float = 0.0  # Peak unrealized loss

    # Context
    thesis_id: Optional[str] = None
    thesis_name: Optional[str] = None
    signal_source: Optional[str] = None
    entry_reasoning: str = ""
    exit_reasoning: str = ""

    # Market context
    market_context: Optional[MarketContext] = None

    # Emotional indicators
    confidence_at_entry: float = 0.5  # 0-1
    fomo_indicator: bool = False
    revenge_trade: bool = False

    # Post-trade analysis
    outcome: TradeOutcome = TradeOutcome.OPEN
    lessons_learned: list[str] = field(default_factory=list)
    would_trade_again: Optional[bool] = None
    tags: list[str] = field(default_factory=list)

    # Timing
    hold_duration_days: Optional[int] = None

    def to_dict(self):
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "trade_type": self.trade_type.value,
            "status": self.status.value,
            "entry_date": self.entry_date.isoformat(),
            "entry_price": self.entry_price,
            "entry_quantity": self.entry_quantity,
            "entry_value": self.entry_value,
            "exit_date": self.exit_date.isoformat() if self.exit_date else None,
            "exit_price": self.exit_price,
            "exit_quantity": self.exit_quantity,
            "exit_value": self.exit_value,
            "realized_pnl": self.realized_pnl,
            "realized_pnl_pct": self.realized_pnl_pct,
            "unrealized_pnl": self.unrealized_pnl,
            "max_gain": self.max_gain,
            "max_drawdown": self.max_drawdown,
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "signal_source": self.signal_source,
            "entry_reasoning": self.entry_reasoning,
            "exit_reasoning": self.exit_reasoning,
            "market_context": self.market_context.to_dict() if self.market_context else None,
            "confidence_at_entry": self.confidence_at_entry,
            "fomo_indicator": self.fomo_indicator,
            "revenge_trade": self.revenge_trade,
            "outcome": self.outcome.value,
            "lessons_learned": self.lessons_learned,
            "would_trade_again": self.would_trade_again,
            "tags": self.tags,
            "hold_duration_days": self.hold_duration_days,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradeEntry":
        """Create TradeEntry from dict."""
        market_ctx = None
        if data.get("market_context"):
            market_ctx = MarketContext(**data["market_context"])

        return cls(
            trade_id=data["trade_id"],
            symbol=data["symbol"],
            trade_type=TradeType(data["trade_type"]),
            status=TradeStatus(data["status"]),
            entry_date=datetime.fromisoformat(data["entry_date"]),
            entry_price=data["entry_price"],
            entry_quantity=data["entry_quantity"],
            entry_value=data["entry_value"],
            exit_date=datetime.fromisoformat(data["exit_date"]) if data.get("exit_date") else None,
            exit_price=data.get("exit_price"),
            exit_quantity=data.get("exit_quantity"),
            exit_value=data.get("exit_value"),
            realized_pnl=data.get("realized_pnl", 0),
            realized_pnl_pct=data.get("realized_pnl_pct", 0),
            unrealized_pnl=data.get("unrealized_pnl", 0),
            max_gain=data.get("max_gain", 0),
            max_drawdown=data.get("max_drawdown", 0),
            thesis_id=data.get("thesis_id"),
            thesis_name=data.get("thesis_name"),
            signal_source=data.get("signal_source"),
            entry_reasoning=data.get("entry_reasoning", ""),
            exit_reasoning=data.get("exit_reasoning", ""),
            market_context=market_ctx,
            confidence_at_entry=data.get("confidence_at_entry", 0.5),
            fomo_indicator=data.get("fomo_indicator", False),
            revenge_trade=data.get("revenge_trade", False),
            outcome=TradeOutcome(data.get("outcome", "open")),
            lessons_learned=data.get("lessons_learned", []),
            would_trade_again=data.get("would_trade_again"),
            tags=data.get("tags", []),
            hold_duration_days=data.get("hold_duration_days"),
        )


class TradeJournal:
    """Automated trade journal for tracking and learning."""

    def __init__(self, journal_dir: Optional[Path] = None):
        self.journal_dir = journal_dir or Path.home() / "quant_results" / "journal"
        self.journal_dir.mkdir(parents=True, exist_ok=True)

        self.journal_file = self.journal_dir / "trades.json"
        self.stats_file = self.journal_dir / "statistics.json"

        # Load existing trades
        self.trades: dict[str, TradeEntry] = {}
        self._load_trades()

    def _load_trades(self):
        """Load trades from journal file."""
        if not self.journal_file.exists():
            return

        with open(self.journal_file) as f:
            data = json.load(f)

        for trade_data in data.get("trades", []):
            trade = TradeEntry.from_dict(trade_data)
            self.trades[trade.trade_id] = trade

    def _save_trades(self):
        """Save trades to journal file."""
        data = {
            "last_updated": datetime.now().isoformat(),
            "trade_count": len(self.trades),
            "trades": [t.to_dict() for t in self.trades.values()],
        }

        with open(self.journal_file, "w") as f:
            json.dump(data, f, indent=2)

    async def get_market_context(self) -> MarketContext:
        """Get current market context."""
        import yfinance as yf

        try:
            spy = yf.Ticker("SPY")
            vix = yf.Ticker("^VIX")

            spy_price = spy.info.get("regularMarketPrice", 0)
            vix_level = vix.info.get("regularMarketPrice", 20)

            # Determine regime
            spy_hist = spy.history(period="20d")
            if len(spy_hist) >= 20:
                sma20 = spy_hist["Close"].mean()
                if spy_price > sma20 * 1.02:
                    regime = "bull"
                elif spy_price < sma20 * 0.98:
                    regime = "bear"
                else:
                    regime = "sideways"
            else:
                regime = "unknown"

            return MarketContext(
                spy_price=spy_price,
                vix_level=vix_level,
                market_regime=regime,
            )

        except Exception as e:
            logger.warning(f"Could not get market context: {e}")
            return MarketContext(spy_price=0, vix_level=20, market_regime="unknown")

    async def record_entry(
        self,
        symbol: str,
        price: float,
        quantity: int,
        trade_type: TradeType = TradeType.LONG,
        thesis_id: Optional[str] = None,
        thesis_name: Optional[str] = None,
        signal_source: Optional[str] = None,
        reasoning: str = "",
        confidence: float = 0.5,
        fomo: bool = False,
        revenge: bool = False,
        tags: list[str] = None,
    ) -> TradeEntry:
        """Record a new trade entry."""
        trade_id = str(uuid.uuid4())[:8]

        # Get market context
        context = await self.get_market_context()

        trade = TradeEntry(
            trade_id=trade_id,
            symbol=symbol,
            trade_type=trade_type,
            status=TradeStatus.OPEN,
            entry_date=datetime.now(),
            entry_price=price,
            entry_quantity=quantity,
            entry_value=price * quantity,
            thesis_id=thesis_id,
            thesis_name=thesis_name,
            signal_source=signal_source,
            entry_reasoning=reasoning,
            market_context=context,
            confidence_at_entry=confidence,
            fomo_indicator=fomo,
            revenge_trade=revenge,
            tags=tags or [],
        )

        self.trades[trade_id] = trade
        self._save_trades()

        logger.info(f"Recorded trade entry: {trade_id} - {trade_type.value} {quantity} {symbol} @ ${price:.2f}")

        return trade

    def record_exit(
        self,
        trade_id: str,
        price: float,
        quantity: Optional[int] = None,
        reasoning: str = "",
        lessons: list[str] = None,
        would_trade_again: Optional[bool] = None,
    ) -> TradeEntry:
        """Record a trade exit."""
        if trade_id not in self.trades:
            raise ValueError(f"Trade {trade_id} not found")

        trade = self.trades[trade_id]

        exit_qty = quantity or trade.entry_quantity
        exit_value = price * exit_qty

        # Calculate P&L
        if trade.trade_type == TradeType.LONG:
            pnl = exit_value - (trade.entry_price * exit_qty)
        else:
            pnl = (trade.entry_price * exit_qty) - exit_value

        pnl_pct = (pnl / (trade.entry_price * exit_qty)) * 100

        # Update trade
        trade.exit_date = datetime.now()
        trade.exit_price = price
        trade.exit_quantity = exit_qty
        trade.exit_value = exit_value
        trade.realized_pnl = pnl
        trade.realized_pnl_pct = pnl_pct
        trade.exit_reasoning = reasoning

        # Determine status
        if exit_qty >= trade.entry_quantity:
            trade.status = TradeStatus.CLOSED
        else:
            trade.status = TradeStatus.PARTIAL

        # Determine outcome
        if pnl > trade.entry_value * 0.005:  # > 0.5% gain
            trade.outcome = TradeOutcome.WIN
        elif pnl < -trade.entry_value * 0.005:  # > 0.5% loss
            trade.outcome = TradeOutcome.LOSS
        else:
            trade.outcome = TradeOutcome.BREAKEVEN

        # Calculate hold duration
        trade.hold_duration_days = (trade.exit_date - trade.entry_date).days

        # Add lessons
        if lessons:
            trade.lessons_learned.extend(lessons)

        trade.would_trade_again = would_trade_again

        self._save_trades()

        logger.info(
            f"Recorded trade exit: {trade_id} - {trade.symbol} "
            f"P&L: ${pnl:.2f} ({pnl_pct:+.1f}%)"
        )

        return trade

    def update_unrealized(self, trade_id: str, current_price: float):
        """Update unrealized P&L for an open trade."""
        if trade_id not in self.trades:
            return

        trade = self.trades[trade_id]
        if trade.status == TradeStatus.CLOSED:
            return

        current_value = current_price * trade.entry_quantity

        if trade.trade_type == TradeType.LONG:
            unrealized = current_value - trade.entry_value
        else:
            unrealized = trade.entry_value - current_value

        trade.unrealized_pnl = unrealized

        # Track max gain/drawdown
        if unrealized > trade.max_gain:
            trade.max_gain = unrealized
        if unrealized < -trade.max_drawdown:
            trade.max_drawdown = abs(unrealized)

        self._save_trades()

    def add_lesson(self, trade_id: str, lesson: str):
        """Add a lesson learned to a trade."""
        if trade_id in self.trades:
            self.trades[trade_id].lessons_learned.append(lesson)
            self._save_trades()

    def add_tag(self, trade_id: str, tag: str):
        """Add a tag to a trade."""
        if trade_id in self.trades:
            if tag not in self.trades[trade_id].tags:
                self.trades[trade_id].tags.append(tag)
                self._save_trades()

    def get_open_trades(self) -> list[TradeEntry]:
        """Get all open trades."""
        return [t for t in self.trades.values() if t.status == TradeStatus.OPEN]

    def get_trades_by_symbol(self, symbol: str) -> list[TradeEntry]:
        """Get all trades for a symbol."""
        return [t for t in self.trades.values() if t.symbol == symbol]

    def get_trades_by_thesis(self, thesis_id: str) -> list[TradeEntry]:
        """Get all trades for a thesis."""
        return [t for t in self.trades.values() if t.thesis_id == thesis_id]

    def get_recent_trades(self, days: int = 30) -> list[TradeEntry]:
        """Get recent trades."""
        cutoff = datetime.now() - timedelta(days=days)
        return [t for t in self.trades.values() if t.entry_date >= cutoff]

    def calculate_statistics(self) -> dict:
        """Calculate trading statistics."""
        closed = [t for t in self.trades.values() if t.status == TradeStatus.CLOSED]

        if not closed:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "profit_factor": 0,
                "total_pnl": 0,
            }

        wins = [t for t in closed if t.outcome == TradeOutcome.WIN]
        losses = [t for t in closed if t.outcome == TradeOutcome.LOSS]

        total_pnl = sum(t.realized_pnl for t in closed)
        win_pnl = sum(t.realized_pnl for t in wins)
        loss_pnl = abs(sum(t.realized_pnl for t in losses))

        avg_win = win_pnl / len(wins) if wins else 0
        avg_loss = loss_pnl / len(losses) if losses else 0

        # By thesis
        thesis_stats = {}
        for trade in closed:
            thesis = trade.thesis_name or "No Thesis"
            if thesis not in thesis_stats:
                thesis_stats[thesis] = {"trades": 0, "pnl": 0, "wins": 0}
            thesis_stats[thesis]["trades"] += 1
            thesis_stats[thesis]["pnl"] += trade.realized_pnl
            if trade.outcome == TradeOutcome.WIN:
                thesis_stats[thesis]["wins"] += 1

        # By tag
        tag_stats = {}
        for trade in closed:
            for tag in trade.tags:
                if tag not in tag_stats:
                    tag_stats[tag] = {"trades": 0, "pnl": 0, "wins": 0}
                tag_stats[tag]["trades"] += 1
                tag_stats[tag]["pnl"] += trade.realized_pnl
                if trade.outcome == TradeOutcome.WIN:
                    tag_stats[tag]["wins"] += 1

        # Hold duration analysis
        hold_durations = [t.hold_duration_days for t in closed if t.hold_duration_days]
        avg_hold = sum(hold_durations) / len(hold_durations) if hold_durations else 0

        # FOMO/Revenge analysis
        fomo_trades = [t for t in closed if t.fomo_indicator]
        revenge_trades = [t for t in closed if t.revenge_trade]

        fomo_pnl = sum(t.realized_pnl for t in fomo_trades)
        revenge_pnl = sum(t.realized_pnl for t in revenge_trades)

        stats = {
            "total_trades": len(closed),
            "win_rate": len(wins) / len(closed) if closed else 0,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": win_pnl / loss_pnl if loss_pnl > 0 else float("inf"),
            "total_pnl": total_pnl,
            "avg_pnl_per_trade": total_pnl / len(closed),
            "avg_hold_duration_days": avg_hold,
            "thesis_breakdown": thesis_stats,
            "tag_breakdown": tag_stats,
            "fomo_trades": {"count": len(fomo_trades), "pnl": fomo_pnl},
            "revenge_trades": {"count": len(revenge_trades), "pnl": revenge_pnl},
            "lessons_count": sum(len(t.lessons_learned) for t in closed),
        }

        # Save stats
        with open(self.stats_file, "w") as f:
            json.dump(stats, f, indent=2, default=str)

        return stats

    def generate_report(self, days: int = 30) -> str:
        """Generate human-readable journal report."""
        recent = self.get_recent_trades(days)
        stats = self.calculate_statistics()

        lines = [
            "Trade Journal Report",
            "=" * 50,
            f"Period: Last {days} days",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "Overall Statistics",
            "-" * 50,
            f"Total Trades: {stats['total_trades']}",
            f"Win Rate: {stats['win_rate']:.1%}",
            f"Profit Factor: {stats['profit_factor']:.2f}",
            f"Total P&L: ${stats['total_pnl']:,.2f}",
            f"Avg P&L per Trade: ${stats.get('avg_pnl_per_trade', 0):,.2f}",
            f"Avg Hold Duration: {stats.get('avg_hold_duration_days', 0):.1f} days",
            "",
        ]

        # Thesis breakdown
        if stats.get("thesis_breakdown"):
            lines.extend(["Performance by Thesis", "-" * 50])
            for thesis, data in sorted(
                stats["thesis_breakdown"].items(),
                key=lambda x: x[1]["pnl"],
                reverse=True
            ):
                wr = data["wins"] / data["trades"] if data["trades"] else 0
                lines.append(f"  {thesis}: ${data['pnl']:,.2f} ({data['trades']} trades, {wr:.0%} WR)")
            lines.append("")

        # FOMO/Revenge analysis
        if stats.get("fomo_trades", {}).get("count", 0) > 0:
            fomo = stats["fomo_trades"]
            lines.append(f"FOMO Trades: {fomo['count']} (P&L: ${fomo['pnl']:,.2f})")

        if stats.get("revenge_trades", {}).get("count", 0) > 0:
            revenge = stats["revenge_trades"]
            lines.append(f"Revenge Trades: {revenge['count']} (P&L: ${revenge['pnl']:,.2f})")

        # Recent trades
        if recent:
            lines.extend(["", "Recent Trades", "-" * 50])
            for trade in recent[:10]:
                outcome_emoji = {
                    TradeOutcome.WIN: "✅",
                    TradeOutcome.LOSS: "❌",
                    TradeOutcome.BREAKEVEN: "➡️",
                    TradeOutcome.OPEN: "⏳",
                }.get(trade.outcome, "❓")

                pnl = trade.realized_pnl if trade.status == TradeStatus.CLOSED else trade.unrealized_pnl

                lines.append(
                    f"{outcome_emoji} {trade.entry_date.strftime('%m/%d')} "
                    f"{trade.symbol}: ${pnl:+,.2f}"
                )

        # Lessons learned
        all_lessons = []
        for trade in self.trades.values():
            all_lessons.extend(trade.lessons_learned)

        if all_lessons:
            lines.extend(["", "Recent Lessons", "-" * 50])
            for lesson in all_lessons[-5:]:
                lines.append(f"  - {lesson}")

        return "\n".join(lines)

    def get_trade_by_symbol_and_date(self, symbol: str, date: datetime) -> Optional[TradeEntry]:
        """Find a trade by symbol and approximate date."""
        for trade in self.trades.values():
            if trade.symbol == symbol:
                if abs((trade.entry_date - date).days) <= 1:
                    return trade
        return None


async def main():
    """Test trade journal."""
    journal = TradeJournal()

    # Record a test trade
    trade = await journal.record_entry(
        symbol="AAPL",
        price=185.50,
        quantity=10,
        thesis_name="Tech Momentum",
        signal_source="breakout_scanner",
        reasoning="Bullish breakout above resistance with volume confirmation",
        confidence=0.75,
        tags=["breakout", "tech"],
    )

    print(f"Recorded trade: {trade.trade_id}")

    # Update unrealized
    journal.update_unrealized(trade.trade_id, 188.00)

    # Close it
    journal.record_exit(
        trade_id=trade.trade_id,
        price=188.50,
        reasoning="Hit 2% target",
        lessons=["Patience paid off", "Let winners run"],
        would_trade_again=True,
    )

    # Generate report
    print("\n" + journal.generate_report())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
