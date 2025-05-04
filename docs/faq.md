# Frequently Asked Questions

## General Questions

### What is wp_chariot?
wp_chariot is a tool that allows WordPress developers to quickly set up local development environments that mirror production sites, synchronize changes bidirectionally, and manage patches to third-party code in a controlled manner.

### Is wp_chariot free to use?
Yes, wp_chariot is free and open source software, released under the MIT license.

### Can I use wp_chariot with multiple WordPress sites?
Yes, wp_chariot is specifically designed to manage multiple WordPress sites from a single installation, with each site having its own configuration.

### Does wp_chariot work with any hosting provider?
Yes, as long as you have SSH access to your server. It works with VPS providers, shared hosting (with SSH), dedicated servers, and even managed WordPress hosts that provide SSH access.

## Installation & Configuration

### What are the system requirements for wp_chariot?
Local machine: Unix-based OS (Linux/macOS), Python 3.6+, DDEV, SSH, and rsync.  
Remote server: SSH access, WP-CLI, and rsync.

### Can I use wp_chariot on Windows?
wp_chariot is primarily designed for Unix-based systems. While it might work on Windows using WSL (Windows Subsystem for Linux), it's not officially supported.

### Do I need to install wp_chariot in my WordPress directory?
No, you should install wp_chariot OUTSIDE your WordPress installation. It's designed to be a standalone tool that can manage multiple WordPress sites.

### How do I configure SSH for wp_chariot?
wp_chariot uses your system's SSH configuration. You should have your SSH keys set up and ideally have an alias in your `~/.ssh/config` file for your remote server.

## Usage

### How long does it take to set up a local environment with wp_chariot?
Setting up a site typically takes just a few minutes, compared to hours with manual methods. The exact time depends on the size of your WordPress installation and your internet connection speed.

### Does wp_chariot download all media files from my production site?
No, one of wp_chariot's key features is that it can configure your local environment to use media files directly from production, saving you from downloading gigabytes of data.

### Is it safe to use wp_chariot with production sites?
wp_chariot has built-in safety features to prevent accidental changes to production. However, as with any tool that can modify production data, you should use it with caution and always have backups.

### Can I use wp_chariot with version-controlled plugins and themes?
Yes, you can configure wp_chariot to exclude certain directories (like your custom plugins or themes) that are already version-controlled or deployed via CI/CD.

## Synchronization

### Does wp_chariot sync databases?
Yes, wp_chariot can synchronize databases from production to local and vice versa, with automatic URL replacement.

### What happens if synchronization is interrupted?
wp_chariot operations are idempotent, meaning you can run them multiple times without negative side effects. If synchronization is interrupted, you can simply run the command again.

### Can wp_chariot sync only certain files or directories?
Yes, you can configure exclusions in your site configuration to skip certain files or directories during synchronization.

### Will wp_chariot overwrite my local changes?
wp_chariot has a "protected files" feature that prevents overwriting local changes to specified files, even during synchronization from production.

## Patch Management

### What is the patch system in wp_chariot?
The patch system allows you to make changes to third-party plugins or themes (code that isn't yours) and track these changes for easy reapplication after updates.

### How do patches work with plugin updates?
When a plugin is updated, wp_chariot's patch system helps you identify and reapply your custom changes. It creates backups of original files and maintains a registry of your modifications.

### Can I roll back patches if they cause problems?
Yes, wp_chariot allows you to roll back individual patches or all patches for a site using the `rollback` command.

### Where are patches stored?
Patch information is stored in a JSON lock file (`patches-{sitename}.lock.json`) in the wp_chariot directory.

## Troubleshooting

### Why can't wp_chariot connect to my remote server?
Common issues include incorrect SSH configuration, firewall restrictions, or incorrect server details in your configuration file. Verify your SSH connection works outside of wp_chariot first.

### What should I do if database synchronization fails?
Check your database credentials, ensure your database user has the necessary permissions, and verify that mysqldump is available on your remote server.

### How do I resolve "Permission denied" errors?
Ensure that your user has the necessary permissions on both the local machine and the remote server. This is particularly important for file synchronization operations.

### What if my site uses a non-standard WordPress setup?
wp_chariot is configurable to accommodate many different WordPress setups, including non-standard directory structures. You may need to adjust your configuration accordingly.

## Advanced Usage

### Can wp_chariot work with CI/CD pipelines?
Yes, wp_chariot can be used alongside CI/CD pipelines. You can configure it to exclude directories that are managed by your CI/CD process.

### Is it possible to automate wp_chariot operations?
Yes, you can automate wp_chariot operations using cron jobs or other scheduling tools. The commands are designed to be scriptable.

### Can wp_chariot work with WordPress Multisite?
It has not been tested but it should work.

### How do I contribute to wp_chariot?
Contributions are welcome! Check out the [Contributing Guide](../CONTRIBUTING.md) for details on how to get started. 