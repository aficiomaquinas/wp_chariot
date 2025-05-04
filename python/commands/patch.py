"""
Module for applying patches to third-party plugins

This module provides functions to apply patches from local plugins
to the remote server, with tracking through a lock file.
"""

import os
import sys
import tempfile
import shutil
import difflib
import json
import hashlib
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, Set

from config_yaml import get_yaml_config, get_nested
from utils.ssh import SSHClient
from utils.filesystem import ensure_dir_exists, create_backup
from utils.wp_cli import get_item_version_from_path

# Import functions and constants from patch_utils
from .patch_utils import (
    calculate_checksum, 
    get_remote_file_checksum,
    get_remote_file_version,
    get_local_file_version,
    show_file_diff,
    determine_patch_status,
    get_site_specific_lock_file,
    load_lock_file,
    save_lock_file,
    PATCH_STATUS_PENDING,
    PATCH_STATUS_APPLIED,
    PATCH_STATUS_ORPHANED,
    PATCH_STATUS_OBSOLETED,
    PATCH_STATUS_MISMATCHED,
    PATCH_STATUS_STALE,
    PATCH_STATUS_LABELS
)

class PatchManager:
    """
    Class for managing patch application
    
    Notes:
    - Patches are managed by site, with a specific lock file for each site.
    - If a general `patches.lock.json` file exists, it will be used as a starting point
      for sites that don't have a specific file.
    - Site-specific lock files are named as `patches-{sitename}.lock.json`.
    """
    
    def __init__(self):
        """
        Initializes the patch manager
        """
        self.config = get_yaml_config(verbose=False)
        
        # Load configuration following "fail fast" principle
        try:
            # Get required SSH values
            if "ssh" not in self.config.config:
                raise ValueError("Missing 'ssh' section in configuration")
            
            self.remote_host = self.config.get_strict("ssh", "remote_host")
            self.remote_path = self.config.get_strict("ssh", "remote_path")
            self.local_path = Path(self.config.get_strict("ssh", "local_path"))
            
            # Ensure remote paths end with a single /
            self.remote_path = self.remote_path.rstrip('/') + '/'
            
            # Load security configuration
            self.production_safety = get_nested(self.config, "security", "production_safety") == "enabled"
            
            # Determine current site for site-specific lock file
            self.current_site = self.config.current_site
            
            # Generate lock file name using utility function
            self.lock_file = get_site_specific_lock_file(self.current_site)
            
            # Load lock file
            self.lock_data = load_lock_file(self.lock_file)
            
            # Load protected files
            self.protected_files = self.config.get_protected_files()
            
            # Load memory limit for WP-CLI - no default values (fail fast)
            self.wp_memory_limit = self.config.get_wp_memory_limit()
            
            # Initialize patch list
            self.patches = []
            
        except ValueError as e:
            print(f"❌ Configuration error: {str(e)}")
            print("   The system cannot continue without the required configuration.")
            raise
        
    def save_lock_file(self):
        """
        Saves the lock file data
        """
        save_lock_file(self.lock_file, self.lock_data, self.current_site)
    
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
                print(f"❌ Could not access remote server: {self.remote_host}")
                if stderr:
                    print(f"   Error: {stderr}")
                return False
                
            if "NOT_FOUND" in stdout:
                print(f"❌ Remote path does not exist: {self.remote_path}")
                return False
                
            print(f"✅ Successful connection with remote server")
            return True
    
    def calculate_checksum(self, file_path: Path) -> str:
        """
        Calculates the MD5 checksum of a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            str: MD5 checksum of the file
        """
        return calculate_checksum(file_path)
        
    def list_patches(self, verbose: bool = False) -> None:
        """
        Shows the list of registered patches with detailed status
        
        Args:
            verbose: If True, shows additional information
        """
        if not self.lock_data.get("patches", {}):
            print("ℹ️ There are no registered patches.")
            print("   You can add patches with the 'patch --add path/to/file' command")
            return
            
        print("🔍 Registered patches:")
        
        # Verify SSH connection for more precise states
        ssh = None
        connected = False
        try:
            connected = self.check_remote_connection()
            if connected:
                ssh = SSHClient(self.remote_host)
                ssh.connect()
                print() # Blank line to separate connection from results
        except Exception as e:
            print(f"⚠️ Connection error: {str(e)}")
            connected = False
            
        try:
            # Process each registered patch
            php_memory_error_shown = False
            
            for file_path, info in self.lock_data.get("patches", {}).items():
                # Determine plugin or theme name
                if '/plugins/' in file_path:
                    plugin_name = file_path.split('/')[2]
                    item_type = "Plugin"
                elif '/themes/' in file_path:
                    plugin_name = file_path.split('/')[2]
                    item_type = "Theme"
                elif '/mu-plugins/' in file_path:
                    plugin_name = os.path.basename(file_path)
                    item_type = "MU Plugin"
                else:
                    plugin_name = os.path.basename(file_path)
                    item_type = "File"
                
                description = info.get("description", "No description")
                applied_date = info.get("applied_date", "")
                local_checksum = info.get("local_checksum", "Unknown")
                original_checksum = info.get("original_checksum", "")
                local_version = info.get("local_version", "Unknown")
                remote_version = info.get("remote_version", "Unknown")
                
                # Determine patch status if connected
                status = "Unknown"
                status_code = PATCH_STATUS_PENDING  # Default
                
                if connected and ssh:
                    try:
                        status_code, status_details = self.get_patch_status(file_path, ssh)
                        status = PATCH_STATUS_LABELS.get(status_code, "Unknown status")
                    except Exception as e:
                        # Capture specific PHP memory errors
                        if "Fatal error: Allowed memory size" in str(e):
                            if not php_memory_error_shown:
                                print(f"⚠️ PHP memory error when getting some states. Use WP_CLI_PHP_ARGS to increase memory limit.")
                                php_memory_error_shown = True
                            status = "⚠️ Memory error"
                        else:
                            status = f"⚠️ Error: {str(e)}"
                elif connected:
                    status = "⚠️ Not connected"
                else:
                    # If not connected, use local information
                    if applied_date:
                        status = "✅ Applied (unverified)"
                    else:
                        status = "⏳ Pending (unverified)"
                
                # Format date if exists
                formatted_date = ""
                if applied_date:
                    try:
                        # Try to parse the date
                        applied_datetime = datetime.datetime.fromisoformat(applied_date)
                        formatted_date = applied_datetime.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        formatted_date = applied_date
                
                # Show patch information
                print(f"\n📄 {item_type}: {plugin_name}")
                print(f"   • File: {file_path}")
                print(f"   • Description: {description}")
                print(f"   • Status: {status}")
                
                # Check if there are differences between checksums indicating changes
                if original_checksum and local_checksum and original_checksum != local_checksum:
                    print(f"   • Changes: ✅ Detected (different checksums)")
                elif original_checksum and local_checksum and original_checksum == local_checksum:
                    print(f"   • Changes: ❌ Not detected (identical checksums)")
                
                if verbose:
                    print(f"   • Local version: {local_version}")
                    print(f"   • Remote version: {remote_version}")
                    if formatted_date:
                        print(f"   • Applied date: {formatted_date}")
                
        except Exception as e:
            print(f"⚠️ Error listing patches: {str(e)}")
        finally:
            # Close SSH connection
            if ssh and ssh.client:
                ssh.disconnect()

    def check_safety(self, force_dry_run: bool = False) -> Optional[bool]:
        """
        Verifies security measures to protect production environments
        
        Args:
            force_dry_run: If True, always executes in simulation mode
            
        Returns:
            Optional[bool]: True if it's safe to proceed, False if it should abort, None if force dry-run
        """
        if force_dry_run:
            print("\n⚠️ WARNING: Forced security. Executing in simulation mode.")
            return None
            
        if self.production_safety:
            print("\n⚠️ WARNING: Production protection activated in configuration.")
            print("   This operation could affect a production environment.")
            print("   To continue, disable protection in config.yaml or confirm to continue.")
            
            user_input = input("\nAre you sure you want to continue? (y/N): ")
            
            if user_input.lower() not in ["y", "yes"]:
                print("Operation canceled by user.")
                return False
                
            print("Protection temporarily disabled at user request.\n")
            
        return True
        
    def get_remote_file_checksum(self, ssh: SSHClient, remote_file: str) -> str:
        """
        Gets the checksum of a file on the remote server
        
        Args:
            ssh: Connected SSH client
            remote_file: Path to the file on the remote server
            
        Returns:
            str: MD5 checksum of the remote file
        """
        return get_remote_file_checksum(ssh, remote_file)
        
    def get_remote_file_version(self, ssh: SSHClient, file_path: str) -> str:
        """
        Gets the version of a plugin or theme from a file on the remote server
        
        Args:
            ssh: Connected SSH client
            file_path: Path to the file
            
        Returns:
            str: Version of the plugin or theme, or empty string if it cannot be determined
        """
        return get_remote_file_version(ssh, file_path, self.remote_path, self.wp_memory_limit)
        
    def get_local_file_version(self, file_path: str) -> str:
        """
        Gets the version of a plugin or theme from a local file
        
        Args:
            file_path: Relative path to the file
            
        Returns:
            str: Version of the plugin or theme, or empty string if it cannot be determined
        """
        return get_local_file_version(file_path, self.local_path)
    
    def add_patch(self, file_path: str, description: str = "") -> bool:
        """
        Registers a new patch in the lock file
        
        Correct flow:
        1. Verify that the local file exists and is modified
        2. Download the original version from the remote server
        3. Save that version as local backup
        4. Calculate checksums of both versions
        5. Register the patch with all necessary information
        
        Args:
            file_path: Relative path to the file
            description: Patch description
            
        Returns:
            bool: True if registered correctly, False otherwise
        """
        print(f"🔄 Registering patch: {file_path}")
        
        # Verify that the local file exists
        local_file = self.local_path / file_path
        if not local_file.exists():
            print(f"❌ Error: Local file does not exist: {local_file}")
            print("   You must provide a valid relative path from the project root.")
            return False
            
        # Calculate checksum of the local file (already modified)
        local_checksum = self.calculate_checksum(local_file)
        if not local_checksum:
            print(f"❌ Error: No checksum could be calculated for the local file")
            return False
            
        # Verify connection with the remote server to download the original file
        if not self.check_remote_connection():
            print("❌ Error: No connection could be established with the remote server to obtain the original file")
            return False
            
        # Get the original file from the remote server
        remote_file = f"{self.remote_path}{file_path}"
        original_checksum = ""
        backup_path = local_file.with_suffix(f"{local_file.suffix}.original.bak")
        local_backup_file = str(backup_path.relative_to(self.local_path))
        backup_checksum = ""
        remote_file_exists = False
            
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                print("❌ Error: No SSH connection could be established")
                return False
                
            # Verify if the file exists on the server
            cmd = f"test -f '{remote_file}' && echo 'EXISTS' || echo 'NOT_EXISTS'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if "EXISTS" in stdout:
                remote_file_exists = True
                
                # Get checksum of the remote file
                original_checksum = self.get_remote_file_checksum(ssh, remote_file)
                
                # Compare checksums to verify if there are changes
                if original_checksum == local_checksum:
                    print("⚠️ Warning: Local and remote files have the same checksum")
                    print("   It doesn't seem there are modifications to patch.")
                    confirm = input("   ¿Do you want to continue anyway? (y/n): ")
                    if confirm.lower() != "y":
                        print("   Operation canceled.")
                        return False
                
                # Download the original file as backup
                print(f"📥 Downloading original file from server...")
                if not ssh.download_file(remote_file, backup_path):
                    print(f"❌ Error: No file could be downloaded from the server")
                    return False
                    
                # Verify that the backup was created correctly
                if not backup_path.exists():
                    print(f"❌ Error: No backup file could be created")
                    return False
                    
                # Calculate checksum of the backup
                backup_checksum = self.calculate_checksum(backup_path)
                if not backup_checksum:
                    print(f"❌ Error: No checksum could be calculated for the backup")
                    return False
                    
                # Verify that the backup checksum matches the remote
                if backup_checksum != original_checksum:
                    print(f"⚠️ Warning: Backup checksum does not match remote")
                    print(f"   Remote checksum: {original_checksum}")
                    print(f"   Backup checksum: {backup_checksum}")
                    confirm = input("   ¿Do you want to continue anyway? (y/n): ")
                    if confirm.lower() != "y":
                        print("   Operation canceled.")
                        return False
                
                print(f"✅ Original file saved as: {backup_path.name}")
            else:
                print(f"ℹ️ File does not exist on server. It will be considered new.")
                original_checksum = ""
        
        # Get DDEV configuration
        ddev_wp_path = get_nested(self.config, "ddev", "webroot")

        # Get version information of the plugin/theme
        item_type, item_slug, local_version = get_item_version_from_path(
            file_path, 
            self.local_path,
            remote=False,
            use_ddev=True,
            wp_path=ddev_wp_path
        )
        
        # Get remote version of the plugin/theme if exists
        remote_version = ""
        if remote_file_exists:
            try:
                _, _, remote_version = get_item_version_from_path(
                    file_path, 
                    self.remote_path,
                    remote=True,
                    remote_host=self.remote_host,
                    remote_path=self.remote_path,
                    memory_limit=self.wp_memory_limit,
                    use_ddev=False
                )
            except Exception as e:
                print(f"⚠️ Remote version could not be obtained: {str(e)}")
        
        # Create or update entry in the lock file
        if "patches" not in self.lock_data:
            self.lock_data["patches"] = {}
            
        # If an entry already exists for this file, update it
        if file_path in self.lock_data["patches"]:
            print(f"ℹ️ Patch for '{file_path}' already exists. Updating...")
            
        # If no description was provided, use the existing one or a generic one
        if not description:
            if file_path in self.lock_data["patches"] and self.lock_data["patches"][file_path].get("description"):
                description = self.lock_data["patches"][file_path]["description"]
            else:
                description = f"Patch for {os.path.basename(file_path)}"
                
        # Register the patch
        self.lock_data["patches"][file_path] = {
            "description": description,
            "local_checksum": local_checksum,
            "original_checksum": original_checksum,
            "registered_date": datetime.datetime.now().isoformat(),
            "item_type": item_type,
            "item_slug": item_slug,
            "local_version": local_version,
            "remote_version": remote_version,
            "local_backup_file": local_backup_file,
            "local_backup_checksum": backup_checksum
        }
        
        # Save lock file
        self.save_lock_file()
        
        print(f"✅ Patch registered: {file_path}")
        if item_type != "other" and local_version:
            print(f"   Detected {item_type}: {item_slug} (local version {local_version})")
            if remote_version:
                print(f"   Remote version: {remote_version}")
        
        if original_checksum and original_checksum != local_checksum:
            print(f"   Changes detected in the file")
        
        print(f"   To apply the patch, execute: patch {file_path}")
        
        return True
    
    def remove_patch(self, file_path: str) -> bool:
        """
        Removes a patch from the lock file
        
        Args:
            file_path: Relative path to the file
            
        Returns:
            bool: True if removed correctly, False otherwise
        """
        if "patches" not in self.lock_data or file_path not in self.lock_data["patches"]:
            print(f"❌ Patch '{file_path}' is not registered.")
            return False
            
        # Check if the patch was already applied
        if self.lock_data["patches"][file_path].get("applied_date"):
            print("⚠️ This patch was already applied to the server.")
            confirm = input("   ¿Do you want to remove it from the record anyway? (y/n): ")
            if confirm.lower() != "y":
                print("   ⏭️ Operation canceled.")
                return False
                
        # Remove the patch
        del self.lock_data["patches"][file_path]
        
        # Save lock file
        self.save_lock_file()
        
        print(f"✅ Patch removed from record: {file_path}")
        return True
        
    def apply_patch(self, file_path: str, dry_run: bool = False, show_details: bool = False, force: bool = False, ssh_client: Optional[SSHClient] = None) -> bool:
        """
        Applies a patch to a remote file
        
        Args:
            file_path: Relative path to the file
            dry_run: If True, only shows what would be done
            show_details: If True, shows more details
            force: If True, applies the patch even if versions do not match
            ssh_client: Already initialized SSH client (optional)
            
        Returns:
            bool: True if the patch was applied correctly, False otherwise
        """
        # Verify that the patch exists in the record
        if "patches" not in self.lock_data or file_path not in self.lock_data["patches"]:
            print(f"❌ Error: Patch for '{file_path}' is not registered")
            print("   You can register it with the 'patch --add' command")
            return False
        
        # Verify security only if production_safety is enabled
        if self.production_safety and not dry_run:
            safety_check = self.check_safety(force_dry_run=False)
            if safety_check is None:  # Force dry-run for security
                print("⚠️ Forcing dry-run due to security configuration")
                dry_run = True
            elif not safety_check:  # Abort if not safe and not force dry-run
                return False
        
        # Verify local file
        local_file = self.local_path / file_path
        if not local_file.exists():
            print(f"❌ Error: Local file does not exist: {local_file}")
            return False
            
        # Calculate checksum of the local file
        local_checksum = self.calculate_checksum(local_file)
        if not local_checksum:
            print(f"❌ Error: No checksum could be calculated for the local file")
            return False
            
        # Verify if the local file has changed since the patch was registered
        patch_info = self.lock_data["patches"][file_path]
        registered_checksum = patch_info.get("local_checksum", "")
        if local_checksum != registered_checksum and not force:
            print(f"❌ Error: Local file has changed since the patch was registered")
            print(f"   Registered checksum: {registered_checksum}")
            print(f"   Actual checksum: {local_checksum}")
            print("   Patch application could be incorrect.")
            print("   Use --force to apply the patch of all modes.")
            return False
        
        # Verify SSH connection
        ssh = None
        ssh_provided = ssh_client is not None
        try:
            if ssh_client is not None:
                ssh = ssh_client
            else:
                # Verify connection to the server
                if not self.check_remote_connection():
                    return False
                
                # Establish SSH connection
                ssh = SSHClient(self.remote_host)
                ssh.connect()
            
            # Verify if the patch application is safe
            remote_file = f"{self.remote_path.rstrip('/')}/{file_path}"
            
            # Check if the file exists on the server
            cmd = f"test -f \"{remote_file}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error verifying remote file: {stderr}")
                return False
                
            remote_exists = "EXISTS" in stdout
            
            # If marked as applied, verify if it's actually applied
            if patch_info.get("applied_date"):
                if not remote_exists:
                    print(f"⚠️ File is marked as patched but does not exist on the server")
                    if not force:
                        print("   Use --force to apply the patch of all modes.")
                        return False
                else:
                    # Verify if the checksum matches the saved one
                    remote_checksum = self.get_remote_file_checksum(ssh, remote_file)
                    patched_checksum = patch_info.get("patched_checksum", "")
                    
                    if remote_checksum == patched_checksum:
                        if not show_details:
                            print(f"✅ Patch already applied correctly")
                            return True
                        else:
                            print(f"✅ Patch applied correctly with checksum {patched_checksum}")
                    else:
                        print(f"⚠️ Remote file has been modified since patch was applied")
                        print(f"   Saved checksum: {patched_checksum}")
                        print(f"   Actual checksum: {remote_checksum}")
                        
                        if not force:
                            print("   Use --force to apply the patch of all modes.")
                            return False
            
            # If the file exists on the server, create backup
            backup_file = ""
            if remote_exists and not dry_run:
                # Generate backup file name with timestamp
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{self.remote_path.rstrip('/')}/{file_path}.bak.{timestamp}"
                
                # Create backup
                cmd = f"cp -f \"{remote_file}\" \"{backup_path}\""
                code, stdout, stderr = ssh.execute(cmd)
                
                if code != 0:
                    print(f"❌ Error creating backup: {stderr}")
                    return False
                    
                backup_file = backup_path
                print(f"✅ Backup created: {os.path.basename(backup_path)}")
                
                # Verify that the backup was created correctly
                cmd = f"test -f \"{backup_path}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
                code, stdout, stderr = ssh.execute(cmd)
                
                if code != 0 or "EXISTS" not in stdout:
                    print(f"❌ Error: No backup verification")
                    return False
            
            # Show differences if requested
            if show_details:
                print("\n📋 Differences between files:")
                self._show_file_diff(local_file, remote_file, ssh)
                print("")
            
            # In dry-run mode, do not make changes
            if dry_run:
                print("ℹ️ Dry-run mode: No changes made")
                return True
            
            # Transfer the file
            remote_dir = os.path.dirname(remote_file)
            
            # Ensure remote directory exists
            cmd = f"mkdir -p \"{remote_dir}\""
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error creating remote directory: {stderr}")
                return False
            
            # Use SCP to transfer the file
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = tmp.name
                
            try:
                # Copy local file to temporary
                shutil.copy2(local_file, tmp_path)
                
                # Transfer the file to the server
                if not ssh.upload_file(tmp_path, remote_file):
                    print(f"❌ Error transferring file to server")
                    return False
                    
                # Verify original file permissions to keep them
                if remote_exists:
                    cmd = f"stat -c '%a' \"{backup_path}\""
                    code, stdout, stderr = ssh.execute(cmd)
                    
                    if code == 0 and stdout.strip():
                        permissions = stdout.strip()
                        # Apply the same permissions
                        cmd = f"chmod {permissions} \"{remote_file}\""
                        ssh.execute(cmd)
                
                # Update patch information in the lock
                patch_info.update({
                    "applied_date": datetime.datetime.now().isoformat(),
                    "backup_file": backup_file,
                    "patched_checksum": local_checksum  # Checksum of the modified file uploaded
                })
                
                # If it's a plugin or theme, get the updated remote version
                if patch_info.get("item_type") in ["plugin", "theme"] and patch_info.get("item_slug"):
                    try:
                        _, _, remote_version = get_item_version_from_path(
                            file_path, 
                            self.remote_path,
                            remote=True,
                            remote_host=self.remote_host,
                            remote_path=self.remote_path,
                            memory_limit=self.wp_memory_limit,
                            use_ddev=False
                        )
                        
                        if remote_version:
                            patch_info["remote_version"] = remote_version
                    except Exception as e:
                        print(f"⚠️ Remote version could not be obtained: {str(e)}")
                
                # Save changes
                self.save_lock_file()
                
                print(f"✅ Patch applied correctly: {file_path}")
                return True
                
            finally:
                # Delete temporary file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            print(f"❌ Error applying patch: {str(e)}")
            return False
            
        finally:
            # Close SSH connection if created in this method
            if ssh and ssh.client and not ssh_provided:
                ssh.disconnect()
    
    def _show_file_diff(self, local_file: Path, remote_file: str, ssh: Optional[SSHClient] = None) -> None:
        """
        Shows the differences between a local file and one remote
        
        Args:
            local_file: Path to the local file
            remote_file: Path to the remote file
            ssh: Connected SSH client (optional, a new one is created if not provided)
        """
        show_file_diff(local_file, remote_file, ssh)
    
    def rollback_patch(self, file_path: str, dry_run: bool = False) -> bool:
        """
        Reverts an applied patch previously
        
        Args:
            file_path: Relative path to the file
            dry_run: If True, only shows what would be done
            
        Returns:
            bool: True if rollback was successful, False otherwise
        """
        print(f"🔄 Trying to revert patch: {file_path}")
        
        # Verify if the patch exists in the lock file
        if "patches" not in self.lock_data or file_path not in self.lock_data["patches"]:
            print(f"❌ Patch '{file_path}' is not found in the record.")
            print("   Use --list to see available patches.")
            return False
            
        # Get patch information
        patch_info = self.lock_data["patches"][file_path]
        backup_file = patch_info.get("backup_file", "")
        
        if not backup_file:
            print("❌ No backup file found for this patch.")
            print("   Automatic rollback cannot be performed.")
            return False
            
        # Verify security and possibly force dry-run
        safety_check = self.check_safety(force_dry_run=True)
        if safety_check is None:  # Force dry-run for security
            dry_run = True
        elif not safety_check:  # Abort if not safe and not force dry-run
            return False
            
        # Verify connection
        if not self.check_remote_connection():
            return False
            
        remote_file = f"{self.remote_path.rstrip('/')}/{file_path}"
        
        # If it's dry-run mode, only show what would be done
        if dry_run:
            print("   🔄 Dry-run mode: No real changes will be made")
            print(f"   - Backup {backup_file} would be restored to {remote_file}")
            print(f"   - Lock file would be updated: {self.lock_file}")
            return True
            
        # Restore backup
        with SSHClient(self.remote_host) as ssh:
            # Verify if the backup exists
            cmd_check = f"test -f \"{backup_file}\" && echo \"EXISTS\" || echo \"NOT_EXISTS\""
            _, stdout, _ = ssh.execute(cmd_check)
            
            if "NOT_EXISTS" in stdout:
                print(f"❌ Backup file does not exist on server: {backup_file}")
                return False
                
            # Show differences between backup and actual file
            print("   🔍 Showing differences between actual file and backup...")
            
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            backup_temp = Path(temp_dir) / f"backup_{os.path.basename(file_path)}"
            current_temp = Path(temp_dir) / f"current_{os.path.basename(file_path)}"
            
            try:
                # Download files for comparison
                ssh.download_file(backup_file, backup_temp)
                ssh.download_file(remote_file, current_temp)
                
                # Compare files
                with open(backup_temp, 'r') as backup_f, open(current_temp, 'r') as current_f:
                    backup_content = backup_f.readlines()
                    current_content = current_f.readlines()
                    
                diff = list(difflib.unified_diff(
                    current_content, backup_content, 
                    fromfile='actual', tofile='backup',
                    lineterm=''
                ))
                
                if not diff:
                    print("   ℹ️ No differences found between actual file and backup.")
                else:
                    # Show differences (limited)
                    print("   📊 Differences found:")
                    for line in diff[:30]:
                        print(f"   {line}")
                    if len(diff) > 30:
                        print("   ... (more differences)")
            finally:
                # Clean temporary directory
                shutil.rmtree(temp_dir)
                
            # Ask if you want to restore
            restore = input("   ¿Do you want to restore to previous version? (y/n): ")
            if restore.lower() != "y":
                print("   ⏭️ Operation canceled.")
                return False
                
            # Restore backup
            cmd_restore = f"cp \"{backup_file}\" \"{remote_file}\""
            code, stdout, stderr = ssh.execute(cmd_restore)
            
            if code != 0:
                print(f"❌ Error restoring backup: {stderr}")
                return False
                
            print(f"✅ File restored from backup: {backup_file}")
            
            # Update lock file
            # We remove application flags but keep the record
            self.lock_data["patches"][file_path].update({
                "patched_checksum": "",
                "backup_file": "",
                "rollback_date": datetime.datetime.now().isoformat(),
                "applied_date": "",
                "remote_version": ""
            })
            
            self.save_lock_file()
            print(f"✅ Record updated: patch marked as reverted.")
                
            return True
            
    def apply_all_patches(self, dry_run: bool = False, force: bool = False) -> bool:
        """
        Applies all registered patches
        
        Args:
            dry_run: If True, only shows what would be done
            force: If True, applies patches even if versions do not match
            
        Returns:
            bool: True if all patches were applied correctly, False otherwise
        """
        if not self.lock_data.get("patches", {}):
            print("ℹ️ No patches registered to apply.")
            print("   You can register patches with 'patch --add path/to/file'")
            return False
            
        print("🔧 Starting application of patches from local to server...")
        print(f"   Source: {self.local_path}")
        print(f"   Destination: {self.remote_host}:{self.remote_path}")
        print("")
        
        # Verify security only if production_safety is enabled
        if self.production_safety and not dry_run:
            safety_check = self.check_safety(force_dry_run=False)
            if safety_check is None:  # Force dry-run for security
                print("⚠️ Forcing dry-run due to security configuration")
                dry_run = True
            elif not safety_check:  # Abort if not safe and not force dry-run
                return False
        
        # Verify connection
        if not self.check_remote_connection():
            return False

        # We configure a single SSH connection for all operations
        php_memory_error_shown = False
        
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                print("❌ Error establishing SSH connection")
                return False
                
            success_count = 0
            total_count = len(self.lock_data["patches"])
            
            print(f"Applying {total_count} patches:")
            
            for i, file_path in enumerate(self.lock_data["patches"]):
                # Get basic information of the current patch
                patch_info = self.lock_data["patches"][file_path]
                description = patch_info.get("description", "No description")
                
                print(f"\n[{i+1}/{total_count}] {file_path} - {description}")
                
                try:
                    # Verify patch status
                    status_code, status_details = self.get_patch_status(file_path, ssh)
                    
                    # Verify if PHP memory errors are detected
                    error_msg = status_details.get("error", "")
                    if "memory size" in error_msg.lower() and not php_memory_error_shown:
                        print("⚠️ Warning: PHP memory errors detected. Increasing limit if possible.")
                        php_memory_error_shown = True
                    
                    # Verify if we can apply the patch
                    if status_code == PATCH_STATUS_ORPHANED and not force:
                        print(f"⚠️ Patch is orphaned (ORPHANED): Local file has changed")
                        print("   Skipping (use --force to apply of all modes)")
                        continue
                    
                    if status_code == PATCH_STATUS_OBSOLETED and not force:
                        print(f"⚠️ Patch is obsolete (OBSOLETED): Local file modified after applying")
                        print("   Skipping (use --force to apply of all modes)")
                        continue
                        
                    if status_code == PATCH_STATUS_APPLIED:
                        print(f"✅ Patch already applied correctly.")
                        success_count += 1
                        continue
                        
                    # Apply the patch
                    success = self.apply_patch(file_path, dry_run, False, force, ssh)
                    if success:
                        success_count += 1
                
                except Exception as e:
                    print(f"❌ Error processing patch: {str(e)}")
                    
        print("")
        print(f"🎉 Patch application process completed.")
        print(f"   ✅ {success_count}/{total_count} patches applied correctly.")
        
        return success_count == total_count
        
    def get_patch_status(self, file_path: str, ssh: Optional[SSHClient] = None) -> Tuple[str, Dict]:
        """
        Determines the status of a patch
        
        Args:
            file_path: Relative path to the file
            ssh: Connected SSH client (optional)
            
        Returns:
            Tuple[str, Dict]: Patch status code and details
        """
        patch_info = self.lock_data.get("patches", {}).get(file_path, {})
        
        if not patch_info:
            return PATCH_STATUS_PENDING, {"error": "Patch not found", "messages": ["Patch not registered"]}
            
        # Initialize values
        details = {
            "remote_exists": False,
            "local_exists": False,
            "remote_checksum": "",
            "current_local_checksum": "",
            "registered_local_checksum": patch_info.get("local_checksum", ""),
            "current_remote_version": "",
            "registered_remote_version": patch_info.get("remote_version", ""),
            "messages": []
        }
            
        # Check local file
        local_file = self.local_path / file_path
        local_exists = local_file.exists()
        details["local_exists"] = local_exists
        
        # Get current local checksum
        current_local_checksum = ""
        if local_exists:
            current_local_checksum = self.calculate_checksum(local_file)
        details["current_local_checksum"] = current_local_checksum
            
        # Verify existence and checksum of the remote file
        remote_exists = False
        remote_checksum = ""
        current_remote_version = ""
        
        if ssh and ssh.client:
            # Construct full remote path
            remote_file = self.remote_path + file_path
            
            # Check if the remote file exists
            cmd = f"test -f '{remote_file}' && echo 'EXISTS' || echo 'NOT_FOUND'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if "EXISTS" in stdout:
                remote_exists = True
                
                # Get checksum of the remote file
                remote_checksum = self.get_remote_file_checksum(ssh, remote_file)
                
                # Get version of the plugin/theme remote
                current_remote_version = self.get_remote_file_version(ssh, file_path)
                
        details["remote_exists"] = remote_exists
        details["remote_checksum"] = remote_checksum
        details["current_remote_version"] = current_remote_version
                
        # Determine patch status
        return determine_patch_status(
            patch_info,
            remote_exists,
            remote_checksum,
            local_exists,
            current_local_checksum,
            current_remote_version,
            patch_info.get("local_checksum", "")
        )

    def show_config_info(self, verbose: bool = False) -> None:
        """
        Shows patch manager configuration information
        
        Args:
            verbose: If True, shows additional information
        """
        print("\n🛠️ Patch manager configuration:")
        
        # Information about the site
        if self.current_site:
            print(f"   • Current site: {self.current_site}")
        else:
            print(f"   • Using general configuration (no site specific)")
            
        # Information about the lock file
        print(f"   • Patch file: {self.lock_file.name}")
        if self.lock_file.exists():
            print(f"     - Status: Exists ({len(self.lock_data.get('patches', {}))} patches registered)")
            last_updated = self.lock_data.get("last_updated", "Unknown")
            print(f"     - Last update: {last_updated}")
        else:
            # Verify if the general file exists
            generic_lock_file = Path(__file__).resolve().parent.parent / "patches.lock.json"
            if generic_lock_file.exists():
                print(f"     - Status: Not exists (general: patches.lock.json will be used)")
            else:
                print(f"     - Status: Not exists (will be created when needed)")
                
        # Relevant paths
        if verbose:
            print(f"\n📂 Paths:")
            print(f"   • Lock file path: {self.lock_file}")
            print(f"   • Site local path: {self.local_path}")
            print(f"   • Remote server: {self.remote_host}:{self.remote_path}")
            
        print("")

    def _load_patched_files(self) -> List[Tuple[str, str]]:
        """
        Loads the list of patched files and their backups from the lock file
        
        Returns:
            List[Tuple[str, str]]: List of tuples with (patched file, local backup)
        """
        patched_files = []
        
        # Verify if the lock file exists
        if self.lock_data and "patches" in self.lock_data:
            # Extract paths of patched files and their backups
            for file_path, patch_info in self.lock_data["patches"].items():
                # Add patched file
                local_backup = patch_info.get("local_backup_file", "")
                
                if local_backup:
                    patched_files.append((file_path, local_backup))
                    print(f"🔧 Excluding patch: {file_path} and its local backup: {local_backup}")
                else:
                    patched_files.append((file_path, None))
                    print(f"🔧 Excluding patch: {file_path} (no local backup)")
                
                # Add remote backup if exists
                remote_backup = patch_info.get("backup_file", "")
                if remote_backup and remote_backup.startswith(self.remote_path):
                    # Convert full remote path to a relative path
                    relative_backup = remote_backup[len(self.remote_path):]
                    patched_files.append((file_path, relative_backup))
                
            if patched_files:
                print(f"🔧 {len(patched_files)} patches and backups found to exclude")
                
        return patched_files

