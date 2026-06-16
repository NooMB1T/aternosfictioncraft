import asyncio
import logging
import json
import os
from datetime import datetime
from threading import Thread
from playwright.async_api import async_playwright

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
stats = {"starts": 0, "stops": 0, "last_start": None, "last_stop": None, "uptime_from": None, "peak_players": 0}

telegram_app = None
page = None
aternos_connected = False
server_online = False
current_players = []

def load_stats():
    global stats
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE) as f:
                stats = json.load(f)
                log.info(f"✅ Статистика: {stats['starts']} запусків")
        except Exception as e:
            log.error(f"Помилка stats: {e}")

def save_stats():
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Помилка збереження: {e}")

# ══════════════════════════════════════════════════════════════════
# PLAYWRIGHT ATERNOS
# ══════════════════════════════════════════════════════════════════

async def init_browser():
    """Ініціалізація браузера та логін"""
    global page, aternos_connected, server_online, current_players
    try:
        log.info("🚀 Запускаю браузер...")
        playwright = await async_playwright().start()
        
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        log.info("✅ Браузер запущений")
        
        # Логіничимось
        log.info("🔑 Логінимось в Aternos...")
        await page.goto("https://aternos.org/account/login/", timeout=30000)
        await page.wait_for_timeout(2000)
        
        await page.fill('input[name="user"]', ATERNOS_USER)
        await page.fill('input[name="password"]', ATERNOS_PASS)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(5000)
        
        if "account" in page.url or "panel" in page.url:
            log.info("✅ Логін успішний!")
            aternos_connected = True
            await check_server_status_browser()
            return True
        else:
            log.error("❌ Логін не вийшов")
            return False
            
    except Exception as e:
        log.error(f"❌ Помилка браузера: {e}")
        return False

