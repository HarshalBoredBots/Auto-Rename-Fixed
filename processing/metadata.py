import asyncio
import os
from utils.logger import logger

SUPPORTED_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


async def apply_metadata(input_path: str, output_path: str, meta: dict) -> bool:
    """
    Apply metadata tags to a media file using FFmpeg.
    Returns True on success. Output file is written to output_path.
    """
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        return False

    # Build -metadata flags
    meta_args = []
    field_map = {
        "title": "title",
        "author": "author",
        "artist": "artist",
        "album": "album",
        "genre": "genre",
        "year": "date",
        "comment": "comment",
    }
    has_any = False
    for our_key, ffmpeg_key in field_map.items():
        val = meta.get(our_key)
        if val:
            meta_args += ["-metadata", f"{ffmpeg_key}={val}"]
            has_any = True

    if not has_any:
        return False

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c", "copy",
        *meta_args,
        output_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=120)
        if proc.returncode == 0 and os.path.exists(output_path):
            logger.info(f"Metadata applied: {output_path}")
            return True
    except asyncio.TimeoutError:
        logger.warning(f"FFmpeg metadata timed out for {input_path}")
    except Exception as e:
        logger.warning(f"FFmpeg metadata failed for {input_path}: {e}")
    return False
