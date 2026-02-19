import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import control, main_menu, settings
from bot.middlewares.chat_registry import ChatRegistryMiddleware
from config import BOT_TOKEN, LOG_LEVEL
from core.order_processor import OrderProcessor
from db.engine import init_db

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
processor = OrderProcessor(bot)


async def main() -> None:
    await init_db()

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ChatRegistryMiddleware())

    dp.include_router(main_menu.router)
    dp.include_router(settings.router)
    dp.include_router(control.router)

    loop = asyncio.get_running_loop()
    processor.set_loop(loop)

    logger.info("Bot started")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
