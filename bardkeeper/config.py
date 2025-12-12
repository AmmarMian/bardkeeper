"""
Configuration manager for BardKeeper
"""

import os
import json
from pathlib import Path

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.bardkeeper/config.json")


class ConfigManager:
    """Manage configuration for BardKeeper"""

    def __init__(self, db):
        """Initialize config manager"""
        self.db = db

    def get_config(self):
        """Get all configuration"""
        return self.db.get_config()

    def update_config(self, **kwargs):
        """Update configuration values"""
        # Special handling for database path changes
        if "db_path" in kwargs and kwargs["db_path"] != self.db.get_config("db_path"):
            # Save DB path to config file so future runs know where the DB is
            self._save_db_path(kwargs["db_path"])

        # Handle cache directory
        if "cache_enabled" in kwargs and kwargs["cache_enabled"]:
            cache_dir = kwargs.get("cache_dir", self.db.get_config("cache_dir"))
            os.makedirs(os.path.expanduser(cache_dir), exist_ok=True)

        # Update in database
        self.db.update_config(**kwargs)

    def _save_db_path(self, db_path):
        """Save database path to config file"""
        config_data = {"db_path": db_path}

        # Ensure config directory exists
        os.makedirs(os.path.dirname(DEFAULT_CONFIG_PATH), exist_ok=True)

        # Write to config file
        with open(DEFAULT_CONFIG_PATH, "w") as f:
            json.dump(config_data, f)

    @staticmethod
    def get_saved_db_path():
        """Get saved database path from config file"""
        if os.path.exists(DEFAULT_CONFIG_PATH):
            try:
                with open(DEFAULT_CONFIG_PATH, "r") as f:
                    config = json.load(f)
                    return config.get("db_path")
            except:
                pass

        return None
