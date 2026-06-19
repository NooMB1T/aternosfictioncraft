#!/usr/bin/env python3
"""
ATERNOS TELEGRAM BOT v10.0
Управление Minecraft Bedrock сервером fictionmine
"""

import os, sys, json, asyncio, hashlib, logging, random
from datetime import datetime
from threading import Thread
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters, ConversationHandler
)
from telegram.constants import ChatAction

# ══════════════════════════════════════════════════════════════════
# КОНФИГ
# ══════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ATERNOS_USER   = os.getenv("ATERNOS_USER", "")
ATERNOS_PASS   = os.getenv("ATERNOS_PASS", "")
SERVER_ID      = os.getenv("SERVER_ID", "")
LOG_CHAT_ID    = int(os.getenv("LOG_CHAT_ID", "0"))
PORT           = int(os.getenv("PORT", "8000"))
ADMIN_CODE     = os.getenv("ADMIN_CODE", "2011")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)
log = logging.getLogger("bot")

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN не установлен!")
    sys.exit(1)

log.info("=" * 60)
log.info("🎮 ATERNOS BOT v10.0 — fictionmine")
log.info("=" * 60)

# ══════════════════════════════════════════════════════════════════
# ХРАНИЛИЩЕ
# ══════════════════════════════════════════════════════════════════

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
    "motd": "Добро пожаловать на fictionmine!",
}
admins: set = set()
users: dict = {}

telegram_app    = None
aternos_connected = False
server_status   = "offline"
current_players = []

sess = requests.Session()
retry_s = Retry(total=3, backoff_factor=1, status_forcelist=[429,500,502,503,504])
sess.mount("http://",  HTTPAdapter(max_retries=retry_s))
sess.mount("https://", HTTPAdapter(max_retries=retry_s))
sess.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})

WAIT_CODE = 1

# ══════════════════════════════════════════════════════════════════
# СОХРАНЕНИЕ
# ══════════════════════════════════════════════════════════════════

def load_all():
    global stats, config, admins, users
    for fname, obj in [(STATS_FILE, stats), (CONFIG_FILE, config)]:
        if os.path.exists(fname):
            try:
                with open(fname, encoding="utf-8") as f:
                    obj.update(json.load(f))
            except Exception as e:
                log.warning(f"⚠️ Ошибка загрузки {fname}: {e}")
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
        log.error(f"❌ Ошибка сохранения: {e}")

def reg(update: Update):
    u = update.effective_user
    users[str(u.id)] = {
        "first_name": u.first_name or "",
        "username":   u.username   or "",
        "last_seen":  datetime.now().isoformat(),
    }
    stats["total_commands"] = stats.get("total_commands", 0) + 1

# ══════════════════════════════════════════════════════════════════
# ATERNOS
# ══════════════════════════════════════════════════════════════════

def aternos_login() -> bool:
    global aternos_connected
    if not all([ATERNOS_USER, ATERNOS_PASS, SERVER_ID]):
        log.warning("⚠️ Данные Aternos не заполнены")
        return False
    try:
        log.info("🔑 Логинюсь в Aternos...")
        sess.get("https://aternos.org/go/", timeout=15)
        r = sess.post(
            "https://aternos.org/panel/ajax/account/login.php",
            data={
                "user":     ATERNOS_USER,
                "password": hashlib.sha256(ATERNOS_PASS.encode()).hexdigest(),
            },
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://aternos.org/go/",
                "Origin":  "https://aternos.org",
            },
            timeout=15,
        )
        if r.status_code == 200:
            try:
                if r.json().get("error"):
                    log.error(f"❌ Логин ошибка: {r.json()}")
                    return False
            except Exception:
                pass
            aternos_connected = True
            log.info("✅ Aternos подключён!")
            update_server_info()
            return True
        log.error(f"❌ Логин: {r.status_code}")
        return False
    except Exception as e:
        log.error(f"❌ Aternos login: {e}")
        return False

