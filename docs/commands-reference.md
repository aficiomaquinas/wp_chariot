# Command Reference

This document provides a comprehensive reference for all available wp_chariot commands, organized by category.

## Command Format

All commands can be executed in several ways:

### Using uv run (recommended)

```bash
# Using the entry point (shortest)
uv run wpchariot <command> [options] [--site sitename]
# or
uv run wp_chariot <command> [options] [--site sitename]

# Using Python directly
uv run python cli.py <command> [options] [--site sitename]
```

### Using activated virtual environment

```bash
# Activate the environment first
cd ~/wp_chariot/python
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Then run commands
wpchariot <command> [options] [--site sitename]
# or
python cli.py <command> [options] [--site sitename]
```

### Using Python directly (legacy)

```bash
python ~/wp_chariot/python/cli.py <command> [options] [--site sitename]
```

For brevity in the examples below, we'll use `wpchariot` or `cli.py` without the full path, assuming you're either using `uv run` or have activated the virtual environment.

## Quick Reference Table

| Category | Commands |
|----------|----------|
| [Setup](#setup-commands) | `site`, `config`, `check` |
| [Synchronization](#synchronization-commands) | `sync-files`, `sync-db`, `init`, `sync-all` |
| [Patch Management](#patch-management-commands) | `patch`, `patch-commit`, `rollback` |
| [Media](#media-commands) | `media-path` |
| [Verification](#verification-commands) | `diff` |

## Setup Commands

Commands for configuring and setting up wp_chariot and sites.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `site --init` | Initialize site management system | | `cli.py site --init` |
| `site --add <name>` | Add a new site | `--from-current`: Use current config | `cli.py site --add mystore` |
| `site --set-default <name>` | Set a site as default | | `cli.py site --set-default mystore` |
| `site --list` | List all configured sites | | `cli.py site --list` |
| `site --remove <name>` | Remove a site from config (doesn't delete files) | | `cli.py site --remove oldsite` |
| `config --show` | Display current configuration | `--site <name>`: Show for specific site | `cli.py config --show --site mystore` |
| `config --init` | Create default config files | | `cli.py config --init` |
| `config --template` | Generate config template with explanatory comments | | `cli.py config --template` |
| `check` | Verify config and system requirements | `--site <name>`: Check specific site | `cli.py check --site mystore` |

## Synchronization Commands

Commands for synchronizing files and databases between environments.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `init` | Initialize complete environment | `--with-db`: Include database sync<br>`--with-media`: Configure media paths<br>`--site <n>`: Specify site | `cli.py init --with-db --with-media --site mystore` |
| `sync-files` | Synchronize files | `--direction`: `from-remote` (default) or `to-remote`<br>`--dry-run`: Simulate without changes<br>`--clean/--no-clean`: Clean excluded files<br>`--skip-backup`: Skip full backup<br>`--site <n>`: Specify site | `cli.py sync-files --site mystore` |
| `sync-db` | Synchronize database | `--direction`: `from-remote` (default) or `to-remote` (dangerous)<br>`--dry-run`: Simulate without changes<br>`--site <n>`: Specify site | `cli.py sync-db --site mystore` |
| `sync-all` | Synchronize database, files, and configure media path | `--direction`: `from-remote` (default) or `to-remote`<br>`--dry-run`: Simulate without changes<br>`--clean/--no-clean`: Clean excluded files<br>`--skip-backup`: Skip full backup<br>`--skip-media`: Skip media path configuration<br>`--site <n>`: Specify site | `cli.py sync-all --site mystore` |

## Patch Management Commands

Commands for managing patches to third-party code.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `patch --list` | List registered patches | `--site <name>`: For specific site | `cli.py patch --list --site mystore` |
| `patch --add <file>` | Register a new patch | `--description <text>`: Add description<br>`--site <name>`: For specific site | `cli.py patch --add wp-content/plugins/woocommerce/file.php --description "Fix issue" --site mystore` |
| `patch --info <file>` | View patch details | `--site <name>`: For specific site | `cli.py patch --info wp-content/plugins/woocommerce/file.php --site mystore` |
| `patch --remove <file>` | Remove patch from registry | `--site <name>`: For specific site | `cli.py patch --remove wp-content/plugins/woocommerce/file.php --site mystore` |
| `patch-commit [file]` | Apply patches to remote | `--dry-run`: Simulate without changes<br>`--force`: Force application<br>`--site <name>`: For specific site | `cli.py patch-commit --site mystore` |
| `rollback <file>` | Revert an applied patch | `--dry-run`: Simulate without changes<br>`--site <name>`: For specific site | `cli.py rollback wp-content/plugins/woocommerce/file.php --site mystore` |

## Media Commands

Commands for media management.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `media-path` | Configure media paths using WP Original Media Path plugin | `--remote`: Apply on remote server<br>`--verbose`: Show detailed info<br>`--site <n>`: For specific site | `cli.py media-path --site mystore` |

## Verification Commands

Commands for verification and checking differences.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `diff` | Show differences between environments | `--patches`: Show only patched files<br>`--site <name>`: For specific site | `cli.py diff --site mystore` |

## Command Shortcuts

For convenience, you can create shell aliases to simplify common commands:

```bash
# Add to your .bashrc or .zshrc
# Using uv run (recommended)
alias wp-chariot="cd ~/wp_chariot/python && uv run wpchariot"
alias wp-init="wp-chariot init --with-db --with-media"
alias wp-sync-files="wp-chariot sync-files"
alias wp-sync-db="wp-chariot sync-db"
alias wp-sync-all="wp-chariot sync-all"
alias wp-media="wp-chariot media-path"

# Or if using activated virtual environment
# alias wp-chariot="cd ~/wp_chariot/python && source .venv/bin/activate && wpchariot"
```

Then use them like:

```bash
wp-init --site mystore
wp-sync-files --site mystore  # Solo sincroniza archivos
wp-sync-all --site mystore    # Sincroniza DB, archivos y configura media path
```

## Advanced Usage

### Using Environment Variables

You can use environment variables to avoid hardcoding sensitive information in configuration files:

```bash
# Set environment variables
export WP_CHARIOT_DB_PASSWORD="secure_password"

# Use in commands
python cli.py sync-db --site mystore
```

### Automation with Cron

For scheduled synchronization, you can use cron jobs:

```bash
# Example cron job for daily database backup using uv
0 2 * * * cd ~/wp_chariot/python && uv run wpchariot sync-db --direction from-remote --site mystore

# Or using activated virtual environment
0 2 * * * cd ~/wp_chariot/python && source .venv/bin/activate && wpchariot sync-db --direction from-remote --site mystore
```

For more detailed information on each command, refer to the specific documentation sections:

- [Synchronization Guide](workflow.md#synchronization)
- [Patch Management](workflow.md#patch-management)
- [Media Path Management](workflow.md#media-path-management) 