import os
import re
from utils.formatting import human_size

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".m2ts"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wav", ".wma"}


def resolve_caption(template: str | None, context: dict) -> str | None:
    """Replace {placeholder} tokens in a caption template."""
    if not template:
        return None

    def replacer(match):
        key = match.group(1).strip()
        return str(context.get(key, ""))

    return re.sub(r"\{(\w+)\}", replacer, template)


def build_caption_context(
    file_path: str,
    job: dict,
    user_id: int,
    username: str = "",
    duration: int = 0,
) -> dict:
    size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    name = os.path.basename(file_path)
    return {
        "name": name,
        "size": human_size(size_bytes),
        "duration": f"{duration // 60}m {duration % 60}s" if duration else "",
        "user": username or str(user_id),
        "year": __import__("datetime").datetime.now().year,
    }


def detect_upload_type(file_path: str, preferred: str) -> str:
    """
    Detect appropriate upload type for a file.
    preferred: 'document' | 'video' | 'audio'
    Returns the final upload type.
    """
    if preferred == "document":
        return "document"

    ext = os.path.splitext(file_path)[1].lower()

    if preferred == "video":
        if ext in VIDEO_EXTS:
            return "video"
        return "document"

    if preferred == "audio":
        if ext in AUDIO_EXTS:
            return "audio"
        return "document"

    # Auto
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return "document"
