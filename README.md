# 🚀 Telegram Torrent / Leech Bot

A production-ready Telegram bot that downloads torrents via aria2 and uploads the files straight back to Telegram. Built with **wzgram** (Pyrogram fork), **MongoDB**, and **aria2 RPC**.

---

## Features

- **Magnet links, `.torrent` files, torrent URLs**
- **Inline progress messages** — single edited message, never spam
- **aria2 RPC backend** — fast, reliable, multi-connection downloads
- **Per-user settings** — upload type, thumbnail, caption, rename, metadata
- **FFmpeg thumbnails** — auto-extracted for video files
- **FFmpeg metadata** — title/author/year/genre applied on upload
- **Queue system** — per-user and global limits, job cancellation
- **Multi-file torrent support** — all files uploaded in sequence
- **MongoDB persistence** — job state survives restarts
- **Render Background Worker** — Docker-based, no web server required

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + quick buttons |
| `/l <magnet\|URL>` | Start a leech job |
| `/s` or `/status` | Show your active job status |
| `/queue` | List all your queued jobs |
| `/cancel` | Cancel your active job |
| `/us` | Open user settings panel |
| `/help` | Full command reference |
| `/setthumb` | Reply to an image to set thumbnail |
| `/delthumb` | Remove custom thumbnail |
| `/set_caption <text>` | Set upload caption template |
| `/del_caption` | Remove caption |
| `/see_caption` | Show current caption |
| `/set_rename <template>` | Set rename template e.g. `{name} - {year}` |
| `/del_rename` | Remove rename template |

**Admin only** (requires `OWNER_ID`):

| Command | Description |
|---------|-------------|
| `/stats` | Bot-wide statistics |
| `/jobs` | List all active jobs |
| `/broadcast <text>` | Send message to all users |
| `/clearqueue` | Cancel all active jobs |
| `/restart` | Graceful restart |

---

## Project Structure

```
telegram-torrent-bot/
├── bot.py                  # Entrypoint
├── config.py               # Environment variable loader
├── requirements.txt
├── Dockerfile
├── render.yaml
├── .env.example
│
├── handlers/               # Telegram command/callback handlers
│   ├── start.py
│   ├── help.py
│   ├── leech.py
│   ├── status.py
│   ├── queue.py
│   ├── cancel.py
│   ├── settings.py
│   └── admin.py
│
├── torrent/                # aria2 integration
│   ├── aria2.py            # aria2 JSON-RPC client + subprocess launcher
│   └── manager.py          # Job lifecycle orchestration
│
├── telegram/               # Telegram upload pipeline
│   ├── uploader.py
│   └── progress.py
│
├── processing/             # Media processing
│   ├── thumbnail.py        # FFmpeg frame extraction
│   ├── metadata.py         # FFmpeg metadata injection
│   ├── rename.py           # Filename template engine
│   └── media.py            # Caption + upload-type helpers
│
├── database/               # MongoDB layer
│   ├── mongo.py
│   ├── users.py
│   └── jobs.py
│
└── utils/
    ├── cleanup.py
    ├── formatting.py
    ├── validation.py
    └── logger.py
```

---

## Quick Start (Local)

### Prerequisites

- Python 3.12+
- `aria2c` installed (`sudo apt install aria2`)
- `ffmpeg` installed (`sudo apt install ffmpeg`)
- MongoDB URI (free tier at [MongoDB Atlas](https://cloud.mongodb.com))
- Telegram API credentials from [my.telegram.org](https://my.telegram.org/apps)
- A bot token from [@BotFather](https://t.me/BotFather)

### Setup

```bash
git clone <this-repo>
cd telegram-torrent-bot

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and fill in all required values

python bot.py
```

---

## Render Deployment

### 1. Create a MongoDB database

Use [MongoDB Atlas](https://cloud.mongodb.com) free tier. Copy your connection URI.

### 2. Connect your repo to Render

1. Push this project to GitHub.
2. Go to [render.com](https://render.com) → **New** → **Background Worker**.
3. Connect your GitHub repo.
4. Render detects `render.yaml` automatically.

### 3. Set environment variables

In Render Dashboard → Environment, set:

| Variable | Value |
|----------|-------|
| `API_ID` | From my.telegram.org |
| `API_HASH` | From my.telegram.org |
| `BOT_TOKEN` | From @BotFather |
| `MONGO_URI` | Your MongoDB Atlas URI |
| `OWNER_ID` | Your Telegram numeric user ID |
| `ARIA2_RPC_SECRET` | Any random string (optional) |

### 4. Deploy

Render builds the Docker image and starts the worker. Logs are available in the Render dashboard.

> **Important:** Render ephemeral storage is wiped on restart. All downloads are temporary. Job state is persisted in MongoDB, and interrupted jobs are marked automatically on startup.

---

## Environment Variables

See `.env.example` for all variables with descriptions.

---

## How It Works

### `/l` — Leech

1. User sends `/l magnet:?xt=urn:btih:…` or a `.torrent` file.
2. A job is created in MongoDB with status `waiting`.
3. The job enters the download queue (controlled by `MAX_CONCURRENT_DOWNLOADS`).
4. aria2 downloads the torrent to `/downloads/<job_id>/`.
5. A single Telegram message is edited every ~5s with download progress.
6. After download, files are processed (thumbnail/metadata/rename if configured).
7. Files are uploaded to Telegram one by one (controlled by `MAX_CONCURRENT_UPLOADS`).
8. Upload progress is shown in the same message.
9. On success: all local files are deleted, job marked `completed`.
10. On failure/cancel: files deleted, job marked `failed`/`cancelled`.

### `/s` / `/status`

Shows the current state of your most active job: progress bar, speed, ETA, seeders.

### `/queue`

Lists all your active jobs with their current status.

### `/cancel`

Cancels your most active job, terminates the aria2 download, and deletes all temporary files.

### `/us` — Settings

Opens an inline keyboard settings panel. Settings are stored per-user in MongoDB and applied to every upload.

---

## Caption Placeholders

| Placeholder | Value |
|-------------|-------|
| `{name}` | File name |
| `{size}` | File size (human-readable) |
| `{user}` | Uploader's user ID |
| `{year}` | Current year |
| `{duration}` | Video duration |

Example: `🎬 {name}\n📦 {size}\n👤 {user}`

---

## Rename Placeholders

| Placeholder | Value |
|-------------|-------|
| `{name}` | Original filename (no extension) |
| `{title}` | Metadata title (if set) |
| `{year}` | Year from metadata settings |
| `{user}` | User ID |

Example: `{name} - {year}` → `MyMovie - 2026.mkv`
