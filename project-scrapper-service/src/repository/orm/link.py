from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, insert
from migrations.db import Link, Chat, link_chat, link_tag
from src.schemas import LinkResponse
from src.repository.interfaces import LinkRepository
from src.exceptions import LinkAlreadyExistsException, ChatNotFoundException


class OrmLinkRepository(LinkRepository):
    """ORM реализация репозитория для работы со ссылками."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_links(
        self, chat_id: int, limit: int = 10, offset: int = 0
    ) -> list[LinkResponse]:
        async with self.session.begin():
            internal_chat_id = await self._get_internal_chat_id(chat_id)

            link_chat_result = await self.session.execute(
                select(link_chat.c.link_id)
                .where(link_chat.c.chat_id == internal_chat_id)
                .limit(limit)
                .offset(offset)
            )
            link_ids = [row.link_id for row in link_chat_result.fetchall()]

            if not link_ids:
                return []

            links_result = await self.session.execute(
                select(Link).where(Link.id.in_(link_ids))
            )
            links = links_result.scalars().all()

            result = []
            for link in links:
                tags_result = await self.session.execute(
                    select(link_tag.c.tag_name).where(
                        link_tag.c.link_id == link.id,
                        link_tag.c.chat_id == internal_chat_id,
                    )
                )
                tags = [row.tag_name for row in tags_result.fetchall()]

                result.append(
                    LinkResponse(
                        id=link.id,
                        url=link.url,
                        tags=tags,
                        filters=[],
                        updated_at=link.updated_at,
                    )
                )
            return result

    async def add_link(
        self, chat_id: int, url: str, tags: list[str] | None = None
    ) -> LinkResponse:
        async with self.session.begin():
            internal_chat_id = await self._get_internal_chat_id(chat_id)

            link = await self._get_link_by_url(url)
            if link:
                existing_binding = await self.session.execute(
                    select(link_chat).where(
                        (link_chat.c.chat_id == internal_chat_id)
                        & (link_chat.c.link_id == link.id)
                    )
                )
                if existing_binding.fetchone():
                    raise LinkAlreadyExistsException(url)
            else:
                link = Link(url=url)
                self.session.add(link)
                await self.session.flush()

            await self.session.execute(
                insert(link_chat).values(chat_id=internal_chat_id, link_id=link.id)
            )

            if tags:
                for tag in tags:
                    await self.session.execute(
                        insert(link_tag).values(
                            chat_id=internal_chat_id, link_id=link.id, tag_name=tag
                        )
                    )

            return LinkResponse(
                id=link.id,
                url=link.url,
                tags=tags or [],
                filters=[],
                updated_at=link.updated_at,
            )

    async def update_link_updated_at(self, url: str, updated_at: datetime) -> bool:
        async with self.session.begin():
            link = await self._get_link_by_url(url)
            if not link:
                return False
            link.updated_at = updated_at
            return True

    async def remove_link(self, chat_id: int, url: str) -> LinkResponse | None:
        async with self.session.begin():
            internal_chat_id = await self._get_internal_chat_id(chat_id)

            link = await self._get_link_by_url(url)
            if not link:
                return None

            binding = await self.session.execute(
                select(link_chat).where(
                    (link_chat.c.chat_id == internal_chat_id)
                    & (link_chat.c.link_id == link.id)
                )
            )
            if not binding.fetchone():
                return None

            tags_result = await self.session.execute(
                select(link_tag.c.tag_name).where(
                    link_tag.c.chat_id == internal_chat_id,
                    link_tag.c.link_id == link.id,
                )
            )
            tags = [row.tag_name for row in tags_result.fetchall()]

            await self.session.execute(
                delete(link_chat).where(
                    (link_chat.c.chat_id == internal_chat_id)
                    & (link_chat.c.link_id == link.id)
                )
            )

            remaining = await self.session.execute(
                select(link_chat).where(link_chat.c.link_id == link.id)
            )
            if not remaining.fetchone():
                await self.session.delete(link)

            return LinkResponse(
                id=link.id,
                url=link.url,
                tags=tags,
                filters=[],
                updated_at=link.updated_at,
            )

    async def link_exists_for_chat(self, chat_id: int, url: str) -> bool:
        async with self.session.begin():
            internal_chat_id = await self._get_internal_chat_id(chat_id)
            result = await self.session.execute(
                select(link_chat)
                .join(Link, link_chat.c.link_id == Link.id)
                .where((link_chat.c.chat_id == internal_chat_id) & (Link.url == url))
            )
            return result.fetchone() is not None

    async def _get_link_by_url(self, url: str) -> Link | None:
        """Получить ссылку по URL."""
        result = await self.session.execute(select(Link).where(Link.url == url))
        return result.scalar_one_or_none()

    async def _get_internal_chat_id(self, chat_id: int) -> int:
        """Получить внутренний chats.id по Telegram chat_id."""
        result = await self.session.execute(
            select(Chat.id).where(Chat.chat_id == chat_id)
        )
        row = result.first()
        if not row:
            raise ChatNotFoundException(chat_id)
        return row[0]
