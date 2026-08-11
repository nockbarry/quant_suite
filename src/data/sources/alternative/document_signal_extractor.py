"""
Document Signal Extractor — LLM extraction of structured signals from
SEC filings and earnings press releases.

Milestone v1: capex guidance only. Single signal type by design — accuracy
must be measurable on a holdout before scope expands.

Anti-hallucination guard: every extracted signal must include a verbatim
substring of the source text (`exact_quote`). If the substring is not found
(case-insensitive) in the source, the signal is discarded and logged.

Backend: spawns the Claude Code CLI in non-interactive mode (`claude -p`).
This routes spend through the user's Claude Code subscription rather than
opening a separate Anthropic API billing channel. Invocation flags:
  --disable-slash-commands    skip skill loading (drops ~42K context tokens,
                              cuts per-call cost ~10x)
  --system-prompt             replace default Claude Code system prompt
  --output-format json        structured response with usage + cost
  --max-turns 1               no tool use; single-shot extraction
  --dangerously-skip-permissions   no human review of internal calls

Cost ceiling: hard rate limit of 50 extractions/day enforced via a
date-stamped counter file. Empirically ~$0.005-0.02/call with Haiku 4.5.
"""

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class DocumentSignal:
    """A single tradeable signal extracted from a document.

    Currently scoped to capex guidance signals (v1). Future signal types
    (demand language in v2, hiring velocity in v5) reuse this dataclass.
    """
    symbol: str
    direction: str           # "bullish" | "bearish" | "neutral"
    magnitude: str           # "strong" | "moderate" | "mild"
    confidence: float        # 0..1
    signal_type: str         # "capex_guidance" for v1
    driver_text: str         # Short human-readable summary
    exact_quote: str         # Verbatim substring of source (validated)
    yoy_change_pct: Optional[float]  # e.g. 40.0 for "+40% YoY"
    filed_date: str          # ISO YYYY-MM-DD
    doc_type: str            # "earnings_call" | "10-K" | "10-Q" | "8-K"
    source_doc_id: Optional[str] = None  # corpus doc_id, if from TextCorpus
    extraction_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionFailure:
    """Why an extraction was discarded."""
    symbol: str
    doc_type: str
    filed_date: str
    reason: str
    raw_response: str = ""
    failed_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ---------------------------------------------------------------------------
# Rate limiter (date-stamped daily counter file)
# ---------------------------------------------------------------------------

class DailyRateLimiter:
    """Persists a per-day counter to disk; rejects requests over the limit."""

    def __init__(self, path: Path, daily_limit: int):
        self.path = path
        self.daily_limit = daily_limit

    def _load(self) -> dict:
        if not self.path.exists():
            return {"date": "", "count": 0}
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return {"date": "", "count": 0}

    def _save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state))

    def try_consume(self) -> tuple[bool, int]:
        """Returns (allowed, current_count_after)."""
        today = date.today().isoformat()
        state = self._load()
        if state.get("date") != today:
            state = {"date": today, "count": 0}
        if state["count"] >= self.daily_limit:
            return False, state["count"]
        state["count"] += 1
        self._save(state)
        return True, state["count"]

    def current_count(self) -> int:
        today = date.today().isoformat()
        state = self._load()
        return state["count"] if state.get("date") == today else 0


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

# v1 scope: a single, measurable signal type. Expand only after holdout passes.
_CAPEX_SYSTEM_PROMPT = """You extract a single capex guidance signal from a company's earnings release or filing.

Output strict JSON with these keys (no surrounding text, no markdown fences):
{
  "has_signal": bool,
  "direction": "bullish" | "bearish" | "neutral",
  "magnitude": "strong" | "moderate" | "mild",
  "confidence": float between 0 and 1,
  "exact_quote": str,
  "yoy_change_pct": float | null,
  "driver_text": str
}

Rules:
- "has_signal" is true only if management gave forward capital expenditure
  guidance with either a numeric figure (dollar amount or percent change)
  OR explicit directional language like "doubling", "accelerating", "cutting back".
- "exact_quote" MUST be a verbatim substring of the source text.
  Do not paraphrase, do not summarize, do not insert ellipses.
  If you cannot identify a verbatim quote, set has_signal=false and
  return an empty exact_quote.
- "direction":
    - "bullish" if capex growing — signals strong demand visibility, market expansion.
    - "bearish" if capex cutting — signals demand weakness or capital discipline.
    - "neutral" if guidance maintained or no clear directional change.
- "magnitude":
    - "strong" for clear ≥30% YoY growth or cuts, or explicit "doubling"/"halving" language.
    - "moderate" for 10–29% changes or directional but cautious language.
    - "mild" for sub-10% changes or vague language.
- "confidence" reflects how clearly the guidance is stated and how forward-looking it is.
- "yoy_change_pct" is the year-over-year capex change in percent if explicitly stated, else null.
  Positive = growth (bullish). Negative = cut (bearish).
- "driver_text" is a 1-sentence human-readable summary (≤200 chars).

Output JSON only."""


