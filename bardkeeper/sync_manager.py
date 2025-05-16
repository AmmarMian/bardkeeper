"""
Sync manager for BardKeeper
"""

import os
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

try:
    from croniter import croniter
except ImportError:
    croniter = None


class SyncManager:
    """High-level sync job management"""
    
    def __init__(self, db, rsync_manager):
        """Initialize the sync manager"""
        self.db = db
        self.rsync = rsync_manager
    
    def add_sync_job(self, name, host, username, remote_path, local_path, 
                     use_compression=False, cron_schedule=None, track_progress=False):
        """Add a new sync job"""
        # Validate cron schedule if provided
        if cron_schedule and croniter:
            try:
                croniter(cron_schedule, datetime.now())
            except ValueError:
                raise ValueError(f"Invalid cron schedule: {cron_schedule}")
        
        # Add job to database
        return self.db.add_sync_job(
            name=name,
            host=host,
            username=username,
            remote_path=remote_path,
            local_path=local_path,
            use_compression=use_compression,
            cron_schedule=cron_schedule,
            track_progress=track_progress
        )
    
    def remove_sync_job(self, name, remove_files=False):
        """Remove a sync job and optionally its files"""
        job = self.db.get_sync_job(name)
        if not job:
            raise ValueError(f"No sync job found with name '{name}'")
        
        # Remove files if requested
        if remove_files:
            # Original directory
            local_path = job['local_path']
            if os.path.exists(local_path):
                if os.path.isdir(local_path):
                    shutil.rmtree(local_path)
                else:
                    os.remove(local_path)
            
            # Compressed archive if it exists
            if job['use_compression']:
                archive_path = f"{local_path}.tar.gz"
                if os.path.exists(archive_path):
                    os.remove(archive_path)
        
        # Remove from database
        return self.db.remove_sync_job(name)
    
    def sync_job(self, name, progress_callback=None):
        """Sync a specific job"""
        return self.rsync.sync(name, progress_callback)
    
    def should_sync_now(self, job):
        """Check if a job should be synced now based on cron schedule"""
        if not job['cron_schedule'] or not croniter:
            return False
        
        # If never synced, then yes
        if not job['last_synced']:
            return True
        
        # Get last sync time
        last_time = datetime.fromisoformat(job['last_synced'])
        
        # Create cron iterator
        cron = croniter(job['cron_schedule'], last_time)
        
        # Get next run time
        next_time = cron.get_next(datetime)
        
        # Check if next run time is in the past
        return datetime.now() >= next_time
    
    def sync_all_due(self, progress_callback=None):
        """Sync all jobs that are due according to their cron schedule"""
        jobs = self.db.get_all_sync_jobs()
        synced = []
        
        for job in jobs:
            if self.should_sync_now(job):
                success, _ = self.rsync.sync(job['name'], progress_callback)
                if success:
                    synced.append(job['name'])
        
        return synced
    
    def update_job(self, name, **kwargs):
        """Update a sync job with changes"""
        job = self.db.get_sync_job(name)
        if not job:
            raise ValueError(f"No sync job found with name '{name}'")
        
        # Handle special update cases
        
        # 1. Local path change: move files
        if 'local_path' in kwargs and kwargs['local_path'] != job['local_path']:
            old_path = job['local_path']
            new_path = os.path.expanduser(kwargs['local_path'])
            
            # Move actual files if they exist
            if os.path.exists(old_path):
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.move(old_path, new_path)
            
            # Move compressed archive if it exists
            if job['use_compression']:
                old_archive_name = os.path.basename(old_path.rstrip('/'))
                old_archive = f"{os.path.dirname(old_path)}/{old_archive_name}.tar.gz"
                
                new_archive_name = os.path.basename(new_path.rstrip('/'))
                new_archive = f"{os.path.dirname(new_path)}/{new_archive_name}.tar.gz"
                
                if os.path.exists(old_archive):
                    os.makedirs(os.path.dirname(new_archive), exist_ok=True)
                    shutil.move(old_archive, new_archive)
        
        # 2. Host/Remote path change: reset sync status
        if 'host' in kwargs or 'remote_path' in kwargs:
            kwargs['last_synced'] = None
            kwargs['sync_status'] = 'never_run'
        
        # 3. Compression change: handle files
        if 'use_compression' in kwargs and kwargs['use_compression'] != job['use_compression']:
            local_path = job['local_path']
            
            if kwargs['use_compression']:  # Turning compression ON
                # Compress directory if it exists
                if os.path.exists(local_path) and os.path.isdir(local_path):
                    compression_cmd = self.db.get_config('compression_command')
                    
                    # Get directory name and parent directory
                    dir_name = os.path.basename(local_path.rstrip('/'))
                    parent_dir = os.path.dirname(local_path)
                    archive_path = f"{parent_dir}/{dir_name}.tar.gz"
                    
                    # Build compression command that changes to parent dir first
                    cmd = f"cd {shlex.quote(parent_dir)} && {compression_cmd} {shlex.quote(dir_name + '.tar.gz')} {shlex.quote(dir_name)}"
                    subprocess.run(cmd, shell=True, check=True)
                    
                    # Remove original directory if archive was created
                    if os.path.exists(archive_path):
                        shutil.rmtree(local_path, ignore_errors=True)
            else:  # Turning compression OFF
                # Reconstruct archive path
                dir_name = os.path.basename(local_path.rstrip('/'))
                parent_dir = os.path.dirname(local_path)
                archive_path = f"{parent_dir}/{dir_name}.tar.gz"
                
                # Extract archive if it exists
                if os.path.exists(archive_path):
                    extraction_cmd = self.db.get_config('extraction_command')
                    
                    # Ensure parent directory exists
                    os.makedirs(parent_dir, exist_ok=True)
                    
                    # Extract to parent directory
                    cmd = f"{extraction_cmd} {shlex.quote(archive_path)} -C {shlex.quote(parent_dir)}"
                    subprocess.run(cmd, shell=True, check=True)
                    
                    # Remove archive
                    os.remove(archive_path)
        
        # 4. Validate cron schedule if provided
        if 'cron_schedule' in kwargs and kwargs['cron_schedule'] and croniter:
            try:
                croniter(kwargs['cron_schedule'], datetime.now())
            except ValueError:
                raise ValueError(f"Invalid cron schedule: {kwargs['cron_schedule']}")
        
        # Update in database
        return self.db.update_sync_job(name, **kwargs)
    
    def get_all_jobs_status(self):
        """Get status of all jobs including next sync time"""
        jobs = self.db.get_all_sync_jobs()
        result = []
        
        for job in jobs:
            # Calculate next sync time if cron is set
            next_sync = None
            if job['cron_schedule'] and job['last_synced'] and croniter:
                try:
                    cron = croniter(job['cron_schedule'], datetime.fromisoformat(job['last_synced']))
                    next_sync = cron.get_next(datetime)
                except:
                    next_sync = None
            
            # Add job to result with additional info
            result.append({
                **job,
                'next_sync': next_sync.isoformat() if next_sync else None,
            })
        
        return result
