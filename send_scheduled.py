import asyncio
import json
import os
import random

from telegram import Bot

BASE_DIR = os.path.dirname(__file__)
WORDS_FILE = os.path.join(BASE_DIR, "words.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "progress.json")
CHAT_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))
QUIZ_COUNT = int(os.environ.get("QUIZ_COUNT", "5"))
MASTERY_THRESHOLD = 5


def load_words():
    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def pick_cards():
    all_cards = []
    for title, words in load_words().items():
        for w in words:
            all_cards.append({"en": w["en"], "ru": w["ru"]})

    if not all_cards:
        return []

    progress = load_progress()

    non_mastered = [
        c for c in all_cards
        if progress.get(c["en"], {}).get("correct", 0) < MASTERY_THRESHOLD
    ]

    if not non_mastered:
        print("Все слова выучены, рассылка пропущена.")
        return []

    return random.sample(non_mastered, min(QUIZ_COUNT, len(non_mastered)))


async def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Переменная BOT_TOKEN не задана!")

    sample = pick_cards()
    if not sample:
        print("Словарь пуст, рассылка пропущена.")
        return

    bot = Bot(token)
    intro = "📬 <b>Время тренировки!</b> Переведи эти слова:\n\n" + "\n".join(
        f"{i + 1}. <b>{c['en']}</b>" for i, c in enumerate(sample)
    )
    await bot.send_message(CHAT_ID, intro, parse_mode="HTML")

    for c in sample:
        await bot.send_message(
            CHAT_ID, f"🇬🇧 <b>{c['en']}</b>\n\n<i>Ответ — через 10 секунд</i>",
            parse_mode="HTML",
        )
        await asyncio.sleep(10)
        await bot.send_message(CHAT_ID, f"✅ <b>{c['ru']}</b>", parse_mode="HTML")

    print(f"Отправлено карточек: {len(sample)}")


if __name__ == "__main__":
    asyncio.run(main())