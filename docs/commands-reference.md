This document provides a comprehensive reference for all available wp_chariot commands, organized by category.

`wp-chariot` follows the [Trailercito Principle](idempotency-audit.md) (Mechanistic Safety and Idempotency).

## Command Format

All commands can be executed in several ways:

### Using uv run (recommended)

```bash
# Using the entry point (shortest)
uv run wpchariot <command> [options] [--site sitename] [--yes]
# or
uv run wp_chariot <command> [options] [--site sitename] [--yes]
```

### Using activated virtual environment

```bash
# Activate the environment first
cd ~/wp_chariot/python
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Then run commands
wpchariot <command> [options] [--site sitename]
```

For brevity in the examples below, we'll use `wpchariot` assuming you have activated the virtual environment.

## Quick Reference Table

| Category | Commands |
|----------|----------|
| [Setup](#setup-commands) | `site`, `config`, `check` |
| [Synchronization](#synchronization-commands) | `sync-files`, `sync-db`, `init`, `sync-all` |
| [Backup](#backup-commands) | `backup` |
| [Patch Management](#patch-management-commands) | `patch`, `patch-commit`, `rollback` |
| [Plugin Management](#plugin-management-commands) | `plugin`, `wp` |
| [Cache Management](#cache-management-commands) | `cache install`, `cache flush` |
| [Media](#media-commands) | `media-path` |
| [Verification & Diagnostics](#verification-and-diagnostic-commands) | `diff`, `verify-wp`, `debug-config`, `show-ddev-config` |

## Setup Commands

Commands for configuring and setting up wp_chariot and sites.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `site --init` | Initialize site management system | | `wpchariot site --init` |
| `site --add <name>` | Add a new site | `--from-current`: Use current config | `wpchariot site --add mystore` |
| `site --set-default <name>` | Set a site as default | | `wpchariot site --set-default mystore` |
| `site --list` | List all configured sites | | `wpchariot site --list` |
| `site --remove <name>` | Remove a site from config (doesn't delete files) | | `wpchariot site --remove oldsite` |
| `config --show` | Display current configuration | `--site <name>`: Show for specific site | `wpchariot config --show --site mystore` |
| `config --init` | Create default config files | | `wpchariot config --init` |
| `config --template` | Generate config template with explanatory comments | | `wpchariot config --template` |
| `check` | Verify config and system requirements | `--site <name>`: Check specific site | `wpchariot check --site mystore` |

## Synchronization Commands

Commands for synchronizing files and databases between environments.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `init` | Initialize complete environment | `--with-db`: Include database sync<br>`--with-infra`: Configure infra and media paths<br>`--site <n>`: Specify site<br>`--yes`: Auto-confirm | `wpchariot init --with-db --with-infra --site mystore --yes` |
| `sync-files` | Synchronize files | `--direction`: `from-remote` (default) or `to-remote`<br>`--dry-run`: Simulate without changes<br>`--clean/--no-clean`: Clean excluded files<br>`--skip-backup`: Skip full backup<br>`--site <n>`: Specify site<br>`--yes`: Auto-confirm | `wpchariot sync-files --site mystore --yes` |
| `sync-db` | Synchronize database | `--direction`: `from-remote` (default) or `to-remote` (dangerous)<br>`--dry-run`: Simulate without changes<br>`--site <n>`: Specify site<br>`--yes`: Auto-confirm | `wpchariot sync-db --site mystore --yes` |
| `sync-all` | Synchronize database and files | `--direction`: `from-remote` (default) or `to-remote`<br>`--dry-run`: Simulate without changes<br>`--clean/--no-clean`: Clean excluded files<br>`--skip-backup`: Skip full backup<br>`--with-infra`: Install infrastructure plugins locally<br>`--site <n>`: Specify site<br>`--yes`: Auto-confirm | `wpchariot sync-all --site mystore --yes` |

## Backup Commands

Commands for backing up remote states before dangerous operations.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `backup` | Creates a full backup of the remote WordPress site | `--site <n>`: Specify site<br>`--yes`: Auto-confirm | `wpchariot backup --site mystore` |

## Patch Management Commands

Commands for managing patches to third-party code.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `patch --list` | List registered patches | `--site <name>`: For specific site | `wpchariot patch --list --site mystore` |
| `patch --add <file>` | Register a new patch | `--description <text>`: Add description<br>`--site <name>`: For specific site | `wpchariot patch --add wp-content/plugins/woocommerce/file.php --description "Fix issue" --site mystore` |
| `patch --info <file>` | View patch details | `--site <name>`: For specific site | `wpchariot patch --info wp-content/plugins/woocommerce/file.php --site mystore` |
| `patch --remove <file>` | Remove patch from registry | `--site <name>`: For specific site | `wpchariot patch --remove wp-content/plugins/woocommerce/file.php --site mystore` |
| `patch-commit [file]` | Apply patches to remote | `--dry-run`: Simulate without changes<br>`--force`: Force application<br>`--site <name>`: For specific site<br>`--yes`: Auto-confirm | `wpchariot patch-commit --site mystore --yes` |
| `rollback <file>` | Revert an applied patch | `--dry-run`: Simulate without changes<br>`--site <name>`: For specific site<br>`--yes`: Auto-confirm | `wpchariot rollback wp-content/plugins/woocommerce/file.php --site mystore --yes` |

---

## Plugin Management Commands

Commands for managing WordPress plugins and themes.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `plugin list` | List installed plugins | `--remote`: Check remote server | `wpchariot plugin list --site mystore` |
| `plugin install` | Install a plugin | `--activate`: Activate after install<br>`--remote`: Install on remote | `wpchariot plugin install nginx-helper --activate` |
| `plugin activate` | Activate a plugin | `--remote`: Activate on remote | `wpchariot plugin activate nginx-helper --remote` |
| `wp` | Passthrough to WP-CLI | `--remote`: Run on remote server | `wpchariot wp "cache flush" --remote` |

## Cache Management Commands

Commands for managing persistent object cache and FastCGI page caching.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `cache install` | Idempotent installation of Redis and Nginx Helper | `--remote`: Setup on remote server<br>`--site <name>`: For specific site | `wpchariot cache install --site mystore` |
| `cache flush` | Flush object, FastCGI, and filesystem caches | `--remote`: Purge remote cache<br>`--site <name>`: For specific site | `wpchariot cache flush --remote` |

## Media Commands

Specialized tools for media configuration.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `media-path` | Configure and activate WP Original Media Path plugin | `--remote`: Apply on remote server<br>`--verbose`: Show detailed info<br>`--site <n>`: For specific site | `wpchariot media-path --site mystore` |

## Verification and Diagnostic Commands

Commands for verification, checking differences, and diagnosing config.

| Command | Description | Options | Example |
|---------|-------------|---------|---------|
| `diff` | Show differences between environments | `--patches`: Show only patched files<br>`--site <name>`: For specific site | `wpchariot diff --site mystore` |
| `verify-wp`| Verifies if WordPress is correctly installed | `--remote`: Verify remote server<br>`--site <name>`: For specific site | `wpchariot verify-wp --site mystore` |
| `debug-config` | Shows debugging info about configuration parsing | `--site <name>`: For specific site | `wpchariot debug-config` |
| `show-ddev-config` | Shows connection info for DDEV | `--site <name>`: For specific site | `wpchariot show-ddev-config` |

## Advanced Usage

### Using Environment Variables

You can use environment variables to avoid hardcoding sensitive information in configuration files:

```bash
# Set environment variables
export WP_CHARIOT_DB_PASSWORD="secure_password"

# Use in commands
wpchariot sync-db --site mystore
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