def update_server_info():
    global server_status, current_players
    try:
        r = sess.get(f"https://aternos.org/api/server/{SERVER_ID}", timeout=15)
        if r.status_code == 200:
            d = r.json()
            server_status   = d.get("status", "offline")
            p = d.get("players", [])
            current_players = p if isinstance(p, list) else []
        return True
    except Exception as e:
        log.warning(f"⚠️ update_info: {e}")
        return False

def aternos_start() -> bool:
    global server_status
    try:
        r = sess.post(f"https://aternos.org/api/server/{SERVER_ID}/start", timeout=30)
        if r.status_code in (200, 201):
            server_status = "starting"
            return True
    except Exception as e:
        log.error(f"❌ start: {e}")
    return False

def aternos_stop() -> bool:
    global server_status
    try:
        r = sess.post(f"https://aternos.org/api/server/{SERVER_ID}/stop", timeout=30)
        if r.status_code in (200, 201):
            server_status = "offline"
            return True
    except Exception as e:
        log.error(f"❌ stop: {e}")
    return False

# ══════════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ══════════════════════════════════════════════════════════════════

def icon(s):
    return {"online":"🟢","offline":"🔴","starting":"🟡","loading":"🟡"}.get(s,"⚫")

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

def now_str():    return datetime.now().strftime("%H:%M:%S")
def now_full():   return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def get_uptime() -> str:
    if stats.get("uptime_from") and server_status == "online":
        delta = datetime.now() - datetime.fromisoformat(stats["uptime_from"])
        h = delta.seconds // 3600
        m = (delta.seconds % 3600) // 60
        return f"{h}ч {m}м"
    return "—"

# ══════════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ
# ══════════════════════════════════════════════════════════════════

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Запустить сервер", callback_data="on")],
        [InlineKeyboardButton("👥 Игроки онлайн",   callback_data="players"),
         InlineKeyboardButton("⚙️ Статус",          callback_data="status")],
        [InlineKeyboardButton("📊 Инфо",            callback_data="info"),
         InlineKeyboardButton("🗺 Как подключиться", callback_data="connect")],
    ])

def admin_kb():
    m = config.get("maintenance", False)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Запустить",   callback_data="adm_start"),
         InlineKeyboardButton("🔴 Остановить",  callback_data="adm_stop")],
        [InlineKeyboardButton("🔄 Перезапустить сервер", callback_data="adm_restart")],
        [InlineKeyboardButton("📢 Броадкаст",   callback_data="adm_broadcast")],
        [InlineKeyboardButton("👥 Пользователи",callback_data="adm_users")],
        [InlineKeyboardButton("📊 Статистика",  callback_data="adm_stats")],
        [InlineKeyboardButton(
            f"{'🔴 Выключить' if m else '🟢 Включить'} техобслуживание",
            callback_data="adm_maintenance"
        )],
        [InlineKeyboardButton("🔄 Переподключить Aternos", callback_data="adm_reconnect")],
        [InlineKeyboardButton("📜 Логи → этот чат",        callback_data="adm_setlog")],
        [InlineKeyboardButton("❌ Закрыть панель",          callback_data="adm_exit")],
    ])

# ══════════════════════════════════════════════════════════════════
# КОМАНДЫ — ОБЫЧНЫЕ ПОЛЬЗОВАТЕЛИ
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text(
            "🔧 <b>Технические работы</b>\n\nСервер временно недоступен. Попробуй позже!",
            parse_mode="HTML")
        return
    text = (
        f"<b>🎮 Добро пожаловать на {config['server_name']}!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} Сервер: <b>{server_status.upper()}</b>\n"
        f"👥 Игроков онлайн: <b>{len(current_players)}</b>\n"
        f"🌐 IP: <code>{config['server_ip']}</code>\n"
        f"🔌 Порт: <code>{config['server_port']}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Доступные команды:</b>\n"
        "▶️ /on — запустить сервер\n"
        "👥 /players — кто онлайн\n"
        "⚙️ /status — статус сервера\n"
        "📊 /info — статистика\n"
        "🗺 /connect — как подключиться\n"
        "📜 /rules — правила сервера\n"
        "❓ /help — все команды\n"
    )
    await get_msg(update).reply_text(text, reply_markup=main_kb(), parse_mode="HTML")


