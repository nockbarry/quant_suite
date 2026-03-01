"""Parse Claude CLI --output-format stream-json NDJSON into typed events.

With --include-partial-messages, the CLI emits these line types on stderr:

  {"type":"system", "subtype":"init", ...}
  {"type":"stream_event", "event":{"type":"message_start", ...}}
  {"type":"stream_event", "event":{"type":"content_block_start", ...}}
  {"type":"stream_event", "event":{"type":"content_block_delta", "delta":{"type":"text_delta", ...}}}
  {"type":"stream_event", "event":{"type":"content_block_stop"}}
  {"type":"stream_event", "event":{"type":"message_delta", "usage":{...}}}
  {"type":"stream_event", "event":{"type":"message_stop"}}
  {"type":"assistant", "message":{...}}     # complete message (after partials)
  {"type":"rate_limit_event", ...}
  {"type":"result", "result":"...", "total_cost_usd":..., "usage":{...}}

Without --include-partial-messages, only system/assistant/result/rate_limit lines appear
(no stream_event lines).
"""

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Cost per 1M tokens (same as src/autonomy/llm_decisions.py)
MODEL_COSTS = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-opus-4-6-20250610": {"input": 15.0, "output": 75.0},
    # Fallback handled in get_token_summary
}


@dataclass
class StreamEvent:
    """A parsed stream event from Claude CLI."""

    type: str  # text_delta, tool_use_start, tool_input_delta, thinking_delta,
    #            turn_start, turn_end, result, assistant_message
    data: dict
    turn: int
    raw: str


