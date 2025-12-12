"""
Compression and extraction utilities for BardKeeper.
"""

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..exceptions import CompressionError


class CompressionManager:
    """Handles compression and extraction of sync directories."""

    def __init__(
        self,
        compression_command: str = "tar -czf",
        extraction_command: str = "tar -xzf"
    ):
        self.compression_command = compression_command
        self.extraction_command = extraction_command

    def compress_directory(self, source_dir: Path, archive_path: Optional[Path] = None) -> Path:
        """
        Compress a directory into a tar.gz archive.

        Args:
            source_dir: Directory to compress
            archive_path: Optional output archive path. If not provided,
                         creates archive in parent directory with .tar.gz extension

        Returns:
            Path to the created archive

        Raises:
            CompressionError: If compression fails
        """
        source_dir = Path(source_dir).resolve()

        if not source_dir.exists():
            raise CompressionError(f"Directory to compress not found: {source_dir}")

        # Determine archive path
        if archive_path is None:
            archive_name = source_dir.name
            archive_path = source_dir.parent / f"{archive_name}.tar.gz"
        else:
            archive_path = Path(archive_path)

        # Ensure archive has .tar.gz extension
        if not str(archive_path).endswith('.tar.gz'):
            archive_path = Path(str(archive_path) + '.tar.gz')

        # Build compression command
        # cd to parent directory for proper relative paths in archive
        parent_dir = source_dir.parent
        dir_to_compress = source_dir.name

        cmd = [
            "tar", "-czf",
            str(archive_path),
            "-C", str(parent_dir),
            dir_to_compress
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode != 0:
                raise CompressionError(
                    f"Compression failed",
                    details=result.stderr
                )

            return archive_path

        except subprocess.TimeoutExpired:
            raise CompressionError("Compression timed out after 1 hour")
        except Exception as e:
            raise CompressionError(f"Compression failed: {e}")

    def extract_archive(
        self,
        archive_path: Path,
        extract_dir: Optional[Path] = None
    ) -> Path:
        """
        Extract a tar.gz archive.

        Args:
            archive_path: Path to archive file
            extract_dir: Optional directory to extract to.
                        If not provided, extracts to archive's parent directory

        Returns:
            Path to the extraction directory

        Raises:
            CompressionError: If extraction fails
        """
        archive_path = Path(archive_path)

        if not archive_path.exists():
            raise CompressionError(f"Archive file not found: {archive_path}")

        # Determine extraction directory
        if extract_dir is None:
            extract_dir = archive_path.parent
        else:
            extract_dir = Path(extract_dir)

        # Create extract directory if it doesn't exist
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Build extraction command
        cmd = [
            "tar", "-xzf",
            str(archive_path),
            "-C", str(extract_dir)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode != 0:
                raise CompressionError(
                    f"Extraction failed",
                    details=result.stderr
                )

            return extract_dir

        except subprocess.TimeoutExpired:
            raise CompressionError("Extraction timed out after 1 hour")
        except Exception as e:
            raise CompressionError(f"Extraction failed: {e}")

    def compress_and_cleanup(self, source_dir: Path) -> Path:
        """
        Compress directory and remove original on success.

        This is an atomic operation - the original directory is only
        removed if compression succeeds.

        Args:
            source_dir: Directory to compress and remove

        Returns:
            Path to created archive

        Raises:
            CompressionError: If compression fails
        """
        archive_path = self.compress_directory(source_dir)

        # Only remove source if compression succeeded and archive exists
        if archive_path.exists():
            try:
                shutil.rmtree(source_dir)
            except Exception as e:
                # Archive was created successfully, but cleanup failed
                # This is not critical - log but don't raise
                print(f"Warning: Failed to remove source directory after compression: {e}")

        return archive_path

    def get_archive_path(self, local_path: Path) -> Path:
        """
        Calculate the expected archive path for a local directory.

        Args:
            local_path: Local directory path

        Returns:
            Expected archive file path
        """
        local_path = Path(local_path)
        archive_name = local_path.name
        return local_path.parent / f"{archive_name}.tar.gz"
