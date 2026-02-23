"""
Database synchronization module between environments

This module provides functions to synchronize the database
between a remote server and the local environment.
"""

import os
import sys
import tempfile
import time
import re
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from config_yaml import get_yaml_config
from utils.ssh import SSHClient
from utils.filesystem import ensure_dir_exists, create_backup
from utils.wp_cli import run_wp_cli

class DatabaseSynchronizer:
    """
    Class to synchronize databases between environments
    """
    
    def __init__(self, verbose=False):
        """
        Initializes the database synchronizer
        
        Args:
            verbose: If True, displays detailed debug messages
        """
        # Save verbosity level
        self.verbose = verbose
        
        # Load configuration using the site system
        config_obj = get_yaml_config(verbose=self.verbose)
        
        # Default values in case configuration can't be loaded
        self.remote_host = "example-server"
        self.remote_path = ""
        self.local_path = Path(".")
        self.remote_url = ""
        self.local_url = ""
        self.remote_db_name = ""
        self.remote_db_user = ""
        self.remote_db_pass = ""
        self.remote_db_host = "localhost"
        self.production_safety = True
        self.cache_config = {}
        self.remote_url_clean = ""
        self.local_url_clean = ""
        
        # Load values from configuration
        if config_obj:
            # Get configuration as dictionary
            config = config_obj.config
            
            # Load SSH configuration
            if 'ssh' in config:
                ssh_config = config['ssh']
                self.remote_host = ssh_config.get('remote_host', self.remote_host)
                self.remote_path = ssh_config.get('remote_path', self.remote_path)
                self.local_path = Path(ssh_config.get('local_path', str(self.local_path)))
            
            # Load security configuration
            if 'security' in config:
                security_config = config['security']
                self.production_safety = security_config.get('production_safety', 'enabled') == 'enabled'
            
            # Load URLs configuration
            if 'urls' in config:
                urls_config = config['urls']
                self.remote_url = urls_config.get('remote', self.remote_url)
                self.local_url = urls_config.get('local', self.local_url)
            
            # Load remote database configuration
            if 'database' in config and 'remote' in config['database']:
                db_config = config['database']['remote']
                self.remote_db_name = db_config.get('name', self.remote_db_name)
                self.remote_db_user = db_config.get('user', self.remote_db_user)
                self.remote_db_pass = db_config.get('password', self.remote_db_pass)
                self.remote_db_host = db_config.get('host', self.remote_db_host)
            
            # Load cache configuration
            self.cache_config = config.get('cache', {})
        
        # Ensure URLs don't end with /
        if self.remote_url.endswith("/"):
            self.remote_url = self.remote_url[:-1]
            
        if self.local_url.endswith("/"):
            self.local_url = self.local_url[:-1]
        
        # Clean versions without protocol for some replacements
        self.remote_url_clean = self.remote_url.replace("https://", "").replace("http://", "")
        self.local_url_clean = self.local_url.replace("https://", "").replace("http://", "")
        
        # Debug to verify what configuration is being loaded (only if verbose is True)
        if self.verbose:
            print("📋 Configuration loaded:")
            print(f"   - SSH: {self.remote_host}:{self.remote_path}")
            print(f"   - URLs: {self.remote_url} → {self.local_url}")
            print(f"   - DB Host: {self.remote_db_host}")
            print(f"   - DB User: {self.remote_db_user}")
            print(f"   - DB Name: {self.remote_db_name}")
            print(f"   - DB Pass: {'*' * len(self.remote_db_pass) if self.remote_db_pass else 'not configured'}")
        else:
            # Display minimal information in normal mode
            print(f"📋 Scope: [Remote] {self.remote_url} ({self.remote_host}) ⟷ [Local] {self.local_url}")
        
        # Save reference to config for methods that need it
        self.config = {'security': {'backups': 'disabled'}}
        if config_obj and hasattr(config_obj, 'config'):
            self.config = config_obj.config
            
            # Check if we have DDEV configuration and display it if in verbose mode
            if self.verbose and 'ddev' in self.config:
                ddev_webroot = self.config.get('ddev', {}).get('webroot', 'Not configured')
                print(f"   - DDEV webroot: {ddev_webroot}")
        
        # Check if default values are being used
        default_values = ["example-server", "remote_db_name", "remote_db_user", "remote_db_password"]
        if any(val in default_values for val in [self.remote_host, self.remote_db_name, self.remote_db_user]):
            print("⚠️ WARNING: Default values are being used in the configuration.")
            print("   Verify that the config.yaml file is correctly configured.")
        
    def check_remote_connection(self) -> bool:
        """
        Verifies the connection with the remote server
        
        Returns:
            bool: True if the connection is successful, False otherwise
        """
        print(f"🔄 Checking connection to remote server: {self.remote_host}")
        
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                return False
                
            # Verify access to remote path
            cmd = f"test -d {self.remote_path} && echo 'OK' || echo 'NOT_FOUND'"
            code, stdout, stderr = ssh.execute(cmd)
            
            if code != 0:
                print(f"❌ Error checking remote path: {stderr}")
                return False
                
            if "OK" not in stdout:
                print(f"❌ Remote path does not exist: {self.remote_path}")
                return False
                
            print(f"✅ Connection verified successfully")
            return True
            
    def check_remote_database(self) -> bool:
        """
        Verifies the connection to the remote database
        
        Returns:
            bool: True if the database connection is successful, False otherwise
        """
        print(f"🔄 Checking connection to remote database...")
        
        # Check that credentials are not default values
        default_credentials = ["remote_db_name", "remote_db_user", "remote_db_password"]
        if self.remote_db_name in default_credentials or self.remote_db_user in default_credentials:
            print(f"❌ Error: Remote database credentials appear to be default values")
            print("   It's likely that the variables from the .env file are not being loaded correctly")
            print("   Check the following keys in the configuration or .env file:")
            print("   - REMOTE_DB_NAME: Remote database")
            print("   - REMOTE_DB_USER: Database user")
            print("   - REMOTE_DB_PASS: Database password")
            return False
            
        if not self.remote_db_name or not self.remote_db_user:
            print(f"❌ Error: Missing remote database credentials")
            return False
            
        with SSHClient(self.remote_host) as ssh:
            if not ssh.client:
                return False
                
            # Verify directly with configured credentials
            # Secure method: create local file and upload it, without showing the password in the log
            import hashlib, random, string
            import tempfile
            import os
            
            # Create a local temporary file with the configuration
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
                temp_file_path = temp_file.name
                temp_file.write(f"[client]\n")
                temp_file.write(f"host={self.remote_db_host}\n")
                temp_file.write(f"user={self.remote_db_user}\n")
                temp_file.write(f"password={self.remote_db_pass}\n")
                temp_file.flush()
            
            try:
                # Generate a unique temporary filename on the server
                random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                file_hash = hashlib.md5(f"{self.remote_db_name}_{random_suffix}".encode()).hexdigest()
                
                # Avoid double slash when remote_path already ends with /
                if self.remote_path.endswith('/'):
                    remote_temp_dir = f"{self.remote_path}wp-content"
                else:
                    remote_temp_dir = f"{self.remote_path}/wp-content"
                    
                remote_temp_pass = f"{remote_temp_dir}/.wp_deploy_tmp_{file_hash}.cnf"
                
                # Upload the file to the server
                if self.verbose:
                    print(f"🔒 Uploading secure connection configuration...")
                
                if not ssh.upload_file(temp_file_path, remote_temp_pass):
                    print("❌ Error uploading connection configuration")
                    return False
                
                # Set correct permissions
                ssh.execute(f"chmod 600 {remote_temp_pass}")
                
                # Secure MySQL command that uses the temporary configuration file
                mysql_check_cmd = (
                    f"mysql --defaults-extra-file={remote_temp_pass} "
                    f"-e 'SHOW DATABASES LIKE \"{self.remote_db_name}\";'"
                )
                
                # Execute the command to verify the connection
                code, stdout, stderr = ssh.execute(mysql_check_cmd)
                
                # Analyze result
                if code != 0:
                    print(f"❌ Error when connecting to MySQL: {stderr}")
                    print("   Verify the database credentials in the configuration:")
                    print(f"   - Host: {self.remote_db_host}")
                    print(f"   - User: {self.remote_db_user}")
                    print(f"   - Database: {self.remote_db_name}")
                    return False
                    
                if self.remote_db_name not in stdout:
                    print(f"❌ The database '{self.remote_db_name}' does not exist or is not accessible")
                    print("   Verify the database name in the configuration")
                    return False
                
                # Check that we can also connect using wp-cli
                # (this verifies that WordPress is correctly configured)
                code, stdout, stderr = run_wp_cli(
                    ["db", "check"],
                    path=".",  # Doesn't matter here, remote_path is used
                    remote=True,
                    remote_host=self.remote_host,
                    remote_path=self.remote_path
                )
                
                if code != 0:
                    print(f"⚠️ WordPress may not be correctly configured: {stderr}")
                    if self.verbose:
                        print(f"   Output: {stdout}")
                    # Don't return False here, as sometimes wp-cli might not work but MySQL does
                    # We're more interested in the MySQL connection than WordPress configuration
                
                # Clean up the temporary file on the server before returning
                ssh.execute(f"rm -f {remote_temp_pass}")
                
                return True
                
            finally:
                # Always clean up the local temporary file
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                
    def export_remote_db(self) -> Optional[str]:
        """
        Exports the remote database to a SQL file
        
        Returns:
            Optional[str]: Path to the export file or None if failed
        """
        print(f"📤 Exporting remote database '{self.remote_db_name}'...")
        
        # Verify connection
        if not self.check_remote_connection():
            return None
            
        # Create temporary directory for the SQL file
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        temp_dir = Path(tempfile.gettempdir()) / f"wp-deploy-{timestamp}"
        ensure_dir_exists(temp_dir)
        
        # Avoid double slash in remote paths
        if self.remote_path.endswith('/'):
            remote_sql_file = f"{self.remote_path}wp-content/db-export-{timestamp}.sql"
        else:
            remote_sql_file = f"{self.remote_path}/wp-content/db-export-{timestamp}.sql"
        
        local_sql_file = temp_dir / f"db-export-{timestamp}.sql"
        
        # Get information about the charset of the database
        with SSHClient(self.remote_host) as ssh:
            print("🔍 Getting information about the database charset...")
            charset_cmd = (
                f"cd {self.remote_path} && "
                f"wp db query 'SHOW VARIABLES LIKE \"%character%\";' --skip-column-names"
            )
            try:
                code, stdout, stderr = ssh.execute(charset_cmd)
                if code == 0 and stdout:
                    charset_info = stdout.strip().split('\n')
                    for line in charset_info:
                        if 'character_set_database' in line:
                            db_charset = line.split()[1]
                            print(f"   - Database charset: {db_charset}")
                        elif 'character_set_connection' in line:
                            conn_charset = line.split()[1]
                            print(f"   - Connection charset: {conn_charset}")
            except Exception as e:
                print(f"   ⚠️ Unable to get charset information: {str(e)}")
        
        # Create export command with explicit charset options
        export_cmd = (
            f"cd {self.remote_path} && "
            f"wp db export {remote_sql_file} --add-drop-table"
        )
        
        # Execute export command on the remote server
        with SSHClient(self.remote_host) as ssh:
            print("⚙️ Executing export on the remote server...")
            code, stdout, stderr = ssh.execute(export_cmd)
            
            if code != 0:
                print(f"❌ Error exporting remote database: {stderr}")
                return None
                
            # Download SQL file
            print(f"⬇️ Downloading SQL file ({remote_sql_file})...")
            success = ssh.download_file(remote_sql_file, local_sql_file)
            
            if not success:
                print("❌ Error downloading SQL file")
                print(f"   File remains on the server: {remote_sql_file}")
                return None
                
            # Only delete the file if the download was successful
            print(f"🧹 Cleaning temporary file on the server...")
            ssh.execute(f"rm {remote_sql_file}")
            
        print(f"✅ Remote database exported successfully to {local_sql_file}")
        
        # Display information about the downloaded file
        file_size_mb = os.path.getsize(local_sql_file) / (1024*1024)
        print(f"   - File size: {file_size_mb:.2f} MB")
        
        return str(local_sql_file)

    def export_local_db(self) -> Optional[str]:
        """
        Exports the local database (DDEV) to a SQL file
        
        Returns:
            Optional[str]: Path to the export file or None if failed
        """
        print(f"📤 Exporting local database (DDEV)...")
        
        # Verify that DDEV is installed
        try:
            subprocess.run(["ddev", "--version"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            print("❌ DDEV is not installed or not in the PATH")
            return None

        # Create temporary directory for the SQL file
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        temp_dir = Path(tempfile.gettempdir()) / f"wp-deploy-{timestamp}"
        ensure_dir_exists(temp_dir)
        
        local_sql_file = temp_dir / f"db-export-local-{timestamp}.sql"
        
        # Export local database using DDEV
        try:
            print("⚙️ Executing export on the local environment...")
            result = subprocess.run(
                ["ddev", "export-db", "-f", str(local_sql_file)],
                cwd=self.local_path.parent,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"❌ Error exporting local database: {result.stderr}")
                return None
                
            print(f"✅ Local database exported successfully to {local_sql_file}")
            return str(local_sql_file)
            
        except Exception as e:
            print(f"❌ Error during export: {str(e)}")
            return None
        
    def search_replace_urls(self, sql_file: str, reverse: bool = False) -> Optional[str]:
        """
        Replaces URLs in the exported SQL file
        
        Args:
            sql_file: Path to the SQL file
            reverse: If True, replaces local->remote instead of remote->local
            
        Returns:
            Optional[str]: Path to the processed file, None if there was an error
        """
        if not sql_file or not os.path.exists(sql_file):
            print(f"❌ SQL file not found: {sql_file}")
            return None
            
        # We no longer modify the SQL file, the replacement will be done after importing
        if reverse:
            print(f"ℹ️ URLs will be replaced after importing: {self.local_url} -> {self.remote_url}")
        else:
            print(f"ℹ️ URLs will be replaced after importing: {self.remote_url} -> {self.local_url}")
            
        # Only inform the file size
        file_size = os.path.getsize(sql_file)
        print(f"   - File size: {file_size / (1024*1024):.2f} MB")
        
        return sql_file  # We return the same unprocessed file
            
    def import_to_local(self, sql_file: str) -> bool:
        """
        Imports the SQL file to the local environment (DDEV)
        
        Args:
            sql_file: Path to the SQL file to import
            
        Returns:
            bool: True if the import was successful, False otherwise
        """
        if not sql_file or not os.path.exists(sql_file):
            print(f"❌ SQL file not found: {sql_file}")
            return False
            
        print(f"📥 Importing database to local environment (DDEV)...")
        
        # Verify that DDEV is installed
        try:
            subprocess.run(["ddev", "--version"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            print("❌ DDEV is not installed or not in the PATH")
            return False
            
        # Create backup of local database if configured
        if self.config.get('security', {}).get('backups', 'disabled') == "enabled":
            print("📦 Creating local database backup...")
            try:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                backup_dir = Path(self.local_path).parent / "db-backups"
                ensure_dir_exists(backup_dir)
                
                backup_file = backup_dir / f"db-backup-{timestamp}.sql"
                result = subprocess.run(
                    ["ddev", "export-db", "-f", str(backup_file)],
                    cwd=self.local_path.parent,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"✅ Backup created in {backup_file}")
                else:
                    print(f"⚠️ Unable to create backup: {result.stderr}")
                    
            except Exception as e:
                print(f"⚠️ Error creating backup: {str(e)}")
                
        # Ensure the file has the correct extension
        if not sql_file.endswith('.sql'):
            new_sql_file = f"{sql_file.split('.')[0]}.sql"
            try:
                os.rename(sql_file, new_sql_file)
                sql_file = new_sql_file
                print(f"✅ File renamed to ensure compatibility: {sql_file}")
            except Exception as e:
                print(f"⚠️ Unable to rename file: {str(e)}")
        
        # Verify the start of the SQL file for potential problems
        try:
            with open(sql_file, 'rb') as f:
                header = f.read(4096)  # Read the first 4KB
                
                # Verify if it looks like a valid SQL file
                if not header.startswith(b"-- ") and not header.startswith(b"/*") and b"CREATE TABLE" not in header and b"INSERT INTO" not in header:
                    print("⚠️ The SQL file might not be valid or have an unexpected format")
                    print("   We'll try to import anyway but it might fail")
        except Exception as e:
            print(f"⚠️ Unable to verify SQL file content: {str(e)}")
            
        # Import the SQL to DDEV
        try:
            print(f"⚙️ Importing SQL file to DDEV...")
            print(f"   File: {sql_file}")
            print(f"   Size: {os.path.getsize(sql_file) / (1024*1024):.2f} MB")
            
            # Get the WordPress path inside the container from the configuration (sites.yaml)
            ddev_wp_path = None
            if hasattr(self, 'config') and isinstance(self.config, dict) and 'ddev' in self.config:
                ddev_config = self.config.get('ddev', {})
                # Explicitly require both parameters (fail fast)
                if 'base_path' not in ddev_config or 'docroot' not in ddev_config:
                    print("❌ Error: DDEV configuration incomplete in sites.yaml")
                    print("   Both parameters are required:")
                    print("   - ddev.base_path: Base path inside the container (e.g. \"/var/www/html\")")
                    print("   - ddev.docroot: Docroot directory (e.g. \"app/public\")")
                    return False
                
                # Construct the full WP path
                base_path = ddev_config.get('base_path')
                docroot = ddev_config.get('docroot')
                ddev_wp_path = f"{base_path}/{docroot}"
                print(f"ℹ️ Using WordPress path: {ddev_wp_path}")
            else:
                print("❌ Error: DDEV configuration not found in sites.yaml")
                print("   'ddev' section with 'base_path' and 'docroot' is required")
                return False
            
            # Use a more explicit command with all complete options
            # 1. Clean state (Best Practice: drop tables before import for idempotency)
            print("🗑️ Resetting local database (dropping tables)...")
            run_wp_cli(["db", "reset", "--yes"], self.local_path.parent, remote=False, use_ddev=True)

            # 2. Primary import method
            print(f"📥 Importing database to DDEV: {os.path.basename(sql_file)}")
            result = subprocess.run(
                ["ddev", "import-db", "--file", sql_file, "--database", "db"],
                cwd=self.local_path.parent,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"❌ Error importing database:")
                print(f"   - Error code: {result.returncode}")
                if result.stderr:
                    print(f"   - Error: {result.stderr}")
                if result.stdout:
                    print(f"   - Output: {result.stdout}")
                    
                # Verify common errors
                error_output = result.stderr + result.stdout
                if "ERROR 1180" in error_output or "Operation not permitted" in error_output:
                    print("\n⚠️ Operation not permitted error detected.")
                    print("   This error usually occurs due to permission issues or restrictions in the file system.")
                    print("   Recommendations:")
                    print("   1. Ensure the user has write permissions in the directory")
                    print("   2. Verify that there are no locks on the database")
                    print("   3. Try importing with a smaller or fragmented file")
                
                elif "Unknown character set" in error_output:
                    print("\n⚠️ Unknown character set error detected.")
                    print("   This may occur when the SQL contains charset declarations that MySQL/MariaDB does not recognize.")
                    print("   Recommendations:")
                    print("   1. Edit the SQL file to change charset declarations")
                    print("   2. Use a tool like 'sed' to correct these issues")
                    
                # Try an alternative approach of direct import by MySQL
                print("\n🔄 Trying alternative import method...")
                try:
                    alt_result = subprocess.run(
                        ["ddev", "mysql", "db", "<", sql_file],
                        cwd=self.local_path.parent,
                        shell=True,  # Necessary for redirection
                        capture_output=True,
                        text=True
                    )
                    
                    if alt_result.returncode == 0:
                        print("✅ Alternative import succeeded using direct MySQL")
                        # Continue with success flow
                    else:
                        print(f"❌ Also failed alternative method: {alt_result.stderr}")
                        return False
                            
                except Exception as alt_e:
                    print(f"❌ Error in alternative method: {str(alt_e)}")
                    return False
                    
                # If we get here, the alternative method succeeded
                    
            print("✅ Database imported successfully")
            
            # Execute WP CLI to ensure everything works
            print("⚙️ Verifying WordPress installation...")
            
            if ddev_wp_path:
                print(f"   Using WordPress path: {ddev_wp_path}")
            else:
                print("   ⚠️ WordPress path not found in configuration")
            
            # Use run_wp_cli function to verify installation with the correct path
            code, stdout, stderr = run_wp_cli(
                ["core", "is-installed"],
                self.local_path.parent,
                remote=False,
                use_ddev=True,
                wp_path=ddev_wp_path  # Pass the path obtained from configuration
            )
            
            if code != 0:
                print("❌ WordPress is not installed or not detected")
                print("   Database imported successfully, but WordPress verification failed")
                if stderr:
                    print(f"   Error: {stderr}")
            else:
                print("✅ WordPress verified successfully")
                
            return True
            
        except Exception as e:
            print(f"❌ Error during import: {str(e)}")
            return False

    def purge_caches(self, remote: bool = True) -> None:
        """
        Purges all configured caches (FastCGI, Redis, Filesystem)
        """
        if remote:
            with SSHClient(self.remote_host) as ssh:
                # Transients (Always recommended post-sync)
                print("🧹 Cleaning transients on remote server...")
                ssh.execute(f"cd {self.remote_path} && wp transient delete --all")
                
                if not self.cache_config:
                    # Legacy fallback
                    print("🧹 Purging cache (remote default fallback)...")
                    ssh.execute(f"cd {self.remote_path} && wp cache flush")
                    ssh.execute(f"cd {self.remote_path} && wp nginx-helper purge-all")
                    return

                # Redis / Object Cache
                if self.cache_config.get('redis', {}).get('purge', False):
                    print("🧹 Purging Redis object cache on remote...")
                    ssh.execute(f"cd {self.remote_path} && wp cache flush")
                
                # FastCGI Cache (Angie/Nginx)
                fastcgi_cfg = self.cache_config.get('fastcgi', {})
                if fastcgi_cfg.get('purge', False) and fastcgi_cfg.get('path'):
                    path = fastcgi_cfg['path']
                    print(f"🧹 Purging Nginx FastCGI cache on remote: {path}")
                    # Use find to delete children only, keeps root directory and permissions
                    ssh.execute(f"find {path} -mindepth 1 -delete")
                
                # WordPress Filesystem Cache (wp-content/cache)
                if self.cache_config.get('wordpress', {}).get('purge', False):
                    print("🧹 Purging WordPress filesystem cache on remote...")
                    wp_cache_path = os.path.join(self.remote_path, 'wp-content/cache')
                    ssh.execute(f"test -d {wp_cache_path} && find {wp_cache_path} -mindepth 1 -delete")
        else:
            # Local (DDEV)
            print("🧹 Cleaning transients in local environment...")
            run_wp_cli(["transient", "delete", "--all"], self.local_path.parent, remote=False, use_ddev=True)
            
            # For local, we only purge what is explicitly enabled OR just Redis by default if no config
            if self.cache_config:
                if self.cache_config.get('redis', {}).get('purge', False):
                    print("🧹 Purging local Redis object cache...")
                    run_wp_cli(["cache", "flush"], self.local_path.parent, remote=False, use_ddev=True)
                
                if self.cache_config.get('wordpress', {}).get('purge', False):
                    print("🧹 Purging local WordPress filesystem cache...")
                    # Local path handling
                    local_cache = self.local_path / "wp-content" / "cache"
                    if local_cache.exists():
                        shutil.rmtree(local_cache)
                        local_cache.mkdir(parents=True, exist_ok=True)
            else:
                # Default local behavior
                run_wp_cli(["cache", "flush"], self.local_path.parent, remote=False, use_ddev=True)

    def import_to_remote(self, sql_file: str, is_gzipped: bool = False) -> bool:
        """
        Imports the SQL file to the remote server
        
        Args:
            sql_file: Path to the SQL file to import
            is_gzipped: True if the SQL file is gzipped, False otherwise
            
        Returns:
            bool: True if the import was successful, False otherwise
        """
        if not sql_file or not os.path.exists(sql_file):
            print(f"❌ SQL file not found: {sql_file}")
            return False
            
        print(f"📤 Importing database to remote server...")
        
        # Verify connection
        if not self.check_remote_connection():
            return False
            
        # Verify if the file is compressed with gzip
        is_gzipped = False
        with open(sql_file, 'rb') as f:
            header = f.read(2)
            if header == b'\x1f\x8b':  # gzip header
                is_gzipped = True
                print("📦 Detected compressed SQL file (gzip)")
        
        # Create temporary filename for the SQL file on the server
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        
        # Construct remote path
        if self.remote_path.endswith('/'):
            remote_sql_file = f"{self.remote_path}wp-content/db-import-{timestamp}.sql"
        else:
            remote_sql_file = f"{self.remote_path}/wp-content/db-import-{timestamp}.sql"
            
        if is_gzipped:
            remote_sql_file += ".gz"
        
        # Upload SQL file to the server
        with SSHClient(self.remote_host) as ssh:
            print(f"⬆️ Uploading SQL file to the server...")
            
            # Create remote directory
            ssh.execute(f"mkdir -p {os.path.dirname(remote_sql_file)}")
            
            # Upload file using standard method
            if not ssh.upload_file(sql_file, remote_sql_file):
                print("❌ Error uploading SQL file")
                return False
                
            # 1. Prepare database (Drop everything for a clean state)
            print("🗑️ Resetting remote database (dropping tables)...")
            ssh.execute(f"cd {self.remote_path} && wp db reset --yes")

            # 2. Import correctly based on whether it's compressed or not
            print("⚙️ Importing database to the remote server...")
            cat_cmd = "zcat" if is_gzipped else "cat"
            import_cmd = f"cd {self.remote_path} && {cat_cmd} {remote_sql_file} | wp db import -"
            code, stdout, stderr = ssh.execute(import_cmd)
            
            # Delete temporary file
            ssh.execute(f"rm {remote_sql_file}")
            
            if code != 0:
                print(f"❌ Error importing database: {stderr}")
                return False
                
            # Initial purge after import (Reset state)
            self.purge_caches(remote=True)
            
            print("✅ Database imported successfully to the remote server")
            return True

    def sync(self, direction: str = "from-remote", dry_run: bool = False, auto_confirm: bool = False) -> bool:
        """
        Synchronizes the database between environments
        
        Args:
            direction: Synchronization direction ("from-remote" or "to-remote")
            dry_run: If True, only shows what would be done
            auto_confirm: If True, skips confirmation prompts
            
        Returns:
            bool: True if the synchronization was successful, False otherwise
        """
        # Check allowed directions
        sync_config = self.config.get('sync', {}) if self.config else {}
        allowed_directions = sync_config.get('allowed_directions')
        
        if allowed_directions:
            if isinstance(allowed_directions, str):
                allowed_directions = [allowed_directions]
            
            if direction not in allowed_directions:
                print(f"❌ Operation '{direction}' is not allowed for this site.")
                print(f"   Allowed directions: {', '.join(allowed_directions)}")
                return False

        if direction == "from-remote":
            print(f"📥 Synchronizing database from remote server to local environment...")
            
            # Check allowed directions (REMOVED - now global)
            
            # Verify connection even in dry-run mode
            if not self.check_remote_connection():
                print("❌ Unable to continue without a valid remote connection")
                return False
            
            # Verify remote database information
            if not self.remote_db_name:
                print("❌ Error: Remote database name not configured")
                print("   Please set database.remote.name in the configuration file.")
                return False
                
            # Verify remote database connection
            if not self.check_remote_database():
                print("❌ Unable to continue without a valid remote database connection")
                return False
                
            # Verify that DDEV is installed
            try:
                subprocess.run(["ddev", "--version"], capture_output=True, check=True)
            except (subprocess.SubprocessError, FileNotFoundError):
                print("❌ DDEV is not installed or not in the PATH")
                print("   DDEV is required for synchronization with the local environment")
                return False
                
            if dry_run:
                print("🔄 Dry run mode: No real changes will be made")
                print(f"   - Remote database '{self.remote_db_name}' would be exported")
                print(f"   - Imported to DDEV (local environment)")
                print(f"   - URLs would be replaced: {self.remote_url} -> {self.local_url} using wp-cli")
                return True
                
            # Real process
            # 1. Export remote database
            sql_file = self.export_remote_db()
            if not sql_file:
                return False
                
            # 2. Import to local (without modifying the file)
            success = self.import_to_local(sql_file)
            if not success:
                return False
                
            # 3. Replace URLs using wp-cli (after importing)
            print(f"🔄 Replacing URLs in the database...")
            
            # Get domains without protocol
            remote_domain = self.remote_url.replace("https://", "").replace("http://", "")
            local_domain = self.local_url.replace("https://", "").replace("http://", "")
            
            print(f"   - Changing: {self.remote_url} -> {self.local_url}")
            
            # Full list of patterns to replace to cover all possible cases
            # 3. Replace URLs using wp-cli
            print(f"🔄 Replacing URLs: {self.remote_url} -> {self.local_url}")
            
            # Standard search-replace with best practice flags
            run_wp_cli(
                ["search-replace", self.remote_url, self.local_url, "--all-tables", "--precise", "--skip-columns=guid"],
                self.local_path.parent, remote=False, use_ddev=True
            )
            
            # Protocol fallback (ensure http/https variants are covered)
            if self.remote_url.startswith("https://"):
                http_remote = self.remote_url.replace("https://", "http://")
                run_wp_cli(["search-replace", http_remote, self.local_url, "--all-tables", "--precise", "--skip-columns=guid"],
                           self.local_path.parent, remote=False, use_ddev=True)
            
            # Force update core options for accessibility
            update_option("siteurl", self.local_url, self.local_path.parent, use_ddev=True)
            update_option("home", self.local_url, self.local_path.parent, use_ddev=True)

            # Best Practice: Clean transients and flush cache after migration
            self.purge_caches(remote=False)
            
            print("✅ Database sync (remote -> local) completed")
            
            # 4. Clean temporary files
            try:
                os.unlink(sql_file)
            except:
                pass
                
            return success
            
        else:  # to-remote
            print(f"📤 Synchronizing database from local environment to remote server...")
            
            # Verify production protection
            if self.production_safety:
                print("⛔ Unable to upload database to production with protection activated.")
                print("   To continue, disable 'production_safety' in the configuration:")
                print("   security:")
                print("     production_safety: disabled")
                return False
                
            # Verify connections
            if not self.check_remote_connection():
                return False
                
            if not self.check_remote_database():
                return False
                
            # Verify DDEV
            try:
                subprocess.run(["ddev", "--version"], capture_output=True, check=True)
            except (subprocess.SubprocessError, FileNotFoundError):
                print("❌ DDEV is not installed or not in the PATH")
                return False
                
            # NEW: Pre-flight check for disk space
            # Minimum 2GB free required for safe database import
            with SSHClient(self.remote_host) as ssh:
                if not ssh.check_disk_space(self.remote_path, threshold_gb=2):
                    print("❌ Aborting synchronization due to insufficient disk space on the remote server.")
                    return False
                
            # Dry run
            if dry_run:
                print("🔄 Dry run mode: No real changes will be made")
                print("   - Local database would be exported")
                print("   - Imported to remote")
                print(f"   - URLs would be replaced: {self.local_url} -> {self.remote_url} on the server")
                return True
                
            # Confirmation
            if not auto_confirm:
                print("⚠️ WARNING: You are about to overwrite the production database.")
                confirm = input("   ¿Are you COMPLETELY SURE to continue? (type 'yes' to continue): ")
                
                if confirm.lower() not in ["yes", "y", "si"]:
                    print("❌ Operation cancelled by user.")
                    return False
                
                print("⚡ Confirmation received. Proceeding with the operation...")
            else:
                print("⚡ Auto-confirm enabled. Proceeding with the operation...")
            
            # 1. Export local database directly
            sql_file = self.export_local_db()
            if not sql_file:
                return False
                
            # 2. Import to remote
            success = self.import_to_remote(sql_file)
            
            if not success:
                return False
                
            # 3. Replace URLs on the server
            print(f"🔄 Replacing URLs on the remote server...")
            
            # 3. Replace URLs using wp-cli on remote server
            print(f"🔄 Replacing URLs: {self.local_url} -> {self.remote_url}")
            
            try:
                # Standard search-replace with best practice flags
                run_wp_cli(
                    ["search-replace", self.local_url, self.remote_url, "--all-tables", "--precise", "--skip-columns=guid"],
                    path=".", remote=True, remote_host=self.remote_host, remote_path=self.remote_path
                )
                
                # Protocol fallback (ensure http/https variants are covered)
                if self.local_url.startswith("https://"):
                    http_local = self.local_url.replace("https://", "http://")
                    run_wp_cli(["search-replace", http_local, self.remote_url, "--all-tables", "--precise", "--skip-columns=guid"],
                               path=".", remote=True, remote_host=self.remote_host, remote_path=self.remote_path)
                
                # Force accessibility options
                print(f"   - Updating siteurl and home to: {self.remote_url}")
                run_wp_cli(["option", "update", "siteurl", self.remote_url], path=".", remote=True, remote_host=self.remote_host, remote_path=self.remote_path)
                run_wp_cli(["option", "update", "home", self.remote_url], path=".", remote=True, remote_host=self.remote_host, remote_path=self.remote_path)

                # Best Practice: Clean transients and flush cache after migration
                self.purge_caches(remote=True)
                
                print("✅ Database sync (local -> remote) completed on the server")
            except Exception as e:
                print(f"❌ Error during remote URL replacement: {str(e)}")
                return False
            
            # Clean temporary files
            try:
                os.unlink(sql_file)
            except:
                pass
                
            return success
            
def sync_database(direction: str = "from-remote", dry_run: bool = False, verbose: bool = False, auto_confirm: bool = False) -> bool:
    """
    Synchronizes the database between environments
    
    Args:
        direction: Synchronization direction ("from-remote" or "to-remote")
        dry_run: If True, only shows what would be done
        verbose: If True, displays detailed debug messages
        auto_confirm: If True, skips confirmation prompts
        
    Returns:
        bool: True if the synchronization was successful, False otherwise
    """
    synchronizer = DatabaseSynchronizer(verbose=verbose)
    return synchronizer.sync(direction=direction, dry_run=dry_run, auto_confirm=auto_confirm)