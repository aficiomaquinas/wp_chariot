#!/usr/bin/env python3
"""
Module for generic WordPress plugin management.

This module provides functions to install, activate, deactivate, and list
WordPress plugins using WP-CLI.
"""

import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from utils.wp_cli import (
    run_wp_cli,
    is_plugin_installed,
    get_plugin_status,
    install_plugin,
    activate_plugin,
    deactivate_plugin,
    get_plugin_info,
    is_wordpress_installed
)
from config_yaml import get_yaml_config, get_nested

def manage_plugin(
    operation: str,
    plugin_slug: str,
    remote: bool = False,
    verbose: bool = False,
    force: bool = False
) -> bool:
    """
    Manages a WordPress plugin (install, activate, deactivate, etc.)
    
    Args:
        operation: 'install', 'activate', 'deactivate', 'toggle', 'info', 'list'
        plugin_slug: Plugin slug or URL
        remote: Apply on the remote server instead of locally
        verbose: Show detailed information
        force: Force operation (e.g. reinstall)
        
    Returns:
        bool: True if the operation was successful, False otherwise
    """
    # Load configuration
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    
    # Get DDEV configuration
    base_path = get_nested(config, "ddev", "base_path")
    docroot = get_nested(config, "ddev", "docroot")
    ddev_wp_path = f"{base_path}/{docroot}" if base_path and docroot else None
    
    # Memory limit from config or default
    memory_limit = config.get_wp_memory_limit() if hasattr(config, "get_wp_memory_limit") else "512M"
    
    env_name = "Remote" if remote else "Local"
    
    if operation == "list":
        print(f"📋 Listing plugins on {env_name}...")
        cmd = ["plugin", "list"]
        if verbose:
            cmd.append("--verbose")
        code, stdout, stderr = run_wp_cli(cmd, local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit)
        if code == 0:
            print(stdout)
            return True
        else:
            print(f"❌ Error listing plugins: {stderr}")
            return False

    if not plugin_slug:
        print("❌ Error: Plugin slug or URL is required.")
        return False

    if operation == "install":
        print(f"📦 Installing plugin '{plugin_slug}' on {env_name}...")
        use_url = plugin_slug.startswith("http")
        success = install_plugin(plugin_slug, local_path, remote, remote_host, remote_path, True, ddev_wp_path, use_url, memory_limit)
        if success:
            print(f"✅ Plugin '{plugin_slug}' installed successfully.")
        return success

    if operation == "activate":
        print(f"🔌 Activating plugin '{plugin_slug}' on {env_name}...")
        success = activate_plugin(plugin_slug, local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit)
        if success:
            print(f"✅ Plugin '{plugin_slug}' activated successfully.")
        return success

    if operation == "deactivate":
        print(f"🔌 Deactivating plugin '{plugin_slug}' on {env_name}...")
        success = deactivate_plugin(plugin_slug, local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit)
        if success:
            print(f"✅ Plugin '{plugin_slug}' deactivated successfully.")
        return success

    if operation == "info":
        print(f"ℹ️ Getting info for plugin '{plugin_slug}' on {env_name}...")
        info = get_plugin_info(plugin_slug, local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit)
        if info:
            for key, value in info.items():
                print(f"  {key}: {value}")
            return True
        return False

    print(f"❌ Error: Unknown operation '{operation}'")
    return False
