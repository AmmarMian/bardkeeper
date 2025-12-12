"""
Test suite for rsync module
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import Mock, patch
from pathlib import Path

from bardkeeper.database import BardkeeperDB
from bardkeeper.rsync import RsyncManager


class TestRsyncManager(unittest.TestCase):
    """Test cases for RsyncManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Use a temporary file for the database
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_db.json")
        self.db = BardkeeperDB(self.db_path)
        self.rsync_manager = RsyncManager(self.db)
        
        # Create a mock job
        self.job_name = "test_job"
        self.db.add_sync_job(
            name=self.job_name,
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path=os.path.join(self.temp_dir.name, "local_path"),
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
        cmd = self.rsync_manager._build_rsync_command(job)
        
        # Check command structure
        self.assertEqual(cmd[0], "rsync")
        self.assertIn("-avh", cmd)  # Archive, verbose, human-readable
        self.assertIn("-z", cmd)  # Compression
        self.assertIn("--progress", cmd)  # Progress tracking
        self.assertIn("--delete", cmd)
        self.assertIn("--itemize-changes", cmd)
        
        # Check source and destination
        source = f"test_user@test_host:/remote/path"
        dest = os.path.join(self.temp_dir.name, "local_path")
        self.assertIn(source, cmd)
        self.assertIn(dest, cmd)
    
    def test_parse_progress(self):
        """Test parsing progress from rsync output"""
        # Test with progress line
        line = "    1,238,459  99%   14.98MB/s    0:01:23"
        progress = self.rsync_manager._parse_progress(line)
        self.assertEqual(progress, 99)
        
        # Test with non-progress line
        line = "sending incremental file list"
        progress = self.rsync_manager._parse_progress(line)
        self.assertIsNone(progress)
    
    @patch('subprocess.Popen')
    def test_sync_success(self, mock_popen):
        """Test successful sync operation"""
        # Mock subprocess.Popen
        mock_process = Mock()
        mock_process.stdout = ["sending incremental file list", "file1", "file2", "    1,238,459  99%   14.98MB/s    0:01:23"]
        mock_process.wait.return_value = 0  # Success
        mock_popen.return_value = mock_process
        
        # Mock progress callback
        mock_callback = Mock()
        
        # Call sync
        success, log_lines = self.rsync_manager.sync(self.job_name, mock_callback)
        
        # Check result
        self.assertTrue(success)
        self.assertEqual(len(log_lines), 4)
        
        # Check callback was called
        mock_callback.assert_called_with(99)
        
        # Check job status was updated
        job = self.db.get_sync_job(self.job_name)
        self.assertEqual(job["sync_status"], "completed")
        self.assertIsNotNone(job["last_synced"])
    
    @patch('subprocess.Popen')
    def test_sync_failure(self, mock_popen):
        """Test failed sync operation"""
        # Mock subprocess.Popen
        mock_process = Mock()
        mock_process.stdout = ["sending incremental file list", "rsync: connection failed: Connection refused (111)"]
        mock_process.wait.return_value = 1  # Failure
        mock_popen.return_value = mock_process
        
        # Call sync
        success, log_lines = self.rsync_manager.sync(self.job_name)
        
        # Check result
        self.assertFalse(success)
        self.assertEqual(len(log_lines), 2)
        
        # Check job status was updated
        job = self.db.get_sync_job(self.job_name)
        self.assertEqual(job["sync_status"], "failed")
    
    @patch('subprocess.run')
    def test_compress_directory(self, mock_run):
        """Test directory compression"""
        # Set up mock
        mock_run.return_value.returncode = 0
        
        # Get job and set up directory
        job = self.db.get_sync_job(self.job_name)
        os.makedirs(job["local_path"], exist_ok=True)
        
        # Call compress
        self.rsync_manager._compress_directory(job)
        
        # Check subprocess.run was called with correct arguments
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("tar -czf", args)
        self.assertIn(job["local_path"], args)
    
    @patch('subprocess.run')
    def test_extract_archive(self, mock_run):
        """Test archive extraction"""
        # Set up mock
        mock_run.return_value.returncode = 0
        
        # Get job and update to use compression
        self.db.update_sync_job(self.job_name, use_compression=True)
        job = self.db.get_sync_job(self.job_name)
        
        # Create dummy archive file
        archive_path = f"{job['local_path']}.tar.gz"
        os.makedirs(os.path.dirname(archive_path), exist_ok=True)
        with open(archive_path, 'w') as f:
            f.write("dummy archive")
        
        # Call extract
        extract_path = self.rsync_manager.extract_archive(self.job_name)
        
        # Check subprocess.run was called with correct arguments
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("tar -xzf", args)
        self.assertIn(archive_path, args)
        self.assertIn(extract_path, args)
    
    def test_get_directory_tree(self):
        """Test directory tree generation"""
        # Set up directory structure
        job = self.db.get_sync_job(self.job_name)
        os.makedirs(job["local_path"], exist_ok=True)
        os.makedirs(os.path.join(job["local_path"], "dir1"), exist_ok=True)
        os.makedirs(os.path.join(job["local_path"], "dir2"), exist_ok=True)
        with open(os.path.join(job["local_path"], "file1.txt"), 'w') as f:
            f.write("test")
        
        # Get tree with depth 1
        tree = self.rsync_manager.get_directory_tree(self.job_name, max_depth=1)
        
        # Check tree structure
        self.assertTrue(any("dir1" in line for line in tree))
        self.assertTrue(any("dir2" in line for line in tree))
        self.assertTrue(any("file1.txt" in line for line in tree))


if __name__ == "__main__":
    unittest.main()
