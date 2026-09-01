import pytest
import traceback
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from src.api.updates import router, get_bot
from src.schemas import ApiErrorResponse

app_for_test = FastAPI()

app_for_test.include_router(router)


@app_for_test.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_response = ApiErrorResponse(
        description="Некорректные параметры запроса",
        code="400",
        exceptionName=exc.__class__.__name__,
        exceptionMessage=str(exc.errors()),
        stacktrace=traceback.format_exception(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(status_code=400, content=error_response.model_dump())


class DummyBot:
    async def send_message(self, *args, **kwargs):
        return True


app_for_test.dependency_overrides[get_bot] = lambda: DummyBot()


@pytest.fixture(scope="module")
def client():
    with TestClient(app_for_test) as c:
        yield c


def test_correct_update_request_returns_200(client: TestClient) -> None:
    """Тест 1: Корректный запрос к сервису Бота."""
    valid_payload = {
        "id": 1,
        "url": "https://example.com",
        "description": "Новый коммит",
        "tgChatIds": [12345, 67890],
    }

    response = client.post("/updates", json=valid_payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_incorrect_update_request_returns_400(client: TestClient) -> None:
    """Тест 2: Некорректный запрос к сервису Бота (нет поля description)."""
    invalid_payload = {"id": 1, "url": "https://example.com", "tgChatIds": [12345]}

    response = client.post("/updates", json=invalid_payload)

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "400"
    assert "RequestValidationError" in data["exceptionName"]
