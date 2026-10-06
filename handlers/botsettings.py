"""
/bs — Bot Settings (owner-only).
One persistent editable message per invocation, navigated via inline keyboards.
Every callback verifies the requesting user is OWNER_ID.
"""
from wzgram import Client, filters
from wzgram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import Config
from database.jobs import JobsDB
from database.users import UsersDB
from database.settings import BotSettingsDB
from utils.formatting import human_size
from utils.logger import logger


# ── Owner guard ────────────────────────────────────────────────────────────

def _is_owner(user_id: int) -> bool:
    return user_id == Config.OWNER_ID


async def _deny(cb: CallbackQuery) -> None:
    await cb.answer("❌ Owner only.", show_alert=True)


# ── Main menu ──────────────────────────────────────────────────────────────

async def _render_main(bs_db: BotSettingsDB, jobs_db: JobsDB, users_db: UsersDB) -> tuple[str, InlineKeyboardMarkup]:
    s = await bs_db.get_bot_settings()
    conc = s.get("concurrency", {})
    toggles = s.get("toggles", {})
    dump_ch = s.get("dump_channel_id")

    total_users = await users_db.get_total_users()
    active_jobs = await jobs_db.get_all_active_jobs()
    queued = sum(1 for j in active_jobs if j["status"] == "waiting")
    running = sum(1 for j in active_jobs if j["status"] != "waiting")

    maintenance = "🔴 Maintenance" if toggles.get("maintenance_mode") else "🟢 Online"
    dump_str = str(dump_ch) if dump_ch else "Not configured"

    text = (
        f"⚙️ **BOT SETTINGS**\n\n"
        f"🤖 **Torrent Bot**\n"
        f"Status: {maintenance}\n\n"
        f"📥 Concurrent Downloads: `{conc.get('downloads', 1)}`\n"
        f"📤 Concurrent Uploads: `{conc.get('uploads', 1)}`\n"
        f"👥 Users: `{total_users}`\n"
        f"📋 Queued Jobs: `{queued}`\n"
        f"🔄 Active Jobs: `{running}`\n\n"
        f"📢 Dump Channel:\n`{dump_str}`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download Settings", callback_data="bs_dl"),
         InlineKeyboardButton("📤 Upload Settings", callback_data="bs_ul")],
        [InlineKeyboardButton("📋 Queue Settings", callback_data="bs_queue"),
         InlineKeyboardButton("📢 Dump Channel", callback_data="bs_dump")],
        [InlineKeyboardButton("👥 Limits", callback_data="bs_limits"),
         InlineKeyboardButton("🛡 Security", callback_data="bs_security")],
        [InlineKeyboardButton("📊 Statistics", callback_data="bs_stats"),
         InlineKeyboardButton("🔄 Refresh", callback_data="bs_main")],
    ])
    return text, kb


# ── Sub-page builders ──────────────────────────────────────────────────────

async def _render_dl(bs_db: BotSettingsDB) -> tuple[str, InlineKeyboardMarkup]:
    conc = await bs_db.get_concurrency_settings()
    cur = conc.get("downloads", 1)
    text = (
        f"📥 **DOWNLOAD SETTINGS**\n\n"
        f"Current concurrency: `{cur}`\n\n"
        f"Select maximum concurrent downloads:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅ ' if cur==i else ''}{i}", callback_data=f"bs_dl_set_{i}")
         for i in range(1, 5)],
        [InlineKeyboardButton("🔙 Back", callback_data="bs_main")],
    ])
    return text, kb


async def _render_ul(bs_db: BotSettingsDB) -> tuple[str, InlineKeyboardMarkup]:
    conc = await bs_db.get_concurrency_settings()
    cur = conc.get("uploads", 1)
    text = (
        f"📤 **UPLOAD SETTINGS**\n\n"
        f"Current concurrency: `{cur}`\n\n"
        f"Select maximum concurrent uploads:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅ ' if cur==i else ''}{i}", callback_data=f"bs_ul_set_{i}")
         for i in range(1, 5)],
        [InlineKeyboardButton("🔙 Back", callback_data="bs_main")],
    ])
    return text, kb


