"""
ClaudeCodeClient — single canonical entry point for non-interactive Claude
calls in this codebase.

Design rationale:
  All judgment-task LLM invocations should route through the user's Claude
  Code subscription, not a separate Anthropic API channel. This consolidates
  spend, eliminates the need for ANTHROPIC_API_KEY in cron environments,
  and lets the existing rate-limit / retry / fallback logic in
  scripts/session_wrapper.sh reach the entire LLM call surface.

  Direct subprocess invocation of `claude -p` is the canonical pattern.
  --disable-slash-commands cuts ~42K tokens of skill metadata per call
  (10x cost reduction). --system-prompt replaces the default prompt so
  callers control the full context window.

  This client is sync; async callers should use asyncio.to_thread() to
  avoid blocking the event loop.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Map common model aliases / legacy IDs to Claude Code's accepted aliases.
# Claude Code accepts both aliases ("haiku") and full model IDs.
# We normalize known legacy IDs to the current alias so callers using stale
# enum values still work.
_MODEL_ALIASES = {
    # Aliases pass through
    "haiku": "haiku",
    "sonnet": "sonnet",
    "opus": "opus",
    # Legacy/stale model IDs from llm_agent.py LLMModel enum
    "claude-opus-4-5-20251101": "opus",
    "claude-sonnet-4-20250514": "sonnet",
    "claude-3-5-haiku-20241022": "haiku",
    "claude-3-opus-20240229": "opus",
    "claude-3-sonnet-20240229": "sonnet",
    # Newer IDs that may appear in caller code
    "claude-haiku-4-5-20251001": "haiku",
    "claude-sonnet-4-6": "sonnet",
    "claude-opus-4-7": "opus",
}


def normalize_model(model: str) -> str:
    """Map any known model identifier to the Claude Code alias."""
    if not model:
        return "sonnet"
    return _MODEL_ALIASES.get(model.lower(), model)


@dataclass
class ClaudeCodeResponse:
    """Result of a `claude -p` invocation."""
    text: str
    model: str
    duration_ms: int
    total_cost_usd: Optional[float]
    usage: dict = field(default_factory=dict)
    is_error: bool = False
    raw_envelope: dict = field(default_factory=dict)


class ClaudeCodeError(RuntimeError):
    """Raised when the claude subprocess fails or returns a malformed response."""


class ClaudeCodeClient:
    """Sync subprocess wrapper around `claude -p --output-format json`.

    Usage:
        client = ClaudeCodeClient()
        resp = client.complete(
            user="Analyze this data: ...",
            system="You are a quantitative analyst.",
            model="haiku",
        )
        print(resp.text, resp.total_cost_usd)
    """

    DEFAULT_MODEL = "sonnet"
    # Subprocess timeout. Most non-interactive calls finish in 5-30s; cap at
    # 5 min as the safety bound for very long context.
    DEFAULT_TIMEOUT_SEC = 300
    # Disable slash commands by default — cuts 42K tokens of skill metadata
    # per call. Callers that DO want skill access should pass disable_skills=False.
    DEFAULT_DISABLE_SKILLS = True

    def __init__(self, claude_binary: Optional[str] = None):
        self.claude_binary = claude_binary or shutil.which("claude")

    def _ensure_binary(self) -> str:
        if not self.claude_binary or not Path(self.claude_binary).exists():
            raise ClaudeCodeError(
                "claude CLI not found on PATH. Install Claude Code or pass "
                "claude_binary= explicitly."
            )
        return self.claude_binary

    def complete(
        self,
        user: str,
        system: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        max_turns: int = 1,
        json_schema: Optional[dict] = None,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
        disable_skills: bool = DEFAULT_DISABLE_SKILLS,
        extra_flags: Optional[list[str]] = None,
    ) -> ClaudeCodeResponse:
        """Run a single non-interactive Claude Code call.

        Args:
            user: User prompt text. If long, the caller should pre-truncate.
            system: System prompt. None uses Claude Code default (much more
                expensive — only do this if you need its tooling context).
            model: "haiku" | "sonnet" | "opus", or a full model id.
            max_turns: Max reasoning turns. 1 = single-shot, no tool use.
            json_schema: If provided, output is schema-validated JSON.
            timeout_sec: Subprocess hard timeout.
            disable_skills: If True (default), skips the skill loader. Saves
                ~42K context tokens (~10x cost reduction).
            extra_flags: Additional CLI flags appended verbatim.

        Returns:
            ClaudeCodeResponse with text, usage, cost.

        Raises:
            ClaudeCodeError on subprocess failure or malformed envelope.
        """
        binary = self._ensure_binary()
        normalized_model = normalize_model(model)

        cmd: list[str] = [
            binary,
            "--model", normalized_model,
            "--output-format", "json",
            "--max-turns", str(max_turns),
            "--dangerously-skip-permissions",
        ]
        if disable_skills:
            cmd.append("--disable-slash-commands")
        if system is not None:
            cmd.extend(["--system-prompt", system])
        if json_schema is not None:
            cmd.extend(["--json-schema", json.dumps(json_schema)])
        if extra_flags:
            cmd.extend(extra_flags)
        cmd.extend(["-p", user])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise ClaudeCodeError(
                f"claude subprocess timed out after {timeout_sec}s "
                f"(model={normalized_model}, user_chars={len(user)})"
            ) from e

        if proc.returncode != 0:
            raise ClaudeCodeError(
                f"claude subprocess failed (exit={proc.returncode}, "
                f"model={normalized_model}): stderr={proc.stderr[:500]!r}"
            )

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise ClaudeCodeError(
                f"claude returned non-JSON envelope: {proc.stdout[:500]!r}"
            ) from e

        is_error = bool(envelope.get("is_error"))
        if is_error:
            raise ClaudeCodeError(
                f"claude reported error: {envelope.get('result', '')[:500]!r}"
            )

        return ClaudeCodeResponse(
            text=envelope.get("result", "") or "",
            model=normalized_model,
            duration_ms=int(envelope.get("duration_ms", 0)),
            total_cost_usd=envelope.get("total_cost_usd"),
            usage=envelope.get("usage", {}) or {},
            is_error=is_error,
            raw_envelope=envelope,
        )

    def complete_json(
        self,
        user: str,
        system: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        json_schema: Optional[dict] = None,
        **kwargs,
    ) -> tuple[dict, ClaudeCodeResponse]:
        """Convenience wrapper that parses the response as JSON.

        Returns (parsed_dict, full_response). Strips markdown fences.
        Raises ClaudeCodeError if the response is not valid JSON.
        """
        resp = self.complete(
            user=user,
            system=system,
            model=model,
            json_schema=json_schema,
            **kwargs,
        )
        text = resp.text.strip()
        if text.startswith("```"):
            import re
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)
        try:
            return json.loads(text), resp
        except json.JSONDecodeError as e:
            raise ClaudeCodeError(
                f"Response is not valid JSON: {resp.text[:300]!r}"
            ) from e


# Module-level singleton for convenience.
_default_client: Optional[ClaudeCodeClient] = None


def get_client() -> ClaudeCodeClient:
    """Lazy singleton accessor."""
    global _default_client
    if _default_client is None:
        _default_client = ClaudeCodeClient()
    return _default_client
