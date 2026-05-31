import logging

from aiogram import Bot

from app.config import Config
from app.services.safe_bot import telegram_call
from app.utils.text import html_escape

logger = logging.getLogger(__name__)


async def alert_admins(bot: Bot, config: Config, text: str) -> None:
    for admin_id in config.admin_ids:
        await telegram_call(
            f"send admin alert to {admin_id}",
            lambda admin_id=admin_id: bot.send_message(admin_id, text),
        )


async def critical_alert(bot: Bot, config: Config, title: str, error: Exception | str) -> None:
    await alert_admins(
        bot,
        config,
        f"🚨 <b>{html_escape(title)}</b>\n\n<code>{html_escape(error)}</code>",
    )
