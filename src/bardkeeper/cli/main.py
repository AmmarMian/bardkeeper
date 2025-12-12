"""
BardKeeper CLI interface - Main entry point.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..data.database import BardkeeperDB, DEFAULT_DB_PATH
from ..core.rsync import RsyncManager
from ..core.compression import CompressionManager
from ..services.sync_manager import SyncManager
from ..config import ConfigManager
from ..cli.ui.tables import jobs_table, job_info_table, config_table
from ..cli.ui.menus import (
    select_from_menu,
    prompt_for_job_details,
    prompt_for_config_changes,
)
from ..cli.ui.progress import SyncProgressDisplay, parse_rsync_progress
from ..exceptions import (
    BardKeeperError,
    JobNotFoundError,
    SyncAlreadyRunningError,
    SSHAuthenticationError,
    SSHTimeoutError,
)

# Initialize console for rich output
console = Console()

# Set up logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# Application context
class AppContext:
    """Application context for sharing state between commands."""

    def __init__(self):
        self.db: Optional[BardkeeperDB] = None
        self.rsync_manager: Optional[RsyncManager] = None
        self.sync_manager: Optional[SyncManager] = None
        self.config_manager: Optional[ConfigManager] = None
        self.compression_manager: Optional[CompressionManager] = None

    def init_app(self, db_path: Optional[Path] = None) -> bool:
        """Initialize the application with the given database path."""
        # Check if rsync is installed
        import shutil
        if not shutil.which("rsync"):
            console.print("[bold red]Error: rsync is not installed.[/bold red]")
            console.print("Please install rsync first using your package manager.")
            return False

        # Initialize database
        try:
            self.db = BardkeeperDB(db_path)
            self.compression_manager = CompressionManager()
            self.rsync_manager = RsyncManager(self.db, self.compression_manager)
            self.sync_manager = SyncManager(self.db, self.rsync_manager)
            self.config_manager = ConfigManager(self.db)
            return True
        except Exception as e:
            console.print(f"[bold red]Error initializing BardKeeper: {str(e)}[/bold red]")
            return False


# Create application context
app_ctx = AppContext()


# Define CLI group
@click.group()
@click.version_option(version="2.0.0", package_name="bardkeeper")
@click.option('--db-path', type=click.Path(), help='Path to the database file')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(db_path: Optional[str], verbose: bool):
    """
    BardKeeper - A reliable rsync job manager CLI

    BardKeeper helps you manage your rsync operations between local and remote
    machines with features for tracking, compressing, scheduling, and monitoring syncs.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize application
    db_path_obj = Path(db_path) if db_path else None
    if not app_ctx.init_app(db_path_obj):
        sys.exit(1)


# === LIST COMMAND ===
@cli.command("list")
def list_jobs():
    """Show all managed sync jobs with their status."""
    # Get all jobs with status
    jobs = app_ctx.sync_manager.get_all_jobs_status()

    if not jobs:
        console.print("[yellow]No sync jobs found. Add one with 'bardkeeper add'.[/yellow]")
        return

    # Create and display table
    table = jobs_table(jobs)
    console.print(Panel(table, title="[bold cyan]Managed Sync Jobs[/bold cyan]"))


# === ADD COMMAND ===
@cli.command("add")
@click.option('--name', help='Name for the sync job')
@click.option('--host', help='Remote host address')
@click.option('--username', help='Username for remote host')
@click.option('--remote-path', help='Path on remote host to sync')
@click.option('--local-path', type=click.Path(), help='Local path to sync to')
@click.option('--ssh-port', type=int, default=22, help='SSH port (default: 22)')
@click.option('--ssh-key', type=click.Path(), help='Path to SSH private key')
@click.option('--use-compression/--no-compression', default=False, help='Enable compression after sync')
@click.option('--track-progress/--no-progress', default=True, help='Track sync progress')
@click.option('--cron-schedule', help='Cron schedule for automatic syncs')
def add_job(name, host, username, remote_path, local_path, ssh_port, ssh_key,
            use_compression, track_progress, cron_schedule):
    """Add a new sync job."""
    try:
        # If not all options provided, use interactive mode
        if not all([name, host, username, remote_path, local_path]):
            console.print("[cyan]Interactive mode: Please provide job details[/cyan]")
            details = prompt_for_job_details()
        else:
            details = {
                'name': name,
                'host': host,
                'username': username,
                'remote_path': remote_path,
                'local_path': local_path,
                'ssh_port': ssh_port,
                'ssh_key_path': ssh_key,
                'use_compression': use_compression,
                'track_progress': track_progress,
                'cron_schedule': cron_schedule,
            }

        # Add job
        job = app_ctx.sync_manager.add_sync_job(**details)
        console.print(f"[green]✓[/green] Added sync job '[cyan]{job.name}[/cyan]'")

    except Exception as e:
        console.print(f"[bold red]Error adding sync job: {str(e)}[/bold red]")
        sys.exit(1)


