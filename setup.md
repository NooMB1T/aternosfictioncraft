# 🚂 ATERNOS BOT — RAILWAY.APP SETUP

## ✅ ЧОМУ RAILWAY:
- Не потрібна карта для старту ($5 FREE кредиту)
- 512MB RAM достатньо
- 8 годин/день Free тарифу (достатньо для бота)
- Більш лояльні до ботів ніж Render

## 🚀 КРОК 1: РЕЄСТРАЦІЯ

1. Йди на https://railway.app
2. Sign up (GitHub або Email)
3. Підтверди емейл
4. ✅ Готово! Дають $5 FREE кредиту на старт

## 📝 КРОК 2: ЗАЛЕЙ ФАЙЛИ НА GITHUB

В корінь репо zalej:
- `bot_railway.py` (ОБОВ'ЯЗКОВО перейменуй на `bot.py`!)
- `requirements_railway.txt` (перейменуй на `requirements.txt`!)

Або замість файлів — просто замініть уміст старих на нові

## 🏗️ КРОК 3: DEPLOY НА RAILWAY

1. На Railway Dashboard натисни **New Project**
2. **Deploy from GitHub**
3. Обери свій репо `aternosfictioncraft`
4. Railway автоматично детектує Python

## ⚙️ КРОК 4: ENVIRONMENT VARIABLES

В Railway проекті:
1. Settings -> Variables
2. Добавь:

```
TELEGRAM_TOKEN=8932716211:AAEC1-wnXkYWP2n4d2RtdaynBKkEq0H0JNs
ATERNOS_USER=GodB1T
ATERNOS_PASS=AntonGod
SERVER_ID=ZMbbJv4TMQFIbi78
LOG_CHAT_ID=-1002221201789
PORT=8000
```

## 🚀 КРОК 5: DEPLOY

Railway автоматично детектує `bot.py` та запустить його.
Якщо треба вручну — натисни Deploy button.

## 📊 ЩО БУДЕ ПРАЦЮВАТИ:

- ✅ /start, /on, /off, /players, /status, /info
- ✅ Telegram polling (отримує повідомлення)
- ✅ Логування всіх дій в чат
- ✅ Статистика (starts, stops, peak players)
- ⚠️ Aternos логін — спробуємо requests (можливо не спрацює)

Якщо Aternos логін не пройде (403 помилка) — значитьIP Render знову заблокував 
або алгоритм змінили. В такому разі:
- Либо спробуємо Playwright потім
- Либо логиниш вручну один раз, а потім бот юзає куки
- Либо потрібен інший спосіб (proxy, VPN тощо)

## 🎯ДО РЕЧІ:

Railway дає $5/місяц FREE, потім треба вносити карту для більшого.
Якщо не вносити карту — бот працює максимум 8 годин/день (休眠 після цього).
Це достатньо для бота що запускає сервер пару разів.

