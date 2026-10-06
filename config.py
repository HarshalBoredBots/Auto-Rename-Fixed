import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Telegram
    API_ID: int = int(os.environ["API_ID"])
    API_HASH: str = os.environ["API_HASH"]
    BOT_TOKEN: str = os.environ["BOT_TOKEN"]

    # MongoDB
    MONGO_URI: str = os.environ["MONGO_URI"]
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "TorrentBot")

    # Storage
    DOWNLOAD_DIR: str = os.getenv("DOWNLOAD_DIR", "/downloads")

    # Queue limits (env-level defaults; MongoDB overrides these at runtime)
    MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "1"))
    MAX_CONCURRENT_UPLOADS: int = int(os.getenv("MAX_CONCURRENT_UPLOADS", "1"))
    MAX_QUEUE_PER_USER: int = int(os.getenv("MAX_QUEUE_PER_USER", "5"))

    # aria2 RPC
    ARIA2_RPC_HOST: str = os.getenv("ARIA2_RPC_HOST", "127.0.0.1")
    ARIA2_RPC_PORT: int = int(os.getenv("ARIA2_RPC_PORT", "6800"))
    ARIA2_RPC_SECRET: str = os.getenv("ARIA2_RPC_SECRET", "")

    # Seeding
    SEED_TIME: int = int(os.getenv("SEED_TIME", "0"))
    SEED_RATIO: float = float(os.getenv("SEED_RATIO", "0"))

    # Admin
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))

    # Dump channel (env-level default; overridden by MongoDB once set via /bs)
    DUMP_CHANNEL_ID: int | None = int(os.getenv("DUMP_CHANNEL_ID", "0")) or None

    # Limits
    MAX_TORRENT_SIZE_GB: float = float(os.getenv("MAX_TORRENT_SIZE_GB", "20"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Progress update throttle (seconds)
    PROGRESS_UPDATE_INTERVAL: float = float(os.getenv("PROGRESS_UPDATE_INTERVAL", "5"))
