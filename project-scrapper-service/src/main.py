import uvicorn
import asyncio
import structlog

from src.api.app import create_app
from src.config import load_config

logger = structlog.get_logger(__name__)

config = load_config()
app = create_app(config)


async def main():
    host = config.server_host
    port = config.server_port

    uvicorn_config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(uvicorn_config)

    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка работы программы")
    except Exception as e:
        logger.error("Произошла ошибка в работе программы", error=str(e))
