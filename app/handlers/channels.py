import math

from aiogram import F, Router
from aiogram.fsm.state import State, StatesGroup
from telethon import errors

from app.handlers.search import api_error
from app.keyboards.main_menu import button, keyboard, menu_button
from app.keyboards.pagination import navigation
from app.services.progress_service import Status
from app.services.telegram_client import SessionExpired

router = Router()
PAGE_SIZE = 8


class ChannelForm(StatesGroup):
    link = State()


async def show(message, telegram, repo, page=0, *, refresh=False, toggle=None, notice=""):
    try:
        channels = await telegram.channels(refresh=refresh)
    except (SessionExpired, errors.RPCError, OSError) as error:
        await Status(message).edit(api_error(error), keyboard(
            [button("🔄 Обновить список", "channel-refresh")], [menu_button()]), final=True)
        return
    repo.sync_channels(channels)
    if toggle is not None and any(channel.id == toggle for channel in channels):
        repo.toggle(toggle)
    enabled = repo.channels()
    pages = max(1, math.ceil(len(channels) / PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    rows = [
        [button(f"{'✅' if enabled[channel.id] else '➖'} {channel.title[:48]}",
                f"channel-toggle:{page}:{channel.id}")]
        for channel in channels[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    ]
    label = f"📢 Мои каналы · {page + 1}/{pages}\nКаналы с ✅ участвуют в поиске. Нажмите на канал, чтобы изменить выбор."
    if not channels:
        label = "Каналы не найдены. Подпишитесь на канал в Telegram или добавьте доступный канал по ссылке."
    if notice:
        label = f"{notice}\n\n{label}"
    await Status(message).edit(label, keyboard(
        *rows, *navigation("channels", page, pages),
        [button("➕ Добавить канал", "channel-add"), button("🔄 Обновить список", "channel-refresh")],
        [menu_button()]), final=True)


@router.callback_query(F.data.startswith("channels:") | F.data.startswith("channel-toggle:")
                       | (F.data == "channel-refresh"))
async def channel_list(callback, state, telegram, repo, jobs):
    action, *args = callback.data.split(":")
    if jobs.active and action == "channel-refresh":
        await callback.answer("Обновите список после завершения поиска.", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    page = int(args[0]) if args else 0
    await show(callback.message, telegram, repo, page, refresh=action == "channel-refresh",
               toggle=int(args[1]) if len(args) == 2 else None)


@router.callback_query(F.data == "channel-add")
async def ask_link(callback, state):
    await callback.answer()
    await state.set_state(ChannelForm.link)
    await callback.message.edit_text("Отправьте @username или ссылку t.me на канал.",
                                     reply_markup=keyboard([menu_button()]))


@router.message(ChannelForm.link)
async def add_channel(message, state, telegram, repo, jobs):
    if jobs.active:
        await message.answer("Добавьте канал после завершения поиска.")
        return
    try:
        channel = await telegram.add((message.text or "").strip())
    except (SessionExpired, errors.RPCError, OSError) as error:
        await message.answer(api_error(error))
        return
    if not channel:
        await message.answer("Канал недоступен. Проверьте ссылку и доступ к каналу из личного аккаунта.")
        return
    repo.add_channel(channel)
    await state.clear()
    status = await message.answer("Канал добавлен.")
    await show(status, telegram, repo, notice=f"✅ {channel.title[:150]}")
