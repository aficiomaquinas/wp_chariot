<p align="center">
  <img src="logo.png" alt="wp_chariot logo" width="500"/>
</p>

# wp_chariot

Spin up idempotent Wordpress dev envs with one click. Sync your changes both ways conveniently. Only SSH required on your server, and only DDEV and Python required on your local machine.
 **PRE-RELEASE: Don't use on important stuff until it gets tested by more people.**

## The Problem wp_chariot Solves: Your Time Is Valuable

In the WordPress development world, especially if you're a freelancer or small agency, you face a constant dilemma: **time vs. money**.

### The WordPress Developer's Vicious Cycle

Do any of these situations sound familiar?

- **You spend a fortune on managed hosting** (Kinsta, WP Engine, Cloudways) but realize you're not getting the expected performance or security guarantees.
- **You want to migrate to more economical solutions** like a VPS with RunCloud, but you're concerned about the potential time that scaling and keeping it updated/patched would take.
- **You need to make quick changes to a client site**, but setting up the entire local environment would take hours. These sites can't have that much downtime either.
- **You have custom components** (plugins, themes, mu-plugins) that make synchronization between local and production a headache, so you perhaps handle those via CI/CD or at least you plan on doing so.
- **You end up working directly in production** because "it's just a small change"... until something goes wrong. Fortunately you had a backup... it's a bad solution, but a solution nontheless.

The reality: **68% of WordPress developers admit to working directly in production at least once a week**, simply because setting up a local environment for each project takes too much time. AI made that up but it's funny and it really makes my point. If you come to think about it, it sounds concerning, and it should be!

Production sites often have transactionality, logs, auto-updates, security plugins, cache plugins. Replicating and dev env can take some time, because it involves several steps, such as dumping the db, importing, syncing the wp files (except the media perhaps, the cache plugins, the security plugins), then replacing the urls for your local machine. This process is pretty darn slow to do manually. This tool uses DDEV to scaffold a working local dev env, a production replica with one click.

WP auto updates sometimes work and sometimes they break your site, but they are a good solution to the very complicated security problem most people are having with production sites these days, which is malware and exploits, which are abundant today. A good way of dealing with the current security problems in production WP sites is Patchstack Community (or with individual protection for important sites or for auto updates on vulnerable software), CI/CD or Wordpress.org versioning for your custom plugins or themes (that you are the author of), and a simple but a bit ugly way of dealing with old plugins/themes that you are not the author of but still have to mantain because they run on your production site: a simple rsync diff with checksum comparison between your local and dev env and just simply keeping track of those patched files in a simple way, that's what wp_chariot is for.

## Why this and not Github Actions or CI/CD? Wasn't this what git was created for? 

Github Actions is a popular CI/CD platform. If you manage a WP site and you, too, are the author of one or several of it's plugins or themes, those should use Git + CI/CD or Wordpress.org versioning for syncing and updating that theme or plugin, ideally. This tool works along your existing CI/CD for your theme or plugin (just add them to the exceptions) but provides tools for automating the sync and most importantly the replicating capability from production to be able to spin up a local dev env quickly with nothing more on the source server than standard UNIX tools (rsync).


## Modern WP Workflow with wp_chariot: Maximum Productivity

1. **Initial setup (one-time)**

```bash
# Clone the tool OUTSIDE your WordPress installation
git clone https://github.com/aficiomaquinas/wp_chariot.git wp_chariot

# Set up your first site
cd wp_chariot/python
# Don't use the system default python, use a version manager like asdf
pip install -r requirements.txt

# Edit your individual sites (a single file with many sites)
cp sites.example.yaml sites.yaml
vim sites.yaml

# Edit your global options (one config for defaults for all sites)
cp config.example.yaml config.yaml
vim config.yaml
```

2. **Daily development (minutes, not hours)**

```bash
# Initialize the complete local dev environment with a single command
python cli.py init --with-db --with-media --site mysitedotcom

# Which is the same as executing the following:
#   Download the files from production with certain exception rules using rsync over SSH
    python cli.py sync-files --site mysitedotcom
#   Dump the database in production, download to local, import and replace the urls.
    python cli.py sync-db --site mysitedotcom
#   Use WP-Original-Media-Path plugin to use the uploads folder from production and save the trouble of serving media from local.
    python cli.py media-path --site mysitedotcom

# Ready to develop! No gigabytes of media, without our excluded plugins/themes/files
# and the cloned database from production (with urls replaced).
```

