#!/usr/bin/env python3
"""
CLI for WordPress Deploy Tools

This script provides a command-line interface for deployment tools.
"""

import os
import sys
import click
from pathlib import Path
import yaml

# Ensure the wp_deploy package can be imported
script_dir = Path(__file__).resolve().parent
if script_dir not in sys.path:
    sys.path.append(str(script_dir))

# Import YAML configuration instead of previous .env based configuration
from config_yaml import get_yaml_config
from commands.sync import sync_files
from commands.diff import show_diff
from commands.database import sync_database
from commands.patch import list_patches, apply_patch, rollback_patch, add_patch, remove_patch
from commands.media import configure_media_path
from commands.backup import create_full_backup

# Define a common option for site
site_option = click.option(
    "--site", 
    help="Site alias to operate on (if multiple are configured)"
)

# Main command group
@click.group()
@click.version_option("0.1.0")
def cli():
    """
    Deployment tools for WordPress.
    
    This set of commands facilitates the development, synchronization
    and deployment of WordPress sites between environments.
    """
    pass

@cli.command("diff")
@click.option("--all", is_flag=True, help="Show all files without limit")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information during execution")
@click.option("--patches", is_flag=True, help="Show only information related to patches")
@site_option
def diff_command(all, verbose, patches, site):
    """
    Shows the differences between the remote server and the local environment.
    This command is always read-only and never makes changes.
    """
    # Select site if necessary
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
        
    success = show_diff(show_all=all, verbose=verbose, only_patches=patches)
    if not success:
        sys.exit(1)
    
@cli.command("sync-files")
@click.option("--dry-run", is_flag=True, help="Simulate operation without making changes")
@click.option("--direction", type=click.Choice(['from-remote', 'to-remote']), 
              default='from-remote', help="Direction of synchronization")
@click.option("--clean/--no-clean", default=True, help="Clean excluded files after synchronization")
@click.option("--skip-backup", is_flag=True, help="Skip creating a full backup before synchronizing from remote")
@click.option("--patch-exclusions", type=click.Choice(['default', 'disabled', 'local-only', 'remote-only', 'both-ways']), 
              default='default', help="Method of excluding registered patches: 'default' uses global configuration, 'disabled' doesn't exclude patches")
@site_option
def sync_files_command(dry_run, direction, clean, skip_backup, patch_exclusions, site):
    """
    Synchronizes files between the remote server and the local environment.
    
    By default, when synchronizing from the remote server (from-remote), 
    a full backup of the local environment is automatically created before 
    making any changes. This backup is independent of the configured exclusions 
    and saves all files.
    
    Use --skip-backup if you don't want to create this full backup.
    
    The system can automatically protect files with registered patches
    during synchronization. Use --patch-exclusions to control this behavior:
    - default: uses the global configuration defined in config.yaml
    - disabled: doesn't automatically exclude files with patches
    - local-only: excludes patches only when synchronizing from remote to local
    - remote-only: excludes patches only when synchronizing from local to remote  
    - both-ways: excludes patches in both directions
    """
    # Select site if necessary
    config = get_yaml_config()
    if not config.select_site(site):
        sys.exit(1)
    
    # If the user has specified a patch exclusion mode different from the default,
    # temporarily modify the configuration
    original_exclusions_mode = None
    if patch_exclusions != 'default':
        # Save the original value
        original_exclusions_mode = config.get("patches", "exclusions_mode", default="local-only")
        # Modify the configuration temporarily
        if "patches" not in config.config:
            config.config["patches"] = {}
        config.config["patches"]["exclusions_mode"] = patch_exclusions
    
    # Execute synchronization
    success = sync_files(direction=direction, dry_run=dry_run, clean=clean, skip_full_backup=skip_backup)
    
    # Restore the original configuration if it was modified
    if original_exclusions_mode is not None:
        config.config["patches"]["exclusions_mode"] = original_exclusions_mode
    
    if not success:
        sys.exit(1)
    
