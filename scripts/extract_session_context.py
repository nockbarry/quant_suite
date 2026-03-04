#!/usr/bin/env python3
"""
Extract structured context events from Claude Code .jsonl transcripts.

Parses conversation transcripts to recover:
- WebSearch tool calls -> web_search events
- WebFetch tool calls -> news_item events
- Agent tool calls -> agent_output events
- Bash calls to quick_trade.py / claude_execute.py -> trade execution events
- Assistant messages referencing prices/VIX -> market context

Usage:
    # Extract from a specific session
    PYTHONPATH=. python3 scripts/extract_session_context.py --session SESSION_ID

    # Extract and link to decisions made during that session
    PYTHONPATH=. python3 scripts/extract_session_context.py --session SESSION_ID --link-decisions

    # List available sessions
    PYTHONPATH=. python3 scripts/extract_session_context.py --list

    # Extract from all sessions in the last N days
    PYTHONPATH=. python3 scripts/extract_session_context.py --recent 7
"""

import argparse
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from src.context.session_context import ContextEvent

logger = logging.getLogger(__name__)

TRANSCRIPT_DIR = Path.home() / ".claude" / "projects" / "-home-nock-projects-quant-suite"


def list_sessions(days: int = 7) -> list[dict]:
    """List available session transcripts."""
    cutoff = datetime.now() - timedelta(days=days)
    sessions = []

    for f in sorted(TRANSCRIPT_DIR.glob("*.jsonl")):
        stat = f.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        if mtime >= cutoff:
            # Read first line to get session info
            try:
                with open(f) as fh:
                    first_line = json.loads(fh.readline())
                    session_id = first_line.get("sessionId", f.stem)
            except Exception:
                session_id = f.stem

            sessions.append({
                "session_id": session_id,
                "file": str(f),
                "modified": mtime.isoformat(),
                "size_kb": stat.st_size // 1024,
            })

    return sessions


def extract_from_transcript(session_id: str) -> list[ContextEvent]:
    """Parse a .jsonl transcript and extract structured events.

    Extracts:
    - WebSearch tool calls -> web_search events
    - WebFetch tool calls -> news_item events
    - Agent tool calls -> agent_output events
    - Bash calls to quick_trade.py -> trade execution events
    """
    transcript_file = TRANSCRIPT_DIR / f"{session_id}.jsonl"
    if not transcript_file.exists():
        logger.error(f"Transcript not found: {transcript_file}")
        return []

    events: list[ContextEvent] = []

    with open(transcript_file) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            msg = entry.get("message", {})
            content = msg.get("content", [])
            timestamp_str = entry.get("timestamp")
            timestamp = _parse_timestamp(timestamp_str) if timestamp_str else datetime.utcnow()

            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue

                if block.get("type") == "tool_use":
                    tool_events = _extract_tool_use(block, timestamp)
                    events.extend(tool_events)

                elif block.get("type") == "tool_result":
                    # Tool results can contain WebSearch/WebFetch responses
                    result_events = _extract_tool_result(block, timestamp)
                    events.extend(result_events)

    logger.info(f"Extracted {len(events)} events from session {session_id}")
    return events


def _extract_tool_use(block: dict, timestamp: datetime) -> list[ContextEvent]:
    """Extract events from a tool_use block."""
    events = []
    tool = block.get("name", "")
    inp = block.get("input", {})

    if tool == "WebSearch":
        query = inp.get("query", "")
        events.append(ContextEvent(
            timestamp=timestamp,
            event_type="web_search",
            source="websearch",
            symbols=_extract_symbols(query),
            summary=f"Search: {query}",
            detail=query,
            metadata={"query": query, "tool_use_id": block.get("id", "")},
        ))

    elif tool == "WebFetch":
        url = inp.get("url", "")
        prompt = inp.get("prompt", "")
        events.append(ContextEvent(
            timestamp=timestamp,
            event_type="news_item",
            source="webfetch",
            symbols=_extract_symbols(prompt),
            summary=f"Fetched: {url[:80]}",
            detail=prompt[:2048],
            metadata={"url": url, "tool_use_id": block.get("id", "")},
        ))

    elif tool == "Agent":
        agent_type = inp.get("subagent_type", "unknown")
        description = inp.get("description", "")
        prompt = inp.get("prompt", "")
        events.append(ContextEvent(
            timestamp=timestamp,
            event_type="agent_output",
            source=f"agent:{agent_type}",
            symbols=_extract_symbols(prompt),
            summary=f"Agent [{agent_type}]: {description}",
            detail=prompt[:2048],
            metadata={"agent_type": agent_type, "description": description},
        ))

    elif tool == "Bash":
        cmd = inp.get("command", "")
        if "quick_trade.py" in cmd or "claude_execute.py" in cmd:
            events.append(ContextEvent(
                timestamp=timestamp,
                event_type="trade_execution",
                source="bash:trade",
                symbols=_extract_symbols(cmd),
                summary=f"Trade command: {cmd[:100]}",
                detail=cmd[:2048],
                metadata={"command": cmd},
            ))

    return events


