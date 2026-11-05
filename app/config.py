"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    alert_from_email: str
    alert_to_email: str
    quote_asset: str
    kline_interval: str
    rsi_period: int
    rsi_threshold: float
    log_level: str
    database_path: Path

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> "Settings":
        """Load settings from an optional .env file and process environment."""
        load_dotenv(dotenv_path=env_file, override=False)

        settings = cls(
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=_as_int("SMTP_PORT", 587),
            smtp_username=os.getenv("SMTP_USERNAME", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            alert_from_email=os.getenv("ALERT_FROM_EMAIL", ""),
            alert_to_email=os.getenv("ALERT_TO_EMAIL", ""),
            quote_asset=os.getenv("QUOTE_ASSET", "USDT").upper(),
            kline_interval=os.getenv("KLINE_INTERVAL", "1h"),
            rsi_period=_as_int("RSI_PERIOD", 6),
            rsi_threshold=_as_float("RSI_THRESHOLD", 20.0),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            database_path=Path(os.getenv("DATABASE_PATH", "data/alerts.sqlite3")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.smtp_port < 1 or self.smtp_port > 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535")
        if self.rsi_period < 2:
            raise ValueError("RSI_PERIOD must be at least 2")
        if not 0 < self.rsi_threshold < 100:
            raise ValueError("RSI_THRESHOLD must be between 0 and 100")
        if not self.quote_asset:
            raise ValueError("QUOTE_ASSET cannot be empty")
        if self.kline_interval != "1h":
            raise ValueError("This project currently supports only KLINE_INTERVAL=1h")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")


def _as_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _as_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
