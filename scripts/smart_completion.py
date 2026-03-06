#!/usr/bin/env python3
"""Smart completion fallback — extracts findings from actual session outputs.

Called by session_wrapper.sh when Claude didn't write an enriched completion record.
Instead of writing empty arrays, this reads actual outputs (DB, files, logs) and
populates key_findings and symbols from what the session actually produced.

Usage:
    python3 scripts/smart_completion.py <session_type> <start_timestamp> [log_file]

    start_timestamp: ISO format or epoch seconds
    Writes to ~/quant_results/scheduler/completions/{session_type}_{timestamp}.json
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [smart_completion] %(message)s")
logger = logging.getLogger(__name__)

RESULTS_DIR = Path.home() / "quant_results"
COMPLETIONS_DIR = RESULTS_DIR / "scheduler" / "completions"


def extract_trade_decision(start_time: datetime) -> tuple[list[str], list[str], str]:
    """Extract findings from trade-decision session: read today's decisions from DB."""
    findings, symbols = [], []
    try:
        from src.db.database import get_db, init_db
        from src.db.models import DecisionRecord

        init_db()
        with get_db() as session:
            decisions = session.query(DecisionRecord).filter(
                DecisionRecord.timestamp >= start_time
            ).order_by(DecisionRecord.timestamp).all()

            for d in decisions:
                symbols.append(d.symbol)
                pnl = ""
                if d.realized_pnl_pct is not None:
                    pnl = f" (P&L: {d.realized_pnl_pct:+.1f}%)"
                findings.append(
                    f"{d.action} {d.symbol} @ {d.confidence:.0%} conf — "
                    f"{(d.reasoning or '')[:100]}{pnl}"
                )

        summary = f"Generated {len(decisions)} trade decisions: {', '.join(symbols)}" if decisions else "No decisions generated"
    except Exception as e:
        summary = f"Trade decision extraction failed: {e}"

    return findings, list(dict.fromkeys(symbols)), summary


def extract_morning_briefing(start_time: datetime) -> tuple[list[str], list[str], str]:
    """Extract findings from morning briefing: read today's briefing file."""
    findings, symbols = [], []
    today = start_time.strftime("%Y%m%d")

    # Check for briefing file
    briefing_file = RESULTS_DIR / "briefings" / f"briefing_{today}.json"
    briefing_md = RESULTS_DIR / "briefings" / f"briefing_{today}.md"

    if briefing_file.exists():
        try:
            with open(briefing_file) as f:
                data = json.load(f)
            symbols = data.get("symbols", data.get("watchlist", []))
            if isinstance(symbols, list) and symbols and isinstance(symbols[0], dict):
                symbols = [s.get("symbol", "") for s in symbols]
            for section in ["key_themes", "thesis_updates", "alerts", "key_findings"]:
                items = data.get(section, [])
                if isinstance(items, list):
                    for item in items[:5]:
                        if isinstance(item, str):
                            findings.append(item)
                        elif isinstance(item, dict):
                            findings.append(item.get("summary", item.get("title", str(item)))[:150])
        except Exception:
            pass

    if briefing_md.exists() and not findings:
        try:
            text = briefing_md.read_text()
            import re
            # Look for explicit ticker patterns: $AAPL, **AAPL**, or known watchlist tickers
            explicit = re.findall(r'\$([A-Z]{1,5})\b', text)
            bold = re.findall(r'\*\*([A-Z]{1,5})\*\*', text)
            # Also match uppercase words but require 2-5 chars and adjacent to price/pct context
            contextual = re.findall(r'\b([A-Z]{2,5})\b(?=\s+(?:up|down|at|@|\$|\+|-))', text)
            raw_syms = explicit + bold + contextual
            # Still filter obvious non-tickers
            noise = {"THE", "AND", "FOR", "THIS", "THAT", "WITH", "FROM", "BUT", "NOT",
                     "ARE", "WAS", "HAS", "HAD", "WILL", "CAN", "ALL", "NEW", "NOW",
                     "ONE", "TWO", "OUR", "ITS", "MAY", "KEY", "PM", "AM", "ET", "USD",
                     "YOY", "QOQ", "MOM", "EPS", "GDP", "CPI", "BPS", "ATH", "IPO",
                     "CEO", "CFO", "COO", "ETF", "SEC", "DOJ", "FTC", "FDA", "EPA",
                     "TOP", "TO", "UP", "AT", "ON", "IF", "OR", "NO", "SO", "BE", "BY",
                     "DO", "IN", "WE", "AS", "AN", "OF", "MARKET", "WATCH", "TODAY",
                     "CRITICAL", "SNAPSHOT", "ALERT", "NOTE", "ALSO", "SEE", "TBD",
                     "HOLD", "BUY", "SELL", "LONG", "SHORT", "OPEN", "HIGH", "LOW",
                     "CLOSE", "RISK", "STOP", "LOSS", "GAIN", "MOVE", "DROP", "RISE",
                     "YEAR", "WEEK", "NEXT", "LAST", "OVER", "VERY", "JUST", "MORE",
                     "MUCH", "THAN", "BACK", "BEEN", "EACH", "SOME", "WHEN", "WHAT",
                     "THEM", "THEN", "TAKE", "LIKE", "MAKE", "INTO", "ONLY"}
            symbols = list(dict.fromkeys(s for s in raw_syms if s not in noise))[:20]
            # Extract first few heading lines as findings
            for line in text.split("\n"):
                if line.startswith("##") and len(findings) < 5:
                    findings.append(line.lstrip("#").strip()[:150])
        except Exception:
            pass

    summary = f"Morning briefing with {len(findings)} findings, {len(symbols)} symbols"
    return findings[:10], symbols[:20], summary