async def _render_queue(bs_db: BotSettingsDB) -> tuple[str, InlineKeyboardMarkup]:
    limits = await bs_db.get_limits()
    per_user = limits.get("max_queue_per_user", 5)
    global_q = limits.get("max_global_queue", 50)
    text = (
        f"📋 **QUEUE SETTINGS**\n\n"
        f"Per-user queue: `{per_user}`\n"
        f"Global queue: `{global_q}`\n\n"
        f"Select to change:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 User Limit", callback_data="bs_queue_user"),
         InlineKeyboardButton("🌐 Global Limit", callback_data="bs_queue_global")],
        [InlineKeyboardButton("🔙 Back", callback_data="bs_main")],
    ])
    return text, kb


async def _render_dump(bs_db: BotSettingsDB) -> tuple[str, InlineKeyboardMarkup]:
    dump_ch = await bs_db.get_dump_channel()
    current = str(dump_ch) if dump_ch else "Not configured"
    text = (
        f"📢 **DUMP CHANNEL**\n\n"
        f"Current:\n`{current}`\n\n"
        f"To set: click ➕ Set Channel and send the channel ID "
        f"(e.g. `-100123456789`) in your next message."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Set Channel", callback_data="bs_dump_set"),
         InlineKeyboardButton("🗑 Remove Channel", callback_data="bs_dump_remove")],
        [InlineKeyboardButton("🔙 Back", callback_data="bs_main")],
    ])
    return text, kb


async def _render_limits(bs_db: BotSettingsDB) -> tuple[str, InlineKeyboardMarkup]:
    limits = await bs_db.get_limits()
    max_fs = limits.get("max_file_size", 4 * 1024 ** 3)
    max_active = limits.get("max_active_jobs_per_user", 1)
    max_q = limits.get("max_queue_per_user", 5)
    text = (
        f"👥 **USER LIMITS**\n\n"
        f"Max file size: `{human_size(max_fs)}`\n"
        f"Active jobs/user: `{max_active}`\n"
        f"Queue/user: `{max_q}`\n\n"
        f"Send new value after tapping a button:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Max File Size", callback_data="bs_lim_filesize"),
         InlineKeyboardButton("🔢 Active Jobs", callback_data="bs_lim_active")],
        [InlineKeyboardButton("📋 Queue/User", callback_data="bs_lim_queue")],
        [InlineKeyboardButton("🔙 Back", callback_data="bs_main")],
    ])
    return text, kb


async def _render_security(bs_db: BotSettingsDB) -> tuple[str, InlineKeyboardMarkup]:
    toggles = await bs_db.get_toggles()

    def _t(key: str) -> str:
        return "✅ ON" if toggles.get(key, True) else "❌ OFF"

    text = (
        f"🛡 **SECURITY & TOGGLES**\n\n"
        f"🛠 Maintenance: `{'ON' if toggles.get('maintenance_mode') else 'OFF'}`\n"
        f"🧲 Magnet: `{'ON' if toggles.get('allow_magnet', True) else 'OFF'}`\n"
        f"📄 Torrent Files: `{'ON' if toggles.get('allow_torrent_file', True) else 'OFF'}`\n"
        f"🔗 Torrent URLs: `{'ON' if toggles.get('allow_torrent_url', True) else 'OFF'}`\n"
        f"🗑 Auto Delete: `{'ON' if toggles.get('auto_delete', True) else 'OFF'}`\n"
        f"🖼 Auto Thumbnail: `{'ON' if toggles.get('auto_thumbnail', True) else 'OFF'}`\n"
        f"📢 Dump: `{'ON' if toggles.get('dump_enabled', True) else 'OFF'}`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠 Maintenance", callback_data="bs_tog_maintenance_mode"),
         InlineKeyboardButton("🧲 Magnet", callback_data="bs_tog_allow_magnet")],
        [InlineKeyboardButton("📄 .torrent Files", callback_data="bs_tog_allow_torrent_file"),
         InlineKeyboardButton("🔗 Torrent URLs", callback_data="bs_tog_allow_torrent_url")],
        [InlineKeyboardButton("🗑 Auto Delete", callback_data="bs_tog_auto_delete"),
         InlineKeyboardButton("🖼 Auto Thumbnail", callback_data="bs_tog_auto_thumbnail")],
        [InlineKeyboardButton("📢 Dump", callback_data="bs_tog_dump_enabled")],
        [InlineKeyboardButton("🔙 Back", callback_data="bs_main")],
    ])
    return text, kb