3. **Secure patch application**

```bash
# suppose we are debugging or patching a security problem of a third-party plugin
vim ~/mysite/wp-content/plugins/problematicvendor/theirplugin/compromised.php

# Register a patch for a problematic plugin, notice the path is relative to the wp install, not absolute
python cli.py patch --add wp-content/plugins/problematicvendor/theirplugin/compromised.php --site mysitedotcom

# get the files diff's from your productive server using rsync --dry-mode along with your exclusions, no need to git track your whole wp install!
python cli.py diff --site mysitedotcom

# and when ready commit to production
python cli.py patch-commit --site mysitedotcom

# get the status of the patches comparing local and remote versions
python cli.py patch --list
```

### Example Configuration Files

#### Global Configuration (config.yaml)

```yaml
# Global configuration for wp_chariot
# This file contains common configuration for all sites

# Global WP-CLI settings
wp_cli:
  memory_limit: "512M"  # Memory limit for PHP in WP-CLI

# Default security parameters
security:
  production_safety: "enabled"  # Protection against overwriting in production
  backups: "enabled"  # Create automatic backups before dangerous operations

# Default exclusions (can be overridden per site)
exclusions:
  # Cache and optimization directories
  cache: "wp-content/cache/"
  litespeed: "wp-content/litespeed/"
  
  # Media (by default do not synchronize uploads)
  default-themes: "wp-content/themes/twenty*"
  uploads-by-year: "wp-content/uploads/[0-9][0-9][0-9][0-9]/"

# Default protected files
protected_files:
  - "wp-config.php"
  - "wp-config-ddev.php"
  - ".gitignore"
  - ".ddev/"
```

#### Site Configuration (sites.yaml)

```yaml
# Multiple site configuration for wp_chariot

# Default site (if multiple are configured)
default: "mystore"

# Individual site configuration
sites:
  mystore:
    ssh:
      remote_host: "my-server"  # SSH alias in ~/.ssh/config
      remote_path: "/path/to/wordpress/on/server/"
      local_path: "/local/path/to/project/app/public/"

    security:
      production_safety: "enabled"  # Protection against overwriting

    urls:
      remote: "https://my-site.com"
      local: "https://my-site.ddev.site"

    database:
      remote:
        name: "db_name"
        user: "db_user"
        password: "secure_password"
        host: "localhost"

    media:
      url: "https://my-site.com/wp-content/uploads/"
      expert_mode: false
      path: "../media"

    # DDEV Configuration
    ddev:
      base_path: "/var/www/html"
      docroot: "app/public"

    # Specific exclusions for this site
    exclusions:
      # Custom plugins that should not be synchronized, many times these are versioned on their own and have their own CI/CD to deploy them to production.
      my-plugin: "wp-content/plugins/my-custom-plugin/" # maybe this plugin is synced over CI/CI and you don't want to sync that at all (neither from-remote nor to-remote).
    protected_files:
      - "wp-content/plugins/my-custom-plugin/" # make sure you also protect that plugin so that you can sync from remote without losing your changes locally.
      # if your plugin/theme (authored by you) is not handled with the CI/CD you can remove it from both the exclusion and protected files, so that you can pull and push it to/from prod.
      
  othersite:
    ssh:
      remote_host: "other-server"
      remote_path: "/var/www/html/othersite/"
      local_path: "/local/path/othersite/app/public/"
    
    # ... similar configuration for each site
```
## Project Structure

