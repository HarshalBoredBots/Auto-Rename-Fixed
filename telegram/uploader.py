"""
TelegramUploader: handles all file uploads for a completed leech job.
After user DM upload, optionally forwards to the configured dump channel.
"""
import asyncio
import os
import time
from datetime import datetime, timezone

from wzgram.errors import FloodWait

from config import Config
from database.jobs import JobsDB
from database.users import UsersDB
from database.settings import BotSettingsDB
from processing.media import build_caption_context, detect_upload_type, resolve_caption
from processing.metadata import apply_metadata
from processing.rename import build_filename
from processing.thumbnail import extract_thumbnail, get_video_duration
from telegram.progress import ProgressTracker, format_upload_progress
from utils.cleanup import remove_file
from utils.formatting import human_size
from utils.logger import logger
from utils.validation import sanitize_filename, safe_job_path


class TelegramUploader:
    def __init__(self, client, jobs_db: JobsDB, users_db: UsersDB, bs_db: BotSettingsDB):
        self.client = client
        self.jobs_db = jobs_db
        self.users_db = users_db
        self.bs_db = bs_db
        self._progress_trackers: dict[str, ProgressTracker] = {}

    def register_progress_tracker(self, job_id: str, tracker: ProgressTracker) -> None:
        self._progress_trackers[job_id] = tracker

    async def update_progress_message(self, job_id: str, phase: str, st: dict) -> None:
        from telegram.progress import format_download_progress
        tracker = self._progress_trackers.get(job_id)
        if not tracker:
            return
        if phase == "download":
            text = format_download_progress(st)
            await tracker.update(text)

    async def upload_job(self, job_id: str) -> int:
        """
        Upload all files for a job. Returns total bytes uploaded.
        After user DM upload, dumps to dump channel if configured & enabled.
        """
        job = await self.jobs_db.get_job(job_id)
        if not job:
            return 0

        user_id = job["user_id"]
        chat_id = job["chat_id"]

        user = await self.users_db.get_user(user_id)
        settings = user.get("settings", {})
        # Support both old (upload_type) and new (upload_mode) key names
        upload_type_pref = settings.get("upload_mode") or settings.get("upload_type", "document")
        thumb_mode = settings.get("thumbnail_mode", "auto")
        thumb_file_id = settings.get("thumbnail_file_id") or user.get("thumbnail_file_id")
        caption_template = settings.get("caption") or user.get("caption_template")
        rename_template = settings.get("rename_template")
        meta = settings.get("metadata", {})

        files = job.get("files_to_upload", [])
        if not files:
            download_dir = job.get("download_dir") or safe_job_path(Config.DOWNLOAD_DIR, job_id)
            from torrent.manager import TorrentManager
            files = TorrentManager._collect_files(None, download_dir)

        tracker = self._progress_trackers.get(job_id)

        # Determine dump channel
        dump_channel_id: int | None = None
        try:
            toggles = await self.bs_db.get_toggles()
            if toggles.get("dump_enabled", True):
                dump_channel_id = await self.bs_db.get_dump_channel()
        except Exception as e:
            logger.warning(f"Could not read dump channel settings: {e}")

        total_uploaded_bytes = 0

        for file_path in files:
            if not os.path.exists(file_path):
                logger.warning(f"File missing for upload: {file_path}")
                continue

            processed_path = None
            thumb_path = None

            try:
                final_name = build_filename(
                    file_path,
                    rename_template if settings.get("rename_enabled") else None,
                    {"user": str(user_id)},
                )
                final_name = sanitize_filename(final_name)
                upload_type = detect_upload_type(file_path, upload_type_pref)

                duration = 0
                if upload_type == "video":
                    duration = await get_video_duration(file_path)

                # Thumbnail
                local_thumb: str | None = None
                if thumb_mode == "custom" and thumb_file_id:
                    local_thumb = await self._download_thumb_by_file_id(thumb_file_id, job_id)
                elif thumb_mode == "auto" and upload_type == "video":
                    t_path = os.path.join(
                        safe_job_path(Config.DOWNLOAD_DIR, job_id),
                        f"thumb_{os.getpid()}.jpg",
                    )
                    ok = await extract_thumbnail(
                        file_path, t_path,
                        seek=min(duration // 4, 30) if duration else 5,
                    )
                    if ok:
                        thumb_path = t_path
                        local_thumb = t_path

                # Metadata
                upload_path = file_path
                if settings.get("metadata_enabled") and any(v for v in meta.values() if v):
                    out_path = file_path + ".meta_tmp" + os.path.splitext(file_path)[1]
                    ok = await apply_metadata(file_path, out_path, meta)
                    if ok:
                        processed_path = out_path
                        upload_path = out_path

                # Caption
                ctx = build_caption_context(upload_path, job, user_id, duration=duration)
                caption = resolve_caption(caption_template, ctx) if settings.get("caption_enabled") else None

                file_size = os.path.getsize(upload_path)

                # ── Progress callback ──────────────────────────────────────
                last_current = [0]
                last_time = [time.time()]

                async def progress_cb(current: int, total: int) -> None:
                    now = time.time()
                    elapsed = now - last_time[0]
                    speed = (current - last_current[0]) / elapsed if elapsed > 0 else 0
                    last_current[0] = current
                    last_time[0] = now
                    if tracker:
                        text = format_upload_progress(final_name, current, total, speed)
                        await tracker.update(text)

                # ── Upload to user DM ──────────────────────────────────────
                await self._send_file(
                    chat_id=chat_id,
                    file_path=upload_path,
                    filename=final_name,
                    upload_type=upload_type,
                    caption=caption,
                    thumb=local_thumb,
                    duration=duration,
                    progress=progress_cb,
                )
                total_uploaded_bytes += file_size
                logger.info(f"Job {job_id} uploaded to user: {final_name}")

                # ── Dump channel upload ────────────────────────────────────
                if dump_channel_id:
                    try:
                        await self._send_file(
                            chat_id=dump_channel_id,
                            file_path=upload_path,
                            filename=final_name,
                            upload_type=upload_type,
                            caption=caption,
                            thumb=local_thumb,
                            duration=duration,
                            progress=None,
                        )
                        logger.info(f"Job {job_id} dumped to channel {dump_channel_id}: {final_name}")
                    except Exception as e:
                        logger.warning(f"Dump channel upload failed for {final_name}: {e}")

            except Exception as e:
                logger.error(f"Upload failed for {file_path}: {e}")
                raise
            finally:
                if processed_path:
                    remove_file(processed_path)
                if thumb_path:
                    remove_file(thumb_path)

        if tracker:
            await tracker.update("✅ **Upload complete!**", force=True)

        return total_uploaded_bytes

    # ── Internal helpers ───────────────────────────────────────────────────

    async def _send_file(
        self,
        chat_id: int,
        file_path: str,
        filename: str,
        upload_type: str,
        caption: str | None,
        thumb: str | None,
        duration: int,
        progress,
        retries: int = 3,
    ) -> None:
        for attempt in range(retries):
            try:
                kwargs = dict(caption=caption, file_name=filename)
                if upload_type == "video":
                    await self.client.send_video(
                        chat_id=chat_id,
                        video=file_path,
                        duration=duration or None,
                        thumb=thumb,
                        supports_streaming=True,
                        progress=progress,
                        **kwargs,
                    )
                elif upload_type == "audio":
                    await self.client.send_audio(
                        chat_id=chat_id,
                        audio=file_path,
                        progress=progress,
                        **kwargs,
                    )
                else:
                    await self.client.send_document(
                        chat_id=chat_id,
                        document=file_path,
                        thumb=thumb,
                        progress=progress,
                        **kwargs,
                    )
                return
            except FloodWait as e:
                wait = e.value + 2
                logger.warning(f"FloodWait {wait}s during upload, attempt {attempt + 1}")
                await asyncio.sleep(wait)
            except Exception as e:
                if attempt == retries - 1:
                    raise
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}, retrying…")
                await asyncio.sleep(5)

    async def _download_thumb_by_file_id(self, file_id: str, job_id: str) -> str | None:
        try:
            out_dir = safe_job_path(Config.DOWNLOAD_DIR, job_id)
            out_path = os.path.join(out_dir, "custom_thumb.jpg")
            await self.client.download_media(file_id, file_name=out_path)
            if os.path.exists(out_path):
                return out_path
        except Exception as e:
            logger.warning(f"Failed to download custom thumb: {e}")
        return None
