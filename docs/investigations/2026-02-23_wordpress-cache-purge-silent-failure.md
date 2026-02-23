# Investigation: WordPress Cache Purge Silent Failures (2026-02-23)

## Status: Reproduced / Identified Root Cause

### Problem Statement

Users report that even after `wp_chariot` reports a successful cache flush, the staging site continues to serve stale content unless a `?cachebuster=1` query string is used. Additionally, critical plugins like `redis-cache` and `nginx-helper` appear inactive on the instance.

### Findings

#### 1. Angie Cache Purge Failure (Symlinks)

The `wp_chariot` tool executes the following command to purge the Angie FastCGI cache:

```bash
find /var/cache/angie/wordpress -mindepth 1 -delete
```

However, on the server, `/var/cache/angie/wordpress` is a **symlink** to `/var/lib/sporeharbor/sites/.../cache`.

> [!IMPORTANT]
> **Manual Verification on Throwaway Instance:**
>
> - `find /var/cache/angie/wordpress -mindepth 1` -> **0 files found**
> - `find /var/cache/angie/wordpress/ -mindepth 1` -> **261 files found**
>
> Without a trailing slash, standard GNU `find` treats the symlink as a file entry and does not descend. Since the symlink itself is at "depth 0", `-mindepth 1` skips everything.

This explains why Angie continues to serve stale files despite the "success" message.

#### 2. Inactive Plugins (`redis-cache`, `nginx-helper`)

Analysis of the throwaway instance shows these plugins are installed but **inactive**.

- **Cause A (Ansible):** The Ansible tasks to activate these plugins are skipped if `migration_context == 'restore'`.
- **Cause B (Database Sync):** When `wp_chariot sync to-remote` is run, it overwrites the remote `wp_options` table (specifically `active_plugins`). If these plugins are inactive in the local DDEV environment, they become inactive remotely.

#### 3. Why `cachebuster` works

The Angie configuration (`angie-site.conf.j2`) contains:

```nginx
if ($query_string != "") { set $skip_cache 1; }
```

Any query string bypasses the FastCGI cache entirely, proving the issue lies in the stale FastCGI cache files.

### Solutions Implemented

1. **wp_chariot (Fixed):** Appended a trailing slash to the cache path in the `find` command.
2. **tt-wordpress-automation (Fixed):** Updated `ansible/roles/wordpress/tasks/post_restore.yml` to also include the trailing slash in the manual purge task.
3. **wp_chariot (Strengthened):** Added idempotent plugin management. Now it checks, installs, activates, and **re-configures** `redis-cache` and `nginx-helper` before any purge, ensuring infrastructure is healthy.
4. **wp_chariot (Fail-Fast):** Switched from warnings to exceptions. Every command failure now aborts execution with clear details and a non-zero exit code.

### Infrastructure State (Snapshot)

- **Angie Cache Symlink:** Verified.
- **Redis Cache Plugin:** Inactive.
- **Nginx Helper Plugin:** Inactive.
- **Purge Command Log:** Confirmed execution on wrong depth.
