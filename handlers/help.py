from wzgram import Client, filters
from wzgram.types import Message

HELP_TEXT = """\
**📖 COMMANDS**

`/l <magnet|URL>` — Leech a torrent
`/s` or `/status` — Show your active job status
`/queue` — List your queued jobs
`/cancel` — Cancel your active job
`/us` — Open user settings

**🖼 Thumbnails**
`/setthumb` — Reply to an image to set as thumbnail
`/delthumb` — Remove custom thumbnail

**💬 Caption**
`/set_caption <text>` — Set upload caption (supports `{name}`, `{size}`, `{user}`, `{year}`, `{duration}`)
`/del_caption` — Remove caption
`/see_caption` — Show current caption

**✏️ Rename**
`/set_rename <template>` — e.g. `{name} - {year}`
`/del_rename` — Remove rename template

**ℹ️ Tips**
• Send a `.torrent` file directly to the bot.
• Multiple files in a torrent are all uploaded.
• Progress is shown in a single updating message.
"""


def register(app: Client, **_):
    @app.on_message(filters.command("help") & filters.private)
    async def help_cmd(client: Client, message: Message):
        await message.reply(HELP_TEXT)