def extract_operator(start_time: datetime) -> tuple[list[str], list[str], str]:
    """Extract findings from operator session: read operator log entries."""
    findings, symbols = [], []
    log_file = RESULTS_DIR / "logs" / "operator_log.jsonl"

    if not log_file.exists():
        return findings, symbols, "No operator log found"

    alerts, checks = 0, 0
    social_signals_seen = set()
    try:
        with open(log_file) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                ts_str = entry.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    continue

                if ts < start_time:
                    continue

                checks += 1
                alerts += entry.get("alert_count", 0)

                # Collect symbols from alerts
                for alert in entry.get("alerts", []):
                    sym = alert.get("symbol", "")
                    if sym:
                        symbols.append(sym)
                    findings.append(f"ALERT: {alert.get('message', str(alert))[:120]}")

                # Collect social signals
                for sig in entry.get("social_signals", []):
                    sym = sig.get("symbol", "")
                    if sym and sym not in social_signals_seen:
                        social_signals_seen.add(sym)
                        symbols.append(sym)
                        sig_type = sig.get("type", "signal")
                        if sig_type == "wsb_signal":
                            findings.append(f"WSB: {sym} phase={sig.get('phase','')} mentions={sig.get('mentions',0)}")
                        elif sig_type == "thesis_suggestion":
                            findings.append(f"Thesis suggestion: {sym} — {sig.get('name','')}")
    except Exception:
        pass

    summary = f"Operator: {checks} checks, {alerts} alerts, {len(social_signals_seen)} social signals"
    return findings[:15], list(dict.fromkeys(symbols))[:20], summary


def extract_signal_scan(start_time: datetime) -> tuple[list[str], list[str], str]:
    """Extract findings from signal-scan session: read latest_scan.json + completions."""
    findings, symbols = [], []
    scan_file = RESULTS_DIR / "social" / "latest_scan.json"

    if scan_file.exists():
        try:
            with open(scan_file) as f:
                scan = json.load(f)

            wsb = scan.get("wsb", {})
            for sig in wsb.get("signals", [])[:5]:
                sym = sig.get("symbol", "")
                symbols.append(sym)
                findings.append(
                    f"WSB: {sym} ({sig.get('phase','')}) "
                    f"mentions={sig.get('mentions',0)} sentiment={sig.get('sentiment',0):+.2f}"
                )

            suggestions = scan.get("suggestions", {})
            for sug in suggestions.get("suggestions", [])[:3]:
                sym = sug.get("symbol", "")
                symbols.append(sym)
                findings.append(
                    f"Thesis suggestion: {sym} — {sug.get('name','')} "
                    f"({sug.get('direction','')}, {sug.get('signal_count',0)} signals)"
                )

            news = scan.get("news", {})
            if news.get("status") == "stale":
                findings.append(f"NEWS STALE: {news.get('age_hours', 0):.1f}h old")
        except Exception:
            pass

    summary = f"Signal scan: {len(findings)} findings, {len(symbols)} symbols tracked"
    return findings[:10], list(dict.fromkeys(symbols))[:20], summary


