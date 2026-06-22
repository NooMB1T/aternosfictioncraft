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
        [InlineKeyboardButton("━━━ ⚙️ ATERNOS ━━━", callback_data="noop")],
        [InlineKeyboardButton("🔄 Переподключить", callback_data="adm_reconnect"),
         InlineKeyboardButton("📊 Статус", callback_data="adm_aternos_status")],
        [InlineKeyboardButton("📸 Скриншот", callback_data="adm_screenshot"),
         InlineKeyboardButton("📋 Консоль", callback_data="adm_console")],
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

# ══════════════════════════════════════════════════════════════════
# КОМАНДИ КОРИСТУВАЧА
# ══════════════════════════════════════════════════════════════════

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
    ]:
        telegram_app.add_handler(CommandHandler(cmd, fn))

    telegram_app.add_handler(CallbackQueryHandler(on_admin_button, pattern="^adm_"))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

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
