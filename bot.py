#!/usr/bin/env python3
"""ATERNOS TELEGRAM BOT v19.0 — fictionmine | ULTRA PRO MAX"""

import os, sys, json, asyncio, logging, random, io, time, re
from datetime import datetime
from threading import Thread

from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters, ConversationHandler
)
from telegram.constants import ChatAction
from telegram.error import Conflict
import aiohttp
from yarl import URL as yarl_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)
log = logging.getLogger("bot")

# ═══════════════════════════════════════════════════════════════
# КОНФИГ
# ═══════════════════════════════════════════════════════════════
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
ATERNOS_USER    = os.getenv("ATERNOS_USER", "")
ATERNOS_PASS    = os.getenv("ATERNOS_PASS", "")
SERVER_ID       = os.getenv("SERVER_ID", "")
LOG_CHAT_ID     = int(os.getenv("LOG_CHAT_ID", "0"))
PORT            = int(os.getenv("PORT", "8000"))
ADMIN_CODE      = os.getenv("ADMIN_CODE", "2011")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL      = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN не задан!")
    sys.exit(1)

log.info("=" * 60)
log.info("🎮 ATERNOS BOT v19.0 — fictionmine ULTRA PRO MAX")
log.info("=" * 60)

# ═══════════════════════════════════════════════════════════════
# ФАЙЛЫ
# ═══════════════════════════════════════════════════════════════
STATS_FILE  = "stats.json"
CONFIG_FILE = "config.json"
ADMINS_FILE = "admins.json"
USERS_FILE  = "users.json"
WARNS_FILE  = "warns.json"
NOTES_FILE  = "notes.json"
BANNED_FILE = "banned.json"

stats  = {"starts": 0, "stops": 0, "restarts": 0, "last_start": None,
          "last_stop": None, "uptime_from": None, "peak_players": 0,
          "total_commands": 0}
config = {"log_chat_id": LOG_CHAT_ID, "maintenance": False,
          "server_name": "fictionmine", "server_ip": "fictionmine.aternos.me",
          "server_port": "19132", "motd": "Добро пожаловать на fictionmine! ⛏️",
          "allow_all_start": True, "world_seed": "", "shop_link": "",
          "top_players": [], "lang": "ru", "backup_time": "02:00"}
admins: set = set()
users:  dict = {}
warns:  dict = {}
notes:  list = []
banned: set  = set()

# ═══════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ СТЕЙТ
# ═══════════════════════════════════════════════════════════════
telegram_app       = None
http_session       = None
aternos_connected  = False
last_login_time    = 0
server_status      = "offline"
current_players    = []
login_cookies      = {}

# Browser Control
browser_sessions:     dict = {}   # chat_id -> {pw, browser, ctx, page, active, mobile, ...}
browser_control_mode: set  = set() # chat_ids в режиме ввода

# ConversationHandler states
WAIT_CODE = 1

# Глобальный action для админских вводов (вместо ctx.user_data — проще)
pending_action: dict = {}  # chat_id -> action string

# ═══════════════════════════════════════════════════════════════
# ЗАГРУЗКА / СОХРАНЕНИЕ
# ═══════════════════════════════════════════════════════════════
def load_all():
    global stats, config, admins, users, warns, notes, banned
    for f, obj in [(STATS_FILE, stats), (CONFIG_FILE, config)]:
        if os.path.exists(f):
            try:
                with open(f, encoding="utf-8") as fh:
                    obj.update(json.load(fh))
            except: pass
    for f, key in [(ADMINS_FILE,"a"),(USERS_FILE,"u"),(WARNS_FILE,"w"),(NOTES_FILE,"n"),(BANNED_FILE,"b")]:
        if os.path.exists(f):
            try:
                with open(f, encoding="utf-8") as fh:
                    v = json.load(fh)
                    if key == "a": admins.update(v)
                    elif key == "u": users.update(v)
                    elif key == "w": warns.update(v)
                    elif key == "n": notes.extend(v)
                    elif key == "b": banned.update(v)
            except: pass

def save_all():
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f: json.dump(stats, f, ensure_ascii=False, indent=2)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(config, f, ensure_ascii=False, indent=2)
        with open(ADMINS_FILE, "w") as f: json.dump(list(admins), f)
        with open(USERS_FILE, "w", encoding="utf-8") as f: json.dump(users, f, ensure_ascii=False, indent=2)
        with open(WARNS_FILE, "w", encoding="utf-8") as f: json.dump(warns, f, ensure_ascii=False, indent=2)
        with open(NOTES_FILE, "w", encoding="utf-8") as f: json.dump(notes, f, ensure_ascii=False, indent=2)
        with open(BANNED_FILE, "w") as f: json.dump(list(banned), f)
    except Exception as e:
        log.error(f"save_all: {e}")

# ═══════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════
def reg(u: Update) -> bool:
    usr = u.effective_user
    if usr.id in banned: return False
    users[str(usr.id)] = {
        "first_name": usr.first_name or "",
        "username": usr.username or "",
        "last_seen": datetime.now().isoformat(),
    }
    stats["total_commands"] = stats.get("total_commands", 0) + 1
    return True

def is_admin(u: Update) -> bool:
    return u.effective_user.id in admins

def get_msg(u: Update):
    return u.callback_query.message if u.callback_query else u.message

def icon(s: str) -> str:
    return {"online":"🟢","offline":"🔴","starting":"🟡","stopping":"🟠"}.get(s,"⚫")

def now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")

def now_full() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def get_uptime() -> str:
    if stats.get("uptime_from") and server_status in ("online","starting"):
        d = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
        return f"{d.seconds//3600}ч {(d.seconds%3600)//60}м"
    return "—"

def ulabel(u: Update) -> str:
    return f"@{u.effective_user.username}" if u.effective_user.username else u.effective_user.first_name or "???"

async def typing(u: Update):
    try: await get_msg(u).chat.send_action(ChatAction.TYPING)
    except: pass

async def send_log(text: str):
    if not telegram_app: return
    t_id = config.get("log_chat_id") or LOG_CHAT_ID
    if not t_id: return
    try: await telegram_app.bot.send_message(t_id, text, parse_mode="HTML")
    except: pass

def esc(s: str) -> str:
    """Экранировать HTML-символы."""
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# ═══════════════════════════════════════════════════════════════
# ATERNOS API
# ═══════════════════════════════════════════════════════════════
async def aternos_login() -> bool:
    global aternos_connected, http_session, login_cookies, last_login_time
    if not all([ATERNOS_USER, ATERNOS_PASS]): return False
    if time.time() - last_login_time < 60:
        log.warning("⏳ Логин ещё в процессе")
        return False
    last_login_time = time.time()
    try:
        from playwright.async_api import async_playwright
        log.info("🔑 Playwright: логинюсь на Aternos...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-setuid-sandbox","--disable-gpu",
                      "--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"]
            )
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
            page = await ctx.new_page()
            await page.goto("https://aternos.org/go/", wait_until="domcontentloaded", timeout=60000)

            # Ждём форму логина (макс 45 сек)
            for i in range(45):
                await asyncio.sleep(1)
                if await page.query_selector("input[name='user']"):
                    log.info(f"   ✅ Форма найдена за {i+1}с")
                    break
                log.info(f"   [{i+1}s] Жду форму...")
            else:
                log.error("   ❌ Форма не появилась за 45с")
                await browser.close()
                return False

            # Вводим логин
            for ch in ATERNOS_USER:
                await page.type("input[name='user']", ch, delay=random.randint(50,100))
            await asyncio.sleep(0.3)
            for ch in ATERNOS_PASS:
                await page.type("input[name='password']", ch, delay=random.randint(50,100))
            await asyncio.sleep(0.4)

            # Кликаем Login
            for sel in ["button[type='submit']","button:has-text('Login')","button:has-text('Log in')",".login-button"]:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    log.info(f"   ✅ Кнопка {sel} нажата")
                    break

            await asyncio.sleep(5)
            cookies = await ctx.cookies()
            await browser.close()

        # Строим сессию
        jar = aiohttp.CookieJar()
        login_cookies.clear()
        for c in cookies:
            jar.update_cookies({c["name"]: c["value"]}, response_url=yarl_URL("https://aternos.org/"))
            login_cookies[c["name"]] = c["value"]

        if http_session and not http_session.closed:
            await http_session.close()

        http_session = aiohttp.ClientSession(
            cookie_jar=jar,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        aternos_connected = True
        log.info(f"✅ Aternos подключён! Куков: {len(login_cookies)}")
        return True
    except Exception as e:
        log.error(f"❌ aternos_login: {e}", exc_info=True)
        return False

async def _api(endpoint: str, params=None):
    if not http_session: return None, 0
    try:
        async with http_session.get(
            f"https://aternos.org/panel/ajax/{endpoint}",
            params=params or {"server": SERVER_ID},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            if r.status == 200:
                try: return await r.json(), 200
                except: return {}, 200
            return None, r.status
    except Exception as e:
        log.error(f"_api {endpoint}: {e}")
        return None, 0

async def update_server_info():
    global server_status, current_players
    if not aternos_connected: return
    data, code = await _api("status.php")
    if code == 200 and data:
        server_status = data.get("status", "offline")
        p = data.get("players", {})
        current_players = p.get("list", []) if isinstance(p, dict) else []

async def aternos_start() -> bool:
    _, code = await _api("start.php")
    if code == 200:
        global server_status
        server_status = "starting"
        return True
    return False

async def aternos_stop() -> bool:
    _, code = await _api("stop.php")
    if code == 200:
        global server_status
        server_status = "offline"
        return True
    return False

# ═══════════════════════════════════════════════════════════════
# WATCH — ЖИВОЙ ПРОСМОТР СТРАНИЦЫ
# ═══════════════════════════════════════════════════════════════
watch_sessions: dict = {}  # chat_id -> {url, interval, task, auto_login, w_user, w_pass}

def watch_kb(chat_id: int):
    sess     = watch_sessions.get(chat_id, {})
    interval = sess.get("interval", 20)
    auto     = sess.get("auto_login", True)
    running  = bool(sess.get("task") and not sess["task"].done())
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🟢 Трансляция активна' if running else '🔴 Остановлена'}", callback_data="noop")],
        [InlineKeyboardButton("▶️ Старт" if not running else "🛑 Стоп", callback_data="wt_toggle"),
         InlineKeyboardButton("📸 Снимок сейчас", callback_data="wt_snap")],
        [InlineKeyboardButton("── ⚡ СКОРОСТЬ ──", callback_data="noop")],
        [InlineKeyboardButton("10с" + (" ✅" if interval==10 else ""), callback_data="wt_spd_10"),
         InlineKeyboardButton("20с" + (" ✅" if interval==20 else ""), callback_data="wt_spd_20"),
         InlineKeyboardButton("30с" + (" ✅" if interval==30 else ""), callback_data="wt_spd_30"),
         InlineKeyboardButton("60с" + (" ✅" if interval==60 else ""), callback_data="wt_spd_60")],
        [InlineKeyboardButton("✏️ Своя скорость", callback_data="wt_spd_custom")],
        [InlineKeyboardButton("── 🔑 АВТОРИЗАЦИЯ ──", callback_data="noop")],
        [InlineKeyboardButton(f"Режим: {'🤖 Авто' if auto else '✋ Вручную'}", callback_data="wt_toggle_auth")],
        [InlineKeyboardButton("👤 Логин",  callback_data="wt_set_user"),
         InlineKeyboardButton("🔐 Пароль", callback_data="wt_set_pass")],
        [InlineKeyboardButton("── 🗺 НАВИГАЦИЯ ──", callback_data="noop")],
        [InlineKeyboardButton("🏠 Главная",  callback_data="wt_nav_home"),
         InlineKeyboardButton("🔑 Логин",   callback_data="wt_nav_login"),
         InlineKeyboardButton("🖥 Сервер",  callback_data="wt_nav_server")],
        [InlineKeyboardButton("✏️ Свой URL", callback_data="wt_set_url")],
        [InlineKeyboardButton("🔙 /admin",   callback_data="adm_back_to_admin")],
    ])

