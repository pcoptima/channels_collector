from telethon import TelegramClient
import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

# Укажите имя файла для сохранения сессии
SESSION_NAME = "channel_fetcher"


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    async with client:
        print("Авторизация завершена. Сессия сохранена.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
