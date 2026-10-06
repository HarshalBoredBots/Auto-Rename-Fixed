from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

# Job status constants
STATUS_WAITING = "waiting"
STATUS_DOWNLOADING = "downloading"
STATUS_PROCESSING = "processing"
STATUS_UPLOADING = "uploading"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_INTERRUPTED = "interrupted"

ACTIVE_STATUSES = {STATUS_WAITING, STATUS_DOWNLOADING, STATUS_PROCESSING, STATUS_UPLOADING}
IN_PROGRESS_STATUSES = {STATUS_DOWNLOADING, STATUS_PROCESSING, STATUS_UPLOADING}


class JobsDB:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["jobs"]

    async def ensure_indexes(self) -> None:
        await self.col.create_index("user_id")
        await self.col.create_index("job_id", unique=True)
        await self.col.create_index("status")
        await self.col.create_index("torrent_hash")
        await self.col.create_index("aria2_gid")
        await self.col.create_index("created_at")
        await self.col.create_index([("user_id", 1), ("status", 1)])

    # ── Create ─────────────────────────────────────────────────────────────

    async def create_job(self, job: dict) -> dict:
        now = datetime.now(timezone.utc)
        job.setdefault("created_at", now)
        job.setdefault("started_at", None)
        job.setdefault("completed_at", None)
        job.setdefault("error", None)
        job.setdefault("progress", 0.0)
        job.setdefault("downloaded", 0)
        job.setdefault("total", 0)
        job.setdefault("total_size", 0)
        job.setdefault("speed", 0)
        job.setdefault("download_speed", 0)
        job.setdefault("upload_speed", 0)
        job.setdefault("eta", 0)
        job.setdefault("file_path", None)
        job.setdefault("aria2_gid", None)
        await self.col.insert_one(job)
        return job

    # ── Read ───────────────────────────────────────────────────────────────

    async def get_job(self, job_id: str) -> dict | None:
        return await self.col.find_one({"job_id": job_id})

    async def get_user_jobs(self, user_id: int, statuses: list | None = None) -> list:
        query: dict = {"user_id": user_id}
        if statuses:
            query["status"] = {"$in": statuses}
        cursor = self.col.find(query).sort("created_at", 1)
        return await cursor.to_list(length=100)

    async def get_active_user_job(self, user_id: int) -> dict | None:
        return await self.col.find_one(
            {"user_id": user_id, "status": {"$in": list(IN_PROGRESS_STATUSES)}}
        )

    async def get_user_queue(self, user_id: int) -> list:
        return await self.get_user_jobs(user_id, list(ACTIVE_STATUSES))

    async def get_all_active_jobs(self) -> list:
        cursor = self.col.find({"status": {"$in": list(ACTIVE_STATUSES)}}).sort("created_at", 1)
        return await cursor.to_list(length=200)

    async def get_jobs_by_status(self, status: str, limit: int = 50) -> list:
        cursor = self.col.find({"status": status}).sort("created_at", 1).limit(limit)
        return await cursor.to_list(length=limit)

    # ── Counts ─────────────────────────────────────────────────────────────

    async def count_user_active_jobs(self, user_id: int) -> int:
        return await self.col.count_documents(
            {"user_id": user_id, "status": {"$in": list(ACTIVE_STATUSES)}}
        )

    async def count_active_by_status(self, status: str) -> int:
        return await self.col.count_documents({"status": status})

    async def get_total_jobs(self) -> int:
        return await self.col.count_documents({})

    async def get_active_count(self) -> int:
        return await self.col.count_documents({"status": {"$in": list(ACTIVE_STATUSES)}})

    async def get_status_counts(self) -> dict:
        """Return a dict of {status: count} for all statuses."""
        pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        result = await self.col.aggregate(pipeline).to_list(20)
        return {r["_id"]: r["count"] for r in result}

    # ── Update ─────────────────────────────────────────────────────────────

    async def update_job(self, job_id: str, updates: dict) -> None:
        await self.col.update_one({"job_id": job_id}, {"$set": updates})

    # ── Atomic job claiming (prevents double-claiming) ─────────────────────

    async def claim_next_queued_job(self) -> dict | None:
        """
        Atomically find the oldest waiting job and mark it as downloading.
        Only one worker can claim a given job even with concurrent callers.
        Returns the claimed job dict, or None if nothing is waiting.
        """
        now = datetime.now(timezone.utc)
        doc = await self.col.find_one_and_update(
            {"status": STATUS_WAITING},
            {
                "$set": {
                    "status": STATUS_DOWNLOADING,
                    "started_at": now,
                }
            },
            sort=[("created_at", 1)],
            return_document=True,
        )
        return doc

    # ── Startup recovery ────────────────────────────────────────────────────

    async def mark_interrupted_jobs(self) -> None:
        """
        On startup, mark any in-progress jobs as interrupted.
        Waiting jobs survive restart and remain queued.
        """
        await self.col.update_many(
            {"status": {"$in": list(IN_PROGRESS_STATUSES)}},
            {
                "$set": {
                    "status": STATUS_INTERRUPTED,
                    "error": "Worker restarted unexpectedly",
                    "completed_at": datetime.now(timezone.utc),
                }
            },
        )
