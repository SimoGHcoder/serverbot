"""Docker operations through the SDK; no shell, pull-on-check, or implicit update."""
from __future__ import annotations

import logging
from typing import Any

import docker
from docker.errors import APIError, DockerException, NotFound

logger = logging.getLogger("ServerBot.Docker")
_client: docker.DockerClient | None = None


class DockerUnavailable(RuntimeError):
    pass


class ContainerOperationError(RuntimeError):
    pass


def get_client() -> docker.DockerClient:
    global _client
    if _client is None:
        try:
            _client = docker.from_env(timeout=10)
            _client.ping()
        except DockerException as exc:
            _client = None
            raise DockerUnavailable from exc
    return _client


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def list_containers() -> list[dict[str, Any]]:
    try:
        client = get_client()
        results = []
        for container in client.containers.list(all=True):
            container.reload()
            state = container.attrs.get("State", {})
            health = state.get("Health", {}).get("Status", "n/a")
            results.append({
                "name": container.name,
                "status": state.get("Status", container.status),
                "health": health,
                "running": state.get("Running", False),
                "image": container.image.tags[0] if container.image.tags else container.image.short_id,
            })
        return sorted(results, key=lambda row: row["name"].casefold())
    except DockerUnavailable:
        raise
    except DockerException as exc:
        raise DockerUnavailable from exc


def get_container(name: str) -> dict[str, Any]:
    try:
        container = get_client().containers.get(name)
        container.reload()
        state = container.attrs.get("State", {})
        mounts = [
            f"{m.get('Source','?')} → {m.get('Destination','?')} ({'rw' if m.get('RW') else 'ro'})"
            for m in container.attrs.get("Mounts", [])
        ]
        try:
            image = container.image.tags[0] if container.image.tags else container.image.short_id
        except docker.errors.ImageNotFound:
            image = "<removed>"
        return {
            "name": container.name,
            "status": state.get("Status", container.status),
            "health": state.get("Health", {}).get("Status", "n/a"),
            "running": state.get("Running", False),
            "image": image,
            "started": state.get("StartedAt", "unknown"),
            "restart_count": container.attrs.get("RestartCount", 0),
            "mounts": mounts,
        }
    except (DockerException, NotFound) as exc:
        raise ContainerOperationError from exc


def format_container(item: dict[str, Any]) -> str:
    mounts = item["mounts"][:5]
    mount_text = "\n".join(f"• {line}" for line in mounts) or "• Nessun mount"
    return (
        f"🐳 <b>{item['name']}</b>\n"
        f"Stato: {item['status']} · Health: {item['health']}\n"
        f"Immagine: <code>{item['image']}</code>\n"
        f"Avvii: {item['restart_count']}\nMount:\n{mount_text}"
    )


def perform(action: str, name: str) -> None:
    if action not in {"start", "stop", "restart"}:
        raise ValueError("Unsupported Docker action")
    try:
        container = get_client().containers.get(name)
        if action == "start":
            container.start()
        elif action == "stop":
            container.stop(timeout=15)
        else:
            container.restart(timeout=15)
    except (DockerException, NotFound) as exc:
        logger.error("Container action failed (%s)", type(exc).__name__)
        raise ContainerOperationError from exc


def restart_all(exclude: set[str] | None = None) -> list[tuple[str, Exception | None]]:
    excluded = exclude or set()
    results: list[tuple[str, Exception | None]] = []
    for item in list_containers():
        if not item["running"] or item["name"] in excluded:
            continue
        try:
            perform("restart", item["name"])
            results.append((item["name"], None))
        except ContainerOperationError as exc:
            results.append((item["name"], exc))
    return results


def get_logs(name: str, lines: int = 60) -> str:
    if not 1 <= lines <= 200:
        raise ValueError("Log line count out of range")
    try:
        raw = get_client().containers.get(name).logs(tail=lines, timestamps=True)
        return raw.decode("utf-8", errors="replace")[-12000:]
    except (DockerException, NotFound) as exc:
        raise ContainerOperationError from exc
