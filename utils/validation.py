import re
import os

MAGNET_PATTERN = re.compile(
    r"^magnet:\?xt=urn:btih:[a-fA-F0-9]{40,}",
    re.IGNORECASE,
)
TORRENT_URL_PATTERN = re.compile(
    r"^https?://[^\s]+\.torrent(\?[^\s]*)?$",
    re.IGNORECASE,
)
# Also allow generic http(s) URLs that might redirect to a .torrent
HTTP_URL_PATTERN = re.compile(r"^https?://[^\s]+", re.IGNORECASE)


def is_magnet(text: str) -> bool:
    return bool(MAGNET_PATTERN.match(text.strip()))


def is_torrent_url(text: str) -> bool:
    return bool(TORRENT_URL_PATTERN.match(text.strip()))


def is_http_url(text: str) -> bool:
    return bool(HTTP_URL_PATTERN.match(text.strip()))


def sanitize_filename(name: str) -> str:
    """Remove characters unsafe for Linux filenames and Telegram."""
    # Replace path separators
    name = name.replace("/", "_").replace("\\", "_")
    # Remove control characters and other dangerous chars
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Limit length
    if len(name) > 200:
        base, ext = os.path.splitext(name)
        name = base[: 200 - len(ext)] + ext
    return name or "unnamed"


def safe_job_path(base_dir: str, job_id: str) -> str:
    """Return a safe, isolated directory for this job."""
    # job_id must only contain alphanumeric and hyphens
    if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
        raise ValueError(f"Invalid job_id: {job_id}")
    path = os.path.realpath(os.path.join(base_dir, job_id))
    base_real = os.path.realpath(base_dir)
    if not path.startswith(base_real + os.sep) and path != base_real:
        raise ValueError("Path traversal detected")
    return path
