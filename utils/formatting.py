def human_size(size_bytes: int | float) -> str:
    """Convert bytes to human-readable string."""
    if size_bytes < 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def human_speed(speed_bytes: int | float) -> str:
    """Convert bytes/s to human-readable speed."""
    return f"{human_size(speed_bytes)}/s"


def human_eta(seconds: int | float) -> str:
    """Convert seconds to mm:ss or hh:mm:ss string."""
    if seconds <= 0 or seconds == float("inf"):
        return "∞"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}h {minutes:02d}m {secs:02d}s"
    return f"{minutes:02d}m {secs:02d}s"


def progress_bar(percent: float, length: int = 10) -> str:
    filled = int(length * percent / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}]"