@cli.command("sync-db")
@click.option("--dry-run", is_flag=True, help="Simulate operation without making changes")
@click.option("--direction", type=click.Choice(['from-remote', 'to-remote']), 
              default='from-remote', help="Direction of synchronization")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information during execution")
@site_option
def sync_db_command(dry_run, direction, verbose, site):
    """
    Synchronizes the database between the remote server and the local environment.
    """
    # Select site if necessary
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
        
    success = sync_database(direction=direction, dry_run=dry_run, verbose=verbose)
    if not success:
        sys.exit(1)

@cli.command("media-path")
@click.option("--remote", is_flag=True, help="Apply on the remote server instead of locally")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information during execution")
@site_option
def media_path_command(remote, verbose, site):
    """
    Configures the WordPress media path using the WP Original Media Path plugin.
    
    This command installs and configures the necessary plugin to manage
    custom media paths according to the values defined in config.yaml.
    It maintains a single source of configuration to ensure consistency.
    
    Examples:
      media-path                 # Configure in local environment
      media-path --remote        # Configure in remote server
      media-path --verbose       # Show detailed information
    """
    # Select site if necessary
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
        
    # Get the configuration
    media_config = config.config.get("media", {})
    expert_mode = media_config.get("expert_mode", False)
    
    success = configure_media_path(
        media_url=None,  # Force to get value from config.yaml
        expert_mode=expert_mode,
        media_path=None,  # Force to get value from config.yaml
        remote=remote,
        verbose=verbose
    )
    
    if not success:
        sys.exit(1)
    
@cli.command("patch")
@click.argument("file_path", required=False)
@click.option("--list", is_flag=True, help="List registered patches")
@click.option("--add", is_flag=True, help="Register a new patch")
@click.option("--remove", is_flag=True, help="Remove a patch from the registry")
@click.option("--info", is_flag=True, help="Show detailed information about a patch without applying it")
@click.option("--dry-run", is_flag=True, help="Simulate operation without making changes")
@click.option("--description", "-d", help="Patch description (when registering)")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.option("--config", is_flag=True, help="Show patch system configuration")
@site_option
def patch_command(file_path, list, add, remove, info, dry_run, description, verbose, config, site):
    """
    Manages and registers patches to third-party plugins.
    
    FILE_PATH is the relative path to the file to be patched.
    This command DOES NOT APPLY the patches, it only manages them. To apply
    a patch use the 'patch commit' command.
    
    Examples:
      patch --list -v                     # List patches with detailed information
      patch --add wp-content/plugins/x/y.php  # Register a new patch
      patch --add --description "Fix..." x.php # Register with description
      patch --remove wp-content/plugins/x/y.php # Remove a patch from the registry
      patch --info wp-content/plugins/x/y.php   # View details without applying
      patch --config                      # View patch system configuration
    """
    # Select site if necessary
    config_obj = get_yaml_config(verbose=verbose)
    if not config_obj.select_site(site):
        sys.exit(1)
    
    # Show patch system configuration if requested
    if config:
        from commands.patch import PatchManager
        manager = PatchManager()
        manager.show_config_info(verbose=True)
        return
        
    # Option to list patches
    if list:
        from commands.patch import PatchManager
        manager = PatchManager()
        manager.list_patches(verbose=verbose)
        return
    
    # Verify that a path was provided for add/remove/info
    if (add or remove or info) and not file_path:
        click.echo("❌ You must specify the file path for --add, --remove or --info")
        sys.exit(1)
    
    # Option to add a patch
    if add:
        success = add_patch(file_path, description)
        if not success:
            sys.exit(1)
        return
    
    # Option to remove a patch
    if remove:
        success = remove_patch(file_path)
        if not success:
            sys.exit(1)
        return
    
    # Option to show detailed info
    if info and file_path:
        # Show detailed info about a patch without applying it
        success = apply_patch(file_path=file_path, dry_run=True, show_details=True)
        if not success:
            sys.exit(1)
        return
        
    # If no action was specified but a file was, show info
    if file_path and not (add or remove or info):
        # Show simple info
        success = apply_patch(file_path=file_path, dry_run=True, show_details=False)
        if not success:
            sys.exit(1)
        return
        
    # Default behavior: list registered patches
    list_patches(verbose=verbose)

