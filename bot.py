import json
import logging
import os
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

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

BASE_DIR = os.path.dirname(__file__)
WORDS_FILE = os.path.join(BASE_DIR, "words.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "progress.json")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))
MASTERY_THRESHOLD = 5

MENU_BUTTONS = ReplyKeyboardMarkup(
    [["🎴 Карточки", "🎲 Квиз"], ["📚 Словарь"]],
    resize_keyboard=True,
)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def start_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info("Health check server listening on port %d", port)
    server.serve_forever()


def load_words():
    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def flat_cards():
    cards = []
    for title, words in load_words().items():
        for w in words:
            cards.append({"title": title, "en": w["en"], "ru": w["ru"]})
    return cards


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(progress):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def get_word_progress(progress, en):
    w = progress.get(en, {})
    return w.get("correct", 0)


def set_word_progress(progress, en, correct):
    progress[en] = {"correct": correct}
    save_progress(progress)


def reset_word_progress(progress, en):
    progress.pop(en, None)
    save_progress(progress)


def is_mastered(progress, en):
    return get_word_progress(progress, en) >= MASTERY_THRESHOLD


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎓 <b>Твой личный тренер по английскому!</b>\n\n"
        "Я присылаю карточки со словами из English File Intermediate.\n"
        "Два раза в день — автоматическая тренировка, в любое время — по кнопкам.\n\n"
        "<b>Как работать:</b>\n"
        "🎴 Карточки — смотришь и открываешь перевод\n"
        "🎲 Квиз — печатаешь перевод с клавиатуры\n"
        "📚 Словарь — прогресс по всем словам",
        parse_mode="HTML",
        reply_markup=MENU_BUTTONS,
    )


def is_owner(update: Update) -> bool:
    return ALLOWED_USER_ID and update.effective_user.id == ALLOWED_USER_ID


async def send_card(chat_id, context: ContextTypes.DEFAULT_TYPE, card: dict, done: int, total: int):
    progress_text = f"<i>{done + 1}/{total}</i>"
    text = f"🇬🇧 <b>Переведи на русский:</b>\n\n<b>{card['en']}</b>\n\n{progress_text}"

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
    context.user_data.pop("quiz_word", None)
    context.user_data.pop("quiz_mode", None)
    await send_card(update.effective_chat.id, context, context.user_data["queue"].pop(0), 0, context.user_data["cards_total"])


async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cards(update, context)


async def vocab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("Это доступно только владельцу.", reply_markup=MENU_BUTTONS)
        return

    progress = load_progress()
    lines = []
    for title, words in load_words().items():
        lines.append(f"📚 {title}")
        for w in words:
            en = w["en"]
            cnt = get_word_progress(progress, en)
            if cnt >= MASTERY_THRESHOLD:
                status = "✅"
            elif cnt > 0:
                status = f"🔄"
            else:
                status = "⚪"
            lines.append(f"   {status} {en} — <b>{w['ru']}</b> ({cnt}/{MASTERY_THRESHOLD})")

    await update.message.reply_text(
        "\n".join(lines) or "📭 Словарь пуст.",
        parse_mode="HTML",
        reply_markup=MENU_BUTTONS,
    )


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    progress = load_progress()
    all_cards = flat_cards()

    non_mastered = [c for c in all_cards if not is_mastered(progress, c["en"])]

    if not non_mastered:
        await update.message.reply_text(
            "🎉 Все слова выучены! Хочешь повторить всё заново?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Повторить", callback_data="quiz_reset")]
            ]),
        )
        return

    sample = random.sample(non_mastered, min(5, len(non_mastered)))

    context.user_data["quiz_words"] = list(sample)
    context.user_data["quiz_index"] = 0
    context.user_data["quiz_correct"] = 0
    context.user_data["quiz_wrong"] = 0
    context.user_data["quiz_mastered_new"] = 0
    context.user_data["quiz_mode"] = True
    context.user_data.pop("queue", None)
    context.user_data.pop("cards_total", None)

    await send_quiz_word(update.effective_chat.id, context)


async def send_quiz_word(chat_id, context: ContextTypes.DEFAULT_TYPE):
    words = context.user_data.get("quiz_words", [])
    idx = context.user_data.get("quiz_index", 0)

    if idx >= len(words):
        await finish_quiz(chat_id, context)
        return

    card = words[idx]
    context.user_data["quiz_word"] = card

    await context.bot.send_message(
        chat_id,
        f"🎲 <b>Квиз!</b> Напиши перевод слова:\n\n<b>{card['en']}</b>",
        parse_mode="HTML",
    )


