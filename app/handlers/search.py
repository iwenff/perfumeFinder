import asyncio
import logging
import math
import re
import secrets
import time
from collections import OrderedDict
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.fsm.state import State, StatesGroup
from telethon import errors

from app.keyboards import pagination
from app.keyboards.main_menu import keyboard, menu_button
from app.keyboards.search import cancel, volume_text, volumes
from app.services.progress_service import Status
from app.services.search_service import Progress, sort_offers
from app.services.telegram_client import SessionExpired
from app.utils.text import normalize

router = Router()
log = logging.getLogger(__name__)


class SearchForm(StatesGroup):
    name = State()
    volume = State()
    custom = State()


def page_items(offers, page, size=5):
    pages = max(1, math.ceil(len(offers) / size))
    page = min(max(0, page), pages - 1)
    start = page * size
    return page, pages, list(enumerate(offers[start:start + size], start + 1))


def price_text(offer):
    if offer.price is None:
        return "Цена не определена"
    formatted = f"{offer.price:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")
    return formatted + " " + {"RUB": "₽", "EUR": "€", "USD": "$"}[offer.currency]


def render(run, request, result, order="cheap", page=0):
    name, volume, _days = request
    page, pages, items = page_items(sort_offers(result.offers, order), page)
    lines = [f"🧴 {name}\n💧 {volume_text(volume)}\nСтраница {page + 1} из {pages}"]
    if result.partial:
        lines.append("⚠️ Показаны частичные результаты.")
    if not items:
        lines.append("Предложения не найдены.")
    for number, offer in items:
        date = datetime.fromisoformat(offer.date).astimezone().strftime("%d.%m.%Y")
        lines.append(
            f"{'🥇' if number == 1 else '📦'} Предложение №{number}\n"
            f"🧴 {offer.name[:120]}\n💧 {volume_text(offer.volume) if offer.volume else 'Объём не указан'}\n"
            f"💰 {price_text(offer)}\n📢 {offer.channel[:100]}\n📅 {date}\n"
            f"💬 {' '.join(offer.snippet.split())[:110]}"
        )
    return "\n\n".join(lines), pagination.results(run, page, pages, order, items)


def api_error(error):
    if isinstance(error, SessionExpired):
        return "Сессия личного аккаунта истекла. Перезапустите бота и войдите в локальном терминале."
    if isinstance(error, errors.FloodWaitError):
        return f"Telegram ограничил запросы. Повторите через {error.seconds} сек."
    if isinstance(error, (OSError, TimeoutError)):
        return "Не удалось связаться с Telegram. Проверьте подключение к интернету."
    return "Не удалось выполнить запрос. Попробуйте позже."


async def send(origin, text, markup):
    try:
        return await origin.answer(text, reply_markup=markup)
    except TelegramRetryAfter as error:
        await asyncio.sleep(error.retry_after)
        return await origin.answer(text, reply_markup=markup)


class SearchJobs:
    def __init__(self, service):
        self.service = service
        self.task = None
        self.run = None
        self.cancellable = False
        self.closing = False
        self.views = OrderedDict()

    @property
    def active(self):
        return self.task is not None and not self.task.done()

    def launch(self, message, request, refresh=False):
        if self.active:
            return False
        self.run = secrets.token_hex(5)
        self.cancellable = False
        self.task = asyncio.create_task(self.execute(self.run, message, request, refresh))
        return True

    def cancel(self, run):
        if self.active and self.cancellable and self.run == run:
            self.cancellable = False
            self.task.cancel()
            return True
        return False

    async def close(self):
        self.closing = True
        if self.active:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def execute(self, run, origin, request, refresh):
        name, volume, days = request
        progress = Progress()
        started = time.monotonic()
        status = None
        animation = None
        result = None
        try:
            message = await send(origin, "🔍 Подключаюсь к Telegram…", cancel(run))
            status = Status(message)
            self.cancellable = True
            animation = asyncio.create_task(status.animate(run, name, volume, progress, started))
            try:
                result = await self.service.run(name, volume, days, progress, refresh=refresh)
                summary = (
                    f"{'⚠️ Поиск завершён частично' if result.partial else '✅ Поиск завершён!'}\n\n"
                    f"🧴 {name}\n💧 Объём: {volume_text(volume)}\n"
                    f"📢 Проверено каналов: {result.checked} из {result.total}\n"
                    f"📦 Найдено предложений: {len(result.offers)}\n"
                    f"⏱ Время поиска: {time.monotonic() - started:.1f} сек."
                )
                if result.cached:
                    summary += "\nРезультат из кеша."
                if result.failed:
                    summary += f"\nОшибки доступа или связи: {result.failed}."
                if result.limited:
                    summary += f"\nДостигнут лимит страниц публичного превью в каналах: {result.limited}."
                if result.session_expired:
                    summary += "\n" + api_error(SessionExpired())
                if result.wait:
                    summary += f"\nTelegram ограничил запросы на {result.wait} сек."
                if not result.total:
                    summary += "\nВыберите каналы в разделе «Мои каналы»."
            except asyncio.CancelledError:
                if self.closing:
                    raise
                summary = "❌ Поиск отменён."
            except Exception as error:
                summary = api_error(error)
                log.warning("Поиск завершился ошибкой (%s)", type(error).__name__)
            finally:
                self.cancellable = False
                animation.cancel()
                await asyncio.gather(animation, return_exceptions=True)

            if result is not None:
                try:
                    await status.edit(summary, final=True)
                except TelegramAPIError as error:
                    log.warning("Не удалось обновить статус (%s)", type(error).__name__)
                self.views[run] = (request, result)
                if len(self.views) > 10:
                    self.views.popitem(last=False)
                text, markup = render(run, request, result)
                await send(origin, text, markup)
            else:
                await status.edit(summary, keyboard([menu_button()]), final=True)
        except TelegramAPIError as error:
            log.warning("Ошибка доставки в Telegram (%s)", type(error).__name__)


