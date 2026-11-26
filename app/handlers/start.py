from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.keyboards.main_menu import main_menu

router = Router()
WELCOME = "👋 Привет! Я помогу найти нужный аромат среди твоих Telegram-каналов"


class OwnerOnly(BaseMiddleware):
    def __init__(self, owner):
        self.owner = owner

    async def __call__(self, handler, event, data):
        message = event.message if isinstance(event, CallbackQuery) else event
        user = event.from_user
        if isinstance(message, Message) and message.chat.type == "private" and user and user.id == self.owner:
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            await event.answer("Доступ только для владельца.", show_alert=True)
        elif isinstance(event, Message) and event.chat.type == "private":
            await event.answer("Доступ только для владельца.")


@router.message(CommandStart())
async def start(message, state):
    await state.clear()
    await message.answer(WELCOME, reply_markup=main_menu())


@router.message(Command("id"))
async def owner_id(message):
    await message.answer(str(message.from_user.id))


@router.callback_query(F.data == "menu")
async def menu(callback, state):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(WELCOME, reply_markup=main_menu())
