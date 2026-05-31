from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.services.posts import save_post


def test_post_dedup_by_channel_message_and_text_hash() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    first, created = save_post(
        session,
        channel_id=1,
        channel_name="Test",
        username="test",
        message_id=10,
        published_at=datetime.utcnow(),
        hashtag="#BTC",
        text="BTC long",
        status="candidate",
    )
    session.commit()

    assert first is not None
    assert created is True

    duplicate, created = save_post(
        session,
        channel_id=1,
        channel_name="Test",
        username="test",
        message_id=10,
        published_at=datetime.utcnow(),
        hashtag="#BTC",
        text="BTC long",
        status="candidate",
    )

    assert duplicate is None
    assert created is False
