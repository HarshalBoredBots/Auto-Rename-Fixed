from wzgram import Client, filters
from wzgram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message


def register(app: Client, **_):
    @app.on_message(filters.command("start") & filters.private)
    async def start_cmd(client: Client, message: Message):
        text = (
            "🚀 **Telegram Torrent / Leech Bot**\n\n"
            "Send me a magnet link, `.torrent` file, or torrent URL and I'll "
            "download it and upload all files straight to Telegram.\n\n"
            "**Quick start:** `/l magnet:?xt=urn:btih:…`"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚀 Leech", callback_data="help_leech"),
                InlineKeyboardButton("⚙️ Settings", callback_data="open_settings"),
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="open_status"),
                InlineKeyboardButton("📋 Queue", callback_data="open_queue"),
            ],
            [InlineKeyboardButton("❓ Help", callback_data="open_help")],
        ])
        await message.reply(text, reply_markup=kb)

    @app.on_callback_query(filters.regex("^help_leech$"))
    async def cb_help_leech(client, cb):
        await cb.answer()
        await cb.message.reply(
            "**Leech a torrent:**\n"
            "`/l magnet:?xt=urn:btih:…`\n"
            "or just send a `.torrent` file.\n\n"
            "Track progress with `/s`."
        )

    @app.on_callback_query(filters.regex("^open_help$"))
    async def cb_open_help(client, cb):
        await cb.answer()
        from handlers.help import HELP_TEXT
        await cb.message.reply(HELP_TEXT)

    @app.on_callback_query(filters.regex("^open_status$"))
    async def cb_open_status(client, cb):
        await cb.answer()
        # Trigger the status handler inline
        from handlers.status import send_status
        await send_status(client, cb.message.chat.id, cb.from_user.id)

    @app.on_callback_query(filters.regex("^open_queue$"))
    async def cb_open_queue(client, cb):
        await cb.answer()
        from handlers.queue import send_queue
        await send_queue(client, cb.message.chat.id, cb.from_user.id)

    @app.on_callback_query(filters.regex("^open_settings$"))
    async def cb_open_settings(client, cb):
        await cb.answer()
        from handlers.settings import send_settings_menu
        await send_settings_menu(client, cb.message.chat.id, cb.from_user.id)