@cli.command("patch-commit")
@click.argument("file_path", required=False)
@click.option("--dry-run", is_flag=True, help="Simulate operation without making changes")
@click.option("--force", is_flag=True, help="Force application even with modified or different versions")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information during execution")
@site_option
def patch_commit_command(file_path, dry_run, force, verbose, site):
    """
    Applies registered patches to the remote server.
    
    FILE_PATH is the relative path to the file to be patched. If not specified,
    all registered patches will be applied.
    
    This command requires explicit confirmation and verifies the production
    security configuration before applying any changes.
    
    Examples:
      patch-commit wp-content/plugins/x/y.php  # Apply a specific patch
      patch-commit                           # Apply all registered patches
      patch-commit --dry-run                 # View what changes would be made without applying
      patch-commit --force                   # Force application even with modified
    """
    # Select site if necessary
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
        
    # Verify production protection
    production_safety = config.get("security", "production_safety") == "enabled"
    
    if production_safety and not dry_run:
        print("⛔ ERROR: Cannot apply patches with production protection activated.")
        print("   This operation will modify files on the PRODUCTION server.")
        print("   If you are sure what you are doing, you can:")
        print("   1. Use --dry-run to view what changes would be made without applying")
        print("   2. Temporarily disable 'production_safety' in the configuration")
        sys.exit(1)
    
    # Request explicit confirmation to apply patches
    if not dry_run and not force:
        if file_path:
            message = f"⚠️ Are you sure you want to apply the patch to '{file_path}'? This action will modify files on the server."
        else:
            message = "⚠️ Are you sure you want to apply ALL registered patches? This action will modify files on the server."
        
        confirm = input(f"{message} (s/N): ")
        if confirm.lower() != "s":
            print("❌ Operation cancelled.")
            sys.exit(0)
    
    # Apply the patch or patches
    success = apply_patch(file_path=file_path, dry_run=dry_run, show_details=verbose, force=force)
    
    if not success:
        sys.exit(1)

@cli.command("rollback")
@click.argument("file_path")
@click.option("--dry-run", is_flag=True, help="Simulate operation without making changes")
@site_option
def rollback_command(file_path, dry_run, site):
    """
    Reverts a previously applied patch to a plugin or theme.
    
    FILE_PATH is the relative path to the file to be restored from the backup.
    It works only with patches that have been applied previously and are registered
    in the patches.lock.json file.
    """
    # Select site if necessary
    config = get_yaml_config()
    if not config.select_site(site):
        sys.exit(1)
        
    success = rollback_patch(file_path=file_path, dry_run=dry_run)
    if not success:
        sys.exit(1)
    
