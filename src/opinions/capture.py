"""Opinion capture engine — assembles context, generates prompts, parses responses."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .context_assembler import OpinionContextAssembler
from .models import OpinionItem
from .universe import OpinionUniverse

logger = logging.getLogger(__name__)


class OpinionCaptureEngine:
    """Main engine: assemble context, generate prompt, parse response, save.

    This engine does NOT call the LLM. It returns a prompt that the calling
    session (operator, briefing, trade-decision) includes in its conversation.
    The LLM outputs JSON, which is then parsed and saved.

    Usage from a session:
        engine = OpinionCaptureEngine()
        result = engine.capture(session_type="operator")
        # ... LLM outputs JSON based on result["prompt"] ...
        opinions = engine.parse_response(json_text, result["batch_id"], "operator")
        saved = engine.save_batch(opinions)
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path(
            os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results"))
        )
        self.instance_id = os.environ.get("ATHENA_INSTANCE", "auto")
        if self.instance_id == "default":
            self.instance_id = "auto"
        self.universe_mgr = OpinionUniverse(results_dir=self.results_dir)
        self.assembler = OpinionContextAssembler(results_dir=self.results_dir)

    def capture(self, session_type: str = "operator") -> dict:
        """Full capture cycle: assemble context, return prompt + metadata.

        Returns:
            {"prompt": str, "batch_id": str, "universe_size": int,
             "context_tokens_est": int, "universe": list[dict]}
        """
        universe = self.universe_mgr.get_universe()
        context_lines, market = self.assembler.assemble_batch(universe)
        batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

        prompt = self._build_prompt(universe, context_lines, market)

        return {
            "prompt": prompt,
            "batch_id": batch_id,
            "universe_size": len(universe),
            "context_tokens_est": len(prompt) // 4,
            "universe": universe,
        }

    def parse_response(
        self, json_text: str, batch_id: str, session_type: str,
        universe: list[dict] | None = None,
    ) -> list[dict]:
        """Parse the LLM's JSON array response into opinion dicts.

        Args:
            json_text: Raw JSON string from the LLM
            batch_id: Batch identifier from capture()
            session_type: Session type (operator, briefing, trade_decision)
            universe: Universe list from capture() for enriching with thesis/signal data
        """
        # Clean up common LLM response artifacts
        text = json_text.strip()
        if text.startswith("```"):
            # Strip markdown code fencing
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            items = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse opinion JSON: {e}")
            logger.debug(f"Raw text: {text[:500]}")
            return []

        if not isinstance(items, list):
            logger.error(f"Expected JSON array, got {type(items).__name__}")
            return []

        # Build lookup for universe enrichment
        uni_lookup = {}
        if universe:
            for u in universe:
                uni_lookup[u["symbol"]] = u

        # Build signal lookup from state
        signals_lookup = {}
        try:
            state_path = self.results_dir / "live" / "state.json"
            if state_path.exists():
                state = json.loads(state_path.read_text())
                signals_lookup = state.get("watchlist_signals", {})
        except Exception:
            pass

        opinions = []
        for item in items:
            try:
                validated = OpinionItem.model_validate(item)
                sym = validated.s.upper()

                # Enrich with snapshot data
                uni_entry = uni_lookup.get(sym, {})
                sig = signals_lookup.get(sym, {})

                opinion = validated.to_opinion_dict(
                    batch_id=batch_id,
                    instance_id=self.instance_id,
                    session_type=session_type,
                    price_at_opinion=sig.get("current_price", 0),
                    composite_signal=sig.get("composite_score", 0),
                    rsi_at_opinion=sig.get("rsi", 0),
                    thesis_id=uni_entry.get("thesis_id", ""),
                )
                opinions.append(opinion)
            except Exception as e:
                logger.warning(f"Failed to parse opinion item: {e} — {item}")
                continue

        logger.info(f"Parsed {len(opinions)}/{len(items)} opinions from batch {batch_id}")
        return opinions

    def save_batch(self, opinions: list[dict]) -> int:
        """Save a batch of opinions to DB via write_api."""
        from src.db.write_api import athena_db

        return athena_db.save_opinion_batch(opinions)

    def _build_prompt(
        self, universe: list[dict], context_lines: str, market: dict
    ) -> str:
        """Build the full prompt for the LLM to generate opinions."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M ET")
        n = len(universe)
        spy = market.get("spy_price", 0)
        spy_chg = market.get("spy_change", 0)
        vix = market.get("vix", 0)
        regime = market.get("regime", "unknown")

        return f"""MARKET OPINION CAPTURE — {timestamp}

Form price opinions on {n} symbols. For each, provide:
1. Price targets at 5d/10d/30d horizons (bull/base/bear dollar values)
2. Trend direction (bullish/bearish/neutral) and magnitude (strong/moderate/mild/flat)
3. Expected performance vs SPY over 10 days (outperform/underperform/inline and alpha %)
4. Confidence (0-1), key driver (one phrase), key risk (one phrase)

Current market: SPY ${spy:.2f} ({spy_chg:+.1f}%) | VIX {vix:.1f} | Regime: {regime}

Symbol context:
{context_lines}

Output a JSON array. Use SHORT keys to minimize tokens:
[{{"s":"MU","t5":[108,105,100],"t10":[115,110,98],"t30":[125,115,95],"dir":"bullish","mag":"moderate","conf":0.65,"rel":"outperform","relm":3.0,"drv":"HBM demand","risk":"inventory correction"}}]

Keys: s=symbol, t5/t10/t30=[bull,base,bear prices], dir=direction, mag=magnitude, conf=confidence, rel=relative vs SPY, relm=alpha %, drv=driver, risk=risk

ONLY output the JSON array. No markdown fencing, no explanation."""
