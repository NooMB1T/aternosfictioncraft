#!/usr/bin/env python3
import asyncio
import logging
import json
import os
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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8932716211:AAEC1-wnXkYWP2n4d2RtdaynBKkEq0H0JNs")
ATERNOS_USER = os.getenv("ATERNOS_USER", "GodB1T")
ATERNOS_PASS = os.getenv("ATERNOS_PASS", "AntonGod")
SERVER_ID = os.getenv("SERVER_ID", "ZMbbJv4TMQFIbi78")
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "-1002221201789"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНІ ЗМІННІ
# ══════════════════════════════════════════════════════════════════

STATS_FILE = "stats.json"
CONFIG_FILE = "config.json"

stats = {"starts": 0, "stops": 0, "last_start": None, "last_stop": None, "uptime_from": None, "peak_players": 0}
config = {"log_chat_id": LOG_CHAT_ID}

telegram_app = None
sess = requests.Session()
aternos_connected = False
server_status = "offline"
current_players = []

def load_files():
    global stats, config
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE) as f: 
                stats = json.load(f)
        except: 
            pass
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f: 
                config = json.load(f)
        except: 
            pass

def save_files():
    try:
        with open(STATS_FILE, "w") as f: 
            json.dump(stats, f, ensure_ascii=False, indent=2)
        with open(CONFIG_FILE, "w") as f: 
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Ошибка сохранения: {e}")

# ══════════════════════════════════════════════════════════════════
# ATERNOS
# ══════════════════════════════════════════════════════════════════

def login_aternos():
    """Логін в Aternos"""
    global aternos_connected, server_status, current_players
    try:
        log.info("🔑 Логинимся в Aternos...")
        
        resp = sess.post(
            "https://aternos.org/panel/ajax/account/login.php",
            data={"user": ATERNOS_USER, "password": ATERNOS_PASS},
            timeout=15
        )
        
        if resp.status_code != 200:
            log.error(f"❌ Логин ошибка: {resp.status_code}")
            return False
        
        aternos_connected = True
        log.info("✅ Логин успешен!")
        
        update_info()
        return True
    except Exception as e:
        log.error(f"❌ Ошибка логина: {e}")
        return False

def update_info():
    """Обновить инфо о сервере"""
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
        log.warning(f"⚠️ Ошибка обновления: {e}")
        return False

def start_server():
    """Запустить сервер"""
    global server_status
    try:
        url = f"https://aternos.org/api/server/{SERVER_ID}/start"
        resp = sess.post(url, timeout=30)
        
        if resp.status_code in [200, 201]:
            server_status = "online"
            log.info("✅ Сервер запущен!")
            return True
        
        return False
    except Exception as e:
        log.error(f"❌ Ошибка запуска: {e}")
        return False

def stop_server():
    """Остановить сервер"""
    global server_status
    try:
        url = f"https://aternos.org/api/server/{SERVER_ID}/stop"
        resp = sess.post(url, timeout=30)
        
        if resp.status_code in [200, 201]:
            server_status = "offline"
            log.info("✅ Сервер остановлен!")
            return True
        
        return False
    except Exception as e:
        log.error(f"❌ Ошибка остановки: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

async def send_log(text: str, chat_id=None):
    """Отправить лог"""
    if not telegram_app:
        return
    
    cid = chat_id or config.get("log_chat_id", LOG_CHAT_ID)
    try:
        await telegram_app.bot.send_message(cid, text, parse_mode="HTML")
    except Exception as e:
        log.error(f"send_log: {e}")

def get_msg(update: Update):
    return update.callback_query.message if update.callback_query else update.message

async def typing(update: Update):
    try:
        await get_msg(update).chat.send_action(ChatAction.TYPING)
    except:
        pass

def emoji(s):
    return {"online": "🟢", "offline": "🔴", "loading": "🟡"}.get(s, "⚫")

# ══════════════════════════════════════════════════════════════════
# КНОПКИ
# ══════════════════════════════════════════════════════════════════

KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 ЗАПУСТИТЬ", callback_data="on"),
     InlineKeyboardButton("🔴 ОСТАНОВИТЬ", callback_data="off")],
    [InlineKeyboardButton("👥 ИГРОКИ", callback_data="players")],
    [InlineKeyboardButton("📊 ИНФО", callback_data="info"),
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
    return "✅ OK", 200

@app.route("/ping")
def ping():
    return "pong", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

async def main():
    global telegram_app
    
    log.info("🎮 ATERNOS BOT v5.1 - ЗАПУЩЕН")
    
    load_files()
    
    ok = login_aternos()
    if not ok:
        log.error("❌ Не удалось логиниться!")
    
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("on", cmd_on))
    telegram_app.add_handler(CommandHandler("off", cmd_off))
    telegram_app.add_handler(CommandHandler("players", cmd_players))
    telegram_app.add_handler(CommandHandler("status", cmd_status))
    telegram_app.add_handler(CommandHandler("info", cmd_info))
    telegram_app.add_handler(CommandHandler("logthischat", cmd_logthis))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    
    log.info("✅ Бот готов!")
    
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    log.info("✅ Flask запущен")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Остановлен")
    except Exception as e:
        log.error(f"❌ Ошибка: {e}")
