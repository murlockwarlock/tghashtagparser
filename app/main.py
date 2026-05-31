import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

from app.bot.handlers import build_router
from app.config import load_config
from app.db.init_db import init_db
from app.logging_config import setup_logging
from app.services.alerts import critical_alert
from app.services.backups import backup_loop
from app.services.health import account_session_check_loop, health_loop
from app.workers.jobs import job_worker_loop, auto_search_loop, auto_expire_loop

logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = load_config()
    setup_logging(cfg)
    init_db()

    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_router())

    async def on_error(event: ErrorEvent) -> bool:
        logger.exception("Unhandled bot error", exc_info=event.exception)
        await critical_alert(bot, cfg, "Критическая ошибка в боте", event.exception)
        return True

    dp.errors.register(on_error)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="list_tags", description="Хэштеги"),
            BotCommand(command="add_tag", description="Добавить хэштег"),
            BotCommand(command="remove_tag", description="Убрать хэштег"),
            BotCommand(command="run_search", description="Запустить поиск"),
            BotCommand(command="stats", description="Стата"),
            BotCommand(command="health_full", description="Полный статус"),
        ]
    )
    await bot.delete_webhook(drop_pending_updates=True)
    backup_task = asyncio.create_task(backup_loop(bot, cfg))
    health_task = asyncio.create_task(health_loop(bot, cfg))
    account_check_task = asyncio.create_task(account_session_check_loop(bot, cfg))
    job_worker_task = asyncio.create_task(job_worker_loop(bot, cfg))
    auto_search_task = asyncio.create_task(auto_search_loop(bot, cfg))
    auto_expire_task = asyncio.create_task(auto_expire_loop(bot, cfg))
    try:
        logger.info("Bot polling started")
        await dp.start_polling(bot)
    finally:
        backup_task.cancel()
        health_task.cancel()
        account_check_task.cancel()
        job_worker_task.cancel()
        auto_search_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
