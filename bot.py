#!/usr/bin/env python3
"""ATERNOS TELEGRAM BOT v17.0 — fictionmine"""

import os, sys, json, asyncio, logging, random, hashlib
from datetime import datetime
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

log.info("="*60); log.info("🎮 ATERNOS BOT v17.0 — fictionmine"); log.info("="*60)

STATS_FILE="stats.json"; CONFIG_FILE="config.json"; ADMINS_FILE="admins.json"
USERS_FILE="users.json"; WARNS_FILE="warns.json";  NOTES_FILE="notes.json"

stats  = {"starts":0,"stops":0,"restarts":0,"last_start":None,"last_stop":None,"uptime_from":None,"peak_players":0,"total_commands":0}
config = {"log_chat_id":LOG_CHAT_ID,"maintenance":False,"server_name":"fictionmine","server_ip":"fictionmine.aternos.me","server_port":"19132","motd":"Ласкаво просимо на fictionmine! ⛏️","allow_all_start":True,"world_seed":"","shop_link":"","top_players":[]}
admins:set=set(); users:dict={}; warns:dict={}; notes:list=[]

telegram_app=None; http_session=None; aternos_connected=False
server_status="offline"; current_players=[]; login_cookies={}

WAIT_CODE=1; WAIT_BROADCAST=2; WAIT_ANNOUNCE=3; WAIT_MOTD=4; WAIT_SEED=5; WAIT_SHOP=6; WAIT_NOTE=7; WAIT_WARN=8

def load_all():
    global stats,config,admins,users,warns,notes
    for f,o in [(STATS_FILE,stats),(CONFIG_FILE,config)]:
        if os.path.exists(f):
            try:
                with open(f,encoding="utf-8") as fh: o.update(json.load(fh))
            except: pass
    for f,t in [(ADMINS_FILE,"a"),(USERS_FILE,"u"),(WARNS_FILE,"w"),(NOTES_FILE,"n")]:
        if os.path.exists(f):
            try:
                with open(f,encoding="utf-8") as fh:
                    v=json.load(fh)
                    if t=="a": admins.update(v)
                    elif t=="u": users.update(v)
                    elif t=="w": warns.update(v)
                    elif t=="n": notes.extend(v)
            except: pass

def save_all():
    try:
        with open(STATS_FILE,"w",encoding="utf-8") as f: json.dump(stats,f,ensure_ascii=False,indent=2)
        with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(config,f,ensure_ascii=False,indent=2)
        with open(ADMINS_FILE,"w") as f: json.dump(list(admins),f)
        with open(USERS_FILE,"w",encoding="utf-8") as f: json.dump(users,f,ensure_ascii=False,indent=2)
        with open(WARNS_FILE,"w",encoding="utf-8") as f: json.dump(warns,f,ensure_ascii=False,indent=2)
        with open(NOTES_FILE,"w",encoding="utf-8") as f: json.dump(notes,f,ensure_ascii=False,indent=2)
    except Exception as e: log.error(f"❌ save: {e}")

def reg(u:Update):
    usr=u.effective_user
    users[str(usr.id)]={"first_name":usr.first_name or "","username":usr.username or "","last_seen":datetime.now().isoformat()}
    stats["total_commands"]=stats.get("total_commands",0)+1

# ══════════════════════════════════════════════════
# ATERNOS
# ══════════════════════════════════════════════════

