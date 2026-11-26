from aiogram import F, Router

from app.handlers.settings import PERIODS
from app.keyboards.main_menu import button, keyboard, menu_button
from app.keyboards.pagination import navigation
from app.keyboards.search import volume_text
from app.services.progress_service import Status

router = Router()
SIZE = 7


@router.callback_query(F.data.startswith("history:"))
async def history(callback, state, repo):
    await state.clear()
    await callback.answer()
    page = max(0, int(callback.data.split(":")[1]))
    entries = repo.history(SIZE + 1, page * SIZE)
    rows = [
        [button(f"{name[:28]} · {volume_text(volume)} · {PERIODS[days]}",
                f"history-repeat:{item}")]
        for item, name, volume, days in entries[:SIZE]
    ]
    text = "🕓 История поиска\nНажмите на запрос, чтобы повторить его." if entries else "🕓 История поиска пока пуста."
    await Status(callback.message).edit(text, keyboard(
        *rows, *navigation("history", page, page + (2 if len(entries) > SIZE else 1)), [menu_button()]), final=True)


@router.callback_query(F.data.startswith("history-repeat:"))
async def history_repeat(callback, state, repo, jobs):
    request = repo.previous(int(callback.data.split(":")[1]))
    if request and jobs.launch(callback.message, request):
        await state.clear()
        await callback.answer()
    else:
        await callback.answer("Поиск уже выполняется." if request else "Запрос не найден.", show_alert=True)
