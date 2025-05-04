"""
Configuration module for wp_deploy

This module is responsible for loading and managing configuration
from .env files and environment variables.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

class Config:
    """
    Class to handle system configuration.
    Loads variables from .env files and provides access to them.
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Initializes the configuration object.
        
        Args:
            project_root: Project root path. If None, it is automatically detected.
        """
        # Define the project root directory
        if project_root is None:
            # Try to detect the project root
            self.project_root = self._detect_project_root()
        else:
            self.project_root = project_root
            
        # Deployment tools directory
        self.deploy_tools_dir = self.project_root / "deploy-tools"
        
        # Default configuration
        self.config: Dict[str, Any] = {
            # SSH Configuration
            "REMOTE_SSH": "server",
            "REMOTE_PATH": "/home/user/webapps/wordpress/",
            "LOCAL_PATH": str(self.project_root / "app" / "public"),
            
            # Security Configuration
            "PRODUCTION_SAFETY": "enabled",
            
            # Database Configuration
            "REMOTE_DB_NAME": "",
            "REMOTE_DB_USER": "",
            "REMOTE_DB_PASS": "",
            "REMOTE_DB_HOST": "localhost",
            
            # URLs
            "REMOTE_URL": "https://example.com",
            "LOCAL_URL": "https://example.ddev.site",
        }
        
        # Load configuration
        self._load_config()
        
    def _detect_project_root(self) -> Path:
        """
        Detects the WordPress project root.
        Searches up the directory tree until finding
        a directory containing a deploy-tools folder.
        
        Returns:
            Path: Path to the project root
        """
        current_dir = Path.cwd()
        
        # Search up the directory tree
        while current_dir != current_dir.parent:
            # Check if the current directory contains deploy-tools
            if (current_dir / "deploy-tools").exists():
                return current_dir
                
            # Go up one level
            current_dir = current_dir.parent
            
        # If not found, use the current directory
        print("⚠️ Could not detect the project root. Using current directory.")
        return Path.cwd()
        
    def _load_config(self):
        """
        Loads configuration from .env files
        """
        # Load deploy-tools.env first
        deploy_tools_env = self.deploy_tools_dir / "deploy-tools.env"
        if deploy_tools_env.exists():
            print(f"📝 Loading configuration from {deploy_tools_env}")
            load_dotenv(deploy_tools_env)
            
            # Check if a custom path for the .env file is specified
            project_env_path = os.getenv("PROJECT_ENV_PATH")
            if project_env_path:
                env_path = self.deploy_tools_dir / project_env_path
                if env_path.exists():
                    print(f"📝 Loading configuration from {env_path}")
                    load_dotenv(env_path)
                else:
                    print(f"⚠️ Specified .env file not found: {env_path}")
        
        # Try to load .env from the project root
        project_env = self.project_root / ".env"
        if project_env.exists():
            print(f"📝 Loading configuration from {project_env}")
            load_dotenv(project_env)
            
        # Update configuration with loaded environment variables
        for key in self.config.keys():
            env_value = os.getenv(key)
            if env_value is not None:
                self.config[key] = env_value
                
    def get(self, key: str, default: Any = None) -> Any:
        """
        Gets a configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key is not found
            
        Returns:
            The configuration value or default value
        """
        return self.config.get(key, default)
        
    def __getitem__(self, key: str) -> Any:
        """
        Allows accessing configuration using index syntax:
        config["REMOTE_SSH"]
        
        Args:
            key: Configuration key
            
        Returns:
            The configuration value
            
        Raises:
            KeyError: If the key doesn't exist
        """
        if key in self.config:
            return self.config[key]
        raise KeyError(f"Configuration key not found: {key}")
        
    def display(self):
        """
        Displays the current configuration
        """
        print("\n🔧 Loaded configuration:")
        for key, value in self.config.items():
            # Hide passwords
            if "PASS" in key or "PASSWORD" in key:
                display_value = "********"
            else:
                display_value = value
            print(f"   - {key}: {display_value}")
        print()
        
# Global configuration instance
_config: Optional[Config] = None

def get_config() -> Config:
    """
    Gets the global configuration instance.
    If it doesn't exist yet, creates it.
    
    Returns:
        Config: Configuration instance
    """
    global _config
    if _config is None:
        _config = Config()
    return _config 