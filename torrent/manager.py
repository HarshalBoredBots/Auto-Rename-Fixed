"""
TorrentManager: orchestrates the full lifecycle of a leech job.
download → process → upload → (dump) → cleanup
"""
import asyncio
import base64
import os
import time
import uuid
from datetime import datetime, timezone

from config import Config
from database.jobs import (
    JobsDB,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_DOWNLOADING,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_UPLOADING,
    STATUS_WAITING,
)
from database.users import UsersDB
from database.settings import BotSettingsDB
from torrent.aria2 import aria2
from utils.cleanup import cleanup_job_dir
from utils.logger import logger
from utils.validation import safe_job_path


class TorrentManager:
    def __init__(self, jobs_db: JobsDB, users_db: UsersDB, bs_db: BotSettingsDB):
        self.jobs_db = jobs_db
        self.users_db = users_db
        self.bs_db = bs_db
        # Semaphores initialised from env defaults; dynamically re-read from DB per job
        self._download_sem = asyncio.Semaphore(Config.MAX_CONCURRENT_DOWNLOADS)
        self._upload_sem = asyncio.Semaphore(Config.MAX_CONCURRENT_UPLOADS)
        self._active: dict[str, asyncio.Task] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._uploader = None  # set by bot.py

    def set_uploader(self, uploader) -> None:
        self._uploader = uploader

    def _new_job_id(self) -> str:
        return uuid.uuid4().hex[:16]

    # ── Queue limit helpers (DB-driven) ────────────────────────────────────

    async def _max_queue_per_user(self) -> int:
        try:
            limits = await self.bs_db.get_limits()
            return int(limits.get("max_queue_per_user", Config.MAX_QUEUE_PER_USER))
        except Exception:
            return Config.MAX_QUEUE_PER_USER

    async def _max_global_queue(self) -> int:
        try:
            limits = await self.bs_db.get_limits()
            return int(limits.get("max_global_queue", 50))
        except Exception:
            return 50

    # ── Submit ─────────────────────────────────────────────────────────────

    async def submit_job(
        self,
        user_id: int,
        source: str,
        source_type: str,
        client_msg_id: int,
        chat_id: int,
    ) -> dict | None:
        max_per_user = await self._max_queue_per_user()
        active_count = await self.jobs_db.count_user_active_jobs(user_id)
        if active_count >= max_per_user:
            return None

        job_id = self._new_job_id()
        job = {
            "job_id": job_id,
            "user_id": user_id,
            "torrent_hash": None,
            "torrent_name": None,
            "status": STATUS_WAITING,
            "source": source,
            "source_type": source_type,
            "chat_id": chat_id,
            "status_msg_id": client_msg_id,
            "aria2_gid": None,
        }
        await self.jobs_db.create_job(job)
        # Increment total_jobs counter atomically
        await self.users_db.inc_stats(user_id, total_jobs=1)

        task = asyncio.create_task(self._run_job(job_id))
        self._active[job_id] = task
        self._cancel_events[job_id] = asyncio.Event()
        return job

    # ── Cancel ─────────────────────────────────────────────────────────────

    async def cancel_job(self, job_id: str) -> bool:
        job = await self.jobs_db.get_job(job_id)
        if not job:
            return False
        if job["status"] in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED):
            return False

        ev = self._cancel_events.get(job_id)
        if ev:
            ev.set()

        gid = job.get("aria2_gid")
        if gid:
            try:
                await aria2.remove(gid)
            except Exception as e:
                logger.warning(f"aria2 remove on cancel {job_id}: {e}")

        await self.jobs_db.update_job(
            job_id,
            {"status": STATUS_CANCELLED, "completed_at": datetime.now(timezone.utc)},
        )
        await self.users_db.inc_stats(job["user_id"], cancelled_jobs=1)
        cleanup_job_dir(Config.DOWNLOAD_DIR, job_id)

        task = self._active.pop(job_id, None)
        if task and not task.done():
            task.cancel()
        return True

    def is_cancelled(self, job_id: str) -> bool:
        ev = self._cancel_events.get(job_id)
        return ev is not None and ev.is_set()

    # ── Core runner ────────────────────────────────────────────────────────

    async def _run_job(self, job_id: str) -> None:
        job = await self.jobs_db.get_job(job_id)
        user_id = job["user_id"] if job else 0
        try:
            async with self._download_sem:
                await self._download_phase(job_id)
            if self.is_cancelled(job_id):
                return
            await self._process_phase(job_id)
            if self.is_cancelled(job_id):
                return
            async with self._upload_sem:
                await self._upload_phase(job_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Job {job_id} failed: {e}")
            await self.jobs_db.update_job(
                job_id,
                {
                    "status": STATUS_FAILED,
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc),
                },
            )
            if user_id:
                await self.users_db.inc_stats(user_id, failed_jobs=1)
        finally:
            cleanup_job_dir(Config.DOWNLOAD_DIR, job_id)
            self._active.pop(job_id, None)
            self._cancel_events.pop(job_id, None)

    # ── Download phase ─────────────────────────────────────────────────────

    async def _download_phase(self, job_id: str) -> None:
        job = await self.jobs_db.get_job(job_id)
        if not job or self.is_cancelled(job_id):
            return

        download_dir = safe_job_path(Config.DOWNLOAD_DIR, job_id)
        os.makedirs(download_dir, exist_ok=True)

        await self.jobs_db.update_job(
            job_id,
            {"status": STATUS_DOWNLOADING, "started_at": datetime.now(timezone.utc)},
        )

        source = job["source"]
        source_type = job["source_type"]

        try:
            if source_type == "magnet":
                gid = await aria2.add_magnet(source, download_dir)
            elif source_type == "url":
                gid = await aria2.add_torrent_url(source, download_dir)
            elif source_type == "file_path":
                with open(source, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                gid = await aria2.add_torrent_file(b64, download_dir)
            else:
                raise ValueError(f"Unknown source_type: {source_type}")
        except Exception as e:
            raise RuntimeError(f"Failed to add torrent to aria2: {e}") from e

        await self.jobs_db.update_job(job_id, {"aria2_gid": gid})

        last_update = 0.0
        while True:
            if self.is_cancelled(job_id):
                await aria2.remove(gid)
                return

            try:
                raw = await aria2.get_status(gid)
            except Exception as e:
                raise RuntimeError(f"aria2 status error: {e}") from e

            st = aria2.parse_status(raw)
            aria2_status = st["status"]

            now = time.time()
            if now - last_update >= Config.PROGRESS_UPDATE_INTERVAL:
                updates = {
                    "progress": st["progress"],
                    "downloaded": st["downloaded"],
                    "total": st["total"],
                    "total_size": st["total"],
                    "download_speed": st["speed"],
                    "speed": st["speed"],
                    "eta": st["eta"],
                    "torrent_name": st["name"] or job.get("torrent_name"),
                }
                await self.jobs_db.update_job(job_id, updates)
                last_update = now
                if self._uploader:
                    await self._uploader.update_progress_message(job_id, "download", st)

            if aria2_status == "complete":
                total = st["total"]
                await self.jobs_db.update_job(
                    job_id,
                    {
                        "progress": 100.0,
                        "downloaded": total,
                        "total": total,
                        "total_size": total,
                        "download_speed": 0,
                        "speed": 0,
                        "eta": 0,
                        "torrent_name": st["name"] or job.get("torrent_name"),
                        "download_dir": download_dir,
                    },
                )
                # Increment downloaded bytes stat
                await self.users_db.inc_stats(job["user_id"], total_downloaded=total)
                logger.info(f"Job {job_id} download complete")
                return

            if aria2_status == "error":
                raise RuntimeError(f"aria2 download error: {st.get('error', 'unknown')}")

            if aria2_status in ("removed", "waiting") and self.is_cancelled(job_id):
                return

            await asyncio.sleep(2)

    # ── Processing phase ───────────────────────────────────────────────────

    async def _process_phase(self, job_id: str) -> None:
        job = await self.jobs_db.get_job(job_id)
        if not job:
            return

        await self.jobs_db.update_job(job_id, {"status": STATUS_PROCESSING})

        download_dir = job.get("download_dir") or safe_job_path(Config.DOWNLOAD_DIR, job_id)
        files = self._collect_files(download_dir)
        if not files:
            raise RuntimeError("No files found after download")

        await self.jobs_db.update_job(
            job_id, {"files_to_upload": files, "download_dir": download_dir}
        )

    def _collect_files(self, directory: str) -> list[str]:
        result = []
        for root, _dirs, fnames in os.walk(directory):
            for fname in fnames:
                if fname.endswith(".torrent") or fname.endswith(".aria2"):
                    continue
                full = os.path.join(root, fname)
                if os.path.isfile(full) and os.path.getsize(full) > 0:
                    result.append(full)
        return sorted(result)

    # ── Upload phase ───────────────────────────────────────────────────────

    async def _upload_phase(self, job_id: str) -> None:
        job = await self.jobs_db.get_job(job_id)
        if not job:
            return

        await self.jobs_db.update_job(job_id, {"status": STATUS_UPLOADING})

        if not self._uploader:
            raise RuntimeError("Uploader not configured")

        total_uploaded = await self._uploader.upload_job(job_id)

        await self.jobs_db.update_job(
            job_id,
            {"status": STATUS_COMPLETED, "completed_at": datetime.now(timezone.utc)},
        )
        await self.users_db.inc_stats(
            job["user_id"],
            completed_jobs=1,
            total_uploaded=total_uploaded or 0,
        )
        logger.info(f"Job {job_id} completed")
