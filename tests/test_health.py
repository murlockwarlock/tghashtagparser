import pytest
from unittest.mock import AsyncMock, patch
from app.services.health import collect_health_warnings, health_full_text, check_account_session, check_all_accounts
from app.db.models import TelegramAccount, Hashtag, PublishChannel, SearchRun, Job
from app.db.session import SessionLocal
from hydrogram.errors import Unauthorized, RPCError

@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session

def test_collect_health_warnings(db):
    db.query(TelegramAccount).delete()
    db.query(Hashtag).delete()
    db.query(PublishChannel).delete()
    db.commit()

    warnings = collect_health_warnings()
    assert len(warnings) == 2
    assert "нет активного TG аккаунта" in warnings
    assert "нет активных хэштегов" in warnings

    db.add(TelegramAccount(title="T", api_id=1, api_hash="h", phone="p", session_string="s", is_active=True))
    db.add(Hashtag(tag="#t", is_active=True))
    db.commit()

    warnings = collect_health_warnings()
    assert len(warnings) == 0

def test_health_full_text(db):
    db.query(TelegramAccount).delete()
    db.query(SearchRun).delete()
    db.query(Job).delete()
    db.commit()

    text = health_full_text()
    assert "Пока нет аккаунтов" in text
    assert "Еще не запускали" in text
    assert "Пока пусто" in text

    db.add(TelegramAccount(title="T", api_id=1, api_hash="h", phone="p", session_string="s", is_active=True))
    db.add(SearchRun(status="done"))
    db.add(Job(kind="search", status="pending"))
    db.commit()

    text2 = health_full_text()
    assert "<code>T</code>" in text2
    assert "<code>done</code>" in text2
    assert "<code>search</code> <code>pending</code>" in text2

@pytest.mark.asyncio
async def test_check_account_session_ok():
    account = TelegramAccount(id=1, title="T", api_id=1, api_hash="enc:h", phone="p", session_string="enc:s")
    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock
    client_mock.get_me = AsyncMock()

    with patch("app.services.health.build_client", return_value=client_mock):
        ok, error = await check_account_session(account)
        assert ok is True
        assert error is None

@pytest.mark.asyncio
async def test_check_account_session_unauthorized():
    account = TelegramAccount(id=1, title="T", api_id=1, api_hash="enc:h", phone="p", session_string="enc:s")
    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock

    class FakeUnauthorized(Unauthorized):
        def __init__(self):
            super().__init__("Unauthorized")

    client_mock.get_me.side_effect = FakeUnauthorized()

    with patch("app.services.health.build_client", return_value=client_mock):
        ok, error = await check_account_session(account)
        assert ok is False
        assert "Unauthorized" in error

@pytest.mark.asyncio
async def test_check_all_accounts(db):
    db.query(TelegramAccount).delete()
    account = TelegramAccount(title="T", api_id=1, api_hash="enc:h", phone="p", session_string="enc:s", is_active=True)
    db.add(account)
    db.commit()

    bot_mock = AsyncMock()
    config_mock = AsyncMock()
    config_mock.admin_ids = {1}

    with patch("app.services.health.check_account_session", return_value=(False, "Unauthorized")):
        await check_all_accounts(bot_mock, config_mock)

    db.expire_all()
    acc = db.get(TelegramAccount, account.id)
    assert acc.status == "unauthorized"
    assert acc.is_active is False