async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 <b>Техобслуживание. Подожди!</b>", parse_mode="HTML")
        return
    msg = await get_msg(update).reply_text("⏳ <b>Запускаю сервер...</b>", parse_mode="HTML")
    if not aternos_connected:
        await msg.edit_text("❌ <b>Aternos не подключён!</b>\nСообщи администратору.", parse_mode="HTML")
        await send_log(f"❌ Попытка запуска: нет соединения\n👤 {ulabel(update)}")
        return
    update_server_info()
    if server_status in ("online", "starting"):
        await msg.edit_text(
            f"✅ <b>Сервер уже {'работает' if server_status=='online' else 'запускается'}!</b>\n"
            f"🌐 Подключайся: <code>{config['server_ip']}</code>",
            parse_mode="HTML")
        return
    if aternos_start():
        stats["starts"] += 1
        stats["last_start"] = datetime.now().isoformat()
        stats["uptime_from"] = datetime.now().isoformat()
        save_all()
        await msg.edit_text(
            "🟢 <b>СЕРВЕР ЗАПУСКАЕТСЯ!</b>\n\n"
            f"⏰ Время: {now_str()}\n"
            f"🌐 IP: <code>{config['server_ip']}</code>\n"
            f"🔌 Порт: <code>{config['server_port']}</code>\n\n"
            "<i>⏱ Обычно загружается 1-3 минуты</i>",
            parse_mode="HTML")
        await send_log(
            f"🟢 <b>СЕРВЕР ЗАПУЩЕН</b>\n"
            f"👤 {ulabel(update)}\n"
            f"⏰ {now_full()}\n"
            f"📊 Запуск №{stats['starts']}")
    else:
        await msg.edit_text(
            "❌ <b>Не удалось запустить!</b>\n"
            "Попробуй через минуту или напиши администратору.", parse_mode="HTML")
        await send_log(f"❌ Ошибка запуска\n👤 {ulabel(update)}")


async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    update_server_info()
    if server_status != "online":
        await get_msg(update).reply_text(
            f"🔴 <b>Сервер выключен</b>\n\nЗапусти его командой /on!",
            parse_mode="HTML")
        return
    if not current_players:
        await get_msg(update).reply_text(
            "👥 <b>Сейчас никого нет</b> 😿\n\n"
            f"Сервер включён, но пусто.\n"
            f"🌐 Заходи: <code>{config['server_ip']}</code>",
            parse_mode="HTML")
        return
    if len(current_players) > stats["peak_players"]:
        stats["peak_players"] = len(current_players)
        save_all()
    pl_str = "\n".join(f"  🧑 <b>{p}</b>" for p in current_players)
    await get_msg(update).reply_text(
        f"👥 <b>ОНЛАЙН: {len(current_players)} игрок(ов)</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n{pl_str}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏱ Аптайм: {get_uptime()}",
        parse_mode="HTML")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    update_server_info()
    await get_msg(update).reply_text(
        f"{icon(server_status)} <b>СТАТУС СЕРВЕРА</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 Сервер: <b>{config['server_name']}</b> (Bedrock)\n"
        f"📍 Статус: <b>{server_status.upper()}</b>\n"
        f"👥 Игроков: <b>{len(current_players)}</b>\n"
        f"🌐 IP: <code>{config['server_ip']}</code>\n"
        f"🔌 Порт: <code>{config['server_port']}</code>\n"
        f"⏱ Аптайм: <b>{get_uptime()}</b>\n"
        f"🔌 Aternos: {'✅ подключён' if aternos_connected else '❌ нет'}\n"
        f"⏰ Проверено: {now_str()}",
        parse_mode="HTML")


