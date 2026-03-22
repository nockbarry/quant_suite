"""LLM Decision Engine — Anthropic API with full interaction logging.

Builds context-rich prompts from system state and logs every interaction
with complete prompt/response, tokens, and cost for the audit trail.
"""

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.autonomy.config import LLMConfig
from src.autonomy.provenance import log_llm_called, generate_id
from src.db.database import get_db
from src.db.models import LLMInteraction


# Cost per million tokens (as of 2026-02)
MODEL_COSTS = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
}

SYSTEM_PROMPT = """You are Athena, an autonomous trading intelligence system. You make trading decisions
based on converging signals, thesis alignment, and risk management rules.

RULES:
1. NO OPTIONS TRADING (averaged -14.25% return historically)
2. HOLD POSITIONS — don't exit early unless a bearish signpost triggers, conviction < 40%, or -15% stop loss
3. Equal weight within theses — don't over-concentrate
4. Maximum 10% single position, 40% single thesis, 45% sector

When making a decision, respond with JSON:
{
    "action": "BUY|SELL|HOLD|ADD|TRIM",
    "symbol": "TICKER",
    "confidence": 0.0-1.0,
    "size_pct": 0.0-10.0,
    "reasoning": "2-3 sentences",
    "key_factors": ["factor1", "factor2"],
    "risks": ["risk1", "risk2"],
    "pre_mortem": "What could go wrong in 30 days",
    "setup_type": "thesis_driven|momentum|mean_reversion|convergence"
}

If no action is warranted, respond with:
{"action": "HOLD", "reasoning": "explanation"}
"""


