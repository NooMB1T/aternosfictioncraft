#!/usr/bin/env python3
"""
ATERNOS TELEGRAM BOT v15.0
Playwright (тільки для логіну) + WebSocket (для управління)
"""

import os, sys, json, asyncio, logging, random, hashlib
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
log.info("🎮 ATERNOS BOT v15.0 — WebSocket Edition")
log.info("=" * 60)

# ══════════════════════════════════════════════════════════════════
# СТАН
# ══════════════════════════════════════════════════════════════════

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
aternos_connected = False
aternos_session   = {}   # cookies після логіну
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
# ATERNOS — Playwright логін + WebSocket управління
# ══════════════════════════════════════════════════════════════════

async def aternos_login() -> bool:
    """Playwright логін з очікуванням Cloudflare і діагностикою"""
    global aternos_connected, aternos_session
    if not all([ATERNOS_USER, ATERNOS_PASS]):
        log.warning("⚠️ Aternos дані не вказані")
        return False
    try:
        from playwright.async_api import async_playwright
        log.info("🔑 Playwright: логінюсь в Aternos...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
                locale="en-US",
            )
            page = await ctx.new_page()

            # Прибираємо ознаки headless
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            log.info("   Відкриваю aternos.org/go/ ...")
            await page.goto(
                "https://aternos.org/go/",
                wait_until="networkidle",
                timeout=60000
            )

            # Чекаємо Cloudflare
            log.info("   Чекаю Cloudflare (5 сек)...")
            await asyncio.sleep(5)

            current_url = page.url
            title = await page.title()
            log.info(f"   URL: {current_url} | Title: {title}")

            # Пробуємо знайти поле user різними способами
            selectors_user = [
                "input[name='user']",
                "input[type='text']",
                "#user",
                "input[placeholder*='user' i]",
                "input[placeholder*='name' i]",
                "input[autocomplete*='user' i]",
            ]

            user_field = None
            for sel in selectors_user:
                try:
                    await page.wait_for_selector(sel, timeout=3000, state="visible")
                    user_field = sel
                    log.info(f"   ✅ Поле знайдено: {sel}")
                    break
                except Exception:
                    log.info(f"   Не знайдено: {sel}")

            if not user_field:
                html = await page.content()
                log.error(f"   Форма не знайдена! HTML: {html[:800]}")
                await send_log(
                    "❌ <b>Форма логіну не знайдена!</b>\n\n"
                    f"URL: <code>{current_url}</code>\n"
                    f"Title: <code>{title}</code>\n\n"
                    f"<code>{html[:400]}</code>"
                )
                await browser.close()
                return False

            # Вводимо логін
            log.info("   Вводжу логін...")
            await page.fill(user_field, ATERNOS_USER)
            await asyncio.sleep(0.5)

            # Вводимо пароль
            for sel in ["input[name='password']", "input[type='password']"]:
                try:
                    await page.wait_for_selector(sel, timeout=3000, state="visible")
                    await page.fill(sel, ATERNOS_PASS)
                    log.info(f"   ✅ Пароль введено: {sel}")
                    break
                except Exception:
                    pass

            await asyncio.sleep(0.5)

            # Натискаємо кнопку
            for sel in ["button[type='submit']", "button:has-text('Login')", ".login-button"]:
                try:
                    await page.wait_for_selector(sel, timeout=2000, state="visible")
                    await page.click(sel)
                    log.info(f"   ✅ Кнопка: {sel}")
                    break
                except Exception:
                    pass

            log.info("   Чекаю після входу (5 сек)...")
            await asyncio.sleep(5)

            final_url = page.url
            cookies = await ctx.cookies()
            aternos_session = {c["name"]: c["value"] for c in cookies}
            log.info(f"   Фінальний URL: {final_url}")
            log.info(f"   Куки: {list(aternos_session.keys())}")

            await browser.close()

        if "server" in final_url or "ATERNOS_SESSION" in aternos_session:
            aternos_connected = True
            log.info("✅ Aternos логін успішний!")
            return True
        else:
            log.error(f"❌ Логін не вдався: {final_url}")
            await send_log(
                f"❌ <b>Логін не вдався</b>\n"
                f"URL: <code>{final_url}</code>\n"
                f"Куки: <code>{list(aternos_session.keys())}</code>"
            )
            return False

    except ImportError:
        log.warning("⚠️ Playwright не встановлено")
        return False
    except Exception as e:
        log.error(f"❌ Playwright login: {e}", exc_info=True)
        await send_log(f"❌ <b>Помилка Playwright:</b>\n<code>{str(e)[:300]}</code>")
        return False
