from aiogram import F, Router

from app.services.progress_service import Status
from app.keyboards.main_menu import button, keyboard, menu_button

router = Router()
PERIODS = {7: "Последние 7 дней", 30: "Последние 30 дней",
           90: "Последние 90 дней", 0: "За всё доступное время"}


@router.callback_query((F.data == "settings") | F.data.startswith("period:"))
async def settings(callback, state, repo):
    await state.clear()
    if callback.data.startswith("period:"):
        value = int(callback.data.split(":")[1])
        if value in PERIODS:
            repo.set_days(value)
    await callback.answer()
    current = repo.days()
    rows = [[button(("✓ " if days == current else "") + label, f"period:{days}")]
            for days, label in PERIODS.items()]
    await Status(callback.message).edit("⚙️ Период поиска", keyboard(*rows, [menu_button()]), final=True)
