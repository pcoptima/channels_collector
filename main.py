import os
import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from sqlalchemy import BigInteger, String, DateTime, select, distinct
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Настройка логирования
logging.basicConfig(
    filename="log.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Инициализация асинхронной БД (SQLite)


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_url: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)


# Асинхронный движок и сессия
engine = create_async_engine("sqlite+aiosqlite:///channels.db")
async_session = async_sessionmaker(engine, expire_on_commit=False)

# Создание таблиц (асинхронно)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Обработка пересланных сообщений


@dp.message(F.forward_from_chat)
async def handle_forwarded_message(message: Message):
    chat = message.forward_from_chat
    channel_url = f"https://t.me/{chat.username}" if chat.username else f"chat_id:{chat.id}"

    async with async_session() as session:
        try:
            session.add(Channel(
                channel_id=chat.id,
                channel_url=channel_url
            ))
            await session.commit()
            logging.info(f"Канал сохранён: {channel_url}")
            await message.reply(f"✅ Канал сохранён: {channel_url}")
        except Exception as e:
            await session.rollback()
            logging.error(f"Ошибка при сохранении канала: {str(e)}")
            await message.reply(f"❌ Ошибка: {str(e)}")

# Обработка команды /channels


@dp.message(Command("channels"))
async def send_channels_list(message: Message):
    async with async_session() as session:
        try:
            result = await session.execute(
                select(distinct(Channel.channel_url)))
            channels = result.scalars().all()

            if channels:
                response = "📋 Список каналов:\n" + "\n".join(channels)
                logging.info("Список каналов отправлен.")
                await message.reply(response)
            else:
                logging.info("Нет сохранённых каналов.")
                await message.reply("ℹ️ Нет сохранённых каналов.")
        except Exception as e:
            logging.error(f"Ошибка при получении списка каналов: {str(e)}")
            await message.reply(f"❌ Ошибка: {str(e)}")

# Запуск бота


async def main():
    await create_tables()  # Создаём таблицы при старте
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
