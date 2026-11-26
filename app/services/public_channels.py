import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp
from bs4 import BeautifulSoup

from app.services.telegram_client import RateLimited

PUBLIC_LINK = re.compile(
    r"(?:(?:https?://)?(?:t\.me|telegram\.me)/(?:s/)?|@)?"
    r"([a-z][a-z0-9_]{3,31})(?:/\d+)?/?(?:\?[^\s#]*)?", re.I | re.ASCII,
)
MAX_PAGES = 10


class PreviewLimit(Exception):
    pass


@dataclass(frozen=True)
class PublicChannel:
    id: int
    username: str
    title: str

    def link(self, message_id):
        return f"https://t.me/{self.username}/{message_id}"


@dataclass(frozen=True)
class PublicPost:
    id: int
    date: datetime
    message: str


def parse_preview(html, username):
    page = BeautifulSoup(html, "html.parser")
    title = page.select_one(".tgme_channel_info_header_title")
    posts = []
    for post in page.select(".tgme_widget_message[data-post]"):
        match = re.fullmatch(rf"{re.escape(username)}/([0-9]+)", post["data-post"], re.I)
        timestamp = post.select_one(".tgme_widget_message_date time[datetime]")
        if not match or not timestamp:
            continue
        try:
            date = datetime.fromisoformat(timestamp["datetime"])
        except ValueError:
            continue
        if date.tzinfo is None:
            continue
        caption = post.select_one(".tgme_widget_message_text")
        if caption is not None:
            for linebreak in caption.find_all("br"):
                linebreak.replace_with("\n")
        posts.append(PublicPost(int(match[1]), date.astimezone(timezone.utc),
                                caption.get_text() if caption is not None else ""))
    older = page.select_one(".js-messages_more[data-before]")
    cursor = older["data-before"] if older else ""
    return title.get_text(strip=True) if title else "", posts, int(cursor) if re.fullmatch(r"[0-9]{1,15}", cursor) else None


class ChannelSources:
    def __init__(self, repo, http, personal=None):
        self.repo = repo
        self.http = http
        self.personal = personal
        self.web_retry_at = 0.0

    async def channels(self, *, refresh=False):
        saved = [PublicChannel(*row) for row in self.repo.public_channels()]
        usernames = {channel.username for channel in saved}
        subscriptions = await self.personal.channels(refresh=refresh) if self.personal else []
        return sorted(saved + [channel for channel in subscriptions
                               if (channel.username or "").lower() not in usernames],
                      key=lambda channel: channel.title.casefold())

    async def add(self, raw):
        match = PUBLIC_LINK.fullmatch(raw)
        if match:
            username = match[1].lower()
            title, _, _ = await self.preview(username)
            if title:
                return PublicChannel(*self.repo.add_public_channel(username, title))
        if self.personal:
            channel = await self.personal.add(raw)
            if channel:
                self.repo.add_channel(channel)
            return channel
        return None

    async def preview(self, username, before=None):
        loop = asyncio.get_running_loop()
        if self.web_retry_at > loop.time():
            raise RateLimited(request=None, capture=int(self.web_retry_at - loop.time()) + 1)
        try:
            async with self.http.get(f"https://t.me/s/{username}",
                                     params={"before": before} if before else None,
                                     allow_redirects=False) as response:
                if response.status == 429:
                    retry = response.headers.get("Retry-After", "")
                    seconds = int(retry) if retry.isascii() and retry.isdecimal() and len(retry) <= 9 else 60
                    self.web_retry_at = loop.time() + max(1, seconds)
                    raise RateLimited(request=None, capture=max(1, seconds))
                if response.status in {301, 302, 303, 307, 308, 404, 410}:
                    return "", [], None
                response.raise_for_status()
                return parse_preview(await response.text(), username)
        except aiohttp.ClientError as error:
            raise OSError("Не удалось прочитать публичное превью Telegram.") from error

    def note_limit(self, seconds):
        if self.personal:
            self.personal.note_limit(seconds)

    async def messages(self, channel, query, cutoff):
        if not isinstance(channel, PublicChannel):
            async for post in self.personal.messages(channel, query, cutoff):
                yield post
            return

        before = None
        seen = set()
        for _ in range(MAX_PAGES):
            title, posts, older = await self.preview(channel.username, before)
            if not title:
                raise OSError("Публичное превью канала недоступно.")
            for post in reversed(posts):
                if post.id not in seen and post.message and (cutoff is None or post.date >= cutoff):
                    yield post
                seen.add(post.id)
            if not older or (before is not None and older >= before):
                return
            if cutoff and posts and min(post.date for post in posts) < cutoff:
                return
            before = older
            await asyncio.sleep(0.3)
        raise PreviewLimit
