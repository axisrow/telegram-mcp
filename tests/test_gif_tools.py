"""get_gif_search / send_gif talk to Telegram the way the apps do: via the @gif inline bot."""

import json
from datetime import datetime, timezone

import pytest
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession

from telegram_mcp.tools import media

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
GIF_BOT = types.User(id=900, first_name="GIF", username="gif", bot=True, access_hash=9)
FRIEND = types.User(id=101, first_name="Ivan", access_hash=1)
GIF_ID = 5390871221226233431


def gif_document(document_id=GIF_ID):
    return types.Document(
        id=document_id,
        access_hash=777,
        file_reference=b"ref",
        date=NOW,
        mime_type="video/mp4",
        size=1000,
        dc_id=2,
        attributes=[types.DocumentAttributeAnimated()],
    )


class GifServer(TelegramClient):
    def __init__(self, saved=()):
        super().__init__(StringSession(), 12345, "dummy_hash")
        self.requests = []
        self.saved = list(saved)

    async def __call__(self, request, ordered=False, flood_sleep_threshold=None):
        self.requests.append(request)
        if isinstance(request, functions.contacts.ResolveUsernameRequest):
            return types.contacts.ResolvedPeer(
                peer=types.PeerUser(GIF_BOT.id), chats=[], users=[GIF_BOT]
            )
        if isinstance(request, functions.messages.GetInlineBotResultsRequest):
            results = [
                types.BotInlineMediaResult(
                    id=f"r{i}",
                    type="gif",
                    send_message=types.BotInlineMessageMediaAuto(message=""),
                    document=gif_document(GIF_ID + i),
                )
                for i in range(3)
            ]
            return types.messages.BotResults(
                query_id=1, results=results, cache_time=0, users=[GIF_BOT]
            )
        if isinstance(request, functions.messages.GetSavedGifsRequest):
            return types.messages.SavedGifs(hash=1, gifs=self.saved)
        if isinstance(request, functions.messages.SendMediaRequest):
            return types.Updates(updates=[], users=[], chats=[], date=NOW, seq=0)
        raise AssertionError(f"unexpected request {type(request).__name__}")


@pytest.fixture
def server(monkeypatch):
    client = GifServer()

    async def resolve(chat_id, cl=None):
        return FRIEND

    async def connected(cl=None):
        return None

    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.setattr(media, "get_client", lambda account=None: client)
    monkeypatch.setattr(media, "resolve_entity", resolve)
    monkeypatch.setattr(media, "ensure_connected", connected)
    monkeypatch.setattr(media, "_known_gifs", {})
    return client


@pytest.mark.asyncio
async def test_gif_search_queries_the_gif_bot(server):
    result = json.loads(await media.get_gif_search(query="cat", limit=2))

    assert result == [GIF_ID, GIF_ID + 1]
    inline = [
        r for r in server.requests if isinstance(r, functions.messages.GetInlineBotResultsRequest)
    ]
    assert [r.query for r in inline] == ["cat"]


@pytest.mark.asyncio
async def test_send_gif_sends_a_gif_found_by_the_search(server):
    await media.get_gif_search(query="cat")

    result = await media.send_gif(chat_id=101, gif_id=GIF_ID)

    assert result == "GIF sent to chat 101."
    sent = [r for r in server.requests if isinstance(r, functions.messages.SendMediaRequest)]
    assert len(sent) == 1
    document = sent[0].media.id
    assert (document.id, document.access_hash, document.file_reference) == (GIF_ID, 777, b"ref")


@pytest.mark.asyncio
async def test_send_gif_finds_a_saved_gif(server):
    server.saved = [gif_document(42)]

    assert await media.send_gif(chat_id=101, gif_id=42) == "GIF sent to chat 101."


@pytest.mark.asyncio
async def test_send_gif_explains_an_unknown_id(server):
    result = await media.send_gif(chat_id=101, gif_id=1)

    assert "Run get_gif_search first" in result
    assert not [r for r in server.requests if isinstance(r, functions.messages.SendMediaRequest)]
