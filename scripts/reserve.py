#!/usr/bin/env python3
"""Manage named cash reserves (dry powder) for the declarative portfolio.

Reserves hold cash back from auto-deployment for a specific catalyst, with an
expiry after which the cash auto-deploys. Formalizes intentional dry powder
(e.g. holding for an IPO or an FOMC decision) instead of letting cash sit idle
as an unaccountable residual.

    python3 scripts/reserve.py list
    python3 scripts/reserve.py add --name SpaceX-IPO --pct 0.20 \
        --catalyst "SpaceX IPO deploy gate" --expiry 2026-06-15
    python3 scripts/reserve.py remove --name SpaceX-IPO
    python3 scripts/reserve.py band --min 0.80 --max 0.95

The builder reads this policy each morning (scripts/cron_build_target.py).
"""

import argparse
import sys
from datetime import date


def _print_policy(cp) -> None:
    today = date.today()
    lo, hi = cp.target_invested_band
    print(f"Invested band: {lo:.0%}–{hi:.0%}   "
          f"reserves held: {cp.named_reserve_pct(today):.1%}   "
          f"effective max invested: {cp.max_invested(today):.0%}")
    if not cp.reserves:
        print("  (no reserves)")
        return
    for r in cp.reserves:
        status = "ACTIVE" if r.active(today) else "EXPIRED"
        print(f"  [{status}] {r.name:18} {r.target_pct:5.1%}  exp {r.expiry}  — {r.catalyst}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage portfolio cash reserves")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="show current cash policy + reserves")

    a = sub.add_parser("add", help="add or update a named reserve")
    a.add_argument("--name", required=True)
    a.add_argument("--pct", type=float, required=True, help="fraction of equity, 0-1")
    a.add_argument("--catalyst", default="")
    a.add_argument("--expiry", required=True, help="YYYY-MM-DD; auto-deploys after")
    a.add_argument("--thesis-id", default=None)

    rm = sub.add_parser("remove", help="remove a named reserve")
    rm.add_argument("--name", required=True)

    bd = sub.add_parser("band", help="set the target invested band")
    bd.add_argument("--min", type=float, required=True)
    bd.add_argument("--max", type=float, required=True)

    args = parser.parse_args()

    from src.portfolio.store import load_cash_policy, save_cash_policy
    from src.portfolio.target import Reserve

    cp = load_cash_policy()

    if args.cmd == "list":
        _print_policy(cp)
        return 0

    if args.cmd == "add":
        if not (0.0 <= args.pct <= 1.0):
            print("--pct must be a fraction 0-1")
            return 1
        cp.reserves = [r for r in cp.reserves if r.name != args.name]
        cp.reserves.append(Reserve(
            name=args.name, target_pct=args.pct, catalyst=args.catalyst,
            expiry=date.fromisoformat(args.expiry), thesis_id=args.thesis_id,
        ))
        save_cash_policy(cp)
        print(f"Added reserve '{args.name}' ({args.pct:.0%} until {args.expiry}).")
        _print_policy(cp)
        return 0

    if args.cmd == "remove":
        before = len(cp.reserves)
        cp.reserves = [r for r in cp.reserves if r.name != args.name]
        save_cash_policy(cp)
        print(f"Removed '{args.name}'." if len(cp.reserves) < before else f"No reserve '{args.name}'.")
        _print_policy(cp)
        return 0

    if args.cmd == "band":
        cp.target_invested_band = (args.min, args.max)
        save_cash_policy(cp)
        print(f"Set invested band to {args.min:.0%}–{args.max:.0%}.")
        _print_policy(cp)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
