"""
Menus and prompts for BardKeeper UI
"""

import os
from simple_term_menu import TerminalMenu
from rich.prompt import Prompt, Confirm


def select_from_menu(title, options):
    """Display a terminal menu and return selected option"""
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


def prompt_for_job_details(existing_job=None):
    """Interactive prompt for job details"""
    details = {}
    existing_job = existing_job or {}
    
    # If editing existing job, name cannot be changed
    if 'name' in existing_job:
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
    
    # Prompt for local details
    details['local_path'] = Prompt.ask(
        "Enter local path",
        default=existing_job.get('local_path', "")
    )
    
    # Options
    details['use_compression'] = Confirm.ask(
        "Enable compression?",
        default=existing_job.get('use_compression', False)
    )
    
    details['track_progress'] = Confirm.ask(
        "Track sync progress?",
        default=existing_job.get('track_progress', False)
    )
    
    # Cron schedule
    use_cron = Confirm.ask(
        "Set up automatic sync schedule?",
        default=bool(existing_job.get('cron_schedule', False))
    )
    
    if use_cron:
        details['cron_schedule'] = Prompt.ask(
            "Enter cron schedule (e.g. '0 4 * * *' for daily at 4 AM)",
            default=existing_job.get('cron_schedule', "0 4 * * *")
        )
    else:
        details['cron_schedule'] = None
    
    return details


def prompt_for_config_changes(current_config):
    """Interactive prompt for configuration changes"""
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
