import asyncio
import logging

from aiogram import Bot
from sqlalchemy import case
from sqlalchemy import func

from app.config import Config
from app.db.models import Job, Post
from app.db.session import SessionLocal
from app.services.alerts import alert_admins, critical_alert
from app.services.jobs import JOB_AI_ANALYSIS, JOB_BINGX_SYNC, JOB_SEARCH
from app.services.jobs import claim_next_job, fail_job, finish_job, requeue_stale_jobs
from app.telegram_client.search import run_global_search

logger = logging.getLogger(__name__)


async def send_latest_candidates(
    bot: Bot,
    config: Config,
    after_post_id: int | None = None,
) -> None:
    from app.bot.keyboards import candidate_actions
    from app.bot.render import post_text
    from app.services.safe_bot import telegram_call

    with SessionLocal() as db:
        query = db.query(Post).filter(Post.status == "candidate")
        if after_post_id is not None:
            query = query.filter(Post.id > after_post_id)
        if not query.first():
            return
        priority_order = case(
            (Post.priority == "high", 1),
            (Post.priority == "medium", 2),
            (Post.priority == "low", 3),
            else_=4,
        )
        all_candidates = (
            db.query(Post)
            .filter(Post.status == "candidate")
            .order_by(priority_order.asc(), Post.id.desc())
        )
        post = all_candidates.first()
        total = all_candidates.count()
    if not post:
        return
    for admin_id in config.admin_ids:
        await telegram_call(
            f"send candidate queue to admin {admin_id}",
            lambda a=admin_id, p=post, t=total: bot.send_message(
                a,
                post_text(p),
                reply_markup=candidate_actions(p.id, 1, t),
            ),
        )


async def handle_search_job(bot: Bot, config: Config, job: Job) -> None:
    await alert_admins(bot, config, "🔎 Запустил фоновый поиск...")
    with SessionLocal() as db:
        last_post_id = db.query(func.max(Post.id)).scalar() or 0
    result = await run_global_search()
    for event in result.get("account_events", []):
        await alert_admins(bot, config, f"⚠️ TG аккаунт: <code>{event}</code>")
    await alert_admins(
        bot,
        config,
        f"<b>Поиск #{result.get('run_id', '?')} готов</b>\n\n"
        f"Нашел: <code>{result['found']}</code>\n"
        f"Сохранил: <code>{result['saved']}</code>\n"
        f"Кандидаты: <code>{result['candidates']}</code>",
    )
    await send_latest_candidates(bot, config, after_post_id=last_post_id)


async def handle_bingx_job(bot: Bot, config: Config, job: Job) -> None:
    from app.services.bingx import BingXClient
    from app.db.models import Exchange
    
    with SessionLocal() as db:
        exchange = db.query(Exchange).filter_by(name="bingx", is_active=True).first()
        if not exchange:
            raise RuntimeError("Активный BingX API ключ не найден в базе")
            
        client = BingXClient.from_exchange_model(exchange)
        
    balance = await client.get_balance()
    await alert_admins(bot, config, f"✅ BingX API подключен! Текущий баланс: {balance}")


async def handle_job(bot: Bot, config: Config, job: Job) -> None:
    if job.kind == JOB_SEARCH:
        await handle_search_job(bot, config, job)
        return
    if job.kind == JOB_BINGX_SYNC:
        await handle_bingx_job(bot, config, job)
        return
    if job.kind == JOB_AI_ANALYSIS:
        raise RuntimeError(f"Job {job.kind} пока не подключен")
    raise RuntimeError(f"Неизвестный job kind: {job.kind}")


async def job_worker_loop(bot: Bot, config: Config) -> None:
    while True:
        try:
            with SessionLocal() as db:
                requeue_stale_jobs(db)
                job = claim_next_job(db)
                db.commit()
            if not job:
                await asyncio.sleep(2)
                continue
            try:
                logger.info("Job %s started: %s", job.id, job.kind)
                await handle_job(bot, config, job)
                with SessionLocal() as db:
                    job_db = db.get(Job, job.id)
                    if job_db:
                        finish_job(db, job_db)
                    db.commit()
                logger.info("Job %s done", job.id)
            except Exception as exc:
                logger.exception("Job %s failed", job.id)
                with SessionLocal() as db:
                    job_db = db.get(Job, job.id)
                    if job_db:
                        fail_job(db, job_db, str(exc))
                        failed_finally = job_db.status == "failed"
                    else:
                        failed_finally = True
                    db.commit()
                if failed_finally:
                    await critical_alert(bot, config, f"Job #{job.id} упал", exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Job worker failed")
            await critical_alert(bot, config, "Очередь jobs упала", exc)
            await asyncio.sleep(10)


async def auto_search_loop(bot: Bot, config: Config) -> None:
    from app.services.settings import get_int
    from app.services.jobs import enqueue_job, JOB_SEARCH

    while True:
        try:
            with SessionLocal() as db:
                interval = get_int(db, "search_auto_interval_minutes", 60)

            if interval > 0:
                logger.info("Auto-search triggered. Next run in %s minutes", interval)
                with SessionLocal() as db:
                    enqueue_job(db, JOB_SEARCH, created_by_admin_id=None)
                    db.commit()
                await asyncio.sleep(interval * 60)
            else:
                await asyncio.sleep(60)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Auto search loop failed")
            await asyncio.sleep(60)


async def auto_expire_loop(bot: Bot, config: Config) -> None:
    """Daily cleanup: move candidate posts older than 24h to skipped/expired."""
    from app.services.posts import expire_old_candidates

    while True:
        try:
            with SessionLocal() as db:
                count = expire_old_candidates(db, older_than_hours=24)
            if count:
                logger.info("Auto-expire: moved %s stale candidates to skipped/expired", count)
                await alert_admins(bot, config, f"🗑 Авточистка: перемещено {count} устаревших кандидатов в архив")
            await asyncio.sleep(24 * 60 * 60)  # раз в сутки
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Auto expire loop failed")
            await asyncio.sleep(60 * 60)  # retry через час при ошибке