```
wp_chariot/
├── logo.png                      # Project logo
├── README.md                     # Project documentation
└── python/                       # Main code directory
    ├── __init__.py               # Package initialization
    ├── cli.py                    # CLI entry point
    ├── config_yaml.py            # YAML configuration management
    ├── config.py                 # Configuration system
    ├── commands/                 # Available commands
    │   ├── __init__.py
    │   ├── diff.py               # Show differences
    │   ├── sync.py               # File synchronization
    │   ├── database.py           # Database synchronization
    │   ├── patch.py              # Patch application
    │   ├── patch_cli.py          # Patch CLI
    │   ├── patch_utils.py        # Patch CLI utilities
    │   ├── wp_cli.py             # WP CLI command utilities
    │   └── media.py              # Media path management
    ├── sync/                     # Synchronization modules
    │   ├── __init__.py
    │   └── files.py              # File synchronization 
    ├── utils/                    # Shared utilities
    │   ├── __init__.py
    │   ├── ssh.py                # SSH operations
    │   ├── wp_cli.py             # WP-CLI operations
    │   └── filesystem.py         # Filesystem operations
    ├── config.yaml               # Global configuration for all sites
    ├── sites.yaml                # Specific configuration for each site
    ├── config.example.yaml       # Example global configuration
    ├── sites.example.yaml        # Example site configuration
    ├── patches-*.lock.json       # Applied patches registry (per site)
    ├── setup.py                  # Installation configuration
    └── requirements.txt          # Dependencies
```

### Multiple Site Management

The system allows operating with multiple WordPress sites from a single installation of the tools, which:

1. **Centralizes Updates**: Maintaining a single copy of the tools allows for easy updates
2. **Avoids Duplication**: It is not necessary to clone the project in each WordPress site
3. **Location Flexibility**: The project can be in any location on your system, not necessarily within the DDEV directory of each site

### Benefits of this Approach

This workflow solves one of the biggest challenges in WordPress development: the time between deciding to work on a site and having a functional local environment. With this method:

- Setup time is drastically reduced (from hours to minutes)
- No need to download gigabytes of media files that are not part of development
- The database and files exactly reflect production, eliminating surprises
- Changes and patches are applied in a controlled and traceable manner
- Necessary modifications in production can be made safely and consistently
- You can work with multiple sites from a single installation of the tools

In essence, these tools allow developers to focus on creating real value for their clients instead of dealing with repetitive configuration and synchronization tasks.

## Main Features

- **Bidirectional synchronization** of files between local and remote environment
- **Database synchronization** with automatic URL and configuration adjustment
- **Advanced patch management system** for modifying third-party plugins
- **Media path management** for working with CDNs or external media servers
- **Security protections** to prevent accidental changes in production
- **Centralized configuration** through YAML files with environment support
- **Intuitive command-line interface** with commands and subcommands

## Patch System and Synchronization

### Patch Files and Backups (.bak)

When applying patches to third-party plugins or themes, the system:

1. Creates backups (files with .bak extension) of the original files
2. Saves information about patches in a lock file (patches-{sitename}.lock.json)
3. Allows applying and reverting patches safely

**Important:** Backup files (.bak) are configured to be excluded from the remote → local synchronization to prevent losing local patches. This is configured with the following exclusion in sites.yaml:

```yaml
exclusions:
  # Patch and backup files
  backup_files: "**/*.bak"
```

### wp-original-media-path Plugin

The wp-original-media-path plugin is used to configure media URLs in WordPress. To avoid issues with this plugin:

1. The plugin has been added to the protected files in sites.yaml:
   ```yaml
   protected_files:
     - "wp-content/plugins/wp-original-media-path/"
   ```

2. Pauses have been added in the installation/activation process to avoid race conditions in DDEV:
   - Pause after starting DDEV
   - Pause before installing the plugin
   - Pause between installation attempts
   - Pause before activating the plugin

### Recommended Workflow for Patches

```bash
# 1. Register a file to patch
python cli.py patch --add wp-content/plugins/woocommerce/templates/checkout.php --description "Fixes issue X"

# 2. Edit the file locally and test the changes

# 3. Verify the patch status
python cli.py patch --list

# 4. Apply the patch to the remote server
python cli.py patch-commit

# 5. If necessary, revert the patch
python cli.py rollback wp-content/plugins/woocommerce/templates/checkout.php
```

## Local dev env requirements

- UNIX based OS (Linux/MacOs) with rsync installed (usually comes installed by default)
- DDEV installed
- Python 3.6 or higher installed (preferably with a version manager like asdf)
- SSH configured with access to the remote server in your ~/.ssh/config file (used/referenced by the alias on your wp_chariot config file)

## Remote server requirements

- UNIX based server with php, wp-cli and rsync installed (most have that installed out of the box)
- User with regular access to sql and site files
- Supports different or same servers for different sites

### The True Hidden Cost

