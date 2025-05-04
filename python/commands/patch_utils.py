"""
Patch system utilities

This module contains helper functions for working with patches,
calculating checksums, detecting states, and handling file versions.
It follows the "fail fast" principle to ensure predictable behaviors.
"""

import os
import hashlib
import json
import difflib
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, Set

from config_yaml import get_yaml_config, get_nested
from utils.ssh import SSHClient
from utils.wp_cli import get_item_version_from_path

# Patch states
PATCH_STATUS_PENDING = "PENDING"        # Registered, not applied, current checksum
PATCH_STATUS_APPLIED = "APPLIED"        # Applied and current
PATCH_STATUS_ORPHANED = "ORPHANED"      # Local checksum doesn't match, orphaned patch
PATCH_STATUS_OBSOLETED = "OBSOLETED"    # Patch applied but local modified afterward
PATCH_STATUS_MISMATCHED = "MISMATCHED"  # Applied but different remote version
PATCH_STATUS_STALE = "STALE"            # Old patch, no longer relevant

# User-readable state
PATCH_STATUS_LABELS = {
    PATCH_STATUS_PENDING: "⏳ Pending",
    PATCH_STATUS_APPLIED: "✅ Applied",
    PATCH_STATUS_ORPHANED: "⚠️ Orphaned",
    PATCH_STATUS_OBSOLETED: "🔄 Obsolete",
    PATCH_STATUS_MISMATCHED: "❌ Mismatched",
    PATCH_STATUS_STALE: "📅 Stale"
}

def calculate_checksum(file_path: Path) -> str:
    """
    Calculates the MD5 checksum of a file
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: MD5 checksum of the file
    """
    if not file_path.exists():
        return ""
        
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"⚠️ Error calculating checksum: {str(e)}")
        return ""

def get_remote_file_checksum(ssh: SSHClient, remote_file: str) -> str:
    """
    Gets the checksum of a file on the remote server
    
    Args:
        ssh: Connected SSH client
        remote_file: Path to the file on the remote server
        
    Returns:
        str: MD5 checksum of the remote file
    """
    if not ssh or not ssh.client:
        return ""
    
    # Check if the file exists
    cmd = f"test -f '{remote_file}' && echo 'EXISTS' || echo 'NOT_FOUND'"
    code, stdout, stderr = ssh.execute(cmd)
    
    if "NOT_FOUND" in stdout:
        return ""
    
    # Calculate MD5 checksum
    cmd = f"md5sum '{remote_file}' | awk '{{print $1}}'"
    code, stdout, stderr = ssh.execute(cmd)
    
    if code != 0:
        return ""
        
    return stdout.strip()

def get_remote_file_version(ssh: SSHClient, file_path: str, wp_path: str, wp_memory_limit: str) -> str:
    """
    Gets the version of a plugin or theme from a file on the remote server
    
    Args:
        ssh: Connected SSH client
        file_path: Path to the file
        wp_path: Path to WordPress on the remote server
        wp_memory_limit: Memory limit for PHP
        
    Returns:
        str: Version of the plugin or theme, or empty string if it cannot be determined
    """
    if not ssh or not ssh.client:
        return ""
        
    try:
        # Use wp_path directly as the base without trying to get ABSPATH
        wp_base_path = wp_path
        
        # Normalize paths
        if not wp_base_path.endswith("/"):
            wp_base_path += "/"
            
        # Remove any absolute path prefix
        if file_path.startswith("/"):
            file_path = file_path.lstrip("/")
            
        # Detect type and version using WP-CLI
        if "/plugins/" in file_path or "/themes/" in file_path:
            cmd = f"cd {wp_path} && php -d memory_limit={wp_memory_limit} $(which wp) plugin list --format=json || echo 'ERROR'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0 or "ERROR" in stdout:
                return ""
                
            # Analyze the path to determine if it's a plugin or theme
            item_type = "other"
            item_slug = ""
            
            if '/plugins/' in file_path:
                item_type = "plugin"
                parts = file_path.split('/')
                for i, part in enumerate(parts):
                    if part == "plugins" and i + 1 < len(parts):
                        item_slug = parts[i + 1]
                        break
            elif '/themes/' in file_path:
                item_type = "theme"
                parts = file_path.split('/')
                for i, part in enumerate(parts):
                    if part == "themes" and i + 1 < len(parts):
                        item_slug = parts[i + 1]
                        break
                
            # If the type or slug could not be determined, the version cannot be obtained
            if item_type == "other" or not item_slug:
                return ""
            
            # Get the version using WP-CLI
            if item_type == "plugin":
                cmd = f"cd {wp_path} && php -d memory_limit={wp_memory_limit} $(which wp) plugin get {item_slug} --format=json"
            else:  # theme
                cmd = f"cd {wp_path} && php -d memory_limit={wp_memory_limit} $(which wp) theme get {item_slug} --format=json"
                
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0 or not stdout.strip():
                return ""
                
            try:
                data = json.loads(stdout)
                return data.get("version", "")
            except:
                return ""
        
        return ""
    except Exception as e:
        print(f"⚠️ Error getting remote version: {str(e)}")
        return ""

