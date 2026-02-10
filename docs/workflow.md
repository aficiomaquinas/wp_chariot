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

## Configuration Management (Seed/App Model)
To maintain idempotency while allowing environment-specific configurations (like different AWS keys for Prod vs Staging), we use a split configuration model:

1.  **The Seed (`wp-config.php`)**: Managed by Ansible/Infrastructure. Contains the database connection, table prefix, and salts. This file is "resettable" by Ansible.
2.  **The App (`wp-config-app.php`)**: A persistent file that lives on the server (not in git, not synced). It is loaded by `wp-config.php` if it exists.
    *   **Purpose**: Holds environment constants (e.g. `WP_CACHE`, `WPOSES_AWS_ACCESS_KEY_ID`).
    *   **Workflow**: You create this file **manually** (or via script) on the server once. `wp_chariot` ignores it during syncs (protected file), preserving your environment secrets.
    *   **Critical Rule**: Never put Production secrets (like SES keys) in Staging's `wp-config-app.php`.

## Detailed Workflow Steps

### 1. Initial Setup (One-time per site)

Before you begin working with a site, you need to set up wp_chariot and configure it for your site.

```bash
# Clone wp_chariot (if not already done)
git clone https://github.com/aficiomaquinas/wp_chariot.git ~/wp_chariot
cd ~/wp_chariot/python
uv sync
source .venv/bin/activate  # Activate virtual environment

# Set up site configuration
wpchariot site --init
wpchariot site --add mysite
```

Edit `sites.yaml` to configure your site with the appropriate connection details, paths, and other settings.

### 2. Environment Initialization

When you're ready to work on a site, initialize the local development environment:

```bash
# One command to do everything
wpchariot init --with-db --with-infra --site mysite
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
wpchariot patch --add wp-content/plugins/some-plugin/file-to-modify.php --site mysite --description "Fix critical issue"

# Make your changes to the file locally and test them
```

### 4. Testing

Test your changes thoroughly in your local environment. DDEV provides a full local development environment where you can verify your changes work correctly.

```bash
# View differences between local and production
wpchariot diff --site mysite

# View only patch-related differences
wpchariot diff --patches --site mysite
```

### 5. Applying Changes to Production

Once you've tested your changes and are satisfied with them, apply them to production:

For third-party code patches:
```bash
# Apply registered patches to production
wpchariot patch-commit --site mysite
```

For custom code that you maintain (not using the patch system):
```bash
# Synchronize specific files back to production (USE WITH CAUTION)
wpchariot sync-files --direction to-remote --site mysite
```

Note: For custom plugins and themes that you maintain, it's often better to use a dedicated Git repository and CI/CD process instead of wp_chariot's sync-files command.

### 6. Maintaining the Environment

As your production site evolves (new plugins, updates, content changes), you can update your local environment accordingly:

```bash
# Update files from production
wpchariot sync-files --site mysite

# Update database from production
wpchariot sync-db --site mysite

# Configure media paths (if needed)
wpchariot media-path --site mysite

# Or use sync-all to do all the above in one command
wpchariot sync-all --site mysite
```

### 7. Advanced Inspections (Best Practice)

Before performing a synchronization from remote (especially on sites with many changes), it is highly recommended to inspect exactly what will be downloaded. This can prevent surprises and allow you to adjust exclusions if needed.

Use the `diff` command with the `--all` flag and redirect the output to a log file for detailed review:

```bash
# Generate a complete diff report
wpchariot diff --all --site mysite > logs/diff_mysite.txt
```

You can then open `logs/diff_mysite.txt` to inspect:
- **📥 New files**: Files that exist on the server but not locally.
- **🔄 Modified files**: Local files that differ from the server version.
- **🗑️ Files to delete**: Local files that don't exist on the server (and are not in the exclusions list).

This is especially useful before running `sync-all` or `sync-files`.

## Workflow Variants

### Staging Sync Workflow (Desproductionalized)

A common use case is using your local development environment to update a "staging" or "test" server that should remain "desproductionalized". 

While `wp_chariot` doesn't use active entrypoint scripts for this, we achieve a "clean" environment by **strategic synchronization exclusions**. Since most of our business logic resides in custom plugins or themes, we can safely omit production-heavy or side-effect-prone third-party plugins.

#### How it works (The "Sync-based" Desproductionalization)
Instead of running a "desprod" script, we simply **never synchronize** certain folders. By excluding cache plugins, security WAFs, and tracking tools, the target environment (local or staging) never "sees" the production complexity.

**Common Exclusions Example:**
```yaml
exclusions:
  cache: wp-content/cache/
  litespeed: wp-content/plugins/litespeed-cache/
  wordfence: wp-content/plugins/wordfence/
  akismet: wp-content/plugins/akismet/
  jetpack: wp-content/plugins/jetpack/
  # Critical for desproductionalization: Omit Email/SMTP plugins and Payment Gateways
  wp-ses: wp-content/plugins/wp-ses/
  stripe: wp-content/plugins/stripe-for-woocommerce/
  # We ONLY keep our business logic:
  # my-custom-plugin: wp-content/plugins/my-agency-plugin/
```

#### The Email & Payments consideration
A key part of why this "declarative" approach works so well is that it encourages **offloading services**. 
- **Email**: By using plugins like Amazon SES or SendGrid and **excluding them** from synchronization, you ensure that your local or staging environment doesn't have the "credentials" or the "machinery" to accidentally send emails to real customers.
- **Payments**: Similarly, by excluding payment gateway plugins, you physically remove the possibility of processing real transactions in a development environment.

