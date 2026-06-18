#!/usr/bin/env python3
"""
ATERNOS TELEGRAM BOT v8.0 — RAILWAY EDITION
Управління Minecraft Bedrock сервером на Aternos
Оптимізований для Railway.app (512MB RAM, 8 годин/день)
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from threading import Thread
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from flask import Flask, jsonify

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction

# ══════════════════════════════════════════════════════════════════
# КОНФІГ
# ══════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ATERNOS_USER = os.getenv("ATERNOS_USER", "")
ATERNOS_PASS = os.getenv("ATERNOS_PASS", "")
SERVER_ID = os.getenv("SERVER_ID", "")
LOG_CHAT_ID_RAW = os.getenv("LOG_CHAT_ID", "0")
PORT = int(os.getenv("PORT", "5000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)
log = logging.getLogger("bot")

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN не встановлено!")
    sys.exit(1)

try:
    LOG_CHAT_ID = int(LOG_CHAT_ID_RAW)
except Exception:
    LOG_CHAT_ID = 0

log.info("=" * 60)
log.info("🎮 ATERNOS BOT v8.0 — RAILWAY EDITION")
log.info("=" * 60)
log.info(f"Aternos: {ATERNOS_USER or '❌ НЕ ВСТАНОВЛЕНО'}")
log.info(f"Server: {SERVER_ID or '❌ НЕ ВСТАНОВЛЕНО'}")
log.info(f"Log chat: {LOG_CHAT_ID}")
log.info(f"Port: {PORT}")
log.info("=" * 60)

# ══════════════════════════════════════════════════════════════════
# ДАНІ
# ══════════════════════════════════════════════════════════════════

STATS_FILE = "stats.json"
CONFIG_FILE = "config.json"

stats = {
    "starts": 0, "stops": 0, "last_start": None,
    "last_stop": None, "uptime_from": None, "peak_players": 0
}
config = {"log_chat_id": LOG_CHAT_ID}

telegram_app = None
sess = requests.Session()

# Retry策略 для Aternos
retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
sess.mount('http://', adapter)
sess.mount('https://', adapter)
sess.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

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
            log.warning(f"⚠️ Ошибка load stats: {e}")
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception as e:
            log.warning(f"⚠️ Ошибка load config: {e}")


def save_data():
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"❌ Ошибка save: {e}")


# ══════════════════════════════════════════════════════════════════
# ATERNOS API (REQUESTS - ПРОСТОЙ ПОДХОД)
# ══════════════════════════════════════════════════════════════════

def aternos_login():
    """Логін в Aternos з поліпшеними заголовками"""
    global aternos_connected
    
    if not ATERNOS_USER or not ATERNOS_PASS or not SERVER_ID:
        log.warning("⚠️ Aternos дані не встановлені, пропускаю")
        return False
    
    try:
        log.info("🔑 Логінюсь в Aternos...")
        
        # Спочатку отримуємо сторінку щоб скопіювати куки
        resp = sess.get("https://aternos.org/go/", timeout=15)
        
        # Логін з поліпшеними заголовками (типу справжнього браузера)
        sess.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://aternos.org/go/",
        })
        
        resp = sess.post(
            "https://aternos.org/panel/ajax/account/login.php",
            data={
                "user": ATERNOS_USER,
                "password": ATERNOS_PASS,
            },
            timeout=15
        )
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                if not data.get("error"):
                    aternos_connected = True
                    log.info("✅ Логін успішний!")
                    update_server_info()
                    return True
            except Exception:
                # Якщо 200 але не JSON - вважаємо успіхом
                aternos_connected = True
                log.info("✅ Логін ймовірно успішний (не-JSON відповідь)")
                return True
        
        log.error(f"❌ Логін помилка: {resp.status_code}")
        return False
        
    except Exception as e:
        log.error(f"❌ Ошибка логіну: {e}")
        return False


def update_server_info():
    """Обновити інформацію про сервер"""
    global server_status, current_players
    try:
        url = f"https://aternos.org/api/server/{SERVER_ID}"
        resp = sess.get(url, timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            server_status = data.get("status", "offline")
            players = data.get("players", [])
            current_players = players if isinstance(players, list) else []
        return True
    except Exception as e:
        log.warning(f"⚠️ Ошибка update info: {e}")
        return False


def aternos_start():
    """Запустити сервер"""
    global server_status
    try:
        url = f"https://aternos.org/api/server/{SERVER_ID}/start"
        resp = sess.post(url, timeout=30)
        
        if resp.status_code in [200, 201]:
            server_status = "starting"
            log.info("✅ Сервер запущено!")
            return True
        
        log.warning(f"⚠️ Start статус: {resp.status_code}")
        return False
    except Exception as e:
        log.error(f"❌ Ошибка старт: {e}")
        return False


def aternos_stop():
    """Зупинити сервер"""
    global server_status
    try:
        url = f"https://aternos.org/api/server/{SERVER_ID}/stop"
        resp = sess.post(url, timeout=30)
        
        if resp.status_code in [200, 201]:
            server_status = "offline"
            log.info("✅ Сервер зупинено!")
            return True
        
        log.warning(f"⚠️ Stop статус: {resp.status_code}")
        return False
    except Exception as e:
        log.error(f"❌ Ошибка стоп: {e}")
        return False


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def icon(s):
    return {"online": "🟢", "offline": "🔴", "starting": "🟡"}.get(s, "⚫")


def get_msg(update: Update):
    return update.callback_query.message if update.callback_query else update.message


async def typing(update: Update):
    try:
        await get_msg(update).chat.send_action(ChatAction.TYPING)
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
        log.error(f"❌ send_log: {e}")


def user_label(update: Update):
    u = update.effective_user
    return f"@{u.username}" if u.username else u.first_name


KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 ЗАПУСТИТИ", callback_data="on"),
     InlineKeyboardButton("🔴 ЗУПИНИТИ", callback_data="off")],
    [InlineKeyboardButton("👥 ГРАВЦІ", callback_data="players")],
    [InlineKeyboardButton("📊 ІНФО", callback_data="info"),
     InlineKeyboardButton("⚙️ СТАТУС", callback_data="status")],
])


# ══════════════════════════════════════════════════════════════════
# КОМАНДИ
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await typing(update)
    text = (
        "<b>🎮 ATERNOS BOT — fictionmine</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Aternos:</b> {'✅' if aternos_connected else '❌'}\n"
        f"<b>Сервер:</b> {icon(server_status)} {server_status.upper()}\n"
        f"<b>Гравців:</b> {len(current_players)}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Команди:</b>\n"
        "• /on — запустити\n"
        "• /off — зупинити\n"
        "• /players — гравці\n"
        "• /status — статус\n"
        "• /info — інфо\n"
        "• /logthischat — логи тут\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await get_msg(update).reply_text(text, reply_markup=KB, parse_mode="HTML")


async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Запускаю...</b>", parse_mode="HTML")

    if not aternos_connected:
        await msg.edit_text("❌ <b>Aternos не підключено!</b>", parse_mode="HTML")
        await send_log(f"❌ Спроба старту: Aternos не логін\n👤 {user_label(update)}")
        return

    update_server_info()
    if server_status == "online":
        await msg.edit_text("✅ <b>Уже включений!</b>", parse_mode="HTML")
        return

    if aternos_start():
        stats["starts"] += 1
        stats["last_start"] = datetime.now().isoformat()
        stats["uptime_from"] = datetime.now().isoformat()
        save_data()
        
        await msg.edit_text(
            "🟢 <b>ЗАПУЩЕНО!</b>\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"📊 Всього: {stats['starts']}",
            parse_mode="HTML"
        )
        await send_log(
            f"🟢 <b>СЕРВЕР ЗАПУЩЕНО</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"👤 {user_label(update)}\n"
            f"📊 {stats['starts']}"
        )
    else:
        await msg.edit_text("❌ <b>Не вдалось!</b>", parse_mode="HTML")
        await send_log(f"❌ Ошибка старту\n👤 {user_label(update)}")


async def cmd_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Зупиняю...</b>", parse_mode="HTML")

    if not aternos_connected:
        await msg.edit_text("❌ <b>Aternos не підключено!</b>", parse_mode="HTML")
        return

    update_server_info()
    if server_status != "online":
        await msg.edit_text("🔴 <b>Уже вимкнений!</b>", parse_mode="HTML")
        return

    if aternos_stop():
        stats["stops"] += 1
        stats["last_stop"] = datetime.now().isoformat()
        save_data()
        
        await msg.edit_text(
            "🔴 <b>ЗУПИНЕНО!</b>\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="HTML"
        )
        await send_log(
            f"🔴 <b>СЕРВЕР ЗУПИНЕНО</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"👤 {user_label(update)}"
        )
    else:
        await msg.edit_text("❌ <b>Не вдалось!</b>", parse_mode="HTML")


async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Перевіряю...</b>", parse_mode="HTML")

    update_server_info()
    if server_status != "online":
        await msg.edit_text("🔴 <b>Сервер вимкнений!</b>", parse_mode="HTML")
        return

    if not current_players:
        await msg.edit_text("👥 <b>0 гравців</b>", parse_mode="HTML")
        return

    if len(current_players) > stats["peak_players"]:
        stats["peak_players"] = len(current_players)
        save_data()

    pl_str = "\n".join(f"  • {p}" for p in current_players)
    await msg.edit_text(f"👥 <b>{len(current_players)} онлайн</b>\n\n{pl_str}", parse_mode="HTML")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Перевіряю...</b>", parse_mode="HTML")

    update_server_info()
    await msg.edit_text(
        f"{icon(server_status)} <b>СТАТУС</b>\n\n"
        f"fictionmine (Bedrock)\n"
        f"{server_status.upper()}\n"
        f"Гравців: {len(current_players)}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}",
        parse_mode="HTML"
    )


async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Загружаю...</b>", parse_mode="HTML")

    update_server_info()

    last_start = (
        datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M")
        if stats["last_start"] else "ніколи"
    )
    last_stop = (
        datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")
        if stats["last_stop"] else "ніколи"
    )

    uptime = "—"
    if stats["uptime_from"] and server_status == "online":
        delta = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
        h, m = delta.seconds // 3600, (delta.seconds % 3600) // 60
        uptime = f"{h}ч {m}м"

    await msg.edit_text(
        "<b>📊 ІНФОРМАЦІЯ</b>\n\n"
        f"fictionmine (Bedrock)\n"
        f"{icon(server_status)} {server_status.upper()}\n"
        f"Гравців: {len(current_players)}\n\n"
        f"<b>📈 СТАТИСТИКА:</b>\n"
        f"  Запусків: {stats['starts']}\n"
        f"  Зупинень: {stats['stops']}\n"
        f"  Пік: {stats['peak_players']}\n"
        f"  Час роботи: {uptime}\n\n"
        f"<b>⏰ ОСТАННІ:</b>\n"
        f"  Запуск: {last_start}\n"
        f"  Зупин: {last_stop}",
        parse_mode="HTML"
    )


async def cmd_logthis(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    config["log_chat_id"] = chat_id
    save_data()
    await update.message.reply_text(
        f"✅ <b>Логи сюди!</b>\nID: <code>{chat_id}</code>",
        parse_mode="HTML"
    )
    await send_log(
        f"✅ <b>Логи змінено</b>\n👤 {user_label(update)}\nID: <code>{chat_id}</code>",
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
# FLASK
# ══════════════════════════════════════════════════════════════════

app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({"status": "ok", "bot": "aternos-bot"}), 200

@app.route("/ping")
def ping():
    return "pong", 200

def run_flask():
    log.info(f"🌐 Flask на http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)


# ══════════════════════════════════════════════════════════════════
# MAIN
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
    telegram_app.add_handler(CommandHandler("logthischat", cmd_logthis))
    telegram_app.add_handler(CallbackQueryHandler(on_button))

    log.info("✅ Telegram бот готов!")

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    await asyncio.Event().wait()


if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Зупинено")
    except Exception as e:
        log.error(f"❌ Ошибка: {e}", exc_info=True)
        sys.exit(1)
