#!/usr/bin/env python3
"""
Module for configuring media paths in WordPress

This module provides functions to configure the uploads path in WordPress
using the 'WP Original Media Path' plugin.
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple, Dict

from utils.wp_cli import (
    run_wp_cli,
    update_option,
    flush_cache,
    is_plugin_installed,
    install_plugin,
    activate_plugin,
    is_wordpress_installed
)
from config_yaml import get_yaml_config, get_nested

# Required plugin for original media
MEDIA_PLUGIN = "wp-original-media-path"
MEDIA_PLUGIN_URL = "https://downloads.wordpress.org/plugin/wp-original-media-path.latest-stable.zip"

# Memory limit for WP-CLI
WP_CLI_MEMORY_LIMIT = "256M"

def configure_media_path(
    media_url: Optional[str] = None,
    expert_mode: bool = False,
    media_path: Optional[str] = None,
    remote: bool = False,
    verbose: bool = False
) -> bool:
    """
    Configures the media path in WordPress
    
    Args:
        media_url: IGNORED - The value from config.yaml is used
        expert_mode: Indicates if expert mode should be activated (from config.yaml)
        media_path: IGNORED - The value from config.yaml is used
        remote: Apply on the remote server instead of locally
        verbose: Show detailed information
        
    Returns:
        bool: True if the configuration was completed successfully, False otherwise
    """
    # Load configuration
    config = get_yaml_config()
    local_path = Path(get_nested(config, "ssh", "local_path"))
    remote_host = get_nested(config, "ssh", "remote_host")
    remote_path = get_nested(config, "ssh", "remote_path")
    
    # Get path inside DDEV container - explicitly require the two parameters
    # Fail fast: no compatibility with old formats
    base_path = get_nested(config, "ddev", "base_path")
    docroot = get_nested(config, "ddev", "docroot")
    
    if not base_path or not docroot:
        print("❌ Error: Incomplete DDEV configuration in sites.yaml")
        print("   Both parameters are required:")
        print("   - ddev.base_path: Base path inside the container (e.g. \"/var/www/html\")")
        print("   - ddev.docroot: Docroot directory (e.g. \"app/public\")")
        return False
        
    # Build the full path using the two parameters
    ddev_wp_path = f"{base_path}/{docroot}"
    
    if verbose:
        print(f"ℹ️ Using WordPress path: {ddev_wp_path}")
    
    # ALWAYS get values from the configuration
    media_url = get_nested(config, "media", "url", "")
    if not media_url:
        print("⚠️ No media URL found in configuration")
        print("   Configure 'media.url' in config.yaml")
        print("   Example: url: \"https://media.yourdomain.com\"")
        print("   Without a media URL, the default WordPress URL will be used")
    
    # Use expert mode according to configuration
    expert_mode = get_nested(config, "media", "expert_mode", False)
    media_path = None
    if expert_mode:
        media_path = get_nested(config, "media", "path", "")
        if not media_path:
            print("⚠️ Expert mode enabled but no physical path configured")
            print("   Configure 'media.path' in config.yaml")
            print("   Example: path: \"/absolute/path/to/uploads\"")
    
    # If we are in local environment, verify and ensure that DDEV is running
    if not remote:
        try:
            print("🔍 Verifying DDEV status...")
            ddev_status = subprocess.run(
                ["ddev", "status"],
                cwd=local_path.parent,
                capture_output=True,
                text=True
            )
            if "running" not in ddev_status.stdout.lower():
                print("⚠️ DDEV is not running. Starting DDEV automatically...")
                try:
                    start_process = subprocess.run(
                        ["ddev", "start"],
                        cwd=local_path.parent,
                        capture_output=True,
                        text=True
                    )
                    if start_process.returncode == 0:
                        print("✅ DDEV started correctly")
                        # Add pause to ensure DDEV is fully ready
                        print("⏳ Waiting 5 seconds to ensure DDEV is fully started...")
                        time.sleep(5)
                    else:
                        print(f"⚠️ Could not start DDEV: {start_process.stderr}")
                        print("   Continuing anyway, but errors may occur...")
                except Exception as e:
                    print(f"⚠️ Error when trying to start DDEV: {str(e)}")
                    print("   Continuing with the installation...")
        except Exception as e:
            print(f"⚠️ Could not verify DDEV status: {str(e)}")
            print("   Continuing with the installation...")
    
    # WordPress verification before continuing
    print(f"🔍 Verifying WordPress installation...")
    if verbose:
        print(f"   Local path: {local_path}")
        print(f"   Path in DDEV container: {ddev_wp_path}")
    
    if not is_wordpress_installed(local_path, remote, remote_host, remote_path, True, ddev_wp_path):
        print("⚠️ Could not verify a functional WordPress installation")
        print("   Verify that WordPress is correctly installed and configured")
        print("   Continuing anyway, but errors may occur...")
    
    print(f"🔍 Configuring WordPress to use custom media paths")
    if media_url:
        print(f"   Media URL: {media_url}")
    if expert_mode and media_path:
        print(f"   Physical path: {media_path} (Expert Mode)")
    
    # 1. Check if the plugin is already installed
    print(f"📋 Checking plugin '{MEDIA_PLUGIN}'...")
    
    if is_plugin_installed(MEDIA_PLUGIN, local_path, remote, remote_host, remote_path, True, ddev_wp_path):
        print(f"✅ Plugin '{MEDIA_PLUGIN}' is already installed")
        
        # Update the plugin if it's already installed
        print(f"🔄 Updating plugin '{MEDIA_PLUGIN}'...")
        update_result = install_plugin(
            MEDIA_PLUGIN, 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path
        )
        
        if update_result:
            print(f"✅ Plugin '{MEDIA_PLUGIN}' updated successfully")
        else:
            print(f"ℹ️ Update of '{MEDIA_PLUGIN}' was not necessary or an error occurred")
    else:
        print(f"📦 Installing plugin '{MEDIA_PLUGIN}'...")
        
        # Show command that would be executed for debugging
        if not remote:
            debug_cmd = f"ddev wp plugin install {MEDIA_PLUGIN}"
        else:
            debug_cmd = f"ssh {remote_host} 'cd {remote_path} && wp plugin install {MEDIA_PLUGIN}'"
        print(f"🔍 Command to execute: {debug_cmd}")
        
        # Add pause to ensure WordPress is ready to install plugins
        print("⏳ Ensuring WordPress is fully ready...")
        time.sleep(3)
        
        install_result = install_plugin(
            MEDIA_PLUGIN, 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path
        )
        
        if not install_result:
            print(f"❌ Error installing plugin '{MEDIA_PLUGIN}'")
            print(f"🔄 Trying to install from URL: {MEDIA_PLUGIN_URL}")
            
            # Show command that would be executed for debugging
            if not remote:
                debug_cmd = f"ddev wp plugin install {MEDIA_PLUGIN_URL}"
            else:
                debug_cmd = f"ssh {remote_host} 'cd {remote_path} && wp plugin install {MEDIA_PLUGIN_URL}'"
            print(f"🔍 Command to execute: {debug_cmd}")
            
            # Additional pause before the second attempt
            print("⏳ Waiting 5 seconds before retrying...")
            time.sleep(5)
            
            # Try to install from URL
            install_result = install_plugin(
                MEDIA_PLUGIN_URL, 
                local_path, 
                remote, 
                remote_host, 
                remote_path,
                True,
                ddev_wp_path,
                True  # Use URL
            )
            
            if not install_result:
                print(f"❌ Error installing plugin '{MEDIA_PLUGIN}'")
                print("ℹ️ Possible solutions:")
                print("   1. Verify that WordPress is correctly installed")
                print("   2. Ensure that DDEV is running (ddev start)")
                print("   3. Check Internet connectivity")
                print("   4. Try to install the plugin manually:")
                if not remote:
                    print(f"      $ ddev wp plugin install {MEDIA_PLUGIN_URL}")
                else:
                    print(f"      $ ssh {remote_host} 'cd {remote_path} && wp plugin install {MEDIA_PLUGIN_URL}'")
                
                print("⚠️ Continuing without the plugin. Media configuration may not work correctly.")
                return False
            else:
                print(f"✅ Plugin '{MEDIA_PLUGIN}' installed successfully")
        else:
            print(f"✅ Plugin '{MEDIA_PLUGIN}' installed successfully")
    
    # Pause before activating the plugin
    print("⏳ Waiting 2 seconds before activating the plugin...")
    time.sleep(2)
    
    # 2. Activate the plugin
    print(f"🔌 Activating plugin '{MEDIA_PLUGIN}'...")
    # Try to activate up to 3 times with small pauses
    activate_success = False
    for attempt in range(3):
        activate_result = activate_plugin(
            MEDIA_PLUGIN, 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT  # Use explicit memory limit
        )
        
        if activate_result:
            activate_success = True
            print(f"✅ Plugin '{MEDIA_PLUGIN}' activated successfully")
            break
        else:
            if attempt < 2:  # Don't show in last attempt
                print(f"⚠️ Attempt {attempt+1}/3 failed. Retrying...")
                # Increase pause between attempts
                print(f"⏳ Waiting {(attempt+1)*3} seconds before next attempt...")
                time.sleep((attempt+1) * 3)
    
    if not activate_success:
        print(f"⚠️ Could not activate plugin '{MEDIA_PLUGIN}'. Continuing anyway...")
        print(f"   It's possible you need to activate it manually from the WordPress panel.")
        print(f"   Or review errors using 'wp plugin activate {MEDIA_PLUGIN} --debug'")
    
    # 3. Get current configuration
    if verbose:
        print("🔍 Current configuration:")
        cmd = ["option", "get", "upload_url_path", "--skip-themes", "--skip-plugins"]
        code, stdout, stderr = run_wp_cli(
            cmd, 
            local_path, 
            remote, 
            remote_host, 
            remote_path, 
            True, 
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
        current_url = stdout.strip() if code == 0 and stdout.strip() else "Not configured"
        
        # Clean memory error messages in the output
        if "Failed to set memory limit" in current_url:
            current_url = current_url.split("\n")[-1].strip()
        
        cmd = ["option", "get", "owmp_path", "--skip-themes", "--skip-plugins"]
        code, stdout, stderr = run_wp_cli(
            cmd, 
            local_path, 
            remote, 
            remote_host, 
            remote_path, 
            True, 
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
        current_path = stdout.strip() if code == 0 and stdout.strip() else "Not configured"
        
        # Clean memory error messages in the output
        if "Failed to set memory limit" in current_path:
            current_path = current_path.split("\n")[-1].strip()
        
        cmd = ["option", "get", "owmp_expert_bool", "--skip-themes", "--skip-plugins"]
        code, stdout, stderr = run_wp_cli(
            cmd, 
            local_path, 
            remote, 
            remote_host, 
            remote_path, 
            True, 
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
        current_expert = stdout.strip() if code == 0 and stdout.strip() else "0"
        
        # Clean memory error messages in the output
        if "Failed to set memory limit" in current_expert:
            current_expert = current_expert.split("\n")[-1].strip()
            
        print(f"   Current URL: {current_url}")
        print(f"   Physical path: {current_path}")
        print(f"   Expert mode: {'Enabled' if current_expert == '1' else 'Disabled'}")
    
    # 4. Configure media URL
    if media_url:
        print(f"🔧 Configuring media URL to: {media_url}")
        update_option(
            "upload_url_path", 
            media_url, 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
    
    # 5. Configure expert mode if requested
    if expert_mode:
        print("⚙️ Activating expert mode for custom path")
        update_option(
            "owmp_expert_bool", 
            "1", 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
        
        if media_path:
            print(f"🔧 Configuring physical path to: {media_path}")
            update_option(
                "owmp_path", 
                media_path, 
                local_path, 
                remote, 
                remote_host, 
                remote_path,
                True,
                ddev_wp_path,
                memory_limit=WP_CLI_MEMORY_LIMIT
            )
    else:
        # Ensure that expert mode is disabled
        update_option(
            "owmp_expert_bool", 
            "0", 
            local_path, 
            remote, 
            remote_host, 
            remote_path,
            True,
            ddev_wp_path,
            memory_limit=WP_CLI_MEMORY_LIMIT
        )
    
    # 6. Clear cache
    print("🧹 Clearing WordPress cache...")
    flush_cache(
        local_path, 
        remote, 
        remote_host, 
        remote_path,
        True,
        ddev_wp_path,
        memory_limit=WP_CLI_MEMORY_LIMIT
    )
    
    # 7. Verify final configuration
    print("\n📊 Final configuration:")
    
    # Media URL
    cmd = ["option", "get", "upload_url_path", "--skip-themes", "--skip-plugins"]
    code, stdout, stderr = run_wp_cli(
        cmd, 
        local_path, 
        remote, 
        remote_host, 
        remote_path, 
        True, 
        ddev_wp_path,
        memory_limit=WP_CLI_MEMORY_LIMIT
    )
    final_url = stdout.strip() if code == 0 and stdout.strip() else "Not configured (using default value)"
    
    # Clean memory error messages in the output
    if "Failed to set memory limit" in final_url:
        final_url = final_url.split("\n")[-1].strip()
    
    # Physical path
    cmd = ["option", "get", "owmp_path", "--skip-themes", "--skip-plugins"]
    code, stdout, stderr = run_wp_cli(
        cmd, 
        local_path, 
        remote, 
        remote_host, 
        remote_path, 
        True, 
        ddev_wp_path,
        memory_limit=WP_CLI_MEMORY_LIMIT
    )
    final_path = stdout.strip() if code == 0 and stdout.strip() else "Not configured (using default value)"
    
    # Clean memory error messages in the output
    if "Failed to set memory limit" in final_path:
        final_path = final_path.split("\n")[-1].strip()
    
    # Expert mode
    cmd = ["option", "get", "owmp_expert_bool", "--skip-themes", "--skip-plugins"]
    code, stdout, stderr = run_wp_cli(
        cmd, 
        local_path, 
        remote, 
        remote_host, 
        remote_path, 
        True, 
        ddev_wp_path,
        memory_limit=WP_CLI_MEMORY_LIMIT
    )
    final_expert = "Enabled" if code == 0 and stdout.strip() == "1" else "Disabled"
    
    # Clean memory error messages in the output
    if "Failed to set memory limit" in stdout:
        final_expert = "Enabled" if stdout.split("\n")[-1].strip() == "1" else "Disabled"
    
    print(f"   Media URL: {final_url}")
    print(f"   Physical path: {final_path}")
    print(f"   Expert mode: {final_expert}")
    
    print("\n✅ Configuration completed successfully")
    print("🔍 Media files will now be looked for in the configured path")
    if not remote:
        print("\n💡 Reminder: After synchronizing the production database")
        print("   to development, run this script to configure media paths")
        print("   and ensure media files are available locally.")
    
    return True 