def get_local_file_version(file_path: str, local_base_path: Path) -> str:
    """
    Gets the version of a plugin or theme from a local file
    
    Args:
        file_path: Relative path to the file
        local_base_path: Local base path to WordPress
        
    Returns:
        str: Version of the plugin or theme, or empty string if it cannot be determined
    """
    try:
        # Convert to relative path if necessary
        if file_path.startswith("/"):
            file_path = file_path.lstrip("/")
            
        # Get version
        item_type, item_slug, version = get_item_version_from_path(
            file_path,
            local_base_path,
            remote=False,
            use_ddev=True
        )
        
        return version
    except Exception as e:
        print(f"⚠️ Error getting local version: {str(e)}")
        return ""

def show_file_diff(local_file: Path, remote_file: str, ssh: Optional[SSHClient] = None) -> None:
    """
    Shows the differences between a local file and a remote one
    
    Args:
        local_file: Path to the local file
        remote_file: Path to the remote file
        ssh: Connected SSH client (optional, a new one is created if not provided)
    """
    needs_disconnect = False
    
    try:
        # Check if local_file exists
        if not local_file.exists():
            print(f"❌ The local file does not exist: {local_file}")
            return
            
        # Check SSH
        if not ssh or not ssh.client:
            print(f"⚠️ No SSH connection, cannot show differences")
            return
            
        # Get remote file content
        cmd = f"cat '{remote_file}'"
        code, remote_content, stderr = ssh.execute(cmd)
        
        if code != 0:
            print(f"❌ Could not read the remote file: {remote_file}")
            if stderr:
                print(f"   Error: {stderr}")
            return
            
        # Read local file content
        with open(local_file, 'r', encoding='utf-8', errors='replace') as f:
            local_content = f.read()
            
        # Split into lines
        local_lines = local_content.splitlines()
        remote_lines = remote_content.splitlines()
        
        # Generate difflist
        diff = list(difflib.unified_diff(
            remote_lines, local_lines,
            fromfile=f"{remote_file} (remote)",
            tofile=f"{local_file} (local)",
            lineterm="",
            n=3
        ))
        
        # Show the diff
        if diff:
            print(f"\n📊 Differences between files:")
            for line in diff:
                # Color the lines according to type
                if line.startswith('+'):
                    print(f"\033[92m{line}\033[0m")  # Green for additions
                elif line.startswith('-'):
                    print(f"\033[91m{line}\033[0m")  # Red for deletions
                elif line.startswith('@@'):
                    print(f"\033[96m{line}\033[0m")  # Cyan for markers
                else:
                    print(line)
            print("")
        else:
            print(f"✅ No differences between the files\n")
    except Exception as e:
        print(f"⚠️ Error showing differences: {str(e)}")
    finally:
        # Close SSH connection if we created it here
        if needs_disconnect and ssh and ssh.client:
            ssh.disconnect()

