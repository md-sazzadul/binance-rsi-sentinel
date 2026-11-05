"""Milestone 2 smoke runner: discover pairs, bootstrap candles, and stream updates."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from app.binance import BinanceSpotClient
from app.config import Settings
from app.market_data import BinanceKlineStream


async def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        client = BinanceSpotClient(session)
        symbols = await client.get_spot_usdt_symbols()
        logging.info("Discovered %d active Spot USDT symbols", len(symbols))

        histories = await client.load_symbol_history(
            symbols, interval=settings.kline_interval, limit=1000
        )
        logging.info(
            "Loaded historical candles for %d/%d symbols", len(histories), len(symbols)
        )

        async def on_kline(symbol: str, kline: dict) -> None:
            # Milestone 3 will calculate RSI from this forming/closed candle.
            logging.info(
                "%s %s close=%s closed=%s",
                symbol,
                kline.get("i"),
                kline.get("c"),
                kline.get("x"),
            )

        stream = BinanceKlineStream(
            symbols=symbols,
            handler=on_kline,
            interval=settings.kline_interval,
        )
        await stream.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Stopped by user")
