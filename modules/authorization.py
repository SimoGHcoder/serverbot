"""Telegram identity checks shared by every command and callback."""
from telegram import Update
from modules.settings import SETTINGS


def authorized_user(update: Update) -> bool:
    user = update.effective_user
    return bool(user and SETTINGS.allowed_user_id > 0 and user.id == SETTINGS.allowed_user_id)
