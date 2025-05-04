"""
Commands to create complete backups without applying exclusions
"""

import os
import shutil
import time
from pathlib import Path
import zipfile
from typing import Optional
from tqdm import tqdm


from config_yaml import get_yaml_config

def create_full_backup(site_alias: Optional[str] = None, output_dir: Optional[str] = None) -> str:
    """
    Creates a complete backup of the application directory in ZIP format
    without applying any exclusions.
    
    Args:
        site_alias: Alias of the site to backup
        output_dir: Directory where to save the backup (optional)
        
    Returns:
        str: Path of the created ZIP file
    """
    config = get_yaml_config()
    
    # Select the site if an alias is provided
    if site_alias:
        config.select_site(site_alias)
        print(f"🔍 Selected site: {site_alias}")
    
    # Get the local path of the site
    local_path = Path(config.get("ssh", "local_path"))
    
    if not local_path.exists():
        raise ValueError(f"The local path does not exist: {local_path}")
    
    # Generate filename with timestamp
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    site_name = site_alias or config.get_default_site() or "wordpress"
    backup_filename = f"{site_name}_backup_{timestamp}.zip"
    
    # Determine output directory
    if output_dir:
        backup_dir = Path(output_dir)
    else:
        backup_dir = local_path.parent / "backups"
    
    # Create the directory if it doesn't exist
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Full path of the ZIP file
    backup_path = backup_dir / backup_filename
    
    print(f"📦 Creating complete backup without exclusions...")
    print(f"   Source: {local_path}")
    print(f"   Destination: {backup_path}")
    
    # First count total files for the progress bar
    total_files = 0
    for _, _, files in os.walk(local_path):
        total_files += len(files)
    
    print(f"🔄 Processing {total_files} files...")
    
    # Create the ZIP file
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Get the base path to store relative paths in the ZIP
        base_path = local_path
        
        # File counter
        file_count = 0
        
        progress_bar = tqdm(total=total_files, unit='files', desc="Compressing")
        
        # Loop through all files and directories
        for root, _, files in os.walk(local_path):
            # Add files to the ZIP
            for file in files:
                file_path = Path(root) / file
                # Relative path for the file in the ZIP
                rel_path = file_path.relative_to(base_path)
                
                # Add file to the ZIP
                zipf.write(file_path, rel_path)
                file_count += 1
                
                # Update progress bar
                progress_bar.update(1)
        
        # Close the progress bar
        progress_bar.close()
    
    print(f"✅ Backup completed: {file_count} files")
    print(f"📦 ZIP file created: {backup_path}")
    
    # Return the backup path
    return str(backup_path) 