"""
Custom Exception Hierarchy for BardKeeper

Provides specific exceptions for different failure modes,
enabling appropriate error messages and recovery strategies.
"""


class BardKeeperError(Exception):
    """Base exception for all BardKeeper errors."""

    def __init__(self, message: str, details: str = "", recoverable: bool = False):
        self.message = message
        self.details = details
        self.recoverable = recoverable
        super().__init__(message)

    def user_message(self) -> str:
        """Format error for display to user."""
        if self.details:
            return f"{self.message}\n  Details: {self.details}"
        return self.message


# SSH/Connection Errors
class ConnectionError(BardKeeperError):
    """Base class for connection-related errors."""
    pass


class SSHConnectionError(ConnectionError):
    """SSH connection failed."""
    pass


class SSHAuthenticationError(SSHConnectionError):
    """SSH authentication failed (wrong key, no access)."""
    pass


class SSHTimeoutError(SSHConnectionError):
    """SSH connection timed out."""
    pass


class HostUnreachableError(ConnectionError):
    """Remote host cannot be reached."""
    pass


# Sync Errors
class SyncError(BardKeeperError):
    """Base class for sync operation errors."""
    pass


class RsyncError(SyncError):
    """Rsync command failed."""

    # Map rsync exit codes to human-readable messages
    EXIT_CODES = {
        1: "Syntax or usage error",
        2: "Protocol incompatibility",
        3: "Errors selecting input/output files, dirs",
        4: "Requested action not supported",
        5: "Error starting client-server protocol",
        6: "Daemon unable to append to log-file",
        10: "Error in socket I/O",
        11: "Error in file I/O",
        12: "Error in rsync protocol data stream",
        13: "Errors with program diagnostics",
        14: "Error in IPC code",
        20: "Received SIGUSR1 or SIGINT",
        21: "Some error returned by waitpid()",
        22: "Error allocating core memory buffers",
        23: "Partial transfer due to error",
        24: "Partial transfer due to vanished source files",
        25: "The --max-delete limit stopped deletions",
        30: "Timeout in data send/receive",
        35: "Timeout waiting for daemon connection",
    }

    def __init__(self, exit_code: int, stderr: str = ""):
        message = self.EXIT_CODES.get(exit_code, f"Unknown error (code {exit_code})")
        super().__init__(
            message=f"Rsync failed: {message}",
            details=stderr,
            recoverable=exit_code in (23, 24, 30)
        )
        self.exit_code = exit_code


class PartialSyncError(SyncError):
    """Sync partially completed but some files failed."""
    pass


class SyncAlreadyRunningError(SyncError):
    """Job is already being synced by another process."""
    pass


# Compression Errors
class CompressionError(BardKeeperError):
    """Compression/extraction operation failed."""
    pass


# Database Errors
class DatabaseError(BardKeeperError):
    """Database operation failed."""
    pass


class JobNotFoundError(DatabaseError):
    """Requested job does not exist."""
    pass


class JobExistsError(DatabaseError):
    """Job with this name already exists."""
    pass


# Configuration Errors
class ConfigurationError(BardKeeperError):
    """Configuration is invalid."""
    pass


class InvalidPathError(ConfigurationError):
    """Path does not exist or is not accessible."""
    pass
