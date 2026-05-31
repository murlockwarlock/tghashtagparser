import pytest
from hydrogram.errors import FloodWait, InternalServerError

from app.telegram_client.search import iter_global_messages, wait_flood


class FlakySearchClient:
    def __init__(self) -> None:
        self.calls = 0

    async def search_global(self, tag: str, limit: int):
        self.calls += 1
        if self.calls == 1:
            raise InternalServerError()
        yield {"tag": tag, "limit": limit}


@pytest.mark.asyncio
async def test_internal_server_error_is_retried() -> None:
    client = FlakySearchClient()
    items = [item async for item in iter_global_messages(client, "#BTC", 1)]

    assert client.calls == 2
    assert items == [{"tag": "#BTC", "limit": 1}]


@pytest.mark.asyncio
async def test_large_flood_wait_is_not_slept() -> None:
    error = FloodWait()
    error.value = 999_999

    assert await wait_flood(error, "#BTC") is False


def test_account_search_result_can_carry_proxy_events() -> None:
    from app.telegram_client.search import AccountSearchResult

    result = AccountSearchResult(proxy_events=["proxy1 failed"])

    assert result.proxy_events == ["proxy1 failed"]
