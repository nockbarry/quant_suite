#!/usr/bin/env python3
"""
2-hour market monitoring session with 10-minute intervals.
Outputs observations to stdout and logs to operator_log.jsonl
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monitoring.operator_loop import get_operator_loop


async def run_single_check(check_num: int, total_checks: int) -> dict:
    """Run a single monitoring check."""
    loop = get_operator_loop()

    print(f"\n{'='*60}")
    print(f"OPERATOR CHECK #{check_num}/{total_checks} - {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")

    try:
        observation = loop.operator_check()
        print(loop.format_observation(observation))

        # Check for urgent items
        if hasattr(observation, 'has_urgent_items') and observation.has_urgent_items():
            print("\n🚨 URGENT ITEMS DETECTED - ATTENTION REQUIRED")

        return observation.to_dict() if hasattr(observation, 'to_dict') else {}

    except Exception as e:
        print(f"Check error: {e}")
        # Fallback to manual checks
        return await manual_check(check_num)


async def manual_check(check_num: int) -> dict:
    """Fallback manual check if operator_loop fails."""
    from scripts.quick_trade import get_broker

    result = {
        'check_num': check_num,
        'timestamp': datetime.now().isoformat(),
        'alerts': [],
        'positions': {},
    }

    try:
        broker = get_broker()
        await broker.connect()

        # Get account
        account = await broker.get_account()
        equity = float(account.portfolio_value)
        result['equity'] = equity

        # Get positions
        positions = await broker.get_positions()

        print(f"\n📊 Portfolio: ${equity:,.2f}")

        # Calculate sector exposure
        energy_symbols = ['SLB', 'HAL', 'XLE', 'FRO', 'STNG', 'CNQ', 'PBF', 'BKR',
                        'PBR', 'PSX', 'IMO', 'DHT', 'OIH', 'XOP', 'MPC', 'INSW',
                        'ERX', 'GUSH', 'IEO', 'WFRD', 'KBR', 'FLR', 'PSN', 'J', 'SU']
        gold_symbols = ['GLD', 'GDX', 'NEM', 'GOLD', 'NUGT', 'UGL']

        energy_value = sum(float(p.market_value) for sym, p in positions.items()
                         if sym in energy_symbols)
        gold_value = sum(float(p.market_value) for sym, p in positions.items()
                        if sym in gold_symbols)
        total_value = sum(float(p.market_value) for p in positions.values())

        energy_pct = (energy_value / total_value * 100) if total_value > 0 else 0
        gold_pct = (gold_value / total_value * 100) if total_value > 0 else 0

        print(f"   Energy: ${energy_value:,.0f} ({energy_pct:.1f}%)")
        print(f"   Gold: ${gold_value:,.0f} ({gold_pct:.1f}%)")

        # Check alerts
        if energy_pct > 40:
            print(f"   ⚠️ ALERT: Energy concentration {energy_pct:.1f}% > 40%")
            result['alerts'].append({'type': 'concentration', 'sector': 'Energy', 'pct': energy_pct})

        # Top movers
        movers = sorted(positions.items(),
                       key=lambda x: float(x[1].unrealized_pnl_pct) if hasattr(x[1], 'unrealized_pnl_pct') else 0,
                       reverse=True)

        print("\n📈 Top Movers:")
        for sym, pos in movers[:3]:
            pnl_pct = float(pos.unrealized_pnl_pct) if hasattr(pos, 'unrealized_pnl_pct') else 0
            print(f"   {sym}: {pnl_pct:+.1f}%")

        print("\n📉 Bottom Movers:")
        for sym, pos in movers[-3:]:
            pnl_pct = float(pos.unrealized_pnl_pct) if hasattr(pos, 'unrealized_pnl_pct') else 0
            print(f"   {sym}: {pnl_pct:+.1f}%")

        await broker.disconnect()

    except Exception as e:
        print(f"Error in manual check: {e}")

    return result


async def check_signposts() -> list:
    """Check for signpost triggers."""
    alerts_dir = Path.home() / 'quant_results/alerts'
    today = datetime.now().strftime('%Y%m%d')

    alerts = []
    alert_file = alerts_dir / f'alerts_{today}.json'

    if alert_file.exists():
        with open(alert_file) as f:
            data = json.load(f)
            if isinstance(data, list):
                alerts = data
            else:
                alerts = [data]

    if alerts:
        print("\n🔔 SIGNPOST ALERTS:")
        for alert in alerts[:5]:
            symbol = alert.get('symbol', 'Unknown')
            desc = alert.get('description', alert.get('message', 'No description'))
            priority = alert.get('priority', 'medium')
            icon = '🔴' if priority == 'critical' else '🟡' if priority == 'high' else '⚪'
            print(f"   {icon} {symbol}: {desc}")

    return alerts


async def get_market_data() -> dict:
    """Get current market data."""
    import subprocess

    result = subprocess.run(
        ['python3', 'scripts/quick_trade.py', 'quote', 'SPY', 'QQQ', 'GLD', 'VIX'],
        capture_output=True, text=True, cwd='/home/nock/projects/quant_suite',
        env={'PYTHONPATH': '.'}
    )

    print("\n📊 Market Data:")
    for line in result.stdout.strip().split('\n')[:4]:
        if line.strip():
            print(f"   {line}")

    return {}


async def run_monitoring_session(interval_minutes: int = 10, total_checks: int = 12):
    """Run the full monitoring session."""

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           MARKET MONITORING SESSION ACTIVE                    ║
║                                                              ║
║  Interval: {interval_minutes} minutes                                        ║
║  Total Checks: {total_checks}                                            ║
║  Duration: {interval_minutes * total_checks / 60:.1f} hours                                          ║
╚══════════════════════════════════════════════════════════════╝
    """)

    for check_num in range(1, total_checks + 1):
        # Run check
        await run_single_check(check_num, total_checks)

        # Check signposts
        await check_signposts()

        # Get market data
        await get_market_data()

        # Log to file
        log_entry = {
            'check_num': check_num,
            'timestamp': datetime.now().isoformat(),
            'total_checks': total_checks,
        }

        log_file = Path.home() / 'quant_results/logs/operator_log.jsonl'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

        # Wait for next interval (unless last check)
        if check_num < total_checks:
            next_check = datetime.now() + timedelta(minutes=interval_minutes)
            print(f"\n⏰ Next check at {next_check.strftime('%H:%M:%S')} ({interval_minutes} min)")
            print("-" * 60)
            await asyncio.sleep(interval_minutes * 60)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           MONITORING SESSION COMPLETE                         ║
║                                                              ║
║  Checks Completed: {total_checks}                                        ║
║  End Time: {datetime.now().strftime('%H:%M:%S')}                                       ║
╚══════════════════════════════════════════════════════════════╝
    """)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=int, default=10, help='Check interval in minutes')
    parser.add_argument('--checks', type=int, default=12, help='Total number of checks')
    parser.add_argument('--single', action='store_true', help='Run single check only')
    args = parser.parse_args()

    if args.single:
        asyncio.run(run_single_check(1, 1))
    else:
        asyncio.run(run_monitoring_session(args.interval, args.checks))