async def finish_quiz(chat_id, context: ContextTypes.DEFAULT_TYPE):
    correct = context.user_data.get("quiz_correct", 0)
    wrong = context.user_data.get("quiz_wrong", 0)
    mastered_new = context.user_data.get("quiz_mastered_new", 0)
    total = len(context.user_data.get("quiz_words", []))

    progress = load_progress()
    words_left = len([c for c in flat_cards() if not is_mastered(progress, c["en"])])

    msg = (
        "🏁 <b>Квиз завершён!</b>\n\n"
        f"📊 Всего слов: {total}\n"
        f"✅ Правильно: {correct}\n"
        f"❌ Неправильно: {wrong}\n"
        f"🎉 Выучено новых: {mastered_new}\n"
        f"📚 Осталось выучить: {words_left}"
    )

    await context.bot.send_message(chat_id, msg, parse_mode="HTML")

    context.user_data.pop("quiz_mode", None)
    context.user_data.pop("quiz_word", None)
    context.user_data.pop("quiz_words", None)
    context.user_data.pop("quiz_index", None)
    context.user_data.pop("quiz_correct", None)
    context.user_data.pop("quiz_wrong", None)
    context.user_data.pop("quiz_mastered_new", None)

    progress = load_progress()
    non_mastered = [c for c in flat_cards() if not is_mastered(progress, c["en"])]
    if non_mastered:
        await context.bot.send_message(
            chat_id,
            "Хочешь ещё? Нажимай кнопки внизу 👇",
            reply_markup=MENU_BUTTONS,
        )
    else:
        await context.bot.send_message(
            chat_id,
            "🎉 Поздравляю! Ты выучил(а) все слова!",
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


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("quiz_mode"):
        await handle_quiz_answer(update, context)
    else:
        await handle_menu(update, context)


async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("quiz_mode"):
        return

    user_text = update.message.text.strip()
    card = context.user_data.get("quiz_word")
    if not card:
        return

    chat_id = update.effective_chat.id
    progress = load_progress()
    en = card["en"]
    ru = card["ru"]

    if user_text.lower() == "?" or user_text.lower() == "пропуск":
        await context.bot.send_message(
            chat_id,
            f"⏭ Пропущено. Правильно: <b>{ru}</b>",
            parse_mode="HTML",
        )
        context.user_data["quiz_index"] += 1
        await ask_continue(chat_id, context)
        return

    if user_text.lower().strip() == ru.lower().strip():
        current = get_word_progress(progress, en)
        new_count = current + 1
        set_word_progress(progress, en, new_count)
        context.user_data["quiz_correct"] += 1

        if new_count >= MASTERY_THRESHOLD:
            context.user_data["quiz_mastered_new"] += 1
            await context.bot.send_message(
                chat_id,
                "✅ Верно! 🎉 <b>Слово выучено!</b>",
                parse_mode="HTML",
            )
        else:
            await context.bot.send_message(
                chat_id,
                f"✅ Верно! ({new_count}/{MASTERY_THRESHOLD})",
                parse_mode="HTML",
            )

        context.user_data["quiz_index"] += 1
        await ask_continue(chat_id, context)
    else:
        set_word_progress(progress, en, 0)
        context.user_data["quiz_wrong"] += 1

        await context.bot.send_message(
            chat_id,
            f"❌ Неверно. Правильно: <b>{ru}</b>",
            parse_mode="HTML",
        )

        context.user_data["quiz_index"] += 1
        await ask_continue(chat_id, context)


async def ask_continue(chat_id, context: ContextTypes.DEFAULT_TYPE):
    words = context.user_data.get("quiz_words", [])
    idx = context.user_data.get("quiz_index", 0)

    if idx >= len(words):
        await finish_quiz(chat_id, context)
        return

    await context.bot.send_message(
        chat_id,
        "Продолжить?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Да", callback_data="quiz_continue"),
                InlineKeyboardButton("🔴 Нет", callback_data="quiz_stop"),
            ]
        ]),
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data.startswith("show|"):
        en = data.split("|", 1)[1]
        ru = next((c["ru"] for c in flat_cards() if c["en"] == en), "?")
        queue = context.user_data.get("queue", [])
        done = context.user_data.get("cards_total", 0) - len(queue)

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
        queue = context.user_data.get("queue", [])
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
        queue = context.user_data.get("queue", [])
        if queue:
            card = queue.pop(0)
            done = context.user_data.get("cards_total", 0) - len(queue)
            await send_card(chat_id, context, card, done, context.user_data["cards_total"])
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
    elif data == "quiz_continue":
        await send_quiz_word(chat_id, context)
    elif data == "quiz_stop":
        await finish_quiz(chat_id, context)
    elif data == "quiz_reset":
        progress = load_progress()
        for card in flat_cards():
            progress.pop(card["en"], None)
        save_progress(progress)
        await query.edit_message_text(
            "🔄 Прогресс сброшен! Все слова можно учить заново.\n\nНажми «🎲 Квиз» в меню, чтобы начать.",
        )


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Переменная BOT_TOKEN не задана!")

    t = threading.Thread(target=start_http_server, daemon=True)
    t.start()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cards", cards))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("vocab", vocab))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(button))

    logger.info("Бот запущен (интерактивный режим).")
    app.run_polling()


if __name__ == "__main__":
    main()