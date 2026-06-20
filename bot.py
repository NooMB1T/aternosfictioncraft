#!/usr/bin/env python3
"""
ATERNOS TELEGRAM BOT v13.0
Playwright + Cloudflare bypass
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)
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
log.info("🎮 ATERNOS BOT v13.0 — Playwright Edition")
log.info("=" * 60)

STATS_FILE  = "stats.json"
CONFIG_FILE = "config.json"
ADMINS_FILE = "admins.json"
USERS_FILE  = "users.json"

stats = {
    "starts": 0, "stops": 0, "restarts": 0,
    "last_start": None, "last_stop": None,
    "uptime_from": None, "peak_players": 0,
    "total_commands": 0,
}
config = {
    "log_chat_id": LOG_CHAT_ID,
    "maintenance": False,
    "server_name": "fictionmine",
    "server_ip": "fictionmine.aternos.me",
    "server_port": "19132",
}
admins: set = set()
users: dict = {}

telegram_app      = None
aternos_browser   = None
aternos_connected = False
server_status     = "offline"
current_players   = []

WAIT_CODE = 1

def load_all():
    global stats, config, admins, users
    for fname, obj in [(STATS_FILE, stats), (CONFIG_FILE, config)]:
        if os.path.exists(fname):
            try:
                with open(fname, encoding="utf-8") as f:
                    obj.update(json.load(f))
            except Exception as e:
                log.warning(f"⚠️ {fname}: {e}")
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, encoding="utf-8") as f:
                admins = set(json.load(f))
        except Exception:
            admins = set()
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, encoding="utf-8") as f:
                users = json.load(f)
        except Exception:
            users = {}

def save_all():
    try:
        with open(STATS_FILE,  "w", encoding="utf-8") as f: json.dump(stats,  f, ensure_ascii=False, indent=2)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(config, f, ensure_ascii=False, indent=2)
        with open(ADMINS_FILE, "w", encoding="utf-8") as f: json.dump(list(admins), f)
        with open(USERS_FILE,  "w", encoding="utf-8") as f: json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"❌ save: {e}")

def reg(update: Update):
    u = update.effective_user
    users[str(u.id)] = {
        "first_name": u.first_name or "",
        "username":   u.username   or "",
        "last_seen":  datetime.now().isoformat(),
    }
    stats["total_commands"] = stats.get("total_commands", 0) + 1

# ══════════════════════════════════════════════════════════════════
# ATERNOS — Playwright
# ══════════════════════════════════════════════════════════════════

async def aternos_login() -> bool:
    global aternos_browser, aternos_connected, server_status, current_players

    if not all([ATERNOS_USER, ATERNOS_PASS, SERVER_ID]):
        log.warning("⚠️ Aternos дані не встановлені")
        return False

    try:
        from playwright.async_api import async_playwright

        log.info("🔑 Запускаю браузер для Aternos...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ])
            page = await browser.new_page()

            log.info("🌐 Заходжу на aternos.org...")
            await page.goto("https://aternos.org/go/", wait_until="networkidle", timeout=30000)

            log.info("🔐 Логінюсь...")
            await page.fill("input[name='user']", ATERNOS_USER)
            await page.fill("input[name='password']", ATERNOS_PASS)
            await page.click("button[type='submit']")

            log.info("⏳ Чекаю логін...")
            try:
                await page.wait_for_url("**/servers", timeout=15000)
                log.info("✅ Логін успішний!")
            except Exception as e:
                log.error(f"❌ Логін не спрацював: {e}")
                await browser.close()
                return False

            aternos_browser = browser
            aternos_connected = True
            log.info("✅ Aternos браузер готовий!")
            return True

    except ImportError:
        log.error("❌ playwright не встановлено!")
        log.error("   pip install playwright")
        log.error("   playwright install chromium")
        return False
    except Exception as e:
        log.error(f"❌ Помилка браузера: {e}", exc_info=True)
        return False


async def update_server_info() -> bool:
    global server_status, current_players
    if not aternos_browser:
        return False
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = aternos_browser
            page = await browser.new_page()
            await page.goto(f"https://aternos.org/server/{SERVER_ID}", timeout=15000)

            status = await page.text_content(".server-status") or "offline"
            server_status = "online" if "online" in status.lower() else "offline"

            await page.close()
        return True
    except Exception as e:
        log.warning(f"⚠️ update_info: {e}")
        return False


async def aternos_start() -> bool:
    global server_status
    if not aternos_browser:
        return False
    try:
        page = await aternos_browser.new_page()
        await page.goto(f"https://aternos.org/server/{SERVER_ID}", timeout=15000)
        await page.click("button:has-text('Start')")
        server_status = "starting"
        await page.close()
        log.info("✅ Сервер запускається!")
        return True
    except Exception as e:
        log.error(f"❌ start: {e}")
        return False


async def aternos_stop() -> bool:
    global server_status
    if not aternos_browser:
        return False
    try:
        page = await aternos_browser.new_page()
        await page.goto(f"https://aternos.org/server/{SERVER_ID}", timeout=15000)
        await page.click("button:has-text('Stop')")
        server_status = "offline"
        await page.close()
        log.info("✅ Сервер зупиняється!")
        return True
    except Exception as e:
        log.error(f"❌ stop: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# УТИЛІТИ
# ══════════════════════════════════════════════════════════════════

def icon(s):
    return {"online":"🟢","offline":"🔴","starting":"🟡"}.get(s,"⚫")

def get_msg(update: Update):
    return update.callback_query.message if update.callback_query else update.message

async def typing(update: Update):
    try: await get_msg(update).chat.send_action(ChatAction.TYPING)
    except Exception: pass

async def send_log(text: str, chat_id=None):
    if not telegram_app: return
    target = chat_id or config.get("log_chat_id") or LOG_CHAT_ID
    if not target: return
    try:
        await telegram_app.bot.send_message(target, text, parse_mode="HTML")
    except Exception as e:
        log.error(f"❌ send_log: {e}")

def ulabel(update: Update) -> str:
    u = update.effective_user
    name = u.first_name or "???"
    return f"@{u.username} ({name})" if u.username else name

def is_admin(update: Update) -> bool:
    return update.effective_user.id in admins

def now_str():  return datetime.now().strftime("%H:%M:%S")
def now_full(): return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def get_uptime() -> str:
    if stats.get("uptime_from") and server_status == "online":
        delta = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
        h = delta.seconds // 3600
        m = (delta.seconds % 3600) // 60
        return f"{h}ч {m}м"
    return "—"

# ══════════════════════════════════════════════════════════════════
# КЛАВІАТУРИ
# ══════════════════════════════════════════════════════════════════

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Запустить", callback_data="on")],
        [InlineKeyboardButton("👥 Игроки", callback_data="players"),
         InlineKeyboardButton("⚙️ Статус", callback_data="status")],
        [InlineKeyboardButton("📊 Инфо", callback_data="info")],
    ])

def admin_kb():
    m = config.get("maintenance", False)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Запустить", callback_data="adm_start"),
         InlineKeyboardButton("🔴 Остановить", callback_data="adm_stop")],
        [InlineKeyboardButton("🔄 Перезапустить", callback_data="adm_restart")],
        [InlineKeyboardButton("📢 Броадкаст", callback_data="adm_broadcast")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="adm_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(
            f"{'🔴 Выкл' if m else '🟢 Вкл'} техобслуживание",
            callback_data="adm_maintenance"
        )],
        [InlineKeyboardButton("❌ Закрыть", callback_data="adm_exit")],
    ])

# ══════════════════════════════════════════════════════════════════
# КОМАНДИ — ЗВИЧАЙНІ
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 <b>Техобслуживание!</b>", parse_mode="HTML")
        return
    await asyncio.to_thread(update_server_info)
    await get_msg(update).reply_text(
        f"<b>🎮 {config['server_name']}</b>\n\n"
        f"{icon(server_status)} {server_status.upper()}\n"
        f"👥 {len(current_players)} игроков\n"
        f"🌐 <code>{config['server_ip']}</code>",
        reply_markup=main_kb(), parse_mode="HTML")


async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 <b>Техобслуживание!</b>", parse_mode="HTML")
        return
    msg = await get_msg(update).reply_text("⏳ <b>Запускаю...</b>", parse_mode="HTML")
    if not aternos_connected:
        await msg.edit_text("❌ <b>Aternos не подключён!</b>", parse_mode="HTML")
        return
    await asyncio.to_thread(update_server_info)
    if server_status == "online":
        await msg.edit_text("✅ <b>Уже работает!</b>", parse_mode="HTML")
        return
    ok = await aternos_start()
    if ok:
        stats["starts"] += 1
        stats["last_start"] = datetime.now().isoformat()
        stats["uptime_from"] = datetime.now().isoformat()
        save_all()
        await msg.edit_text(f"🟢 <b>ЗАПУЩЕН!</b>\n⏰ {now_str()}", parse_mode="HTML")
        await send_log(f"🟢 <b>ЗАПУСК</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
    else:
        await msg.edit_text("❌ <b>Ошибка!</b>", parse_mode="HTML")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await asyncio.to_thread(update_server_info)
    await get_msg(update).reply_text(
        f"{icon(server_status)} <b>{server_status.upper()}</b>\n"
        f"🌐 <code>{config['server_ip']}</code>\n"
        f"⏱ {get_uptime()}",
        parse_mode="HTML")


async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    ls = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "—"
    await get_msg(update).reply_text(
        f"<b>📊 СТАТИСТИКА</b>\n\n"
        f"🚀 Запусков: {stats['starts']}\n"
        f"🛑 Остановок: {stats['stops']}\n"
        f"▶️ Последний: {ls}",
        parse_mode="HTML")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    admin_tip = "\n🔐 /admin — панель администратора" if is_admin(update) else ""
    await get_msg(update).reply_text(
        "<b>❓ КОМАНДЫ</b>\n\n"
        "/on — запустить\n"
        "/status — статус\n"
        "/info — информация\n"
        "/help — помощь"
        f"{admin_tip}",
        parse_mode="HTML")

# ══════════════════════════════════════════════════════════════════
# CALLBACK
# ══════════════════════════════════════════════════════════════════

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    h = {"on": cmd_on, "status": cmd_status, "info": cmd_info, "players": cmd_status}
    fn = h.get(q.data)
    if fn:
        await fn(update, ctx)

# ══════════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════════

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if is_admin(update):
        await show_admin_panel(update)
        return
    await update.message.reply_text("🔐 <b>Код доступа:</b>", parse_mode="HTML")
    return WAIT_CODE

async def got_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == ADMIN_CODE:
        admins.add(update.effective_user.id)
        save_all()
        await update.message.reply_text("✅ <b>Добро пожаловать!</b>", parse_mode="HTML")
        await show_admin_panel(update)
    else:
        await update.message.reply_text("❌ <b>Неверный код!</b>", parse_mode="HTML")
    return ConversationHandler.END

async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

async def show_admin_panel(update: Update):
    await asyncio.to_thread(update_server_info)
    await get_msg(update).reply_text(
        "⚙️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        f"🖥 {icon(server_status)} {server_status.upper()}\n"
        f"🔌 Aternos: {'✅' if aternos_connected else '❌'}\n"
        f"👤 Пользователей: {len(users)}",
        reply_markup=admin_kb(), parse_mode="HTML")

async def on_admin_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update):
        await q.answer("🚫 Нет доступа!", show_alert=True)
        return
    d = q.data

    if d == "adm_start":
        await q.message.edit_text("⏳ <b>Запускаю...</b>", parse_mode="HTML")
        ok = await aternos_start()
        if ok:
            stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat()
            stats["uptime_from"] = datetime.now().isoformat()
            save_all()
            await q.message.edit_text("🟢 <b>ЗАПУЩЕН!</b>", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🟢 <b>ЗАПУСК (ADMIN)</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_stop":
        await q.message.edit_text("⏳ <b>Останавливаю...</b>", parse_mode="HTML")
        ok = await aternos_stop()
        if ok:
            stats["stops"] += 1
            stats["last_stop"] = datetime.now().isoformat()
            save_all()
            await q.message.edit_text("🔴 <b>ОСТАНОВЛЕН!</b>", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔴 <b>СТОП (ADMIN)</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_restart":
        await q.message.edit_text("⏳ <b>Перезапускаю...</b>", parse_mode="HTML")
        await aternos_stop()
        await asyncio.sleep(5)
        ok = await aternos_start()
        if ok:
            stats["restarts"] = stats.get("restarts", 0) + 1
            stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat()
            save_all()
            await q.message.edit_text("🔄 <b>ПЕРЕЗАПУЩЕН!</b>", reply_markup=admin_kb(), parse_mode="HTML")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_broadcast":
        ctx.user_data["action"] = "broadcast"
        await q.message.reply_text("📢 <b>Напиши сообщение:</b>", parse_mode="HTML")

    elif d == "adm_users":
        if not users:
            await q.message.edit_text("👥 Нет пользователей", reply_markup=admin_kb(), parse_mode="HTML")
            return
        lines = [f"• {info.get('first_name')} @{info['username']}" for _, info in list(users.items())[-10:]]
        await q.message.edit_text(f"👥 <b>ПОЛЬЗОВАТЕЛИ ({len(users)})</b>\n\n" + "\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_stats":
        await q.message.edit_text(
            f"📊 <b>СТАТИСТИКА</b>\n\n"
            f"🚀 Запусков: {stats['starts']}\n"
            f"🛑 Остановок: {stats['stops']}\n"
            f"🔄 Перезапусков: {stats.get('restarts',0)}",
            reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_maintenance":
        config["maintenance"] = not config.get("maintenance", False)
        save_all()
        await q.message.edit_text(
            f"🔧 <b>Техобслуживание {'ВКЛ' if config['maintenance'] else 'ВЫКЛ'}</b>",
            reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_exit":
        await q.message.edit_text("👋 <b>Панель закрыта.</b>", parse_mode="HTML")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.get("action") == "broadcast" and is_admin(update):
        text = update.message.text
        ctx.user_data["action"] = None
        sent = 0
        for uid in users.keys():
            try:
                await telegram_app.bot.send_message(int(uid), f"📢 <b>{text}</b>", parse_mode="HTML")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await update.message.reply_text(f"✅ Отправлено {sent} пользователям!")

# ══════════════════════════════════════════════════════════════════
# FLASK
# ══════════════════════════════════════════════════════════════════

flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return jsonify({"status":"ok","server":server_status,"aternos":aternos_connected}), 200

@flask_app.route("/ping")
def ping():
    return "pong", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

async def main():
    global telegram_app

    load_all()
    await aternos_login()

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", cmd_admin)],
        states={WAIT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_code)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)],
    )

    telegram_app.add_handler(admin_conv)
    for cmd, fn in [
        ("start", cmd_start), ("on", cmd_on), ("status", cmd_status),
        ("info", cmd_info), ("help", cmd_help),
    ]:
        telegram_app.add_handler(CommandHandler(cmd, fn))

    telegram_app.add_handler(CallbackQueryHandler(on_admin_button, pattern="^adm_"))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("✅ Бот готов!")

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
        log.error(f"❌ Помилка: {e}", exc_info=True)
        sys.exit(1)
