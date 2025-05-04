"""
Utilities for filesystem operations
"""

import os
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
import time

def ensure_dir_exists(directory: Path) -> None:
    """
    Ensures that a directory exists, creating it if necessary
    
    Args:
        directory: Directory path
    """
    directory.mkdir(parents=True, exist_ok=True)
    
def create_backup(file_path: Path, backup_suffix: str = ".bak", config=None) -> Optional[Path]:
    """
    Creates a backup of a file or directory
    
    Args:
        file_path: Path to the file or directory to backup
        backup_suffix: Suffix for the backup file/directory
        config: Configuration object containing protected files definitions
        
    Returns:
        Path: Path to the backup file/directory or None if it couldn't be created
    """
    if not file_path.exists():
        return None
    
    # Generate a unique name for the backup
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    
    if file_path.is_file():
        # For files, use the suffix
        backup_path = file_path.with_suffix(file_path.suffix + backup_suffix)
        try:
            shutil.copy2(file_path, backup_path)
            print(f"✅ Backup created: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"❌ Error creating backup: {str(e)}")
            return None
    elif file_path.is_dir():
        # For directories, create a directory with timestamp in the same path
        parent_dir = file_path.parent
        dir_name = file_path.name
        backup_dir = parent_dir / f"{dir_name}_backup_{timestamp}"
        
        try:
            # Get the list of protected files from the configuration
            protected_files = []
            
            if config:
                # Try to get protected files from the configuration
                if hasattr(config, 'get_protected_files'):
                    protected_files = config.get_protected_files()
                elif hasattr(config, 'config') and isinstance(config.config, dict):
                    # Try to get the list of protected files from the configuration dictionary
                    protected_files = config.config.get('protected_files', [])
            
            # If there's no configuration or no protected files are found, fail fast
            if not protected_files:
                print("❌ Error: No protected files configuration found")
                print("   Cannot create a backup without knowing which files to protect")
                print("   Make sure the 'protected_files' section is defined in config.yaml")
                return None
                
            # Create the backup directory
            if not backup_dir.exists():
                backup_dir.mkdir(parents=True)
            
            # Copy only the protected files specified in the configuration
            files_copied = 0
            for file_pattern in protected_files:
                # Handle patterns with wildcards
                if '*' in file_pattern:
                    matches = list(file_path.glob(file_pattern))
                    for source_file in matches:
                        if source_file.is_file():
                            # Keep the relative structure of subdirectories for files with wildcards
                            rel_path = source_file.relative_to(file_path)
                            dest_file = backup_dir / rel_path
                            # Create parent directories if necessary
                            dest_file.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source_file, dest_file)
                            files_copied += 1
                else:
                    # Specific files (without wildcards)
                    source_file = file_path / file_pattern
                    if source_file.exists() and source_file.is_file():
                        dest_file = backup_dir / file_pattern
                        # Create parent directories if necessary
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_file, dest_file)
                        files_copied += 1
            
            if files_copied > 0:
                print(f"✅ Backup created in {backup_dir} ({files_copied} files)")
                return backup_dir
            else:
                # No files were copied
                print("⚠️ No important files to backup were found in the specified path")
                # Remove the empty directory
                backup_dir.rmdir()
                return None
        except Exception as e:
            print(f"❌ Error creating directory backup: {str(e)}")
            return None
    else:
        # It's neither a file nor a directory (symlink or other)
        print(f"⚠️ Cannot create backup: the type of {file_path} is not supported")
        return None
