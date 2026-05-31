import pytest
from unittest.mock import AsyncMock, MagicMock
from app.bot.guards import is_admin, admin_message, admin_callback
from app.bot.keyboards import main_menu, back, pager, post_actions, kb
from app.bot.render import post_status_display, post_text, telegram_spoiler_html
from app.db.models import Admin, Post
from app.db.session import SessionLocal

@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session

def test_is_admin(db):
    db.query(Admin).delete()
    db.commit()
    assert is_admin(db, 1) is False

    db.add(Admin(telegram_id=1, is_active=True))
    db.add(Admin(telegram_id=2, is_active=False))
    db.commit()

    assert is_admin(db, 1) is True
    assert is_admin(db, 2) is False

@pytest.mark.asyncio
async def test_admin_message(db):
    db.query(Admin).delete()
    db.add(Admin(telegram_id=1, is_active=True))
    db.commit()

    msg_mock = AsyncMock()
    msg_mock.from_user = MagicMock(id=2)

    assert await admin_message(msg_mock, db) is False
    msg_mock.answer.assert_awaited_once_with("⛔ Нет доступа")

    msg_mock.from_user.id = 1
    assert await admin_message(msg_mock, db) is True

@pytest.mark.asyncio
async def test_admin_callback(db):
    db.query(Admin).delete()
    db.add(Admin(telegram_id=1, is_active=True))
    db.commit()

    cb_mock = AsyncMock()
    cb_mock.from_user = MagicMock(id=2)

    assert await admin_callback(cb_mock, db) is False
    cb_mock.answer.assert_awaited_once_with("⛔ Нет доступа", show_alert=True)

    cb_mock.from_user.id = 1
    assert await admin_callback(cb_mock, db) is True

def test_keyboards():
    assert len(main_menu().inline_keyboard) == 6
    assert len(back().inline_keyboard) == 1

    p = pager("test", 2, 3)
    assert len(p.inline_keyboard) == 2
    assert p.inline_keyboard[0][0].callback_data == "test:1"
    assert p.inline_keyboard[0][2].callback_data == "test:3"

    p2 = pager("test", 1, 1)
    assert p2.inline_keyboard[0][0].callback_data == "test:1"

    actions = post_actions(1).inline_keyboard
    assert len(actions) == 4
    assert all(button.text != "Spam" for row in actions for button in row)

def test_render():
    from datetime import datetime
    post = Post(id=1, status="candidate", channel_name="C", hashtag="#h", text="text", published_at=datetime(2020, 1, 1), post_link="link")
    text = post_text(post)
    assert "Пост #1" in text
    assert "Открыть пост" in text
    assert "text" in text


def test_render_expired_status_and_spoiler():
    post = Post(id=2, status="skipped", label="expired", channel_name="C", hashtag="#h", text="<spoiler>#long</spoiler>")
    text = post_text(post)

    assert post_status_display(post) == "expired"
    assert "Статус: <code>expired</code>" in text
    assert "<tg-spoiler>#long</tg-spoiler>" in text
    assert "&lt;spoiler&gt;" not in text


def test_telegram_spoiler_html_raw():
    assert telegram_spoiler_html("<spoiler>x</spoiler>") == "<tg-spoiler>x</tg-spoiler>"
