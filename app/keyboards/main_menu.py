from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def button(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def keyboard(*rows):
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def menu_button():
    return button("🏠 Главное меню", "menu")


def main_menu():
    return keyboard(
        [button("🔎 Найти аромат", "search:new"), button("📢 Мои каналы", "channels:0")],
        [button("⚙️ Настройки", "settings"), button("🕓 История поиска", "history:0")],
    )
