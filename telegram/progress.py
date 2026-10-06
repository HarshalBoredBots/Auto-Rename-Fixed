import asyncio
import time
from typing import Callable, Any

from utils.formatting import human_size, human_speed, human_eta, progress_bar
from utils.logger import logger


class ProgressTracker:
    """Throttles progress message edits to avoid FloodWait."""

    def __init__(self, client, chat_id: int, message_id: int, interval: float = 5.0):
        self.client = client
        self.chat_id = chat_id
        self.message_id = message_id
        self.interval = interval
        self._last_edit = 0.0
        self._last_text = ""

    async def update(self, text: str, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_edit) < self.interval:
            return
        if text == self._last_text:
            return
        try:
            await self.client.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
            )
            self._last_text = text
            self._last_edit = now
        except Exception as e:
            err = str(e).lower()
            if "flood" in err or "420" in err:
                wait = 10
                import re
                m = re.search(r"flood.*?(\d+)", err)
                if m:
                    wait = int(m.group(1)) + 2
                logger.warning(f"FloodWait {wait}s on progress update")
                await asyncio.sleep(wait)
            elif "message is not modified" in err:
                pass
            else:
                logger.debug(f"Progress edit error: {e}")


def format_download_progress(st: dict) -> str:
    pct = st.get("progress", 0.0)
    downloaded = st.get("downloaded", 0)
    total = st.get("total", 0)
    speed = st.get("speed", 0)
    eta = st.get("eta", 0)
    name = st.get("name") or "Unknown"
    seeders = st.get("seeders", 0)

    bar = progress_bar(pct)
    size_str = f"{human_size(downloaded)} / {human_size(total)}" if total else human_size(downloaded)

    text = (
        f"📥 **DOWNLOADING**\n\n"
        f"📁 `{name}`\n\n"
        f"{bar} `{pct:.1f}%`\n"
        f"**Downloaded:** {size_str}\n"
        f"**Speed:** {human_speed(speed)}\n"
        f"**ETA:** {human_eta(eta)}\n"
        f"**Seeds:** {seeders}"
    )
    return text


def format_upload_progress(filename: str, current: int, total: int, speed: float = 0) -> str:
    pct = (current / total * 100) if total > 0 else 0.0
    bar = progress_bar(pct)
    size_str = f"{human_size(current)} / {human_size(total)}"
    speed_str = human_speed(speed) if speed > 0 else "—"
    eta_val = int((total - current) / speed) if speed > 0 and total > current else 0

    return (
        f"📤 **UPLOADING**\n\n"
        f"📁 `{filename}`\n\n"
        f"{bar} `{pct:.1f}%`\n"
        f"**Uploaded:** {size_str}\n"
        f"**Speed:** {speed_str}\n"
        f"**ETA:** {human_eta(eta_val)}"
    )
