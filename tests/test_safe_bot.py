import pytest
from unittest.mock import AsyncMock
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramAPIError
from app.services.safe_bot import telegram_call

@pytest.mark.asyncio
async def test_telegram_call_success():
    call = AsyncMock(return_value="ok")
    res = await telegram_call("test", call)
    assert res == "ok"
    call.assert_awaited_once()

@pytest.mark.asyncio
async def test_telegram_call_retry_after(monkeypatch):
    import asyncio
    sleep_mock = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep_mock)

    call = AsyncMock(side_effect=[TelegramRetryAfter(method="m", message="m", retry_after=5), "ok2"])
    res = await telegram_call("test", call)

    assert res == "ok2"
    assert call.call_count == 2
    sleep_mock.assert_awaited_once_with(5)

@pytest.mark.asyncio
async def test_telegram_call_retry_fails(monkeypatch):
    import asyncio
    sleep_mock = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep_mock)

    call = AsyncMock(side_effect=[TelegramRetryAfter(method="m", message="m", retry_after=5), TelegramAPIError(method="m", message="m")])
    res = await telegram_call("test", call)

    assert res is None

@pytest.mark.asyncio
async def test_telegram_call_forbidden():
    call = AsyncMock(side_effect=TelegramForbiddenError(method="m", message="m"))
    res = await telegram_call("test", call)
    assert res is None

@pytest.mark.asyncio
async def test_telegram_call_api_error():
    call = AsyncMock(side_effect=TelegramAPIError(method="m", message="m"))
    res = await telegram_call("test", call)
    assert res is None
