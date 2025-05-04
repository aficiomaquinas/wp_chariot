"""
File synchronization module between environments

This module provides functions to synchronize files between
a remote server and the local environment using rsync.
"""

import os
import sys
import tempfile
import shutil
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, Set

from config_yaml import get_yaml_config
from utils.ssh import SSHClient, run_rsync
from utils.filesystem import ensure_dir_exists, create_backup
from commands.backup import create_full_backup

class FileSynchronizer:
    """
    Class for synchronizing files between environments
    """
    
    def __init__(self):
        """
        Initializes the file synchronizer
        """
        self.config = get_yaml_config()
        
        # Load configuration
        self.remote_host = self.config.get("ssh", "remote_host")
        self.remote_path = self.config.get("ssh", "remote_path")
        self.local_path = Path(self.config.get("ssh", "local_path"))
        
        # Ensure remote paths end with a single / 
        self.remote_path = self.remote_path.rstrip('/') + '/'
            
        # Load exclusions
        self.exclusions = self.config.get_exclusions()
        
        # Load protected files
        self.protected_files = self.config.get_protected_files()
        
        # Load memory limit for WP-CLI
        self.wp_memory_limit = self.config.get_wp_memory_limit()
        
    def _load_patched_files(self) -> List[str]:
        """
        Loads the list of patched files and their backups from the lock file
        
        Returns:
            List[str]: List of patched files and their backups
        """
        try:
            from commands.patch import PatchManager
            
            # Create PatchManager instance to access its methods
            patch_manager = PatchManager()
            
            # Use the _load_patched_files method from PatchManager that returns tuples (file, backup)
            patched_tuples = patch_manager._load_patched_files()
            
            # Convert tuples to a flat list of files for exclusion
            patched_files = []
            for file_path, backup_path in patched_tuples:
                if file_path:
                    patched_files.append(file_path)
                if backup_path:
                    patched_files.append(backup_path)
            
            return patched_files
            
        except Exception as e:
            print(f"⚠️ Error loading patch file: {str(e)}")
            return []
        
    def _prepare_paths(self, direction: str) -> Tuple[str, str]:
        """
        Prepares the source and destination paths according to the direction
        
        Args:
            direction: Direction of synchronization ("from-remote" or "to-remote")
            
        Returns:
            Tuple[str, str]: Source and destination paths
        """
        # Ensure the remote path doesn't end with multiple /
        remote_path = self.remote_path.rstrip('/')
        
        if direction == "from-remote":
            # From remote to local
            source = f"{self.remote_host}:{remote_path}"
            dest = str(self.local_path)
        else:
            # From local to remote
            source = str(self.local_path)
            dest = f"{self.remote_host}:{remote_path}"
            
        return source, dest
        
    def check_remote_connection(self) -> bool:
        """
        Verifies the connection with the remote server
        
        Returns:
            bool: True if the connection is successful, False otherwise
        """
        print(f"🔄 Checking connection with remote server: {self.remote_host}")
        
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                return False
                
            # Verify access to remote path
            cmd = f"test -d {self.remote_path} && echo 'OK' || echo 'NOT_FOUND'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error checking remote path: {stderr}")
                return False
                
            if "OK" not in stdout:
                print(f"❌ Remote path does not exist: {self.remote_path}")
                return False
                
            print(f"✅ Connection verified successfully")
            return True
            
    def diff(self, dry_run: bool = True, show_all: bool = False, verbose: bool = False, only_patches: bool = False) -> bool:
        """
        Shows the differences between the remote server and the local environment.
        This method is always read-only and never makes changes,
        regardless of the value of the dry_run parameter.
        
        Args:
            dry_run: This parameter is kept for compatibility but is always ignored
            show_all: If True, shows all files without limit
            verbose: If True, shows detailed information
            only_patches: If True, shows only information related to patches
            
        Returns:
            bool: True if the operation was successful, False otherwise
        """
        if not only_patches:
            print(f"🔍 Comparing files between remote server and local environment...")
        
        # Verify connection
        if not self.check_remote_connection():
            return False
            
        # Prepare paths (always from remote for diff)
        source, dest = self._prepare_paths("from-remote")
        
        # Get exclusions and verify they are a valid dictionary
        exclusions = self.exclusions.copy() if self.exclusions else {}
        if not exclusions:
            if not only_patches:
                print("ℹ️ No exclusions configured.")
        
        # Add protected files to exclusions so they don't appear in the diff
        if self.protected_files:
            if not only_patches:
                print(f"🛡️ Protecting {len(self.protected_files)} files during comparison")
            for i, file_pattern in enumerate(self.protected_files):
                exclusions[f"protected_{i}"] = file_pattern
        
        # Show number of exclusions
        if not only_patches:
            print(f"ℹ️ {len(exclusions)} exclusion patterns will be applied")
            
            # In verbose mode, show exclusion patterns
            if verbose:
                print("📋 Applying exclusion patterns:")
                for key, pattern in sorted(exclusions.items()):
                    print(f"   - {key}: {pattern}")
        
        # Rsync options to show differences
        options = [
            "-avzhnc",  # archive, verbose, compression, human-readable, dry-run, checksum
            "--itemize-changes",  # show detailed changes
            "--delete",  # delete files that don't exist in source
        ]
        
        # Run rsync in comparison mode
        # Always use dry_run=True because this method is only to show differences
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=exclusions,
            dry_run=True,  # Always in simulation mode for diff
            capture_output=True,  # Capture output to process it ourselves
            verbose=verbose  # Only show raw output in verbose mode
        )
        
        if not success:
            print("❌ Error showing differences")
            return False
            
        # If we only want patch information, we don't need to continue with normal analysis
        if only_patches:
            return self._analyze_patches(output, show_all, verbose)
        
        # Parse rsync output
        files_new = []       # New files in the server (>f....)
        files_modified = []  # Modified files (.s....)
        files_deleted = []   # Files that would be deleted (*deleting)
        files_directories = [] # Directories (.d....)
        
        # File limit to show per category
        limit = 0 if show_all else 100
        
        # Analyze each line of output
        for line in output.split('\n'):
            line = line.strip()
            
            # Ignore empty lines or without file information
            if not line or line.startswith('sent ') or line.startswith('receiving ') or line.startswith('total size'):
                continue
                
            # Extract change pattern and file name
            if line.startswith('>'):
                # New file in server
                pattern = line[:10]
                file = line[10:].strip()
                files_new.append((pattern, file))
            elif line.startswith('*deleting'):
                # File present locally but not in server
                file = line[10:].strip()
                files_deleted.append(('*deleting', file))
            elif line.startswith('.d'):
                # Directory
                pattern = line[:10]
                file = line[10:].strip()
                files_directories.append((pattern, file))
            elif '.s' in line[:5]:
                # Modified file
                pattern = line[:10]
                file = line[10:].strip()
                files_modified.append((pattern, file))
        
        # Create function to print files with limit
        def print_files(files, title, symbol, limit_count=limit):
            if not files:
                return
                
            count = len(files)
            print(f"\n{symbol} {title} ({count} items):")
            
            # Sort files by name
            files_sorted = sorted(files, key=lambda x: x[1].lower())
            
            # Show files up to limit or all if no limit
            for i, (pattern, file) in enumerate(files_sorted):
                if limit_count > 0 and i >= limit_count:
                    print(f"... and {count - limit_count} more files")
                    break
                
                # Process rsync pattern to determine file type
                file_type = "?"
                if pattern[1] == 'f':
                    file_type = "📄"  # Regular file
                elif pattern[1] == 'd':
                    file_type = "📁"  # Directory
                elif pattern[1] == 'L':
                    file_type = "🔗"  # Symlink
                    
                print(f"  {file_type} {file}")
        
        # Print different categories of changes
        print_files(files_new, "New files in server (would be downloaded)", "📥")
        print_files(files_modified, "Modified files (would be updated)", "🔄")
        print_files(files_deleted, "Files to delete (exists locally but not in server)", "🗑️")
        
        # Analyze if there are patches affected by the synchronization
        return self._analyze_patches(output, show_all, verbose, files_modified, files_deleted)
        
    def _analyze_patches(self, output: str = "", show_all: bool = False, verbose: bool = False, files_modified: list = None, files_deleted: list = None) -> bool:
        """
        Analyzes if the synchronization would affect registered patches
        
        Args:
            output: Rsync command output
            show_all: If True, shows all affected files
            verbose: If True, shows additional information
            files_modified: List of modified files
            files_deleted: List of files that would be deleted
            
        Returns:
            bool: True if operation can continue safely, False otherwise
        """
        # Try to load patched files from patch manager
        try:
            from commands.patch import PatchManager
            
            # Create patch manager instance to load patches
            patch_manager = PatchManager()
            
            # Check if there are patches
            if not patch_manager.lock_data.get("patches", {}):
                return True  # No patches to analyze
            
            # First collect all patched files
            patched_files = []
            patched_applied = []
            
            for file_path, info in patch_manager.lock_data.get("patches", {}).items():
                patched_files.append(file_path)
                if info.get("applied_date"):
                    patched_applied.append(file_path)
            
            # Check if we got a complete file list
            if files_modified is None or files_deleted is None:
                # We need to analyze the rsync output to find affected files
                files_modified = []
                files_deleted = []
                
                # Parse rsync output to get modified and deleted files
                for line in output.split('\n'):
                    line = line.strip()
                    
                    # Skip lines without file info
                    if not line or line.startswith('sent ') or line.startswith('receiving ') or line.startswith('total size'):
                        continue
                    
                    # Find modified files
                    if '.s' in line[:5]:
                        pattern = line[:10]
                        file = line[10:].strip()
                        files_modified.append((pattern, file))
                    
                    # Find deleted files
                    elif line.startswith('*deleting'):
                        file = line[10:].strip()
                        files_deleted.append(('*deleting', file))
            
            # Format files modified and deleted as plain list if needed
            if files_modified and isinstance(files_modified[0], tuple):
                files_modified_list = [file for _, file in files_modified]
            else:
                files_modified_list = files_modified
                
            if files_deleted and isinstance(files_deleted[0], tuple):
                files_deleted_list = [file for _, file in files_deleted]
            else:
                files_deleted_list = files_deleted
            
            # Find patched files affected by sync
            affected_modified = []
            affected_deleted = []
            
            for patch_file in patched_files:
                # Check if in modified files
                for mod_file in files_modified_list:
                    if patch_file == mod_file:
                        affected_modified.append(patch_file)
                
                # Check if in deleted files
                for del_file in files_deleted_list:
                    if patch_file == del_file:
                        affected_deleted.append(patch_file)
            
            # If we found no affected files
            if not affected_modified and not affected_deleted:
                # Only show message in verbose mode
                if verbose:
                    print("\n✅ No patched files would be affected by synchronization")
                return True
            
            # Show alert about affected patches
            print("\n⚠️ WARNING: This synchronization would affect patches:")
            
            # Show affected files
            if affected_modified:
                print(f"\n🔄 Modified patched files ({len(affected_modified)}):")
                for file in affected_modified:
                    # Get patch info
                    info = patch_manager.lock_data.get("patches", {}).get(file, {})
                    description = info.get("description", "No description")
                    status = "Applied" if file in patched_applied else "Registered"
                    print(f"  📄 {file}")
                    print(f"     • Description: {description}")
                    print(f"     • Status: {status}")
            
            if affected_deleted:
                print(f"\n🗑️ Deleted patched files ({len(affected_deleted)}):")
                for file in affected_deleted:
                    # Get patch info
                    info = patch_manager.lock_data.get("patches", {}).get(file, {})
                    description = info.get("description", "No description")
                    status = "Applied" if file in patched_applied else "Registered"
                    print(f"  📄 {file}")
                    print(f"     • Description: {description}")
                    print(f"     • Status: {status}")
            
            # Show recommendations
            print("\n⚠️ RECOMMENDATIONS:")
            print("   - If continuing with synchronization, patches would be overwritten")
            print("   - Use 'patch --list' to view details of all patches")
            print("   - After synchronization, apply patches again with 'patch-commit'")
            
            return True
            
        except Exception as e:
            if verbose:
                print(f"\n⚠️ Error analyzing patches: {str(e)}")
            return True
        
    def _check_protected_files(self, direction: str) -> bool:
        """
        Verifies if protected files would be affected by synchronization
        
        Args:
            direction: Direction of synchronization ("from-remote" or "to-remote")
            
        Returns:
            bool: True if it's safe to continue, False otherwise
        """
        # Get protected files list
        if not self.protected_files:
            return True
            
        print(f"🛡️ Checking {len(self.protected_files)} protected files...")
        
        # Prepare command to check file existence
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                print("❌ Error establishing SSH connection")
                return False
                
            # Build command to check all files
            check_script = []
            for pattern in self.protected_files:
                if pattern.startswith('/'):
                    # Absolute path, check directly
                    check_script.append(f"if [ -e \"{pattern}\" ]; then echo \"EXISTS {pattern}\"; fi")
                else:
                    # Relative path, build full path
                    check_script.append(f"if [ -e \"{self.remote_path}{pattern}\" ]; then echo \"EXISTS {pattern}\"; fi")
            
            # Execute remote check
            cmd = "; ".join(check_script)
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error checking protected files: {stderr}")
                return False
            
            # Process results
            existing_files = []
            for line in stdout.split('\n'):
                if line.startswith('EXISTS '):
                    file_path = line[7:]
                    existing_files.append(file_path)
            
            # Show results
            if existing_files:
                if direction == "from-remote":
                    print(f"🛡️ Found {len(existing_files)} protected files on the server that will be ignored:")
                else:  # to-remote
                    print(f"🛡️ Found {len(existing_files)} protected files on the server that will not be overwritten:")
                
                for file in existing_files:
                    print(f"   - {file}")
            else:
                print("✅ No protected files found in the destination")
            
            return True
        
    def _clean_excluded_files(self, direction: str) -> bool:
        """
        Cleans (deletes) excluded files that may have been downloaded in previous synchronizations
        
        Args:
            direction: Direction of synchronization ("from-remote" or "to-remote")
            
        Returns:
            bool: True if the operation was successful, False otherwise
        """
        # This only makes sense for from-remote direction and with exclusions
        if direction != "from-remote" or not self.exclusions:
            return True
            
        print(f"🧹 Cleaning excluded files in local environment...")
        
        excluded_files = []
        excluded_dirs = []
        
        # Process exclusions
        for pattern in self.exclusions.values():
            # Skip if it's a pattern that doesn't refer to a specific file
            if '*' in pattern or '?' in pattern:
                continue
                
            # Check if it's a directory or file
            local_path = self.local_path / pattern
            if os.path.isdir(local_path):
                excluded_dirs.append(pattern)
            elif os.path.isfile(local_path):
                excluded_files.append(pattern)
        
        # If we found no files to clean
        if not excluded_files and not excluded_dirs:
            print("✅ No excluded files need to be cleaned")
            return True
        
        # Show what we will clean
        if excluded_files:
            print(f"🗑️ Found {len(excluded_files)} excluded files to remove:")
            for file in excluded_files:
                print(f"   - {file}")
                # Delete the file
                try:
                    local_path = self.local_path / file
                    if os.path.isfile(local_path):
                        os.unlink(local_path)
                except Exception as e:
                    print(f"   ⚠️ Error deleting file {file}: {str(e)}")
        
        if excluded_dirs:
            print(f"🗑️ Found {len(excluded_dirs)} excluded directories to remove:")
            for directory in excluded_dirs:
                print(f"   - {directory}")
                # Delete the directory recursively
                try:
                    local_path = self.local_path / directory
                    if os.path.isdir(local_path):
                        shutil.rmtree(local_path)
                except Exception as e:
                    print(f"   ⚠️ Error deleting directory {directory}: {str(e)}")
        
        print("✅ Finished cleaning excluded files")
        return True
        
    def sync(self, direction: str = "from-remote", dry_run: bool = False, clean: bool = True) -> bool:
        """
        Synchronizes files between environments
        
        Args:
            direction: Direction of synchronization ("from-remote" or "to-remote")
            dry_run: If True, only simulates synchronization without making changes
            clean: If True, cleans excluded files after synchronization
            
        Returns:
            bool: True if the synchronization was successful, False otherwise
        """
        if direction == "from-remote":
            print(f"🔄 Synchronizing files from remote server to local environment...")
            print(f"   Source: {self.remote_host}:{self.remote_path}")
            print(f"   Destination: {self.local_path}")
        else:
            print(f"🔄 Synchronizing files from local environment to remote server...")
            print(f"   Source: {self.local_path}")
            print(f"   Destination: {self.remote_host}:{self.remote_path}")
        
        # Verify connection
        if not self.check_remote_connection():
            return False
        
        # Prepare source and destination paths
        source, dest = self._prepare_paths(direction)
        
        # Get exclusions and verify they are a valid dictionary
        exclusions = self.exclusions.copy() if self.exclusions else {}
        if not exclusions:
            print("ℹ️ No exclusions configured. All files in the source will be synchronized.")
        
        # Process patch exclusions
        try:
            # Check if we need to exclude patched files according to configuration
            exclusions_mode = self.config.get("patches", "exclusions_mode", default="local-only")
            
            if (direction == "from-remote" and exclusions_mode in ["local-only", "both-ways"]) or \
               (direction == "to-remote" and exclusions_mode in ["remote-only", "both-ways"]):
                # Load patched files
                patched_files = self._load_patched_files()
                
                # Add each patched file to exclusions
                for i, patched_file in enumerate(patched_files):
                    if patched_file:
                        exclusions[f"patched_file_{i}"] = patched_file
                
                if patched_files:
                    print(f"ℹ️ Excluding {len(patched_files)} patched files as configured")
        except Exception as e:
            print(f"⚠️ Error processing patch exclusions: {str(e)}")
            print("   Continuing without patch exclusions")
            
        # Add protected files to exclusions
        if self.protected_files:
            print(f"🛡️ Adding {len(self.protected_files)} protected files to exclusions")
            for i, file_pattern in enumerate(self.protected_files):
                exclusions[f"protected_{i}"] = file_pattern
                
            # Verify protected files in destination if not dry-run
            if not dry_run:
                self._check_protected_files(direction)
        
        # Show number of exclusions
        print(f"ℹ️ {len(exclusions)} exclusion patterns will be applied")
        
        # Options for rsync
        options = [
            "-avzh",  # archive, verbose, compression, human-readable
            "--delete",  # delete files that don't exist in source
        ]
        
        # Add --dry-run if we're simulating
        if dry_run:
            options.append("--dry-run")
            print("🔍 Dry-run mode: No real changes will be made")
        
        # Execute rsync
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=exclusions,
            dry_run=dry_run,
            capture_output=False  # Let it print directly to the console
        )
        
        if not success:
            print("❌ Error during synchronization")
            return False
        
        # Clean excluded files if necessary
        if clean and not dry_run and direction == "from-remote":
            self._clean_excluded_files(direction)
            
        # Fix local configuration if needed after from-remote sync
        if not dry_run and direction == "from-remote":
            self._fix_local_config()
            
        if dry_run:
            print("🔍 Dry-run complete. No changes were made.")
        else:
            print("✅ Synchronization completed successfully.")
            
        return True
    
    def _fix_local_config(self):
        """
        Fixes local configuration after synchronization from remote
        
        This is needed when configuration elements in remote environment
        differ from local and need to be adjusted after syncing.
        """
        print("🔧 Checking if local configuration needs adjustments...")
        
        # Check media URL
        media_config = self.config.config.get("media", {})
        if media_config:
            # Get URLs
            remote_url = self.config.get("urls", "remote", default="")
            local_url = self.config.get("urls", "local", default="")
            
            if remote_url and local_url and remote_url != local_url:
                print("ℹ️ URLs are different, checking if media configuration needs update")
                
                # Check if we need to configure local media
                try:
                    from commands.media import configure_media_path
                    
                    # Configure media
                    print("🔄 Configuring local media path...")
                    configure_media_path(
                        media_url=None,  # Force to get value from config.yaml
                        expert_mode=media_config.get("expert_mode", False),
                        media_path=None,  # Force to get value from config.yaml
                        remote=False,
                        verbose=False
                    )
                except Exception as e:
                    print(f"⚠️ Error configuring media: {str(e)}")
                    print("   You may need to run 'media-path' manually")
        else:
            print("ℹ️ No media configuration found, skipping")
            
        # Clean cache
        try:
            from utils.wp_cli import flush_cache
            
            print("🧹 Cleaning local cache...")
            flush_cache(
                path=self.local_path,
                remote=False,
                use_ddev=True
            )
        except Exception as e:
            print(f"⚠️ Error cleaning cache: {str(e)}")
            print("   You may need to run 'wp cache flush' manually")
            
        print("✅ Local configuration adjustments completed")

