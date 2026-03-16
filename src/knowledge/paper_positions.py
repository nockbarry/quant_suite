"""Paper Position Tracking for Thesis Monitoring.

Track virtual/paper positions to monitor thesis performance without actual investment.
Useful for:
- Tracking "what if" scenarios
- Monitoring theses before committing capital
- Comparing paper vs actual performance

Paper positions are stored in ~/quant_results/paper_positions.json
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional, Any
import json
import logging
import uuid

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    """A virtual/paper position for tracking purposes."""

    id: str
    symbol: str
    quantity: float
    entry_price: float
    entry_date: datetime
    thesis_id: Optional[str] = None
    thesis_name: Optional[str] = None
    notes: str = ""

    # Calculated at runtime
    current_price: Optional[float] = None
    last_updated: Optional[datetime] = None

    @property
    def entry_value(self) -> float:
        """Total value at entry."""
        return self.quantity * self.entry_price

    @property
    def current_value(self) -> Optional[float]:
        """Current market value."""
        if self.current_price is None:
            return None
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> Optional[float]:
        """Unrealized P&L in dollars."""
        if self.current_price is None:
            return None
        return self.current_value - self.entry_value

    @property
    def unrealized_pnl_pct(self) -> Optional[float]:
        """Unrealized P&L as percentage."""
        if self.current_price is None or self.entry_price == 0:
            return None
        return ((self.current_price - self.entry_price) / self.entry_price) * 100

    @property
    def days_held(self) -> int:
        """Number of days since entry."""
        return (datetime.now() - self.entry_date).days

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "entry_date": self.entry_date.isoformat(),
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PaperPosition":
        return cls(
            id=data["id"],
            symbol=data["symbol"],
            quantity=data["quantity"],
            entry_price=data["entry_price"],
            entry_date=datetime.fromisoformat(data["entry_date"]),
            thesis_id=data.get("thesis_id"),
            thesis_name=data.get("thesis_name"),
            notes=data.get("notes", ""),
        )


@dataclass
class PaperPositionSummary:
    """Summary of paper positions by thesis."""

    thesis_id: Optional[str]
    thesis_name: Optional[str]
    positions: list[PaperPosition]
    total_entry_value: float
    total_current_value: Optional[float]
    total_pnl: Optional[float]
    total_pnl_pct: Optional[float]


class PaperPositionTracker:
    """
    Manages paper/virtual positions for thesis tracking.

    Usage:
        tracker = PaperPositionTracker()

        # Add a paper position
        tracker.add_position(
            symbol="IWM",
            quantity=50,
            entry_price=230.50,
            thesis_id="small_cap_123",
            thesis_name="Small Cap Renaissance"
        )

        # Get positions with current prices
        positions = await tracker.get_positions_with_prices()

        # Get summary by thesis
        summary = await tracker.get_thesis_summary("small_cap_123")
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize tracker.

        Args:
            storage_path: Path to JSON file for persistence.
                         Defaults to ~/quant_results/paper_positions.json
        """
        if storage_path is None:
            storage_path = paths.base / "paper_positions.json"

        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._positions: dict[str, PaperPosition] = {}
        self._load()

    def add_position(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        thesis_id: Optional[str] = None,
        thesis_name: Optional[str] = None,
        notes: str = "",
        entry_date: Optional[datetime] = None,
    ) -> PaperPosition:
        """
        Add a new paper position.

        Args:
            symbol: Stock/ETF symbol
            quantity: Number of shares (virtual)
            entry_price: Price at "entry"
            thesis_id: ID of linked thesis
            thesis_name: Name of linked thesis
            notes: Optional notes
            entry_date: Entry date (defaults to now)

        Returns:
            Created PaperPosition
        """
        position_id = str(uuid.uuid4())[:8]

        position = PaperPosition(
            id=position_id,
            symbol=symbol.upper(),
            quantity=quantity,
            entry_price=entry_price,
            entry_date=entry_date or datetime.now(),
            thesis_id=thesis_id,
            thesis_name=thesis_name,
            notes=notes,
        )

        self._positions[position_id] = position
        self._save()

        logger.info(
            f"Added paper position: {quantity} {symbol} @ ${entry_price:.2f} "
            f"(thesis: {thesis_name or 'None'})"
        )

        return position

    def add_position_by_value(
        self,
        symbol: str,
        target_value: float,
        entry_price: float,
        thesis_id: Optional[str] = None,
        thesis_name: Optional[str] = None,
        notes: str = "",
        entry_date: Optional[datetime] = None,
    ) -> PaperPosition:
        """
        Add a paper position by target dollar value.

        Args:
            symbol: Stock/ETF symbol
            target_value: Dollar amount to "invest"
            entry_price: Price at "entry"
            thesis_id: ID of linked thesis
            thesis_name: Name of linked thesis
            notes: Optional notes
            entry_date: Entry date (defaults to now)

        Returns:
            Created PaperPosition
        """
        quantity = int(target_value / entry_price)
        return self.add_position(
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            thesis_id=thesis_id,
            thesis_name=thesis_name,
            notes=notes,
            entry_date=entry_date,
        )

    def remove_position(self, position_id: str) -> bool:
        """Remove a paper position."""
        if position_id in self._positions:
            position = self._positions.pop(position_id)
            self._save()
            logger.info(f"Removed paper position: {position.symbol}")
            return True
        return False

    def get_position(self, position_id: str) -> Optional[PaperPosition]:
        """Get a specific position by ID."""
        return self._positions.get(position_id)

    def get_positions(self) -> list[PaperPosition]:
        """Get all paper positions."""
        return list(self._positions.values())

    def get_positions_for_thesis(self, thesis_id: str) -> list[PaperPosition]:
        """Get all paper positions linked to a thesis."""
        return [p for p in self._positions.values() if p.thesis_id == thesis_id]

    def get_positions_for_symbol(self, symbol: str) -> list[PaperPosition]:
        """Get all paper positions for a symbol."""
        symbol = symbol.upper()
        return [p for p in self._positions.values() if p.symbol == symbol]

    async def update_prices(self, broker=None) -> None:
        """
        Update current prices for all positions.

        Args:
            broker: Optional broker instance for price fetching.
                   If not provided, will create one.
        """
        if not self._positions:
            return

        # Get unique symbols
        symbols = list(set(p.symbol for p in self._positions.values()))

        # Fetch prices
        if broker is None:
            try:
                import yaml
                from src.execution.broker.alpaca import AlpacaBroker

                creds_path = Path.home() / "projects" / "quant_suite" / "config" / "credentials.yaml"
                with open(creds_path, 'r') as f:
                    creds = yaml.safe_load(f)

                alpaca_creds = creds.get('alpaca', {})
                broker = AlpacaBroker(
                    api_key=alpaca_creds.get('api_key'),
                    secret_key=alpaca_creds.get('secret_key'),
                    paper=True
                )
                await broker.connect()
                own_broker = True
            except Exception as e:
                logger.error(f"Could not create broker for price updates: {e}")
                return
        else:
            own_broker = False

        try:
            quotes = await broker.get_quotes(symbols)
            now = datetime.now()

            for position in self._positions.values():
                if position.symbol in quotes:
                    quote = quotes[position.symbol]
                    position.current_price = float(quote.last)
                    position.last_updated = now
        finally:
            if own_broker:
                await broker.disconnect()

    async def get_positions_with_prices(self, broker=None) -> list[PaperPosition]:
        """Get all positions with updated prices."""
        await self.update_prices(broker)
        return self.get_positions()

    async def get_thesis_summary(
        self,
        thesis_id: str,
        broker=None
    ) -> Optional[PaperPositionSummary]:
        """Get summary of paper positions for a thesis."""
        positions = self.get_positions_for_thesis(thesis_id)
        if not positions:
            return None

        # Update prices
        await self.update_prices(broker)

        # Recalculate after price update
        positions = self.get_positions_for_thesis(thesis_id)

        total_entry = sum(p.entry_value for p in positions)

        if all(p.current_price is not None for p in positions):
            total_current = sum(p.current_value for p in positions)
            total_pnl = total_current - total_entry
            total_pnl_pct = (total_pnl / total_entry * 100) if total_entry > 0 else 0
        else:
            total_current = None
            total_pnl = None
            total_pnl_pct = None

        return PaperPositionSummary(
            thesis_id=thesis_id,
            thesis_name=positions[0].thesis_name if positions else None,
            positions=positions,
            total_entry_value=total_entry,
            total_current_value=total_current,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
        )

    async def get_all_summaries(self, broker=None) -> list[PaperPositionSummary]:
        """Get summaries for all theses with paper positions."""
        await self.update_prices(broker)

        # Group by thesis
        thesis_ids = set(p.thesis_id for p in self._positions.values())

        summaries = []
        for thesis_id in thesis_ids:
            positions = [p for p in self._positions.values() if p.thesis_id == thesis_id]

            total_entry = sum(p.entry_value for p in positions)

            if all(p.current_price is not None for p in positions):
                total_current = sum(p.current_value for p in positions)
                total_pnl = total_current - total_entry
                total_pnl_pct = (total_pnl / total_entry * 100) if total_entry > 0 else 0
            else:
                total_current = None
                total_pnl = None
                total_pnl_pct = None

            summaries.append(PaperPositionSummary(
                thesis_id=thesis_id,
                thesis_name=positions[0].thesis_name if positions else None,
                positions=positions,
                total_entry_value=total_entry,
                total_current_value=total_current,
                total_pnl=total_pnl,
                total_pnl_pct=total_pnl_pct,
            ))

        return summaries

    def clear_all(self) -> None:
        """Remove all paper positions."""
        self._positions.clear()
        self._save()
        logger.info("Cleared all paper positions")

    def _save(self) -> None:
        """Save positions to file."""
        data = {
            "updated_at": datetime.now().isoformat(),
            "positions": [p.to_dict() for p in self._positions.values()]
        }
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Load positions from file."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)

            for pos_data in data.get("positions", []):
                position = PaperPosition.from_dict(pos_data)
                self._positions[position.id] = position

            logger.info(f"Loaded {len(self._positions)} paper positions")
        except Exception as e:
            logger.error(f"Failed to load paper positions: {e}")


# Convenience function for quick paper position tracking
async def track_thesis_paper(
    thesis_id: str,
    thesis_name: str,
    symbols: list[str],
    target_value_per_position: float = 3500.0,
) -> list[PaperPosition]:
    """
    Quick helper to add paper positions for a thesis.

    Args:
        thesis_id: Thesis ID
        thesis_name: Thesis name
        symbols: List of symbols to track
        target_value_per_position: Dollar amount per position

    Returns:
        List of created paper positions
    """
    import yaml
    from src.execution.broker.alpaca import AlpacaBroker

    # Get current prices
    creds_path = Path.home() / "projects" / "quant_suite" / "config" / "credentials.yaml"
    with open(creds_path, 'r') as f:
        creds = yaml.safe_load(f)

    alpaca_creds = creds.get('alpaca', {})
    broker = AlpacaBroker(
        api_key=alpaca_creds.get('api_key'),
        secret_key=alpaca_creds.get('secret_key'),
        paper=True
    )
    await broker.connect()

    try:
        tracker = PaperPositionTracker()
        positions = []

        for symbol in symbols:
            quote = await broker.get_quote(symbol)
            if quote:
                price = float(quote.last)
                position = tracker.add_position_by_value(
                    symbol=symbol,
                    target_value=target_value_per_position,
                    entry_price=price,
                    thesis_id=thesis_id,
                    thesis_name=thesis_name,
                )
                positions.append(position)
                print(f"  Added paper: {position.quantity} {symbol} @ ${price:.2f}")

        return positions
    finally:
        await broker.disconnect()
