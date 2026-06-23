#!/usr/bin/env python3
"""ATERNOS TELEGRAM BOT v18.0 — fictionmine (RU + Features + Fixes)"""

import os, sys, json, asyncio, logging, random, hashlib, time
from datetime import datetime, timedelta
from threading import Thread
from yarl import URL as yarl_URL

from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters, ConversationHandler
)
from telegram.constants import ChatAction
import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", stream=sys.stdout)
log = logging.getLogger("bot")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN","")
ATERNOS_USER   = os.getenv("ATERNOS_USER","")
ATERNOS_PASS   = os.getenv("ATERNOS_PASS","")
SERVER_ID      = os.getenv("SERVER_ID","")
LOG_CHAT_ID    = int(os.getenv("LOG_CHAT_ID","0"))
PORT           = int(os.getenv("PORT","8000"))
ADMIN_CODE     = os.getenv("ADMIN_CODE","2011")

if not TELEGRAM_TOKEN: log.error("❌ TELEGRAM_TOKEN!"); sys.exit(1)

log.info("="*60); log.info("🎮 ATERNOS BOT v18.0 — fictionmine"); log.info("="*60)

STATS_FILE="stats.json"; CONFIG_FILE="config.json"; ADMINS_FILE="admins.json"
USERS_FILE="users.json"; WARNS_FILE="warns.json"; NOTES_FILE="notes.json"; BANNED_FILE="banned.json"

stats  = {"starts":0,"stops":0,"restarts":0,"last_start":None,"last_stop":None,"uptime_from":None,"peak_players":0,"total_commands":0,"total_hours":0}
config = {"log_chat_id":LOG_CHAT_ID,"maintenance":False,"server_name":"fictionmine","server_ip":"fictionmine.aternos.me","server_port":"19132","motd":"Добро пожаловать на fictionmine! ⛏️","allow_all_start":True,"world_seed":"","shop_link":"","top_players":[],"lang":"ru","backup_time":"02:00"}
admins:set=set(); users:dict={}; warns:dict={}; notes:list=[]; banned:set=set()

telegram_app=None; http_session=None; aternos_connected=False; last_login_time=0
server_status="offline"; current_players=[]; login_cookies={}

WAIT_CODE=1; WAIT_BROADCAST=2; WAIT_ANNOUNCE=3; WAIT_MOTD=4; WAIT_SEED=5; WAIT_SHOP=6; WAIT_NOTE=7; WAIT_WARN=8
WAIT_COOKIE=9; WAIT_WATCH_URL=10; WAIT_WATCH_USER=11; WAIT_WATCH_PASS=12; WAIT_WATCH_SPEED=13; WAIT_WATCH_NAV=14

# watch_sessions: chat_id -> {url, interval, task, auto_login, w_user, w_pass}
watch_sessions: dict = {}

# browser_sessions: chat_id -> {browser, context, page, pw_instance, active(bool)}
# Браузер живе в пам'яті між командами — не закривається після кожної дії
browser_sessions: dict = {}

# Режим керування: якщо True — текст з чату іде в браузер, а не боту
browser_control_mode: set = set()  # chat_id's у режимі контролю

# ══════════════════════════════════════════════════════════════════
# ЛОКАЛІЗАЦІЯ (РУ)
# ══════════════════════════════════════════════════════════════════

T = {
    "start_title": "⛏️ <b>FictionMine — Minecraft Bedrock</b>",
    "status": "Статус",
    "players_online": "игроков онлайн",
    "server_disabled": "Сервер отключен",
    "ip": "IP",
    "port": "Порт",
    "uptime": "Аптайм",
    "welcome": "Добро пожаловать!",
    "server_starting": "СЕРВЕР ЗАПУСКАЕТСЯ!",
    "usually": "обычно 1-3 минуты",
    "start_error": "Ошибка запуска!",
    "try_or_admin": "Попробуй ещё или напиши администратору.",
    "aternos_offline": "Aternos не подключён!",
    "admin_help": "Администратор проверит подключение.",
    "only_admins": "Только администраторы могут запускать!",
    "already_running": "Сервер уже работает!",
    "join": "Присоединиться",
    "rules": "ПРАВИЛА FICTIONMINE",
    "allowed": "РАЗРЕШЕНО",
    "forbidden": "ЗАПРЕЩЕНО",
    "griefing": "Гриферство и разрушение",
    "cheats": "Читы, хаки, дюпы",
    "insults": "Оскорбления и токсичность",
    "spam": "Спам и реклама",
    "xray": "X-ray и подобное",
    "punishments": "НАКАЗАНИЯ",
    "warning": "Предупреждение",
    "ban_24": "Бан 24 часа",
    "perm_ban": "Перманентный бан",
    "good_game": "Приятной игры! ⛏️",
    "help": "ПОМОЩЬ",
    "server_commands": "🌐 Сервер",
    "info_commands": "ℹ️ Информация",
    "misc_commands": "🎮 Разное",
    "admin_panel": "🔐 /admin — панель администратора",
    "tip_of_day": "💡 СОВЕТ ДНЯ",
    "broadcast": "ОБЪЯВЛЕНИЕ",
    "admin": "АДМИНИСТРАТОР",
    "maintenance": "Техническое обслуживание",
    "try_later": "Сервер временно недоступен. Попробуй позже!",
    "no_players": "👥 Сейчас никого нет 😿",
    "first_join": "Будь первым!",
    "players_online_list": "ОНЛАЙН",
    "record": "Рекорд",
    "statistics": "СТАТИСТИКА",
    "launches": "Запусков",
    "stops": "Остановок",
    "restarts": "Перезапусков",
    "peak": "Пик игроков",
    "commands_executed": "Команд выполнено",
    "unique_players": "Уникальных игроков",
    "last_launch": "Ост. запуск",
    "last_stop": "Ост. остановка",
    "how_to_join": "КАК ПОДКЛЮЧИТЬСЯ",
    "minecraft_bedrock": "Minecraft Bedrock Edition",
    "play": "Играть",
    "servers_tab": "Серверы",
    "add_server": "Добавить сервер",
    "enter_address": "Введи адрес",
    "connect": "Подключайся!",
    "now": "Сейчас",
    "vote_for_server": "ПРОГОЛОСУЙ ЗА СЕРВЕР!",
    "vote_help": "Голос помогает нам расти и привлекать новых игроков!",
    "vote_link": "Minecraft Server List",
    "vote_bonus": "🎁 За каждый голос — бонусы на сервере!",
    "world_seed": "СИД МИРА",
    "use_for_exploring": "Используй для изучения карты!",
    "shop": "ДОНАТ-МАГАЗИН",
    "support_server": "Поддержи сервер и получи привилегии!",
    "vip": "VIP",
    "vip_features": "цветной ник, /fly",
    "premium": "PREMIUM",
    "premium_features": "всё VIP + /god",
    "elite": "ELITE",
    "elite_features": "всё + личный варп",
    "top_players": "ТОП ИГРОКОВ",
    "top_10": "ТОП 10 ИГРОКОВ",
    "message_of_day": "СООБЩЕНИЕ ДНЯ",
    "admin_menu": "МЕНЮ АДМИНИСТРАТОРА",
    "aternos": "Aternos",
    "connected": "Подключено",
    "disconnected": "Отключено",
    "server": "Сервер",
    "players": "Игроков",
    "users": "Юзеров",
    "admins": "Админов",
    "warnings": "Варнов",
    "notes": "Заметок",
    "tech_work": "Техроботы",
    "on": "ВКЛ 🟡",
    "off": "ВЫКЛ 🟢",
    "all_can_start": "ВСЕ могут стартовать ✅",
    "only_admins_start": "Только АДМИНЫ 🔐",
    "start": "Старт",
    "stop": "Стоп",
    "restart": "Рестарт",
    "broadcast_msg": "Напиши объявление для всех",
    "announce_msg": "Напиши текст анонса",
    "list": "Список",
    "full_stats": "Полная статистика",
    "reset_stats": "Сброс статистики",
    "set_log": "Логи → этот чат",
    "close_panel": "Закрыть панель",
    "cancelled": "Отменено.",
    "done": "Готово!",
    "sent": "Отправлено",
    "error": "Ошибка",
    "time": "Время",
}

def t(key, **kwargs):
    txt = T.get(key, key)
    for k, v in kwargs.items():
        txt = txt.replace(f"{{{k}}}", str(v))
    return txt

# ══════════════════════════════════════════════════════════════════
# УТІЛІТИ І ЗБЕРЕЖЕННЯ
# ══════════════════════════════════════════════════════════════════

def load_all():
    global stats, config, admins, users, warns, notes, banned
    for f, o in [(STATS_FILE, stats), (CONFIG_FILE, config)]:
        if os.path.exists(f):
            try:
                with open(f, encoding="utf-8") as fh:
                    o.update(json.load(fh))
            except:
                pass
    for f, t_var in [(ADMINS_FILE, "a"), (USERS_FILE, "u"), (WARNS_FILE, "w"), (NOTES_FILE, "n"), (BANNED_FILE, "b")]:
        if os.path.exists(f):
            try:
                with open(f, encoding="utf-8") as fh:
                    v = json.load(fh)
                    if t_var == "a":
                        admins.update(v)
                    elif t_var == "u":
                        users.update(v)
                    elif t_var == "w":
                        warns.update(v)
                    elif t_var == "n":
                        notes.extend(v)
                    elif t_var == "b":
                        banned.update(v)
            except:
                pass

def save_all():
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        with open(ADMINS_FILE, "w") as f:
            json.dump(list(admins), f)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        with open(WARNS_FILE, "w", encoding="utf-8") as f:
            json.dump(warns, f, ensure_ascii=False, indent=2)
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        with open(BANNED_FILE, "w") as f:
            json.dump(list(banned), f)
    except Exception as e:
        log.error(f"❌ save: {e}")

def reg(u: Update):
    usr = u.effective_user
    if usr.id in banned:
        return False
    users[str(usr.id)] = {
        "first_name": usr.first_name or "",
        "username": usr.username or "",
        "last_seen": datetime.now().isoformat(),
    }
    stats["total_commands"] = stats.get("total_commands", 0) + 1
    return True

# ══════════════════════════════════════════════════════════════════
# ATERNOS
# ══════════════════════════════════════════════════════════════════

async def aternos_login() -> bool:
    global aternos_connected, http_session, login_cookies, last_login_time
    if not all([ATERNOS_USER, ATERNOS_PASS]):
        return False
    if time.time() - last_login_time < 60:
        log.warning("⏳ Логін ещё в процессе, жду...")
        return False

    last_login_time = time.time()

    try:
        from playwright.async_api import async_playwright

        log.info("🔑 Playwright: логинюсь...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            page = await ctx.new_page()

            await ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get:()=>undefined});"
            )

            log.info("   Открываю aternos.org...")
            await page.goto("https://aternos.org/go/", wait_until="domcontentloaded", timeout=60000)

            log.info("   Жду Cloudflare Turnstile...")
            for i in range(30):
                await asyncio.sleep(1)
                
                # Шукаємо й закриваємо рекламу
                try:
                    ads = await page.query_selector_all("[id*='ad'], [class*='ad'], iframe[src*='ad']")
                    for ad in ads:
                        await ad.evaluate("el => el.remove()")
                    log.info("   🗑 Реклама закрита")
                except:
                    pass
                
                # Пробуємо натиснути Turnstile checkbox
                try:
                    checkbox = await page.query_selector("input[type='checkbox'][id*='turnstile']")
                    if checkbox:
                        await checkbox.click()
                        log.info("   ✅ Turnstile checkbox натиснуто!")
                        await asyncio.sleep(2)
                except:
                    pass
                
                # Пробуємо натиснути через JS (може бути приховано)
                try:
                    await page.evaluate("""
                        () => {
                            // Натискаємо іфрейм Turnstile
                            const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                            if (iframe) {
                                const doc = iframe.contentDocument || iframe.contentWindow.document;
                                const checkbox = doc.querySelector('input[type="checkbox"]');
                                if (checkbox) checkbox.click();
                            }
                            // Закриваємо рекламу
                            document.querySelectorAll('[id*="ad"], [class*="advertisement"]').forEach(el => el.remove());
                        }
                    """)
                    log.info("   ⚙️ JS: спроба натиснути Turnstile")
                except:
                    pass
                
                has_form = await page.query_selector("input[name='user']")
                if has_form:
                    log.info("   ✅ Форма найдена!")
                    break
                log.info(f"   [{i + 1}s] Чекаю Turnstile...")
            else:
                log.error("   ❌ Turnstile не пройден за 30 сек")
                await browser.close()
                return False

            log.info("   Вводу логин/пароль...")
            
            # Вводимо повільно як людина
            user_input = await page.query_selector("input[name='user']")
            if user_input:
                await user_input.click()
                await asyncio.sleep(0.2)
                for char in ATERNOS_USER:
                    await page.type("input[name='user']", char, delay=random.randint(50, 100))
                log.info("   ✅ Логин введен")
            else:
                log.error("   ❌ Поле логина не найдено!")
                await browser.close()
                return False

            await asyncio.sleep(0.3)

            pass_input = await page.query_selector("input[name='password']")
            if pass_input:
                await pass_input.click()
                await asyncio.sleep(0.2)
                for char in ATERNOS_PASS:
                    await page.type("input[name='password']", char, delay=random.randint(50, 100))
                log.info("   ✅ Пароль введен")
            else:
                log.error("   ❌ Поле пароля не найдено!")
                await browser.close()
                return False

            await asyncio.sleep(0.5)

            # Натискаємо кнопку логіну
            login_btn = None
            for sel in ["button[type='submit']", "button:has-text('Login')", "button:has-text('Log in')", ".login-button", "input[type='submit']"]:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        login_btn = el
                        log.info(f"   ✅ Кнопка найдена: {sel}")
                        break
                except:
                    pass

            if login_btn:
                await login_btn.click()
                log.info("   ✅ Кнопка натиснута")
            else:
                log.error("   ❌ Кнопка логіну не найдена!")
                await browser.close()
                return False

            await asyncio.sleep(5)
            cookies = await ctx.cookies()
            log.info(f"   Куки: {len(cookies)}")
            await browser.close()

        # Создаём aiohttp сессию
        jar = aiohttp.CookieJar()
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
            },
        )
        aternos_connected = True
        log.info("✅ Aternos подключён!")
        return True
    except Exception as e:
        log.error(f"❌ login: {e}", exc_info=True)
        return False

