"""
YAML-based configuration module for wp_deploy

This module is responsible for loading and managing configuration
from YAML files, with support for complex data structures.
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
import copy
import re

class YAMLConfig:
    """
    Class for managing YAML-based configuration, with support for multiple sites
    """
    
    def __init__(self, verbose=False):
        """
        Initializes configuration from YAML file
        
        Args:
            verbose (bool): Enable detailed mode
        """
        self.verbose = verbose
        self.config = {}
        self.sites = {}
        self.current_site = None
        self.default_site = None
        
        # Detect project directory and deploy-tools
        self.detect_project_roots()
        
        # Load configuration
        self.load_config()
        
        # Detect and load multi-site configuration
        self.load_sites_config()
        
        # Automatically select the default site if it exists
        if self.default_site and self.default_site in self.sites:
            self.set_current_site(self.default_site)
            if self.verbose:
                print(f"✅ Default site automatically selected: {self.default_site}")
        
    def detect_project_roots(self):
        """
        Detects the directory structure of the project and deploy-tools
        """
        # Detect deploy-tools
        current_file = Path(__file__).resolve()
        # config_yaml.py -> python -> deploy-tools
        self.deploy_tools_dir = current_file.parent.parent
        
        # If we are running from within deploy-tools
        if "deploy-tools" in str(self.deploy_tools_dir):
            # The project directory is the parent of deploy-tools
            self.project_root = self.deploy_tools_dir.parent
        else:
            # In case the package is installed as a library and is not in the deploy-tools structure
            # Use the current directory as the project root
            self.project_root = Path.cwd()
        
        if self.verbose:
            print(f"Detected project directory: {self.project_root}")
            print(f"Detected deploy-tools directory: {self.deploy_tools_dir}")

    def load_config(self):
        """
        Loads the configuration from YAML files
        """
        # Global configuration (inside deploy-tools)
        global_config_file = self.deploy_tools_dir / "python" / "config.yaml"
        
        # Project configuration (in the project root)
        project_config_file = self.project_root / "wp-deploy.yaml"
        
        # Initialize empty configuration
        self.config = {}
        
        # Load global configuration if it exists
        if global_config_file.exists():
            try:
                with open(global_config_file, 'r') as f:
                    global_config = yaml.safe_load(f) or {}
                    # Set the global configuration
                    self.config = global_config
                if self.verbose:
                    print(f"Global configuration loaded from: {global_config_file}")
            except Exception as e:
                print(f"Error loading global configuration: {str(e)}")
                
        # Load project configuration if it exists
        if project_config_file.exists():
            try:
                with open(project_config_file, 'r') as f:
                    project_config = yaml.safe_load(f) or {}
                    # Merge with existing configuration
                    self.merge_config(project_config)
                if self.verbose:
                    print(f"Project configuration loaded from: {project_config_file}")
            except Exception as e:
                print(f"Error loading project configuration: {str(e)}")
    
    def load_sites_config(self):
        """
        Loads configuration for multiple sites
        """
        sites_config_file = self.deploy_tools_dir / "python" / "sites.yaml"
        
        if sites_config_file.exists():
            try:
                with open(sites_config_file, 'r') as f:
                    sites_config = yaml.safe_load(f) or {}
                    
                # Extract the site list
                self.sites = sites_config.get("sites", {})
                self.default_site = sites_config.get("default", None)
                
                if self.verbose:
                    print(f"Sites configuration loaded: {len(self.sites)} sites found")
                    if self.default_site:
                        print(f"Default site: {self.default_site}")
            except Exception as e:
                print(f"Error loading sites configuration: {str(e)}")
    
    def set_current_site(self, site_alias):
        """
        Sets the current site to use
        
        Args:
            site_alias: Alias of the site to use
            
        Returns:
            bool: True if the site exists and was set correctly
        """
        if site_alias not in self.sites:
            print(f"❌ Error: Site '{site_alias}' not found in configuration")
            return False
        
        # Save the name of the current site
        self.current_site = site_alias
        
        # Load the site configuration
        site_config = self.sites[site_alias]
        
        # Reset the current configuration to an empty dictionary
        self.config = {}
        
        # Load global configuration
        global_config_file = self.deploy_tools_dir / "python" / "config.yaml"
        if global_config_file.exists():
            try:
                with open(global_config_file, 'r') as f:
                    global_config = yaml.safe_load(f) or {}
                    self.config = global_config
            except Exception:
                pass
        
        # Apply the site-specific configuration
        self.merge_config(site_config)
        
        if self.verbose:
            print(f"✅ Current site set to: {site_alias}")
        
        return True
    
    def get_available_sites(self):
        """
        Gets the list of available sites
        
        Returns:
            dict: Dictionary with available sites
        """
        return self.sites
    
    def get_default_site(self):
        """
        Gets the default site
        
        Returns:
            str: Alias of the default site or None if none exists
        """
        return self.default_site
    
    def select_site(self, site_alias=None):
        """
        Selects a site to use
        
        Args:
            site_alias: Alias of the site to use (optional)
            
        Returns:
            bool: True if the site was selected correctly
        """
        # If no site is specified, attempt to determine automatically
        if not site_alias:
            # If there is only one site, use it
            if len(self.sites) == 1:
                site_alias = list(self.sites.keys())[0]
                if self.verbose:
                    print(f"ℹ️ Single site selected automatically: {site_alias}")
            # If there are more than one and there is one by default, use that
            elif self.default_site and self.default_site in self.sites:
                site_alias = self.default_site
                if self.verbose:
                    print(f"ℹ️ Default site selected: {site_alias}")
            # If there is no default site and there are multiple sites, error
            elif len(self.sites) > 1:
                print("❌ Error: Multiple sites available. Specify one with --site ALIAS")
                print("   Available sites:")
                for alias in self.sites.keys():
                    default_mark = " (default)" if alias == self.default_site else ""
                    print(f"   - {alias}{default_mark}")
                return False
            # If no sites are configured, continue with the current configuration
            else:
                if self.verbose:
                    print("ℹ️ No sites configured. Using current configuration.")
                return True
        
        # Attempt to set the selected site
        if site_alias:
            return self.set_current_site(site_alias)
        
        return True
    
    def create_sites_config(self, default_site=None):
        """
        Creates an empty sites configuration file
        
        Args:
            default_site: Default site (optional)
            
        Returns:
            bool: True if created correctly
        """
        sites_config_file = self.deploy_tools_dir / "python" / "sites.yaml"
        
        # Initial template
        template = {
            "default": default_site,
            "sites": {}
        }
        
        # If there are already sites configured, keep them
        if hasattr(self, 'sites') and self.sites:
            template["sites"] = self.sites
        
        # Write configuration
        try:
            with open(sites_config_file, 'w') as f:
                yaml.dump(template, f, default_flow_style=False, sort_keys=False)
            print(f"✅ Sites configuration file created: {sites_config_file}")
            return True
        except Exception as e:
            print(f"❌ Error creating sites configuration file: {str(e)}")
            return False
    
    def add_site(self, alias, config=None, is_default=False):
        """
        Adds a new site to the configuration
        
        Args:
            alias: Alias of the site
            config: Site configuration (optional)
            is_default: If it is the default site
            
        Returns:
            bool: True if added correctly
        """
        sites_config_file = self.deploy_tools_dir / "python" / "sites.yaml"
        
        # Load current configuration
        self.load_sites_config()
        
        # If no configuration is provided, use the current one
        if not config:
            config = self.config
        
        # Add/update the site
        self.sites[alias] = config
        
        # Update default site if necessary
        if is_default:
            self.default_site = alias
        
        # Save configuration
        template = {
            "default": self.default_site,
            "sites": self.sites
        }
        
        try:
            with open(sites_config_file, 'w') as f:
                yaml.dump(template, f, default_flow_style=False, sort_keys=False)
            print(f"✅ Site '{alias}' added/updated correctly")
            
            if is_default:
                print(f"✅ '{alias}' set as default site")
                
            return True
        except Exception as e:
            print(f"❌ Error saving sites configuration: {str(e)}")
            return False
    
    def remove_site(self, alias):
        """
        Removes a site from the configuration
        
        Args:
            alias: Alias of the site to remove
            
        Returns:
            bool: True if removed correctly
        """
        sites_config_file = self.deploy_tools_dir / "python" / "sites.yaml"
        
        # Load current configuration
        self.load_sites_config()
        
        # Verify if the site exists
        if alias not in self.sites:
            print(f"❌ Error: Site '{alias}' not found")
            return False
        
        # Remove the site
        del self.sites[alias]
        
        # If it was the default site, remove that configuration
        if self.default_site == alias:
            self.default_site = None
            print(f"ℹ️ Site removed was the default site. No default site now.")
        
        # Save configuration
        template = {
            "default": self.default_site,
            "sites": self.sites
        }
        
        try:
            with open(sites_config_file, 'w') as f:
                yaml.dump(template, f, default_flow_style=False, sort_keys=False)
            print(f"✅ Site '{alias}' removed correctly")
            return True
        except Exception as e:
            print(f"❌ Error saving sites configuration: {str(e)}")
            return False

    def _detect_project_root(self) -> Path:
        """
        Detects the project root WordPress.
        Searches up the directory tree until finding 
        a directory that contains a deploy-tools folder.
        
        Returns:
            Path: Path to the project root
        """
        current_dir = Path.cwd()
        
        # Search up the directory tree
        while current_dir != current_dir.parent:
            # Verify if the current directory contains deploy-tools
            if (current_dir / "deploy-tools").exists():
                return current_dir
                
            # Go up one level
            current_dir = current_dir.parent
            
        # If not found, use the current directory
        print("⚠️ Project root could not be detected. Using current directory.")
        return Path.cwd()
        
    def _load_config(self):
        """
        Loads the configuration from YAML files.
        First loads the global configuration, then the project configuration.
        """
        # Variable to track if any configuration file was loaded
        config_loaded = False
        
        # Load global configuration
        global_config_file = self.deploy_tools_dir / "python" / "config.yaml"
        if global_config_file.exists():
            if self.verbose:
                print(f"📝 Loading configuration from {global_config_file}")
            self._load_yaml_file(global_config_file)
            config_loaded = True
            
        # Load project configuration
        project_config_file = self.project_root / "wp-deploy.yaml"
        if project_config_file.exists():
            if self.verbose:
                print(f"📝 Loading configuration from {project_config_file}")
            self._load_yaml_file(project_config_file)
            config_loaded = True
        
        # If no configuration was loaded, show warning
        if not config_loaded:
            # This is not a critical error because we have default values
            print("⚠️ No valid configuration file found.")
            print(f"   Searching in:")
            print(f"   - {global_config_file}")
            print(f"   - {project_config_file}")
            print(f"   Default values will be used.")
            
        # Load environment variables for compatibility with the previous system
        self._load_env_vars()
        
    def _load_yaml_file(self, file_path: Path):
        """
        Loads a YAML file and updates the configuration
        
        Args:
            file_path: Path to the YAML file
        """
        try:
            with open(file_path, 'r') as file:
                if self.verbose:
                    print(f"📝 Reading YAML file: {file_path}")
                yaml_data = yaml.safe_load(file)
                
            if yaml_data and isinstance(yaml_data, dict):
                # Show main keys for debugging
                if self.verbose:
                    print(f"📝 Found keys in {file_path}: {', '.join(yaml_data.keys())}")
                
                # If there is a database section, show its contents
                if 'database' in yaml_data and self.verbose:
                    db_config = yaml_data['database']
                    print(f"📝 Found database configuration:")
                    if 'remote' in db_config:
                        remote_db = db_config['remote']
                        print(f"   - DB Host: {remote_db.get('host', 'no configured')}")
                        print(f"   - DB Name: {remote_db.get('name', 'no configured')}")
                        print(f"   - DB User: {remote_db.get('user', 'no configured')}")
                        print(f"   - DB Pass: {'*'*len(remote_db.get('password', '')) if 'password' in remote_db else 'no configured'}")
                
                # Update the configuration recursively
                self._update_dict_recursive(self.config, yaml_data)
                
                # Verify that values were updated
                if 'database' in yaml_data and 'remote' in yaml_data['database'] and self.verbose:
                    print(f"📝 Database values after updating:")
                    remote_db = self.config['database']['remote']
                    print(f"   - DB Host: {remote_db.get('host', 'no configured')}")
                    print(f"   - DB Name: {remote_db.get('name', 'no configured')}")
                    print(f"   - DB User: {remote_db.get('user', 'no configured')}")
                    print(f"   - DB Pass: {'*'*len(remote_db.get('password', '')) if 'password' in remote_db else 'no configured'}")
        except Exception as e:
            print(f"❌ Error loading YAML file {file_path}: {str(e)}")
            import traceback
            traceback.print_exc()
            
    def _update_dict_recursive(self, target: Dict, source: Dict):
        """
        Updates a dictionary recursively
        
        Args:
            target: Destination dictionary
            source: Dictionary with new values
        """
        for key, value in source.items():
            # If both values are dictionaries, update recursively
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                # Special case for security section, ensuring that site configuration takes precedence
                if key == 'security' and 'production_safety' in value:
                    # Preserve production_safety value directly from site before doing recursive merge
                    production_safety_value = value.get('production_safety')
                    
                    # Do recursive merge normally
                    self._update_dict_recursive(target[key], value)
                    
                    # Apply site value with precedence
                    target[key]['production_safety'] = production_safety_value
                    
                    if self.verbose:
                        print(f"Security configuration updated: production_safety={production_safety_value}")
                else:
                    # For other sections, do normal recursive merge
                    self._update_dict_recursive(target[key], value)
            else:
                # Otherwise, overwrite the value
                target[key] = copy.deepcopy(value)
                
    def _load_env_vars(self):
        """
        Loads environment variables for compatibility with the previous system
        """
        # Mapping of environment variables to the new structure
        env_mapping = {
            "REMOTE_SSH": ("ssh", "remote_host"),
            "REMOTE_SSH_ALIAS": ("ssh", "remote_host"),  # Alternate alias
            "REMOTE_PATH": ("ssh", "remote_path"),
            "LOCAL_PATH": ("ssh", "local_path"),
            "PRODUCTION_SAFETY": ("security", "production_safety"),
            "REMOTE_DB_NAME": ("database", "remote", "name"),
            "REMOTE_DB_USER": ("database", "remote", "user"),
            "REMOTE_DB_PASS": ("database", "remote", "password"),
            "REMOTE_DB_HOST": ("database", "remote", "host"),
            "REMOTE_URL": ("urls", "remote"),
            "LOCAL_URL": ("urls", "local"),
            "WP_MEDIA_URL": ("media", "url"),
            "WP_MEDIA_EXPERT": ("media", "expert_mode"),
            "WP_MEDIA_PATH": ("media", "path"),
        }
        
        # Attempt to load .env in the project root
        env_file = self.project_root / ".env"
        if env_file.exists():
            if self.verbose:
                print(f"📝 Loading environment variables from {env_file} (compatibility)")
            env_vars = self._parse_env_file(env_file)
            
            # Apply environment variables according to mapping
            for env_name, config_path in env_mapping.items():
                if env_name in env_vars:
                    value = env_vars[env_name]
                    
                    # Convert boolean values
                    if env_name == "WP_MEDIA_EXPERT":
                        if value in ("1", "true", "yes", "on"):
                            value = True
                        elif value in ("0", "false", "no", "off"):
                            value = False
                    
                    self._set_nested_value(self.config, config_path, value)
                    
    def _parse_env_file(self, file_path: Path) -> Dict[str, str]:
        """
        Parses an .env file and returns a dictionary with the variables
        
        Args:
            file_path: Path to the .env file
            
        Returns:
            Dict[str, str]: Dictionary with environment variables
        """
        env_vars = {}
        
        try:
            with open(file_path, 'r') as file:
                for line in file:
                    line = line.strip()
                    # Ignore empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                        
                    # Split into key and value
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Remove quotes if they exist
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                            
                        env_vars[key] = value
                        
        except Exception as e:
            if self.verbose:
                print(f"❌ Error parsing .env file {file_path}: {str(e)}")
            
        return env_vars
        
    def _set_nested_value(self, target: Dict, path: tuple, value: Any):
        """
        Sets a value in a nested dictionary according to a path
        
        Args:
            target: Destination dictionary
            path: Tuple with key path to access the value
            value: Value to set
        """
        current = target
        for i, key in enumerate(path):
            if i == len(path) - 1:
                # Last element: set the value
                current[key] = value
            else:
                # Intermediate element: ensure the dictionary exists
                if key not in current or not isinstance(current[key], dict):
                    current[key] = {}
                current = current[key]
                
    def get(self, *path: str, default: Any = None) -> Any:
        """
        Gets a configuration value according to a key path
        
        Args:
            *path: Key path to access the value
            default: Default value if the path is not found
            
        Returns:
            The configuration value or the default value
        """
        current = self.config
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current
        
    def get_strict(self, *path: str) -> Any:
        """
        Gets a configuration value following the fail-fast principle
        
        Unlike get(), this function raises an exception if the path does not exist,
        instead of returning a default value.
        
        Args:
            *path: Key path to access the value
            
        Returns:
            Any: The configuration value
            
        Raises:
            ValueError: If the path does not exist in the configuration
        """
        current = self.config
        for i, key in enumerate(path):
            if not isinstance(current, dict):
                path_str = ' -> '.join(path[:i])
                raise ValueError(f"Configuration path '{path_str}' is not a dictionary")
            
            if key not in current:
                path_str = ' -> '.join(path[:i+1])
                raise ValueError(f"Key '{key}' does not exist in path '{path_str}'")
            
            current = current[key]
        
        return current
        
    def get_exclusions(self) -> Dict[str, str]:
        """
        Gets the exclusion dictionary for rsync
        
        Returns:
            Dict[str, str]: Exclusion dictionary (key -> pattern)
        """
        # Get exclusions and ensure it is a dictionary
        raw_exclusions = self.config.get("exclusions", {}) or {}
        
        if not isinstance(raw_exclusions, dict):
            print(f"⚠️ Warning: Exclusions are not a valid dictionary.")
            return {}
            
        # If no exclusions are configured, use an empty dictionary
        if not raw_exclusions:
            print(f"ℹ️ No exclusions configured.")
            return {}
        
        # Process exclusions, removing disabled (False)
        exclusions = {}
        for key, value in raw_exclusions.items():
            if value is not False:  # Allow disabling exclusions by setting to False
                exclusions[key] = value
                
        return exclusions
        
    def get_protected_files(self) -> List[str]:
        """
        Gets the list of protected files that should not be deleted
        
        Returns:
            List[str]: List of protected file patterns
        """
        return self.config.get("protected_files", [])
        
    def get_media_config(self) -> Dict[str, Any]:
        """
        Gets the media configuration
        
        Returns:
            Dict[str, Any]: Media configuration
        """
        return self.config.get("media", {})
        
    def display(self):
        """
        Displays the current configuration in a structured format
        """
        print("\n🔧 Loaded configuration:")
        self._display_dict(self.config)
        print()
        
    def _display_dict(self, data: Dict, indent: int = 1):
        """
        Displays a dictionary in a structured format
        
        Args:
            data: Dictionary to display
            indent: Indentation level
        """
        for key, value in data.items():
            # Hide passwords and sensitive values (actual values are used internally)
            if "password" in key.lower() or "pass" in key.lower():
                display_value = "***********"
            # Hide database credentials for greater security
            elif key == "name" and isinstance(data.get("password"), str):
                display_value = "***********"
            elif key == "user" and isinstance(data.get("password"), str):
                display_value = "***********"
            elif key == "host" and isinstance(data.get("password"), str):
                # Keep host visible as it is not sensitive
                display_value = value
            elif isinstance(value, dict):
                print(f"{'   ' * indent}- {key}:")
                self._display_dict(value, indent + 1)
                continue
            else:
                display_value = value
                
            print(f"{'   ' * indent}- {key}: {display_value}")
            
    def get_wp_memory_limit(self) -> str:
        """
        Gets the PHP memory limit for WP-CLI
        
        Following the "fail fast" principle, this function returns exactly
        what is in the configuration without attempting to fix invalid values.
        If the value does not exist in the configuration, it fails explicitly.
        
        Returns:
            str: PHP memory limit
            
        Raises:
            ValueError: If the value does not exist in the configuration
        """
        # Verify if the wp_cli section exists
        if "wp_cli" not in self.config:
            raise ValueError("The 'wp_cli' section is not defined in the configuration")
        
        # Verify if the memory_limit exists
        if "memory_limit" not in self.config["wp_cli"]:
            raise ValueError("The 'memory_limit' key is not defined in the 'wp_cli' section")
        
        # Return exactly what is in the configuration, without attempting to fix it
        return self.config["wp_cli"]["memory_limit"]

    def merge_config(self, config):
        """
        Merges the provided configuration with the current configuration
        
        Args:
            config: Dictionary with configuration to merge
        """
        if not config:
            return
            
        self._update_dict_recursive(self.config, config)

# Global function to get the configuration
_config_instance = None

def get_yaml_config(verbose=False):
    """
    Gets the unique instance of the configuration
    
    Args:
        verbose: If True, shows additional information
        
    Returns:
        YAMLConfig: Configuration instance
    """
    global _config_instance
    
    if not _config_instance:
        _config_instance = YAMLConfig(verbose=verbose)
        
    return _config_instance

def get_nested(config_or_dict: Any, section: str, key: str, default: Any = None) -> Any:
    """
    Accesses a value in a nested configuration
    
    Args:
        config_or_dict: Configuration (YAMLConfig or Dict)
        section: Main section
        key: Key within the section
        default: Default value
        
    Returns:
        Any: Found value or default value
    """
    # If it is a YAMLConfig object, use its get() method
    if isinstance(config_or_dict, YAMLConfig):
        return config_or_dict.get(section, key, default=default)
        
    # If it is a dictionary, access directly
    if not isinstance(config_or_dict, dict) or section not in config_or_dict:
        return default
        
    section_dict = config_or_dict[section]
    if not isinstance(section_dict, dict) or key not in section_dict:
        return default
        
    return section_dict[key] 