async def _watch_snap(chat_id: int, label: str = ""):
    """Одиночный снимок для watch (отдельный Playwright, не путаем с browser_sessions)."""
    sess = watch_sessions.get(chat_id, {})
    url  = sess.get("url", f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/")
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=[
                "--no-sandbox","--disable-gpu","--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ])
            bctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
            )
            await bctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
            # Куки если есть
            if login_cookies:
                await bctx.add_cookies([
                    {"name":k,"value":v,"domain":"aternos.org","path":"/"}
                    for k,v in login_cookies.items()
                ])
            page = await bctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            # Если видим форму логина — логинимся
            if await page.query_selector("input[name='user']"):
                auto   = sess.get("auto_login", True)
                w_user = sess.get("w_user") or (ATERNOS_USER if auto else "")
                w_pass = sess.get("w_pass") or (ATERNOS_PASS if auto else "")
                if w_user and w_pass:
                    for ch in w_user: await page.type("input[name='user']",   ch, delay=random.randint(40,80))
                    for ch in w_pass: await page.type("input[name='password']",ch, delay=random.randint(40,80))
                    for sel in ["button[type='submit']","button:has-text('Login')",".login-button"]:
                        btn = await page.query_selector(sel)
                        if btn: await btn.click(); break
                    await asyncio.sleep(4)
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(2)
            title = await page.title()
            shot  = await page.screenshot(full_page=False)
            await browser.close()
        bio = io.BytesIO(shot); bio.name = "watch.png"
        cap = f"👁 Watch{' · '+label if label else ''}\n📄 {esc(title[:40])}\n🔗 <code>{esc(url[:60])}</code>\n⏰ {now_str()}"
        await telegram_app.bot.send_photo(chat_id, bio, caption=cap, parse_mode="HTML")
    except Exception as e:
        log.error(f"_watch_snap: {e}")
        await telegram_app.bot.send_message(chat_id, f"👁 ❌ <code>{esc(str(e)[:200])}</code>", parse_mode="HTML")

async def _watch_loop(chat_id: int):
    count = 0
    try:
        while True:
            sess     = watch_sessions.get(chat_id, {})
            interval = sess.get("interval", 20)
            count   += 1
            await _watch_snap(chat_id, f"#{count}")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        await telegram_app.bot.send_message(
            chat_id, f"🛑 <b>Watch остановлен.</b> Снимков: {count}", parse_mode="HTML")

async def show_watch(update: Update):
    cid  = update.effective_chat.id if not update.callback_query else update.callback_query.message.chat_id
    sess = watch_sessions.get(cid, {})
    if cid not in watch_sessions:
        watch_sessions[cid] = {
            "interval": 20, "auto_login": True,
            "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/",
        }
        sess = watch_sessions[cid]
    running = bool(sess.get("task") and not sess["task"].done())
    auto    = sess.get("auto_login", True)
    msg     = get_msg(update)
    await msg.reply_text(
        f"👁 <b>WATCH — ЖИВОЙ ПРОСМОТР</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{'🟢 Активен' if running else '🔴 Остановлен'}\n"
        f"⚡ Интервал: <b>{sess.get('interval',20)}с</b>\n"
        f"🔑 Режим: <b>{'🤖 Авто (env)' if auto else '✋ Вручную'}</b>\n"
        f"👤 Логин: <b>{sess.get('w_user','—') if not auto else '(из env)'}</b>\n"
        f"🔐 Пароль: <b>{'✅ задан' if sess.get('w_pass') else '(из env)' if auto else '❌ нет'}</b>\n"
        f"🔗 URL: <code>{esc(sess.get('url','—')[:60])}</code>",
        reply_markup=watch_kb(cid), parse_mode="HTML")

async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update): return
    if not is_admin(update):
        return await get_msg(update).reply_text("🚫 Только для администраторов!", parse_mode="HTML")
    cid  = update.effective_chat.id
    args = ctx.args
    if args and args[0].lower() == "stop":
        sess = watch_sessions.get(cid, {})
        t    = sess.get("task")
        if t and not t.done(): t.cancel()
        return await get_msg(update).reply_text("🛑 Watch остановлен.", parse_mode="HTML")
    await show_watch(update)

# ═══════════════════════════════════════════════════════════════
# БРАУЗЕР КОНТРОЛЬ
# ═══════════════════════════════════════════════════════════════
SPECIAL_KEYS = {
    "<TAB>": "Tab", "<ENTER>": "Enter", "<ESC>": "Escape",
    "<SPACE>": "Space", "<BACKSPACE>": "Backspace", "<DELETE>": "Delete",
    "<UP>": "ArrowUp", "<DOWN>": "ArrowDown", "<LEFT>": "ArrowLeft", "<RIGHT>": "ArrowRight",
    "<HOME>": "Home", "<END>": "End", "<PGUP>": "PageUp", "<PGDN>": "PageDown",
    "<F5>": "F5", "<F12>": "F12",
    "<CTRL+A>": "Control+a", "<CTRL+C>": "Control+c", "<CTRL+V>": "Control+v",
    "<CTRL+Z>": "Control+z", "<CTRL+R>": "Control+r", "<CTRL+X>": "Control+x",
    "<SHIFT+TAB>": "Shift+Tab",
}

async def bc_get_page(chat_id: int):
    sess = browser_sessions.get(chat_id)
    if not sess or not sess.get("active"): return None
    page = sess.get("page")
    if not page or page.is_closed():
        browser_sessions[chat_id]["active"] = False
        return None
    return page

async def bc_screenshot(chat_id: int, caption: str = "", full_page: bool = False):
    """Делает скриншот и отправляет. BytesIO обязателен для PTB v21."""
    page = await bc_get_page(chat_id)
    if not page:
        await telegram_app.bot.send_message(chat_id,
            "❌ <b>Браузер не запущен</b>\n/browser → 🚀 Запустить", parse_mode="HTML")
        return
    try:
        title = await page.title()
        url   = page.url
        shot  = await page.screenshot(full_page=full_page)
        bio   = io.BytesIO(shot); bio.name = "screen.png"
        cap   = caption or f"📸 <b>{esc(title[:50])}</b>\n🔗 <code>{esc(url[:80])}</code>\n⏰ {now_str()}"
        await telegram_app.bot.send_photo(chat_id, bio, caption=cap, parse_mode="HTML")
    except Exception as e:
        log.error(f"bc_screenshot: {e}")
        await telegram_app.bot.send_message(chat_id,
            f"📸 ❌ <code>{esc(str(e)[:200])}</code>", parse_mode="HTML")

async def bc_start(chat_id: int):
    """Запускает персистентный браузер."""
    await bc_close(chat_id)
    try:
        from playwright.async_api import async_playwright
        log.info(f"🌐 bc_start chat={chat_id}")
        pw      = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-gpu","--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"
        ])
        bctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        await bctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        if login_cookies:
            await bctx.add_cookies([
                {"name": k, "value": v, "domain": "aternos.org", "path": "/"}
                for k, v in login_cookies.items()
            ])
        page = await bctx.new_page()
        url  = f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        browser_sessions[chat_id] = {
            "pw": pw, "browser": browser, "ctx": bctx, "page": page,
            "active": True, "mobile": False, "url": url,
            "snaptask": None, "snap_interval": 30,
        }
        log.info(f"✅ bc_start: {await page.title()}")
        return True
    except Exception as e:
        log.error(f"❌ bc_start: {e}", exc_info=True)
        return str(e)

async def bc_close(chat_id: int):
    sess = browser_sessions.pop(chat_id, None)
    browser_control_mode.discard(chat_id)
    if not sess: return
    t = sess.get("snaptask")
    if t and not t.done(): t.cancel()
    try: await sess["browser"].close()
    except: pass
    try: await sess["pw"].stop()
    except: pass

