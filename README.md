# English Cards Bot

Бот-тренер по английскому: два раза в день присылает карточки на перевод
из словаря English File Intermediate.

## Файлы

- `bot.py` — код бота (python-telegram-bot, long polling + JobQueue)
- `words.json` — словарь (источник слов для карточек)
- `requirements.txt` — зависимости
- `render.yaml` — конфигурация деплоя на Render

## Команды в боте

- `/start` — приветствие
- `/cards` — карточки сейчас
- `/quiz` — случайные 5 слов
- `/vocab` — все слова словаря (только владелец)

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `BOT_TOKEN` | токен бота от @BotFather |
| `ALLOWED_USER_ID` | твой Telegram chat ID (владелец) |
| `QUIZ_TIMES` | время рассылки, через запятую, например `09:00,18:00` |

## Как добавить слова

Слова живут в `words.json`. Во время занятия я обновляю этот файл,
ты коммитишь и пушишь в GitHub — Render сам перезапустит бота с новыми словами.

## Как задеплоить на Render

1. Создай GitHub-репозиторий и залей папку `bot`.
2. На [render.com](https://render.com) → New → Web Service → подключи репозиторий.
3. Render сам увидит `render.yaml` и применит настройки.
4. Добавь секрет `BOT_TOKEN` (вкладка Environment).
5. Deploy. Готово.
