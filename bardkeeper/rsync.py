"""
Core rsync functionality for BardKeeper
"""

import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
import tempfile


class RsyncManager:
    """Class to handle rsync operations"""
    
    def __init__(self, db):
        """Initialize the rsync manager"""
        self.db = db
    
    def _build_rsync_command(self, job):
        """Build the rsync command based on job configuration"""
        # Base rsync command
        cmd = ["rsync"]
        
        # Add options
        options = ["-avh"]  # Archive, verbose, human-readable
        
        if job['track_progress']:
            options.append("--progress")
        
        # Add compression if requested
        options.append("-z")  # Compression
        
        # Other useful options
        options.extend(["--delete", "--itemize-changes"])
        
        # Source path - ensure trailing slash to copy contents
        # If the remote path doesn't end with a slash, rsync will create
        # a subdirectory with the basename of the remote path
        remote_path = job['remote_path']
        if not remote_path.endswith('/'):
            remote_path += '/'
        source = f"{job['username']}@{job['host']}:{remote_path}"
        
        # Destination path (ensure it exists)
        # Extract the basename of the remote path to create a subdirectory
        remote_basename = os.path.basename(os.path.normpath(job['remote_path']))
        dest = job['local_path']
        
        # If local_path doesn't end with the remote basename, append it
        if not dest.endswith(remote_basename):
            dest = os.path.join(dest, remote_basename)
        
        # Ensure destination directory exists
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        
        # Build full command
        cmd.extend(options)
        cmd.extend([source, dest])
        
        return cmd
    
    def _parse_progress(self, line):
        """Parse rsync progress from output line"""
        # Match percentage patterns like "    1,238,459  99%   14.98MB/s    0:01:23"
        match = re.search(r'(\d+)%', line)
        if match:
            return int(match.group(1))
        return None
    
    def sync(self, job_name, progress_callback=None):
        """Sync a specific job"""
        job = self.db.get_sync_job(job_name)
        if not job:
            raise ValueError(f"No sync job found with name '{job_name}'")
        
        # Update job status
        self.db.update_sync_status(job_name, 'running')
        
        # Build the rsync command
        cmd = self._build_rsync_command(job)
        
        # Prepare log file if tracking progress
        log_file = None
        if job['track_progress']:
            log_dir = os.path.expanduser("~/.bardkeeper/logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f"{job_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        
        try:
            # Run rsync command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Process output
            log_lines = []
            for line in process.stdout:
                # Store log line
                log_lines.append(line)
                
                # Write to log file if tracking progress
                if log_file:
                    with open(log_file, 'a') as f:
                        f.write(line)
                
                # Extract progress if callback provided
                if progress_callback and job['track_progress']:
                    progress = self._parse_progress(line)
                    if progress is not None:
                        progress_callback(progress)
            
            # Wait for process to complete
            returncode = process.wait()
            
            # Check if rsync was successful
            if returncode == 0:
                # Update last synced timestamp
                self.db.update_last_synced(job_name)
                
                # Handle compression if needed
                if job['use_compression']:
                    self._compress_directory(job)
                
                return True, log_lines
            else:
                self.db.update_sync_status(job_name, 'failed')
                return False, log_lines
                
        except Exception as e:
            self.db.update_sync_status(job_name, 'failed')
            raise e
    
    def _compress_directory(self, job):
        """Compress a directory after syncing"""
        # Get compression command from config
        compression_cmd = self.db.get_config('compression_command')
        
        # Source directory to compress
        source_dir = job['local_path']
        if not os.path.exists(source_dir):
            raise FileNotFoundError(f"Directory to compress not found: {source_dir}")
        
        # Destination archive file - ensure it ends with .tar.gz
        archive_name = os.path.basename(source_dir.rstrip('/'))
        dest_file = f"{os.path.dirname(source_dir)}/{archive_name}.tar.gz"
        
        # Build compression command - need to cd to parent directory for proper archiving
        parent_dir = os.path.dirname(source_dir)
        dir_to_compress = os.path.basename(source_dir.rstrip('/'))
        
        # Create a command that changes to the parent directory and then compresses
        cmd = f"cd {shlex.quote(parent_dir)} && {compression_cmd} {shlex.quote(archive_name + '.tar.gz')} {shlex.quote(dir_to_compress)}"
        
        # Run compression command
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"Compression failed: {result.stderr}")
            
        # Remove the original directory after successful compression
        if os.path.exists(dest_file):
            shutil.rmtree(source_dir, ignore_errors=True)
    
    def extract_archive(self, job_name, extract_path=None):
        """Extract a compressed archive"""
        job = self.db.get_sync_job(job_name)
        if not job:
            raise ValueError(f"No sync job found with name '{job_name}'")
        
        if not job['use_compression']:
            raise ValueError(f"Job '{job_name}' is not configured for compression")
        
        # Source archive file - reconstruct archive path from job settings
        local_path = job['local_path']
        archive_name = os.path.basename(local_path.rstrip('/'))
        source_file = f"{os.path.dirname(local_path)}/{archive_name}.tar.gz"
        
        if not os.path.exists(source_file):
            raise FileNotFoundError(f"Archive file not found: {source_file}")
        
        # Destination directory to extract to
        if not extract_path:
            extract_path = os.path.dirname(local_path)
        extract_path = os.path.expanduser(extract_path)
        
        # Create extract directory if it doesn't exist
        os.makedirs(extract_path, exist_ok=True)
        
        # Get extraction command from config
        extraction_cmd = self.db.get_config('extraction_command')
        
        # Build extraction command
        cmd = f"{extraction_cmd} {shlex.quote(source_file)} -C {shlex.quote(extract_path)}"
        
        # Run extraction command
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"Extraction failed: {result.stderr}")
        
        return extract_path
    
    def get_directory_tree(self, job_name, max_depth=2):
        """Generate a directory tree for a sync job"""
        job = self.db.get_sync_job(job_name)
        if not job:
            raise ValueError(f"No sync job found with name '{job_name}'")
        
        # Determine the correct path to check
        if job['use_compression']:
            # For compressed archives, we need to check if the archive exists
            local_path = job['local_path']
            archive_name = os.path.basename(local_path.rstrip('/'))
            archive_path = f"{os.path.dirname(local_path)}/{archive_name}.tar.gz"
            
            if os.path.exists(archive_path):
                # Extract to temp directory for tree generation
                with tempfile.TemporaryDirectory() as tmp_dir:
                    extraction_cmd = self.db.get_config('extraction_command')
                    cmd = f"{extraction_cmd} {shlex.quote(archive_path)} -C {shlex.quote(tmp_dir)}"
                    
                    try:
                        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        return self._get_tree(tmp_dir, max_depth)
                    except subprocess.CalledProcessError:
                        return ["[Error extracting archive for preview]"]
            else:
                return ["[Compressed archive not found]"]
        else:
            # For regular directories
            path = job['local_path']
            if os.path.exists(path):
                return self._get_tree(path, max_depth)
            else:
                return ["[Directory not found]"]
    
    def _get_tree(self, path, max_depth, current_depth=0, prefix=""):
        """Recursive helper for directory tree generation"""
        if current_depth > max_depth:
            return ["..."]
        
        result = []
        path_obj = Path(path)
        
        try:
            # Get sorted list of items
            items = sorted(path_obj.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                item_prefix = "└── " if is_last else "├── "
                
                # Add item to result
                result.append(f"{prefix}{item_prefix}{item.name}{'/' if item.is_dir() else ''}")
                
                # Add sub-items if directory and not at max depth
                if item.is_dir() and current_depth < max_depth:
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    result.extend(self._get_tree(item, max_depth, current_depth + 1, child_prefix))
                
        except PermissionError:
            result.append(f"{prefix}[Permission denied]")
        except Exception as e:
            result.append(f"{prefix}[Error: {str(e)}]")
        
        return result
