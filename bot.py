import asyncio
import logging
import json
import os
from datetime import datetime
from threading import Thread
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) or None

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
session = None
aternos_cookies = None
aternos_connected = False
server_status = "offline"
current_players = []

def load_files():
    global stats, config
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE) as f: stats = json.load(f)
        except: pass
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f: config = json.load(f)
        except: pass

def save_files():
    try:
        with open(STATS_FILE, "w") as f: json.dump(stats, f, ensure_ascii=False, indent=2)
        with open(CONFIG_FILE, "w") as f: json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Помилка збереження: {e}")

# ══════════════════════════════════════════════════════════════════
# REQUESTS СЕСІЯ
# ══════════════════════════════════════════════════════════════════

def get_session():
    global session
    if session is None:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    return session

# ══════════════════════════════════════════════════════════════════
# ATERNOS API
# ══════════════════════════════════════════════════════════════════

def aternos_login():
    """Логіни в Aternos і отримання cookies"""
    global aternos_cookies, aternos_connected, server_status, current_players
    try:
        log.info("🔑 Логінимось в Aternos...")
        s = get_session()
        
        # Логін
        resp = s.post("https://aternos.org/panel/ajax/account/login.php", 
                     data={"user": ATERNOS_USER, "password": ATERNOS_PASS}, 
                     timeout=15)
        
        if resp.status_code != 200:
            log.error(f"❌ Помилка логіну: {resp.status_code}")
            return False
        
        aternos_cookies = s.cookies
        aternos_connected = True
        log.info("✅ Логін успішний!")
        
        # Відразу перевіряємо статус
        update_server_info()
        return True
    except Exception as e:
        log.error(f"❌ Помилка логіну: {e}")
        return False

def update_server_info():
    """Оновити інформацію про сервер"""
    global server_status, current_players, aternos_cookies
    try:
        if not aternos_cookies:
            return False
        
        s = get_session()
        s.cookies.update(aternos_cookies)
        
        # Статус
        url = f"https://aternos.org/api/server/{SERVER_ID}"
        resp = s.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            server_status = data.get("status", "offline")
            
            # Гравці
            try:
                players = data.get("players", [])
                current_players = players if isinstance(players, list) else []
            except:
                current_players = []
        
        return True
    except Exception as e:
        log.warning(f"⚠️ Помилка оновлення: {e}")
        return False

def start_server_api():
    """Запустити сервер"""
    global server_status, aternos_cookies
    try:
        s = get_session()
        s.cookies.update(aternos_cookies)
        
        url = f"https://aternos.org/api/server/{SERVER_ID}/start"
        resp = s.post(url, timeout=30)
        
        if resp.status_code in [200, 201]:
            log.info("✅ Сервер запущено!")
            server_status = "online"
            return True
        
        log.warning(f"⚠️ Статус: {resp.status_code}")
        return False
    except Exception as e:
        log.error(f"❌ Помилка запуску: {e}")
        return False

