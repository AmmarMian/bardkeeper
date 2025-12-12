"""
Test suite for rsync module
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.bardkeeper.data.database import BardkeeperDB
from src.bardkeeper.core.rsync import RsyncManager
from src.bardkeeper.data.models import Job
from src.bardkeeper.cli.ui.progress import SyncProgress


class TestRsyncManager(unittest.TestCase):
    """Test cases for RsyncManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Use a temporary file for the database
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_db.json"
        self.db = BardkeeperDB(self.db_path)
        self.rsync_manager = RsyncManager(self.db)

        # Create a mock job
        self.job_name = "test_job"
        self.db.add_sync_job(
            name=self.job_name,
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path=Path(self.temp_dir.name) / "local_path",
            use_compression=False,
            cron_schedule=None,
            track_progress=True
        )
    
    def tearDown(self):
        """Tear down test fixtures"""
        self.temp_dir.cleanup()
    
    def test_build_rsync_command(self):
        """Test building rsync command"""
        job = self.db.get_sync_job(self.job_name)

        # Get rsync command
        cmd = self.rsync_manager.build_rsync_command(job)

        # Check command structure
        self.assertEqual(cmd[0], "rsync")
        self.assertIn("-avh", cmd)  # Archive, verbose, human-readable
        self.assertIn("-z", cmd)  # Compression
        # Progress tracking - depends on rsync type
        if self.rsync_manager._rsync_type == 'openrsync':
            self.assertIn("--progress", cmd)
        else:
            self.assertIn("--info=progress2", cmd)
        self.assertIn("--delete", cmd)
        self.assertIn("--itemize-changes", cmd)

        # Check source and destination (source has trailing slash in new API)
        source = "test_user@test_host:/remote/path/"
        # Check that source and local_path are in the command
        self.assertTrue(any(source in arg for arg in cmd))
        self.assertTrue(any(str(job.local_path) in arg for arg in cmd))
    
    def test_parse_progress(self):
        """Test parsing progress from rsync output"""
        from src.bardkeeper.cli.ui.progress import parse_rsync_progress

        # Test with progress2 format line
        line = "    1,238,459  99%   14.98MB/s    0:01:23"
        progress = parse_rsync_progress(line)
        self.assertIsNotNone(progress)
        self.assertEqual(progress.percent, 99)
        self.assertEqual(progress.bytes_transferred, 1238459)

        # Test with non-progress line
        line = "sending incremental file list"
        progress = parse_rsync_progress(line)
        self.assertIsNone(progress)
    
    @patch('subprocess.Popen')
    @patch('subprocess.run')
    def test_sync_success(self, mock_run, mock_popen):
        """Test successful sync operation"""
        # Mock SSH connection test (subprocess.run)
        mock_ssh_result = Mock()
        mock_ssh_result.returncode = 0
        mock_ssh_result.stdout = "bardkeeper-connection-test"
        mock_ssh_result.stderr = ""
        mock_run.return_value = mock_ssh_result

        # Mock subprocess.Popen for rsync with readline() support
        lines = ["sending incremental file list\n", "file1\n", "file2\n", "    1,238,459  99%   14.98MB/s    0:01:23\n", ""]
        mock_stdout = Mock()
        mock_stdout.readline = Mock(side_effect=lines)

        mock_process = Mock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 0  # Success
        mock_popen.return_value = mock_process

        # Mock progress callback
        mock_callback = Mock()

        # Call sync
        result = self.rsync_manager.sync(self.job_name, mock_callback)

        # Check result
        self.assertTrue(result.success)
        self.assertGreater(len(result.log_lines), 0)

        # Check callback was called with SyncProgress object
        # mock_callback.assert_called() - callback receives SyncProgress objects

        # Check job status was updated
        job = self.db.get_sync_job(self.job_name)
        self.assertIsNotNone(job.last_synced)
    
    @patch('subprocess.Popen')
    @patch('subprocess.run')
    def test_sync_failure(self, mock_run, mock_popen):
        """Test failed sync operation"""
        # Mock SSH connection test to succeed (subprocess.run)
        mock_ssh_result = Mock()
        mock_ssh_result.returncode = 0
        mock_ssh_result.stdout = "bardkeeper-connection-test"
        mock_ssh_result.stderr = ""
        mock_run.return_value = mock_ssh_result

        # Mock subprocess.Popen for rsync with readline() support
        lines = ["sending incremental file list\n", "rsync: connection failed: Connection refused (111)\n", ""]
        mock_stdout = Mock()
        mock_stdout.readline = Mock(side_effect=lines)

        mock_process = Mock()
        mock_process.stdout = mock_stdout
        mock_process.wait.return_value = 1  # Failure
        mock_popen.return_value = mock_process

        # Call sync - should raise RsyncError
        from src.bardkeeper.exceptions import RsyncError
        with self.assertRaises(RsyncError):
            self.rsync_manager.sync(self.job_name)

        # Check job status was updated to failed
        job = self.db.get_sync_job(self.job_name)
        from src.bardkeeper.data.models import SyncStatus
        self.assertEqual(job.sync_status, SyncStatus.FAILED)
    
    @patch('subprocess.run')
    def test_compress_directory(self, mock_run):
        """Test directory compression via CompressionManager"""
        from src.bardkeeper.core.compression import CompressionManager

        # Set up mock
        mock_run.return_value.returncode = 0

        # Get job and set up directory
        job = self.db.get_sync_job(self.job_name)
        job.local_path.mkdir(parents=True, exist_ok=True)

        # Call compress using CompressionManager
        compression_mgr = CompressionManager()
        archive_path = compression_mgr.compress_directory(job.local_path)

        # Check subprocess.run was called
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        # Check that tar command was used
        self.assertTrue(any("tar" in str(arg) for arg in args))

    @patch('subprocess.run')
    def test_extract_archive(self, mock_run):
        """Test archive extraction via CompressionManager"""
        from src.bardkeeper.core.compression import CompressionManager

        # Set up mock
        mock_run.return_value.returncode = 0

        # Get job
        job = self.db.get_sync_job(self.job_name)

        # Create dummy archive file
        archive_path = job.local_path.parent / f"{job.local_path.name}.tar.gz"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text("dummy archive")

        # Call extract using CompressionManager
        compression_mgr = CompressionManager()
        extract_dest = job.local_path.parent / "extracted"
        compression_mgr.extract_archive(archive_path, extract_dest)

        # Check subprocess.run was called
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        # Check that tar command was used
        self.assertTrue(any("tar" in str(arg) for arg in args))
    
    def test_get_directory_tree(self):
        """Test directory tree generation"""
        # Set up directory structure
        job = self.db.get_sync_job(self.job_name)
        job.local_path.mkdir(parents=True, exist_ok=True)
        (job.local_path / "dir1").mkdir(exist_ok=True)
        (job.local_path / "dir2").mkdir(exist_ok=True)
        (job.local_path / "file1.txt").write_text("test")

        # Get tree with depth 1
        tree = self.rsync_manager.get_directory_tree(self.job_name, max_depth=1)

        # Check tree structure
        self.assertTrue(any("dir1" in line for line in tree))
        self.assertTrue(any("dir2" in line for line in tree))
        self.assertTrue(any("file1.txt" in line for line in tree))