If you need more complex logic, since `wp_chariot` is a CLI tool, you can always wrap it in external scripts, but keeping the core "desprod" logic in the sync layer via exclusions makes the process robust and predictable.

Since `sites.yaml` is designed to handle different environments cleanly, you can clone a site entry to manage this:

1. **Source Site**: Your usual production site (e.g., `mysite`).
2. **Staging Site**: A cloned entry in `sites.yaml` (e.g., `mysite-staging`) that uses the **same** `local_path` but a different `remote_host` and `remote_path`.

Example `sites.yaml`:
```yaml
sites:
  mysite:
    ssh:
      remote_host: production-server
      local_path: /path/to/local/app/
    # ... rest of prod config (includes exclusions)
  mysite-staging:
    ssh:
      remote_host: staging-server # NEW server
      local_path: /path/to/local/app/ # SAME local path
    # ... staging config (reuses SAME exclusions)
```

**Workflow Steps:**
1. **Pull from production**: `wpchariot sync-all --direction from-remote --site mysite`. This brings down content and DB but **skips** the production-only plugins listed in `exclusions`.
2. **Perform local adjustments**: If needed, test your custom code.
3. **Push to staging**: `wpchariot sync-all --direction to-remote --site mysite-staging`. This uploads your "clean" local environment to the staging server.

The result is a staging server that mirrors production data but remains lightweight and "safe" for testing without side effects like sending production emails or triggering external WAFs.

### Live-to-Live Migration Workflow (Full Sync)

For moving servers or Disaster Recovery without desproductionalization.

#### The 4-Site Model (Isolation Strategy)
To manage dev and full migrations without pollution, use separate folders:
1.  **Dev Layer**: `.../mysite-dev/` (Uses exclusions for speed/safety).
2.  **Full Layer**: `.../mysite-full/` (Pull EVERYTHING, 1:1 clone).

### Standard Staging/Migration Sequence (The "Trailercito" Path)

This is the deterministic process for both layers. It treats Production as read-only.

#### 1. Pull from Production ("The Golden Copy")
```bash
wpchariot sync-all --direction from-remote --site prod-site --with-infra
```
*   **Goal**: Create a local mirror. `--with-infra` pulls core data and ensures infrastructure plugins are ready.

#### 2. Provision & Verify Target
*   **Action**: Provision a fresh environment (SporeHarbor or DDEV).
*   **Safety Check**: `curl -I https://target.site` (Should be vanilla/empty).

#### 3. Local Preparation (The Bridge)
*   **Config**: Update local `wp-config-app.php` with Target-specific constants.
*   **Guardrails**: Verify Target's `sites.yaml` (Exclusions OFF for infra, `wp-config-app.php` PROTECTED).

#### 4. Push to Target ("The Payload")
```bash
wpchariot sync-all --direction to-remote --site staging-site --with-infra --yes
```
*   **Reliability**: Handles search-replace and infra-plugin upload.

#### 5. Remote Activation & Validation
```bash
wpchariot media-path --remote --site staging-site
```
*   **Final Step**: Activates plugins and configures media offloading.

**5. STAGE 5: Post-Migration Flush (Manual & Agnostic)**
*   **Context**: Staging is a "Quasi-Prod" environment. Its purpose is to test the *real* caching behavior. Therefore, `wp_chariot` does **NOT** auto-flush, to avoid masking configuration issues.
*   **Goal**: Ensure you are serving fresh content, using *your* specific stack's tools.
*   **Action**: SSH into Target and flush your specific cache layers.
    *   *Example (for our Nginx/Redis stack)*:
        ```bash
        ssh target-host "cd /var/www/wordpress && wp nginx-helper purge-all && redis-cli flushall"
        ```
*   **Philosophy**: We don't couple the deployment tool to a specific cache plugin. You manage your cache strategy; we just move the bits.

### From Validation to Full Migration (The "Go Live")

Once you have successfully validated your site on **Staging** (Dev Layer) using the 5 stages above, you are ready for the real migration (e.g., Moving to a new server or Disaster Recovery).

**DO NOT use your Dev folder for this.**

1.  **Switch Context**: Go to your `mysite-full/` folder (The "Full Layer").
2.  **Repeat the 5 Stages**, but use the **Full Sites**:
    *   **Pull**: `wpchariot sync-all from-remote --site mysite-full-src` (Pulls EVERYTHING, no exclusions).
    *   **Prep**: Create the production `wp-config-app.php` locally.
    *   **Push**: `wpchariot sync-all to-remote --site mysite-full-target`.
3.  **Result**: You have moved the site 1:1 to the new infrastructure, fully tested, without carrying over development artifacts.

### Working with Multiple Sites

wp_chariot excels at managing multiple WordPress sites:

```bash
# Add another site
wpchariot site --add anothersite

# List all sites
wpchariot site --list

# Set a default site
wpchariot site --set-default mysite
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
wpchariot sync-files --site mysite
wpchariot sync-db --site mysite
wpchariot media-path --site mysite

# Or use the all-in-one sync command
wpchariot sync-all --site mysite
```

### 5. Document Site-Specific Workflows

For each site, document any special considerations or workflows in a `README.md` file within the site's directory.

## Advanced Workflows

### Automated Synchronization

For ongoing projects, you might want to automate synchronization:

```bash
# Add to your crontab (assuming venv is activated in the script)
0 9 * * 1-5 cd ~/wp_chariot/python && source .venv/bin/activate && wpchariot sync-db --site mysite
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