@router.callback_query(F.data == "search:new")
async def new(callback, state, jobs):
    if jobs.active:
        await callback.answer("Поиск уже выполняется.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(SearchForm.name)
    await callback.message.edit_text("Введите название аромата, например Tom Ford Oud Wood.",
                                     reply_markup=keyboard([menu_button()]))


@router.message(SearchForm.name)
async def name_input(message, state):
    name = " ".join((message.text or "").split())
    if not 2 <= len(name) <= 100 or not normalize(name):
        await message.answer("Введите название аромата длиной от 2 до 100 символов.")
        return
    prompt = await message.answer(f"🧴 {name}\nВыберите объём.", reply_markup=volumes())
    await state.update_data(name=name, prompt=prompt.message_id)
    await state.set_state(SearchForm.volume)


@router.callback_query(SearchForm.volume, F.data.startswith("volume:"))
async def choose_volume(callback, state, jobs, repo):
    data = await state.get_data()
    if callback.message.message_id != data["prompt"]:
        await callback.answer("Используйте последнее сообщение с выбором объёма.")
        return
    value = callback.data.split(":")[1]
    if value == "custom":
        await state.set_state(SearchForm.custom)
        await callback.answer()
        await callback.message.edit_text("Введите объём в мл, например 7,5.", reply_markup=keyboard([menu_button()]))
        return
    volume = None if value == "any" else float(value)
    if jobs.launch(callback.message, (data["name"], volume, repo.days())):
        await state.clear()
        await callback.answer()
    else:
        await callback.answer("Поиск уже выполняется.", show_alert=True)


@router.callback_query(F.data.startswith("volume:"))
async def expired_volume(callback):
    await callback.answer("Начните новый поиск через главное меню.", show_alert=True)


@router.message(SearchForm.custom)
async def custom_volume(message, state, jobs, repo):
    match = re.fullmatch(r"(\d{1,5}(?:[.,]\d{1,3})?)\s*(?:мл|ml)?", (message.text or "").strip(), re.I)
    volume = float(match[1].replace(",", ".")) if match else 0
    if not 0 < volume <= 10000:
        await message.answer("Введите объём больше нуля и до 10 000 мл, например 7,5.")
        return
    data = await state.get_data()
    if jobs.launch(message, (data["name"], volume, repo.days())):
        await state.clear()
    else:
        await message.answer("Поиск уже выполняется.")


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_search(callback, jobs):
    run = callback.data.split(":")[1]
    await callback.answer("Останавливаю поиск…" if jobs.cancel(run) else "Поиск уже завершён.")


@router.callback_query(F.data.startswith("result:"))
async def change_page(callback, jobs):
    _, run, order, page = callback.data.split(":")
    if run not in jobs.views:
        await callback.answer("Откройте историю и повторите запрос.", show_alert=True)
        return
    await callback.answer()
    text, markup = render(run, *jobs.views[run], order, int(page))
    await Status(callback.message).edit(text, markup, final=True)


@router.callback_query(F.data.startswith("repeat:"))
async def repeat(callback, state, jobs):
    _, run, refresh = callback.data.split(":")
    if run not in jobs.views:
        await callback.answer("Откройте историю и повторите запрос.", show_alert=True)
        return
    if jobs.launch(callback.message, jobs.views[run][0], refresh == "1"):
        await state.clear()
        await callback.answer()
    else:
        await callback.answer("Поиск уже выполняется.", show_alert=True)
