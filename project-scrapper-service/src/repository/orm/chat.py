from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from migrations.db import Chat
from src.repository.interfaces import ChatRepository


class OrmChatRepository(ChatRepository):
    """ORM реализация репозитория для работы с чатами."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_chat_ids(self, limit: int = 10, offset: int = 0) -> list[int]:
        async with self.session.begin():
            result = await self.session.execute(
                select(Chat.chat_id).limit(limit).offset(offset)
            )
            return [row[0] for row in result.fetchall()]

    async def add_chat(self, chat_id: int) -> bool:
        async with self.session.begin():
            if await self._get_chat_by_chat_id(chat_id):
                return False
            self.session.add(Chat(chat_id=chat_id))
            return True

    async def remove_chat(self, chat_id: int) -> bool:
        async with self.session.begin():
            chat = await self._get_chat_by_chat_id(chat_id)
            if not chat:
                return False
            await self.session.delete(chat)
            return True

    async def chat_exists(self, chat_id: int) -> bool:
        async with self.session.begin():
            chat = await self._get_chat_by_chat_id(chat_id)
            return chat is not None

    async def _get_chat_by_chat_id(self, chat_id: int) -> Chat | None:
        """Получить чат по ID."""
        result = await self.session.execute(select(Chat).where(Chat.chat_id == chat_id))
        return result.scalar_one_or_none()
