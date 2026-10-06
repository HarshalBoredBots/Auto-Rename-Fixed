import asyncio
import os

from utils.logger import logger

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".m2ts"}


async def extract_thumbnail(video_path: str, output_path: str, seek: int = 5) -> bool:
    """
    Extract a single frame from a video using FFmpeg.
    Returns True on success.
    """
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in VIDEO_EXTS:
        return False

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(seek),
        "-i", video_path,
        "-vframes", "1",
        "-vf", "scale=320:-1",
        "-q:v", "5",
        output_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)
        if proc.returncode == 0 and os.path.exists(output_path):
            return True
    except asyncio.TimeoutError:
        logger.warning(f"FFmpeg thumbnail timed out for {video_path}")
    except Exception as e:
        logger.warning(f"FFmpeg thumbnail failed for {video_path}: {e}")
    return False


async def get_video_duration(video_path: str) -> int:
    """Return video duration in seconds using ffprobe. Returns 0 on failure."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            import json
            data = json.loads(stdout)
            dur = float(data.get("format", {}).get("duration", 0))
            return int(dur)
    except Exception as e:
        logger.warning(f"ffprobe duration failed for {video_path}: {e}")
    return 0
