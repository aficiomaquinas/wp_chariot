#!/usr/bin/env python3
"""
Module for WordPress cache management.
"""

import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from utils.wp_cli import (
    run_wp_cli,
    install_plugin,
    activate_plugin,
    flush_cache as wp_flush_cache,
    update_option
)
from config_yaml import get_yaml_config, get_nested

def install_cache(remote: bool = False, verbose: bool = False) -> bool:
    """
    Idempotent installation and configuration of cache plugins based on sites.yaml.
    
    Args:
        remote: Apply on the remote server instead of locally
        verbose: Show detailed information
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Load configuration
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    
    # Get cache configuration for the current site
    cache_config = config.get("cache", default={})
    if not cache_config:
        print("ℹ️ No cache configuration found for this site. Skipping setup.")
        return True

    # Get DDEV configuration
    base_path = get_nested(config, "ddev", "base_path")
    docroot = get_nested(config, "ddev", "docroot")
    ddev_wp_path = f"{base_path}/{docroot}" if base_path and docroot else None
    
    # Memory limit from config or default
    memory_limit = config.get_wp_memory_limit() if hasattr(config, "get_wp_memory_limit") else "512M"
    
    env_name = "Remote" if remote else "Local"
    
    print(f"🚀 Setting up cache plugins on {env_name} based on config...")
    
    # 1. Redis Cache
    redis_cfg = cache_config.get("redis", {})
    if redis_cfg.get("enabled", False):
        print(f"📦 Configuring Redis Object Cache...")
        if not install_plugin("redis-cache", local_path, remote, remote_host, remote_path, True, ddev_wp_path, False, memory_limit):
            print("❌ Error installing redis-cache plugin.")
            return False
        if not activate_plugin("redis-cache", local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit):
            print("❌ Error activating redis-cache plugin.")
            return False
            
        # Enable Redis (idempotent: wp redis enable)
        cmd = ["redis", "enable"]
        code, stdout, stderr = run_wp_cli(cmd, local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit)
        if code != 0 and "Object cache already enabled" not in stdout and "Success" not in stdout:
            print(f"⚠️ Warning enabling Redis cache: {stderr}")
        else:
            print(f"✅ Redis Object Cache enabled.")
    else:
        if verbose:
            print("ℹ️ Redis cache is not enabled for this site.")

    # 2. Nginx Helper
    fcgi_cfg = cache_config.get("fastcgi", {})
    if fcgi_cfg.get("enabled", False):
        print(f"📦 Configuring Nginx Helper (Page Cache Purge)...")
        if not install_plugin("nginx-helper", local_path, remote, remote_host, remote_path, True, ddev_wp_path, False, memory_limit):
            print("❌ Error installing nginx-helper plugin.")
            return False
        if not activate_plugin("nginx-helper", local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit):
            print("❌ Error activating nginx-helper plugin.")
            return False
            
        # Configure Nginx Helper options (JSON format)
        options = {
            "enable_purge": "1",
            "cache_method": "enable_fastcgi",
            "purge_method": fcgi_cfg.get("purge_method", "get_request"),
            "is_fastcgi": "1",
            "cache_path": fcgi_cfg.get("path", "/var/www/wordpress/cache"),
            "log_level": "INFO"
        }
        
        options_json = json.dumps(options)
        if update_option("rt_wp_nginx_helper_options", options_json, local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit):
            print(f"✅ Nginx Helper configured correctly.")
        else:
            return False
    else:
        if fcgi_cfg.get("purge", False):
            print("⚠️ Nginx Helper purging is enabled, but 'enabled: true' is missing in sites.yaml. Skipping setup.")
        elif verbose:
            print("ℹ️ FastCGI cache (Nginx Helper) is not enabled for this site.")

    # 3. Final Cache Flush (if any purge is enabled)
    if redis_cfg.get("purge", False) or fcgi_cfg.get("purge", False) or cache_config.get("wordpress", {}).get("purge", False):
        print(f"🧹 Performing final cache flush...")
        if wp_flush_cache(local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit):
            print(f"✅ Cache management setup complete on {env_name}.")
            return True
        return False
    
    return True

def flush_cache(remote: bool = False, verbose: bool = False) -> bool:
    """
    Flushes the WordPress cache (unified, respects config).
    
    Args:
        remote: Apply on the remote server instead of locally
        verbose: Show detailed information
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Load configuration
    config = get_yaml_config()
    cache_config = config.get("cache", default={})
    
    # Only flush if at least one purge is enabled in config
    if not (cache_config.get("redis", {}).get("purge", False) or 
            cache_config.get("fastcgi", {}).get("purge", False) or 
            cache_config.get("wordpress", {}).get("purge", False)):
        if verbose:
            print("ℹ️ Cache purging is not enabled in config. Skipping flush.")
        return True

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
    if verbose:
        print(f"🧹 Flushing cache on {env_name}...")
        
    return wp_flush_cache(local_path, remote, remote_host, remote_path, True, ddev_wp_path, memory_limit)
