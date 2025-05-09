import os
import logging
from datetime import datetime
from typing import Optional, Tuple, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from sqlalchemy import BigInteger, String, DateTime, select, distinct
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from dotenv import load_dotenv
from telethon import TelegramClient

# Настройка логирования
logging.basicConfig(
    filename='log.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Инициализация Telethon клиента
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
telethon_client = TelegramClient("channel_fetcher", API_ID, API_HASH)

# Асинхронная БД


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_url: Mapped[str] = mapped_column(String, nullable=False)
    channel_name: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False)


engine = create_async_engine("sqlite+aiosqlite:///channels.db")
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def create_tables() -> None:
    logging.info("Создание таблиц в базе данных")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def get_original_channel(message: Message) -> Optional[Tuple[int, str]]:
    """Рекурсивно ищет первоначальный канал в цепочке пересылок."""
    if message.forward_from_chat:
        channel = message.forward_from_chat
        channel_url = f"https://t.me/{channel.username}" if channel.username else f"chat_id:{channel.id}"
        return (channel.id, channel_url)

    if message.forward_from_message_id and message.forward_from:
        # Если сообщение переслано из другого сообщения (например, из группы в канал, потом в бота)
        # В Aiogram нет прямого доступа к исходному сообщению, поэтому берём только текущий пересланный чат
        return None  # Можно добавить дополнительную логику через API Telegram

    return None


async def fetch_channel_name(channel_url: str) -> str:
    """Получает название канала по его URL с использованием Telethon."""
    try:
        async with telethon_client:
            entity = await telethon_client.get_entity(channel_url)
            return entity.title if hasattr(entity, 'title') else "Неизвестно"
    except Exception as e:
        logging.error(f"Ошибка при получении названия канала: {str(e)}")
        return "Неизвестно"


@dp.message(F.forward_from_chat)
async def handle_forwarded_message(message: Message) -> None:
    logging.info("Обработка пересланного сообщения")
    original_channel = get_original_channel(message)
    if not original_channel:
        logging.warning("Не удалось определить исходный канал")
        await message.reply("❌ Не удалось определить исходный канал.")
        return

    channel_id, channel_url = original_channel
    channel_name = message.forward_from_chat.title if message.forward_from_chat else "Неизвестно"

    async with async_session() as session:
        try:
            session.add(Channel(
                channel_id=channel_id,
                channel_url=channel_url,
                channel_name=channel_name
            ))
            await session.commit()
            logging.info(f"Канал сохранён: {channel_url} ({channel_name})")
            await message.reply(f"✅ Канал сохранён: {channel_url} ({channel_name})")
        except Exception as e:
            logging.error(f"Ошибка при сохранении канала: {str(e)}")
            await session.rollback()
            await message.reply(f"❌ Ошибка: {str(e)}")


@dp.message(F.forward_from)
async def handle_forwarded_from_bot(message: Message) -> None:
    logging.info("Обработка пересланного сообщения от другого бота")
    if message.forward_from.is_bot:
        bot_name = message.forward_from.username
        bot_id = message.forward_from.id
        logging.info(f"Сообщение переслано от бота: {bot_name} (ID: {bot_id})")

        # Извлечение ссылки на канал из текста сообщения
        if message.entities:
            for entity in message.entities:
                if entity.type == "text_link" and entity.url.startswith("https://t.me/"):
                    channel_url = entity.url
                    # Получаем название канала
                    channel_name = await fetch_channel_name(channel_url)
                    async with async_session() as session:
                        try:
                            session.add(Channel(
                                channel_id=bot_id,  # Используем ID бота как временный идентификатор
                                channel_url=channel_url,
                                channel_name=channel_name
                            ))
                            await session.commit()
                            logging.info(
                                f"Канал сохранён: {channel_url} ({channel_name})")
                            await message.reply(f"✅ Канал сохранён: {channel_url} ({channel_name})")
                        except Exception as e:
                            logging.error(
                                f"Ошибка при сохранении канала: {str(e)}")
                            await session.rollback()
                            await message.reply(f"❌ Ошибка: {str(e)}")
                    return

        logging.warning("Не удалось извлечь ссылку на канал из сообщения")
        await message.reply("❌ Не удалось извлечь ссылку на канал из сообщения.")
    else:
        logging.warning("Сообщение не от бота")
        await message.reply("❌ Это сообщение не от бота.")


@dp.message(Command("channels"))
async def send_channels_list(message: Message) -> None:
    logging.info("Запрос списка url каналов")
    async with async_session() as session:
        try:
            result = await session.execute(
                select(distinct(Channel.channel_url)))
            channels = result.scalars().all()

            if channels:
                response = "📋 Список url каналов:\n" + "\n".join(channels)
                logging.info("Список url каналов отправлен")
                await message.answer(response)
            else:
                logging.info("Нет сохранённых каналов")
                await message.reply("ℹ️ Нет сохранённых каналов.")
        except Exception as e:
            logging.error(f"Ошибка при запросе списка url каналов: {str(e)}")
            await message.reply(f"❌ Ошибка: {str(e)}")


@dp.message(Command("name_channels"))
async def send_channels_list(message: Message) -> None:
    logging.info("Запрос списка названий каналов")
    async with async_session() as session:
        try:
            result = await session.execute(
                select(distinct(Channel.channel_name)))
            channels = result.scalars().all()

            if channels:
                response = "📋 Список названий каналов:\n" + "\n".join(channels)
                logging.info("Список названий каналов отправлен")
                await message.answer(response)
            else:
                logging.info("Нет сохранённых каналов")
                await message.reply("ℹ️ Нет сохранённых каналов.")
        except Exception as e:
            logging.error(
                f"Ошибка при запросе списка названий каналов: {str(e)}")
            await message.reply(f"❌ Ошибка: {str(e)}")


async def main() -> None:
    await create_tables()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
