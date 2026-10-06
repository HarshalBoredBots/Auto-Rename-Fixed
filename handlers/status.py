from wzgram import Client, filters
from wzgram.types import Message

from database.jobs import JobsDB, STATUS_WAITING, STATUS_DOWNLOADING, STATUS_UPLOADING, STATUS_PROCESSING
from utils.formatting import human_size, human_speed, human_eta, progress_bar


async def send_status(client: Client, chat_id: int, user_id: int, jobs_db: JobsDB = None):
    if not jobs_db:
        await client.send_message(chat_id, "❌ Internal error.")
        return

    # Find the most relevant active job
    jobs = await jobs_db.get_user_queue(user_id)
    if not jobs:
        await client.send_message(chat_id, "📭 No active jobs. Use `/l <magnet>` to start one.")
        return

    # Show the most active job first
    order = {STATUS_DOWNLOADING: 0, STATUS_UPLOADING: 1, STATUS_PROCESSING: 2, STATUS_WAITING: 3}
    jobs.sort(key=lambda j: order.get(j["status"], 9))
    job = jobs[0]

    text = _format_job_status(job)
    await client.send_message(chat_id, text)


def _format_job_status(job: dict) -> str:
    status = job.get("status", "unknown")
    name = job.get("torrent_name") or "Unknown"
    progress = job.get("progress", 0.0)
    downloaded = job.get("downloaded", 0)
    total = job.get("total", 0)
    speed = job.get("speed", 0)
    eta = job.get("eta", 0)
    job_id = job.get("job_id", "")[:8]

    bar = progress_bar(progress)

    if status == STATUS_DOWNLOADING:
        size_str = f"{human_size(downloaded)} / {human_size(total)}" if total else human_size(downloaded)
        return (
            f"📥 **DOWNLOAD** `[{job_id}]`\n\n"
            f"📁 **{name}**\n\n"
            f"{bar} `{progress:.1f}%`\n"
            f"**Downloaded:** {size_str}\n"
            f"**Speed:** {human_speed(speed)}\n"
            f"**ETA:** {human_eta(eta)}\n"
            f"**Seeds:** {job.get('seeders', 0)}\n\n"
            f"**Status:** Downloading"
        )
    elif status == STATUS_UPLOADING:
        size_str = f"{human_size(downloaded)} / {human_size(total)}" if total else human_size(downloaded)
        return (
            f"📤 **UPLOAD** `[{job_id}]`\n\n"
            f"📁 **{name}**\n\n"
            f"{bar} `{progress:.1f}%`\n"
            f"**Uploaded:** {size_str}\n"
            f"**Speed:** {human_speed(speed)}\n\n"
            f"**Status:** Uploading…"
        )
    elif status == STATUS_PROCESSING:
        return f"⚙️ **PROCESSING** `[{job_id}]`\n\n📁 **{name}**\n\n**Status:** Processing…"
    elif status == STATUS_WAITING:
        jobs_ahead = 0  # Could be fetched but not critical
        return (
            f"⏳ **WAITING** `[{job_id}]`\n\n"
            f"📁 **{name or 'Pending…'}**\n\n"
            f"**Status:** Queued"
        )
    else:
        return f"ℹ️ Job `{job_id}` — **{status}**"


def register(app: Client, jobs_db: JobsDB, **_):
    @app.on_message(filters.command(["s", "status"]) & filters.private)
    async def status_cmd(client: Client, message: Message):
        await send_status(client, message.chat.id, message.from_user.id, jobs_db=jobs_db)
