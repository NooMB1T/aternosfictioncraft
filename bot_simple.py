#!/usr/bin/env python3
"""
ATERNOS BOT - ПРОСТАЯ ВЕРСИЯ
"""
import os
import sys
import logging
from datetime import datetime

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)
log = logging.getLogger(__name__)

# Конфіг
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ATERNOS_USER = os.getenv("ATERNOS_USER")
ATERNOS_PASS = os.getenv("ATERNOS_PASS")
PORT = int(os.getenv("PORT", 5000))

if not TELEGRAM_TOKEN:
    log.error("❌ TELEGRAM_TOKEN не встановлен!")
    sys.exit(1)

log.info("=" * 60)
log.info("🎮 ATERNOS BOT - ПРОСТАЯ ВЕРСИЯ")
log.info("=" * 60)
log.info(f"🔑 Username: {ATERNOS_USER}")
log.info(f"💬 Telegram: OK")
log.info(f"🌐 Port: {PORT}")
log.info("=" * 60)

# Flask для keep-alive
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "ok", "bot": "aternos-bot", "time": datetime.now().isoformat()}), 200

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/health")
def health():
    return jsonify({"status": "ok", "uptime": "running"}), 200

# Telegram бот
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
    from telegram.constants import ChatAction
    import asyncio
    
    TELEGRAM_OK = True
    log.info("✅ Telegram библиотека загружена")
except ImportError as e:
    TELEGRAM_OK = False
    log.warning(f"⚠️ Telegram ошибка: {e}")

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    text = (
        "<b>🎮 ATERNOS BOT</b>\n\n"
        "✅ Бот работает!\n\n"
        "Доступные команды:\n"
        "• /status - Статус\n"
        "• /help - Помощь"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    await update.message.reply_text("✅ <b>БОТ РАБОТАЕТ!</b>", parse_mode="HTML")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    text = (
        "<b>СПРАВКА</b>\n\n"
        "Бот подключается к Aternos и управляет сервером.\n\n"
        "Команды:\n"
        "• /start - Главное меню\n"
        "• /status - Статус бота\n"
        "• /help - Эта справка"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def run_telegram_bot():
    """Запустить Telegram бота"""
    if not TELEGRAM_OK:
        log.warning("⚠️ Telegram бот отключен")
        return
    
    try:
        log.info("🤖 Инициализирую Telegram бота...")
        app_tg = Application.builder().token(TELEGRAM_TOKEN).build()
        
        app_tg.add_handler(CommandHandler("start", cmd_start))
        app_tg.add_handler(CommandHandler("status", cmd_status))
        app_tg.add_handler(CommandHandler("help", cmd_help))
        
        log.info("✅ Telegram бот готов!")
        log.info("📡 Начинаю получать сообщения...")
        
        await app_tg.initialize()
        await app_tg.start()
        await app_tg.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        log.error(f"❌ Telegram ошибка: {e}", exc_info=True)

if __name__ == "__main__":
    from threading import Thread
    
    # Flask в потоке
    def run_flask():
        log.info(f"🌐 Flask запускается на http://0.0.0.0:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    log.info("✅ Flask запущен")
    log.info("=" * 60)
    
    try:
        # Telegram бот
        if TELEGRAM_OK:
            asyncio.run(run_telegram_bot())
        else:
            # Если Telegram не работает - просто Flask
            log.info("⏳ Приложение работает (только Flask)")
            while True:
                import time
                time.sleep(10)
    except KeyboardInterrupt:
        log.info("⛔ Бот остановлен")
    except Exception as e:
        log.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)
        sys.exit(1)
