import pytest
from httpx import AsyncClient

from src.clients import ValkeyClient

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("clean_cache")]


class TestChatManagement:
    async def test_register_chat(self, client: AsyncClient) -> None:
        """Тест регистрации чата."""
        response = await client.post("/tg-chat/1")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Chat registered successfully"

    async def test_register_duplicate_chat(self, client: AsyncClient) -> None:
        """Тест регистрации дублирующегося чата (409 Conflict)."""
        await client.post("/tg-chat/1")
        response = await client.post("/tg-chat/1")
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "409"
        assert isinstance(data["stacktrace"], list)

    async def test_delete_chat(self, client: AsyncClient) -> None:
        """Тест удаления чата."""
        await client.post("/tg-chat/1")
        response = await client.delete("/tg-chat/1")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Chat unregistered successfully"

    async def test_delete_non_existent_chat(self, client: AsyncClient) -> None:
        """Тест удаления несуществующего чата (404 Not Found)."""
        response = await client.delete("/tg-chat/999")
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "404"
        assert isinstance(data["stacktrace"], list)


class TestLinkManagement:
    async def test_add_and_get_link(self, client: AsyncClient) -> None:
        """Тест добавления и получения ссылки."""
        await client.post("/tg-chat/1")

        link_payload = {
            "link": "https://github.com/user/repo",
            "tags": ["work"],
            "filters": [],
        }
        response = await client.post(
            "/links", headers={"Tg-Chat-Id": "1"}, json=link_payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://github.com/user/repo"
        assert data["tags"] == ["work"]
        assert "updated_at" in data

        response = await client.get("/links", headers={"Tg-Chat-Id": "1"})
        assert response.status_code == 200
        data = response.json()
        assert data["size"] == 1
        assert data["links"][0]["url"] == "https://github.com/user/repo"

    async def test_add_and_delete_link(self, client: AsyncClient) -> None:
        """Тест добавления и удаления ссылки."""
        await client.post("/tg-chat/1")

        link_payload = {
            "link": "https://stackoverflow.com/questions/123",
            "tags": [],
            "filters": [],
        }
        await client.post("/links", headers={"Tg-Chat-Id": "1"}, json=link_payload)

        remove_payload = {"link": "https://stackoverflow.com/questions/123"}
        response = await client.request(
            "DELETE", "/links", headers={"Tg-Chat-Id": "1"}, json=remove_payload
        )
        assert response.status_code == 200

        response = await client.get("/links", headers={"Tg-Chat-Id": "1"})
        assert response.status_code == 200
        assert response.json()["size"] == 0

    async def test_delete_link_from_non_existent_chat(
        self, client: AsyncClient
    ) -> None:
        """Тест удаления ссылки из несуществующего чата."""
        await client.post("/tg-chat/1")

        link_payload = {"link": "https://example.com", "tags": [], "filters": []}
        await client.post("/links", headers={"Tg-Chat-Id": "1"}, json=link_payload)

        remove_payload = {"link": "https://example.com"}
        response = await client.request(
            "DELETE", "/links", headers={"Tg-Chat-Id": "999"}, json=remove_payload
        )
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "404"
        assert isinstance(data["stacktrace"], list)

        response = await client.get("/links", headers={"Tg-Chat-Id": "1"})
        assert response.status_code == 200
        assert response.json()["size"] == 1

    async def test_add_link_to_non_existent_chat(self, client: AsyncClient) -> None:
        """Тест добавления ссылки в несуществующий чат."""
        link_payload = {"link": "https://example.com", "tags": [], "filters": []}
        response = await client.post(
            "/links", headers={"Tg-Chat-Id": "2"}, json=link_payload
        )
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "404"
        assert isinstance(data["stacktrace"], list)

    async def test_work_with_deleted_chat(self, client: AsyncClient) -> None:
        """Тест работы с удалённым чатом."""
        await client.post("/tg-chat/1")
        response = await client.delete("/tg-chat/1")
        assert response.status_code == 200

        link_payload = {"link": "https://example.com", "tags": [], "filters": []}
        response = await client.post(
            "/links", headers={"Tg-Chat-Id": "1"}, json=link_payload
        )
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "404"
        assert isinstance(data["stacktrace"], list)

    async def test_add_duplicate_link(self, client: AsyncClient) -> None:
        """Тест добавления дублирующейся ссылки (409 Conflict)."""
        await client.post("/tg-chat/1")

        link_payload = {"link": "https://example.com", "tags": [], "filters": []}
        await client.post("/links", headers={"Tg-Chat-Id": "1"}, json=link_payload)

        response = await client.post(
            "/links", headers={"Tg-Chat-Id": "1"}, json=link_payload
        )
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "409"
        assert isinstance(data["stacktrace"], list)


class TestCacheManagement:
    async def test_get_links_uses_cache(
        self, client: AsyncClient, valkey_client: ValkeyClient
    ) -> None:
        """Тест: GET /links кэширует результат при первом запросе."""
        await client.post("/tg-chat/1")

        cache_key = valkey_client.get_cache_key(1)
        assert await valkey_client.get(cache_key) is None

        response = await client.get("/links", headers={"Tg-Chat-Id": "1"})
        assert response.status_code == 200

        cached_data = await valkey_client.get(cache_key)
        assert cached_data is not None
        assert '"size":' in cached_data

    async def test_add_link_invalidates_cache(
        self, client: AsyncClient, valkey_client: ValkeyClient
    ) -> None:
        """Тест: POST /links сбрасывает кэш для конкретного чата."""
        await client.post("/tg-chat/1")

        await client.get("/links", headers={"Tg-Chat-Id": "1"})
        cache_key = valkey_client.get_cache_key(1)
        assert await valkey_client.get(cache_key) is not None

        link_payload = {"link": "https://example.com", "tags": [], "filters": []}
        response = await client.post(
            "/links", headers={"Tg-Chat-Id": "1"}, json=link_payload
        )
        assert response.status_code == 200

        assert await valkey_client.get(cache_key) is None

    async def test_remove_link_invalidates_cache(
        self, client: AsyncClient, valkey_client: ValkeyClient
    ) -> None:
        """Тест: DELETE /links сбрасывает кэш для конкретного чата."""
        await client.post("/tg-chat/1")

        link_payload = {"link": "https://example.com", "tags": [], "filters": []}
        await client.post("/links", headers={"Tg-Chat-Id": "1"}, json=link_payload)

        await client.get("/links", headers={"Tg-Chat-Id": "1"})
        cache_key = valkey_client.get_cache_key(1)
        assert await valkey_client.get(cache_key) is not None

        remove_payload = {"link": "https://example.com"}
        response = await client.request(
            "DELETE", "/links", headers={"Tg-Chat-Id": "1"}, json=remove_payload
        )
        assert response.status_code == 200

        assert await valkey_client.get(cache_key) is None
