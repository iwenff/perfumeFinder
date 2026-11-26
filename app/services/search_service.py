import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from telethon import errors

from app.services.perfume_parser import parse
from app.services.public_channels import PreviewLimit
from app.services.telegram_client import RateLimited
from app.utils.text import normalize

log = logging.getLogger(__name__)


@dataclass
class Progress:
    total: int = 0
    checked: int = 0
    found: int = 0
    channel: str = ""
    phase: str = "📡 Получаю список каналов…"


@dataclass(frozen=True)
class Offer:
    name: str
    volume: float | None
    price: float | None
    currency: str | None
    snippet: str
    channel: str
    date: str
    link: str


@dataclass
class Result:
    offers: list[Offer]
    checked: int
    total: int
    failed: int = 0
    wait: int = 0
    cached: bool = False
    session_expired: bool = False
    limited: int = 0

    @property
    def partial(self):
        return bool(self.failed or self.limited or self.wait or self.session_expired or self.checked < self.total)


def sort_offers(offers, order):
    recent = sorted(offers, key=lambda offer: offer.date, reverse=True)
    if order == "new":
        return recent
    return sorted(recent, key=lambda offer: (offer.price is None,
                  {"RUB": 0, "EUR": 1, "USD": 2}.get(offer.currency, 3), offer.price or 0))


class SearchService:
    def __init__(self, telegram, repo):
        self.telegram = telegram
        self.repo = repo

    async def run(self, name, volume, days, progress, *, refresh=False):
        self.repo.record(name, volume, days)
        channels = await self.telegram.channels()
        self.repo.sync_channels(channels)
        enabled = self.repo.channels()
        channels = [channel for channel in channels if enabled[channel.id]]
        progress.total = len(channels)
        key = repr((normalize(name), volume, days, sorted(channel.id for channel in channels)))
        if not refresh and (cached := self.repo.cached(key)) is not None:
            return Result([Offer(**row) for row in cached["offers"]], cached["checked"],
                          cached["total"], cached=True)

        cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
        result = Result([], 0, len(channels))
        unique = {}
        progress.phase = "🔎 Ищу"
        for channel in channels:
            progress.channel = channel.title
            try:
                async for message in self.telegram.messages(channel, name, cutoff):
                    progress.phase = "📦 Проверяю объёмы и стоимость"
                    for item in parse(message.message, name, volume):
                        offer = Offer(**asdict(item), channel=channel.title,
                                      date=message.date.isoformat(), link=channel.link(message.id))
                        # Keep the newest copy of identical offer text and terms.
                        fingerprint = (normalize(item.name), item.volume, item.price,
                                       item.currency, normalize(message.message))
                        previous = unique.get(fingerprint)
                        if previous is None or previous.date < offer.date:
                            unique[fingerprint] = offer
                    progress.found = len(unique)
                    progress.phase = "🔎 Ищу"
                    await asyncio.sleep(0)
            except PreviewLimit:
                result.limited += 1
            except errors.FloodWaitError as error:
                if not isinstance(error, RateLimited):
                    self.telegram.note_limit(error.seconds)
                result.wait = error.seconds
                break
            except (errors.UnauthorizedError, errors.AuthKeyError):
                result.session_expired = True
                break
            except (errors.RPCError, OSError, TimeoutError) as error:
                result.failed += 1
                log.warning("Ошибка поиска в канале %s (%s)", channel.id, type(error).__name__)
            progress.checked += 1
            await asyncio.sleep(0.25)
        progress.phase = "✨ Сортирую найденные предложения…"
        progress.channel = ""
        await asyncio.sleep(0)
        result.checked = progress.checked
        result.offers = sort_offers(unique.values(), "cheap")
        if not result.partial:
            self.repo.store(key, asdict(result))
        return result

