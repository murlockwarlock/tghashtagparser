from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Job
from app.services.jobs import claim_next_job, enqueue_job, fail_job, finish_job


def test_job_lifecycle() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    job = enqueue_job(session, "search", created_by_admin_id=123)
    session.commit()

    claimed = claim_next_job(session)
    assert claimed.id == job.id
    assert claimed.status == "running"
    assert claimed.attempts == 1

    finish_job(session, claimed)
    session.commit()

    done = session.get(Job, job.id)
    assert done.status == "done"


def test_job_retry_then_fail() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    job = enqueue_job(session, "search", max_attempts=1)
    session.commit()

    claimed = claim_next_job(session)
    fail_job(session, claimed, "boom")
    session.commit()

    failed = session.get(Job, job.id)
    assert failed.status == "failed"
    assert failed.last_error == "boom"

def test_job_duplicate_search() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    job1 = enqueue_job(session, "search")
    session.commit()

    job2 = enqueue_job(session, "search")
    session.commit()

    assert job1.id == job2.id
    
    # Check that another type of job can be duplicated
    job3 = enqueue_job(session, "other")
    session.commit()
    job4 = enqueue_job(session, "other")
    session.commit()
    
    assert job3.id != job4.id