@cli.command("config")
@click.option("--show", is_flag=True, help="Show current configuration")
@click.option("--repair", is_flag=True, help="Repair configuration if there are structure problems")
@click.option("--output", type=str, default="wp-deploy.yaml", help="Output path for configuration file")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information during execution")
@site_option
def config_command(show, repair, output, verbose, site):
    """
    Manages the configuration of the tools.
    """
    # Select site if necessary
    config = get_yaml_config(verbose=verbose)
    if site and (show or repair) and not config.select_site(site):
        sys.exit(1)
        
    output_path = Path(output)
    
    if show:
        # Show current configuration
        if site:
            print(f"Showing configuration for site: {site}")
        config.display()
    elif repair:
        # Repair configuration
        import shutil
        
        # Make a backup if the file exists
        if output_path.exists():
            backup_path = output_path.with_suffix(".yaml.bak")
            shutil.copy2(output_path, backup_path)
            click.echo(f"✅ Backup created: {backup_path}")
            
        # Read existing template if exists
        existing_config = {}
        if output_path.exists():
            try:
                with open(output_path, 'r') as f:
                    existing_config = yaml.safe_load(f) or {}
            except Exception as e:
                click.echo(f"⚠️ Error reading current configuration: {str(e)}")
                
        # Ensure all main sections exist
        sections = ["ssh", "security", "database", "urls", "media", "exclusions", "protected_files"]
        
        for section in sections:
            if section not in existing_config:
                existing_config[section] = config.config.get(section, {})
                
        # Save repaired configuration
        try:
            with open(output_path, 'w') as f:
                yaml.dump(existing_config, f, default_flow_style=False, sort_keys=False)
            click.echo(f"✅ Repaired configuration saved in {output_path}")
        except Exception as e:
            click.echo(f"❌ Error saving repaired configuration: {str(e)}")
    else:
        click.echo("Usage: wp-deploy config [--show|--repair] [--output ARCHIVO]")

@cli.command("site")
@click.option("--list", is_flag=True, help="List configured sites")
@click.option("--add", is_flag=True, help="Add or update a site")
@click.option("--remove", is_flag=True, help="Remove a site")
@click.option("--set-default", is_flag=True, help="Set a site as default")
@click.option("--init", is_flag=True, help="Initialize site configuration file")
@click.option("--from-current", is_flag=True, help="Use current configuration when adding a site")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.argument("site_alias", required=False)
def site_command(list, add, remove, set_default, init, from_current, verbose, site_alias):
    """
    Manages multiple sites configurations.
    
    This function allows maintaining a single installation of the tools
    that can operate with multiple independent WordPress sites.
    
    Examples:
      site --list                  # List configured sites
      site --add mitienda          # Add a site with alias 'mitienda'
      site --add mitienda --from-current  # Add using current configuration
      site --remove mitienda       # Remove a site
      site --set-default mitienda  # Set site as default
    """
    config = get_yaml_config(verbose=verbose)
    
    # Initialize site configuration file
    if init:
        default = site_alias if set_default else None
        success = config.create_sites_config(default_site=default)
        return
    
    # List configured sites
    if list:
        sites = config.get_available_sites()
        default_site = config.get_default_site()
        
        if not sites:
            print("ℹ️ No sites configured")
            print("   You can add sites with: site --add ALIAS")
            return
        
        print("📋 Configured sites:")
        for alias, site_config in sites.items():
            default_mark = " (default)" if alias == default_site else ""
            print(f"  - {alias}{default_mark}")
            
            # Show details if verbose
            if verbose:
                ssh_config = site_config.get("ssh", {})
                remote = ssh_config.get("remote_host", "Not configured")
                path = ssh_config.get("remote_path", "Not configured")
                print(f"    Server: {remote}")
                print(f"    Path: {path}")
                
                if "urls" in site_config:
                    print(f"    Remote URL: {site_config['urls'].get('remote', 'Not configured')}")
                    print(f"    Local URL: {site_config['urls'].get('local', 'Not configured')}")
                
                print("")
        return
    
    # Verify that a site alias was provided for other operations
    if (add or remove or set_default) and not site_alias:
        print("❌ You must specify an alias for adding, removing or setting as default")
        print("   Example: site --add misitio")
        sys.exit(1)
    
    # Add or update a site
    if add:
        site_config = None
        if from_current:
            site_config = config.config
            print(f"ℹ️ Using current configuration for site '{site_alias}'")
        
        success = config.add_site(site_alias, config=site_config, is_default=set_default)
        if not success:
            sys.exit(1)
        return
    
    # Remove a site
    if remove:
        success = config.remove_site(site_alias)
        if not success:
            sys.exit(1)
        return
    
    # Set site as default
    if set_default and not add:
        # Verify that the site exists
        sites = config.get_available_sites()
        if site_alias not in sites:
            print(f"❌ Error: Site '{site_alias}' not found")
            sys.exit(1)
        
        success = config.add_site(site_alias, config=sites[site_alias], is_default=True)
        if not success:
            sys.exit(1)
        return
    
    # If no option was specified, show help
    print("ℹ️ Usage: site [--list|--add|--remove|--set-default|--init] [ALIAS]")
    print("   For detailed help: site --help")

