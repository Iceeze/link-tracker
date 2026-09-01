import uvicorn
import structlog
import asyncio

from src.api.app import create_app
from src.config import config

# configure_logging()
logger = structlog.get_logger(__name__)

app = create_app(config)


async def main():
    port = config.server_port
    host = config.server_host

    uvicorn_config = uvicorn.Config(app, host=host, port=port, log_config=None)
    server = uvicorn.Server(uvicorn_config)

    try:
        logger.info("Запуск веб-сервера для Bot API...", host=host, port=port)
        await server.serve()
    finally:
        logger.info("Остановка приложения...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка работы программы")
    except Exception as e:
        logger.error("Произошла ошибка в работе программы", error=str(e))
