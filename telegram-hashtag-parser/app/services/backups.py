import asyncio
import logging
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from app.config import Config
from app.db.session import SessionLocal
from app.services.alerts import alert_admins, critical_alert
from app.services.safe_bot import telegram_call
from app.services.settings import get_int

logger = logging.getLogger(__name__)


def sqlite_path(database_url: str) -> Path | None:
    if database_url.startswith("sqlite:////"):
        return Path("/" + database_url.removeprefix("sqlite:////"))
    if database_url.startswith("sqlite:///"):
        return Path(database_url.removeprefix("sqlite:///"))
    return None


def cleanup_backups(directory: Path, retention_days: int) -> None:
    threshold = datetime.now() - timedelta(days=retention_days)
    for item in directory.glob("db_backup_*.zip"):
        if datetime.fromtimestamp(item.stat().st_mtime) < threshold:
            item.unlink(missing_ok=True)


def make_sqlite_backup(config: Config) -> Path:
    db_path = sqlite_path(config.database_url)
    if db_path is None:
        raise RuntimeError("Only sqlite backups are supported in MVP")
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    if not db_path.exists():
        raise RuntimeError(f"Database file not found: {db_path}")

    backup_dir = Path(config.log_dir) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    copy_path = backup_dir / f"db_backup_{stamp}.sqlite3"
    zip_path = backup_dir / f"db_backup_{stamp}.zip"

    source = sqlite3.connect(db_path)
    target = sqlite3.connect(copy_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(copy_path, arcname=copy_path.name)

    copy_path.unlink(missing_ok=True)
    return zip_path


async def send_database_backup(bot: Bot, config: Config) -> None:
    logger.info("Starting scheduled database backup")
    with SessionLocal() as db:
        retention_days = get_int(db, "backup_retention_days", 7)

    archive_path = make_sqlite_backup(config)
    file = FSInputFile(archive_path)
    caption = f"✅ Бэкап БД готов\n<code>{archive_path.name}</code>"

    for admin_id in config.admin_ids:
        await telegram_call(
            f"send database backup to {admin_id}",
            lambda admin_id=admin_id: bot.send_document(admin_id, file, caption=caption),
        )

    cleanup_backups(archive_path.parent, retention_days)
    logger.info("Database backup sent: %s", archive_path)


async def backup_loop(bot: Bot, config: Config) -> None:
    await alert_admins(bot, config, "✅ Бот запущен. Бэкап БД включен.")
    while True:
        try:
            with SessionLocal() as db:
                backup_hour = get_int(db, "backup_hour", 7)
            now = datetime.now()
            next_run = now.replace(hour=backup_hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())
            await send_database_backup(bot, config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Scheduled database backup failed")
            await critical_alert(bot, config, "Не смог сделать бэкап БД", exc)
            await asyncio.sleep(3600)
