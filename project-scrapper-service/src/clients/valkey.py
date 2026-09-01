import redis.asyncio as redis


class ValkeyClient:
    def __init__(self, host: str, port: int, ttl: int):
        self.client = redis.Redis(host=host, port=port, decode_responses=True)
        self.ttl = ttl

    async def get(self, key: str) -> str | None:
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        await self.client.set(key, value, ex=ex)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def aclose(self) -> None:
        await self.client.aclose()

    @staticmethod
    def get_cache_key(tg_chat_id: int) -> str:
        """Вспомогательная функция для генерации ключа кэша."""
        return f"chat_links:{tg_chat_id}"
