"""
Fixed Progress Tracking for Rsync Operations

Solves the 0% stuck bug by:
1. Using rsync's --info=progress2 for consistent output
2. Parsing total transfer progress instead of per-file
3. Providing fallback for non-progress output
4. Always updating to 100% on completion
"""

import re
from dataclasses import dataclass
from typing import Optional

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
    TaskID,
    SpinnerColumn,
)


@dataclass
class SyncProgress:
    """Parsed rsync progress information."""
    percent: int
    bytes_transferred: int = 0
    transfer_rate: str = ""
    eta: str = ""


# Regex for --info=progress2 output format:
# "1,234,567 100%  123.45kB/s    0:00:10 (xfr#1, to-chk=0/10)"
PROGRESS2_PATTERN = re.compile(
    r'^\s*([\d,]+)\s+(\d+)%\s+([\d.]+\w+/s)\s+(\d+:\d+:\d+|\d+:\d+)',
    re.MULTILINE
)

# Fallback pattern for --progress output
SIMPLE_PROGRESS_PATTERN = re.compile(r'^\s*(\d+)%\s', re.MULTILINE)


def parse_rsync_progress(line: str) -> Optional[SyncProgress]:
    """
    Parse rsync progress output line.

    Uses --info=progress2 format for accurate total progress.
    Falls back to simple percentage if format differs.
    """
    # Try progress2 format first
    match = PROGRESS2_PATTERN.search(line)
    if match:
        bytes_str, percent, rate, eta = match.groups()
        return SyncProgress(
            percent=int(percent),
            bytes_transferred=int(bytes_str.replace(',', '')),
            transfer_rate=rate,
            eta=eta,
        )

    # Fallback to simple percentage
    match = SIMPLE_PROGRESS_PATTERN.search(line)
    if match:
        return SyncProgress(
            percent=int(match.group(1)),
            bytes_transferred=0,
            transfer_rate="",
            eta="",
        )

    return None


class SyncProgressDisplay:
    """
    Manages progress display for sync operations.

    Features:
    - Handles both progress tracking and spinner modes
    - Always shows completion state
    - Displays transfer statistics
    """

    def __init__(self, job_name: str, track_progress: bool = True):
        self.job_name = job_name
        self.track_progress = track_progress
        self._progress: Optional[Progress] = None
        self._task_id: Optional[TaskID] = None
        self._last_percent = 0

    def __enter__(self):
        if self.track_progress:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
            )
        else:
            # Spinner mode for non-progress tracking
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                TextColumn("[dim]{task.fields[status]}"),
            )

        self._progress.start()

        if self.track_progress:
            self._task_id = self._progress.add_task(
                f"Syncing {self.job_name}",
                total=100
            )
        else:
            self._task_id = self._progress.add_task(
                f"Syncing {self.job_name}",
                total=None,
                status="Starting..."
            )

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._progress:
            # Always complete the task visually
            if exc_type is None and self._task_id is not None:
                if self.track_progress:
                    self._progress.update(self._task_id, completed=100)
                else:
                    self._progress.update(self._task_id, status="Complete")
            self._progress.stop()

    def update(self, sync_progress: Optional[SyncProgress] = None, status: str = ""):
        """Update progress display."""
        if not self._progress or self._task_id is None:
            return

        if self.track_progress and sync_progress:
            # Only update if progress increased (avoid flickering)
            if sync_progress.percent >= self._last_percent:
                self._progress.update(
                    self._task_id,
                    completed=sync_progress.percent,
                )
                self._last_percent = sync_progress.percent
        elif not self.track_progress and status:
            self._progress.update(self._task_id, status=status)

    def set_error(self, error: str):
        """Display error state."""
        if self._progress and self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=f"[bold red]Failed: {self.job_name}",
            )
