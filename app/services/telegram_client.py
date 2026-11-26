import asyncio
import re
import sys
from dataclasses import dataclass
from getpass import getpass

from telethon import TelegramClient, errors, functions, types

from app.config import DATA, ConfigurationError
from app.utils.text import normalize


class RateLimited(errors.FloodWaitError):
    pass


class SessionExpired(Exception):
    pass


@dataclass(frozen=True)
class Channel:
    id: int
    title: str
    username: str | None
    peer: types.InputPeerChannel

    def link(self, message_id):
        path = self.username or f"c/{self.id}"
        return f"https://t.me/{path}/{message_id}"


def as_channel(entity):
    return Channel(entity.id, entity.title, entity.username,
                   types.InputPeerChannel(entity.id, entity.access_hash))


class PersonalTelegram:
    def __init__(self, config, repo):
        self.client = TelegramClient(
            str(DATA / "account"), config.api_id, config.api_hash,
            flood_sleep_threshold=0, request_retries=0, receive_updates=False,
        )
        self.owner_id = config.owner_id
        self.subscriptions = None
        self.extra = {item: Channel(item, title, username, types.InputPeerChannel(item, access_hash))
                      for item, title, username, access_hash in repo.added_channels()}
        self.lock = asyncio.Lock()
        self.blocked_until = 0.0

    async def login(self):
        await self.client.connect()
        if not await self.client.is_user_authorized():
            if not sys.stdin.isatty():
                raise ConfigurationError("Для первого входа запустите бота в локальном терминале.")
            phone = input("Номер телефона Telegram в международном формате: ").strip()
            await self.client.send_code_request(phone)
            try:
                await self.client.sign_in(phone=phone, code=getpass("Код Telegram: ").strip())
            except errors.SessionPasswordNeededError:
                await self.client.sign_in(password=getpass("Пароль двухфакторной авторизации: "))
        user = await self.client.get_me()
        if not user or user.bot or user.id != self.owner_id:
            raise ConfigurationError("OWNER_ID должен совпадать с ID личного аккаунта Telegram.")

    async def channels(self, *, refresh=False):
        if self.subscriptions is None or refresh:
            async with self.lock:
                if self.subscriptions is None or refresh:
                    self.check_limit()
                    found = {}
                    try:
                        async for dialog in self.client.iter_dialogs():
                            entity = dialog.entity
                            if isinstance(entity, types.Channel) and entity.broadcast and not entity.left:
                                found[entity.id] = as_channel(entity)
                    except errors.FloodWaitError as error:
                        self.note_limit(error.seconds)
                        raise
                    except (errors.UnauthorizedError, errors.AuthKeyError):
                        raise SessionExpired from None
                    self.subscriptions = found
        return sorted((self.extra | self.subscriptions).values(), key=lambda item: item.title.casefold())

    def check_limit(self):
        remaining = self.blocked_until - asyncio.get_running_loop().time()
        if remaining > 0:
            raise RateLimited(request=None, capture=int(remaining) + 1)

    def note_limit(self, seconds):
        self.blocked_until = max(self.blocked_until, asyncio.get_running_loop().time() + seconds)

    async def add(self, raw):
        self.check_limit()
        public = re.fullmatch(r"(?:(?:https?://)?(?:t\.me|telegram\.me)/(?:s/)?|@)?([A-Za-z][A-Za-z0-9_]{3,31})/?", raw)
        invite = re.fullmatch(r"https?://(?:t\.me|telegram\.me)/(?:\+|joinchat/)([\w-]+)/?", raw)
        private = re.fullmatch(r"https?://t\.me/c/(\d+)(?:/\d+)?/?", raw)
        try:
            if private:
                return next((item for item in await self.channels() if item.id == int(private[1])), None)
            if invite:
                result = await self.client(functions.messages.CheckChatInviteRequest(invite[1]))
                entity = result.chat if isinstance(result, types.ChatInviteAlready) else None
            elif public and public[1].casefold() not in {"me", "self"}:
                result = await self.client(functions.contacts.ResolveUsernameRequest(public[1]))
                entity = next((chat for chat in result.chats if chat.id == getattr(result.peer, "channel_id", None)), None)
            else:
                return None
        except errors.FloodWaitError as error:
            self.note_limit(error.seconds)
            raise
        except (errors.UnauthorizedError, errors.AuthKeyError):
            raise SessionExpired from None
        except (errors.UsernameInvalidError, errors.UsernameNotOccupiedError, errors.InviteHashInvalidError,
                errors.InviteHashExpiredError, errors.ChannelPrivateError):
            return None
        if isinstance(entity, types.Channel) and entity.broadcast:
            channel = as_channel(entity)
            self.extra[channel.id] = channel
            return channel
        return None

    async def messages(self, channel, query, cutoff):
        terms = normalize(query).split()
        # One distinctive word plus the phrase when they differ. Local parsing
        # checks exact normalized names before anything is returned to the owner.
        phrase = " ".join(terms)
        keyword = max(terms, key=len)
        seen = set()
        for term in dict.fromkeys((phrase, keyword)):
            self.check_limit()
            async for message in self.client.iter_messages(channel.peer, search=term, wait_time=1):
                if cutoff and message.date < cutoff:
                    break
                if message.id not in seen:
                    seen.add(message.id)
                    if message.message:
                        yield message
