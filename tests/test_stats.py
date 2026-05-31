import pytest
from app.services.stats import status_text, stats_text
from app.db.models import Post, SearchRun, TelegramAccount
from app.db.session import SessionLocal

@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session

def test_status_text(db):
    db.query(TelegramAccount).delete()
    db.query(Post).delete()
    db.query(SearchRun).delete()
    db.commit()

    text = status_text(db)
    assert "TG Аккаунты (активны): <code>0 / 0</code>" in text
    assert "Всего постов в БД: <code>0</code>" in text
    assert "еще не запускали" in text

    db.add(TelegramAccount(title="Test", api_id=1, api_hash="h", phone="p", session_string="s", is_active=True))
    db.add(Post(channel_id=1, message_id=1, hashtag="h", text="t", text_hash="h", status="candidate"))
    db.add(SearchRun(status="done", found_count=5, saved_count=2))
    db.commit()

    text2 = status_text(db)
    assert "TG Аккаунты (активны): <code>1 / 1</code>" in text2
    assert "Всего постов в БД: <code>1</code>" in text2
    assert "Ожидают проверки: <code>1</code>" in text2
    assert "Найдено: 5" in text2
    assert "Новых сохранено: 2" in text2

def test_stats_text(db):
    db.query(Post).delete()
    db.commit()

    db.add(Post(channel_id=1, message_id=1, hashtag="h", text="t", text_hash="h1", status="candidate"))
    db.add(Post(channel_id=1, message_id=2, hashtag="h", text="t", text_hash="h2", status="rejected"))
    db.commit()

    text = stats_text(db)
    assert "🔥 <b>Кандидаты:</b> <code>1</code>" in text
    assert "├ Всего найдено: <code>5</code>" in text