async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    update_server_info()
    last_start = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "никогда"
    last_stop  = datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")  if stats.get("last_stop")  else "никогда"
    await get_msg(update).reply_text(
        f"<b>📊 ИНФОРМАЦИЯ — {config['server_name']}</b>\n\n"
        f"{icon(server_status)} {server_status.upper()} | 👥 {len(current_players)} онлайн\n\n"
        "<b>📈 Статистика:</b>\n"
        f"  🚀 Запусков: <b>{stats['starts']}</b>\n"
        f"  🛑 Остановок: <b>{stats['stops']}</b>\n"
        f"  🔄 Перезапусков: <b>{stats.get('restarts',0)}</b>\n"
        f"  👑 Пик игроков: <b>{stats['peak_players']}</b>\n"
        f"  ⏱ Аптайм: <b>{get_uptime()}</b>\n"
        f"  💬 Команд всего: <b>{stats.get('total_commands',0)}</b>\n"
        f"  👤 Пользователей: <b>{len(users)}</b>\n\n"
        "<b>⏰ Последние события:</b>\n"
        f"  ▶️ Запуск: {last_start}\n"
        f"  ⏹ Остановка: {last_stop}",
        parse_mode="HTML")


async def cmd_connect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    update_server_info()
    await get_msg(update).reply_text(
        f"🗺 <b>КАК ПОДКЛЮЧИТЬСЯ К {config['server_name'].upper()}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 Адрес: <code>{config['server_ip']}</code>\n"
        f"🔌 Порт: <code>{config['server_port']}</code>\n"
        f"📱 Версия: <b>Minecraft Bedrock</b>\n\n"
        "<b>📲 Инструкция:</b>\n"
        "1. Открой Minecraft Bedrock\n"
        "2. Нажми «Играть» → «Серверы»\n"
        "3. Прокрути вниз → «Добавить сервер»\n"
        f"4. Введи адрес: <code>{config['server_ip']}</code>\n"
        f"5. Порт: <code>{config['server_port']}</code>\n"
        "6. Сохрани и подключайся!\n\n"
        f"{icon(server_status)} Сервер сейчас: <b>{server_status.upper()}</b>\n"
        f"{'✅ Можно заходить!' if server_status=='online' else '⏳ Сначала запусти /on'}",
        parse_mode="HTML")


async def cmd_rules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await get_msg(update).reply_text(
        f"📜 <b>ПРАВИЛА СЕРВЕРА {config['server_name'].upper()}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>✅ Разрешено:</b>\n"
        "• Строить где угодно (кроме чужих территорий)\n"
        "• Торговать с другими игроками\n"
        "• Создавать кланы и союзы\n"
        "• PvP в специальных зонах\n\n"
        "<b>❌ Запрещено:</b>\n"
        "• Гриферство и уничтожение чужих построек\n"
        "• Читы, хакерские клиенты, дюп\n"
        "• Оскорбления и токсичность\n"
        "• Спам в чате\n"
        "• Реклама других серверов\n\n"
        "<b>⚠️ За нарушение:</b>\n"
        "• 1-е нарушение: предупреждение\n"
        "• 2-е нарушение: бан на 24 часа\n"
        "• 3-е нарушение: перманентный бан\n\n"
        "Приятной игры! 🎮",
        parse_mode="HTML")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    admin_hint = "\n\n🔐 <b>Для администраторов:</b>\n/admin — панель управления" if is_admin(update) else "\n\n💡 /admin — войти в панель администратора"
    await get_msg(update).reply_text(
        "<b>❓ ВСЕ КОМАНДЫ БОТА</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>🌐 Сервер:</b>\n"
        "▶️ /on — запустить сервер\n"
        "⚙️ /status — статус и IP\n"
        "👥 /players — кто онлайн\n"
        "📊 /info — полная статистика\n\n"
        "<b>📱 Информация:</b>\n"
        "🗺 /connect — как подключиться\n"
        "📜 /rules — правила сервера\n"
        "🎰 /random — случайный совет\n"
        "🕐 /uptime — время работы\n"
        "📅 /laststart — последний запуск\n"
        f"{admin_hint}",
        parse_mode="HTML")


