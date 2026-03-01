"""Scan Claude Code CLI sessions and import as AgentRun records.

Reads from ~/.claude/projects/-home-nock-projects-quant-suite/sessions-index.json
and imports untracked sessions into the Athena DB for unified provenance.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path.home() / ".claude" / "projects" / "-home-nock-projects-quant-suite"
SESSIONS_INDEX = SESSIONS_DIR / "sessions-index.json"

# Cost per 1M tokens (duplicated from stream_parser to avoid circular imports)
_MODEL_COSTS = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-opus-4-6-20250610": {"input": 15.0, "output": 75.0},
}


def _parse_session_jsonl(filepath: Path) -> dict:
    """Parse a CLI session JSONL file for token usage, cost, model, and last output.

    Returns dict with keys: total_input, total_output, total_cache_read,
    total_cache_creation, cost_usd, model, last_text.
    """
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0
    model = ""
    last_text = ""

    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if obj.get("type") != "assistant":
                    continue

                message = obj.get("message", {})
                usage = message.get("usage", {})
                if not usage:
                    continue

                if message.get("model"):
                    model = message["model"]

                total_input += usage.get("input_tokens", 0)
                total_output += usage.get("output_tokens", 0)
                total_cache_read += usage.get("cache_read_input_tokens", 0)
                total_cache_creation += usage.get("cache_creation_input_tokens", 0)

                # Capture last assistant text
                content = message.get("content", [])
                for block in content:
                    if block.get("type") == "text" and block.get("text"):
                        last_text = block["text"]

    except Exception as e:
        logger.warning(f"Failed to parse session JSONL {filepath}: {e}")

    # Compute cost from tokens + model
    costs = _MODEL_COSTS.get(model, {"input": 15.0, "output": 75.0})
    cost_usd = round(
        (total_input * costs["input"] + total_output * costs["output"]) / 1_000_000,
        6,
    )

    return {
        "total_input": total_input,
        "total_output": total_output,
        "total_cache_read": total_cache_read,
        "total_cache_creation": total_cache_creation,
        "total_tokens": total_input + total_output,
        "cost_usd": cost_usd,
        "model": model,
        "last_text": last_text,
    }


def _extract_first_prompt(filepath: Path) -> str:
    """Extract the first user prompt from a session JSONL file."""
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "user":
                    content = obj.get("message", {}).get("content", "")
                    if isinstance(content, str) and content:
                        return content
    except Exception:
        pass
    return "CLI session"


def _extract_timestamps(filepath: Path) -> tuple[datetime | None, datetime | None]:
    """Extract first and last timestamps from a session JSONL file."""
    first_ts = None
    last_ts = None
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = obj.get("timestamp")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts
                    except (ValueError, TypeError):
                        pass
    except Exception:
        pass
    return first_ts, last_ts


def _count_messages(filepath: Path) -> int:
    """Count user + assistant messages in a session JSONL."""
    count = 0
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") in ("user", "assistant"):
                    count += 1
    except Exception:
        pass
    return count


def scan_cli_sessions() -> list[dict]:
    """Discover CLI sessions from index + disk, return entries not yet in DB.

    The sessions-index.json may be stale, so we also scan for .jsonl files
    directly in the sessions directory.
    """
    # Check which session_ids are already imported
    from src.db.database import get_db
    from src.db.models import AgentRun

    existing_ids = set()
    try:
        with get_db() as session:
            rows = (
                session.query(AgentRun.session_id)
                .filter(AgentRun.session_id.isnot(None))
                .all()
            )
            existing_ids = {r[0] for r in rows}
    except Exception as e:
        logger.warning(f"Failed to query existing session_ids: {e}")

    # Collect entries from index
    indexed = {}
    if SESSIONS_INDEX.exists():
        try:
            index = json.loads(SESSIONS_INDEX.read_text())
            for entry in index.get("entries", []):
                sid = entry.get("sessionId", "")
                if sid:
                    indexed[sid] = entry
        except Exception as e:
            logger.warning(f"Failed to read sessions index: {e}")

    # Collect entries from disk JSONL files (handles stale index)
    unimported = []
    if SESSIONS_DIR.exists():
        for jsonl_file in SESSIONS_DIR.glob("*.jsonl"):
            sid = jsonl_file.stem
            if sid in existing_ids:
                continue

            if sid in indexed:
                # Use index entry (has richer metadata)
                entry = indexed[sid]
                # Ensure fullPath points to actual file
                entry["fullPath"] = str(jsonl_file)
                unimported.append(entry)
            else:
                # Build entry from the JSONL file directly
                unimported.append({
                    "sessionId": sid,
                    "fullPath": str(jsonl_file),
                    "firstPrompt": None,  # will extract from file
                    "messageCount": None,  # will extract from file
                    "created": None,
                    "modified": None,
                    "gitBranch": "",
                })

    return unimported


def import_cli_session(entry: dict) -> str | None:
    """Import a single CLI session entry as an AgentRun. Returns run_id or None."""
    session_id = entry.get("sessionId", "")
    if not session_id:
        return None

    jsonl_path = Path(entry.get("fullPath", ""))
    if not jsonl_path.exists():
        logger.warning(f"Session JSONL not found: {jsonl_path}")
        return None

    # Parse the JSONL for tokens/cost
    parsed = _parse_session_jsonl(jsonl_path)

    # Build the AgentRun
    run_id = f"cli_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

    # Get metadata — from index entry or extract from JSONL
    first_prompt = entry.get("firstPrompt")
    if not first_prompt:
        first_prompt = _extract_first_prompt(jsonl_path)

    message_count = entry.get("messageCount")
    if message_count is None:
        message_count = _count_messages(jsonl_path)

    # Parse timestamps — from index or extract from JSONL
    created = None
    modified = None
    if entry.get("created"):
        try:
            created = datetime.fromisoformat(entry["created"].replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            pass
    if entry.get("modified"):
        try:
            modified = datetime.fromisoformat(entry["modified"].replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            pass

    if not created or not modified:
        ts_first, ts_last = _extract_timestamps(jsonl_path)
        if not created:
            created = ts_first or datetime.utcnow()
        if not modified:
            modified = ts_last

    last_text = parsed.get("last_text", "")

    try:
        from src.db.database import get_db
        from src.db.models import AgentRun

        with get_db() as session:
            run = AgentRun(
                id=run_id,
                agent_type="cli_session",
                task=first_prompt[:500] if first_prompt else "CLI session",
                trigger_reason=f"CLI terminal ({message_count} messages)",
                session_id=session_id,
                started_at=created,
                completed_at=modified,
                status="completed",
                tokens_used=parsed["total_tokens"],
                cost_usd=parsed["cost_usd"],
                findings_summary=last_text[:5000] if last_text else "",
                raw_output=last_text,
                artifacts=json.dumps({
                    "session_jsonl": str(jsonl_path),
                    "model": parsed["model"],
                    "message_count": message_count,
                    "git_branch": entry.get("gitBranch", ""),
                }),
            )
            session.add(run)
        return run_id
    except Exception as e:
        logger.warning(f"Failed to import CLI session {session_id}: {e}")
        return None


def import_all_cli_sessions() -> int:
    """Batch import all unimported CLI sessions. Returns count imported."""
    unimported = scan_cli_sessions()
    count = 0
    for entry in unimported:
        run_id = import_cli_session(entry)
        if run_id:
            count += 1
            logger.info(f"Imported CLI session {entry.get('sessionId', '?')} as {run_id}")
    return count


# Auto-scan with cooldown (used by HTMX metrics refresh)
_last_scan_time: datetime | None = None


def maybe_auto_scan() -> int:
    """Auto-import CLI sessions with a 5-minute cooldown. Returns count imported."""
    global _last_scan_time
    now = datetime.utcnow()
    if _last_scan_time is not None and (now - _last_scan_time).total_seconds() < 300:
        return 0
    _last_scan_time = now
    try:
        return import_all_cli_sessions()
    except Exception as e:
        logger.warning(f"Auto-scan failed: {e}")
        return 0
