import asyncio
import logging
import json
import os
import re
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

TELEGRAM_TOKEN = "8932716211:AAEC1-wnXkYWP2n4d2RtdaynBKkEq0H0JNs"
ATERNOS_USER = "GodB1T"
ATERNOS_PASS = "AntonGod"
SERVER_ID = "ZMbbJv4TMQFIbi78"
LOG_CHAT_ID = -1002221201789
SCOREBOARD_NAME = "Money"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНІ ЗМІННІ
# ══════════════════════════════════════════════════════════════════

STATS_FILE = "stats.json"
stats = {
    "starts": 0,
    "stops": 0,
    "last_start": None,
    "last_stop": None,
    "uptime_from": None,
    "peak_players": 0
}

telegram_app = None
session = None
server_online = False
current_players = []

def load_stats():
    global stats
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE) as f:
                stats = json.load(f)
                log.info(f"✅ Статистика завантажена: {stats['starts']} запусків")
        except Exception as e:
            log.error(f"Помилка завантаження stats: {e}")

def save_stats():
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f)
    except Exception as e:
        log.error(f"Помилка збереження stats: {e}")

# ══════════════════════════════════════════════════════════════════
# ATERNOS API (REQUESTS)
# ══════════════════════════════════════════════════════════════════

def get_session():
    """Отримати requests сесію з retry логікою"""
    global session
    if session is None:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    return session

def aternos_login():
    """Логін в Aternos через прямий API запит"""
    global session, server_online, current_players
    try:
        s = get_session()
        
        # Крок 1: Отримуємо токен сесії
        log.info("🔑 Логінимось в Aternos...")
        login_url = "https://aternos.org/panel/ajax/account/login.php"
        
        login_data = {
            "user": ATERNOS_USER,
            "password": ATERNOS_PASS
        }
        
        resp = s.post(login_url, data=login_data, timeout=10)
        if resp.status_code != 200:
            log.error(f"❌ Помилка логіну: {resp.status_code}")
            return False
        
        log.info("✅ Aternos логін успішний!")
        
        # Крок 2: Отримуємо статус сервера
        try:
            server_online = check_server_status()
            current_players = get_players_list()
            log.info(f"✅ Статус сервера: {'🟢 ОНЛАЙН' if server_online else '🔴 ОФФЛАЙН'}")
            log.info(f"✅ Гравців онлайн: {len(current_players)}")
        except Exception as e:
            log.warning(f"⚠️ Не вдалось отримати статус: {e}")
        
        return True
        
    except Exception as e:
        log.error(f"❌ Помилка логіну Aternos: {e}")
        return False

def check_server_status():
    """Перевірити статус сервера"""
    try:
        s = get_session()
        url = f"https://aternos.org/api/server/{SERVER_ID}"
        resp = s.get(url, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "offline")
            return status == "online"
        return False
    except Exception as e:
        log.warning(f"⚠️ Помилка перевірки статусу: {e}")
        return False

def get_players_list():
    """Отримати список гравців онлайн"""
    try:
        s = get_session()
        url = f"https://aternos.org/api/server/{SERVER_ID}/players"
        resp = s.get(url, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            players = data.get("players", [])
            return players
        return []
    except Exception as e:
        log.warning(f"⚠️ Помилка отримання гравців: {e}")
        return []

def start_server():
    """Включити сервер"""
    try:
        s = get_session()
        url = f"https://aternos.org/api/server/{SERVER_ID}/start"
        resp = s.post(url, timeout=30)
        
        if resp.status_code in [200, 201]:
            log.info("✅ Команда запуску відправлена")
            return True
        log.warning(f"⚠️ Статус відповіді: {resp.status_code}")
        return False
    except Exception as e:
        log.error(f"❌ Помилка запуску: {e}")
        return False

def stop_server():
    """Вимкнути сервер"""
    try:
        s = get_session()
        url = f"https://aternos.org/api/server/{SERVER_ID}/stop"
        resp = s.post(url, timeout=30)
        
        if resp.status_code in [200, 201]:
            log.info("✅ Команда вимкнення відправлена")
            return True
        log.warning(f"⚠️ Статус відповіді: {resp.status_code}")
        return False
    except Exception as e:
        log.error(f"❌ Помилка вимкнення: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

async def send_log(text: str):
    """Відправити в лог-чат"""
    if telegram_app:
        try:
            await telegram_app.bot.send_message(LOG_CHAT_ID, text, parse_mode="HTML")
        except Exception as e:
            log.error(f"send_log error: {e}")

def get_msg(update: Update):
    """Отримати повідомлення (команда або кнопка)"""
    if update.callback_query:
        return update.callback_query.message
    return update.message

async def typing(update: Update):
    """Показати "печатает""""
    try:
        await get_msg(update).chat.send_action(ChatAction.TYPING)
    except:
        pass

def status_emoji(online):
    return "🟢" if online else "🔴"

# ══════════════════════════════════════════════════════════════════
# КНОПКИ
# ══════════════════════════════════════════════════════════════════

MAIN_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 ВКЛЮЧИТИ", callback_data="on"),
     InlineKeyboardButton("🔴 ВИМКНУТИ", callback_data="off")],
    [InlineKeyboardButton("👥 ГРАВЦІ", callback_data="players")],
    [InlineKeyboardButton("📊 ІНФО", callback_data="menu"),
     InlineKeyboardButton("⚙️ СТАТУС", callback_data="status")],
    [InlineKeyboardButton("💰 СКОРБОРД", callback_data="scoreboard")],
])