def _extract_tool_result(block: dict, timestamp: datetime) -> list[ContextEvent]:
    """Extract events from tool_result blocks (e.g., search results)."""
    # Tool results are harder to parse consistently — skip for now.
    # The tool_use blocks capture intent; results can be backfilled later.
    return []


def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp string."""
    try:
        # Handle Z suffix
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).replace(tzinfo=None)
    except (ValueError, TypeError):
        return datetime.utcnow()


# Common stock symbol pattern
_SYMBOL_RE = re.compile(r'\b([A-Z]{1,5})\b')
_KNOWN_SYMBOLS = {
    "SLB", "HAL", "XLE", "XLF", "XLK", "USO", "GLD", "VIX", "SPY", "QQQ",
    "AAPL", "MSFT", "NVDA", "MU", "QCOM", "FCX", "LEN", "FRO", "INSW",
    "AXP", "UVXY", "VXX", "CEG", "VLO", "JPM", "WDC", "GOLD", "NEM",
    "LMT", "RTX", "NOC", "GD", "HII", "DFEN", "ITA",
    "URA", "LEU", "CCJ", "SMR", "OKLO", "NNE",
    "EUAD", "COPA", "EWZ", "BRT", "PBR",
}


def _extract_symbols(text: str) -> list[str]:
    """Extract stock symbols from text using known list."""
    if not text:
        return []
    found = _SYMBOL_RE.findall(text)
    return list(set(s for s in found if s in _KNOWN_SYMBOLS))


def link_events_to_decisions(events: list[ContextEvent], session_id: str) -> int:
    """Link extracted events to decisions made during the session (by timestamp proximity).

    Returns the number of events linked.
    """
    if not events:
        return 0

    try:
        from src.db.database import get_db
        from src.db.models import DecisionRecord
    except Exception as e:
        logger.error(f"Cannot import DB modules: {e}")
        return 0

    # Find the session time range
    session_start = min(e.timestamp for e in events)
    session_end = max(e.timestamp for e in events)

    # Expand window by 1 hour on each side
    session_start -= timedelta(hours=1)
    session_end += timedelta(hours=1)

    # Find decisions made during this time
    with get_db() as session:
        decisions = (
            session.query(DecisionRecord)
            .filter(
                DecisionRecord.timestamp >= session_start,
                DecisionRecord.timestamp <= session_end,
            )
            .all()
        )

        if not decisions:
            logger.info("No decisions found in session time range")
            return 0

        logger.info(f"Found {len(decisions)} decisions in session time range")

        # For each decision, find events within 30 minutes before it
        from src.db.write_api import athena_db
        linked = 0

        for dec in decisions:
            dec_time = dec.timestamp
            window_start = dec_time - timedelta(minutes=30)
            relevant = [
                e for e in events
                if window_start <= e.timestamp <= dec_time
                and (not e.symbols or dec.symbol in e.symbols or not dec.symbol)
            ]

            for event in relevant:
                try:
                    athena_db.log_event(
                        event_type=event.event_type,
                        source=event.source,
                        title=event.summary[:300],
                        detail=event.detail,
                        symbol=dec.symbol,
                        severity="info",
                        decision_id=dec.id,
                    )
                    linked += 1
                except Exception as exc:
                    logger.debug(f"Failed to link event: {exc}")

        return linked


def main():
    parser = argparse.ArgumentParser(description="Extract context from Claude Code transcripts")
    parser.add_argument("--session", help="Session ID to extract from")
    parser.add_argument("--list", action="store_true", help="List available sessions")
    parser.add_argument("--recent", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument("--link-decisions", action="store_true", help="Link events to decisions in DB")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if args.list:
        sessions = list_sessions(args.recent)
        print(f"\n{'Session ID':<40} {'Modified':<20} {'Size':>8}")
        print("-" * 72)
        for s in sessions:
            print(f"{s['session_id']:<40} {s['modified'][:16]:<20} {s['size_kb']:>6} KB")
        print(f"\n{len(sessions)} sessions in last {args.recent} days")
        return

    if not args.session:
        parser.error("--session required (or use --list to see available sessions)")

    events = extract_from_transcript(args.session)

    # Print summary
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1

    print(f"\nExtracted {len(events)} events from session {args.session}")
    print(f"\nBy type:")
    for t, c in sorted(by_type.items()):
        print(f"  {t}: {c}")

    if events:
        print(f"\nSymbols mentioned: {sorted(set(s for e in events for s in e.symbols))}")
        print(f"\nFirst 10 events:")
        for e in events[:10]:
            print(f"  [{e.event_type}] {e.summary[:80]}")

    if args.link_decisions:
        linked = link_events_to_decisions(events, args.session)
        print(f"\nLinked {linked} events to decisions in DB")


if __name__ == "__main__":
    main()
