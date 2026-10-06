from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

DEFAULT_SETTINGS = {
    "upload_mode": "document",       # document | video | audio  (alias: upload_type)
    "thumbnail_mode": "auto",        # auto | custom | disabled
    "thumbnail_file_id": None,
    "caption_enabled": True,
    "caption": None,                 # alias: caption_template
    "metadata_enabled": False,
    "metadata": {
        "title": None,
        "author": None,
        "artist": None,
        "album": None,
        "genre": None,
        "year": None,
        "comment": None,
    },
    "rename_enabled": False,
    "rename_template": None,
}

DEFAULT_STATS = {
    "total_jobs": 0,
    "completed_jobs": 0,
    "failed_jobs": 0,
    "cancelled_jobs": 0,
    "total_downloaded": 0,   # bytes
    "total_uploaded": 0,     # bytes
}


class UsersDB:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db["users"]

    async def ensure_indexes(self):
        await self.col.create_index("user_id", unique=True)

    # ── User creation / retrieval ──────────────────────────────────────────

    async def upsert_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> None:
        """Create or update a user record with Telegram profile info."""
        now = datetime.now(timezone.utc)
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "username": username,
                    "first_name": first_name,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "_id": user_id,
                    "settings": DEFAULT_SETTINGS.copy(),
                    "stats": DEFAULT_STATS.copy(),
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def get_user(self, user_id: int) -> dict:
        doc = await self.col.find_one({"user_id": user_id})
        if not doc:
            await self.upsert_user(user_id)
            doc = await self.col.find_one({"user_id": user_id})
        # Back-fill missing keys without a write round-trip
        if "settings" not in doc:
            doc["settings"] = DEFAULT_SETTINGS.copy()
        if "stats" not in doc:
            doc["stats"] = DEFAULT_STATS.copy()
        return doc

    # ── Settings ───────────────────────────────────────────────────────────

    async def get_settings(self, user_id: int) -> dict:
        user = await self.get_user(user_id)
        s = user.get("settings", {})
        # Normalise legacy key names so the rest of the codebase works either way
        if "upload_type" in s and "upload_mode" not in s:
            s["upload_mode"] = s["upload_type"]
        if "caption_template" in s and "caption" not in s:
            s["caption"] = s["caption_template"]
        return s

    async def update_settings(self, user_id: int, updates: dict) -> None:
        await self.get_user(user_id)  # ensure exists
        set_fields = {f"settings.{k}": v for k, v in updates.items()}
        set_fields["updated_at"] = datetime.now(timezone.utc)
        await self.col.update_one(
            {"user_id": user_id},
            {"$set": set_fields},
            upsert=True,
        )

    async def update_metadata_field(self, user_id: int, field: str, value) -> None:
        await self.get_user(user_id)
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    f"settings.metadata.{field}": value,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def set_thumbnail(self, user_id: int, file_id: str) -> None:
        await self.get_user(user_id)
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "settings.thumbnail_file_id": file_id,
                    "settings.thumbnail_mode": "custom",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def del_thumbnail(self, user_id: int) -> None:
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "settings.thumbnail_file_id": None,
                    "settings.thumbnail_mode": "auto",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def set_caption(self, user_id: int, caption: str) -> None:
        await self.get_user(user_id)
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "settings.caption": caption,
                    "settings.caption_enabled": True,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def del_caption(self, user_id: int) -> None:
        await self.col.update_one(
            {"user_id": user_id},
            {"$set": {"settings.caption": None, "updated_at": datetime.now(timezone.utc)}},
        )

    async def set_rename_template(self, user_id: int, template: str) -> None:
        await self.get_user(user_id)
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "settings.rename_template": template,
                    "settings.rename_enabled": True,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def del_rename_template(self, user_id: int) -> None:
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "settings.rename_template": None,
                    "settings.rename_enabled": False,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def reset_settings(self, user_id: int) -> None:
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "settings": DEFAULT_SETTINGS.copy(),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    # ── Stats (atomic $inc — never read-modify-write) ──────────────────────

    async def inc_stats(self, user_id: int, **fields: int) -> None:
        """
        Atomically increment per-user stat counters.
        Example: inc_stats(uid, completed_jobs=1, total_downloaded=1234567)
        """
        if not fields:
            return
        inc = {f"stats.{k}": v for k, v in fields.items()}
        await self.col.update_one(
            {"user_id": user_id},
            {"$inc": inc, "$set": {"updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    async def get_stats(self, user_id: int) -> dict:
        user = await self.get_user(user_id)
        return user.get("stats", DEFAULT_STATS.copy())

    # ── Aggregated stats for /bs ────────────────────────────────────────────

    async def get_total_users(self) -> int:
        return await self.col.count_documents({})

    async def get_global_stats(self) -> dict:
        """Sum stats across all users using an aggregation pipeline."""
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_jobs": {"$sum": "$stats.total_jobs"},
                    "completed_jobs": {"$sum": "$stats.completed_jobs"},
                    "failed_jobs": {"$sum": "$stats.failed_jobs"},
                    "cancelled_jobs": {"$sum": "$stats.cancelled_jobs"},
                    "total_downloaded": {"$sum": "$stats.total_downloaded"},
                    "total_uploaded": {"$sum": "$stats.total_uploaded"},
                }
            }
        ]
        result = await self.col.aggregate(pipeline).to_list(1)
        if result:
            r = result[0]
            r.pop("_id", None)
            return r
        return {k: 0 for k in DEFAULT_STATS}
