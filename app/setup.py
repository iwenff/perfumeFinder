import asyncio
import os

from dotenv import dotenv_values, set_key

from app.config import ENV, PATTERNS, ROOT, valid
from app.owner_id import lookup


def main():
    if not ENV.exists():
        with os.fdopen(os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                       "w", encoding="utf-8") as output:
            output.write((ROOT / ".env.example").read_text(encoding="utf-8"))

    saved = dotenv_values(ENV, interpolate=False)
    print("Заполните настройки по инструкции README.md.")
    print("Для открытых каналов оставьте API_ID и API_HASH пустыми.")
    for key in PATTERNS:
        if key == "API_HASH" and not (saved.get("API_ID") or saved.get("API_HASH")):
            continue
        if saved.get(key):
            if not valid(key, saved[key]):
                print(f"Проверьте {key} в существующем файле .env.")
                return 1
            continue
        if key == "OWNER_ID":
            print("Чтобы узнать ID, нажмите Enter без значения и следуйте подсказке.")
        while True:
            value = input(f"{key}: ").strip()
            if not value and key == "API_ID" and not saved.get("API_HASH"):
                break
            if not value and key == "OWNER_ID":
                try:
                    asyncio.run(lookup(dotenv_values(ENV, interpolate=False)["BOT_TOKEN"]))
                except Exception as error:
                    print(f"Не удалось узнать ID ({type(error).__name__}). См. README.md.")
                continue
            if valid(key, value):
                set_key(str(ENV), key, value, quote_mode="never")
                ENV.chmod(0o600)
                saved[key] = value
                break
            print("Неверный формат. Проверьте значение по README.md.")
    print("Готово. Запустите start.bat или bash start.sh.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nНастройка прервана. Введённые значения сохранены.")
