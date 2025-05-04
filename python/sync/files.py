"""
Module for file synchronization between environments in wp_chariot

This module provides functions to synchronize files between
a remote server and the local environment using rsync.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from config_yaml import get_yaml_config
from utils.ssh import SSHClient, run_rsync
from utils.filesystem import ensure_dir_exists, create_backup

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
        
        # Make sure remote paths end with /
        if not self.remote_path.endswith("/"):
            self.remote_path += "/"
            
        # Load exclusions
        self.exclusions = self.config.get_exclusions()
        
        # Load protected files
        self.protected_files = self.config.get_protected_files()
        
    def _prepare_paths(self, direction: str) -> Tuple[str, str]:
        """
        Prepares source and destination paths according to the direction
        
        Args:
            direction: Synchronization direction ("from-remote" or "to-remote")
            
        Returns:
            Tuple[str, str]: Source and destination paths
        """
        if direction == "from-remote":
            # From remote to local
            source = f"{self.remote_host}:{self.remote_path}"
            dest = str(self.local_path)
        else:
            # From local to remote
            source = str(self.local_path)
            dest = f"{self.remote_host}:{self.remote_path}"
            
        return source, dest
        
    def check_remote_connection(self) -> bool:
        """
        Verifies the connection to the remote server
        
        Returns:
            bool: True if connection is successful, False otherwise
        """
        print(f"🔄 Verifying connection with remote server: {self.remote_host}")
        
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                return False
                
            # Verify access to remote path
            cmd = f"test -d {self.remote_path} && echo 'OK' || echo 'NOT_FOUND'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error verifying remote path: {stderr}")
                return False
                
            if "OK" not in stdout:
                print(f"❌ Remote path does not exist: {self.remote_path}")
                return False
                
            print(f"✅ Connection verified successfully")
            return True
            
    def diff(self, dry_run: bool = True) -> bool:
        """
        Shows the differences between the remote server and local environment
        
        Args:
            dry_run: If True, no real changes are made
            
        Returns:
            bool: True if synchronization was successful, False otherwise
        """
        print(f"🔍 Comparing files between remote server and local environment...")
        
        # Verify connection
        if not self.check_remote_connection():
            return False
            
        # Prepare paths (always from remote for diff)
        source, dest = self._prepare_paths("from-remote")
        
        # Get exclusions and verify they are a valid dictionary
        exclusions = self.exclusions
        if not exclusions:
            print("ℹ️ No exclusions configured. Using default exclusions.")
            exclusions = {}
            
        # Show number of exclusions
        print(f"ℹ️ {len(exclusions)} exclusion patterns will be applied")
        
        # Rsync options to show differences
        options = [
            "-avzhnc",  # archive, verbose, compression, human-readable, dry-run, checksum
            "--itemize-changes",  # show detailed changes
            "--delete",  # delete files that don't exist in source
        ]
        
        # Run rsync in comparison mode
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=exclusions,
            dry_run=True  # Always in simulation mode for diff
        )
        
        return success
        
    def sync(self, direction: str = "from-remote", dry_run: bool = False) -> bool:
        """
        Synchronizes files between the remote server and local environment
        
        Args:
            direction: Synchronization direction ("from-remote" or "to-remote")
            dry_run: If True, no real changes are made
            
        Returns:
            bool: True if synchronization was successful, False otherwise
        """
        if direction == "from-remote":
            print(f"📥 Synchronizing files from remote server to local environment...")
        else:
            print(f"📤 Synchronizing files from local environment to remote server...")
            
            # Check if production safety is enabled
            if self.config.get("security", "production_safety") == "enabled":
                print("⚠️ WARNING: Production safety is enabled.")
                print("   This operation would modify files in PRODUCTION.")
                
                # Request explicit confirmation
                confirm = input("   Are you COMPLETELY SURE you want to continue? (type 'yes' to confirm): ")
                
                if confirm.lower() != "yes":
                    print("❌ Operation cancelled for safety.")
                    return False
                    
                print("⚡ Confirmation received. Proceeding with operation...")
                print("")
        
        # Verify connection
        if not self.check_remote_connection():
            return False
            
        # Prepare paths
        source, dest = self._prepare_paths(direction)
        
        # Rsync options
        options = [
            "-avzh",  # archive, verbose, compression, human-readable
            "--progress",  # show progress
            "--delete",  # delete files that don't exist in source
        ]
        
        # If simulation, add option
        if dry_run:
            print("🔄 Running in simulation mode (no changes will be made)")
            
        # Run rsync
        success, output = run_rsync(
            source=source,
            dest=dest,
            options=options,
            exclusions=self.exclusions,
            dry_run=dry_run
        )
        
        # If synchronization was from remote to local, fix local config if necessary
        if success and direction == "from-remote" and not dry_run:
            self._fix_local_config()
            
        return success
        
    def _fix_local_config(self):
        """
        Fixes local configuration after syncing from remote
        """
        # Adjust wp-config.php for DDEV if necessary
        wp_config_path = self.local_path / "wp-config.php"
        wp_config_ddev_path = self.local_path / "wp-config-ddev.php"
        
        if wp_config_path.exists() and wp_config_ddev_path.exists():
            print("🔍 Verifying that wp-config.php includes DDEV configuration...")
            
            # Read the file
            with open(wp_config_path, 'r') as f:
                content = f.read()
                
            # Check if it already includes DDEV configuration
            if "wp-config-ddev.php" not in content:
                print("⚙️ Fixing wp-config.php to include DDEV configuration...")
                
                # Create a backup
                create_backup(wp_config_path)
                
                # Code to include DDEV
                ddev_config = (
                    "<?php\n"
                    "// DDEV configuration\n"
                    "$ddev_settings = dirname(__FILE__) . '/wp-config-ddev.php';\n"
                    "if (is_readable($ddev_settings) && !defined('DB_USER')) {\n"
                    "  require_once($ddev_settings);\n"
                    "}\n\n"
                )
                
                # Add code to the beginning of the file
                with open(wp_config_path, 'w') as f:
                    f.write(ddev_config + content)
                    
                print("✅ wp-config.php updated for DDEV.")
            else:
                print("✅ wp-config.php already includes DDEV configuration.")
                
# Class for diff commands (more specific than general synchronization)
class DiffCommand:
    """
    Class for specific difference commands
    """
    
    def __init__(self):
        """
        Initializes the diff object
        """
        self.synchronizer = FileSynchronizer()
        
    def show_diff(self):
        """
        Shows the differences between the remote server and local environment
        """
        return self.synchronizer.diff(dry_run=True)
        
# Module-level functions to facilitate use from other modules
def sync_files(direction: str = "from-remote", dry_run: bool = False) -> bool:
    """
    Synchronizes files between environments
    
    Args:
        direction: Synchronization direction ("from-remote" or "to-remote")
        dry_run: If True, no real changes are made
        
    Returns:
        bool: True if synchronization was successful, False otherwise
    """
    synchronizer = FileSynchronizer()
    return synchronizer.sync(direction=direction, dry_run=dry_run)
    
def show_diff() -> bool:
    """
    Shows the differences between the remote server and local environment
    
    Returns:
        bool: True if operation was successful, False otherwise
    """
    diff_cmd = DiffCommand()
    return diff_cmd.show_diff() 