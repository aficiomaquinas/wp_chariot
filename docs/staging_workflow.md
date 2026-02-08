# Standard Staging Synchronization Workflow

This document outlines the deterministic process for staging a WordPress site using `wpchariot` and `sporeharbor`. The philosophy is to treat Production as a read-only "Gold Source" that is accessed once, and then use `wpchariot` to build a deterministic bridge to a fresh, ephemeral Staging environment provided by `sporeharbor`.

## Philosophy
*   **Production is Read-Only (mostly):** We confine interaction with Production to a single initial pull. We generally do NOT push to production; we work with stages.
*   **Deterministic Bridge:** We trace a route from the local state to a better state in a Spore.
*   **Freshness:** We verify the target is clean before applying our state.
*   **No Unknown Unknowns:** By replacing the database and files entirely, we eliminate lingering configuration drift.

## Workflow Steps

### 1. Pull from Production ("The Golden Copy")
First, we update our local environment with the latest data and files from production. This is the **only** time we touch production.

```bash
wpchariot sync-all --direction from-remote --site tiendattamayocom
```
*   **Goal:** Create a local mirror of production.
*   **Note:** This runs `rsync` for files and `wp db export/import` for the database.
*   **Safety:** Ensure `sites.yaml` has `production_safety: enabled` (or similar safeguards) if strictly enforcing safety, though `from-remote` is inherently safer.

### 2. Provisions Fresh Spore (SporeHarbor)
Deploy a new Spore to ensure we are deploying to a clean, known state.

*   **Action:** Trigger a new deploy in SporeHarbor.
*   **Checks:**
    *   Verify `target_domain` in `config.yaml` matches the staging environment (e.g., `staging.tiendatest.ttamayo.com`).
    *   **CRITICAL:** Ensure we are NOT targeting production.
    *   Wait for the deployment to complete.

### 3. Verify Clean Slate
Before syncing our data, confirm the Spore is a fresh, vanilla WordPress install. This proves the environment is active and we aren't inheriting old issues.

```bash
curl -I https://staging.tiendatest.ttamayo.com
```
*   **Expected:** HTTP 200 OK.
*   **Content:** Should look like a generic "Hello World" or boilerplate WordPress install.

### 4. Push to Staging ("The Bridge")
Now we push our local state (derived from Prod) to the fresh Staging Spore. `wpchariot` handles the URL transformations and file synchronization deterministically.

```bash
wpchariot sync-all --direction to-remote --site tiendattamayocom-staging --yes
```
*   **Source:** The local directory (sync'd from Step 1).
*   **Transformations:** `wpchariot` automatically runs `search-replace` to update URLs from Production to Staging.
*   **Reliability:** Since we just fixed the "Fail-Fast" logic, if anything (like a plugin) breaks the DB import or Search-Replace, the process will halt immediately rather than leaving a broken/half-migrated site.

### 5. Final Validation
Visit the staging URL to confirm the migration was successful.

*   **Action:** Browse `https://staging.tiendatest.ttamayo.com`.
*   **Expected:** The site should look exactly like Production (Storefront, Products, Theme).
*   **Caveat:** If media files/uploads were excluded (for speed), images might be missing, but the *structure* and *theme* must be correct. It should **not** look like the generic boilerplate from Step 3.

### 6. (Optional) Fix Media
If images are required for validation and were excluded:
*   **Option A:** Run `wpchariot media-path` (if configured).
*   **Option B:** Sync uploads directory explicitly (slower).