async def cmd_random(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    tips = [
        "💡 Создай кровать — она устанавливает точку возрождения!",
        "⚔️ Зачарованный меч с «Добычей III» даёт больше ресурсов!",
        "🏠 Построй дом с дверью до первой ночи — зомби не войдут!",
        "🌾 Посади пшеницу — это основа выживания!",
        "🔥 Огниво поджигает непрочитанные блоки и создаёт порталы в Ад!",
        "🧪 Зелья скорости помогают быстрее перемещаться по миру!",
        "🗡 Прокачай лук — это лучшее оружие против скелетов!",
        "🛡 Щит блокирует урон — не забудь скрафтить!",
        "💎 Алмазы чаще встречаются на уровне Y=-58 в Java Edition!",
        "🐝 Пчёлы опыляют цветы и дают мёд — строй ульи рядом с фермой!",
        "🎣 Рыбалка ночью даёт лучшие результаты!",
        "🏔 Изумруды можно найти только в горах — торгуй с жителями!",
        "🧊 Лёд упакованный не тает под источниками света!",
        "🌊 Дыхание воды II позволяет строить под водой!",
        "⚡ Молния превращает свинью в свиножителя!",
    ]
    tip = random.choice(tips)
    await get_msg(update).reply_text(
        f"🎲 <b>СЛУЧАЙНЫЙ СОВЕТ</b>\n\n{tip}\n\n<i>Используй /random ещё раз для нового совета!</i>",
        parse_mode="HTML")


async def cmd_uptime(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    update_server_info()
    await get_msg(update).reply_text(
        f"⏱ <b>ВРЕМЯ РАБОТЫ</b>\n\n"
        f"{icon(server_status)} Статус: <b>{server_status.upper()}</b>\n"
        f"⏱ Аптайм: <b>{get_uptime()}</b>\n"
        f"⏰ Проверено: {now_full()}",
        parse_mode="HTML")


async def cmd_laststart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    last = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m.%Y в %H:%M:%S") if stats.get("last_start") else "никогда"
    last_stop = datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m.%Y в %H:%M:%S") if stats.get("last_stop") else "никогда"
    await get_msg(update).reply_text(
        f"📅 <b>ИСТОРИЯ СОБЫТИЙ</b>\n\n"
        f"▶️ Последний запуск: <b>{last}</b>\n"
        f"⏹ Последняя остановка: <b>{last_stop}</b>\n"
        f"🚀 Всего запусков: <b>{stats['starts']}</b>\n"
        f"🔄 Перезапусков: <b>{stats.get('restarts',0)}</b>",
        parse_mode="HTML")


async def cmd_logthischat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if not is_admin(update):
        await get_msg(update).reply_text("🚫 <b>Только для администраторов!</b>", parse_mode="HTML")
        return
    chat_id = update.effective_chat.id
    config["log_chat_id"] = chat_id
    save_all()
    await update.message.reply_text(f"✅ <b>Логи теперь здесь!</b>\nID: <code>{chat_id}</code>", parse_mode="HTML")
    await send_log(f"✅ <b>Чат логов изменён</b>\n👤 {ulabel(update)}\nID: <code>{chat_id}</code>", chat_id=chat_id)

# ══════════════════════════════════════════════════════════════════
# CALLBACK — ОБЫЧНЫЕ КНОПКИ
# ══════════════════════════════════════════════════════════════════

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    handlers = {
        "on":      cmd_on,
        "players": cmd_players,
        "status":  cmd_status,
        "info":    cmd_info,
        "connect": cmd_connect,
    }
    fn = handlers.get(q.data)
    if fn:
        await fn(update, ctx)

# ══════════════════════════════════════════════════════════════════
# ADMIN — ВХОД
# ══════════════════════════════════════════════════════════════════

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if is_admin(update):
        await show_admin_panel(update, ctx)
        return
    await update.message.reply_text(
        "🔐 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "Введите 4-значный код доступа:",
        parse_mode="HTML")
    return WAIT_CODE

async def got_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code == ADMIN_CODE:
        admins.add(update.effective_user.id)
        save_all()
        await update.message.reply_text("✅ <b>Добро пожаловать, Администратор!</b>", parse_mode="HTML")
        await send_log(
            f"🔐 <b>НОВЫЙ АДМИНИСТРАТОР</b>\n"
            f"👤 {ulabel(update)}\n⏰ {now_full()}")
        await show_admin_panel(update, ctx)
    else:
        await update.message.reply_text("❌ <b>Неверный код!</b>", parse_mode="HTML")
        await send_log(
            f"⚠️ <b>НЕУДАЧНАЯ ПОПЫТКА В АДМИНКУ</b>\n"
            f"👤 {ulabel(update)}\n🔢 Код: <code>{code}</code>")
    return ConversationHandler.END

async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

async def show_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    update_server_info()
    m = config.get("maintenance", False)
    await get_msg(update).reply_text(
        "⚙️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Aternos: {'✅ подключён' if aternos_connected else '❌ нет'}\n"
        f"🖥 Сервер: {icon(server_status)} {server_status.upper()}\n"
        f"👥 Игроков: {len(current_players)}\n"
        f"👤 Пользователей: {len(users)}\n"
        f"🔐 Админов: {len(admins)}\n"
        f"🔧 Техобслуживание: {'🟡 ВКЛ' if m else '🟢 ВЫКЛ'}\n"
        "━━━━━━━━━━━━━━━━━━━━",
        reply_markup=admin_kb(), parse_mode="HTML")

# ══════════════════════════════════════════════════════════════════
# ADMIN — КНОПКИ
# ══════════════════════════════════════════════════════════════════

async def on_admin_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not is_admin(update):
        await q.answer("🚫 Нет доступа!", show_alert=True)
        return

    d = q.data

    # ── Запустить ──────────────────────────────────────────────
    if d == "adm_start":
        await q.message.edit_text("⏳ <b>Запускаю...</b>", parse_mode="HTML")
        update_server_info()
        if server_status in ("online", "starting"):
            await q.message.edit_text("✅ <b>Уже работает!</b>", reply_markup=admin_kb(), parse_mode="HTML")
            return
        if aternos_start():
            stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat()
            stats["uptime_from"] = datetime.now().isoformat()
            save_all()
            await q.message.edit_text(
                f"🟢 <b>СЕРВЕР ЗАПУЩЕН!</b>\n⏰ {now_str()}",
                reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🟢 <b>ЗАПУСК (ADMIN)</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        else:
            await q.message.edit_text("❌ <b>Не удалось!</b>", reply_markup=admin_kb(), parse_mode="HTML")
        return

    # ── Остановить ─────────────────────────────────────────────
    if d == "adm_stop":
        await q.message.edit_text("⏳ <b>Останавливаю...</b>", parse_mode="HTML")
        update_server_info()
        if server_status == "offline":
            await q.message.edit_text("🔴 <b>Уже выключен!</b>", reply_markup=admin_kb(), parse_mode="HTML")
            return
        if aternos_stop():
            stats["stops"] += 1
            stats["last_stop"] = datetime.now().isoformat()
            stats["uptime_from"] = None
            save_all()
            await q.message.edit_text(
                f"🔴 <b>СЕРВЕР ОСТАНОВЛЕН!</b>\n⏰ {now_str()}",
                reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔴 <b>ОСТАНОВКА (ADMIN)</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        else:
            await q.message.edit_text("❌ <b>Не удалось!</b>", reply_markup=admin_kb(), parse_mode="HTML")
        return

    # ── Перезапустить ──────────────────────────────────────────
    if d == "adm_restart":
        await q.message.edit_text("⏳ <b>Перезапускаю сервер...</b>", parse_mode="HTML")
        aternos_stop()
        await asyncio.sleep(5)
        if aternos_start():
            stats["restarts"] = stats.get("restarts", 0) + 1
            stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat()
            stats["uptime_from"] = datetime.now().isoformat()
            save_all()
            await q.message.edit_text(
                f"🔄 <b>СЕРВЕР ПЕРЕЗАПУЩЕН!</b>\n⏰ {now_str()}",
                reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔄 <b>ПЕРЕЗАПУСК (ADMIN)</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        else:
            await q.message.edit_text("❌ <b>Не удалось!</b>", reply_markup=admin_kb(), parse_mode="HTML")
        return

    # ── Броадкаст ──────────────────────────────────────────────
    if d == "adm_broadcast":
        ctx.user_data["waiting_broadcast"] = True
        await q.message.reply_text(
            "📢 <b>БРОАДКАСТ</b>\n\n"
            "Напиши сообщение — его получат все пользователи.\n"
            "<i>Отправь /cancel для отмены</i>",
            parse_mode="HTML")
        return

    # ── Пользователи ───────────────────────────────────────────
    if d == "adm_users":
        if not users:
            await q.message.edit_text("👥 <b>Пользователей ещё нет</b>", reply_markup=admin_kb(), parse_mode="HTML")
            return
        lines = []
        for uid, info in list(users.items())[-15:]:
            name  = info.get("first_name","???")
            uname = f"@{info['username']}" if info.get("username") else "—"
            try:    seen = datetime.fromisoformat(info.get("last_seen","")).strftime("%d.%m %H:%M")
            except: seen = "—"
            mark = " 🔐" if int(uid) in admins else ""
            lines.append(f"• {name} {uname}{mark} | <i>{seen}</i>")
        text = f"👥 <b>ПОЛЬЗОВАТЕЛИ ({len(users)} всего)</b>\n\n" + "\n".join(lines)
        await q.message.edit_text(text, reply_markup=admin_kb(), parse_mode="HTML")
        return

    # ── Статистика ─────────────────────────────────────────────
    if d == "adm_stats":
        update_server_info()
        last_start = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "никогда"
        last_stop  = datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")  if stats.get("last_stop")  else "никогда"
        text = (
            "📊 <b>ПОЛНАЯ СТАТИСТИКА</b>\n\n"
            f"🚀 Запусков: <b>{stats['starts']}</b>\n"
            f"🛑 Остановок: <b>{stats['stops']}</b>\n"
            f"🔄 Перезапусков: <b>{stats.get('restarts',0)}</b>\n"
            f"👑 Пик игроков: <b>{stats['peak_players']}</b>\n"
            f"⏱ Аптайм: <b>{get_uptime()}</b>\n"
            f"💬 Команд: <b>{stats.get('total_commands',0)}</b>\n"
            f"👤 Пользователей: <b>{len(users)}</b>\n"
            f"🔐 Админов: <b>{len(admins)}</b>\n\n"
            f"▶️ Запуск: {last_start}\n"
            f"⏹ Стоп: {last_stop}\n"
            f"⏰ Сейчас: {now_full()}"
        )
        await q.message.edit_text(text, reply_markup=admin_kb(), parse_mode="HTML")
        return

    # ── Техобслуживание ────────────────────────────────────────
    if d == "adm_maintenance":
        config["maintenance"] = not config.get("maintenance", False)
        save_all()
        word = "ВКЛЮЧЕНО 🟡" if config["maintenance"] else "ВЫКЛЮЧЕНО 🟢"
        await q.message.edit_text(
            f"🔧 <b>Техобслуживание {word}</b>",
            reply_markup=admin_kb(), parse_mode="HTML")
        await send_log(f"🔧 <b>Техобслуживание {word}</b>\n👤 {ulabel(update)}")
        return

    # ── Переподключить Aternos ─────────────────────────────────
    if d == "adm_reconnect":
        await q.message.edit_text("⏳ <b>Переподключаюсь...</b>", parse_mode="HTML")
        ok = aternos_login()
        result = "✅ Подключён!" if ok else "❌ Не удалось"
        await q.message.edit_text(
            f"🔌 <b>Aternos: {result}</b>",
            reply_markup=admin_kb(), parse_mode="HTML")
        await send_log(f"🔌 <b>Переподключение: {result}</b>\n👤 {ulabel(update)}")
        return

    # ── Установить лог-чат ─────────────────────────────────────
    if d == "adm_setlog":
        cid = q.message.chat_id
        config["log_chat_id"] = cid
        save_all()
        await q.message.edit_text(
            f"✅ <b>Логи теперь здесь!</b>\nID: <code>{cid}</code>",
            reply_markup=admin_kb(), parse_mode="HTML")
        return

    # ── Выход ──────────────────────────────────────────────────
    if d == "adm_exit":
        await q.message.edit_text("👋 <b>Панель закрыта.</b>", parse_mode="HTML")
        return

# ══════════════════════════════════════════════════════════════════
# БРОАДКАСТ — ПРИЁМ ТЕКСТА
# ══════════════════════════════════════════════════════════════════

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("waiting_broadcast"):
        return
    if not is_admin(update):
        return

    text = update.message.text.strip()
    if text.startswith("/cancel"):
        ctx.user_data["waiting_broadcast"] = False
        await update.message.reply_text("❌ Броадкаст отменён.")
        return

    ctx.user_data["waiting_broadcast"] = False
    broadcast_text = (
        f"📢 <b>ОБЪЯВЛЕНИЕ — {config['server_name']}</b>\n\n"
        f"{text}\n\n"
        f"<i>— Администрация</i>"
    )

    sent = 0
    failed = 0
    status_msg = await update.message.reply_text("⏳ <b>Отправляю...</b>", parse_mode="HTML")

    for uid in list(users.keys()):
        try:
            await telegram_app.bot.send_message(int(uid), broadcast_text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"📢 <b>Броадкаст отправлен!</b>\n\n"
        f"✅ Доставлено: <b>{sent}</b>\n"
        f"❌ Не доставлено: <b>{failed}</b>",
        parse_mode="HTML")
    await send_log(
        f"📢 <b>БРОАДКАСТ</b>\n"
        f"👤 {ulabel(update)}\n"
        f"✅ {sent} / ❌ {failed}\n\n"
        f"<i>{text[:200]}</i>")

# ══════════════════════════════════════════════════════════════════
# АВТО-ОТЧЁТ
# ══════════════════════════════════════════════════════════════════

async def auto_report():
    await asyncio.sleep(30)
    while True:
        await asyncio.sleep(600)
        if not aternos_connected:
            continue
        update_server_info()
        if server_status != "online":
            continue
        try:
            pl_str = "\n".join(f"  • {p}" for p in current_players) if current_players else "  (никого)"
            await send_log(
                "🟢 <b>АВТООТЧЁТ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {now_full()}\n"
                f"⏱ Аптайм: {get_uptime()}\n"
                f"👥 Игроки ({len(current_players)}):\n{pl_str}")
        except Exception as e:
            log.error(f"❌ auto_report: {e}")

# ══════════════════════════════════════════════════════════════════
# FLASK
# ══════════════════════════════════════════════════════════════════

flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return jsonify({
        "status": "ok", "bot": "fictionmine-bot v10.0",
        "server": server_status, "players": len(current_players),
        "aternos": aternos_connected,
    }), 200

@flask_app.route("/ping")
def ping():
    return "pong", 200

def run_flask():
    log.info(f"🌐 Flask на 0.0.0.0:{PORT}")
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

async def main():
    global telegram_app

    load_all()
    aternos_login()

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

    # ConversationHandler для /admin
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", cmd_admin)],
        states={WAIT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_code)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)],
    )

    telegram_app.add_handler(admin_conv)
    telegram_app.add_handler(CommandHandler("start",       cmd_start))
    telegram_app.add_handler(CommandHandler("on",          cmd_on))
    telegram_app.add_handler(CommandHandler("players",     cmd_players))
    telegram_app.add_handler(CommandHandler("status",      cmd_status))
    telegram_app.add_handler(CommandHandler("info",        cmd_info))
    telegram_app.add_handler(CommandHandler("connect",     cmd_connect))
    telegram_app.add_handler(CommandHandler("rules",       cmd_rules))
    telegram_app.add_handler(CommandHandler("help",        cmd_help))
    telegram_app.add_handler(CommandHandler("random",      cmd_random))
    telegram_app.add_handler(CommandHandler("uptime",      cmd_uptime))
    telegram_app.add_handler(CommandHandler("laststart",   cmd_laststart))
    telegram_app.add_handler(CommandHandler("logthischat", cmd_logthischat))

    telegram_app.add_handler(CallbackQueryHandler(on_admin_button, pattern="^adm_"))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("✅ Telegram бот готов!")
    asyncio.create_task(auto_report())

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await asyncio.Event().wait()


if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Бот остановлен")
    except Exception as e:
        log.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
