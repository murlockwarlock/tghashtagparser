import pytest
from unittest.mock import AsyncMock, patch
from app.services.alerts import alert_admins, critical_alert
from app.config import Config

@pytest.fixture
def config():
    return Config(bot_token="t", admin_ids={1, 2}, database_url="db", log_dir="l")

@pytest.mark.asyncio
async def test_alert_admins(config):
    bot_mock = AsyncMock()

    with patch("app.services.alerts.telegram_call", new_callable=AsyncMock) as call_mock:
        await alert_admins(bot_mock, config, "test text")

        assert call_mock.call_count == 2
        calls = call_mock.call_args_list
        assert any(args[0][0] == "send admin alert to 1" for args in calls)
        assert any(args[0][0] == "send admin alert to 2" for args in calls)

        # Call the lambda
        for args in calls:
            await args[0][1]()

        assert bot_mock.send_message.call_count == 2

@pytest.mark.asyncio
async def test_critical_alert(config):
    bot_mock = AsyncMock()

    with patch("app.services.alerts.alert_admins", new_callable=AsyncMock) as alert_mock:
        await critical_alert(bot_mock, config, "Title <", "Error >")

        alert_mock.assert_awaited_once()
        text = alert_mock.call_args[0][2]
        assert "Title &lt;" in text
        assert "Error &gt;" in text