# ══════════════════════════════════════════════════════════════════
# КОМАНДИ
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await typing(update)
    text = (
        "<b>🎮 ATERNOS BOT — fictionmine</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• /on — включити сервер\n"
        "• /off — вимкнути сервер\n"
        "• /players — гравці онлайн\n"
        "• /status — статус\n"
        "• /info — інфо + статистика\n"
        "• /scoreboard — скорборд гравців\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Або натисни кнопку 👇</i>"
    )
    await get_msg(update).reply_text(text, reply_markup=MAIN_KB, parse_mode="HTML")

async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Включити сервер"""
    global server_online, stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Запускаю сервер...</b>", parse_mode="HTML")
    
    try:
        # Перевіряємо перед запуском
        server_online = check_server_status()
        
        if server_online:
            return await msg.edit_text(
                "✅ <b>Сервер вже включений!</b>",
                parse_mode="HTML"
            )
        
        # Запускаємо
        ok = await asyncio.to_thread(start_server)
        
        if not ok:
            return await msg.edit_text(
                "❌ <b>Не вдалось запустити сервер</b>\n"
                "<i>Спробуй через 30 секунд</i>",
                parse_mode="HTML"
            )
        
        stats["starts"] += 1
        stats["last_start"] = datetime.now().isoformat()
        stats["uptime_from"] = datetime.now().isoformat()
        save_stats()
        server_online = True
        
        await msg.edit_text(
            "🟢 <b>СЕРВЕР ЗАПУЩЕНО!</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ <b>Час:</b> {datetime.now().strftime('%H:%M:%S')}\n"
            f"🎮 <b>Сервер:</b> fictionmine\n"
            f"📊 <b>Запусків:</b> {stats['starts']}\n"
            "<i>Завантаження 5-10 хв...</i>",
            parse_mode="HTML"
        )
        
        await send_log(
            f"🟢 <b>СЕРВЕР ЗАПУЩЕНО!</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"📊 Всього запусків: {stats['starts']}"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ <b>Помилка:</b>\n<code>{str(e)[:200]}</code>", parse_mode="HTML")

async def cmd_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Вимкнути сервер"""
    global server_online, stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Вимикаю сервер...</b>", parse_mode="HTML")
    
    try:
        server_online = check_server_status()
        
        if not server_online:
            return await msg.edit_text(
                "🔴 <b>Сервер вже вимкнений!</b>",
                parse_mode="HTML"
            )
        
        ok = await asyncio.to_thread(stop_server)
        
        if not ok:
            return await msg.edit_text(
                "❌ <b>Не вдалось вимкнути сервер</b>",
                parse_mode="HTML"
            )
        
        stats["stops"] += 1
        stats["last_stop"] = datetime.now().isoformat()
        stats["uptime_from"] = None
        save_stats()
        server_online = False
        
        await msg.edit_text(
            "🔴 <b>СЕРВЕР ВИМКНЕНО!</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ <b>Час:</b> {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="HTML"
        )
        
        await send_log(f"🔴 <b>СЕРВЕР ВИМКНЕНО!</b>\n⏰ {datetime.now().strftime('%H:%M:%S')}")
        
    except Exception as e:
        await msg.edit_text(f"❌ <b>Помилка:</b>\n<code>{str(e)[:200]}</code>", parse_mode="HTML")

