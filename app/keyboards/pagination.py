from aiogram.types import InlineKeyboardButton

from app.keyboards.main_menu import button, keyboard, menu_button


def navigation(prefix, page, pages):
    row = []
    if page:
        row.append(button("⬅️ Назад", f"{prefix}:{page - 1}"))
    if page + 1 < pages:
        row.append(button("➡️ Далее", f"{prefix}:{page + 1}"))
    return [row] if row else []


def results(run, page, pages, order, offers):
    links = [[InlineKeyboardButton(text=f"Открыть объявление №{number}", url=offer.link)]
             for number, offer in offers]
    return keyboard(
        *links, *navigation(f"result:{run}:{order}", page, pages),
        [button("💰 Сначала дешёвые", f"result:{run}:cheap:0"),
         button("🆕 Сначала новые", f"result:{run}:new:0")],
        [button("🔄 Повторить поиск", f"repeat:{run}:0"),
         button("♻️ Обновить без кеша", f"repeat:{run}:1")],
        [button("🔎 Новый поиск", "search:new"), menu_button()],
    )
