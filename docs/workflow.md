# WordPress Development Workflow with wp_chariot

This guide explains the typical development workflow when using wp_chariot. The tool is designed to make WordPress development more efficient by automating the setup and synchronization of development environments.

## Workflow Overview

```
┌─────────────────────┐     ┌─────────────────────┐
│                     │     │                     │
│   Production Site   │     │   Local Dev Env     │
│                     │     │                     │
└──────────┬──────────┘     └──────────┬──────────┘
           │                           │
           │  1. Initial Sync          │
           ├──────────────────────────►│
           │                           │
           │  2. DB Sync               │
           ├──────────────────────────►│
           │                           │
           │  3. Configure Media       │(optional, but saves the trouble of syncing huge media folders)
           ├─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ►│
           │                           │
           │                  Develop  │
           │                  & Test   │
           │                    ▼      │
           │                           │
           │  4. Apply Patches         │
           │◄──────────────────────────┤
           │                           │
           │  5. (Optional) Sync Back  │ Useful for mostly static sites, without transactions, perhaps an artist portfolio. Not recommended for a store for example.
           │◄──────────────────────────┤
           |---------------------------|
           | Some time passes and we find ourselves with our local dev env desynced from production, perhaps because of auto-updates, or logs from production, both db and files
           | As long as the files we are working at (our plugin or theme) are correctly excluded in the config we can simply:
           | 6.  Sync files -> will add missing files from the server without touching our exclusions
           | 7.  Sync db -> will replace local db completely but with the correct local urls
           | 8. optional configure media.

           │                           │
└──────────┴──────────┘     └──────────┴──────────┘
```

## Detailed Workflow Steps

### 1. Initial Setup (One-time per site)

Before you begin working with a site, you need to set up wp_chariot and configure it for your site.

```bash
# Clone wp_chariot (if not already done)
git clone https://github.com/aficiomaquinas/wp_chariot.git ~/wp_chariot
cd ~/wp_chariot/python
pip install -r requirements.txt

# Set up site configuration
python cli.py site --init
python cli.py site --add mysite
```

Edit `sites.yaml` to configure your site with the appropriate connection details, paths, and other settings.

### 2. Environment Initialization

When you're ready to work on a site, initialize the local development environment:

```bash
# One command to do everything
python ~/wp_chariot/python/cli.py init --with-db --with-media --site mysite
```

This single command:
1. **Synchronizes files** from production to local (excluding media and specified directories)
2. **Synchronizes the database** from production to local (with URL replacement)
3. **Configures media paths** to use production media URLs

The result is a fully functional local environment that mirrors your production site, without downloading gigabytes of media files.

### 3. Development

Now you can work on your site locally, making changes to:
- Custom themes and plugins
- Third-party plugins that need patching
- WordPress configuration

When working with third-party code (code you didn't write and maintain elsewhere), use the patching system:

```bash
# Register a file to be patched
python ~/wp_chariot/python/cli.py patch --add wp-content/plugins/some-plugin/file-to-modify.php --site mysite --description "Fix critical issue"

# Make your changes to the file locally and test them
```

### 4. Testing

Test your changes thoroughly in your local environment. DDEV provides a full local development environment where you can verify your changes work correctly.

```bash
# View differences between local and production
python ~/wp_chariot/python/cli.py diff --site mysite

# View only patch-related differences
python ~/wp_chariot/python/cli.py diff --patches --site mysite
```

### 5. Applying Changes to Production

Once you've tested your changes and are satisfied with them, apply them to production:

For third-party code patches:
```bash
# Apply registered patches to production
python ~/wp_chariot/python/cli.py patch-commit --site mysite
```

For custom code that you maintain (not using the patch system):
```bash
# Synchronize specific files back to production (USE WITH CAUTION)
python ~/wp_chariot/python/cli.py sync-files --direction to-remote --site mysite
```

Note: For custom plugins and themes that you maintain, it's often better to use a dedicated Git repository and CI/CD process instead of wp_chariot's sync-files command.

### 6. Maintaining the Environment

As your production site evolves (new plugins, updates, content changes), you can update your local environment accordingly:

```bash
# Update files from production
python ~/wp_chariot/python/cli.py sync-files --site mysite

# Update database from production
python ~/wp_chariot/python/cli.py sync-db --site mysite
```

## Workflow Variants

### Working with Multiple Sites

wp_chariot excels at managing multiple WordPress sites:

```bash
# Add another site
python ~/wp_chariot/python/cli.py site --add anothersite

# List all sites
python ~/wp_chariot/python/cli.py site --list

# Set a default site
python ~/wp_chariot/python/cli.py site --set-default mysite
```

### CI/CD Integration

For custom plugins and themes, use a standard Git workflow with CI/CD:

1. Exclude your custom plugins/themes in wp_chariot's configuration:
   ```yaml
   exclusions:
     my-custom-plugin: "wp-content/plugins/my-custom-plugin/"
   ```

2. Manage these components in separate Git repositories with their own CI/CD pipelines.

3. Use wp_chariot for everything else (core WordPress, third-party plugins, database, etc.).

## Best Practices

### 1. Always Work with Backups

Before applying changes to production, ensure you have a recent backup:

```bash
# Create a backup of your production database
ssh your-server "wp db export backup.sql --path=/path/to/wordpress"
```

### 2. Use the Patch System for Third-Party Code

Always use the patch system for modifying third-party plugins and themes. This creates a traceable history of your changes and makes it easier to reapply them after updates.

### 3. Prefer CI/CD for Your Custom Code

For plugins and themes you create and maintain, use dedicated Git repositories and CI/CD pipelines rather than wp_chariot's synchronization.

### 4. Regularly Update Your Local Environment

Keep your local environment in sync with production to catch and address potential conflicts early:

```bash
# Regular sync workflow
python ~/wp_chariot/python/cli.py sync-files --site mysite
python ~/wp_chariot/python/cli.py sync-db --site mysite
```

### 5. Document Site-Specific Workflows

For each site, document any special considerations or workflows in a `README.md` file within the site's directory.

## Advanced Workflows

### Automated Synchronization

For ongoing projects, you might want to automate synchronization:

```bash
# Add to your crontab
0 9 * * 1-5 cd ~/wp_chariot/python && python cli.py sync-db --site mysite
```

### Pre-deployment Testing

Before applying changes to production, test them in a staging environment:

1. Configure a staging site in `sites.yaml`
2. Apply changes to staging first
3. Test thoroughly
4. Only then apply to production

## Troubleshooting Common Workflow Issues

### Synchronization Conflicts

If you encounter conflicts during synchronization:

1. Check the output for specific file conflicts
2. Review the `diff` output to understand the differences
3. Decide whether local or remote changes should take precedence
4. Add conflicting files to the protected list if needed

### Database Synchronization Issues

If database synchronization fails:

1. Verify database credentials in your configuration
2. Check that your database user has the necessary permissions
3. Try a manual database export/import to identify specific issues

For more troubleshooting help, see the [Troubleshooting Guide](troubleshooting.md). 