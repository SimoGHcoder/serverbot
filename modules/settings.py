"""Central configuration. Secrets remain in the host-wide /opt/.env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv("/opt/.env", override=False)

# Bot version — managed locally in code, never via environment.
BOT_VERSION = "3.5.0"


def _positive_integer(*names: str, default: int | None = None) -> int:
    for name in names:
        raw = os.getenv(name, "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            raise RuntimeError(f"{name} must be an integer") from None
        if value <= 0:
            raise RuntimeError(f"{name} must be positive")
        return value
    if default is not None:
        return default
    raise RuntimeError(f"One of {', '.join(names)} is required")


def _parse_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a number") from None


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    allowed_user_id: int
    omniroute_webhook_token: str
    timezone: str
    log_level: str
    bot_version: str
    container_name: str
    metrics_enabled: bool
    metrics_disk_warn: int
    metrics_mem_warn: int
    metrics_load_warn: float
    metrics_interval: int


SETTINGS = Settings(
    telegram_token=os.getenv("TELEGRAM_TOKEN", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
    allowed_user_id=_positive_integer("ALLOWED_USER_ID", "TELEGRAM_CHAT_ID"),
    omniroute_webhook_token=os.getenv("OMNIROUTE_WEBHOOK_TOKEN", "").strip(),
    timezone=os.getenv("TZ", "Europe/Rome").strip() or "Europe/Rome",
    log_level=os.getenv("SERVER_BOT_LOG_LEVEL", "INFO").strip().upper(),
    bot_version=BOT_VERSION,
    container_name=os.getenv("SERVER_BOT_CONTAINER_NAME", "server-bot").strip() or "server-bot",
    metrics_enabled=os.getenv("SERVER_BOT_METRICS_ENABLED", "1").strip() in {"1", "true", "yes"},
    metrics_disk_warn=_positive_integer("SERVER_BOT_METRICS_DISK_WARN", default=90),
    metrics_mem_warn=_positive_integer("SERVER_BOT_METRICS_MEM_WARN", default=85),
    metrics_load_warn=_parse_float("SERVER_BOT_METRICS_LOAD_WARN", default=5.0),
    metrics_interval=_positive_integer("SERVER_BOT_METRICS_INTERVAL", default=300),
)
