import pytest
from unittest.mock import AsyncMock, MagicMock

from app.bot.handlers.posts import post_status, posts_menu, render_posts_page, folder_filter
from app.db.models import Admin, BlacklistedChannel, Post, Source
from app.db.session import SessionLocal


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def admin(db):
    db.query(Admin).delete()
    admin = Admin(telegram_id=1, is_active=True)
    db.add(admin)
    db.commit()
    return admin


@pytest.fixture
def cb():
    callback = AsyncMock()
    callback.from_user = MagicMock(id=1)
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_posts_menu_opens_folders(db, admin, cb):
    db.query(Post).delete()
    db.add(Post(channel_id=1, message_id=1, hashtag="#t", text="t", text_hash="h1", status="candidate"))
    db.add(Post(channel_id=2, message_id=1, hashtag="#t", text="t", text_hash="h2", status="skipped"))
    db.commit()

    await posts_menu(cb)

    text = cb.message.edit_text.await_args.args[0]
    markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
    buttons = [button.text for row in markup.inline_keyboard for button in row]
    assert "Выберите папку" in text
    assert "Кандидаты (1)" in buttons
    assert "Архив (Все) (1)" in buttons
    assert "Архив (Плохие источники) (0)" in buttons
    assert "Архив (Устаревшие) (0)" in buttons


@pytest.mark.asyncio
async def test_expired_folder_list_shows_expired_status(db, admin, cb):
    db.query(Post).delete()
    db.add(Post(id=1, channel_id=1, message_id=1, hashtag="#t", text="t", text_hash="h1", status="skipped", label="expired"))
    db.commit()

    await render_posts_page(cb, "expired", 1)

    text = cb.message.edit_text.await_args.args[0]
    assert "#1 <code>expired</code>" in text
    assert "<code>skipped</code>" not in text


@pytest.mark.asyncio
async def test_bad_source_marks_source_history(db, admin, cb):
    db.query(BlacklistedChannel).delete()
    db.query(Source).delete()
    db.query(Post).delete()
    db.add(Post(id=1, channel_id=100, channel_name="bad", message_id=1, hashtag="#t", text="a", text_hash="h1", status="candidate"))
    db.add(Post(id=2, channel_id=100, channel_name="bad", message_id=2, hashtag="#t", text="b", text_hash="h2", status="candidate"))
    db.add(Post(id=3, channel_id=200, channel_name="ok", message_id=1, hashtag="#t", text="c", text_hash="h3", status="candidate"))
    db.commit()

    cb.data = "post:1:bad_source"
    await post_status(cb)

    db.expire_all()
    assert db.get(Post, 1).status == "rejected"
    assert db.get(Post, 1).label == "bad_source"
    assert db.get(Post, 2).status == "rejected"
    assert db.get(Post, 3).status == "candidate"
    assert db.query(BlacklistedChannel).filter_by(channel_id=100).first() is not None
    source = db.query(Source).filter_by(channel_id=100).first()
    assert source is not None
    assert source.is_blacklisted is True
    assert source.bad_source_score == 1
    cb.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_moves_one_post_to_archive(db, admin, cb):
    db.query(Post).delete()
    db.add(Post(id=1, channel_id=100, message_id=1, hashtag="#t", text="a", text_hash="h1", status="candidate"))
    db.add(Post(id=2, channel_id=100, message_id=2, hashtag="#t", text="b", text_hash="h2", status="candidate"))
    db.commit()

    cb.data = "post:1:skipped"
    await post_status(cb)

    db.expire_all()
    assert db.get(Post, 1).status == "skipped"
    assert db.get(Post, 1).label == "neutral"
    assert db.get(Post, 2).status == "candidate"


@pytest.mark.asyncio
async def test_not_signal_rejects_one_post(db, admin, cb):
    db.query(Post).delete()
    db.add(Post(id=1, channel_id=100, message_id=1, hashtag="#t", text="a", text_hash="h1", status="candidate"))
    db.add(Post(id=2, channel_id=100, message_id=2, hashtag="#t", text="b", text_hash="h2", status="candidate"))
    db.commit()

    cb.data = "post:1:not_signal"
    await post_status(cb)

    db.expire_all()
    assert db.get(Post, 1).status == "rejected"
    assert db.get(Post, 1).label == "not_signal"
    assert db.get(Post, 2).status == "candidate"

def test_folder_filter_by_source_does_not_crash(db):
    db.query(Post).delete()
    db.add(Post(id=1, channel_id=123, message_id=1, hashtag="#t", text="a", text_hash="h1", status="candidate"))
    db.commit()
    
    q = folder_filter(db.query(Post), "candidate", {"source": "123"})
    assert q.count() == 1
