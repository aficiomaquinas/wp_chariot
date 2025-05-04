# Configuration Files

This document provides a detailed guide to the configuration files used by wp_chariot.

## Overview

wp_chariot uses two main configuration files:

1. **config.yaml**: Global configuration that applies to all sites
2. **sites.yaml**: Site-specific configuration for each WordPress site

Both files use the YAML format, which is easy to read and edit manually.

## Configuration Structure

### Configuration Hierarchy

wp_chariot follows this hierarchy to determine the final configuration:

1. Internal default values
2. Global configuration from `config.yaml`
3. Site-specific configuration from `sites.yaml`
4. Command-line arguments

Lower levels take precedence over higher ones.

## config.yaml File

This file contains global settings that apply to all sites. It's used to establish default behaviors and security policies.

### Complete Example of config.yaml

```yaml
# Global configuration for WordPress Deploy Tools
# This configuration applies to ALL sites

# WP-CLI configuration
wp_cli:
  memory_limit: "512M"  # PHP memory limit for WP-CLI operations

# Security configuration
security:
  production_safety: "enabled"  # Protection against accidentally overwriting production
  backups: "enabled"  # Always create backups before critical operations

# Patch and synchronization configuration
sync:
  allow_empty_diff: true  # Allow continuing even with empty diff
  allow_deletions: false  # Whether to allow deletions during synchronization (dangerous)
  check_conflicts: true   # Always check for conflicts with local changes

# Default exclusions (are merged with site-specific exclusions)
exclusions:
  # Cache and optimization directories
  litespeed: "wp-content/litespeed/*"
  cache: "wp-content/cache/*"
  wpsc-cache: "wp-content/wp-super-cache/*"
  w3c: "wp-content/w3tc-cache/*"
  
  # Cache and configuration files
  autoptimize: "wp-content/autoptimize/*"
  
  # Security plugins (to avoid conflicts)
  wordfence: "wp-content/wflogs/*"
  
  # Logs and temporary files
  debug.log: "wp-content/debug.log"
  debug: "wp-content/debug/*"
  
  # Backup files
  backup_files: "**/*.bak"

# Protected files by default
protected_files:
  - "wp-config.php"
  - "wp-config-ddev.php"
  - ".gitignore"
  - ".ddev/**/*"
  - "wp-content/plugins/wp-original-media-path/"
```

### config.yaml Sections

#### WP-CLI

```yaml
wp_cli:
  memory_limit: "512M"  # PHP memory limit for WP-CLI operations
```

| Option | Description | Possible Values | Default |
|--------|-------------|-----------------|---------|
| `memory_limit` | PHP memory limit for WP-CLI operations | Any valid PHP memory value | `"512M"` |

#### Security

```yaml
security:
  production_safety: "enabled"  # Protection against accidentally overwriting production
  backups: "enabled"  # Always create backups before critical operations
```

| Option | Description | Possible Values | Default |
|--------|-------------|-----------------|---------|
| `production_safety` | Protection against accidentally overwriting production | `"enabled"`, `"disabled"` | `"enabled"` |
| `backups` | Create backups before critical operations | `"enabled"`, `"disabled"` | `"enabled"` |

#### Synchronization

```yaml
sync:
  allow_empty_diff: true  # Allow continuing even with empty diff
  allow_deletions: false  # Whether to allow deletions during synchronization (dangerous)
  check_conflicts: true   # Always check for conflicts with local changes
```

| Option | Description | Possible Values | Default |
|--------|-------------|-----------------|---------|
| `allow_empty_diff` | Allow continuing with empty diff | `true`, `false` | `true` |
| `allow_deletions` | Allow deletions during synchronization | `true`, `false` | `false` |
| `check_conflicts` | Check for conflicts with local changes | `true`, `false` | `true` |

#### Exclusions

```yaml
exclusions:
  litespeed: "wp-content/litespeed/*"
  cache: "wp-content/cache/*"
  # ... more exclusions ...
```

Each key-value pair defines an exclusion pattern for files that should not be synchronized. The key is a unique identifier and the value is a glob pattern that specifies the files to exclude.

#### Protected Files

```yaml
protected_files:
  - "wp-config.php"
  - "wp-config-ddev.php"
  # ... more protected files ...
```

