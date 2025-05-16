"""
Database handler for BardKeeper using TinyDB
"""

import os
from datetime import datetime
from pathlib import Path
from tinydb import TinyDB, Query

DEFAULT_DB_PATH = os.path.expanduser("~/.bardkeeper/database.json")


class BardkeeperDB:
    """Database management class for BardKeeper"""
    
    def __init__(self, db_path=None):
        """Initialize the database"""
        self.db_path = db_path or DEFAULT_DB_PATH
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize TinyDB
        self.db = TinyDB(self.db_path)
        self.sync_jobs = self.db.table('sync_jobs')
        self.config = self.db.table('config')
        
        # Initialize default config if not exists
        if not self.config.all():
            self.config.insert({
                'db_path': self.db_path,
                'compression_command': 'tar -czf',
                'extraction_command': 'tar -xzf',
                'cache_enabled': False,
                'cache_dir': os.path.expanduser("~/.bardkeeper/cache")
            })
    
    def add_sync_job(self, name, host, username, remote_path, local_path, 
                    use_compression=False, cron_schedule=None, track_progress=False):
        """Add a new sync job to the database"""
        Job = Query()
        
        # Check if job with this name already exists
        if self.sync_jobs.search(Job.name == name):
            raise ValueError(f"A sync job with name '{name}' already exists")
        
        # Expand local path
        local_path = os.path.expanduser(local_path)
        
        # If the local_path doesn't include the remote directory name, append it
        remote_basename = os.path.basename(os.path.normpath(remote_path))
        if not local_path.endswith(remote_basename):
            local_path = os.path.join(local_path, remote_basename)
        
        # Create new job
        job = {
            'name': name,
            'host': host,
            'username': username,
            'remote_path': remote_path,
            'local_path': local_path,
            'use_compression': use_compression,
            'cron_schedule': cron_schedule,
            'track_progress': track_progress,
            'last_synced': None,
            'sync_status': 'never_run'
        }
        
        self.sync_jobs.insert(job)
        return job
    
    def get_sync_job(self, name):
        """Get a sync job by name"""
        Job = Query()
        jobs = self.sync_jobs.search(Job.name == name)
        return jobs[0] if jobs else None
    
    def get_all_sync_jobs(self):
        """Get all sync jobs"""
        return self.sync_jobs.all()
    
    def update_sync_job(self, name, **kwargs):
        """Update a sync job with new values"""
        Job = Query()
        
        # If updating local_path, expand the path and handle remote basename
        if 'local_path' in kwargs:
            local_path = os.path.expanduser(kwargs['local_path'])
            
            # Get the current job to access remote_path if needed
            current_job = self.get_sync_job(name)
            if current_job:
                # If remote_path is being updated, use that instead
                remote_path = kwargs.get('remote_path', current_job['remote_path'])
                remote_basename = os.path.basename(os.path.normpath(remote_path))
                
                # If the local_path doesn't include the remote basename, append it
                if not local_path.endswith(remote_basename):
                    local_path = os.path.join(local_path, remote_basename)
            
            kwargs['local_path'] = local_path
        
        # If updating remote_path, may need to update local_path to match
        if 'remote_path' in kwargs and 'local_path' not in kwargs:
            current_job = self.get_sync_job(name)
            if current_job:
                old_remote_basename = os.path.basename(os.path.normpath(current_job['remote_path']))
                new_remote_basename = os.path.basename(os.path.normpath(kwargs['remote_path']))
                
                # If basenames differ and old basename is at the end of local_path, update it
                if old_remote_basename != new_remote_basename and current_job['local_path'].endswith(old_remote_basename):
                    local_path = current_job['local_path']
                    parent_dir = os.path.dirname(local_path)
                    new_local_path = os.path.join(parent_dir, new_remote_basename)
                    kwargs['local_path'] = new_local_path
        
        self.sync_jobs.update(kwargs, Job.name == name)
        return self.get_sync_job(name)
    
    def remove_sync_job(self, name):
        """Remove a sync job"""
        Job = Query()
        return bool(self.sync_jobs.remove(Job.name == name))
    
    def update_last_synced(self, name, timestamp=None):
        """Update the last_synced field of a job"""
        timestamp = timestamp or datetime.now().isoformat()
        Job = Query()
        self.sync_jobs.update({'last_synced': timestamp, 'sync_status': 'completed'}, Job.name == name)
    
    def update_sync_status(self, name, status):
        """Update the sync_status field of a job"""
        Job = Query()
        self.sync_jobs.update({'sync_status': status}, Job.name == name)
    
    def get_config(self, key=None):
        """Get configuration value(s)"""
        config = self.config.all()[0]
        return config.get(key) if key else config
    
    def update_config(self, **kwargs):
        """Update configuration values"""
        self.config.update(kwargs)
