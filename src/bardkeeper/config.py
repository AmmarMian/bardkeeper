"""
Configuration manager for BardKeeper.
"""

import json
import os
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_PATH = Path("~/.bardkeeper/config.json").expanduser()


class ConfigManager:
    """Manage configuration for BardKeeper."""

    def __init__(self, db):
        """Initialize config manager."""
        self.db = db

    def get_config(self, key: Optional[str] = None):
        """
        Get configuration value(s).

        Args:
            key: Optional specific config key to retrieve

        Returns:
            Config value or entire config dict
        """
        return self.db.get_config(key)

    def update_config(self, **kwargs):
        """
        Update configuration values.

        Args:
            **kwargs: Configuration key-value pairs to update
        """
        # Special handling for database path changes
        if "db_path" in kwargs:
            current_db_path = self.db.get_config("db_path")
            if current_db_path and kwargs["db_path"] != current_db_path:
                # Save DB path to config file so future runs know where the DB is
                self._save_db_path(kwargs["db_path"])

        # Handle cache directory
        if kwargs.get("cache_enabled"):
            cache_dir = kwargs.get("cache_dir", self.db.get_config("cache_dir"))
            if cache_dir:
                Path(cache_dir).expanduser().mkdir(parents=True, exist_ok=True)

        # Update in database
        self.db.update_config(**kwargs)

    def _save_db_path(self, db_path: str):
        """Save database path to config file."""
        config_data = {"db_path": db_path}

        # Ensure config directory exists
        DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Write to config file
        with open(DEFAULT_CONFIG_PATH, "w") as f:
            json.dump(config_data, f, indent=2, default=str)

    @staticmethod
    def get_saved_db_path() -> Optional[str]:
        """
        Get saved database path from config file.

        Returns:
            Saved database path or None
        """
        if DEFAULT_CONFIG_PATH.exists():
            try:
                with open(DEFAULT_CONFIG_PATH, "r") as f:
                    config = json.load(f)
                    return config.get("db_path")
            except Exception:
                pass

        return None
