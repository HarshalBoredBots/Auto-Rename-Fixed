from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
from utils.logger import logger

_client: AsyncIOMotorClient | None = None
_db = None


async def connect_db():
    global _client, _db
    _client = AsyncIOMotorClient(Config.MONGO_URI)
    _db = _client[Config.MONGO_DB_NAME]
    # Ping to verify connection
    await _client.admin.command("ping")
    logger.info("MongoDB connected")
    return _db


async def get_db():
    global _db
    if _db is None:
        await connect_db()
    return _db


async def close_db():
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed")