def _cookie_header() -> str:
    """Формує cookie header для запитів"""
    return "; ".join(f"{k}={v}" for k, v in aternos_session.items())


async def update_server_info() -> bool:
    """Отримуємо статус через HTTP (з cookies)"""
    global server_status, current_players
    if not aternos_connected or not aternos_session:
        return False
    try:
        import aiohttp
        headers = {
            "Cookie": _cookie_header(),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://aternos.org/server/{SERVER_ID}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://aternos.org/panel/ajax/status.php",
                params={"server": SERVER_ID},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                log.info(f"   status → {r.status}")
                if r.status == 200:
                    data = await r.json()
                    server_status = data.get("status", "offline")
                    p = data.get("players", {})
                    current_players = p.get("list", []) if isinstance(p, dict) else []
                    return True
    except ImportError:
        # Fallback на requests якщо немає aiohttp
        try:
            import requests
            headers = {
                "Cookie": _cookie_header(),
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest",
            }
            r = requests.get(
                "https://aternos.org/panel/ajax/status.php",
                params={"server": SERVER_ID},
                headers=headers,
                timeout=15
            )
            log.info(f"   status (requests) → {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                server_status = data.get("status", "offline")
                p = data.get("players", {})
                current_players = p.get("list", []) if isinstance(p, dict) else []
                return True
        except Exception as e:
            log.warning(f"⚠️ status requests: {e}")
    except Exception as e:
        log.warning(f"⚠️ update_info: {e}")
    return False


async def _aternos_action(action: str) -> bool:
    """Виконуємо дію start/stop через HTTP з cookies"""
    if not aternos_connected or not aternos_session:
        return False
    global server_status

    endpoint = f"https://aternos.org/panel/ajax/{action}.php"
    headers = {
        "Cookie": _cookie_header(),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://aternos.org/server/{SERVER_ID}",
    }
    params = {"server": SERVER_ID}

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, params=params, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=30)) as r:
                log.info(f"   {action} → {r.status}")
                if r.status == 200:
                    server_status = "starting" if action == "start" else "offline"
                    return True
    except ImportError:
        import requests
        r = requests.get(endpoint, params=params, headers=headers, timeout=30)
        log.info(f"   {action} (requests) → {r.status_code}")
        if r.status_code == 200:
            server_status = "starting" if action == "start" else "offline"
            return True
    except Exception as e:
        log.error(f"❌ {action}: {e}")
    return False

async def aternos_start() -> bool: return await _aternos_action("start")
async def aternos_stop()  -> bool: return await _aternos_action("stop")

# ══════════════════════════════════════════════════════════════════
# УТИЛІТИ
# ══════════════════════════════════════════════════════════════════

def icon(s): return {"online":"🟢","offline":"🔴","starting":"🟡","stopping":"🟠"}.get(s,"⚫")
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

# ══════════════════════════════════════════════════════════════════
# КЛАВІАТУРИ
# ══════════════════════════════════════════════════════════════════

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Запустить", callback_data="on")],
        [InlineKeyboardButton("👥 Игроки", callback_data="players"),
         InlineKeyboardButton("⚙️ Статус",  callback_data="status")],
        [InlineKeyboardButton("📊 Инфо",    callback_data="info"),
         InlineKeyboardButton("🗺 Войти",    callback_data="connect")],
    ])

def admin_kb():
    m = config.get("maintenance", False)
    a = config.get("allow_all_start", True)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Старт",       callback_data="adm_start"),
         InlineKeyboardButton("🔴 Стоп",        callback_data="adm_stop")],
        [InlineKeyboardButton("🔄 Перезапуск",  callback_data="adm_restart")],
        [InlineKeyboardButton("📢 Броадкаст",   callback_data="adm_broadcast")],
        [InlineKeyboardButton("📣 Анонс",       callback_data="adm_announce")],
        [InlineKeyboardButton("👥 Пользователи",callback_data="adm_users")],
        [InlineKeyboardButton("📊 Статистика",  callback_data="adm_stats")],
        [InlineKeyboardButton("⚠️ Варны",       callback_data="adm_warns")],
        [InlineKeyboardButton("📝 Заметки",     callback_data="adm_notes")],
        [InlineKeyboardButton(f"{'🔴 Выкл' if m else '🟢 Вкл'} техобслуживание", callback_data="adm_maintenance")],
        [InlineKeyboardButton(f"{'✅' if a else '❌'} Все могут запускать", callback_data="adm_toggle_start")],
        [InlineKeyboardButton("🔄 Переподключить Aternos", callback_data="adm_reconnect")],
        [InlineKeyboardButton("📜 Логи → этот чат",        callback_data="adm_setlog")],
        [InlineKeyboardButton("🗑 Сброс статистики",        callback_data="adm_resetstats")],
        [InlineKeyboardButton("❌ Закрыть",                 callback_data="adm_exit")],
    ])

