"""
BardKeeper CLI interface
"""

import os
import sys
import time
import math
import rich_click as click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from tinydb import TinyDB
from datetime import datetime
import importlib.metadata

# BardKeeper imports
from .database import BardkeeperDB, DEFAULT_DB_PATH
from .rsync import RsyncManager
from .sync_manager import SyncManager
from .config import ConfigManager
from .ui import jobs_table, job_info_table, config_table
from .ui import select_from_menu, prompt_for_job_details, prompt_for_config_changes
from .utils import create_progress_bar, ensure_directory_exists, is_rsync_installed

# Initialize console for rich output
console = Console()

# Application context
class AppContext:
    """Application context for sharing state between commands"""
    def __init__(self):
        self.db = None
        self.rsync_manager = None
        self.sync_manager = None
        self.config_manager = None

    def init_app(self, db_path=None):
        """Initialize the application with the given database path"""
        # Check if rsync is installed
        if not is_rsync_installed():
            console.print("[bold red]Error: rsync is not installed.[/bold red]")
            console.print("Please install rsync first using your package manager.")
            sys.exit(1)
        
        # Initialize database
        try:
            self.db = BardkeeperDB(db_path)
            self.rsync_manager = RsyncManager(self.db)
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
@click.version_option(package_name="bardkeeper")
@click.option('--db-path', help='Path to the database file')
def cli(db_path):
    """
    BardKeeper - A tool for managing rsync-based archives
    
    BardKeeper helps you manage your rsync operations between local and remote
    machines with features for tracking, compressing, and scheduling syncs.
    """
    # Initialize application
    if not app_ctx.init_app(db_path):
        sys.exit(1)


@cli.command("list")
def list_jobs():
    """Show a list of managed syncs with their information"""
    # Get all jobs with status
    jobs = app_ctx.sync_manager.get_all_jobs_status()
    
    if not jobs:
        console.print("[yellow]No sync jobs found. Add one with 'bardkeeper add'.[/yellow]")
        return
    
    # Create and display table
    table = jobs_table(jobs)
    console.print(Panel(table, title="[bold cyan]Managed Sync Jobs[/bold cyan]"))


@cli.command("add")
@click.option('--name', help='Name for the sync job')
@click.option('--host', help='Remote host address')
@click.option('--username', help='Username for remote host')
@click.option('--remote-path', help='Path on remote host to sync')
@click.option('--local-path', help='Local path to sync to')
@click.option('--use-compression/--no-compression', default=False, help='Enable compression after sync')
@click.option('--track-progress/--no-progress', default=False, help='Track sync progress')
@click.option('--cron-schedule', help='Cron schedule for automatic syncing (e.g., "0 3 * * *" for daily at 3 AM)')
def add_job(name, host, username, remote_path, local_path, use_compression, track_progress, cron_schedule):
    """Add a new managed rsync with a name"""
    # If not all required options provided, use interactive prompts
    if not all([name, host, username, remote_path, local_path]):
        details = prompt_for_job_details()
    else:
        details = {
            'name': name,
            'host': host,
            'username': username, 
            'remote_path': remote_path,
            'local_path': local_path,
            'use_compression': use_compression,
            'track_progress': track_progress,
            'cron_schedule': cron_schedule
        }
    
    try:
        # Add the job
        job = app_ctx.sync_manager.add_sync_job(**details)
        console.print(f"[green]Successfully added sync job: [bold]{job['name']}[/bold][/green]")
        
        # Ask if user wants to sync now
        if click.confirm("Do you want to sync this job now?"):
            _sync_job(job['name'])
    
    except Exception as e:
        console.print(f"[bold red]Error adding sync job: {str(e)}[/bold red]")


@cli.command("remove")
@click.argument('name', required=False)
@click.option('--remove-files', is_flag=True, help='Also remove synced files')
def remove_job(name, remove_files):
    """Remove a managed rsync"""
    # If no name provided, show list of jobs to select from
    if not name:
        jobs = app_ctx.db.get_all_sync_jobs()
        
        if not jobs:
            console.print("[yellow]No sync jobs found.[/yellow]")
            return
        
        job_names = [job['name'] for job in jobs]
        job_names.append("Cancel")
        
        selected = select_from_menu("Select job to remove:", job_names)
        
        if not selected or selected == "Cancel":
            console.print("[yellow]Operation cancelled.[/yellow]")
            return
        
        name = selected
    
    # Confirm removal
    if not click.confirm(f"Are you sure you want to remove the sync job '{name}'?"):
        console.print("[yellow]Operation cancelled.[/yellow]")
        return
    
    # If removing files, ask for confirmation
    if remove_files:
        if not click.confirm(f"This will also delete all synced files for '{name}'. Are you sure?"):
            remove_files = False
    
    try:
        # Remove the job
        success = app_ctx.sync_manager.remove_sync_job(name, remove_files)
        
        if success:
            console.print(f"[green]Successfully removed sync job: [bold]{name}[/bold][/green]")
        else:
            console.print(f"[yellow]No sync job found with name: [bold]{name}[/bold][/yellow]")
    
    except Exception as e:
        console.print(f"[bold red]Error removing sync job: {str(e)}[/bold red]")


