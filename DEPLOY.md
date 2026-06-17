# 🎮 ATERNOS BOT v5.0 — ФИНАЛЬНАЯ ВЕРСИЯ

## 🚀 DEPLOY НА RENDER

### 1️⃣ GitHub
Залей:
- `bot.py`
- `requirements.txt`

### 2️⃣ Render Dashboard
1. **New** → **Web Service**
2. Обери GitHub репо
3. Названи:
   - Name: `aternos-bot`
   - Environment: `Python 3`
   - Build: `pip install -r requirements.txt`
   - Start: `python bot.py`

### 3️⃣ Environment Variables
```
TELEGRAM_TOKEN=8932716211:AAEC1-wnXkYWP2n4d2RtdaynBKkEq0H0JNs
ATERNOS_USER=GodB1T
ATERNOS_PASS=AntonGod
SERVER_ID=ZMbbJv4TMQFIbi78
LOG_CHAT_ID=-1002221201789
```

### 4️⃣ Deploy! 🎉

---

## ✨ НОВОЕ В v5.0

✅ **Русская локализация**
✅ **Полное логирование** всех действий
✅ `/logthischat` — установить чат для логов
✅ **Автоотчеты** каждые 10 минут
✅ **Чистый код** без Playwright гавна
✅ **Красивый интерфейс** с Inline кнопками
✅ **Статистика** запусков/остановок
✅ **Просмотр игроков** в реальном времени

---

## 📋 КОМАНДЫ

```
/start        - Главное меню
/on           - Запустить сервер
/off          - Остановить сервер
/players      - Список игроков онлайн
/status       - Статус сервера
/info         - Информация + статистика
/logthischat  - Логи в этот чат
```

---

## 📊 ЛОГИРОВАНИЕ

Все действия логируются в чат:
- 🟢 Запуск сервера (кто, когда)
- 🔴 Остановка сервера (кто, когда)
- 👥 Список игроков (каждые 10 мин)
- ❌ Ошибки и предупреждения
- ⚙️ Установка чата для логов

**Команда `/logthischat` в нужном чате** → логи будут там! ✨

---

## 🛠️ КОНФИГ

Все сохраняется в файлы:
- `stats.json` — статистика
- `config.json` — чат для логов

На Render можно просмотреть через консоль Render 📝

---

## ✅ ГОТОВО!

Всё работает, без гавна, красиво, надежно! 💪

**Sleep well, brother! Завтра будет шедевр!** 🚀

