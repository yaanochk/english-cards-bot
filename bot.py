import json
import logging
import os
import random

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("english_bot")

WORDS_FILE = os.path.join(os.path.dirname(__file__), "words.json")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))


def load_words():
    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def flat_cards():
    cards = []
    for title, words in load_words().items():
        for w in words:
            cards.append({"title": title, "en": w["en"], "ru": w["ru"]})
    return cards


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой бот-тренер по английскому 🎓\n\n"
        "Два раза в день я буду присылать карточки на перевод из твоего "
        "словаря English File. Нажимай на кнопки, чтобы проверять себя.\n\n"
        "Команды:\n"
        "/cards — получить карточки сейчас\n"
        "/vocab — все слова текущего словаря\n"
        "/quiz — случайные 5 слов для проверки"
    )


def is_owner(update: Update) -> bool:
    return ALLOWED_USER_ID and update.effective_user.id == ALLOWED_USER_ID


async def send_card(update: Update, context: ContextTypes.DEFAULT_TYPE, card: dict):
    text = f"🇬🇧 Переведи на русский:\n\n<b>{card['en']}</b>\n\n<i>{card['title']}</i>"
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=[[
            {"text": "Показать ответ", "callback_data": f"show|{card['en']}"},
            {"text": "Пропустить", "callback_data": "skip"},
        ]],
    )


async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cards_list = flat_cards()
    if not cards_list:
        await update.message.reply_text("Словарь пока пуст. Добавим слова на занятии.")
        return
    context.user_data["queue"] = list(cards_list)
    context.user_data["cards_total"] = len(cards_list)
    await send_card(update, context, context.user_data["queue"].pop(0))


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cards_list = flat_cards()
    if not cards_list:
        await update.message.reply_text("Словарь пока пуст.")
        return
    sample = random.sample(cards_list, min(5, len(cards_list)))
    context.user_data["queue"] = sample
    await send_card(update, context, context.user_data["queue"].pop(0))


async def vocab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("Это доступно только владельцу.")
        return
    lines = []
    for title, words in load_words().items():
        lines.append(f"📚 {title}")
        for w in words:
            lines.append(f"   {w['en']} — {w['ru']}")
    await update.message.reply_text("\n".join(lines) or "Словарь пуст.")


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("show|"):
        en = data.split("|", 1)[1]
        ru = next((c["ru"] for c in flat_cards() if c["en"] == en), "?")
        await query.edit_message_text(f"✅ {en} — <b>{ru}</b>", parse_mode="HTML")
    elif data == "skip":
        await query.edit_message_text("Пропущено.")
    queue = context.user_data.get("queue", [])
    if queue:
        await send_card(update, context, queue.pop(0))


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Переменная BOT_TOKEN не задана!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cards", cards))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("vocab", vocab))
    app.add_handler(CallbackQueryHandler(button))

    logger.info("Бот запущен (интерактивный режим). Расписание рассылки — на стороне Render Cron.")
    app.run_polling()


if __name__ == "__main__":
    main()
