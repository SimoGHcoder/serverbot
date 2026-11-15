"""Send the host updater's summary buffer once, without exposing arbitrary file data."""
from __future__ import annotations

import json
import logging
import os
from telegram import Bot
from telegram.constants import ParseMode
from html import escape

logger = logging.getLogger("ServerBot.Updates")
BUFFER_FILE = "/opt/server-bot/logs/os_updates_buffer.json"


async def check_and_send_os_updates(bot: Bot, chat_id: str) -> None:
    if not os.path.isfile(BUFFER_FILE):
        return
    try:
        with open(BUFFER_FILE, encoding="utf-8") as file:
            data = json.load(file)
        packages = data.get("packages", []) if isinstance(data, dict) else []
        if not isinstance(packages, list):
            raise ValueError("invalid package list")
        unique = list(dict.fromkeys(str(item)[:120] for item in packages if isinstance(item, str)))[:40]
        if unique:
            text = "🛠 <b>Aggiornamenti host rilevati</b>\n" + "\n".join(f"• <code>{escape(item)}</code>" for item in unique)
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        try:
            os.unlink(BUFFER_FILE)
        except OSError as unlink_exc:
            logger.error("Could not remove update buffer (%s)", type(unlink_exc).__name__)
    except Exception as exc:
        logger.error("Could not process update buffer (%s)", type(exc).__name__)
