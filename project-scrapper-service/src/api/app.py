import traceback
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.clients import ValkeyClient
from src.config import Settings
from src.sre.utils import limiter
from src.exceptions import ApiException
from src.schemas import ApiErrorResponse
from src.api import chat, links
from src.scheduler import start_scheduler, stop_scheduler
from src.database import run_migrations, get_db_engine, get_db_session, get_asyncpg_pool
from src.repository.factory import create_repository_factory
from src.services.notification_service import get_notification_service

logger = structlog.get_logger(__name__)


def create_app(
    config: Settings, skip_migrations: bool = False, use_scheduler: bool = True
) -> FastAPI:
    """Создаёт отдельное приложение FastAPI."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = None
        pool = None
        notification_service = None
        try:
            if not skip_migrations:
                run_migrations(config)

            engine = get_db_engine(config)
            session_factory = get_db_session(engine)
            pool = await get_asyncpg_pool(config)

            repository_factory = create_repository_factory(
                session_factory=session_factory,
                pool=pool,
                access_type=config.access_type,
            )

            valkey_client = ValkeyClient(
                host=config.valkey_host,
                port=config.valkey_port,
                ttl=config.valkey_ttl,
            )

            app.state.config = config
            app.state.engine = engine
            app.state.session_factory = session_factory
            app.state.pool = pool
            app.state.valkey_client = valkey_client
            app.state.repository_factory = repository_factory

            notification_service = get_notification_service(config)
            chat_service = repository_factory.create_chat_service()
            link_service = repository_factory.create_link_service()

            if use_scheduler:
                await start_scheduler(chat_service, link_service, notification_service)

            yield
        except Exception as e:
            logger.error("Ошибка при старте приложения", error=str(e))
            raise

        finally:
            if use_scheduler and notification_service:
                await stop_scheduler(notification_service)
            if pool:
                await pool.close()
            if engine:
                await engine.dispose()
            if valkey_client:
                await valkey_client.aclose()

    app = FastAPI(
        title="Scrapper Service",
        description="Сервис для фонового отслеживания изменений по ссылкам",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(links.router)
    app.include_router(chat.router)

    async def rate_limit_handler(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, RateLimitExceeded)
        return _rate_limit_exceeded_handler(request, exc)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(ApiException)
    async def api_exception_handler(request: Request, exc: ApiException):
        """Перехватчик кастомных бизнес-ошибок (чат не найден и т.д.)."""
        error_response = ApiErrorResponse(
            description=exc.description,
            code=exc.code,
            exceptionName=exc.__class__.__name__,
            exceptionMessage=str(exc),
            stacktrace=traceback.format_exception(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=exc.status_code, content=error_response.model_dump()
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Перехватчик ошибок валидации Pydantic."""
        error_response = ApiErrorResponse(
            description="Некорректные параметры запроса",
            code="400",
            exceptionName=exc.__class__.__name__,
            exceptionMessage=str(exc.errors()),
            stacktrace=traceback.format_exception(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content=error_response.model_dump()
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Перехватчик стандартных HTTP ошибок."""
        error_response = ApiErrorResponse(
            description=str(exc.detail),
            code=str(exc.status_code),
            exceptionName=exc.__class__.__name__,
            exceptionMessage=str(exc.detail),
            stacktrace=traceback.format_exception(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=exc.status_code, content=error_response.model_dump()
        )

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        """Health эндпоинт для проверки состояния сервиса."""
        return {"status": "Scrapper is up and running!"}

    return app
