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
    [
        ["🎴 Карточки", "🎲 Квиз"],
        ["🔁 Рус → Англ", "🎯 Варианты"],
        ["⚡ Скорость", "📚 Словарь"],
        ["🔀 Весь словарь", "♻️ Заново"],
    ],
    resize_keyboard=True,
)

MODE_TITLES = {
    "en_ru": "🎲 Квиз (Англ → Рус)",
    "ru_en": "🔁 Тест (Рус → Англ)",
    "choice": "🎯 Варианты (Англ → Рус)",
    "speed": "⚡ Скорость (Англ → Рус)",
}


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


def is_mastered(progress, en):
    return get_word_progress(progress, en) >= MASTERY_THRESHOLD


def reset_quiz_state(context: ContextTypes.DEFAULT_TYPE):
    for key in (
        "quiz_mode",
        "quiz_word",
        "quiz_words",
        "quiz_index",
        "quiz_correct",
        "quiz_wrong",
        "quiz_mastered_new",
        "quiz_options",
        "quiz_correct_option",
        "quiz_auto",
        "queue",
        "cards_total",
    ):
        context.user_data.pop(key, None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_quiz_state(context)
    await update.message.reply_text(
        "🎓 <b>Твой личный тренер по английскому!</b>\n\n"
        "Слова из English File Intermediate. Выбери режим кнопками внизу 👇\n\n"
        "🎴 <b>Карточки</b> — посмотреть слово и открыть перевод\n"
        "🎲 <b>Квиз</b> — напечатать перевод с англ. на рус.\n"
        "🔁 <b>Рус → Англ</b> — напечатать перевод с рус. на англ.\n"
        "🎯 <b>Варианты</b> — выбрать правильный перевод из 4\n"
        "⚡ <b>Скорость</b> — 10 слов подряд без остановки\n"
        "📚 <b>Словарь</b> — прогресс по словам\n"
        "🔀 <b>Весь словарь</b> — карточки по всем словам\n"
        "♻️ <b>Заново</b> — сбросить прогресс\n\n"
        f"Слово выучено, когда ответишь верно <b>{MASTERY_THRESHOLD}</b> раз — "
        "и больше не появится в тестах.",
        parse_mode="HTML",
        reply_markup=MENU_BUTTONS,
    )


def is_owner(update: Update) -> bool:
    return ALLOWED_USER_ID and update.effective_user.id == ALLOWED_USER_ID


def available_words():
    progress = load_progress()
    return [c for c in flat_cards() if not is_mastered(progress, c["en"])]


async def send_card(chat_id, context: ContextTypes.DEFAULT_TYPE, card: dict, done: int, total: int):
    text = (
        f"🇬🇧 <b>Переведи на русский:</b>\n\n<b>{card['en']}</b>\n\n"
        f"<i>{done + 1}/{total}</i>"
    )
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


async def start_cards(update: Update, context: ContextTypes.DEFAULT_TYPE, only_new: bool = False):
    reset_quiz_state(context)
    cards_list = available_words() if only_new else flat_cards()
    if not cards_list:
        await update.message.reply_text(
            "🎉 Новых слов нет — всё выучено! Используй «🔀 Весь словарь» для повтора.",
            reply_markup=MENU_BUTTONS,
        )
        return

    context.user_data["queue"] = list(cards_list)
    context.user_data["cards_total"] = len(cards_list)
    await send_card(update.effective_chat.id, context, context.user_data["queue"].pop(0), 0, context.user_data["cards_total"])


async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cards(update, context, only_new=False)


async def vocab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    progress = load_progress()
    mastered = sum(1 for c in flat_cards() if is_mastered(progress, c["en"]))
    lines = [f"📊 <b>Выучено: {mastered} / {len(flat_cards())}</b>\n"]
    for title, words in load_words().items():
        lines.append(f"📚 {title}")
        for w in words:
            en = w["en"]
            cnt = get_word_progress(progress, en)
            if cnt >= MASTERY_THRESHOLD:
                status = "✅"
            elif cnt > 0:
                status = "🔄"
            else:
                status = "⚪"
            lines.append(f"   {status} {en} — <b>{w['ru']}</b> ({cnt}/{MASTERY_THRESHOLD})")

    await update.message.reply_text(
        "\n".join(lines) or "📭 Словарь пуст.",
        parse_mode="HTML",
        reply_markup=MENU_BUTTONS,
    )


async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    reset_quiz_state(context)
    pool = available_words()
    if not pool:
        await update.message.reply_text(
            "🎉 Все слова выучены! Сбрось прогресс кнопкой «♻️ Заново», чтобы повторить.",
            reply_markup=MENU_BUTTONS,
        )
        return

    count = 10 if mode == "speed" else 5
    sample = random.sample(pool, min(count, len(pool)))

    context.user_data["quiz_mode"] = mode
    context.user_data["quiz_words"] = list(sample)
    context.user_data["quiz_index"] = 0
    context.user_data["quiz_correct"] = 0
    context.user_data["quiz_wrong"] = 0
    context.user_data["quiz_mastered_new"] = 0
    context.user_data["quiz_auto"] = mode == "speed"

    await context.bot.send_message(
        update.effective_chat.id,
        f"{MODE_TITLES.get(mode, 'Тест')}\nСлов в этой тренировке: <b>{len(sample)}</b>",
        parse_mode="HTML",
    )
    await next_question(update.effective_chat.id, context)


async def next_question(chat_id, context: ContextTypes.DEFAULT_TYPE):
    words = context.user_data.get("quiz_words", [])
    idx = context.user_data.get("quiz_index", 0)
    mode = context.user_data.get("quiz_mode")

    if idx >= len(words):
        await finish_quiz(chat_id, context)
        return

    card = words[idx]
    context.user_data["quiz_word"] = card

    if mode == "choice":
        await send_choice(chat_id, context, card)
    else:
        await send_typing(chat_id, context, card, mode)


async def send_typing(chat_id, context: ContextTypes.DEFAULT_TYPE, card: dict, mode: str):
    if mode == "ru_en":
        prompt = f"🔁 <b>Напиши по-английски:</b>\n\n<b>{card['ru']}</b>"
    else:
        prompt = f"✏️ <b>Напиши перевод на русский:</b>\n\n<b>{card['en']}</b>"
    await context.bot.send_message(chat_id, prompt, parse_mode="HTML")


def build_options(card: dict):
    pool = [c["ru"] for c in flat_cards() if c["ru"] != card["ru"]]
    random.shuffle(pool)
    distractors = []
    seen = set()
    for ru in pool:
        if ru not in seen:
            seen.add(ru)
            distractors.append(ru)
        if len(distractors) == 3:
            break
    options = distractors + [card["ru"]]
    random.shuffle(options)
    correct_index = options.index(card["ru"])
    return options, correct_index


async def send_choice(chat_id, context: ContextTypes.DEFAULT_TYPE, card: dict):
    options, correct_index = build_options(card)
    context.user_data["quiz_options"] = options
    context.user_data["quiz_correct_option"] = correct_index

    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"opt|{i}")]
        for i, opt in enumerate(options)
    ]
    await context.bot.send_message(
        chat_id,
        f"🎯 <b>Выбери правильный перевод:</b>\n\n<b>{card['en']}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def check_answer(user_text: str, card: dict, mode: str) -> bool:
    text = user_text.strip().lower()
    if mode == "ru_en":
        return text == card["en"].strip().lower()
    return text == card["ru"].strip().lower()


async def register_result(chat_id, context: ContextTypes.DEFAULT_TYPE, correct: bool, card: dict):
    progress = load_progress()
    en = card["en"]

    if correct:
        new_count = get_word_progress(progress, en) + 1
        set_word_progress(progress, en, new_count)
        context.user_data["quiz_correct"] += 1
        if new_count >= MASTERY_THRESHOLD:
            context.user_data["quiz_mastered_new"] += 1
            await context.bot.send_message(
                chat_id, "✅ Верно! 🎉 <b>Слово выучено!</b>", parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id, f"✅ Верно! ({new_count}/{MASTERY_THRESHOLD})", parse_mode="HTML"
            )
    else:
        set_word_progress(progress, en, 0)
        context.user_data["quiz_wrong"] += 1
        await context.bot.send_message(
            chat_id,
            f"❌ Неверно. Правильно: <b>{card['ru']}</b> — <b>{card['en']}</b>",
            parse_mode="HTML",
        )

    context.user_data["quiz_index"] += 1
    if context.user_data.get("quiz_auto"):
        await next_question(chat_id, context)
    else:
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


async def finish_quiz(chat_id, context: ContextTypes.DEFAULT_TYPE):
    correct = context.user_data.get("quiz_correct", 0)
    wrong = context.user_data.get("quiz_wrong", 0)
    mastered_new = context.user_data.get("quiz_mastered_new", 0)
    total = len(context.user_data.get("quiz_words", []))
    words_left = len(available_words())

    msg = (
        "🏁 <b>Тренировка завершена!</b>\n\n"
        f"📊 Всего слов: {total}\n"
        f"✅ Правильно: {correct}\n"
        f"❌ Ошибок: {wrong}\n"
        f"🎉 Выучено новых: {mastered_new}\n"
        f"📚 Осталось выучить: {words_left}"
    )
    await context.bot.send_message(chat_id, msg, parse_mode="HTML")

    reset_quiz_state(context)

    if words_left:
        await context.bot.send_message(
            chat_id, "Хочешь ещё? Выбирай режим кнопками внизу 👇", reply_markup=MENU_BUTTONS
        )
    else:
        await context.bot.send_message(
            chat_id, "🎉 Поздравляю! Ты выучил(а) все слова!", reply_markup=MENU_BUTTONS
        )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🎴 Карточки":
        await start_cards(update, context, only_new=True)
    elif text == "🔀 Весь словарь":
        await start_cards(update, context, only_new=False)
    elif text == "🎲 Квиз":
        await start_quiz(update, context, "en_ru")
    elif text == "🔁 Рус → Англ":
        await start_quiz(update, context, "ru_en")
    elif text == "🎯 Варианты":
        await start_quiz(update, context, "choice")
    elif text == "⚡ Скорость":
        await start_quiz(update, context, "speed")
    elif text == "📚 Словарь":
        await vocab(update, context)
    elif text == "♻️ Заново":
        reset_quiz_state(context)
        await update.message.reply_text(
            "♻️ Готово! Состояние сброшено, выбери режим заново. "
            "(Прогресс слов сохраняется — сбросить его можно кнопкой ниже.)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Сбросить прогресс слов", callback_data="quiz_reset")]
            ]),
        )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("quiz_mode")
    if mode in ("en_ru", "ru_en", "speed"):
        await handle_quiz_answer(update, context)
    else:
        await handle_menu(update, context)


