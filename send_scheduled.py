import asyncio
import json
import os
import random

from telegram import Bot

WORDS_FILE = os.path.join(os.path.dirname(__file__), "words.json")
CHAT_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))
QUIZ_COUNT = int(os.environ.get("QUIZ_COUNT", "5"))


def load_words():
    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_cards():
    cards = []
    for title, words in load_words().items():
        for w in words:
            cards.append({"en": w["en"], "ru": w["ru"]})
    if not cards:
        return []
    return random.sample(cards, min(QUIZ_COUNT, len(cards)))


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