async def bc_ai(chat_id: int, instruction: str):
    """Gemini управляет браузером."""
    page = await bc_get_page(chat_id)
    if not page:
        await telegram_app.bot.send_message(chat_id, "❌ Браузер не запущен!", parse_mode="HTML")
        return
    if not GEMINI_API_KEY:
        await telegram_app.bot.send_message(chat_id,
            "❌ <b>Нет GEMINI_API_KEY!</b>\nДобавь в Railway Variables.\n"
            "Ключ бесплатный: https://aistudio.google.com/app/apikey", parse_mode="HTML")
        return

    await telegram_app.bot.send_message(chat_id,
        f"🤖 <b>Gemini думает...</b>\n<i>{esc(instruction[:80])}</i>", parse_mode="HTML")
    try:
        title     = await page.title()
        page_text = await page.evaluate("()=>document.body.innerText.slice(0,3000)")
        prompt = (
            f"Автоматизируешь браузер Playwright на aternos.org.\n"
            f"URL: {page.url}\nTitle: {title}\nТекст: {page_text}\n\n"
            f"Задача: {instruction}\n\n"
            f"Ответь ТОЛЬКО JSON-массивом без пояснений:\n"
            f'[{{"action":"goto","url":"..."}},'
            f'{{"action":"click","selector":"..."}},'
            f'{{"action":"type","selector":"...","text":"..."}},'
            f'{{"action":"press","key":"Enter"}},'
            f'{{"action":"wait","ms":2000}},'
            f'{{"action":"scroll","y":300}},'
            f'{{"action":"rclick","selector":"..."}},'
            f'{{"action":"screenshot"}}]'
        )
        async with aiohttp.ClientSession() as s:
            async with s.post(GEMINI_URL, params={"key": GEMINI_API_KEY},
                json={"contents":[{"parts":[{"text":prompt}]}],
                      "generationConfig":{"temperature":0.1,"maxOutputTokens":1024}},
                timeout=aiohttp.ClientTimeout(total=30)) as r:
                d = await r.json()
        raw = d["candidates"][0]["content"]["parts"][0]["text"]
        raw = re.sub(r"```json|```","", raw).strip()
        actions = json.loads(raw)
        results = []
        for act in actions:
            a = act.get("action","")
            try:
                if   a == "goto":      await page.goto(act["url"], wait_until="domcontentloaded", timeout=20000); results.append(f"✅ goto")
                elif a == "click":     await page.click(act["selector"], timeout=5000); results.append(f"✅ click: {act['selector'][:30]}")
                elif a == "rclick":    await page.click(act["selector"], button="right", timeout=5000); results.append(f"✅ rclick")
                elif a == "type":      await page.type(act["selector"], act["text"], delay=60); results.append(f"✅ type: «{act['text'][:20]}»")
                elif a == "press":     await page.keyboard.press(act["key"]); results.append(f"✅ press: {act['key']}")
                elif a == "wait":      await asyncio.sleep(act.get("ms",1000)/1000); results.append(f"✅ wait")
                elif a == "scroll":    await page.evaluate(f"window.scrollBy(0,{act.get('y',300)})"); results.append(f"✅ scroll")
                elif a == "screenshot": await bc_screenshot(chat_id, f"🤖 {esc(instruction[:40])}"); results.append(f"✅ screenshot")
            except Exception as e:
                results.append(f"❌ {a}: {str(e)[:50]}")
        await telegram_app.bot.send_message(chat_id,
            f"🤖 <b>Готово ({len(results)} действий):</b>\n" + "\n".join(results[:15]), parse_mode="HTML")
        await bc_screenshot(chat_id, f"🤖 Результат: {esc(instruction[:40])}")
    except Exception as e:
        await telegram_app.bot.send_message(chat_id,
            f"🤖 ❌ <code>{esc(str(e)[:300])}</code>", parse_mode="HTML")

async def _snap_loop(chat_id: int):
    count = 0
    try:
        while True:
            sess = browser_sessions.get(chat_id, {})
            await asyncio.sleep(sess.get("snap_interval", 30))
            if not await bc_get_page(chat_id): break
            count += 1
            await bc_screenshot(chat_id, f"⏱ Авто #{count} | {now_str()}")
    except asyncio.CancelledError:
        await telegram_app.bot.send_message(chat_id,
            f"⏱ <b>Авто-снап стоп.</b> Сделано: {count}", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Запустить", callback_data="on")],
        [InlineKeyboardButton("📊 Статус",     callback_data="status"),
         InlineKeyboardButton("👥 Игроки",     callback_data="players")],
        [InlineKeyboardButton("ℹ️ Инфо",       callback_data="info"),
         InlineKeyboardButton("🗺 Подключиться",callback_data="connect")],
        [InlineKeyboardButton("📜 Правила",    callback_data="rules"),
         InlineKeyboardButton("🎲 Совет",      callback_data="random")],
        [InlineKeyboardButton("🏆 Топ",        callback_data="top"),
         InlineKeyboardButton("🌍 Сид",        callback_data="seed")],
        [InlineKeyboardButton("🗳 Голос",       callback_data="vote"),
         InlineKeyboardButton("🛒 Магазин",    callback_data="shop")],
        [InlineKeyboardButton("⏱ Аптайм",     callback_data="uptime"),
         InlineKeyboardButton("💬 MOTD",       callback_data="motd")],
    ])

def admin_kb():
    m = config.get("maintenance", False)
    a = config.get("allow_all_start", True)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("━━━ 🖥 СЕРВЕР ━━━",         callback_data="noop")],
        [InlineKeyboardButton("🟢 Старт",  callback_data="adm_start"),
         InlineKeyboardButton("🔴 Стоп",   callback_data="adm_stop"),
         InlineKeyboardButton("🔄 Рестарт",callback_data="adm_restart")],
        [InlineKeyboardButton("━━━ 📢 СООБЩЕНИЯ ━━━",      callback_data="noop")],
        [InlineKeyboardButton("📢 Броадкаст",callback_data="adm_broadcast"),
         InlineKeyboardButton("📣 Анонс",   callback_data="adm_announce")],
        [InlineKeyboardButton("━━━ ⚙️ ATERNOS ━━━",        callback_data="noop")],
        [InlineKeyboardButton("🔄 Переподключить",callback_data="adm_reconnect"),
         InlineKeyboardButton("📊 Статус",       callback_data="adm_aternos_status")],
        [InlineKeyboardButton("🍪 Куки вручную", callback_data="adm_set_cookie"),
         InlineKeyboardButton("🔍 Диагностика",  callback_data="adm_diagnose")],
        [InlineKeyboardButton("━━━ 🌐 БРАУЗЕР ━━━",        callback_data="noop")],
        [InlineKeyboardButton("🖥 Remote Browser",callback_data="adm_browser")],
        [InlineKeyboardButton("━━━ 👥 ИГРОКИ ━━━",         callback_data="noop")],
        [InlineKeyboardButton("👥 Список",  callback_data="adm_users"),
         InlineKeyboardButton("⚠️ Варны",  callback_data="adm_warns")],
        [InlineKeyboardButton("⚠️ Дать варн",callback_data="adm_warn_give"),
         InlineKeyboardButton("🚫 Бан",    callback_data="adm_ban")],
        [InlineKeyboardButton("━━━ 🔧 НАСТРОЙКИ ━━━",      callback_data="noop")],
        [InlineKeyboardButton(f"{'🔴 ТехРаботы ВКЛ' if m else '🟢 ТехРаботы ВЫКЛ'}",callback_data="adm_maintenance"),
         InlineKeyboardButton(f"{'✅ Все' if a else '🔐 Адм'}",callback_data="adm_toggle_start")],
        [InlineKeyboardButton("✏️ MOTD",   callback_data="adm_setmotd"),
         InlineKeyboardButton("🌍 Сид",    callback_data="adm_setseed"),
         InlineKeyboardButton("🛒 Магаз",  callback_data="adm_setshop")],
        [InlineKeyboardButton("📝 Заметки",callback_data="adm_notes")],
        [InlineKeyboardButton("━━━ 📈 СТАТИСТИКА ━━━",     callback_data="noop")],
        [InlineKeyboardButton("📊 Стата",  callback_data="adm_stats"),
         InlineKeyboardButton("🗑 Сброс",  callback_data="adm_resetstats"),
         InlineKeyboardButton("📜 Логи→чат",callback_data="adm_setlog")],
        [InlineKeyboardButton("❌ Закрыть",callback_data="adm_exit")],
    ])

def browser_kb(chat_id: int):
    sess    = browser_sessions.get(chat_id, {})
    active  = sess.get("active", False)
    inp_on  = chat_id in browser_control_mode
    mobile  = sess.get("mobile", False)
    ai_ok   = "🤖 Gemini ✅" if GEMINI_API_KEY else "🤖 Нет ключа"
    snapping= sess.get("snaptask") and not sess["snaptask"].done() if sess.get("snaptask") else False
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'🟢 АКТИВЕН' if active else '🔴 НЕ ЗАПУЩЕН'}",
            callback_data="noop")],
        [InlineKeyboardButton("🚀 Старт",  callback_data="bc_start"),
         InlineKeyboardButton("🔄 Рестарт",callback_data="bc_restart"),
         InlineKeyboardButton("🛑 Стоп",   callback_data="bc_close")],
        # Клавиши
        [InlineKeyboardButton("── ⌨️ КЛАВИШИ ──", callback_data="noop")],
        [InlineKeyboardButton("TAB",   callback_data="bck_Tab"),
         InlineKeyboardButton("ENTER", callback_data="bck_Enter"),
         InlineKeyboardButton("ESC",   callback_data="bck_Escape"),
         InlineKeyboardButton("⌫",     callback_data="bck_Backspace")],
        [InlineKeyboardButton("▲",callback_data="bck_ArrowUp"),
         InlineKeyboardButton("▼",callback_data="bck_ArrowDown"),
         InlineKeyboardButton("◀",callback_data="bck_ArrowLeft"),
         InlineKeyboardButton("▶",callback_data="bck_ArrowRight")],
        [InlineKeyboardButton("F5",    callback_data="bck_F5"),
         InlineKeyboardButton("Ctrl+A",callback_data="bck_cA"),
         InlineKeyboardButton("Ctrl+C",callback_data="bck_cC"),
         InlineKeyboardButton("Ctrl+V",callback_data="bck_cV")],
        # Мышь
        [InlineKeyboardButton("── 🖱 МЫШЬ ──", callback_data="noop")],
        [InlineKeyboardButton("🖱 ЛКМ",  callback_data="bcm_lmb"),
         InlineKeyboardButton("🖱 ПКМ",  callback_data="bcm_rmb"),
         InlineKeyboardButton("🖱 2×",   callback_data="bcm_dbl"),
         InlineKeyboardButton("🔍 Hover",callback_data="bcm_hover")],
        [InlineKeyboardButton("↕ Drag",  callback_data="bcm_drag"),
         InlineKeyboardButton("📜 ↓",    callback_data="bcm_sd"),
         InlineKeyboardButton("📜 ↑",    callback_data="bcm_su"),
         InlineKeyboardButton("📜 →",    callback_data="bcm_sr")],
        # Навигация
        [InlineKeyboardButton("── 🗺 НАВИГАЦИЯ ──", callback_data="noop")],
        [InlineKeyboardButton("🏠",callback_data="bcn_home"),
         InlineKeyboardButton("🔑 Логин",callback_data="bcn_login"),
         InlineKeyboardButton("🖥 Сервер",callback_data="bcn_server")],
        [InlineKeyboardButton("◀️",callback_data="bcn_back"),
         InlineKeyboardButton("🔄",callback_data="bcn_reload"),
         InlineKeyboardButton("▶️",callback_data="bcn_fwd"),
         InlineKeyboardButton("✏️ URL",callback_data="bcn_url")],
        # Инструменты
        [InlineKeyboardButton("── 🔧 ИНСТРУМЕНТЫ ──", callback_data="noop")],
        [InlineKeyboardButton("📸 Скрин",    callback_data="bct_snap"),
         InlineKeyboardButton("🖼 Полный",   callback_data="bct_snapfull"),
         InlineKeyboardButton("📊 Инфо",     callback_data="bct_info")],
        [InlineKeyboardButton("🔎 Найти",    callback_data="bct_find"),
         InlineKeyboardButton("📋 Текст",    callback_data="bct_copytext"),
         InlineKeyboardButton("🎯 Кл.текст", callback_data="bct_clicktext")],
        [InlineKeyboardButton("📝 Форма",    callback_data="bct_fillform"),
         InlineKeyboardButton("🧹 Куки",     callback_data="bct_clearcookies"),
         InlineKeyboardButton("🌙 Dark",     callback_data="bct_dark")],
        [InlineKeyboardButton(f"{'📱 Моб ✅' if mobile else '🖥 Desktop'}",callback_data="bct_mobile"),
         InlineKeyboardButton("🔍+",callback_data="bct_zin"),
         InlineKeyboardButton("🔍-",callback_data="bct_zout"),
         InlineKeyboardButton(f"⏱{'🟢' if snapping else '🔴'}",callback_data="bct_autosnap")],
        # Ввод
        [InlineKeyboardButton("── ✍️ ВВОД ──", callback_data="noop")],
        [InlineKeyboardButton(
            f"⌨️ Ввод в браузер: {'🟢 ВКЛ' if inp_on else '🔴 ВЫКЛ'}",
            callback_data="bct_input")],
        # ИИ
        [InlineKeyboardButton(f"── {ai_ok} ──", callback_data="noop")],
        [InlineKeyboardButton("🤖 Залогиниться", callback_data="bca_login"),
         InlineKeyboardButton("🤖 Задача...",    callback_data="bca_custom")],
        [InlineKeyboardButton("🔙 /admin", callback_data="adm_back_to_admin")],
    ])

