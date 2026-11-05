"""Tests for environment configuration."""

import pytest

from app.config import Settings


def test_settings_load_project_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.load_dotenv", lambda **kwargs: False)
    for key in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
        "ALERT_FROM_EMAIL", "ALERT_TO_EMAIL", "QUOTE_ASSET",
        "KLINE_INTERVAL", "RSI_PERIOD", "RSI_THRESHOLD", "LOG_LEVEL",
        "DATABASE_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings.from_env(env_file=tmp_path / ".env")

    assert settings.smtp_host == "smtp.gmail.com"
    assert settings.smtp_port == 587
    assert settings.quote_asset == "USDT"
    assert settings.kline_interval == "1h"
    assert settings.rsi_period == 6
    assert settings.rsi_threshold == 20.0
    assert settings.database_path.as_posix() == "data/alerts.sqlite3"


def test_invalid_rsi_threshold_is_rejected(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda **kwargs: False)
    monkeypatch.setenv("RSI_THRESHOLD", "100")

    with pytest.raises(ValueError, match="RSI_THRESHOLD"):
        Settings.from_env(env_file="/nonexistent/.env")


def test_only_one_hour_interval_is_currently_supported(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda **kwargs: False)
    monkeypatch.setenv("KLINE_INTERVAL", "15m")

    with pytest.raises(ValueError, match="KLINE_INTERVAL"):
        Settings.from_env(env_file="/nonexistent/.env")
