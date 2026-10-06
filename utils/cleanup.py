import os
import shutil
from utils.logger import logger


def remove_file(path: str) -> None:
    try:
        if path and os.path.isfile(path):
            os.remove(path)
            logger.info(f"Deleted file: {path}")
    except Exception as e:
        logger.warning(f"Failed to delete file {path}: {e}")


def remove_dir(path: str) -> None:
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            logger.info(f"Deleted directory: {path}")
    except Exception as e:
        logger.warning(f"Failed to delete directory {path}: {e}")


def cleanup_job_dir(download_dir: str, job_id: str) -> None:
    from utils.validation import safe_job_path
    try:
        job_path = safe_job_path(download_dir, job_id)
        remove_dir(job_path)
    except Exception as e:
        logger.warning(f"cleanup_job_dir error for {job_id}: {e}")


async def startup_cleanup(download_dir: str, db_jobs) -> None:
    """
    On startup, mark any 'downloading'/'uploading'/'processing' jobs as
    'interrupted' since Render ephemeral storage is wiped on restart.
    """
    try:
        await db_jobs.mark_interrupted_jobs()
        logger.info("Startup cleanup: interrupted jobs marked")
    except Exception as e:
        logger.warning(f"startup_cleanup error: {e}")
