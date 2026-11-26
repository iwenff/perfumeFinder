import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from telethon import errors, types

from app.database.repository import Repository
from app.handlers.search import SearchJobs, page_items, render
from app.handlers.start import WELCOME
from app.main import build_dispatcher
from app.services.search_service import Offer, Progress, SearchService, sort_offers
from app.services.telegram_client import Channel


def offer(price, date="2026-11-25T00:00:00+00:00"):
    return Offer("Oud Wood", 10, price, "RUB" if price else None, "отливант", "Market",
                 date, "https://t.me/c/12/34")


def test_sort_and_pagination():
    recent = offer(200, "2026-11-26T00:00:00+00:00")
    items = [offer(None), offer(300), recent, offer(100)]
    assert [item.price for item in sort_offers(items, "cheap")] == [100, 200, 300, None]
    assert sort_offers(items, "new")[0] == recent
    page, pages, entries = page_items(items * 3, 1)
    assert (page, pages, [index for index, _ in entries]) == (1, 3, [6, 7, 8, 9, 10])
    assert page_items([], 8) == (0, 1, [])


def test_cache_channels_expiry_and_refresh(tmp_path, monkeypatch):
    repository = Repository(tmp_path / "test.sqlite")
    clock = [1000]
    monkeypatch.setattr("app.database.repository.time.time", lambda: clock[0])
    channel = Channel(42, "Market", None, types.InputPeerChannel(42, 100))
    calls = []

    class Telegram:
        channels = AsyncMock(return_value=[channel])

        async def messages(self, selected, name, cutoff):
            calls.append((selected, cutoff))
            day = datetime.now(timezone.utc)
            yield SimpleNamespace(message="Oud Wood 10ml — 1800 ₽", id=1, date=day)
            yield SimpleNamespace(message="OUD WOOD 10ml — 1800 ₽", id=2, date=day + timedelta(seconds=1))

    async def scenario():
        service = SearchService(Telegram(), repository)
        first = await service.run("Oud Wood", 10, 30, Progress())
        assert first.checked == 1 and not first.cached
        assert len(first.offers) == 1
        assert first.offers[0].link == "https://t.me/c/42/2"
        assert (await service.run("oud-wood", 10, 30, Progress())).cached
        assert len(calls) == 1
        clock[0] += 299
        assert (await service.run("oud wood", 10, 30, Progress())).cached
        clock[0] += 1
        assert not (await service.run("oud wood", 10, 30, Progress())).cached
        assert not (await service.run("oud wood", 10, 30, Progress(), refresh=True)).cached
        repository.toggle(42)
        assert (await service.run("oud wood", 10, 30, Progress())).total == 0
        assert len(calls) == 3
        assert len(repository.history()) == 6
        repository.add_channel(channel)
        assert Repository(repository.path).added_channels() == [(42, "Market", None, 100)]
        assert Repository(repository.path).channels() == {42: True}

    asyncio.run(scenario())


def test_owner_access():
    async def scenario():
        session = AsyncMock()
        bot = Bot("123:mock-token", session=session)
        dispatcher = build_dispatcher(23)
        owner = User(id=23, is_bot=False, first_name="Owner")
        stranger = User(id=24, is_bot=False, first_name="Stranger")

        def message(user, chat):
            return Message(message_id=1, date=datetime.now(timezone.utc), chat=chat,
                           from_user=user, text="/start")

        private = Chat(id=23, type=ChatType.PRIVATE)
        await dispatcher.feed_update(bot, Update(update_id=1, message=message(owner, private)))
        method = session.await_args.args[1]
        assert method.text == WELCOME and method.reply_markup.inline_keyboard

        their_chat = Chat(id=24, type=ChatType.PRIVATE)
        await dispatcher.feed_update(bot, Update(update_id=2, message=message(stranger, their_chat)))
        assert session.await_args.args[1].text == "Доступ только для владельца."
        callback = CallbackQuery(id="1", from_user=stranger, chat_instance="chat",
                                 message=message(owner, private), data="search:new")
        await dispatcher.feed_update(bot, Update(update_id=3, callback_query=callback))
        assert session.await_args.args[1].show_alert
        group = Chat(id=-100, type=ChatType.SUPERGROUP)
        await dispatcher.feed_update(bot, Update(update_id=4, message=message(owner, group)))
        assert session.await_count == 3

    asyncio.run(scenario())


