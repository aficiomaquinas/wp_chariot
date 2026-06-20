# Installation Guide

This guide provides detailed instructions for installing and configuring wp_chariot.

## Prerequisites

### Local Machine Requirements
- **Operating System**: Unix-based (Linux/macOS)
- **Python**: Version 3.8 or higher (preferably managed with [asdf](https://asdf-vm.com/) or similar)
- **uv**: Latest version [installed](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- **DDEV**: Latest version [installed](https://ddev.readthedocs.io/en/stable/users/install/)
- **SSH**: Properly configured with access to your remote server
- **rsync**: Usually installed by default on Unix-based systems

### Remote Server Requirements
- **Operating System**: Unix-based server
- **PHP**: With WordPress requirements
- **WP-CLI**: Installed and accessible
- **SSH**: Access configured for your user
- **rsync**: Installed (usually default)
- **MySQL/MariaDB**: Installed with command-line tools
- **Database Access**: User with sufficient privileges for import/export operations

## Installation Steps

### 1. Clone the Repository

```bash
# Clone the repository OUTSIDE any WordPress installation
git clone https://github.com/aficiomaquinas/wp_chariot.git ~/wp_chariot
cd ~/wp_chariot/python
```

### 2. Install Python Dependencies

```bash
# Use a Python version manager (recommended)
# If using asdf:
asdf local python 3.10.0  # Or your preferred version

# Install dependencies using uv
# This will create a virtual environment and install all dependencies
uv sync
```

**Note**: This project uses [uv](https://docs.astral.sh/uv/) for dependency management. The `uv sync` command will:
- Create a virtual environment in `.venv` (if it doesn't exist)
- Install all dependencies from `pyproject.toml`
- Generate/update the `uv.lock` file with locked versions

#### Alternative: Create and activate virtual environment manually

If you prefer to work with an activated virtual environment (useful for IDEs and editors), you can create it manually:

```bash
# Create the virtual environment
uv venv

# Activate it (Linux/macOS)
source .venv/bin/activate

# Or on Windows
# .venv\Scripts\activate

# Then install dependencies
uv sync
```

After activation, you can run commands directly:
```bash
wpchariot check
```

#### Using uv run (recommended)

You can also use `uv run` to execute commands without activating the environment:

```bash
# Run the CLI directly
uv run wpchariot check
# or
uv run wp_chariot check
```

The `uv run` command automatically ensures the environment is up-to-date before executing.

#### Using pip (legacy)

If you prefer to use the project without uv, you can still use pip:
```bash
pip install -r requirements.txt
```

### 3. Create Configuration Files

```bash
# Copy example configuration files
cp config.example.yaml config.yaml
cp sites.example.yaml sites.yaml
```

### 4. Configure Your Site(s)

Edit `sites.yaml` to configure your site with the appropriate connection details, paths, and other settings.

### 5. Database Configuration 

The database section in `sites.yaml` requires special attention:

```yaml
database:
  remote:
    name: "your_db_name"      # Database name on remote server
    user: "your_db_user"      # Database username with access permissions
    password: "your_db_pass"  # Database password
    host: "localhost"         # Usually localhost or 127.0.0.1
```

wp_chariot uses these credentials to:
1. Connect to the database directly on the remote server (via SSH)
2. Export the database using `mysqldump`
3. Import the database locally using DDEV

The user must have permissions to:
- SELECT data from all tables
- EXPORT the database (mysqldump)
- INSERT/UPDATE data (for bi-directional sync)

### 6. Verify Installation

```bash
# Check if configuration is valid
# Using uv run (recommended):
uv run wpchariot check

# Or using the virtual environment directly:
source .venv/bin/activate
wpchariot check
```

## 7. Local Infrastructure Initialization & Initial Seeding (DDEV + wpchariot init)

`wp_chariot` is designed to synchronize data and logic, but it does **not** automatically provision the underlying host-level infrastructure (like DDEV containers). You must configure and start your local DDEV project independently **before** running the initial seeding commands.

### Prerequisites for Site Seeding
Ensure the following are defined in your `sites.yaml` for the target site:
- `local_path`: Absolute path to your local WordPress installation directory.
- `ddev.docroot`: The relative path from the project root to the WordPress root (e.g., `app/public`).

### Initial Provisioning Flow

#### Step 1: Initialize and Start DDEV
First, create your local project directory and set up the DDEV container. DDEV must be running because `wpchariot init` needs an active local database container to import the MySQL dump.

1. Navigate to your local project directory:
   ```bash
   mkdir -p /home/aficio/Documents/DevelopmentV2/myproject
   cd /home/aficio/Documents/DevelopmentV2/myproject
   ```

2. Initialize DDEV:
   Run the DDEV configuration matching your PHP and structure requirements:
   ```bash
   ddev config --project-name=myproject --project-type=wordpress --docroot=app/public --php-version=8.1
   ```

3. Start DDEV:
   ```bash
   ddev start
   ```

#### Step 2: Seed the Local Environment with `wpchariot init`
Once DDEV is running, you can seed the local project files, database, and infrastructure plugins in a single step using the `init` command.

1. Navigate to the `wp_chariot/python` directory:
   ```bash
   cd ~/wp_chariot/python
   ```

2. Run the `init` command:
   ```bash
   uv run wpchariot init --with-db --with-infra --site myproject-alias
   ```

**What this command does under the hood:**
* **File Sync (Step 1)**: Syncs files from the remote server via `rsync`, excluding patterns defined in `sites.yaml`.
* **Database Sync (Step 2)**: Exports the remote database via SSH, downloads the dump, and imports it directly into the active local DDEV container database.
* **Infrastructure Plugins (Step 3)**: Installs development-required plugins locally (`nginx-helper`, `redis-cache`, `wp-original-media-path`).
* **Media Path Alignment (Step 4)**: Automatically configures local WordPress media paths to map cleanly, preventing broken assets on your local workspace.

---

## Verification & Troubleshooting

### 1. Verify Configuration Alignment
Run the check tool to make sure all local paths, remote SSH connections, and configurations are correct:
```bash
uv run wpchariot check --site myproject-alias
```

The output validates:
* **System requirements** (`rsync`, `ssh`, `ddev`).
* **YAML configuration sections** (`ssh`, `security`, `database`, `urls`, `media`, `exclusions`, `protected_files`).
* **Path existence** (ensuring the configured `local_path` maps to your local files).

### 2. Common Installation & Init Issues

* **Database Import Fails**:
  Ensure DDEV is actually running (`ddev status`). If DDEV is stopped, `wpchariot` cannot run the import commands inside the database container.
  
* **SSH Connection / Key Issues**:
  Ensure your local SSH keys are added and the host is defined in your `~/.ssh/config` file. Test with:
  ```bash
  ssh your-remote-host
  ```
  
* **Local path does not exist**:
  Create the folder configured in `sites.yaml` under `ssh.local_path` before running `wpchariot check`.

For more detailed workflows and sync mechanics, proceed to the [Workflow Guide](workflow.md) and [FAQ](faq.md). 