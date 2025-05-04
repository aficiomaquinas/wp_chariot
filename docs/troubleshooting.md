# Troubleshooting Guide

This guide provides solutions to common issues you might encounter when using wp_chariot.

## Installation Issues

### Python Dependency Errors

**Problem**: Errors when installing Python dependencies with pip.

**Solution**:
1. Ensure you're using Python 3.6 or higher:
   ```bash
   python --version
   ```

2. Try upgrading pip:
   ```bash
   pip install --upgrade pip
   ```

3. Install dependencies with the `--user` flag:
   ```bash
   pip install --user -r requirements.txt
   ```

### DDEV Not Found

**Problem**: Commands fail with "DDEV not found" or similar errors.

**Solution**:
1. Verify DDEV is installed:
   ```bash
   ddev --version
   ```

2. If not installed, follow the [DDEV installation instructions](https://ddev.readthedocs.io/en/stable/users/install/).

3. Ensure DDEV is in your PATH:
   ```bash
   echo $PATH
   ```

4. If needed, add DDEV to your PATH:
   ```bash
   # For bash (add to ~/.bashrc)
   export PATH=$PATH:$HOME/.ddev/bin
   
   # For zsh (add to ~/.zshrc)
   export PATH=$PATH:$HOME/.ddev/bin
   ```

## Configuration Issues

### Configuration File Not Found

**Problem**: Error about missing configuration files.

**Solution**:
1. Verify you're in the correct directory:
   ```bash
   pwd
   ```

2. Create the configuration files if they don't exist:
   ```bash
   cd ~/wp_chariot/python
   cp config.example.yaml config.yaml
   cp sites.example.yaml sites.yaml
   ```

3. Edit the files with your settings:
   ```bash
   vim config.yaml
   vim sites.yaml
   ```

### Invalid YAML Syntax

**Problem**: Errors about invalid YAML syntax.

**Solution**:
1. Use a YAML validator (online tools available)

2. Common YAML issues:
   - Indentation (must use spaces, not tabs)
   - Missing colons after keys
   - Incorrect nesting
   - Unquoted strings with special characters

3. Fix the syntax and try again

## Connection Issues

### SSH Connection Failed

**Problem**: Unable to connect to remote server via SSH.

**Solution**:
1. Test SSH connection directly:
   ```bash
   ssh your-remote-server
   ```

2. Check your `~/.ssh/config` file:
   ```
   Host your-remote-server
     HostName actual.server.com
     User yourusername
     IdentityFile ~/.ssh/id_rsa
   ```

3. Verify SSH key permissions:
   ```bash
   chmod 600 ~/.ssh/id_rsa
   chmod 644 ~/.ssh/id_rsa.pub
   ```

4. Try with verbose output:
   ```bash
   ssh -v your-remote-server
   ```

### Remote Path Not Found

**Problem**: Error about remote path not existing.

**Solution**:
1. Verify the path on the remote server:
   ```bash
   ssh your-remote-server "ls -la /path/to/wordpress"
   ```

2. Check the `remote_path` in your `sites.yaml`:
   ```yaml
   ssh:
     remote_path: "/correct/path/to/wordpress/"
   ```

3. Ensure the path ends with a trailing slash `/`

## Synchronization Issues

### File Synchronization Fails

**Problem**: Errors when synchronizing files.

**Solution**:
1. Check if rsync is installed on both local and remote:
   ```bash
   which rsync
   ssh your-remote-server "which rsync"
   ```

2. Verify file permissions:
   ```bash
   ssh your-remote-server "ls -la /path/to/wordpress"
   ```

3. Try with dry-run first:
   ```bash
   python ~/wp_chariot/python/cli.py sync-files --dry-run --site mysite
   ```

4. If specific files fail, add them to exclusions temporarily

### Database Synchronization Fails

**Problem**: Unable to synchronize database.

**Solution**:
1. Verify database credentials in `sites.yaml`

2. Check if WP-CLI is available on remote:
   ```bash
   ssh your-remote-server "wp --info"
   ```

3. Test direct database connection:
   ```bash
   ssh your-remote-server "mysql -u db_user -p db_name -h localhost -e 'SHOW TABLES;'"
   ```

4. Check for database size issues (very large databases may timeout):
   ```bash
   ssh your-remote-server "wp db size --format=mb"
   ```

5. Increase PHP memory limit in `config.yaml`:
   ```yaml
   wp_cli:
     memory_limit: "1024M"
   ```

## Patch System Issues

### Patch Application Fails

**Problem**: Unable to apply patches to remote server.

**Solution**:
1. Verify the patch file exists and is registered:
   ```bash
   python ~/wp_chariot/python/cli.py patch --list --site mysite
   ```

2. Check file permissions on remote:
   ```bash
   ssh your-remote-server "ls -la /path/to/file/to/patch"
   ```

3. Try dry-run first:
   ```bash
   python ~/wp_chariot/python/cli.py patch-commit --dry-run --site mysite
   ```

4. If the file was modified on remote, use force:
   ```bash
   python ~/wp_chariot/python/cli.py patch-commit --force --site mysite
   ```

### Backup Files Missing

**Problem**: Backup (.bak) files not created or missing.

**Solution**:
1. Check if backups are enabled in config:
   ```yaml
   security:
     backups: "enabled"
   ```

2. Verify write permissions in the directory:
   ```bash
   ssh your-remote-server "touch /path/to/wordpress/test.txt && rm /path/to/wordpress/test.txt"
   ```

3. Look for backups in the correct location:
   ```bash
   ssh your-remote-server "find /path/to/wordpress -name '*.bak'"
   ```

## Media Path Issues

### Media Not Displaying

**Problem**: Media files not displaying in local environment.

**Solution**:
1. Verify wp-original-media-path plugin is installed and activated:
   ```bash
   ddev ssh -c "wp plugin list"
   ```

2. Check media URL configuration in `sites.yaml`:
   ```yaml
   media:
     url: "https://your-production-site.com/wp-content/uploads/"
   ```

3. Inspect browser console for media loading errors

4. Make sure the production media URL is accessible from your local machine

### Media Path Plugin Installation Fails

**Problem**: wp-original-media-path plugin installation fails.

**Solution**:
1. Verify DDEV is running:
   ```bash
   ddev status
   ```

2. Try installing the plugin manually:
   ```bash
   ddev ssh -c "wp plugin install wp-original-media-path --activate"
   ```

3. Check WP-CLI connectivity within DDEV:
   ```bash
   ddev ssh -c "wp --info"
   ```

4. Increase timeouts in the configuration if needed

## DDEV Issues

### DDEV Container Not Starting

**Problem**: DDEV containers fail to start.

**Solution**:
1. Check DDEV status:
   ```bash
   ddev status
   ```

2. Try restarting DDEV:
   ```bash
   ddev restart
   ```

3. Look for specific error messages:
   ```bash
   ddev logs
   ```

4. Check for port conflicts:
   ```bash
   sudo lsof -i :80
   sudo lsof -i :443
   ```

5. Verify Docker is running:
   ```bash
   docker ps
   ```

### URL Replacement Issues

**Problem**: URLs not correctly replaced in the database.

**Solution**:
1. Verify URLs in configuration:
   ```yaml
   urls:
     remote: "https://production-site.com"
     local: "https://mysite.ddev.site"
   ```

2. Check current URLs in the database:
   ```bash
   ddev ssh -c "wp search-replace --dry-run 'https://production-site.com' 'https://mysite.ddev.site'"
   ```

3. Manually perform URL replacement:
   ```bash
   ddev ssh -c "wp search-replace 'https://production-site.com' 'https://mysite.ddev.site' --all-tables"
   ```

## Command Execution Issues

### Command Not Found

**Problem**: Python script or command not found.

**Solution**:
1. Verify you're in the correct directory:
   ```bash
   cd ~/wp_chariot/python
   ```

2. Check if the file is executable:
   ```bash
   chmod +x cli.py
   ```

3. Use absolute paths:
   ```bash
   python /absolute/path/to/wp_chariot/python/cli.py command
   ```

### Permission Denied

**Problem**: Permission denied errors when executing commands.

**Solution**:
1. Check file permissions:
   ```bash
   ls -la ~/wp_chariot/python/cli.py
   ```

2. Ensure you have execute permission:
   ```bash
   chmod +x ~/wp_chariot/python/cli.py
   ```

3. Check for sudo requirements (ideally not needed):
   ```bash
   sudo python ~/wp_chariot/python/cli.py command
   ```

## General Troubleshooting Steps

1. **Enable verbose output** when available:
   ```bash
   python ~/wp_chariot/python/cli.py command --verbose
   ```

2. **Check log files** for detailed error messages:
   ```bash
   cat ~/wp_chariot/python/log.txt
   ```

3. **Use dry-run mode** when available to test without making changes:
   ```bash
   python ~/wp_chariot/python/cli.py command --dry-run
   ```

4. **Verify system requirements**:
   ```bash
   python ~/wp_chariot/python/cli.py check
   ```

5. **Update wp_chariot** to the latest version:
   ```bash
   cd ~/wp_chariot
   git pull
   cd python
   pip install -r requirements.txt
   ```

If you encounter issues not covered in this guide, please [open an issue](https://github.com/aficiomaquinas/wp_chariot/issues) on the GitHub repository. 