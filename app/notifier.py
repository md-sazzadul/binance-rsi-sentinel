"""Gmail SMTP alert delivery with bounded retries."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RSIAlert:
    symbol: str
    rsi: float
    period: int
    interval: str
    threshold: float
    candle_close: str
    event_time: str


class GmailNotifier:
    """Send RSI alert emails through Gmail SMTP using an App Password."""

    def __init__(self, settings: Settings, max_attempts: int = 3) -> None:
        self.settings = settings
        self.max_attempts = max_attempts

    def _build_message(self, alert: RSIAlert) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self.settings.alert_from_email
        message["To"] = self.settings.alert_to_email
        message["Subject"] = (
            f"Binance RSI Alert: {alert.symbol} RSI({alert.period}) = {alert.rsi:.2f}"
        )
        message.set_content(
            "\n".join(
                [
                    "Binance RSI Sentinel detected an RSI threshold breach.",
                    "",
                    f"Symbol: {alert.symbol}",
                    "Market: Binance Spot",
                    f"Interval: {alert.interval}",
                    f"RSI period: {alert.period}",
                    f"RSI value: {alert.rsi:.2f}",
                    f"Threshold: below {alert.threshold:g}",
                    f"Latest candle close: {alert.candle_close}",
                    f"Event time (UTC): {alert.event_time}",
                    "",
                    "This is an indicator alert, not a trading recommendation.",
                ]
            )
        )
        return message

    def _send_sync(self, message: EmailMessage) -> None:
        if not self.settings.smtp_username or not self.settings.smtp_password:
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured")
        if not self.settings.alert_from_email or not self.settings.alert_to_email:
            raise ValueError("ALERT_FROM_EMAIL and ALERT_TO_EMAIL must be configured")

        context = ssl.create_default_context()
        with smtplib.SMTP(
            self.settings.smtp_host, self.settings.smtp_port, timeout=20
        ) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)

    async def send(self, alert: RSIAlert) -> None:
        """Send one alert without blocking the asyncio event loop."""
        message = self._build_message(alert)
        for attempt in range(1, self.max_attempts + 1):
            try:
                await asyncio.to_thread(self._send_sync, message)
                logger.info("Email alert sent for %s (RSI %.2f)", alert.symbol, alert.rsi)
                return
            except (OSError, smtplib.SMTPException, ValueError):
                if attempt == self.max_attempts:
                    logger.exception("Email delivery failed for %s after %d attempts", alert.symbol, attempt)
                    raise
                delay = min(2 ** (attempt - 1), 10)
                logger.warning(
                    "Email delivery attempt %d/%d failed for %s; retrying in %ss",
                    attempt,
                    self.max_attempts,
                    alert.symbol,
                    delay,
                    exc_info=True,
                )
                await asyncio.sleep(delay)
