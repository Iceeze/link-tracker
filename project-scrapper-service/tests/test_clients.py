import httpx
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from pytest_httpx import HTTPXMock

from src.clients import GithubClient, StackOverflowClient
from src.services.scrappers import GithubScrapper, StackOverflowScrapper


@pytest.mark.asyncio
async def test_github_client_success(httpx_mock: HTTPXMock) -> None:
    """Тест успешного запроса GitHub клиента по URL."""
    client = GithubClient("https://api.github.com")

    mock_response = {
        "id": 12345,
        "full_name": "tiangolo/fastapi",
        "updated_at": "2026-03-06T12:00:00Z",
        "pushed_at": "2026-03-06T10:00:00Z",
    }
    httpx_mock.add_response(
        url="https://api.github.com/repos/tiangolo/fastapi",
        json=mock_response,
        status_code=200,
    )

    repo_info = await client.fetch_repo("tiangolo", "fastapi")

    assert repo_info is not None
    assert repo_info.id == 12345
    assert repo_info.full_name == "tiangolo/fastapi"
    assert repo_info.updated_at == datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_github_client_not_found(httpx_mock: HTTPXMock) -> None:
    """Тест запроса GitHub клиента по несуществующему URL."""
    client = GithubClient("https://api.github.com")

    httpx_mock.add_response(
        url="https://api.github.com/repos/tiangolo/not_exist", status_code=404
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_repo("tiangolo", "not_exist")


@pytest.mark.asyncio
async def test_stackoverflow_client_success(httpx_mock: HTTPXMock) -> None:
    """Тест успешного запроса StackOverflow клиента по URL."""
    client = StackOverflowClient("https://api.stackexchange.com/2.3")

    mock_response = {"items": [{"question_id": 9999, "last_activity_date": 1709726400}]}
    httpx_mock.add_response(
        url="https://api.stackexchange.com/2.3/questions/9999?site=stackoverflow",
        json=mock_response,
        status_code=200,
    )

    so_info = await client.fetch_question(9999)

    assert so_info is not None
    assert len(so_info.items) == 1
    assert so_info.items[0].question_id == 9999
    assert so_info.items[0].updated_at == datetime.fromtimestamp(
        1709726400, tz=timezone.utc
    )


@pytest.mark.asyncio
async def test_stackoverflow_client_not_found(httpx_mock: HTTPXMock) -> None:
    """Тест запроса StackOverflow клиента по несуществующему URL."""
    client = StackOverflowClient("https://api.stackexchange.com/2.3")

    httpx_mock.add_response(
        url="https://api.stackexchange.com/2.3/questions/1234567789012345?site=stackoverflow",
        status_code=404,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_question(1234567789012345)


@pytest.mark.asyncio
async def test_github_api_unavailable_returns_empty_updates() -> None:
    """При недоступности GitHub API скраппер возвращает пустой список."""
    mock_client = AsyncMock()
    mock_client.fetch_pull_requests.side_effect = Exception("Connection refused")

    scrapper = GithubScrapper(mock_client)

    updates = await scrapper.check_for_updates(
        "https://github.com/org/repo",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert updates == []


@pytest.mark.asyncio
async def test_stackoverflow_api_unavailable_returns_empty_updates() -> None:
    """При недоступности StackOverflow API скраппер возвращает пустой список."""
    mock_client = AsyncMock()
    mock_client.fetch_question_details.side_effect = Exception("Timeout")

    scrapper = StackOverflowScrapper(mock_client)

    updates = await scrapper.check_for_updates(
        "https://stackoverflow.com/questions/12345",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert updates == []


@pytest.mark.asyncio
async def test_github_scrapper_handles_api_error_gracefully() -> None:
    """GitHub скраппер корректно обрабатывает ошибки API."""
    mock_client = AsyncMock()
    mock_client.fetch_pull_requests.return_value = []
    mock_request = httpx.Request("GET", "https://api.github.com/repos/org/repo/issues")
    mock_response = httpx.Response(500, request=mock_request)
    mock_client.fetch_issues.side_effect = httpx.HTTPStatusError(
        "Server Error", request=mock_request, response=mock_response
    )

    scrapper = GithubScrapper(mock_client)
    updates = await scrapper.check_for_updates(
        "https://github.com/org/repo",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert updates == []


@pytest.mark.asyncio
async def test_stackoverflow_scrapper_handles_api_error_gracefully() -> None:
    """StackOverflow скраппер корректно обрабатывает ошибки API."""
    mock_client = AsyncMock()
    mock_request = httpx.Request(
        "GET", "https://api.stackexchange.com/2.3/questions/12345"
    )
    mock_response = httpx.Response(500, request=mock_request)
    mock_client.fetch_question_details.side_effect = httpx.HTTPStatusError(
        "Server Error", request=mock_request, response=mock_response
    )

    scrapper = StackOverflowScrapper(mock_client)
    updates = await scrapper.check_for_updates(
        "https://stackoverflow.com/questions/12345",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert updates == []