async def check_server_status_browser():
    """Перевірити статус сервера та гравців"""
    global page, server_online, current_players
    try:
        await page.goto("https://aternos.org/server/", timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Статус
        try:
            status_elem = await page.query_selector('.status.online')
            server_online = status_elem is not None
        except:
            server_online = False
        
        # Гравці
        try:
            players_text = await page.text_content('.players-list')
            if players_text:
                current_players = [p.strip() for p in players_text.split('\n') if p.strip()]
            else:
                current_players = []
        except:
            current_players = []
        
        log.info(f"✅ Статус: {'🟢 ОНЛАЙН' if server_online else '🔴 ОФФЛАЙН'} | Гравців: {len(current_players)}")
        
    except Exception as e:
        log.error(f"❌ Помилка перевірки: {e}")

async def start_server_browser():
    """Запустити сервер"""
    global page, server_online
    try:
        await page.goto("https://aternos.org/server/", timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Шукаємо кнопку старту
        start_btn = await page.query_selector('button:has-text("Start"), [data-action="start"], .btn-start')
        if start_btn:
            await start_btn.click()
            await page.wait_for_timeout(3000)
            server_online = True
            log.info("✅ Сервер запущено!")
            return True
        
        log.warning("⚠️ Не знайшов кнопку старту")
        return False
    except Exception as e:
        log.error(f"❌ Помилка запуску: {e}")
        return False

async def stop_server_browser():
    """Вимкнути сервер"""
    global page, server_online
    try:
        await page.goto("https://aternos.org/server/", timeout=30000)
        await page.wait_for_timeout(2000)
        
        stop_btn = await page.query_selector('button:has-text("Stop"), [data-action="stop"], .btn-stop')
        if stop_btn:
            await stop_btn.click()
            await page.wait_for_timeout(3000)
            server_online = False
            log.info("✅ Сервер вимкнено!")
            return True
        
        log.warning("⚠️ Не знайшов кнопку стопу")
        return False
    except Exception as e:
        log.error(f"❌ Помилка вимкнення: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

async def send_log(text: str):
    if telegram_app:
        try:
            await telegram_app.bot.send_message(LOG_CHAT_ID, text, parse_mode="HTML")
        except Exception as e:
            log.error(f"send_log error: {e}")

def get_msg(update: Update):
    return update.callback_query.message if update.callback_query else update.message

async def typing(update: Update):
    try:
        await get_msg(update).chat.send_action(ChatAction.TYPING)
    except:
        pass

# ══════════════════════════════════════════════════════════════════
# КНОПКИ
# ══════════════════════════════════════════════════════════════════

MAIN_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 ВКЛЮЧИТИ", callback_data="on"),
     InlineKeyboardButton("🔴 ВИМКНУТИ", callback_data="off")],
    [InlineKeyboardButton("👥 ГРАВЦІ", callback_data="players")],
    [InlineKeyboardButton("📊 ІНФО", callback_data="menu"),
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
        f"Aternos: {'✅ Підключено' if aternos_connected else '❌ Не підключено'}\n"
        f"Сервер: {'🟢 ОНЛАЙН' if server_online else '🔴 ОФФЛАЙН'}\n"
        f"Гравців: {len(current_players)}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• /on — включити\n• /off — вимкнути\n"
        "• /players — гравці\n• /status — статус\n• /info — інфо\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await get_msg(update).reply_text(text, reply_markup=MAIN_KB, parse_mode="HTML")

async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global server_online, stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Запускаю сервер...</b>", parse_mode="HTML")
    
    if not aternos_connected:
        return await msg.edit_text("❌ Aternos не підключено!", parse_mode="HTML")
    
    if server_online:
        return await msg.edit_text("✅ Вже включений!", parse_mode="HTML")
    
    try:
        ok = await start_server_browser()
        if ok:
            stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat()
            stats["uptime_from"] = datetime.now().isoformat()
            save_stats()
            
            await msg.edit_text(
                "🟢 <b>ЗАПУЩЕНО!</b>\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"📊 Запусків: {stats['starts']}",
                parse_mode="HTML"
            )
            await send_log(f"🟢 <b>СЕРВЕР ЗАПУЩЕНО!</b>\n⏰ {datetime.now().strftime('%H:%M:%S')}\n📊 Запусків: {stats['starts']}")
        else:
            await msg.edit_text("❌ Не вдалось запустити", parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {str(e)[:100]}", parse_mode="HTML")

async def cmd_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global server_online, stats
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Вимикаю сервер...</b>", parse_mode="HTML")
    
    if not aternos_connected:
        return await msg.edit_text("❌ Aternos не підключено!", parse_mode="HTML")
    
    if not server_online:
        return await msg.edit_text("🔴 Вже вимкнений!", parse_mode="HTML")
    
    try:
        ok = await stop_server_browser()
        if ok:
            stats["stops"] += 1
            stats["last_stop"] = datetime.now().isoformat()
            stats["uptime_from"] = None
            save_stats()
            
            await msg.edit_text(
                "🔴 <b>ВИМКНЕНО!</b>\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}",
                parse_mode="HTML"
            )
            await send_log(f"🔴 <b>СЕРВЕР ВИМКНЕНО!</b>\n⏰ {datetime.now().strftime('%H:%M:%S')}")
        else:
            await msg.edit_text("❌ Не вдалось вимкнути", parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {str(e)[:100]}", parse_mode="HTML")

async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global current_players
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Перевіряю гравців...</b>", parse_mode="HTML")
    
    if not aternos_connected or not server_online:
        return await msg.edit_text("🔴 Сервер оффлайн", parse_mode="HTML")
    
    try:
        await check_server_status_browser()
        
        if not current_players:
            return await msg.edit_text("👥 <b>0 гравців</b>\nНікого нема 😿", parse_mode="HTML")
        
        if len(current_players) > stats["peak_players"]:
            stats["peak_players"] = len(current_players)
            save_stats()
        
        pl_str = "\n".join(f"  • <b>{p}</b>" for p in current_players)
        await msg.edit_text(f"👥 <b>ОНЛАЙН: {len(current_players)}</b>\n\n{pl_str}", parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {str(e)[:100]}", parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Перевіряю статус...</b>", parse_mode="HTML")
    
    if not aternos_connected:
        return await msg.edit_text("❌ Aternos не підключено!", parse_mode="HTML")
    
    try:
        await check_server_status_browser()
        await msg.edit_text(
            f"{'🟢' if server_online else '🔴'} <b>СТАТУС</b>\n\n"
            f"fictionmine (Bedrock)\n"
            f"{'🟢 ОНЛАЙН' if server_online else '🔴 ОФФЛАЙН'}\n"
            f"Гравців: {len(current_players)}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {str(e)[:100]}", parse_mode="HTML")

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await typing(update)
    msg = await get_msg(update).reply_text("<b>⏳ Завантажую дані...</b>", parse_mode="HTML")
    
    try:
        await check_server_status_browser()
        
        last_start = datetime.fromisoformat(stats["last_start"]).strftime('%d.%m %H:%M') if stats["last_start"] else "Ніколи"
        last_stop = datetime.fromisoformat(stats["last_stop"]).strftime('%d.%m %H:%M') if stats["last_stop"] else "Ніколи"
        
        uptime = "—"
        if stats["uptime_from"] and server_online:
            td = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
            h, m = td.seconds // 3600, (td.seconds % 3600) // 60
            uptime = f"{h}г {m}хв"
        
        await msg.edit_text(
            "<b>📊 ІНФОРМАЦІЯ</b>\n\n"
            f"🎮 fictionmine (Bedrock)\n"
            f"{'🟢 ОНЛАЙН' if server_online else '🔴 ОФФЛАЙН'}\n"
            f"Гравців: {len(current_players)}\n\n"
            f"📈 <b>СТАТИСТИКА:</b>\n"
            f"  Запусків: {stats['starts']}\n"
            f"  Виключень: {stats['stops']}\n"
            f"  Пік: {stats['peak_players']}\n"
            f"  Час роботи: {uptime}\n\n"
            f"⏰ <b>ОСТАННІ:</b>\n"
            f"  Запуск: {last_start}\n"
            f"  Виключення: {last_stop}",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Помилка: {str(e)[:100]}", parse_mode="HTML")

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    handlers = {"on": cmd_on, "off": cmd_off, "players": cmd_players, "status": cmd_status, "menu": cmd_info}
    fn = handlers.get(q.data)
    if fn:
        await fn(update, ctx)

# ══════════════════════════════════════════════════════════════════
# ФОНОВИЙ ЧЕК (10 хвилин)
# ══════════════════════════════════════════════════════════════════

async def background_check():
    await asyncio.sleep(30)
    while True:
        await asyncio.sleep(600)
        
        if not aternos_connected or not server_online:
            continue
        
        try:
            await check_server_status_browser()
            
            uptime_str = ""
            if stats["uptime_from"]:
                td = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
                h, m = td.seconds // 3600, (td.seconds % 3600) // 60
                uptime_str = f"⏱ Час роботи: {h}г {m}хв\n"
            
            pl_str = "\n".join(f"  • {p}" for p in current_players) if current_players else "  (нікого)"
            
            await send_log(
                f"🟢 <b>СЕРВЕР ОНЛАЙН</b> — авто-звіт\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"{uptime_str}"
                f"👥 Гравці ({len(current_players)}):\n{pl_str}"
            )
        except Exception as e:
            log.error(f"background_check: {e}")

# ══════════════════════════════════════════════════════════════════
# FLASK
# ══════════════════════════════════════════════════════════════════

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "✅ Bot running!", 200

@flask_app.route("/ping")
def ping():
    return "pong", 200

@flask_app.route("/health")
def health():
    return {
        "status": "ok",
        "aternos": "✅" if aternos_connected else "❌",
        "server": "🟢" if server_online else "🔴",
        "players": len(current_players),
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
    
    log.info("═════════════════════════════════════════")
    log.info("🎮 ATERNOS BOT v4.0 — PLAYWRIGHT")
    log.info("═════════════════════════════════════════")
    
    load_stats()
    
    ok = await init_browser()
    if not ok:
        log.error("❌ Не вдалось ініціалізувати браузер!")
    
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("on", cmd_on))
    telegram_app.add_handler(CommandHandler("off", cmd_off))
    telegram_app.add_handler(CommandHandler("players", cmd_players))
    telegram_app.add_handler(CommandHandler("status", cmd_status))
    telegram_app.add_handler(CommandHandler("info", cmd_info))
    telegram_app.add_handler(CommandHandler("menu", cmd_info))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    
    log.info("✅ Телеграм бот готовий!")
    log.info("═════════════════════════════════════════")
    
    asyncio.create_task(background_check())
    
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    log.info("✅ Flask запущений")
    
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log.info("⛔ Зупинено")
    except Exception as e:
        log.error(f"❌ Критична помилка: {e}")
