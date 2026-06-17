#!/usr/bin/env python3
"""
ATERNOS BOT v5.2 - RENDER EDITION
Бот для управління Minecraft Aternos сервером через Telegram
"""

import asyncio
import logging
import json
import os
import sys
from datetime import datetime
from threading import Thread
import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
from flask import Flask

# ══════════════════════════════════════════════════════════════════
# КОНФІГ
# ══════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ATERNOS_USER = os.getenv("ATERNOS_USER")
ATERNOS_PASS = os.getenv("ATERNOS_PASS")
SERVER_ID = os.getenv("SERVER_ID")
LOG_CHAT_ID = os.getenv("LOG_CHAT_ID")
PORT = int(os.getenv("PORT", 5000))

if not all([TELEGRAM_TOKEN, ATERNOS_USER, ATERNOS_PASS, SERVER_ID, LOG_CHAT_ID]):
    print("❌ ПОМИЛКА: Не всі environment variables встановлені!")
    sys.exit(1)

LOG_CHAT_ID = int(LOG_CHAT_ID)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНІ ЗМІННІ
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
aternos_connected = False
server_status = "offline"
current_players = []

def load_files():
    """Завантажити файли статистики"""
    global stats, config
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, encoding="utf-8") as f:
                stats = json.load(f)
                log.info(f"✅ Статистика завантажена: {stats['starts']} запусків")
        except Exception as e:
            log.warning(f"⚠️ Помилка завантаження stats: {e}")

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                config = json.load(f)
                log.info(f"✅ Конфіг завантажен")
        except Exception as e:
            log.warning(f"⚠️ Помилка завантаження config: {e}")

def save_files():
    """Зберегти файли"""
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"❌ Помилка збереження: {e}")

# ══════════════════════════════════════════════════════════════════
# ATERNOS API
# ══════════════════════════════════════════════════════════════════

def login_aternos():
    """Логін в Aternos"""
    global aternos_connected, server_status, current_players
    try:
        log.info("🔑 Логінимось в Aternos...")

        resp = sess.post(
            "https://aternos.org/panel/ajax/account/login.php",
            data={"user": ATERNOS_USER, "password": ATERNOS_PASS},
            timeout=15
        )

        if resp.status_code != 200:
            log.error(f"❌ Логін ошибка: {resp.status_code}")
            return False

        aternos_connected = True
        log.info("✅ Логін успішний!")

        update_info()
        return True
    except Exception as e:
        log.error(f"❌ Ошибка логіну: {e}", exc_info=True)
        return False

def update_info():
    """Обновити інформацію про сервер"""
    global server_status, current_players
    try:
        url = f"https://aternos.org/api/server/{SERVER_ID}"
        resp = sess.get(url, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            server_status = data.get("status", "offline")
            current_players = data.get("players", [])
            if not isinstance(current_players, list):
                current_players = []

        return True
    except Exception as e:
        log.warning(f"⚠️ Ошибка обновлення: {e}")
        return False

def start_server():
    """Запустити сервер"""
    global server_status
    try:
        url = f"https://aternos.org/api/server/{SERVER_ID}/start"
        resp = sess.post(url, timeout=30)

        if resp.status_code in [200, 201]:
            server_status = "online"
            log.info("✅ Сервер запущено!")
            return True

        log.warning(f"⚠️ Статус запуску: {resp.status_code}")
        return False
    except Exception as e:
        log.error(f"❌ Ошибка запуску: {e}")
        return False

def stop_server():
    """Остановити сервер"""
    global server_status
    try:
        url = f"https://aternos.org/api/server/{SERVER_ID}/stop"
        resp = sess.post(url, timeout=30)

        if resp.status_code in [200, 201]:
            server_status = "offline"
            log.info("✅ Сервер остановлено!")
            return True

        log.warning(f"⚠️ Статус остановки: {resp.status_code}")
        return False
    except Exception as e:
        log.error(f"❌ Ошибка остановки: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

async def send_log(text: str, chat_id=None):
    """Відправити лог"""
    if not telegram_app:
        return

    cid = chat_id or config.get("log_chat_id", LOG_CHAT_ID)
    try:
        await telegram_app.bot.send_message(cid, text, parse_mode="HTML")
        log.info(f"📝 Лог відправлено в {cid}")
    except Exception as e:
        log.error(f"❌ send_log error: {e}")

def get_msg(update: Update):
    """Отримати повідомлення"""
    return update.callback_query.message if update.callback_query else update.message

async def typing(update: Update):
    """Показати печатает"""
    try:
        await get_msg(update).chat.send_action(ChatAction.TYPING)
    except:
        pass

def emoji(s):
    """Отримати емодзі статусу"""
    return {"online": "🟢", "offline": "🔴", "loading": "🟡"}.get(s, "⚫")

# ══════════════════════════════════════════════════════════════════
# КНОПКИ
# ══════════════════════════════════════════════════════════════════

KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 ЗАПУСТИТИ", callback_data="on"),
     InlineKeyboardButton("🔴 ОСТАНОВИТИ", callback_data="off")],
    [InlineKeyboardButton("👥 ГРАВЦІ", callback_data="players")],
    [InlineKeyboardButton("📊 ІНФО", callback_data="info"),
     InlineKeyboardButton("⚙️ СТАТУС", callback_data="status")],
])

