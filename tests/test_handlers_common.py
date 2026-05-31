import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from app.bot.handlers.common import start, status_cmd, menu, noop, stats_cmd, stats_cb, status_cb, health_full_cmd, run_search, run_search_cmd, blacklist_confirm
from app.db.models import Admin, Job, Source, BlacklistedChannel
from app.db.session import SessionLocal

@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session

@pytest.fixture
def admin(db):
    db.query(Admin).delete()
    a = Admin(telegram_id=1, is_active=True)
    db.add(a)
    db.commit()
    return a

@pytest.fixture
def msg():
    m = AsyncMock()
    m.from_user = MagicMock(id=1)
    return m

@pytest.fixture
def cb():
    c = AsyncMock()
    c.from_user = MagicMock(id=1)
    c.message = AsyncMock()
    return c

@pytest.fixture
def state():
    return AsyncMock()

@pytest.mark.asyncio
async def test_start(db, admin, msg, state):
    await start(msg, state)
    state.clear.assert_awaited_once()
    msg.answer.assert_awaited_once()
    assert "Админка" in msg.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_status_cmd(db, admin, msg):
    with patch("app.bot.handlers.common.status_text", return_value="st"):
        await status_cmd(msg)
        msg.answer.assert_awaited_once()
        assert msg.answer.call_args[0][0] == "st"

@pytest.mark.asyncio
async def test_menu(db, admin, cb, state):
    await menu(cb, state)
    state.clear.assert_awaited_once()
    cb.message.edit_text.assert_awaited_once()
    cb.answer.assert_awaited_once()

@pytest.mark.asyncio
async def test_noop(cb):
    await noop(cb)
    cb.answer.assert_awaited_once()

@pytest.mark.asyncio
async def test_stats_cmd(db, admin, msg):
    with patch("app.bot.handlers.common.stats_text", return_value="st"):
        await stats_cmd(msg)
        msg.answer.assert_awaited_once()

@pytest.mark.asyncio
async def test_stats_cb(db, admin, cb):
    with patch("app.bot.handlers.common.stats_text", return_value="st"):
        await stats_cb(cb)
        cb.message.edit_text.assert_awaited_once()

@pytest.mark.asyncio
async def test_status_cb(db, admin, cb):
    with patch("app.bot.handlers.common.status_text", return_value="st"):
        await status_cb(cb)
        cb.message.edit_text.assert_awaited_once()

@pytest.mark.asyncio
async def test_health_full_cmd(db, admin, msg):
    with patch("app.bot.handlers.common.health_full_text", return_value="st"):
        await health_full_cmd(msg)
        msg.answer.assert_awaited_once()

@pytest.mark.asyncio
async def test_run_search(db, admin, cb):
    db.query(Job).delete()
    db.commit()

    await run_search(cb)

    j = db.query(Job).first()
    assert j is not None
    assert j.kind == "search"
    cb.message.edit_text.assert_awaited_once()

@pytest.mark.asyncio
async def test_run_search_cmd(db, admin, msg):
    db.query(Job).delete()
    db.commit()

    await run_search_cmd(msg)

    j = db.query(Job).first()
    assert j is not None
    msg.answer.assert_awaited_once()

@pytest.mark.asyncio
async def test_blacklist_confirm_unblocks_and_removes(db, admin, cb):
    db.query(BlacklistedChannel).delete()
    db.query(Source).delete()
    db.commit()

    s = Source(channel_id=123, channel_name="test", is_blacklisted=True)
    db.add(s)
    db.add(BlacklistedChannel(channel_id=123, channel_name="test"))
    db.commit()

    cb.data = f"blacklist:confirm:{s.id}:1"

    with patch("app.bot.handlers.common.render_blacklist", new_callable=AsyncMock):
        await blacklist_confirm(cb)

    db.expire_all()
    s_db = db.get(Source, s.id)
    assert not s_db.is_blacklisted
    assert db.query(BlacklistedChannel).filter_by(channel_id=123).first() is None

@pytest.mark.asyncio
async def test_unblock_source_cmd_unblocks_and_removes(db, admin, msg):
    from app.bot.handlers.common import unblock_source_cmd
    db.query(BlacklistedChannel).delete()
    db.query(Source).delete()
    db.commit()

    s = Source(channel_id=456, channel_name="spam", is_blacklisted=True, status="blacklisted", blacklisted_at=datetime.utcnow())
    db.add(s)
    db.add(BlacklistedChannel(channel_id=456, channel_name="spam"))
    db.commit()

    msg.text = f"/unblock_source {s.id}"
    await unblock_source_cmd(msg)

    db.expire_all()
    s_db = db.get(Source, s.id)
    assert not s_db.is_blacklisted
    assert s_db.status == "active"
    assert s_db.blacklisted_at is None
    assert db.query(BlacklistedChannel).filter_by(channel_id=456).first() is None
