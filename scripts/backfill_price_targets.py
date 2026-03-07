#!/usr/bin/env python3
"""Backfill price targets for existing theses.

Generates a template with current prices for all active thesis vehicles,
showing suggested bull/base/bear targets based on simple heuristics.
Claude adjusts and commits real targets during trade-decision sessions.

Usage:
    PYTHONPATH=. python3 scripts/backfill_price_targets.py                    # Show all
    PYTHONPATH=. python3 scripts/backfill_price_targets.py --thesis-id abc123  # Single thesis
    PYTHONPATH=. python3 scripts/backfill_price_targets.py --json             # Output as JSON
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def get_current_prices() -> dict[str, float]:
    """Get current prices from state.json."""
    state_file = Path.home() / "quant_results" / "live" / "state.json"
    if not state_file.exists():
        return {}
    try:
        with open(state_file) as f:
            state = json.load(f)
        return {
            p["symbol"]: p.get("current_price", 0)
            for p in state.get("positions", [])
            if p.get("symbol") and p.get("current_price", 0) > 0
        }
    except Exception:
        return {}


def suggest_targets(current_price: float, conviction: float) -> dict:
    """Generate suggested price targets based on conviction and current price.

    Higher conviction = wider bull target, tighter bear target.
    These are rough suggestions — Claude should adjust based on thesis specifics.
    """
    # Conviction-scaled ranges
    bull_pct = 0.15 + (conviction / 100) * 0.20  # 15-35% upside
    base_pct = 0.08 + (conviction / 100) * 0.10  # 8-18% upside
    bear_pct = 0.10 + ((100 - conviction) / 100) * 0.15  # 10-25% downside

    return {
        "bull_target": round(current_price * (1 + bull_pct), 2),
        "base_target": round(current_price * (1 + base_pct), 2),
        "bear_target": round(current_price * (1 - bear_pct), 2),
        "entry_price": round(current_price, 2),
        "timeframe_days": 90,
        "notes": "Auto-suggested — adjust based on thesis specifics",
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill price targets for theses")
    parser.add_argument("--thesis-id", help="Single thesis ID to process")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    from src.knowledge.thesis import ThesisTracker
    from src.core.paths import paths

    tracker = ThesisTracker(paths.theses)
    prices = get_current_prices()

    if args.thesis_id:
        theses = [tracker.get_thesis(args.thesis_id)]
        theses = [t for t in theses if t]
    else:
        theses = [t for t in tracker.get_all_theses() if t.status == "active"]

    all_targets = {}
    for thesis in sorted(theses, key=lambda t: -t.conviction):
        existing_targets = thesis.price_targets
        missing = [s for s in thesis.positions if s not in existing_targets]
        has_price = [s for s in thesis.positions if s in prices]

        if not args.json:
            symbol_status = []
            for s in thesis.positions:
                has_tgt = "T" if s in existing_targets else "-"
                has_px = "P" if s in prices else "-"
                symbol_status.append(f"{s}({has_tgt}{has_px})")

            print(f"\n{'='*60}")
            print(f"Thesis: {thesis.name} ({thesis.id[:8]})")
            print(f"Conviction: {thesis.conviction:.0f}% | Vehicles: {' '.join(symbol_status)}")
            print(f"Existing targets: {len(existing_targets)} | Missing: {len(missing)}")

        thesis_targets = {}
        for sym in thesis.positions:
            current = prices.get(sym)
            if not current:
                if not args.json:
                    print(f"  {sym:6} — no current price (not in portfolio?)")
                continue

            if sym in existing_targets:
                pt = existing_targets[sym]
                if not args.json:
                    progress = pt.progress_pct(current)
                    print(f"  {sym:6} current=${current:>8.2f}  bear=${pt.bear_target:>8.2f}  base=${pt.base_target:>8.2f}  bull=${pt.bull_target:>8.2f}  progress={progress:>5.1f}%")
            else:
                suggested = suggest_targets(current, thesis.conviction)
                thesis_targets[sym] = suggested
                if not args.json:
                    print(f"  {sym:6} current=${current:>8.2f}  SUGGESTED: bear=${suggested['bear_target']:>8.2f}  base=${suggested['base_target']:>8.2f}  bull=${suggested['bull_target']:>8.2f}")

        if thesis_targets:
            all_targets[thesis.id] = {
                "thesis_name": thesis.name,
                "conviction": thesis.conviction,
                "targets": thesis_targets,
            }

    if args.json:
        print(json.dumps(all_targets, indent=2))
    else:
        # Summary
        total_missing = sum(len(t["targets"]) for t in all_targets.values())
        total_existing = sum(len(t.price_targets) for t in theses)
        total_vehicles = sum(len(t.positions) for t in theses)
        print(f"\n{'='*60}")
        print(f"Summary: {total_existing}/{total_vehicles} vehicles have targets, {total_missing} need targets")
        if total_missing:
            print(f"\nTo set targets, use tracker.set_price_targets() in a /trade-decision session.")
            print(f"Or run with --json to get a template you can edit and apply.")


if __name__ == "__main__":
    main()
