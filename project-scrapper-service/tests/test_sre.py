import pytest
import time
import httpx
from unittest.mock import AsyncMock, patch
from fastapi import Request

from src.sre.circuit_breaker import StatesCircuitBreaker, CircuitBreakerOpenException
from src.clients import GithubClient
from src.services import FallbackNotificationService
from src.sre.utils import breaker


@pytest.fixture
def github_client():
    client = GithubClient(base_url="https://test.api")
    breaker.state = StatesCircuitBreaker.CLOSED
    breaker.history.clear()
    yield client


# --- FR-1: Timeout ---


@pytest.mark.asyncio
async def test_tc_1_1_timeout(github_client):
    """TC-1.1: Превышение времени ожидания."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(httpx.TimeoutException):
            await github_client.fetch_repo("owner", "repo")


# --- FR-2: Retry ---


@pytest.mark.asyncio
async def test_tc_2_1_retry_on_5xx(github_client):
    """TC-2.1: Retry на 5xx. Ответ 500 -> 500 -> 200."""
    responses = [
        httpx.Response(500, request=httpx.Request("GET", "url")),
        httpx.Response(500, request=httpx.Request("GET", "url")),
        httpx.Response(
            200,
            json={
                "id": 1,
                "full_name": "owner/repo",
                "updated_at": "2024-01-01T00:00:00Z",
                "pushed_at": "2024-01-01T00:00:00Z",
            },
            request=httpx.Request("GET", "url"),
        ),
    ]

    with patch("httpx.AsyncClient.get", side_effect=responses) as mock_get:
        result = await github_client.fetch_repo("owner", "repo")

        assert result.id == 1
        assert mock_get.call_count == 3


@pytest.mark.asyncio
async def test_tc_2_2_no_retry_on_4xx(github_client):
    """TC-2.2: Отсутствие Retry на 4xx."""
    response_400 = httpx.Response(400, request=httpx.Request("GET", "url"))

    with patch("httpx.AsyncClient.get", return_value=response_400) as mock_get:
        with pytest.raises(httpx.HTTPStatusError):
            await github_client.fetch_repo("owner", "repo")

        assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_tc_2_3_constant_backoff(github_client):
    """TC-2.3: Соблюдение интервала retry (constant backoff)."""
    response_500 = httpx.Response(500, request=httpx.Request("GET", "url"))

    start_time = time.time()
    with patch("httpx.AsyncClient.get", return_value=response_500) as mock_get:
        with pytest.raises(httpx.HTTPStatusError):  # Упадет после 3 попыток
            await github_client.fetch_repo("owner", "repo")

    elapsed = time.time() - start_time
    # 3 попытки -> 2 ожидания по `retry_wait_time` (1 секунда).
    # Итоговое время должно быть около 2 секунд.
    assert 2.0 <= elapsed < 3.0
    assert mock_get.call_count == 3


# --- FR-4: Rate Limiting ---


@pytest.mark.asyncio
async def test_tc_3_1_rate_limiting():
    """TC-3.1: Превышение лимита."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    app = FastAPI()
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/test")
    @limiter.limit("2/minute")
    async def route(request: Request):
        return {"status": "ok"}

    client = TestClient(app)

    # Первые два запроса в пределах лимита
    assert client.get("/test").status_code == 200
    assert client.get("/test").status_code == 200
    # Третий запрос должен получить HTTP 429
    assert client.get("/test").status_code == 429


# --- FR-5-9: Circuit Breaker ---


@pytest.mark.asyncio
async def test_tc_4_1_cb_transition_to_open(github_client):
    """TC-4.1: Переход в OPEN и немедленное отклонение последующих запросов."""
    error_mock = AsyncMock(
        side_effect=httpx.RequestError(
            "Network Error", request=httpx.Request("GET", "url")
        )
    )

    with patch("httpx.AsyncClient.get", error_mock):
        # Делаем window_size вызовов, чтобы заполнить историю ошибок
        for _ in range(breaker.window_size):
            with pytest.raises(httpx.RequestError):
                await github_client.fetch_repo("owner", "repo")

        assert breaker.state == StatesCircuitBreaker.OPEN

        start_time = time.time()
        with pytest.raises(CircuitBreakerOpenException):
            await github_client.fetch_repo("owner", "repo")
        elapsed = time.time() - start_time
        assert elapsed < 0.1


@pytest.mark.asyncio
async def test_tc_4_2_cb_half_open_to_closed(github_client):
    """TC-4.2: HALF-OPEN -> CLOSED состояние."""
    breaker.state = StatesCircuitBreaker.OPEN
    breaker.opened_at = time.time() - 10

    success_response = httpx.Response(
        200,
        json={
            "id": 1,
            "full_name": "owner/repo",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
        },
        request=httpx.Request("GET", "url"),
    )

    with patch("httpx.AsyncClient.get", return_value=success_response):
        await github_client.fetch_repo("owner", "repo")

    assert breaker.state == StatesCircuitBreaker.CLOSED


@pytest.mark.asyncio
async def test_tc_4_3_cb_half_open_to_open(github_client):
    """TC-4.3: HALF-OPEN состояние -> возврат в OPEN при ошибке."""
    breaker.state = StatesCircuitBreaker.OPEN
    breaker.opened_at = time.time() - 10

    error_mock = AsyncMock(
        side_effect=httpx.RequestError(
            "Network Error", request=httpx.Request("GET", "url")
        )
    )

    with patch("httpx.AsyncClient.get", error_mock):
        with pytest.raises(httpx.RequestError):
            await github_client.fetch_repo("owner", "repo")

    assert breaker.state == StatesCircuitBreaker.OPEN


# --- FR-10: Fallback ---


@pytest.mark.asyncio
async def test_tc_5_1_fallback_transport():
    """TC-5.1: Падение основного транспорта, использование альтернативного."""
    primary_mock = AsyncMock()
    primary_mock.send_update.return_value = False

    secondary_mock = AsyncMock()
    secondary_mock.send_update.return_value = True

    fallback_service = FallbackNotificationService(
        primary=primary_mock, secondary=secondary_mock
    )

    result = await fallback_service.send_update(
        chat_id=1, link=AsyncMock(), author="user1", description="update"
    )

    primary_mock.send_update.assert_called_once()
    secondary_mock.send_update.assert_called_once()
    assert result is True
