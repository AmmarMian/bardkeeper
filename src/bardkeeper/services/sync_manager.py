"""
High-level sync job management with file-based locking for concurrent safety.
"""

import logging
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from filelock import FileLock, Timeout as LockTimeout

try:
    from croniter import croniter
except ImportError:
    croniter = None

from ..data.models import Job, SyncStatus, SyncDirection
from ..exceptions import (
    JobNotFoundError,
    SyncAlreadyRunningError,
    BardKeeperError,
)
from ..core.rsync import RsyncManager, SyncProgress
from ..core.compression import CompressionManager

logger = logging.getLogger(__name__)


class SyncLockManager:
    """
    Manages locks for sync operations to prevent concurrent syncs.

    Uses file-based locks for cross-process safety.
    """

    def __init__(self, lock_dir: Optional[Path] = None):
        self.lock_dir = lock_dir or Path("~/.bardkeeper/locks").expanduser()
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def acquire_job_lock(self, job_name: str, timeout: float = 0.1):
        """
        Acquire exclusive lock for a job.

        Args:
            job_name: Name of the job to lock
            timeout: Lock timeout in seconds (default: 0.1 for non-blocking)

        Raises:
            SyncAlreadyRunningError: If job is already being synced
        """
        lock_file = self.lock_dir / f"{job_name}.lock"
        lock = FileLock(str(lock_file), timeout=timeout)

        try:
            lock.acquire(timeout=timeout)
        except LockTimeout:
            raise SyncAlreadyRunningError(
                f"Job '{job_name}' is already being synced by another process"
            )

        try:
            yield
        finally:
            try:
                lock.release()
                # Clean up lock file
                lock_file.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to clean up lock file: {e}")


