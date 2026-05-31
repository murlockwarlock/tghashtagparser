import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from hydrogram.errors import FloodWait, InternalServerError, Unauthorized, Forbidden, BadRequest, RPCError
from app.telegram_client.search import (
    build_client,
    get_recent_hours,
    invoke_recent_search,
    mark_account,
    wait_flood,
    iter_global_messages,
    message_in_window,
    search_with_account,
    search_with_account_proxy,
    search_global_request,
    search_posts_request,
    run_global_search,
    AccountSearchResult
)
from app.db.models import Hashtag, Keyword, SearchRun, TelegramAccount
from app.services.settings import set_setting
from app.db.session import SessionLocal

@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session

def test_build_client():
    account = TelegramAccount(title="test", api_id=1, api_hash="enc:hash", session_string="enc:session")
    client = build_client(account)
    assert client.name == "test"
    assert client.api_id == 1

def test_mark_account(db):
    account = TelegramAccount(title="test", api_id=1, api_hash="h", phone="p", session_string="s", is_active=True)
    db.add(account)
    db.commit()

    mark_account(account.id, "banned", "err", False)
    db.expire_all()
    acc = db.get(TelegramAccount, account.id)
    assert acc.status == "banned"
    assert acc.is_active is False
    assert acc.last_error == "err"

@pytest.mark.asyncio
async def test_wait_flood_short(monkeypatch):
    sleep_mock = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep_mock)

    exc = FloodWait("wait")
    exc.value = 10
    res = await wait_flood(exc, "#BTC")

    assert res is True
    sleep_mock.assert_awaited_once_with(10)

@pytest.mark.asyncio
async def test_wait_flood_too_long():
    exc = FloodWait("wait")
    exc.value = 999999
    res = await wait_flood(exc, "#BTC")
    assert res is False

@pytest.mark.asyncio
async def test_iter_global_messages_success():
    class FakeClient:
        async def search_global(self, tag, limit):
            yield 1
            yield 2

    items = [x async for x in iter_global_messages(FakeClient(), "tag", 10)]
    assert items == [1, 2]

@pytest.mark.asyncio
async def test_iter_global_messages_internal_error(monkeypatch):
    sleep_mock = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep_mock)

    class FakeClient:
        def __init__(self):
            self.calls = 0
        async def search_global(self, tag, limit):
            self.calls += 1
            if self.calls < 3:
                raise InternalServerError("err")
            yield 1

    client = FakeClient()
    items = [x async for x in iter_global_messages(client, "tag", 10)]

    assert items == [1]
    assert sleep_mock.call_count == 2


def test_search_global_request_uses_date_window():
    now = datetime(2026, 5, 27, 12, 0, 0)
    min_date = now - timedelta(days=3)
    request = search_global_request(
        "#BTC",
        20,
        min_date,
        now,
        0,
        MagicMock(),
        0,
    )

    assert request.q == "#BTC"
    assert request.min_date == int(min_date.timestamp())
    assert request.max_date == int(now.timestamp())
    assert request.limit == 20
    if hasattr(request, "broadcasts_only"):
        assert request.broadcasts_only is True


def test_search_posts_request_strips_hash_symbol():
    request = search_posts_request("#BTCUSDT", 20, 0, MagicMock(), 0)

    assert request.hashtag == "BTCUSDT"
    assert request.limit == 20


@pytest.mark.asyncio
async def test_invoke_recent_search_falls_back_to_search_global():
    now = datetime(2026, 5, 27, 12, 0, 0)
    client = AsyncMock()
    client.invoke.side_effect = [BadRequest("bad"), "ok"]

    response = await invoke_recent_search(
        client,
        "#BTC",
        20,
        now - timedelta(days=3),
        now,
        0,
        MagicMock(),
        0,
    )

    first_request = client.invoke.await_args_list[0].args[0]
    second_request = client.invoke.await_args_list[1].args[0]
    assert response == "ok"
    assert first_request.__class__.__name__ == "SearchPosts"
    assert second_request.__class__.__name__ == "SearchGlobal"


