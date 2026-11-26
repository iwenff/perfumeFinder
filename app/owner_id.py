"""Read the sender ID of a private message to the owner's new bot."""
import asyncio
import sys
from getpass import getpass

from aiogram import Bot

from app.config import valid


async def lookup(token):
    async with Bot(token) as bot:
        profile = await bot.get_me()
        input(f"Отправьте /start боту @{profile.username} из личного аккаунта и нажмите Enter. ")
        updates = await bot.get_updates(allowed_updates=["message"], timeout=5)
        ids = sorted({
            update.message.from_user.id
            for update in updates
            if update.message and update.message.chat.type == "private"
            and update.message.from_user and not update.message.from_user.is_bot
            and update.message.text == "/start"
        })
        if len(ids) == 1:
            print(f"OWNER_ID: {ids[0]}")
            return 0
        print("Не удалось однозначно определить ID. Убедитесь, что бот остановлен и только вы отправили /start.")
        return 1


def main():
    if not sys.stdin.isatty():
        print("Запустите команду в локальном терминале.")
        return 1
    try:
        token = getpass("BOT_TOKEN: ").strip()
        if not valid("BOT_TOKEN", token):
            print("Проверьте формат токена.")
            return 1
        return asyncio.run(lookup(token))
    except (KeyboardInterrupt, EOFError):
        return 1
    except Exception as error:
        print(f"Не удалось получить ID ({type(error).__name__}). Проверьте токен, сеть и запущенные копии.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
