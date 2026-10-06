from wzgram import Client, filters
from wzgram.types import Message

from database.jobs import (
    JobsDB,
    STATUS_WAITING, STATUS_DOWNLOADING, STATUS_UPLOADING, STATUS_PROCESSING,
)

STATUS_EMOJI = {
    STATUS_DOWNLOADING: "🔄",
    STATUS_UPLOADING: "📤",
    STATUS_PROCESSING: "⚙️",
    STATUS_WAITING: "⏳",
}


async def send_queue(client: Client, chat_id: int, user_id: int, jobs_db: JobsDB = None):
    if not jobs_db:
        await client.send_message(chat_id, "❌ Internal error.")
        return

    jobs = await jobs_db.get_user_queue(user_id)
    if not jobs:
        await client.send_message(chat_id, "📭 Your queue is empty. Use `/l <magnet>` to add a job.")
        return

    lines = ["📋 **YOUR QUEUE**\n"]
    for i, job in enumerate(jobs, 1):
        emoji = STATUS_EMOJI.get(job["status"], "•")
        name = job.get("torrent_name") or "Pending…"
        status = job["status"].capitalize()
        pct = job.get("progress", 0.0)
        line = f"{i}. {emoji} `{name[:40]}` — {status}"
        if pct > 0 and job["status"] != STATUS_WAITING:
            line += f" ({pct:.0f}%)"
        lines.append(line)

    await client.send_message(chat_id, "\n".join(lines))


def register(app: Client, jobs_db: JobsDB, **_):
    @app.on_message(filters.command("queue") & filters.private)
    async def queue_cmd(client: Client, message: Message):
        await send_queue(client, message.chat.id, message.from_user.id, jobs_db=jobs_db)
