from typing import Literal
from sqlalchemy.ext.asyncio import async_sessionmaker
import asyncpg

from src.repository.orm import OrmChatRepository, OrmLinkRepository
from src.repository.sql import SqlChatRepository, SqlLinkRepository
from src.repository.interfaces import ChatRepository, LinkRepository
from src.services import ChatServiceImpl, LinkServiceImpl, ChatService, LinkService


class RepositoryFactory:
    """Фабрика для создания репозиториев в зависимости от access-type."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        pool: asyncpg.Pool,
        access_type: Literal["SQL", "ORM"] = "ORM",
    ):
        self.session_factory = session_factory
        self.pool = pool
        self.access_type = access_type

    def create_chat_repository(self) -> ChatRepository:
        """Создать репозиторий для работы с чатами."""
        if self.access_type == "ORM":
            return OrmChatRepository(self.session_factory())
        else:
            return SqlChatRepository(self.pool)

    def create_link_repository(self) -> LinkRepository:
        """Создать репозиторий для работы со ссылками."""
        if self.access_type == "ORM":
            return OrmLinkRepository(self.session_factory())
        else:
            return SqlLinkRepository(self.pool)

    def create_chat_service(self) -> ChatService:
        """Создать сервис для работы с чатами."""
        return ChatServiceImpl(self.create_chat_repository())

    def create_link_service(self) -> LinkService:
        """Создать сервис для работы со ссылками."""
        return LinkServiceImpl(
            chat_repo=self.create_chat_repository(),
            link_repo=self.create_link_repository(),
        )


def create_repository_factory(
    session_factory: async_sessionmaker,
    pool: asyncpg.Pool,
    access_type: Literal["SQL", "ORM"] = "ORM",
) -> RepositoryFactory:
    """Создать фабрику репозиториев и сервисов."""
    return RepositoryFactory(
        session_factory=session_factory,
        pool=pool,
        access_type=access_type,
    )