@cli.command("check")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information during execution")
@site_option
def check_command(verbose, site):
    """
    Verifies system requirements and configuration.
    """
    # Select site if necessary
    config = get_yaml_config(verbose=verbose)
    if site and not config.select_site(site):
        sys.exit(1)
        
    import shutil
    
    click.echo("🔍 Verifying system requirements...")
    
    # Verify that rsync is installed
    if shutil.which("rsync"):
        click.echo("✅ rsync: Installed")
    else:
        click.echo("❌ rsync: Not found")
        
    # Verify that ssh is installed
    if shutil.which("ssh"):
        click.echo("✅ ssh: Installed")
    else:
        click.echo("❌ ssh: Not found")
        
    # Verify that ddev is installed (for sync-db)
    if shutil.which("ddev"):
        click.echo("✅ ddev: Installed")
    else:
        click.echo("⚠️ ddev: Not found (required for database synchronization)")
        
    # Verify SSH configuration
    ssh_config = os.path.expanduser("~/.ssh/config")
    if os.path.exists(ssh_config):
        click.echo("✅ SSH configuration file: Found")
    else:
        click.echo("❌ SSH configuration file: Not found")
        
    # Verify project configuration
    click.echo("\n🔍 Verifying YAML configuration structure...")
    
    # Verify main sections structure
    sections = ["ssh", "security", "database", "urls", "media", "exclusions", "protected_files"]
    all_good = True
    
    for section in sections:
        if section in config.config:
            click.echo(f"✅ Section '{section}': Present")
        else:
            click.echo(f"❌ Section '{section}': Missing")
            all_good = False
    
    if not all_good:
        click.echo("⚠️ Some sections of the configuration are missing. Run 'config --repair' to generate a complete template.")
    
    # Verify that paths exist
    click.echo("\n🔍 Verifying paths and configuration...")
    local_path = Path(config.get("ssh", "local_path"))
    if local_path.exists():
        click.echo(f"✅ Local path: Exists ({local_path})")
    else:
        click.echo(f"❌ Local path: Not exists ({local_path})")
        
    # Verify critical configuration variables
    critical_configs = [
        ("ssh", "remote_host"),
        ("ssh", "remote_path"),
        ("ssh", "local_path"),
    ]
    
    for path in critical_configs:
        if config.get(*path):
            click.echo(f"✅ Configuration {'.'.join(path)}: Configured")
        else:
            click.echo(f"❌ Configuration {'.'.join(path)}: Not configured")
            
    # Verify exclusions
    try:
        exclusions = config.get_exclusions()
        if exclusions:
            click.echo(f"✅ Exclusions: {len(exclusions)} pattern configured")
        else:
            click.echo("⚠️ Exclusions: No pattern configured")
    except Exception as e:
        click.echo(f"❌ Error verifying exclusions: {str(e)}")
        
    # Verify media configuration
    try:
        media_config = config.get_media_config()
        if media_config and media_config.get("url"):
            click.echo(f"✅ Media URL configured: {media_config.get('url')}")
        else:
            click.echo("ℹ️ Media URL not configured (standard path will be used)")
    except Exception as e:
        click.echo(f"❌ Error verifying media configuration: {str(e)}")

