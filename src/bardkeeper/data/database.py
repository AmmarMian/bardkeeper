"""
Database handler for BardKeeper using TinyDB with Pydantic models.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from tinydb import TinyDB, Query

from ..exceptions import JobNotFoundError, JobExistsError, DatabaseError
from .models import Job, Config, SyncStatus, SyncDirection

DEFAULT_DB_PATH = Path("~/.bardkeeper/database.json").expanduser()


class BardkeeperDB:
    """Database management class for BardKeeper with Pydantic validation."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the database."""
        self.db_path = db_path or DEFAULT_DB_PATH

        # Create directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize TinyDB
        try:
            self.db = TinyDB(str(self.db_path))
            self.sync_jobs = self.db.table("sync_jobs")
            self.config = self.db.table("config")
        except Exception as e:
            raise DatabaseError(f"Failed to initialize database: {e}")

        # Initialize default config if not exists
        if not self.config.all():
            default_config = Config(
                db_path=self.db_path,
                compression_command="tar -czf",
                extraction_command="tar -xzf",
                cache_enabled=False,
                cache_dir=Path("~/.bardkeeper/cache").expanduser(),
            )
            data = default_config.model_dump()
            data["db_path"] = str(data["db_path"])
            data["cache_dir"] = str(data["cache_dir"])
            self.config.insert(data)

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
        exclude_patterns: list[str] = None,
        sync_direction: SyncDirection = SyncDirection.PULL,
    ) -> Job:
        """Add a new sync job to the database with validation."""
        JobQuery = Query()

        # Check if job with this name already exists
        if self.sync_jobs.search(JobQuery.name == name):
            raise JobExistsError(f"A sync job with name '{name}' already exists")

        # Expand local path
        local_path = Path(local_path).expanduser().resolve()

        # If the local_path doesn't include the remote directory name, append it
        remote_basename = os.path.basename(os.path.normpath(remote_path))
        if not str(local_path).endswith(remote_basename):
            local_path = local_path / remote_basename

        # Create and validate job with Pydantic
        job = Job(
            name=name,
            host=host,
            username=username,
            remote_path=remote_path,
            local_path=local_path,
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
            sync_status=SyncStatus.NEVER_RUN,
            last_synced=None,
        )

        self.sync_jobs.insert(job.to_dict())
        return job

    def get_sync_job(self, name: str) -> Optional[Job]:
        """Get a sync job by name."""
        JobQuery = Query()
        jobs = self.sync_jobs.search(JobQuery.name == name)
        if not jobs:
            return None
        return Job.from_dict(jobs[0])

    def get_all_sync_jobs(self) -> list[Job]:
        """Get all sync jobs."""
        return [Job.from_dict(job_dict) for job_dict in self.sync_jobs.all()]

    def update_sync_job(self, name: str, **kwargs) -> Job:
        """Update a sync job with new values."""
        JobQuery = Query()

        current_job = self.get_sync_job(name)
        if not current_job:
            raise JobNotFoundError(f"Sync job '{name}' not found")

        # If updating local_path, expand the path and handle remote basename
        if "local_path" in kwargs:
            local_path = Path(kwargs["local_path"]).expanduser().resolve()

            # If remote_path is being updated, use that instead
            remote_path = kwargs.get("remote_path", current_job.remote_path)
            remote_basename = os.path.basename(os.path.normpath(remote_path))

            # If the local_path doesn't include the remote basename, append it
            if not str(local_path).endswith(remote_basename):
                local_path = local_path / remote_basename

            kwargs["local_path"] = local_path

        # Update the current job data
        job_dict = current_job.to_dict()
        job_dict.update(kwargs)

        # Validate with Pydantic
        updated_job = Job.from_dict(job_dict)

        # Save to database
        self.sync_jobs.update(updated_job.to_dict(), JobQuery.name == name)
        return updated_job

    def remove_sync_job(self, name: str) -> bool:
        """Remove a sync job."""
        JobQuery = Query()
        removed = self.sync_jobs.remove(JobQuery.name == name)
        return len(removed) > 0

    def update_last_synced(
        self,
        name: str,
        timestamp: Optional[datetime] = None,
        duration: Optional[float] = None,
        bytes_transferred: Optional[int] = None,
    ):
        """Update the last_synced field and related metadata of a job."""
        timestamp = timestamp or datetime.now()
        JobQuery = Query()

        update_data = {
            "last_synced": timestamp.isoformat(),
            "sync_status": SyncStatus.COMPLETED.value,
        }

        if duration is not None:
            update_data["last_sync_duration"] = duration
        if bytes_transferred is not None:
            update_data["bytes_transferred"] = bytes_transferred

        self.sync_jobs.update(update_data, JobQuery.name == name)

    def update_sync_status(self, name: str, status: SyncStatus, error: Optional[str] = None):
        """Update the sync_status field of a job."""
        JobQuery = Query()
        update_data = {"sync_status": status.value}

        if error:
            update_data["last_error"] = error
        elif status == SyncStatus.COMPLETED:
            # Clear error on successful completion
            update_data["last_error"] = None

        self.sync_jobs.update(update_data, JobQuery.name == name)

    def get_config(self, key: Optional[str] = None):
        """Get configuration value(s)."""
        config_data = self.config.all()
        if not config_data:
            return None
        config = config_data[0]
        return config.get(key) if key else config

    def update_config(self, **kwargs):
        """Update configuration values."""
        self.config.update(kwargs)

    def close(self):
        """Close the database connection."""
        self.db.close()
