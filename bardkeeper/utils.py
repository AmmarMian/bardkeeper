"""
Utility functions for BardKeeper
"""

import os
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path

from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn


def create_progress_bar():
    """Create a rich progress bar"""
    return Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    )


def parse_rsync_progress(output_lines):
    """Parse rsync output to estimate progress"""
    # Look for progress indicators in the output
    progress_matches = []
    for line in output_lines:
        match = re.search(r'(\d+)%', line)
        if match:
            progress_matches.append(int(match.group(1)))
    
    # Return the last progress value or 0 if none found
    return progress_matches[-1] if progress_matches else 0


def human_readable_size(size_bytes):
    """Convert bytes to human-readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
    
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    
    return f"{s} {size_names[i]}"


def ensure_directory_exists(path):
    """Ensure a directory exists, creating it if necessary"""
    path = os.path.expanduser(path)
    os.makedirs(path, exist_ok=True)
    return path


def is_cron_installed():
    """Check if cron is installed on the system"""
    try:
        subprocess.run(
            ["which", "cron"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            check=False
        )
        return True
    except:
        return False


def is_rsync_installed():
    """Check if rsync is installed on the system"""
    try:
        result = subprocess.run(
            ["rsync", "--version"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            check=False
        )
        return result.returncode == 0
    except:
        return False


def get_install_command():
    """Get the appropriate command to install missing dependencies"""
    # Try to detect the package manager
    if os.path.exists("/usr/bin/apt"):
        return "sudo apt update && sudo apt install -y"
    elif os.path.exists("/usr/bin/dnf"):
        return "sudo dnf install -y"
    elif os.path.exists("/usr/bin/yum"):
        return "sudo yum install -y"
    elif os.path.exists("/usr/local/bin/brew"):
        return "brew install"
    else:
        return None