async def _get(endpoint, params=None):
    if not http_session:
        return None, 0
    try:
        async with http_session.get(
            f"https://aternos.org/panel/ajax/{endpoint}",
            params=params or {"server": SERVER_ID},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            if r.status == 200:
                try:
                    return await r.json(), 200
                except:
                    return {}, 200
            return None, r.status
    except Exception as e:
        log.error(f"❌ {endpoint}: {e}")
        return None, 0

async def update_server_info():
    global server_status, current_players
    if not aternos_connected:
        return
    data, code = await _get("status.php")
    if code == 200 and data:
        server_status = data.get("status", "offline")
        p = data.get("players", {})
        current_players = p.get("list", []) if isinstance(p, dict) else []

async def aternos_start() -> bool:
    _, code = await _get("start.php")
    if code == 200:
        global server_status
        server_status = "starting"
        return True
    return False

async def aternos_stop() -> bool:
    _, code = await _get("stop.php")
    if code == 200:
        global server_status
        server_status = "offline"
        return True
    return False

# ══════════════════════════════════════════════════════════════════
# УТИЛІТИ
# ══════════════════════════════════════════════════════════════════

def icon(s):
    return {"online": "🟢", "offline": "🔴", "starting": "🟡", "stopping": "🟠"}.get(s, "⚫")

def get_msg(u):
    return u.callback_query.message if u.callback_query else u.message

async def typing(u):
    try:
        await get_msg(u).chat.send_action(ChatAction.TYPING)
    except:
        pass

async def send_log(text):
    if not telegram_app:
        return
    t_id = config.get("log_chat_id") or LOG_CHAT_ID
    if not t_id:
        return
    try:
        await telegram_app.bot.send_message(t_id, text, parse_mode="HTML")
    except:
        pass

def ulabel(u):
    return f"@{u.effective_user.username}" if u.effective_user.username else u.effective_user.first_name or "???"

def is_admin(u):
    return u.effective_user.id in admins

def is_banned(u):
    return u.effective_user.id in banned

def now_str():
    return datetime.now().strftime("%H:%M:%S")

def now_full():
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def get_uptime():
    if stats.get("uptime_from") and server_status in ("online", "starting"):
        d = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
        return f"{d.seconds//3600}ч {(d.seconds%3600)//60}м"
    return "—"

# ══════════════════════════════════════════════════════════════════
# КЛАВІАТУРИ
# ══════════════════════════════════════════════════════════════════

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Запустить", callback_data="on")],
        [InlineKeyboardButton("📊 Статус", callback_data="status"),
         InlineKeyboardButton("👥 Игроки", callback_data="players")],
        [InlineKeyboardButton("ℹ️ Инфо", callback_data="info"),
         InlineKeyboardButton("🗺 Подключиться", callback_data="connect")],
        [InlineKeyboardButton("📜 Правила", callback_data="rules"),
         InlineKeyboardButton("🎲 Совет", callback_data="random")],
        [InlineKeyboardButton("🏆 Топ", callback_data="top"),
         InlineKeyboardButton("🌍 Сид", callback_data="seed")],
        [InlineKeyboardButton("🗳 Голос", callback_data="vote"),
         InlineKeyboardButton("🛒 Магазин", callback_data="shop")],
        [InlineKeyboardButton("⏱ Аптайм", callback_data="uptime"),
         InlineKeyboardButton("💬 MOTD", callback_data="motd")],
    ])

def admin_kb():
    m = config.get("maintenance", False)
    a = config.get("allow_all_start", True)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("━━━ 🖥 СЕРВЕР ━━━", callback_data="noop")],
        [InlineKeyboardButton("🟢 Старт", callback_data="adm_start"),
         InlineKeyboardButton("🔴 Стоп", callback_data="adm_stop"),
         InlineKeyboardButton("🔄 Рестарт", callback_data="adm_restart")],
        [InlineKeyboardButton("━━━ 📢 СООБЩЕНИЯ ━━━", callback_data="noop")],
        [InlineKeyboardButton("📢 Броадкаст", callback_data="adm_broadcast"),
         InlineKeyboardButton("📣 Анонс", callback_data="adm_announce")],
        [InlineKeyboardButton("━━━ ⚙️ ATERNOS / ЛОГІН ━━━", callback_data="noop")],
        [InlineKeyboardButton("🔄 Переподключить", callback_data="adm_reconnect"),
         InlineKeyboardButton("📊 Статус", callback_data="adm_aternos_status")],
        [InlineKeyboardButton("🍪 Ввести куки", callback_data="adm_set_cookie"),
         InlineKeyboardButton("🔍 Диагностика", callback_data="adm_diagnose")],
        [InlineKeyboardButton("📸 Скриншот", callback_data="adm_screenshot"),
         InlineKeyboardButton("👁 Watch панель", callback_data="adm_watch_panel")],
        [InlineKeyboardButton("📋 Консоль", callback_data="adm_console")],
        [InlineKeyboardButton("━━━ 👥 ИГРОКИ ━━━", callback_data="noop")],
        [InlineKeyboardButton("👥 Список", callback_data="adm_users"),
         InlineKeyboardButton("⚠️ Варны", callback_data="adm_warns")],
        [InlineKeyboardButton("👮 Выдать варн", callback_data="adm_warn_give"),
         InlineKeyboardButton("🚫 Забанить", callback_data="adm_ban")],
        [InlineKeyboardButton("━━━ 🔧 НАСТРОЙКИ ━━━", callback_data="noop")],
        [InlineKeyboardButton(f"{'🔴 Техроботы' if m else '🟢 Техроботы'}", callback_data="adm_maintenance"),
         InlineKeyboardButton(f"{'✅ Все' if a else '🔐 Админы'}", callback_data="adm_toggle_start")],
        [InlineKeyboardButton("✏️ MOTD", callback_data="adm_setmotd"),
         InlineKeyboardButton("🌍 Сід", callback_data="adm_setseed")],
        [InlineKeyboardButton("🛒 Магазин", callback_data="adm_setshop"),
         InlineKeyboardButton("📝 Заметки", callback_data="adm_notes")],
        [InlineKeyboardButton("━━━ 📈 СТАТИСТИКА ━━━", callback_data="noop")],
        [InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"),
         InlineKeyboardButton("🗑 Сброс", callback_data="adm_resetstats")],
        [InlineKeyboardButton("📜 Логи → чат", callback_data="adm_setlog")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="adm_exit")],
    ])

def watch_kb(chat_id: int):
    sess = watch_sessions.get(chat_id, {})
    interval = sess.get("interval", 20)
    auto = sess.get("auto_login", True)
    running = sess.get("task") and not sess["task"].done() if sess.get("task") else False
    auto_label = "🤖 Авто" if auto else "✋ Вручну"
    run_label = "🛑 Зупинити" if running else "▶️ Запустити"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("━━━ 👁 WATCH ПАНЕЛЬ ━━━", callback_data="noop")],
        [InlineKeyboardButton(f"{'🟢 Активний' if running else '🔴 Зупинено'}", callback_data="noop")],
        [InlineKeyboardButton(run_label, callback_data="watch_toggle"),
         InlineKeyboardButton("📸 Знімок зараз", callback_data="watch_snap")],
        [InlineKeyboardButton("━━━ ⚡ ШВИДКІСТЬ ━━━", callback_data="noop")],
        [InlineKeyboardButton("10с", callback_data="watch_spd_10"),
         InlineKeyboardButton("20с" + (" ✅" if interval==20 else ""), callback_data="watch_spd_20"),
         InlineKeyboardButton("30с" + (" ✅" if interval==30 else ""), callback_data="watch_spd_30"),
         InlineKeyboardButton("60с" + (" ✅" if interval==60 else ""), callback_data="watch_spd_60")],
        [InlineKeyboardButton("✏️ Своя швидкість", callback_data="watch_spd_custom")],
        [InlineKeyboardButton("━━━ 🔑 АВТОРИЗАЦІЯ ━━━", callback_data="noop")],
        [InlineKeyboardButton(f"Режим: {auto_label}", callback_data="watch_toggle_auth"),
         InlineKeyboardButton("🔍 Діагностика", callback_data="watch_diagnose")],
        [InlineKeyboardButton("👤 Ввести логін", callback_data="watch_set_user"),
         InlineKeyboardButton("🔐 Ввести пароль", callback_data="watch_set_pass")],
        [InlineKeyboardButton("🍪 Ввести куки", callback_data="adm_set_cookie")],
        [InlineKeyboardButton("━━━ 🗺 НАВІГАЦІЯ ━━━", callback_data="noop")],
        [InlineKeyboardButton("🏠 Головна", callback_data="watch_nav_home"),
         InlineKeyboardButton("🔑 Логін", callback_data="watch_nav_login"),
         InlineKeyboardButton("🖥 Сервер", callback_data="watch_nav_server")],
        [InlineKeyboardButton("◀️ Назад", callback_data="watch_nav_back"),
         InlineKeyboardButton("▶️ Вперед", callback_data="watch_nav_fwd"),
         InlineKeyboardButton("🔄 Оновити", callback_data="watch_nav_reload")],
        [InlineKeyboardButton("✏️ Свій URL", callback_data="watch_set_url")],
        [InlineKeyboardButton("━━━━━━━━━━━━━━━━━━━━━━", callback_data="noop")],
        [InlineKeyboardButton("🔙 Назад до /admin", callback_data="watch_back_admin")],
    ])

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update):
        await get_msg(update).reply_text("🚫 <b>Ты забанен!</b>", parse_mode="HTML")
        return
    save_all()
    await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text(
            f"🔧 <b>{t('maintenance')}</b>\n\n{t('try_later')}", parse_mode="HTML"
        )
        return
    await update_server_info()
    pl_str = f"{len(current_players)} {t('players_online')}" if server_status == "online" else t("server_disabled")
    await get_msg(update).reply_text(
        f"{t('start_title')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} <b>Статус:</b> {server_status.upper()}\n"
        f"👥 <b>Игроки:</b> {pl_str}\n"
        f"🌐 <b>IP:</b> <code>{config['server_ip']}</code>\n"
        f"🔌 <b>Порт:</b> <code>{config['server_port']}</code>\n"
        f"⏱ <b>Аптайм:</b> {get_uptime()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>{config.get('motd', '')}</i>",
        reply_markup=main_kb(),
        parse_mode="HTML",
    )

