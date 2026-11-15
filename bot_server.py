"""Server Bot entry point. All secrets are loaded from the host-wide /opt/.env."""
from __future__ import annotations

import asyncio
import datetime as dt
import hmac
import logging
import secrets
import threading
from html import escape
from typing import Any
from zoneinfo import ZoneInfo
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Header, HTTPException, Request
import uvicorn
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from modules.settings import SETTINGS
from modules import alea, db, diun, docker_mgr, keyboards, metrics, omniroute_mgr, system, system_updates
from modules.authorization import authorized_user

logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            "/opt/server-bot/logs/bot.log", maxBytes=5 * 1024 * 1024,
            backupCount=3, encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("ServerBot")
web_app = FastAPI(title="Server Bot internal webhook", docs_url=None, redoc_url=None)
_telegram_application: Application | None = None
_telegram_loop: asyncio.AbstractEventLoop | None = None
_webhook_server: uvicorn.Server | None = None
_webhook_thread: threading.Thread | None = None
_last_container_states: dict[str, str] = {}


@web_app.post("/webhook/omniroute")
async def omniroute_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Accept only small, authenticated events; disabled unless a shared secret exists."""
    secret = SETTINGS.omniroute_webhook_token
    if not secret:
        raise HTTPException(status_code=404, detail="Not found")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not hmac.compare_digest(supplied, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(status_code=413, detail="Event too large")
    try:
        import json
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid event")
    event = str(payload.get("event") or "System alert")[:120]
    message = str(payload.get("message") or "No details")[:1000]
    db.log_omniroute_event(event, message)
    if _telegram_application and _telegram_loop and SETTINGS.allowed_user_id:
        safe_text = (
            "🚨 <b>OmniRoute alert</b>\n\n"
            f"<b>Evento:</b> {escape(event)}\n<b>Dettagli:</b> {escape(message)}"
        )
        future = asyncio.run_coroutine_threadsafe(
            _telegram_application.bot.send_message(
                chat_id=SETTINGS.allowed_user_id, text=safe_text, parse_mode=ParseMode.HTML,
            ),
            _telegram_loop,
        )
        try:
            await asyncio.wrap_future(future)
        except Exception as exc:
            logger.error("Webhook notification failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Notification unavailable") from None
    return {"status": "accepted"}


def _start_webhook_server() -> None:
    global _webhook_server, _webhook_thread
    if not SETTINGS.omniroute_webhook_token:
        logger.info("OmniRoute webhook disabled: shared token is not configured")
        return
    config = uvicorn.Config(web_app, host="0.0.0.0", port=8000, log_level="warning")
    _webhook_server = uvicorn.Server(config)
    _webhook_thread = threading.Thread(target=_webhook_server.run, name="internal-webhook", daemon=True)
    _webhook_thread.start()


async def _authorized(update: Update) -> bool:
    if authorized_user(update):
        return True
    query = update.callback_query
    if query:
        await query.answer("Accesso non autorizzato.", show_alert=True)
    return False


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update) or not update.effective_message:
        return
    await update.effective_message.reply_text(
        "🖥️ <b>NERD-HUB · Centro di controllo</b>\nSeleziona l'area da gestire.",
        reply_markup=keyboards.main_menu(), parse_mode=ParseMode.HTML,
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update) or not update.effective_message:
        return
    await update.effective_message.reply_text(
        await _system_status_text(), parse_mode=ParseMode.HTML,
        reply_markup=keyboards.main_menu(),
    )


async def orario_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update) or not update.effective_message:
        return
    if context.args:
        value = context.args[0]
        try:
            dt.datetime.strptime(value, "%H:%M")
        except ValueError:
            await update.effective_message.reply_text("Formato richiesto: <code>HH:MM</code>.", parse_mode=ParseMode.HTML)
            return
        alea.set_notification_time(value)
        await update.effective_message.reply_text(f"Orario Alea impostato a <b>{escape(value)}</b>.", parse_mode=ParseMode.HTML)
        return
    current = alea.get_notification_time()
    await update.effective_message.reply_text(
        f"Orario Alea attuale: <b>{escape(current)}</b>\nUsa <code>/orario HH:MM</code> per cambiarlo.",
        parse_mode=ParseMode.HTML,
    )


async def _system_status_text() -> str:
    host = system.get_host_status()
    try:
        containers = docker_mgr.list_containers()
        docker_line = f"{sum(c['running'] for c in containers)} attivi / {len(containers)} totali"
    except docker_mgr.DockerUnavailable:
        docker_line = "Docker non raggiungibile"
    return (
        "🖥️ <b>STATO SERVER</b>\n"
        f"⏱ Uptime: {escape(host['uptime'])}\n"
        f"🧠 RAM: {escape(host['memory'])}\n"
        f"💽 Root: {escape(host['root_disk'])}\n"
        f"📦 Storage: {escape(host['storage_disk'])}\n"
        f"⚙️ Carico: {escape(host['load'])}\n"
        f"🐳 Container: {escape(docker_line)}"
    )


def _pending_map(context: ContextTypes.DEFAULT_TYPE) -> dict[str, dict[str, Any]]:
    if context.user_data is None:
        context.user_data = {}
    return context.user_data.setdefault("pending_actions", {})


def _resolve_container_ref(context: ContextTypes.DEFAULT_TYPE, token: str) -> str | None:
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    refs = context.user_data.get("container_refs", {})
    # Purge expired refs to avoid an unbounded per-user memory leak.
    context.user_data["container_refs"] = {
        t: e for t, e in refs.items() if isinstance(e, dict) and e.get("expires", 0) >= now
    }
    entry = context.user_data["container_refs"].get(token)
    if not isinstance(entry, dict) or entry.get("expires", 0) < now:
        return None
    return entry.get("name")


async def _show_container_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        containers = docker_mgr.list_containers()
    except docker_mgr.DockerUnavailable:
        await query.edit_message_text("Docker non è raggiungibile dal bot.", reply_markup=keyboards.back_menu())
        return
    expiry = dt.datetime.now(dt.timezone.utc).timestamp() + 300
    refs = {secrets.token_urlsafe(5): {"name": item["name"], "expires": expiry} for item in containers}
    context.user_data["container_refs"] = refs
    await query.edit_message_text(
        f"🐳 <b>CONTAINER</b> · {len(containers)} rilevati",
        reply_markup=keyboards.container_list(containers, refs), parse_mode=ParseMode.HTML,
    )


async def _ask_confirmation(query: Any, context: ContextTypes.DEFAULT_TYPE, action: str, name: str | None) -> None:
    challenge = secrets.token_urlsafe(6)
    _pending_map(context)[challenge] = {
        "action": action,
        "name": name,
        "expires": dt.datetime.now(dt.timezone.utc).timestamp() + 90,
    }
    target = f" <code>{escape(name)}</code>" if name else " tutti i container"
    label = {"start": "avviare", "stop": "arrestare", "restart": "riavviare", "restart_all": "riavviare"}.get(action, "eseguire")
    await query.edit_message_text(
        f"Confermi di {label}{target}? La conferma scade tra 90 secondi.",
        reply_markup=keyboards.confirm_action(challenge), parse_mode=ParseMode.HTML,
    )


async def _execute_action(query: Any, context: ContextTypes.DEFAULT_TYPE, challenge: str) -> None:
    pending = _pending_map(context).pop(challenge, None)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    if not pending or pending["expires"] < now:
        await query.edit_message_text("Conferma scaduta. Riapri il menu e riprova.", reply_markup=keyboards.back_menu())
        return
    action, name = pending["action"], pending["name"]
    actor = query.from_user.id
    try:
        if action == "restart_all":
            result = docker_mgr.restart_all(exclude={SETTINGS.container_name})
            successes = [item for item, error in result if error is None]
            failures = [item for item, error in result if error is not None]
            db.log_action(actor, action, ",".join(successes), "partial" if failures else "ok")
            body = f"Completato: {len(successes)}. Errori: {len(failures)}."
        elif action in {"start", "stop", "restart"} and name:
            docker_mgr.perform(action, name)
            db.log_action(actor, action, name, "ok")
            body = f"Operazione <b>{escape(action)}</b> completata per <code>{escape(name)}</code>."
        else:
            raise ValueError("Unsupported action")
    except (docker_mgr.DockerUnavailable, docker_mgr.ContainerOperationError, ValueError) as exc:
        db.log_action(actor, action, name or "", "error:" + type(exc).__name__)
        body = f"Operazione non completata (<code>{escape(type(exc).__name__)}</code>)."
    await query.edit_message_text(body, reply_markup=keyboards.back_menu(), parse_mode=ParseMode.HTML)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if data != "alea_time":
        context.user_data["awaiting_alea_time"] = False
    try:
        if data == "menu":
            await query.edit_message_text("🖥️ <b>NERD-HUB · Centro di controllo</b>", reply_markup=keyboards.main_menu(), parse_mode=ParseMode.HTML)
        elif data == "status":
            await query.edit_message_text(await _system_status_text(), reply_markup=keyboards.main_menu(), parse_mode=ParseMode.HTML)
        elif data == "containers":
            await _show_container_list(update, context)
        elif data.startswith("container:"):
            token = data.split(":", 1)[1]
            name = _resolve_container_ref(context, token)
            if not name:
                await query.edit_message_text("Elenco scaduto: riaprilo e seleziona di nuovo.", reply_markup=keyboards.back_menu())
                return
            detail = docker_mgr.get_container(name)
            token = secrets.token_urlsafe(5)
            context.user_data.setdefault("container_refs", {})[token] = {
                "name": name,
                "expires": dt.datetime.now(dt.timezone.utc).timestamp() + 300,
            }
            await query.edit_message_text(
                docker_mgr.format_container(detail),
                reply_markup=keyboards.container_actions(token, detail["running"]),
                parse_mode=ParseMode.HTML,
            )
        elif data.startswith("confirm:"):
            _, action, token = data.split(":", 2)
            if action == "restart_all":
                await _ask_confirmation(query, context, action, None)
            else:
                name = _resolve_container_ref(context, token)
                if not name or action not in {"start", "stop", "restart"}:
                    await query.edit_message_text("Azione non valida o scaduta.", reply_markup=keyboards.back_menu())
                    return
                await _ask_confirmation(query, context, action, name)
        elif data.startswith("execute:"):
            await _execute_action(query, context, data.split(":", 1)[1])
        elif data.startswith("logs:"):
            token = data.split(":", 1)[1]
            name = _resolve_container_ref(context, token)
            if not name:
                await query.edit_message_text("Elenco scaduto.", reply_markup=keyboards.back_menu())
                return
            text = docker_mgr.get_logs(name, lines=60)
            safe = escape(text[-3200:] or "(nessun log)")
            await query.edit_message_text(f"<b>Log: {escape(name)}</b>\n<pre>{safe}</pre>", reply_markup=keyboards.back_menu(), parse_mode=ParseMode.HTML)
        elif data == "diun_logs":
            safe = escape(diun.get_diun_logs(40)[-3200:] or "(nessun log)")
            await query.edit_message_text(f"<b>Log DIUN</b>\n<pre>{safe}</pre>", reply_markup=keyboards.back_menu(), parse_mode=ParseMode.HTML)
        elif data == "omniroute":
            state = omniroute_mgr.get_status()
            await query.edit_message_text(escape(state), reply_markup=keyboards.back_menu())
        elif data == "alea":
            when = alea.get_notification_time()
            date, items = alea.get_collection_for_tomorrow_str()
            await query.edit_message_text(
                f"🗑️ <b>ALEA</b>\nDomani ({escape(date)}): {escape(', '.join(items) or 'nessun rifiuto')}\nOrario: {escape(when)}",
                reply_markup=keyboards.alea_menu(when), parse_mode=ParseMode.HTML,
            )
        elif data == "alea_check":
            date, items = alea.get_collection_for_tomorrow_str()
            await query.edit_message_text(
                f"Domani ({escape(date)}): {escape(', '.join(items) or 'nessun rifiuto')}.",
                reply_markup=keyboards.back_menu(), parse_mode=ParseMode.HTML,
            )
        elif data == "metrics":
            current = metrics.get_numeric_metrics()
            report = metrics.format_metrics_report(current, history_minutes=60)
            await query.edit_message_text(report, reply_markup=keyboards.back_menu(), parse_mode=ParseMode.HTML)
        elif data == "alea_time":
            context.user_data["awaiting_alea_time"] = True
            await query.edit_message_text("Invia il nuovo orario nel formato <code>HH:MM</code>.", parse_mode=ParseMode.HTML, reply_markup=keyboards.back_menu())
        elif data == "cancel":
            await query.edit_message_text("Operazione annullata.", reply_markup=keyboards.main_menu())
        else:
            await query.edit_message_text("Comando non riconosciuto.", reply_markup=keyboards.main_menu())
    except docker_mgr.ContainerOperationError as exc:
        await query.edit_message_text(f"Operazione non disponibile (<code>{escape(type(exc).__name__)}</code>).", parse_mode=ParseMode.HTML, reply_markup=keyboards.back_menu())
    except Exception as exc:
        logger.error("Callback failed (%s)", type(exc).__name__)
        await query.edit_message_text("Errore durante l'operazione. Controlla i log locali del bot.", reply_markup=keyboards.back_menu())


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update) or not update.effective_message:
        return
    if not context.user_data.get("awaiting_alea_time"):
        return
    value = (update.effective_message.text or "").strip()
    try:
        dt.datetime.strptime(value, "%H:%M")
    except ValueError:
        await update.effective_message.reply_text("Formato non valido; usa <code>HH:MM</code>.", parse_mode=ParseMode.HTML)
        return
    alea.set_notification_time(value)
    context.user_data["awaiting_alea_time"] = False
    db.log_action(update.effective_user.id, "alea_set_time", value, "ok")
    await update.effective_message.reply_text(f"Orario Alea impostato a <b>{escape(value)}</b>.", parse_mode=ParseMode.HTML)


async def watchdog_task(application: Application) -> None:
    global _last_container_states
    while True:
        await asyncio.sleep(60)
        try:
            containers = docker_mgr.list_containers()
        except docker_mgr.DockerUnavailable:
            logger.warning("Watchdog could not reach Docker")
            continue
        current = {item["name"]: item["status"] for item in containers}
        if _last_container_states:
            for name, status in current.items():
                previous = _last_container_states.get(name)
                if previous and previous != status:
                    text = f"⚠️ <b>Docker state changed</b>\n<code>{escape(name)}</code>: {escape(previous)} → {escape(status)}"
                    await application.bot.send_message(SETTINGS.allowed_user_id, text, parse_mode=ParseMode.HTML)
        _last_container_states = current
        db.save_container_states(current)


async def alea_reminder_task(application: Application) -> None:
    timezone = ZoneInfo(SETTINGS.timezone)
    while True:
        now = dt.datetime.now(timezone)
        try:
            time_str = alea.get_notification_time()
            hour, minute = map(int, time_str.split(":"))
            if now.hour == hour and now.minute == minute:
                date, items = alea.get_collection_for_tomorrow_str()
                if items:
                    text = f"🗑️ <b>Promemoria Alea</b> · {escape(date)}\n{escape(', '.join(items))}"
                    await application.bot.send_message(SETTINGS.allowed_user_id, text, parse_mode=ParseMode.HTML)
                await asyncio.sleep(65)
            else:
                # Sleep until the next minute boundary to avoid drift and double-fires.
                await asyncio.sleep(max(1, 60 - now.second))
        except ValueError:
            logger.error("Invalid Alea notification time: %r", alea.get_notification_time())
            await asyncio.sleep(60)
        except Exception as exc:
            logger.error("Alea reminder failed (%s)", type(exc).__name__)
            await asyncio.sleep(60)


async def post_init(application: Application) -> None:
    global _telegram_application, _telegram_loop, _last_container_states
    if not SETTINGS.allowed_user_id:
        raise RuntimeError("ALLOWED_USER_ID must be a positive integer before starting background tasks")
    _telegram_application = application
    _telegram_loop = asyncio.get_running_loop()
    db.init_db()
    _last_container_states = db.get_container_states()
    _start_webhook_server()
    await application.bot.send_message(SETTINGS.allowed_user_id, f"🤖 Server Bot {escape(SETTINGS.bot_version)} avviato.", parse_mode=ParseMode.HTML)
    await system_updates.check_and_send_os_updates(application.bot, str(SETTINGS.allowed_user_id))
    tasks = [
        asyncio.create_task(watchdog_task(application)),
        asyncio.create_task(alea_reminder_task(application)),
        asyncio.create_task(metrics_task(application)),
    ]
    application.bot_data["background_tasks"] = tasks


async def post_shutdown(application: Application) -> None:
    global _webhook_server, _webhook_thread
    for task in application.bot_data.get("background_tasks", []):
        task.cancel()
    if application.bot_data.get("background_tasks"):
        await asyncio.gather(*application.bot_data["background_tasks"], return_exceptions=True)
    if _webhook_server:
        _webhook_server.should_exit = True
    if _webhook_thread and _webhook_thread.is_alive():
        await asyncio.to_thread(_webhook_thread.join, 5)
    docker_mgr.close_client()

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    logger.error("Telegram update failed (%s)", type(error).__name__ if error else "unknown")
    if isinstance(update, Update) and update.effective_message and authorized_user(update):
        await update.effective_message.reply_text("Richiesta non completata. Controlla i log locali del bot.")


def main() -> None:
    if not SETTINGS.telegram_token:
        raise RuntimeError("Token Telegram assente dal file globale /opt/.env")
    if not SETTINGS.allowed_user_id:
        raise RuntimeError("Impostare ALLOWED_USER_ID nel file globale /opt/.env")
    application = (
        ApplicationBuilder()
        .token(SETTINGS.telegram_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("orario", orario_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    application.add_error_handler(error_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