@cli.command("debug-config")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information during execution")
@site_option
def debug_config_command(verbose, site):
    """
    Shows debugging information about configuration
    """
    # Select site if necessary
    config = get_yaml_config(verbose=True)  # Force verbose for this command
    if site and not config.select_site(site):
        sys.exit(1)
        
    # Show configuration paths
    print("\n🔍 Debugging configuration information:")
    print(f"  - Detected root directory: {config.project_root}")
    print(f"  - Deploy-tools directory: {config.deploy_tools_dir}")
    
    # Verify configuration files
    global_config_file = config.deploy_tools_dir / "python" / "config.yaml"
    project_config_file = config.project_root / "wp-deploy.yaml"
    sites_config_file = config.deploy_tools_dir / "python" / "sites.yaml"
    
    print("\n📂 Configuration files:")
    if global_config_file.exists():
        print(f"  ✅ Global file: {global_config_file} (EXISTS)")
    else:
        print(f"  ❌ Global file: {global_config_file} (DOES NOT EXIST)")
        
    if project_config_file.exists():
        print(f"  ✅ Project file: {project_config_file} (EXISTS)")
    else:
        print(f"  ❌ Project file: {project_config_file} (DOES NOT EXIST)")
        
    if sites_config_file.exists():
        print(f"  ✅ Sites file: {sites_config_file} (EXISTS)")
        
        # Show site information
        available_sites = config.get_available_sites()
        default_site = config.get_default_site()
        
        if available_sites:
            print(f"     Configured sites: {len(available_sites)}")
            print(f"     Default site: {default_site if default_site else 'None'}")
            print(f"     Current site: {config.current_site if hasattr(config, 'current_site') and config.current_site else 'None'}")
        else:
            print(f"     No sites configured")
    else:
        print(f"  ❌ Sites file: {sites_config_file} (DOES NOT EXIST)")
        
    # Show critical configuration values
    print("\n🔑 REAL VALUES of database configuration (never shown in other commands):")
    db_config = config.config.get('database', {}).get('remote', {})
    print(f"  - Host: {db_config.get('host', 'Not configured')}")
    print(f"  - Name: {db_config.get('name', 'Not configured')}")
    print(f"  - User: {db_config.get('user', 'Not configured')}")
    print(f"  - Password: {'*'*len(db_config.get('password', '')) if 'password' in db_config else 'Not configured'}")
    
    print("\n⚠️  IMPORTANT: For security, when you use normal commands like 'config --show',")
    print("   example values will be shown for sensitive credentials (as seen below).")
    print("   Real values are used internally but not shown to protect credentials.")
    
    # Show complete configuration with masked values
    print("\n🔧 Configuration as shown normally (with hidden credentials):")
    config.display()

@cli.command("init")
@click.option("--with-db", is_flag=True, help="Include database synchronization")
@click.option("--with-media", is_flag=True, help="Configure media URLs")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.option("--dry-run", is_flag=True, help="Simulate operation without making changes")
@site_option
def init_command(with_db, with_media, verbose, dry_run, site):
    """
    Initializes a complete development environment in a single step.
    
    This command performs the following operations in sequence:
    1. Synchronizes files from the remote server
    2. Optionally synchronizes the database
    3. Optionally configures media paths
    
    It is equivalent to executing the following commands in sequence:
    - sync-files
    - sync-db (if --with-db)
    - media-path (if --with-media)
    """
    # Select site if necessary
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
    
    print("🚀 Initializing development environment...")
    
    # 1. Synchronize files
    print("\n📂 Step 1: Synchronization of files")
    success = sync_files(direction="from-remote", dry_run=dry_run, clean=True)
    if not success:
        print("❌ Error in file synchronization")
        sys.exit(1)
    
    # 2. Synchronize database (optional)
    if with_db:
        print("\n🗄️ Step 2: Synchronization of database")
        success = sync_database(direction="from-remote", dry_run=dry_run, verbose=verbose)
        if not success:
            print("❌ Error in database synchronization")
            sys.exit(1)
    
    # 3. Configure media paths (optional)
    if with_media:
        print("\n🖼️ Step 3: Configure media paths")
        media_config = config.config.get("media", {})
        expert_mode = media_config.get("expert_mode", False)
        
        success = configure_media_path(
            media_url=None,
            expert_mode=expert_mode,
            media_path=None,
            remote=False,
            verbose=verbose
        )
        if not success:
            print("❌ Error in media path configuration")
            sys.exit(1)
    
    print("\n✅ Development environment initialized successfully")
    print("🌟 Ready to start working!")