class TestOpenRsyncWrapper(unittest.TestCase):
    """Test cases for openrsync wrapper script functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_db.json"
        self.db = BardkeeperDB(self.db_path)

        # Create a mock job
        self.job_name = "test_job"
        self.db.add_sync_job(
            name=self.job_name,
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path=Path(self.temp_dir.name) / "local_path",
            use_compression=False,
            cron_schedule=None,
            track_progress=True
        )

    def tearDown(self):
        """Tear down test fixtures"""
        self.temp_dir.cleanup()

    def test_detect_rsync_type_openrsync(self):
        """Test detection of openrsync"""
        from src.bardkeeper.core.rsync import detect_rsync_type

        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.stdout = "openrsync: protocol version 29"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            rsync_type = detect_rsync_type()
            self.assertEqual(rsync_type, 'openrsync')

    def test_detect_rsync_type_gnu(self):
        """Test detection of GNU rsync"""
        from src.bardkeeper.core.rsync import detect_rsync_type

        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.stdout = "rsync  version 3.2.3  protocol version 31"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            rsync_type = detect_rsync_type()
            self.assertEqual(rsync_type, 'gnu')

    def test_wrapper_script_creation(self):
        """Test SSH wrapper script creation"""
        from src.bardkeeper.core.ssh import SSHConfig

        rsync_manager = RsyncManager(self.db)
        ssh_config = SSHConfig(
            host="test_host",
            username="test_user",
            port=22,
            key_path=None,
            connect_timeout=30
        )

        # Create wrapper script
        wrapper_path = rsync_manager._create_ssh_wrapper_script(ssh_config)

        try:
            # Check script exists
            self.assertTrue(wrapper_path.exists())

            # Check script is executable
            self.assertTrue(os.access(wrapper_path, os.X_OK))

            # Check script content
            content = wrapper_path.read_text()
            self.assertIn("#!/bin/sh", content)
            self.assertIn("exec ssh", content)
            self.assertIn("ConnectTimeout=30", content)

        finally:
            # Clean up
            if wrapper_path.exists():
                wrapper_path.unlink()

    def test_wrapper_script_cleanup(self):
        """Test that wrapper scripts are cleaned up"""
        from src.bardkeeper.core.ssh import SSHConfig

        rsync_manager = RsyncManager(self.db)
        ssh_config = SSHConfig(
            host="test_host",
            username="test_user",
            port=22,
            key_path=None,
            connect_timeout=30
        )

        # Create wrapper script
        wrapper_path = rsync_manager._create_ssh_wrapper_script(ssh_config)
        rsync_manager._wrapper_script_path = wrapper_path

        # Verify it exists
        self.assertTrue(wrapper_path.exists())

        # Clean up
        rsync_manager._cleanup_wrapper_script()

        # Verify it's deleted
        self.assertFalse(wrapper_path.exists())
        self.assertIsNone(rsync_manager._wrapper_script_path)

    def test_build_command_with_openrsync(self):
        """Test that wrapper script is used with openrsync"""
        # Force openrsync type
        rsync_manager = RsyncManager(self.db)
        rsync_manager._rsync_type = 'openrsync'

        job = self.db.get_sync_job(self.job_name)
        cmd = rsync_manager.build_rsync_command(job)

        # Check that -e option points to a script file
        e_index = cmd.index('-e')
        ssh_cmd = cmd[e_index + 1]

        # Should be a path to wrapper script, not a command string
        self.assertTrue(ssh_cmd.startswith('/'))
        self.assertTrue('ssh' not in ssh_cmd or ssh_cmd.endswith('.sh'))

        # Clean up the created wrapper script
        if rsync_manager._wrapper_script_path:
            rsync_manager._cleanup_wrapper_script()

    def test_build_command_with_gnu_rsync(self):
        """Test that command string is used with GNU rsync"""
        # Force GNU rsync type
        rsync_manager = RsyncManager(self.db)
        rsync_manager._rsync_type = 'gnu'

        job = self.db.get_sync_job(self.job_name)
        cmd = rsync_manager.build_rsync_command(job)

        # Check that -e option contains SSH command string
        e_index = cmd.index('-e')
        ssh_cmd = cmd[e_index + 1]

        # Should be a command string, not a file path
        self.assertIn('ssh', ssh_cmd)
        self.assertIn('ConnectTimeout=30', ssh_cmd)

        # No wrapper script should be created
        self.assertIsNone(rsync_manager._wrapper_script_path)

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    def test_wrapper_cleanup_after_sync(self, mock_run, mock_popen):
        """Test that wrapper script is cleaned up after sync"""
        # Mock SSH connection test
        mock_ssh_result = Mock()
        mock_ssh_result.returncode = 0
        mock_ssh_result.stdout = "bardkeeper-connection-test"
        mock_ssh_result.stderr = ""
        mock_run.return_value = mock_ssh_result

        # Mock rsync process
        lines = ["sending incremental file list\n", ""]
        mock_stdout = Mock()
        mock_stdout.readline = Mock(side_effect=lines)

        mock_process = Mock()
        mock_process.stdout = mock_stdout
        mock_process.wait = Mock(return_value=0)
        mock_popen.return_value = mock_process

        # Force openrsync type
        rsync_manager = RsyncManager(self.db)
        rsync_manager._rsync_type = 'openrsync'

        job = self.db.get_sync_job(self.job_name)

        # Execute sync
        result = rsync_manager.execute_sync(job)

        # Check that sync succeeded
        self.assertTrue(result.success)

        # Check that wrapper script was cleaned up
        self.assertIsNone(rsync_manager._wrapper_script_path)


if __name__ == "__main__":
    unittest.main()
