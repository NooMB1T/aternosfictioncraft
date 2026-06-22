#!/usr/bin/env python3
"""
ATERNOS TELEGRAM BOT v16.0
Playwright для логіну + aiohttp для управління (з правильним jar)
"""

import os, sys, json, asyncio, logging, random
from datetime import datetime
from threading import Thread

from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters, ConversationHandler
)
from telegram.constants import ChatAction

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", stream=sys.stdout)
log = logging.getLogger("bot")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ATERNOS_USER   = os.getenv("ATERNOS_USER", "")
ATERNOS_PASS   = os.getenv("ATERNOS_PASS", "")
SERVER_ID      = os.getenv("SERVER_ID", "")
LOG_CHAT_ID    = int(os.getenv("LOG_CHAT_ID", "0"))
PORT           = int(os.getenv("PORT", "8000"))
ADMIN_CODE     = os.getenv("ADMIN_CODE", "2011")

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN не установлен!")
    sys.exit(1)

log.info("=" * 60)
log.info("🎮 ATERNOS BOT v16.0 — fictionmine")
log.info("=" * 60)

STATS_FILE  = "stats.json"
CONFIG_FILE = "config.json"
ADMINS_FILE = "admins.json"
USERS_FILE  = "users.json"
WARNS_FILE  = "warns.json"
NOTES_FILE  = "notes.json"

stats = {"starts":0,"stops":0,"restarts":0,"last_start":None,"last_stop":None,"uptime_from":None,"peak_players":0,"total_commands":0}
config = {"log_chat_id":LOG_CHAT_ID,"maintenance":False,"server_name":"fictionmine","server_ip":"fictionmine.aternos.me","server_port":"19132","motd":"Добро пожаловать на fictionmine! 🎮","allow_all_start":True,"world_seed":"","shop_link":""}
admins: set = set()
users:  dict = {}
warns:  dict = {}
notes:  list = []

telegram_app      = None
aternos_session   = None  # aiohttp.ClientSession
aternos_connected = False
server_status     = "offline"
current_players   = []

WAIT_CODE = 1

def load_all():
    global stats, config, admins, users, warns, notes
    for fname, obj in [(STATS_FILE, stats), (CONFIG_FILE, config)]:
        if os.path.exists(fname):
            try:
                with open(fname, encoding="utf-8") as f: obj.update(json.load(f))
            except: pass
    for fname, var, default in [(ADMINS_FILE,"admins",set()), (USERS_FILE,"users",{}), (WARNS_FILE,"warns",{}), (NOTES_FILE,"notes",[])]:
        if os.path.exists(fname):
            try:
                with open(fname, encoding="utf-8") as f:
                    val = json.load(f)
                    if fname == ADMINS_FILE: admins.update(val)
                    elif fname == USERS_FILE: users.update(val)
                    elif fname == WARNS_FILE: warns.update(val)
                    elif fname == NOTES_FILE: notes.extend(val)
            except: pass

def save_all():
    try:
        with open(STATS_FILE,  "w", encoding="utf-8") as f: json.dump(stats,  f, ensure_ascii=False, indent=2)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(config, f, ensure_ascii=False, indent=2)
        with open(ADMINS_FILE, "w", encoding="utf-8") as f: json.dump(list(admins), f)
        with open(USERS_FILE,  "w", encoding="utf-8") as f: json.dump(users,  f, ensure_ascii=False, indent=2)
        with open(WARNS_FILE,  "w", encoding="utf-8") as f: json.dump(warns,  f, ensure_ascii=False, indent=2)
        with open(NOTES_FILE,  "w", encoding="utf-8") as f: json.dump(notes,  f, ensure_ascii=False, indent=2)
    except Exception as e: log.error(f"❌ save: {e}")

def reg(update: Update):
    u = update.effective_user
    users[str(u.id)] = {"first_name":u.first_name or "","username":u.username or "","last_seen":datetime.now().isoformat()}
    stats["total_commands"] = stats.get("total_commands",0) + 1

