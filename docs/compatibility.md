# Compatibility and Requirements

This document outlines the compatibility requirements for wp_chariot and provides guidance on supported versions of various components.

## System Requirements

### Local Machine Requirements

| Component | Minimum Version | Recommended Version | Notes |
|-----------|----------------|---------------------|-------|
| Operating System | Unix-based | Linux or macOS | Windows with WSL may work but is not officially supported |
| Python | 3.6+ | 3.10+ | Use a version manager like asdf or pyenv |
| DDEV | 1.19+ | Latest | DDEV is used for local WordPress environment |
| Docker | Latest | Latest | Required by DDEV |
| SSH | OpenSSH 7.0+ | Latest | For secure connections to remote servers |
| rsync | 3.1.0+ | Latest | For file synchronization |

### Remote Server Requirements

| Component | Minimum Version | Recommended Version | Notes |
|-----------|----------------|---------------------|-------|
| Operating System | Unix-based | Linux | Most hosting providers use Linux |
| PHP | 7.4+ | 8.0+ | Must meet WordPress requirements |
| MySQL/MariaDB | 5.7+ / 10.3+ | 8.0+ / 10.5+ | Must meet WordPress requirements |
| WP-CLI | 2.5.0+ | Latest | Required for database operations |
| SSH | OpenSSH 7.0+ | Latest | Must allow key-based authentication |
| rsync | 3.1.0+ | Latest | For file synchronization |

### Database Access Requirements

wp_chariot requires direct access to the database on the remote server to perform synchronization operations. Specifically:

| Requirement | Description | Alternative |
|-------------|-------------|-------------|
| MySQL/MariaDB Client | Command-line client installed on the server | None |
| Database User Credentials | Valid username/password with SELECT, INSERT, UPDATE privileges | None |
| Database Export Permissions | Ability to run `mysqldump` on the server | None |
| Database Import Permissions | Ability to run `mysql` command to import data | None |
| Database Access from SSH | MySQL client accessible via SSH session | None |

The tool uses the database credentials configured in `sites.yaml` and connects to the database through SSH using the MySQL/MariaDB client available on the remote server. It does not use any external database connections or drivers.

## WordPress Compatibility

wp_chariot is designed to work with all modern WordPress installations.

| WordPress Version | Compatibility | Notes |
|-------------------|---------------|-------|
| 6.0+ | Full | Fully tested and supported |
| 5.6 - 5.9 | Good | Should work without issues |
| 5.0 - 5.5 | Partial | May work but not fully tested |
| < 5.0 | Limited | Not recommended, may require adjustments |

## DDEV Compatibility

DDEV is used for managing local development environments.

| DDEV Version | Compatibility | Notes |
|--------------|---------------|-------|
| 1.21+ | Full | Fully tested and supported |
| 1.19 - 1.20 | Good | Should work without issues |
| < 1.19 | Limited | Not recommended |

## Plugin Dependencies

### Required Plugins

| Plugin | Purpose | Installation | Compatibility |
|--------|---------|--------------|---------------|
| wp-original-media-path | Media URL configuration | Automatic | All WordPress versions |

### Compatible with Security Plugins

wp_chariot has been tested with the following security plugins:

| Plugin | Compatibility | Notes |
|--------|---------------|-------|
| Wordfence | Good | May need to exclude wp_chariot operations from security rules |
| Sucuri | Good | May need to exclude wp_chariot operations from security rules |
| iThemes Security | Good | May need adjustments for database operations |
| All-In-One WP Security | Good | File modification detection may trigger alerts |

### Compatible with Caching Plugins

| Plugin | Compatibility | Notes |
|--------|---------------|-------|
| W3 Total Cache | Good | May need to clear cache after synchronization |
| WP Super Cache | Good | May need to clear cache after synchronization |
| WP Rocket | Good | May need to clear cache after synchronization |
| LiteSpeed Cache | Good | Exclusion patterns included by default |

## Hosting Environment Compatibility

| Hosting Type | Compatibility | Requirements | Notes |
|--------------|---------------|--------------|-------|
| Shared Hosting | Limited to Good | SSH access, WP-CLI | Performance may vary |
| VPS/Dedicated | Excellent | SSH access | Recommended setup |
| Managed WordPress | Varies | SSH access | Depends on provider's restrictions |
| Cloudways | Excellent | SSH access | Well tested |
| RunCloud | Excellent | SSH access | Well tested |
| Plesk/cPanel | Good | SSH access | Standard configuration |

### Specific Hosting Providers

| Provider | Compatibility | Notes |
|----------|---------------|-------|
| DigitalOcean | Excellent | Ideal for VPS setup |
| Linode | Excellent | Well tested |
| AWS Lightsail | Good | Requires proper SSH configuration |
| Contabo | Excellent | Well tested |
| Hetzner | Excellent | Well tested |
| GoDaddy | Limited | SSH access may be restricted |
| SiteGround | Good | Requires SSH access |
| Kinsta | Limited | May restrict some operations |
| WP Engine | Limited | May restrict some operations |
| Flywheel | Limited | May restrict some operations |

## Configuration Management Tools

wp_chariot can be used alongside these configuration management tools:

| Tool | Compatibility | Integration |
|------|---------------|-------------|
| Git | Excellent | Use exclusion patterns for files managed by Git |
| Composer | Good | Compatible with Composer-managed WordPress |
| Bedrock | Good | Requires custom path configuration |
| WP-CLI | Excellent | Used internally by wp_chariot |
| Ansible | Good | Can be used to automate wp_chariot operations |

## Version Upgrade Notes

### Upgrading Python

When upgrading Python, it's recommended to:

1. Use a version manager (asdf, pyenv)
2. Reinstall dependencies: `pip install -r requirements.txt`
3. Test basic commands before performing critical operations

### Upgrading DDEV

When upgrading DDEV:

1. Follow [official upgrade instructions](https://ddev.readthedocs.io/en/stable/users/install/#update-upgrade)
2. Restart DDEV projects: `ddev restart`
3. Test with wp_chariot: `python ~/wp_chariot/python/cli.py check`

## Troubleshooting Version Conflicts

If you encounter compatibility issues:

1. Check your versions:
   ```bash
   python --version
   ddev --version
   docker --version
   ssh -V
   rsync --version
   ```

2. Update to recommended versions

3. Verify remote server versions:
   ```bash
   ssh your-server "php -v"
   ssh your-server "wp --info"
   ssh your-server "rsync --version"
   ```

For specific compatibility issues, see the [Troubleshooting Guide](troubleshooting.md).

## Future Compatibility

The wp_chariot project aims to maintain compatibility with:

- The latest two major WordPress versions
- The latest DDEV version
- Current LTS versions of major Linux distributions
- Current stable versions of Python (3.6+)

Check the project repository for updates on compatibility changes. 