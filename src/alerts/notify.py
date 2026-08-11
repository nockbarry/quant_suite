"""Critical-path notification with guaranteed local fallback.

`notify_critical()` is the one call sites use when something MUST reach the
owner: missed-job SLOs, cron drift, dead subsystems. Delivery order:

1. Telegram via MobileAlertBot (if config/mobile_alerts.yaml has real,
   enabled credentials — bypasses quiet hours / level filtering, this is
   critical by definition).
2. Always: append to ~/quant_results/live/ALERTS.md, which the morning
   briefing and situation board surface. This never fails silently even
   when no external transport is configured.

Dedup: callers pass a `key`; the same key notifies at most once per calendar
day (stamp files under logs/notify_stamps/). Prevents the 4x/day readiness
cron from spamming the same stale-artifact alert.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from src.core.paths import paths

logger = logging.getLogger(__name__)

ALERTS_FILE = paths.base / "live" / "ALERTS.md"
STAMP_DIR = paths.base / "logs" / "notify_stamps"


def _already_sent_today(key: str) -> bool:
    stamp = STAMP_DIR / f"{key}.{datetime.now():%Y%m%d}"
    if stamp.exists():
        return True
    STAMP_DIR.mkdir(parents=True, exist_ok=True)
    stamp.touch()
    # Prune stamps older than today so the dir doesn't accumulate forever
    today_suffix = f".{datetime.now():%Y%m%d}"
    for old in STAMP_DIR.iterdir():
        if not old.name.endswith(today_suffix):
            old.unlink(missing_ok=True)
    return False


def _append_alerts_md(subject: str, body: str) -> bool:
    try:
        ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ALERTS_FILE, "a") as f:
            f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M} — {subject}\n\n{body}\n")
        return True
    except Exception as e:
        logger.error(f"ALERTS.md append failed: {e}")
        return False


def _send_telegram(subject: str, body: str) -> bool:
    try:
        from src.alerts.mobile_bot import AlertLevel, MobileAlert, MobileAlertBot

        bot = MobileAlertBot()
        tg = bot.config.get("telegram", {})
        token = str(tg.get("bot_token", ""))
        if not tg.get("enabled") or not token or "YOUR_" in token:
            return False
        alert = MobileAlert(title=subject, message=body, level=AlertLevel.CRITICAL, symbols=[])

        async def _run() -> bool:
            try:
                return await bot.send_telegram(alert)
            finally:
                await bot.close()

        return asyncio.run(_run())
    except Exception as e:
        logger.error(f"Telegram notify failed: {e}")
        return False


def notify_critical(subject: str, body: str, key: str | None = None) -> bool:
    """Send a critical notification. Returns True if any channel delivered.

    `key`: dedup key — same key alerts at most once per day. Defaults to a
    slug of the subject.
    """
    dedup_key = (key or subject).lower().replace(" ", "_").replace("/", "_")[:80]
    if _already_sent_today(dedup_key):
        logger.info(f"notify_critical deduped (already sent today): {dedup_key}")
        return True

    sent_tg = _send_telegram(subject, body)
    sent_md = _append_alerts_md(subject, body)
    if not sent_tg:
        logger.warning(f"Telegram unavailable; alert written to {ALERTS_FILE}: {subject}")
    return sent_tg or sent_md