async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Список гравців"""
    global current_players, server_online
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Перевіряю гравців...</b>", parse_mode="HTML")
    
    try:
        server_online = check_server_status()
        
        if not server_online:
            return await msg.edit_text(
                "🔴 <b>Сервер оффлайн</b>\n"
                "<i>Включи командою /on</i>",
                parse_mode="HTML"
            )
        
        current_players = await asyncio.to_thread(get_players_list)
        
        if not current_players:
            return await msg.edit_text(
                "👥 <b>ОНЛАЙН: 0 гравців</b>\n\n"
                "Сервер включений, але нікого немає 😿",
                parse_mode="HTML"
            )
        
        if len(current_players) > stats["peak_players"]:
            stats["peak_players"] = len(current_players)
            save_stats()
        
        pl_str = "\n".join(f"  • <b>{p}</b>" for p in current_players)
        await msg.edit_text(
            f"👥 <b>ОНЛАЙН: {len(current_players)} гравець(ів)</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n{pl_str}\n━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ <b>Помилка:</b>\n<code>{str(e)[:200]}</code>", parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Статус сервера"""
    global server_online
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Перевіряю статус...</b>", parse_mode="HTML")
    
    try:
        server_online = check_server_status()
        
        await msg.edit_text(
            f"{status_emoji(server_online)} <b>СТАТУС СЕРВЕРА</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 <b>Ім'я:</b> fictionmine (Bedrock)\n"
            f"📍 <b>Статус:</b> {'🟢 ОНЛАЙН' if server_online else '🔴 ОФФЛАЙН'}\n"
            f"⏰ <b>Перевірено:</b> {datetime.now().strftime('%H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"❌ <b>Помилка:</b>\n<code>{str(e)[:200]}</code>", parse_mode="HTML")

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Інформаційне меню"""
    global server_online, current_players, stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Завантажую дані...</b>", parse_mode="HTML")
    
    try:
        server_online = check_server_status()
        if server_online:
            current_players = await asyncio.to_thread(get_players_list)
        
        last_start = (
            datetime.fromisoformat(stats["last_start"]).strftime('%d.%m %H:%M')
            if stats["last_start"] else "Ніколи"
        )
        last_stop = (
            datetime.fromisoformat(stats["last_stop"]).strftime('%d.%m %H:%M')
            if stats["last_stop"] else "Ніколи"
        )
        
        uptime = "Невідомо"
        if stats["uptime_from"] and server_online:
            td = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
            h, m = td.seconds // 3600, (td.seconds % 3600) // 60
            uptime = f"{h}г {m}хв"
        
        await msg.edit_text(
            "<b>📊 ІНФОРМАЦІЙНЕ МЕНЮ</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<b>🎮 СЕРВЕР:</b>\n"
            f"  Ім'я: fictionmine (Bedrock)\n"
            f"  Статус: {status_emoji(server_online)} {'🟢 ОНЛАЙН' if server_online else '🔴 ОФФЛАЙН'}\n"
            f"  Гравців: {len(current_players)}\n\n"
            "<b>📈 СТАТИСТИКА:</b>\n"
            f"  Запусків: {stats['starts']}\n"
            f"  Виключень: {stats['stops']}\n"
            f"  Пік гравців: {stats['peak_players']}\n"
            f"  Час роботи: {uptime}\n\n"
            "<b>⏰ ОСТАННІ ПОДІЇ:</b>\n"
            f"  Запуск: {last_start}\n"
            f"  Виключення: {last_stop}\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"❌ <b>Помилка:</b>\n<code>{str(e)[:200]}</code>", parse_mode="HTML")

async def cmd_scoreboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Скорборд гравців"""
    global server_online
    await typing(update)
    msg = await get_msg(update).reply_text(
        f"⏳ <b>Завантажую скорборд...</b>",
        parse_mode="HTML"
    )
    
    try:
        server_online = check_server_status()
        
        if not server_online:
            return await msg.edit_text(
                f"🔴 <b>Сервер оффлайн</b>\n"
                "<i>Скорборд доступний тільки коли сервер включений</i>",
                parse_mode="HTML"
            )
        
        # На жаль Aternos API не дозволяє прочитати скорборд напряму
        # Показуємо інструкцію
        await msg.edit_text(
            f"💰 <b>СКОРБОРД: {SCOREBOARD_NAME}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Aternos API не дозволяє прочитати скорборд автоматично.\n\n"
            f"<b>Як подивитись:</b>\n"
            f"1. Увійди на сервер\n"
            f"2. Відкрий сторону табуляції (Tab)\n"
            f"3. Побачиш гравців і їх баланс\n\n"
            f"Або введи в чаті:\n"
            f"<code>/scoreboard players list</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ <b>Помилка:</b>\n<code>{str(e)[:200]}</code>", parse_mode="HTML")

# ══════════════════════════════════════════════════════════════════
# ФОНОВИЙ ЧЕК (кожні 10 хвилин)
# ══════════════════════════════════════════════════════════════════

async def background_check():
    """Кожні 10 хвилин відправляє звіт якщо сервер онлайн"""
    await asyncio.sleep(10)  # Чекаємо щоб бот запустився
    
    while True:
        await asyncio.sleep(600)  # 10 хвилин
        
        try:
            online = await asyncio.to_thread(check_server_status)
            if not online:
                continue
            
            players = await asyncio.to_thread(get_players_list)
            
            uptime_str = ""
            if stats["uptime_from"]:
                td = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
                h, m = td.seconds // 3600, (td.seconds % 3600) // 60
                uptime_str = f"⏱ <b>Час роботи:</b> {h}г {m}хв\n"
            
            pl_str = (
                "\n".join(f"  • {p}" for p in players)
                if players else "  (нікого немає)"
            )
            
            await send_log(
                f"🟢 <b>СЕРВЕР ОНЛАЙН</b> — авто-звіт\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"{uptime_str}"
                f"👥 <b>Гравці ({len(players)}):</b>\n{pl_str}"
            )
        except Exception as e:
            log.error(f"background_check error: {e}")

# ══════════════════════════════════════════════════════════════════
# CALLBACK КНОПКИ
# ══════════════════════════════════════════════════════════════════

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обробка кнопок"""
    q = update.callback_query
    await q.answer()
    
    handlers = {
        "on": cmd_on,
        "off": cmd_off,
        "players": cmd_players,
        "status": cmd_status,
        "menu": cmd_info,
        "scoreboard": cmd_scoreboard,
    }
    
    fn = handlers.get(q.data)
    if fn:
        await fn(update, ctx)

# ══════════════════════════════════════════════════════════════════
# FLASK (для Render)
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
        "server": "🟢 ОНЛАЙН" if server_online else "🔴 ОФФЛАЙН",
        "time": datetime.now().isoformat(),
        "starts": stats["starts"]
    }, 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

async def run_bot():
    global telegram_app
    
    log.info("═══════════════════════════════════════════════════════")
    log.info("🎮 ATERNOS BOT v3.0 — RENDER")
    log.info("═══════════════════════════════════════════════════════")
    
    load_stats()
    
    # Логін в Aternos
    log.info("🔑 Логінюсь в Aternos...")
    ok = await asyncio.to_thread(aternos_login)
    
    if not ok:
        log.error("❌ Не вдалось залогіниться в Aternos!")
        log.error("Перевір username/password!")
    
    # Телеграм бот
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("on", cmd_on))
    telegram_app.add_handler(CommandHandler("off", cmd_off))
    telegram_app.add_handler(CommandHandler("players", cmd_players))
    telegram_app.add_handler(CommandHandler("status", cmd_status))
    telegram_app.add_handler(CommandHandler("info", cmd_info))
    telegram_app.add_handler(CommandHandler("menu", cmd_info))
    telegram_app.add_handler(CommandHandler("scoreboard", cmd_scoreboard))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    
    log.info("✅ Телеграм бот ініціалізований!")
    log.info("═══════════════════════════════════════════════════════")
    
    # Запускаємо фоновий чек
    asyncio.create_task(background_check())
    
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Flask в окремому потоці
    Thread(target=run_flask, daemon=True).start()
    log.info("✅ Flask запущений на порту 5000")
    
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log.info("⛔ Бот зупинено")
    except Exception as e:
        log.error(f"❌ Критична помилка: {e}", exc_info=True)
