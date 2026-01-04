#!/usr/bin/env python3
"""
Alpaca Credentials Setup and Test Script.

Sets up environment variables and tests connection to Alpaca paper trading.

Usage:
    python scripts/setup_alpaca.py
"""

import asyncio
import os
import sys
from pathlib import Path
from getpass import getpass

sys.path.insert(0, str(Path(__file__).parent.parent))

def get_credentials():
    """Prompt for credentials if not in environment."""
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key:
        print("\n" + "=" * 60)
        print("ALPACA PAPER TRADING SETUP")
        print("=" * 60)
        print("\nGet your paper trading keys from:")
        print("https://app.alpaca.markets/paper/api")
        print()
        api_key = input("Enter your Alpaca API Key: ").strip()

    if not secret_key:
        secret_key = getpass("Enter your Alpaca Secret Key: ").strip()

    return api_key, secret_key


async def test_connection(api_key: str, secret_key: str) -> bool:
    """Test connection to Alpaca."""
    print("\n" + "-" * 40)
    print("Testing connection...")
    print("-" * 40)

    try:
        from src.execution.broker.alpaca import AlpacaBroker

        broker = AlpacaBroker(
            api_key=api_key,
            secret_key=secret_key,
            paper=True,
        )

        connected = await broker.connect()

        if connected:
            print("[OK] Connected to Alpaca Paper Trading")

            # Get account info
            account = await broker.get_account()
            print(f"\n Account Info:")
            print(f"   Account ID: {account.account_id}")
            print(f"   Cash: ${float(account.cash):,.2f}")
            print(f"   Portfolio Value: ${float(account.portfolio_value):,.2f}")
            print(f"   Buying Power: ${float(account.buying_power):,.2f}")
            print(f"   Day Trade Count: {account.day_trade_count}")
            print(f"   PDT Status: {'Yes' if account.pattern_day_trader else 'No'}")

            # Get positions
            positions = await broker.get_positions()
            print(f"\n Positions: {len(positions)}")
            for symbol, pos in positions.items():
                print(f"   {symbol}: {pos.quantity} shares @ ${float(pos.entry_price):.2f}")

            await broker.disconnect()
            return True
        else:
            print("[FAIL] Could not connect to Alpaca")
            return False

    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def print_export_commands(api_key: str, secret_key: str):
    """Print shell export commands."""
    print("\n" + "=" * 60)
    print("ADD TO YOUR SHELL (~/.bashrc or ~/.zshrc):")
    print("=" * 60)
    print(f'\nexport ALPACA_API_KEY="{api_key}"')
    print(f'export ALPACA_SECRET_KEY="{secret_key}"')
    print('export ALPACA_PAPER="true"')
    print("\nThen run: source ~/.bashrc")
    print("=" * 60)


async def main():
    api_key, secret_key = get_credentials()

    if not api_key or not secret_key:
        print("Error: Both API key and secret key are required")
        sys.exit(1)

    success = await test_connection(api_key, secret_key)

    if success:
        print_export_commands(api_key, secret_key)
        print("\n[SUCCESS] Alpaca paper trading is ready!")
        print("\nTo run paper trading:")
        print("  python scripts/run_daily.py --mode paper")
    else:
        print("\n[FAILED] Please check your credentials and try again")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