# ══════════════════════════════════════════════════════════════════
# ATERNOS — Playwright логін + aiohttp для управління
# ══════════════════════════════════════════════════════════════════

async def aternos_login() -> bool:
    """Playwright логін з jar сесією для aiohttp"""
    global aternos_connected, aternos_session
    if not all([ATERNOS_USER, ATERNOS_PASS]):
        log.warning("⚠️ Aternos дані не вказані")
        return False
    try:
        import aiohttp
        from playwright.async_api import async_playwright

        log.info("🔑 Playwright: логінюсь в Aternos...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=[
                "--no-sandbox","--disable-setuid-sandbox","--disable-gpu","--disable-dev-shm-usage"
            ])
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await ctx.new_page()

            log.info("   Відкриваю aternos.org/go/ ...")
            await page.goto("https://aternos.org/go/", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(5)

            # Знаходимо і заповнюємо форму
            for sel in ["input[name='user']", "input[type='text']"]:
                try:
                    await page.wait_for_selector(sel, timeout=3000)
                    await page.fill(sel, ATERNOS_USER)
                    break
                except: pass

            for sel in ["input[name='password']", "input[type='password']"]:
                try:
                    await page.wait_for_selector(sel, timeout=3000)
                    await page.fill(sel, ATERNOS_PASS)
                    break
                except: pass

            for sel in ["button[type='submit']", "button:has-text('Login')"]:
                try:
                    await page.click(sel)
                    break
                except: pass

            await asyncio.sleep(5)

            # Витягуємо куки з браузера
            cookies = await ctx.cookies()
            log.info(f"   Отримано {len(cookies)} cookies: {[c['name'] for c in cookies]}")

            await browser.close()

        # Створюємо aiohttp сесію з цими cookies
        jar = aiohttp.CookieJar()
        aternos_session = aiohttp.ClientSession(cookie_jar=jar)

        # Додаємо куки вручну
        for c in cookies:
            from yarl import URL as _URL
        aternos_session.cookie_jar.update_cookies({c['name']: c['value']}, response_url=_URL("https://aternos.org/"))

        log.info("✅ Aternos підключено! (aiohttp сесія з cookies)")
        aternos_connected = True
        return True

    except Exception as e:
        log.error(f"❌ Playwright login: {e}", exc_info=True)
        return False


async def update_server_info() -> bool:
    """Отримуємо статус через HTTP"""
    global server_status, current_players
    if not aternos_connected or not aternos_session:
        return False
    try:
        async with aternos_session.get(
            "https://aternos.org/panel/ajax/status.php",
            params={"server": SERVER_ID},
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            log.info(f"   status → {r.status}")
            if r.status == 200:
                d = await r.json()
                server_status = d.get("status", "offline")
                p = d.get("players", {})
                current_players = p.get("list", []) if isinstance(p, dict) else []
                return True
            elif r.status == 403:
                log.error(f"❌ 403 — cookies невалідні!")
                return False
    except Exception as e:
        log.warning(f"⚠️ update_info: {e}")
    return False


async def _aternos_action(action: str) -> bool:
    """Виконуємо дію start/stop"""
    if not aternos_connected or not aternos_session:
        return False
    global server_status

    try:
        url = f"https://aternos.org/panel/ajax/{action}.php"
        async with aternos_session.get(
            url,
            params={"server": SERVER_ID},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            log.info(f"   {action} → {r.status}")
            if r.status == 200:
                server_status = "starting" if action == "start" else "offline"
                return True
            elif r.status == 403:
                log.error(f"❌ 403 — cookies невалідні!")
                return False
    except Exception as e:
        log.error(f"❌ {action}: {e}")
    return False

async def aternos_start() -> bool: return await _aternos_action("start")
async def aternos_stop()  -> bool: return await _aternos_action("stop")

# ══════════════════════════════════════════════════════════════════
# УТИЛІТИ
# ══════════════════════════════════════════════════════════════════

def icon(s): return {"online":"🟢","offline":"🔴","starting":"🟡"}.get(s,"⚫")
def get_msg(u): return u.callback_query.message if u.callback_query else u.message
async def typing(u):
    try: await get_msg(u).chat.send_action(ChatAction.TYPING)
    except: pass
async def send_log(text, chat_id=None):
    if not telegram_app: return
    t = chat_id or config.get("log_chat_id") or LOG_CHAT_ID
    if not t: return
    try: await telegram_app.bot.send_message(t, text, parse_mode="HTML")
    except Exception as e: log.error(f"❌ send_log: {e}")
def ulabel(u): return f"@{u.effective_user.username} ({u.effective_user.first_name})" if u.effective_user.username else u.effective_user.first_name or "???"
def is_admin(u): return u.effective_user.id in admins
def now_str():  return datetime.now().strftime("%H:%M:%S")
def now_full(): return datetime.now().strftime("%d.%m.%Y %H:%M:%S")
def get_uptime():
    if stats.get("uptime_from") and server_status in ("online","starting"):
        d = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
        return f"{d.seconds//3600}ч {(d.seconds%3600)//60}м"
    return "—"

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Запустить", callback_data="on")],
        [InlineKeyboardButton("👥 Игроки", callback_data="players"),
         InlineKeyboardButton("⚙️ Статус",  callback_data="status")],
        [InlineKeyboardButton("📊 Инфо",    callback_data="info")],
    ])

def admin_kb():
    m = config.get("maintenance", False)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Старт",       callback_data="adm_start"),
         InlineKeyboardButton("🔴 Стоп",        callback_data="adm_stop")],
        [InlineKeyboardButton("🔄 Перезапуск",  callback_data="adm_restart")],
        [InlineKeyboardButton("📢 Броадкаст",   callback_data="adm_broadcast")],
        [InlineKeyboardButton("👥 Пользователи",callback_data="adm_users")],
        [InlineKeyboardButton("📊 Статистика",  callback_data="adm_stats")],
        [InlineKeyboardButton(f"{'🔴 Выкл' if m else '🟢 Вкл'} техобслуживание", callback_data="adm_maintenance")],
        [InlineKeyboardButton("❌ Закрыть",      callback_data="adm_exit")],
    ])