def test_message_in_window_handles_timezone_aware_dates():
    now = datetime(2026, 5, 27, 12, 0, 0)
    message = MagicMock(date=now.replace(tzinfo=timezone.utc))

    assert message_in_window(message, now - timedelta(hours=1), now + timedelta(hours=1))
    assert not message_in_window(message, now + timedelta(hours=1), now + timedelta(hours=2))


def test_get_recent_hours_prefers_hour_setting(db):
    set_setting(db, "search_recent_days", "3", "int")
    set_setting(db, "search_recent_hours", "2", "int")
    db.commit()

    assert get_recent_hours(db) == 2


@pytest.mark.asyncio
async def test_search_with_account_proxy_success(db):
    db.query(TelegramAccount).delete()
    db.query(Hashtag).delete()
    db.query(Keyword).delete()
    account = TelegramAccount(title="test_proxy_success", api_id=2, api_hash="h", phone="p2", session_string="s", is_active=True)
    tag = Hashtag(tag="#btc_proxy", is_active=True)
    db.add(account)
    db.add(tag)
    db.add(Keyword(word="long", kind="direction", is_active=True))
    db.add(Keyword(word="entry", kind="entry", is_active=True))
    db.add(Keyword(word="target", kind="target", is_active=True))
    db.commit()

    class FakeMessage:
        def __init__(self, id):
            self.id = id
            self.text = f"long btc entry target {id} word1 word2 word3 #btc_proxy"
            self.caption = None
            self.date = None
            self.chat = MagicMock(id=1, title="c", username="u")

    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock

    async def mock_iter(*args, **kwargs):
        yield FakeMessage(1)
        yield FakeMessage(2)

    with patch("app.telegram_client.search.build_client", return_value=client_mock), \
         patch("app.telegram_client.search.iter_recent_global_messages", new=mock_iter), \
         patch("app.telegram_client.search.asyncio.sleep", new_callable=AsyncMock):

        res = await search_with_account_proxy(account, None, [tag], 2, 0, 1)

        assert res.found == 2
        assert res.saved == 2
        assert res.candidates == 2

@pytest.mark.asyncio
async def test_search_with_account_proxy_flood_wait(db):
    db.query(TelegramAccount).delete()
    db.query(Hashtag).delete()
    account = TelegramAccount(title="test_flood", api_id=3, api_hash="h", phone="p3", session_string="s", is_active=True)
    tag = Hashtag(tag="#btc_flood", is_active=True)
    db.add(account)
    db.add(tag)
    db.commit()

    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock

    async def mock_iter(*args, **kwargs):
        exc = FloodWait("wait")
        exc.value = 999999
        raise exc
        yield 1

    with patch("app.telegram_client.search.build_client", return_value=client_mock), \
         patch("app.telegram_client.search.iter_recent_global_messages", new=mock_iter):

        res = await search_with_account_proxy(account, None, [tag], 2, 0, 1)

        assert res.rate_limited is True

        db.expire_all()
        acc = db.get(TelegramAccount, account.id)
        assert acc.status == "rate_limited"
        assert acc.is_active is True

@pytest.mark.asyncio
async def test_run_global_search_no_accounts(db):
    db.query(TelegramAccount).delete()
    db.commit()
    with pytest.raises(RuntimeError, match="Нет активного TG аккаунта"):
        await run_global_search()

@pytest.mark.asyncio
async def test_run_global_search_success(db):
    db.query(TelegramAccount).delete()
    db.query(Hashtag).delete()
    db.add(TelegramAccount(title="test", api_id=1, api_hash="h", phone="p", session_string="s", is_active=True))
    db.add(Hashtag(tag="#btc", is_active=True))
    db.commit()

    res_mock = AccountSearchResult(found=5, saved=2, candidates=1, proxy_events=["e1"])
    with patch("app.telegram_client.search.search_with_account", return_value=res_mock):
        res = await run_global_search()

        assert res["found"] == 5
        assert res["saved"] == 2
        assert res["candidates"] == 1
        assert res["account_events"] == ["test: proxy fallback e1"]

        run = db.query(SearchRun).order_by(SearchRun.id.desc()).first()
        assert run.status == "done"
        assert run.found_count == 5