def test_cancel_reaches_search_and_edits_status():
    async def scenario():
        entered = asyncio.Event()
        stopped = asyncio.Event()

        class Service:
            async def run(self, *args, **kwargs):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

        jobs = SearchJobs(Service())
        message = SimpleNamespace(edit_text=AsyncMock())
        origin = SimpleNamespace(answer=AsyncMock(return_value=message))
        request = ("Oud Wood", 10, 30)
        assert jobs.launch(origin, request)
        await asyncio.wait_for(entered.wait(), 2)
        assert not jobs.launch(origin, request)
        assert not jobs.cancel("different")
        assert jobs.cancel(jobs.run)
        await asyncio.wait_for(jobs.task, 2)
        assert stopped.is_set()
        message.edit_text.assert_awaited_once()
        assert "отменён" in message.edit_text.await_args.args[0]
        origin.answer.assert_awaited_once()
        assert not jobs.active

    asyncio.run(scenario())


def test_partial_channel_failure_and_flood_wait(tmp_path):
    repository = Repository(tmp_path / "test.sqlite")
    channel_list = [Channel(index, str(index), None, types.InputPeerChannel(index, index))
                for index in range(4)]

    class Telegram:
        channels = AsyncMock(return_value=channel_list)
        note_limit = staticmethod(lambda seconds: None)

        async def messages(self, channel, name, cutoff):
            if channel.id == 0:
                raise errors.ChannelPrivateError(request=None)
            if channel.id == 2:
                raise errors.FloodWaitError(request=None, capture=30)
            assert channel.id == 1
            yield SimpleNamespace(message="Oud Wood 10 ml — 200 ₽", id=5, date=datetime.now(timezone.utc))

    result = asyncio.run(SearchService(Telegram(), repository).run("Oud Wood", 10, 7, Progress()))
    assert result.partial and result.failed == 1 and result.total == 4 and result.checked == 2
    assert result.wait == 30 and len(result.offers) == 1
    text, markup = render("1", ("Oud Wood", 10, 7), result)
    assert "частичные" in text and markup.inline_keyboard[0][0].url == "https://t.me/c/1/5"
    assert repository.cached(repr(("oud wood", 10, 7, [0, 1, 2, 3]))) is None


def test_telegram_search_uses_server_and_keeps_caption(tmp_path, monkeypatch):
    from app.config import Config
    from app.services.telegram_client import PersonalTelegram

    channel = Channel(42, "Public", "public_market", types.InputPeerChannel(42, 100))
    now = datetime.now(timezone.utc)
    caption = SimpleNamespace(id=1, date=now, message="Oud-Wood 10мл — 1850 ₽", media=object())
    old = SimpleNamespace(id=2, date=now - timedelta(days=10), message="Oud Wood 10мл — 500 ₽")
    calls = []

    class Client:
        async def iter_messages(self, peer, *, search, wait_time):
            calls.append((peer, search, wait_time))
            yield caption
            yield old

    monkeypatch.setattr("app.services.telegram_client.TelegramClient", lambda *args, **kwargs: Client())
    tg = PersonalTelegram(Config("test", 1, "test", 23), Repository(tmp_path / "test.sqlite"))

    async def scenario():
        messages = [message async for message in tg.messages(channel, "Oud-Wood", now - timedelta(days=7))]
        assert messages == [caption]
        assert calls == [(channel.peer, "oud wood", 1), (channel.peer, "wood", 1)]
        assert channel.link(caption.id) == "https://t.me/public_market/1"

    asyncio.run(scenario())


def test_status_handles_retry_after_and_unchanged_message():
    from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
    from aiogram.methods import EditMessageText

    from app.services.progress_service import Status

    async def scenario():
        method = EditMessageText(chat_id=23, message_id=1, text="status")
        message = SimpleNamespace(edit_text=AsyncMock(side_effect=[
            TelegramRetryAfter(method=method, message="retry later", retry_after=0),
            TelegramBadRequest(method=method, message="message is not modified"),
        ]))
        await Status(message).edit("status", final=True)
        assert message.edit_text.await_count == 2

    asyncio.run(scenario())
