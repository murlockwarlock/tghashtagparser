import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from hydrogram.errors import RPCError, Unauthorized

from app.config import Config
from app.db.models import Hashtag, Job, PublishChannel, SearchRun, TelegramAccount
from app.db.session import SessionLocal
from app.services.alerts import alert_admins
from app.services.accounts import set_account_status
from app.telegram_client.search import build_client

logger = logging.getLogger(__name__)


def collect_health_warnings() -> list[str]:
    with SessionLocal() as db:
        warnings = []
        if not db.query(TelegramAccount).filter(TelegramAccount.is_active.is_(True)).first():
            warnings.append("нет активного TG аккаунта")
        if not db.query(Hashtag).filter(Hashtag.is_active.is_(True)).first():
            warnings.append("нет активных хэштегов")
        return warnings


def health_full_text() -> str:
    with SessionLocal() as db:
        accounts = db.query(TelegramAccount).order_by(TelegramAccount.id.asc()).all()
        last_run = db.query(SearchRun).order_by(SearchRun.id.desc()).first()
        jobs = db.query(Job).order_by(Job.id.desc()).limit(5).all()
        lines = ["<b>Полный статус</b>", ""]
        lines.append("<b>TG аккаунты</b>")
        if not accounts:
            lines.append("Пока нет аккаунтов")
        for account in accounts:
            checked = account.last_checked_at or "-"
            flood_until = account.flood_wait_until or "-"
            error = account.last_error or "-"
            is_active_ru = "Да" if account.is_active else "Нет"
            lines.append(
                f"#{account.id} <code>{account.title}</code> "
                f"<code>{account.status}</code>\n"
                f"Активен: <code>{is_active_ru}</code>\n"
                f"Проверен: <code>{checked}</code>\n"
                f"Блок до: <code>{flood_until}</code>\n"
                f"Ошибка: <code>{error}</code>"
            )
        lines.append("")
        lines.append("<b>Последний поиск</b>")
        if last_run:
            lines.append(
                f"#{last_run.id} <code>{last_run.status}</code>\n"
                f"найдено: <code>{last_run.found_count}</code>, "
                f"сохранено: <code>{last_run.saved_count}</code>, "
                f"кандидаты: <code>{last_run.candidate_count}</code>\n"
                f"ошибка: <code>{last_run.last_error or '-'}</code>"
            )
        else:
            lines.append("Еще не запускали")
        lines.append("")
        lines.append("<b>Задачи (Jobs)</b>")
        if not jobs:
            lines.append("Пока пусто")
        for job in jobs:
            lines.append(
                f"#{job.id} <code>{job.kind}</code> <code>{job.status}</code> "
                f"попытки: <code>{job.attempts}/{job.max_attempts}</code>\n"
                f"ошибка: <code>{job.last_error or '-'}</code>"
            )
        return "\n".join(lines)


async def check_account_session(account: TelegramAccount) -> tuple[bool, str | None]:
    client = build_client(account)
    try:
        async with client:
            await client.get_me()
        return True, None
    except Unauthorized as exc:
        return False, str(exc)
    except (OSError, TimeoutError, ConnectionError, RPCError) as exc:
        return False, str(exc)


async def check_all_accounts(bot: Bot, config: Config) -> None:
    with SessionLocal() as db:
        accounts = db.query(TelegramAccount).order_by(TelegramAccount.id.asc()).all()

    for account in accounts:
        ok, error = await check_account_session(account)
        with SessionLocal() as db:
            if ok:
                set_account_status(db, account.id, "active", None, True)
            else:
                set_account_status(db, account.id, "unauthorized", error, False)
            db.commit()
        if not ok:
            logger.warning("Account %s disabled by health check: %s", account.title, error)
            await alert_admins(
                bot,
                config,
                f"⚠️ TG аккаунт отключен\n\n"
                f"<code>{account.title}</code>\n"
                f"<code>{error}</code>",
            )


async def health_loop(bot: Bot, config: Config) -> None:
    last_message = ""
    while True:
        try:
            warnings = collect_health_warnings()
            message = "\n".join(f"• {item}" for item in warnings)
            if warnings and message != last_message:
                logger.warning("Health warnings: %s", "; ".join(warnings))
                await alert_admins(bot, config, f"⚠️ <b>Проверь настройки</b>\n\n{message}")
                last_message = message
            if not warnings:
                last_message = ""
            await asyncio.sleep(21600)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Health check failed")
            await asyncio.sleep(3600)


async def account_session_check_loop(bot: Bot, config: Config) -> None:
    while True:
        try:
            now = datetime.now()
            next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())
            await check_all_accounts(bot, config)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Account session check failed")
            await asyncio.sleep(86400)
