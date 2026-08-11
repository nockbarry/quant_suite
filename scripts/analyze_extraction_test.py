"""Analyze the results of a live ingest+extraction test.

For each new SignalProvenance with source=EARNINGS_CALL, prints:
  - The signal direction/magnitude/confidence
  - The verbatim quote that survived the anti-hallucination guard
  - The route_signal decision (UPDATE_CONVICTION / ADD_TO_THESIS / CREATE_NEW)

Then runs ThesisSuggester.generate_suggestions() and lists what would be
auto-created vs what's queued for review.

Usage:
    PYTHONPATH=. python3 scripts/analyze_extraction_test.py
    PYTHONPATH=. python3 scripts/analyze_extraction_test.py --since 2026-04-26
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from src.core.paths import paths
from src.knowledge.signal_provenance import (
    SignalSource,
    get_provenance_tracker,
)
from src.knowledge.thesis_suggester import ThesisSuggester, RouteAction


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", help="Only signals created on/after this ISO date")
    parser.add_argument("--source", default="earnings_call",
                        help="SignalSource value (default earnings_call)")
    args = parser.parse_args()

    if args.since:
        cutoff = datetime.fromisoformat(args.since)
    else:
        # Default: last 24 hours (the test run)
        cutoff = datetime.now() - timedelta(hours=24)

    tracker = get_provenance_tracker()
    suggester = ThesisSuggester()

    target_source = SignalSource(args.source)
    signals = [
        s for s in tracker._cache.values()
        if s.source == target_source and s.created_at >= cutoff
    ]
    signals.sort(key=lambda s: (s.symbol, s.created_at))

    print(f"\n=== {len(signals)} {target_source.value} signals since {cutoff.date()} ===\n")

    by_action: dict[str, int] = {}
    by_symbol: dict[str, list] = {}
    for sig in signals:
        by_symbol.setdefault(sig.symbol, []).append(sig)

    for symbol, sigs in sorted(by_symbol.items()):
        print(f"\n--- {symbol} ({len(sigs)} signal{'s' if len(sigs) > 1 else ''}) ---")
        for sig in sigs:
            quote = sig.metadata.get("exact_quote", "")
            magnitude = sig.metadata.get("magnitude", "?")
            yoy = sig.metadata.get("yoy_change_pct")
            yoy_str = f" yoy={yoy:+.0f}%" if yoy is not None else ""

            print(
                f"  {sig.signal_id} | {sig.initial_direction:7} | {magnitude:8} | "
                f"conf={sig.initial_confidence:.2f}{yoy_str}"
            )
            print(f"    desc: {sig.initial_description[:140]}")
            if quote:
                print(f"    quote: {quote[:140]!r}")

            # Route this signal
            routed = suggester.route_signal(sig)
            by_action[routed.action] = by_action.get(routed.action, 0) + 1
            tag = {
                RouteAction.UPDATE_CONVICTION: "→ UPDATE",
                RouteAction.ADD_TO_THESIS: "→ ADD",
                RouteAction.CREATE_NEW: "→ NEW",
            }.get(routed.action, routed.action)
            thesis_part = f" thesis={routed.thesis_name!r}" if routed.thesis_name else ""
            print(f"    {tag}{thesis_part}  reason: {routed.reason[:100]}")

    # Routing distribution
    print(f"\n=== Routing distribution ===")
    for action, count in sorted(by_action.items()):
        print(f"  {action}: {count}")

    # Convergences (only those including at least one earnings_call signal —
    # filters out the noise of pure-statistical accumulated-history convergences).
    print(f"\n=== ThesisSuggester.find_convergences() — filtered to earnings_call ===")
    convergences = suggester.find_convergences(max_age_days=30)
    relevant = []
    for (sym, direction), sigs in convergences.items():
        if any(s.source.value == "earnings_call" for s in sigs):
            relevant.append((sym, direction, sigs))
    if not relevant:
        print("  (no convergences include earnings_call)")
    else:
        for sym, direction, sigs in sorted(relevant):
            unique_roots = {(s.root_signal_id or s.signal_id) for s in sigs}
            sources = sorted({s.source.value for s in sigs})
            print(f"  ({sym!r}, {direction!r}): {len(sigs)} signals, {len(unique_roots)} unique roots, sources={sources}")

    # Suggestions
    print(f"\n=== Pending thesis suggestions ===")
    pending = suggester.get_pending_suggestions()
    if not pending:
        print("  (none)")
    else:
        for s in pending:
            print(f"  {s.symbol}: {s.suggested_name!r}  confidence={s.confidence_score:.2f}  count={s.signal_count}")

    # Failure log inspection (verbatim guard catches)
    failure_log = paths.logs / "extraction_failures.jsonl"
    if failure_log.exists():
        recent_failures = []
        for line in failure_log.read_text().splitlines():
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["failed_at"])
                if ts >= cutoff:
                    recent_failures.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        if recent_failures:
            print(f"\n=== {len(recent_failures)} extraction failures in window ===")
            by_reason: dict[str, int] = {}
            for f in recent_failures:
                reason = f.get("reason", "unknown")
                by_reason[reason] = by_reason.get(reason, 0) + 1
            for reason, n in sorted(by_reason.items(), key=lambda x: -x[1]):
                print(f"  {reason}: {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
