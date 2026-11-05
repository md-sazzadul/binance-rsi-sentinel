"""Public Binance Spot REST API helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

REST_BASE_URL = "https://data-api.binance.vision"


class BinanceAPIError(RuntimeError):
    """Raised when Binance returns an unsuccessful API response."""


class BinanceSpotClient:
    """Small asynchronous client for public Binance Spot market data."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str = REST_BASE_URL,
        request_concurrency: int = 8,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._semaphore = asyncio.Semaphore(request_concurrency)

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self._base_url}{path}"
        for attempt in range(5):
            try:
                async with self._semaphore:
                    async with self._session.get(url, params=params) as response:
                        if response.status in (418, 429):
                            retry_after = float(response.headers.get("Retry-After", "2"))
                            logger.warning("Binance rate limit (%s); retrying in %.1fs", response.status, retry_after)
                            await asyncio.sleep(min(retry_after, 60.0))
                            continue
                        response.raise_for_status()
                        payload = await response.json()
                        if isinstance(payload, dict) and "code" in payload and payload.get("code", 0) < 0:
                            raise BinanceAPIError(f"Binance API error: {payload}")
                        return payload
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == 4:
                    raise BinanceAPIError(f"Request failed after retries: {url}") from exc
                delay = min(2**attempt, 20)
                logger.warning("Binance request failed (%s); retrying in %ss", exc, delay)
                await asyncio.sleep(delay)
        raise BinanceAPIError(f"Unable to retrieve {url}")

    async def get_spot_usdt_symbols(self) -> list[str]:
        """Return active Spot symbols whose quote asset is USDT."""
        payload = await self._get_json("/api/v3/exchangeInfo")
        symbols: list[str] = []
        for item in payload.get("symbols", []):
            if item.get("quoteAsset") != "USDT" or item.get("status") != "TRADING":
                continue
            if item.get("isSpotTradingAllowed") is False:
                continue
            symbols.append(item["symbol"])
        return sorted(set(symbols))

    async def get_klines(
        self, symbol: str, interval: str = "1h", limit: int = 1000
    ) -> list[list[Any]]:
        """Return recent raw kline rows for a symbol."""
        payload = await self._get_json(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        if not isinstance(payload, list):
            raise BinanceAPIError(f"Unexpected kline response for {symbol}: {payload}")
        return payload

    async def load_symbol_history(
        self, symbols: list[str], interval: str = "1h", limit: int = 1000
    ) -> dict[str, list[list[Any]]]:
        """Fetch candle history for symbols with bounded concurrency."""
        async def fetch(symbol: str) -> tuple[str, list[list[Any]] | None]:
            try:
                rows = await self.get_klines(symbol, interval=interval, limit=limit)
                return symbol, rows
            except (BinanceAPIError, aiohttp.ClientError, asyncio.TimeoutError):
                logger.exception("Could not load historical candles for %s", symbol)
                return symbol, None

        results = await asyncio.gather(*(fetch(symbol) for symbol in symbols))
        return {symbol: rows for symbol, rows in results if rows}
