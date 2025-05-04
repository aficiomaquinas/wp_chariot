# Security Considerations

wp_chariot provides powerful capabilities for WordPress development, but with that power comes responsibility, especially when working with production environments. This document outlines key security considerations to ensure safe and secure use of the tool.

## General Security Principles

### 1. Least Privilege Access

Always follow the principle of least privilege:

- Use SSH keys instead of passwords
- Create dedicated database users with limited permissions
- Use a separate server user for wp_chariot operations that doesn't have sudo access

### 2. Production Safety Features

wp_chariot includes built-in safety features to protect production environments:

```yaml
# In config.yaml
security:
  production_safety: "enabled"  # Protect against accidental production overwrites
  backups: "enabled"            # Automatically create backups before operations
```

Never disable these features unless you fully understand the implications.

## Configuration Security

### Securing Sensitive Information

Your configuration files contain sensitive information:

1. **Store securely**:
   - Keep configuration files out of version control
   - Set appropriate file permissions: `chmod 600 sites.yaml`

2. **Use environment variables** for highly sensitive data:
   ```yaml
   database:
     remote:
       password: "${WP_CHARIOT_DB_PASSWORD}"
   ```

3. **Sanitize examples**:
   - Always remove real credentials when sharing configuration examples
   - Use placeholder values in documentation

### Protected Files

Configure protected files carefully to prevent accidental overwrites:

```yaml
protected_files:
  - "wp-config.php"                # Core WordPress configuration
  - ".htaccess"                    # Server configuration
  - "wp-content/plugins/my-plugin/" # Custom plugin
```

## SSH Security

### SSH Key Management

1. **Use SSH keys** instead of passwords:
   ```bash
   # Generate keys if you don't have them
   ssh-keygen -t ed25519 -C "your_email@example.com"
   
   # Copy to server
   ssh-copy-id user@your-server
   ```

2. **Protect private keys**:
   ```bash
   chmod 600 ~/.ssh/id_ed25519
   ```

3. **Use SSH config** for consistent connections:
   ```
   # ~/.ssh/config
   Host production
     HostName your-server.com
     User your-username
     IdentityFile ~/.ssh/id_ed25519
   ```

### SSH Authentication

Consider using SSH agent for convenient but secure authentication:

```bash
# Start SSH agent
eval "$(ssh-agent -s)"

# Add key to agent
ssh-add ~/.ssh/id_ed25519
```

## Database Security

### Backup Before Syncing

Always create backups before synchronizing databases, especially when pushing to production:

```bash
# Manual backup
ssh your-server "wp db export backup_$(date +%Y-%m-%d).sql --path=/path/to/wordpress"
```

wp_chariot creates backups automatically when the `backups` security setting is enabled.

## File Synchronization Security

### Exclusion Patterns

Always exclude sensitive files and directories from synchronization:

```yaml
exclusions:
  # WordPress security files
  wp-config: "wp-config.php"
  htaccess: ".htaccess"
  
  # Potentially sensitive data
  uploads: "wp-content/uploads/"
  
  # Log files that may contain sensitive information
  logs: "**/*.log"
```

### Media File Handling

Use the media path functionality instead of synchronizing media files:

```yaml
media:
  url: "https://production-site.com/wp-content/uploads/"
```

This approach:
- Reduces data transfer
- Preserves sensitive uploads on production
- Avoids storing duplicate media locally

## Patch System Security

### Backup Original Files

The patch system automatically creates backups of original files with a `.bak` extension. Ensure these are:

1. Excluded from synchronization
2. Protected from unauthorized access
3. Regularly cleaned up if no longer needed

### Review Patches Before Applying

Always review patches before committing them to production:

```bash
# Review patch differences
python ~/wp_chariot/python/cli.py diff --patches --site mysite

# Use dry-run to see what would happen
python ~/wp_chariot/python/cli.py patch-commit --dry-run --site mysite
```

## Production Safety

### Direction Control

Exercise extreme caution when using `to-remote` operations:

```bash
# POTENTIALLY DANGEROUS: overwrites production database
python ~/wp_chariot/python/cli.py sync-db --direction to-remote --site mysite
```

Such operations should:
1. Be preceded by a backup
2. Be tested in staging first
3. Be performed with clear understanding of the impact

### Execution Environment

Consider creating a dedicated wp_chariot execution environment:

1. Use a separate user for wp_chariot operations
2. Configure limited sudo access if needed
3. Use a dedicated SSH key pair for wp_chariot operations

## Best Practices

### Regular Security Audits

Regularly audit your wp_chariot setup:

1. Review SSH key access
2. Update protected files list
3. Check exclusion patterns
4. Verify backup procedures
5. Rotate passwords and credentials

### Handling Security Incidents

If you suspect a security incident:

1. Disconnect affected systems from the network
2. Restore from known-good backups
3. Change all passwords and credentials
4. Investigate the cause
5. Apply necessary patches

### Documentation

Document your security practices:

1. Create a security checklist for your team
2. Document the backup and restore procedures
3. Establish clear protocols for production changes

## External Resources

- [WordPress Security Best Practices](https://wordpress.org/documentation/article/hardening-wordpress/)
- [SSH Security Best Practices](https://www.ssh.com/academy/ssh/security)
- [Database Security Guidelines](https://dev.mysql.com/doc/refman/8.0/en/security.html) 