def extract_eod_review(start_time: datetime) -> tuple[list[str], list[str], str]:
    """Extract findings from EOD review: read today's review file."""
    findings, symbols = [], []
    today = start_time.strftime("%Y%m%d")

    review_file = RESULTS_DIR / "eod_reviews" / f"review_{today}.json"
    if review_file.exists():
        try:
            with open(review_file) as f:
                data = json.load(f)
            symbols = data.get("symbols_reviewed", [])
            for learning in data.get("learnings", [])[:5]:
                if isinstance(learning, str):
                    findings.append(learning[:150])
                elif isinstance(learning, dict):
                    findings.append(learning.get("insight", str(learning))[:150])
            for rec in data.get("recommendations", [])[:3]:
                if isinstance(rec, str):
                    findings.append(f"REC: {rec[:120]}")
        except Exception:
            pass

    summary = f"EOD review: {len(findings)} learnings, {len(symbols)} symbols reviewed"
    return findings[:10], list(dict.fromkeys(symbols))[:20], summary


EXTRACTORS = {
    "trade-decision": extract_trade_decision,
    "morning-briefing": extract_morning_briefing,
    "operator": extract_operator,
    "signal-scan": extract_signal_scan,
    "eod-review": extract_eod_review,
    "research": extract_signal_scan,  # Research reads same scan data
    "thesis": extract_morning_briefing,  # Thesis review reads similar data
    "brainstorm": extract_signal_scan,
    "internal-review": extract_eod_review,  # Review reads similar evaluation data
}


def main():
    if len(sys.argv) < 3:
        print("Usage: smart_completion.py <session_type> <start_timestamp> [log_file]")
        sys.exit(1)

    session_type = sys.argv[1]
    start_ts = sys.argv[2]
    log_file = sys.argv[3] if len(sys.argv) > 3 else ""

    # Parse start time
    try:
        if start_ts.isdigit():
            start_time = datetime.fromtimestamp(int(start_ts))
        else:
            start_time = datetime.fromisoformat(start_ts)
    except (ValueError, TypeError):
        start_time = datetime.now() - timedelta(hours=1)

    # Check if enriched record already exists (written by Claude during session)
    existing = sorted(COMPLETIONS_DIR.glob(f"{session_type}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if existing:
        newest = existing[0]
        if newest.stat().st_mtime > start_time.timestamp():
            # Check if it has actual findings
            try:
                with open(newest) as f:
                    record = json.load(f)
                if record.get("key_findings"):
                    logger.info(f"Enriched completion already exists: {newest.name}")
                    return
            except Exception:
                pass

    # Extract findings using appropriate extractor
    extractor = EXTRACTORS.get(session_type)
    if extractor:
        findings, symbols, summary = extractor(start_time)
    else:
        findings, symbols, summary = [], [], f"Session {session_type} completed"

    if not findings:
        summary = f"Session {session_type} completed (no extractable findings)"

    # Compute duration
    duration = int((datetime.now() - start_time).total_seconds())

    # Write completion record
    COMPLETIONS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    filename = f"{session_type}_{now.strftime('%Y%m%d_%H%M%S')}.json"

    record = {
        "session_type": session_type,
        "success": True,
        "summary": summary,
        "key_findings": findings,
        "symbols": symbols,
        "duration_seconds": duration,
        "completed_at": now.isoformat(),
        "log_file": log_file,
        "source": "smart_completion",
    }

    with open(COMPLETIONS_DIR / filename, "w") as f:
        json.dump(record, f, indent=2)

    logger.info(f"Wrote completion: {filename} ({len(findings)} findings, {len(symbols)} symbols)")

    # Also log to ProcessEvent
    try:
        from src.autonomy.provenance import log_event
        log_event(
            "session_completed",
            source=f"scheduler:{session_type}",
            title=f"Session {session_type}: {summary[:200]}",
            detail={"key_findings": findings, "symbols": symbols},
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