def determine_patch_status(patch_info: Dict[str, Any], 
                          remote_exists: bool, 
                          remote_checksum: str, 
                          local_exists: bool,
                          current_local_checksum: str,
                          current_remote_version: str,
                          registered_local_checksum: str) -> Tuple[str, Dict]:
    """
    Determines the status of a patch based on checksums and versions
    
    Args:
        patch_info: Patch information from the lock file
        remote_exists: True if the remote file exists
        remote_checksum: Checksum of the remote file
        local_exists: True if the local file exists
        current_local_checksum: Current checksum of the local file
        current_remote_version: Version of the remote plugin
        registered_local_checksum: Registered checksum of the local file
        
    Returns:
        Tuple[str, Dict]: Patch status code and details
    """
    details = {
        "remote_exists": remote_exists,
        "remote_checksum": remote_checksum,
        "local_exists": local_exists,
        "current_local_checksum": current_local_checksum,
        "registered_local_checksum": registered_local_checksum,
        "original_checksum": patch_info.get("original_checksum", ""),
        "current_remote_version": current_remote_version,
        "registered_remote_version": patch_info.get("remote_version", ""),
        "messages": []
    }
    
    if remote_exists:
        if patch_info.get("applied_date"):
            # Patch is marked as applied
            patched_checksum = patch_info.get("patched_checksum", "")
            original_checksum = patch_info.get("original_checksum", "")
            
            if remote_checksum == patched_checksum:
                # The remote checksum matches the applied patch checksum
                if local_exists and current_local_checksum == registered_local_checksum:
                    return PATCH_STATUS_APPLIED, details
                else:
                    # The local file has changed, obsolete patch
                    return PATCH_STATUS_OBSOLETED, details
            elif remote_checksum == original_checksum:
                # The remote checksum matches the original (patch reverted or never applied)
                details["messages"].append(f"The remote file matches the original version")
                return PATCH_STATUS_PENDING, details
            else:
                # The remote checksum doesn't match, mismatched patch
                if details.get("current_remote_version") != patch_info.get("remote_version"):
                    # The remote version changed, stale patch
                    return PATCH_STATUS_STALE, details
                else:
                    # Same plugin but file modified on the server
                    return PATCH_STATUS_MISMATCHED, details
        else:
            # Patch is not applied
            original_checksum = patch_info.get("original_checksum", "")
            
            if remote_checksum == original_checksum:
                # The remote file matches the original
                if local_exists and current_local_checksum == registered_local_checksum:
                    # The local file matches the registered one, pending patch
                    return PATCH_STATUS_PENDING, details
                else:
                    # The local file has changed, orphaned patch
                    return PATCH_STATUS_ORPHANED, details
            else:
                # The remote file doesn't match the original
                details["messages"].append(f"The remote file has changed from the original")
                return PATCH_STATUS_STALE, details
    else:
        # The remote file doesn't exist
        details["messages"].append(f"The remote file doesn't exist")
        
        if patch_info.get("applied_date"):
            # Patch is marked as applied but the file doesn't exist
            return PATCH_STATUS_MISMATCHED, details
        else:
            # Patch not applied and remote file doesn't exist
            if local_exists and current_local_checksum == registered_local_checksum:
                # Correct local file, pending (will be a new file)
                return PATCH_STATUS_PENDING, details
            else:
                # Modified local file, orphaned
                return PATCH_STATUS_ORPHANED, details
    
    # Default state
    return PATCH_STATUS_PENDING, details

def get_site_specific_lock_file(site_name: Optional[str] = None) -> Path:
    """
    Gets the path to the site-specific lock file
    
    Args:
        site_name: Site name, None for the default site
        
    Returns:
        Path: Path to the site-specific lock file
    """
    # If no specific site, use the generic file
    if not site_name:
        return Path(__file__).resolve().parent.parent / "patches.lock.json"
    
    # If there is a site, use a specific file
    return Path(__file__).resolve().parent.parent / f"patches-{site_name}.lock.json"

def load_lock_file(lock_file: Path) -> Dict:
    """
    Loads the lock file with patch information
    
    Args:
        lock_file: Path to the lock file
        
    Returns:
        Dict: Lock file data
    """
    # Create initial structure of the lock file
    lock_data = {
        "patches": {},
        "last_updated": datetime.datetime.now().isoformat()
    }
    
    # Check if the file exists
    if lock_file.exists():
        try:
            with open(lock_file, 'r') as f:
                lock_data = json.load(f)
                
            print(f"✅ Lock file '{lock_file.name}' loaded: {len(lock_data.get('patches', {}))} registered patches")
            return lock_data
        except Exception as e:
            print(f"⚠️ Error loading lock file: {str(e)}")
            print("   A new lock file will be created.")
    else:
        print(f"ℹ️ Lock file not found. A new one will be created.")
        
    return lock_data

def save_lock_file(lock_file: Path, lock_data: Dict, site_name: Optional[str] = None) -> bool:
    """
    Saves the lock file data
    
    Args:
        lock_file: Path to the lock file
        lock_data: Data to save
        site_name: Site name (for informational messages)
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    try:
        # Update modification date
        lock_data["last_updated"] = datetime.datetime.now().isoformat()
        
        # Make sure the parent directory exists
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(lock_file, 'w') as f:
            json.dump(lock_data, f, indent=2)
            
        # Show information about the site if it's a specific file
        if site_name:
            print(f"✅ Lock file for site '{site_name}' updated: {lock_file}")
        else:
            print(f"✅ General lock file updated: {lock_file}")
            
        return True
    except Exception as e:
        print(f"⚠️ Error saving lock file: {str(e)}")
        return False 