List of files that should never be overwritten, regardless of synchronization settings.

## sites.yaml File

This file contains the specific configuration for each WordPress site managed with wp_chariot.

### Complete Example of sites.yaml

```yaml
# Multiple site configuration
# This file manages multiple WordPress sites with a single installation
# of wp_chariot.

# Default site (optional) - Used when --site is not specified
default: "mysite1"

# Individual site configuration
sites:
  # First site
  mysite1:
    ssh:
      remote_host: "server1"  # SSH alias in ~/.ssh/config
      remote_path: "/home/user/webapps/site1/"
      local_path: "/home/user/Projects/site1/app/public/"

    security:
      production_safety: "enabled"  # enabled or disabled

    urls:
      remote: "https://site1.com"
      local: "https://site1.ddev.site"

    database:
      remote:
        name: "site1_db"
        user: "site1_user"
        password: "secure-password"
        host: "localhost"

    media:
      url: "https://site1.com/wp-content/uploads/"
      expert_mode: false
      path: "../media"

    ddev:
      base_path: "/var/www/html"
      docroot: "app/public"

    # You can override specific exclusions for this site
    exclusions:
      custom-plugin: "wp-content/plugins/specific-plugin-site1/"
      # You can also disable some global exclusion
      akismet: false  # This will synchronize Akismet on this site

  # Second site
  mysite2:
    ssh:
      remote_host: "server2"
      remote_path: "/var/www/site2/"
      local_path: "/home/user/Projects/site2/public_html/"

    urls:
      remote: "https://site2.com"
      local: "https://site2.ddev.site"

    database:
      remote:
        name: "site2_db"
        user: "site2_user"
        password: "another-secure-password"
        host: "localhost"

    media:
      url: "https://site2.com/wp-content/uploads/"
      # You can customize each site according to its specific needs
      expert_mode: true
      path: "/absolute/path/to/uploads"

    ddev:
      webroot: "/var/www/html"

    # Specific exclusions for this site
    exclusions:
      # Here you can have different exclusions for each site
      my-theme: "wp-content/themes/my-custom-theme/"
```

### sites.yaml Sections

#### Default Site Configuration

```yaml
default: "mysite1"
```

Specifies which site to use when the `--site` option is not provided in commands.

#### Sites Section

```yaml
sites:
  mysite1:
    # Site configuration
  mysite2:
    # Site configuration
```

Each site has its own section with a unique identifier.

#### SSH

```yaml
ssh:
  remote_host: "server1"  # SSH alias in ~/.ssh/config
  remote_path: "/home/user/webapps/site1/"
  local_path: "/home/user/Projects/site1/app/public/"
```

| Option | Description | Required |
|--------|-------------|----------|
| `remote_host` | Host name or SSH alias configured in ~/.ssh/config | Yes |
| `remote_path` | Absolute path to the WordPress root directory on the remote server | Yes |
| `local_path` | Absolute path to the WordPress root directory on the local machine | Yes |

#### Security

```yaml
security:
  production_safety: "enabled"  # enabled or disabled
```

Overrides the global security configuration for this specific site.

#### URLs

```yaml
urls:
  remote: "https://site1.com"
  local: "https://site1.ddev.site"
```

| Option | Description | Required |
|--------|-------------|----------|
| `remote` | Full URL of the site in production | Yes |
| `local` | Full URL of the site in local environment | Yes |

These URLs are used for automatic replacements during database synchronization.

#### Database

```yaml
database:
  remote:
    name: "site1_db"
    user: "site1_user"
    password: "secure-password"
    host: "localhost"
```

| Option | Description | Required |
|--------|-------------|----------|
| `name` | Database name on the remote server | Yes |
| `user` | Username with access to the database | Yes |
| `password` | Database user password | Yes |
| `host` | Database host, usually "localhost" | Yes |

These credentials are used to access the database on the remote server via SSH.

#### Media

```yaml
media:
  url: "https://site1.com/wp-content/uploads/"
  expert_mode: false
  path: "../media"
```

