import json
import logging
import os
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("english_bot")

WORDS_FILE = os.path.join(os.path.dirname(__file__), "words.json")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

MENU_BUTTONS = ReplyKeyboardMarkup(
    [["🎴 Карточки", "🎲 Квиз"], ["📚 Словарь"]],
    resize_keyboard=True,
)


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
        "🎓 <b>Твой личный тренер по английскому!</b>\n\n"
        "Я присылаю карточки со словами из English File Intermediate.\n"
        "Два раза в день — автоматическая тренировка, в любое время — по кнопкам.\n\n"
        "<b>Как работать с карточкой:</b>\n"
        "1. Смотри слово на английском\n"
        "2. Вспоминаешь перевод\n"
        "3. Нажимаешь «Показать ответ»\n"
        "4. Жмёшь «Дальше» — и следующее слово",
        parse_mode="HTML",
        reply_markup=MENU_BUTTONS,
    )


def is_owner(update: Update) -> bool:
    return ALLOWED_USER_ID and update.effective_user.id == ALLOWED_USER_ID


async def send_card(chat_id, context: ContextTypes.DEFAULT_TYPE, card: dict, done: int, total: int):
    progress = f"<i>{done + 1}/{total}</i>"
    text = f"🇬🇧 <b>Переведи на русский:</b>\n\n<b>{card['en']}</b>\n\n{progress}"

    await context.bot.send_message(
        chat_id,
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👀 Показать ответ", callback_data=f"show|{card['en']}"),
                InlineKeyboardButton("➡ Пропустить", callback_data="skip"),
            ]
        ]),
    )


async def start_cards(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int = None):
    cards_list = flat_cards()
    if not cards_list:
        await update.message.reply_text("📭 Словарь пока пуст. Добавим слова на занятии.", reply_markup=MENU_BUTTONS)
        return

    if count:
        sample = random.sample(cards_list, min(count, len(cards_list)))
        context.user_data["queue"] = list(sample)
    else:
        context.user_data["queue"] = list(cards_list)

    context.user_data["cards_total"] = len(context.user_data["queue"])
    await send_card(update.effective_chat.id, context, context.user_data["queue"].pop(0), 0, context.user_data["cards_total"])


async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cards(update, context)


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cards(update, context, count=5)


async def vocab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("Это доступно только владельцу.", reply_markup=MENU_BUTTONS)
        return

    lines = []
    for title, words in load_words().items():
        lines.append(f"📚 {title}")
        for w in words:
            lines.append(f"   {w['en']} — <b>{w['ru']}</b>")

    await update.message.reply_text(
        "\n".join(lines) or "📭 Словарь пуст.",
        parse_mode="HTML",
        reply_markup=MENU_BUTTONS,
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🎴 Карточки":
        await cards(update, context)
    elif text == "🎲 Квиз":
        await quiz(update, context)
    elif text == "📚 Словарь":
        await vocab(update, context)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    queue = context.user_data.get("queue", [])
    done = context.user_data.get("cards_total", 0) - len(queue)

    if data.startswith("show|"):
        en = data.split("|", 1)[1]
        ru = next((c["ru"] for c in flat_cards() if c["en"] == en), "?")
        markup = None
        if queue:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("➡ Дальше", callback_data="next")]
            ])
        elif not queue:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏁 Завершить", callback_data="finish")]
            ])
        await query.edit_message_text(
            f"✅ <b>{en}</b> — <b>{ru}</b>",
            parse_mode="HTML",
            reply_markup=markup,
        )
    elif data == "skip":
        if queue:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("➡ Дальше", callback_data="next")]
            ])
        else:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏁 Завершить", callback_data="finish")]
            ])
        await query.edit_message_text("⏭ Пропущено.", reply_markup=markup)
    elif data == "next":
        if queue:
            card = queue.pop(0)
            done += 1
            await send_card(query.message.chat_id, context, card, done, context.user_data["cards_total"])
            await query.message.delete()
    elif data == "finish":
        total = context.user_data.get("cards_total", 0)
        await query.edit_message_text(
            f"🎉 Готово! Повторили <b>{total}</b> слов(а).\n"
            "Хочешь ещё? Нажимай кнопки внизу 👇",
            parse_mode="HTML",
        )
        context.user_data.pop("queue", None)
        context.user_data.pop("cards_total", None)


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Переменная BOT_TOKEN не задана!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cards", cards))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("vocab", vocab))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    app.add_handler(CallbackQueryHandler(button))

    logger.info("Бот запущен (интерактивный режим).")
    app.run_polling()


if __name__ == "__main__":
    main()