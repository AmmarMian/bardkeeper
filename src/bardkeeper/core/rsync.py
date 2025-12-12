"""
Core rsync functionality for BardKeeper with improved error handling and retry logic.
"""

import logging
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Generator

from ..data.models import Job, SyncStatus
from ..exceptions import (
    RsyncError,
    SSHTimeoutError,
    SSHAuthenticationError,
    SyncError,
)
from .ssh import SSHConfig, test_ssh_connection
from .compression import CompressionManager
from ..cli.ui.progress import parse_rsync_progress, SyncProgress

logger = logging.getLogger(__name__)


def detect_rsync_type() -> str:
    """
    Detect the type of rsync installed (GNU rsync or openrsync/BSD).

    Returns:
        'openrsync' if BSD implementation is detected, 'gnu' otherwise
    """
    try:
        result = subprocess.run(
            ['rsync', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stdout + result.stderr

        if 'openrsync' in output.lower():
            logger.debug("Detected openrsync (BSD implementation)")
            return 'openrsync'
        else:
            logger.debug("Detected GNU rsync")
            return 'gnu'
    except Exception as e:
        logger.warning(f"Could not detect rsync type: {e}, assuming GNU rsync")
        return 'gnu'


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    bytes_transferred: int = 0
    duration: float = 0.0
    error_message: str = ""
    log_lines: list[str] = None

    def __post_init__(self):
        if self.log_lines is None:
            self.log_lines = []


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0

    def delays(self) -> Generator[float, None, None]:
        """Generate delay values for each retry attempt."""
        delay = self.initial_delay
        for _ in range(self.max_attempts - 1):  # -1 because first attempt has no delay
            yield delay
            delay = min(delay * self.exponential_base, self.max_delay)


class RsyncManager:
    """Manages rsync operations with retry logic and error handling."""

    def __init__(self, db, compression_manager: Optional[CompressionManager] = None):
        """Initialize the rsync manager."""
        self.db = db
        self.compression_manager = compression_manager or CompressionManager()
        self._wrapper_script_path: Optional[Path] = None
        self._rsync_type = detect_rsync_type()

    def _create_ssh_wrapper_script(self, ssh_config: SSHConfig) -> Path:
        """
        Create a temporary wrapper script for SSH command.

        This is necessary for openrsync (BSD) which doesn't properly parse
        complex SSH command strings passed via -e option.

        Args:
            ssh_config: SSH configuration

        Returns:
            Path to the created wrapper script
        """
        # Create wrapper script in a temporary location
        fd, script_path = tempfile.mkstemp(suffix='.sh', prefix='bardkeeper_ssh_')
        script_path = Path(script_path)

        try:
            # Build the SSH command
            ssh_parts = ssh_config.get_ssh_command()

            # Write the wrapper script
            with os.fdopen(fd, 'w') as f:
                f.write("#!/bin/sh\n")
                f.write("# Auto-generated SSH wrapper for BardKeeper\n")
                f.write("# This script will be automatically deleted after sync\n\n")

                # Build the exec line - all parts except 'ssh' itself, then add "$@" for additional args
                ssh_options = ' '.join(shlex.quote(arg) for arg in ssh_parts[1:])
                f.write(f'exec ssh {ssh_options} "$@"\n')

            # Make script executable
            script_path.chmod(0o700)

            logger.debug(f"Created SSH wrapper script at {script_path}")
            return script_path

        except Exception as e:
            # Clean up on error
            if script_path.exists():
                script_path.unlink()
            raise SyncError(f"Failed to create SSH wrapper script: {e}")

    def _cleanup_wrapper_script(self):
        """Clean up temporary wrapper script if it exists."""
        if self._wrapper_script_path and self._wrapper_script_path.exists():
            try:
                self._wrapper_script_path.unlink()
                logger.debug(f"Cleaned up wrapper script: {self._wrapper_script_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up wrapper script: {e}")
            finally:
                self._wrapper_script_path = None

    def build_rsync_command(self, job: Job) -> list[str]:
        """Build rsync command with proper progress flags and SSH options."""
        cmd = ["rsync"]

        # Basic flags
        cmd.extend(["-avh"])  # archive, verbose, human-readable

        # Progress tracking - use different flags based on rsync type
        if job.track_progress:
            if self._rsync_type == 'openrsync':
                # OpenRSync only supports basic --progress flag
                cmd.append("--progress")
            else:
                # GNU rsync supports more advanced progress reporting
                cmd.extend(["--info=progress2", "--no-inc-recursive"])

        # Compression for transfer
        cmd.append("-z")

        # Delete extraneous files on destination
        if job.delete_remote:
            cmd.append("--delete")

        # Itemize changes for logging
        cmd.append("--itemize-changes")

        # Bandwidth limit
        if job.bandwidth_limit:
            cmd.extend(["--bwlimit", str(job.bandwidth_limit)])

        # Exclude patterns
        for pattern in job.exclude_patterns:
            cmd.extend(["--exclude", pattern])

        # SSH command with all options
        ssh_config = SSHConfig(
            host=job.host,
            username=job.username,
            port=job.ssh_port,
            key_path=job.ssh_key_path,
            connect_timeout=job.ssh_timeout,
        )

        # Handle SSH command based on rsync type
        if self._rsync_type == 'openrsync':
            # OpenRSync (BSD) doesn't handle complex SSH strings well
            # Use a wrapper script instead
            self._wrapper_script_path = self._create_ssh_wrapper_script(ssh_config)
            cmd.extend(["-e", str(self._wrapper_script_path)])
            logger.debug(f"Using SSH wrapper script for openrsync: {self._wrapper_script_path}")
        else:
            # GNU rsync can handle the SSH command string directly
            ssh_cmd = ssh_config.get_ssh_command_string()
            cmd.extend(["-e", ssh_cmd])

        # Source (remote) - ensure trailing slash to copy contents
        remote = f"{job.username}@{job.host}:{job.remote_path}"
        if not remote.endswith('/'):
            remote += '/'
        cmd.append(remote)

        # Destination (local) - ensure parent directories exist
        local_dest = job.local_path
        local_dest.parent.mkdir(parents=True, exist_ok=True)

        # Ensure the destination directory exists
        if not str(local_dest).endswith('/'):
            local_dest = Path(str(local_dest) + '/')
        cmd.append(str(local_dest))

        return cmd

    def execute_sync(
        self,
        job: Job,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None
    ) -> SyncResult:
        """
        Execute a single sync operation.

        Args:
            job: Job to sync
            progress_callback: Optional callback for progress updates

        Returns:
            SyncResult with sync status

        Raises:
            SSHAuthenticationError: If SSH authentication fails
            SSHTimeoutError: If SSH connection times out
            RsyncError: If rsync fails
        """
        start_time = time.time()

        # Test SSH connection first
        ssh_config = SSHConfig(
            host=job.host,
            username=job.username,
            port=job.ssh_port,
            key_path=job.ssh_key_path,
            connect_timeout=job.ssh_timeout,
        )

        try:
            success, message = test_ssh_connection(ssh_config)
            if not success:
                raise SyncError(f"SSH connection test failed: {message}")
        except (SSHAuthenticationError, SSHTimeoutError):
            # Re-raise these specific errors
            raise

        # Build rsync command
        cmd = self.build_rsync_command(job)

        # Prepare log file
        log_file = None
        if job.track_progress:
            log_dir = Path("~/.bardkeeper/logs").expanduser()
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{job.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        try:
            # Run rsync command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Process output
            log_lines = []
            bytes_transferred = 0

            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                # Store log line
                log_lines.append(line)

                # Write to log file
                if log_file:
                    with open(log_file, 'a') as f:
                        f.write(line)

                # Extract and report progress
                if progress_callback:
                    sync_progress = parse_rsync_progress(line)
                    if sync_progress:
                        progress_callback(sync_progress)
                        if sync_progress.bytes_transferred > bytes_transferred:
                            bytes_transferred = sync_progress.bytes_transferred

            # Wait for process to complete
            returncode = process.wait()
            duration = time.time() - start_time

            # Check rsync exit code
            if returncode == 0:
                return SyncResult(
                    success=True,
                    bytes_transferred=bytes_transferred,
                    duration=duration,
                    log_lines=log_lines,
                )
            else:
                # Rsync failed - get error message from logs
                error_output = '\n'.join(log_lines[-10:])  # Last 10 lines
                raise RsyncError(returncode, stderr=error_output)

        except subprocess.TimeoutExpired:
            process.kill()
            raise SSHTimeoutError(f"Rsync operation timed out")
        except Exception as e:
            if not isinstance(e, (RsyncError, SSHTimeoutError, SSHAuthenticationError)):
                raise SyncError(f"Sync failed: {e}")
            raise
        finally:
            # Always clean up wrapper script if it was created
            self._cleanup_wrapper_script()

    def sync_with_retry(
        self,
        job: Job,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> SyncResult:
        """
        Execute sync with automatic retry for recoverable errors.

        Retries on:
        - SSH timeout errors
        - Partial transfer errors (rsync exit codes 23, 24, 30)

        Does NOT retry on:
        - Authentication failures
        - Invalid paths
        - Permission errors

        Args:
            job: Job to sync
            progress_callback: Optional callback for progress updates
            retry_config: Optional retry configuration

        Returns:
            SyncResult

        Raises:
            Various sync-related exceptions if all retries fail
        """
        retry_config = retry_config or RetryConfig()
        last_error: Optional[Exception] = None
        attempt = 0

        for attempt in range(1, retry_config.max_attempts + 1):
            try:
                return self.execute_sync(job, progress_callback)

            except SSHTimeoutError as e:
                last_error = e
                if attempt < retry_config.max_attempts:
                    delay = next(retry_config.delays())
                    logger.warning(
                        f"Attempt {attempt} timed out for job '{job.name}', "
                        f"retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    raise

            except RsyncError as e:
                last_error = e
                if e.recoverable and attempt < retry_config.max_attempts:
                    delay = next(retry_config.delays())
                    logger.warning(
                        f"Attempt {attempt} failed for job '{job.name}' ({e.message}), "
                        f"retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    raise

            except SSHAuthenticationError:
                # Never retry auth errors
                raise

        # Should not reach here, but safety net
        if last_error:
            raise last_error
        raise SyncError("Sync failed after all retry attempts")

    def sync(
        self,
        job_name: str,
        progress_callback: Optional[Callable[[SyncProgress], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        use_retry: bool = True,
    ) -> SyncResult:
        """
        Sync a specific job by name.

        Args:
            job_name: Name of job to sync
            progress_callback: Optional callback for progress updates
            use_retry: Whether to use retry logic (default: True)

        Returns:
            SyncResult

        Raises:
            JobNotFoundError: If job doesn't exist
            Various sync-related exceptions on failure
        """
        job = self.db.get_sync_job(job_name)
        if not job:
            from ..exceptions import JobNotFoundError
            raise JobNotFoundError(f"No sync job found with name '{job_name}'")

        # Update job status to running
        self.db.update_sync_status(job_name, SyncStatus.RUNNING)

        try:
            # Execute sync (with or without retry)
            if use_retry:
                result = self.sync_with_retry(job, progress_callback)
            else:
                result = self.execute_sync(job, progress_callback)

            # Update database with success
            self.db.update_last_synced(
                job_name,
                duration=result.duration,
                bytes_transferred=result.bytes_transferred,
            )

            # Handle compression if needed
            if job.use_compression and result.success:
                try:
                    if status_callback:
                        status_callback("Compressing synced files...")
                    self.compression_manager.compress_and_cleanup(job.local_path)
                    if status_callback:
                        status_callback("Compression complete")
                except Exception as e:
                    logger.error(f"Compression failed for job '{job_name}': {e}")
                    if status_callback:
                        status_callback(f"Compression failed: {e}")
                    # Don't fail the whole sync if compression fails
                    # The data is already synced successfully

            return result

        except Exception as e:
            # Update database with failure
            error_msg = str(e)
            self.db.update_sync_status(job_name, SyncStatus.FAILED, error=error_msg)
            raise

    def get_directory_tree(self, job_name: str, max_depth: int = 2) -> list[str]:
        """Generate a directory tree for a sync job."""
        job = self.db.get_sync_job(job_name)
        if not job:
            from ..exceptions import JobNotFoundError
            raise JobNotFoundError(f"No sync job found with name '{job_name}'")

        # Determine the correct path to check
        if job.use_compression:
            # For compressed archives
            archive_path = self.compression_manager.get_archive_path(job.local_path)

            if archive_path.exists():
                # Extract to temp directory for tree generation
                with tempfile.TemporaryDirectory() as tmp_dir:
                    try:
                        self.compression_manager.extract_archive(
                            archive_path,
                            Path(tmp_dir)
                        )
                        return self._get_tree(Path(tmp_dir), max_depth)
                    except Exception as e:
                        return [f"[Error extracting archive: {e}]"]
            else:
                return ["[Compressed archive not found]"]
        else:
            # For regular directories
            if job.local_path.exists():
                return self._get_tree(job.local_path, max_depth)
            else:
                return ["[Directory not found]"]

    def _get_tree(self, path: Path, max_depth: int, current_depth: int = 0, prefix: str = "") -> list[str]:
        """Recursive helper for directory tree generation."""
        if current_depth > max_depth:
            return ["..."]

        result = []

        try:
            # Get sorted list of items
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                item_prefix = "└── " if is_last else "├── "

                # Add item to result
                result.append(f"{prefix}{item_prefix}{item.name}{'/' if item.is_dir() else ''}")

                # Add sub-items if directory and not at max depth
                if item.is_dir() and current_depth < max_depth:
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    result.extend(self._get_tree(item, max_depth, current_depth + 1, child_prefix))

        except PermissionError:
            result.append(f"{prefix}[Permission denied]")
        except Exception as e:
            result.append(f"{prefix}[Error: {str(e)}]")

        return result
