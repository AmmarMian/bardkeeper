"""
Rich tables for BardKeeper UI
"""

from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich import box


def format_datetime(timestamp):
    """Format a timestamp for display"""
    if not timestamp:
        return "Never"
    
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp


def get_status_emoji(status):
    """Get emoji for sync status"""
    status_map = {
        'never_run': '🔄',
        'running': '⏳',
        'completed': '✅',
        'failed': '❌',
    }
    return status_map.get(status, '❓')


def jobs_table(jobs):
    """Create a rich table for displaying all sync jobs"""
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
        remote = f"{job['username']}@{job['host']}:{job['remote_path']}"
        
        # Format status
        status_emoji = get_status_emoji(job['sync_status'])
        status = f"{status_emoji} {job['sync_status'].replace('_', ' ').title()}"
        
        # Format schedule
        if job['cron_schedule']:
            # Add next sync time if available
            if 'next_sync' in job and job['next_sync']:
                schedule = f"{job['cron_schedule']} (Next: {format_datetime(job['next_sync']).split()[1]})"
            else:
                schedule = job['cron_schedule']
        else:
            schedule = "Manual only"
        
        # Add row
        table.add_row(
            job['name'],
            remote,
            job['local_path'],
            format_datetime(job['last_synced']),
            status,
            "Yes" if job['use_compression'] else "No",
            schedule
        )
    
    return table


def job_info_table(job, tree_lines=None):
    """Create a detailed table for a single job"""
    table = Table(box=box.ROUNDED, show_header=False, expand=True)
    
    # Define columns
    table.add_column("Property", style="cyan bold")
    table.add_column("Value")
    
    # Add basic info rows
    table.add_row("Name", job['name'])
    table.add_row("Host", job['host'])
    table.add_row("Username", job['username'])
    table.add_row("Remote Path", job['remote_path'])
    table.add_row("Local Path", job['local_path'])
    
    # Format status with emoji
    status_emoji = get_status_emoji(job['sync_status'])
    status = f"{status_emoji} {job['sync_status'].replace('_', ' ').title()}"
    table.add_row("Status", status)
    
    # Last and next sync times
    table.add_row("Last Synced", format_datetime(job['last_synced']))
    if 'next_sync' in job and job['next_sync']:
        table.add_row("Next Sync", format_datetime(job['next_sync']))
    
    # Other settings
    table.add_row("Compression", "Enabled" if job['use_compression'] else "Disabled")
    table.add_row("Progress Tracking", "Enabled" if job['track_progress'] else "Disabled")
    
    # Schedule
    if job['cron_schedule']:
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


def config_table(config):
    """Create a table for configuration settings"""
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
