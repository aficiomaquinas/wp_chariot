# Idempotency Audit & "Trailercito" Principle

## The "Trailercito" Principle (Small Cargo Truck)

`wp-chariot` is designed as a **declarative, idempotency-first, lightweight "small cargo truck"**. 

It follows the SporeHarbor philosophy of **Mechanistic Safety**:
- **Small vs. Heavy**: We don't use an airplane (complex K8s/Cloud-Native orchestration) to drag another airplane. We use a "trailercito" (a specialized truck) to move the specific payload of a WordPress Spore.
- **Specific Objective**: It does one thing well—synchronizing and re-parameterizing WordPress environments—without adding unnecessary complexity.
- **Declarative**: The state is defined in `sites.yaml` and `config.yaml`. The tool tries to bring the environment to that state.

## Idempotency Audit

An operation is **idempotent** if running it multiple times has the same effect as running it once. This is critical for reliable automation.

| Command / Operation | Idempotent? | Notes |
|---------------------|:-----------:|-------|
| `sync-files` | ✅ **Yes** | Uses `rsync`, which only transfers changes. |
| `sync-db` | ⚠️ **Partial** | Importing is destructive (replaces DB). Search-replace is safe if search strings are unique. **Handling Exit Code 1**: WP-CLI may return exit code 1 with the message `Error: Could not update option` if the value is already the same as the target. wpchariot detects this case and treats it as a success to maintain idempotence. |
| `patch-commit` | ✅ **Yes** | Checks if patch is already applied before applying. |
| `media-path` | ✅ **Yes** | Updates options and flushes cache. Updating to the same value is neutral. We handle the WP-CLI "no-op failure" (Exit Code 1) as a successful idempotent state. |
| `plugin install` | ✅ **Yes** | `wp plugin install` handles "already installed" gracefully. |
| `plugin activate` | ✅ **Yes** | `wp plugin activate` does nothing if already active. |
| `init` / `sync-all` | ✅ **Yes** | Composed of idempotent sub-commands. |

### Areas for Improvement (Nuclear Safety)
While `sync-db` is technically idempotent in terms of the *result* (it always leaves the DB in the target state), the *process* of searching and replacing strings can be sensitive if run on a DB that has already been partially transformed. We recommend always syncing from a clean **Source** to a **Target**.

## Configuration Guardrails (The Bridge)

For the `--with-infra` workflow to be safe and reliable, your `sites.yaml` must have correct **Guardrails**.

### 1. Protected Files (`protected_files`)
These files are **Shielded from Deletion**. Even if you sync with `--clean` and the file is missing in the source, `wp-chariot` will NOT delete it on the target.

- **`wp-config-app.php`**: **CRITICAL**. This is the bridge. It contains target-specific constants (Redis IPs, Cache Salts). It must be protected to prevent accidental loss during sync.
- **`wp-content/plugins/wp-original-media-path/`**: Should be protected if you want to ensure the target infrastructure remains intact even if you mess up your local plugin folder.

### 2. Exclusions (`exclusions`)
These files are **Ignored by rsync**.

- **Infrastructure Plugins**: `nginx-helper`, `redis-cache`, `wp-original-media-path`.
    - **Rule**: They must **NOT** be in the exclusions list if you want `sync-all --with-infra` to push them to the target.
    - **Tip**: You can exclude them in the `SOURCE` site (to avoid pulling production junk) but they must be included in the `TARGET` sync.