@cli.command("sync")
@click.argument('name', required=False)
def sync_job(name):
    """Sync a specific job or all jobs"""
    if name:
        _sync_job(name)
    else:
        # No name provided, show list of jobs to select from
        jobs = app_ctx.db.get_all_sync_jobs()
        
        if not jobs:
            console.print("[yellow]No sync jobs found. Add one with 'bardkeeper add'.[/yellow]")
            return
        
        # Add option to sync all jobs
        job_names = ["All Jobs"] + [job['name'] for job in jobs] + ["Cancel"]
        
        selected = select_from_menu("Select job to sync:", job_names)
        
        if not selected or selected == "Cancel":
            console.print("[yellow]Operation cancelled.[/yellow]")
            return
        
        if selected == "All Jobs":
            _sync_all_jobs()
        else:
            _sync_job(selected)


def _sync_job(name):
    """Helper function to sync a specific job"""
    # Check if job exists
    job = app_ctx.db.get_sync_job(name)
    
    if not job:
        console.print(f"[yellow]No sync job found with name: [bold]{name}[/bold][/yellow]")
        return
    
    # Setup progress tracking if enabled
    progress = None
    task = None
    
    if job['track_progress']:
        progress = create_progress_bar()
        task = progress.add_task(f"Syncing {name}", total=100)
        
        def update_progress(percent):
            if progress and task is not None:
                progress.update(task, completed=percent)
    else:
        update_progress = None
        # Use spinner instead
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Syncing {task.description}..."),
        )
        task = progress.add_task(name)
    
    # Start sync with progress
    with progress:
        try:
            success, log_lines = app_ctx.rsync_manager.sync(name, update_progress)
            
            if success:
                console.print(f"[green]Successfully synced job: [bold]{name}[/bold][/green]")
                
                # Show additional info for compressed jobs
                if job['use_compression']:
                    console.print("[blue]Archive compressed and saved.[/blue]")
            else:
                console.print(f"[bold red]Sync failed for job: [bold]{name}[/bold][/bold red]")
                console.print("[yellow]Check the logs for more information.[/yellow]")
        
        except Exception as e:
            console.print(f"[bold red]Error syncing job: {str(e)}[/bold red]")


def _sync_all_jobs():
    """Helper function to sync all jobs"""
    jobs = app_ctx.db.get_all_sync_jobs()
    
    if not jobs:
        console.print("[yellow]No sync jobs found.[/yellow]")
        return
    
    # Create a spinner progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Syncing all jobs..."),
    ) as progress:
        task = progress.add_task("syncing")
        
        for job in jobs:
            try:
                progress.update(task, description=f"Syncing {job['name']}...")
                success, _ = app_ctx.rsync_manager.sync(job['name'])
                
                if not success:
                    console.print(f"[yellow]Warning: Sync failed for job: [bold]{job['name']}[/bold][/yellow]")
            
            except Exception as e:
                console.print(f"[red]Error syncing job {job['name']}: {str(e)}[/red]")
    
    console.print("[green]Finished syncing all jobs.[/green]")


@cli.command("info")
@click.argument('name', required=False)
@click.option('--depth', default=2, help='Directory tree depth (2-5 recommended)')
def job_info(name, depth):
    """Show detailed information about a sync job"""
    # If no name provided, show list of jobs to select from
    if not name:
        jobs = app_ctx.db.get_all_sync_jobs()
        
        if not jobs:
            console.print("[yellow]No sync jobs found. Add one with 'bardkeeper add'.[/yellow]")
            return
        
        job_names = [job['name'] for job in jobs]
        job_names.append("Cancel")
        
        selected = select_from_menu("Select job to view:", job_names)
        
        if not selected or selected == "Cancel":
            console.print("[yellow]Operation cancelled.[/yellow]")
            return
        
        name = selected
    
    # Get job details
    job = app_ctx.db.get_sync_job(name)
    
    if not job:
        console.print(f"[yellow]No sync job found with name: [bold]{name}[/bold][/yellow]")
        return
    
    # Add next sync time if scheduled
    if job['cron_schedule'] and job['last_synced']:
        try:
            from croniter import croniter
            cron = croniter(job['cron_schedule'], datetime.fromisoformat(job['last_synced']))
            job['next_sync'] = cron.get_next(datetime).isoformat()
        except (ImportError, ValueError):
            pass
    
    # Get directory tree if available
    try:
        tree_lines = app_ctx.rsync.get_directory_tree(name, max_depth=depth)
    except Exception:
        tree_lines = ["[Directory information not available]"]
    
    # Create and display info table
    table = job_info_table(job, tree_lines)
    console.print(Panel(table, title=f"[bold cyan]Sync Job: {name}[/bold cyan]"))


