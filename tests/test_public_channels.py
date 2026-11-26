import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.config import Config
from app.database.repository import Repository
from app.services.public_channels import ChannelSources, parse_preview
from app.services.search_service import Progress, SearchService

HTML = """
<div class="tgme_channel_info_header_title"><span>Perfume Store</span></div>
<div class="tgme_widget_message" data-post="perfumes/15">
  <div class="tgme_widget_message_text">Oud <b>Wood</b><br>10 мл — 1200 ₽</div>
  <a class="tgme_widget_message_date"><time datetime="2026-11-25T16:00:00+03:00"></time></a>
</div>
"""


def test_preview_caption_and_cursor():
    anchor = '<a class="js-messages_more" data-before="15"></a>'
    title, posts, cursor = parse_preview(HTML + anchor, "perfumes")
    assert title == "Perfume Store" and cursor == 15
    assert posts[0].message == "Oud Wood\n10 мл — 1200 ₽"
    assert posts[0].date == datetime(2026, 11, 25, 13, tzinfo=timezone.utc)


def test_save_and_search_without_personal_account(tmp_path):
    repo = Repository(tmp_path / "bot.sqlite")

    async def scenario():
        sources = ChannelSources(repo, None)
        sources.preview = AsyncMock(return_value=parse_preview(HTML, "perfumes"))
        channel = await sources.add("https://t.me/s/Perfumes?before=20")
        assert channel.username == "perfumes"
        assert (await sources.add("@perfumes")).id == channel.id
        assert await sources.add("https://example.com/perfumes") is None
        restarted = ChannelSources(Repository(repo.path), None)
        restarted.preview = sources.preview
        assert await restarted.channels() == [channel]
        result = await SearchService(restarted, repo).run("Oud Wood", 10, 0, Progress())
        assert not result.partial and len(result.offers) == 1
        assert result.offers[0].price == 1200
        assert result.offers[0].link == "https://t.me/perfumes/15"

    asyncio.run(scenario())


def test_public_only_config(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("BOT_TOKEN=123:abcdefghijklmnopqrstuvwxyz\nOWNER_ID=123\nAPI_ID=\nAPI_HASH=\n")
    monkeypatch.setattr("app.config.ENV", env)
    for key in ("BOT_TOKEN", "OWNER_ID", "API_ID", "API_HASH"):
        monkeypatch.delenv(key, raising=False)
    config = Config.load()
    assert config.owner_id == 123 and config.api_id is None and not config.api_hash
