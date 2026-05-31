import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


async def telegram_call(action: str, call: Callable[[], Awaitable[T]]) -> T | None:
    try:
        return await call()
    except TelegramRetryAfter as exc:
        logger.warning("Telegram retry after during %s: %s", action, exc.retry_after)
        await asyncio.sleep(exc.retry_after)
        try:
            return await call()
        except TelegramAPIError:
            logger.exception("Telegram call failed after retry: %s", action)
            return None
    except (TelegramForbiddenError, TelegramUnauthorizedError):
        logger.warning("Telegram access denied during %s", action, exc_info=True)
        return None
    except TelegramAPIError:
        logger.exception("Telegram API error during %s", action)
        return None