@cli.command()
@click.option('--path', '-p', help='Path inside DDEV container where to search WordPress (obsolete, use sites.yaml)')
@site_option
def verify_wp(path, site):
    """
    Verifies if WordPress is correctly installed.
    
    This command executes 'wp core is-installed' directly 
    using sites.yaml configuration, without depending
    on files .ddev.
    """
    from utils.wp_cli import run_wp_cli
    from config_yaml import get_yaml_config
    import os
    
    # Get sites configuration
    config = get_yaml_config()
    if not config.select_site(site):
        sys.exit(1)
    
    print(f"🔍 Verifying WordPress installation...")
    
    # Get project local directory from configuration
    if 'ssh' not in config.config or 'local_path' not in config.config['ssh']:
        print("❌ Error: No local path configuration found in sites.yaml")
        sys.exit(1)
        
    # Get project local directory directly from sites.yaml
    local_path_str = config.config['ssh']['local_path']
    
    # Get project base directory
    # Example: /home/user/proyecto/app/public -> /home/user/proyecto
    local_path = Path(local_path_str)
    project_dir = local_path.parent.parent  # Up two levels from app/public
    
    print(f"ℹ️ Project DDEV directory: {project_dir}")
    
    # Get wp_path from base_path and docroot parameters (explicitly required)
    if 'ddev' not in config.config:
        print("❌ Error: No ddev section found in sites.yaml")
        sys.exit(1)
        
    # Explicitly require both parameters (fail fast)
    if 'base_path' not in config.config['ddev'] or 'docroot' not in config.config['ddev']:
        print("❌ Error: Complete DDEV configuration not found in sites.yaml")
        print("   Both parameters are required:")
        print("   - ddev.base_path: Base path inside container (e.g. \"/var/www/html\")")
        print("   - ddev.docroot: Docroot directory (e.g. \"app/public\")")
        sys.exit(1)
    
    # Build wp_path with configured parameters
    base_path = config.config['ddev']['base_path']
    docroot = config.config['ddev']['docroot']
    wp_path = f"{base_path}/{docroot}"
    
    # Ignore any path passed by parameter (obsolete)
    if path:
        print("⚠️ Ignoring --path parameter (obsolete)")
        print("   Path is obtained automatically from sites.yaml (ddev.base_path + ddev.docroot)")
    
    print(f"ℹ️ Using WordPress path inside container: {wp_path}")
        
    # Verify that directory exists in the system
    if not project_dir.exists():
        print(f"❌ Error: Project directory '{project_dir}' does not exist")
        sys.exit(1)
    
    # Execute verification with specified path
    code, stdout, stderr = run_wp_cli(
        ["core", "is-installed"],
        project_dir,  # Execute in project directory
        remote=False,
        use_ddev=True,
        wp_path=wp_path
    )
    
    # Show result
    if code == 0:
        print("✅ WordPress is correctly installed and configured")
        sys.exit(0)
    else:
        print("❌ WordPress is not installed or could not be detected")
        if stderr:
            print(f"   Error: {stderr}")
        print(f"   Used path: {wp_path}")
        sys.exit(1)

