from app.db.init_db import init_db
from app.db.models import Admin, AiProvider, Exchange, Hashtag, Keyword, Setting
from app.db.session import SessionLocal

def test_init_db_creates_default_data():
    init_db()
    with SessionLocal() as db:
        admins = db.query(Admin).all()
        assert len(admins) >= 1
        assert any(a.telegram_id == 123 for a in admins)

        tags = db.query(Hashtag).all()
        assert len(tags) >= 10
        assert any(t.tag == "#BTC" for t in tags)

        include = db.query(Keyword).filter(Keyword.kind == "include").count()
        assert include >= 1

        exclude = db.query(Keyword).filter(Keyword.kind == "exclude").count()
        assert exclude >= 1

        direction = db.query(Keyword).filter(Keyword.kind == "direction").count()
        assert direction >= 16

        hard_spam = db.query(Keyword).filter(Keyword.kind == "hard_spam").count()
        assert hard_spam >= 9

        settings = db.query(Setting).all()
        assert len(settings) >= 8
        assert any(s.key == "search_recent_days" for s in settings)
        assert any(s.key == "search_recent_hours" for s in settings)

        openai = db.query(AiProvider).filter_by(provider="openai").first()
        assert openai is not None
        assert openai.selected_model == "gpt-4.1-mini"

        bingx = db.query(Exchange).filter_by(name="bingx").first()
        assert bingx is not None

def test_init_db_is_idempotent():
    init_db()
    with SessionLocal() as db:
        count_tags = db.query(Hashtag).count()
        count_settings = db.query(Setting).count()

    init_db()

    with SessionLocal() as db:
        assert db.query(Hashtag).count() == count_tags
        assert db.query(Setting).count() == count_settings
