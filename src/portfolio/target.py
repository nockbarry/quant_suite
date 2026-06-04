"""Data model for the declarative portfolio spine.

All weights are fractions of total equity (0-1). These are pure dataclasses
with no I/O — the builder produces them, the store persists them, the
reconciler consumes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Reserve:
    """Named dry powder held back for a specific catalyst, with an expiry.

    Formalizes the intentional cash the operator wants to keep uninvested
    (e.g. "FOMC-June", "SpaceX-IPO"). Untagged cash above the invested band
    is auto-deployed; reserved cash is not. After ``expiry`` the reserve no
    longer holds cash back (it auto-deploys).
    """

    name: str
    target_pct: float          # fraction of equity (0-1) to hold for this catalyst
    catalyst: str              # human description of what we're waiting for
    expiry: date               # after this date the reserve lapses -> auto-deploy
    thesis_id: Optional[str] = None

    def active(self, today: date) -> bool:
        return self.expiry >= today

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target_pct": self.target_pct,
            "catalyst": self.catalyst,
            "expiry": self.expiry.isoformat(),
            "thesis_id": self.thesis_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Reserve":
        exp = d["expiry"]
        if isinstance(exp, str):
            exp = date.fromisoformat(exp[:10])
        return cls(
            name=d["name"],
            target_pct=float(d.get("target_pct", 0.0)),
            catalyst=d.get("catalyst", ""),
            expiry=exp,
            thesis_id=d.get("thesis_id"),
        )


@dataclass
class TargetWeight:
    """Desired weight for one symbol, with provenance for audit."""

    symbol: str
    weight: float                       # fraction of equity (0-1)
    thesis_id: Optional[str] = None
    thesis_name: Optional[str] = None
    source: str = "thesis_ladder"       # thesis_ladder | rule_adjustment | manual
    bounded_by: Optional[str] = None    # which cap clipped it, if any (audit)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "weight": round(self.weight, 4),
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "source": self.source,
            "bounded_by": self.bounded_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TargetWeight":
        return cls(
            symbol=d["symbol"],
            weight=float(d.get("weight", 0.0)),
            thesis_id=d.get("thesis_id"),
            thesis_name=d.get("thesis_name"),
            source=d.get("source", "thesis_ladder"),
            bounded_by=d.get("bounded_by"),
        )


@dataclass
class CashPolicy:
    """Governs how much cash is held vs deployed.

    ``target_invested_band`` is (min, max) fraction invested in a normal
    regime. Named reserves lower the effective invested ceiling; untagged
    excess above the band is auto-deployed by the builder.
    """

    target_invested_band: tuple[float, float] = (0.80, 0.95)
    reserves: list[Reserve] = field(default_factory=list)

    def named_reserve_pct(self, today: date) -> float:
        """Total fraction of equity held back by still-active reserves."""
        return sum(r.target_pct for r in self.reserves if r.active(today))

    def max_invested(self, today: date) -> float:
        """Effective invested ceiling after honoring active reserves."""
        hi = self.target_invested_band[1]
        return max(0.0, hi - self.named_reserve_pct(today))

    def min_invested(self, today: date) -> float:
        lo = self.target_invested_band[0]
        return max(0.0, min(lo, self.max_invested(today)))

    def to_dict(self, today: Optional[date] = None) -> dict:
        d = {
            "target_invested_band": list(self.target_invested_band),
            "reserves": [r.to_dict() for r in self.reserves],
        }
        if today is not None:
            d["named_reserve_pct"] = round(self.named_reserve_pct(today), 4)
            d["max_invested"] = round(self.max_invested(today), 4)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CashPolicy":
        band = d.get("target_invested_band", [0.80, 0.95])
        return cls(
            target_invested_band=(float(band[0]), float(band[1])),
            reserves=[Reserve.from_dict(r) for r in d.get("reserves", [])],
        )


@dataclass
class TargetPortfolio:
    """A complete desired portfolio: symbol weights + cash policy."""

    weights: dict[str, TargetWeight]
    cash_policy: CashPolicy
    generated_at: datetime
    equity_at_build: float
    id: Optional[str] = None

    def invested_pct(self) -> float:
        return sum(w.weight for w in self.weights.values())

    def cash_pct(self) -> float:
        return max(0.0, 1.0 - self.invested_pct())

    def target_value(self, symbol: str, equity: Optional[float] = None) -> float:
        eq = equity if equity is not None else self.equity_at_build
        w = self.weights.get(symbol)
        return (w.weight * eq) if w else 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "generated_at": self.generated_at.isoformat(),
            "equity_at_build": self.equity_at_build,
            "invested_pct": round(self.invested_pct(), 4),
            "cash_pct": round(self.cash_pct(), 4),
            "weights": [w.to_dict() for w in self.weights.values()],
            "cash_policy": self.cash_policy.to_dict(today=self.generated_at.date()),
        }
