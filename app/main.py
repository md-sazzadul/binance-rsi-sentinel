"""Milestone 4 runner: monitor RSI and send Gmail threshold alerts."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from app.binance import BinanceSpotClient
from app.config import Settings
from app.market_data import BinanceKlineStream, MAX_STREAMS_PER_CONNECTION
from app.notifier import GmailNotifier, RSIAlert
from app.rsi import WilderRSI


def chunked(items: list[str], size: int) -> list[list[str]]:
    """Split symbols into groups that fit Binance's per-connection stream limit."""
    return [items[index : index + size] for index in range(0, len(items), size)]


async def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    notifier = GmailNotifier(settings)
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        client = BinanceSpotClient(session)
        symbols = await client.get_spot_usdt_symbols()
        logging.info("Discovered %d active Spot USDT symbols", len(symbols))

        histories = await client.load_symbol_history(
            symbols, interval=settings.kline_interval, limit=1000
        )
        server_time = await client.get_server_time()
        rsi_by_symbol: dict[str, WilderRSI] = {}
        for symbol, rows in histories.items():
            # Binance REST kline rows: close at index 4, close time at index 6.
            closed_rows = [row for row in rows if int(row[6]) <= server_time]
            if len(closed_rows) < settings.rsi_period + 1:
                logging.warning("Not enough closed candles to seed RSI for %s", symbol)
                continue
            closes = [float(row[4]) for row in closed_rows]
            rsi_by_symbol[symbol] = WilderRSI(closes, period=settings.rsi_period)

        logging.info(
            "Initialized RSI(%d) for %d/%d symbols",
            settings.rsi_period,
            len(rsi_by_symbol),
            len(symbols),
        )

        # In-memory re-arming is used temporarily; Milestone 5 will persist it in SQLite.
        alert_armed = {
            symbol: calculator.value >= settings.rsi_threshold
            for symbol, calculator in rsi_by_symbol.items()
        }

        async def on_kline(symbol: str, kline: dict) -> None:
            calculator = rsi_by_symbol.get(symbol)
            if calculator is None:
                return
            try:
                close = float(kline["c"])
                if kline.get("x") is True:
                    value = calculator.commit(close)
                    logging.info(
                        "%s RSI(%d) candle closed: %.2f",
                        symbol,
                        settings.rsi_period,
                        value,
                    )
                else:
                    value = calculator.preview(close)

                if value >= settings.rsi_threshold:
                    alert_armed[symbol] = True
                    return

                if not alert_armed.get(symbol, False):
                    return

                close_time_ms = int(kline.get("T", 0))
                event_time = datetime.fromtimestamp(
                    close_time_ms / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S UTC")
                alert = RSIAlert(
                    symbol=symbol,
                    rsi=value,
                    period=settings.rsi_period,
                    interval=settings.kline_interval,
                    threshold=settings.rsi_threshold,
                    candle_close=f"{close:.12g}",
                    event_time=event_time,
                )
                await notifier.send(alert)
                alert_armed[symbol] = False
                logging.warning(
                    "RSI ALERT SENT: %s RSI(%d)=%.2f (< %.2f)",
                    symbol,
                    settings.rsi_period,
                    value,
                    settings.rsi_threshold,
                )
            except (KeyError, TypeError, ValueError) as exc:
                logging.warning("Skipping invalid kline update for %s: %s", symbol, exc)
            except Exception:
                # Keep the alert armed; a later market update can retry delivery.
                logging.exception("Could not send RSI alert for %s", symbol)

        groups = chunked(list(rsi_by_symbol), MAX_STREAMS_PER_CONNECTION)
        logging.info(
            "Starting %d WebSocket connection(s), up to %d symbols each",
            len(groups),
            MAX_STREAMS_PER_CONNECTION,
        )
        streams = [
            BinanceKlineStream(
                symbols=group,
                handler=on_kline,
                interval=settings.kline_interval,
            )
            for group in groups
        ]
        if not streams:
            raise RuntimeError("No symbols have sufficient candle history to initialize RSI")
        await asyncio.gather(*(stream.run_forever() for stream in streams))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Stopped by user")
