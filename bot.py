#!/usr/bin/env python3
"""
ATERNOS TELEGRAM BOT
Бот для управления Minecraft Bedrock сервером на Aternos
Версия: 6.0 FINAL
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from threading import Thread

import requests
from flask import Flask, jsonify

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction

# ══════════════════════════════════════════════════════════════════
# КОНФИГ
# ══════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ATERNOS_USER = os.getenv("ATERNOS_USER", "")
ATERNOS_PASS = os.getenv("ATERNOS_PASS", "")
SERVER_ID = os.getenv("SERVER_ID", "")
LOG_CHAT_ID = os.getenv("LOG_CHAT_ID", "0")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)
log = logging.getLogger("bot")

# Проверка конфига
if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN не установлен! Бот не может запуститься.")
    sys.exit(1)

try:
    LOG_CHAT_ID = int(LOG_CHAT_ID)
except:
    LOG_CHAT_ID = 0

log.info("=" * 60)
log.info("🎮 ATERNOS BOT v6.0 — ЗАПУСК")
log.info("=" * 60)
log.info(f"Telegram токен: {'✅ установлен' if TELEGRAM_TOKEN else '❌ НЕТ'}")
log.info(f"Aternos логин: {ATERNOS_USER or '❌ НЕТ'}")
log.info(f"Server ID: {SERVER_ID or '❌ НЕТ'}")
log.info(f"Log chat ID: {LOG_CHAT_ID}")
log.info(f"Port: {PORT}")
log.info("=" * 60)

# ══════════════════════════════════════════════════════════════════
# ДАННЫЕ
# ══════════════════════════════════════════════════════════════════

STATS_FILE = "stats.json"
CONFIG_FILE = "config.json"

stats = {
    "starts": 0,
    "stops": 0,
    "last_start": None,
    "last_stop": None,
    "uptime_from": None,
    "peak_players": 0
}
config = {"log_chat_id": LOG_CHAT_ID}

telegram_app = None
sess = requests.Session()
sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

aternos_connected = False
server_status = "offline"
current_players = []


def load_data():
    global stats, config
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, encoding="utf-8") as f:
                stats.update(json.load(f))
        except Exception as e:
            log.warning(f"Не удалось загрузить stats: {e}")
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception as e:
            log.warning(f"Не удалось загрузить config: {e}")


def save_data():
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Ошибка сохранения данных: {e}")


# ══════════════════════════════════════════════════════════════════
# ATERNOS
# ══════════════════════════════════════════════════════════════════

def aternos_login():
    global aternos_connected
    if not ATERNOS_USER or not ATERNOS_PASS or not SERVER_ID:
        log.warning("⚠️ Данные Aternos не заполнены, пропускаю подключение")
        return False
    try:
        log.info("🔑 Подключаюсь к Aternos...")
        resp = sess.post(
            "https://aternos.org/panel/ajax/account/login.php",
            data={"user": ATERNOS_USER, "password": ATERNOS_PASS},
            timeout=15
        )
        if resp.status_code == 200:
            aternos_connected = True
            log.info("✅ Aternos подключен!")
            update_server_info()
            return True
        else:
            log.error(f"❌ Aternos логин: код {resp.status_code}")
            return False
    except Exception as e:
        log.error(f"❌ Ошибка подключения к Aternos: {e}")
        return False


def update_server_info():
    global server_status, current_players
    if not SERVER_ID:
        return False
    try:
        resp = sess.get(f"https://aternos.org/api/server/{SERVER_ID}", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            server_status = data.get("status", "offline")
            players = data.get("players", [])
            current_players = players if isinstance(players, list) else []
            return True
    except Exception as e:
        log.warning(f"⚠️ Не удалось обновить статус сервера: {e}")
    return False


def aternos_start():
    global server_status
    try:
        resp = sess.post(f"https://aternos.org/api/server/{SERVER_ID}/start", timeout=30)
        if resp.status_code in (200, 201):
            server_status = "online"
            return True
    except Exception as e:
        log.error(f"❌ Ошибка запуска сервера: {e}")
    return False


def aternos_stop():
    global server_status
    try:
        resp = sess.post(f"https://aternos.org/api/server/{SERVER_ID}/stop", timeout=30)
        if resp.status_code in (200, 201):
            server_status = "offline"
            return True
    except Exception as e:
        log.error(f"❌ Ошибка остановки сервера: {e}")
    return False


# ══════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════════════════════════

def status_icon(s):
    return {"online": "🟢", "offline": "🔴", "loading": "🟡", "starting": "🟡"}.get(s, "⚫")


def get_message(update: Update):
    return update.callback_query.message if update.callback_query else update.message


async def show_typing(update: Update):
    try:
        await get_message(update).chat.send_action(ChatAction.TYPING)
    except Exception:
        pass


async def send_log(text: str, chat_id=None):
    if not telegram_app:
        return
    target = chat_id or config.get("log_chat_id") or LOG_CHAT_ID
    if not target:
        return
    try:
        await telegram_app.bot.send_message(target, text, parse_mode="HTML")
    except Exception as e:
        log.error(f"❌ Не удалось отправить лог: {e}")


def user_label(update: Update):
    u = update.effective_user
    return f"@{u.username}" if u.username else u.first_name


MAIN_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 ЗАПУСТИТЬ", callback_data="on"),
     InlineKeyboardButton("🔴 ОСТАНОВИТЬ", callback_data="off")],
    [InlineKeyboardButton("👥 ИГРОКИ", callback_data="players")],
    [InlineKeyboardButton("📊 ИНФОРМАЦИЯ", callback_data="info"),
     InlineKeyboardButton("⚙️ СТАТУС", callback_data="status")],
])


# ══════════════════════════════════════════════════════════════════
# КОМАНДЫ TELEGRAM
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await show_typing(update)
    text = (
        "<b>🎮 ATERNOS BOT — fictionmine</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Aternos:</b> {'✅ подключен' if aternos_connected else '❌ не подключен'}\n"
        f"<b>Сервер:</b> {status_icon(server_status)} {server_status.upper()}\n"
        f"<b>Игроков:</b> {len(current_players)}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Команды:</b>\n"
        "• /on — запустить сервер\n"
        "• /off — остановить сервер\n"
        "• /players — список игроков\n"
        "• /status — статус сервера\n"
        "• /info — статистика\n"
        "• /logthischat — логи в этот чат\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await get_message(update).reply_text(text, reply_markup=MAIN_KEYBOARD, parse_mode="HTML")


async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global stats
    await show_typing(update)
    msg = await get_message(update).reply_text("<b>⏳ Запускаю сервер...</b>", parse_mode="HTML")

    if not aternos_connected:
        await msg.edit_text("❌ <b>Aternos не подключен.</b>\nПроверь логин/пароль в настройках.", parse_mode="HTML")
        await send_log(f"❌ Попытка запуска: Aternos не подключен\n👤 {user_label(update)}")
        return

    update_server_info()
    if server_status == "online":
        await msg.edit_text("✅ <b>Сервер уже включён!</b>", parse_mode="HTML")
        return

    if aternos_start():
        stats["starts"] += 1
        stats["last_start"] = datetime.now().isoformat()
        stats["uptime_from"] = datetime.now().isoformat()
        save_data()
        await msg.edit_text(
            "🟢 <b>СЕРВЕР ЗАПУЩЕН!</b>\n\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"📊 Всего запусков: {stats['starts']}\n\n"
            "<i>Сервер загружается, подожди пару минут</i>",
            parse_mode="HTML"
        )
        await send_log(
            f"🟢 <b>СЕРВЕР ЗАПУЩЕН</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"👤 {user_label(update)}\n"
            f"📊 Запусков всего: {stats['starts']}"
        )
    else:
        await msg.edit_text("❌ <b>Не удалось запустить сервер.</b>\nПопробуй ещё раз через минуту.", parse_mode="HTML")
        await send_log(f"❌ Ошибка запуска сервера\n👤 {user_label(update)}")


async def cmd_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global stats
    await show_typing(update)
    msg = await get_message(update).reply_text("<b>⏳ Останавливаю сервер...</b>", parse_mode="HTML")

    if not aternos_connected:
        await msg.edit_text("❌ <b>Aternos не подключен.</b>", parse_mode="HTML")
        return

    update_server_info()
    if server_status != "online":
        await msg.edit_text("🔴 <b>Сервер уже выключен!</b>", parse_mode="HTML")
        return

    if aternos_stop():
        stats["stops"] += 1
        stats["last_stop"] = datetime.now().isoformat()
        stats["uptime_from"] = None
        save_data()
        await msg.edit_text(
            "🔴 <b>СЕРВЕР ОСТАНОВЛЕН!</b>\n\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="HTML"
        )
        await send_log(
            f"🔴 <b>СЕРВЕР ОСТАНОВЛЕН</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"👤 {user_label(update)}"
        )
    else:
        await msg.edit_text("❌ <b>Не удалось остановить сервер.</b>", parse_mode="HTML")


async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global stats
    await show_typing(update)
    msg = await get_message(update).reply_text("<b>⏳ Проверяю игроков...</b>", parse_mode="HTML")

    update_server_info()
    if server_status != "online":
        await msg.edit_text("🔴 <b>Сервер выключен.</b>\nВключи его командой /on", parse_mode="HTML")
        return

    if not current_players:
        await msg.edit_text("👥 <b>Онлайн: 0 игроков</b>\n\nНикого нет 😿", parse_mode="HTML")
        return

    if len(current_players) > stats["peak_players"]:
        stats["peak_players"] = len(current_players)
        save_data()

    players_str = "\n".join(f"  • <b>{p}</b>" for p in current_players)
    await msg.edit_text(
        f"👥 <b>ОНЛАЙН: {len(current_players)} игрок(ов)</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n{players_str}",
        parse_mode="HTML"
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await show_typing(update)
    msg = await get_message(update).reply_text("<b>⏳ Проверяю статус...</b>", parse_mode="HTML")

    update_server_info()
    await msg.edit_text(
        f"{status_icon(server_status)} <b>СТАТУС СЕРВЕРА</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 Имя: fictionmine (Bedrock)\n"
        f"📍 Статус: {server_status.upper()}\n"
        f"👥 Игроков: {len(current_players)}\n"
        f"⏰ Проверено: {datetime.now().strftime('%H:%M:%S')}",
        parse_mode="HTML"
    )


async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await show_typing(update)
    msg = await get_message(update).reply_text("<b>⏳ Загружаю информацию...</b>", parse_mode="HTML")

    update_server_info()

    last_start = (
        datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M")
        if stats["last_start"] else "никогда"
    )
    last_stop = (
        datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")
        if stats["last_stop"] else "никогда"
    )

    uptime = "—"
    if stats["uptime_from"] and server_status == "online":
        delta = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
        h, m = delta.seconds // 3600, (delta.seconds % 3600) // 60
        uptime = f"{h}ч {m}м"

    await msg.edit_text(
        "<b>📊 ИНФОРМАЦИЯ О СЕРВЕРЕ</b>\n\n"
        f"🎮 fictionmine (Bedrock)\n"
        f"{status_icon(server_status)} {server_status.upper()}\n"
        f"👥 Игроков сейчас: {len(current_players)}\n\n"
        "<b>📈 Статистика:</b>\n"
        f"  Запусков: {stats['starts']}\n"
        f"  Остановок: {stats['stops']}\n"
        f"  Пик игроков: {stats['peak_players']}\n"
        f"  Время работы: {uptime}\n\n"
        "<b>⏰ Последние события:</b>\n"
        f"  Запуск: {last_start}\n"
        f"  Остановка: {last_stop}",
        parse_mode="HTML"
    )


async def cmd_logthischat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    config["log_chat_id"] = chat_id
    save_data()
    await update.message.reply_text(
        f"✅ <b>Готово!</b>\nЛоги теперь приходят в этот чат.\nID: <code>{chat_id}</code>",
        parse_mode="HTML"
    )
    await send_log(
        f"✅ <b>Чат для логов изменён</b>\n👤 {user_label(update)}\nID: <code>{chat_id}</code>",
        chat_id=chat_id
    )


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    handlers = {
        "on": cmd_on, "off": cmd_off, "players": cmd_players,
        "status": cmd_status, "info": cmd_info,
    }
    handler = handlers.get(query.data)
    if handler:
        await handler(update, ctx)


# ══════════════════════════════════════════════════════════════════
# АВТОМАТИЧЕСКИЙ ОТЧЁТ
# ══════════════════════════════════════════════════════════════════

async def auto_report_loop():
    await asyncio.sleep(30)
    while True:
        await asyncio.sleep(600)
        if not aternos_connected:
            continue
        update_server_info()
        if server_status != "online":
            continue
        try:
            uptime_line = ""
            if stats["uptime_from"]:
                delta = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
                h, m = delta.seconds // 3600, (delta.seconds % 3600) // 60
                uptime_line = f"⏱ Время работы: {h}ч {m}м\n"
            players_str = "\n".join(f"  • {p}" for p in current_players) if current_players else "  (никого)"
            await send_log(
                "🟢 <b>СЕРВЕР ОНЛАЙН</b> — автоотчёт\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"{uptime_line}"
                f"👥 Игроки ({len(current_players)}):\n{players_str}"
            )
        except Exception as e:
            log.error(f"Ошибка автоотчёта: {e}")


# ══════════════════════════════════════════════════════════════════
# FLASK (keep-alive для Render)
# ══════════════════════════════════════════════════════════════════

flask_app = Flask(__name__)


@flask_app.route("/")
def index():
    return jsonify({"status": "ok", "bot": "aternos-bot", "time": datetime.now().isoformat()}), 200


@flask_app.route("/ping")
def ping():
    return "pong", 200


@flask_app.route("/health")
def health():
    return jsonify({
        "aternos_connected": aternos_connected,
        "server_status": server_status,
        "players": len(current_players),
        "starts": stats["starts"],
    }), 200


def run_flask():
    log.info(f"🌐 Flask стартует на 0.0.0.0:{PORT}")
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)


# ══════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ
# ══════════════════════════════════════════════════════════════════

async def main():
    global telegram_app

    load_data()
    aternos_login()

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("on", cmd_on))
    telegram_app.add_handler(CommandHandler("off", cmd_off))
    telegram_app.add_handler(CommandHandler("players", cmd_players))
    telegram_app.add_handler(CommandHandler("status", cmd_status))
    telegram_app.add_handler(CommandHandler("info", cmd_info))
    telegram_app.add_handler(CommandHandler("logthischat", cmd_logthischat))
    telegram_app.add_handler(CallbackQueryHandler(on_button))

    log.info("✅ Telegram бот настроен, запускаю polling...")

    asyncio.create_task(auto_report_loop())

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    # держим процесс живым
    await asyncio.Event().wait()


if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Бот остановлен вручную")
    except Exception as e:
        log.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
