"""Binance Spot 1-hour kline WebSocket stream consumer."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

WEBSOCKET_URL = "wss://data-stream.binance.vision/ws"
MAX_STREAMS_PER_CONNECTION = 1024
SUBSCRIBE_BATCH_SIZE = 100

KlineHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class BinanceKlineStream:
    """Subscribe to one-hour kline updates for a set of Spot symbols."""

    def __init__(
        self,
        symbols: list[str],
        handler: KlineHandler,
        interval: str = "1h",
        websocket_url: str = WEBSOCKET_URL,
    ) -> None:
        self.symbols = sorted(set(symbols))
        self.handler = handler
        self.interval = interval
        self.websocket_url = websocket_url
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        """Reconnect with backoff; Binance connections are limited to 24 hours."""
        delay = 1
        while not self._stop.is_set():
            try:
                await self._run_connection()
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Kline WebSocket disconnected; reconnecting")
            if not self._stop.is_set():
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    async def _run_connection(self) -> None:
        if not self.symbols:
            raise ValueError("Cannot start a WebSocket stream without symbols")
        if len(self.symbols) > MAX_STREAMS_PER_CONNECTION:
            raise ValueError(
                f"{len(self.symbols)} symbols exceed the {MAX_STREAMS_PER_CONNECTION}-stream "
                "connection limit; split them across connections"
            )

        streams = [f"{symbol.lower()}@kline_{self.interval}" for symbol in self.symbols]
        async with connect(
            self.websocket_url,
            ping_interval=None,
            close_timeout=10,
            max_queue=4096,
            open_timeout=20,
        ) as websocket:
            logger.info("Connected to Binance market-data WebSocket (%d symbols)", len(streams))
            for request_id, start in enumerate(range(0, len(streams), SUBSCRIBE_BATCH_SIZE), start=1):
                batch = streams[start : start + SUBSCRIBE_BATCH_SIZE]
                await websocket.send(json.dumps({
                    "method": "SUBSCRIBE",
                    "params": batch,
                    "id": request_id,
                }))
                # Stay comfortably below Binance's incoming-message limit.
                await asyncio.sleep(0.25)

            while not self._stop.is_set():
                try:
                    raw_message = await asyncio.wait_for(websocket.recv(), timeout=60)
                except asyncio.TimeoutError:
                    logger.warning("No WebSocket message received for 60 seconds")
                    continue
                message = json.loads(raw_message)
                if "result" in message:
                    if message["result"] is None:
                        logger.debug("Subscription acknowledgement: id=%s", message.get("id"))
                    continue
                if message.get("e") != "kline":
                    continue
                symbol = message.get("s")
                kline = message.get("k")
                if not symbol or not isinstance(kline, dict):
                    continue
                await self.handler(symbol, kline)