async def _render_stats(bs_db: BotSettingsDB, jobs_db: JobsDB, users_db: UsersDB) -> tuple[str, InlineKeyboardMarkup]:
    total_users = await users_db.get_total_users()
    global_stats = await users_db.get_global_stats()
    status_counts = await jobs_db.get_status_counts()

    active_dl = status_counts.get("downloading", 0)
    active_ul = status_counts.get("uploading", 0)
    queued = status_counts.get("waiting", 0)

    text = (
        f"📊 **BOT STATISTICS**\n\n"
        f"👥 Users: `{total_users:,}`\n\n"
        f"📋 Total Jobs: `{global_stats.get('total_jobs', 0):,}`\n"
        f"✅ Completed: `{global_stats.get('completed_jobs', 0):,}`\n"
        f"❌ Failed: `{global_stats.get('failed_jobs', 0):,}`\n"
        f"🚫 Cancelled: `{global_stats.get('cancelled_jobs', 0):,}`\n\n"
        f"📥 Active Downloads: `{active_dl}`\n"
        f"📤 Active Uploads: `{active_ul}`\n"
        f"⏳ Queued: `{queued}`\n\n"
        f"💾 Downloaded: `{human_size(global_stats.get('total_downloaded', 0))}`\n"
        f"📤 Uploaded: `{human_size(global_stats.get('total_uploaded', 0))}`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="bs_stats"),
         InlineKeyboardButton("🔙 Back", callback_data="bs_main")],
    ])
    return text, kb


# ── Shared edit helper ─────────────────────────────────────────────────────

