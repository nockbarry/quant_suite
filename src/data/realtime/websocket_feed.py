#!/usr/bin/env python3
"""WebSocket Real-Time Price Feed - Low-latency price updates.

Connects to free WebSocket feeds for real-time price monitoring.
Supports: Alpaca (with API key), Finnhub (free tier), or polling fallback.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from collections import defaultdict
import websockets
import yaml

logger = logging.getLogger(__name__)


@dataclass
class PriceUpdate:
    """Real-time price update."""
    symbol: str
    price: float
    bid: float
    ask: float
    volume: int
    timestamp: datetime
    source: str

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "price": self.price,
            "bid": self.bid,
            "ask": self.ask,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }


class RealtimePriceFeed:
    """Real-time price feed with WebSocket support."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.home() / "quant_results" / "config" / "realtime.yaml"
        self.config = self._load_config()

        # Subscribed symbols
        self.subscriptions: set[str] = set()

        # Latest prices
        self.prices: dict[str, PriceUpdate] = {}

        # Callbacks
        self.on_price_callbacks: list[Callable] = []
        self.on_alert_callbacks: list[Callable] = []

        # Alert levels
        self.alert_levels: dict[str, list[dict]] = defaultdict(list)

        # Connection state
        self.connected = False
        self.ws = None

    def _load_config(self) -> dict:
        """Load configuration."""
        if self.config_path.exists():
            with open(self.config_path) as f:
                return yaml.safe_load(f) or {}

        # Default config
        default = {
            "source": "polling",  # alpaca, finnhub, or polling
            "alpaca": {
                "api_key": "",
                "secret_key": "",
                "feed": "iex",  # iex (free) or sip (paid)
            },
            "finnhub": {
                "api_key": "",
            },
            "polling": {
                "interval_seconds": 5,
            },
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(default, f)

        return default

    def subscribe(self, symbols: list[str]):
        """Subscribe to symbols for price updates."""
        self.subscriptions.update(symbols)
        logger.info(f"Subscribed to: {symbols}")

    def unsubscribe(self, symbols: list[str]):
        """Unsubscribe from symbols."""
        self.subscriptions -= set(symbols)

    def set_alert_level(self, symbol: str, level: float, direction: str,
                       callback: Optional[Callable] = None):
        """Set price alert level."""
        self.alert_levels[symbol].append({
            "level": level,
            "direction": direction,  # above, below
            "callback": callback,
            "triggered": False,
        })
        logger.info(f"Alert set: {symbol} {direction} ${level}")

    def on_price(self, callback: Callable):
        """Register callback for price updates."""
        self.on_price_callbacks.append(callback)

    def _handle_price_update(self, update: PriceUpdate):
        """Process incoming price update."""
        self.prices[update.symbol] = update

        # Check alert levels
        for alert in self.alert_levels.get(update.symbol, []):
            if alert["triggered"]:
                continue

            triggered = False
            if alert["direction"] == "above" and update.price > alert["level"]:
                triggered = True
            elif alert["direction"] == "below" and update.price < alert["level"]:
                triggered = True

            if triggered:
                alert["triggered"] = True
                logger.warning(f"ALERT: {update.symbol} {alert['direction']} ${alert['level']} "
                             f"(current: ${update.price})")

                if alert["callback"]:
                    try:
                        alert["callback"](update, alert)
                    except Exception as e:
                        logger.error(f"Alert callback error: {e}")

                for cb in self.on_alert_callbacks:
                    try:
                        cb(update, alert)
                    except Exception as e:
                        logger.error(f"Alert callback error: {e}")

        # Notify price callbacks
        for callback in self.on_price_callbacks:
            try:
                callback(update)
            except Exception as e:
                logger.error(f"Price callback error: {e}")

    async def _connect_alpaca(self):
        """Connect to Alpaca WebSocket."""
        config = self.config.get("alpaca", {})
        api_key = config.get("api_key", "")
        secret_key = config.get("secret_key", "")
        feed = config.get("feed", "iex")

        if not api_key or not secret_key:
            logger.error("Alpaca credentials not configured")
            return

        url = f"wss://stream.data.alpaca.markets/v2/{feed}"

        try:
            async with websockets.connect(url) as ws:
                self.ws = ws
                self.connected = True

                # Authenticate
                auth_msg = {
                    "action": "auth",
                    "key": api_key,
                    "secret": secret_key,
                }
                await ws.send(json.dumps(auth_msg))

                # Wait for auth response
                response = await ws.recv()
                logger.info(f"Alpaca auth response: {response}")

                # Subscribe to symbols
                if self.subscriptions:
                    sub_msg = {
                        "action": "subscribe",
                        "quotes": list(self.subscriptions),
                    }
                    await ws.send(json.dumps(sub_msg))

                # Process messages
                async for message in ws:
                    data = json.loads(message)

                    for item in data:
                        if item.get("T") == "q":  # Quote
                            update = PriceUpdate(
                                symbol=item["S"],
                                price=(item["bp"] + item["ap"]) / 2,
                                bid=item["bp"],
                                ask=item["ap"],
                                volume=item.get("bs", 0) + item.get("as", 0),
                                timestamp=datetime.fromisoformat(item["t"].replace("Z", "+00:00")),
                                source="alpaca",
                            )
                            self._handle_price_update(update)

        except Exception as e:
            logger.error(f"Alpaca connection error: {e}")
            self.connected = False

    async def _connect_finnhub(self):
        """Connect to Finnhub WebSocket."""
        config = self.config.get("finnhub", {})
        api_key = config.get("api_key", "")

        if not api_key:
            logger.error("Finnhub API key not configured")
            return

        url = f"wss://ws.finnhub.io?token={api_key}"

        try:
            async with websockets.connect(url) as ws:
                self.ws = ws
                self.connected = True

                # Subscribe to symbols
                for symbol in self.subscriptions:
                    sub_msg = {"type": "subscribe", "symbol": symbol}
                    await ws.send(json.dumps(sub_msg))

                # Process messages
                async for message in ws:
                    data = json.loads(message)

                    if data.get("type") == "trade":
                        for trade in data.get("data", []):
                            update = PriceUpdate(
                                symbol=trade["s"],
                                price=trade["p"],
                                bid=trade["p"],  # Finnhub doesn't provide bid/ask
                                ask=trade["p"],
                                volume=int(trade["v"]),
                                timestamp=datetime.fromtimestamp(trade["t"] / 1000),
                                source="finnhub",
                            )
                            self._handle_price_update(update)

        except Exception as e:
            logger.error(f"Finnhub connection error: {e}")
            self.connected = False

    async def _polling_fallback(self):
        """Polling fallback when WebSocket not available."""
        import yfinance as yf

        interval = self.config.get("polling", {}).get("interval_seconds", 5)
        logger.info(f"Using polling fallback (interval: {interval}s)")

        while True:
            for symbol in self.subscriptions:
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info

                    price = info.get("regularMarketPrice") or info.get("previousClose", 0)
                    bid = info.get("bid", price)
                    ask = info.get("ask", price)
                    volume = info.get("regularMarketVolume", 0)

                    update = PriceUpdate(
                        symbol=symbol,
                        price=price,
                        bid=bid,
                        ask=ask,
                        volume=volume,
                        timestamp=datetime.now(),
                        source="yfinance",
                    )
                    self._handle_price_update(update)

                except Exception as e:
                    logger.warning(f"Polling error for {symbol}: {e}")

            await asyncio.sleep(interval)

    async def start(self):
        """Start the price feed."""
        source = self.config.get("source", "polling")
        logger.info(f"Starting price feed (source: {source})")

        if source == "alpaca":
            await self._connect_alpaca()
        elif source == "finnhub":
            await self._connect_finnhub()
        else:
            await self._polling_fallback()

    async def stop(self):
        """Stop the price feed."""
        self.connected = False
        if self.ws:
            await self.ws.close()

    def get_price(self, symbol: str) -> Optional[PriceUpdate]:
        """Get latest price for symbol."""
        return self.prices.get(symbol)

    def get_all_prices(self) -> dict[str, PriceUpdate]:
        """Get all latest prices."""
        return self.prices.copy()


async def main():
    """Test price feed."""
    feed = RealtimePriceFeed()

    # Subscribe to symbols
    feed.subscribe(["SPY", "QQQ", "AAPL"])

    # Set up alert
    feed.set_alert_level("SPY", 680.0, "below", lambda u, a: print(f"ALERT: {u.symbol} below {a['level']}!"))

    # Register callback
    def on_update(update: PriceUpdate):
        print(f"{update.symbol}: ${update.price:.2f} (bid: ${update.bid:.2f}, ask: ${update.ask:.2f})")

    feed.on_price(on_update)

    # Start feed (will run forever)
    print("Starting price feed... (Ctrl+C to stop)")
    try:
        await feed.start()
    except KeyboardInterrupt:
        await feed.stop()
        print("Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
