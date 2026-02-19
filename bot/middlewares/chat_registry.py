from typing import Any, Awaitable, Callable, Dict, List

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update


class ChatRegistryMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            chat_id = None
            if event.message:
                chat_id = event.message.chat.id
            elif event.callback_query and event.callback_query.message:
                chat_id = event.callback_query.message.chat.id

            if chat_id is not None:
                from main import processor
                processor.register_chat(chat_id)

        return await handler(event, data)
