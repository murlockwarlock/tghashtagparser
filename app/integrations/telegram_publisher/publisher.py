class TelegramPublisher:
    async def publish(self, channel_id: str, text: str, buttons: list | None = None) -> int:
        raise NotImplementedError