class SyncManager:
    """High-level sync job management with locking and scheduling."""

    def __init__(
        self,
        db,
        rsync_manager: Optional[RsyncManager] = None,
        lock_manager: Optional[SyncLockManager] = None,
    ):
        """Initialize the sync manager."""
        self.db = db
        self.rsync = rsync_manager or RsyncManager(db)
        self.lock_manager = lock_manager or SyncLockManager()
        self.compression_manager = CompressionManager()

    def add_sync_job(
        self,
        name: str,
        host: str,
        username: str,
        remote_path: str,
        local_path: Path,
        use_compression: bool = False,
        cron_schedule: Optional[str] = None,
        track_progress: bool = True,
        ssh_port: int = 22,
        ssh_key_path: Optional[Path] = None,
        ssh_timeout: int = 30,
        delete_remote: bool = True,
        bandwidth_limit: Optional[int] = None,
        exclude_patterns: Optional[list[str]] = None,
        sync_direction: SyncDirection = SyncDirection.PULL,
    ) -> Job:
        """
        Add a new sync job with validation.

        Args:
            name: Unique job name
            host: Remote host
            username: SSH username
            remote_path: Remote directory path
            local_path: Local destination path
            use_compression: Whether to compress after sync
            cron_schedule: Optional cron schedule string
            track_progress: Whether to track sync progress
            ssh_port: SSH port (default: 22)
            ssh_key_path: Optional path to SSH private key
            ssh_timeout: SSH connection timeout in seconds
            delete_remote: Whether to delete files not present on remote
            bandwidth_limit: Optional bandwidth limit in KB/s
            exclude_patterns: Optional list of exclude patterns
            sync_direction: Sync direction (pull/push/bidirectional)

        Returns:
            Created Job instance

        Raises:
            JobExistsError: If job with this name already exists
            ValueError: If cron schedule is invalid
        """
        # Validate cron schedule if provided
        if cron_schedule and croniter:
            try:
                croniter(cron_schedule, datetime.now())
            except (ValueError, KeyError) as e:
                raise ValueError(f"Invalid cron schedule: {cron_schedule}") from e

        # Add job to database (validation happens in Pydantic model)
        return self.db.add_sync_job(
            name=name,
            host=host,
            username=username,
            remote_path=remote_path,
            local_path=Path(local_path),
            use_compression=use_compression,
            cron_schedule=cron_schedule,
            track_progress=track_progress,
            ssh_port=ssh_port,
            ssh_key_path=ssh_key_path,
            ssh_timeout=ssh_timeout,
            delete_remote=delete_remote,
            bandwidth_limit=bandwidth_limit,
            exclude_patterns=exclude_patterns or [],
            sync_direction=sync_direction,
        )

    def remove_sync_job(self, name: str, remove_files: bool = False) -> bool:
        """
        Remove a sync job and optionally its files.

        Args:
            name: Job name
            remove_files: Whether to remove local files/archives

        Returns:
            True if job was removed

        Raises:
            JobNotFoundError: If job doesn't exist
        """
        job = self.db.get_sync_job(name)
        if not job:
            raise JobNotFoundError(f"No sync job found with name '{name}'")

        # Remove files if requested
        if remove_files:
            # Original directory
            if job.local_path.exists():
                if job.local_path.is_dir():
                    shutil.rmtree(job.local_path)
                else:
                    job.local_path.unlink()

            # Compressed archive if it exists
            if job.use_compression:
                archive_path = self.compression_manager.get_archive_path(job.local_path)
                if archive_path.exists():
                    archive_path.unlink()

        # Remove from database
        return self.db.remove_sync_job(name)

    def sync_job(
        self,
        name: str,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        use_retry: bool = True,
        sync_direction: Optional[SyncDirection] = None,
    ):
        """
        Sync a specific job with locking to prevent concurrent runs.

        Args:
            name: Job name
            progress_callback: Optional progress callback
            status_callback: Optional status message callback
            use_retry: Whether to use retry logic
            sync_direction: Optional direction override (defaults to job.sync_direction)

        Returns:
            SyncResult

        Raises:
            JobNotFoundError: If job doesn't exist
            SyncAlreadyRunningError: If job is already running
            Various sync-related exceptions
        """
        # Acquire lock for this job
        with self.lock_manager.acquire_job_lock(name):
            return self.rsync.sync(name, progress_callback, status_callback, use_retry, sync_direction)

    def should_sync_now(self, job: Job) -> bool:
        """
        Check if a job should be synced now based on cron schedule.

        Args:
            job: Job to check

        Returns:
            True if job should be synced now
        """
        if not job.cron_schedule or not croniter:
            return False

        # If never synced, then yes
        if not job.last_synced:
            return True

        # Create cron iterator from last sync time
        cron = croniter(job.cron_schedule, job.last_synced)

        # Get next run time
        next_time = cron.get_next(datetime)

        # Check if next run time is in the past
        return datetime.now() >= next_time

    def sync_all_due(
        self,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None
    ) -> list[str]:
        """
        Sync all jobs that are due according to their cron schedule.

        Args:
            progress_callback: Optional progress callback

        Returns:
            List of successfully synced job names
        """
        jobs = self.db.get_all_sync_jobs()
        synced = []

        for job in jobs:
            if self.should_sync_now(job):
                try:
                    result = self.sync_job(job.name, progress_callback)
                    if result.success:
                        synced.append(job.name)
                except SyncAlreadyRunningError:
                    logger.info(f"Job '{job.name}' is already running, skipping")
                except Exception as e:
                    logger.error(f"Failed to sync job '{job.name}': {e}")

        return synced

    def update_job(self, name: str, **kwargs) -> Job:
        """
        Update a sync job with changes, handling file operations as needed.

        Args:
            name: Job name
            **kwargs: Fields to update

        Returns:
            Updated Job instance

        Raises:
            JobNotFoundError: If job doesn't exist
            ValueError: If cron schedule is invalid
        """
        job = self.db.get_sync_job(name)
        if not job:
            raise JobNotFoundError(f"No sync job found with name '{name}'")

        # Handle special update cases

        # 1. Local path change: move files
        if 'local_path' in kwargs:
            new_path = Path(kwargs['local_path']).expanduser().resolve()

            if new_path != job.local_path and job.local_path.exists():
                # Move actual files
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(job.local_path), str(new_path))

                # Move compressed archive if it exists
                if job.use_compression:
                    old_archive = self.compression_manager.get_archive_path(job.local_path)
                    new_archive = self.compression_manager.get_archive_path(new_path)

                    if old_archive.exists():
                        new_archive.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(old_archive), str(new_archive))

        # 2. Host/Remote path change: reset sync status
        if 'host' in kwargs or 'remote_path' in kwargs:
            kwargs['last_synced'] = None
            kwargs['sync_status'] = SyncStatus.NEVER_RUN

        # 3. Compression change: handle files
        if 'use_compression' in kwargs and kwargs['use_compression'] != job.use_compression:
            if kwargs['use_compression']:  # Turning compression ON
                if job.local_path.exists() and job.local_path.is_dir():
                    try:
                        self.compression_manager.compress_and_cleanup(job.local_path)
                    except Exception as e:
                        raise BardKeeperError(f"Failed to compress directory: {e}")
            else:  # Turning compression OFF
                archive_path = self.compression_manager.get_archive_path(job.local_path)
                if archive_path.exists():
                    try:
                        self.compression_manager.extract_archive(
                            archive_path,
                            job.local_path.parent
                        )
                        archive_path.unlink()
                    except Exception as e:
                        raise BardKeeperError(f"Failed to extract archive: {e}")

        # 4. Validate cron schedule if provided
        if 'cron_schedule' in kwargs and kwargs['cron_schedule'] and croniter:
            try:
                croniter(kwargs['cron_schedule'], datetime.now())
            except (ValueError, KeyError) as e:
                raise ValueError(f"Invalid cron schedule: {kwargs['cron_schedule']}") from e

        # Update in database
        return self.db.update_sync_job(name, **kwargs)

    def get_all_jobs_status(self) -> list[dict]:
        """
        Get status of all jobs including next sync time.

        Returns:
            List of job dictionaries with status information
        """
        jobs = self.db.get_all_sync_jobs()
        result = []

        for job in jobs:
            # Calculate next sync time if cron is set
            next_sync = None
            if job.cron_schedule and job.last_synced and croniter:
                try:
                    cron = croniter(job.cron_schedule, job.last_synced)
                    next_sync = cron.get_next(datetime)
                except Exception:
                    next_sync = None

            # Add job to result with additional info
            job_dict = job.to_dict()
            job_dict['next_sync'] = next_sync.isoformat() if next_sync else None

            result.append(job_dict)

        return result
