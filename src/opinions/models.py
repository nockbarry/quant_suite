"""Pydantic validation models for opinion capture parsing."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class OpinionItem(BaseModel):
    """Validates a single element from the LLM's JSON opinion response.

    Short keys from the LLM prompt:
        s=symbol, t5/t10/t30=[bull,base,bear], dir=direction,
        mag=magnitude, conf=confidence, rel=relative_direction,
        relm=relative_magnitude, drv=key_driver, risk=risk_flag
    """

    s: str  # symbol
    t5: list[float] = [0, 0, 0]  # [bull, base, bear] 5-day
    t10: list[float] = [0, 0, 0]  # [bull, base, bear] 10-day
    t30: list[float] = [0, 0, 0]  # [bull, base, bear] 30-day
    dir: str = "neutral"  # bullish, bearish, neutral
    mag: str = "flat"  # strong, moderate, mild, flat
    conf: float = 0.5  # 0-1
    rel: str = "inline"  # outperform, underperform, inline
    relm: float = 0.0  # expected alpha % vs benchmark
    drv: str = ""  # key driver
    risk: str = ""  # key risk

    @field_validator("dir")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("bullish", "bearish", "neutral"):
            return "neutral"
        return v

    @field_validator("mag")
    @classmethod
    def validate_magnitude(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("strong", "moderate", "mild", "flat"):
            return "flat"
        return v

    @field_validator("conf")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @field_validator("rel")
    @classmethod
    def validate_relative(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("outperform", "underperform", "inline"):
            return "inline"
        return v

    @field_validator("t5", "t10", "t30")
    @classmethod
    def validate_targets(cls, v: list) -> list[float]:
        if not v or len(v) < 3:
            return [0.0, 0.0, 0.0]
        return [float(x) for x in v[:3]]

    def to_opinion_dict(
        self,
        batch_id: str,
        instance_id: str,
        session_type: str,
        price_at_opinion: float = 0,
        composite_signal: float = 0,
        rsi_at_opinion: float = 0,
        thesis_id: str = "",
        relative_benchmark: str = "SPY",
    ) -> dict:
        """Convert to a dict suitable for save_opinion_batch()."""
        return {
            "symbol": self.s.upper(),
            "instance_id": instance_id,
            "session_type": session_type,
            "batch_id": batch_id,
            "price_at_opinion": price_at_opinion,
            "composite_signal": composite_signal,
            "rsi_at_opinion": rsi_at_opinion,
            "target_5d_bull": self.t5[0],
            "target_5d_base": self.t5[1],
            "target_5d_bear": self.t5[2],
            "target_10d_bull": self.t10[0],
            "target_10d_base": self.t10[1],
            "target_10d_bear": self.t10[2],
            "target_30d_bull": self.t30[0],
            "target_30d_base": self.t30[1],
            "target_30d_bear": self.t30[2],
            "trend_direction": self.dir,
            "trend_magnitude": self.mag,
            "trend_confidence": self.conf,
            "relative_benchmark": relative_benchmark,
            "relative_direction": self.rel,
            "relative_magnitude": self.relm,
            "thesis_id": thesis_id or None,
            "key_driver": self.drv[:200],
            "risk_flag": self.risk[:200],
            "created": datetime.utcnow().isoformat(),
        }
