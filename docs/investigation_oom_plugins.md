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
    - Also, `siteurl` and `home` were successfully updated to `https://staging.tiendatest.ttamayo.com`.

## Recommendations

### Immediate Actions (Production)
1.  **Clear LiteSpeed Cache**: Run `rm -rf /home/runcloud/webapps/ttamayocom/wp-content/litespeed/*`. This will free ~67GB instantly.
2.  **Verify `product-blocks-pro`**: Monitor memory usage after disk cleanup. If generic OOMs persist, consider increasing PHP Memory Limit or profiling the plugin.

### Tooling Improvements (`wp_chariot` / `tt-wordpress-automation`)
1.  **Fail-Fast Logic**: (Implemented) Ensure `sync-db` aborts immediately if `search-replace` fails to avoid half-migrated states.
2.  **Plugin Safety**: Add a mechanism to temporarily deactivate high-memory/problematic plugins (`product-blocks-pro`) *before* running sync operations, then reactivate them (if safe) or warn the user.
3.  **Disk Check**: Add a pre-flight check for disk space on remote targets before attempting syncs.

### Exclusions
- **`product-blocks-pro`**: Adding it to `exclusions` in `sites.yaml` won't solve the runtime crash if it's active on the target. It must be managed via `wp plugin deactivate` during maintenance windows or fixed upstream.
