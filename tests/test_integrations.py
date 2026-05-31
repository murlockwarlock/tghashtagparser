import pytest
from app.integrations.telegram_publisher.publisher import TelegramPublisher
from app.integrations.openai.signal_analyzer import SignalAnalysisService
from app.integrations.bingx.symbols import BingXSymbolsProvider

@pytest.mark.asyncio
async def test_telegram_publisher_not_implemented():
    publisher = TelegramPublisher()
    with pytest.raises(NotImplementedError):
        await publisher.publish("1", "test")

@pytest.mark.asyncio
async def test_openai_analyzer_not_implemented():
    analyzer = SignalAnalysisService()
    with pytest.raises(NotImplementedError):
        await analyzer.analyze("test")

@pytest.mark.asyncio
async def test_bingx_symbols_not_implemented():
    bingx = BingXSymbolsProvider()
    with pytest.raises(NotImplementedError):
        await bingx.fetch_usdt_futures()
