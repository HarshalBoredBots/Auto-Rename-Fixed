import asyncio
import os
import shutil

from wzgram import Client, filters
from wzgram.types import Message

from config import Config
from database.jobs import JobsDB
from database.users import UsersDB
from torrent.manager import TorrentManager
from utils.formatting import human_size
from utils.logger import logger


def owner_only(func):
    """Decorator: only allow OWNER_ID."""
    async def wrapper(client, message: Message):
        if message.from_user.id != Config.OWNER_ID:
            await message.reply("❌ Admin only.")
            return
        await func(client, message)
    return wrapper


def register(app: Client, jobs_db: JobsDB, users_db: UsersDB, manager: TorrentManager, **_):

    @app.on_message(filters.command("stats") & filters.private)
    @owner_only
    async def stats_cmd(client: Client, message: Message):
        total_users = await users_db.get_total_users()
        active_jobs = await jobs_db.get_all_active_jobs()

        downloading = sum(1 for j in active_jobs if j["status"] == "downloading")
        uploading = sum(1 for j in active_jobs if j["status"] == "uploading")
        waiting = sum(1 for j in active_jobs if j["status"] == "waiting")

        total_speed = sum(j.get("speed", 0) for j in active_jobs)

        # Disk usage
        dl_dir = Config.DOWNLOAD_DIR
        disk_used = 0
        if os.path.exists(dl_dir):
            for root, _dirs, fnames in os.walk(dl_dir):
                for fn in fnames:
                    try:
                        disk_used += os.path.getsize(os.path.join(root, fn))
                    except OSError:
                        pass

        text = (
            "📊 **BOT STATS**\n\n"
            f"👥 **Users:** {total_users}\n"
            f"📥 **Downloading:** {downloading}\n"
            f"📤 **Uploading:** {uploading}\n"
            f"📋 **Queued:** {waiting}\n"
            f"💾 **Temp storage:** {human_size(disk_used)}\n"
            f"⚡ **Total download speed:** {human_size(total_speed)}/s"
        )
        await message.reply(text)

    @app.on_message(filters.command("jobs") & filters.private)
    @owner_only
    async def jobs_cmd(client: Client, message: Message):
        jobs = await jobs_db.get_all_active_jobs()
        if not jobs:
            await message.reply("📭 No active jobs.")
            return
        lines = ["📋 **ALL ACTIVE JOBS**\n"]
        for j in jobs[:20]:
            lines.append(
                f"• `{j['job_id'][:8]}` — uid:{j['user_id']} — "
                f"{j['status']} — {j.get('torrent_name','?')[:30]}"
            )
        await message.reply("\n".join(lines))

    @app.on_message(filters.command("broadcast") & filters.private)
    @owner_only
    async def broadcast_cmd(client: Client, message: Message):
        parts = message.text.split(None, 1)
        if len(parts) < 2:
            await message.reply("Usage: `/broadcast <message>`")
            return
        text = parts[1]
        # Broadcast to all users (basic implementation)
        sent = 0
        failed = 0
        from database.mongo import get_db
        db = await get_db()
        async for user in db["users"].find({}, {"user_id": 1}):
            try:
                await client.send_message(user["user_id"], text)
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                failed += 1
        await message.reply(f"📢 Broadcast sent: {sent} ✅ / {failed} ❌")

    @app.on_message(filters.command("clearqueue") & filters.private)
    @owner_only
    async def clearqueue_cmd(client: Client, message: Message):
        from database.jobs import ACTIVE_STATUSES
        jobs = await jobs_db.get_all_active_jobs()
        count = 0
        for job in jobs:
            ok = await manager.cancel_job(job["job_id"])
            if ok:
                count += 1
        await message.reply(f"🗑 Cleared {count} jobs from queue.")

    @app.on_message(filters.command("restart") & filters.private)
    @owner_only
    async def restart_cmd(client: Client, message: Message):
        await message.reply("♻️ Restarting… (Render will restart the worker automatically.)")
        logger.info("Admin requested restart via /restart")
        os.kill(os.getpid(), 15)  # SIGTERM