# ══════════════════════════════════════════════════════════════════
# КОМАНДИ
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    await typing(update)

    text = (
        "<b>🎮 ATERNOS BOT — fictionmine</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Статус:</b> {'✅ Подключено' if aternos_connected else '❌ Нет'}\n"
        f"<b>Сервер:</b> {emoji(server_status)} {server_status.upper()}\n"
        f"<b>Игроков:</b> {len(current_players)}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• /on — Запустить\n"
        "• /off — Остановить\n"
        "• /players — Игроки\n"
        "• /status — Статус\n"
        "• /info — Инфо\n"
        "• /logthischat — Логи сюда\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    await get_msg(update).reply_text(text, reply_markup=KB, parse_mode="HTML")

async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Запустить"""
    global server_status, stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Запускаю...</b>", parse_mode="HTML")

    if not aternos_connected:
        await send_log("❌ ОШИБКА: Попытка запустить, но Aternos не подключен!")
        return await msg.edit_text("❌ Aternos не подключен!", parse_mode="HTML")

    if server_status == "online":
        return await msg.edit_text("✅ Уже включен!", parse_mode="HTML")

    ok = start_server()
    if ok:
        stats["starts"] += 1
        stats["last_start"] = datetime.now().isoformat()
        stats["uptime_from"] = datetime.now().isoformat()
        save_files()

        await msg.edit_text(
            "🟢 <b>ЗАПУЩЕН!</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"📊 Запусков: {stats['starts']}",
            parse_mode="HTML"
        )

        await send_log(
            f"🟢 <b>СЕРВЕР ЗАПУЩЕН!</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"👤 @{update.effective_user.username or update.effective_user.first_name}\n"
            f"📊 Всего: {stats['starts']}"
        )
    else:
        await msg.edit_text("❌ Не удалось запустить!", parse_mode="HTML")
        await send_log(f"❌ ОШИБКА запуска\n👤 @{update.effective_user.username}")

async def cmd_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Остановить"""
    global server_status, stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Останавливаю...</b>", parse_mode="HTML")

    if not aternos_connected:
        return await msg.edit_text("❌ Aternos не подключен!", parse_mode="HTML")

    if server_status != "online":
        return await msg.edit_text("🔴 Уже выключен!", parse_mode="HTML")

    ok = stop_server()
    if ok:
        stats["stops"] += 1
        stats["last_stop"] = datetime.now().isoformat()
        save_files()

        await msg.edit_text(
            "🔴 <b>ОСТАНОВЛЕН!</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="HTML"
        )

        await send_log(
            f"🔴 <b>СЕРВЕР ОСТАНОВЛЕН!</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"👤 @{update.effective_user.username}"
        )
    else:
        await msg.edit_text("❌ Не удалось остановить!", parse_mode="HTML")

async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Игроки"""
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Проверяю...</b>", parse_mode="HTML")

    if server_status != "online":
        return await msg.edit_text("🔴 Сервер оффлайн", parse_mode="HTML")

    update_info()

    if not current_players:
        return await msg.edit_text("👥 <b>0 игроков</b>\nНикого 😿", parse_mode="HTML")

    if len(current_players) > stats["peak_players"]:
        stats["peak_players"] = len(current_players)
        save_files()

    pl_str = "\n".join(f"  • {p}" for p in current_players)
    await msg.edit_text(f"👥 <b>ОНЛАЙН: {len(current_players)}</b>\n\n{pl_str}", parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Статус"""
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Проверяю...</b>", parse_mode="HTML")

    update_info()

    await msg.edit_text(
        f"{emoji(server_status)} <b>СТАТУС</b>\n\n"
        f"fictionmine (Bedrock)\n"
        f"{server_status.upper()}\n"
        f"Игроков: {len(current_players)}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}",
        parse_mode="HTML"
    )

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Инфо"""
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Загружаю...</b>", parse_mode="HTML")

    update_info()

    last_start = datetime.fromisoformat(stats["last_start"]).strftime('%d.%m %H:%M') if stats["last_start"] else "Никогда"
    last_stop = datetime.fromisoformat(stats["last_stop"]).strftime('%d.%m %H:%M') if stats["last_stop"] else "Никогда"

    uptime = "—"
    if stats["uptime_from"] and server_status == "online":
        td = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
        h, m = td.seconds // 3600, (td.seconds % 3600) // 60
        uptime = f"{h}ч {m}м"

    await msg.edit_text(
        "<b>📊 ИНФОРМАЦИЯ</b>\n\n"
        f"fictionmine (Bedrock)\n"
        f"{emoji(server_status)} {server_status.upper()}\n"
        f"Игроков: {len(current_players)}\n\n"
        f"<b>📈 СТАТИСТИКА:</b>\n"
        f"  Запусков: {stats['starts']}\n"
        f"  Остановок: {stats['stops']}\n"
        f"  Пик: {stats['peak_players']}\n"
        f"  Время работы: {uptime}\n\n"
        f"<b>⏰ ПОСЛЕДНИЕ:</b>\n"
        f"  Запуск: {last_start}\n"
        f"  Остановка: {last_stop}",
        parse_mode="HTML"
    )

async def cmd_logthis(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Логи в этот чат"""
    await typing(update)

    cid = update.effective_chat.id
    config["log_chat_id"] = cid
    save_files()

    await update.message.reply_text(
        f"✅ <b>ЛОГИ УСТАНОВЛЕНЫ!</b>\n"
        f"ID: <code>{cid}</code>",
        parse_mode="HTML"
    )

    await send_log(
        f"✅ ЛОГИ УСТАНОВЛЕНЫ\n"
        f"ID: <code>{cid}</code>\n"
        f"👤 @{update.effective_user.username}",
        chat_id=cid
    )

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Кнопки"""
    q = update.callback_query
    await q.answer()

    handlers = {"on": cmd_on, "off": cmd_off, "players": cmd_players, "status": cmd_status, "info": cmd_info}

    fn = handlers.get(q.data)
    if fn:
        await fn(update, ctx)

# ══════════════════════════════════════════════════════════════════
# FLASK
# ══════════════════════════════════════════════════════════════════

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running!", 200

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/health")
def health():
    return {
        "status": "ok",
        "aternos": "✅" if aternos_connected else "❌",
        "server": server_status,
        "players": len(current_players),
        "starts": stats["starts"]
    }, 200

def run_flask():
    """Запустить Flask"""
    try:
        log.info(f"🌐 Flask запускається на порту {PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        log.error(f"❌ Flask error: {e}")

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

async def main():
    """Основна функція"""
    global telegram_app

    log.info("═" * 60)
    log.info("🎮 ATERNOS BOT v5.2 - RENDER EDITION")
    log.info("═" * 60)

    load_files()

    log.info(f"🔑 Учетная запись: {ATERNOS_USER}")
    log.info(f"🎯 ID сервера: {SERVER_ID}")
    log.info(f"💬 Лог чат ID: {LOG_CHAT_ID}")

    ok = login_aternos()
    if not ok:
        log.error("❌ Не удалось подключиться к Aternos!")

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("on", cmd_on))
    telegram_app.add_handler(CommandHandler("off", cmd_off))
    telegram_app.add_handler(CommandHandler("players", cmd_players))
    telegram_app.add_handler(CommandHandler("status", cmd_status))
    telegram_app.add_handler(CommandHandler("info", cmd_info))
    telegram_app.add_handler(CommandHandler("logthischat", cmd_logthis))
    telegram_app.add_handler(CallbackQueryHandler(on_button))

    log.info("✅ Telegram бот инициализирован!")
    log.info("═" * 60)

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    try:
        log.info("🚀 Запускаю Telegram бота...")
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Бот остановлен")
    except Exception as e:
        log.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