@dataclass
class LLMDecisionResult:
    """Result from an LLM decision call."""
    interaction_id: str
    action: str = "HOLD"
    symbol: str = ""
    confidence: float = 0.0
    size_pct: float = 0.0
    reasoning: str = ""
    key_factors: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    pre_mortem: str = ""
    setup_type: str = "thesis_driven"
    raw_response: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class DecisionContext:
    """Context bundle for LLM decision-making."""
    trigger_type: str  # convergence, alert, rule, scheduled
    trigger_id: str
    symbol: str
    state_summary: str
    signals: list[dict] = field(default_factory=list)
    convergence: Optional[dict] = None
    thesis_context: Optional[dict] = None
    portfolio_context: Optional[dict] = None
    recent_decisions: list[dict] = field(default_factory=list)


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate USD cost from token usage."""
    costs = MODEL_COSTS.get(model, {"input": 3.0, "output": 15.0})
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000


class LLMDecisionEngine:
    """Makes trading decisions via the Anthropic API with full logging."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def build_prompt(self, context: DecisionContext) -> str:
        """Build the user prompt from decision context."""
        parts = [
            f"## Trigger: {context.trigger_type}",
            f"Symbol: {context.symbol}",
            "",
            "## Current State Summary",
            context.state_summary,
        ]

        if context.signals:
            parts.append("\n## Active Signals")
            for s in context.signals:
                parts.append(f"- [{s.get('source', '?')}] {s.get('direction', '?')} "
                            f"(confidence: {s.get('confidence', 0):.0%}): {s.get('description', '')}")

        if context.convergence:
            parts.append(f"\n## Convergence Detected")
            parts.append(f"- {context.convergence.get('signal_count', 0)} signals aligned "
                        f"({context.convergence.get('direction', '?')})")
            parts.append(f"- Weighted score: {context.convergence.get('weighted_score', 0):.2f}")

        if context.thesis_context:
            t = context.thesis_context
            parts.append(f"\n## Thesis: {t.get('name', '?')}")
            parts.append(f"- Conviction: {t.get('conviction', 0)}%")
            parts.append(f"- Status: {t.get('status', '?')}")
            parts.append(f"- Positions: {', '.join(t.get('positions', []))}")

        if context.portfolio_context:
            p = context.portfolio_context
            parts.append(f"\n## Portfolio")
            parts.append(f"- Equity: ${p.get('total_value', 0):,.0f}")
            parts.append(f"- Positions: {p.get('position_count', 0)}")
            parts.append(f"- Day P&L: ${p.get('day_pnl', 0):+,.0f}")

        if context.recent_decisions:
            parts.append(f"\n## Recent Decisions (last 3)")
            for d in context.recent_decisions[:3]:
                parts.append(f"- {d.get('action', '?')} {d.get('symbol', '?')} "
                            f"@ {d.get('confidence', 0):.0%} — {d.get('status', '?')}")

        parts.append("\n## Your Decision")
        parts.append(f"Evaluate whether to trade {context.symbol}. Respond with JSON.")

        return "\n".join(parts)

    def make_trade_decision(self, context: DecisionContext) -> LLMDecisionResult:
        """Call the LLM and log the full interaction."""
        interaction_id = generate_id("llm")
        prompt = self.build_prompt(context)

        system_hash = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:16]

        start = time.time()

        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            # Log failed interaction
            self._save_interaction(
                interaction_id=interaction_id,
                trigger_type=context.trigger_type,
                trigger_id=context.trigger_id,
                model=self.config.model,
                system_prompt_hash=system_hash,
                user_prompt=prompt if self.config.log_full_prompts else "[redacted]",
                response=f"ERROR: {e}",
                tokens_input=0,
                tokens_output=0,
                cost_usd=0,
                latency_ms=int((time.time() - start) * 1000),
            )
            return LLMDecisionResult(interaction_id=interaction_id, reasoning=f"LLM error: {e}")

        latency_ms = int((time.time() - start) * 1000)
        response_text = response.content[0].text if response.content else ""
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost = _calculate_cost(self.config.model, tokens_in, tokens_out)

        # Save interaction to DB
        self._save_interaction(
            interaction_id=interaction_id,
            trigger_type=context.trigger_type,
            trigger_id=context.trigger_id,
            model=self.config.model,
            system_prompt_hash=system_hash,
            user_prompt=prompt if self.config.log_full_prompts else "[redacted]",
            response=response_text,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

        # Log event
        log_llm_called(
            interaction_id=interaction_id,
            model=self.config.model,
            tokens=tokens_in + tokens_out,
            cost=cost,
            trigger_type=context.trigger_type,
        )

        # Parse response
        result = self._parse_response(response_text, interaction_id)
        result.tokens_input = tokens_in
        result.tokens_output = tokens_out
        result.cost_usd = cost
        result.latency_ms = latency_ms
        result.raw_response = response_text

        return result

    def _parse_response(self, text: str, interaction_id: str) -> LLMDecisionResult:
        """Parse LLM JSON response into a decision result."""
        try:
            # Find JSON in response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return LLMDecisionResult(
                    interaction_id=interaction_id,
                    action=data.get("action", "HOLD"),
                    symbol=data.get("symbol", ""),
                    confidence=data.get("confidence", 0.0),
                    size_pct=data.get("size_pct", 0.0),
                    reasoning=data.get("reasoning", ""),
                    key_factors=data.get("key_factors", []),
                    risks=data.get("risks", []),
                    pre_mortem=data.get("pre_mortem", ""),
                    setup_type=data.get("setup_type", "thesis_driven"),
                )
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

        return LLMDecisionResult(
            interaction_id=interaction_id,
            reasoning=f"Failed to parse LLM response: {text[:200]}",
        )

    def _save_interaction(self, **kwargs):
        """Save LLM interaction to DB."""
        try:
            interaction = LLMInteraction(
                id=kwargs["interaction_id"],
                timestamp=datetime.utcnow(),
                trigger_type=kwargs.get("trigger_type", ""),
                trigger_id=kwargs.get("trigger_id", ""),
                model=kwargs.get("model", ""),
                system_prompt_hash=kwargs.get("system_prompt_hash", ""),
                user_prompt=kwargs.get("user_prompt", ""),
                response=kwargs.get("response", ""),
                tokens_input=kwargs.get("tokens_input", 0),
                tokens_output=kwargs.get("tokens_output", 0),
                cost_usd=kwargs.get("cost_usd", 0.0),
                latency_ms=kwargs.get("latency_ms", 0),
            )
            with get_db() as session:
                session.add(interaction)
        except Exception as e:
            print(f"WARN: Failed to save LLM interaction to DB: {e}")
