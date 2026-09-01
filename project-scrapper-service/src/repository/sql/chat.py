import asyncpg
from src.repository.interfaces import ChatRepository


class SqlChatRepository(ChatRepository):
    """Raw SQL реализация репозитория для работы с чатами."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_all_chat_ids(self, limit: int = 10, offset: int = 0) -> list[int]:
        rows = await self.pool.fetch(
            "SELECT chat_id FROM chats LIMIT $1 OFFSET $2", limit, offset
        )
        return [row["chat_id"] for row in rows]

    async def add_chat(self, chat_id: int) -> bool:
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO chats (chat_id) VALUES ($1)",
                    chat_id,
                )
                return True
            except asyncpg.UniqueViolationError:
                return False

    async def remove_chat(self, chat_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM chats WHERE chat_id = $1",
                chat_id,
            )
            return result == "DELETE 1"

    async def chat_exists(self, chat_id: int) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM chats WHERE chat_id = $1)",
                chat_id,
            )
            return row
