"""Data model for calibrated symbol probabilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SymbolProbability:
    """Calibrated P(direction correct over ~10d) for one symbol.

    `sources` records each contributing estimate pre-blend ({"curve": 0.55,
    "blind": 0.61, "ensemble": 0.58}) for audit; `red_flags` carries
    anomalies like stated_conf_ge_90 (overconfidence is a warning sign here,
    never a size boost).
    """

    symbol: str
    p_direction: float
    thesis_id: str | None = None
    sources: dict[str, float] = field(default_factory=dict)
    n_effective: int = 0
    as_of: datetime = field(default_factory=datetime.now)
    red_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "p_direction": round(self.p_direction, 4),
            "thesis_id": self.thesis_id,
            "sources": {k: round(v, 4) for k, v in self.sources.items()},
            "n_effective": self.n_effective,
            "as_of": self.as_of.isoformat(),
            "red_flags": self.red_flags,
        }
