import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
from flask import Flask
from threading import Thread
import aternos
import traceback
import random
import time

# ==================== КОНФИГ ====================
TELEGRAM_TOKEN = "8932716211:AAEC1-wnXkYWP2n4d2RtdaynBKkEq0H0JNs"
ATERNOS_USERNAME = "GodB1T"
ATERNOS_PASSWORD = "AntonGod"
SERVER_ID = "ZMbbJv4TMQFIbi78"
LOG_CHAT_ID = -1002221201789
ADMIN_USER_ID = None  # Можешь указать свой ID для админ команд

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные переменные
aternos_session = None
telegram_app = None
server_status_cache = {"status": None, "updated": 0}

# ==================== ATERNOS ФУНКЦИИ ====================

async def init_aternos():
    """Инициализация сессии Aternos"""
    global aternos_session
    try:
        aternos_session = aternos.Client()
        aternos_session.login(ATERNOS_USERNAME, ATERNOS_PASSWORD)
        logger.info("✅ Aternos подключен!")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения Aternos: {e}")
        traceback.print_exc()
        return False

async def get_server():
    """Получить сервер"""
    try:
        if not aternos_session:
            await init_aternos()
        server = aternos_session.get_server(SERVER_ID)
        return server
    except Exception as e:
        logger.error(f"❌ Ошибка получения сервера: {e}")
        return None

async def send_log(message: str, parse_mode="HTML"):
    """Отправить лог в чат"""
    try:
        if telegram_app:
            await telegram_app.bot.send_message(
                chat_id=LOG_CHAT_ID, 
                text=message,
                parse_mode=parse_mode
            )
            logger.info(f"📝 Лог отправлен")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки лога: {e}")

def get_status_emoji(status):
    """Получить эмодзи статуса"""
    if status == "online":
        return "🟢"
    elif status == "offline":
        return "🔴"
    elif status in ["loading", "starting"]:
        return "🟡"
    else:
        return "⚫"

