# Exclusions vs. Protected Files in wp_chariot

This document clarifies the conceptual, technical, and operational differences between **Exclusions (`exclusions`)** and **Protected Files (`protected_files`)** in the `wp_chariot` synchronization workflow, and explains how they interact with **Patches** and the **Diff** calculation.

---

## 1. Overview & Purpose

Both configurations are designed to prevent unwanted file modifications during synchronization. However, they serve different architectural purposes:

*   **Exclusions (`exclusions`)** are designed to **globally ignore** folders or files that should never travel between environments (e.g., cache folders, large upload libraries, logs, or lockfiles).
*   **Protected Files (`protected_files`)** are designed to **guard independent assets** residing on the destination server. These assets (like custom plugins with independent CI/CD pipelines, or environment-specific config files) must remain untouched, and their presence is proactively verified before synchronization starts.

---

## 2. Technical Comparison

| Feature | Exclusions (`exclusions`) | Protected Files (`protected_files`) |
| :--- | :--- | :--- |
| **Config Format** | YAML Dictionary (`key: "glob/pattern/*"`) | YAML List (`- "glob/pattern/*"`) |
| **Targeting** | Bidirectional (ignored in both source and destination) | Destination-oriented protection (conserved at target) |
| **Preflight Validation**| None | **Proactive SSH Check** (`_check_protected_files()`) |
| **Console Output** | Silent (only reports total exclusion count) | Verbose warning of protected files found on target |
| **Primary Use Cases** | `wp-content/cache/*`<br>`wp-content/uploads/*`<br>`wp-content/debug.log` | `wp-content/plugins/academia-ttamayo/`<br>`wp-config.php`<br>`.gitignore` |

---

## 3. How the Diff is Calculated and Why It Is Useful

### How is the Diff Calculated?
The diff operation (`wpchariot diff`) is a read-only dry-run simulation of the synchronization. Under the hood, it executes:
*   **Command**: `rsync -avzhnc --itemize-changes --delete`
    *   `-a` (Archive): Preserves timestamps, permissions, symlinks, etc.
    *   `-v` (Verbose): Details execution output.
    *   `-z` (Compress): Optimizes data transfers.
    *   `-h` (Human-readable): Simplifies output numbers.
    *   `-n` (**Dry-Run**): Simulates changes without executing them.
    *   `-c` (**Checksum**): Forces rsync to compare file content checksums instead of just relying on modification time and file sizes. This is critical for catching line-level modifications.
    *   `--itemize-changes`: Outputs a standardized, structured 10-character code detailing exactly what will change (e.g., `>f....` for a new file, `.s....` for a modified file).
    *   `--delete`: Identifies local files that do not exist on the remote (reported as files to delete).
*   It applies the configuration's `exclusions` and `protected_files` as `--exclude` arguments.

### Why is the Diff Useful?
1.  **Transparency & Safety**: Shows exactly what files would be downloaded (`📥`), updated (`🔄`), or deleted (`🗑️`) before altering the destination filesystem.
2.  **Exclusions Validation**: Confirms that your exclusions are working correctly (i.e., configured exclusions do not show up in the diff list).
3.  **Conflict Prevention**: Flags potential overwrites on active development assets.

---

## 4. Relationship with Patches (`patches`)

Patches are code modifications applied locally to core WordPress or third-party plugins. Synchronization can easily wipe these patches if not managed carefully. The system handles this using two mechanisms:

### A. Dynamic Exclusion of Patched Files
When a patch is registered, its target files are saved in the patch manager's lock file. Depending on the `patches.exclusions_mode` configured in `config.yaml` (`local-only` or `both-ways`), `wp_chariot` automatically loads these files and appends them to the active `rsync` exclusions list during both `diff` and `sync`:

```python
# During sync.py -> diff() and sync()
patched_files = self._load_patched_files()
for i, patched_file in enumerate(patched_files):
    key = f"patched_{i}_{os.path.basename(patched_file)}"
    exclusions[key] = patched_file
```
This guarantees that as long as patch exclusions are active, rsync will completely skip these files, preserving their patched state.

### B. Patch Collision Detection & Warning
If a patched file is *not* excluded (or if exclusions are disabled/insufficient), and the `rsync` output detects that a patched file is about to be updated (`.s....` / `🔄`) or deleted (`*deleting` / `🗑️`), the pre-sync analysis flags it:

```
⚠️ WARNING: This synchronization would affect patches:

🔄 Modified patched files (1):
  📄 wp-content/plugins/some-plugin/some-file.php
     • Description: Fix critical WooCommerce tax bug
     • Status: Applied
```

The tool stops and provides a clear recommendation to:
1.  Temporarily pause the sync or proceed knowing the patches will be overwritten.
2.  Run `patch-commit` after synchronization is completed to re-apply all registered patches cleanly.

---

## 5. What is Used for Synchronization?

For the actual file synchronization (`wpchariot sync-files`), `wp_chariot` runs `rsync` without the `-n` (dry-run) parameter:
*   **Command**: `rsync -avzh --delete`
*   It passes the same `--exclude` options generated from `exclusions`, `protected_files`, and patched files.
*   **Safety Post-Check (`_clean_excluded_files`)**: After the transfer completes, a post-synchronization check runs to verify that none of the excluded files were accidentally deleted or altered on the target, maintaining zero-shadow-state integrity.

---

## 6. Real-world Operational Guidelines

### A. Independent CI/CD (Entrypoint Plugins)
When entrypoint plugins like `academia-ttamayo`, `avalon-ttamayo`, or `oxygen-ttamayo` have their own independent repository and deployment pipeline, they must be registered in both lists:

```yaml
exclusions:
  entrypoint_plugin: "wp-content/plugins/academia-ttamayo/**"

protected_files:
  - "wp-content/plugins/academia-ttamayo/**"
```
*   Adding to `exclusions` ensures the local/development setup does not attempt to push these folders to production or staging.
*   Adding to `protected_files` guarantees that if someone syncs from production/staging down to local, or vice versa, the plugin in the destination is never modified or deleted.

### B. Environment-Specific Configurations
Local development tools (like DDEV configuration files or staging-specific configurations) should be listed under `protected_files` to ensure they are never overwritten by production defaults during syncs:

```yaml
protected_files:
  - "wp-config.php"
  - "wp-config-ddev.php"
  - ".ddev/**/*"
```