While Enterprise solutions like Pantheon ($1,000+ monthly 🤮) or complex atomic hosting providers solve these problems, most freelancers and small agencies cannot justify that expense.

The real cost isn't just measured in money, but in lost hours:

- **2-3 hours** to set up a complete local environment (for each site)
- **30-60 minutes** to manually synchronize changes
- **4-8 hours** to recover from a production error
- **Entire days** lost per year in these repetitive processes

### How wp_chariot Transforms Your Workflow

wp_chariot was born as a direct solution to this problem, allowing you to:

1. **Reduce setup time** from hours to minutes
2. **Synchronize safely and bidirectionally** between environments
3. **Work with controlled patches** for third-party code
4. **Avoid downloading gigabytes of unnecessary media files**
5. **Automate repetitive processes** that consume your valuable time

## A Real Case: From Cloudways to Your Own Server

A developer with 10 sites on Cloudways ($100-$250/month) can migrate to a VPS on Contabo/Hetzner ($20-$40/month) + RunCloud Basic ($8/month). The savings: **up to $2,400 per year**.

However, migration and maintenance present technical challenges:
- How do you maintain backup systems?
- How do you synchronize your development environments?
- How do you safely apply patches to third-party plugins?

wp_chariot solves these problems, allowing you to:

1. **Develop professionally** in isolated local environments
2. **Apply patches in a controlled manner** to code that isn't yours
3. **Synchronize bidirectional changes** between development and production
4. **Maintain a change log** to facilitate future updates

## Freeing Your Time for What Really Matters

With the arrival of AI tools like Cursor, you can solve technical problems faster than ever before. However, a critical piece of the modern workflow is missing: efficient synchronization between environments.

wp_chariot complements these tools, providing you with:

- **An extra billable hour every day** by eliminating repetitive manual tasks
- **Greater confidence in your solutions** by testing everything in isolated environments
- **Independence from expensive providers** without sacrificing professional workflows
- **Flexibility to use the best tools** without arbitrary restrictions

## Democratizing Professional Development

While large agencies spend thousands on infrastructure, wp_chariot provides you with the same capabilities at a fraction of the cost, allowing you to:

- **Compete with large agencies** using the same professional standards
- **Scale your business** without multiplying your infrastructure expenses
- **Offer superior technical support** without sacrificing your personal time
- **Diversify your services** without the pressure of high fixed costs

The time you save not only translates into money but into the ability to take on more projects, deliver higher quality solutions, and finally, have a better quality of life.

## Philosophy and Purpose

This project was born from the need to democratize the development and maintenance of WordPress-based websites, especially for small businesses and independent developers, under three fundamental principles:

### Digital Autonomy

In a world where dependence on SaaS platforms and multinational service providers is growing exponentially, these tools help maintain sovereignty over digital infrastructure. The ability to easily migrate between hosting providers, efficiently manage environments, and maintain complete control over data becomes critical for sustainable digital survival.

### Economic Accessibility

The pricing models of many commercial solutions are designed for first-world economies, leaving out small entrepreneurs and businesses from emerging economies. This project allows implementing professional and secure workflows without the need for costly subscriptions, making it possible for small businesses to compete digitally without compromising their finances.

### Operational Efficiency

Manual management of WordPress environments consumes valuable time that could be invested in creating real value for clients. These tools automate repetitive synchronization, configuration, and maintenance tasks, allowing developers and business owners to focus on what really matters: creating and growing their projects.

In essence, this project belongs to a new generation of open source tools that, powered by technological advances such as AI, seek to return technological control to independent individuals and businesses, following the tradition of the free software movement and its vision of a more open and accessible internet for all.

### Single Configuration and Idempotence

This project is based on some fundamental engineering principles:

1. **Split Configuration System**: The project operates with two complementary configuration files:
    - `config.yaml`: Contains global configuration applicable to all sites
    - `sites.yaml`: Defines the specific configuration for each individual site
   This approach allows managing multiple WordPress sites from a single installation of the tools, eliminating inconsistencies and facilitating adaptation to different projects.

2. **Idempotence**: The commands are designed to produce the same final result regardless of how many times they are executed. This allows automating operations without worrying about side effects or intermediate states.