async def _edit(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        await cb.message.reply(text, reply_markup=kb)


# ── Pending-input state (in-memory; safe for single-worker Render) ─────────

_PENDING: dict[int, str] = {}  # user_id → intent key


def _set_pending(user_id: int, intent: str) -> None:
    _PENDING[user_id] = intent


def _pop_pending(user_id: int) -> str | None:
    return _PENDING.pop(user_id, None)


# ── Register ───────────────────────────────────────────────────────────────

def register(app: Client, bs_db: BotSettingsDB, jobs_db: JobsDB, users_db: UsersDB, **_):

    # ── /bs command ────────────────────────────────────────────────────────

    @app.on_message(filters.command("bs") & filters.private)
    async def bs_cmd(client: Client, message: Message):
        if not _is_owner(message.from_user.id):
            await message.reply("❌ This command is for the bot owner only.")
            return
        text, kb = await _render_main(bs_db, jobs_db, users_db)
        await message.reply(text, reply_markup=kb)

    # ── Navigation callbacks ───────────────────────────────────────────────

    @app.on_callback_query(filters.regex("^bs_main$"))
    async def cb_bs_main(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        text, kb = await _render_main(bs_db, jobs_db, users_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex("^bs_dl$"))
    async def cb_bs_dl(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        text, kb = await _render_dl(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex(r"^bs_dl_set_(\d+)$"))
    async def cb_bs_dl_set(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        val = int(cb.data.split("_")[-1])
        await bs_db.set_download_concurrency(val)
        await cb.answer(f"✅ Download concurrency set to {val}", show_alert=False)
        text, kb = await _render_dl(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex("^bs_ul$"))
    async def cb_bs_ul(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        text, kb = await _render_ul(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex(r"^bs_ul_set_(\d+)$"))
    async def cb_bs_ul_set(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        val = int(cb.data.split("_")[-1])
        await bs_db.set_upload_concurrency(val)
        await cb.answer(f"✅ Upload concurrency set to {val}", show_alert=False)
        text, kb = await _render_ul(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex("^bs_queue$"))
    async def cb_bs_queue(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        text, kb = await _render_queue(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex("^bs_queue_(user|global)$"))
    async def cb_bs_queue_limit(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        kind = cb.data.split("_")[-1]
        intent = "queue_per_user" if kind == "user" else "max_global_queue"
        _set_pending(cb.from_user.id, intent)
        await cb.message.reply(
            f"✏️ Send the new **{'per-user queue' if kind == 'user' else 'global queue'}** limit (number):"
        )

    @app.on_callback_query(filters.regex("^bs_dump$"))
    async def cb_bs_dump(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        text, kb = await _render_dump(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex("^bs_dump_set$"))
    async def cb_bs_dump_set(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        _set_pending(cb.from_user.id, "dump_channel_id")
        await cb.message.reply(
            "✏️ Send the **dump channel ID** (e.g. `-100123456789`).\n"
            "The bot must be an admin in that channel."
        )

    @app.on_callback_query(filters.regex("^bs_dump_remove$"))
    async def cb_bs_dump_remove(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        await bs_db.remove_dump_channel()
        text, kb = await _render_dump(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex("^bs_limits$"))
    async def cb_bs_limits(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        text, kb = await _render_limits(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex("^bs_lim_(filesize|active|queue)$"))
    async def cb_bs_lim(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        key = cb.data.split("bs_lim_")[1]
        intent_map = {
            "filesize": "max_file_size_gb",
            "active": "max_active_jobs_per_user",
            "queue": "max_queue_per_user",
        }
        label_map = {
            "filesize": "max file size in **GB** (e.g. `4`)",
            "active": "max **active jobs per user** (e.g. `1`)",
            "queue": "max **queue per user** (e.g. `5`)",
        }
        _set_pending(cb.from_user.id, intent_map[key])
        await cb.message.reply(f"✏️ Send the new {label_map[key]}:")

    @app.on_callback_query(filters.regex("^bs_security$"))
    async def cb_bs_security(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        text, kb = await _render_security(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex(r"^bs_tog_(\w+)$"))
    async def cb_bs_toggle(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        toggle_name = cb.data[len("bs_tog_"):]
        current = await bs_db.get_bot_toggle(toggle_name)
        await bs_db.set_bot_toggle(toggle_name, not current)
        await cb.answer(f"{'✅ Enabled' if not current else '❌ Disabled'}: {toggle_name}")
        text, kb = await _render_security(bs_db)
        await _edit(cb, text, kb)

    @app.on_callback_query(filters.regex("^bs_stats$"))
    async def cb_bs_stats(client, cb: CallbackQuery):
        if not _is_owner(cb.from_user.id):
            return await _deny(cb)
        await cb.answer()
        text, kb = await _render_stats(bs_db, jobs_db, users_db)
        await _edit(cb, text, kb)

    # ── Text input handler for pending operations ──────────────────────────

    @app.on_message(filters.private & filters.text & filters.user(Config.OWNER_ID))
    async def bs_text_input(client: Client, message: Message):
        intent = _pop_pending(message.from_user.id)
        if not intent:
            return  # Not a /bs pending input; let other handlers process it

        raw = message.text.strip()

        try:
            if intent == "dump_channel_id":
                ch_id = int(raw)
                await bs_db.set_dump_channel(ch_id)
                await message.reply(f"✅ Dump channel set to `{ch_id}`.")

            elif intent == "queue_per_user":
                val = int(raw)
                await bs_db.set_limit("max_queue_per_user", val)
                await message.reply(f"✅ Per-user queue limit set to `{val}`.")

            elif intent == "max_global_queue":
                val = int(raw)
                await bs_db.set_limit("max_global_queue", val)
                await message.reply(f"✅ Global queue limit set to `{val}`.")

            elif intent == "max_file_size_gb":
                val_gb = float(raw)
                val_bytes = int(val_gb * 1024 ** 3)
                await bs_db.set_limit("max_file_size", val_bytes)
                await message.reply(f"✅ Max file size set to `{human_size(val_bytes)}`.")

            elif intent == "max_active_jobs_per_user":
                val = int(raw)
                await bs_db.set_limit("max_active_jobs_per_user", val)
                await message.reply(f"✅ Max active jobs per user set to `{val}`.")

            elif intent == "max_queue_per_user":
                val = int(raw)
                await bs_db.set_limit("max_queue_per_user", val)
                await message.reply(f"✅ Queue per user set to `{val}`.")

        except ValueError:
            await message.reply(f"❌ Invalid value: `{raw}`. Expected a number.")
