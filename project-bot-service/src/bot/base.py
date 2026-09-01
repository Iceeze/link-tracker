from aiogram import Bot, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, Message
import structlog

from src.config import config
from src.clients.scrapper import scrapper_client

logger = structlog.get_logger(__name__)
base_router = Router()


def _build_help_text(commands: dict[str, str]) -> str:
    lines = ["Список доступных команд:"]
    lines.extend(f"/{name} - {description}" for name, description in commands.items())
    return "\n".join(lines)


@base_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработка команды /start."""
    if message.from_user is None:
        return
    logger.info("Получена команда /start", user_id=message.from_user.id)
    try:
        await scrapper_client.register_chat(message.from_user.id)
    except Exception as e:
        logger.error("Ошибка при регистрации чата", error=str(e))
    await message.answer(
        "Добро пожаловать!\n" "Используйте /help, чтобы посмотреть доступные команды."
    )


@base_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Обработка команды /help."""
    if message.from_user is None:
        return
    logger.info("Получена команда /help", user_id=message.from_user.id)
    help_text = _build_help_text(config.bot_commands)
    await message.answer(help_text)


async def set_commands(bot: Bot, commands: dict[str, str]) -> None:
    """Устанавливает команды бота в меню Telegram."""
    logger.info("Настройка команд бота...", commands=commands)

    commands_list: list[BotCommand] = [
        BotCommand(command=cmd, description=desc) for cmd, desc in commands.items()
    ]

    success: bool = await bot.set_my_commands(
        commands_list, scope=BotCommandScopeAllPrivateChats()
    )
    if success:
        logger.info("Команды успешно установлены.")
    else:
        logger.warning("Не удалось установить команды.")
