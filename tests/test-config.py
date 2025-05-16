"""
Test suite for config manager module
"""

import os
import sys
import unittest
import tempfile
import json
from unittest.mock import patch, mock_open
from pathlib import Path

from bardkeeper.database import BardkeeperDB
from bardkeeper.config import ConfigManager, DEFAULT_CONFIG_PATH


class TestConfigManager(unittest.TestCase):
    """Test cases for ConfigManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Use a temporary directory for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_db.json")
        
        # Create database and config manager
        self.db = BardkeeperDB(self.db_path)
        self.config_manager = ConfigManager(self.db)
    
    def tearDown(self):
        """Tear down test fixtures"""
        self.temp_dir.cleanup()
    
    def test_get_config(self):
        """Test getting configuration"""
        # Get default config
        config = self.config_manager.get_config()
        
        # Check default values
        self.assertEqual(config["db_path"], self.db_path)
        self.assertEqual(config["compression_command"], "tar -czf")
        self.assertEqual(config["extraction_command"], "tar -xzf")
        self.assertFalse(config["cache_enabled"])
    
    @patch('os.makedirs')
    def test_update_config(self, mock_makedirs):
        """Test updating configuration"""
        # Update config
        self.config_manager.update_config(
            compression_command="custom-tar -czf",
            cache_enabled=True,
            cache_dir="/custom/cache/dir"
        )
        
        # Get updated config
        config = self.config_manager.get_config()
        
        # Check updated values
        self.assertEqual(config["compression_command"], "custom-tar -czf")
        self.assertTrue(config["cache_enabled"])
        self.assertEqual(config["cache_dir"], "/custom/cache/dir")
        
        # Check os.makedirs was called for cache directory
        mock_makedirs.assert_called_with("/custom/cache/dir", exist_ok=True)
    
    @patch('json.dump')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    def test_update_db_path(self, mock_makedirs, mock_file, mock_json_dump):
        """Test updating database path"""
        new_db_path = "/new/db/path.json"
        
        # Update db_path
        self.config_manager.update_config(db_path=new_db_path)
        
        # Check os.makedirs was called for config directory
        mock_makedirs.assert_called_with(os.path.dirname(DEFAULT_CONFIG_PATH), exist_ok=True)
        
        # Check file was opened correctly
        mock_file.assert_called_with(DEFAULT_CONFIG_PATH, 'w')
        
        # Check json.dump was called with correct arguments
        mock_json_dump.assert_called_with({'db_path': new_db_path}, mock_file())
    
    @patch('json.load')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_get_saved_db_path(self, mock_exists, mock_file, mock_json_load):
        """Test getting saved database path"""
        # Set up mocks
        mock_exists.return_value = True
        mock_json_load.return_value = {'db_path': '/saved/db/path.json'}
        
        # Call get_saved_db_path
        db_path = ConfigManager.get_saved_db_path()
        
        # Check result
        self.assertEqual(db_path, '/saved/db/path.json')
        
        # Check file was opened correctly
        mock_file.assert_called_with(DEFAULT_CONFIG_PATH, 'r')
    
    @patch('os.path.exists')
    def test_get_saved_db_path_no_file(self, mock_exists):
        """Test getting saved database path when no file exists"""
        # Set up mock
        mock_exists.return_value = False
        
        # Call get_saved_db_path
        db_path = ConfigManager.get_saved_db_path()
        
        # Check result
        self.assertIsNone(db_path)


if __name__ == "__main__":
    unittest.main()