@dataclass
class StreamEventParser:
    """Parses Claude CLI stream-json lines into typed StreamEvents.

    Handles both streaming mode (--include-partial-messages) and
    non-streaming mode (complete assistant messages only).
    """

    turn: int = 0
    full_text: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cost_usd: float = 0.0
    model: str = ""
    _current_tool_name: str = ""
    _current_tool_id: str = ""
    _current_tool_input: str = ""
    _result_text: str = ""
    raw_lines: list[str] = field(default_factory=list)

    def parse_line(self, line: str) -> StreamEvent | None:
        """Parse a single NDJSON line into a StreamEvent, or None if not relevant."""
        line = line.strip()
        if not line:
            return None

        self.raw_lines.append(line)

        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None

        obj_type = obj.get("type", "")

        # ---- Final result line ----
        if obj_type == "result":
            result_text = obj.get("result", "")
            if isinstance(result_text, str):
                self._result_text = result_text
            # Extract final usage from result
            usage = obj.get("usage", {})
            if usage:
                self.total_input_tokens = usage.get("input_tokens", self.total_input_tokens)
                self.total_output_tokens = usage.get("output_tokens", self.total_output_tokens)
                self.total_cache_read_tokens = usage.get("cache_read_input_tokens", 0)
                self.total_cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
            if obj.get("total_cost_usd"):
                self.total_cost_usd = obj["total_cost_usd"]
            return StreamEvent(
                type="result",
                data={
                    "text": result_text if isinstance(result_text, str) else "",
                    "turn": self.turn,
                    "cost_usd": self.total_cost_usd,
                    "duration_ms": obj.get("duration_ms", 0),
                },
                turn=self.turn,
                raw=line,
            )

        # ---- System init ----
        if obj_type == "system":
            model = obj.get("model", "")
            if model:
                self.model = model
            return None

        # ---- Streaming event (with --include-partial-messages) ----
        if obj_type == "stream_event":
            return self._parse_stream_event(obj.get("event", {}), line)

        # ---- Complete assistant message (non-streaming or after partials) ----
        if obj_type == "assistant":
            return self._parse_assistant_message(obj, line)

        # rate_limit_event, etc. — skip
        return None

    def _parse_stream_event(self, event: dict, raw: str) -> StreamEvent | None:
        """Parse an inner stream_event (API-level streaming event)."""
        etype = event.get("type", "")

        # message_start — new turn
        if etype == "message_start":
            self.turn += 1
            msg = event.get("message", {})
            usage = msg.get("usage", {})
            self.total_input_tokens += usage.get("input_tokens", 0)
            self.total_cache_read_tokens += usage.get("cache_read_input_tokens", 0)
            self.total_cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
            if msg.get("model"):
                self.model = msg["model"]
            return StreamEvent(
                type="turn_start",
                data={
                    "turn": self.turn,
                    "model": self.model,
                    "input_tokens": usage.get("input_tokens", 0),
                },
                turn=self.turn,
                raw=raw,
            )

        # content_block_start
        if etype == "content_block_start":
            block = event.get("content_block", {})
            block_type = block.get("type", "")
            if block_type == "tool_use":
                self._current_tool_name = block.get("name", "")
                self._current_tool_id = block.get("id", "")
                self._current_tool_input = ""
                return StreamEvent(
                    type="tool_use_start",
                    data={
                        "name": self._current_tool_name,
                        "id": self._current_tool_id,
                        "turn": self.turn,
                    },
                    turn=self.turn,
                    raw=raw,
                )
            if block_type == "thinking":
                return StreamEvent(
                    type="thinking_start",
                    data={"turn": self.turn},
                    turn=self.turn,
                    raw=raw,
                )
            return None

        # content_block_delta
        if etype == "content_block_delta":
            delta = event.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta":
                text = delta.get("text", "")
                self.full_text += text
                return StreamEvent(
                    type="text_delta",
                    data={"text": text, "turn": self.turn},
                    turn=self.turn,
                    raw=raw,
                )

            if delta_type == "input_json_delta":
                partial = delta.get("partial_json", "")
                self._current_tool_input += partial
                return StreamEvent(
                    type="tool_input_delta",
                    data={
                        "partial_json": partial,
                        "name": self._current_tool_name,
                        "id": self._current_tool_id,
                        "turn": self.turn,
                    },
                    turn=self.turn,
                    raw=raw,
                )

            if delta_type == "thinking_delta":
                text = delta.get("thinking", "")
                return StreamEvent(
                    type="thinking_delta",
                    data={"text": text, "turn": self.turn},
                    turn=self.turn,
                    raw=raw,
                )

            return None

        # content_block_stop
        if etype == "content_block_stop":
            if self._current_tool_name:
                name = self._current_tool_name
                tool_input = self._current_tool_input
                self._current_tool_name = ""
                self._current_tool_id = ""
                self._current_tool_input = ""
                return StreamEvent(
                    type="tool_use_end",
                    data={"name": name, "input": tool_input, "turn": self.turn},
                    turn=self.turn,
                    raw=raw,
                )
            return None

        # message_delta — end of turn, has output token counts
        if etype == "message_delta":
            usage = event.get("usage", {})
            out_tokens = usage.get("output_tokens", 0)
            self.total_output_tokens += out_tokens
            stop_reason = event.get("delta", {}).get("stop_reason", "")
            return StreamEvent(
                type="turn_end",
                data={
                    "turn": self.turn,
                    "output_tokens": out_tokens,
                    "stop_reason": stop_reason,
                },
                turn=self.turn,
                raw=raw,
            )

        return None

    def _parse_assistant_message(self, obj: dict, raw: str) -> StreamEvent | None:
        """Parse a complete assistant message (non-streaming fallback).

        This handles the case when --include-partial-messages is NOT used,
        or the complete message that arrives after all stream_events.
        """
        message = obj.get("message", {})
        content = message.get("content", [])
        usage = message.get("usage", {})

        if message.get("model"):
            self.model = message["model"]

        # If we already got stream_events for this turn, skip the duplicate
        # complete message. Detect by checking if full_text already has content.
        # But we still want to process tool_use blocks from complete messages.
        has_text_from_stream = bool(self.full_text)

        events_out = []
        for block in content:
            btype = block.get("type", "")
            if btype == "text" and not has_text_from_stream:
                text = block.get("text", "")
                self.full_text += text
                events_out.append(("text_delta", {"text": text, "turn": self.turn}))
            elif btype == "tool_use" and not has_text_from_stream:
                events_out.append(("tool_use_start", {
                    "name": block.get("name", ""),
                    "id": block.get("id", ""),
                    "turn": self.turn,
                }))

        # Update token counts from complete message if we haven't from stream
        if usage and not has_text_from_stream:
            self.total_input_tokens += usage.get("input_tokens", 0)
            self.total_output_tokens += usage.get("output_tokens", 0)
            self.total_cache_read_tokens += usage.get("cache_read_input_tokens", 0)
            self.total_cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)

            if not self.turn:
                self.turn = 1

        # Return only the first event (text or tool); caller gets turn updates
        # from stream_events. For non-streaming mode, emit text as one block.
        if events_out:
            etype, data = events_out[0]
            return StreamEvent(type=etype, data=data, turn=self.turn, raw=raw)

        return None

    def get_token_summary(self) -> dict:
        """Return token usage summary with cost."""
        # Prefer the total_cost_usd from the result line if available
        if self.total_cost_usd > 0:
            cost = round(self.total_cost_usd, 6)
        else:
            costs = MODEL_COSTS.get(self.model, {"input": 3.0, "output": 15.0})
            cost = round(
                (self.total_input_tokens * costs["input"]
                 + self.total_output_tokens * costs["output"]) / 1_000_000,
                6,
            )
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "cache_read_tokens": self.total_cache_read_tokens,
            "cache_creation_tokens": self.total_cache_creation_tokens,
            "model": self.model,
            "cost_usd": cost,
        }
