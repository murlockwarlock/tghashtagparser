from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Keyword
from app.services.filters import classify_text
from app.services.filters import keyword_matches


def test_filter_candidate_and_spam() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all(
        [
            Keyword(word="long", kind="direction", is_active=True),
            Keyword(word="entry", kind="entry", is_active=True),
            Keyword(word="target", kind="target", is_active=True),
            Keyword(word="airdrop", kind="hard_spam", is_active=True),
        ]
    )
    session.commit()

    assert classify_text(session, "BTC long entry target")[0] == "candidate"
    assert classify_text(session, "BTC airdrop claim")[0] == "filtered_out"


def test_filter_priority_and_result_report() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    session.add_all(
        [
            Keyword(word="long", kind="direction", is_active=True),
            Keyword(word="short", kind="direction", is_active=True),
            Keyword(word="buy", kind="direction", is_active=True),
            Keyword(word="entry", kind="entry", is_active=True),
            Keyword(word="target", kind="target", is_active=True),
            Keyword(word="stop loss", kind="stop_loss", is_active=True),
            Keyword(word="tp hit", kind="result_report", is_active=True),
            Keyword(word="profit booked", kind="result_report", is_active=True),
        ]
    )
    session.commit()

    high = classify_text(session, "BTC long entry 100 target 120 stop loss 95")
    medium = classify_text(session, "BTC short entry 100 target 90")
    low = classify_text(session, "BTC buy target 120")
    report = classify_text(session, "BTC long tp hit profit booked")

    assert high.status == "candidate"
    assert high.priority == "high"
    assert medium.priority == "medium"
    assert low.priority == "low"
    assert report.status == "filtered_out"
    assert report.reason.startswith("result_report")


def test_keyword_matching_uses_boundaries() -> None:
    assert keyword_matches("btc long entry", "long") is True
    assert keyword_matches("winter btc setup", "win") is False
    assert keyword_matches("stop loss hit", "stop loss") is True


def test_filter_custom_include_does_not_bypass() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([Keyword(word="signal", kind="include", is_active=True)])
    session.commit()

    res = classify_text(session, "VIP trading signal for BTC")
    assert res.status == "filtered_out"