# ══════════════════════════════════════════════════════════════════
# КОМАНДИ
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 Техобслуживание!", parse_mode="HTML"); return
    await update_server_info()
    await get_msg(update).reply_text(
        f"<b>🎮 {config['server_name']}</b>\n\n"
        f"{icon(server_status)} {server_status.upper()}\n"
        f"🌐 <code>{config['server_ip']}</code>\n"
        f"🔌 <code>{config['server_port']}</code>",
        reply_markup=main_kb(), parse_mode="HTML")

async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 Техобслуживание!", parse_mode="HTML"); return
    if not config.get("allow_all_start", True) and not is_admin(update):
        await get_msg(update).reply_text("🚫 Только администраторы!", parse_mode="HTML"); return
    msg = await get_msg(update).reply_text("⏳ Запускаю...", parse_mode="HTML")
    if not aternos_connected:
        await msg.edit_text("❌ Aternos не подключён!", parse_mode="HTML"); return
    await update_server_info()
    if server_status in ("online","starting"):
        await msg.edit_text(f"✅ Уже работает!\n🌐 <code>{config['server_ip']}</code>", parse_mode="HTML"); return
    ok = await aternos_start()
    if ok:
        stats["starts"]+=1; stats["last_start"]=datetime.now().isoformat(); stats["uptime_from"]=datetime.now().isoformat(); save_all()
        await msg.edit_text(f"🟢 ЗАПУЩЕН!\n⏰ {now_str()}", parse_mode="HTML")
        await send_log(f"🟢 ЗАПУСК\n👤 {ulabel(update)}\n⏰ {now_full()}")
    else:
        await msg.edit_text("❌ Ошибка запуска!", parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await update_server_info()
    await get_msg(update).reply_text(
        f"{icon(server_status)} {server_status.upper()}\n"
        f"👥 {len(current_players)} игроков\n"
        f"🌐 <code>{config['server_ip']}</code>\n"
        f"⏱ {get_uptime()}",
        parse_mode="HTML")

async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await update_server_info()
    if server_status != "online":
        await get_msg(update).reply_text(f"🔴 {server_status.upper()}", parse_mode="HTML"); return
    if not current_players:
        await get_msg(update).reply_text("👥 Никого нет", parse_mode="HTML"); return
    pl = "\n".join(f"  🧑 {p}" for p in current_players)
    await get_msg(update).reply_text(f"👥 ОНЛАЙН: {len(current_players)}\n\n{pl}", parse_mode="HTML")

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await update_server_info()
    await get_msg(update).reply_text(
        f"📊 <b>{config['server_name'].upper()}</b>\n\n"
        f"{icon(server_status)} {server_status.upper()} | 👥 {len(current_players)}\n\n"
        f"🚀 Запусков: {stats['starts']}\n"
        f"🛑 Остановок: {stats['stops']}\n"
        f"👥 Пользователей: {len(users)}",
        parse_mode="HTML")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    adm = "\n🔐 /admin" if is_admin(update) else ""
    await get_msg(update).reply_text(
        "/on /status /players /info /help" + adm,
        parse_mode="HTML")

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    h = {"on":cmd_on,"players":cmd_players,"status":cmd_status,"info":cmd_info}
    fn = h.get(q.data)
    if fn: await fn(update, ctx)

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if is_admin(update): await show_admin_panel(update); return
    await update.message.reply_text("🔐 Код доступа:", parse_mode="HTML")
    return WAIT_CODE

async def got_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == ADMIN_CODE:
        admins.add(update.effective_user.id); save_all()
        await update.message.reply_text("✅ Добро пожаловать!", parse_mode="HTML")
        await show_admin_panel(update)
    else:
        await update.message.reply_text("❌ Неверный код!", parse_mode="HTML")
    return ConversationHandler.END

async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

async def show_admin_panel(update: Update):
    await update_server_info()
    m = config.get("maintenance", False)
    await get_msg(update).reply_text(
        f"⚙️ ПАНЕЛЬ\n\n"
        f"🔌 Aternos: {'✅' if aternos_connected else '❌'}\n"
        f"🖥 {icon(server_status)} {server_status.upper()}\n"
        f"👥 {len(current_players)} | 👤 {len(users)}\n"
        f"🔧 {'ВКЛ' if m else 'ВЫКЛ'}",
        reply_markup=admin_kb(), parse_mode="HTML")

async def on_admin_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(update): await q.answer("❌", show_alert=True); return
    d = q.data

    if d == "adm_start":
        await q.message.edit_text("⏳ Запускаю...", parse_mode="HTML")
        ok = await aternos_start()
        if ok:
            stats["starts"]+=1; stats["last_start"]=datetime.now().isoformat(); stats["uptime_from"]=datetime.now().isoformat(); save_all()
            await q.message.edit_text("🟢 ЗАПУЩЕН!", reply_markup=admin_kb(), parse_mode="HTML")
        else:
            await q.message.edit_text("❌ Ошибка!", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_stop":
        await q.message.edit_text("⏳ Останавливаю...", parse_mode="HTML")
        ok = await aternos_stop()
        if ok:
            stats["stops"]+=1; stats["last_stop"]=datetime.now().isoformat(); stats["uptime_from"]=None; save_all()
            await q.message.edit_text("🔴 ОСТАНОВЛЕН!", reply_markup=admin_kb(), parse_mode="HTML")
        else:
            await q.message.edit_text("❌ Ошибка!", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_restart":
        await q.message.edit_text("⏳ Перезапускаю...", parse_mode="HTML")
        await aternos_stop(); await asyncio.sleep(5)
        ok = await aternos_start()
        if ok:
            stats["restarts"]=stats.get("restarts",0)+1; stats["starts"]+=1; stats["last_start"]=datetime.now().isoformat(); save_all()
            await q.message.edit_text("🔄 ПЕРЕЗАПУЩЕН!", reply_markup=admin_kb(), parse_mode="HTML")
        else:
            await q.message.edit_text("❌ Ошибка!", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_broadcast":
        ctx.user_data["action"] = "broadcast"
        await q.message.reply_text("📢 Напиши сообщение:", parse_mode="HTML")

    elif d == "adm_users":
        if not users: await q.message.edit_text("👥 Пусто", reply_markup=admin_kb(), parse_mode="HTML"); return
        lines = []
        for uid, info in list(users.items())[-10:]:
            n=info.get("first_name","???"); u=f"@{info['username']}" if info.get("username") else "—"
            lines.append(f"• {n} {u}")
        await q.message.edit_text(f"👥 ({len(users)})\n\n"+"\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_stats":
        await q.message.edit_text(
            f"📊 СТАТИСТИКА\n\n🚀 {stats['starts']} | 🛑 {stats['stops']} | 🔄 {stats.get('restarts',0)}\n"
            f"👥 {len(users)} | 👤 {len(admins)}\n\n⏰ {now_full()}",
            reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_maintenance":
        config["maintenance"]=not config.get("maintenance",False); save_all()
        word="ВКЛ" if config["maintenance"] else "ВЫКЛ"
        await q.message.edit_text(f"🔧 Техобслуживание {word}", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_exit":
        await q.message.edit_text("👋 Закрыто.", parse_mode="HTML")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    action = ctx.user_data.get("action")
    if not action or not is_admin(update): return
    text = update.message.text.strip()
    if text.startswith("/cancel"): ctx.user_data["action"] = None; await update.message.reply_text("❌"); return
    ctx.user_data["action"] = None
    msg_text = f"📢 {text}\n\n— {config['server_name']}"
    sent=0
    for uid in list(users.keys()):
        try: await telegram_app.bot.send_message(int(uid), msg_text); sent+=1; await asyncio.sleep(0.05)
        except: pass
    await update.message.reply_text(f"✅ {sent} получили")

# ══════════════════════════════════════════════════════════════════
# FLASK + MAIN
# ══════════════════════════════════════════════════════════════════

flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return jsonify({"status":"ok","v":"16.0","server":server_status,"players":len(current_players),"aternos":aternos_connected}), 200

@flask_app.route("/ping")
def ping(): return "pong", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)

async def _background_login():
    await asyncio.sleep(3)
    log.info("🔑 Фоновий логін...")
    ok = await aternos_login()
    if ok:
        log.info("✅ Aternos підключено!")
        await send_log("✅ Aternos підключено! Бот готовий.")
    else:
        log.error("❌ Aternos логін не вдався")
        await send_log("❌ Aternos не підключено.\n\nПеревір ATERNOS_USER, ATERNOS_PASS")

async def main():
    global telegram_app
    load_all()
    asyncio.create_task(_background_login())

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", cmd_admin)],
        states={WAIT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_code)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)],
    )
    telegram_app.add_handler(admin_conv)

    for cmd, fn in [
        ("start",cmd_start),("on",cmd_on),("status",cmd_status),
        ("players",cmd_players),("info",cmd_info),("help",cmd_help),
    ]:
        telegram_app.add_handler(CommandHandler(cmd, fn))

    telegram_app.add_handler(CallbackQueryHandler(on_admin_button, pattern="^adm_"))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("✅ Бот готов!")

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    await asyncio.Event().wait()

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    try: asyncio.run(main())
    except KeyboardInterrupt: log.info("⛔ Зупинено")
    except Exception as e: log.error(f"❌ {e}", exc_info=True); sys.exit(1)
