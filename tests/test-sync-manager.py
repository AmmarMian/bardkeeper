"""
Test suite for sync manager module
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path

from bardkeeper.database import BardkeeperDB
from bardkeeper.rsync import RsyncManager
from bardkeeper.sync_manager import SyncManager


class TestSyncManager(unittest.TestCase):
    """Test cases for SyncManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Use a temporary directory for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_db.json")
        
        # Create database and managers
        self.db = BardkeeperDB(self.db_path)
        self.rsync_manager = RsyncManager(self.db)
        self.sync_manager = SyncManager(self.db, self.rsync_manager)
        
        # Create test paths
        self.local_path = os.path.join(self.temp_dir.name, "local_path")
    
    def tearDown(self):
        """Tear down test fixtures"""
        self.temp_dir.cleanup()
    
    def test_add_sync_job(self):
        """Test adding a sync job"""
        # Add job
        job = self.sync_manager.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path=self.local_path,
            use_compression=False,
            cron_schedule=None,
            track_progress=False
        )
        
        # Check job was added correctly
        self.assertEqual(job["name"], "test_job")
        self.assertEqual(job["host"], "test_host")
        self.assertEqual(job["username"], "test_user")
        self.assertEqual(job["remote_path"], "/remote/path")
        self.assertEqual(job["local_path"], self.local_path)
        self.assertEqual(job["use_compression"], False)
        self.assertEqual(job["cron_schedule"], None)
        self.assertEqual(job["track_progress"], False)
    
    def test_add_sync_job_with_invalid_cron(self):
        """Test adding a sync job with invalid cron schedule"""
        # We need to mock croniter since it might not be installed
        with patch('bardkeeper.sync_manager.croniter') as mock_croniter:
            # Make croniter raise ValueError
            mock_croniter.side_effect = ValueError("Invalid cron schedule")
            
            # Adding job with invalid cron should raise ValueError
            with self.assertRaises(ValueError):
                self.sync_manager.add_sync_job(
                    name="test_job",
                    host="test_host",
                    username="test_user",
                    remote_path="/remote/path",
                    local_path=self.local_path,
                    cron_schedule="invalid-cron-schedule"
                )
    
    def test_remove_sync_job(self):
        """Test removing a sync job"""
        # Add job
        self.sync_manager.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path=self.local_path,
            use_compression=False
        )
        
        # Create the local directory
        os.makedirs(self.local_path, exist_ok=True)
        
        # Remove job without removing files
        result = self.sync_manager.remove_sync_job("test_job", remove_files=False)
        
        # Check removal was successful
        self.assertTrue(result)
        
        # Job should no longer exist
        job = self.db.get_sync_job("test_job")
        self.assertIsNone(job)
        
        # Directory should still exist
        self.assertTrue(os.path.exists(self.local_path))
        
        # Add job again
        self.sync_manager.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path=self.local_path,
            use_compression=False
        )
        
        # Remove job and files
        result = self.sync_manager.remove_sync_job("test_job", remove_files=True)
        
        # Check removal was successful
        self.assertTrue(result)
        
        # Directory should be removed
        self.assertFalse(os.path.exists(self.local_path))
    
    @patch('bardkeeper.rsync.RsyncManager.sync')
    def test_sync_job(self, mock_sync):
        """Test syncing a job"""
        # Set up mock
        mock_sync.return_value = (True, ["log line 1", "log line 2"])
        
        # Add job
        self.sync_manager.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path=self.local_path
        )
        
        # Call sync_job
        result = self.sync_manager.sync_job("test_job")
        
        # Check result
        self.assertTrue(result[0])
        self.assertEqual(len(result[1]), 2)
        
        # Check mock was called correctly
        mock_sync.assert_called_once_with("test_job", None)
    
    def test_should_sync_now(self):
        """Test checking if a job should be synced now"""
        # Define a job with no schedule
        job_no_schedule = {
            "name": "job_no_schedule",
            "cron_schedule": None,
            "last_synced": None
        }
        
        # Job with no schedule should not sync
        self.assertFalse(self.sync_manager.should_sync_now(job_no_schedule))
        
        # Define a job with schedule but never synced
        job_never_synced = {
            "name": "job_never_synced",
            "cron_schedule": "0 0 * * *",
            "last_synced": None
        }
        
        # We need to mock croniter since it might not be installed
        with patch('bardkeeper.sync_manager.croniter') as mock_croniter:
            # Job with schedule but never synced should sync
            self.assertTrue(self.sync_manager.should_sync_now(job_never_synced))
            
            # Define a job with schedule and last sync in the past
            job_past_sync = {
                "name": "job_past_sync",
                "cron_schedule": "0 0 * * *",
                "last_synced": (datetime.now() - timedelta(days=2)).isoformat()
            }
            
            # Mock croniter
            mock_cron = MagicMock()
            mock_cron.get_next.return_value = datetime.now() - timedelta(hours=1)  # Next run time in the past
            mock_croniter.return_value = mock_cron
            
            # Job with past next run time should sync
            self.assertTrue(self.sync_manager.should_sync_now(job_past_sync))
            
            # Define a job with schedule and next sync in the future
            job_future_sync = {
                "name": "job_future_sync",
                "cron_schedule": "0 0 * * *",
                "last_synced": datetime.now().isoformat()
            }
            
            # Update mock croniter
            mock_cron.get_next.return_value = datetime.now() + timedelta(hours=1)  # Next run time in the future
            
            # Job with future next run time should not sync
            self.assertFalse(self.sync_manager.should_sync_now(job_future_sync))
    
    @patch('bardkeeper.rsync.RsyncManager.sync')
    def test_sync_all_due(self, mock_sync):
        """Test syncing all due jobs"""
        # Set up mock
        mock_sync.return_value = (True, ["log line 1", "log line 2"])
        
        # Add jobs
        self.sync_manager.add_sync_job(
            name="job1",
            host="host1",
            username="user1",
            remote_path="/remote/path1",
            local_path=os.path.join(self.temp_dir.name, "path1"),
            cron_schedule="0 0 * * *"  # Daily at midnight
        )
        
        self.sync_manager.add_sync_job(
            name="job2",
            host="host2",
            username="user2",
            remote_path="/remote/path2",
            local_path=os.path.join(self.temp_dir.name, "path2"),
            cron_schedule=None  # No schedule
        )
        
        # Mock should_sync_now to return True for job1 and False for job2
        original_should_sync_now = self.sync_manager.should_sync_now
        
        def mock_should_sync_now(job):
            if job["name"] == "job1":
                return True
            return False
        
        self.sync_manager.should_sync_now = mock_should_sync_now
        
        # Call sync_all_due
        synced_jobs = self.sync_manager.sync_all_due()
        
        # Check result
        self.assertEqual(len(synced_jobs), 1)
        self.assertEqual(synced_jobs[0], "job1")
        
        # Check mock was called correctly
        mock_sync.assert_called_once_with("job1", None)
        
        # Restore original method
        self.sync_manager.should_sync_now = original_should_sync_now
    
    @patch('subprocess.run')
    def test_update_job_local_path(self, mock_run):
        """Test updating a job's local path"""
        # Add job
        self.sync_manager.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path=self.local_path
        )
        
        # Create the original directory
        os.makedirs(self.local_path, exist_ok=True)
        with open(os.path.join(self.local_path, "test_file.txt"), "w") as f:
            f.write("test content")
        
        # New path
        new_path = os.path.join(self.temp_dir.name, "new_path")
        
        # Update local path
        result = self.sync_manager.update_job("test_job", local_path=new_path)
        
        # Check result
        self.assertEqual(result["local_path"], new_path)
        
        # Check file was moved
        self.assertFalse(os.path.exists(os.path.join(self.local_path, "test_file.txt")))
        self.assertTrue(os.path.exists(os.path.join(new_path, "test_file.txt")))
    
    def test_update_job_host(self):
        """Test updating a job's host resets sync status"""
        # Add job with sync status
        self.sync_manager.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path=self.local_path
        )
        
        # Update last synced and status
        self.db.update_last_synced("test_job")
        job_before = self.db.get_sync_job("test_job")
        self.assertEqual(job_before["sync_status"], "completed")
        self.assertIsNotNone(job_before["last_synced"])
        
        # Update host
        result = self.sync_manager.update_job("test_job", host="new_host")
        
        # Check sync status was reset
        self.assertEqual(result["host"], "new_host")
        self.assertEqual(result["sync_status"], "never_run")
        self.assertIsNone(result["last_synced"])


if __name__ == "__main__":
    unittest.main()
