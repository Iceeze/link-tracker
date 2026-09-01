from datetime import datetime

import asyncpg
from src.repository.interfaces import LinkRepository
from src.schemas import LinkResponse
from src.exceptions import LinkAlreadyExistsException, ChatNotFoundException


class SqlLinkRepository(LinkRepository):
    """Raw SQL реализация репозитория для работы со ссылками."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def _get_internal_chat_id(self, chat_id: int) -> int:
        """Получить внутренний chats.id по Telegram chat_id."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM chats WHERE chat_id = $1",
                chat_id,
            )
            if not row:
                raise ChatNotFoundException(chat_id)
            return row["id"]

    async def get_links(
        self, chat_id: int, limit: int = 10, offset: int = 0
    ) -> list[LinkResponse]:
        internal_chat_id = await self._get_internal_chat_id(chat_id)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT l.id, l.url, l.updated_at, l.created_at
                FROM links l
                JOIN link_chat lc ON l.id = lc.link_id
                WHERE lc.chat_id = $1
                LIMIT $2 OFFSET $3
                """,
                internal_chat_id,
                limit,
                offset,
            )

            if not rows:
                return []

            result = []
            for row in rows:
                tags = await conn.fetch(
                    "SELECT tag_name FROM link_tag WHERE chat_id = $1 AND link_id = $2",
                    internal_chat_id,
                    row["id"],
                )
                tag_names = [t["tag_name"] for t in tags]

                result.append(
                    LinkResponse(
                        id=row["id"],
                        url=row["url"],
                        tags=tag_names,
                        filters=[],
                        updated_at=row["updated_at"],
                    )
                )

            return result

    async def add_link(
        self,
        chat_id: int,
        url: str,
        tags: list[str] | None = None,
    ) -> LinkResponse:
        internal_chat_id = await self._get_internal_chat_id(chat_id)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                link = await conn.fetchrow(
                    "SELECT id FROM links WHERE url = $1",
                    url,
                )

                if link:
                    existing = await conn.fetchrow(
                        "SELECT 1 FROM link_chat WHERE chat_id = $1 AND link_id = $2",
                        internal_chat_id,
                        link["id"],
                    )
                    if existing:
                        raise LinkAlreadyExistsException(url)
                    link_id = link["id"]
                else:
                    link_row = await conn.fetchrow(
                        "INSERT INTO links (url) VALUES ($1) RETURNING id",
                        url,
                    )
                    link_id = link_row["id"]

                await conn.execute(
                    "INSERT INTO link_chat (chat_id, link_id) VALUES ($1, $2)",
                    internal_chat_id,
                    link_id,
                )

                if tags:
                    for tag in tags:
                        await conn.execute(
                            "INSERT INTO link_tag (chat_id, link_id, tag_name) VALUES ($1, $2, $3)",
                            internal_chat_id,
                            link_id,
                            tag,
                        )

                return LinkResponse(
                    id=link_id,
                    url=url,
                    tags=tags or [],
                    filters=[],
                    updated_at=None,
                )

    async def update_link_updated_at(self, url: str, updated_at: datetime) -> bool:
        result = await self.pool.execute(
            "UPDATE links SET updated_at = $1 WHERE url = $2", updated_at, url
        )
        return result == "UPDATE 1" or (result and "UPDATE" in result)

    async def remove_link(self, chat_id: int, url: str) -> LinkResponse | None:
        internal_chat_id = await self._get_internal_chat_id(chat_id)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                link = await conn.fetchrow(
                    "SELECT id, updated_at FROM links WHERE url = $1",
                    url,
                )
                if not link:
                    return None

                binding = await conn.fetchrow(
                    "SELECT 1 FROM link_chat WHERE chat_id = $1 AND link_id = $2",
                    internal_chat_id,
                    link["id"],
                )
                if not binding:
                    return None

                tags = await conn.fetch(
                    "SELECT tag_name FROM link_tag WHERE chat_id = $1 AND link_id = $2",
                    internal_chat_id,
                    link["id"],
                )
                tag_names = [t["tag_name"] for t in tags]

                await conn.execute(
                    "DELETE FROM link_chat WHERE chat_id = $1 AND link_id = $2",
                    internal_chat_id,
                    link["id"],
                )

                remaining = await conn.fetchval(
                    "SELECT COUNT(*) FROM link_chat WHERE link_id = $1",
                    link["id"],
                )
                if remaining == 0:
                    await conn.execute(
                        "DELETE FROM links WHERE id = $1",
                        link["id"],
                    )

                return LinkResponse(
                    id=link["id"],
                    url=url,
                    tags=tag_names,
                    filters=[],
                    updated_at=link["updated_at"],
                )

    async def link_exists_for_chat(self, chat_id: int, url: str) -> bool:
        internal_chat_id = await self._get_internal_chat_id(chat_id)

        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM link_chat lc
                    JOIN links l ON lc.link_id = l.id
                    WHERE lc.chat_id = $1 AND l.url = $2
                )
                """,
                internal_chat_id,
                url,
            )
            return exists
