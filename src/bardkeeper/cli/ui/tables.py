"""
Rich tables for BardKeeper UI.
"""

from datetime import datetime
from typing import Optional

from rich.table import Table
from rich import box

from ...data.models import Job, SyncStatus


def format_datetime(timestamp: Optional[datetime]) -> str:
    """Format a timestamp for display."""
    if not timestamp:
        return "Never"

    try:
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(timestamp)


def get_status_emoji(status: SyncStatus) -> str:
    """Get emoji for sync status."""
    if isinstance(status, str):
        status = SyncStatus(status)

    status_map = {
        SyncStatus.NEVER_RUN: '🔄',
        SyncStatus.RUNNING: '⏳',
        SyncStatus.COMPLETED: '✅',
        SyncStatus.FAILED: '❌',
        SyncStatus.CANCELLED: '⏸️',
    }
    return status_map.get(status, '❓')


def jobs_table(jobs: list[dict]) -> Table:
    """Create a rich table for displaying all sync jobs."""
    table = Table(box=box.ROUNDED)

    # Add columns
    table.add_column("Name", style="cyan bold")
    table.add_column("Remote", style="magenta")
    table.add_column("Local Path", style="green")
    table.add_column("Last Synced", style="yellow")
    table.add_column("Status", style="bold")
    table.add_column("Compressed", style="blue")
    table.add_column("Scheduled", style="dim")

    # Add rows
    for job in jobs:
        # Format remote info
        ssh_port = job.get('ssh_port', 22)
        port_str = f":{ssh_port}" if ssh_port != 22 else ""
        remote = f"{job['username']}@{job['host']}{port_str}:{job['remote_path']}"

        # Format status
        status_emoji = get_status_emoji(job['sync_status'])
        status_str = job['sync_status'].replace('_', ' ').title()
        status = f"{status_emoji} {status_str}"

        # Format schedule
        if job.get('cron_schedule'):
            # Add next sync time if available
            if job.get('next_sync'):
                next_time = format_datetime(job['next_sync']).split()[1]
                schedule = f"{job['cron_schedule']} (Next: {next_time})"
            else:
                schedule = job['cron_schedule']
        else:
            schedule = "Manual only"

        # Add row
        table.add_row(
            job['name'],
            remote,
            str(job['local_path']),
            format_datetime(job.get('last_synced')),
            status,
            "Yes" if job.get('use_compression') else "No",
            schedule
        )

    return table


def job_info_table(job: dict, tree_lines: Optional[list[str]] = None) -> Table:
    """Create a detailed table for a single job."""
    table = Table(box=box.ROUNDED, show_header=False, expand=True)

    # Define columns
    table.add_column("Property", style="cyan bold")
    table.add_column("Value")

    # Add basic info rows
    table.add_row("Name", job['name'])
    table.add_row("Host", job['host'])
    table.add_row("Username", job['username'])
    table.add_row("Remote Path", job['remote_path'])
    table.add_row("Local Path", str(job['local_path']))

    # SSH settings
    ssh_port = job.get('ssh_port', 22)
    if ssh_port != 22:
        table.add_row("SSH Port", str(ssh_port))

    if job.get('ssh_key_path'):
        table.add_row("SSH Key", str(job['ssh_key_path']))

    # Format status with emoji
    status_emoji = get_status_emoji(job['sync_status'])
    status_str = job['sync_status'].replace('_', ' ').title()
    status = f"{status_emoji} {status_str}"
    table.add_row("Status", status)

    # Last error if present
    if job.get('last_error'):
        table.add_row("Last Error", job['last_error'])

    # Last and next sync times
    table.add_row("Last Synced", format_datetime(job.get('last_synced')))
    if job.get('next_sync'):
        table.add_row("Next Sync", format_datetime(job['next_sync']))

    # Transfer statistics
    if job.get('last_sync_duration'):
        duration = job['last_sync_duration']
        table.add_row("Last Sync Duration", f"{duration:.2f}s")

    if job.get('bytes_transferred'):
        bytes_val = job['bytes_transferred']
        mb_val = bytes_val / (1024 * 1024)
        table.add_row("Bytes Transferred", f"{mb_val:.2f} MB")

    # Other settings
    table.add_row("Compression", "Enabled" if job.get('use_compression') else "Disabled")
    table.add_row("Progress Tracking", "Enabled" if job.get('track_progress') else "Disabled")
    table.add_row("Delete Remote Files", "Yes" if job.get('delete_remote', True) else "No")

    if job.get('bandwidth_limit'):
        table.add_row("Bandwidth Limit", f"{job['bandwidth_limit']} KB/s")

    if job.get('exclude_patterns'):
        patterns = ", ".join(job['exclude_patterns'])
        table.add_row("Exclude Patterns", patterns)

    # Schedule
    if job.get('cron_schedule'):
        table.add_row("Schedule", job['cron_schedule'])
    else:
        table.add_row("Schedule", "Manual only")

    # Add directory tree if provided
    if tree_lines:
        table.add_row("", "")
        table.add_row("Directory Structure", "")

        for line in tree_lines:
            table.add_row("", line)

    return table


def config_table(config: dict) -> Table:
    """Create a table for configuration settings."""
    table = Table(box=box.ROUNDED, show_header=False, expand=True)

    # Define columns
    table.add_column("Setting", style="cyan bold")
    table.add_column("Value")

    # Add rows for each config item
    for key, value in config.items():
        # Skip internal keys (those starting with underscore)
        if not key.startswith('_'):
            table.add_row(key.replace('_', ' ').title(), str(value))

    return table
