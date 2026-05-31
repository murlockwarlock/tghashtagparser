import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.bot.handlers.tags import (
    add_tag_cmd,
    add_tag_start,
    add_tag_value,
    disable_tag,
    list_tags_cmd,
    remove_tag_cmd,
    remove_tag_start,
    remove_tag_value,
    tags_menu,
    tags_menu_text,
)
from app.db.models import Admin, Hashtag
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
    m.text = ""
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
async def test_tags_menu(db, admin, cb, state):
    db.query(Hashtag).delete()
    db.add(Hashtag(tag="#one", is_active=True))
    db.add(Hashtag(tag="#two", is_active=True))
    db.add(Hashtag(tag="#three", is_active=True))
    db.commit()

    await tags_menu(cb, state)

    state.clear.assert_awaited_once()
    cb.message.edit_text.assert_awaited_once()
    markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
    first_row = markup.inline_keyboard[0]
    assert len(first_row) == 2
    assert first_row[0].text.startswith("🔴 #")
    assert "Убрать" not in first_row[0].text

@pytest.mark.asyncio
async def test_list_tags_cmd(db, admin, msg):
    await list_tags_cmd(msg)
    msg.answer.assert_awaited_once()

@pytest.mark.asyncio
async def test_add_tag_start(cb, state):
    await add_tag_start(cb, state)
    state.set_state.assert_awaited_once()
    cb.message.edit_text.assert_awaited_once()

@pytest.mark.asyncio
async def test_add_tag_cmd(db, admin, msg):
    db.query(Hashtag).delete()
    db.commit()

    msg.text = "/add_tag #test"
    await add_tag_cmd(msg)

    tag = db.query(Hashtag).first()
    assert tag is not None
    assert tag.tag == "#TEST"
    msg.answer.assert_awaited_once()
    assert "✅" in msg.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_add_tag_cmd_invalid(db, admin, msg):
    msg.text = "/add_tag"
    await add_tag_cmd(msg)
    msg.answer.assert_awaited_once()
    assert "Формат" in msg.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_add_tag_value(db, admin, msg, state):
    db.query(Hashtag).delete()
    db.commit()

    msg.text = "#test"
    await add_tag_value(msg, state)

    tag = db.query(Hashtag).first()
    assert tag is not None
    assert tag.tag == "#TEST"
    msg.answer.assert_awaited_once()
    state.clear.assert_awaited_once()

@pytest.mark.asyncio
async def test_remove_tag_start(cb, state):
    await remove_tag_start(cb, state)
    state.set_state.assert_awaited_once()
    cb.message.edit_text.assert_awaited_once()

@pytest.mark.asyncio
async def test_remove_tag_cmd(db, admin, msg):
    db.query(Hashtag).delete()
    db.add(Hashtag(tag="#test", is_active=True))
    db.commit()

    msg.text = "/remove_tag #test"
    await remove_tag_cmd(msg)

    tag = db.query(Hashtag).first()
    assert tag.is_active is False
    msg.answer.assert_awaited_once()
    assert "#test" not in msg.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_remove_tag_value(db, admin, msg, state):
    db.query(Hashtag).delete()
    db.add(Hashtag(tag="#test", is_active=True))
    db.commit()

    msg.text = "#test"
    await remove_tag_value(msg, state)

    tag = db.query(Hashtag).first()
    assert tag.is_active is False
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_disable_tag_button_hides_tag(db, admin, cb):
    db.query(Hashtag).delete()
    tag = Hashtag(tag="#test", is_active=True)
    db.add(tag)
    db.commit()

    cb.data = f"tag:disable:{tag.id}"
    await disable_tag(cb)

    db.expire_all()
    assert db.get(Hashtag, tag.id).is_active is False
    assert "#test" not in tags_menu_text(db)
    cb.message.edit_text.assert_awaited_once()