3. **Fail Fast**: The codebase embraces the "fail fast" philosophy:
    - Fail explicitly when critical configuration is missing, rather than guessing or inferring values
    - Avoid "magic" default values that may cause unexpected behaviors
    - Maintain idempotency: same input must always produce the same output
    - Provide clear error messages that explain why something failed and how to fix it

This approach:
1. **Improves Debugging**: Errors are immediately visible and diagnoses are more straightforward
2. **Reduces Silent Failures**: No more hidden side effects or unexpected behaviors
3. **Enforces Proper Configuration**: Users must provide required values explicitly
4. **Makes Systems More Predictable**: Behavior is consistent and well-defined at all times

## Configuration Philosophy and Workflow

Each site can have its own complete and independent configuration, and is accessed through a unique alias:

```bash
# Initialize the site system
python ~/wp_chariot/python/cli.py site --init

# Add a site with the current configuration
python ~/wp_chariot/python/cli.py site --add mystore --from-current 

# Add another site (will be created with default configuration that you should edit)
python ~/wp_chariot/python/cli.py site --add othersite

# Set a site as default
python ~/wp_chariot/python/cli.py site --set-default mystore

# List available sites
python ~/wp_chariot/python/cli.py site --list
```

To run any command on a specific site, simply add the `--site` option:

```bash
# Synchronize files for a specific site
python ~/wp_chariot/python/cli.py sync-files --site mystore

# View system information for a site
python ~/wp_chariot/python/cli.py check --site othersite
```

### Recommended Workflow

The typical workflow to start developing on an existing WordPress site is:

#### 1. Initial Setup (one-time)


```bash
# Clone the tools outside your WordPress projects
git clone https://github.com/aficiomaquinas/wp_chariot.git ~/wp_chariot
cd ~/wp_chariot/python
# Don't use the system default python, use a version manager like asdf
pip install -r requirements.txt

# Create a site and configure it
python cli.py site --init
python cli.py site --add mystore
```

Edit the site configuration file (`sites.yaml`) with:
- Remote server SSH connection data
- Local and remote project paths
- Database configuration
- Exclusion patterns for synchronization (especially `wp-content/uploads/*`)
- Media URL to avoid synchronizing them locally

#### 2. Environment Replication (daily development)

The entire process can be done with a single command:

```bash
# Initialize complete environment (files, DB, and media configuration)
python ~/wp_chariot/python/cli.py init --with-db --with-media --site mystore
```

Or step by step:

```bash
# 1. Synchronize files (excluding media and our custom code)
python ~/wp_chariot/python/cli.py sync-files --site mystore

# 2. Synchronize database
python ~/wp_chariot/python/cli.py sync-db --site mystore

# 3. Configure media paths to use production ones
python ~/wp_chariot/python/cli.py media-path --site mystore

# 4. Verify differences
python ~/wp_chariot/python/cli.py diff --site mystore
```

At this point, you have a fully functional local environment that:
- Contains all WordPress files, plugins, and themes from production
- Has the same database configuration and content
- Uses media directly from the production server
- Is ready for development without having downloaded gigabytes of media files

### Complete Automation

This entire process could be automated in a single command thanks to the idempotence of the system. The `init` command allows setting up a complete development environment with a single click, saving valuable time and eliminating human errors in the configuration process.

> 🔍 **Note**: The principle of idempotence is key in this flow. Even if a step fails or is interrupted, you can simply run the same command again and it will continue from where it left off, without unwanted side effects.

#### 3. Development and Patches

From here, you can:
- Develop your own plugins and themes that will reside in their own repositories
- Apply patches to third-party plugins as needed
- Test modifications locally before applying them in production

```bash
# Register a patch for a plugin that needs modification
python ~/wp_chariot/python/cli.py patch --add wp-content/plugins/woocommerce/file-to-modify.php --site mystore

# Edit the file locally

# When ready, apply the patch in production
python ~/wp_chariot/python/cli.py patch-commit --site mystore
```

## Configuration

The system uses YAML configuration files to manage all necessary parameters.

### Configuration Management

The configuration can be customized through the following commands:

```bash
# Show current configuration (global + default site)
python ~/wp_chariot/python/cli.py config --show

# Show configuration for a specific site
python ~/wp_chariot/python/cli.py config --show --site mystore

# Create default configuration files
python ~/wp_chariot/python/cli.py config --init

# Generate a configuration template with explanatory comments
python ~/wp_chariot/python/cli.py config --template

# Verify configuration and system requirements
python ~/wp_chariot/python/cli.py check

# Verify a specific site
python ~/wp_chariot/python/cli.py check --site mystore
```

