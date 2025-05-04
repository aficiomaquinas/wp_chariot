"""
Commands to interact with WordPress through wp-cli
"""

import os
import argparse
import sys
from pathlib import Path
from typing import List, Optional

from config_yaml import get_yaml_config, get_nested
from utils.wp_cli import flush_cache, update_option, update_media_path

def flush_wp_cache(args: Optional[List[str]] = None) -> int:
    """
    Clears the WordPress cache
    
    Args:
        args: List of command line arguments
        
    Returns:
        int: Exit code (0 if success, 1 if error)
    """
    parser = argparse.ArgumentParser(description="Clears the WordPress cache")
    
    parser.add_argument("--remote", action="store_true", help="Run on the remote server")
    
    args = parser.parse_args(args)
    
    # Load configuration
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    
    # Explicitly require both parameters (fail fast)
    base_path = get_nested(config, "ddev", "base_path")
    docroot = get_nested(config, "ddev", "docroot")
    
    if not base_path or not docroot:
        print("❌ Error: Incomplete DDEV configuration in sites.yaml")
        print("   Both parameters are required:")
        print("   - ddev.base_path: Base path inside the container (e.g. \"/var/www/html\")")
        print("   - ddev.docroot: Docroot directory (e.g. \"app/public\")")
        return 1
        
    # Construct the full WP path
    ddev_wp_path = f"{base_path}/{docroot}"
    
    # Clear cache
    success = flush_cache(
        path=local_path,
        remote=args.remote,
        remote_host=remote_host,
        remote_path=remote_path,
        use_ddev=True,
        wp_path=ddev_wp_path
    )
    
    return 0 if success else 1

def update_wp_option(args: Optional[List[str]] = None) -> int:
    """
    Updates a WordPress option
    
    Args:
        args: List of command line arguments
        
    Returns:
        int: Exit code (0 if success, 1 if error)
    """
    parser = argparse.ArgumentParser(description="Updates a WordPress option")
    
    parser.add_argument("name", help="Option name")
    parser.add_argument("value", help="Option value")
    parser.add_argument("--remote", action="store_true", help="Run on the remote server")
    
    args = parser.parse_args(args)
    
    # Load configuration
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    
    # Explicitly require both parameters (fail fast)
    base_path = get_nested(config, "ddev", "base_path")
    docroot = get_nested(config, "ddev", "docroot")
    
    if not base_path or not docroot:
        print("❌ Error: Incomplete DDEV configuration in sites.yaml")
        print("   Both parameters are required:")
        print("   - ddev.base_path: Base path inside the container (e.g. \"/var/www/html\")")
        print("   - ddev.docroot: Docroot directory (e.g. \"app/public\")")
        return 1
        
    # Construct the full WP path
    ddev_wp_path = f"{base_path}/{docroot}"
    
    # Update option
    success = update_option(
        option_name=args.name,
        option_value=args.value,
        path=local_path,
        remote=args.remote,
        remote_host=remote_host,
        remote_path=remote_path,
        use_ddev=True,
        wp_path=ddev_wp_path
    )
    
    return 0 if success else 1

def update_wp_media_path(args: Optional[List[str]] = None) -> int:
    """
    Updates the media path in WordPress
    
    Args:
        args: List of command line arguments
        
    Returns:
        int: Exit code (0 if success, 1 if error)
    """
    parser = argparse.ArgumentParser(description="Updates the media path in WordPress")
    
    parser.add_argument("path", help="New path for media files")
    parser.add_argument("--remote", action="store_true", help="Run on the remote server")
    
    args = parser.parse_args(args)
    
    # Load configuration
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    
    # Explicitly require both parameters (fail fast)
    base_path = get_nested(config, "ddev", "base_path")
    docroot = get_nested(config, "ddev", "docroot")
    
    if not base_path or not docroot:
        print("❌ Error: Incomplete DDEV configuration in sites.yaml")
        print("   Both parameters are required:")
        print("   - ddev.base_path: Base path inside the container (e.g. \"/var/www/html\")")
        print("   - ddev.docroot: Docroot directory (e.g. \"app/public\")")
        return 1
        
    # Construct the full WP path
    ddev_wp_path = f"{base_path}/{docroot}"
    
    # Update media path
    success = update_media_path(
        new_path=args.path,
        path=local_path,
        remote=args.remote,
        remote_host=remote_host,
        remote_path=remote_path,
        use_ddev=True,
        wp_path=ddev_wp_path
    )
    
    return 0 if success else 1

if __name__ == "__main__":
    # Main script to interact with WordPress
    command_map = {
        "cache-flush": flush_wp_cache,
        "update-option": update_wp_option,
        "update-media-path": update_wp_media_path
    }
    
    # Verify arguments
    if len(sys.argv) < 2 or sys.argv[1] not in command_map:
        print("Usage: python -m wp_deploy.commands.wp_cli [command] [options]")
        print("Available commands:")
        for cmd in command_map.keys():
            print(f"  {cmd}")
        sys.exit(1)
        
    # Execute command
    command = sys.argv[1]
    sys.exit(command_map[command](sys.argv[2:]))