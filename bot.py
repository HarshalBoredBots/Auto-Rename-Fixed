"""
Telegram Torrent / Leech Bot
Main entrypoint: initialises all components and starts the bot.
"""
import asyncio
import os

from wzgram import Client

from config import Config
from database.mongo import connect_db, close_db
from database.jobs import JobsDB
from database.users import UsersDB
from database.settings import BotSettingsDB
from torrent.aria2 import aria2
from torrent.manager import TorrentManager
from telegram.uploader import TelegramUploader
from utils.cleanup import startup_cleanup
from utils.logger import logger

import handlers.start as h_start
import handlers.help as h_help
import handlers.leech as h_leech
import handlers.status as h_status
import handlers.queue as h_queue
import handlers.cancel as h_cancel
import handlers.settings as h_settings
import handlers.admin as h_admin
import handlers.botsettings as h_bs


async def main():
    logger.info("Bot starting…")

    # ── Connect MongoDB ────────────────────────────────────────────────────
    db = await connect_db()
    jobs_db = JobsDB(db)
    users_db = UsersDB(db)
    bs_db = BotSettingsDB(db)

    await jobs_db.ensure_indexes()
    await users_db.ensure_indexes()
    await bs_db.ensure_indexes()
    logger.info("MongoDB indexes ensured")

    # Initialise bot settings document (creates if absent, applies env defaults)
    await bs_db.get_bot_settings()
    logger.info("Bot settings document ready")

    # ── Startup recovery ───────────────────────────────────────────────────
    await startup_cleanup(Config.DOWNLOAD_DIR, jobs_db)
    os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)

    # ── Start aria2 ────────────────────────────────────────────────────────
    await aria2.start_process()

    # ── Create Telegram client ─────────────────────────────────────────────
    app = Client(
        name="torrent_bot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        workdir="/tmp",
    )

    # ── Create manager + uploader ──────────────────────────────────────────
    manager = TorrentManager(jobs_db=jobs_db, users_db=users_db, bs_db=bs_db)
    uploader = TelegramUploader(client=app, jobs_db=jobs_db, users_db=users_db, bs_db=bs_db)
    manager.set_uploader(uploader)

    # ── Register handlers ──────────────────────────────────────────────────
    h_start.register(app)
    h_help.register(app)
    h_leech.register(
        app,
        manager=manager,
        jobs_db=jobs_db,
        users_db=users_db,
        bs_db=bs_db,
        uploader=uploader,
    )
    h_status.register(app, jobs_db=jobs_db)
    h_queue.register(app, jobs_db=jobs_db)
    h_cancel.register(app, jobs_db=jobs_db, manager=manager)
    h_settings.register(app, users_db=users_db)
    h_admin.register(app, jobs_db=jobs_db, users_db=users_db, manager=manager)
    h_bs.register(app, bs_db=bs_db, jobs_db=jobs_db, users_db=users_db)

    # ── Start bot ──────────────────────────────────────────────────────────
    await app.start()
    me = await app.get_me()
    logger.info(f"Bot started as @{me.username}")

    # ── Keep alive ─────────────────────────────────────────────────────────
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received")
    finally:
        logger.info("Shutting down…")
        await app.stop()
        await aria2.close()
        await close_db()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
