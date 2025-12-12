"""
Test suite for CLI module
"""

import os
import sys
import unittest
import tempfile
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from bardkeeper.cli import cli, app_ctx


class TestCLI(unittest.TestCase):
    """Test cases for CLI commands"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.runner = CliRunner()
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # Mock app context initialization
        self.mock_init_app = patch.object(app_ctx, 'init_app', return_value=True).start()
        
        # Mock app context components
        self.mock_db = MagicMock()
        self.mock_rsync_manager = MagicMock()
        self.mock_sync_manager = MagicMock()
        self.mock_config_manager = MagicMock()
        
        app_ctx.db = self.mock_db
        app_ctx.rsync_manager = self.mock_rsync_manager
        app_ctx.sync_manager = self.mock_sync_manager
        app_ctx.config_manager = self.mock_config_manager
    
    def tearDown(self):
        """Tear down test fixtures"""
        self.temp_dir.cleanup()
        patch.stopall()
    
    def test_cli_init(self):
        """Test CLI initialization"""
        # Run CLI with --help
        result = self.runner.invoke(cli, ['--help'])
        
        # Check result
        self.assertEqual(result.exit_code, 0)
        self.assertIn("BardKeeper", result.output)
        self.assertIn("A tool for managing rsync-based archives", result.output)
    
    def test_list_command_empty(self):
        """Test list command with no jobs"""
        # Mock get_all_jobs_status to return empty list
        self.mock_sync_manager.get_all_jobs_status.return_value = []
        
        # Run list command
        result = self.runner.invoke(cli, ['list'])
        
        # Check result
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No sync jobs found", result.output)
    
    def test_list_command_with_jobs(self):
        """Test list command with jobs"""
        # Mock get_all_jobs_status to return jobs
        self.mock_sync_manager.get_all_jobs_status.return_value = [
            {
                'name': 'job1',
                'host': 'host1',
                'username': 'user1',
                'remote_path': '/remote/path1',
                'local_path': '/local/path1',
                'use_compression': False,
                'cron_schedule': '0 0 * * *',
                'track_progress': True,
                'last_synced': '2025-05-15T12:00:00',
                'sync_status': 'completed',
                'next_sync': '2025-05-16T00:00:00'
            }
        ]
        
        # Run list command
        result = self.runner.invoke(cli, ['list'])
        
        # Check result
        self.assertEqual(result.exit_code, 0)
        self.assertIn("job1", result.output)
        self.assertIn("host1", result.output)
        self.assertIn("user1", result.output)
    
    @patch('bardkeeper.cli.prompt_for_job_details')
    @patch('click.confirm')
    def test_add_command(self, mock_confirm, mock_prompt):
        """Test add command"""
        # Mock prompt_for_job_details
        mock_prompt.return_value = {
            'name': 'job1',
            'host': 'host1',
            'username': 'user1',
            'remote_path': '/remote/path1',
            'local_path': '/local/path1',
            'use_compression': False,
            'cron_schedule': None,
            'track_progress': False
        }
        
        # Mock add_sync_job
        self.mock_sync_manager.add_sync_job.return_value = {
            'name': 'job1',
            'host': 'host1',
            'username': 'user1',
            'remote_path': '/remote/path1',
            'local_path': '/local/path1',
            'use_compression': False,
            'cron_schedule': None,
            'track_progress': False
        }
        
        # Mock confirm (don't sync now)
        mock_confirm.return_value = False
        
        # Run add command
        result = self.runner.invoke(cli, ['add'])
        
        # Check result
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Successfully added sync job", result.output)
        
        # Check sync_manager.add_sync_job was called correctly
        self.mock_sync_manager.add_sync_job.assert_called_once_with(
            name='job1',
            host='host1',
            username='user1',
            remote_path='/remote/path1',
            local_path='/local/path1',
            use_compression=False,
            cron_schedule=None,
            track_progress=False
        )
    
    @patch('click.confirm')
    def test_remove_command(self, mock_confirm):
        """Test remove command"""
        # Mock confirm (yes, remove)
        mock_confirm.return_value = True
        
        # Mock remove_sync_job
        self.mock_sync_manager.remove_sync_job.return_value = True
        
        # Run remove command
        result = self.runner.invoke(cli, ['remove', 'job1'])
        
        # Check result
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Successfully removed sync job", result.output)
        
        # Check sync_manager.remove_sync_job was called correctly
        self.mock_sync_manager.remove_sync_job.assert_called_once_with('job1', False)
    
    def test_sync_command(self):
        """Test sync command with specified job"""
        # Mock sync
        self.mock_rsync_manager.sync.return_value = (True, ["log line 1", "log line 2"])
        
        # Mock get_sync_job
        self.mock_db.get_sync_job.return_value = {
            'name': 'job1',
            'host': 'host1',
            'username': 'user1',
            'remote_path': '/remote/path1',
            'local_path': '/local/path1',
            'use_compression': False,
            'cron_schedule': None,
            'track_progress': False
        }
        
        # Run sync command
        result = self.runner.invoke(cli, ['sync', 'job1'])
        
        # Because we're mocking most of the dependencies, we can't fully test the sync command
        # But we can at least check if the command runs without errors
        self.assertEqual(result.exit_code, 0)
    
    def test_info_command(self):
        """Test info command"""
        # Mock get_sync_job
        self.mock_db.get_sync_job.return_value = {
            'name': 'job1',
            'host': 'host1',
            'username': 'user1',
            'remote_path': '/remote/path1',
            'local_path': '/local/path1',
            'use_compression': False,
            'cron_schedule': None,
            'track_progress': False,
            'last_synced': '2025-05-15T12:00:00',
            'sync_status': 'completed'
        }
        
        # Mock get_directory_tree
        self.mock_rsync_manager.get_directory_tree.return_value = [
            "file1.txt",
            "dir1/",
            "dir1/file2.txt"
        ]
        
        # Run info command
        result = self.runner.invoke(cli, ['info', 'job1'])
        
        # Because we're mocking the rich output, we can't fully test the info command
        # But we can at least check if the command runs without errors
        self.assertEqual(result.exit_code, 0)
    
    def test_config_command(self):
        """Test config command"""
        # Mock get_config
        self.mock_config_manager.get_config.return_value = {
            'db_path': '/path/to/db.json',
            'compression_command': 'tar -czf',
            'extraction_command': 'tar -xzf',
            'cache_enabled': False,
            'cache_dir': '/path/to/cache'
        }
        
        # Run config command with --help to just check if it's properly defined
        result = self.runner.invoke(cli, ['config', '--help'])
        
        # Check result
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Manage configuration settings", result.output)
    
    def test_manage_command_no_name(self):
        """Test manage command with no job name"""
        # Mock get_all_jobs_status
        self.mock_sync_manager.get_all_jobs_status.return_value = [
            {
                'name': 'job1',
                'host': 'host1',
                'username': 'user1',
                'remote_path': '/remote/path1',
                'local_path': '/local/path1',
                'use_compression': False,
                'cron_schedule': None,
                'track_progress': False,
                'last_synced': '2025-05-15T12:00:00',
                'sync_status': 'completed'
            }
        ]
        
        # Run manage command without name
        result = self.runner.invoke(cli, ['manage'])
        
        # Should show list output
        self.assertEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
