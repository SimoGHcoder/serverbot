"""Telegram keyboards. Dynamic callback data uses short per-user references."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖥 Stato server", callback_data="status"), InlineKeyboardButton("🐳 Container", callback_data="containers")],
        [InlineKeyboardButton("🛡 Log DIUN", callback_data="diun_logs"), InlineKeyboardButton("🔀 OmniRoute", callback_data="omniroute")],
        [InlineKeyboardButton("� Metriche", callback_data="metrics"), InlineKeyboardButton("�🗑 Alea", callback_data="alea")],
    ])


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data="menu")]])


def container_list(containers: list[dict], refs: dict[str, dict]) -> InlineKeyboardMarkup:
    # refs maps token -> {"name": ..., "expires": ...}; build the reverse map
    # in one pass. Docker guarantees unique container names, so this is safe.
    reverse = {entry["name"]: token for token, entry in refs.items()}
    rows = []
    for item in containers:
        icon = "🟢" if item["running"] and item["health"] != "unhealthy" else "🔴" if not item["running"] else "🟡"
        token = reverse.get(item["name"])
        if token is None:
            continue
        rows.append([InlineKeyboardButton(f"{icon} {item['name'][:45]}", callback_data=f"container:{token}")])
    rows.append([InlineKeyboardButton("🔄 Riavvia servizi attivi…", callback_data="confirm:restart_all:all")])
    rows.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def container_actions(token: str, running: bool) -> InlineKeyboardMarkup:
    primary = "stop" if running else "start"
    label = "Arresta" if running else "Avvia"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Riavvia…", callback_data=f"confirm:restart:{token}"), InlineKeyboardButton(f"{label}…", callback_data=f"confirm:{primary}:{token}")],
        [InlineKeyboardButton("📜 Log recenti", callback_data=f"logs:{token}")],
        [InlineKeyboardButton("⬅️ Container", callback_data="containers")],
    ])


def confirm_action(challenge: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Conferma", callback_data=f"execute:{challenge}"),
        InlineKeyboardButton("❌ Annulla", callback_data="cancel"),
    ]])


def alea_menu(current_time: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Verifica domani", callback_data="alea_check")],
        [InlineKeyboardButton(f"Orario {current_time} · Modifica", callback_data="alea_time")],
        [InlineKeyboardButton("⬅️ Menu", callback_data="menu")],
    ])
