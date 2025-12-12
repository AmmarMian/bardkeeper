"""
Pydantic models for BardKeeper data validation.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SyncStatus(str, Enum):
    """Status of a sync job."""
    NEVER_RUN = "never_run"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    """Sync job configuration with validation."""

    # Basic job info
    name: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    host: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    remote_path: str = Field(..., min_length=1)
    local_path: Path

    # SSH settings
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_key_path: Optional[Path] = None
    ssh_timeout: int = Field(default=30, ge=5, le=300)

    # Sync settings
    use_compression: bool = False
    delete_remote: bool = True
    preserve_permissions: bool = True
    track_progress: bool = True
    bandwidth_limit: Optional[int] = None
    exclude_patterns: list[str] = Field(default_factory=list)

    # Scheduling
    cron_schedule: Optional[str] = None

    # Status tracking
    sync_status: SyncStatus = SyncStatus.NEVER_RUN
    last_synced: Optional[datetime] = None
    last_error: Optional[str] = None
    last_sync_duration: Optional[float] = None
    bytes_transferred: Optional[int] = None

    @field_validator('ssh_key_path')
    @classmethod
    def validate_ssh_key(cls, v: Optional[Path]) -> Optional[Path]:
        """Validate SSH key path exists if provided."""
        if v is not None:
            expanded = Path(v).expanduser()
            if not expanded.exists():
                raise ValueError(f"SSH key not found: {expanded}")
            return expanded
        return v

    @field_validator('local_path')
    @classmethod
    def validate_local_path(cls, v: Path) -> Path:
        """Validate and expand local path."""
        expanded = Path(v).expanduser().resolve()
        return expanded

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        data = self.model_dump()
        # Convert Path objects to strings
        if data.get('local_path'):
            data['local_path'] = str(data['local_path'])
        if data.get('ssh_key_path'):
            data['ssh_key_path'] = str(data['ssh_key_path'])
        # Convert datetime to ISO format
        if data.get('last_synced'):
            data['last_synced'] = data['last_synced'].isoformat()
        # Convert enum to string
        data['sync_status'] = data['sync_status'].value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Job':
        """Create Job from dictionary (database record)."""
        # Convert string paths back to Path objects
        if 'local_path' in data and isinstance(data['local_path'], str):
            data['local_path'] = Path(data['local_path'])
        if 'ssh_key_path' in data and data['ssh_key_path']:
            data['ssh_key_path'] = Path(data['ssh_key_path'])
        # Convert ISO datetime string back to datetime
        if 'last_synced' in data and data['last_synced']:
            if isinstance(data['last_synced'], str):
                data['last_synced'] = datetime.fromisoformat(data['last_synced'])
        return cls(**data)


class Config(BaseModel):
    """Application configuration."""

    db_path: Path
    compression_command: str = "tar -czf"
    extraction_command: str = "tar -xzf"
    cache_enabled: bool = False
    cache_dir: Path = Field(default_factory=lambda: Path("~/.bardkeeper/cache").expanduser())

    @field_validator('db_path', 'cache_dir')
    @classmethod
    def expand_path(cls, v: Path) -> Path:
        """Expand user paths."""
        return Path(v).expanduser().resolve()
