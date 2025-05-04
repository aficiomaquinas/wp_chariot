"""
Module for showing differences between environments

This module provides functions for displaying file differences
between a remote server and the local environment.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from config_yaml import get_yaml_config
from utils.ssh import SSHClient, run_rsync

# Import the FileSynchronizer class afterwards to avoid circular import
import commands.sync as sync_module

class DiffCommand:
    """
    Class for specific difference commands
    """
    
    def __init__(self):
        """
        Initializes the difference object
        """
        self.synchronizer = sync_module.FileSynchronizer()
        
    def show_diff(self, show_all: bool = False, verbose: bool = False, only_patches: bool = False) -> bool:
        """
        Shows the differences between the remote server and the local environment.
        This method is always read-only and never makes changes.
        
        Args:
            show_all: If True, shows all files without limit
            verbose: If True, shows detailed information
            only_patches: If True, shows only information related to patches
            
        Returns:
            bool: True if the operation was successful, False otherwise
        """
        # We always use dry_run=True because this command is only for showing differences
        return self.synchronizer.diff(dry_run=True, show_all=show_all, verbose=verbose, only_patches=only_patches)

def show_diff(show_all: bool = False, verbose: bool = False, only_patches: bool = False) -> bool:
    """
    Shows the differences between the remote server and the local environment.
    This function is always read-only and never makes changes.
    
    Args:
        show_all: If True, shows all files without limit
        verbose: If True, shows detailed information
        only_patches: If True, shows only information related to patches
        
    Returns:
        bool: True if the operation was successful, False otherwise
    """
    diff_cmd = DiffCommand()
    return diff_cmd.show_diff(show_all=show_all, verbose=verbose, only_patches=only_patches) 