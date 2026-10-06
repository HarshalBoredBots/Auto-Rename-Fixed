"""
Global bot settings stored as a single MongoDB document (_id: "bot_settings").
All runtime-configurable values live here; env vars are used only as defaults
on first initialisation.
"""
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from config import Config

_DOC_ID = "bot_settings"


def _defaults() -> dict:
    return {
        "_id": _DOC_ID,
        "dump_channel_id": Config.DUMP_CHANNEL_ID or None,
        "limits": {
            "max_file_size": int(Config.MAX_TORRENT_SIZE_GB * 1024 ** 3),
            "max_active_jobs_per_user": 1,
            "max_queue_per_user": Config.MAX_QUEUE_PER_USER,
            "max_global_queue": 50,
        },
        "concurrency": {
            "downloads": Config.MAX_CONCURRENT_DOWNLOADS,
            "uploads": Config.MAX_CONCURRENT_UPLOADS,
        },
        "toggles": {
            "maintenance_mode": False,
            "allow_magnet": True,
            "allow_torrent_file": True,
            "allow_torrent_url": True,
            "auto_delete": True,
            "auto_thumbnail": True,
            "dump_enabled": True,
        },
        "updated_at": datetime.now(timezone.utc),
    }


class BotSettingsDB:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["bot_settings"]

    async def ensure_indexes(self) -> None:
        # _id is already indexed; nothing extra needed for this collection.
        pass

    # ── Internal: load or create ───────────────────────────────────────────

    async def _get(self) -> dict:
        doc = await self.col.find_one({"_id": _DOC_ID})
        if doc is None:
            doc = _defaults()
            await self.col.insert_one(doc)
        return doc

    async def _set(self, path: str, value) -> None:
        await self.col.update_one(
            {"_id": _DOC_ID},
            {
                "$set": {
                    path: value,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    # ── Public API ─────────────────────────────────────────────────────────

    async def get_bot_settings(self) -> dict:
        return await self._get()

    async def update_bot_setting(self, key: str, value) -> None:
        """Set a top-level or dot-notation key, e.g. 'toggles.maintenance_mode'."""
        await self._set(key, value)

    async def update_bot_settings(self, values: dict) -> None:
        """Set multiple dot-notation keys at once."""
        values["updated_at"] = datetime.now(timezone.utc)
        await self.col.update_one(
            {"_id": _DOC_ID},
            {"$set": values},
            upsert=True,
        )

    # ── Dump channel ───────────────────────────────────────────────────────

    async def get_dump_channel(self) -> int | None:
        doc = await self._get()
        val = doc.get("dump_channel_id")
        return int(val) if val else None

    async def set_dump_channel(self, channel_id: int) -> None:
        await self._set("dump_channel_id", channel_id)

    async def remove_dump_channel(self) -> None:
        await self._set("dump_channel_id", None)

    # ── Concurrency ────────────────────────────────────────────────────────

    async def get_concurrency_settings(self) -> dict:
        doc = await self._get()
        return doc.get("concurrency", {"downloads": 1, "uploads": 1})

    async def set_download_concurrency(self, value: int) -> None:
        await self._set("concurrency.downloads", value)

    async def set_upload_concurrency(self, value: int) -> None:
        await self._set("concurrency.uploads", value)

    # ── Limits ─────────────────────────────────────────────────────────────

    async def get_limits(self) -> dict:
        doc = await self._get()
        return doc.get("limits", _defaults()["limits"])

    async def set_limit(self, name: str, value) -> None:
        await self._set(f"limits.{name}", value)

    # ── Toggles ────────────────────────────────────────────────────────────

    async def get_toggles(self) -> dict:
        doc = await self._get()
        return doc.get("toggles", _defaults()["toggles"])

    async def get_bot_toggle(self, name: str) -> bool:
        toggles = await self.get_toggles()
        return bool(toggles.get(name, True))

    async def set_bot_toggle(self, name: str, value: bool) -> None:
        await self._set(f"toggles.{name}", value)
