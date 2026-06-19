#!/usr/bin/env python3
"""
ATERNOS TELEGRAM BOT v11.0
python-aternos бібліотека для логіну (обходить Cloudflare)
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
log.info("🎮 ATERNOS BOT v11.0 — python-aternos edition")
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
}
admins: set = set()
users: dict = {}

telegram_app      = None
aternos_client    = None   # python-aternos клієнт
aternos_server    = None   # об'єкт сервера
aternos_connected = False
server_status     = "offline"
current_players   = []

WAIT_CODE = 1

# ══════════════════════════════════════════════════════════════════
# ЗБЕРЕЖЕННЯ
# ══════════════════════════════════════════════════════════════════

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
# ATERNOS — python-aternos бібліотека
# ══════════════════════════════════════════════════════════════════

def aternos_login() -> bool:
    global aternos_client, aternos_server, aternos_connected, server_status, current_players

    if not all([ATERNOS_USER, ATERNOS_PASS, SERVER_ID]):
        log.warning("⚠️ Данные Aternos не заполнены")
        return False

    try:
        from python_aternos import Client, AternoskeyError, AternosPermissionError

        log.info(f"🔑 Логинюсь в Aternos как {ATERNOS_USER}...")

        # Логін через python-aternos
        aternos_client = Client.from_credentials(ATERNOS_USER, ATERNOS_PASS)

        # Отримуємо список серверів
        servers = aternos_client.list_servers()
        log.info(f"✅ Знайдено серверів: {len(servers)}")

        # Шукаємо наш сервер по ID або беремо перший
        aternos_server = None
        for srv in servers:
            log.info(f"   Сервер: {srv.address} (id={srv.servid})")
            if SERVER_ID in str(srv.servid) or SERVER_ID in str(srv.address):
                aternos_server = srv
                break

        if aternos_server is None and servers:
            aternos_server = servers[0]
            log.info(f"   Беру перший сервер: {aternos_server.address}")

        if aternos_server is None:
            log.error("❌ Сервери не знайдені!")
            return False

        aternos_connected = True
        log.info(f"✅ Підключено до сервера: {aternos_server.address}")

        # Оновлюємо статус
        update_server_info()
        return True

    except ImportError:
        log.error("❌ python-aternos не встановлено! Перевір requirements.txt")
        return False
    except Exception as e:
        log.error(f"❌ Помилка логіну Aternos: {e}", exc_info=True)
        return False


def update_server_info() -> bool:
    global server_status, current_players
    if not aternos_server:
        return False
    try:
        aternos_server.fetch()
        server_status   = aternos_server.status
        current_players = list(aternos_server.players) if hasattr(aternos_server, 'players') else []
        log.info(f"📊 Статус: {server_status} | Гравців: {len(current_players)}")
        return True
    except Exception as e:
        log.warning(f"⚠️ update_info: {e}")
        return False


def aternos_start() -> bool:
    global server_status
    if not aternos_server:
        return False
    try:
        aternos_server.start()
        server_status = "starting"
        log.info("✅ Сервер запускається!")
        return True
    except Exception as e:
        log.error(f"❌ Помилка запуску: {e}")
        return False


def aternos_stop() -> bool:
    global server_status
    if not aternos_server:
        return False
    try:
        aternos_server.stop()
        server_status = "offline"
        log.info("✅ Сервер зупинено!")
        return True
    except Exception as e:
        log.error(f"❌ Помилка зупинки: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# УТИЛІТИ
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
        [InlineKeyboardButton("🟢 Запустить сервер", callback_data="on")],
        [InlineKeyboardButton("👥 Игроки онлайн",    callback_data="players"),
         InlineKeyboardButton("⚙️ Статус",           callback_data="status")],
        [InlineKeyboardButton("📊 Инфо",             callback_data="info"),
         InlineKeyboardButton("🗺 Подключиться",      callback_data="connect")],
    ])

def admin_kb():
    m = config.get("maintenance", False)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Запустить",        callback_data="adm_start"),
         InlineKeyboardButton("🔴 Остановить",       callback_data="adm_stop")],
        [InlineKeyboardButton("🔄 Перезапустить",    callback_data="adm_restart")],
        [InlineKeyboardButton("📢 Броадкаст",        callback_data="adm_broadcast")],
        [InlineKeyboardButton("👥 Пользователи",     callback_data="adm_users")],
        [InlineKeyboardButton("📊 Статистика",       callback_data="adm_stats")],
        [InlineKeyboardButton(
            f"{'🔴 Выкл' if m else '🟢 Вкл'} техобслуживание",
            callback_data="adm_maintenance"
        )],
        [InlineKeyboardButton("🔄 Переподключить Aternos", callback_data="adm_reconnect")],
        [InlineKeyboardButton("📜 Логи → этот чат",        callback_data="adm_setlog")],
        [InlineKeyboardButton("❌ Закрыть панель",          callback_data="adm_exit")],
    ])

# ══════════════════════════════════════════════════════════════════
# КОМАНДИ — ЗВИЧАЙНІ КОРИСТУВАЧІ
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 <b>Технические работы.</b>\nПопробуй позже!", parse_mode="HTML")
        return
    text = (
        f"<b>🎮 Добро пожаловать на {config['server_name']}!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon(server_status)} Сервер: <b>{server_status.upper()}</b>\n"
        f"👥 Игроков: <b>{len(current_players)}</b>\n"
        f"🌐 IP: <code>{config['server_ip']}</code>\n"
        f"🔌 Порт: <code>{config['server_port']}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Команды:</b>\n"
        "▶️ /on — запустить сервер\n"
        "👥 /players — кто онлайн\n"
        "⚙️ /status — статус\n"
        "📊 /info — статистика\n"
        "🗺 /connect — как войти\n"
        "📜 /rules — правила\n"
        "🎲 /random — совет\n"
        "❓ /help — все команды"
    )
    await get_msg(update).reply_text(text, reply_markup=main_kb(), parse_mode="HTML")


async def cmd_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); save_all(); await typing(update)
    if config.get("maintenance") and not is_admin(update):
        await get_msg(update).reply_text("🔧 <b>Техобслуживание!</b>", parse_mode="HTML")
        return
    msg = await get_msg(update).reply_text("⏳ <b>Запускаю сервер...</b>", parse_mode="HTML")
    if not aternos_connected:
        await msg.edit_text("❌ <b>Aternos не подключён!</b>\nСообщи администратору.", parse_mode="HTML")
        await send_log(f"❌ Попытка запуска без соединения\n👤 {ulabel(update)}")
        return
    await asyncio.to_thread(update_server_info)
    if server_status in ("online", "starting"):
        await msg.edit_text(
            f"✅ <b>Сервер уже работает!</b>\n"
            f"🌐 <code>{config['server_ip']}</code>",
            parse_mode="HTML")
        return
    ok = await asyncio.to_thread(aternos_start)
    if ok:
        stats["starts"] += 1
        stats["last_start"] = datetime.now().isoformat()
        stats["uptime_from"] = datetime.now().isoformat()
        save_all()
        await msg.edit_text(
            "🟢 <b>СЕРВЕР ЗАПУСКАЕТСЯ!</b>\n\n"
            f"⏰ {now_str()}\n"
            f"🌐 <code>{config['server_ip']}</code>\n"
            f"🔌 Порт: <code>{config['server_port']}</code>\n\n"
            "<i>⏱ Подожди 1-3 минуты</i>",
            parse_mode="HTML")
        await send_log(
            f"🟢 <b>СЕРВЕР ЗАПУЩЕН</b>\n"
            f"👤 {ulabel(update)}\n"
            f"⏰ {now_full()}\n"
            f"📊 Запуск №{stats['starts']}")
    else:
        await msg.edit_text("❌ <b>Не удалось запустить!</b>\nПопробуй позже.", parse_mode="HTML")
        await send_log(f"❌ Ошибка запуска\n👤 {ulabel(update)}")


async def cmd_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await asyncio.to_thread(update_server_info)
    if server_status != "online":
        await get_msg(update).reply_text("🔴 <b>Сервер выключен.</b>\nЗапусти /on", parse_mode="HTML")
        return
    if not current_players:
        await get_msg(update).reply_text(
            f"👥 <b>Никого нет</b> 😿\n\n🌐 <code>{config['server_ip']}</code>",
            parse_mode="HTML")
        return
    if len(current_players) > stats["peak_players"]:
        stats["peak_players"] = len(current_players)
        save_all()
    pl_str = "\n".join(f"  🧑 <b>{p}</b>" for p in current_players)
    await get_msg(update).reply_text(
        f"👥 <b>ОНЛАЙН: {len(current_players)}</b>\n\n{pl_str}\n\n⏱ {get_uptime()}",
        parse_mode="HTML")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await asyncio.to_thread(update_server_info)
    await get_msg(update).reply_text(
        f"{icon(server_status)} <b>СТАТУС СЕРВЕРА</b>\n\n"
        f"🎮 {config['server_name']} (Bedrock)\n"
        f"📍 {server_status.upper()}\n"
        f"👥 Игроков: <b>{len(current_players)}</b>\n"
        f"🌐 <code>{config['server_ip']}</code>\n"
        f"🔌 Порт: <code>{config['server_port']}</code>\n"
        f"⏱ Аптайм: <b>{get_uptime()}</b>\n"
        f"⏰ {now_str()}",
        parse_mode="HTML")


async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await asyncio.to_thread(update_server_info)
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
        f"  💬 Команд: <b>{stats.get('total_commands',0)}</b>\n"
        f"  👤 Пользователей: <b>{len(users)}</b>\n\n"
        f"▶️ Запуск: {last_start}\n"
        f"⏹ Стоп: {last_stop}",
        parse_mode="HTML")


async def cmd_connect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await asyncio.to_thread(update_server_info)
    await get_msg(update).reply_text(
        f"🗺 <b>КАК ПОДКЛЮЧИТЬСЯ</b>\n\n"
        f"🌐 Адрес: <code>{config['server_ip']}</code>\n"
        f"🔌 Порт: <code>{config['server_port']}</code>\n"
        f"📱 Платформа: <b>Minecraft Bedrock</b>\n\n"
        "<b>📲 Инструкция:</b>\n"
        "1. Открой Minecraft\n"
        "2. Играть → Серверы\n"
        "3. Добавить сервер\n"
        f"4. Адрес: <code>{config['server_ip']}</code>\n"
        f"5. Порт: <code>{config['server_port']}</code>\n"
        "6. Сохрани и подключайся!\n\n"
        f"{icon(server_status)} Сервер: <b>{server_status.upper()}</b>",
        parse_mode="HTML")


async def cmd_rules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await get_msg(update).reply_text(
        f"📜 <b>ПРАВИЛА — {config['server_name'].upper()}</b>\n\n"
        "<b>✅ Разрешено:</b>\n"
        "• Строить и исследовать\n"
        "• Торговать с игроками\n"
        "• Создавать кланы\n"
        "• PvP в специальных зонах\n\n"
        "<b>❌ Запрещено:</b>\n"
        "• Гриферство чужих построек\n"
        "• Читы и дюпы\n"
        "• Оскорбления и токсичность\n"
        "• Спам в чате\n"
        "• Реклама других серверов\n\n"
        "<b>⚠️ За нарушение:</b>\n"
        "• 1-е: предупреждение\n"
        "• 2-е: бан 24 часа\n"
        "• 3-е: перманентный бан\n\n"
        "Приятной игры! 🎮",
        parse_mode="HTML")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    admin_tip = "\n🔐 /admin — панель администратора" if is_admin(update) else "\n💡 /admin — войти как администратор"
    await get_msg(update).reply_text(
        "<b>❓ ВСЕ КОМАНДЫ</b>\n\n"
        "<b>🌐 Сервер:</b>\n"
        "▶️ /on — запустить\n"
        "⚙️ /status — статус\n"
        "👥 /players — онлайн\n"
        "📊 /info — статистика\n\n"
        "<b>📱 Информация:</b>\n"
        "🗺 /connect — как подключиться\n"
        "📜 /rules — правила\n"
        "🎲 /random — совет Minecraft\n"
        "⏱ /uptime — время работы\n"
        "📅 /laststart — последний запуск"
        f"{admin_tip}",
        parse_mode="HTML")


async def cmd_random(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    tips = [
        "💡 Кровать устанавливает точку возрождения!",
        "⚔️ Зачарование «Добыча III» даёт больше ресурсов!",
        "🏠 Построй дом до первой ночи — зомби не войдут!",
        "🌾 Пшеница — основа выживания!",
        "🔥 Огниво создаёт порталы в Ад!",
        "🧪 Зелья скорости ускоряют передвижение!",
        "🗡 Прокачай лук — лучшее против скелетов!",
        "🛡 Щит блокирует урон — не забудь скрафтить!",
        "💎 Алмазы чаще на уровне Y=-58!",
        "🐝 Пчёлы дают мёд — строй ульи рядом с фермой!",
        "🎣 Рыбалка ночью даёт лучшие результаты!",
        "🏔 Изумруды только в горах — торгуй с жителями!",
        "🧊 Лёд упакованный не тает под светом!",
        "⚡ Молния превращает свинью в свиножителя!",
        "🌙 Спи в кровати ночью чтобы пропустить ночь!",
    ]
    await get_msg(update).reply_text(
        f"🎲 <b>СОВЕТ ДНЯ</b>\n\n{random.choice(tips)}\n\n<i>/random — ещё совет!</i>",
        parse_mode="HTML")


async def cmd_uptime(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    await asyncio.to_thread(update_server_info)
    await get_msg(update).reply_text(
        f"⏱ <b>ВРЕМЯ РАБОТЫ</b>\n\n"
        f"{icon(server_status)} {server_status.upper()}\n"
        f"⏱ Аптайм: <b>{get_uptime()}</b>\n"
        f"⏰ {now_full()}",
        parse_mode="HTML")


async def cmd_laststart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update); await typing(update)
    last = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m.%Y в %H:%M") if stats.get("last_start") else "никогда"
    last_stop = datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m.%Y в %H:%M") if stats.get("last_stop") else "никогда"
    await get_msg(update).reply_text(
        f"📅 <b>ИСТОРИЯ</b>\n\n"
        f"▶️ Запуск: <b>{last}</b>\n"
        f"⏹ Стоп: <b>{last_stop}</b>\n"
        f"🚀 Всего запусков: <b>{stats['starts']}</b>",
        parse_mode="HTML")


async def cmd_logthischat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if not is_admin(update):
        await get_msg(update).reply_text("🚫 <b>Только для администраторов!</b>", parse_mode="HTML")
        return
    chat_id = update.effective_chat.id
    config["log_chat_id"] = chat_id
    save_all()
    await update.message.reply_text(f"✅ <b>Логи здесь!</b>\nID: <code>{chat_id}</code>", parse_mode="HTML")

# ══════════════════════════════════════════════════════════════════
# CALLBACK — ЗВИЧАЙНІ КНОПКИ
# ══════════════════════════════════════════════════════════════════

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    handlers = {
        "on": cmd_on, "players": cmd_players,
        "status": cmd_status, "info": cmd_info, "connect": cmd_connect,
    }
    fn = handlers.get(q.data)
    if fn:
        await fn(update, ctx)

# ══════════════════════════════════════════════════════════════════
# ADMIN — ВХІД
# ══════════════════════════════════════════════════════════════════

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update)
    if is_admin(update):
        await show_admin_panel(update, ctx)
        return
    await update.message.reply_text(
        "🔐 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\nВведите код доступа:",
        parse_mode="HTML")
    return WAIT_CODE

async def got_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code == ADMIN_CODE:
        admins.add(update.effective_user.id)
        save_all()
        await update.message.reply_text("✅ <b>Добро пожаловать, Администратор!</b>", parse_mode="HTML")
        await send_log(f"🔐 <b>НОВЫЙ АДМИНИСТРАТОР</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        await show_admin_panel(update, ctx)
    else:
        await update.message.reply_text("❌ <b>Неверный код!</b>", parse_mode="HTML")
        await send_log(f"⚠️ <b>НЕУДАЧНАЯ ПОПЫТКА В АДМИНКУ</b>\n👤 {ulabel(update)}\n🔢 <code>{code}</code>")
    return ConversationHandler.END

async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

async def show_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(update_server_info)
    m = config.get("maintenance", False)
    await get_msg(update).reply_text(
        "⚙️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Aternos: {'✅' if aternos_connected else '❌'}\n"
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

    if d == "adm_start":
        await q.message.edit_text("⏳ <b>Запускаю...</b>", parse_mode="HTML")
        await asyncio.to_thread(update_server_info)
        if server_status in ("online", "starting"):
            await q.message.edit_text("✅ <b>Уже работает!</b>", reply_markup=admin_kb(), parse_mode="HTML")
            return
        ok = await asyncio.to_thread(aternos_start)
        if ok:
            stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat()
            stats["uptime_from"] = datetime.now().isoformat()
            save_all()
            await q.message.edit_text(f"🟢 <b>ЗАПУЩЕН!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🟢 <b>ЗАПУСК (ADMIN)</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")
        return

    if d == "adm_stop":
        await q.message.edit_text("⏳ <b>Останавливаю...</b>", parse_mode="HTML")
        await asyncio.to_thread(update_server_info)
        if server_status == "offline":
            await q.message.edit_text("🔴 <b>Уже выключен!</b>", reply_markup=admin_kb(), parse_mode="HTML")
            return
        ok = await asyncio.to_thread(aternos_stop)
        if ok:
            stats["stops"] += 1
            stats["last_stop"] = datetime.now().isoformat()
            stats["uptime_from"] = None
            save_all()
            await q.message.edit_text(f"🔴 <b>ОСТАНОВЛЕН!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔴 <b>СТОП (ADMIN)</b>\n👤 {ulabel(update)}\n⏰ {now_full()}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")
        return

    if d == "adm_restart":
        await q.message.edit_text("⏳ <b>Перезапускаю...</b>", parse_mode="HTML")
        await asyncio.to_thread(aternos_stop)
        await asyncio.sleep(5)
        ok = await asyncio.to_thread(aternos_start)
        if ok:
            stats["restarts"] = stats.get("restarts", 0) + 1
            stats["starts"] += 1
            stats["last_start"] = datetime.now().isoformat()
            stats["uptime_from"] = datetime.now().isoformat()
            save_all()
            await q.message.edit_text(f"🔄 <b>ПЕРЕЗАПУЩЕН!</b>\n⏰ {now_str()}", reply_markup=admin_kb(), parse_mode="HTML")
            await send_log(f"🔄 <b>ПЕРЕЗАПУСК (ADMIN)</b>\n👤 {ulabel(update)}")
        else:
            await q.message.edit_text("❌ <b>Ошибка!</b>", reply_markup=admin_kb(), parse_mode="HTML")
        return

    if d == "adm_broadcast":
        ctx.user_data["waiting_broadcast"] = True
        await q.message.reply_text(
            "📢 <b>БРОАДКАСТ</b>\n\nНапиши сообщение для всех пользователей.\n<i>/cancel для отмены</i>",
            parse_mode="HTML")
        return

    if d == "adm_users":
        if not users:
            await q.message.edit_text("👥 Нет пользователей", reply_markup=admin_kb(), parse_mode="HTML")
            return
        lines = []
        for uid, info in list(users.items())[-15:]:
            name  = info.get("first_name", "???")
            uname = f"@{info['username']}" if info.get("username") else "—"
            try:    seen = datetime.fromisoformat(info.get("last_seen","")).strftime("%d.%m %H:%M")
            except: seen = "—"
            mark = " 🔐" if int(uid) in admins else ""
            lines.append(f"• {name} {uname}{mark} | <i>{seen}</i>")
        await q.message.edit_text(
            f"👥 <b>ПОЛЬЗОВАТЕЛИ ({len(users)})</b>\n\n" + "\n".join(lines),
            reply_markup=admin_kb(), parse_mode="HTML")
        return

    if d == "adm_stats":
        await asyncio.to_thread(update_server_info)
        last_start = datetime.fromisoformat(stats["last_start"]).strftime("%d.%m %H:%M") if stats.get("last_start") else "никогда"
        last_stop  = datetime.fromisoformat(stats["last_stop"]).strftime("%d.%m %H:%M")  if stats.get("last_stop")  else "никогда"
        await q.message.edit_text(
            "📊 <b>СТАТИСТИКА</b>\n\n"
            f"🚀 Запусков: <b>{stats['starts']}</b>\n"
            f"🛑 Остановок: <b>{stats['stops']}</b>\n"
            f"🔄 Перезапусков: <b>{stats.get('restarts',0)}</b>\n"
            f"👑 Пик: <b>{stats['peak_players']}</b>\n"
            f"⏱ Аптайм: <b>{get_uptime()}</b>\n"
            f"💬 Команд: <b>{stats.get('total_commands',0)}</b>\n"
            f"👤 Пользователей: <b>{len(users)}</b>\n\n"
            f"▶️ {last_start} | ⏹ {last_stop}",
            reply_markup=admin_kb(), parse_mode="HTML")
        return

    if d == "adm_maintenance":
        config["maintenance"] = not config.get("maintenance", False)
        save_all()
        word = "ВКЛ 🟡" if config["maintenance"] else "ВЫКЛ 🟢"
        await q.message.edit_text(f"🔧 <b>Техобслуживание {word}</b>", reply_markup=admin_kb(), parse_mode="HTML")
        await send_log(f"🔧 Техобслуживание {word}\n👤 {ulabel(update)}")
        return

    if d == "adm_reconnect":
        await q.message.edit_text("⏳ <b>Переподключаюсь...</b>", parse_mode="HTML")
        ok = await asyncio.to_thread(aternos_login)
        result = "✅ Подключён!" if ok else "❌ Не удалось"
        await q.message.edit_text(f"🔌 <b>Aternos: {result}</b>", reply_markup=admin_kb(), parse_mode="HTML")
        await send_log(f"🔌 Переподключение: {result}\n👤 {ulabel(update)}")
        return

    if d == "adm_setlog":
        cid = q.message.chat_id
        config["log_chat_id"] = cid
        save_all()
        await q.message.edit_text(f"✅ <b>Логи здесь!</b>\nID: <code>{cid}</code>", reply_markup=admin_kb(), parse_mode="HTML")
        return

    if d == "adm_exit":
        await q.message.edit_text("👋 <b>Панель закрыта.</b>", parse_mode="HTML")
        return

# ══════════════════════════════════════════════════════════════════
# БРОАДКАСТ
# ══════════════════════════════════════════════════════════════════

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("waiting_broadcast") or not is_admin(update):
        return
    text = update.message.text.strip()
    if text.startswith("/cancel"):
        ctx.user_data["waiting_broadcast"] = False
        await update.message.reply_text("❌ Отменено.")
        return
    ctx.user_data["waiting_broadcast"] = False
    broadcast_text = f"📢 <b>ОБЪЯВЛЕНИЕ — {config['server_name']}</b>\n\n{text}\n\n<i>— Администрация</i>"
    sent = failed = 0
    status_msg = await update.message.reply_text("⏳ <b>Отправляю...</b>", parse_mode="HTML")
    for uid in list(users.keys()):
        try:
            await telegram_app.bot.send_message(int(uid), broadcast_text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await status_msg.edit_text(
        f"📢 <b>Броадкаст отправлен!</b>\n✅ {sent} | ❌ {failed}",
        parse_mode="HTML")
    await send_log(f"📢 <b>БРОАДКАСТ</b>\n👤 {ulabel(update)}\n✅{sent}/❌{failed}\n<i>{text[:200]}</i>")

# ══════════════════════════════════════════════════════════════════
# АВТО-ОТЧЁТ
# ══════════════════════════════════════════════════════════════════

async def auto_report():
    await asyncio.sleep(30)
    while True:
        await asyncio.sleep(600)
        if not aternos_connected: continue
        await asyncio.to_thread(update_server_info)
        if server_status != "online": continue
        try:
            pl_str = "\n".join(f"  • {p}" for p in current_players) if current_players else "  (никого)"
            await send_log(
                "🟢 <b>АВТООТЧЁТ</b>\n"
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
    return jsonify({"status":"ok","server":server_status,"players":len(current_players),"aternos":aternos_connected}), 200

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
    await asyncio.to_thread(aternos_login)

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", cmd_admin)],
        states={WAIT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_code)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)],
    )

    telegram_app.add_handler(admin_conv)
    for cmd, fn in [
        ("start", cmd_start), ("on", cmd_on), ("players", cmd_players),
        ("status", cmd_status), ("info", cmd_info), ("connect", cmd_connect),
        ("rules", cmd_rules), ("help", cmd_help), ("random", cmd_random),
        ("uptime", cmd_uptime), ("laststart", cmd_laststart),
        ("logthischat", cmd_logthischat),
    ]:
        telegram_app.add_handler(CommandHandler(cmd, fn))

    telegram_app.add_handler(CallbackQueryHandler(on_admin_button, pattern="^adm_"))
    telegram_app.add_handler(CallbackQueryHandler(on_button))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("✅ Бот готов!")
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
        log.info("⛔ Зупинено")
    except Exception as e:
        log.error(f"❌ Критична помилка: {e}", exc_info=True)
        sys.exit(1)