| Option | Description | Possible Values | Default |
|--------|-------------|-----------------|---------|
| `url` | URL of media files in production | Valid URL | Site URL + "/wp-content/uploads/" |
| `expert_mode` | Expert mode for advanced configuration | `true`, `false` | `false` |
| `path` | Path to media files | Relative or absolute path | `"../media"` |

Configures how media files (images, videos, etc.) are handled.

#### DDEV

```yaml
ddev:
  base_path: "/var/www/html"
  docroot: "app/public"
```

| Option | Description | Possible Values | Default |
|--------|-------------|-----------------|---------|
| `base_path` | Base path inside the DDEV container | Valid path | `"/var/www/html"` |
| `docroot` | Document root directory inside base_path | Relative path | `""` |
| `webroot` | (Alternative to base_path+docroot) Complete path | Valid path | `"/var/www/html"` |

Configures how DDEV maps the file system for the local environment.

#### Exclusions

```yaml
exclusions:
  custom-plugin: "wp-content/plugins/specific-plugin-site1/"
  akismet: false  # Disables a global exclusion
```

Defines site-specific exclusion patterns and/or disables global exclusions configured in config.yaml.

## Environment Variables

You can use environment variables to avoid storing sensitive information in configuration files:

```yaml
database:
  remote:
    name: "${REMOTE_DB_NAME}"
    user: "${REMOTE_DB_USER}"
    password: "${REMOTE_DB_PASS}"
    host: "${REMOTE_DB_HOST:-localhost}"
```

Environment variables are replaced using the format `${VARIABLE_NAME}` or `${VARIABLE_NAME:-default_value}`.

## Editing Tips

1. **Use a YAML syntax highlighting editor** to avoid syntax errors.
2. **Keep indentation consistent** (2 spaces is standard).
3. **Don't use tabs**, only spaces.
4. **Quotes are optional** for simple values, but recommended for values with special characters.
5. **Use environment variables** for sensitive credentials.

## Configuration Validation

You can validate your configuration with:

```bash
python cli.py check
```

This command will check the structure and basic values of your configuration and display warnings if there are issues.

## Configuration Examples

### Minimal Configuration

Minimal sites.yaml:
```yaml
default: "my-site"
sites:
  my-site:
    ssh:
      remote_host: "my-server"
      remote_path: "/var/www/html"
      local_path: "/home/user/projects/my-site"
    urls:
      remote: "https://my-site.com"
      local: "https://my-site.ddev.site"
    database:
      remote:
        name: "my_site_db"
        user: "my_site_user"
        password: "my-password"
        host: "localhost"
```

### Configuration with Multiple Environments

To manage multiple environments (development, staging, production):

```yaml
default: "development"
sites:
  development:
    ssh:
      remote_host: "staging-server"
      remote_path: "/var/www/staging"
      local_path: "/home/user/projects/my-site"
    urls:
      remote: "https://staging.my-site.com"
      local: "https://my-site.ddev.site"
    # ... rest of configuration ...
  
  production:
    ssh:
      remote_host: "prod-server"
      remote_path: "/var/www/production"
      local_path: "/home/user/projects/my-site"
    urls:
      remote: "https://my-site.com"
      local: "https://my-site.ddev.site"
    # ... rest of configuration ...
    security:
      production_safety: "enabled"  # Additional protection for production
```

### Configuration with Custom Paths

For WordPress installed in a subdirectory:

```yaml
sites:
  my-site:
    ssh:
      remote_host: "my-server"
      remote_path: "/var/www/html/blog"  # WordPress in /blog subdirectory
      local_path: "/home/user/projects/my-site/blog"
    urls:
      remote: "https://my-site.com/blog"  # URL with subdirectory
      local: "https://my-site.ddev.site"
    # ... rest of configuration ...
    ddev:
      base_path: "/var/www/html"
      docroot: "blog"  # Docroot pointing to subdirectory
```

## Troubleshooting

### Common Issues

1. **YAML syntax error**:
   - Check indentation (use spaces, not tabs)
   - Make sure values with special characters are quoted

2. **Credentials don't work**:
   - Verify environment variables are set correctly
   - Test credentials manually with SSH

3. **Incorrect paths**:
   - Make sure to use absolute paths
   - Verify paths exist on both systems

For more help, see the [Troubleshooting Guide](troubleshooting.md). 