# ═══════════════════════════════════════════════════════════════
# КОМАНДЫ ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update):
        return await get_msg(update).reply_text("🚫 <b>Ты забанен!</b>", parse_mode="HTML")
    save_all()
    if config.get("maintenance") and not is_admin(update):
        return await get_msg(update).reply_text("🔧 <b>Техработы!</b>\nПопробуй позже.", parse_mode="HTML")
    await typing(update)
    await update_server_info()
    pl = f"{len(current_players)} онлайн" if server_status == "online" else "сервер выключен"
    await get_msg(update).reply_text(
        f"⛏️ <b>FictionMine — Minecraft Bedrock</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} <b>Статус:</b> {server_status.upper()}\n"
        f"👥 <b>Игроки:</b> {pl}\n"
        f"🌐 <b>IP:</b> <code>{config['server_ip']}</code>\n"
        f"🔌 <b>Порт:</b> <code>{config['server_port']}</code>\n"
        f"⏱ <b>Аптайм:</b> {get_uptime()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>{config.get('motd','')}</i>",
        reply_markup=main_kb(), parse_mode="HTML")

async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update): return
    if config.get("maintenance") and not is_admin(update):
        return await get_msg(update).reply_text("🔧 Техработы!", parse_mode="HTML")
    if not config.get("allow_all_start", True) and not is_admin(update):
        return await get_msg(update).reply_text("🚫 Только администраторы могут запускать!", parse_mode="HTML")
    msg = await get_msg(update).reply_text("⏳ <b>Запускаю...</b>", parse_mode="HTML")
    if not aternos_connected:
        return await msg.edit_text("❌ <b>Aternos не подключён!</b>\nАдмин проверит подключение.", parse_mode="HTML")
    await update_server_info()
    if server_status in ("online","starting"):
        return await msg.edit_text(
            f"✅ <b>Сервер уже {'работает' if server_status=='online' else 'запускается'}!</b>\n"
            f"🌐 <code>{config['server_ip']}</code>\n🔌 <code>{config['server_port']}</code>",
            parse_mode="HTML")
    ok = await aternos_start()
    if ok:
        stats["starts"] += 1; stats["last_start"] = datetime.now().isoformat()
        stats["uptime_from"] = datetime.now().isoformat(); save_all()
        await msg.edit_text(
            f"🟢 <b>СЕРВЕР ЗАПУСКАЕТСЯ!</b>\n\n"
            f"🌐 <code>{config['server_ip']}</code>\n🔌 <code>{config['server_port']}</code>\n"
            f"⏰ {now_str()}\n\n<i>⏱ обычно 1-3 минуты</i>", parse_mode="HTML")
        await send_log(f"🟢 <b>ЗАПУСК</b>\n👤 {ulabel(update)}\n⏰ {now_full()}\n🚀 #{stats['starts']}")
    else:
        await msg.edit_text("❌ <b>Ошибка запуска!</b>\nПопробуй ещё или напиши администратору.", parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    await get_msg(update).reply_text(
        f"{icon(server_status)} <b>СТАТУС</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 FictionMine (Bedrock)\n📍 <b>{server_status.upper()}</b>\n"
        f"👥 Игроков: <b>{len(current_players)}</b>\n⏱ Аптайм: <b>{get_uptime()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <code>{config['server_ip']}</code>\n🔌 <code>{config['server_port']}</code>\n⏰ {now_str()}",
        parse_mode="HTML")

async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    if server_status != "online":
        return await get_msg(update).reply_text(f"🔴 Сервер {server_status.upper()}\nЗапусти: /on", parse_mode="HTML")
    if not current_players:
        return await get_msg(update).reply_text(
            f"👥 <b>Сейчас никого нет</b>\n\nБудь первым!\n🌐 <code>{config['server_ip']}</code>", parse_mode="HTML")
    if len(current_players) > stats["peak_players"]:
        stats["peak_players"] = len(current_players); save_all()
    pl = "\n".join(f"  ⚔️ <b>{p}</b>" for p in current_players)
    await get_msg(update).reply_text(
        f"👥 <b>ОНЛАЙН: {len(current_players)}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n{pl}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n⏱ {get_uptime()} | 👑 Рекорд: {stats['peak_players']}",
        parse_mode="HTML")

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    ls = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "—"
    lo = datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")  if stats.get("last_stop")  else "—"
    await get_msg(update).reply_text(
        f"📊 <b>СТАТИСТИКА FICTIONMINE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} {server_status.upper()} | 👥 {len(current_players)}\n\n"
        f"🚀 Запусков: <b>{stats['starts']}</b>\n🛑 Остановок: <b>{stats['stops']}</b>\n"
        f"🔄 Рестартов: <b>{stats.get('restarts',0)}</b>\n👑 Рекорд: <b>{stats['peak_players']}</b>\n"
        f"⏱ Аптайм: <b>{get_uptime()}</b>\n💬 Команд: <b>{stats.get('total_commands',0)}</b>\n"
        f"👤 Юзеров: <b>{len(users)}</b>\n\n▶️ {ls} | ⏹ {lo}",
        parse_mode="HTML")

async def cmd_connect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    await get_msg(update).reply_text(
        f"🗺 <b>КАК ПОДКЛЮЧИТЬСЯ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 <b>Minecraft Bedrock Edition</b>\n\n"
        f"1️⃣ Открой Minecraft\n2️⃣ Играть → Серверы → Добавить сервер\n"
        f"3️⃣ Адрес: <code>{config['server_ip']}</code>\n"
        f"4️⃣ Порт: <code>{config['server_port']}</code>\n\n"
        f"{icon(server_status)} Сейчас: <b>{server_status.upper()}</b>",
        parse_mode="HTML")

async def cmd_rules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await get_msg(update).reply_text(
        "📜 <b>ПРАВИЛА FICTIONMINE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ <b>РАЗРЕШЕНО:</b>\n• Строительство и исследование\n• Торговля между игроками\n"
        "• Кланы и союзы\n• PvP в спец. зонах\n\n"
        "❌ <b>ЗАПРЕЩЕНО:</b>\n• Гриферство и разрушение\n• Читы, хаки, дюпы\n"
        "• Оскорбления и спам\n• X-ray и подобное\n\n"
        "⚠️ <b>НАКАЗАНИЯ:</b>\n1️⃣ Предупреждение\n2️⃣ Бан 24ч\n3️⃣ Перманентный бан\n\n"
        "<i>Приятной игры! ⛏️</i>", parse_mode="HTML")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    adm = "\n\n🔐 /admin — панель администратора\n🌐 /browser — управление браузером" if is_admin(update) else ""
    await get_msg(update).reply_text(
        "❓ <b>ПОМОЩЬ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🌐 Сервер:</b>\n/on — запустить | /status — статус | /players — кто онлайн\n\n"
        "<b>ℹ️ Инфо:</b>\n/info — статистика | /connect — подключиться | /rules — правила\n\n"
        "<b>🎮 Прочее:</b>\n/random — совет | /top | /vote | /seed | /shop | /uptime | /motd"
        f"{adm}", parse_mode="HTML")

async def cmd_random(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    tips = ["💡 Кровать устанавливает точку возрождения!","⚔️ Зачарование «Добыча III» — больше ресурсов!",
            "🛡️ Щит блокирует весь урон от стрел!","💎 Алмазы чаще на уровне Y=-58!",
            "🔥 Огниво создает портал в Ад!","⚡ Молния + свинья = свиноезд!",
            "🎣 Рыбалка ночью — лучшие трофеи!","🏔️ Изумруды только в горах!",
            "⛏️ Кирка с «Удача III» — больше алмазов!","🌙 Спи ночью — пропускаешь мобов!"]
    await get_msg(update).reply_text(
        f"🎲 <b>СОВЕТ ДНЯ</b>\n\n{random.choice(tips)}\n\n<i>/random — ещё совет</i>", parse_mode="HTML")

async def cmd_uptime(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await update_server_info()
    await get_msg(update).reply_text(
        f"⏱ <b>АПТАЙМ</b>\n\n{icon(server_status)} {server_status.upper()}\n<b>{get_uptime()}</b>\n⏰ {now_full()}",
        parse_mode="HTML")

async def cmd_vote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await get_msg(update).reply_text(
        "🗳 <b>ПРОГОЛОСУЙ ЗА СЕРВЕР!</b>\n\n"
        "Голос помогает нам расти!\n\n"
        "🔗 <a href='https://minecraft-server-list.com/'>Minecraft Server List</a>\n"
        "🔗 <a href='https://minecraftservers.org/'>Minecraft Servers</a>\n\n"
        "🎁 За каждый голос — бонусы!",
        parse_mode="HTML", disable_web_page_preview=True)

async def cmd_seed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    seed = config.get("world_seed") or "Не установлено"
    await get_msg(update).reply_text(
        f"🌍 <b>СИД МИРА</b>\n\n<code>{seed}</code>\n\n<i>Используй для изучения карты!</i>",
        parse_mode="HTML")

async def cmd_shop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    link = config.get("shop_link") or "Не настроено"
    await get_msg(update).reply_text(
        f"🛒 <b>ДОНАТ-МАГАЗИН</b>\n\nПоддержи сервер и получи привилегии!\n\n"
        f"💎 VIP — цветной ник, /fly\n👑 PREMIUM — всё VIP + /god\n🏆 ELITE — всё + личный варп\n\n"
        f"🔗 {link}", parse_mode="HTML")

async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    top = config.get("top_players", [])
    if not top:
        return await get_msg(update).reply_text(
            "🏆 <b>ТОП ИГРОКОВ</b>\n\n<i>Статистика ещё не собрана.</i>", parse_mode="HTML")
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines = [f"{medals[i]} <b>{p['name']}</b> — {p.get('score','?')} очков" for i,p in enumerate(top[:10])]
    await get_msg(update).reply_text("🏆 <b>ТОП 10</b>\n\n" + "\n".join(lines), parse_mode="HTML")

async def cmd_motd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await update_server_info()
    await get_msg(update).reply_text(
        f"💬 <b>СООБЩЕНИЕ ДНЯ</b>\n\n{config.get('motd','Добро пожаловать!')}\n\n{icon(server_status)} {server_status.upper()}",
        parse_mode="HTML")

async def cmd_browser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update): return
    if not is_admin(update):
        return await get_msg(update).reply_text("🚫 Только для администраторов!", parse_mode="HTML")
    chat_id = update.effective_chat.id
    sess    = browser_sessions.get(chat_id, {})
    await get_msg(update).reply_text(
        f"🖥 <b>REMOTE BROWSER CONTROL</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{'🟢 Браузер активен' if sess.get('active') else '🔴 Браузер не запущен'}\n\n"
        f"<b>Как пользоваться:</b>\n"
        f"1. Нажми 🚀 Старт\n"
        f"2. Включи ⌨️ Ввод в браузер\n"
        f"3. Пиши текст → вводится на странице\n"
        f"4. <code>&lt;TAB&gt;</code> <code>&lt;ENTER&gt;</code> — спецклавиши\n"
        f"5. <code>&lt;CLICK:640,360&gt;</code> — клик по координатам\n"
        f"6. <code>AI: залогинься</code> — ИИ сделает сам\n\n"
        f"<b>Токены:</b>\n"
        f"<code>&lt;RCLICK:x,y&gt;</code> ПКМ\n"
        f"<code>&lt;DBLCLICK:x,y&gt;</code> двойной клик\n"
        f"<code>&lt;DRAG:x1,y1,x2,y2&gt;</code> перетащить\n"
        f"<code>&lt;SCROLL:down&gt;</code> скролл",
        reply_markup=browser_kb(chat_id), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════════════
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update): return
    if is_admin(update):
        return await show_admin(update)
    await update.message.reply_text("🔐 <b>Введи код доступа:</b>", parse_mode="HTML")
    return WAIT_CODE

async def got_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == ADMIN_CODE:
        admins.add(update.effective_user.id); save_all()
        await update.message.reply_text("✅ <b>Добро пожаловать, Администратор!</b>", parse_mode="HTML")
        await send_log(f"🔐 <b>НОВЫЙ АДМИН</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        await show_admin(update)
    else:
        await update.message.reply_text("❌ <b>Неверный код!</b>", parse_mode="HTML")
        await send_log(f"⚠️ Неудачная попытка\n👤 {ulabel(update)}")
    return ConversationHandler.END

async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pending_action.pop(update.effective_chat.id, None)
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

async def show_admin(update: Update):
    await update_server_info()
    m = config.get("maintenance", False)
    await get_msg(update).reply_text(
        f"⚙️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Aternos: {'✅ Подключён' if aternos_connected else '❌ Нет'}\n"
        f"{icon(server_status)} Сервер: <b>{server_status.upper()}</b>\n"
        f"👥 Игроков: <b>{len(current_players)}</b> | ⏱ {get_uptime()}\n"
        f"👤 Юзеров: <b>{len(users)}</b> | 🔐 Админов: <b>{len(admins)}</b>\n"
        f"⚠️ Варнов: <b>{sum(warns.values())}</b> | 🚫 Банов: <b>{len(banned)}</b>\n"
        f"🔧 ТехРаботы: <b>{'ВКЛ 🟡' if m else 'ВЫКЛ 🟢'}</b>",
        reply_markup=admin_kb(), parse_mode="HTML")

async def on_admin_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    d   = q.data
    cid = q.message.chat_id
    await q.answer()

    if d == "noop": return
    if d == "adm_back_to_admin":
        await show_admin(update); return
    if d.startswith("adm_") and not is_admin(update):
        await q.answer("🚫 Нет доступа!", show_alert=True); return

    # ── СЕРВЕР ───────────────────────────────────────────────
    if d == "adm_start":
        await q.message.edit_text("⏳ Запускаю...", parse_mode="HTML")
        await update_server_info()
        if server_status in ("online","starting"):
            return await q.message.edit_text("✅ Уже работает!", reply_markup=admin_kb(), parse_mode="HTML")
        ok = await aternos_start()
        if ok:
            stats["starts"] += 1; stats["last_start"] = datetime.now().isoformat()
            stats["uptime_from"] = datetime.now().isoformat(); save_all()
            await q.message.edit_text(f"🟢 <b>ЗАПУЩЕНО!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🟢 <b>ЗАПУСК (АДМИН)</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ Ошибка запуска!", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_stop":
        ok = await aternos_stop()
        if ok:
            stats["stops"] += 1; stats["last_stop"] = datetime.now().isoformat()
            stats["uptime_from"] = None; save_all()
            await q.message.edit_text(f"🔴 <b>ОСТАНОВЛЕНО!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔴 <b>СТОП</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ Ошибка!", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_restart":
        await q.message.edit_text("🔄 Перезапускаю...", parse_mode="HTML")
        await aternos_stop(); await asyncio.sleep(5)
        ok = await aternos_start()
        if ok:
            stats["restarts"] = stats.get("restarts",0)+1; stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat(); stats["uptime_from"] = datetime.now().isoformat(); save_all()
            await q.message.edit_text(f"🔄 <b>ПЕРЕЗАПУЩЕНО!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
        else:
            await q.message.edit_text("❌ Ошибка!", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_reconnect":
        await q.message.edit_text("⏳ Переподключаюсь...", parse_mode="HTML")
        ok = await aternos_login()
        await q.message.edit_text(
            f"{'✅ Подключено!' if ok else '❌ Не удалось'}",
            reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_aternos_status":
        data, code = await _api("status.php")
        txt = json.dumps(data, ensure_ascii=False, indent=2)[:600] if data else f"Код: {code}"
        await q.message.edit_text(f"📊 <b>СТАТУС</b>\n\n<code>{txt}</code>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_set_cookie":
        pending_action[cid] = "set_cookie"
        await q.message.reply_text(
            "🍪 <b>Ввод куков</b>\n\nJSON:\n<code>{\"ATERNOS_SESSION\":\"xxx\"}</code>\n\n"
            "или строкой:\n<code>ATERNOS_SESSION=xxx; ATERNOS_SEC=yyy</code>\n\n/cancel", parse_mode="HTML")

    elif d == "adm_diagnose":
        lines = [
            f"🔌 Aternos: {'✅' if aternos_connected else '❌'}",
            f"📡 Session: {'✅' if http_session and not http_session.closed else '❌'}",
            f"🍪 Куков: {len(login_cookies)}",
        ]
        for k in ["ATERNOS_SESSION","ATERNOS_SEC","PHPSESSID"]:
            v = login_cookies.get(k)
            lines.append(f"  {'✅' if v else '❌'} {k}: {'есть' if v else 'нет'}")
        if http_session and not http_session.closed:
            try:
                async with http_session.get("https://aternos.org/panel/ajax/status.php",
                    params={"server": SERVER_ID}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    lines.append(f"🌐 Тест: {r.status} {'✅' if r.status==200 else '❌'}")
            except Exception as e:
                lines.append(f"🌐 Тест: ❌ {str(e)[:50]}")
        await q.message.edit_text("🔍 <b>ДИАГНОСТИКА</b>\n\n" + "\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_browser":
        await cmd_browser(update, ctx)

    elif d == "adm_broadcast":
        pending_action[cid] = "broadcast"
        await q.message.reply_text("📢 Напиши сообщение для всех:\n/cancel", parse_mode="HTML")

    elif d == "adm_announce":
        pending_action[cid] = "announce"
        await q.message.reply_text("📣 Напиши текст анонса:\n/cancel", parse_mode="HTML")

    elif d == "adm_users":
        if not users:
            return await q.message.edit_text("👥 Нет пользователей", reply_markup=admin_kb(), parse_mode="HTML")
        lines = []
        for uid, info in list(users.items())[-15:]:
            n  = info.get("first_name","???")
            un = f"@{info['username']}" if info.get("username") else "—"
            w  = warns.get(uid, 0)
            ma = "🔐" if int(uid) in admins else ""
            ba = "🚫" if int(uid) in banned else ""
            lines.append(f"• {n} {un}{ma}{ba}{' ⚠️'+str(w) if w else ''}")
        await q.message.edit_text(f"👥 <b>ЮЗЕРЫ ({len(users)})</b>\n\n" + "\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_warns":
        if not warns:
            return await q.message.edit_text("⚠️ Варнов нет", reply_markup=admin_kb(), parse_mode="HTML")
        lines = [f"• {users.get(uid,{}).get('first_name','???')} — ⚠️{cnt}/3" for uid,cnt in warns.items()]
        await q.message.edit_text("⚠️ <b>ВАРНЫ</b>\n\n" + "\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_warn_give":
        pending_action[cid] = "warn"
        await q.message.reply_text("⚠️ Напиши @username:\n/cancel", parse_mode="HTML")

    elif d == "adm_ban":
        pending_action[cid] = "ban"
        await q.message.reply_text("🚫 Напиши @username:\n/cancel", parse_mode="HTML")

    elif d == "adm_maintenance":
        config["maintenance"] = not config.get("maintenance", False); save_all()
        w = "ВКЛ 🟡" if config["maintenance"] else "ВЫКЛ 🟢"
        await q.message.edit_text(f"🔧 ТехРаботы {w}", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_toggle_start":
        config["allow_all_start"] = not config.get("allow_all_start", True); save_all()
        await q.message.edit_text(
            f"⚙️ Запуск: {'Все ✅' if config['allow_all_start'] else 'Только Адм 🔐'}",
            reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_setmotd":
        pending_action[cid] = "setmotd"
        await q.message.reply_text("✏️ Напиши новый MOTD:\n/cancel", parse_mode="HTML")

    elif d == "adm_setseed":
        pending_action[cid] = "setseed"
        await q.message.reply_text("🌍 Напиши сид мира:\n/cancel", parse_mode="HTML")

    elif d == "adm_setshop":
        pending_action[cid] = "setshop"
        await q.message.reply_text("🛒 Напиши ссылку на магазин:\n/cancel", parse_mode="HTML")

    elif d == "adm_notes":
        pending_action[cid] = "note"
        txt = "\n".join(f"{i+1}. {n}" for i,n in enumerate(notes[-10:])) if notes else "(пусто)"
        await q.message.reply_text(f"📝 <b>ЗАМЕТКИ</b>\n\n{txt}\n\nНапиши новую:\n/cancel", parse_mode="HTML")

    elif d == "adm_stats":
        await update_server_info()
        ls = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "—"
        await q.message.edit_text(
            f"📊 <b>ПОЛНАЯ СТАТИСТИКА</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 {stats['starts']} | 🛑 {stats['stops']} | 🔄 {stats.get('restarts',0)}\n"
            f"👑 Рекорд: {stats['peak_players']} | 💬 Команд: {stats.get('total_commands',0)}\n"
            f"👤 Юзеров: {len(users)} | 🔐 Админов: {len(admins)}\n"
            f"⚠️ Варнов: {sum(warns.values())} | 🚫 Банов: {len(banned)}\n"
            f"▶️ {ls} | ⏰ {now_full()}",
            reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_resetstats":
        stats.update({"starts":0,"stops":0,"restarts":0,"last_start":None,
                      "last_stop":None,"uptime_from":None,"peak_players":0,"total_commands":0})
        save_all()
        await q.message.edit_text("🗑 Статистика сброшена!", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_setlog":
        config["log_chat_id"] = cid; save_all()
        await q.message.edit_text(f"✅ Логи здесь!\nID: <code>{cid}</code>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_exit":
        await q.message.edit_text("👋 Панель закрыта.", parse_mode="HTML")

    # ── WATCH HANDLERS ───────────────────────────────────────────
    elif d == "wt_toggle":
        sess = watch_sessions.get(cid, {})
        t    = sess.get("task")
        if t and not t.done():
            t.cancel()
            watch_sessions[cid]["task"] = None
            await q.message.edit_text("🛑 Watch остановлен.", reply_markup=watch_kb(cid), parse_mode="HTML")
        else:
            if cid not in watch_sessions:
                watch_sessions[cid] = {"interval":20,"auto_login":True,
                    "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"}
            new_task = asyncio.create_task(_watch_loop(cid))
            watch_sessions[cid]["task"] = new_task
            await q.message.edit_text("▶️ <b>Watch запущен!</b>", reply_markup=watch_kb(cid), parse_mode="HTML")

    elif d == "wt_snap":
        await q.answer("📸 Делаю снимок...")
        if cid not in watch_sessions:
            watch_sessions[cid] = {"interval":20,"auto_login":True,
                "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"}
        asyncio.create_task(_watch_snap(cid, "ручной"))

    elif d.startswith("wt_spd_") and d != "wt_spd_custom":
        spd = int(d.split("_")[-1])
        if cid not in watch_sessions: watch_sessions[cid] = {"interval":spd,"auto_login":True,"url":"https://aternos.org/go/"}
        else: watch_sessions[cid]["interval"] = spd
        await q.message.edit_text(f"⚡ Скорость: <b>{spd}с</b>", reply_markup=watch_kb(cid), parse_mode="HTML")

    elif d == "wt_spd_custom":
        pending_action[cid] = "wt_speed"
        await q.message.reply_text("✏️ Введи интервал в секундах (5–300):\n/cancel", parse_mode="HTML")

    elif d == "wt_toggle_auth":
        if cid not in watch_sessions: watch_sessions[cid] = {"interval":20,"auto_login":True,"url":"https://aternos.org/go/"}
        watch_sessions[cid]["auto_login"] = not watch_sessions[cid].get("auto_login", True)
        await q.message.edit_text(
            f"🔑 Режим: {'🤖 Авто' if watch_sessions[cid]['auto_login'] else '✋ Вручную'}",
            reply_markup=watch_kb(cid), parse_mode="HTML")

    elif d == "wt_set_user":
        pending_action[cid] = "wt_user"
        await q.message.reply_text("👤 Введи логин для Watch:\n/cancel", parse_mode="HTML")

    elif d == "wt_set_pass":
        pending_action[cid] = "wt_pass"
        await q.message.reply_text("🔐 Введи пароль для Watch:\n/cancel", parse_mode="HTML")

    elif d == "wt_set_url":
        pending_action[cid] = "wt_url"
        await q.message.reply_text(
            "🔗 Введи URL:\n• <code>https://aternos.org/go/</code>\n• <code>https://aternos.org/server/</code>\n/cancel",
            parse_mode="HTML")

    elif d in ("wt_nav_home","wt_nav_login","wt_nav_server"):
        urls = {"wt_nav_home":"https://aternos.org/","wt_nav_login":"https://aternos.org/go/",
                "wt_nav_server": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/servers/"}
        if cid not in watch_sessions: watch_sessions[cid] = {"interval":20,"auto_login":True}
        watch_sessions[cid]["url"] = urls[d]
        await q.answer(f"URL: {urls[d][:40]}")
        asyncio.create_task(_watch_snap(cid, "навигация"))

    # ═══════════════════════════════════════════════════════════════
    # BROWSER CONTROL BUTTONS
    # ═══════════════════════════════════════════════════════════════
    elif d == "bc_start":
        await q.message.edit_text("🚀 <b>Запускаю браузер...</b>", parse_mode="HTML")
        result = await bc_start(cid)
        if result is True:
            await bc_screenshot(cid, f"🟢 Браузер запущен! {now_str()}")
            await q.message.edit_text("🟢 <b>Браузер активен!</b>", reply_markup=browser_kb(cid), parse_mode="HTML")
        else:
            await q.message.edit_text(f"❌ Ошибка:\n<code>{esc(str(result)[:200])}</code>", reply_markup=browser_kb(cid), parse_mode="HTML")

    elif d == "bc_restart":
        await q.message.edit_text("🔄 Перезапускаю...", parse_mode="HTML")
        result = await bc_start(cid)
        if result is True:
            await bc_screenshot(cid, f"🔄 Перезапущен! {now_str()}")
        await q.message.edit_text(
            "🔄 Готово!" if result is True else f"❌ <code>{esc(str(result)[:100])}</code>",
            reply_markup=browser_kb(cid), parse_mode="HTML")

    elif d == "bc_close":
        await bc_close(cid)
        await q.message.edit_text("🛑 Браузер закрыт.", reply_markup=browser_kb(cid), parse_mode="HTML")

    elif d.startswith("bck_"):  # клавиши
        key_map = {"cA":"Control+a","cC":"Control+c","cV":"Control+v","cZ":"Control+z"}
        raw = d[4:]
        key = key_map.get(raw, raw)
        page = await bc_get_page(cid)
        if not page: await q.answer("❌ Браузер не запущен!", show_alert=True); return
        await page.keyboard.press(key)
        await asyncio.sleep(0.3)
        await bc_screenshot(cid, f"⌨️ {key}")

    elif d.startswith("bcm_"):  # мышь
        page = await bc_get_page(cid)
        if not page: await q.answer("❌ Браузер не запущен!", show_alert=True); return
        if d in ("bcm_sd","bcm_su","bcm_sr"):
            js = {"bcm_sd":"window.scrollBy(0,400)","bcm_su":"window.scrollBy(0,-400)","bcm_sr":"window.scrollBy(400,0)"}[d]
            await page.evaluate(js); await asyncio.sleep(0.3)
            await bc_screenshot(cid, f"📜 {'↓' if 'sd' in d else '↑' if 'su' in d else '→'}")
        elif d in ("bcm_lmb","bcm_rmb","bcm_dbl","bcm_hover","bcm_drag"):
            labels = {"bcm_lmb":"bc_click","bcm_rmb":"bc_rclick","bcm_dbl":"bc_dblclick",
                      "bcm_hover":"bc_hover","bcm_drag":"bc_drag"}
            pending_action[cid] = labels[d]
            hints = {"bc_click":"x,y","bc_rclick":"x,y","bc_dblclick":"x,y","bc_hover":"x,y","bc_drag":"x1,y1,x2,y2"}
            await q.message.reply_text(
                f"🖱 Введи координаты (<code>{hints[labels[d]]}</code>):\n/cancel", parse_mode="HTML")

    elif d.startswith("bcn_"):  # навигация
        page = await bc_get_page(cid)
        if not page: await q.answer("❌ Браузер не запущен!", show_alert=True); return
        nav = {"bcn_home":"https://aternos.org/",
               "bcn_login":"https://aternos.org/go/",
               "bcn_server": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/servers/"}
        if d == "bcn_url":
            pending_action[cid] = "bc_goto_url"
            await q.message.reply_text("✏️ Введи URL:\n/cancel", parse_mode="HTML"); return
        elif d == "bcn_back": await page.go_back(timeout=10000)
        elif d == "bcn_fwd":  await page.go_forward(timeout=10000)
        elif d == "bcn_reload": await page.reload(wait_until="domcontentloaded", timeout=15000)
        elif d in nav: await page.goto(nav[d], wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(1); await bc_screenshot(cid)

    elif d.startswith("bct_"):  # инструменты
        page = await bc_get_page(cid)
        if d != "bct_input" and not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return

        if d == "bct_snap":
            await bc_screenshot(cid)
            await q.message.edit_text("📸 Отправлено!", reply_markup=browser_kb(cid), parse_mode="HTML")

        elif d == "bct_snapfull":
            await bc_screenshot(cid, full_page=True)
            await q.message.edit_text("🖼 Полный скрин отправлен!", reply_markup=browser_kb(cid), parse_mode="HTML")

        elif d == "bct_info":
            info = await page.evaluate("""()=>({
                title:    document.title,
                url:      location.href,
                elements: document.querySelectorAll('*').length,
                images:   document.images.length,
                links:    document.links.length,
                inputs:   document.querySelectorAll('input,textarea,select').length,
                size:     document.documentElement.innerHTML.length,
                w:        window.innerWidth, h: window.innerHeight,
            })""")
            await q.message.reply_text(
                f"📊 <b>ИНФО СТРАНИЦЫ</b>\n"
                f"📄 {esc(info['title'][:40])}\n🔗 <code>{esc(info['url'][:60])}</code>\n\n"
                f"🔢 Элементов: <b>{info['elements']}</b> | 🖼 Картинок: <b>{info['images']}</b>\n"
                f"🔗 Ссылок: <b>{info['links']}</b> | ⌨️ Полей: <b>{info['inputs']}</b>\n"
                f"📦 HTML: <b>{info['size']//1024} КБ</b> | 📐 {info['w']}×{info['h']}",
                parse_mode="HTML")

        elif d == "bct_find":
            pending_action[cid] = "bc_find"
            await q.message.reply_text("🔎 Введи текст для поиска:\n/cancel", parse_mode="HTML")

        elif d == "bct_copytext":
            txt = await page.evaluate("()=>document.body.innerText.slice(0,3000)")
            await q.message.reply_text(f"📋 <b>Текст страницы:</b>\n\n<code>{esc(txt[:2000])}</code>", parse_mode="HTML")

        elif d == "bct_clicktext":
            pending_action[cid] = "bc_click_by_text"
            await q.message.reply_text("🎯 Введи текст кнопки/ссылки:\n/cancel", parse_mode="HTML")

        elif d == "bct_fillform":
            u_inp = await page.query_selector("input[name='user']")
            p_inp = await page.query_selector("input[name='password']")
            if u_inp and p_inp:
                sess_w = {}  # не используем watch_sessions
                wu = ATERNOS_USER; wp = ATERNOS_PASS
                if wu: await u_inp.click(click_count=3); await page.type("input[name='user']", wu, delay=60)
                if wp: await p_inp.click(click_count=3); await page.type("input[name='password']", wp, delay=60)
                await asyncio.sleep(0.3); await bc_screenshot(cid, "📝 Форма заполнена!")
            else:
                await q.answer("Форма логина не найдена!", show_alert=True)

        elif d == "bct_clearcookies":
            sess2 = browser_sessions.get(cid)
            if sess2 and sess2.get("ctx"):
                await sess2["ctx"].clear_cookies(); login_cookies.clear()
                await q.message.edit_text("🧹 Куки очищены!", reply_markup=browser_kb(cid), parse_mode="HTML")

        elif d == "bct_dark":
            await page.evaluate("""()=>{
                const id='tg-dark';const ex=document.getElementById(id);
                if(ex){ex.remove();return;}
                const s=document.createElement('style');s.id=id;
                s.textContent='*{background-color:#1a1a2e!important;color:#e0e0e0!important}a{color:#7eb8f7!important}';
                document.head.appendChild(s);
            }""")
            await asyncio.sleep(0.3); await bc_screenshot(cid, "🌙 Dark mode")
            await q.message.edit_text("🌙 Dark mode переключён!", reply_markup=browser_kb(cid), parse_mode="HTML")

        elif d == "bct_mobile":
            sess3 = browser_sessions.get(cid, {})
            mobile = not sess3.get("mobile", False)
            browser_sessions[cid]["mobile"] = mobile
            vp = {"width":390,"height":844} if mobile else {"width":1280,"height":720}
            await page.set_viewport_size(vp)
            await page.reload(wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1); await bc_screenshot(cid, f"{'📱 Мобильный' if mobile else '🖥 Десктоп'}")
            await q.message.edit_text(
                f"{'📱 Мобильный (390×844)' if mobile else '🖥 Десктоп (1280×720)'}",
                reply_markup=browser_kb(cid), parse_mode="HTML")

        elif d == "bct_zin":
            await page.evaluate("document.body.style.zoom=(parseFloat(document.body.style.zoom||'1')+0.25).toString()")
            await asyncio.sleep(0.2); await bc_screenshot(cid, "🔍+ Zoom in")

        elif d == "bct_zout":
            await page.evaluate("document.body.style.zoom=Math.max(0.25,parseFloat(document.body.style.zoom||'1')-0.25).toString()")
            await asyncio.sleep(0.2); await bc_screenshot(cid, "🔍- Zoom out")

        elif d == "bct_input":
            if cid in browser_control_mode:
                browser_control_mode.discard(cid)
                await q.message.edit_text("⌨️ Режим ввода: 🔴 ВЫКЛ", reply_markup=browser_kb(cid), parse_mode="HTML")
            else:
                if not browser_sessions.get(cid, {}).get("active"):
                    await q.answer("Сначала запусти браузер!", show_alert=True); return
                browser_control_mode.add(cid)
                await q.message.edit_text(
                    "⌨️ Режим ввода: 🟢 ВКЛ\n\nПиши в чат — всё идёт в браузер.\n"
                    "<code>&lt;TAB&gt;</code> <code>&lt;ENTER&gt;</code> <code>&lt;ESC&gt;</code> — клавиши\n"
                    "<code>&lt;CLICK:x,y&gt;</code> — клик\n<code>AI: задача</code> — ИИ",
                    reply_markup=browser_kb(cid), parse_mode="HTML")

        elif d == "bct_autosnap":
            sess4 = browser_sessions.get(cid, {})
            task  = sess4.get("snaptask")
            if task and not task.done():
                task.cancel(); browser_sessions[cid]["snaptask"] = None
                await q.message.edit_text("⏱ Авто-снап остановлен.", reply_markup=browser_kb(cid), parse_mode="HTML")
            else:
                if not sess4.get("active"): await q.answer("Запусти браузер!", show_alert=True); return
                pending_action[cid] = "bc_autosnap_interval"
                await q.message.reply_text("⏱ Введи интервал в секундах (10–300):\n/cancel", parse_mode="HTML")

    elif d.startswith("bca_"):  # ИИ
        if d == "bca_login":
            asyncio.create_task(bc_ai(cid,
                f"Залогинься на aternos.org. Логин: {ATERNOS_USER}, Пароль: {ATERNOS_PASS}. "
                f"Открой https://aternos.org/go/, введи данные, нажми Login."))
        elif d == "bca_custom":
            pending_action[cid] = "bc_ai"
            await q.message.reply_text(
                "🤖 Что сделать ИИ?\n\nПримеры:\n• залогинься\n• запусти сервер\n• сделай скрин консоли\n/cancel",
                parse_mode="HTML")

async def on_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    fns = {"on":cmd_on,"players":cmd_players,"status":cmd_status,"info":cmd_info,
           "connect":cmd_connect,"rules":cmd_rules,"random":cmd_random,"top":cmd_top,
           "seed":cmd_seed,"vote":cmd_vote,"shop":cmd_shop,"uptime":cmd_uptime,"motd":cmd_motd}
    fn = fns.get(q.data)
    if fn: await fn(update, ctx)

# ═══════════════════════════════════════════════════════════════
# ОБРАБОТКА ТЕКСТА
# ═══════════════════════════════════════════════════════════════
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update): return
    cid    = update.effective_chat.id
    text   = update.message.text.strip()
    action = pending_action.get(cid)

    if text == "/cancel":
        pending_action.pop(cid, None)
        browser_control_mode.discard(cid)
        await update.message.reply_text("❌ Отменено."); return

    # Режим ввода в браузер
    if cid in browser_control_mode:
        await handle_browser_input(update, text); return

    if not action or not is_admin(update): return
    pending_action.pop(cid, None)

    # Adminские действия
    if action == "broadcast":
        msg_text = f"📢 <b>ОБЪЯВЛЕНИЕ — {config['server_name']}</b>\n\n{text}\n\n<i>— Администрация</i>"
        sm = await update.message.reply_text("⏳ Отправляю...", parse_mode="HTML")
        sent = fail = 0
        for uid in list(users.keys()):
            if int(uid) not in banned:
                try: await telegram_app.bot.send_message(int(uid), msg_text, parse_mode="HTML"); sent += 1
                except: fail += 1
                await asyncio.sleep(0.05)
        await sm.edit_text(f"📢 Готово! ✅{sent} ❌{fail}", parse_mode="HTML")

    elif action == "announce":
        msg_text = f"📣 <b>━━━━━━━━━━━━━━━━━━━━━━</b>\n🎮 <b>{config['server_name'].upper()}</b>\n\n{text}\n<b>━━━━━━━━━━━━━━━━━━━━━━</b>"
        sm = await update.message.reply_text("⏳...", parse_mode="HTML")
        sent = fail = 0
        for uid in list(users.keys()):
            if int(uid) not in banned:
                try: await telegram_app.bot.send_message(int(uid), msg_text, parse_mode="HTML"); sent += 1
                except: fail += 1
                await asyncio.sleep(0.05)
        await sm.edit_text(f"📣 Анонс отправлен! ✅{sent} ❌{fail}", parse_mode="HTML")

    elif action == "setmotd":
        config["motd"] = text; save_all()
        await update.message.reply_text(f"✅ MOTD обновлён!\n\n{text}", parse_mode="HTML")

    elif action == "setseed":
        config["world_seed"] = text; save_all()
        await update.message.reply_text(f"✅ Сид: <code>{text}</code>", parse_mode="HTML")

    elif action == "setshop":
        config["shop_link"] = text; save_all()
        await update.message.reply_text(f"✅ Магазин: {text}", parse_mode="HTML")

    elif action == "note":
        notes.append(f"[{now_str()}] {text}"); save_all()
        await update.message.reply_text("📝 Заметка сохранена!", parse_mode="HTML")

    elif action == "warn":
        target = text.lstrip("@")
        uid = next((u for u,i in users.items() if i.get("username","").lower()==target.lower()), None)
        if not uid:
            return await update.message.reply_text(f"❌ @{target} не найден!", parse_mode="HTML")
        warns[uid] = warns.get(uid,0)+1; save_all()
        await update.message.reply_text(f"⚠️ Варн выдан!\n👤 @{target}\n⚠️ {warns[uid]}/3", parse_mode="HTML")

    elif action == "ban":
        target = text.lstrip("@")
        uid = next((u for u,i in users.items() if i.get("username","").lower()==target.lower()), None)
        if not uid:
            return await update.message.reply_text(f"❌ @{target} не найден!", parse_mode="HTML")
        banned.add(int(uid)); save_all()
        await update.message.reply_text(f"🚫 ЗАБАНЕН!\n👤 @{target}", parse_mode="HTML")

    elif action == "wt_speed":
        try:
            spd = max(5, min(300, int(text)))
        except:
            return await update.message.reply_text("❌ Введи число 5–300", parse_mode="HTML")
        if cid not in watch_sessions: watch_sessions[cid] = {"interval":spd,"auto_login":True,"url":"https://aternos.org/go/"}
        else: watch_sessions[cid]["interval"] = spd
        await update.message.reply_text(f"⚡ Скорость: <b>{spd}с</b>", parse_mode="HTML")

    elif action == "wt_user":
        if cid not in watch_sessions: watch_sessions[cid] = {"interval":20,"auto_login":False,"url":"https://aternos.org/go/"}
        watch_sessions[cid]["w_user"] = text
        watch_sessions[cid]["auto_login"] = False
        await update.message.reply_text(f"✅ Логин Watch: <code>{esc(text)}</code>", parse_mode="HTML")

    elif action == "wt_pass":
        if cid not in watch_sessions: watch_sessions[cid] = {"interval":20,"auto_login":False,"url":"https://aternos.org/go/"}
        watch_sessions[cid]["w_pass"] = text
        watch_sessions[cid]["auto_login"] = False
        await update.message.reply_text(f"✅ Пароль Watch сохранён.", parse_mode="HTML")

    elif action == "wt_url":
        url = text if text.startswith("http") else "https://" + text
        if cid not in watch_sessions: watch_sessions[cid] = {"interval":20,"auto_login":True}
        watch_sessions[cid]["url"] = url
        await update.message.reply_text(f"✅ URL: <code>{esc(url)}</code>", parse_mode="HTML")

    elif action == "set_cookie":
        global http_session, aternos_connected
        new_c = {}
        if text.strip().startswith("{"):
            try: new_c = json.loads(text.strip())
            except Exception as e:
                return await update.message.reply_text(f"❌ JSON ошибка: {e}", parse_mode="HTML")
        else:
            for part in text.strip().split(";"):
                if "=" in part:
                    k,v = part.strip().split("=",1)
                    new_c[k.strip()] = v.strip()
        if not new_c:
            return await update.message.reply_text("❌ Не удалось распарсить куки!", parse_mode="HTML")
        login_cookies.update(new_c)
        jar = aiohttp.CookieJar()
        for name,val in login_cookies.items():
            jar.update_cookies({name:val}, response_url=yarl_URL("https://aternos.org/"))
        if http_session and not http_session.closed: await http_session.close()
        http_session = aiohttp.ClientSession(cookie_jar=jar, headers={
            "User-Agent":"Mozilla/5.0","X-Requested-With":"XMLHttpRequest"})
        aternos_connected = True
        found = [k for k in ["ATERNOS_SESSION","ATERNOS_SEC","PHPSESSID"] if k in login_cookies]
        await update.message.reply_text(
            f"✅ Куки установлены!\n🍪 Всего: {len(login_cookies)}\n✅ Важные: {', '.join(found) or 'не найдены!'}",
            parse_mode="HTML")

    # Browser actions
    elif action == "bc_goto_url":
        page = await bc_get_page(cid)
        if not page: return await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML")
        url = text if text.startswith("http") else "https://" + text
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(1); await bc_screenshot(cid, f"🔗 {url[:50]}")

    elif action in ("bc_click","bc_rclick","bc_dblclick","bc_hover"):
        page = await bc_get_page(cid)
        if not page: return await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML")
        try:
            x,y = [int(v.strip()) for v in text.split(",")]
            if   action == "bc_click":   await page.mouse.click(x,y)
            elif action == "bc_rclick":  await page.mouse.click(x,y, button="right")
            elif action == "bc_dblclick":await page.mouse.dblclick(x,y)
            elif action == "bc_hover":   await page.mouse.move(x,y)
            await asyncio.sleep(0.4)
            await bc_screenshot(cid, f"🖱 {action.replace('bc_','')}({x},{y})")
        except Exception as e:
            await update.message.reply_text(f"❌ Формат: x,y\n{e}", parse_mode="HTML")

    elif action == "bc_drag":
        page = await bc_get_page(cid)
        if not page: return await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML")
        try:
            x1,y1,x2,y2 = [int(v.strip()) for v in text.split(",")]
            await page.mouse.move(x1,y1); await page.mouse.down()
            for i in range(1,11):
                await page.mouse.move(x1+(x2-x1)*i//10, y1+(y2-y1)*i//10)
                await asyncio.sleep(0.02)
            await page.mouse.up(); await asyncio.sleep(0.4)
            await bc_screenshot(cid, f"↕ drag({x1},{y1}→{x2},{y2})")
        except Exception as e:
            await update.message.reply_text(f"❌ Формат: x1,y1,x2,y2\n{e}", parse_mode="HTML")

    elif action == "bc_find":
        page = await bc_get_page(cid)
        if not page: return await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML")
        results = await page.evaluate(f"""(q)=>{{
            const r=[];const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
            let n;while(n=w.nextNode()){{if(n.textContent.toLowerCase().includes(q.toLowerCase()))
                r.push(n.parentElement?.tagName+': '+n.textContent.trim().slice(0,60));}}
            return r.slice(0,10);
        }}""", text)
        if results:
            lines = "\n".join(f"• <code>{esc(r)}</code>" for r in results)
            await update.message.reply_text(f"🔎 <b>«{text}»: {len(results)} раз</b>\n\n{lines}", parse_mode="HTML")
            await bc_screenshot(cid, f"🔎 «{text[:30]}»")
        else:
            await update.message.reply_text(f"🔎 «{text}» — не найдено", parse_mode="HTML")

    elif action == "bc_click_by_text":
        page = await bc_get_page(cid)
        if not page: return await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML")
        clicked = await page.evaluate(f"""(txt)=>{{
            const els=[...document.querySelectorAll('button,a,input[type=submit],[role=button]')];
            const el=els.find(e=>e.innerText?.trim().toLowerCase().includes(txt.toLowerCase())||e.value?.toLowerCase().includes(txt.toLowerCase()));
            if(el){{el.scrollIntoView({{block:'center'}});el.click();return el.tagName+': '+el.innerText?.trim().slice(0,30);}}
            return null;
        }}""", text)
        if clicked:
            await asyncio.sleep(0.8); await bc_screenshot(cid, f"🎯 Клик: «{text}» → {clicked}")
        else:
            await update.message.reply_text(f"🎯 «{text}» — элемент не найден", parse_mode="HTML")

    elif action == "bc_ai":
        asyncio.create_task(bc_ai(cid, text))

    elif action == "bc_autosnap_interval":
        try: interval = max(10, min(300, int(text)))
        except: return await update.message.reply_text("❌ Введи число 10–300", parse_mode="HTML")
        if cid not in browser_sessions:
            return await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML")
        browser_sessions[cid]["snap_interval"] = interval
        task = asyncio.create_task(_snap_loop(cid))
        browser_sessions[cid]["snaptask"] = task
        await update.message.reply_text(f"⏱ Авто-снап запущен! Каждые {interval}с\nОстановить: /browser → ⏱", parse_mode="HTML")

async def handle_browser_input(update: Update, text: str):
    """Обрабатывает ввод в режиме браузера."""
    cid  = update.effective_chat.id
    page = await bc_get_page(cid)
    if not page:
        browser_control_mode.discard(cid)
        await update.message.reply_text("❌ Браузер не запущен! Режим ввода выключен.", parse_mode="HTML")
        return
    # AI режим
    if text.upper().startswith("AI:"):
        asyncio.create_task(bc_ai(cid, text[3:].strip())); return
    try:
        tokens = re.split(r'(<[^>]+>)', text)
        done   = []
        for tok in tokens:
            if not tok: continue
            up = tok.upper()
            if up in SPECIAL_KEYS:
                await page.keyboard.press(SPECIAL_KEYS[up]); done.append(f"⌨️{tok}"); await asyncio.sleep(0.1)
            elif up.startswith("<CLICK:"):
                x,y=[int(v.strip()) for v in tok[7:-1].split(",")]; await page.mouse.click(x,y); done.append(f"🖱LKM({x},{y})"); await asyncio.sleep(0.2)
            elif up.startswith("<RCLICK:"):
                x,y=[int(v.strip()) for v in tok[8:-1].split(",")]; await page.mouse.click(x,y,button="right"); done.append(f"🖱PKM({x},{y})"); await asyncio.sleep(0.2)
            elif up.startswith("<DBLCLICK:"):
                x,y=[int(v.strip()) for v in tok[10:-1].split(",")]; await page.mouse.dblclick(x,y); done.append(f"🖱2×({x},{y})"); await asyncio.sleep(0.2)
            elif up.startswith("<HOVER:"):
                x,y=[int(v.strip()) for v in tok[7:-1].split(",")]; await page.mouse.move(x,y); done.append(f"🔍({x},{y})")
            elif up.startswith("<DRAG:"):
                x1,y1,x2,y2=[int(v.strip()) for v in tok[6:-1].split(",")]
                await page.mouse.move(x1,y1); await page.mouse.down()
                for i in range(1,11): await page.mouse.move(x1+(x2-x1)*i//10, y1+(y2-y1)*i//10); await asyncio.sleep(0.02)
                await page.mouse.up(); done.append(f"↕drag")
            elif up.startswith("<SCROLL:"):
                val=tok[8:-1].strip().lower(); dy=-400 if val=="up" else (400 if val=="down" else int(val))
                await page.evaluate(f"window.scrollBy(0,{dy})"); done.append(f"📜{dy:+d}")
            elif up.startswith("<WAIT:"):
                ms=int(tok[6:-1].strip()); await asyncio.sleep(min(ms,10000)/1000); done.append(f"⏱{ms}ms")
            elif not tok.startswith("<"):
                await page.keyboard.type(tok, delay=50); done.append(f"✍️«{tok[:15]}»")
        await asyncio.sleep(0.3)
        await bc_screenshot(cid, "  ".join(done) or "✍️ введено")
    except Exception as e:
        await update.message.reply_text(f"❌ <code>{esc(str(e)[:200])}</code>", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════
# ФОНОВЫЕ ЗАДАЧИ
# ═══════════════════════════════════════════════════════════════
async def _bg_login():
    await asyncio.sleep(3)
    ok = await aternos_login()
    msg = "✅ <b>Aternos подключён!</b>" if ok else "❌ <b>Aternos не подключён.</b>\nИспользуй /admin → 🍪 или 🔄"
    await send_log(msg)

async def _auto_report():
    await asyncio.sleep(60)
    while True:
        await asyncio.sleep(600)
        if not aternos_connected: continue
        await update_server_info()
        if server_status != "online": continue
        pl = "\n".join(f"  • {p}" for p in current_players) if current_players else "  (никого)"
        await send_log(f"🟢 <b>АВТО-ОТЧЁТ</b>\n⏰ {now_full()}\n⏱ {get_uptime()}\n👥 ({len(current_players)}):\n{pl}")

# ═══════════════════════════════════════════════════════════════
# FLASK
# ═══════════════════════════════════════════════════════════════
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return jsonify({"v":"19.0","server":server_status,"players":len(current_players),"aternos":aternos_connected}), 200

@flask_app.route("/ping")
def ping():
    return "pong", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
async def main():
    global telegram_app
    load_all()
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
        ("random",cmd_random),("uptime",cmd_uptime),("vote",cmd_vote),("seed",cmd_seed),
        ("shop",cmd_shop),("top",cmd_top),("motd",cmd_motd),("browser",cmd_browser),("watch",cmd_watch),
    ]:
        telegram_app.add_handler(CommandHandler(cmd, fn))

    telegram_app.add_handler(CallbackQueryHandler(on_admin_btn, pattern="^(adm_|bc_|bck_|bcm_|bcn_|bct_|bca_|wt_|noop)"))
    telegram_app.add_handler(CallbackQueryHandler(on_btn))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("✅ ATERNOS BOT v19.0 ULTRA PRO MAX — ГОТОВ!")
    asyncio.create_task(_bg_login())
    asyncio.create_task(_auto_report())

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    await asyncio.Event().wait()

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Остановлен")
    except Exception as e:
        log.error(f"❌ FATAL: {e}", exc_info=True)
        sys.exit(1)