def sync_files(direction: str = "from-remote", dry_run: bool = False, clean: bool = True, skip_full_backup: bool = False) -> bool:
    """
    Synchronizes files between environments
    
    Args:
        direction: Direction of synchronization ("from-remote" or "to-remote")
        dry_run: If True, only simulates synchronization without making changes
        clean: If True, cleans excluded files after synchronization
        skip_full_backup: If True, skips creating a full backup before synchronizing from remote
        
    Returns:
        bool: True if the synchronization was successful, False otherwise
    """
    # Create backup if going from-remote and not in dry-run mode or explicitly skipped
    if direction == "from-remote" and not dry_run and not skip_full_backup:
        print("📦 Creating full backup before synchronizing files...")
        
        # Create a full backup (calls create_backup with all=True)
        success, backup_path = create_full_backup()
        
        if not success:
            print("⚠️ Failed to create backup. Continuing with synchronization anyway.")
            # Don't abort on backup failure, continue with sync
        else:
            print(f"✅ Backup created: {backup_path}")
            
    # Handle the old pattern where sync_files was monkey-patched by a security check
    # that skipped the backup. We no longer need this pattern, but keep it for compatibility.
    # Now we use the skip_full_backup parameter instead.
    try:
        # Create synchronizer
        synchronizer = FileSynchronizer()
        
        # Run synchronization
        return synchronizer.sync(direction=direction, dry_run=dry_run, clean=clean)
    except Exception as e:
        import traceback
        print(f"❌ Error during synchronization: {str(e)}")
        traceback.print_exc()
        return False
        
    # For backwards compatibility in case something tries to monkey-patch sync_files
    def sync_without_backup(*args, **kwargs):
        # Save original module
        import sys
        original_module = sys.modules[__name__]
        
        # Store original function
        original_sync = original_module.sync_files
        
        try:
            # Create synchronizer
            synchronizer = FileSynchronizer()
            
            # Run synchronization
            return synchronizer.sync(*args, **kwargs)
        finally:
            # Restore original function
            original_module.sync_files = original_sync
    
    # For backwards compatibility
    sync_files.no_backup = sync_without_backup
    
    return sync_without_backup(direction, dry_run, clean) 