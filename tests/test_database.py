"""
Test suite for database module
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from bardkeeper.database import BardkeeperDB


class TestDatabase(unittest.TestCase):
    """Test cases for BardkeeperDB class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Use a temporary file for the database
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_db.json")
        self.db = BardkeeperDB(self.db_path)
    
    def tearDown(self):
        """Tear down test fixtures"""
        self.temp_dir.cleanup()
    
    def test_add_sync_job(self):
        """Test adding a sync job"""
        # Add a job
        job = self.db.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path="/local/path",
            use_compression=False,
            cron_schedule=None,
            track_progress=False
        )
        
        # Check job was added correctly
        self.assertEqual(job["name"], "test_job")
        self.assertEqual(job["host"], "test_host")
        self.assertEqual(job["username"], "test_user")
        self.assertEqual(job["remote_path"], "/remote/path")
        self.assertEqual(job["local_path"], "/local/path")
        self.assertEqual(job["use_compression"], False)
        self.assertEqual(job["cron_schedule"], None)
        self.assertEqual(job["track_progress"], False)
        self.assertEqual(job["last_synced"], None)
        self.assertEqual(job["sync_status"], "never_run")
    
    def test_get_sync_job(self):
        """Test getting a sync job by name"""
        # Add a job
        self.db.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path="/local/path",
            use_compression=False,
            cron_schedule=None,
            track_progress=False
        )
        
        # Get job
        job = self.db.get_sync_job("test_job")
        
        # Check job was retrieved correctly
        self.assertIsNotNone(job)
        self.assertEqual(job["name"], "test_job")
        
        # Try getting non-existent job
        job = self.db.get_sync_job("non_existent_job")
        self.assertIsNone(job)
    
    def test_get_all_sync_jobs(self):
        """Test getting all sync jobs"""
        # Initially should be empty
        jobs = self.db.get_all_sync_jobs()
        self.assertEqual(len(jobs), 0)
        
        # Add two jobs
        self.db.add_sync_job(
            name="job1",
            host="host1",
            username="user1",
            remote_path="/remote/path1",
            local_path="/local/path1",
            use_compression=False,
            cron_schedule=None,
            track_progress=False
        )
        
        self.db.add_sync_job(
            name="job2",
            host="host2",
            username="user2",
            remote_path="/remote/path2",
            local_path="/local/path2",
            use_compression=True,
            cron_schedule="0 0 * * *",
            track_progress=True
        )
        
        # Get all jobs
        jobs = self.db.get_all_sync_jobs()
        
        # Should have two jobs
        self.assertEqual(len(jobs), 2)
    
    def test_update_sync_job(self):
        """Test updating a sync job"""
        # Add a job
        self.db.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path="/local/path",
            use_compression=False,
            cron_schedule=None,
            track_progress=False
        )
        
        # Update job
        self.db.update_sync_job(
            "test_job",
            host="new_host",
            use_compression=True
        )
        
        # Get updated job
        job = self.db.get_sync_job("test_job")
        
        # Check updated fields
        self.assertEqual(job["host"], "new_host")
        self.assertEqual(job["use_compression"], True)
        
        # Check other fields remain the same
        self.assertEqual(job["username"], "test_user")
        self.assertEqual(job["remote_path"], "/remote/path")
        self.assertEqual(job["local_path"], "/local/path")
    
    def test_remove_sync_job(self):
        """Test removing a sync job"""
        # Add a job
        self.db.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path="/local/path",
            use_compression=False,
            cron_schedule=None,
            track_progress=False
        )
        
        # Remove job
        result = self.db.remove_sync_job("test_job")
        
        # Check removal was successful
        self.assertTrue(result)
        
        # Job should no longer exist
        job = self.db.get_sync_job("test_job")
        self.assertIsNone(job)
        
        # Removing non-existent job should return False
        result = self.db.remove_sync_job("non_existent_job")
        self.assertFalse(result)
    
    def test_update_last_synced(self):
        """Test updating the last_synced field"""
        # Add a job
        self.db.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path="/local/path",
            use_compression=False,
            cron_schedule=None,
            track_progress=False
        )
        
        # Update last_synced
        self.db.update_last_synced("test_job")
        
        # Get updated job
        job = self.db.get_sync_job("test_job")
        
        # Check last_synced was updated
        self.assertIsNotNone(job["last_synced"])
        self.assertEqual(job["sync_status"], "completed")
    
    def test_update_sync_status(self):
        """Test updating the sync_status field"""
        # Add a job
        self.db.add_sync_job(
            name="test_job",
            host="test_host",
            username="test_user",
            remote_path="/remote/path",
            local_path="/local/path",
            use_compression=False,
            cron_schedule=None,
            track_progress=False
        )
        
        # Update sync_status
        self.db.update_sync_status("test_job", "running")
        
        # Get updated job
        job = self.db.get_sync_job("test_job")
        
        # Check sync_status was updated
        self.assertEqual(job["sync_status"], "running")
    
    def test_config(self):
        """Test configuration settings"""
        # Get default config
        config = self.db.get_config()
        
        # Check default values
        self.assertEqual(config["db_path"], self.db_path)
        self.assertEqual(config["compression_command"], "tar -czf")
        self.assertEqual(config["extraction_command"], "tar -xzf")
        self.assertFalse(config["cache_enabled"])
        
        # Update config
        self.db.update_config(
            compression_command="custom-tar -czf",
            cache_enabled=True
        )
        
        # Get updated config
        config = self.db.get_config()
        
        # Check updated values
        self.assertEqual(config["compression_command"], "custom-tar -czf")
        self.assertTrue(config["cache_enabled"])
        
        # Check non-updated values remain the same
        self.assertEqual(config["db_path"], self.db_path)
        self.assertEqual(config["extraction_command"], "tar -xzf")


if __name__ == "__main__":
    unittest.main()
