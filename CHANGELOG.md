# Changelog

All notable changes to BardKeeper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-01-XX

### Added
- **SSH Connection Management**: Dedicated SSH module with key support, configurable timeouts, and connection testing
  - SSH key path specification (`--ssh-key` option)
  - Custom SSH ports (`--ssh-port` option)
  - SSH connection timeout configuration
  - SSH multiplexing for improved performance
  - Pre-sync SSH connection testing with clear error messages
- **File-based Locking**: Prevents concurrent syncs of the same job across processes
- **Automatic Retry Logic**: Configurable retry for recoverable errors (timeouts, partial transfers)
- **Interactive Menus**:
  - `bardkeeper sync` without arguments shows job selection menu
  - `bardkeeper manage` without arguments shows job selection menu
  - Option to sync all jobs at once
  - Interactive job editing and deletion
- **Enhanced Progress Tracking**:
  - Uses `--info=progress2` for consistent total progress
  - Fixed 0% stuck bug
  - Spinner mode for jobs without progress tracking
  - Compression status messages
- **Pydantic Data Validation**: All job and config data validated with Pydantic models
- **Bandwidth Limiting**: Optional bandwidth limits for syncs
- **Exclude Patterns**: Support for rsync exclude patterns
- **Extended Job Metadata**:
  - Last sync duration tracking
  - Bytes transferred tracking
  - Last error message storage
- **Rich CLI**: Better terminal UI with rich_click integration

### Changed
- **Project Structure**: Migrated to modern `src/` layout with `pyproject.toml`
- **Package Management**: Now uses `uv` and `pyproject.toml` instead of `setup.py`
- **Dependencies**:
  - All dependencies now have version constraints for reproducibility
  - `filelock` added for concurrent sync protection
  - `pydantic` added for data validation
  - `croniter` now required (was optional)
  - `rich_click` for improved CLI aesthetics
- **Exception Handling**: Custom exception hierarchy with specific error types and recovery strategies
- **Configuration**: Path objects properly serialized for JSON storage
- **Database**: TinyDB operations wrapped with better error handling

### Fixed
- **Progress Tracking**: Fixed bug where progress bar stayed at 0% during sync
- **SSH Handling**: No longer relies solely on `~/.ssh/config`
- **Timeout Issues**: Added timeout handling to prevent indefinite hangs
- **Compression State**: Atomic compression operations prevent inconsistent states
- **Race Conditions**: File-based locking prevents database corruption
- **Path Handling**: Better handling of paths with spaces and special characters
- **Error Messages**: Clear, actionable error messages for common issues

### Removed
- `setup.py` (replaced by `pyproject.toml`)
- `requirements.txt` (dependencies now in `pyproject.toml`)

## [1.0.0] - Previous Release

Initial release with basic rsync job management, compression, and cron scheduling support.

---

## Migration Guide from 1.x to 2.0

### Breaking Changes

1. **Python Version**: Now requires Python 3.9+
2. **Installation**: Use `uv sync` or `pip install -e .` with the new `pyproject.toml`
3. **Database**: Existing databases are compatible, but will be migrated on first run

### New Features to Try

1. **SSH Keys**: Add SSH key paths to your jobs for better security
   ```bash
   bardkeeper manage <job-name>
   # Then select "Edit settings" and specify SSH key path
   ```

2. **Interactive Sync**: Just run `bardkeeper sync` without arguments for a menu

3. **Bandwidth Limits**: Prevent network saturation
   ```bash
   bardkeeper manage <job-name>
   # Set bandwidth limit in KB/s
   ```

4. **Exclude Patterns**: Exclude files from sync
   ```bash
   bardkeeper manage <job-name>
   # Add comma-separated exclude patterns
   ```

### Recommended Actions

1. **Test SSH connections** for existing jobs to ensure they work with the new SSH module
2. **Review job configurations** using `bardkeeper info <job-name>`
3. **Set up SSH keys** if not already using them for better security
4. **Check logs** at `~/.bardkeeper/logs/` for detailed sync information