def stop_server_api():
    """Вимкнути сервер"""
    global server_status, aternos_cookies
    try:
        s = get_session()
        s.cookies.update(aternos_cookies)
        
        url = f"https://aternos.org/api/server/{SERVER_ID}/stop"
        resp = s.post(url, timeout=30)
        
        if resp.status_code in [200, 201]:
            log.info("✅ Сервер вимкнено!")
            server_status = "offline"
            return True
        
        log.warning(f"⚠️ Статус: {resp.status_code}")
        return False
    except Exception as e:
        log.error(f"❌ Помилка вимкнення: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

async def send_log(text: str, chat_id=None):
    """Відправити лог в чат"""
    if not telegram_app:
        return
    
    cid = chat_id or config.get("log_chat_id", LOG_CHAT_ID)
    try:
        await telegram_app.bot.send_message(cid, text, parse_mode="HTML")
    except Exception as e:
        log.error(f"send_log error: {e}")

def get_msg(update: Update):
    return update.callback_query.message if update.callback_query else update.message

async def typing(update: Update):
    try:
        await get_msg(update).chat.send_action(ChatAction.TYPING)
    except:
        pass

def status_emoji(s):
    return {"online": "🟢", "offline": "🔴", "loading": "🟡", "starting": "🟡"}.get(s, "⚫")

# ══════════════════════════════════════════════════════════════════
# КНОПКИ
# ══════════════════════════════════════════════════════════════════

MAIN_KB = InlineKeyboardMarkup([
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
        f"<b>Статус Aternos:</b> {'✅ Подключено' if aternos_connected else '❌ Не подключено'}\n"
        f"<b>Сервер:</b> {status_emoji(server_status)} {server_status.upper()}\n"
        f"<b>Игроков:</b> {len(current_players)}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Команды:</b>\n"
        "• /on — Запустить сервер\n"
        "• /off — Остановить сервер\n"
        "• /players — Список игроков\n"
        "• /status — Статус сервера\n"
        "• /info — Информация\n"
        "• /logthischat — Логи в этот чат\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    
    await get_msg(update).reply_text(text, reply_markup=MAIN_KB, parse_mode="HTML")

async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Запустить сервер"""
    global server_status, stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Запускаю сервер...</b>", parse_mode="HTML")
    
    if not aternos_connected:
        await send_log("❌ <b>ОШИБКА:</b> Попытка запустить сервер, но Aternos не подключен!")
        return await msg.edit_text("❌ <b>Ошибка:</b> Aternos не подключен!", parse_mode="HTML")
    
    if server_status == "online":
        await send_log("⚠️ <b>ПРЕДУПРЕЖДЕНИЕ:</b> Попытка запустить уже включенный сервер")
        return await msg.edit_text("✅ <b>Сервер уже включен!</b>", parse_mode="HTML")
    
    try:
        ok = await asyncio.to_thread(start_server_api)
        if ok:
            stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat()
            stats["uptime_from"] = datetime.now().isoformat()
            save_files()
            
            await msg.edit_text(
                "🟢 <b>СЕРВЕР ЗАПУЩЕН!</b>\n\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
                f"🎮 Сервер: fictionmine\n"
                f"📊 Всего запусков: {stats['starts']}",
                parse_mode="HTML"
            )
            
            await send_log(
                f"🟢 <b>СЕРВЕР ЗАПУЩЕН!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
                f"👤 Юзер: @{update.effective_user.username or update.effective_user.first_name}\n"
                f"📊 Всего запусков: {stats['starts']}"
            )
        else:
            await msg.edit_text("❌ <b>Не удалось запустить!</b> Попробуй позже.", parse_mode="HTML")
            await send_log(f"❌ <b>ОШИБКА:</b> Не удалось запустить сервер\n👤 Юзер: @{update.effective_user.username}")
    except Exception as e:
        await msg.edit_text(f"❌ <b>Ошибка:</b>\n<code>{str(e)[:100]}</code>", parse_mode="HTML")
        await send_log(f"❌ <b>КРИТИЧЕСКАЯ ОШИБКА:</b> {e}")

async def cmd_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Остановить сервер"""
    global server_status, stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Остановляю сервер...</b>", parse_mode="HTML")
    
    if not aternos_connected:
        await send_log("❌ <b>ОШИБКА:</b> Попытка остановить сервер, но Aternos не подключен!")
        return await msg.edit_text("❌ <b>Ошибка:</b> Aternos не подключен!", parse_mode="HTML")
    
    if server_status != "online":
        await send_log(f"⚠️ <b>ПРЕДУПРЕЖДЕНИЕ:</b> Попытка остановить оффлайн сервер (статус: {server_status})")
        return await msg.edit_text("🔴 <b>Сервер уже выключен!</b>", parse_mode="HTML")
    
    try:
        ok = await asyncio.to_thread(stop_server_api)
        if ok:
            stats["stops"] += 1
            stats["last_stop"] = datetime.now().isoformat()
            stats["uptime_from"] = None
            save_files()
            
            await msg.edit_text(
                "🔴 <b>СЕРВЕР ОСТАНОВЛЕН!</b>\n\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}",
                parse_mode="HTML"
            )
            
            await send_log(
                f"🔴 <b>СЕРВЕР ОСТАНОВЛЕН!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
                f"👤 Юзер: @{update.effective_user.username or update.effective_user.first_name}"
            )
        else:
            await msg.edit_text("❌ <b>Не удалось остановить!</b> Попробуй позже.", parse_mode="HTML")
            await send_log(f"❌ <b>ОШИБКА:</b> Не удалось остановить сервер\n👤 Юзер: @{update.effective_user.username}")
    except Exception as e:
        await msg.edit_text(f"❌ <b>Ошибка:</b>\n<code>{str(e)[:100]}</code>", parse_mode="HTML")
        await send_log(f"❌ <b>КРИТИЧЕСКАЯ ОШИБКА:</b> {e}")

async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Список игроков"""
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Проверяю игроков...</b>", parse_mode="HTML")
    
    if not aternos_connected or server_status != "online":
        return await msg.edit_text("🔴 <b>Сервер оффлайн</b>\nИгроки недоступны", parse_mode="HTML")
    
    try:
        await asyncio.to_thread(update_server_info)
        
        if not current_players:
            return await msg.edit_text("👥 <b>ОНЛАЙН: 0 игроков</b>\n\nНикого нет 😿", parse_mode="HTML")
        
        if len(current_players) > stats["peak_players"]:
            stats["peak_players"] = len(current_players)
            save_files()
        
        pl_str = "\n".join(f"  • <b>{p}</b>" for p in current_players)
        await msg.edit_text(
            f"👥 <b>ОНЛАЙН: {len(current_players)} игрок(ов)</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n{pl_str}",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"❌ <b>Ошибка:</b> {str(e)[:100]}", parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Статус сервера"""
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Проверяю статус...</b>", parse_mode="HTML")
    
    try:
        await asyncio.to_thread(update_server_info)
        
        await msg.edit_text(
            f"{status_emoji(server_status)} <b>СТАТУС СЕРВЕРА</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 <b>Имя:</b> fictionmine (Bedrock)\n"
            f"📍 <b>Статус:</b> {server_status.upper()}\n"
            f"👥 <b>Игроков:</b> {len(current_players)}\n"
            f"⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"❌ <b>Ошибка:</b> {str(e)[:100]}", parse_mode="HTML")

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Информация"""
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Загружаю информацию...</b>", parse_mode="HTML")
    
    try:
        await asyncio.to_thread(update_server_info)
        
        last_start = datetime.fromisoformat(stats["last_start"]).strftime('%d.%m %H:%M') if stats["last_start"] else "Никогда"
        last_stop = datetime.fromisoformat(stats["last_stop"]).strftime('%d.%m %H:%M') if stats["last_stop"] else "Никогда"
        
        uptime = "—"
        if stats["uptime_from"] and server_status == "online":
            td = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
            h, m = td.seconds // 3600, (td.seconds % 3600) // 60
            uptime = f"{h}ч {m}м"
        
        await msg.edit_text(
            "<b>📊 ИНФОРМАЦИЯ</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<b>🎮 СЕРВЕР:</b>\n"
            f"  Имя: fictionmine (Bedrock)\n"
            f"  Статус: {status_emoji(server_status)} {server_status.upper()}\n"
            f"  Игроков: {len(current_players)}\n\n"
            "<b>📈 СТАТИСТИКА:</b>\n"
            f"  Запусков: {stats['starts']}\n"
            f"  Остановок: {stats['stops']}\n"
            f"  Пик игроков: {stats['peak_players']}\n"
            f"  Время работы: {uptime}\n\n"
            "<b>⏰ ПОСЛЕДНИЕ СОБЫТИЯ:</b>\n"
            f"  Запуск: {last_start}\n"
            f"  Остановка: {last_stop}\n"
            f"  Логи отправляются: <code>{config.get('log_chat_id', 'не установлено')}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"❌ <b>Ошибка:</b> {str(e)[:100]}", parse_mode="HTML")

async def cmd_logthischat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Установить чат для логов"""
    await typing(update)
    
    chat_id = update.effective_chat.id
    config["log_chat_id"] = chat_id
    save_files()
    
    await update.message.reply_text(
        f"✅ <b>ОК!</b>\n\n"
        f"Логи теперь отправляются в этот чат:\n"
        f"<code>{chat_id}</code>",
        parse_mode="HTML"
    )
    
    await send_log(
        f"✅ <b>ЛОГИ УСТАНОВЛЕНЫ!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Новый чат для логов установлен\n"
        f"ID: <code>{chat_id}</code>\n"
        f"Юзер: @{update.effective_user.username}",
        chat_id=chat_id
    )

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    q = update.callback_query
    await q.answer()
    
    handlers = {
        "on": cmd_on,
        "off": cmd_off,
        "players": cmd_players,
        "status": cmd_status,
        "info": cmd_info,
    }
    
    fn = handlers.get(q.data)
    if fn:
        await fn(update, ctx)

# ══════════════════════════════════════════════════════════════════
# ФОНОВЫЙ ЧЕК
# ══════════════════════════════════════════════════════════════════

async def background_check():
    """Каждые 10 минут - автозвіт"""
    await asyncio.sleep(30)
    while True:
        await asyncio.sleep(600)
        
        if not aternos_connected or server_status != "online":
            continue
        
        try:
            await asyncio.to_thread(update_server_info)
            
            uptime_str = ""
            if stats["uptime_from"]:
                td = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
                h, m = td.seconds // 3600, (td.seconds % 3600) // 60
                uptime_str = f"⏱ Время работы: {h}ч {m}м\n"
            
            pl_str = "\n".join(f"  • {p}" for p in current_players) if current_players else "  (никого)"
            
            await send_log(
                f"🟢 <b>СЕРВЕР ОНЛАЙН</b> — авто-отчет\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"{uptime_str}"
                f"👥 Игроки ({len(current_players)}):\n{pl_str}"
            )
        except Exception as e:
            log.error(f"background_check: {e}")

# ══════════════════════════════════════════════════════════════════
# FLASK
# ══════════════════════════════════════════════════════════════════

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "✅ Bot is running!", 200

@flask_app.route("/ping")
def ping():
    return "pong", 200

@flask_app.route("/health")
def health():
    return {
        "status": "ok",
        "aternos": "✅" if aternos_connected else "❌",
        "server": server_status,
        "players": len(current_players),
        "starts": stats["starts"],
        "time": datetime.now().isoformat()
    }, 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

async def run_bot():
    global telegram_app
    
    log.info("═════════════════════════════════════════")
    log.info("🎮 ATERNOS BOT v5.0 — КРАСИВАЯ ВЕРСИЯ")
    log.info("═════════════════════════════════════════")
    
    load_files()
    
    # Логін
    log.info(f"🔑 Учетная запись: {ATERNOS_USER}")
    ok = await asyncio.to_thread(aternos_login)
    if not ok:
        log.error("❌ Ошибка подключения к Aternos!")
    
    # Telegram
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("on", cmd_on))
    telegram_app.add_handler(CommandHandler("off", cmd_off))
    telegram_app.add_handler(CommandHandler("players", cmd_players))
    telegram_app.add_handler(CommandHandler("status", cmd_status))
    telegram_app.add_handler(CommandHandler("info", cmd_info))
    telegram_app.add_handler(CommandHandler("logthischat", cmd_logthischat))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    
    log.info("✅ Telegram бот инициализирован!")
    log.info("═════════════════════════════════════════")
    
    asyncio.create_task(background_check())
    
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    log.info("✅ Flask запущен на порту 5000")
    
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log.info("⛔ Бот остановлен")
    except Exception as e:
        log.error(f"❌ Критическая ошибка: {e}", exc_info=True)
