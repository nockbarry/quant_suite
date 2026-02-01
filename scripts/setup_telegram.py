#!/usr/bin/env python3
"""Telegram Setup Helper - Configure Telegram alerts for Project Athena.

This script helps you:
1. Test if your bot token is valid
2. Get your chat ID
3. Send a test message
4. Update the config file

Usage:
    # Get your chat ID (after starting chat with bot)
    PYTHONPATH=. python3 scripts/setup_telegram.py --get-chat-id YOUR_BOT_TOKEN

    # Test sending a message
    PYTHONPATH=. python3 scripts/setup_telegram.py --test YOUR_BOT_TOKEN YOUR_CHAT_ID

    # Configure the system
    PYTHONPATH=. python3 scripts/setup_telegram.py --configure YOUR_BOT_TOKEN YOUR_CHAT_ID
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
import yaml


CONFIG_PATH = Path.home() / "quant_results" / "config" / "mobile_alerts.yaml"


async def get_chat_id(bot_token: str) -> str:
    """Get the chat ID from recent messages to the bot."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"

    async with httpx.AsyncClient() as client:
        response = await client.get(url)

        if response.status_code != 200:
            print(f"Error: {response.text}")
            return None

        data = response.json()

        if not data.get("ok"):
            print(f"Error: {data.get('description', 'Unknown error')}")
            return None

        results = data.get("result", [])

        if not results:
            print("\nNo messages found. Please:")
            print("1. Open Telegram")
            print("2. Search for your bot by name")
            print("3. Start a chat and send any message")
            print("4. Run this command again")
            return None

        # Get chat IDs from recent messages
        chat_ids = set()
        for update in results:
            if "message" in update:
                chat = update["message"]["chat"]
                chat_id = chat["id"]
                chat_type = chat.get("type", "unknown")
                chat_name = chat.get("first_name", chat.get("title", "Unknown"))
                chat_ids.add((chat_id, chat_type, chat_name))

        if chat_ids:
            print("\nFound chat(s):")
            for cid, ctype, cname in chat_ids:
                print(f"  Chat ID: {cid}")
                print(f"  Type: {ctype}")
                print(f"  Name: {cname}")
                print()

            # Return first one
            return str(list(chat_ids)[0][0])

    return None


async def test_message(bot_token: str, chat_id: str) -> bool:
    """Send a test message."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    message = """*Project Athena Test Alert*

This is a test message from your trading system.

If you receive this, Telegram alerts are working correctly.

_Sent at: """ + __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "_"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        })

        if response.status_code == 200:
            print("Test message sent successfully!")
            return True
        else:
            print(f"Error sending message: {response.text}")
            return False


def configure_alerts(bot_token: str, chat_id: str):
    """Update the config file with Telegram credentials."""
    if not CONFIG_PATH.exists():
        print(f"Config file not found at {CONFIG_PATH}")
        print("Creating default config...")

        config = {
            "telegram": {
                "enabled": True,
                "bot_token": bot_token,
                "chat_id": chat_id,
            },
            "discord": {
                "enabled": False,
                "webhook_url": "YOUR_WEBHOOK_URL_HERE",
            },
            "settings": {
                "min_level": "high",
                "quiet_hours": {"start": 22, "end": 6},
                "rate_limit_seconds": 60,
            },
            "alert_types": {
                "convergence": True,
                "signpost_trigger": True,
                "stop_loss": True,
                "drawdown": True,
                "trade_executed": True,
                "trade_queued": True,
            }
        }
    else:
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}

        config.setdefault("telegram", {})
        config["telegram"]["enabled"] = True
        config["telegram"]["bot_token"] = bot_token
        config["telegram"]["chat_id"] = chat_id

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"Configuration saved to {CONFIG_PATH}")
    print("Telegram alerts are now ENABLED")


def show_setup_instructions():
    """Show step-by-step setup instructions."""
    print("""
TELEGRAM ALERT SETUP
====================

Step 1: Create a Telegram Bot
-----------------------------
1. Open Telegram and search for @BotFather
2. Send /newbot
3. Follow prompts to name your bot (e.g., "Athena Trading Bot")
4. Copy the bot token (looks like: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)

Step 2: Get Your Chat ID
------------------------
1. Search for your new bot in Telegram
2. Start a chat and send any message (e.g., "hello")
3. Run: python3 scripts/setup_telegram.py --get-chat-id YOUR_BOT_TOKEN

Step 3: Test and Configure
--------------------------
1. Test: python3 scripts/setup_telegram.py --test YOUR_BOT_TOKEN YOUR_CHAT_ID
2. Configure: python3 scripts/setup_telegram.py --configure YOUR_BOT_TOKEN YOUR_CHAT_ID

Step 4: Verify
--------------
Run: PYTHONPATH=. python -m src.monitoring.alert_bridge --test

You should receive a test alert on Telegram!

OPTIONAL: Group Chat
--------------------
To send alerts to a group:
1. Add your bot to the group
2. Make it an admin (if the group restricts who can post)
3. Send a message in the group
4. Run --get-chat-id again - the group chat ID will be negative
""")


async def main():
    parser = argparse.ArgumentParser(
        description="Set up Telegram alerts for Project Athena"
    )
    parser.add_argument(
        "--get-chat-id",
        metavar="BOT_TOKEN",
        help="Get chat ID after sending a message to your bot"
    )
    parser.add_argument(
        "--test",
        nargs=2,
        metavar=("BOT_TOKEN", "CHAT_ID"),
        help="Send a test message"
    )
    parser.add_argument(
        "--configure",
        nargs=2,
        metavar=("BOT_TOKEN", "CHAT_ID"),
        help="Configure alerts with provided credentials"
    )
    parser.add_argument(
        "--instructions",
        action="store_true",
        help="Show setup instructions"
    )

    args = parser.parse_args()

    if args.instructions or len(sys.argv) == 1:
        show_setup_instructions()
        return

    if args.get_chat_id:
        chat_id = await get_chat_id(args.get_chat_id)
        if chat_id:
            print(f"\nYour chat ID is: {chat_id}")
            print(f"\nTo configure, run:")
            print(f"  python3 scripts/setup_telegram.py --configure {args.get_chat_id} {chat_id}")

    if args.test:
        token, chat_id = args.test
        success = await test_message(token, chat_id)
        if success:
            print("\nTo enable alerts permanently, run:")
            print(f"  python3 scripts/setup_telegram.py --configure {token} {chat_id}")

    if args.configure:
        token, chat_id = args.configure
        # Test first
        print("Testing connection...")
        success = await test_message(token, chat_id)
        if success:
            configure_alerts(token, chat_id)
        else:
            print("Configuration aborted - please fix the connection issue first")


if __name__ == "__main__":
    asyncio.run(main())