### Site Management

The multi-site system allows managing several WordPress sites:

```bash
# Initialize the site system
python ~/wp_chariot/python/cli.py site --init

# Add a site with the current configuration
python ~/wp_chariot/python/cli.py site --add mystore --from-current

# Add a new site (with default configuration)
python ~/wp_chariot/python/cli.py site --add othersite

# Set a site as default
python ~/wp_chariot/python/cli.py site --set-default mystore

# List all configured sites
python ~/wp_chariot/python/cli.py site --list

# Remove a site from the configuration (does not delete files)
python ~/wp_chariot/python/cli.py site --remove othersite
```

## Available Commands

### Verification and Differences

```bash
# Verify configuration and requirements for the default site
python ~/wp_chariot/python/cli.py check

# Verify a specific site
python ~/wp_chariot/python/cli.py check --site mystore

# Show differences between remote server and local (default site)
python ~/wp_chariot/python/cli.py diff

# Show differences for a specific site
python ~/wp_chariot/python/cli.py diff --site mystore

# Show only differences in patched files
python ~/wp_chariot/python/cli.py diff --patches

# Show patch differences for a specific site
python ~/wp_chariot/python/cli.py diff --patches --site mystore
```

### File Synchronization

```bash
# Synchronize files from remote server to local environment (default site)
python ~/wp_chariot/python/cli.py sync-files

# Synchronize files for a specific site
python ~/wp_chariot/python/cli.py sync-files --site mystore

# Synchronize files from local environment to remote server
python ~/wp_chariot/python/cli.py sync-files --direction to-remote

# Synchronize local files to remote for a specific site
python ~/wp_chariot/python/cli.py sync-files --direction to-remote --site mystore

# Simulate synchronization without making changes
python ~/wp_chariot/python/cli.py sync-files --dry-run --site mystore
```

### Database Synchronization

```bash
# Synchronize database from remote server to local environment (default site)
python ~/wp_chariot/python/cli.py sync-db

# Synchronize database for a specific site
python ~/wp_chariot/python/cli.py sync-db --site mystore

# Synchronize database from local environment to remote server (DANGEROUS)
python ~/wp_chariot/python/cli.py sync-db --direction to-remote

# Simulate synchronization without making changes
python ~/wp_chariot/python/cli.py sync-db --dry-run --site mystore
```

### Patch Management

```bash
# List registered patches (default site)
python ~/wp_chariot/python/cli.py patch --list

# List patches for a specific site
python ~/wp_chariot/python/cli.py patch --list --site mystore

# Register a new patch
python ~/wp_chariot/python/cli.py patch --add wp-content/plugins/woocommerce/woocommerce.php --site mystore

# Register a patch with description
python ~/wp_chariot/python/cli.py patch --add --description "Error correction" wp-content/plugins/woocommerce/woocommerce.php --site mystore

# View detailed information about a patch
python ~/wp_chariot/python/cli.py patch --info wp-content/plugins/woocommerce/woocommerce.php --site mystore

# Remove a patch from the registry
python ~/wp_chariot/python/cli.py patch --remove wp-content/plugins/woocommerce/woocommerce.php --site mystore
```

### Patch Application

```bash
# Apply a specific patch
python ~/wp_chariot/python/cli.py patch-commit wp-content/plugins/woocommerce/woocommerce.php --site mystore

# Apply all registered patches
python ~/wp_chariot/python/cli.py patch-commit --site mystore

# Simulate patch application without making changes
python ~/wp_chariot/python/cli.py patch-commit --dry-run --site mystore

# Force application even with modified files
python ~/wp_chariot/python/cli.py patch-commit --force --site mystore
```

### Patch Rollback

```bash
# Revert an applied patch
python ~/wp_chariot/python/cli.py rollback wp-content/plugins/woocommerce/woocommerce.php --site mystore

# Simulate rollback without making changes
python ~/wp_chariot/python/cli.py rollback wp-content/plugins/woocommerce/woocommerce.php --dry-run --site mystore
```

### Media Path Management