async def aternos_login() -> bool:
    global aternos_connected, http_session, login_cookies
    if not all([ATERNOS_USER,ATERNOS_PASS]): return False
    try:
        from playwright.async_api import async_playwright
        log.info("🔑 Playwright: логінюсь...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--flag-switches-begin",
                    "--disable-site-isolation-trials",
                    "--flag-switches-end",
                ]
            )
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width":1920,"height":1080},
                locale="en-US",
                timezone_id="Europe/Kiev",
                extra_http_headers={
                    "Accept-Language":"en-US,en;q=0.9",
                    "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "sec-ch-ua":'"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    "sec-ch-ua-platform":'"Windows"',
                    "sec-ch-ua-mobile":"?0",
                }
            )
            page = await ctx.new_page()

            # Маскуємо headless
            await ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get:()=>undefined});
                Object.defineProperty(navigator, 'plugins', {get:()=>({length:3})});
                Object.defineProperty(navigator, 'languages', {get:()=>['en-US','en']});
                window.chrome = {runtime:{}};
                Object.defineProperty(navigator, 'permissions', {
                    get:()=>({query:()=>Promise.resolve({state:'granted'})})
                });
            """)

            log.info("   Відкриваю aternos.org/go/ ...")
            await page.goto("https://aternos.org/go/", wait_until="domcontentloaded", timeout=60000)

            # Чекаємо поки Cloudflare Turnstile пройде (до 30 сек)
            log.info("   Чекаю Cloudflare Turnstile...")
            for i in range(30):
                await asyncio.sleep(1)
                url = page.url
                title = await page.title()
                log.info(f"   [{i+1}с] URL: {url[:60]} | Title: {title[:40]}")

                # Якщо Turnstile пройшов — шукаємо форму
                has_form = await page.query_selector("input[name='user']")
                has_turnstile = await page.query_selector("input[name='cf-turnstile-response']")
                if has_form:
                    log.info("   ✅ Форма знайдена!")
                    break
                if has_turnstile:
                    log.info("   ⏳ Turnstile ще не пройшов...")
            else:
                log.error("   ❌ Turnstile не пройшов за 30 сек")
                html = await page.content()
                log.error(f"   HTML: {html[:300]}")
                await browser.close()
                return False

            # Вводимо дані повільно як людина
            log.info("   Вводжу логін...")
            await page.click("input[name='user']")
            await asyncio.sleep(0.3)
            for char in ATERNOS_USER:
                await page.type("input[name='user']", char, delay=random.randint(50,150))

            await asyncio.sleep(0.5)

            log.info("   Вводжу пароль...")
            await page.click("input[name='password']")
            await asyncio.sleep(0.3)
            for char in ATERNOS_PASS:
                await page.type("input[name='password']", char, delay=random.randint(50,150))

            await asyncio.sleep(0.5)

            # Клік на кнопку
            for sel in ["button[type='submit']","button:has-text('Login')","button:has-text('Log in')"]:
                try:
                    await page.wait_for_selector(sel, timeout=2000, state="visible")
                    await page.click(sel)
                    log.info(f"   ✅ Кнопка: {sel}")
                    break
                except: pass

            # Чекаємо редіректу
            log.info("   Чекаю після логіну...")
            for i in range(15):
                await asyncio.sleep(1)
                url = page.url
                if "server" in url:
                    log.info(f"   ✅ Залогінились! URL: {url}")
                    break
                log.info(f"   [{i+1}с] {url[:60]}")

            cookies = await ctx.cookies()
            log.info(f"   Отримано {len(cookies)} cookies: {[c['name'] for c in cookies[:10]]}")
            await browser.close()

        # Створюємо aiohttp сесію з cookies
        jar = aiohttp.CookieJar()
        for c in cookies:
            jar.update_cookies({c['name']:c['value']}, response_url=yarl_URL("https://aternos.org/"))
            login_cookies[c['name']]=c['value']

        # Закриваємо стару сесію
        if http_session and not http_session.closed:
            await http_session.close()

        http_session = aiohttp.ClientSession(
            cookie_jar=jar,
            headers={
                "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With":"XMLHttpRequest",
                "Referer":f"https://aternos.org/server/{SERVER_ID}",
            }
        )
        aternos_connected = True
        log.info("✅ Aternos підключено!")
        return True
    except Exception as e:
        log.error(f"❌ login: {e}", exc_info=True)
        return False

async def _get(endpoint, params=None):
    if not http_session: return None, 0
    try:
        async with http_session.get(
            f"https://aternos.org/panel/ajax/{endpoint}",
            params=params or {"server":SERVER_ID},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            log.info(f"   {endpoint} → {r.status}")
            if r.status == 200:
                try: return await r.json(), 200
                except: return {}, 200
            return None, r.status
    except Exception as e:
        log.error(f"❌ {endpoint}: {e}")
        return None, 0

async def update_server_info():
    global server_status, current_players
    if not aternos_connected: return
    data, code = await _get("status.php")
    if code == 200 and data:
        server_status = data.get("status","offline")
        p = data.get("players",{})
        current_players = p.get("list",[]) if isinstance(p,dict) else []
    elif code == 403:
        log.warning("⚠️ 403 — cookies протухли, треба перелогінитись")

async def aternos_start() -> bool:
    _,code = await _get("start.php")
    if code==200: global server_status; server_status="starting"; return True
    return False

async def aternos_stop() -> bool:
    _,code = await _get("stop.php")
    if code==200: global server_status; server_status="offline"; return True
    return False

# ══════════════════════════════════════════════════
# УТИЛІТИ
# ══════════════════════════════════════════════════

def icon(s): return {"online":"🟢","offline":"🔴","starting":"🟡","stopping":"🟠"}.get(s,"⚫")
def get_msg(u): return u.callback_query.message if u.callback_query else u.message
async def typing(u):
    try: await get_msg(u).chat.send_action(ChatAction.TYPING)
    except: pass
async def send_log(text):
    if not telegram_app: return
    t = config.get("log_chat_id") or LOG_CHAT_ID
    if not t: return
    try: await telegram_app.bot.send_message(t,text,parse_mode="HTML")
    except: pass
def ulabel(u): return f"@{u.effective_user.username}" if u.effective_user.username else u.effective_user.first_name or "???"
def is_admin(u): return u.effective_user.id in admins
def now_str(): return datetime.now().strftime("%H:%M:%S")
def now_full(): return datetime.now().strftime("%d.%m.%Y %H:%M:%S")
def get_uptime():
    if stats.get("uptime_from") and server_status in("online","starting"):
        d=datetime.now()-datetime.fromisoformat(stats["uptime_from"])
        return f"{d.seconds//3600}г {(d.seconds%3600)//60}хв"
    return "—"

# ══════════════════════════════════════════════════
# КЛАВІАТУРИ
# ══════════════════════════════════════════════════

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Запустити сервер",callback_data="on")],
        [InlineKeyboardButton("📊 Статус",callback_data="status"),
         InlineKeyboardButton("👥 Гравці",callback_data="players")],
        [InlineKeyboardButton("ℹ️ Інфо",callback_data="info"),
         InlineKeyboardButton("🗺 Підключитись",callback_data="connect")],
        [InlineKeyboardButton("📜 Правила",callback_data="rules"),
         InlineKeyboardButton("🎲 Порада",callback_data="random")],
        [InlineKeyboardButton("🏆 Топ гравців",callback_data="top"),
         InlineKeyboardButton("🌍 Сід світу",callback_data="seed")],
        [InlineKeyboardButton("🗳 Голосувати",callback_data="vote"),
         InlineKeyboardButton("🛒 Магазин",callback_data="shop")],
        [InlineKeyboardButton("⏱ Аптайм",callback_data="uptime"),
         InlineKeyboardButton("💬 MOTD",callback_data="motd")],
    ])

def admin_kb():
    m=config.get("maintenance",False)
    a=config.get("allow_all_start",True)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("━━━ 🖥 СЕРВЕР ━━━",callback_data="noop")],
        [InlineKeyboardButton("🟢 Старт",callback_data="adm_start"),
         InlineKeyboardButton("🔴 Стоп",callback_data="adm_stop"),
         InlineKeyboardButton("🔄 Рестарт",callback_data="adm_restart")],
        [InlineKeyboardButton("━━━ 📢 ПОВІДОМЛЕННЯ ━━━",callback_data="noop")],
        [InlineKeyboardButton("📢 Броадкаст",callback_data="adm_broadcast"),
         InlineKeyboardButton("📣 Анонс",callback_data="adm_announce")],
        [InlineKeyboardButton("━━━ ⚙️ ATERNOS ━━━",callback_data="noop")],
        [InlineKeyboardButton("🔄 Перепідключити",callback_data="adm_reconnect"),
         InlineKeyboardButton("📊 Статус Aternos",callback_data="adm_aternos_status")],
        [InlineKeyboardButton("📸 Скріншот",callback_data="adm_screenshot"),
         InlineKeyboardButton("📋 Консоль",callback_data="adm_console")],
        [InlineKeyboardButton("━━━ 👥 ГРАВЦІ ━━━",callback_data="noop")],
        [InlineKeyboardButton("👥 Список",callback_data="adm_users"),
         InlineKeyboardButton("⚠️ Варни",callback_data="adm_warns")],
        [InlineKeyboardButton("👮 Видати варн",callback_data="adm_warn_give"),
         InlineKeyboardButton("🗑 Скинути варни",callback_data="adm_warns_clear")],
        [InlineKeyboardButton("━━━ 🔧 НАЛАШТУВАННЯ ━━━",callback_data="noop")],
        [InlineKeyboardButton(f"{'🔴 Техроботи' if m else '🟢 Техроботи'}",callback_data="adm_maintenance"),
         InlineKeyboardButton(f"{'✅ Всі стартують' if a else '🔐 Лише адміни'}",callback_data="adm_toggle_start")],
        [InlineKeyboardButton("✏️ Змінити MOTD",callback_data="adm_setmotd"),
         InlineKeyboardButton("🌍 Встановити сід",callback_data="adm_setseed")],
        [InlineKeyboardButton("🛒 Посилання магазину",callback_data="adm_setshop"),
         InlineKeyboardButton("📝 Нотатки",callback_data="adm_notes")],
        [InlineKeyboardButton("━━━ 📈 СТАТИСТИКА ━━━",callback_data="noop")],
        [InlineKeyboardButton("📊 Повна стат.",callback_data="adm_stats"),
         InlineKeyboardButton("🗑 Скинути стат.",callback_data="adm_resetstats")],
        [InlineKeyboardButton("📜 Лог → цей чат",callback_data="adm_setlog")],
        [InlineKeyboardButton("❌ Закрити панель",callback_data="adm_exit")],
    ])

# ══════════════════════════════════════════════════
# КОМАНДИ КОРИСТУВАЧА
# ══════════════════════════════════════════════════

async def cmd_start(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text(
            "🔧 <b>Технічне обслуговування</b>\n\nСервер тимчасово недоступний. Спробуй пізніше!",
            parse_mode="HTML"); return
    await update_server_info()
    pl_str = f"{len(current_players)} гравців онлайн" if server_status=="online" else "Сервер вимкнений"
    await get_msg(update).reply_text(
        f"⛏️ <b>FictionMine — Minecraft Bedrock</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} <b>Статус:</b> {server_status.upper()}\n"
        f"👥 <b>Гравці:</b> {pl_str}\n"
        f"🌐 <b>IP:</b> <code>{config['server_ip']}</code>\n"
        f"🔌 <b>Порт:</b> <code>{config['server_port']}</code>\n"
        f"⏱ <b>Аптайм:</b> {get_uptime()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>{config.get('motd','')}</i>",
        reply_markup=main_kb(), parse_mode="HTML")

async def cmd_on(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 <b>Технічне обслуговування!</b>",parse_mode="HTML"); return
    if not config.get("allow_all_start",True) and not is_admin(update):
        await get_msg(update).reply_text("🚫 <b>Лише адміністратори можуть запускати!</b>",parse_mode="HTML"); return
    msg = await get_msg(update).reply_text("⏳ <b>Запускаю сервер...</b>",parse_mode="HTML")
    if not aternos_connected:
        await msg.edit_text("❌ <b>Aternos не підключено!</b>\nАдмін переконається у підключенні.",parse_mode="HTML"); return
    await update_server_info()
    if server_status in("online","starting"):
        await msg.edit_text(
            f"✅ <b>Сервер вже {'працює' if server_status=='online' else 'запускається'}!</b>\n\n"
            f"🌐 <code>{config['server_ip']}</code>\n🔌 <code>{config['server_port']}</code>",
            parse_mode="HTML"); return
    ok = await aternos_start()
    if ok:
        stats["starts"]+=1; stats["last_start"]=datetime.now().isoformat(); stats["uptime_from"]=datetime.now().isoformat(); save_all()
        await msg.edit_text(
            f"🟢 <b>СЕРВЕР ЗАПУСКАЄТЬСЯ!</b>\n\n"
            f"🌐 <code>{config['server_ip']}</code>\n"
            f"🔌 <code>{config['server_port']}</code>\n"
            f"⏰ {now_str()}\n\n"
            f"<i>⏱ Зазвичай 1-3 хвилини</i>",parse_mode="HTML")
        await send_log(f"🟢 <b>ЗАПУСК</b>\n👤 {ulabel(update)}\n⏰ {now_full()}\n🚀 #{stats['starts']}")
    else:
        await msg.edit_text("❌ <b>Помилка запуску!</b>\nСпробуй ще або зверніться до адміна.",parse_mode="HTML")

async def cmd_status(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    pl_list = "\n".join(f"  🧑 {p}" for p in current_players) if current_players else "  <i>Нікого немає</i>"
    await get_msg(update).reply_text(
        f"{icon(server_status)} <b>СТАТУС СЕРВЕРА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 <b>FictionMine</b> (Bedrock)\n"
        f"📍 <b>{server_status.upper()}</b>\n"
        f"👥 <b>Гравців:</b> {len(current_players)}\n"
        f"⏱ <b>Аптайм:</b> {get_uptime()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <code>{config['server_ip']}</code>\n"
        f"🔌 <code>{config['server_port']}</code>\n"
        f"⏰ {now_str()}",parse_mode="HTML")

async def cmd_players(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    if server_status!="online":
        await get_msg(update).reply_text(
            f"🔴 <b>Сервер {server_status.upper()}</b>\n\nЗапусти через /on",parse_mode="HTML"); return
    if not current_players:
        await get_msg(update).reply_text(
            f"👥 <b>Зараз нікого немає</b> 😿\n\n"
            f"Першим заходь!\n🌐 <code>{config['server_ip']}</code>",parse_mode="HTML"); return
    if len(current_players)>stats["peak_players"]:
        stats["peak_players"]=len(current_players); save_all()
    pl="\n".join(f"  ⚔️ <b>{p}</b>" for p in current_players)
    await get_msg(update).reply_text(
        f"👥 <b>ОНЛАЙН: {len(current_players)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{pl}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Аптайм: {get_uptime()}\n👑 Рекорд: {stats['peak_players']}",parse_mode="HTML")

async def cmd_info(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    ls=datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "—"
    lo=datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")  if stats.get("last_stop")  else "—"
    await get_msg(update).reply_text(
        f"📊 <b>FICTIONMINE — СТАТИСТИКА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} {server_status.upper()} | 👥 {len(current_players)} гравців\n\n"
        f"🚀 Запусків: <b>{stats['starts']}</b>\n"
        f"🛑 Зупинок: <b>{stats['stops']}</b>\n"
        f"🔄 Перезапусків: <b>{stats.get('restarts',0)}</b>\n"
        f"👑 Рекорд гравців: <b>{stats['peak_players']}</b>\n"
        f"⏱ Аптайм: <b>{get_uptime()}</b>\n"
        f"💬 Команд виконано: <b>{stats.get('total_commands',0)}</b>\n"
        f"👤 Унікальних гравців: <b>{len(users)}</b>\n\n"
        f"▶️ Ост. запуск: {ls}\n"
        f"⏹ Ост. зупинка: {lo}",parse_mode="HTML")

async def cmd_connect(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    await get_msg(update).reply_text(
        f"🗺 <b>ЯК ПІДКЛЮЧИТИСЬ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 <b>Minecraft Bedrock Edition</b>\n\n"
        f"1️⃣ Відкрий Minecraft\n"
        f"2️⃣ Натисни <b>Грати</b>\n"
        f"3️⃣ Вкладка <b>Сервери</b>\n"
        f"4️⃣ <b>Додати сервер</b>\n"
        f"5️⃣ Введи адресу:\n"
        f"   🌐 <code>{config['server_ip']}</code>\n"
        f"   🔌 <code>{config['server_port']}</code>\n"
        f"6️⃣ Підключайся!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} Зараз: <b>{server_status.upper()}</b>",parse_mode="HTML")

async def cmd_rules(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await get_msg(update).reply_text(
        f"📜 <b>ПРАВИЛА FICTIONMINE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ <b>ДОЗВОЛЕНО:</b>\n"
        f"• Будівництво та дослідження\n"
        f"• Торгівля між гравцями\n"
        f"• Створення кланів та союзів\n"
        f"• PvP у спеціальних зонах\n"
        f"• Редстоун механізми\n\n"
        f"❌ <b>ЗАБОРОНЕНО:</b>\n"
        f"• Гріферство та руйнування\n"
        f"• Чіти, хаки, дюпи\n"
        f"• Образи та токсичність\n"
        f"• Спам та реклама\n"
        f"• X-ray та подібне\n\n"
        f"⚠️ <b>ПОКАРАННЯ:</b>\n"
        f"1️⃣ Попередження\n"
        f"2️⃣ Бан 24 год\n"
        f"3️⃣ Перманентний бан\n\n"
        f"<i>Приємної гри! ⛏️</i>",parse_mode="HTML")

async def cmd_help(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    adm = "\n\n🔐 /admin — панель адміністратора" if is_admin(update) else ""
    await get_msg(update).reply_text(
        f"❓ <b>ДОПОМОГА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🌐 Сервер:</b>\n"
        f"/on — запустити сервер\n"
        f"/status — статус та IP\n"
        f"/players — хто онлайн\n\n"
        f"<b>ℹ️ Інфо:</b>\n"
        f"/info — статистика\n"
        f"/connect — як підключитись\n"
        f"/rules — правила\n"
        f"/random — порада\n\n"
        f"<b>🎮 Різне:</b>\n"
        f"/top — топ гравців\n"
        f"/vote — проголосувати\n"
        f"/seed — сід світу\n"
        f"/shop — магазин\n"
        f"/uptime — час роботи\n"
        f"/motd — повідомлення дня"
        f"{adm}",parse_mode="HTML")

async def cmd_random(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    tips = [
        "💡 Ліжко встановлює точку відродження!",
        "⚔️ Зачарування «Видобуток III» — більше ресурсів!",
        "🛡️ Щит блокує весь урон від стріл!",
        "💎 Алмази частіше на рівні Y=-58!",
        "🔥 Огниво створює портал у Пекло!",
        "⚡ Блискавка + свиня = свиноліт!",
        "🎣 Рибалка вночі — кращі трофеї!",
        "🏔️ Смарагди тільки в горах!",
        "🌙 Поспи вночі — пропускаєш монстрів!",
        "⛏️ Кирка з «Удача III» — більше алмазів!",
        "🪣 Відро води з джерела — нескінченне!",
        "🧙 Зачарований стіл + 15 полиць = рівень 30!",
        "🐝 Бджоли дають мед — будуй вулики!",
        "🔭 Підзорна труба з міді та аметисту!",
        "🗡️ Меч з вогнем — моби горять!",
    ]
    await get_msg(update).reply_text(
        f"🎲 <b>ПОРАДА ДНЯ</b>\n\n{random.choice(tips)}\n\n<i>Натисни /random для нової поради!</i>",
        parse_mode="HTML")

async def cmd_uptime(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    await get_msg(update).reply_text(
        f"⏱ <b>ЧАС РОБОТИ</b>\n\n{icon(server_status)} {server_status.upper()}\n⏱ <b>{get_uptime()}</b>\n⏰ {now_full()}",
        parse_mode="HTML")

async def cmd_vote(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await get_msg(update).reply_text(
        "🗳 <b>ПРОГОЛОСУЙ ЗА СЕРВЕР!</b>\n\n"
        "Голос допомагає нам рости і залучати нових гравців!\n\n"
        "🔗 <a href='https://minecraft-server-list.com/'>Minecraft Server List</a>\n"
        "🔗 <a href='https://minecraftservers.org/'>Minecraft Servers</a>\n\n"
        "🎁 За кожен голос — бонуси на сервері!",
        parse_mode="HTML",disable_web_page_preview=True)

async def cmd_seed(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    seed=config.get("world_seed") or "Не встановлено"
    await get_msg(update).reply_text(
        f"🌍 <b>СІД СВІТУ</b>\n\n<code>{seed}</code>\n\n<i>Використовуй для вивчення карти!</i>",
        parse_mode="HTML")

async def cmd_shop(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    link=config.get("shop_link") or "Не налаштовано"
    await get_msg(update).reply_text(
        "🛒 <b>ДОНАТ-МАГАЗИН</b>\n\n"
        "Підтримай сервер і отримай привілеї!\n\n"
        "💎 <b>VIP</b> — кольоровий нік, /fly\n"
        "👑 <b>PREMIUM</b> — всі VIP + /god\n"
        "🏆 <b>ELITE</b> — всі + власний варп\n\n"
        f"🔗 {link}",parse_mode="HTML")

async def cmd_top(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    top=config.get("top_players",[])
    if not top:
        await get_msg(update).reply_text(
            "🏆 <b>ТОП ГРАВЦІВ</b>\n\n<i>Статистика ще не зібрана.\nАдмін оновить топ!</i>",
            parse_mode="HTML"); return
    medals=["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines=[f"{medals[i]} <b>{p['name']}</b> — {p.get('score','?')} очок" for i,p in enumerate(top[:10])]
    await get_msg(update).reply_text("🏆 <b>ТОП 10 ГРАВЦІВ</b>\n\n"+"\n".join(lines),parse_mode="HTML")

async def cmd_motd(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update); await update_server_info()
    await get_msg(update).reply_text(
        f"💬 <b>ПОВІДОМЛЕННЯ ДНЯ</b>\n\n{config.get('motd','Ласкаво просимо!')}\n\n{icon(server_status)} {server_status.upper()}",
        parse_mode="HTML")

# ══════════════════════════════════════════════════
# АДМІН ПАНЕЛЬ
# ══════════════════════════════════════════════════

async def cmd_admin(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    reg(update)
    if is_admin(update): await show_admin_panel(update); return
    await update.message.reply_text("🔐 <b>Введи код доступу:</b>",parse_mode="HTML")
    return WAIT_CODE

async def got_code(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip()==ADMIN_CODE:
        admins.add(update.effective_user.id); save_all()
        await update.message.reply_text("✅ <b>Ласкаво просимо, Адміністратор!</b>",parse_mode="HTML")
        await send_log(f"🔐 <b>НОВИЙ АДМІН</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        await show_admin_panel(update)
    else:
        await update.message.reply_text("❌ <b>Невірний код!</b>",parse_mode="HTML")
        await send_log(f"⚠️ <b>НЕВДАЛА СПРОБА</b>\n👤 {ulabel(update)}")
    return ConversationHandler.END

async def cancel_conv(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("action",None)
    await update.message.reply_text("❌ Скасовано.")
    return ConversationHandler.END

async def show_admin_panel(update:Update):
    await update_server_info()
    m=config.get("maintenance",False)
    await get_msg(update).reply_text(
        f"⚙️ <b>ПАНЕЛЬ АДМІНІСТРАТОРА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Aternos: {'✅ Підключено' if aternos_connected else '❌ Відключено'}\n"
        f"{icon(server_status)} Сервер: <b>{server_status.upper()}</b>\n"
        f"👥 Гравців: <b>{len(current_players)}</b>\n"
        f"⏱ Аптайм: <b>{get_uptime()}</b>\n"
        f"👤 Юзерів: <b>{len(users)}</b> | 🔐 Адмінів: <b>{len(admins)}</b>\n"
        f"⚠️ Варнів: <b>{sum(warns.values())}</b> | 📝 Нотаток: <b>{len(notes)}</b>\n"
        f"🔧 Техроботи: <b>{'ВКЛ 🟡' if m else 'ВИКЛ 🟢'}</b>",
        reply_markup=admin_kb(),parse_mode="HTML")

async def on_admin_button(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="noop": return
    if not is_admin(update): await q.answer("🚫 Немає доступу!",show_alert=True); return
    d=q.data

    if d=="adm_start":
        await q.message.edit_text("⏳ <b>Запускаю...</b>",parse_mode="HTML")
        await update_server_info()
        if server_status in("online","starting"):
            await q.message.edit_text("✅ <b>Вже працює!</b>",reply_markup=admin_kb(),parse_mode="HTML"); return
        ok=await aternos_start()
        if ok:
            stats["starts"]+=1; stats["last_start"]=datetime.now().isoformat(); stats["uptime_from"]=datetime.now().isoformat(); save_all()
            await q.message.edit_text(f"🟢 <b>ЗАПУЩЕНО!</b>\n⏰ {now_str()}",reply_markup=admin_kb(),parse_mode="HTML")
            await send_log(f"🟢 <b>ЗАПУСК (АДМІН)</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Помилка!</b>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_stop":
        await q.message.edit_text("⏳ <b>Зупиняю...</b>",parse_mode="HTML")
        ok=await aternos_stop()
        if ok:
            stats["stops"]+=1; stats["last_stop"]=datetime.now().isoformat(); stats["uptime_from"]=None; save_all()
            await q.message.edit_text(f"🔴 <b>ЗУПИНЕНО!</b>\n⏰ {now_str()}",reply_markup=admin_kb(),parse_mode="HTML")
            await send_log(f"🔴 <b>СТОП (АДМІН)</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Помилка!</b>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_restart":
        await q.message.edit_text("⏳ <b>Перезапускаю...</b>",parse_mode="HTML")
        await aternos_stop(); await asyncio.sleep(5); ok=await aternos_start()
        if ok:
            stats["restarts"]=stats.get("restarts",0)+1; stats["starts"]+=1; stats["last_start"]=datetime.now().isoformat(); stats["uptime_from"]=datetime.now().isoformat(); save_all()
            await q.message.edit_text(f"🔄 <b>ПЕРЕЗАПУЩЕНО!</b>\n⏰ {now_str()}",reply_markup=admin_kb(),parse_mode="HTML")
            await send_log(f"🔄 <b>ПЕРЕЗАПУСК</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Помилка!</b>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_reconnect":
        await q.message.edit_text("⏳ <b>Перепідключаюсь до Aternos...</b>",parse_mode="HTML")
        ok=await aternos_login()
        r="✅ Підключено!" if ok else "❌ Не вдалось"
        await q.message.edit_text(f"🔌 <b>{r}</b>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_aternos_status":
        data,code=await _get("status.php")
        if code==200 and data:
            await q.message.edit_text(
                f"📊 <b>СТАТУС ATERNOS</b>\n\n<code>{json.dumps(data,ensure_ascii=False,indent=2)[:600]}</code>",
                reply_markup=admin_kb(),parse_mode="HTML")
        else:
            await q.message.edit_text(f"❌ Помилка: код {code}",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_screenshot":
        await q.message.edit_text("📸 <b>Роблю скріншот Aternos...</b>",parse_mode="HTML")
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser=await p.chromium.launch(headless=True,args=["--no-sandbox","--disable-gpu"])
                bctx=await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                # Додаємо збережені куки
                for name,val in login_cookies.items():
                    await bctx.add_cookies([{"name":name,"value":val,"domain":"aternos.org","path":"/"}])
                page=await bctx.new_page()
                await page.goto(f"https://aternos.org/server/{SERVER_ID}",timeout=30000)
                await asyncio.sleep(3)
                screenshot=await page.screenshot(full_page=False)
                await browser.close()
            await telegram_app.bot.send_photo(q.message.chat_id,screenshot,caption=f"📸 Aternos скріншот\n⏰ {now_full()}")
            await q.message.edit_text("📸 <b>Скріншот надіслано!</b>",reply_markup=admin_kb(),parse_mode="HTML")
        except Exception as e:
            await q.message.edit_text(f"❌ Помилка скріншоту:\n<code>{str(e)[:200]}</code>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_console":
        data,code=await _get("console.php")
        if code==200 and data:
            lines=data.get("lines",[]) if isinstance(data,dict) else []
            txt="\n".join(str(l) for l in lines[-20:]) if lines else str(data)[:600]
            await q.message.edit_text(f"📋 <b>КОНСОЛЬ</b>\n\n<code>{txt[:800]}</code>",reply_markup=admin_kb(),parse_mode="HTML")
        else:
            await q.message.edit_text(f"❌ Консоль недоступна (код {code})",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_broadcast":
        ctx.user_data["action"]="broadcast"
        await q.message.reply_text("📢 <b>Напиши повідомлення для всіх:</b>\n<i>/cancel — скасувати</i>",parse_mode="HTML")

    elif d=="adm_announce":
        ctx.user_data["action"]="announce"
        await q.message.reply_text("📣 <b>Напиши текст анонсу:</b>\n<i>/cancel — скасувати</i>",parse_mode="HTML")

    elif d=="adm_users":
        if not users: await q.message.edit_text("👥 Немає користувачів",reply_markup=admin_kb(),parse_mode="HTML"); return
        lines=[]
        for uid,info in list(users.items())[-15:]:
            n=info.get("first_name","???"); u=f"@{info['username']}" if info.get("username") else "—"
            w=warns.get(uid,0); ma="🔐" if int(uid) in admins else ""; wm=f" ⚠️{w}" if w else ""
            try: seen=datetime.fromisoformat(info.get("last_seen","")).strftime("%d.%m %H:%M")
            except: seen="—"
            lines.append(f"• {n} {u}{ma}{wm} <i>{seen}</i>")
        await q.message.edit_text(f"👥 <b>КОРИСТУВАЧІ ({len(users)})</b>\n\n"+"\n".join(lines),reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_warns":
        if not warns: await q.message.edit_text("⚠️ Варнів немає",reply_markup=admin_kb(),parse_mode="HTML"); return
        lines=[]
        for uid,cnt in warns.items():
            info=users.get(uid,{}); u=f"@{info.get('username','')}" if info.get("username") else f"ID:{uid}"
            lines.append(f"• {info.get('first_name','???')} {u} — ⚠️{cnt}/3")
        await q.message.edit_text("⚠️ <b>ВАРНИ</b>\n\n"+"\n".join(lines),reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_warn_give":
        ctx.user_data["action"]="warn"
        await q.message.reply_text("⚠️ <b>Напиши @username для варну:</b>",parse_mode="HTML")

    elif d=="adm_warns_clear":
        warns.clear(); save_all()
        await q.message.edit_text("🗑 <b>Всі варни скинуті!</b>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_maintenance":
        config["maintenance"]=not config.get("maintenance",False); save_all()
        w="ВКЛ 🟡" if config["maintenance"] else "ВИКЛ 🟢"
        await q.message.edit_text(f"🔧 <b>Техроботи {w}</b>",reply_markup=admin_kb(),parse_mode="HTML")
        await send_log(f"🔧 Техроботи {w}\n👤 {ulabel(update)}")

    elif d=="adm_toggle_start":
        config["allow_all_start"]=not config.get("allow_all_start",True); save_all()
        w="ВСІ можуть ✅" if config["allow_all_start"] else "Тільки АДМІНИ 🔐"
        await q.message.edit_text(f"⚙️ <b>Запуск: {w}</b>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_setmotd":
        ctx.user_data["action"]="setmotd"
        await q.message.reply_text("✏️ <b>Напиши новий MOTD:</b>",parse_mode="HTML")

    elif d=="adm_setseed":
        ctx.user_data["action"]="setseed"
        await q.message.reply_text("🌍 <b>Напиши сід світу:</b>",parse_mode="HTML")

    elif d=="adm_setshop":
        ctx.user_data["action"]="setshop"
        await q.message.reply_text("🛒 <b>Напиши посилання на магазин:</b>",parse_mode="HTML")

    elif d=="adm_notes":
        ctx.user_data["action"]="note"
        if not notes:
            await q.message.edit_text("📝 <b>Нотаток немає</b>\n\nНапиши нотатку:",reply_markup=admin_kb(),parse_mode="HTML")
        else:
            lines=[f"{i+1}. {n}" for i,n in enumerate(notes[-10:])]
            await q.message.edit_text("📝 <b>НОТАТКИ</b>\n\n"+"\n".join(lines)+"\n\n<i>Напиши нову нотатку або /cancel</i>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_stats":
        await update_server_info()
        ls=datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "—"
        lo=datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")  if stats.get("last_stop")  else "—"
        await q.message.edit_text(
            f"📊 <b>ПОВНА СТАТИСТИКА</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Запусків: {stats['starts']}\n"
            f"🛑 Зупинок: {stats['stops']}\n"
            f"🔄 Перезапусків: {stats.get('restarts',0)}\n"
            f"👑 Рекорд гравців: {stats['peak_players']}\n"
            f"⏱ Аптайм: {get_uptime()}\n"
            f"💬 Команд: {stats.get('total_commands',0)}\n"
            f"👤 Юзерів: {len(users)}\n"
            f"⚠️ Варнів видано: {sum(warns.values())}\n\n"
            f"▶️ {ls} | ⏹ {lo}\n⏰ {now_full()}",
            reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_resetstats":
        stats.update({"starts":0,"stops":0,"restarts":0,"last_start":None,"last_stop":None,"uptime_from":None,"peak_players":0,"total_commands":0}); save_all()
        await q.message.edit_text("🗑 <b>Статистику скинуто!</b>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_setlog":
        config["log_chat_id"]=q.message.chat_id; save_all()
        await q.message.edit_text(f"✅ <b>Логи тут!</b>\nID: <code>{q.message.chat_id}</code>",reply_markup=admin_kb(),parse_mode="HTML")

    elif d=="adm_exit":
        await q.message.edit_text("👋 <b>Панель закрита.</b>",parse_mode="HTML")

# ══════════════════════════════════════════════════
# ТЕКСТОВІ ВІДПОВІДІ (броадкаст, нотатки тощо)
# ══════════════════════════════════════════════════

async def handle_text(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    action=ctx.user_data.get("action")
    if not action: return
    if not is_admin(update) and action not in []: return
    text=update.message.text.strip()
    if text=="/cancel":
        ctx.user_data["action"]=None
        await update.message.reply_text("❌ Скасовано."); return

    if action=="broadcast":
        ctx.user_data["action"]=None
        msg_text=f"📢 <b>ОГОЛОШЕННЯ — {config['server_name']}</b>\n\n{text}\n\n<i>— Адміністрація</i>"
        sent=fail=0; sm=await update.message.reply_text("⏳ Відправляю...",parse_mode="HTML")
        for uid in list(users.keys()):
            try: await telegram_app.bot.send_message(int(uid),msg_text,parse_mode="HTML"); sent+=1; await asyncio.sleep(0.05)
            except: fail+=1
        await sm.edit_text(f"📢 <b>Готово!</b>\n✅ {sent} | ❌ {fail}",parse_mode="HTML")
        await send_log(f"📢 <b>БРОАДКАСТ</b>\n👤 {ulabel(update)}\n✅{sent}/❌{fail}")

    elif action=="announce":
        ctx.user_data["action"]=None
        msg_text=f"📣 <b>━━━━━━━━━━━━━━━━━━━━━━</b>\n🎮 <b>{config['server_name'].upper()}</b>\n\n{text}\n\n<b>━━━━━━━━━━━━━━━━━━━━━━</b>"
        sent=fail=0; sm=await update.message.reply_text("⏳ Відправляю...",parse_mode="HTML")
        for uid in list(users.keys()):
            try: await telegram_app.bot.send_message(int(uid),msg_text,parse_mode="HTML"); sent+=1; await asyncio.sleep(0.05)
            except: fail+=1
        await sm.edit_text(f"📣 <b>Анонс надіслано!</b>\n✅ {sent} | ❌ {fail}",parse_mode="HTML")

    elif action=="setmotd":
        ctx.user_data["action"]=None
        config["motd"]=text; save_all()
        await update.message.reply_text(f"✅ <b>MOTD оновлено!</b>\n\n{text}",parse_mode="HTML")

    elif action=="setseed":
        ctx.user_data["action"]=None
        config["world_seed"]=text; save_all()
        await update.message.reply_text(f"✅ <b>Сід встановлено:</b> <code>{text}</code>",parse_mode="HTML")

    elif action=="setshop":
        ctx.user_data["action"]=None
        config["shop_link"]=text; save_all()
        await update.message.reply_text(f"✅ <b>Магазин:</b> {text}",parse_mode="HTML")

    elif action=="note":
        ctx.user_data["action"]=None
        notes.append(f"[{now_str()}] {text}"); save_all()
        await update.message.reply_text("📝 <b>Нотатку збережено!</b>",parse_mode="HTML")

    elif action=="warn":
        ctx.user_data["action"]=None
        target=text.lstrip("@")
        uid=next((u for u,i in users.items() if i.get("username","").lower()==target.lower()),None)
        if not uid: await update.message.reply_text(f"❌ @{target} не знайдено!",parse_mode="HTML"); return
        warns[uid]=warns.get(uid,0)+1; save_all()
        await update.message.reply_text(f"⚠️ <b>Варн видано!</b>\n👤 @{target}\n⚠️ {warns[uid]}/3",parse_mode="HTML")
        await send_log(f"⚠️ <b>ВАРН</b>\n👤 @{target}\n⚠️ {warns[uid]}/3\n👮 {ulabel(update)}")

# ══════════════════════════════════════════════════
# CALLBACK BUTTONS (юзери)
# ══════════════════════════════════════════════════

async def on_button(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    fns={
        "on":cmd_on,"players":cmd_players,"status":cmd_status,
        "info":cmd_info,"connect":cmd_connect,"rules":cmd_rules,
        "random":cmd_random,"top":cmd_top,"seed":cmd_seed,
        "vote":cmd_vote,"shop":cmd_shop,"uptime":cmd_uptime,"motd":cmd_motd,
    }
    fn=fns.get(q.data)
    if fn: await fn(update,ctx)

# ══════════════════════════════════════════════════
# АВТО-ЗВІТ
# ══════════════════════════════════════════════════

async def auto_report():
    await asyncio.sleep(60)
    while True:
        await asyncio.sleep(600)
        if not aternos_connected: continue
        await update_server_info()
        if server_status!="online": continue
        try:
            pl="\n".join(f"  • {p}" for p in current_players) if current_players else "  (нікого)"
            await send_log(f"🟢 <b>АВТО-ЗВІТ</b>\n⏰ {now_full()}\n⏱ {get_uptime()}\n👥 ({len(current_players)}):\n{pl}")
        except Exception as e: log.error(f"❌ report: {e}")

async def _background_login():
    await asyncio.sleep(3)
    ok=await aternos_login()
    if ok: await send_log("✅ <b>Aternos підключено!</b>\n🎮 Бот готовий до роботи.")
    else:  await send_log("❌ <b>Aternos не підключено!</b>\nПеревір змінні або використай 🔄 Перепідключити в /admin")

# ══════════════════════════════════════════════════
# FLASK + MAIN
# ══════════════════════════════════════════════════

flask_app=Flask(__name__)

@flask_app.route("/")
def index(): return jsonify({"v":"17.0","server":server_status,"players":len(current_players),"aternos":aternos_connected}),200

@flask_app.route("/ping")
def ping(): return "pong",200

def run_flask():
    flask_app.run(host="0.0.0.0",port=PORT,debug=False,use_reloader=False,threaded=True)

async def main():
    global telegram_app
    load_all()

    telegram_app=Application.builder().token(TELEGRAM_TOKEN).build()

    admin_conv=ConversationHandler(
        entry_points=[CommandHandler("admin",cmd_admin)],
        states={WAIT_CODE:[MessageHandler(filters.TEXT & ~filters.COMMAND,got_code)]},
        fallbacks=[CommandHandler("cancel",cancel_conv)],
    )
    telegram_app.add_handler(admin_conv)

    for cmd,fn in [
        ("start",cmd_start),("on",cmd_on),("status",cmd_status),
        ("players",cmd_players),("info",cmd_info),("connect",cmd_connect),
        ("rules",cmd_rules),("help",cmd_help),("random",cmd_random),
        ("uptime",cmd_uptime),("vote",cmd_vote),("seed",cmd_seed),
        ("shop",cmd_shop),("top",cmd_top),("motd",cmd_motd),
    ]:
        telegram_app.add_handler(CommandHandler(cmd,fn))

    telegram_app.add_handler(CallbackQueryHandler(on_admin_button,pattern="^adm_"))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_text))

    log.info("✅ Бот v17.0 готовий!")
    asyncio.create_task(_background_login())
    asyncio.create_task(auto_report())

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    await asyncio.Event().wait()

if __name__=="__main__":
    Thread(target=run_flask,daemon=True).start()
    try: asyncio.run(main())
    except KeyboardInterrupt: log.info("⛔ Зупинено")
    except Exception as e: log.error(f"❌ {e}",exc_info=True); sys.exit(1)
