import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.workers.jobs import send_latest_candidates, handle_search_job, handle_job, job_worker_loop
from app.db.models import Job, Post
from app.db.session import SessionLocal
from app.config import Config

@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session

@pytest.fixture
def config():
    return Config(bot_token="", admin_ids={1}, database_url="sqlite:///:memory:", log_dir="")

@pytest.mark.asyncio
async def test_send_latest_candidates(db, config):
    db.query(Post).delete()
    db.add(Post(id=1, channel_id=1, message_id=1, hashtag="h", text="t", text_hash="h1", status="candidate"))
    db.commit()

    bot_mock = AsyncMock()

    with patch("app.bot.keyboards.candidate_actions", return_value="markup"):
        with patch("app.bot.render.post_text", return_value="text"):
            await send_latest_candidates(bot_mock, config)
            bot_mock.send_message.assert_awaited_once_with(1, "text", reply_markup="markup")


@pytest.mark.asyncio
async def test_send_latest_candidates_after_post_id(db, config):
    db.query(Post).delete()
    db.add(Post(id=1, channel_id=1, message_id=1, hashtag="h", text="old", text_hash="h1", status="candidate"))
    db.add(Post(id=2, channel_id=1, message_id=2, hashtag="h", text="new", text_hash="h2", status="candidate"))
    db.commit()

    bot_mock = AsyncMock()

    with patch("app.bot.keyboards.candidate_actions", return_value="markup"):
        with patch("app.bot.render.post_text", return_value="text"):
            await send_latest_candidates(bot_mock, config, after_post_id=1)
            bot_mock.send_message.assert_awaited_once_with(1, "text", reply_markup="markup")


@pytest.mark.asyncio
async def test_handle_search_job(config):
    bot_mock = AsyncMock()
    job = Job(id=1, kind="search")

    res_mock = {"found": 1, "saved": 1, "candidates": 1, "account_events": ["err"]}
    with patch("app.workers.jobs.run_global_search", return_value=res_mock, new_callable=AsyncMock) as run_mock, \
         patch("app.workers.jobs.alert_admins", new_callable=AsyncMock) as alert_mock, \
         patch("app.workers.jobs.send_latest_candidates", new_callable=AsyncMock) as send_mock:

        await handle_search_job(bot_mock, config, job)

        run_mock.assert_awaited_once()
        assert alert_mock.call_count == 3
        assert send_mock.await_args.kwargs["after_post_id"] >= 0

@pytest.mark.asyncio
async def test_handle_job(config):
    bot_mock = AsyncMock()

    with patch("app.workers.jobs.handle_search_job", new_callable=AsyncMock) as h_mock:
        await handle_job(bot_mock, config, Job(kind="search"))
        h_mock.assert_awaited_once()

    with pytest.raises(RuntimeError, match="пока не подключен"):
        await handle_job(bot_mock, config, Job(kind="ai_analysis"))

    with pytest.raises(RuntimeError, match="Неизвестный job kind"):
        await handle_job(bot_mock, config, Job(kind="unknown"))

@pytest.mark.asyncio
async def test_job_worker_loop_success(db, config, monkeypatch):
    import datetime
    db.query(Job).delete()
    job = Job(id=1, kind="search", status="pending", run_after=datetime.datetime.utcnow() - datetime.timedelta(days=1))
    db.add(job)
    db.commit()

    bot_mock = AsyncMock()

    async def fake_handle(*args):
        pass
    monkeypatch.setattr("app.workers.jobs.handle_job", fake_handle)

    async def fake_sleep(seconds):
        raise asyncio.CancelledError()
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with patch("app.workers.jobs.requeue_stale_jobs"), \
         patch("app.workers.jobs.claim_next_job", side_effect=[job, None]):
        with pytest.raises(asyncio.CancelledError):
            await job_worker_loop(bot_mock, config)

    db.expire_all()
    j = db.get(Job, job.id)
    assert j.status == "done"

@pytest.mark.asyncio
async def test_job_worker_loop_failure(db, config, monkeypatch):
    import datetime
    db.query(Job).delete()
    job = Job(id=2, kind="search", status="pending", attempts=3, max_attempts=3, run_after=datetime.datetime.utcnow() - datetime.timedelta(days=1))
    db.add(job)
    db.commit()

    bot_mock = AsyncMock()

    async def fake_handle(*args):
        raise RuntimeError("failed")
    monkeypatch.setattr("app.workers.jobs.handle_job", fake_handle)

    async def fake_sleep(seconds):
        raise asyncio.CancelledError()
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with patch("app.workers.jobs.critical_alert", new_callable=AsyncMock) as alert_mock, \
         patch("app.workers.jobs.claim_next_job", side_effect=[job, None]):
        with pytest.raises(asyncio.CancelledError):
            await job_worker_loop(bot_mock, config)
        alert_mock.assert_awaited_once()

    db.expire_all()
    j = db.get(Job, job.id)
    assert j.status == "failed"
