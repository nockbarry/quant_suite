#!/usr/bin/env python3
"""Operator poll helper — emits one-line status for the monitor loop."""
import sys
import json
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["poll", "full", "ccj"])
    args = parser.parse_args()

    if args.mode == "poll":
        import os
        from pathlib import Path
        from src.monitoring.operator_loop import get_operator_loop

        # File-based dedup for news headlines (survives fresh instances)
        seen_file = Path.home() / "quant_results/logs/operator_seen_headlines.txt"
        seen_headlines: set[str] = set()
        if seen_file.exists():
            # Purge stale entries older than today
            today = __import__("datetime").date.today().isoformat()
            lines = seen_file.read_text().splitlines()
            valid = [l for l in lines if l.startswith(today)]
            seen_headlines = {l.split("|", 1)[1] for l in valid if "|" in l}

        loop = get_operator_loop()
        # Pre-populate seen set so lightweight_poll skips already-seen headlines
        loop._seen_urgency_headlines = seen_headlines
        poll = loop.lightweight_poll()

        # Persist any newly seen headlines
        new_seen = loop._seen_urgency_headlines - seen_headlines
        if new_seen:
            today = __import__("datetime").date.today().isoformat()
            with open(seen_file, "a") as f:
                for h in new_seen:
                    f.write(f"{today}|{h}\n")

        has_events = bool(poll.get("events"))
        poll["has_events"] = has_events
        print(json.dumps(poll))

    elif args.mode == "full":
        from src.monitoring.operator_loop import get_operator_loop
        loop = get_operator_loop()
        obs = loop.operator_check()
        alert_count = len(obs.alerts) if obs.alerts else 0
        action_count = len(obs.action_items) if obs.action_items else 0
        conv_count = len(obs.convergences) if obs.convergences else 0
        urgent = obs.has_urgent_items()
        ai = obs.action_items[0] if obs.action_items else None
        trigger = (f"{ai.category}:{ai.symbol}" if ai else "none")[:80]
        print(f"alerts={alert_count} actions={action_count} convs={conv_count} urgent={urgent} trigger={trigger}")

    elif args.mode == "ccj":
        from src.synthesis.state import UnifiedState
        from src.core.paths import paths
        state = UnifiedState.load(paths.live_state)
        for p in state.positions:
            if p.symbol == "CCJ":
                gap = (p.current_price - 98.07) / 98.07 * 100
                pnl = (p.current_price - p.avg_cost) / p.avg_cost * 100
                print(f"CCJ {p.current_price:.2f} pnl={pnl:+.1f}% stop_gap={gap:.1f}%")
                return
        print("CCJ not found")

if __name__ == "__main__":
    main()