@cli.command()
@site_option
def show_ddev_config(site):
    """
    Shows the WordPress configuration from sites.yaml.
    
    Useful for diagnosing problems related to WordPress path.
    """
    import subprocess
    import os
    from config_yaml import get_yaml_config
    from pathlib import Path
    
    # Get sites configuration
    config = get_yaml_config()
    if not config.select_site(site):
        sys.exit(1)
    
    print("🔍 Getting configuration from sites.yaml...")
    
    # Verify if DDEV configuration exists in sites.yaml
    if 'ddev' not in config.config:
        print("❌ No DDEV configuration found in sites.yaml")
        sys.exit(1)
    
    # Get project local directory from configuration
    if 'ssh' not in config.config or 'local_path' not in config.config['ssh']:
        print("❌ Error: No local path configuration found in sites.yaml")
        sys.exit(1)
        
    # Show information from sites.yaml
    print("📋 DDEV configuration found in sites.yaml:")
    
    ddev_config = config.config['ddev']
    
    # Verify that both required parameters exist
    if 'base_path' not in ddev_config or 'docroot' not in ddev_config:
        print("❌ Error: Complete DDEV configuration not found in sites.yaml")
        print("   Both parameters are required:")
        print("   - ddev.base_path: Base path inside container (e.g. \"/var/www/html\")")
        print("   - ddev.docroot: Docroot directory (e.g. \"app/public\")")
        sys.exit(1)
    
    # Show information from current configuration
    base_path = ddev_config['base_path']
    docroot = ddev_config['docroot']
    wp_path = f"{base_path}/{docroot}"
    
    print(f"   - base_path: {base_path}")
    print(f"   - docroot: {docroot}")
    print(f"   - Complete WP path: {wp_path}")
    
    # Get project local directory directly from sites.yaml
    local_path_str = config.config['ssh']['local_path']
    local_path = Path(local_path_str)
    
    # Get project base directory
    # Example: /home/user/proyecto/app/public -> /home/user/proyecto
    project_dir = local_path.parent.parent  # Up two levels from app/public
    
    print(f"   - Project local directory: {project_dir}")
    
    # Verify that directory exists
    if not project_dir.exists():
        print(f"   ❌ Project directory does not exist: {project_dir}")
    else:
        print(f"   ✅ Project directory exists")
    
    # Execute ddev describe to show URLs (in the correct directory)
    print("\n📡 DDEV describe:")
    
    try:
        result = subprocess.run(
            ["ddev", "describe"], 
            cwd=project_dir,  # Execute in project directory
            capture_output=True, 
            text=True, 
            check=False
        )
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if ":" in line:
                    print(f"   {line.strip()}")
        else:
            print(f"   ❌ Error: {result.stderr}")
    except Exception as e:
        print(f"   ❌ Error executing ddev describe: {str(e)}")
    
    # Suggest command to verify WordPress
    print(f"\n💡 To verify WordPress, execute:")
    print(f"   python cli.py verify-wp --site={config.current_site}")
        
    # Show URL values
    if 'urls' in config.config and 'remote' in config.config['urls']:
        print(f"\n🌐 Remote URL configured: {config.config['urls']['remote']}")
    if 'urls' in config.config and 'local' in config.config['urls']:
        print(f"🖥️ Local URL configured: {config.config['urls']['local']}")

@cli.command("backup")
@click.option("--output-dir", help="Directory where to save the backup (optional)")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information during backup creation")
@site_option
def backup_command(output_dir, verbose, site):
    """
    Creates a full backup of the local environment.
    
    This command generates a ZIP file with all files from the local environment,
    independently of the exclusions configured for synchronization.
    The backup includes all files, including applied patches.
    
    If no output directory is specified with --output-dir, the backup
    will be saved in the parent directory of the local environment (one level above the WordPress public directory).
    
    Examples:
      backup                      # Creates a backup in the default directory
      backup --output-dir /tmp    # Saves the backup in /tmp
    """
    # Select site if necessary
    config = get_yaml_config(verbose=verbose)
    if not config.select_site(site):
        sys.exit(1)
        
    site_name = config.current_site or "wordpress"
    
    print(f"📦 Creating full backup of local environment for '{site_name}'...")
    
    try:
        backup_path = create_full_backup(site_alias=site, output_dir=output_dir)
        print(f"✅ Backup completed successfully")
        print(f"📂 Backup saved in: {backup_path}")
    except Exception as e:
        print(f"❌ Error creating backup: {str(e)}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

def main():
    """
    Main entry point
    """
    try:
        cli()
    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 