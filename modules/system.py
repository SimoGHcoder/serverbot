"""Read-only host metrics from procfs and filesystem APIs; no shell commands."""
from __future__ import annotations

import os
import shutil
import time


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


def _disk(path: str) -> str:
    try:
        usage = shutil.disk_usage(path)
        return f"{_human(usage.used)} / {_human(usage.total)} ({usage.used * 100 // usage.total}%)"
    except OSError:
        return "non disponibile"


def get_host_status() -> dict[str, str]:
    try:
        with open("/proc/uptime", encoding="ascii") as file:
            seconds = int(float(file.readline().split()[0]))
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes = remainder // 60
        uptime = f"{days}g {hours}h {minutes}m"
    except (OSError, ValueError, IndexError):
        uptime = "non disponibile"
    try:
        values = {}
        with open("/proc/meminfo", encoding="ascii") as file:
            for line in file:
                if line.startswith(("MemTotal:", "MemAvailable:")):
                    key, value, *_ = line.split()
                    values[key[:-1]] = int(value) * 1024
        total, available = values["MemTotal"], values["MemAvailable"]
        memory = f"{_human(total - available)} / {_human(total)} ({(total - available) * 100 // total}%)"
    except (OSError, ValueError, KeyError):
        memory = "non disponibile"
    try:
        with open("/proc/loadavg", encoding="ascii") as file:
            load = " / ".join(file.readline().split()[:3])
    except OSError:
        load = "non disponibile"
    storage_path = "/mnt/storage_immich" if os.path.ismount("/mnt/storage_immich") else "/mnt"
    return {"uptime": uptime, "memory": memory, "root_disk": _disk("/"), "storage_disk": _disk(storage_path), "load": load}


def format_uptime(uptime_raw: str) -> str:
    return uptime_raw


def get_home_dashboard() -> str:
    status = get_host_status()
    return "\n".join(f"{key}: {value}" for key, value in status.items())
