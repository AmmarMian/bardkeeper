"""
Menus and prompts for BardKeeper UI.
"""

from pathlib import Path
from typing import Optional

from simple_term_menu import TerminalMenu
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.console import Console

from ...data.models import SyncDirection

console = Console()


def select_from_menu(title: str, options: list[str]) -> Optional[str]:
    """
    Display a terminal menu and return selected option.

    Args:
        title: Menu title
        options: List of menu options

    Returns:
        Selected option or None if cancelled
    """
    terminal_menu = TerminalMenu(
        options,
        title=title,
        menu_cursor="➤ ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("bg_cyan", "fg_black"),
    )

    # Show menu and get selection
    menu_index = terminal_menu.show()

    # Return selected option or None if cancelled
    return options[menu_index] if menu_index is not None else None


def prompt_for_job_details(existing_job: Optional[dict] = None) -> dict:
    """
    Interactive prompt for job details.

    Args:
        existing_job: Optional existing job dict for editing

    Returns:
        Dictionary of job details
    """
    details = {}
    existing_job = existing_job or {}

    # If editing existing job, name cannot be changed
    if existing_job.get('name'):
        details['name'] = existing_job['name']
    else:
        details['name'] = Prompt.ask(
            "Enter job name",
            default=existing_job.get('name', "")
        )

    # Prompt for remote details
    details['host'] = Prompt.ask(
        "Enter remote server address",
        default=existing_job.get('host', "")
    )

    details['username'] = Prompt.ask(
        "Enter username",
        default=existing_job.get('username', "")
    )

    details['remote_path'] = Prompt.ask(
        "Enter remote path",
        default=existing_job.get('remote_path', "")
    )

    # SSH settings
    details['ssh_port'] = IntPrompt.ask(
        "Enter SSH port",
        default=existing_job.get('ssh_port', 22)
    )

    use_ssh_key = Confirm.ask(
        "Use custom SSH key?",
        default=bool(existing_job.get('ssh_key_path'))
    )

    if use_ssh_key:
        details['ssh_key_path'] = Prompt.ask(
            "Enter SSH key path",
            default=str(existing_job.get('ssh_key_path', "~/.ssh/id_rsa"))
        )
    else:
        details['ssh_key_path'] = None

    # Prompt for local details
    details['local_path'] = Prompt.ask(
        "Enter local path",
        default=str(existing_job.get('local_path', ""))
    )

    # Basic options
    details['use_compression'] = Confirm.ask(
        "Enable compression after sync?",
        default=existing_job.get('use_compression', False)
    )

    details['track_progress'] = Confirm.ask(
        "Track sync progress?",
        default=existing_job.get('track_progress', True)
    )

    details['delete_remote'] = Confirm.ask(
        "Delete files not present on remote?",
        default=existing_job.get('delete_remote', True)
    )

    # Sync direction
    direction_options = {
        "Pull (Remote → Local) - Safe for backups": SyncDirection.PULL,
        "Push (Local → Remote) - Overwrites remote": SyncDirection.PUSH,
        "Bidirectional - Sync both ways (advanced)": SyncDirection.BIDIRECTIONAL
    }

    # For existing jobs, show current direction or default to PULL
    current_direction = existing_job.get('sync_direction', 'pull')
    if isinstance(current_direction, str):
        # Convert string to enum for comparison
        try:
            current_direction_enum = SyncDirection(current_direction)
        except ValueError:
            current_direction_enum = SyncDirection.PULL
    else:
        current_direction_enum = current_direction

    # Find matching description for current direction
    default_option = "Pull (Remote → Local) - Safe for backups"
    for desc, direction in direction_options.items():
        if direction == current_direction_enum:
            default_option = desc
            break

    # Present menu options
    menu_options = list(direction_options.keys())
    if existing_job:
        menu_options.append("Keep current")

    console.print("\n[bold]Sync Direction:[/bold]")
    selected_direction = select_from_menu(
        "Select default sync direction:",
        menu_options
    )

    if selected_direction and selected_direction != "Keep current":
        details['sync_direction'] = direction_options[selected_direction]

        # Show warning for bidirectional
        if details['sync_direction'] == SyncDirection.BIDIRECTIONAL:
            console.print("\n[bold yellow]⚠️  Bidirectional Sync Limitations:[/bold yellow]")
            console.print("  • Uses modification times (last-write-wins)")
            console.print("  • No conflict resolution for simultaneous changes")
            console.print("  • --delete flag disabled to prevent data loss")
            console.print("  • Consider pull or push for critical data\n")
    elif existing_job and selected_direction == "Keep current":
        # Keep existing direction
        pass
    else:
        # Default to PULL if no selection
        details['sync_direction'] = SyncDirection.PULL

    # Advanced options
    use_bandwidth_limit = Confirm.ask(
        "Set bandwidth limit?",
        default=bool(existing_job.get('bandwidth_limit'))
    )

    if use_bandwidth_limit:
        details['bandwidth_limit'] = IntPrompt.ask(
            "Enter bandwidth limit (KB/s)",
            default=existing_job.get('bandwidth_limit', 1000)
        )
    else:
        details['bandwidth_limit'] = None

    # Exclude patterns
    use_exclude = Confirm.ask(
        "Add exclude patterns?",
        default=bool(existing_job.get('exclude_patterns'))
    )

    if use_exclude:
        patterns_str = Prompt.ask(
            "Enter exclude patterns (comma-separated)",
            default=",".join(existing_job.get('exclude_patterns', []))
        )
        details['exclude_patterns'] = [
            p.strip() for p in patterns_str.split(',') if p.strip()
        ]
    else:
        details['exclude_patterns'] = []

    # Cron schedule
    use_cron = Confirm.ask(
        "Set up automatic sync schedule?",
        default=bool(existing_job.get('cron_schedule'))
    )

    if use_cron:
        details['cron_schedule'] = Prompt.ask(
            "Enter cron schedule (e.g. '0 4 * * *' for daily at 4 AM)",
            default=existing_job.get('cron_schedule', "0 4 * * *")
        )
    else:
        details['cron_schedule'] = None

    return details


def prompt_for_config_changes(current_config: dict) -> dict:
    """
    Interactive prompt for configuration changes.

    Args:
        current_config: Current configuration

    Returns:
        Dictionary of configuration changes
    """
    changes = {}

    # Which setting to change
    options = [
        "Database Path",
        "Compression Command",
        "Extraction Command",
        "Cache Settings",
        "Back to Main Menu"
    ]

    selection = select_from_menu("Select setting to change:", options)

    if selection == "Database Path":
        changes['db_path'] = Prompt.ask(
            "Enter database path",
            default=current_config.get('db_path', "~/.bardkeeper/database.json")
        )

    elif selection == "Compression Command":
        changes['compression_command'] = Prompt.ask(
            "Enter compression command",
            default=current_config.get('compression_command', "tar -czf")
        )

    elif selection == "Extraction Command":
        changes['extraction_command'] = Prompt.ask(
            "Enter extraction command",
            default=current_config.get('extraction_command', "tar -xzf")
        )

    elif selection == "Cache Settings":
        changes['cache_enabled'] = Confirm.ask(
            "Enable cache?",
            default=current_config.get('cache_enabled', False)
        )

        if changes['cache_enabled']:
            changes['cache_dir'] = Prompt.ask(
                "Enter cache directory",
                default=current_config.get('cache_dir', "~/.bardkeeper/cache")
            )

    return changes