@cli.command("config")
def configure():
    """Manage configuration settings"""
    # Get current config
    config = app_ctx.config_manager.get_config()
    
    # Show current config
    table = config_table(config)
    console.print(Panel(table, title="[bold cyan]Current Configuration[/bold cyan]"))
    
    # Ask if user wants to change settings
    if click.confirm("Do you want to change any settings?"):
        # Loop until user is done
        while True:
            # Prompt for changes
            changes = prompt_for_config_changes(config)
            
            if not changes:
                break
            
            # Apply changes
            try:
                app_ctx.config_manager.update_config(**changes)
                console.print("[green]Configuration updated successfully.[/green]")
                
                # Update config for next iteration
                config = app_ctx.config_manager.get_config()
                
                # Show updated config
                table = config_table(config)
                console.print(Panel(table, title="[bold cyan]Updated Configuration[/bold cyan]"))
                
                # Ask if user wants to make more changes
                if not click.confirm("Do you want to make more changes?"):
                    break
            
            except Exception as e:
                console.print(f"[bold red]Error updating configuration: {str(e)}[/bold red]")
                break


@cli.command("manage")
@click.argument('name', required=False)
def manage_job(name):
    """Change information for a managed rsync"""
    # If no name provided, show list command
    if not name:
        list_jobs()
        return
    
    # Get job details
    job = app_ctx.db.get_sync_job(name)
    
    if not job:
        console.print(f"[yellow]No sync job found with name: [bold]{name}[/bold][/yellow]")
        return
    
    # Show current job info
    try:
        tree_lines = app_ctx.rsync.get_directory_tree(name, max_depth=2)
    except Exception:
        tree_lines = None
    
    table = job_info_table(job, tree_lines)
    console.print(Panel(table, title=f"[bold cyan]Sync Job: {name}[/bold cyan]"))
    
    # Ask what to change
    options = [
        "Update Remote Details",
        "Update Local Path",
        "Toggle Compression",
        "Toggle Progress Tracking",
        "Update Schedule",
        "Back to Main Menu"
    ]
    
    selection = select_from_menu("Select what to change:", options)
    
    if not selection or selection == "Back to Main Menu":
        return
    
    try:
        if selection == "Update Remote Details":
            host = click.prompt("Enter new host", default=job['host'])
            username = click.prompt("Enter new username", default=job['username'])
            remote_path = click.prompt("Enter new remote path", default=job['remote_path'])
            
            app_ctx.sync_manager.update_job(
                name,
                host=host,
                username=username,
                remote_path=remote_path
            )
            
            console.print("[green]Remote details updated successfully.[/green]")
            console.print("[yellow]Note: You'll need to sync again to fetch data from the new location.[/yellow]")
        
        elif selection == "Update Local Path":
            local_path = click.prompt("Enter new local path", default=job['local_path'])
            
            app_ctx.sync_manager.update_job(name, local_path=local_path)
            console.print("[green]Local path updated successfully.[/green]")
        
        elif selection == "Toggle Compression":
            new_value = not job['use_compression']
            action = "enabled" if new_value else "disabled"
            
            if click.confirm(f"Are you sure you want to {action} compression?"):
                app_ctx.sync_manager.update_job(name, use_compression=new_value)
                console.print(f"[green]Compression {action} successfully.[/green]")
        
        elif selection == "Toggle Progress Tracking":
            new_value = not job['track_progress']
            action = "enabled" if new_value else "disabled"
            
            app_ctx.sync_manager.update_job(name, track_progress=new_value)
            console.print(f"[green]Progress tracking {action} successfully.[/green]")
        
        elif selection == "Update Schedule":
            has_schedule = job['cron_schedule'] is not None
            
            if has_schedule:
                if click.confirm("Job is currently scheduled. Do you want to disable scheduling?"):
                    app_ctx.sync_manager.update_job(name, cron_schedule=None)
                    console.print("[green]Scheduling disabled successfully.[/green]")
                else:
                    cron_schedule = click.prompt(
                        "Enter new cron schedule (e.g. '0 4 * * *' for daily at 4 AM)",
                        default=job['cron_schedule']
                    )
                    app_ctx.sync_manager.update_job(name, cron_schedule=cron_schedule)
                    console.print("[green]Schedule updated successfully.[/green]")
            else:
                if click.confirm("Do you want to enable scheduling?"):
                    cron_schedule = click.prompt(
                        "Enter cron schedule (e.g. '0 4 * * *' for daily at 4 AM)",
                        default="0 4 * * *"
                    )
                    app_ctx.sync_manager.update_job(name, cron_schedule=cron_schedule)
                    console.print("[green]Scheduling enabled successfully.[/green]")
    
    except Exception as e:
        console.print(f"[bold red]Error updating job: {str(e)}[/bold red]")


def main():
    """Main entry point for the CLI"""
    try:
        cli()
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
