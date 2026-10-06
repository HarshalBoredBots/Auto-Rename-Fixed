import os

from wzgram import Client, filters
from wzgram.types import Message

from config import Config
from database.jobs import JobsDB
from database.users import UsersDB
from database.settings import BotSettingsDB
from torrent.manager import TorrentManager
from telegram.progress import ProgressTracker
from telegram.uploader import TelegramUploader
from utils.logger import logger
from utils.validation import is_magnet, is_torrent_url, is_http_url, safe_job_path


def register(
    app: Client,
    manager: TorrentManager,
    jobs_db: JobsDB,
    users_db: UsersDB,
    bs_db: BotSettingsDB,
    uploader: TelegramUploader,
):

    @app.on_message(filters.command("l") & filters.private)
    async def leech_cmd(client: Client, message: Message):
        user = message.from_user

        # Maintenance check (owner bypasses)
        if user.id != Config.OWNER_ID:
            if await bs_db.get_bot_toggle("maintenance_mode"):
                await message.reply(
                    "🛠 **Bot is currently under maintenance.**\n\nPlease try again later."
                )
                return

        parts = message.text.split(None, 1)
        if len(parts) < 2:
            await message.reply(
                "**Usage:** `/l <magnet|URL>`\n\nOr just send a `.torrent` file."
            )
            return

        source = parts[1].strip()
        await _process_source(client, message, source, jobs_db, users_db, bs_db, manager, uploader)

    @app.on_message(filters.document & filters.private)
    async def torrent_file_handler(client: Client, message: Message):
        doc = message.document
        if not doc:
            return
        fname = doc.file_name or ""
        if not fname.lower().endswith(".torrent"):
            return

        user = message.from_user

        # Maintenance check
        if user.id != Config.OWNER_ID:
            if await bs_db.get_bot_toggle("maintenance_mode"):
                await message.reply(
                    "🛠 **Bot is currently under maintenance.**\n\nPlease try again later."
                )
                return
            # Toggle: allow torrent files?
            if not await bs_db.get_bot_toggle("allow_torrent_file"):
                await message.reply("❌ `.torrent` file uploads are disabled.")
                return

        status_msg = await message.reply("⏳ Downloading .torrent file…")
        try:
            dl_dir = os.path.join(Config.DOWNLOAD_DIR, "torrent_files")
            os.makedirs(dl_dir, exist_ok=True)
            file_path = await client.download_media(
                message,
                file_name=os.path.join(dl_dir, doc.file_id + ".torrent"),
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ Failed to download .torrent file: {e}")
            return

        # Upsert user record
        await users_db.upsert_user(user.id, username=user.username, first_name=user.first_name)

        await _submit_job(
            client, message, status_msg,
            source=file_path, source_type="file_path",
            jobs_db=jobs_db, manager=manager, uploader=uploader,
        )


async def _process_source(client, message, source, jobs_db, users_db, bs_db, manager, uploader):
    user = message.from_user

    if is_magnet(source):
        # Toggle check (owner bypasses)
        if user.id != Config.OWNER_ID and not await bs_db.get_bot_toggle("allow_magnet"):
            await message.reply("❌ Magnet links are disabled.")
            return
        source_type = "magnet"
    elif is_torrent_url(source):
        if user.id != Config.OWNER_ID and not await bs_db.get_bot_toggle("allow_torrent_url"):
            await message.reply("❌ Torrent URLs are disabled.")
            return
        source_type = "url"
    elif is_http_url(source):
        if user.id != Config.OWNER_ID and not await bs_db.get_bot_toggle("allow_torrent_url"):
            await message.reply("❌ Torrent URLs are disabled.")
            return
        source_type = "url"
    else:
        await message.reply("❌ Invalid input. Send a magnet link, `.torrent` URL, or `.torrent` file.")
        return

    # Upsert user
    await users_db.upsert_user(user.id, username=user.username, first_name=user.first_name)

    status_msg = await message.reply("⏳ Validating…")
    await _submit_job(client, message, status_msg, source, source_type, jobs_db, manager, uploader)


async def _submit_job(client, message, status_msg, source, source_type, jobs_db, manager, uploader):
    user_id = message.from_user.id
    chat_id = message.chat.id

    job = await manager.submit_job(
        user_id=user_id,
        source=source,
        source_type=source_type,
        client_msg_id=status_msg.id,
        chat_id=chat_id,
    )
    if not job:
        max_q = await manager._max_queue_per_user()
        await status_msg.edit_text(
            f"❌ Queue full ({max_q} max). Use /cancel to free a slot."
        )
        return

    job_id = job["job_id"]

    tracker = ProgressTracker(client, chat_id, status_msg.id)
    uploader.register_progress_tracker(job_id, tracker)

    user_jobs = await jobs_db.get_user_queue(user_id)
    position = len(user_jobs)
    name = source[:40] + "…" if len(source) > 40 else source

    text = (
        f"📥 **Torrent Added**\n\n"
        f"🔗 `{name}`\n\n"
        f"**Position:** #{position}\n"
        f"**Status:** Waiting…\n\n"
        f"Use /s to check progress."
    )
    await status_msg.edit_text(text)
    logger.info(f"Job {job_id} created for user {user_id}")