async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("quiz_mode")
    user_text = update.message.text.strip()
    card = context.user_data.get("quiz_word")
    if not card:
        return
    chat_id = update.effective_chat.id

    if user_text.lower() in ("?", "пропуск", "skip"):
        await context.bot.send_message(
            chat_id,
            f"⏭ Пропущено. Правильно: <b>{card['ru']}</b> — <b>{card['en']}</b>",
            parse_mode="HTML",
        )
        context.user_data["quiz_index"] += 1
        if context.user_data.get("quiz_auto"):
            await next_question(chat_id, context)
        else:
            await ask_continue(chat_id, context)
        return

    correct = check_answer(user_text, card, mode)
    await register_result(chat_id, context, correct, card)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data.startswith("show|"):
        en = data.split("|", 1)[1]
        ru = next((c["ru"] for c in flat_cards() if c["en"] == en), "?")
        queue = context.user_data.get("queue", [])
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("➡ Дальше", callback_data="next")]
        ]) if queue else InlineKeyboardMarkup([
            [InlineKeyboardButton("🏁 Завершить", callback_data="finish")]
        ])
        await query.edit_message_text(f"✅ <b>{en}</b> — <b>{ru}</b>", parse_mode="HTML", reply_markup=markup)
    elif data == "skip":
        queue = context.user_data.get("queue", [])
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("➡ Дальше", callback_data="next")]
        ]) if queue else InlineKeyboardMarkup([
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
            f"🎉 Готово! Повторили <b>{total}</b> слов(а).",
            parse_mode="HTML",
        )
        reset_quiz_state(context)
    elif data.startswith("opt|"):
        idx = int(data.split("|", 1)[1])
        options = context.user_data.get("quiz_options", [])
        correct_option = context.user_data.get("quiz_correct_option")
        card = context.user_data.get("quiz_word")
        chosen = options[idx] if 0 <= idx < len(options) else "?"
        await query.edit_message_text(
            f"Твой выбор: <b>{chosen}</b>", parse_mode="HTML"
        )
        await register_result(chat_id, context, idx == correct_option, card)
    elif data == "quiz_continue":
        await next_question(chat_id, context)
    elif data == "quiz_stop":
        await finish_quiz(chat_id, context)
    elif data == "quiz_reset":
        progress = load_progress()
        for card in flat_cards():
            progress.pop(card["en"], None)
        save_progress(progress)
        reset_quiz_state(context)
        await query.edit_message_text(
            "🗑 Прогресс сброшен! Все слова снова в тренировке.\nВыбирай режим кнопками внизу 👇",
        )


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Переменная BOT_TOKEN не задана!")

    threading.Thread(target=start_http_server, daemon=True).start()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(button))

    logger.info("Бот запущен (интерактивный режим).")
    app.run_polling()


if __name__ == "__main__":
    main()