# === REMOVE COMMAND ===
@cli.command("remove")
@click.argument('name')
@click.option('--remove-files', is_flag=True, help='Also remove local files')
def remove_job(name, remove_files):
    """Remove a sync job."""
    try:
        # Confirm deletion
        from rich.prompt import Confirm
        if not Confirm.ask(f"Remove sync job '{name}'?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

        # Remove job
        app_ctx.sync_manager.remove_sync_job(name, remove_files=remove_files)
        console.print(f"[green]✓[/green] Removed sync job '[cyan]{name}[/cyan]'")

    except JobNotFoundError as e:
        console.print(f"[bold red]{str(e)}[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Error removing sync job: {str(e)}[/bold red]")
        sys.exit(1)


# === SYNC COMMAND ===
@cli.command("sync")
@click.argument('name')
@click.option('--no-retry', is_flag=True, help='Disable automatic retry on failure')
def sync_job(name, no_retry):
    """Sync a specific job."""
    try:
        job = app_ctx.db.get_sync_job(name)
        if not job:
            raise JobNotFoundError(f"No sync job found with name '{name}'")

        # Create progress display
        with SyncProgressDisplay(name, track_progress=job.track_progress) as progress:
            def progress_callback(sync_progress):
                progress.update(sync_progress)

            # Execute sync
            result = app_ctx.sync_manager.sync_job(
                name,
                progress_callback=progress_callback,
                use_retry=not no_retry
            )

        if result.success:
            duration_str = f"{result.duration:.2f}s"
            console.print(
                f"[green]✓[/green] Successfully synced '[cyan]{name}[/cyan]' "
                f"in {duration_str}"
            )
        else:
            console.print(f"[bold red]✗[/bold red] Sync failed for '[cyan]{name}[/cyan]'")
            if result.error_message:
                console.print(f"[red]{result.error_message}[/red]")
            sys.exit(1)

    except SyncAlreadyRunningError as e:
        console.print(f"[bold yellow]{str(e)}[/bold yellow]")
        sys.exit(1)
    except SSHAuthenticationError as e:
        console.print(f"[bold red]SSH Authentication Error:[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        sys.exit(1)
    except SSHTimeoutError as e:
        console.print(f"[bold red]SSH Timeout:[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        sys.exit(1)
    except JobNotFoundError as e:
        console.print(f"[bold red]{str(e)}[/bold red]")
        sys.exit(1)
    except BardKeeperError as e:
        console.print(f"[bold red]Error:[/bold red] {e.user_message()}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error: {str(e)}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


# === INFO COMMAND ===
@cli.command("info")
@click.argument('name')
def job_info(name):
    """Show detailed information about a sync job."""
    try:
        job = app_ctx.db.get_sync_job(name)
        if not job:
            raise JobNotFoundError(f"No sync job found with name '{name}'")

        # Get directory tree
        try:
            tree_lines = app_ctx.rsync_manager.get_directory_tree(name, max_depth=2)
        except Exception:
            tree_lines = None

        # Create and display table
        job_dict = job.to_dict()
        table = job_info_table(job_dict, tree_lines)
        console.print(Panel(table, title=f"[bold cyan]Job: {name}[/bold cyan]"))

    except JobNotFoundError as e:
        console.print(f"[bold red]{str(e)}[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        sys.exit(1)


# === CONFIG COMMAND ===
@cli.command("config")
def show_config():
    """Show and modify configuration settings."""
    try:
        config = app_ctx.config_manager.get_config()

        # Show current config
        table = config_table(config)
        console.print(Panel(table, title="[bold cyan]Configuration[/bold cyan]"))

        # Ask if user wants to change anything
        from rich.prompt import Confirm
        if Confirm.ask("Change any settings?"):
            changes = prompt_for_config_changes(config)
            if changes:
                app_ctx.config_manager.update_config(**changes)
                console.print("[green]✓[/green] Configuration updated")

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        sys.exit(1)


# === MANAGE COMMAND ===
@cli.command("manage")
@click.argument('name')
def manage_job(name):
    """Edit settings for an existing sync job."""
    try:
        job = app_ctx.db.get_sync_job(name)
        if not job:
            raise JobNotFoundError(f"No sync job found with name '{name}'")

        # Show current settings
        console.print(f"[cyan]Current settings for job '{name}':[/cyan]")
        job_dict = job.to_dict()
        table = job_info_table(job_dict)
        console.print(table)

        # Prompt for changes
        from rich.prompt import Confirm
        if Confirm.ask("Edit settings?"):
            details = prompt_for_job_details(job_dict)
            # Remove name from details (can't change name)
            details.pop('name', None)

            if details:
                app_ctx.sync_manager.update_job(name, **details)
                console.print(f"[green]✓[/green] Updated job '[cyan]{name}[/cyan]'")

    except JobNotFoundError as e:
        console.print(f"[bold red]{str(e)}[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        sys.exit(1)


if __name__ == '__main__':
    cli()
