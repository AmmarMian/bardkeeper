"""
SSH Connection Management for BardKeeper

Features:
1. SSH key specification support
2. Connection testing before sync
3. Configurable timeouts
4. Clear error messages for auth failures
5. SSH multiplexing for performance
"""

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..exceptions import SSHConnectionError, SSHAuthenticationError, SSHTimeoutError


@dataclass
class SSHConfig:
    """SSH connection configuration for a job."""
    host: str
    username: str
    port: int = 22
    key_path: Optional[Path] = None
    connect_timeout: int = 30
    use_multiplexing: bool = True

    def get_ssh_command(self) -> list[str]:
        """Build SSH command arguments for rsync -e option."""
        parts = ["ssh"]

        # Port
        if self.port != 22:
            parts.extend(["-p", str(self.port)])

        # Key file
        if self.key_path:
            parts.extend(["-i", str(self.key_path)])

        # Timeouts
        parts.extend([
            "-o", f"ConnectTimeout={self.connect_timeout}",
            "-o", "ServerAliveInterval=10",
            "-o", "ServerAliveCountMax=3",
            "-o", "BatchMode=yes",  # Fail instead of prompting for password
        ])

        # Multiplexing for faster subsequent connections
        if self.use_multiplexing:
            socket_path = f"~/.ssh/bardkeeper-{self.host}-%r@%h:%p"
            parts.extend([
                "-o", f"ControlPath={socket_path}",
                "-o", "ControlMaster=auto",
                "-o", "ControlPersist=600",
            ])

        # Disable strict host key checking warning (but still verify)
        parts.extend(["-o", "StrictHostKeyChecking=accept-new"])

        return parts

    def get_ssh_command_string(self) -> str:
        """Get SSH command as a properly quoted string."""
        return " ".join(shlex.quote(arg) for arg in self.get_ssh_command())


def test_ssh_connection(config: SSHConfig) -> tuple[bool, str]:
    """
    Test SSH connectivity before starting sync.

    Returns:
        (success: bool, message: str)

    Raises:
        SSHAuthenticationError: If authentication fails
        SSHConnectionError: If connection fails for other reasons
        SSHTimeoutError: If connection times out
    """
    ssh_cmd = config.get_ssh_command()
    test_cmd = ssh_cmd + [
        f"{config.username}@{config.host}",
        "echo", "bardkeeper-connection-test"
    ]

    try:
        result = subprocess.run(
            test_cmd,
            capture_output=True,
            text=True,
            timeout=config.connect_timeout + 5
        )

        if result.returncode == 0 and "bardkeeper-connection-test" in result.stdout:
            return True, "Connection successful"

        # Parse common SSH errors
        stderr = result.stderr.lower()
        if "permission denied" in stderr:
            raise SSHAuthenticationError(
                f"Authentication failed for {config.username}@{config.host}. "
                f"Check your SSH key or credentials."
            )
        elif "host key verification failed" in stderr:
            raise SSHConnectionError(
                f"Host key verification failed for {config.host}. "
                f"Run: ssh-keyscan {config.host} >> ~/.ssh/known_hosts"
            )
        elif "connection refused" in stderr:
            raise SSHConnectionError(
                f"Connection refused by {config.host}:{config.port}. "
                f"Check if SSH server is running."
            )
        elif "no route to host" in stderr or "network is unreachable" in stderr:
            raise SSHConnectionError(
                f"Cannot reach {config.host}. Check network connectivity."
            )
        else:
            raise SSHConnectionError(f"SSH connection failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        raise SSHTimeoutError(
            f"Connection to {config.host} timed out after {config.connect_timeout}s"
        )