```bash
# Configure media paths according to config.yaml (default site)
python ~/wp_chariot/python/cli.py media-path

# Configure media paths for a specific site
python ~/wp_chariot/python/cli.py media-path --site mystore

# Apply configuration on the remote server
python ~/wp_chariot/python/cli.py media-path --remote --site mystore

# Show detailed information during configuration
python ~/wp_chariot/python/cli.py media-path --verbose --site mystore
```

Media path management allows configuring custom URLs for WordPress media files, facilitating:

- Used in combination with exclusions (for example wp-content/uploads/{year}) reduces the time it takes to make the local development environment work.
- Use CDNs or external media servers to improve performance and reduce the startup time of the local development environment, avoiding having to synchronize media that can be very heavy directories and that are generally static and not usually involved with the operation of the site (generally they do not have scripts).
- Maintain media files in locations independent of code
- Configure development environments to work with media from production
- Implement optimal storage strategies according to budget and needs

The command automatically installs and configures the "WP Original Media Path" plugin using the values defined in the `media` section of the configuration file:

```yaml
media:
  url: "https://media.mydomain.com/wp-content/uploads/"  # URL for media files
  expert_mode: false  # Activate expert mode for custom physical paths
  path: "/absolute/path/to/uploads"  # Physical path (only with expert_mode: true)
```

## Development and Refactoring Plan

The wp_chariot codebase requires ongoing refactoring to improve maintainability and reduce technical debt. The following issues have been identified and need to be addressed:

### Current Issues and Refactoring Tasks

1. **Circular Dependencies**
   - `config_yaml.py` and `utils/filesystem.py` have a circular dependency:
     - `utils/filesystem.py` has a `create_backup()` function that uses a `config` parameter and calls `get_protected_files()`
     - Multiple modules import both, creating tight coupling
   - **Proposed Solution**:
     - Refactor `create_backup()` to accept a list of protected files instead of a config object?
     - Create a dedicated configuration interface or module that doesn't depend on filesystem utilities
     - Use dependency injection more explicitly throughout the codebase

2. **Large Files**
   - Several files exceed 500 lines, making maintenance difficult:
     - `commands/patch.py` (1410 lines)
     - `config_yaml.py` (857 lines)
     - `commands/database.py` (743 lines)
     - `cli.py` (714 lines)
     - `commands/sync.py` (686 lines)
     - `utils/wp_cli.py` (622 lines)
   - **Proposed Solution**:
     - Split large files into smaller, more focused modules
     - Extract reusable logic into utility classes
     - Create specialized classes instead of large procedural modules

3. **Duplicated Code**
   - SSH/DDEV execution logic duplicated across files
   - Similar command execution patterns repeated in many places
   - WP-CLI command execution contains significant duplication
   - **Proposed Solution**:
     - Create dedicated command execution factories
     - Implement common patterns as reusable utilities
     - Use composition instead of copying code

4. **Configuration Management**
   - Default values defined in utility modules instead of configuration
   - `get_protected_files()` and `get_default_exclusions()` should be part of configuration
   - **Proposed Solution**:
     - Centralize all configuration-related logic
     - Create a clean separation between configuration and utilities
     - Implement proper configuration interfaces

### Implementation Plan

1. **Phase 1: Dependency Resolution**
   - Resolve circular dependencies between configuration and filesystem utilities
   - Create proper abstractions for command execution
   - Implement consistent error handling

2. **Phase 2: Code Organization**
   - Split large files into smaller, more focused modules
   - Extract reusable logic into utility classes
   - Implement proper separation of concerns

3. **Phase 3: Configuration Redesign**
   - Redesign configuration management
   - Create better interfaces for accessing configuration
   - Implement proper validation for configuration values

4. **Phase 4: Testing**
   - Add unit tests for critical functionality
   - Implement integration tests for command execution
   - Create end-to-end tests for common workflows

### Benefits of Refactoring

- **Improved Maintainability**: Smaller, more focused files are easier to understand and modify
- **Better Testability**: Clean interfaces allow for better unit testing
- **Reduced Complexity**: Clear separation of concerns simplifies the codebase
- **Enhanced Reliability**: Proper error handling and validation improve stability
- **Easier Onboarding**: Well-organized code is easier for new contributors to understand

## License

This project is free software under the [MIT](LICENSE) license.
