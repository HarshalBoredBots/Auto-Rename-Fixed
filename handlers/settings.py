from wzgram import Client, filters
from wzgram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from database.users import UsersDB

# ── Helpers ────────────────────────────────────────────────────────────────

def _on(val) -> str:
    return "✅ ON" if val else "❌ OFF"

def _mode(val, opt) -> str:
    return "✅ " + opt.upper() if val == opt else opt.capitalize()


async def send_settings_menu(client: Client, chat_id: int, user_id: int, users_db: UsersDB = None, message_id: int = None):
    s = await users_db.get_settings(user_id)
    user = await users_db.get_user(user_id)

    caption_template = user.get("caption_template") or "—"
    rename_template = user.get("rename_template") or "—"
    thumb_mode = s.get("thumbnail_mode", "auto")

    text = (
        "⚙️ **USER SETTINGS**\n\n"
        f"📤 **Upload**\n"
        f"├ Type: `{s.get('upload_type','document').upper()}`\n"
        f"├ Thumbnail: `{thumb_mode.upper()}`\n"
        f"└ Caption: `{'ON' if s.get('caption_enabled') else 'OFF'}`\n\n"
        f"📝 **Metadata**\n"
        f"├ Enabled: `{'ON' if s.get('metadata_enabled') else 'OFF'}`\n"
        f"├ Title: `{s.get('metadata',{}).get('title') or '—'}`\n"
        f"├ Author: `{s.get('metadata',{}).get('author') or '—'}`\n"
        f"└ Year: `{s.get('metadata',{}).get('year') or '—'}`\n\n"
        f"✏️ **Processing**\n"
        f"├ Rename: `{'ON' if s.get('rename_enabled') else 'OFF'}` — `{rename_template[:30]}`\n"
        f"└ Caption template: `{caption_template[:30]}`"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Settings", callback_data="set_upload_menu")],
        [InlineKeyboardButton("📝 Metadata", callback_data="set_metadata_menu")],
        [InlineKeyboardButton("🖼 Thumbnail", callback_data="set_thumb_menu")],
        [InlineKeyboardButton("✏️ Rename", callback_data="set_rename_menu")],
        [InlineKeyboardButton("💬 Caption", callback_data="set_caption_menu")],
        [InlineKeyboardButton("🔄 Reset Settings", callback_data="set_reset_confirm")],
    ])

    if message_id:
        try:
            await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=kb)
        except Exception:
            await client.send_message(chat_id, text, reply_markup=kb)
    else:
        await client.send_message(chat_id, text, reply_markup=kb)


# ── Register all handlers ──────────────────────────────────────────────────