# ══════════════════════════════════════════════════════════════════
# КОМАНДИ
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 <b>Техобслуживание!</b>\nПопробуй позже.", parse_mode="HTML"); return
    await update_server_info()
    await get_msg(update).reply_text(
        f"<b>🎮 {config['server_name']} — Minecraft Bedrock</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} Сервер: <b>{server_status.upper()}</b>\n"
        f"👥 Игроков: <b>{len(current_players)}</b>\n"
        f"🌐 IP: <code>{config['server_ip']}</code>\n"
        f"🔌 Порт: <code>{config['server_port']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>{config.get('motd','')}</i>",
        reply_markup=main_kb(), parse_mode="HTML")

async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 <b>Техобслуживание!</b>", parse_mode="HTML"); return
    if not config.get("allow_all_start", True) and not is_admin(update):
        await get_msg(update).reply_text("🚫 <b>Только администраторы могут запускать!</b>", parse_mode="HTML"); return
    msg = await get_msg(update).reply_text("⏳ <b>Запускаю сервер...</b>", parse_mode="HTML")
    if not aternos_connected:
        await msg.edit_text("❌ <b>Aternos не подключён!</b>", parse_mode="HTML"); return
    await update_server_info()
    if server_status in ("online","starting"):
        await msg.edit_text(f"✅ <b>Уже {'работает' if server_status=='online' else 'запускается'}!</b>\n🌐 <code>{config['server_ip']}</code>", parse_mode="HTML"); return
    ok = await aternos_start()
    if ok:
        stats["starts"] += 1; stats["last_start"] = datetime.now().isoformat(); stats["uptime_from"] = datetime.now().isoformat(); save_all()
        await msg.edit_text(f"🟢 <b>ЗАПУСКАЕТСЯ!</b>\n\n⏰ {now_str()}\n🌐 <code>{config['server_ip']}</code>\n🔌 <code>{config['server_port']}</code>\n\n<i>⏱ 1-3 минуты</i>", parse_mode="HTML")
        await send_log(f"🟢 <b>ЗАПУСК</b>\n👤 {ulabel(update)}\n⏰ {now_full()}\n📊 #{stats['starts']}")
    else:
        await msg.edit_text("❌ <b>Не удалось!</b>", parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await update_server_info()
    await get_msg(update).reply_text(
        f"{icon(server_status)} <b>СТАТУС</b>\n\n🎮 {config['server_name']} (Bedrock)\n📍 <b>{server_status.upper()}</b>\n"
        f"👥 Игроков: <b>{len(current_players)}</b>\n🌐 <code>{config['server_ip']}</code>\n"
        f"🔌 <code>{config['server_port']}</code>\n⏱ Аптайм: <b>{get_uptime()}</b>\n🔌 Aternos: {'✅' if aternos_connected else '❌'}\n⏰ {now_str()}",
        parse_mode="HTML")

async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await update_server_info()
    if server_status != "online":
        await get_msg(update).reply_text(f"🔴 <b>{server_status.upper()}</b>\nЗапусти /on", parse_mode="HTML"); return
    if not current_players:
        await get_msg(update).reply_text(f"👥 <b>Никого нет</b> 😿\n🌐 <code>{config['server_ip']}</code>", parse_mode="HTML"); return
    if len(current_players) > stats["peak_players"]: stats["peak_players"] = len(current_players); save_all()
    pl = "\n".join(f"  🧑 <b>{p}</b>" for p in current_players)
    await get_msg(update).reply_text(f"👥 <b>ОНЛАЙН: {len(current_players)}</b>\n\n{pl}\n\n⏱ {get_uptime()}", parse_mode="HTML")

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await update_server_info()
    ls = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "—"
    lo = datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")  if stats.get("last_stop")  else "—"
    await get_msg(update).reply_text(
        f"<b>📊 {config['server_name'].upper()}</b>\n\n{icon(server_status)} {server_status.upper()} | 👥 {len(current_players)}\n\n"
        f"🚀 Запусков: <b>{stats['starts']}</b>\n🛑 Остановок: <b>{stats['stops']}</b>\n"
        f"🔄 Перезапусков: <b>{stats.get('restarts',0)}</b>\n👑 Пик: <b>{stats['peak_players']}</b>\n"
        f"⏱ Аптайм: <b>{get_uptime()}</b>\n💬 Команд: <b>{stats.get('total_commands',0)}</b>\n"
        f"👤 Пользователей: <b>{len(users)}</b>\n\n▶️ {ls} | ⏹ {lo}", parse_mode="HTML")

async def cmd_connect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    await get_msg(update).reply_text(
        f"🗺 <b>КАК ПОДКЛЮЧИТЬСЯ</b>\n\n🌐 <code>{config['server_ip']}</code>\n🔌 <code>{config['server_port']}</code>\n📱 Bedrock\n\n"
        "1. Minecraft → Играть → Серверы → Добавить\n"
        f"2. Адрес: <code>{config['server_ip']}</code>\n3. Порт: <code>{config['server_port']}</code>\n\n"
        f"{icon(server_status)} {server_status.upper()}", parse_mode="HTML")

async def cmd_rules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await get_msg(update).reply_text(
        f"📜 <b>ПРАВИЛА</b>\n\n✅ Строить, торговать, кланы, PvP в арене\n\n"
        "❌ Гриферство, читы, оскорбления, спам\n\n⚠️ 1 — варн | 2 — бан 24ч | 3 — перм.бан", parse_mode="HTML")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    adm = "\n🔐 /admin — панель администратора" if is_admin(update) else ""
    await get_msg(update).reply_text(
        "<b>❓ КОМАНДЫ</b>\n\n/on — запустить\n/status — статус\n/players — онлайн\n/info — статистика\n"
        "/connect — как войти\n/rules — правила\n/random — совет\n/uptime — аптайм\n"
        "/vote — проголосовать\n/seed — сид мира\n/shop — магазин\n/top — топ игроков\n/motd — сообщение дня" + adm,
        parse_mode="HTML")

async def cmd_random(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    tips = ["💡 Кровать = точка возрождения!","⚔️ Добыча III — больше ресурсов!","🛡 Щит блокирует урон!",
            "💎 Алмазы чаще на Y=-58!","🔥 Огниво = портал в Ад!","⚡ Молния + свинья = свиножитель!",
            "🎣 Рыбалка ночью — лучшие трофеи!","🏔 Изумруды только в горах!","🌙 Спи — пропускаешь ночь!","⛏ Удача III — больше алмазов!"]
    await get_msg(update).reply_text(f"🎲 <b>СОВЕТ</b>\n\n{random.choice(tips)}\n\n<i>/random — ещё!</i>", parse_mode="HTML")

async def cmd_uptime(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    await get_msg(update).reply_text(f"⏱ <b>АПТАЙМ</b>\n\n{icon(server_status)} {server_status.upper()}\n⏱ <b>{get_uptime()}</b>\n⏰ {now_full()}", parse_mode="HTML")

async def cmd_laststart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    ls = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m.%Y в %H:%M") if stats.get("last_start") else "никогда"
    lo = datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m.%Y в %H:%M")  if stats.get("last_stop")  else "никогда"
    await get_msg(update).reply_text(f"📅 <b>ИСТОРИЯ</b>\n\n▶️ {ls}\n⏹ {lo}\n🚀 Всего: {stats['starts']}", parse_mode="HTML")

async def cmd_logthischat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if not is_admin(update):
        await get_msg(update).reply_text("🚫 <b>Только для администраторов!</b>", parse_mode="HTML"); return
    config["log_chat_id"] = update.effective_chat.id; save_all()
    await update.message.reply_text(f"✅ <b>Логи здесь!</b>\nID: <code>{update.effective_chat.id}</code>", parse_mode="HTML")

async def cmd_vote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await get_msg(update).reply_text(
        "🗳 <b>ПРОГОЛОСУЙ ЗА СЕРВЕР!</b>\n\n🔗 <a href='https://minecraft-server-list.com/'>minecraft-server-list.com</a>\n"
        "🔗 <a href='https://minecraftservers.org/'>minecraftservers.org</a>\n\n🎁 Голос = бонуси на сервері!",
        parse_mode="HTML", disable_web_page_preview=True)

async def cmd_seed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    seed = config.get("world_seed") or "Не установлен"
    await get_msg(update).reply_text(f"🌍 <b>СИД МИРА</b>\n\n<code>{seed}</code>", parse_mode="HTML")

async def cmd_shop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    link = config.get("shop_link") or "Не настроен"
    await get_msg(update).reply_text(
        "🛒 <b>ДОНАТ-МАГАЗИН</b>\n\n💎 VIP — ник, /fly\n👑 PREMIUM — всё + /god\n🏆 ELITE — всё + варп\n\n"
        f"🔗 {link}", parse_mode="HTML")

async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    top = config.get("top_players", [])
    if not top:
        await get_msg(update).reply_text("🏆 <b>ТОП ИГРОКОВ</b>\n\n<i>Статистика собирается...</i>", parse_mode="HTML"); return
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines = [f"{medals[i]} <b>{p['name']}</b> — {p.get('score','?')} очков" for i, p in enumerate(top[:10])]
    await get_msg(update).reply_text("🏆 <b>ТОП 10</b>\n\n" + "\n".join(lines), parse_mode="HTML")

async def cmd_motd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await get_msg(update).reply_text(f"💬 <b>СООБЩЕНИЕ ДНЯ</b>\n\n{config.get('motd','Добро пожаловать!')}\n\n{icon(server_status)} {server_status.upper()}", parse_mode="HTML")

async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if not is_admin(update):
        await get_msg(update).reply_text("🚫 <b>Только для администраторов!</b>", parse_mode="HTML"); return
    text = " ".join(ctx.args) if ctx.args else ""
    if not text:
        if not notes: await update.message.reply_text("📝 <b>Заметок нет</b>", parse_mode="HTML"); return
        lines = [f"{i+1}. {n}" for i,n in enumerate(notes[-10:])]
        await update.message.reply_text("📝 <b>ЗАМЕТКИ</b>\n\n" + "\n".join(lines), parse_mode="HTML"); return
    notes.append(f"[{now_str()}] {text}"); save_all()
    await update.message.reply_text("📝 <b>Сохранено!</b>", parse_mode="HTML")

async def cmd_warn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if not is_admin(update):
        await get_msg(update).reply_text("🚫 <b>Только для администраторов!</b>", parse_mode="HTML"); return
    if not ctx.args:
        if not warns: await update.message.reply_text("⚠️ <b>Варнов нет</b>", parse_mode="HTML"); return
        lines = []
        for uid, cnt in warns.items():
            info = users.get(uid,{}); uname = f"@{info.get('username','')}" if info.get("username") else f"ID:{uid}"
            lines.append(f"• {info.get('first_name','???')} {uname} — ⚠️{cnt}/3")
        await update.message.reply_text("⚠️ <b>ВАРНЫ</b>\n\n" + "\n".join(lines), parse_mode="HTML"); return
    target = ctx.args[0].lstrip("@")
    uid = next((u for u,i in users.items() if i.get("username","").lower() == target.lower()), None)
    if not uid: await update.message.reply_text(f"❌ @{target} не знайдений!", parse_mode="HTML"); return
    warns[uid] = warns.get(uid,0) + 1; save_all()
    await update.message.reply_text(f"⚠️ <b>ВАРН!</b>\n👤 @{target}\n⚠️ {warns[uid]}/3", parse_mode="HTML")
    await send_log(f"⚠️ <b>ВАРН</b>\n👤 @{target}\n⚠️ {warns[uid]}/3\n👮 {ulabel(update)}")

async def cmd_setmotd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if not is_admin(update): await get_msg(update).reply_text("🚫", parse_mode="HTML"); return
    text = " ".join(ctx.args) if ctx.args else ""
    if not text: await update.message.reply_text("❌ /setmotd Текст", parse_mode="HTML"); return
    config["motd"] = text; save_all()
    await update.message.reply_text(f"✅ <b>MOTD обновлён!</b>\n\n{text}", parse_mode="HTML")

async def cmd_setseed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if not is_admin(update): await get_msg(update).reply_text("🚫", parse_mode="HTML"); return
    seed = " ".join(ctx.args) if ctx.args else ""
    if not seed: await update.message.reply_text("❌ /setseed -1234567890", parse_mode="HTML"); return
    config["world_seed"] = seed; save_all()
    await update.message.reply_text(f"✅ <b>Сид:</b> <code>{seed}</code>", parse_mode="HTML")

async def cmd_setshop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if not is_admin(update): await get_msg(update).reply_text("🚫", parse_mode="HTML"); return
    link = " ".join(ctx.args) if ctx.args else ""
    if not link: await update.message.reply_text("❌ /setshop https://...", parse_mode="HTML"); return
    config["shop_link"] = link; save_all()
    await update.message.reply_text(f"✅ <b>Магазин:</b> {link}", parse_mode="HTML")

# ══════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    h = {"on":cmd_on,"players":cmd_players,"status":cmd_status,"info":cmd_info,"connect":cmd_connect}
    fn = h.get(q.data)
    if fn: await fn(update, ctx)

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if is_admin(update): await show_admin_panel(update); return
    await update.message.reply_text("🔐 <b>Код доступа:</b>", parse_mode="HTML")
    return WAIT_CODE

async def got_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == ADMIN_CODE:
        admins.add(update.effective_user.id); save_all()
        await update.message.reply_text("✅ <b>Добро пожаловать, Администратор!</b>", parse_mode="HTML")
        await send_log(f"🔐 <b>НОВЫЙ ADMIN</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        await show_admin_panel(update)
    else:
        await update.message.reply_text("❌ <b>Неверный код!</b>", parse_mode="HTML")
        await send_log(f"⚠️ <b>НЕУДАЧНАЯ ПОПЫТКА</b>\n👤 {ulabel(update)}")
    return ConversationHandler.END

async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

async def show_admin_panel(update: Update):
    await update_server_info()
    m = config.get("maintenance", False)
    await get_msg(update).reply_text(
        "⚙️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        f"🔌 Aternos: {'✅' if aternos_connected else '❌'}\n"
        f"🖥 {icon(server_status)} {server_status.upper()}\n"
        f"👥 Игроков: {len(current_players)}\n"
        f"👤 Пользователей: {len(users)}\n"
        f"🔐 Админов: {len(admins)}\n"
        f"⚠️ Варнов: {sum(warns.values())}\n"
        f"📝 Заметок: {len(notes)}\n"
        f"🔧 Тех.работы: {'🟡 ВКЛ' if m else '🟢 ВЫКЛ'}",
        reply_markup=admin_kb(), parse_mode="HTML")

async def on_admin_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(update): await q.answer("🚫 Нет доступа!", show_alert=True); return
    d = q.data

    if d == "adm_start":
        await q.message.edit_text("⏳ <b>Запускаю...</b>", parse_mode="HTML")
        await update_server_info()
        if server_status in ("online","starting"):
            await q.message.edit_text("✅ <b>Уже работает!</b>", reply_markup=admin_kb(), parse_mode="HTML"); return
        ok = await aternos_start()
        if ok:
            stats["starts"]+=1; stats["last_start"]=datetime.now().isoformat(); stats["uptime_from"]=datetime.now().isoformat(); save_all()
            await q.message.edit_text(f"🟢 <b>ЗАПУЩЕН!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🟢 <b>ЗАПУСК (ADMIN)</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_stop":
        await q.message.edit_text("⏳ <b>Останавливаю...</b>", parse_mode="HTML")
        ok = await aternos_stop()
        if ok:
            stats["stops"]+=1; stats["last_stop"]=datetime.now().isoformat(); stats["uptime_from"]=None; save_all()
            await q.message.edit_text(f"🔴 <b>ОСТАНОВЛЕН!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔴 <b>СТОП (ADMIN)</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_restart":
        await q.message.edit_text("⏳ <b>Перезапускаю...</b>", parse_mode="HTML")
        await aternos_stop(); await asyncio.sleep(5)
        ok = await aternos_start()
        if ok:
            stats["restarts"]=stats.get("restarts",0)+1; stats["starts"]+=1; stats["last_start"]=datetime.now().isoformat(); stats["uptime_from"]=datetime.now().isoformat(); save_all()
            await q.message.edit_text(f"🔄 <b>ПЕРЕЗАПУЩЕН!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔄 <b>ПЕРЕЗАПУСК</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_broadcast":
        ctx.user_data["action"] = "broadcast"
        await q.message.reply_text("📢 <b>Напиши сообщение:</b>\n<i>/cancel — отмена</i>", parse_mode="HTML")

    elif d == "adm_announce":
        ctx.user_data["action"] = "announce"
        await q.message.reply_text("📣 <b>Напиши анонс:</b>\n<i>/cancel — отмена</i>", parse_mode="HTML")

    elif d == "adm_users":
        if not users: await q.message.edit_text("👥 Нет пользователей", reply_markup=admin_kb(), parse_mode="HTML"); return
        lines = []
        for uid, info in list(users.items())[-15:]:
            n=info.get("first_name","???"); u=f"@{info['username']}" if info.get("username") else "—"
            w=warns.get(uid,0); m="🔐" if int(uid) in admins else ""; wm=f"⚠️{w}" if w else ""
            try: seen=datetime.fromisoformat(info.get("last_seen","")).strftime("%d.%m %H:%M")
            except: seen="—"
            lines.append(f"• {n} {u} {m}{wm} <i>{seen}</i>")
        await q.message.edit_text(f"👥 <b>ПОЛЬЗОВАТЕЛИ ({len(users)})</b>\n\n"+"\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_stats":
        await update_server_info()
        ls=datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "—"
        lo=datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")  if stats.get("last_stop")  else "—"
        await q.message.edit_text(
            f"📊 <b>СТАТИСТИКА</b>\n\n🚀 {stats['starts']} | 🛑 {stats['stops']} | 🔄 {stats.get('restarts',0)}\n"
            f"👑 Пик: {stats['peak_players']} | ⏱ {get_uptime()}\n💬 Команд: {stats.get('total_commands',0)}\n"
            f"👤 Юзеров: {len(users)} | ⚠️ Варнов: {sum(warns.values())}\n\n▶️ {ls} | ⏹ {lo}\n⏰ {now_full()}",
            reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_warns":
        if not warns: await q.message.edit_text("⚠️ <b>Варнов нет</b>", reply_markup=admin_kb(), parse_mode="HTML"); return
        lines=[]
        for uid,cnt in warns.items():
            info=users.get(uid,{}); u=f"@{info.get('username','')}" if info.get("username") else f"ID:{uid}"
            lines.append(f"• {info.get('first_name','???')} {u} — ⚠️{cnt}/3")
        await q.message.edit_text("⚠️ <b>ВАРНЫ</b>\n\n"+"\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_notes":
        if not notes: await q.message.edit_text("📝 <b>Заметок нет</b>", reply_markup=admin_kb(), parse_mode="HTML"); return
        lines=[f"{i+1}. {n}" for i,n in enumerate(notes[-10:])]
        await q.message.edit_text("📝 <b>ЗАМЕТКИ</b>\n\n"+"\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_maintenance":
        config["maintenance"]=not config.get("maintenance",False); save_all()
        word="ВКЛ 🟡" if config["maintenance"] else "ВЫКЛ 🟢"
        await q.message.edit_text(f"🔧 <b>Техобслуживание {word}</b>", reply_markup=admin_kb(), parse_mode="HTML")
        await send_log(f"🔧 {word}\n👤 {ulabel(update)}")

    elif d == "adm_toggle_start":
        config["allow_all_start"]=not config.get("allow_all_start",True); save_all()
        word="ВСЕ ✅" if config["allow_all_start"] else "ТОЛЬКО АДМИНЫ 🔐"
        await q.message.edit_text(f"⚙️ <b>Запуск: {word}</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_reconnect":
        await q.message.edit_text("⏳ <b>Переподключаюсь...</b>", parse_mode="HTML")
        ok = await aternos_login()
        await q.message.edit_text(f"🔌 <b>{'✅ Подключён!' if ok else '❌ Не удалось'}</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_setlog":
        config["log_chat_id"]=q.message.chat_id; save_all()
        await q.message.edit_text(f"✅ <b>Логи здесь!</b>\nID: <code>{q.message.chat_id}</code>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_resetstats":
        stats.update({"starts":0,"stops":0,"restarts":0,"last_start":None,"last_stop":None,"uptime_from":None,"peak_players":0,"total_commands":0}); save_all()
        await q.message.edit_text("🗑 <b>Сброшено!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_exit":
        await q.message.edit_text("👋 <b>Панель закрыта.</b>", parse_mode="HTML")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    action = ctx.user_data.get("action")
    if not action or not is_admin(update): return
    text = update.message.text.strip()
    if text.startswith("/cancel"):
        ctx.user_data["action"] = None
        await update.message.reply_text("❌ Отменено."); return
    ctx.user_data["action"] = None
    msg_text = (f"📢 <b>ОБЪЯВЛЕНИЕ — {config['server_name']}</b>\n\n{text}\n\n<i>— Администрация</i>"
                if action=="broadcast" else
                f"📣 <b>━━━━━━━━━━━━━━━━━━━━</b>\n🎮 <b>{config['server_name'].upper()}</b>\n\n{text}\n<b>━━━━━━━━━━━━━━━━━━━━</b>")
    sent=failed=0
    sm = await update.message.reply_text("⏳ <b>Отправляю...</b>", parse_mode="HTML")
    for uid in list(users.keys()):
        try: await telegram_app.bot.send_message(int(uid), msg_text, parse_mode="HTML"); sent+=1; await asyncio.sleep(0.05)
        except: failed+=1
    await sm.edit_text(f"✅ Отправлено: {sent} | ❌ Не доставлено: {failed}", parse_mode="HTML")
    await send_log(f"{'📢' if action=='broadcast' else '📣'} {ulabel(update)}\n✅{sent}/❌{failed}")

async def _background_login():
    """Логін в Aternos у фоні після старту бота"""
    await asyncio.sleep(3)
    log.info("🔑 Фоновий логін...")
    try:
        ok = await aternos_login()
        if ok:
            await send_log("✅ <b>Aternos підключено!</b>")
        else:
            await send_log("❌ <b>Aternos не підключено!</b>\n\nПеревір ATERNOS_USER, ATERNOS_PASS і Playwright.")
    except Exception as e:
        log.error(f"❌ bg_login: {e}", exc_info=True)
        await send_log(f"❌ <b>Помилка:</b>\n<code>{str(e)[:300]}</code>")

async def auto_report():
    await asyncio.sleep(60)
    while True:
        await asyncio.sleep(600)
        if not aternos_connected: continue
        await update_server_info()
        if server_status != "online": continue
        try:
            pl = "\n".join(f"  • {p}" for p in current_players) if current_players else "  (никого)"
            await send_log(f"🟢 <b>АВТООТЧЁТ</b>\n⏰ {now_full()}\n⏱ {get_uptime()}\n👥 ({len(current_players)}):\n{pl}")
        except Exception as e: log.error(f"❌ report: {e}")

# ══════════════════════════════════════════════════════════════════
# FLASK + MAIN
# ══════════════════════════════════════════════════════════════════

flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return jsonify({"status":"ok","v":"15.0","server":server_status,"players":len(current_players),"aternos":aternos_connected}), 200

@flask_app.route("/ping")
def ping(): return "pong", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)

async def main():
    global telegram_app
    load_all()
    # Логін запускається в фоні щоб не блокувати старт бота
    asyncio.create_task(_background_login())

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", cmd_admin)],
        states={WAIT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_code)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)],
    )
    telegram_app.add_handler(admin_conv)

    for cmd, fn in [
        ("start",cmd_start),("on",cmd_on),("status",cmd_status),("players",cmd_players),
        ("info",cmd_info),("connect",cmd_connect),("rules",cmd_rules),("help",cmd_help),
        ("random",cmd_random),("uptime",cmd_uptime),("laststart",cmd_laststart),
        ("logthischat",cmd_logthischat),("vote",cmd_vote),("seed",cmd_seed),
        ("shop",cmd_shop),("top",cmd_top),("motd",cmd_motd),
        ("note",cmd_note),("warn",cmd_warn),("setmotd",cmd_setmotd),
        ("setseed",cmd_setseed),("setshop",cmd_setshop),
    ]:
        telegram_app.add_handler(CommandHandler(cmd, fn))

    telegram_app.add_handler(CallbackQueryHandler(on_admin_button, pattern="^adm_"))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("✅ Бот v15.0 готов!")
    asyncio.create_task(auto_report())

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await asyncio.Event().wait()

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    try: asyncio.run(main())
    except KeyboardInterrupt: log.info("⛔ Зупинено")
    except Exception as e: log.error(f"❌ {e}", exc_info=True); sys.exit(1)