async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update):
        return
    save_all()
    await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 <b>Техническое обслуживание!</b>", parse_mode="HTML")
        return
    if not config.get("allow_all_start", True) and not is_admin(update):
        await get_msg(update).reply_text(f"🚫 <b>{t('only_admins')}</b>", parse_mode="HTML")
        return
    msg = await get_msg(update).reply_text(f"⏳ <b>Запускаю сервер...</b>", parse_mode="HTML")
    if not aternos_connected:
        await msg.edit_text(
            f"❌ <b>{t('aternos_offline')}</b>\n{t('admin_help')}", parse_mode="HTML"
        )
        return
    await update_server_info()
    if server_status in ("online", "starting"):
        await msg.edit_text(
            f"✅ <b>Сервер уже {'работает' if server_status == 'online' else 'запускается'}!</b>\n\n"
            f"🌐 <code>{config['server_ip']}</code>\n🔌 <code>{config['server_port']}</code>",
            parse_mode="HTML",
        )
        return
    ok = await aternos_start()
    if ok:
        stats["starts"] += 1
        stats["last_start"] = datetime.now().isoformat()
        stats["uptime_from"] = datetime.now().isoformat()
        save_all()
        await msg.edit_text(
            f"🟢 <b>{t('server_starting')}</b>\n\n"
            f"🌐 <code>{config['server_ip']}</code>\n"
            f"🔌 <code>{config['server_port']}</code>\n"
            f"⏰ {now_str()}\n\n"
            f"<i>⏱ {t('usually')}</i>",
            parse_mode="HTML",
        )
        await send_log(
            f"🟢 <b>ЗАПУСК</b>\n👤 {ulabel(update)}\n⏰ {now_full()}\n🚀 #{stats['starts']}"
        )
    else:
        await msg.edit_text(f"❌ <b>{t('start_error')}</b>\n{t('try_or_admin')}", parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    await update_server_info()
    await get_msg(update).reply_text(
        f"{icon(server_status)} <b>СТАТУС СЕРВЕРА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 <b>FictionMine</b> (Bedrock)\n"
        f"📍 <b>{server_status.upper()}</b>\n"
        f"👥 <b>Игроков:</b> {len(current_players)}\n"
        f"⏱ <b>Аптайм:</b> {get_uptime()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <code>{config['server_ip']}</code>\n"
        f"🔌 <code>{config['server_port']}</code>\n"
        f"⏰ {now_str()}",
        parse_mode="HTML",
    )

async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    await update_server_info()
    if server_status != "online":
        await get_msg(update).reply_text(
            f"🔴 <b>Сервер {server_status.upper()}</b>\n\nЗапусти через /on", parse_mode="HTML"
        )
        return
    if not current_players:
        await get_msg(update).reply_text(
            f"👥 <b>{t('no_players')}</b>\n\n{t('first_join')}\n🌐 <code>{config['server_ip']}</code>",
            parse_mode="HTML",
        )
        return
    if len(current_players) > stats["peak_players"]:
        stats["peak_players"] = len(current_players)
        save_all()
    pl = "\n".join(f"  ⚔️ <b>{p}</b>" for p in current_players)
    await get_msg(update).reply_text(
        f"👥 <b>{t('players_online_list')}: {len(current_players)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{pl}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Аптайм: {get_uptime()}\n👑 Рекорд: {stats['peak_players']}",
        parse_mode="HTML",
    )

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    await update_server_info()
    ls = (
        datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M")
        if stats.get("last_start")
        else "—"
    )
    lo = (
        datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")
        if stats.get("last_stop")
        else "—"
    )
    await get_msg(update).reply_text(
        f"📊 <b>FICTIONMINE — СТАТИСТИКА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} {server_status.upper()} | 👥 {len(current_players)} игроков\n\n"
        f"🚀 {t('launches')}: <b>{stats['starts']}</b>\n"
        f"🛑 {t('stops')}: <b>{stats['stops']}</b>\n"
        f"🔄 {t('restarts')}: <b>{stats.get('restarts', 0)}</b>\n"
        f"👑 {t('record')}: <b>{stats['peak_players']}</b>\n"
        f"⏱ {t('uptime')}: <b>{get_uptime()}</b>\n"
        f"💬 {t('commands_executed')}: <b>{stats.get('total_commands', 0)}</b>\n"
        f"👤 {t('unique_players')}: <b>{len(users)}</b>\n\n"
        f"▶️ {t('last_launch')}: {ls}\n"
        f"⏹ {t('last_stop')}: {lo}",
        parse_mode="HTML",
    )

async def cmd_connect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    await update_server_info()
    await get_msg(update).reply_text(
        f"🗺 <b>{t('how_to_join')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 <b>{t('minecraft_bedrock')}</b>\n\n"
        f"1️⃣ Открой Minecraft\n"
        f"2️⃣ Нажми <b>{t('play')}</b>\n"
        f"3️⃣ Вкладка <b>{t('servers_tab')}</b>\n"
        f"4️⃣ <b>{t('add_server')}</b>\n"
        f"5️⃣ {t('enter_address')}:\n"
        f"   🌐 <code>{config['server_ip']}</code>\n"
        f"   🔌 <code>{config['server_port']}</code>\n"
        f"6️⃣ {t('connect')}!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} {t('now')}: <b>{server_status.upper()}</b>",
        parse_mode="HTML",
    )

async def cmd_rules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    await get_msg(update).reply_text(
        f"📜 <b>{t('rules')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ <b>{t('allowed')}:</b>\n"
        f"• Строительство и исследование\n"
        f"• Торговля между игроками\n"
        f"• Создание кланов и союзов\n"
        f"• PvP в специальных зонах\n"
        f"• Редстоун механизмы\n\n"
        f"❌ <b>{t('forbidden')}:</b>\n"
        f"• {t('griefing')}\n"
        f"• {t('cheats')}\n"
        f"• Оскорбления и токсичность\n"
        f"• Спам и реклама\n"
        f"• {t('xray')}\n\n"
        f"⚠️ <b>{t('punishments')}:</b>\n"
        f"1️⃣ {t('warning')}\n"
        f"2️⃣ {t('ban_24')}\n"
        f"3️⃣ {t('perm_ban')}\n\n"
        f"<i>{t('good_game')}</i>",
        parse_mode="HTML",
    )

async def cmd_random(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    tips = [
        "💡 Кровать устанавливает точку возрождения!",
        "⚔️ Зачарование «Добыча III» — больше ресурсов!",
        "🛡️ Щит блокирует весь урон от стрел!",
        "💎 Алмазы чаще на уровне Y=-58!",
        "🔥 Огниво создает портал в Ад!",
        "⚡ Молния + свинья = свиноезд!",
        "🎣 Рыбалка ночью — лучшие трофеи!",
        "🏔️ Изумруды только в горах!",
        "🌙 Спи ночью — пропускаешь монстров!",
        "⛏️ Кирка с «Удача III» — больше алмазов!",
    ]
    await get_msg(update).reply_text(
        f"🎲 <b>{t('tip_of_day')}</b>\n\n{random.choice(tips)}\n\n<i>Напиши /random для новой подсказки!</i>",
        parse_mode="HTML",
    )

async def cmd_uptime(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    await update_server_info()
    await get_msg(update).reply_text(
        f"⏱ <b>{t('uptime').upper()}</b>\n\n{icon(server_status)} {server_status.upper()}\n⏱ <b>{get_uptime()}</b>\n⏰ {now_full()}",
        parse_mode="HTML",
    )

async def cmd_vote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    await get_msg(update).reply_text(
        f"🗳 <b>{t('vote_for_server')}</b>\n\n"
        f"{t('vote_help')}\n\n"
        f"🔗 <a href='https://minecraft-server-list.com/'>Minecraft Server List</a>\n"
        f"🔗 <a href='https://minecraftservers.org/'>Minecraft Servers</a>\n\n"
        f"{t('vote_bonus')}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

async def cmd_seed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    seed = config.get("world_seed") or "Не установлено"
    await get_msg(update).reply_text(
        f"🌍 <b>{t('world_seed')}</b>\n\n<code>{seed}</code>\n\n<i>{t('use_for_exploring')}</i>",
        parse_mode="HTML",
    )

async def cmd_shop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    link = config.get("shop_link") or "Не настроено"
    await get_msg(update).reply_text(
        f"🛒 <b>{t('shop')}</b>\n\n"
        f"{t('support_server')}\n\n"
        f"💎 <b>{t('vip')}</b> — {t('vip_features')}\n"
        f"👑 <b>{t('premium')}</b> — {t('premium_features')}\n"
        f"🏆 <b>{t('elite')}</b> — {t('elite_features')}\n\n"
        f"🔗 {link}",
        parse_mode="HTML",
    )

async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    top = config.get("top_players", [])
    if not top:
        await get_msg(update).reply_text(
            f"🏆 <b>{t('top_players')}</b>\n\n<i>Статистика еще не собрана.\nАдмин обновит топ!</i>",
            parse_mode="HTML",
        )
        return
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = [f"{medals[i]} <b>{p['name']}</b> — {p.get('score', '?')} очков" for i, p in enumerate(top[:10])]
    await get_msg(update).reply_text(f"🏆 <b>{t('top_10')}</b>\n\n" + "\n".join(lines), parse_mode="HTML")

async def cmd_motd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    await update_server_info()
    await get_msg(update).reply_text(
        f"💬 <b>{t('message_of_day')}</b>\n\n{config.get('motd', 'Добро пожаловать!')}\n\n{icon(server_status)} {server_status.upper()}",
        parse_mode="HTML",
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    await typing(update)
    adm = "\n\n🔐 /admin — панель администратора" if is_admin(update) else ""
    await get_msg(update).reply_text(
        f"❓ <b>{t('help')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{t('server_commands')}:</b>\n"
        f"/on — запустить сервер\n"
        f"/status — статус и IP\n"
        f"/players — кто онлайн\n\n"
        f"<b>{t('info_commands')}:</b>\n"
        f"/info — статистика\n"
        f"/connect — как подключиться\n"
        f"/rules — правила\n"
        f"/random — совет\n\n"
        f"<b>{t('misc_commands')}:</b>\n"
        f"/top — топ игроков\n"
        f"/vote — проголосовать\n"
        f"/seed — сид мира\n"
        f"/shop — магазин\n"
        f"/uptime — время работы\n"
        f"/motd — сообщение дня"
        f"{adm}",
        parse_mode="HTML",
    )

# ══════════════════════════════════════════════════════════════════
# ADMIN PANEL
# ══════════════════════════════════════════════════════════════════

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update):
        return
    if is_admin(update):
        await show_admin_panel(update)
        return
    await update.message.reply_text("🔐 <b>Введи код доступа:</b>", parse_mode="HTML")
    return WAIT_CODE

async def got_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == ADMIN_CODE:
        admins.add(update.effective_user.id)
        save_all()
        await update.message.reply_text("✅ <b>Добро пожаловать, Администратор!</b>", parse_mode="HTML")
        await send_log(f"🔐 <b>НОВЫЙ АДМИН</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        await show_admin_panel(update)
    else:
        await update.message.reply_text("❌ <b>Неверный код!</b>", parse_mode="HTML")
        await send_log(f"⚠️ <b>НЕУДАЧНАЯ ПОПЫТКА</b>\n👤 {ulabel(update)}")
    return ConversationHandler.END

async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("action", None)
    await update.message.reply_text(f"❌ {t('cancelled')}")
    return ConversationHandler.END

async def show_admin_panel(update: Update):
    await update_server_info()
    m = config.get("maintenance", False)
    await get_msg(update).reply_text(
        f"⚙️ <b>{t('admin_menu')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 {t('aternos')}: {'✅ ' + t('connected') if aternos_connected else '❌ ' + t('disconnected')}\n"
        f"{icon(server_status)} {t('server')}: <b>{server_status.upper()}</b>\n"
        f"👥 {t('players')}: <b>{len(current_players)}</b>\n"
        f"⏱ {t('uptime')}: <b>{get_uptime()}</b>\n"
        f"👤 {t('users')}: <b>{len(users)}</b> | 🔐 {t('admins')}: <b>{len(admins)}</b>\n"
        f"⚠️ {t('warnings')}: <b>{sum(warns.values())}</b> | 📝 {t('notes')}: <b>{len(notes)}</b>\n"
        f"🔧 {t('tech_work')}: <b>{'ВКЛ 🟡' if m else 'ВЫКЛ 🟢'}</b>",
        reply_markup=admin_kb(),
        parse_mode="HTML",
    )

async def on_admin_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "noop":
        return
    if not is_admin(update):
        await q.answer("🚫 Нет доступа!", show_alert=True)
        return
    d = q.data

    if d == "adm_start":
        await q.message.edit_text("⏳ <b>Запускаю...</b>", parse_mode="HTML")
        await update_server_info()
        if server_status in ("online", "starting"):
            await q.message.edit_text("✅ <b>Уже работает!</b>", reply_markup=admin_kb(), parse_mode="HTML")
            return
        ok = await aternos_start()
        if ok:
            stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat()
            stats["uptime_from"] = datetime.now().isoformat()
            save_all()
            await q.message.edit_text(f"🟢 <b>ЗАПУЩЕНО!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🟢 <b>ЗАПУСК (АДМИН)</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_stop":
        await q.message.edit_text("⏳ <b>Останавливаю...</b>", parse_mode="HTML")
        ok = await aternos_stop()
        if ok:
            stats["stops"] += 1
            stats["last_stop"] = datetime.now().isoformat()
            stats["uptime_from"] = None
            save_all()
            await q.message.edit_text(f"🔴 <b>ОСТАНОВЛЕНО!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔴 <b>СТОП (АДМИН)</b>\n👤 {ulabel(update)}")
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
            stats["uptime_from"] = datetime.now().isoformat()
            save_all()
            await q.message.edit_text(f"🔄 <b>ПЕРЕЗАПУЩЕНО!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔄 <b>ПЕРЕЗАПУСК</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_reconnect":
        await q.message.edit_text("⏳ <b>Переподключаюсь...</b>", parse_mode="HTML")
        ok = await aternos_login()
        r = "✅ Подключено!" if ok else "❌ Не удалось"
        await q.message.edit_text(f"🔌 <b>{r}</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_aternos_status":
        data, code = await _get("status.php")
        if code == 200 and data:
            await q.message.edit_text(
                f"📊 <b>СТАТУС ATERNOS</b>\n\n<code>{json.dumps(data, ensure_ascii=False, indent=2)[:600]}</code>",
                reply_markup=admin_kb(),
                parse_mode="HTML",
            )
        else:
            await q.message.edit_text(f"❌ Ошибка: код {code}", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_screenshot":
        await q.message.edit_text("📸 <b>Делаю скриншот...</b>", parse_mode="HTML")
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                bctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
                for name, val in login_cookies.items():
                    await bctx.add_cookies([{"name": name, "value": val, "domain": "aternos.org", "path": "/"}])
                page = await bctx.new_page()
                await page.goto(f"https://aternos.org/server/{SERVER_ID}", timeout=30000)
                await asyncio.sleep(3)
                screenshot = await page.screenshot(full_page=False)
                await browser.close()
            await telegram_app.bot.send_photo(q.message.chat_id, screenshot, caption=f"📸 Скриншот\n⏰ {now_full()}")
            await q.message.edit_text("📸 <b>Скриншот отправлен!</b>", reply_markup=admin_kb(), parse_mode="HTML")
        except Exception as e:
            await q.message.edit_text(f"❌ Ошибка:\n<code>{str(e)[:200]}</code>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_console":
        data, code = await _get("console.php")
        if code == 200 and data:
            lines = data.get("lines", []) if isinstance(data, dict) else []
            txt = "\n".join(str(l) for l in lines[-20:]) if lines else str(data)[:600]
            await q.message.edit_text(f"📋 <b>КОНСОЛЬ</b>\n\n<code>{txt[:800]}</code>", reply_markup=admin_kb(), parse_mode="HTML")
        else:
            await q.message.edit_text(f"❌ Консоль недоступна (код {code})", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_set_cookie":
        ctx.user_data["action"] = "set_cookie"
        await q.message.reply_text(
            "🍪 <b>РУЧНЕ ВВЕДЕННЯ КУКІВ</b>\n\n"
            "Введи куки у форматі JSON або як рядок:\n\n"
            "<b>JSON:</b>\n<code>{\"ATERNOS_SESSION\": \"xxx\", \"ATERNOS_SEC\": \"yyy\"}</code>\n\n"
            "<b>або рядком:</b>\n<code>ATERNOS_SESSION=xxx; ATERNOS_SEC=yyy</code>\n\n"
            "Де взяти куки:\n"
            "DevTools → Application → Cookies → aternos.org\n\n"
            "<i>/cancel — скасувати</i>",
            parse_mode="HTML"
        )

    elif d == "adm_diagnose":
        await q.message.edit_text("🔍 <b>Діагностика...</b>", parse_mode="HTML")
        lines = []
        lines.append(f"🔌 Aternos connected: <b>{'✅' if aternos_connected else '❌'}</b>")
        lines.append(f"📡 http_session: <b>{'✅ є' if http_session and not http_session.closed else '❌ немає/закрита'}</b>")
        lines.append(f"🍪 Куків у пам'яті: <b>{len(login_cookies)}</b>")
        if login_cookies:
            important = ["ATERNOS_SESSION", "ATERNOS_SEC", "PHPSESSID"]
            for k in important:
                val = login_cookies.get(k)
                lines.append(f"  {'✅' if val else '❌'} {k}: {'є (' + str(len(val)) + ' символів)' if val else 'відсутній'}")
        lines.append(f"⏱ Останній логін: <b>{datetime.fromtimestamp(last_login_time).strftime('%H:%M:%S') if last_login_time else 'ніколи'}</b>")
        # Тест запиту
        if http_session and not http_session.closed:
            try:
                async with http_session.get(
                    "https://aternos.org/panel/ajax/status.php",
                    params={"server": SERVER_ID},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    lines.append(f"🌐 Тест status.php: <b>{r.status}</b>")
                    if r.status == 403:
                        lines.append("  ⚠️ 403 = сесія протухла або куки не пройшли")
                    elif r.status == 200:
                        lines.append("  ✅ Запит успішний!")
            except Exception as e:
                lines.append(f"🌐 Тест: ❌ <code>{str(e)[:100]}</code>")
        else:
            lines.append("🌐 Тест: ❌ Сесія не ініціалізована")
        await q.message.edit_text(
            "🔍 <b>ДІАГНОСТИКА</b>\n\n" + "\n".join(lines),
            reply_markup=admin_kb(), parse_mode="HTML"
        )

    elif d == "adm_watch_panel":
        await show_watch_panel(update, q.message)

    elif d == "watch_back_admin":
        await show_admin_panel(update)

    elif d == "watch_toggle":
        chat_id = q.message.chat_id
        sess = watch_sessions.get(chat_id, {})
        task = sess.get("task")
        if task and not task.done():
            task.cancel()
            watch_sessions.get(chat_id, {}).pop("task", None)
            if chat_id in watch_sessions:
                watch_sessions[chat_id]["task"] = None
            await q.message.edit_text("🛑 <b>Watch зупинено!</b>", reply_markup=watch_kb(chat_id), parse_mode="HTML")
        else:
            if chat_id not in watch_sessions:
                watch_sessions[chat_id] = {"interval": 20, "auto_login": True, "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"}
            new_task = asyncio.create_task(_watch_loop(chat_id))
            watch_sessions[chat_id]["task"] = new_task
            await q.message.edit_text("▶️ <b>Watch запущено!</b>", reply_markup=watch_kb(chat_id), parse_mode="HTML")

    elif d == "watch_snap":
        chat_id = q.message.chat_id
        await q.message.reply_text("📸 <b>Роблю знімок...</b>", parse_mode="HTML")
        if chat_id not in watch_sessions:
            watch_sessions[chat_id] = {"interval": 20, "auto_login": True, "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"}
        await _take_and_send_screenshot(chat_id, q.message.chat_id)

    elif d in ("watch_spd_10", "watch_spd_20", "watch_spd_30", "watch_spd_60"):
        chat_id = q.message.chat_id
        spd = int(d.split("_")[-1])
        if chat_id not in watch_sessions:
            watch_sessions[chat_id] = {"interval": spd, "auto_login": True, "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"}
        else:
            watch_sessions[chat_id]["interval"] = spd
        await q.message.edit_text(f"⚡ <b>Швидкість: {spd} сек</b>", reply_markup=watch_kb(chat_id), parse_mode="HTML")

    elif d == "watch_spd_custom":
        ctx.user_data["action"] = "watch_speed"
        await q.message.reply_text("✏️ <b>Введи інтервал в секундах (5–300):</b>\n<i>/cancel — скасувати</i>", parse_mode="HTML")

    elif d == "watch_toggle_auth":
        chat_id = q.message.chat_id
        if chat_id not in watch_sessions:
            watch_sessions[chat_id] = {"interval": 20, "auto_login": True, "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"}
        cur = watch_sessions[chat_id].get("auto_login", True)
        watch_sessions[chat_id]["auto_login"] = not cur
        label = "🤖 Авто" if not cur else "✋ Вручну"
        await q.message.edit_text(f"🔑 <b>Режим авторизації: {label}</b>", reply_markup=watch_kb(chat_id), parse_mode="HTML")

    elif d == "watch_set_user":
        ctx.user_data["action"] = "watch_user"
        await q.message.reply_text(
            "👤 <b>Введи логін для Watch:</b>\n\n"
            "<i>Це окремо від основного ATERNOS_USER.\n"
            "Залиш порожнім для використання env змінної.\n"
            "/cancel — скасувати</i>",
            parse_mode="HTML"
        )

    elif d == "watch_set_pass":
        ctx.user_data["action"] = "watch_pass"
        await q.message.reply_text(
            "🔐 <b>Введи пароль для Watch:</b>\n\n"
            "<i>Це окремо від основного ATERNOS_PASS.\n"
            "Залиш порожнім для використання env змінної.\n"
            "/cancel — скасувати</i>",
            parse_mode="HTML"
        )

    elif d == "watch_set_url":
        ctx.user_data["action"] = "watch_url"
        await q.message.reply_text(
            "🔗 <b>Введи URL для Watch:</b>\n\n"
            "• <code>https://aternos.org/server/</code>\n"
            "• <code>https://aternos.org/go/</code>\n"
            "• Або будь-який інший URL\n\n"
            "<i>/cancel — скасувати</i>",
            parse_mode="HTML"
        )

    elif d == "watch_diagnose":
        chat_id = q.message.chat_id
        sess = watch_sessions.get(chat_id, {})
        running = sess.get("task") and not sess["task"].done()
        w_user = sess.get("w_user") or "(з env)"
        w_pass = "***" if sess.get("w_pass") else "(з env)"
        auto = sess.get("auto_login", True)
        lines = [
            f"👁 Watch: <b>{'🟢 Активний' if running else '🔴 Зупинено'}</b>",
            f"⚡ Інтервал: <b>{sess.get('interval', 20)} сек</b>",
            f"🔑 Режим: <b>{'🤖 Авто' if auto else '✋ Вручну'}</b>",
            f"👤 Логін: <b>{w_user}</b>",
            f"🔐 Пароль: <b>{w_pass}</b>",
            f"🔗 URL: <code>{sess.get('url', '—')}</code>",
            f"🍪 Куків: <b>{len(login_cookies)}</b>",
            f"🔌 Aternos: <b>{'✅' if aternos_connected else '❌'}</b>",
        ]
        await q.message.edit_text(
            "🔍 <b>WATCH ДІАГНОСТИКА</b>\n\n" + "\n".join(lines),
            reply_markup=watch_kb(chat_id), parse_mode="HTML"
        )

    elif d in ("watch_nav_home", "watch_nav_login", "watch_nav_server", "watch_nav_back", "watch_nav_fwd", "watch_nav_reload"):
        chat_id = q.message.chat_id
        if chat_id not in watch_sessions:
            watch_sessions[chat_id] = {"interval": 20, "auto_login": True, "url": "https://aternos.org/go/"}
        nav_map = {
            "watch_nav_home":   "https://aternos.org/",
            "watch_nav_login":  "https://aternos.org/go/",
            "watch_nav_server": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/servers/",
        }
        if d in nav_map:
            watch_sessions[chat_id]["url"] = nav_map[d]
            await q.message.reply_text(f"🗺 <b>URL змінено:</b>\n<code>{nav_map[d]}</code>", parse_mode="HTML")
        elif d == "watch_nav_reload":
            pass  # просто робимо знімок поточного
        elif d in ("watch_nav_back", "watch_nav_fwd"):
            await q.message.reply_text(
                "ℹ️ Навігація назад/вперед доступна тільки в активному Watch.\n"
                "Запусти Watch і використовуй кнопки під час трансляції.",
                parse_mode="HTML"
            )
            return
        await q.message.reply_text("📸 <b>Роблю знімок...</b>", parse_mode="HTML")
        await _take_and_send_screenshot(chat_id, chat_id)

    # ── BROWSER CONTROL ──────────────────────────────────────────
    elif d == "bc_start":
        chat_id = q.message.chat_id
        await q.message.edit_text("🚀 <b>Запускаю браузер...</b>", parse_mode="HTML")
        result = await bc_start_browser(chat_id)
        if result is True:
            await bc_screenshot_and_send(chat_id, f"🟢 Браузер запущен!\n⏰ {now_str()}")
            await q.message.edit_text("🟢 <b>Браузер активен!</b>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")
        else:
            await q.message.edit_text(f"❌ <b>Ошибка:</b>\n<code>{str(result)[:200]}</code>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")

    elif d == "bc_restart":
        chat_id = q.message.chat_id
        await q.message.edit_text("🔄 <b>Перезапускаю...</b>", parse_mode="HTML")
        result = await bc_start_browser(chat_id)
        if result is True:
            await bc_screenshot_and_send(chat_id, f"🔄 Браузер перезапущен!\n⏰ {now_str()}")
        await q.message.edit_text(
            "🔄 <b>Готово!</b>" if result is True else f"❌ <code>{str(result)[:100]}</code>",
            reply_markup=browser_control_kb(chat_id), parse_mode="HTML"
        )

    elif d == "bc_close":
        chat_id = q.message.chat_id
        await bc_close_browser(chat_id)
        await q.message.edit_text("🛑 <b>Браузер закрыт.</b>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")

    elif d == "bc_snap":
        chat_id = q.message.chat_id
        await bc_screenshot_and_send(chat_id)
        await q.message.edit_text("📸 <b>Скриншот отправлен!</b>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")

    elif d == "bc_snap_full":
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        try:
            title = await page.title()
            shot = await page.screenshot(full_page=True)
            await telegram_app.bot.send_photo(chat_id, shot,
                caption=f"🖼 Полный скриншот\n📄 {title}\n⏰ {now_str()}", parse_mode="HTML")
            await q.message.edit_text("🖼 <b>Полный скриншот отправлен!</b>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")
        except Exception as e:
            await q.message.edit_text(f"❌ <code>{e}</code>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")

    elif d == "bc_toggle_input":
        chat_id = q.message.chat_id
        if chat_id in browser_control_mode:
            browser_control_mode.discard(chat_id)
            status = "🔴 ВЫКЛ — текст идёт боту"
        else:
            if not browser_sessions.get(chat_id, {}).get("active"):
                await q.answer("⚠️ Сначала запусти браузер!", show_alert=True); return
            browser_control_mode.add(chat_id)
            status = "🟢 ВКЛ — текст идёт в браузер"
        await q.message.edit_text(
            f"⌨️ <b>Режим ввода: {status}</b>\n\n"
            f"{'Пиши в чат — всё вводится на странице.' if chat_id in browser_control_mode else 'Команды идут боту.'}\n\n"
            f"Спецклавиши: <code>&lt;TAB&gt;</code> <code>&lt;ENTER&gt;</code> <code>&lt;ESC&gt;</code>\n"
            f"ЛКМ: <code>&lt;CLICK:x,y&gt;</code>\n"
            f"ПКМ: <code>&lt;RCLICK:x,y&gt;</code>\n"
            f"2x:  <code>&lt;DBLCLICK:x,y&gt;</code>\n"
            f"AI:  просто пиши <code>AI: что сделать</code>",
            reply_markup=browser_control_kb(chat_id), parse_mode="HTML"
        )

    elif d.startswith("bc_key_"):
        chat_id = q.message.chat_id
        raw = d.replace("bc_key_", "")
        # Маппинг коротких алиасов на Playwright keys
        key_map = {
            "ctrla": "Control+a", "ctrlc": "Control+c",
            "ctrlv": "Control+v", "ctrlz": "Control+z",
        }
        key = key_map.get(raw, raw)
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        await page.keyboard.press(key)
        await asyncio.sleep(0.3)
        await bc_screenshot_and_send(chat_id, f"⌨️ {key}")

    elif d in ("bc_nav_home","bc_nav_login","bc_nav_server","bc_nav_back","bc_nav_reload","bc_nav_url"):
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        nav_map = {
            "bc_nav_home":   "https://aternos.org/",
            "bc_nav_login":  "https://aternos.org/go/",
            "bc_nav_server": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/servers/",
        }
        if d == "bc_nav_url":
            ctx.user_data["action"] = "bc_goto_url"
            await q.message.reply_text("✏️ <b>Введи URL:</b>\n<i>/cancel — отмена</i>", parse_mode="HTML"); return
        elif d == "bc_nav_back":
            await page.go_back(timeout=10000)
        elif d == "bc_nav_reload":
            await page.reload(wait_until="domcontentloaded", timeout=15000)
        elif d in nav_map:
            await page.goto(nav_map[d], wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(1)
        await bc_screenshot_and_send(chat_id)

    # ── МЫШЬ ─────────────────────────────────────────────────────
    elif d in ("bc_scroll_down","bc_scroll_up","bc_scroll_right"):
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        if d == "bc_scroll_down":  js = "window.scrollBy(0,400)"
        elif d == "bc_scroll_up":  js = "window.scrollBy(0,-400)"
        else:                      js = "window.scrollBy(400,0)"
        await page.evaluate(js)
        await asyncio.sleep(0.3)
        await bc_screenshot_and_send(chat_id, f"📜 {'↓' if 'down' in d else '↑' if 'up' in d else '→'}")

    elif d == "bc_click_xy":
        ctx.user_data["action"] = "bc_click"
        await q.message.reply_text(
            "🖱 <b>ЛКМ — введи координаты:</b>\n\nФормат: <code>x,y</code>\n"
            "Пример: <code>640,360</code>\n\n<i>/cancel — отмена</i>", parse_mode="HTML")

    elif d == "bc_rclick_xy":
        ctx.user_data["action"] = "bc_rclick"
        await q.message.reply_text(
            "🖱 <b>ПКМ — введи координаты:</b>\n\nФормат: <code>x,y</code>\n\n<i>/cancel — отмена</i>",
            parse_mode="HTML")

    elif d == "bc_dblclick_xy":
        ctx.user_data["action"] = "bc_dblclick"
        await q.message.reply_text(
            "🖱 <b>Двойной клик — введи координаты:</b>\n\nФормат: <code>x,y</code>\n\n<i>/cancel — отмена</i>",
            parse_mode="HTML")

    elif d == "bc_hover_xy":
        ctx.user_data["action"] = "bc_hover"
        await q.message.reply_text(
            "🔍 <b>Навести мышь — введи координаты:</b>\n\nФормат: <code>x,y</code>\n\n<i>/cancel — отмена</i>",
            parse_mode="HTML")

    elif d == "bc_drag_xy":
        ctx.user_data["action"] = "bc_drag"
        await q.message.reply_text(
            "↕ <b>Drag&Drop — введи координаты:</b>\n\n"
            "Формат: <code>x1,y1,x2,y2</code>\n"
            "Пример: <code>100,200,500,200</code>\n\n<i>/cancel — отмена</i>",
            parse_mode="HTML")

    # ── ИНСТРУМЕНТЫ ──────────────────────────────────────────────
    elif d == "bc_find_text":
        ctx.user_data["action"] = "bc_find"
        await q.message.reply_text(
            "🔎 <b>Найти текст на странице:</b>\n\nВведи текст для поиска\n<i>/cancel — отмена</i>",
            parse_mode="HTML")

    elif d == "bc_copy_text":
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        txt = await page.evaluate("() => document.body.innerText.slice(0,3000)")
        url = page.url
        await q.message.reply_text(
            f"📋 <b>Текст страницы:</b>\n🔗 <code>{url[:50]}</code>\n\n<code>{txt[:2000]}</code>",
            parse_mode="HTML")

    elif d == "bc_zoom_in":
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        await page.evaluate("document.body.style.zoom = (parseFloat(document.body.style.zoom||1)+0.25).toString()")
        await asyncio.sleep(0.3)
        await bc_screenshot_and_send(chat_id, "🔍+ Zoom in")

    elif d == "bc_zoom_out":
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        await page.evaluate("document.body.style.zoom = Math.max(0.25,(parseFloat(document.body.style.zoom||1)-0.25)).toString()")
        await asyncio.sleep(0.3)
        await bc_screenshot_and_send(chat_id, "🔍- Zoom out")

    elif d == "bc_fill_form":
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        # Автозаполнение логина/пароля если видим форму Aternos
        u_inp = await page.query_selector("input[name='user']")
        p_inp = await page.query_selector("input[name='password']")
        if u_inp and p_inp:
            w_sess = watch_sessions.get(chat_id, {})
            w_user = w_sess.get("w_user") or ATERNOS_USER
            w_pass = w_sess.get("w_pass") or ATERNOS_PASS
            if w_user:
                await u_inp.click(click_count=3)
                await page.type("input[name='user']", w_user, delay=60)
            if w_pass:
                await p_inp.click(click_count=3)
                await page.type("input[name='password']", w_pass, delay=60)
            await asyncio.sleep(0.3)
            await bc_screenshot_and_send(chat_id, "📝 Форма заполнена!")
        else:
            await q.answer("ℹ️ Форма логина не найдена на этой странице", show_alert=True)

    elif d == "bc_clear_cookies":
        chat_id = q.message.chat_id
        sess = browser_sessions.get(chat_id)
        if sess and sess.get("ctx"):
            await sess["ctx"].clear_cookies()
            login_cookies.clear()
            await q.message.edit_text("🧹 <b>Куки очищены!</b>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")
        else:
            await q.answer("❌ Браузер не запущен!", show_alert=True)

    # ── НОВЫЕ ФИЧИ ───────────────────────────────────────────────

    elif d == "bc_page_info":
        # Фича 1: Инфо о странице — размер, время загрузки, кол-во элементов
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        try:
            info = await page.evaluate("""() => ({
                title:    document.title,
                url:      location.href,
                elements: document.querySelectorAll('*').length,
                images:   document.images.length,
                links:    document.links.length,
                forms:    document.forms.length,
                inputs:   document.querySelectorAll('input,textarea,select').length,
                size:     document.documentElement.innerHTML.length,
                width:    window.innerWidth,
                height:   window.innerHeight,
            })""")
            await q.message.reply_text(
                f"📊 <b>Инфо страницы</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📄 <b>{info['title'][:50]}</b>\n"
                f"🔗 <code>{info['url'][:60]}</code>\n\n"
                f"🔢 Элементов: <b>{info['elements']}</b>\n"
                f"🖼 Картинок: <b>{info['images']}</b>\n"
                f"🔗 Ссылок: <b>{info['links']}</b>\n"
                f"📝 Форм: <b>{info['forms']}</b>\n"
                f"⌨️ Полей ввода: <b>{info['inputs']}</b>\n"
                f"📦 Размер HTML: <b>{info['size']//1024} КБ</b>\n"
                f"📐 Вьюпорт: <b>{info['width']}×{info['height']}</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            await q.message.reply_text(f"❌ <code>{e}</code>", parse_mode="HTML")

    elif d == "bc_mobile_toggle":
        # Фича 2: Переключение мобильный/десктоп режим
        chat_id = q.message.chat_id
        sess = browser_sessions.get(chat_id)
        if not sess or not sess.get("active"):
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        mobile = not sess.get("mobile", False)
        browser_sessions[chat_id]["mobile"] = mobile
        # Меняем viewport через JS
        if mobile:
            vp = {"width": 390, "height": 844}
            ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        else:
            vp = {"width": 1280, "height": 720}
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        try:
            page = sess["page"]
            await page.set_viewport_size(vp)
            await page.evaluate(f"Object.defineProperty(navigator,'userAgent',{{get:()=>'{ua}'}})")
            await page.reload(wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1)
            mode_txt = "📱 Мобильный (390×844)" if mobile else "🖥 Десктоп (1280×720)"
            await q.message.edit_text(f"✅ <b>Режим: {mode_txt}</b>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")
            await bc_screenshot_and_send(chat_id, f"{'📱' if mobile else '🖥'} {mode_txt}")
        except Exception as e:
            await q.message.reply_text(f"❌ <code>{e}</code>", parse_mode="HTML")

    elif d == "bc_dark_mode":
        # Фича 3: Dark mode — инжектируем CSS
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        try:
            await page.evaluate("""() => {
                const id = 'tg-dark-style';
                const existing = document.getElementById(id);
                if (existing) { existing.remove(); return false; }
                const style = document.createElement('style');
                style.id = id;
                style.textContent = `
                    * { background-color: #1a1a2e !important;
                        color: #e0e0e0 !important;
                        border-color: #444 !important; }
                    img, video { opacity: 0.85 !important; }
                    a { color: #7eb8f7 !important; }
                `;
                document.head.appendChild(style);
                return true;
            }""")
            await asyncio.sleep(0.3)
            await bc_screenshot_and_send(chat_id, "🌙 Dark mode")
            await q.message.edit_text("🌙 <b>Dark mode переключён!</b>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")
        except Exception as e:
            await q.message.reply_text(f"❌ <code>{e}</code>", parse_mode="HTML")

    elif d == "bc_click_text":
        # Фича 4: Клик по тексту — ищет элемент с таким текстом
        ctx.user_data["action"] = "bc_click_by_text"
        await q.message.reply_text(
            "🎯 <b>Клик по тексту</b>\n\n"
            "Введи текст кнопки/ссылки для клика:\n"
            "Пример: <code>Login</code> или <code>Start</code>\n\n"
            "<i>/cancel — отмена</i>", parse_mode="HTML")

    elif d == "bc_autosnap":
        # Фича 5: Авто-снап — периодические скриншоты
        chat_id = q.message.chat_id
        sess = browser_sessions.get(chat_id, {})
        task = sess.get("auto_snap_task")
        if task and not task.done():
            task.cancel()
            browser_sessions[chat_id]["auto_snap_task"] = None
            await q.message.edit_text("⏱ <b>Авто-снап выключен.</b>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")
        else:
            if not sess.get("active"):
                await q.answer("❌ Браузер не запущен!", show_alert=True); return
            ctx.user_data["action"] = "bc_autosnap_interval"
            await q.message.reply_text(
                "⏱ <b>Авто-снап</b>\n\nВведи интервал в секундах (10–300):\n"
                "Пример: <code>30</code>\n\n<i>/cancel — отмена</i>", parse_mode="HTML")

    elif d == "bc_snap_full":
        # Полный скриншот страницы
        chat_id = q.message.chat_id
        page = await bc_get_page(chat_id)
        if not page:
            await q.answer("❌ Браузер не запущен!", show_alert=True); return
        try:
            import io
            title = await page.title()
            shot  = await page.screenshot(full_page=True)
            bio   = io.BytesIO(shot); bio.name = "full.png"
            await telegram_app.bot.send_photo(
                chat_id, bio,
                caption=f"🖼 Полный скрин\n📄 {title[:50]}\n⏰ {now_str()}",
                parse_mode="HTML"
            )
            await q.message.edit_text("🖼 <b>Полный скриншот отправлен!</b>", reply_markup=browser_control_kb(chat_id), parse_mode="HTML")
        except Exception as e:
            await q.message.reply_text(f"❌ <code>{e}</code>", parse_mode="HTML")

    # ── ИИ ───────────────────────────────────────────────────────
    elif d == "bc_ai_login":
        chat_id = q.message.chat_id
        w_sess = watch_sessions.get(chat_id, {})
        w_user = w_sess.get("w_user") or ATERNOS_USER
        w_pass = w_sess.get("w_pass") or ATERNOS_PASS
        asyncio.create_task(bc_do_ai_action(
            chat_id,
            f"Залогинься на aternos.org. Логин: {w_user}, Пароль: {w_pass}. "
            f"Открой https://aternos.org/go/, введи данные в поля user и password, нажми кнопку Login."
        ))

    elif d == "bc_ai_custom":
        ctx.user_data["action"] = "bc_ai"
        await q.message.reply_text(
            "🤖 <b>Что сделать ИИ?</b>\n\n"
            "Примеры:\n"
            "• <code>залогинься на Aternos</code>\n"
            "• <code>запусти сервер fictionmine</code>\n"
            "• <code>сделай скрин консоли</code>\n"
            "• <code>нажми на кнопку Start</code>\n\n"
            "<i>/cancel — отмена</i>",
            parse_mode="HTML"
        )

    elif d == "adm_broadcast":
        ctx.user_data["action"] = "broadcast"
        await q.message.reply_text("📢 <b>Напиши сообщение для всех:</b>\n<i>/cancel — отмена</i>", parse_mode="HTML")

    elif d == "adm_announce":
        ctx.user_data["action"] = "announce"
        await q.message.reply_text("📣 <b>Напиши текст анонса:</b>\n<i>/cancel — отмена</i>", parse_mode="HTML")

    elif d == "adm_users":
        if not users:
            await q.message.edit_text("👥 Нет пользователей", reply_markup=admin_kb(), parse_mode="HTML")
            return
        lines = []
        for uid, info in list(users.items())[-15:]:
            n = info.get("first_name", "???")
            u = f"@{info['username']}" if info.get("username") else "—"
            w = warns.get(uid, 0)
            ma = "🔐" if int(uid) in admins else ""
            ba = "🚫" if int(uid) in banned else ""
            wm = f" ⚠️{w}" if w else ""
            try:
                seen = datetime.fromisoformat(info.get("last_seen", "")).strftime("%d.%m %H:%M")
            except:
                seen = "—"
            lines.append(f"• {n} {u}{ma}{ba}{wm} <i>{seen}</i>")
        await q.message.edit_text(f"👥 <b>ПОЛЬЗОВАТЕЛИ ({len(users)})</b>\n\n" + "\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_warns":
        if not warns:
            await q.message.edit_text("⚠️ Варнов нет", reply_markup=admin_kb(), parse_mode="HTML")
            return
        lines = []
        for uid, cnt in warns.items():
            info = users.get(uid, {})
            u = f"@{info.get('username', '')}" if info.get("username") else f"ID:{uid}"
            lines.append(f"• {info.get('first_name', '???')} {u} — ⚠️{cnt}/3")
        await q.message.edit_text("⚠️ <b>ВАРНЫ</b>\n\n" + "\n".join(lines), reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_warn_give":
        ctx.user_data["action"] = "warn"
        await q.message.reply_text("⚠️ <b>Напиши @username для варна:</b>", parse_mode="HTML")

    elif d == "adm_ban":
        ctx.user_data["action"] = "ban"
        await q.message.reply_text("🚫 <b>Напиши @username для бана:</b>", parse_mode="HTML")

    elif d == "adm_maintenance":
        config["maintenance"] = not config.get("maintenance", False)
        save_all()
        w = "ВКЛ 🟡" if config["maintenance"] else "ВЫКЛ 🟢"
        await q.message.edit_text(f"🔧 <b>Техроботы {w}</b>", reply_markup=admin_kb(), parse_mode="HTML")
        await send_log(f"🔧 Техроботы {w}\n👤 {ulabel(update)}")

    elif d == "adm_toggle_start":
        config["allow_all_start"] = not config.get("allow_all_start", True)
        save_all()
        w = "ВСЕ могут ✅" if config["allow_all_start"] else "Только АДМИНЫ 🔐"
        await q.message.edit_text(f"⚙️ <b>Запуск: {w}</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_setmotd":
        ctx.user_data["action"] = "setmotd"
        await q.message.reply_text("✏️ <b>Напиши новый MOTD:</b>", parse_mode="HTML")

    elif d == "adm_setseed":
        ctx.user_data["action"] = "setseed"
        await q.message.reply_text("🌍 <b>Напиши сид мира:</b>", parse_mode="HTML")

    elif d == "adm_setshop":
        ctx.user_data["action"] = "setshop"
        await q.message.reply_text("🛒 <b>Напиши ссылку на магазин:</b>", parse_mode="HTML")

    elif d == "adm_notes":
        ctx.user_data["action"] = "note"
        if not notes:
            await q.message.edit_text("📝 <b>Заметок нет</b>\n\nНапиши заметку:", reply_markup=admin_kb(), parse_mode="HTML")
        else:
            lines = [f"{i+1}. {n}" for i, n in enumerate(notes[-10:])]
            await q.message.edit_text("📝 <b>ЗАМЕТКИ</b>\n\n" + "\n".join(lines) + "\n\n<i>Напиши новую заметку или /cancel</i>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_stats":
        await update_server_info()
        ls = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "—"
        lo = datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M") if stats.get("last_stop") else "—"
        await q.message.edit_text(
            f"📊 <b>ПОЛНАЯ СТАТИСТИКА</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Запусков: {stats['starts']}\n"
            f"🛑 Остановок: {stats['stops']}\n"
            f"🔄 Перезапусков: {stats.get('restarts', 0)}\n"
            f"👑 Рекорд игроков: {stats['peak_players']}\n"
            f"⏱ Аптайм: {get_uptime()}\n"
            f"💬 Команд: {stats.get('total_commands', 0)}\n"
            f"👤 Юзеров: {len(users)}\n"
            f"⚠️ Варнов выдано: {sum(warns.values())}\n"
            f"🚫 Забанено: {len(banned)}\n\n"
            f"▶️ {ls} | ⏹ {lo}\n⏰ {now_full()}",
            reply_markup=admin_kb(),
            parse_mode="HTML",
        )

    elif d == "adm_resetstats":
        stats.update(
            {
                "starts": 0,
                "stops": 0,
                "restarts": 0,
                "last_start": None,
                "last_stop": None,
                "uptime_from": None,
                "peak_players": 0,
                "total_commands": 0,
            }
        )
        save_all()
        await q.message.edit_text("🗑 <b>Статистика сброшена!</b>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_setlog":
        config["log_chat_id"] = q.message.chat_id
        save_all()
        await q.message.edit_text(f"✅ <b>Логи здесь!</b>\nID: <code>{q.message.chat_id}</code>", reply_markup=admin_kb(), parse_mode="HTML")

    elif d == "adm_exit":
        await q.message.edit_text("👋 <b>Панель закрыта.</b>", parse_mode="HTML")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not reg(update):
        return
    action = ctx.user_data.get("action")
    if not action:
        return
    if not is_admin(update):
        return
    text = update.message.text.strip()
    if text == "/cancel":
        ctx.user_data["action"] = None
        await update.message.reply_text(f"❌ {t('cancelled')}")
        return

    if action == "broadcast":
        ctx.user_data["action"] = None
        msg_text = f"📢 <b>ОБЪЯВЛЕНИЕ — {config['server_name']}</b>\n\n{text}\n\n<i>— Администрация</i>"
        sent = fail = 0
        sm = await update.message.reply_text("⏳ Отправляю...", parse_mode="HTML")
        for uid in list(users.keys()):
            if int(uid) not in banned:
                try:
                    await telegram_app.bot.send_message(int(uid), msg_text, parse_mode="HTML")
                    sent += 1
                    await asyncio.sleep(0.05)
                except:
                    fail += 1
        await sm.edit_text(f"📢 <b>Готово!</b>\n✅ {sent} | ❌ {fail}", parse_mode="HTML")
        await send_log(f"📢 <b>БРОАДКАСТ</b>\n👤 {ulabel(update)}\n✅{sent}/❌{fail}")

    elif action == "announce":
        ctx.user_data["action"] = None
        msg_text = f"📣 <b>━━━━━━━━━━━━━━━━━━━━━━</b>\n🎮 <b>{config['server_name'].upper()}</b>\n\n{text}\n\n<b>━━━━━━━━━━━━━━━━━━━━━━</b>"
        sent = fail = 0
        sm = await update.message.reply_text("⏳ Отправляю...", parse_mode="HTML")
        for uid in list(users.keys()):
            if int(uid) not in banned:
                try:
                    await telegram_app.bot.send_message(int(uid), msg_text, parse_mode="HTML")
                    sent += 1
                    await asyncio.sleep(0.05)
                except:
                    fail += 1
        await sm.edit_text(f"📣 <b>Анонс отправлен!</b>\n✅ {sent} | ❌ {fail}", parse_mode="HTML")

    elif action == "setmotd":
        ctx.user_data["action"] = None
        config["motd"] = text
        save_all()
        await update.message.reply_text(f"✅ <b>MOTD обновлен!</b>\n\n{text}", parse_mode="HTML")

    elif action == "setseed":
        ctx.user_data["action"] = None
        config["world_seed"] = text
        save_all()
        await update.message.reply_text(f"✅ <b>Сід установлен:</b> <code>{text}</code>", parse_mode="HTML")

    elif action == "setshop":
        ctx.user_data["action"] = None
        config["shop_link"] = text
        save_all()
        await update.message.reply_text(f"✅ <b>Магазин:</b> {text}", parse_mode="HTML")

    elif action == "note":
        ctx.user_data["action"] = None
        notes.append(f"[{now_str()}] {text}")
        save_all()
        await update.message.reply_text("📝 <b>Заметка сохранена!</b>", parse_mode="HTML")

    elif action == "warn":
        ctx.user_data["action"] = None
        target = text.lstrip("@")
        uid = next((u for u, i in users.items() if i.get("username", "").lower() == target.lower()), None)
        if not uid:
            await update.message.reply_text(f"❌ @{target} не найден!", parse_mode="HTML")
            return
        warns[uid] = warns.get(uid, 0) + 1
        save_all()
        await update.message.reply_text(f"⚠️ <b>Варн выдан!</b>\n👤 @{target}\n⚠️ {warns[uid]}/3", parse_mode="HTML")
        await send_log(f"⚠️ <b>ВАРН</b>\n👤 @{target}\n⚠️ {warns[uid]}/3\n👮 {ulabel(update)}")

    elif action == "ban":
        ctx.user_data["action"] = None
        target = text.lstrip("@")
        uid = next((u for u, i in users.items() if i.get("username", "").lower() == target.lower()), None)
        if not uid:
            await update.message.reply_text(f"❌ @{target} не найден!", parse_mode="HTML")
            return
        banned.add(int(uid))
        save_all()
        await update.message.reply_text(f"🚫 <b>ЗАБАНЕН!</b>\n👤 @{target}", parse_mode="HTML")
        await send_log(f"🚫 <b>БАН</b>\n👤 @{target}\n👮 {ulabel(update)}")

    elif action == "set_cookie":
        ctx.user_data["action"] = None
        global http_session, aternos_connected, login_cookies
        new_cookies = {}
        text_stripped = text.strip()
        # Парсимо JSON
        if text_stripped.startswith("{"):
            try:
                new_cookies = json.loads(text_stripped)
            except Exception as e:
                await update.message.reply_text(f"❌ Помилка JSON: <code>{e}</code>", parse_mode="HTML")
                return
        else:
            # Парсимо рядок типу "NAME=value; NAME2=value2"
            for part in text_stripped.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    new_cookies[k.strip()] = v.strip()
        if not new_cookies:
            await update.message.reply_text("❌ Не вдалося розпарсити куки!", parse_mode="HTML")
            return
        # Оновлюємо сесію
        login_cookies.update(new_cookies)
        jar = aiohttp.CookieJar()
        for name, val in login_cookies.items():
            from yarl import URL as yarl_URL
            jar.update_cookies({name: val}, response_url=yarl_URL("https://aternos.org/"))
        if http_session and not http_session.closed:
            await http_session.close()
        http_session = aiohttp.ClientSession(
            cookie_jar=jar,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        aternos_connected = True
        important = ["ATERNOS_SESSION", "ATERNOS_SEC", "PHPSESSID"]
        found = [k for k in important if k in login_cookies]
        await update.message.reply_text(
            f"✅ <b>Куки встановлені!</b>\n\n"
            f"🍪 Всього: <b>{len(login_cookies)}</b>\n"
            f"✅ Важливі: <b>{', '.join(found) if found else 'не знайдено!'}</b>\n\n"
            f"<i>Тепер спробуй 🔍 Діагностика</i>",
            parse_mode="HTML"
        )
        await send_log(f"🍪 <b>КУКИ ОНОВЛЕНІ</b>\n👤 {ulabel(update)}\n🍪 {len(login_cookies)} шт.")

    elif action == "watch_url":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        url = text.strip() if text.strip() else (f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/")
        if chat_id not in watch_sessions:
            watch_sessions[chat_id] = {"interval": 20, "auto_login": True}
        watch_sessions[chat_id]["url"] = url
        await update.message.reply_text(f"✅ <b>URL встановлено:</b>\n<code>{url}</code>", parse_mode="HTML")
        await show_watch_panel(update, update.message)

    elif action == "watch_user":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        if chat_id not in watch_sessions:
            watch_sessions[chat_id] = {"interval": 20, "auto_login": False, "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"}
        watch_sessions[chat_id]["w_user"] = text.strip()
        watch_sessions[chat_id]["auto_login"] = False
        await update.message.reply_text(
            f"✅ <b>Логін збережено!</b>\n👤 <code>{text.strip()}</code>\n\n"
            f"Режим автоматично переключено на ✋ Вручну",
            parse_mode="HTML"
        )
        await show_watch_panel(update, update.message)

    elif action == "watch_pass":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        if chat_id not in watch_sessions:
            watch_sessions[chat_id] = {"interval": 20, "auto_login": False, "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"}
        watch_sessions[chat_id]["w_pass"] = text.strip()
        watch_sessions[chat_id]["auto_login"] = False
        await update.message.reply_text(
            f"✅ <b>Пароль збережено!</b>\n🔐 {'*' * min(len(text.strip()), 8)}\n\n"
            f"Режим автоматично переключено на ✋ Вручну",
            parse_mode="HTML"
        )
        await show_watch_panel(update, update.message)

    elif action == "watch_speed":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        try:
            spd = int(text.strip())
            spd = max(5, min(300, spd))
        except:
            await update.message.reply_text("❌ Введи число від 5 до 300!", parse_mode="HTML")
            return
        if chat_id not in watch_sessions:
            watch_sessions[chat_id] = {"interval": spd, "auto_login": True, "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"}
        else:
            watch_sessions[chat_id]["interval"] = spd
        await update.message.reply_text(f"⚡ <b>Швидкість: {spd} сек</b>", parse_mode="HTML")
        await show_watch_panel(update, update.message)

    elif action == "bc_goto_url":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        page = await bc_get_page(chat_id)
        if not page:
            await update.message.reply_text("❌ Браузер не запущено!", parse_mode="HTML")
            return
        url = text.strip()
        if not url.startswith("http"):
            url = "https://" + url
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(1)
        await bc_screenshot_and_send(chat_id, f"🔗 Перейшов: {url}")

    elif action == "bc_click":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        page = await bc_get_page(chat_id)
        if not page:
            await update.message.reply_text("❌ Браузер не запущено!", parse_mode="HTML")
            return
        try:
            parts = text.strip().split(",")
            x, y = int(parts[0].strip()), int(parts[1].strip())
            await page.mouse.click(x, y)
            await asyncio.sleep(0.5)
            await bc_screenshot_and_send(chat_id, f"🖱 Клік: {x},{y}")
        except Exception as e:
            await update.message.reply_text(f"❌ Формат: <code>x,y</code>\nПомилка: {e}", parse_mode="HTML")

    elif action == "bc_click_by_text":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        page = await bc_get_page(chat_id)
        if not page:
            await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML"); return
        query = text.strip()
        try:
            # Ищем элемент с таким текстом и кликаем
            clicked = await page.evaluate(f"""(txt) => {{
                const els = [...document.querySelectorAll('button,a,input[type=submit],[role=button]')];
                const el = els.find(e => e.innerText.trim().toLowerCase().includes(txt.toLowerCase())
                                      || e.value?.toLowerCase().includes(txt.toLowerCase()));
                if (el) {{ el.scrollIntoView({{block:'center'}}); el.click(); return el.tagName+': '+el.innerText.trim().slice(0,30); }}
                return null;
            }}""", query)
            if clicked:
                await asyncio.sleep(0.8)
                await bc_screenshot_and_send(chat_id, f"🎯 Клик: «{query}» → {clicked}")
            else:
                await update.message.reply_text(f"🎯 Элемент «{query}» <b>не найден</b>", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ <code>{e}</code>", parse_mode="HTML")

    elif action == "bc_autosnap_interval":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        try:
            interval = max(10, min(300, int(text.strip())))
        except:
            await update.message.reply_text("❌ Введи число от 10 до 300", parse_mode="HTML"); return
        if chat_id not in browser_sessions:
            await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML"); return
        browser_sessions[chat_id]["auto_snap_interval"] = interval
        task = asyncio.create_task(_bc_autosnap_loop(chat_id, interval))
        browser_sessions[chat_id]["auto_snap_task"] = task
        await update.message.reply_text(
            f"⏱ <b>Авто-снап запущен!</b>\n📸 Каждые {interval} сек\n"
            f"Остановить: /browser → кнопка ⏱",
            parse_mode="HTML"
        )

    elif action in ("bc_rclick", "bc_dblclick", "bc_hover"):
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        page = await bc_get_page(chat_id)
        if not page:
            await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML")
            return
        try:
            parts = text.strip().split(",")
            x, y = int(parts[0].strip()), int(parts[1].strip())
            if action == "bc_rclick":
                await page.mouse.click(x, y, button="right")
                label = f"🖱 ПКМ: {x},{y}"
            elif action == "bc_dblclick":
                await page.mouse.dblclick(x, y)
                label = f"🖱 2x клик: {x},{y}"
            else:
                await page.mouse.move(x, y)
                label = f"🔍 Hover: {x},{y}"
            await asyncio.sleep(0.5)
            await bc_screenshot_and_send(chat_id, label)
        except Exception as e:
            await update.message.reply_text(f"❌ Формат: <code>x,y</code>\n{e}", parse_mode="HTML")

    elif action == "bc_drag":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        page = await bc_get_page(chat_id)
        if not page:
            await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML")
            return
        try:
            parts = [int(p.strip()) for p in text.strip().split(",")]
            x1, y1, x2, y2 = parts[0], parts[1], parts[2], parts[3]
            await page.mouse.move(x1, y1)
            await page.mouse.down()
            await asyncio.sleep(0.2)
            # Плавно переміщаємо
            steps = 10
            for i in range(1, steps + 1):
                mx = x1 + (x2 - x1) * i // steps
                my = y1 + (y2 - y1) * i // steps
                await page.mouse.move(mx, my)
                await asyncio.sleep(0.02)
            await page.mouse.up()
            await asyncio.sleep(0.4)
            await bc_screenshot_and_send(chat_id, f"↕ Drag: {x1},{y1} → {x2},{y2}")
        except Exception as e:
            await update.message.reply_text(f"❌ Формат: <code>x1,y1,x2,y2</code>\n{e}", parse_mode="HTML")

    elif action == "bc_find":
        ctx.user_data["action"] = None
        chat_id = update.effective_chat.id
        page = await bc_get_page(chat_id)
        if not page:
            await update.message.reply_text("❌ Браузер не запущен!", parse_mode="HTML")
            return
        query = text.strip()
        try:
            # Ctrl+F через JS (highlight всіх входжень)
            count = await page.evaluate(f"""
                () => {{
                    const results = [];
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_TEXT
                    );
                    let node;
                    while (node = walker.nextNode()) {{
                        if (node.textContent.toLowerCase().includes({json.dumps(query.lower())})) {{
                            results.push(node.parentElement?.tagName + ': ' +
                                node.textContent.trim().slice(0, 60));
                        }}
                    }}
                    return results.slice(0, 10);
                }}
            """)
            if count:
                lines = "\n".join(f"• <code>{c}</code>" for c in count)
                await update.message.reply_text(
                    f"🔎 <b>Найдено «{query}»: {len(count)} раз</b>\n\n{lines}",
                    parse_mode="HTML"
                )
                # Скролимо до першого входження
                await page.evaluate(f"""
                    () => {{
                        const el = document.evaluate(
                            "//*[contains(text(),{json.dumps(query)})]",
                            document, null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE, null
                        ).singleNodeValue;
                        if (el) el.scrollIntoView({{block:'center'}});
                    }}
                """)
                await asyncio.sleep(0.3)
                await bc_screenshot_and_send(chat_id, f"🔎 «{query}»")
            else:
                await update.message.reply_text(f"🔎 «{query}» — <b>не найдено</b>", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ <code>{e}</code>", parse_mode="HTML")


async def _bc_autosnap_loop(chat_id: int, interval: int):
    """Авто-снап: скриншот каждые N секунд."""
    count = 0
    try:
        while True:
            await asyncio.sleep(interval)
            page = await bc_get_page(chat_id)
            if not page:
                break
            count += 1
            await bc_screenshot_and_send(chat_id, f"⏱ Авто-снап #{count} | каждые {interval}с\n⏰ {now_full()}")
    except asyncio.CancelledError:
        await telegram_app.bot.send_message(
            chat_id,
            f"⏱ <b>Авто-снап остановлен.</b> Сделано {count} скриншотов.",
            parse_mode="HTML"
        )


async def handle_browser_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Перехватывает текст в режиме управления браузером."""
    if not reg(update):
        return
    chat_id = update.effective_chat.id
    text = update.message.text or ""

    # AI режим
    if text.upper().startswith("AI:"):
        asyncio.create_task(bc_do_ai_action(chat_id, text[3:].strip()))
        return

    page = await bc_get_page(chat_id)
    if not page:
        await update.message.reply_text(
            "❌ <b>Браузер не запущен!</b>\nИспользуй /browser → 🚀 Запустить",
            parse_mode="HTML"
        )
        return

    try:
        import re
        tokens = re.split(r'(<[^>]+>)', text)
        done = []

        for tok in tokens:
            if not tok:
                continue
            up = tok.upper()

            # ── Спецклавиши ─────────────────────────────────────
            if up in SPECIAL_KEYS:
                await page.keyboard.press(SPECIAL_KEYS[up])
                done.append(f"⌨️ {tok}")
                await asyncio.sleep(0.1)

            # ── ЛКМ <CLICK:x,y> ─────────────────────────────────
            elif up.startswith("<CLICK:"):
                x, y = [int(v.strip()) for v in tok[7:-1].split(",")]
                await page.mouse.click(x, y)
                done.append(f"🖱 ЛКМ({x},{y})")
                await asyncio.sleep(0.3)

            # ── ПКМ <RCLICK:x,y> ────────────────────────────────
            elif up.startswith("<RCLICK:"):
                x, y = [int(v.strip()) for v in tok[8:-1].split(",")]
                await page.mouse.click(x, y, button="right")
                done.append(f"🖱 ПКМ({x},{y})")
                await asyncio.sleep(0.3)

            # ── 2x клик <DBLCLICK:x,y> ──────────────────────────
            elif up.startswith("<DBLCLICK:"):
                x, y = [int(v.strip()) for v in tok[10:-1].split(",")]
                await page.mouse.dblclick(x, y)
                done.append(f"🖱 2x({x},{y})")
                await asyncio.sleep(0.3)

            # ── Hover <HOVER:x,y> ───────────────────────────────
            elif up.startswith("<HOVER:"):
                x, y = [int(v.strip()) for v in tok[7:-1].split(",")]
                await page.mouse.move(x, y)
                done.append(f"🔍 hover({x},{y})")
                await asyncio.sleep(0.2)

            # ── Drag <DRAG:x1,y1,x2,y2> ─────────────────────────
            elif up.startswith("<DRAG:"):
                x1, y1, x2, y2 = [int(v.strip()) for v in tok[6:-1].split(",")]
                await page.mouse.move(x1, y1)
                await page.mouse.down()
                for i in range(1, 11):
                    await page.mouse.move(
                        x1 + (x2 - x1) * i // 10,
                        y1 + (y2 - y1) * i // 10
                    )
                    await asyncio.sleep(0.02)
                await page.mouse.up()
                done.append(f"↕ drag({x1},{y1}→{x2},{y2})")
                await asyncio.sleep(0.3)

            # ── Скрол <SCROLL:down/up/N> ────────────────────────
            elif up.startswith("<SCROLL:"):
                val = tok[8:-1].strip().lower()
                dy = -400 if val == "up" else (400 if val == "down" else int(val))
                await page.evaluate(f"window.scrollBy(0,{dy})")
                done.append(f"📜 scroll({dy})")
                await asyncio.sleep(0.2)

            # ── Пауза <WAIT:ms> ──────────────────────────────────
            elif up.startswith("<WAIT:"):
                ms = int(tok[6:-1].strip())
                await asyncio.sleep(min(ms, 10000) / 1000)
                done.append(f"⏱ wait({ms}ms)")

            # ── Обычный текст ────────────────────────────────────
            elif not tok.startswith("<"):
                await page.keyboard.type(tok, delay=50)
                done.append(f"✍️ «{tok[:20]}»")

        await asyncio.sleep(0.4)
        summary = "  ".join(done) if done else "✍️ введено"
        await bc_screenshot_and_send(chat_id, f"{summary}\n⏰ {now_str()}")

    except Exception as e:
        await update.message.reply_text(
            f"❌ <code>{str(e)[:200]}</code>", parse_mode="HTML"
        )

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    fns = {
        "on": cmd_on,
        "players": cmd_players,
        "status": cmd_status,
        "info": cmd_info,
        "connect": cmd_connect,
        "rules": cmd_rules,
        "random": cmd_random,
        "top": cmd_top,
        "seed": cmd_seed,
        "vote": cmd_vote,
        "shop": cmd_shop,
        "uptime": cmd_uptime,
        "motd": cmd_motd,
    }
    fn = fns.get(q.data)
    if fn:
        await fn(update, ctx)

async def _get_watch_browser_ctx(p, sess: dict):
    """Запускає браузер і логіниться (авто або ручний режим)."""
    from playwright.async_api import async_playwright
    browser = await p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
              "--disable-blink-features=AutomationControlled"]
    )
    bctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720},
        locale="en-US",
    )
    await bctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    )
    # Якщо є куки — підставляємо
    if login_cookies:
        for name, val in login_cookies.items():
            await bctx.add_cookies([{"name": name, "value": val, "domain": "aternos.org", "path": "/"}])
    return browser, bctx


async def _watch_do_login(page, bctx, sess: dict) -> bool:
    """Логін через Playwright. Повертає True якщо успіх."""
    auto = sess.get("auto_login", True)
    w_user = sess.get("w_user") or ATERNOS_USER
    w_pass = sess.get("w_pass") or ATERNOS_PASS
    if not w_user or not w_pass:
        return False
    try:
        await page.goto("https://aternos.org/go/", wait_until="domcontentloaded", timeout=30000)
        # Чекаємо форму (до 20 сек)
        for _ in range(20):
            await asyncio.sleep(1)
            if await page.query_selector("input[name='user']"):
                break
        user_inp = await page.query_selector("input[name='user']")
        pass_inp = await page.query_selector("input[name='password']")
        if not user_inp or not pass_inp:
            return False
        await user_inp.click()
        for ch in w_user:
            await page.type("input[name='user']", ch, delay=random.randint(40, 90))
        await asyncio.sleep(0.2)
        await pass_inp.click()
        for ch in w_pass:
            await page.type("input[name='password']", ch, delay=random.randint(40, 90))
        await asyncio.sleep(0.3)
        for sel in ["button[type='submit']", "button:has-text('Login')", ".login-button"]:
            btn = await page.query_selector(sel)
            if btn:
                await btn.click()
                break
        await asyncio.sleep(4)
        # Зберігаємо нові куки
        new_cookies = await bctx.cookies()
        for c in new_cookies:
            login_cookies[c["name"]] = c["value"]
        return True
    except Exception as e:
        log.error(f"watch_login: {e}")
        return False



# ══════════════════════════════════════════════════════════════════
# REMOTE BROWSER CONTROL
# ══════════════════════════════════════════════════════════════════

SPECIAL_KEYS = {
    "<TAB>": "Tab", "<ENTER>": "Enter", "<ESC>": "Escape",
    "<SPACE>": "Space", "<BACKSPACE>": "Backspace", "<DELETE>": "Delete",
    "<UP>": "ArrowUp", "<DOWN>": "ArrowDown", "<LEFT>": "ArrowLeft", "<RIGHT>": "ArrowRight",
    "<HOME>": "Home", "<END>": "End", "<PGUP>": "PageUp", "<PGDN>": "PageDown",
    "<F1>": "F1", "<F2>": "F2", "<F5>": "F5", "<F12>": "F12",
    "<CTRL+A>": "Control+a", "<CTRL+C>": "Control+c", "<CTRL+V>": "Control+v",
    "<CTRL+Z>": "Control+z", "<CTRL+R>": "Control+r", "<CTRL+X>": "Control+x",
    "<ALT+F4>": "Alt+F4", "<SHIFT+TAB>": "Shift+Tab",
    "<WIN>": "Meta", "<CAPS>": "CapsLock",
}

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-2.0-flash"
GEMINI_URL     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

def browser_control_kb(chat_id: int):
    sess    = browser_sessions.get(chat_id, {})
    active  = sess.get("active", False)
    inp_on  = chat_id in browser_control_mode
    mobile  = sess.get("mobile", False)
    ai_src  = "Gemini 🆓" if GEMINI_API_KEY else "нет ключа"
    auto_sn = sess.get("auto_snap_task") and not sess["auto_snap_task"].done() if sess.get("auto_snap_task") else False
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'🟢 Браузер активен' if active else '🔴 Браузер не запущен'}",
            callback_data="noop")],
        [InlineKeyboardButton("🚀 Запустить",  callback_data="bc_start"),
         InlineKeyboardButton("🔄 Рестарт",   callback_data="bc_restart"),
         InlineKeyboardButton("🛑 Закрыть",   callback_data="bc_close")],
        # ── КЛАВИШИ ──────────────────────────────────────────────
        [InlineKeyboardButton("━━━ ⌨️ КЛАВИШИ ━━━", callback_data="noop")],
        [InlineKeyboardButton("TAB",   callback_data="bc_key_Tab"),
         InlineKeyboardButton("ENTER", callback_data="bc_key_Enter"),
         InlineKeyboardButton("ESC",   callback_data="bc_key_Escape"),
         InlineKeyboardButton("⌫",     callback_data="bc_key_Backspace")],
        [InlineKeyboardButton("▲", callback_data="bc_key_ArrowUp"),
         InlineKeyboardButton("▼", callback_data="bc_key_ArrowDown"),
         InlineKeyboardButton("◀", callback_data="bc_key_ArrowLeft"),
         InlineKeyboardButton("▶", callback_data="bc_key_ArrowRight")],
        [InlineKeyboardButton("F5",     callback_data="bc_key_F5"),
         InlineKeyboardButton("Ctrl+A", callback_data="bc_key_ctrla"),
         InlineKeyboardButton("Ctrl+C", callback_data="bc_key_ctrlc"),
         InlineKeyboardButton("Ctrl+V", callback_data="bc_key_ctrlv")],
        # ── МЫШЬ ─────────────────────────────────────────────────
        [InlineKeyboardButton("━━━ 🖱 МЫШЬ ━━━", callback_data="noop")],
        [InlineKeyboardButton("🖱 ЛКМ",  callback_data="bc_click_xy"),
         InlineKeyboardButton("🖱 ПКМ",  callback_data="bc_rclick_xy"),
         InlineKeyboardButton("🖱 2×кл", callback_data="bc_dblclick_xy")],
        [InlineKeyboardButton("🔍 Hover",     callback_data="bc_hover_xy"),
         InlineKeyboardButton("↕ Drag",       callback_data="bc_drag_xy"),
         InlineKeyboardButton("🎯 Кл.по тексту", callback_data="bc_click_text")],
        [InlineKeyboardButton("📜 ↓",  callback_data="bc_scroll_down"),
         InlineKeyboardButton("📜 ↑",  callback_data="bc_scroll_up"),
         InlineKeyboardButton("📜 →",  callback_data="bc_scroll_right")],
        # ── НАВИГАЦИЯ ─────────────────────────────────────────────
        [InlineKeyboardButton("━━━ 🗺 НАВИГАЦИЯ ━━━", callback_data="noop")],
        [InlineKeyboardButton("🏠 Главная", callback_data="bc_nav_home"),
         InlineKeyboardButton("🔑 Логин",   callback_data="bc_nav_login"),
         InlineKeyboardButton("🖥 Сервер",  callback_data="bc_nav_server")],
        [InlineKeyboardButton("◀️ Назад",   callback_data="bc_nav_back"),
         InlineKeyboardButton("🔄 Reload",  callback_data="bc_nav_reload"),
         InlineKeyboardButton("✏️ URL",     callback_data="bc_nav_url")],
        # ── ИНСТРУМЕНТЫ ───────────────────────────────────────────
        [InlineKeyboardButton("━━━ 🔧 ИНСТРУМЕНТЫ ━━━", callback_data="noop")],
        [InlineKeyboardButton("🔎 Найти",       callback_data="bc_find_text"),
         InlineKeyboardButton("📋 Копир.текст", callback_data="bc_copy_text"),
         InlineKeyboardButton("📊 Инфо страниц", callback_data="bc_page_info")],
        [InlineKeyboardButton("🖼 Полный скрин", callback_data="bc_snap_full"),
         InlineKeyboardButton("🔍+",             callback_data="bc_zoom_in"),
         InlineKeyboardButton("🔍-",             callback_data="bc_zoom_out"),
         InlineKeyboardButton("📱" + (" ✅" if mobile else ""), callback_data="bc_mobile_toggle")],
        [InlineKeyboardButton("📝 Заполнить форму", callback_data="bc_fill_form"),
         InlineKeyboardButton("🧹 Куки",            callback_data="bc_clear_cookies"),
         InlineKeyboardButton("🌙 Dark mode",        callback_data="bc_dark_mode")],
        [InlineKeyboardButton(
            f"⏱ Авто-снап: {'🟢 ' + str(sess.get('auto_snap_interval',30)) + 'с' if auto_sn else '🔴 выкл'}",
            callback_data="bc_autosnap")],
        # ── ВВОД ──────────────────────────────────────────────────
        [InlineKeyboardButton("━━━ ✍️ ВВОД ━━━", callback_data="noop")],
        [InlineKeyboardButton(
            "⌨️ Режим ввода: " + ("🟢 ВКЛ" if inp_on else "🔴 ВЫКЛ"),
            callback_data="bc_toggle_input")],
        # ── ИИ ────────────────────────────────────────────────────
        [InlineKeyboardButton(f"━━━ 🤖 ИИ ({ai_src}) ━━━", callback_data="noop")],
        [InlineKeyboardButton("🤖 Залогиниться",  callback_data="bc_ai_login"),
         InlineKeyboardButton("🤖 Задача...",     callback_data="bc_ai_custom")],
        # ── НИЗ ───────────────────────────────────────────────────
        [InlineKeyboardButton("📸 Скриншот", callback_data="bc_snap"),
         InlineKeyboardButton("🔙 /admin",   callback_data="watch_back_admin")],
    ])


async def bc_get_page(chat_id: int):
    """Возвращает активную страницу или None. Проверяет что страница жива."""
    sess = browser_sessions.get(chat_id)
    if not sess or not sess.get("active"):
        return None
    page = sess.get("page")
    if page is None:
        return None
    try:
        # Проверяем что страница ещё жива
        if page.is_closed():
            browser_sessions[chat_id]["active"] = False
            return None
    except:
        return None
    return page


async def bc_screenshot_and_send(chat_id: int, caption: str = ""):
    """Делает скриншот и отправляет в чат. Использует BytesIO для совместимости с PTB v21."""
    import io
    page = await bc_get_page(chat_id)
    if not page:
        await telegram_app.bot.send_message(
            chat_id,
            "❌ <b>Браузер не запущен.</b>\nНажми /browser → 🚀 Запустить",
            parse_mode="HTML"
        )
        return
    try:
        title  = await page.title()
        url    = page.url
        shot   = await page.screenshot(full_page=False)
        # PTB v21 требует BytesIO, не raw bytes
        bio        = io.BytesIO(shot)
        bio.name   = "screenshot.png"
        # Экранируем HTML-символы в URL
        safe_url   = url[:80].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        safe_title = title[:60].replace("<","&lt;").replace(">","&gt;")
        cap = caption or f"📸 <b>{safe_title}</b>\n🔗 <code>{safe_url}</code>\n⏰ {now_str()}"
        await telegram_app.bot.send_photo(chat_id, bio, caption=cap, parse_mode="HTML")
    except Exception as e:
        log.error(f"bc_screenshot: {e}", exc_info=True)
        await telegram_app.bot.send_message(
            chat_id,
            f"📸 ❌ Ошибка скриншота:\n<code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )


async def bc_start_browser(chat_id: int):
    """Запускает Playwright браузер. Возвращает True или строку с ошибкой."""
    await bc_close_browser(chat_id)
    try:
        from playwright.async_api import async_playwright
        log.info(f"🌐 bc_start: запуск Playwright для chat={chat_id}")
        pw      = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
            ]
        )
        mobile = False
        bctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        await bctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        # Подставляем куки если есть
        if login_cookies:
            cookies_list = []
            for name, val in login_cookies.items():
                cookies_list.append({"name": name, "value": val, "domain": "aternos.org", "path": "/"})
            try:
                await bctx.add_cookies(cookies_list)
                log.info(f"🍪 bc_start: добавлено {len(cookies_list)} куков")
            except Exception as e:
                log.warning(f"bc_start cookies: {e}")

        page      = await bctx.new_page()
        start_url = f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/"
        log.info(f"🌐 bc_start: открываю {start_url}")
        await page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
        log.info(f"✅ bc_start: готово! title={await page.title()}")

        browser_sessions[chat_id] = {
            "pw": pw, "browser": browser, "ctx": bctx,
            "page": page, "active": True, "url": start_url,
            "mobile": False, "history": [start_url],
            "auto_snap_task": None,
        }
        return True
    except Exception as e:
        log.error(f"❌ bc_start_browser: {e}", exc_info=True)
        return str(e)


async def bc_close_browser(chat_id: int):
    """Закрывает браузер и чистит сессию."""
    sess = browser_sessions.pop(chat_id, None)
    browser_control_mode.discard(chat_id)
    if not sess:
        return
    # Останавливаем авто-снап если запущен
    task = sess.get("auto_snap_task")
    if task and not task.done():
        task.cancel()
    try:
        await sess["browser"].close()
    except:
        pass
    try:
        await sess["pw"].stop()
    except:
        pass
    log.info(f"🛑 bc_close: браузер закрыт для chat={chat_id}")


async def bc_do_ai_action(chat_id: int, instruction: str):
    """ИИ (Gemini бесплатно) анализирует страницу и выполняет действия."""
    page = await bc_get_page(chat_id)
    if not page:
        await telegram_app.bot.send_message(chat_id, "❌ Браузер не запущен!", parse_mode="HTML")
        return

    await telegram_app.bot.send_message(
        chat_id,
        f"🤖 <b>ИИ думает...</b>\n<i>{instruction[:100]}</i>",
        parse_mode="HTML"
    )

    try:
        title = await page.title()
        url   = page.url
        page_text = await page.evaluate("() => document.body.innerText.slice(0, 3000)")

        prompt = (
            f"Ты автоматизируешь браузер через Playwright для сайта aternos.org.\n"
            f"Текущая страница:\nURL: {url}\nTitle: {title}\n"
            f"Текст страницы:\n{page_text}\n\n"
            f"Задача: {instruction}\n\n"
            f"Ответь ТОЛЬКО валидным JSON-массивом действий (без пояснений, без ```json):\n"
            f'[{{"action":"goto","url":"..."}},{{"action":"click","selector":"..."}},'
            f'{{"action":"type","selector":"...","text":"..."}},'
            f'{{"action":"press","key":"Enter"}},{{"action":"wait","ms":2000}},'
            f'{{"action":"scroll","y":300}},{{"action":"rclick","selector":"..."}},'
            f'{{"action":"dblclick","selector":"..."}},{{"action":"screenshot"}}]'
        )

        raw_text = None

        # Пробуем Gemini (бесплатно)
        if GEMINI_API_KEY:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        GEMINI_URL,
                        params={"key": GEMINI_API_KEY},
                        json={"contents": [{"parts": [{"text": prompt}]}],
                              "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024}},
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as r:
                        d = await r.json()
                raw_text = d["candidates"][0]["content"]["parts"][0]["text"]
                log.info("✅ Gemini ответил")
            except Exception as e:
                log.warning(f"Gemini ошибка: {e}")

        if not raw_text:
            await telegram_app.bot.send_message(
                chat_id,
                "❌ <b>ИИ недоступен!</b>\nДобавь <code>GEMINI_API_KEY</code> в переменные Railway.\n"
                "Ключ бесплатный: https://aistudio.google.com/app/apikey",
                parse_mode="HTML"
            )
            return

        # Чистим от ```json если есть
        import re as _re
        raw_text = _re.sub(r"```json|```", "", raw_text).strip()
        actions  = json.loads(raw_text)
        log.info(f"AI actions: {actions}")
        results  = []

        for act in actions:
            a = act.get("action", "")
            try:
                if a == "goto":
                    await page.goto(act["url"], wait_until="domcontentloaded", timeout=20000)
                    results.append(f"✅ goto: {act['url'][:40]}")
                elif a == "click":
                    await page.click(act["selector"], timeout=5000)
                    results.append(f"✅ click: {act['selector']}")
                elif a == "rclick":
                    await page.click(act["selector"], button="right", timeout=5000)
                    results.append(f"✅ rclick: {act['selector']}")
                elif a == "dblclick":
                    await page.dblclick(act["selector"], timeout=5000)
                    results.append(f"✅ dblclick: {act['selector']}")
                elif a == "type":
                    await page.click(act["selector"], timeout=5000)
                    await page.type(act["selector"], act["text"], delay=60)
                    results.append(f"✅ type: «{act['text'][:20]}»")
                elif a == "press":
                    await page.keyboard.press(act["key"])
                    results.append(f"✅ press: {act['key']}")
                elif a == "wait":
                    await asyncio.sleep(act.get("ms", 1000) / 1000)
                    results.append(f"✅ wait {act.get('ms')}ms")
                elif a == "scroll":
                    await page.evaluate(f"window.scrollBy(0,{act.get('y',300)})")
                    results.append(f"✅ scroll {act.get('y')}")
                elif a == "screenshot":
                    await bc_screenshot_and_send(chat_id, f"🤖 ИИ: {instruction[:40]}")
                    results.append("✅ screenshot")
            except Exception as e:
                results.append(f"❌ {a}: {str(e)[:50]}")

        await telegram_app.bot.send_message(
            chat_id,
            f"🤖 <b>ИИ выполнил {len(results)} действий:</b>\n\n" + "\n".join(results[:15]),
            parse_mode="HTML"
        )
        await bc_screenshot_and_send(chat_id, f"🤖 Результат: {instruction[:40]}")

    except Exception as e:
        await telegram_app.bot.send_message(
            chat_id,
            f"🤖 ❌ Ошибка ИИ:\n<code>{str(e)[:300]}</code>",
            parse_mode="HTML"
        )


async def cmd_browser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Команда /browser — відкриває панель керування браузером."""
    if not reg(update):
        return
    if not is_admin(update):
        await get_msg(update).reply_text("🚫 Тільки адміни!", parse_mode="HTML")
        return
    chat_id = update.effective_chat.id
    sess = browser_sessions.get(chat_id, {})
    active = sess.get("active", False)
    await get_msg(update).reply_text(
        f"🖥 <b>REMOTE BROWSER CONTROL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{'🟢 Браузер активний' if active else '🔴 Браузер не запущено'}\n\n"
        f"<b>Як керувати:</b>\n"
        f"1️⃣ Запусти браузер кнопкою 🚀\n"
        f"2️⃣ Увімкни ⌨️ Режим вводу\n"
        f"3️⃣ Пиши в чат — текст вводиться на сторінці\n"
        f"4️⃣ Використовуй <code>&lt;TAB&gt;</code> <code>&lt;ENTER&gt;</code> <code>&lt;ESC&gt;</code> для клавіш\n\n"
        f"<b>AI режим:</b> пиши <code>AI: залогінься</code> і він сам все зробить\n\n"
        f"<b>Клік:</b> <code>&lt;CLICK:150,300&gt;</code> — клік по координатах\n"
        f"<b>Скрол:</b> <code>&lt;SCROLL:down&gt;</code> або <code>&lt;SCROLL:up&gt;</code>",
        reply_markup=browser_control_kb(chat_id),
        parse_mode="HTML",
    )


    """Одиночний скріншот і надсилає в чат."""
    sess = watch_sessions.get(chat_id, {})
    url = sess.get("url", f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/")
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser, bctx = await _get_watch_browser_ctx(p, sess)
            page = await bctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            title = await page.title()
            # Якщо бачимо форму логіну — логінимося
            if await page.query_selector("input[name='user']"):
                log.info("watch: бачу форму логіну, логінюсь...")
                await _watch_do_login(page, bctx, sess)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                title = await page.title()
            screenshot = await page.screenshot(full_page=False)
            await browser.close()
        caption = (
            f"👁 <b>Watch{' · ' + label if label else ''}</b>\n"
            f"📄 {title}\n"
            f"🔗 <code>{url}</code>\n"
            f"⏰ {now_full()}"
        )
        await telegram_app.bot.send_photo(send_to, screenshot, caption=caption, parse_mode="HTML")
    except Exception as e:
        await telegram_app.bot.send_message(send_to, f"📸 ❌ <code>{str(e)[:200]}</code>", parse_mode="HTML")


async def _watch_loop(chat_id: int):
    """Основний цикл Watch — скріншоти з заданим інтервалом."""
    count = 0
    try:
        while True:
            sess = watch_sessions.get(chat_id)
            if not sess:
                break
            interval = sess.get("interval", 20)
            count += 1
            await _take_and_send_screenshot(chat_id, chat_id, label=f"#{count}")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        await telegram_app.bot.send_message(
            chat_id,
            f"🛑 <b>Watch зупинено.</b> Зроблено {count} скріншотів.",
            parse_mode="HTML"
        )


async def show_watch_panel(update: Update, msg):
    """Показує Watch-панель."""
    chat_id = msg.chat_id if hasattr(msg, "chat_id") else update.effective_chat.id
    if chat_id not in watch_sessions:
        watch_sessions[chat_id] = {
            "interval": 20,
            "auto_login": True,
            "url": f"https://aternos.org/server/{SERVER_ID}" if SERVER_ID else "https://aternos.org/go/",
        }
    sess = watch_sessions[chat_id]
    running = sess.get("task") and not sess["task"].done()
    auto = sess.get("auto_login", True)
    w_user = sess.get("w_user", "—")
    w_pass = "✅ є" if sess.get("w_pass") else "❌ немає"
    await msg.reply_text(
        f"👁 <b>WATCH ПАНЕЛЬ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{'🟢 Активний' if running else '🔴 Зупинено'}\n"
        f"⚡ Інтервал: <b>{sess.get('interval', 20)} сек</b>\n"
        f"🔑 Режим: <b>{'🤖 Авто (env)' if auto else '✋ Вручну'}</b>\n"
        f"👤 Логін: <b>{w_user if not auto else '(з env)'}</b>\n"
        f"🔐 Пароль: <b>{w_pass if not auto else '(з env)'}</b>\n"
        f"🔗 URL: <code>{sess.get('url', '—')}</code>\n"
        f"🍪 Куків: <b>{len(login_cookies)}</b>",
        reply_markup=watch_kb(chat_id),
        parse_mode="HTML",
    )


async def cmd_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Команда /watch."""
    if not reg(update):
        return
    if not is_admin(update):
        await get_msg(update).reply_text("🚫 <b>Тільки адміни!</b>", parse_mode="HTML")
        return
    chat_id = update.effective_chat.id
    args = ctx.args  # /watch stop | /watch <url> | /watch

    # /watch stop
    if args and args[0].lower() == "stop":
        if chat_id in watch_sessions:
            task = watch_sessions[chat_id].get("task")
            if task and not task.done():
                task.cancel()
            if chat_id in watch_sessions:
                watch_sessions[chat_id]["task"] = None
            await get_msg(update).reply_text("🛑 <b>Watch зупинено!</b>", parse_mode="HTML")
        else:
            await get_msg(update).reply_text("ℹ️ Watch не запущено.", parse_mode="HTML")
        return

    await show_watch_panel(update, get_msg(update))


async def _background_login():
    await asyncio.sleep(3)
    ok = await aternos_login()
    if ok:
        await send_log("✅ <b>Aternos подключён!</b>\n🎮 Бот готов к работе.")
    else:
        await send_log("❌ <b>Aternos не подключён!</b>\nПроверь переменные или используй 🔄 Переподключить в /admin")

async def auto_report():
    await asyncio.sleep(60)
    while True:
        await asyncio.sleep(600)
        if not aternos_connected:
            continue
        await update_server_info()
        if server_status != "online":
            continue
        try:
            pl = "\n".join(f"  • {p}" for p in current_players) if current_players else "  (никого)"
            await send_log(f"🟢 <b>АВТО-ОТЧЁТ</b>\n⏰ {now_full()}\n⏱ {get_uptime()}\n👥 ({len(current_players)}):\n{pl}")
        except Exception as e:
            log.error(f"❌ report: {e}")

# ══════════════════════════════════════════════════════════════════
# FLASK + MAIN
# ══════════════════════════════════════════════════════════════════

flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return jsonify({"v": "18.0", "server": server_status, "players": len(current_players), "aternos": aternos_connected}), 200

@flask_app.route("/ping")
def ping():
    return "pong", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)

async def _route_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Роутер: якщо chat_id в browser_control_mode — іде в браузер, інакше — handle_text."""
    chat_id = update.effective_chat.id
    if chat_id in browser_control_mode:
        await handle_browser_input(update, ctx)
    else:
        await handle_text(update, ctx)


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
        ("start", cmd_start),
        ("on", cmd_on),
        ("status", cmd_status),
        ("players", cmd_players),
        ("info", cmd_info),
        ("connect", cmd_connect),
        ("rules", cmd_rules),
        ("help", cmd_help),
        ("random", cmd_random),
        ("uptime", cmd_uptime),
        ("vote", cmd_vote),
        ("seed", cmd_seed),
        ("shop", cmd_shop),
        ("top", cmd_top),
        ("motd", cmd_motd),
        ("watch", cmd_watch),
        ("browser", cmd_browser),
    ]:
        telegram_app.add_handler(CommandHandler(cmd, fn))

    telegram_app.add_handler(CallbackQueryHandler(on_admin_button, pattern="^adm_"))
    telegram_app.add_handler(CallbackQueryHandler(on_admin_button, pattern="^watch_"))
    telegram_app.add_handler(CallbackQueryHandler(on_admin_button, pattern="^bc_"))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    # Спочатку browser_control_mode — потім звичайний handle_text
    telegram_app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        _route_text
    ))

    log.info("✅ Бот v18.0 готов!")
    asyncio.create_task(_background_login())
    asyncio.create_task(auto_report())

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    await asyncio.Event().wait()

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Зупинено")
    except Exception as e:
        log.error(f"❌ {e}", exc_info=True)
        sys.exit(1)
