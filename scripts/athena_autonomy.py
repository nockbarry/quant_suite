#!/usr/bin/env python3
"""Athena Autonomy Event Loop — entry point for systemd service.

Usage:
    PYTHONPATH=. python3 scripts/athena_autonomy.py
    PYTHONPATH=. python3 scripts/athena_autonomy.py --dry-run
    PYTHONPATH=. python3 scripts/athena_autonomy.py --interval 5
"""

import argparse
import asyncio
import signal
import sys

from src.autonomy.config import load_autonomy_config
from src.autonomy.event_loop import AthenaEventLoop


def main():
    parser = argparse.ArgumentParser(description="Athena Autonomy Event Loop")
    parser.add_argument("--dry-run", action="store_true", help="Run without executing trades")
    parser.add_argument("--interval", type=int, help="Check interval in minutes")
    args = parser.parse_args()

    config = load_autonomy_config()

    if args.dry_run:
        config.execution.dry_run = True
    if args.interval:
        config.event_loop.check_interval_minutes = args.interval

    loop = AthenaEventLoop(config)

    # Handle signals for graceful shutdown
    def shutdown_handler(signum, frame):
        loop.stop()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    print(f"Starting Athena Autonomy Loop")
    print(f"  Interval: {config.event_loop.check_interval_minutes} min")
    print(f"  Dry run: {config.execution.dry_run}")
    print(f"  LLM model: {config.llm.model}")
    print(f"  Execution authority: {config.execution.authority}")

    asyncio.run(loop.run())


if __name__ == "__main__":
    main()
