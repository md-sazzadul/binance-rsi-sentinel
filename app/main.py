"""Milestone 5 runner: RSI monitoring with durable SQLite alert delivery."""

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
from app.storage import AlertStore, PendingAlert


def chunked(items: list[str], size: int) -> list[list[str]]:
    """Split symbols into groups that fit Binance's per-connection stream limit."""
    return [items[index : index + size] for index in range(0, len(items), size)]


async def deliver_pending_alerts(
    store: AlertStore, notifier: GmailNotifier, delivery_lock: asyncio.Lock
) -> None:
    """Deliver queued notifications and mark them sent only after SMTP succeeds."""
    async with delivery_lock:
        await _deliver_pending_alerts_locked(store, notifier)


async def _deliver_pending_alerts_locked(
    store: AlertStore, notifier: GmailNotifier
) -> None:
    for item in store.get_pending_alerts():
        alert = RSIAlert(
            symbol=item.symbol,
            rsi=item.rsi,
            period=item.period,
            interval=item.interval,
            threshold=item.threshold,
            candle_close=item.candle_close,
            event_time=item.event_time,
        )
        try:
            await notifier.send(alert)
        except Exception as exc:
            store.record_delivery_failure(item.id, f"{type(exc).__name__}: {exc}")
            logging.exception(
                "Alert %s for %s remains queued for a later retry",
                item.id,
                item.symbol,
            )
        else:
            store.mark_alert_sent(item.id)
            logging.warning(
                "RSI ALERT SENT: %s RSI(%d)=%.2f (< %.2f)",
                item.symbol,
                item.period,
                item.rsi,
                item.threshold,
            )


async def retry_outbox_forever(
    store: AlertStore, notifier: GmailNotifier, delivery_lock: asyncio.Lock,
    interval_seconds: int = 30
) -> None:
    """Retry pending email notifications periodically while the process is running."""
    while True:
        await asyncio.sleep(interval_seconds)
        await deliver_pending_alerts(store, notifier, delivery_lock)


async def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    store = AlertStore(settings.database_path)
    notifier = GmailNotifier(settings)
    timeout = aiohttp.ClientTimeout(total=30, connect=10)

    try:
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
                calculator = WilderRSI(closes, period=settings.rsi_period)
                rsi_by_symbol[symbol] = calculator
                # Only create a state for new symbols; preserve existing state on restart.
                store.initialize_symbol(
                    symbol, armed=calculator.value >= settings.rsi_threshold
                )

            logging.info(
                "Initialized RSI(%d) for %d/%d symbols",
                settings.rsi_period,
                len(rsi_by_symbol),
                len(symbols),
            )

            # Serialize all outbox sends so periodic retries cannot race a new alert.
            delivery_lock = asyncio.Lock()
            # Retry notifications left pending by an earlier run before starting streams.
            await deliver_pending_alerts(store, notifier, delivery_lock)
            outbox_task = asyncio.create_task(
                retry_outbox_forever(store, notifier, delivery_lock)
            )

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

                    candle_close_ms = int(kline.get("T", 0))
                    candle_close_time = datetime.fromtimestamp(
                        candle_close_ms / 1000, tz=timezone.utc
                    ).isoformat(timespec="seconds")
                    alert_id = store.observe_rsi(
                        symbol=symbol,
                        rsi=value,
                        period=settings.rsi_period,
                        interval=settings.kline_interval,
                        threshold=settings.rsi_threshold,
                        candle_close=f"{close:.12g}",
                        candle_close_time=candle_close_time,
                        # Alerts remain intrabar, but re-arming requires a confirmed close.
                        candle_closed=kline.get("x") is True,
                    )
                    if alert_id is not None:
                        logging.warning(
                            "RSI threshold crossing queued: %s RSI(%d)=%.2f",
                            symbol,
                            settings.rsi_period,
                            value,
                        )
                        await deliver_pending_alerts(store, notifier, delivery_lock)
                except (KeyError, TypeError, ValueError, OSError) as exc:
                    logging.warning("Could not process kline update for %s: %s", symbol, exc)
                except Exception:
                    logging.exception("Unexpected error while processing %s", symbol)

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
                outbox_task.cancel()
                raise RuntimeError("No symbols have sufficient candle history to initialize RSI")
            try:
                await asyncio.gather(*(stream.run_forever() for stream in streams))
            finally:
                outbox_task.cancel()
                await asyncio.gather(outbox_task, return_exceptions=True)
    finally:
        store.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Stopped by user")
