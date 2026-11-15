"""Numeric host metrics, time-series storage, and threshold alerts."""
from __future__ import annotations

import logging
import re
import shutil
import time
from typing import Any

from modules import db
from modules.settings import SETTINGS

logger = logging.getLogger("ServerBot.Metrics")

# --- Numeric collectors -----------------------------------------------------------


def get_numeric_metrics() -> dict[str, float]:
    """Return numeric host metrics: uptime_sec, mem_used_pct, root_disk_pct,
    storage_disk_pct, load_1m. Missing values default to 0.0."""
    metrics: dict[str, float] = {}

    # Uptime
    try:
        with open("/proc/uptime", encoding="ascii") as f:
            metrics["uptime_sec"] = float(f.readline().split()[0])
    except (OSError, ValueError, IndexError):
        metrics["uptime_sec"] = 0.0

    # Memory
    try:
        values: dict[str, int] = {}
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith(("MemTotal:", "MemAvailable:")):
                    key, value, *_ = line.split()
                    values[key[:-1]] = int(value) * 1024
        total = values["MemTotal"]
        available = values["MemAvailable"]
        metrics["mem_used_pct"] = round((total - available) * 100 / total, 1) if total else 0.0
    except (OSError, ValueError, KeyError):
        metrics["mem_used_pct"] = 0.0

    # Disks
    metrics["root_disk_pct"] = _disk_pct("/")
    metrics["storage_disk_pct"] = _disk_pct(
        "/mnt/storage_immich" if _is_mount("/mnt/storage_immich") else "/mnt"
    )

    # Load
    try:
        with open("/proc/loadavg", encoding="ascii") as f:
            metrics["load_1m"] = float(f.readline().split()[0])
    except (OSError, ValueError, IndexError):
        metrics["load_1m"] = 0.0

    return metrics


def _disk_pct(path: str) -> float:
    try:
        usage = shutil.disk_usage(path)
        return round(usage.used * 100 / usage.total, 1) if usage.total else 0.0
    except OSError:
        return 0.0


def _is_mount(path: str) -> bool:
    try:
        return shutil.disk_usage(path) is not None and path != "/"
    except OSError:
        return False


# --- Time-series storage ----------------------------------------------------------


def save_metrics_sample(metrics: dict[str, float]) -> None:
    """Insert one metrics sample into the metrics_history table."""
    db.save_metrics_sample(metrics)


def get_metrics_history(minutes: int = 60) -> list[dict[str, Any]]:
    """Return metrics samples from the last N minutes, oldest first."""
    return db.get_metrics_history(minutes)


# --- Threshold alerts -------------------------------------------------------------


def check_thresholds(metrics: dict[str, float]) -> list[str]:
    """Return a list of human-readable alerts for exceeded thresholds."""
    alerts: list[str] = []
    if metrics["root_disk_pct"] >= SETTINGS.metrics_disk_warn:
        alerts.append(f"💾 Disco root al {metrics['root_disk_pct']:.1f}% (soglia {SETTINGS.metrics_disk_warn}%)")
    if metrics["storage_disk_pct"] >= SETTINGS.metrics_disk_warn:
        alerts.append(f"💾 Storage al {metrics['storage_disk_pct']:.1f}% (soglia {SETTINGS.metrics_disk_warn}%)")
    if metrics["mem_used_pct"] >= SETTINGS.metrics_mem_warn:
        alerts.append(f"🧠 RAM al {metrics['mem_used_pct']:.1f}% (soglia {SETTINGS.metrics_mem_warn}%)")
    if metrics["load_1m"] >= SETTINGS.metrics_load_warn:
        alerts.append(f"⚙️ Load 1m a {metrics['load_1m']:.2f} (soglia {SETTINGS.metrics_load_warn})")
    return alerts


def format_metrics_report(metrics: dict[str, float], history_minutes: int = 60) -> str:
    """Format a human-readable metrics report with current values and trend."""
    lines = ["📊 <b>METRICHE SERVER</b>"]
    lines.append(f"⏱ Uptime: {_human_duration(metrics['uptime_sec'])}")
    lines.append(f"🧠 RAM: {metrics['mem_used_pct']:.1f}%")
    lines.append(f"💽 Root: {metrics['root_disk_pct']:.1f}%")
    lines.append(f"📦 Storage: {metrics['storage_disk_pct']:.1f}%")
    lines.append(f"⚙️ Load 1m: {metrics['load_1m']:.2f}")

    history = get_metrics_history(history_minutes)
    if history:
        first = history[0]
        last = history[-1]
        lines.append("")
        lines.append("📈 <b>Trend (ultima ora)</b>")
        for key in ("mem_used_pct", "root_disk_pct", "storage_disk_pct", "load_1m"):
            delta = last[key] - first[key]
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            lines.append(f"  {key}: {first[key]:.1f} → {last[key]:.1f} ({arrow} {abs(delta):.1f})")
    else:
        lines.append("")
        lines.append("📈 Nessun storico disponibile")

    return "\n".join(lines)


def _human_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    return f"{days}g {hours}h {minutes}m"


# --- Metrics collection task ------------------------------------------------------


async def metrics_task(application: Any) -> None:
    """Periodically collect metrics, store them, and alert on threshold breaches."""
    import asyncio
    from telegram.constants import ParseMode
    from html import escape

    while True:
        await asyncio.sleep(SETTINGS.metrics_interval)
        try:
            metrics = get_numeric_metrics()
            save_metrics_sample(metrics)
            alerts = check_thresholds(metrics)
            if alerts and SETTINGS.allowed_user_id:
                text = "🚨 <b>Soglie superate</b>\n" + "\n".join(f"• {escape(a)}" for a in alerts)
                await application.bot.send_message(
                    SETTINGS.allowed_user_id, text, parse_mode=ParseMode.HTML
                )
                logger.warning("Metrics alerts sent: %s", alerts)
        except Exception as exc:
            logger.error("Metrics task failed (%s)", type(exc).__name__)


# --- Parsing utilities (re-exported for tests) ------------------------------------


def _parse_percent(text: str) -> float | None:
    """Extract a percentage value from a string like '45.2%' or '45%'. Returns None if not found."""
    match = re.search(r"(\d+(?:\.\d+)?)%", text)
    return float(match.group(1)) if match else None