class DocumentSignalExtractor:
    """Extracts capex guidance signals from earnings press releases.

    Usage:
        extractor = DocumentSignalExtractor()
        signal = extractor.extract_capex(
            symbol="MU",
            text=transcript_text,
            filed_date="2025-06-25",
            doc_type="earnings_call",
        )
        # Returns DocumentSignal or None.

    Backend is the Claude Code CLI (`claude -p ... --output-format json`),
    so spend flows through the existing Claude Code subscription instead of
    a separate Anthropic API billing channel.
    """

    DAILY_RATE_LIMIT = 50
    # Haiku is cheap and good enough for structured extraction. Override via
    # ATHENA_EXTRACTION_MODEL if you want Sonnet for higher accuracy.
    DEFAULT_MODEL = "haiku"
    # Cap input text to keep cost bounded. ~8K tokens of input is enough for the
    # signal-bearing first half of any earnings press release.
    MAX_INPUT_CHARS = 30_000
    # Subprocess timeout. Most calls complete in 5-15s; 90s is safety bound.
    SUBPROCESS_TIMEOUT_SEC = 90

    def __init__(
        self,
        model: Optional[str] = None,
        rate_limit_path: Optional[Path] = None,
        failure_log_path: Optional[Path] = None,
        claude_binary: Optional[str] = None,
    ):
        self.model = model or os.environ.get("ATHENA_EXTRACTION_MODEL", self.DEFAULT_MODEL)
        self.claude_binary = claude_binary or shutil.which("claude")
        self.rate_limiter = DailyRateLimiter(
            rate_limit_path or (paths.scheduler / "document_extraction_rate.json"),
            self.DAILY_RATE_LIMIT,
        )
        self.failure_log = failure_log_path or (paths.logs / "extraction_failures.jsonl")

    def _ensure_binary(self) -> str:
        if not self.claude_binary or not Path(self.claude_binary).exists():
            raise RuntimeError(
                "claude CLI not found on PATH. "
                "Install Claude Code or pass claude_binary= explicitly."
            )
        return self.claude_binary

    def extract_capex(
        self,
        symbol: str,
        text: str,
        filed_date: str,
        doc_type: str = "earnings_call",
        source_doc_id: Optional[str] = None,
    ) -> Optional[DocumentSignal]:
        """Extract a capex guidance signal from `text`. Returns None if no signal.

        Records a failure to the failure log if the LLM hallucinates an
        exact_quote that is not actually in the source text.
        """
        if not text or len(text) < 200:
            return None

        allowed, count = self.rate_limiter.try_consume()
        if not allowed:
            logger.warning(
                f"Rate limit hit ({self.DAILY_RATE_LIMIT}/day). "
                f"Skipping {symbol} {doc_type} {filed_date}."
            )
            return None

        # Truncate to bound input cost; signal-bearing content is at the top.
        truncated = text[: self.MAX_INPUT_CHARS]

        try:
            response_text, usage = self._call_api(symbol, truncated, filed_date, doc_type)
        except Exception as e:
            logger.exception(f"API call failed for {symbol} {filed_date}: {e}")
            self._log_failure(symbol, doc_type, filed_date, f"api_error: {e}")
            return None

        parsed = self._parse_response(response_text)
        if parsed is None:
            self._log_failure(symbol, doc_type, filed_date, "parse_error", response_text)
            return None

        if not parsed.get("has_signal"):
            return None  # Not an error — just no signal in this filing.

        # Anti-hallucination: verbatim quote must exist in the source text.
        quote = (parsed.get("exact_quote") or "").strip()
        if not quote or not self._verify_quote(quote, text):
            logger.warning(
                f"HALLUCINATION GUARD tripped for {symbol} {filed_date}: "
                f"quote not found in source. Quote: {quote[:120]!r}"
            )
            self._log_failure(
                symbol, doc_type, filed_date,
                "hallucinated_quote",
                response_text,
            )
            return None

        signal = DocumentSignal(
            symbol=symbol.upper(),
            direction=parsed.get("direction", "neutral"),
            magnitude=parsed.get("magnitude", "mild"),
            confidence=float(parsed.get("confidence", 0.5)),
            signal_type="capex_guidance",
            driver_text=(parsed.get("driver_text") or "")[:200],
            exact_quote=quote,
            yoy_change_pct=parsed.get("yoy_change_pct"),
            filed_date=filed_date,
            doc_type=doc_type,
            source_doc_id=source_doc_id,
            extraction_metadata={
                "model": self.model,
                "extracted_at": datetime.now().isoformat(timespec="seconds"),
                "input_chars": len(truncated),
                "rate_count_after": count,
                "usage": usage,
            },
        )
        return signal

    def _call_api(
        self,
        symbol: str,
        text: str,
        filed_date: str,
        doc_type: str,
    ) -> tuple[str, dict]:
        """Returns (response_text, usage_dict). Spawns `claude -p` subprocess."""
        binary = self._ensure_binary()
        user_content = (
            f"Symbol: {symbol}\n"
            f"Document type: {doc_type}\n"
            f"Filed date: {filed_date}\n\n"
            f"Source text:\n{text}"
        )
        cmd = [
            binary,
            "--model", self.model,
            "--output-format", "json",
            "--max-turns", "1",
            "--disable-slash-commands",  # skip skill loading — 10x cost reduction
            "--dangerously-skip-permissions",
            "--system-prompt", _CAPEX_SYSTEM_PROMPT,
            "-p", user_content,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.SUBPROCESS_TIMEOUT_SEC,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"claude subprocess timed out after {self.SUBPROCESS_TIMEOUT_SEC}s") from e

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude subprocess failed (exit={proc.returncode}): "
                f"stderr={proc.stderr[:500]!r}"
            )

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"claude returned non-JSON envelope: {proc.stdout[:500]!r}"
            ) from e

        if envelope.get("is_error"):
            raise RuntimeError(
                f"claude reported error: {envelope.get('result', '<no result>')[:500]!r}"
            )

        text_out = envelope.get("result", "") or ""
        usage_raw = envelope.get("usage", {}) or {}
        usage = {
            "input_tokens": usage_raw.get("input_tokens", 0),
            "output_tokens": usage_raw.get("output_tokens", 0),
            "cache_read_input_tokens": usage_raw.get("cache_read_input_tokens", 0),
            "cache_creation_input_tokens": usage_raw.get("cache_creation_input_tokens", 0),
            "total_cost_usd": envelope.get("total_cost_usd"),
            "duration_ms": envelope.get("duration_ms"),
            "model": self.model,
        }
        return text_out, usage

    @staticmethod
    def _parse_response(text: str) -> Optional[dict]:
        """Parse JSON from the LLM response. Strips markdown fences if present."""
        if not text:
            return None
        cleaned = text.strip()
        # Strip ```json ... ``` and ``` ... ``` fences
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Could not parse LLM response as JSON: {e}; text={cleaned[:300]!r}")
            return None

    @staticmethod
    def _verify_quote(quote: str, source_text: str) -> bool:
        """Verbatim substring check (case-insensitive, whitespace-normalized).

        Whitespace normalization is necessary because HTML extraction can
        introduce single spaces where the LLM might reproduce double spaces
        or vice versa. We collapse all runs of whitespace before comparing.
        """
        if not quote or len(quote) < 10:
            return False
        # Fast path: literal containment
        if quote.lower() in source_text.lower():
            return True
        # Whitespace-normalized comparison
        norm_quote = re.sub(r"\s+", " ", quote.lower()).strip()
        norm_source = re.sub(r"\s+", " ", source_text.lower())
        return norm_quote in norm_source

    def _log_failure(
        self,
        symbol: str,
        doc_type: str,
        filed_date: str,
        reason: str,
        raw_response: str = "",
    ) -> None:
        failure = ExtractionFailure(
            symbol=symbol,
            doc_type=doc_type,
            filed_date=filed_date,
            reason=reason,
            raw_response=raw_response[:1000],  # cap log size
        )
        self.failure_log.parent.mkdir(parents=True, exist_ok=True)
        with self.failure_log.open("a") as f:
            f.write(json.dumps(asdict(failure)) + "\n")