def list_patches(verbose: bool = False):
    """
    Shows the list of available patches with detailed information
    
    Args:
        verbose: If True, shows additional information
    """
    manager = PatchManager()
    
    # In verbose mode, show configuration information
    if verbose:
        manager.show_config_info(verbose=True)
    
    manager.list_patches(verbose=verbose)
    
def add_patch(file_path: str, description: str = "") -> bool:
    """
    Registers a new patch in the lock file
    
    Args:
        file_path: Relative path to the file to patch
        description: Patch description
        
    Returns:
        bool: True if registered correctly, False otherwise
    """
    manager = PatchManager()
    return manager.add_patch(file_path, description)
    
def remove_patch(file_path: str) -> bool:
    """
    Removes a patch from the lock file
    
    Args:
        file_path: Relative path to the file to remove
        
    Returns:
        bool: True if removed correctly, False otherwise
    """
    manager = PatchManager()
    return manager.remove_patch(file_path)
    
def apply_patch(file_path: str = None, dry_run: bool = False, show_details: bool = False, force: bool = False) -> bool:
    """
    Applies one or all patches
    
    Args:
        file_path: Relative path to the file to patch, or None for all
        dry_run: If True, only shows what would be done
        show_details: If True, shows additional details of the patch
        force: If True, applies patches even if versions do not match or the file has changed
        
    Returns:
        bool: True if the patch was applied correctly, False otherwise
    """
    manager = PatchManager()
    
    if file_path:
        # Apply a single patch
        return manager.apply_patch(file_path, dry_run, show_details, force)
    else:
        # Apply all patches
        return manager.apply_all_patches(dry_run, force)
        
def rollback_patch(file_path: str, dry_run: bool = False) -> bool:
    """
    Reverts an applied patch previously
    
    Args:
        file_path: Relative path to the file to revert
        dry_run: If True, only shows what would be done
        
    Returns:
        bool: True if rollback was successful, False otherwise
    """
    manager = PatchManager()
    return manager.rollback_patch(file_path, dry_run)

def get_patched_files() -> List[str]:
    """
    Returns the list of files that have patches applied
    
    Returns:
        List[str]: List of paths to patched files
    """
    manager = PatchManager()
    patched_files = []
    
    for file_path, info in manager.lock_data.get("patches", {}).items():
        if info.get("applied_date"):
            patched_files.append(file_path)
            
    return patched_files 