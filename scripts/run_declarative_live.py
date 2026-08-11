#!/usr/bin/env python3
"""Run the declarative portfolio system LIVE on one isolated paper account.

Self-contained (no state.json dependency): pulls equity/positions/prices from
the broker, builds a TargetPortfolio from the shared theses, and reconciles the
account toward it. Designed to run a SECOND paper account (e.g. ATHENA_INSTANCE=
beta) in parallel with — and fully isolated from — the existing default system.

Isolation contract (set these in the environment):
    ATHENA_INSTANCE=beta            -> selects config/credentials_beta.yaml
    QUANT_RESULTS_DIR=~/quant_results_beta  -> isolated DB / target snapshots

Theses (beliefs) are intentionally SHARED with the default system via a symlink
(~/quant_results_beta/theses -> ~/quant_results/theses) so this is a clean A/B:
same beliefs, two execution strategies, two accounts.

    python3 scripts/run_declarative_live.py --shadow   # plan only (default)
    python3 scripts/run_declarative_live.py --live      # submit orders
"""

import argparse
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("declarative-live")


async def main_async(live: bool) -> int:
    from scripts.quick_trade import get_broker
    from src.core.events import emit
    from src.core.instance import InstanceConfig
    from src.db.database import init_db
    from src.knowledge.thesis import ThesisTracker
    from src.portfolio.adjustments import compute_rule_adjustments
    from src.portfolio.builder import TargetPortfolioBuilder
    from src.portfolio.calibration_bound import get_calibration_bound
    from src.portfolio.reconciler import Reconciler
    from src.portfolio.store import load_cash_policy, save_target

    instance = InstanceConfig.instance_name()
    mode = "LIVE" if live else "SHADOW"
    logger.info(f"=== Declarative run: instance={instance} mode={mode} ===")

    init_db()  # creates portfolio tables in THIS instance's DB

    broker = get_broker(paper=True)
    await broker.connect()
    try:
        # Market-hours guard: never submit live on stale after-hours quotes
        # (the MU over-buy happened on a midnight run with a $52 stale print).
        market_open = True
        try:
            market_open = bool(broker._trading_client.get_clock().is_open)
        except Exception as e:
            logger.warning(f"Could not read market clock ({e})")
        if live and not market_open:
            logger.warning("Market CLOSED — refusing to submit live orders. Re-run during market hours.")
            return 0

        account = await broker.get_account()
        equity = float(account.portfolio_value)
        cash = float(account.cash)
        positions = await broker.get_positions()

        current_values, pos_dicts = {}, []
        for sym, p in positions.items():
            s = str(sym)
            current_values[s] = float(p.market_value)
            try:
                pos_dicts.append({"symbol": s, "unrealized_pnl_pct": float(p.unrealized_pnl_pct)})
            except Exception:
                pass

        # Build target from SHARED theses + this instance's cash policy
        tracker = ThesisTracker()
        cash_policy = load_cash_policy()

        # Event-driven reserves: auto-hold cash into binary macro events
        # (FOMC etc), merged with any manually-set reserves (manual wins on
        # name collision). Expired reserves auto-deploy.
        from src.portfolio.event_reserves import merge_event_reserves
        merge_event_reserves(cash_policy)

        adjustments = compute_rule_adjustments(pos_dicts)
        if adjustments:
            logger.info(f"Stop-loss adjustments: {[a.symbol for a in adjustments]}")

        from src.portfolio.clusters import compute_clusters
        from src.portfolio.ranking import load_ranking
        vehicle_universe = sorted({
            s for t in tracker.get_active_theses() for s in (t.positions or [])
        })
        clusters = compute_clusters(vehicle_universe)
        ranking = load_ranking()

        target = TargetPortfolioBuilder(tracker, cash_policy=cash_policy).build(
            equity=equity, extra_adjustments=adjustments,
            calibration_bound=get_calibration_bound(),
            correlation_clusters=clusters, ranking=ranking,
        )
        tid = save_target(target, source=f"live_runner:{instance}")

        # Robust prices via bid/ask MID for EVERY symbol in the plan universe
        # (held + target). Falls back to the position's last price only if no
        # two-sided quote exists; a symbol with no usable price is skipped.
        prices = {}
        universe = set(current_values) | set(target.weights)
        quotes = await broker.get_quotes(list(universe))
        for sym in universe:
            q = (quotes or {}).get(sym)
            px = Reconciler.safe_price(q) if q else None
            if px is None and sym in positions:
                px = float(positions[sym].current_price)  # fallback for held
            if px and px > 0:
                prices[sym] = px

        reconciler = Reconciler()
        orders = reconciler.plan(
            target, current_values=current_values, equity=equity, prices=prices,
            available_cash=cash,
        )

        logger.info(
            f"[{instance}/{mode}] equity=${equity:,.0f} "
            f"target invested={target.invested_pct():.0%} "
            f"current invested={sum(current_values.values())/equity:.0%}"
        )
        if not orders:
            logger.info("Already at target — no orders.")
        for o in orders:
            logger.info(f"  {o.side.upper():4} {o.symbol:6} x{o.qty:<5} ~${o.notional:9,.0f}  [{o.reason}]")

        await reconciler.execute(orders, broker, target_id=tid, dry_run=not live)

        submitted = [o for o in orders if o.status == "submitted"]
        emit(
            "declarative_instance_run",
            source="run_declarative_live",
            severity="info",
            title=f"{instance}/{mode}: {len(orders)} planned, {len(submitted)} submitted",
            detail={"instance": instance, "mode": mode.lower(), "target_id": tid,
                    "planned": len(orders), "submitted": len(submitted)},
        )
        logger.info(f"[{instance}/{mode}] done — {len(submitted)} orders submitted, "
                    f"{len(orders) - len(submitted)} planned/skipped.")
    finally:
        try:
            await broker.disconnect()
        except Exception:
            pass
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Run declarative system live on one paper account")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--shadow", action="store_true", help="plan only, submit nothing (default)")
    g.add_argument("--live", action="store_true", help="submit orders to the broker")
    args = p.parse_args()
    return asyncio.run(main_async(live=args.live))


if __name__ == "__main__":
    sys.exit(main())
