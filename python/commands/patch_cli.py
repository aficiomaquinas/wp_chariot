#!/usr/bin/env python3
"""
Command line tool for patch management

Allows managing patches for WordPress plugins and themes,
keeping a record of applied patches.
"""

import argparse
import sys
from typing import List, Optional

from commands.patch import (
    add_patch, remove_patch, apply_patch, list_patches, rollback_patch
)

def parse_args(args: Optional[List[str]] = None):
    """
    Parses command line arguments
    
    Args:
        args: List of arguments (if None, uses sys.argv)
        
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Manages patches for WordPress plugins and themes"
    )
    
    # Specific arguments for actions
    parser.add_argument("--add", metavar="FILE_PATH", help="Registers a new patch")
    parser.add_argument("--remove", metavar="FILE_PATH", help="Removes a patch from registry")
    parser.add_argument("--list", action="store_true", help="Lists registered patches")
    parser.add_argument("--rollback", metavar="FILE_PATH", help="Reverts a previously applied patch")
    parser.add_argument("--info", action="store_true", help="Shows detailed information when applying patches")
    parser.add_argument("--dry-run", action="store_true", help="Shows what would be done without making actual changes")
    parser.add_argument("--description", metavar="DESC", help="Patch description (to use with --add)")
    parser.add_argument("--force", action="store_true", help="Force patch application even if versions don't match")
    
    # Positional argument for the file to patch
    parser.add_argument("file_path", nargs="?", help="Relative path to the file to patch")
    
    return parser.parse_args(args)

def main(args: Optional[List[str]] = None) -> int:
    """
    Main entry point for the CLI
    
    Args:
        args: List of arguments (if None, uses sys.argv)
        
    Returns:
        int: Exit code (0 if success, non-zero in case of error)
    """
    args = parse_args(args)
    
    # Process commands
    if args.list:
        # List patches
        list_patches()
        return 0
        
    elif args.add:
        # Add patch
        description = args.description or ""
        success = add_patch(args.add, description)
        return 0 if success else 1
        
    elif args.remove:
        # Remove patch
        success = remove_patch(args.remove)
        return 0 if success else 1
        
    elif args.rollback:
        # Rollback patch
        success = rollback_patch(args.rollback, args.dry_run)
        return 0 if success else 1
        
    elif args.file_path:
        # Apply specific patch
        success = apply_patch(
            args.file_path, 
            args.dry_run, 
            args.info,
            args.force
        )
        return 0 if success else 1
        
    else:
        # Apply all patches
        success = apply_patch(
            None,  # None indicates to apply all patches
            args.dry_run,
            args.info,
            args.force
        )
        return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 