# ==================== TELEGRAM КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - главное меню"""
    await update.message.chat.send_action(ChatAction.TYPING)
    
    keyboard = [
        [
            InlineKeyboardButton("🟢 ВКЛЮЧИТЬ", callback_data="cmd_on"),
            InlineKeyboardButton("🔴 ВЫКЛЮЧИТЬ", callback_data="cmd_off"),
        ],
        [
            InlineKeyboardButton("👥 ИГРОКИ", callback_data="cmd_players"),
        ],
        [
            InlineKeyboardButton("📊 СТАТУС", callback_data="cmd_status"),
            InlineKeyboardButton("🎮 ПРИКОЛЫ", callback_data="cmd_menu"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "<b>🎮 ATERNOS BOT - fictionmine 🎮</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Привет! Я твой помощник для управления сервером.</b>\n\n"
        "Доступные команды:\n"
        "• <code>/on</code> - Включить сервер\n"
        "• <code>/off</code> - Выключить сервер\n"
        "• <code>/players</code> - Список игроков\n"
        "• <code>/status</code> - Статус сервера\n"
        "• <code>/menu</code> - Приколы\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<i>Или просто нажми кнопку ниже!</i>"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def cmd_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /on - включить сервер"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            msg = update.callback_query.message
            await msg.edit_text(
                "<b>⏳ Запускаю сервер...</b>\n\n"
                "<i>Это может занять некоторое время...</i>",
                parse_mode="HTML"
            )
        else:
            msg = await update.message.reply_text(
                "<b>⏳ Запускаю сервер...</b>\n\n"
                "<i>Это может занять некоторое время...</i>",
                parse_mode="HTML"
            )
        
        server = await get_server()
        if not server:
            await msg.edit_text(
                "❌ <b>Ошибка подключения</b>\n\n"
                "Не удалось подключиться к серверу Aternos.\n"
                "Проверь интернет и попробуй снова.",
                parse_mode="HTML"
            )
            return
        
        status = server.status
        
        if status == "online":
            await msg.edit_text(
                "✅ <b>Сервер уже включен!</b>\n\n"
                "<i>Игроки уже могут подключаться...</i>",
                parse_mode="HTML"
            )
            return
        
        # Запускаем сервер
        await asyncio.to_thread(server.start)
        
        await msg.edit_text(
            "🟢 <b>СЕРВЕР ЗАПУЩЕН!</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n"
            f"🎮 <b>Сервер:</b> fictionmine\n"
            "📝 <b>Статус:</b> Загружается...\n\n"
            "<i>Подожди 5-10 минут, сервер загружается</i>",
            parse_mode="HTML"
        )
        
        log_msg = (
            f"<b>🟢 СЕРВЕР ЗАПУЩЕН!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"🎮 Сервер: fictionmine\n"
            f"📝 Статус: Запуск инициирован\n"
            f"👤 Автор: NooMBOT"
        )
        await send_log(log_msg)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /on: {e}\n{traceback.format_exc()}")
        error_text = f"❌ <b>Ошибка при запуске:</b>\n\n<code>{str(e)[:200]}</code>"
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.edit_text(error_text, parse_mode="HTML")
        else:
            await update.message.reply_text(error_text, parse_mode="HTML")

async def cmd_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /off - выключить сервер"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            msg = update.callback_query.message
            await msg.edit_text(
                "<b>⏳ Выключаю сервер...</b>",
                parse_mode="HTML"
            )
        else:
            msg = await update.message.reply_text(
                "<b>⏳ Выключаю сервер...</b>",
                parse_mode="HTML"
            )
        
        server = await get_server()
        if not server:
            await msg.edit_text(
                "❌ <b>Ошибка подключения</b>",
                parse_mode="HTML"
            )
            return
        
        if server.status == "offline":
            await msg.edit_text(
                "🔴 <b>Сервер уже выключен!</b>",
                parse_mode="HTML"
            )
            return
        
        await asyncio.to_thread(server.stop)
        
        await msg.edit_text(
            "🔴 <b>СЕРВЕР ВЫКЛЮЧЕН!</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n"
            f"🎮 <b>Сервер:</b> fictionmine\n"
            "📝 <b>Статус:</b> Выключен",
            parse_mode="HTML"
        )
        
        log_msg = (
            f"<b>🔴 СЕРВЕР ВЫКЛЮЧЕН!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"🎮 Сервер: fictionmine"
        )
        await send_log(log_msg)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /off: {e}")
        error_text = f"❌ <b>Ошибка при выключении:</b>\n\n<code>{str(e)[:200]}</code>"
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.edit_text(error_text, parse_mode="HTML")
        else:
            await update.message.reply_text(error_text, parse_mode="HTML")

async def cmd_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /players - список игроков"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            msg = update.callback_query.message
            await msg.edit_text(
                "<b>⏳ Проверяю игроков...</b>",
                parse_mode="HTML"
            )
        else:
            msg = await update.message.reply_text(
                "<b>⏳ Проверяю игроков...</b>",
                parse_mode="HTML"
            )
        
        server = await get_server()
        if not server:
            await msg.edit_text(
                "❌ <b>Ошибка подключения</b>",
                parse_mode="HTML"
            )
            return
        
        status = server.status
        
        if status != "online":
            status_emoji = get_status_emoji(status)
            await msg.edit_text(
                f"{status_emoji} <b>Сервер оффлайн</b>\n\n"
                f"Статус: {status.upper()}\n"
                f"<i>Включи сервер командой /on</i>",
                parse_mode="HTML"
            )
            return
        
        try:
            players_list = server.players
            
            if not players_list or len(players_list) == 0:
                players_text = (
                    "👥 <b>ОНЛАЙН: 0 игроков</b>\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Сервер включен, но никого нет 😿"
                )
            else:
                players_str = "\n".join([f"  • {p}" for p in players_list])
                players_text = (
                    f"👥 <b>ОНЛАЙН: {len(players_list)} игрок(ов)</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"{players_str}\n"
                    f"━━━━━━━━━━━━━━━━━━━━"
                )
            
            await msg.edit_text(players_text, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Ошибка получения игроков: {e}")
            await msg.edit_text(
                "⚠️ <b>Не удалось получить список игроков</b>\n\n"
                "<i>Сервер может еще загружаться...</i>",
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /players: {e}\n{traceback.format_exc()}")
        error_text = f"❌ <b>Ошибка:</b>\n\n<code>{str(e)[:200]}</code>"
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.edit_text(error_text, parse_mode="HTML")
        else:
            await update.message.reply_text(error_text, parse_mode="HTML")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - статус сервера"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            msg = update.callback_query.message
            await msg.edit_text(
                "<b>⏳ Проверяю статус...</b>",
                parse_mode="HTML"
            )
        else:
            msg = await update.message.reply_text(
                "<b>⏳ Проверяю статус...</b>",
                parse_mode="HTML"
            )
        
        server = await get_server()
        if not server:
            await msg.edit_text(
                "❌ <b>Ошибка подключения</b>",
                parse_mode="HTML"
            )
            return
        
        status_emoji = get_status_emoji(server.status)
        status_text_long = server.status.upper()
        
        status_msg = (
            f"{status_emoji} <b>СТАТУС СЕРВЕРА</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎮 <b>Имя:</b> fictionmine\n"
            f"📍 <b>Статус:</b> {status_text_long}\n"
            f"🔗 <b>ID:</b> {SERVER_ID[:8]}...\n"
            f"⏰ <b>Проверено:</b> {datetime.now().strftime('%H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        
        await msg.edit_text(status_msg, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /status: {e}")
        error_text = f"❌ <b>Ошибка:</b>\n\n<code>{str(e)[:200]}</code>"
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.edit_text(error_text, parse_mode="HTML")
        else:
            await update.message.reply_text(error_text, parse_mode="HTML")

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /menu - меню приколов"""
    jokes = [
        "🎮 Попробуй крафтить Нозерайта в Creative режиме\n(Спойлер: не получится, это Bedrock!)",
        "😂 Зачем нужен паспорт в Майнкрафте?\nЧтобы пересечь границу Nether'а без виз!",
        "💎 Почему алмазы в Bedrock дороже чем в Java?\nПотому что тут они на консолях!",
        "🔥 Что сказал крипер ползунку?\n'Ты мне не нужна, я сам себя взорву!'",
        "🎯 Как назвать ендермена?\nОтвет: 'Черный ящик' - потому что ты не знаешь, что он там делает",
        "⚔️ Почему зомби не играют в шахматы?\nПотому что они всегда падают в ямы!",
        "🌙 Что делает Стив в Bedrock?\nФлексит своими очками!",
        "🚀 Как быстро добраться до конца?\nОтвет: очень медленно, если ты как я и не знаешь маршрут!",
        "💀 Почему скелеты - лучшие лучники?\nПотому что у них нет сердца для сомнений!",
        "🎪 Знаешь, почему сервер Bedrock называется 'fictionmine'?\nПотому что это вымышленный мир... ИЛИ ЭТО?\n🤔",
        "🔴 Что общего между Крипером и твоим кодом?\nОба взрываются на неожиданных входных данных!",
        "💻 Почему программист предпочитает Bedrock Java?\nПотому что в Bedrock меньше версионных конфликтов! (Шутка)",
        "🌍 Как создать идеальный Minecraft сервер?\nШаг 1: Сделай его\nШаг 2: Жди когда он упадет\nШаг 3: Винь Mojang",
        "🎮 Что сказал Стив Алекс?\n'Ты видела мою кровать?'\nАлекс: 'Да, ты ее 100 раз переносил!'",
        "⛏️ Почему майнер не может быть грустным?\nПотому что он всегда добывает радость!",
    ]
    
    joke = random.choice(jokes)
    joke_msg = (
        "<b>🤣 ВОТ ТЕБЕ ПРИКОЛЕЦ!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{joke}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(joke_msg, parse_mode="HTML")
    else:
        await update.message.reply_text(joke_msg, parse_mode="HTML")

# ==================== CALLBACK BUTTONS ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок"""
    query = update.callback_query
    await query.answer()
    
    # Добавляем атрибут callback_query в update для наших функций
    if query.data == "cmd_on":
        update.callback_query = query
        await cmd_on(update, context)
    elif query.data == "cmd_off":
        update.callback_query = query
        await cmd_off(update, context)
    elif query.data == "cmd_players":
        update.callback_query = query
        await cmd_players(update, context)
    elif query.data == "cmd_menu":
        update.callback_query = query
        await cmd_menu(update, context)
    elif query.data == "cmd_status":
        update.callback_query = query
        await cmd_status(update, context)

# ==================== FLASK ДЛЯ REPLIT ====================

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return '✅ <b>ATERNOS BOT WORK!</b>', 200

@flask_app.route('/ping')
def ping():
    return '🏓 pong', 200

@flask_app.route('/health')
def health():
    return {
        'status': 'ok',
        'time': datetime.now().isoformat(),
        'server': 'fictionmine',
        'bot': 'aternos_bot'
    }, 200

def run_flask():
    """Запуск Flask в отдельном потоке"""
    flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ==================== ОСНОВНОЙ БОТ ====================

async def run_bot():
    """Запуск Telegram бота"""
    global telegram_app, aternos_session
    
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК ATERNOS BOT")
    logger.info("=" * 60)
    
    # Инициализируем Aternos
    await init_aternos()
    
    # Создаем приложение Telegram
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики команд
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("on", cmd_on))
    telegram_app.add_handler(CommandHandler("off", cmd_off))
    telegram_app.add_handler(CommandHandler("players", cmd_players))
    telegram_app.add_handler(CommandHandler("menu", cmd_menu))
    telegram_app.add_handler(CommandHandler("status", cmd_status))
    
    # Обработчик кнопок
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("✅ Бот инициализирован!")
    logger.info("=" * 60)
    
    # Запускаем бот
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

# ==================== ТОЧКА ВХОДА ====================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🎮 FICTIONMINE ATERNOS BOT")
    logger.info("=" * 60)
    logger.info(f"📝 Username: {ATERNOS_USERNAME}")
    logger.info(f"🎯 Server ID: {SERVER_ID}")
    logger.info(f"💬 Log Chat ID: {LOG_CHAT_ID}")
    logger.info("=" * 60)
    
    # Запускаем Flask в отдельном потоке (для Replit)
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask сервер запущен на port 5000")
    logger.info("=" * 60)
    
    # Запускаем Telegram бота
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("⛔ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        traceback.print_exc()
