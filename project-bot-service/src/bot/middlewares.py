from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from aiogram.fsm.context import FSMContext


class CancelDialogMiddleware(BaseMiddleware):
    """Middleware для отмены FSM-состояния при вводе любой команды."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.text is None:
            return await handler(event, data)

        if event.text and event.text.startswith("/"):
            state: FSMContext | None = data.get("state")
            if state:
                current_state = await state.get_state()
                if current_state is not None:
                    if event.text.strip().startswith("/cancel"):
                        return await handler(event, data)
                    await state.clear()

        return await handler(event, data)
