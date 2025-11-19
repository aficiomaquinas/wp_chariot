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
python cli.py check
wpchariot check  # or wp_chariot check
```

#### Using uv run (recommended)

You can also use `uv run` to execute commands without activating the environment:

```bash
# Run the CLI directly
uv run wpchariot check
# or
uv run wp_chariot check

# Run Python scripts
uv run python cli.py check
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

Edit `sites.yaml` with your site information:

```bash
# Open with your preferred editor
vim sites.yaml
```

Required configuration:
- SSH connection details
- Remote and local paths
- Database credentials
- URL configuration

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
# or
uv run python cli.py check

# Or using the virtual environment directly:
source .venv/bin/activate
python cli.py check
# or
wpchariot check
```

## Configuration Verification

After installation, ensure everything is properly set up:

1. **SSH Connection**:
   ```bash
   # Test SSH connection to your server
   ssh your-remote-server
   ```

2. **DDEV Availability**:
   ```bash
   # Verify DDEV is installed
   ddev --version
   ```

3. **wp_chariot Configuration**:
   ```bash
   # Verify configuration (using uv)
   cd ~/wp_chariot/python
   uv run wpchariot config --show
   # or
   uv run python cli.py config --show
   ```

4. **Database Access**:
   ```bash
   # Test database access on remote server
   ssh your-remote-server "mysql -u your_db_user -p your_db_name -e 'SHOW TABLES;'"
   ```

## Common Installation Issues

- **SSH Key Issues**: Ensure your SSH keys are properly set up in `~/.ssh/config`
- **Python Version**: If you encounter errors, verify you're using Python 3.8+
- **uv Not Found**: Make sure uv is installed and in your PATH. See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)
- **Permission Issues**: Ensure you have correct permissions on both local and remote
- **DDEV Not Found**: Make sure DDEV is in your PATH
- **Database Access Denied**: Verify your database credentials and permissions

For more troubleshooting help, see [Troubleshooting Guide](troubleshooting.md).

## Next Steps

After installation, set up your first WordPress site:

```bash
cd ~/wp_chariot/python

# Initialize site system (using uv)
uv run wpchariot site --init
# or
uv run python cli.py site --init

# Add your first site
uv run wpchariot site --add mysite
# or
uv run python cli.py site --add mysite
```

Then proceed to the [Workflow Guide](workflow.md) to learn how to use wp_chariot effectively. 