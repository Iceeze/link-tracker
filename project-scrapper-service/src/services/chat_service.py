from src.repository.interfaces import ChatRepository
from src.services.interfaces import ChatService
from src.exceptions import ChatAlreadyExistsException, ChatNotFoundException


class ChatServiceImpl(ChatService):
    """Реализация сервиса для работы с чатами."""

    def __init__(self, chat_repo: ChatRepository):
        self.chat_repo = chat_repo

    async def register_chat(self, chat_id: int) -> bool:
        if await self.chat_repo.chat_exists(chat_id):
            raise ChatAlreadyExistsException(chat_id)
        return await self.chat_repo.add_chat(chat_id)

    async def unregister_chat(self, chat_id: int) -> bool:
        if not await self.chat_repo.chat_exists(chat_id):
            raise ChatNotFoundException(chat_id)
        return await self.chat_repo.remove_chat(chat_id)

    async def get_all_chats(self, limit: int = 10, offset: int = 0) -> list[int]:
        return await self.chat_repo.get_all_chat_ids(limit, offset)
