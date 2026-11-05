"""Tests for Gmail notification message construction and retry behavior."""

from dataclasses import replace
from email.message import EmailMessage

import pytest

from app.config import Settings
from app.notifier import GmailNotifier, RSIAlert


def make_settings():
    return Settings(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username="sender@gmail.com",
        smtp_password="test-app-password",
        alert_from_email="sender@gmail.com",
        alert_to_email="recipient@example.com",
        quote_asset="USDT",
        kline_interval="1h",
        rsi_period=6,
        rsi_threshold=20.0,
        log_level="INFO",
        database_path=__import__("pathlib").Path("data/test.sqlite3"),
    )


def make_alert():
    return RSIAlert(
        symbol="BTCUSDT",
        rsi=18.42,
        period=6,
        interval="1h",
        threshold=20.0,
        candle_close="101234.50",
        event_time="2026-11-05 10:30:00",
    )


def test_email_message_contains_signal_details():
    notifier = GmailNotifier(make_settings())
    message = notifier._build_message(make_alert())

    assert message["From"] == "sender@gmail.com"
    assert message["To"] == "recipient@example.com"
    assert "BTCUSDT" in message["Subject"]
    assert "18.42" in message.get_content()
    assert "below 20" in message.get_content()
    assert "not a trading recommendation" in message.get_content()


@pytest.mark.asyncio
async def test_send_runs_smtp_sender_and_returns_on_success(monkeypatch):
    notifier = GmailNotifier(make_settings())
    sent = []

    def fake_send(message):
        sent.append(message)

    monkeypatch.setattr(notifier, "_send_sync", fake_send)
    await notifier.send(make_alert())

    assert len(sent) == 1
    assert isinstance(sent[0], EmailMessage)


@pytest.mark.asyncio
async def test_send_retries_then_succeeds(monkeypatch):
    notifier = GmailNotifier(make_settings(), max_attempts=3)
    calls = []

    def fake_send(message):
        calls.append(message)
        if len(calls) == 1:
            raise OSError("temporary SMTP issue")

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(notifier, "_send_sync", fake_send)
    monkeypatch.setattr("app.notifier.asyncio.sleep", no_wait)
    await notifier.send(make_alert())

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_send_raises_after_final_failed_attempt(monkeypatch):
    notifier = GmailNotifier(make_settings(), max_attempts=2)
    calls = []

    def fake_send(_message):
        calls.append(True)
        raise OSError("SMTP unavailable")

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(notifier, "_send_sync", fake_send)
    monkeypatch.setattr("app.notifier.asyncio.sleep", no_wait)

    with pytest.raises(OSError, match="SMTP unavailable"):
        await notifier.send(make_alert())

    assert len(calls) == 2
