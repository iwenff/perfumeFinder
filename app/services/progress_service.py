import asyncio
import itertools
import time

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter

from app.keyboards.search import cancel, volume_text


class Status:
    def __init__(self, message):
        self.message = message
        self.retry_at = 0.0

    async def edit(self, text, markup=None, *, final=False):
        while True:
            delay = self.retry_at - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                await self.message.edit_text(text, reply_markup=markup)
            except TelegramRetryAfter as error:
                self.retry_at = time.monotonic() + error.retry_after
                if final:
                    final = False
                    continue
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).lower():
                    raise
            return

    async def animate(self, run, name, volume, progress, started):
        for icon in itertools.cycle(("⏳", "⌛")):
            await asyncio.sleep(1.5)
            ratio = progress.checked / progress.total if progress.total else 0
            filled = int(ratio * 10)
            text = (
                f"{progress.phase} {name if progress.total else ''}\n"
                f"Объём: {volume_text(volume)}\n\n"
                f"{'█' * filled}{'░' * (10 - filled)} {ratio:.0%}\n"
                f"📢 Проверено каналов: {progress.checked} из {progress.total}\n"
                f"📦 Найдено предложений: {progress.found}\n"
                f"{icon} Прошло: {int(time.monotonic() - started)} сек."
            )
            if progress.channel:
                text += f"\nТекущий канал: {progress.channel[:150]}"
            try:
                await self.edit(text, cancel(run))
            except TelegramNetworkError:
                continue
            except TelegramBadRequest:
                return
