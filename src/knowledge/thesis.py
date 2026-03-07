"""Investment Thesis Tracking.

Tracks investment theses with:
- Signposts (events that validate/invalidate)
- Conviction history over time
- Linked positions
- Review schedules

Theses are stored as YAML files in ~/quant_results/theses/
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
import json
import uuid
import logging

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class Signpost:
    """An event that validates or invalidates the thesis."""

    description: str
    status: str = "pending"  # pending, triggered, missed, expired
    bullish_if: str = ""
    bearish_if: str = ""
    target_date: Optional[str] = None  # YYYY-MM-DD
    triggered_at: Optional[datetime] = None
    outcome: Optional[str] = None  # bullish, bearish, neutral

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "status": self.status,
            "bullish_if": self.bullish_if,
            "bearish_if": self.bearish_if,
            "target_date": self.target_date,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Signpost":
        return cls(
            description=data["description"],
            status=data.get("status", "pending"),
            bullish_if=data.get("bullish_if", ""),
            bearish_if=data.get("bearish_if", ""),
            target_date=data.get("target_date"),
            triggered_at=datetime.fromisoformat(data["triggered_at"]) if data.get("triggered_at") else None,
            outcome=data.get("outcome"),
        )


@dataclass
class ConvictionUpdate:
    """Record of conviction change."""

    timestamp: datetime
    old_value: float
    new_value: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConvictionUpdate":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            old_value=data["old_value"],
            new_value=data["new_value"],
            reason=data["reason"],
        )


@dataclass
class PriceTarget:
    """Bull/base/bear price targets for a thesis vehicle."""

    symbol: str
    bull_target: float
    base_target: float
    bear_target: float
    entry_price: float
    timeframe_days: int = 90
    set_at: Optional[str] = None
    updated_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "bull_target": self.bull_target,
            "base_target": self.base_target,
            "bear_target": self.bear_target,
            "entry_price": self.entry_price,
            "timeframe_days": self.timeframe_days,
            "set_at": self.set_at,
            "updated_at": self.updated_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PriceTarget":
        return cls(
            symbol=data.get("symbol", ""),
            bull_target=data.get("bull_target", 0),
            base_target=data.get("base_target", 0),
            bear_target=data.get("bear_target", 0),
            entry_price=data.get("entry_price", 0),
            timeframe_days=data.get("timeframe_days", 90),
            set_at=data.get("set_at"),
            updated_at=data.get("updated_at"),
            notes=data.get("notes", ""),
        )

    def progress_pct(self, current_price: float) -> float:
        """How far from entry_price toward base_target (0-100+)."""
        if self.base_target == self.entry_price:
            return 100.0 if current_price >= self.base_target else 0.0
        return ((current_price - self.entry_price) / (self.base_target - self.entry_price)) * 100


@dataclass
class Thesis:
    """An investment thesis with tracking."""

    id: str
    name: str
    created: datetime
    status: str  # active, validated, invalidated, expired, paused

    # The thesis itself
    summary: str
    bull_case: str
    bear_case: str

    # Conviction (0-100)
    conviction: float

    # Tracking
    signposts: list[Signpost] = field(default_factory=list)
    invalidation_triggers: list[str] = field(default_factory=list)
    positions: list[str] = field(default_factory=list)  # Symbols

    # Price targets per vehicle
    price_targets: dict[str, PriceTarget] = field(default_factory=dict)

    # Review
    last_review: Optional[datetime] = None
    next_review: Optional[datetime] = None
    review_interval_days: int = 7

    # History
    conviction_history: list[ConvictionUpdate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def update_conviction(self, new_value: float, reason: str) -> None:
        """Update conviction with audit trail."""
        old_value = self.conviction
        update = ConvictionUpdate(
            timestamp=datetime.now(),
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
        self.conviction_history.append(update)
        self.conviction = new_value
        logger.info(f"Thesis '{self.name}' conviction: {old_value:.0f}% -> {new_value:.0f}%: {reason}")

        try:
            from src.core.events import emit
            emit(
                "thesis_conviction_changed",
                source="thesis_tracker",
                title=f"Thesis '{self.name}' conviction: {old_value:.0f}% -> {new_value:.0f}%",
                detail={"old_value": old_value, "new_value": new_value, "reason": reason},
                thesis_id=self.id,
                severity="warning" if abs(new_value - old_value) >= 15 else "info",
            )
        except Exception:
            pass

    def add_note(self, note: str) -> None:
        """Add a timestamped note."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.notes.append(f"[{timestamp}] {note}")

    def trigger_signpost(self, index: int, outcome: str) -> None:
        """Mark a signpost as triggered."""
        if 0 <= index < len(self.signposts):
            signpost = self.signposts[index]
            signpost.status = "triggered"
            signpost.triggered_at = datetime.now()
            signpost.outcome = outcome
            logger.info(f"Signpost triggered for '{self.name}': {signpost.description} -> {outcome}")

            try:
                from src.core.events import emit
                emit(
                    "thesis_signpost_triggered",
                    source="thesis_tracker",
                    title=f"Signpost triggered: {signpost.description} -> {outcome}",
                    detail={"description": signpost.description, "outcome": outcome,
                            "thesis_name": self.name},
                    thesis_id=self.id,
                    severity="warning" if outcome == "bearish" else "info",
                )
            except Exception:
                pass

    def check_review_due(self) -> bool:
        """Check if thesis review is due."""
        if self.next_review is None:
            return True
        return datetime.now() >= self.next_review

    def schedule_next_review(self) -> None:
        """Schedule the next review."""
        self.last_review = datetime.now()
        self.next_review = datetime.now() + timedelta(days=self.review_interval_days)

    def get_pending_signposts(self) -> list[Signpost]:
        """Get signposts that haven't been triggered."""
        return [s for s in self.signposts if s.status == "pending"]

    def set_price_target(
        self, symbol: str, bull: float, base: float, bear: float,
        entry_price: float, timeframe_days: int = 90, notes: str = "",
    ) -> PriceTarget:
        """Set or update price targets for a vehicle."""
        now = datetime.now().isoformat()
        existing = self.price_targets.get(symbol)
        pt = PriceTarget(
            symbol=symbol,
            bull_target=bull,
            base_target=base,
            bear_target=bear,
            entry_price=entry_price,
            timeframe_days=timeframe_days,
            set_at=existing.set_at if existing else now,
            updated_at=now,
            notes=notes,
        )
        self.price_targets[symbol] = pt
        return pt

    def get_price_target(self, symbol: str) -> Optional[PriceTarget]:
        """Get price target for a specific vehicle."""
        return self.price_targets.get(symbol)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "created": self.created.isoformat(),
            "status": self.status,
            "summary": self.summary,
            "bull_case": self.bull_case,
            "bear_case": self.bear_case,
            "conviction": self.conviction,
            "signposts": [s.to_dict() for s in self.signposts],
            "invalidation_triggers": self.invalidation_triggers,
            "positions": self.positions,
            "price_targets": {sym: pt.to_dict() for sym, pt in self.price_targets.items()},
            "last_review": self.last_review.isoformat() if self.last_review else None,
            "next_review": self.next_review.isoformat() if self.next_review else None,
            "review_interval_days": self.review_interval_days,
            "conviction_history": [c.to_dict() for c in self.conviction_history],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Thesis":
        return cls(
            id=data["id"],
            name=data["name"],
            created=datetime.fromisoformat(data["created"]),
            status=data["status"],
            summary=data["summary"],
            bull_case=data["bull_case"],
            bear_case=data["bear_case"],
            conviction=data["conviction"],
            signposts=[Signpost.from_dict(s) for s in data.get("signposts", [])],
            invalidation_triggers=data.get("invalidation_triggers", []),
            positions=data.get("positions", []),
            price_targets={
                sym: PriceTarget.from_dict(pt)
                for sym, pt in data.get("price_targets", {}).items()
            },
            last_review=datetime.fromisoformat(data["last_review"]) if data.get("last_review") else None,
            next_review=datetime.fromisoformat(data["next_review"]) if data.get("next_review") else None,
            review_interval_days=data.get("review_interval_days", 7),
            conviction_history=[ConvictionUpdate.from_dict(c) for c in data.get("conviction_history", [])],
            notes=data.get("notes", []),
        )

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        if not HAS_YAML:
            return json.dumps(self.to_dict(), indent=2)
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Thesis":
        """Deserialize from YAML string."""
        if not HAS_YAML:
            data = json.loads(yaml_str)
        else:
            data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)