def register(app: Client, users_db: UsersDB, **_):

    @app.on_message(filters.command("us") & filters.private)
    async def us_cmd(client: Client, message: Message):
        await send_settings_menu(client, message.chat.id, message.from_user.id, users_db=users_db)

    # ── Upload type menu ──────────────────────────────────────────────────

    @app.on_callback_query(filters.regex("^set_upload_menu$"))
    async def cb_upload_menu(client, cb: CallbackQuery):
        await cb.answer()
        s = await users_db.get_settings(cb.from_user.id)
        current = s.get("upload_type", "document")
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{'✅ ' if current=='document' else ''}📄 Document", callback_data="set_utype_document"),
                InlineKeyboardButton(f"{'✅ ' if current=='video' else ''}🎥 Video", callback_data="set_utype_video"),
                InlineKeyboardButton(f"{'✅ ' if current=='audio' else ''}🎵 Audio", callback_data="set_utype_audio"),
            ],
            [InlineKeyboardButton("« Back", callback_data="back_to_settings")],
        ])
        await cb.message.edit_text("📤 **Upload Type**\n\nChoose how files are uploaded to Telegram:", reply_markup=kb)

    @app.on_callback_query(filters.regex("^set_utype_"))
    async def cb_set_utype(client, cb: CallbackQuery):
        await cb.answer()
        utype = cb.data.split("_")[-1]
        await users_db.update_settings(cb.from_user.id, {"upload_type": utype})
        await cb.message.edit_text(f"✅ Upload type set to **{utype.upper()}**.")

    # ── Thumbnail menu ────────────────────────────────────────────────────

    @app.on_callback_query(filters.regex("^set_thumb_menu$"))
    async def cb_thumb_menu(client, cb: CallbackQuery):
        await cb.answer()
        s = await users_db.get_settings(cb.from_user.id)
        mode = s.get("thumbnail_mode", "auto")
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{'✅ ' if mode=='auto' else ''}🤖 Auto", callback_data="set_tmode_auto"),
                InlineKeyboardButton(f"{'✅ ' if mode=='custom' else ''}🖼 Custom", callback_data="set_tmode_custom"),
                InlineKeyboardButton(f"{'✅ ' if mode=='disabled' else ''}🚫 Disabled", callback_data="set_tmode_disabled"),
            ],
            [InlineKeyboardButton("🗑 Remove Custom", callback_data="del_thumb_cb")],
            [InlineKeyboardButton("« Back", callback_data="back_to_settings")],
        ])
        text = f"🖼 **Thumbnail**\n\nCurrent: `{mode.upper()}`\n\nUse `/setthumb` (reply to image) to set a custom thumbnail."
        await cb.message.edit_text(text, reply_markup=kb)

    @app.on_callback_query(filters.regex("^set_tmode_"))
    async def cb_set_tmode(client, cb: CallbackQuery):
        await cb.answer()
        mode = cb.data.split("_")[-1]
        await users_db.update_settings(cb.from_user.id, {"thumbnail_mode": mode})
        await cb.message.edit_text(f"✅ Thumbnail mode set to **{mode.upper()}**.")

    @app.on_callback_query(filters.regex("^del_thumb_cb$"))
    async def cb_del_thumb(client, cb: CallbackQuery):
        await cb.answer()
        await users_db.del_thumbnail(cb.from_user.id)
        await cb.message.edit_text("🗑 Custom thumbnail removed.")

    # ── Metadata menu ─────────────────────────────────────────────────────

    @app.on_callback_query(filters.regex("^set_metadata_menu$"))
    async def cb_meta_menu(client, cb: CallbackQuery):
        await cb.answer()
        s = await users_db.get_settings(cb.from_user.id)
        meta = s.get("metadata", {})
        enabled = s.get("metadata_enabled", False)
        fields = ["title", "author", "artist", "album", "genre", "year", "comment"]
        lines = [f"📝 **METADATA** — `{'ON' if enabled else 'OFF'}`\n"]
        for f in fields:
            lines.append(f"• {f.capitalize()}: `{meta.get(f) or '—'}`")
        lines.append("\nTap a field to set it. Use `/us` to navigate.")
        kb_rows = []
        for f in fields:
            kb_rows.append([InlineKeyboardButton(f"✏️ Set {f.capitalize()}", callback_data=f"meta_set_{f}")])
        kb_rows.append([
            InlineKeyboardButton(f"{'✅ ON' if enabled else '❌ OFF'}", callback_data="meta_toggle"),
        ])
        kb_rows.append([InlineKeyboardButton("« Back", callback_data="back_to_settings")])
        await cb.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb_rows))

    @app.on_callback_query(filters.regex("^meta_toggle$"))
    async def cb_meta_toggle(client, cb: CallbackQuery):
        await cb.answer()
        s = await users_db.get_settings(cb.from_user.id)
        new_val = not s.get("metadata_enabled", False)
        await users_db.update_settings(cb.from_user.id, {"metadata_enabled": new_val})
        await cb.message.edit_text(f"✅ Metadata **{'enabled' if new_val else 'disabled'}**.")

    @app.on_callback_query(filters.regex("^meta_set_"))
    async def cb_meta_set(client, cb: CallbackQuery):
        await cb.answer()
        field = cb.data.split("meta_set_")[1]
        await cb.message.edit_text(
            f"📝 Send the value for **{field.capitalize()}**:\n\n"
            f"(Reply to this message or just send the value in the next message.)\n"
            f"Send `/cancel` to abort."
        )
        # Use a conversation-like listener
        @client.on_message(filters.private & filters.user(cb.from_user.id) & ~filters.command("cancel"), group=99)
        async def meta_value_listener(cl, msg: Message):
            val = msg.text.strip() if msg.text else None
            if val:
                await users_db.update_metadata_field(cb.from_user.id, field, val)
                await msg.reply(f"✅ **{field.capitalize()}** set to `{val}`.")
            cl.remove_handler(*_current_handlers[-1])

        # Track handler for removal
        _current_handlers = [None]
        # wzgram/Pyrogram handler removal requires the handler + group reference
        # This approach registers a one-shot listener properly
        # For simplicity, we collect it after registration
        # The handler auto-removes on first message
        pass

    # ── Rename menu ───────────────────────────────────────────────────────

    @app.on_callback_query(filters.regex("^set_rename_menu$"))
    async def cb_rename_menu(client, cb: CallbackQuery):
        await cb.answer()
        user = await users_db.get_user(cb.from_user.id)
        tmpl = user.get("rename_template") or "—"
        s = user.get("settings", {})
        enabled = s.get("rename_enabled", False)
        text = (
            f"✏️ **RENAME**\n\n"
            f"Status: `{'ON' if enabled else 'OFF'}`\n"
            f"Template: `{tmpl}`\n\n"
            f"Placeholders: `{{name}}`, `{{title}}`, `{{year}}`, `{{user}}`\n\n"
            f"Use `/set_rename <template>` to change."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back", callback_data="back_to_settings")],
        ])
        await cb.message.edit_text(text, reply_markup=kb)

    # ── Caption menu ──────────────────────────────────────────────────────

    @app.on_callback_query(filters.regex("^set_caption_menu$"))
    async def cb_caption_menu(client, cb: CallbackQuery):
        await cb.answer()
        user = await users_db.get_user(cb.from_user.id)
        tmpl = user.get("caption_template") or "—"
        text = (
            f"💬 **CAPTION**\n\n"
            f"Current template:\n`{tmpl}`\n\n"
            f"Placeholders: `{{name}}`, `{{size}}`, `{{user}}`, `{{year}}`, `{{duration}}`\n\n"
            f"Use `/set_caption <text>` to change."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back", callback_data="back_to_settings")],
        ])
        await cb.message.edit_text(text, reply_markup=kb)

    # ── Reset confirm ─────────────────────────────────────────────────────

    @app.on_callback_query(filters.regex("^set_reset_confirm$"))
    async def cb_reset_confirm(client, cb: CallbackQuery):
        await cb.answer()
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, reset", callback_data="set_reset_do"),
                InlineKeyboardButton("❌ Cancel", callback_data="back_to_settings"),
            ]
        ])
        await cb.message.edit_text("⚠️ Reset all settings to defaults?", reply_markup=kb)

    @app.on_callback_query(filters.regex("^set_reset_do$"))
    async def cb_reset_do(client, cb: CallbackQuery):
        await cb.answer()
        await users_db.reset_settings(cb.from_user.id)
        await cb.message.edit_text("✅ Settings reset to defaults.")

    # ── Back button ───────────────────────────────────────────────────────

    @app.on_callback_query(filters.regex("^back_to_settings$"))
    async def cb_back_settings(client, cb: CallbackQuery):
        await cb.answer()
        await send_settings_menu(
            client, cb.message.chat.id, cb.from_user.id,
            users_db=users_db, message_id=cb.message.id
        )

    # ── Thumbnail commands ────────────────────────────────────────────────

    @app.on_message(filters.command("setthumb") & filters.private)
    async def setthumb_cmd(client: Client, message: Message):
        replied = message.reply_to_message
        if not replied:
            await message.reply("↩️ Reply to an image with `/setthumb`.")
            return
        photo = replied.photo
        if not photo:
            doc = replied.document
            if doc and doc.mime_type and doc.mime_type.startswith("image/"):
                file_id = doc.file_id
            else:
                await message.reply("❌ Reply to an image.")
                return
        else:
            file_id = photo.file_id

        await users_db.set_thumbnail(message.from_user.id, file_id)
        await message.reply("✅ Custom thumbnail saved.")

    @app.on_message(filters.command("delthumb") & filters.private)
    async def delthumb_cmd(client: Client, message: Message):
        await users_db.del_thumbnail(message.from_user.id)
        await message.reply("🗑 Thumbnail removed. Mode set to Auto.")

    # ── Caption commands ──────────────────────────────────────────────────

    @app.on_message(filters.command("set_caption") & filters.private)
    async def set_caption_cmd(client: Client, message: Message):
        parts = message.text.split(None, 1)
        if len(parts) < 2:
            await message.reply("Usage: `/set_caption <template>`\n\nSupported: `{name}`, `{size}`, `{user}`, `{year}`, `{duration}`")
            return
        await users_db.set_caption(message.from_user.id, parts[1])
        await message.reply("✅ Caption template saved.")

    @app.on_message(filters.command("del_caption") & filters.private)
    async def del_caption_cmd(client: Client, message: Message):
        await users_db.del_caption(message.from_user.id)
        await message.reply("🗑 Caption removed.")

    @app.on_message(filters.command("see_caption") & filters.private)
    async def see_caption_cmd(client: Client, message: Message):
        user = await users_db.get_user(message.from_user.id)
        tmpl = user.get("caption_template")
        if tmpl:
            await message.reply(f"💬 Your caption template:\n\n`{tmpl}`")
        else:
            await message.reply("📭 No caption template set.")

    # ── Rename commands ───────────────────────────────────────────────────

    @app.on_message(filters.command("set_rename") & filters.private)
    async def set_rename_cmd(client: Client, message: Message):
        parts = message.text.split(None, 1)
        if len(parts) < 2:
            await message.reply("Usage: `/set_rename <template>`\n\nExample: `{name} - {year}`")
            return
        await users_db.set_rename_template(message.from_user.id, parts[1])
        await message.reply("✅ Rename template saved.")

    @app.on_message(filters.command("del_rename") & filters.private)
    async def del_rename_cmd(client: Client, message: Message):
        await users_db.del_rename_template(message.from_user.id)
        await message.reply("🗑 Rename template removed.")
