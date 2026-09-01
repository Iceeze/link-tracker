import re
import structlog
from html import escape
from aiogram import Router, F
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message

from src.clients.scrapper import scrapper_client

logger = structlog.get_logger(__name__)

links_router = Router()

GITHUB_REPO_RE = re.compile(r"^https?://(www\.)?github\.com/([^/]+)/([^/]+)/?$")
SO_QUESTION_RE = re.compile(
    r"^https?://((ru|www)\.)?stackoverflow\.com/questions/(\d+)(/[^/]+)?/?$"
)


def parse_supported_url(url: str) -> tuple[str, tuple[str, ...]] | None:
    """Парсинг и валидация URL."""
    if match := GITHUB_REPO_RE.fullmatch(url):
        return "github", (match.group(2), match.group(3))
    if match := SO_QUESTION_RE.fullmatch(url):
        return "stackoverflow", (match.group(3),)
    return None


class TrackStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_tags = State()


class UntrackStates(StatesGroup):
    waiting_for_url = State()


@links_router.message(
    Command("cancel"),
    StateFilter(
        TrackStates.waiting_for_url,
        TrackStates.waiting_for_tags,
        UntrackStates.waiting_for_url,
    ),
)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Команда отмены выполнения команды."""
    if message.from_user is None:
        return
    logger.info("Получена команда /cancel", user_id=message.from_user.id)
    await state.clear()
    await message.answer("Отмена выполнения команды.")


@links_router.message(Command("track"))
async def cmd_track(message: Message, state: FSMContext) -> None:
    """Команда отслеживания ссылки."""
    if message.from_user is None:
        return
    logger.info("Получена команда /track", user_id=message.from_user.id)
    await state.set_state(TrackStates.waiting_for_url)
    await message.answer(
        "Пожалуйста, отправьте ссылку на репозиторий GitHub или вопрос StackOverflow.\n"
        "Для отмены введите /cancel."
    )


@links_router.message(StateFilter(TrackStates.waiting_for_url), ~F.text.startswith("/"))
async def process_url(message: Message, state: FSMContext) -> None:
    """Обработка URL от пользователя для отслеживания."""
    if message.text is None:
        return
    url = message.text.strip()

    parsed = parse_supported_url(url)
    if parsed is None:
        await message.answer(
            "Неподдерживаемая ссылка. Принимаются только ссылки на репозитории GitHub "
            "или вопросы StackOverflow.\n"
            "Примеры:\n"
            "• https://github.com/username/repository\n"
            "• https://stackoverflow.com/questions/123456"
        )
        return

    await state.update_data(url=url)

    await state.set_state(TrackStates.waiting_for_tags)
    await message.answer(
        "Теперь введите теги (через запятую) или отправьте 'нет', если теги не нужны.\n"
        "Пример: работа, баг"
    )


@links_router.message(
    StateFilter(TrackStates.waiting_for_tags), ~F.text.startswith("/")
)
async def process_tags(message: Message, state: FSMContext) -> None:
    """Обработка тэгов от пользователя."""
    if message.text is None or message.from_user is None:
        return
    tags_text = message.text.strip().lower()

    data = await state.get_data()
    url = data.get("url")
    if url is None:
        return

    tags = []
    if tags_text != "нет":
        tags = [t.strip() for t in tags_text.split(",")]

    await state.clear()

    success, response_msg = await scrapper_client.add_link(
        message.from_user.id, url, tags
    )

    if success:
        logger.info(
            "Пользователь добавил ссылку", user_id=message.from_user.id, url=url
        )
        await message.answer(
            f"Ссылка {url} добавлена в список отслеживаемых.",
            disable_web_page_preview=True,
        )
    else:
        logger.warning(
            "Ошибка добавления ссылки",
            user_id=message.from_user.id,
            reason=response_msg,
        )
        await message.answer(response_msg)


@links_router.message(Command("untrack"))
async def cmd_untrack(message: Message, state: FSMContext) -> None:
    """Команда удаления ссылки."""
    if message.from_user is None:
        return
    logger.info("Получена команда /untrack", user_id=message.from_user.id)
    await state.set_state(UntrackStates.waiting_for_url)
    await message.answer(
        "Какую ссылку вы хотите перестать отслеживать? Отправьте её URL.\n"
        "Для отмены введите /cancel."
    )


@links_router.message(
    StateFilter(UntrackStates.waiting_for_url), ~F.text.startswith("/")
)
async def process_untrack_url(message: Message, state: FSMContext) -> None:
    """Обработка URL от пользователя для удаления."""
    if message.text is None or message.from_user is None:
        return
    url = message.text.strip()

    await state.clear()

    success = await scrapper_client.remove_link(message.from_user.id, url)
    if success:
        logger.info("Пользователь удалил ссылку", user_id=message.from_user.id, url=url)
        await message.answer(
            f"Отслеживание ссылки {url} прекращено.", disable_web_page_preview=True
        )
    else:
        await message.answer(
            "Не удалось удалить ссылку. Возможно, вы её не отслеживали."
        )


@links_router.message(Command("list"))
async def cmd_list(message: Message, command: CommandObject) -> None:
    """Команда получения списка отслеживаемых ссылок.

    Поддерживает опциональную фильтрацию по тегу.
    Пользователь может ввести, например, "/list работа", и тогда будут показаны только
    ссылки с тегом "работа". Если тег не указан, показываются все ссылки.
    """
    if message.from_user is None:
        return
    logger.info("Получена команда /list", user_id=message.from_user.id)

    data = await scrapper_client.get_links(message.from_user.id)

    if data is None or data.size == 0:
        await message.answer("Вы пока не отслеживаете ни одной ссылки.")
        return

    links = data.links

    filter_tag = command.args
    if filter_tag:
        filter_tag = filter_tag.strip().lower()
        links = [lnk for lnk in links if filter_tag in lnk.tags]

        if not links:
            await message.answer(
                f"У вас нет отслеживаемых ссылок с тегом '{filter_tag}'."
            )
            return

    response_text = "📋 <b>Ваши отслеживаемые ссылки:</b>\n\n"
    for lnk in links:
        url = escape(str(lnk.url))
        tags = lnk.tags
        tags_escaped = escape(", ".join(tags)) if tags else ""
        tags_str = f"[Теги: {tags_escaped}]\n" if tags else ""
        response_text += f"🔗 {url}\n{tags_str}\n"

    await message.answer(
        response_text, disable_web_page_preview=True, parse_mode="HTML"
    )
