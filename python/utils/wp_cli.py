"""
Utilities for interacting with WP-CLI from Python

IMPORTANT: Never use wp-cli commands directly. Always use these functions
that automatically manage the correct paths according to the site configuration in sites.yaml.

This module follows the "fail fast" design philosophy:
- Fail explicitly when critical information is missing, rather than guessing or inferring
- Do not use "magic" default values that could cause unexpected behaviors
- Maintain idempotence: the same input must always produce the same output
- Provide clear error messages that explain why it failed and how to fix it

Explicit configuration is a requirement, not an option. All necessary information
must be obtained from the configuration in sites.yaml, including the path inside the DDEV container.
"""

import os
import subprocess
import json
import shlex
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, Literal
import yaml

from config_yaml import get_yaml_config, get_nested

# WP-CLI path configuration - this could be moved to sites.yaml in the future
WP_CLI_PATH = "/usr/local/bin/wp"

def _format_wp_command(command: List[str]) -> str:
    """
    Formats a command list for safe execution in shell
    
    Args:
        command: List with the command and its arguments
        
    Returns:
        str: Command formatted for shell
    """
    return " ".join([f"'{arg}'" if ' ' in arg else arg for arg in command])

def _execute_ddev_command(command: List[str], path: Union[str, Path], wp_path: Optional[str] = None, 
                         memory_limit: str = "512M") -> Tuple[int, str, str]:
    """
    Executes a WP-CLI command using DDEV
    
    Follows the "fail fast" principle: if we cannot execute the command correctly, we fail
    explicitly instead of guessing paths or parameters.
    
    IMPORTANT: wp_path is mandatory and must be obtained from sites.yaml.
    
    Args:
        command: List with the command and its arguments
        path: Path to the directory where to execute the ddev command (project directory)
        wp_path: Path inside the DDEV container where WordPress is located (MANDATORY)
        memory_limit: Memory limit for PHP
        
    Returns:
        Tuple[int, str, str]: Exit code, standard output, standard error
    """
    # Format the base wp-cli command
    wp_cmd = " ".join(command)
    
    # If there is no wp_path, fail explicitly
    if not wp_path:
        return 1, "", "Error: WordPress path inside the container (wp_path) was not specified. It must be obtained from sites.yaml."
    
    # Build the complete command using the specified wp_path
    exec_cmd = f"cd {wp_path} && "
    
    # Add the wp-cli command with absolute path and memory options if necessary
    if memory_limit:
        exec_cmd += f"php -d memory_limit={memory_limit} {WP_CLI_PATH} {wp_cmd}"
    else:
        exec_cmd += f"{WP_CLI_PATH} {wp_cmd}"
    
    try:
        # Execute the command in DDEV and return results directly
        # Execute in the directory specified in path
        result = subprocess.run(
            ["ddev", "exec", exec_cmd],
            cwd=str(path),  # Important: execute in this directory
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        # If there's an error in execution, report immediately
        return 1, "", f"Error executing DDEV command: {str(e)}"

def _execute_direct_command(command: List[str], path: Union[str, Path], 
                           memory_limit: str = "512M") -> Tuple[int, str, str]:
    """
    Executes a WP-CLI command directly (without DDEV)
    
    Args:
        command: List with the command and its arguments
        path: Path to the WordPress directory
        memory_limit: Memory limit for PHP
        
    Returns:
        Tuple[int, str, str]: Exit code, standard output, standard error
    """
    wp_cmd = ["wp"] + command
    
    try:
        # Try to configure the environment with the memory limit
        env = os.environ.copy()
        env["PHP_MEMORY_LIMIT"] = memory_limit
        
        result = subprocess.run(
            wp_cmd,
            cwd=str(path),
            capture_output=True,
            text=True,
            check=False,
            env=env
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def _execute_ssh_command(command: List[str], remote_host: str, remote_path: str, 
                        memory_limit: str = "512M") -> Tuple[int, str, str]:
    """
    Executes a WP-CLI command on a remote server via SSH
    
    Args:
        command: List with the command and its arguments
        remote_host: Remote host
        remote_path: Remote path
        memory_limit: Memory limit for PHP
        
    Returns:
        Tuple[int, str, str]: Exit code, standard output, standard error
    """
    if not remote_host or not remote_path:
        return 1, "", "Remote host and path are required to execute WP-CLI on the server"
        
    # Add the memory limit to PHP commands
    php_memory_cmd = f"php -d memory_limit={memory_limit}"
    ssh_cmd = ["ssh", remote_host, f"cd {remote_path} && {php_memory_cmd} $(which wp) {' '.join(command)}"]
    
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def run_wp_cli(command: List[str], path: Union[str, Path], remote: bool = False, 
              remote_host: Optional[str] = None, remote_path: Optional[str] = None,
              use_ddev: bool = True, wp_path: Optional[str] = None,
              memory_limit: Optional[str] = None) -> Tuple[int, str, str]:
    """
    Executes a WP-CLI command
    
    IMPORTANT: For DDEV commands (use_ddev=True), wp_path is MANDATORY and 
    must be obtained from sites.yaml.
    
    Args:
        command: List with the command and its arguments
        path: Path to the WordPress directory on the host (project directory)
        remote: If True, executes the command on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Path inside the DDEV container where WordPress is located
                (REQUIRED if use_ddev=True, obtained from sites.yaml)
        memory_limit: Memory limit for PHP (if None, uses the configuration value)
        
    Returns:
        Tuple[int, str, str]: Exit code, standard output, standard error
    """
    # Get configuration and memory value
    config = get_yaml_config()
    
    # If memory limit is not specified, use the configuration value
    if memory_limit is None:
        memory_limit = config.get_wp_memory_limit()
    
    # Execute command according to the environment
    if remote:
        # Remote command via SSH
        if not remote_host or not remote_path:
            return 1, "", "Remote host and path are required to execute WP-CLI on the server"
        return _execute_ssh_command(command, remote_host, remote_path, memory_limit)
    elif use_ddev:
        # Local command using DDEV - wp_path is mandatory
        if not wp_path:
            # Explicitly fail without wp_path
            return 1, "", "Error: wp_path (path inside the DDEV container) was not specified. It must be obtained from sites.yaml."
        
        return _execute_ddev_command(command, path, wp_path, memory_limit)
    else:
        # Direct command without DDEV
        return _execute_direct_command(command, path, memory_limit)

def is_plugin_installed(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                       remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                       use_ddev: bool = True, wp_path: Optional[str] = None,
                       memory_limit: Optional[str] = None) -> bool:
    """
    Verifies if a plugin is installed
    
    Args:
        plugin_slug: Plugin slug
        path: Path to the WordPress directory
        remote: If True, checks on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        bool: True if the plugin is installed, False otherwise
    """
    cmd = ["plugin", "list", "--status=inactive,active", "--format=json"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        return False
        
    try:
        plugins = json.loads(stdout)
        for plugin in plugins:
            if plugin.get("name", "").lower() == plugin_slug.lower():
                return True
        return False
    except Exception as e:
        return False

def get_plugin_status(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                     remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                     use_ddev: bool = True, wp_path: Optional[str] = None,
                     memory_limit: Optional[str] = None) -> Optional[str]:
    """
    Gets the status of a plugin (active, inactive, not installed)
    
    Args:
        plugin_slug: Plugin slug
        path: Path to the WordPress directory
        remote: If True, checks on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        Optional[str]: Plugin status ("active", "inactive", None if not installed)
    """
    cmd = ["plugin", "list", "--format=json"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        return None
        
    try:
        plugins = json.loads(stdout)
        for plugin in plugins:
            if plugin.get("name", "").lower() == plugin_slug.lower():
                return plugin.get("status", "")
        return None
    except Exception as e:
        return None

def install_plugin(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                  remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                  use_ddev: bool = True, wp_path: Optional[str] = None, 
                  use_url: bool = False, memory_limit: Optional[str] = None) -> bool:
    """
    Installs a WordPress plugin
    
    Args:
        plugin_slug: Plugin slug or URL if use_url=True
        path: Path to the WordPress directory
        remote: If True, installs on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        use_url: If True, plugin_slug is interpreted as a URL
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        bool: True if the plugin was installed correctly, False otherwise
    """
    cmd = ["plugin", "install", plugin_slug]
    
    if use_url:
        cmd.append("--force")
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"Error installing the plugin: {stderr}")
        return False
        
    # Verify that the plugin was installed correctly
    if "successfully installed the plugin" in stdout or "Plugin already installed" in stdout:
        return True
    
    return False

def activate_plugin(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                   remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                   use_ddev: bool = True, wp_path: Optional[str] = None,
                   memory_limit: Optional[str] = None) -> bool:
    """
    Activates a WordPress plugin
    
    Args:
        plugin_slug: Plugin slug
        path: Path to the WordPress directory
        remote: If True, activates on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        bool: True if the plugin was activated correctly, False otherwise
    """
    # Verify current plugin status
    status = get_plugin_status(plugin_slug, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    # If already active, do nothing
    if status == "active":
        return True
    
    # If not installed, we can't activate it
    if status is None:
        return False
        
    # Activate the plugin
    cmd = ["plugin", "activate", plugin_slug]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"Error activating the plugin: {stderr}")
        return False
        
    # Verify that the plugin was activated correctly
    if "Plugin 'wp-original-media-path' activated" in stdout or "Success:" in stdout or "Plugin '" in stdout:
        return True
    
    return False

def deactivate_plugin(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                     remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                     use_ddev: bool = True, wp_path: Optional[str] = None,
                     memory_limit: Optional[str] = None) -> bool:
    """
    Deactivates a WordPress plugin
    
    Args:
        plugin_slug: Plugin slug
        path: Path to the WordPress directory
        remote: If True, deactivates on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        bool: True if the plugin was deactivated correctly, False otherwise
    """
    # Verify current plugin status
    status = get_plugin_status(plugin_slug, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    # If already inactive or not installed, do nothing
    if status != "active":
        return True
        
    # Deactivate the plugin
    cmd = ["plugin", "deactivate", plugin_slug]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"Error deactivating the plugin: {stderr}")
        return False
        
    return True

def get_plugin_info(plugin_slug: str, path: Union[str, Path], remote: bool = False,
                   remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                   use_ddev: bool = True, wp_path: Optional[str] = None,
                   memory_limit: Optional[str] = None) -> Dict[str, Any]:
    """
    Gets plugin information
    
    Args:
        plugin_slug: Plugin slug
        path: Path to the WordPress directory
        remote: If True, gets information from the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        Dict[str, Any]: Plugin information
    """
    cmd = ["plugin", "get", plugin_slug, "--format=json"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"⚠️ Error getting plugin information: {stderr}")
        return {}
        
    try:
        plugin_info = json.loads(stdout)
        return plugin_info
    except json.JSONDecodeError:
        print(f"⚠️ Error parsing plugin information")
        return {}

def get_theme_info(theme_slug: str, path: Union[str, Path], remote: bool = False,
                  remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                  use_ddev: bool = True, wp_path: Optional[str] = None,
                  memory_limit: Optional[str] = None) -> Dict[str, Any]:
    """
    Gets theme information
    
    Args:
        theme_slug: Theme slug
        path: Path to the WordPress directory
        remote: If True, gets information from the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        Dict[str, Any]: Theme information
    """
    cmd = ["theme", "get", theme_slug, "--format=json"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"⚠️ Error getting theme information: {stderr}")
        return {}
        
    try:
        theme_info = json.loads(stdout)
        return theme_info
    except json.JSONDecodeError:
        print(f"⚠️ Error parsing theme information")
        return {}
        
def get_item_version_from_path(file_path: str, path: Union[str, Path], remote: bool = False,
                             remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                             use_ddev: bool = True, wp_path: Optional[str] = None, 
                             memory_limit: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Gets information about the type of item (plugin/theme) and version from a file path
    
    Args:
        file_path: Relative path to the file (from the site root)
        path: Base path to the WordPress directory
        remote: If True, checks on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        Tuple[str, str, str]: Item type ("plugin", "theme"), slug, version
    """
    # Analyze the path to determine if it's a plugin or theme
    item_type = "other"
    item_slug = ""
    
    if '/plugins/' in file_path:
        item_type = "plugin"
        # The plugin slug is the main directory inside plugins/
        parts = file_path.split('/')
        for i, part in enumerate(parts):
            if part == "plugins" and i + 1 < len(parts):
                item_slug = parts[i + 1]
                break
    elif '/themes/' in file_path:
        item_type = "theme"
        # The theme slug is the main directory inside themes/
        parts = file_path.split('/')
        for i, part in enumerate(parts):
            if part == "themes" and i + 1 < len(parts):
                item_slug = parts[i + 1]
                break
                
    # If we couldn't determine the type or slug, we can't get version
    if item_type == "other" or not item_slug:
        return item_type, item_slug, ""
    
    # Get version using WP-CLI
    try:
        if item_type == "plugin":
            cmd = ["plugin", "get", item_slug, "--format=json"]
            code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
            
            if code != 0 or not stdout.strip():
                # If there's an error, much information in the log
                if "Fatal error: Allowed memory size" in stderr:
                    # Increase available memory
                    enlarged_memory = "1024M"
                    if memory_limit:
                        try:
                            # Try to increase the specified limit
                            current_limit = int(memory_limit.replace("M", "").replace("G", "000").replace("K", ""))
                            enlarged_memory = str(current_limit * 2) + "M"
                        except:
                            enlarged_memory = "1024M"
                            
                    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, enlarged_memory)
                    
                    if code != 0 or not stdout.strip():
                        if "Fatal error: Allowed memory size" in stderr:
                            raise Exception(f"Memory error getting plugin information: {stderr}")
                        else:
                            return item_type, item_slug, ""
                else:
                    return item_type, item_slug, ""
                
            try:
                data = json.loads(stdout)
                return item_type, item_slug, data.get("version", "")
            except:
                return item_type, item_slug, ""
                
        elif item_type == "theme":
            cmd = ["theme", "get", item_slug, "--format=json"]
            code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
            
            if code != 0 or not stdout.strip():
                # If there's an error, much information in the log
                if "Fatal error: Allowed memory size" in stderr:
                    # Increase available memory
                    enlarged_memory = "1024M"
                    if memory_limit:
                        try:
                            # Try to increase the specified limit
                            current_limit = int(memory_limit.replace("M", "").replace("G", "000").replace("K", ""))
                            enlarged_memory = str(current_limit * 2) + "M"
                        except:
                            enlarged_memory = "1024M"
                            
                    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, enlarged_memory)
                    
                    if code != 0 or not stdout.strip():
                        if "Fatal error: Allowed memory size" in stderr:
                            raise Exception(f"Memory error getting theme information: {stderr}")
                        else:
                            return item_type, item_slug, ""
                else:
                    return item_type, item_slug, ""
                
            try:
                data = json.loads(stdout)
                return item_type, item_slug, data.get("version", "")
            except:
                return item_type, item_slug, ""
                
    except Exception as e:
        if isinstance(e, Exception):
            raise e
        return item_type, item_slug, ""
        
    return item_type, item_slug, ""

def flush_cache(path: Union[str, Path], remote: bool = False,
               remote_host: Optional[str] = None, remote_path: Optional[str] = None,
               use_ddev: bool = True, wp_path: Optional[str] = None,
               memory_limit: Optional[str] = None) -> bool:
    """
    Flushes the WordPress cache
    
    Args:
        path: Path to the WordPress directory
        remote: If True, executes the command on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        bool: True if it was flushed correctly, False otherwise
    """
    cmd = ["cache", "flush"]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"⚠️ Error flushing cache: {stderr}")
        return False
        
    print("✅ WordPress cache flushed correctly")
    return True

def update_option(option_name: str, option_value: str, path: Union[str, Path], 
                 remote: bool = False, remote_host: Optional[str] = None, 
                 remote_path: Optional[str] = None, use_ddev: bool = True, 
                 wp_path: Optional[str] = None, memory_limit: Optional[str] = None) -> bool:
    """
    Updates a WordPress option
    
    Args:
        option_name: Option name
        option_value: Option value
        path: Path to the WordPress directory
        remote: If True, executes the command on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        bool: True if it was updated correctly, False otherwise
    """
    cmd = ["option", "update", option_name, option_value]
    
    code, stdout, stderr = run_wp_cli(cmd, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if code != 0:
        print(f"⚠️ Error updating option {option_name}: {stderr}")
        return False
        
    print(f"✅ Option {option_name} updated correctly")
    return True

def update_media_path(new_path: str, path: Union[str, Path], 
                     remote: bool = False, remote_host: Optional[str] = None, 
                     remote_path: Optional[str] = None, use_ddev: bool = True,
                     wp_path: Optional[str] = None, memory_limit: Optional[str] = None) -> bool:
    """
    Updates the media path in WordPress
    
    Args:
        new_path: New path for media files
        path: Path to the WordPress directory
        remote: If True, executes the command on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Specific WordPress path inside the container (optional)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        bool: True if it was updated correctly, False otherwise
    """
    # Update upload_path option
    upload_success = update_option("upload_path", new_path, path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    if not upload_success:
        return False
        
    # Flush cache to make changes take effect
    cache_success = flush_cache(path, remote, remote_host, remote_path, use_ddev, wp_path, memory_limit)
    
    return upload_success and cache_success 

def is_wordpress_installed(path: Union[str, Path], remote: bool = False,
                         remote_host: Optional[str] = None, remote_path: Optional[str] = None,
                         use_ddev: bool = True, wp_path: Optional[str] = None,
                         memory_limit: Optional[str] = None) -> bool:
    """
    Verifies if WordPress is correctly installed
    
    Following the "fail fast" principle, executes 'wp core is-installed' and returns
    its result without attempting to detect configurations automatically.
    
    IMPORTANT: For DDEV (use_ddev=True), wp_path is MANDATORY and must
    be obtained from sites.yaml.
    
    Args:
        path: Path to the WordPress directory on the host (project directory)
        remote: If True, checks on the remote server
        remote_host: Remote host (only if remote=True)
        remote_path: Remote path (only if remote=True)
        use_ddev: If True (default), uses ddev in local environment
        wp_path: Path inside the DDEV container (REQUIRED if use_ddev=True)
        memory_limit: Memory limit for PHP (optional)
        
    Returns:
        bool: True if WordPress is installed, False otherwise
    """
    # Standard command to verify WordPress installation
    cmd = ["core", "is-installed"]
    
    # If we're using DDEV but wp_path wasn't provided, return False directly
    if use_ddev and not wp_path:
        print("❌ Error: wp_path (path inside the DDEV container) was not specified")
        print("   This information must be obtained from sites.yaml (ddev.webroot or ddev.base_path + ddev.docroot)")
        return False
    
    # Execute the command - fail fast
    code, stdout, stderr = run_wp_cli(
        cmd, 
        path, 
        remote=remote, 
        remote_host=remote_host, 
        remote_path=remote_path,
        use_ddev=use_ddev, 
        wp_path=wp_path,
        memory_limit=memory_limit
    )
    
    # Return result directly without further processing
    return code == 0 