@dataclass
class ThesisSummary:
    """Lightweight thesis summary for unified state."""

    id: str
    name: str
    status: str
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


class ThesisTracker:
    """
    Manages investment theses stored as YAML files.

    Theses are stored in ~/quant_results/theses/{id}.yaml
    """

    def __init__(self, theses_dir: Optional[Path] = None):
        """Initialize tracker.

        Args:
            theses_dir: Directory for thesis files.
                       Defaults to paths.theses.
        """
        self.theses_dir = theses_dir or paths.theses
        self.theses_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Thesis] = {}

    def create_thesis(
        self,
        name: str,
        summary: str,
        bull_case: str,
        bear_case: str,
        conviction: float = 50.0,
        signposts: Optional[list[dict]] = None,
        invalidation_triggers: Optional[list[str]] = None,
        positions: Optional[list[str]] = None,
        review_interval_days: int = 7,
    ) -> Thesis:
        """
        Create a new thesis.

        Args:
            name: Thesis name (e.g., "Venezuela Energy Recovery")
            summary: Brief summary of the thesis
            bull_case: Why this could work
            bear_case: Why this could fail
            conviction: Initial conviction (0-100)
            signposts: List of signpost dicts with description, bullish_if, bearish_if
            invalidation_triggers: List of conditions that would invalidate thesis
            positions: List of symbols linked to this thesis
            review_interval_days: How often to review

        Returns:
            Created Thesis object.
        """
        thesis_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        thesis = Thesis(
            id=thesis_id,
            name=name,
            created=now,
            status="active",
            summary=summary,
            bull_case=bull_case,
            bear_case=bear_case,
            conviction=conviction,
            signposts=[Signpost(**s) for s in (signposts or [])],
            invalidation_triggers=invalidation_triggers or [],
            positions=positions or [],
            last_review=now,
            next_review=now + timedelta(days=review_interval_days),
            review_interval_days=review_interval_days,
        )

        self._save_thesis(thesis)
        self._cache[thesis_id] = thesis

        logger.info(f"Created thesis: {name} (id={thesis_id})")

        try:
            from src.core.events import emit
            emit(
                "thesis_created",
                source="thesis_tracker",
                title=f"Thesis created: {name}",
                detail={"name": name, "conviction": conviction, "positions": positions or []},
                thesis_id=thesis_id,
                conviction=conviction,
            )
        except Exception:
            pass

        return thesis

    def get_thesis(self, thesis_id: str) -> Optional[Thesis]:
        """Get a thesis by ID."""
        if thesis_id in self._cache:
            return self._cache[thesis_id]

        filepath = self.theses_dir / f"{thesis_id}.yaml"
        if not filepath.exists():
            filepath = self.theses_dir / f"{thesis_id}.json"

        if not filepath.exists():
            return None

        thesis = self._load_thesis(filepath)
        if thesis:
            self._cache[thesis_id] = thesis
        return thesis

    def get_active_theses(self) -> list[Thesis]:
        """Get all active theses."""
        theses = []
        for filepath in self.theses_dir.glob("*.*"):
            if filepath.suffix in [".yaml", ".json"]:
                thesis = self._load_thesis(filepath)
                if thesis and thesis.status == "active":
                    theses.append(thesis)
                    self._cache[thesis.id] = thesis
        return theses

    def get_all_theses(self) -> list[Thesis]:
        """Get all theses regardless of status."""
        theses = []
        for filepath in self.theses_dir.glob("*.*"):
            if filepath.suffix in [".yaml", ".json"]:
                thesis = self._load_thesis(filepath)
                if thesis:
                    theses.append(thesis)
                    self._cache[thesis.id] = thesis
        return theses

    def get_theses_for_symbol(self, symbol: str) -> list[Thesis]:
        """Get all active theses that include this symbol in positions.

        Args:
            symbol: Stock symbol to search for

        Returns:
            List of active theses that have this symbol in positions
        """
        return [t for t in self.get_active_theses() if symbol in t.positions]

    def get_all_theses_for_symbol(self, symbol: str) -> list[Thesis]:
        """Get all theses (any status) that include this symbol.

        Args:
            symbol: Stock symbol to search for

        Returns:
            List of all theses that have this symbol in positions
        """
        return [t for t in self.get_all_theses() if symbol in t.positions]

    def update_thesis(self, thesis_id: str, updates: dict) -> bool:
        """
        Update a thesis.

        Args:
            thesis_id: Thesis to update
            updates: Dict of field -> value updates

        Returns:
            True if updated successfully.
        """
        thesis = self.get_thesis(thesis_id)
        if not thesis:
            return False

        for key, value in updates.items():
            if hasattr(thesis, key):
                setattr(thesis, key, value)

        self._save_thesis(thesis)
        return True

    def add_position(self, thesis_id: str, symbol: str) -> bool:
        """Add a position to a thesis."""
        thesis = self.get_thesis(thesis_id)
        if not thesis:
            return False

        if symbol not in thesis.positions:
            thesis.positions.append(symbol)
            self._save_thesis(thesis)

        return True

    def remove_position(self, thesis_id: str, symbol: str) -> bool:
        """Remove a position from a thesis."""
        thesis = self.get_thesis(thesis_id)
        if not thesis:
            return False

        if symbol in thesis.positions:
            thesis.positions.remove(symbol)
            self._save_thesis(thesis)

        return True

    def set_price_targets(
        self, thesis_id: str, targets: dict[str, dict],
    ) -> bool:
        """Set price targets for thesis vehicles and create predictions.

        Args:
            thesis_id: Thesis to update
            targets: Dict of symbol -> {bull_target, base_target, bear_target, entry_price, ...}
        """
        thesis = self.get_thesis(thesis_id)
        if not thesis:
            logger.warning(f"Thesis {thesis_id} not found for price targets")
            return False

        for symbol, t in targets.items():
            thesis.set_price_target(
                symbol=symbol,
                bull=t["bull_target"],
                base=t["base_target"],
                bear=t["bear_target"],
                entry_price=t["entry_price"],
                timeframe_days=t.get("timeframe_days", 90),
                notes=t.get("notes", ""),
            )

        self._save_thesis(thesis)

        # Create/update price_target predictions
        try:
            from src.db.write_api import athena_db
            athena_db.update_price_targets(thesis_id, {
                sym: pt.to_dict() for sym, pt in thesis.price_targets.items()
            })
        except Exception as e:
            logger.warning(f"Price target prediction creation failed: {e}")

        logger.info(f"Set price targets for thesis '{thesis.name}': {list(targets.keys())}")
        return True

    def invalidate_thesis(self, thesis_id: str, reason: str) -> bool:
        """Mark a thesis as invalidated."""
        thesis = self.get_thesis(thesis_id)
        if not thesis:
            return False

        thesis.status = "invalidated"
        thesis.add_note(f"INVALIDATED: {reason}")
        self._save_thesis(thesis)

        logger.info(f"Thesis '{thesis.name}' invalidated: {reason}")

        try:
            from src.core.events import emit
            emit(
                "thesis_invalidated",
                source="thesis_tracker",
                severity="critical",
                title=f"Thesis INVALIDATED: {thesis.name}",
                detail={"reason": reason, "thesis_name": thesis.name,
                        "positions": thesis.positions},
                thesis_id=thesis_id,
            )
        except Exception:
            pass

        return True

    def validate_thesis(self, thesis_id: str, reason: str) -> bool:
        """Mark a thesis as validated (played out successfully)."""
        thesis = self.get_thesis(thesis_id)
        if not thesis:
            return False

        thesis.status = "validated"
        thesis.add_note(f"VALIDATED: {reason}")
        self._save_thesis(thesis)

        logger.info(f"Thesis '{thesis.name}' validated: {reason}")
        return True

    def get_theses_due_for_review(self) -> list[Thesis]:
        """Get theses that need review."""
        return [t for t in self.get_active_theses() if t.check_review_due()]

    def get_summaries(self) -> list[ThesisSummary]:
        """Get lightweight summaries of active theses."""
        summaries = []
        for thesis in self.get_active_theses():
            pending = thesis.get_pending_signposts()
            summaries.append(ThesisSummary(
                id=thesis.id,
                name=thesis.name,
                status=thesis.status,
                conviction=thesis.conviction,
                positions=thesis.positions,
                next_signpost=pending[0].description if pending else None,
                days_active=(datetime.now() - thesis.created).days,
            ))
        return summaries

    def _save_thesis(self, thesis: Thesis) -> None:
        """Save thesis to file and sync to DB."""
        if HAS_YAML:
            filepath = self.theses_dir / f"{thesis.id}.yaml"
            content = thesis.to_yaml()
        else:
            filepath = self.theses_dir / f"{thesis.id}.json"
            content = json.dumps(thesis.to_dict(), indent=2)

        with open(filepath, "w") as f:
            f.write(content)

        # Sync to DB
        try:
            from src.db.write_api import athena_db
            athena_db.upsert_thesis(thesis.to_dict())
        except Exception as e:
            logger.warning(f"DB sync failed for thesis {thesis.id}: {e}")

    def _load_thesis(self, filepath: Path) -> Optional[Thesis]:
        """Load thesis from file."""
        try:
            with open(filepath, "r") as f:
                content = f.read()

            if filepath.suffix == ".yaml" and HAS_YAML:
                return Thesis.from_yaml(content)
            else:
                data = json.loads(content)
                return Thesis.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load thesis from {filepath}: {e}")
            return None
