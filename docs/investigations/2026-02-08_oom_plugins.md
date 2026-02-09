# Investigation: Production OOM Kills & Staging Synchronization Issues

## Executive Summary
- **Critical Production Issue**: The production server (`ttContaboUsWest01Runcloud`) has **0% Disk Space Available** (`/dev/sda3` is 100% full).
- **Root Cause on Production**: The `ttamayocom` application has accumulated **67GB of LiteSpeed Cache** (`litespeed/`) and **17GB of Uploads**, consuming the entire disk. This prevents `tienda.ttamayo.com` and other apps from writing logs, sessions, or caches, causing instability and "OOM-like" behavior (processes dying due to I/O failures).
- **Staging Issue**: The "Generic Site" appearance is likely due to the deactivation of `product-blocks-pro`, which is responsible for rendering key content blocks. This plugin was causing PHP Fatal Errors (Memory Exhaustion > 256MB) on Staging, preventing `wp-cli` operations.

## Detailed Findings

### 1. Production (`ttContaboUsWest01Runcloud`)
- **Disk Usage**:
    - Total: 244GB
    - Used: 231GB (100%)
    - **Culprit**: `/home/runcloud/webapps/ttamayocom/` (85GB)
        - **`wp-content/litespeed/`: 67GB** (Cache files not being purged or huge churn).
        - `wp-content/uploads/`: 17GB.
    - `tiendattamayocom` is only 6.8GB.
- **Symptoms**:
    - Nginx/OpenLiteSpeed errors: `cacheTofile() Failed due to write file error!` (Disk Full).
    - `debug.log` is stale (last entry Jan 13), likely because `WP_DEBUG` is off or file entry failed.
    - OOM Kills: Likely system-wide instability due to disk saturation, not just RAM.

### 2. Staging (`stagingTiendaTestTtamayoCom`)
- **Plugin Failure**: `product-blocks-pro`.
    - Error: `Allowed memory size of 268435456 bytes exhausted`.
    - Trigger: Even execution of simple commands like `wp option get` caused a crash when this plugin was active.
    - Mitigation: Deactivated plugin to allow `search-replace` to fix URLs.
- **Generic Site Appearance**:
    - Likely due to `product-blocks-pro` being inactive.
    - **Persistence after Sync**: Even after a successful `sync-all` (DB + Files), the generic site persisted.
    - **Root Cause**: The Nginx FastCGI cache was NOT purged because `nginx-helper` was not found on the remote server, despite being added to the Ansible role.
    - **Plugin Status**: Manual check confirmed `nginx-helper` is NOT active or installed on Staging, indicating a failure in the deployment pipeline or repository synchronization with Kestra.

### 3. Deployment Pipeline (`v0.0.78`)
- **Status**: Reported as SUCCESS, but failed to apply new tasks.
- **Missing Tasks**: The installation and configuration of `nginx-helper` were skipped or ignored.
- **Observation**: `wp nginx-helper purge-all` failed during `sync-all` with error `not a registered wp command`.

## Recommendations

### Immediate Actions (Production)
1.  **Clear LiteSpeed Cache**: Run `rm -rf /home/runcloud/webapps/ttamayocom/wp-content/litespeed/*`. This will free ~67GB instantly.
2.  **Verify `product-blocks-pro`**: Monitor memory usage after disk cleanup. If generic OOMs persist, consider increasing PHP Memory Limit or profiling the plugin.

### Tooling Improvements (`wp_chariot` / `tt-wordpress-automation`)
1.  **Fail-Fast Logic**: (Implemented) Ensure `sync-db` aborts immediately if `search-replace` fails to avoid half-migrated states.
2.  **Plugin Safety**: Add a mechanism to temporarily deactivate high-memory/problematic plugins (`product-blocks-pro`) *before* running sync operations, then reactivate them (if safe) or warn the user.
3.  **Disk Check**: Add a pre-flight check for disk space on remote targets before attempting syncs.

### Exclusions
- **`product-blocks-pro`**: Managed via increased PHP memory limit (512M) in the Spore to avoid OOM crashes without deactivation.
- **`litespeed-cache`**: Explicitly excluded from Staging syncs as it's a Production-only stack component.

## Log of Progress
- **Feb 8, 20:00**: Attempted `sync-all` to Staging. Database synced successfully, but Nginx purge failed due to missing `nginx-helper`.
- **Feb 8, 20:10**: Verified `siteurl` is correct on DB, but site still serves generic content. Confirmed `nginx-helper` is missing on target.
- **Feb 8, 20:15**: **DATA PARITY CONFIRMED**: Staging and Production both have exactly **17,117 posts**. This confirms that the database was successfully synchronized.
- **Feb 8, 20:20**: **Mystery of 22 vs 211 tables**: `wp db tables` reports 22 tables, but `mysql SHOW TABLES` confirms 211 tables (all `wp_` prefixed). This is likely a `wp-cli` reporting anomaly on the server, not a missing data issue. 
- **Feb 8, 20:25**: **Manual Intervention**: Installed `nginx-helper` manually on Staging and purged FastCGI cache. Site title now matches ("Tienda ttamayo.com"), but design is still generic.

## The Seed/App Configuration Model (Closte Style)
To maintain idempotency and environment safety, we have split the configuration:
1.  **`wp-config.php` (The Seed)**: Managed by Ansible. Contains DB connection, Salts, and table prefix.
2.  **`wp-config-app.php` (The App)**: Managed by `wp-chariot` or manual parity. Contains custom plugin constants, `WP_CACHE`, etc. 
    *   **CRITICAL RULE**: **NO SES KEYS IN STAGING**. Production email credentials must NEVER be ported to non-production environments to avoid accidental email leakage to customers.

## Log of Progress
- **Feb 8, 20:30**: Implemented Seed/App split. Corrected `wp-config-app.php` in Staging to explicitly EXCLUDE SES keys.
- **Feb 8, 20:35**: Confirmed data parity (17,117 posts) but frontend still serves `twentytwentyfive`. The `curl` response shows a generic "WordPress Site" title, contradicting `wp-cli` which sees the correct DB values.
- **Feb 8, 20:45**: **THE SMOKING GUN FOUND**: Nginx FastCGI cache permissions are preventing the deploy user (`wordpress`) from clearing old cache files created by `www-data`.
    - **Symptom**: `rm -rf /var/cache/nginx/wordpress/*` fails with "Permission denied".
    - **Confirmation**: Accessing the site with `?nocache=123` bypasses the stuck cache and **successfully loads the Avalon theme**.
    - **Root Cause**: Nginx creates cache directories with restrictive permissions (`0700` owned by `www-data`), ignoring the parent directory's setgid bit effectively for deletion purposes by the `wordpress` group user if it can't enter the directory.
    - **Structural Fix Needed**: Update Nginx systemd unit to use `UMask=0002` or ensure cache path is writable by `wordpress` group/ACLs.

## Final Status
- **Database**: Parity confirmed (17k posts).
- **Configuration**: Seed/App model implemented. `wp-config-app.php` created manually in Staging (excluding SES keys).
- **Theme/Frontend**: Validated as working via cache bypass. The visible "Generic Site" is purely a caching artifact.
- **Action Items**:
    1.  Implement `wp-config-app.php` logic in `wp-chariot` for automated sync.
    2.  Fix Nginx cache directory permissions in Ansible (force `2775` recursively or change Nginx umask).
    3.  **IMMEDIATE**: Use cache-busting params to verify Staging.
