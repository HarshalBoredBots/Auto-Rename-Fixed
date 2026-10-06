from wzgram import Client, filters
from wzgram.types import Message

from database.jobs import JobsDB
from torrent.manager import TorrentManager
from utils.logger import logger


def register(app: Client, jobs_db: JobsDB, manager: TorrentManager, **_):

    @app.on_message(filters.command("cancel") & filters.private)
    async def cancel_cmd(client: Client, message: Message):
        user_id = message.from_user.id

        jobs = await jobs_db.get_user_queue(user_id)
        if not jobs:
            await message.reply("📭 No active jobs to cancel.")
            return

        # Cancel the most active job
        from database.jobs import STATUS_DOWNLOADING, STATUS_UPLOADING, STATUS_PROCESSING, STATUS_WAITING
        order = {STATUS_DOWNLOADING: 0, STATUS_UPLOADING: 1, STATUS_PROCESSING: 2, STATUS_WAITING: 3}
        jobs.sort(key=lambda j: order.get(j["status"], 9))
        job = jobs[0]
        job_id = job["job_id"]

        ok = await manager.cancel_job(job_id)
        if ok:
            name = job.get("torrent_name") or f"job `{job_id[:8]}`"
            await message.reply(f"🗑 Cancelled: **{name}**\n\nAll temporary files deleted.")
            logger.info(f"Job {job_id} cancelled by user {user_id}")
        else:
            await message.reply("❌ Could not cancel job (already completed or not found).")
