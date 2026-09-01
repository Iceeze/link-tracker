import structlog
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.schemas import LinkResponse, LinkUpdateDetails
from src.clients import GithubClient, StackOverflowClient
from src.config import load_config
from src.services import (
    ChatService,
    LinkService,
    NotificationService,
    KafkaNotificationService,
    FallbackNotificationService,
)
from src.services.scrappers import BaseScrapper, GithubScrapper, StackOverflowScrapper

logger = structlog.get_logger(__name__)
config = load_config()

github_client = GithubClient(config.github_base_url, config.github_token)
so_client = StackOverflowClient(config.stackoverflow_base_url)

github_scrapper: BaseScrapper = GithubScrapper(github_client)
stackoverflow_scrapper: BaseScrapper = StackOverflowScrapper(so_client)

_scheduler: AsyncIOScheduler | None = None


def format_description(update: LinkUpdateDetails) -> str:
    """Сформировать описание изменения."""
    lines: list[str] = []

    type_label = update.update_type.replace("_", " ").upper()
    lines.append(f"{update.created_at}")
    lines.append(f"{type_label}: {update.title} by @{update.username}")
    if update.preview:
        lines.append(f"  Preview: {update.preview}")
    lines.append(f"  URL: {update.url}")

    description = "\n".join(lines).rstrip()

    return description


async def check_updates(
    chat_service: ChatService,
    link_service: LinkService,
    notification_service: NotificationService,
) -> None:
    """Основной цикл проверки обновлений.

    Логика:
    1. Получаем все чаты и их ссылки.
    2. Группируем ссылки по URL, чтобы избежать дублирующих запросов.
    3. Для каждого уникального URL определяем scrapper и делаем один запрос к API.
    4. Отправляем уведомления.
    """
    logger.info("Запуск проверки обновлений по ссылкам...")

    chat_offset = 0
    batch_size_db = config.batch_size_db
    while True:
        subscriptions: dict[str, list[tuple[int, LinkResponse]]] = {}
        chat_ids = await chat_service.get_all_chats(
            limit=batch_size_db, offset=chat_offset
        )
        if not chat_ids:
            break

        for chat_id in chat_ids:
            link_offset = 0
            while True:
                links = await link_service.get_links(
                    chat_id, limit=batch_size_db, offset=link_offset
                )
                if not links:
                    break

                for link in links:
                    url_str = str(link.url)
                    subscriptions.setdefault(url_str, []).append((chat_id, link))

                link_offset += batch_size_db

        chat_offset += batch_size_db

        for url, subscribers in subscriptions.items():
            min_last_updated = None
            for _, link in subscribers:
                if link.updated_at is None:
                    min_last_updated = None
                    break
                if min_last_updated is None or link.updated_at < min_last_updated:
                    min_last_updated = link.updated_at

            logger.info(
                "Проверка ссылки",
                url=url,
                subscribers_count=len(subscribers),
                min_last_updated=(
                    min_last_updated.isoformat() if min_last_updated else None
                ),
            )

            scrapper = _get_scrapper_for_url(url)
            if scrapper is None:
                logger.warning("Неподдерживаемый тип ссылки", url=url)
                continue

            try:
                updates = await scrapper.check_for_updates(
                    url, min_last_updated, config.batch_size_scrapper
                )
            except Exception as e:
                logger.error(
                    "Ошибка при проверке обновлений, пропускаем URL",
                    url=url,
                    error=str(e),
                )
                continue

            if not updates:
                logger.info("Нет обновлений", url=url)
                continue

            for chat_id, link in subscribers:
                for update in updates:
                    logger.info(
                        "Отправляем уведомление об обновлении",
                        chat_id=chat_id,
                        url=url,
                        update_type=update.update_type,
                    )
                    author = update.username
                    description = format_description(update)
                    success = await notification_service.send_update(
                        chat_id, link, author, description
                    )

                    if success:
                        now = datetime.now(tz=timezone.utc)
                        await link_service.update_link_updated_at(chat_id, url, now)
                        logger.info(
                            "Ссылка обновлена после успешной отправки уведомлений",
                            chat_id=chat_id,
                            url=url,
                        )
                    else:
                        logger.error(
                            "Не удалось отправить уведомления, ссылка не обновлена",
                            chat_id=chat_id,
                            url=url,
                        )

    logger.info("Проверка обновлений завершена")


def _get_scrapper_for_url(url: str) -> BaseScrapper | None:
    """Определить какой scrapper использовать для URL."""
    if "github.com" in url:
        return github_scrapper
    elif "stackoverflow.com" in url:
        return stackoverflow_scrapper
    return None


async def start_scheduler(
    chat_service: ChatService,
    link_service: LinkService,
    notification_service: NotificationService,
) -> None:
    """Инициализация и запуск планировщика APScheduler."""
    global _scheduler

    if isinstance(
        notification_service, (KafkaNotificationService, FallbackNotificationService)
    ):
        await notification_service.start()

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        check_updates,
        "interval",
        seconds=config.interval_seconds,
        kwargs={
            "chat_service": chat_service,
            "link_service": link_service,
            "notification_service": notification_service,
        },
    )
    _scheduler.start()
    logger.info(
        "Планировщик задач запущен",
        interval_seconds=config.interval_seconds,
        batch_size_scrapper=config.batch_size_scrapper,
        batch_size_db=config.batch_size_db,
    )


async def stop_scheduler(notification_service: NotificationService) -> None:
    """Остановка планировщика задач."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=True)
        _scheduler = None
        logger.info("Планировщик задач остановлен")

    if isinstance(
        notification_service, (KafkaNotificationService, FallbackNotificationService)
    ):
        await notification_service.stop()
