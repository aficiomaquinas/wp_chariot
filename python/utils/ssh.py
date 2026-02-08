"""
Utilities for SSH operations with remote servers
"""

import os
import paramiko
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import subprocess
import shlex

class SSHClient:
    """
    SSH Client to execute commands on remote servers
    """
    
    def __init__(self, host: str):
        """
        Initializes the SSH client
        
        Args:
            host: SSH host alias (must be configured in ~/.ssh/config)
        """
        self.host = host
        self.client = None
        
    def connect(self) -> bool:
        """
        Establishes an SSH connection with the remote server
        
        Returns:
            bool: True if the connection was successful, False otherwise
        """
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Use the user's SSH configuration file
            ssh_config = paramiko.SSHConfig()
            user_config_file = os.path.expanduser("~/.ssh/config")
            
            if os.path.exists(user_config_file):
                with open(user_config_file) as f:
                    ssh_config.parse(f)
                    
                # Get the configuration for the specific host
                host_config = ssh_config.lookup(self.host)
                
                # Extract connection parameters
                hostname = host_config.get('hostname', self.host)
                port = int(host_config.get('port', 22))
                username = host_config.get('user', os.getenv('USER', 'root'))
                identity_file = host_config.get('identityfile', [None])[0]
                
                # Expand the identity file path
                if identity_file:
                    identity_file = os.path.expanduser(identity_file)
                
                # Connect using the configuration
                if identity_file:
                    self.client.connect(
                        hostname=hostname,
                        port=port,
                        username=username,
                        key_filename=identity_file
                    )
                else:
                    # Without identity file, use password or SSH agent authentication
                    self.client.connect(
                        hostname=hostname,
                        port=port,
                        username=username
                    )
                
                print(f"✅ SSH connection established with {self.host} ({hostname})")
                return True
            else:
                print(f"❌ SSH configuration file not found: {user_config_file}")
                return False
                
        except Exception as e:
            print(f"❌ Error connecting to {self.host}: {str(e)}")
            return False
            
    def disconnect(self):
        """
        Closes the SSH connection
        """
        if self.client:
            self.client.close()
            print(f"✅ SSH connection closed with {self.host}")
            
    def __enter__(self):
        """
        Support for the with pattern
        """
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Closes the connection when exiting the with block
        """
        self.disconnect()
        
    def execute(self, command: str) -> Tuple[int, str, str]:
        """
        Executes a command on the remote server
        
        Args:
            command: Command to execute
            
        Returns:
            Tuple[int, str, str]: Exit code, standard output, error output
        """
        if not self.client:
            print("❌ No SSH connection established")
            return (1, "", "No SSH connection established")
            
        try:
            print(f"🔄 Executing remote command: {command}")
            stdin, stdout, stderr = self.client.exec_command(command)
            
            # Read the output
            stdout_str = stdout.read().decode('utf-8')
            stderr_str = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
            
            if exit_code != 0:
                print(f"⚠️ The command returned exit code {exit_code}")
                if stderr_str:
                    print(f"Error: {stderr_str}")
            
            return (exit_code, stdout_str, stderr_str)
            
        except Exception as e:
            print(f"❌ Error executing remote command: {str(e)}")
            return (1, "", str(e))
            
    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """
        Uploads a file to the remote server
        
        Args:
            local_path: Local path of the file
            remote_path: Remote path where to save the file
            
        Returns:
            bool: True if the transfer was successful, False otherwise
        """
        if not self.client:
            print("❌ No SSH connection established")
            return False
            
        try:
            # Create an SFTP client
            sftp = self.client.open_sftp()
            
            # Ensure the remote directory exists
            remote_dir = os.path.dirname(remote_path)
            self.execute(f"mkdir -p {shlex.quote(remote_dir)}")
            
            # Transfer the file
            print(f"📤 Uploading file {local_path} -> {remote_path}")
            sftp.put(str(local_path), remote_path)
            sftp.close()
            
            print(f"✅ File uploaded successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error uploading file: {str(e)}")
            return False
            
    def download_file(self, remote_path: str, local_path: Path) -> bool:
        """
        Downloads a file from the remote server
        
        Args:
            remote_path: Remote path of the file
            local_path: Local path where to save the file
            
        Returns:
            bool: True if the transfer was successful, False otherwise
        """
        if not self.client:
            print("❌ No SSH connection established")
            return False
            
        try:
            # Create an SFTP client
            sftp = self.client.open_sftp()
            
            # Ensure the local directory exists
            local_dir = local_path.parent
            local_dir.mkdir(parents=True, exist_ok=True)
            
            # Transfer the file
            print(f"📥 Downloading file {remote_path} -> {local_path}")
            sftp.get(remote_path, str(local_path))
            sftp.close()
            
            print(f"✅ File downloaded successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error downloading file: {str(e)}")
            return False


def run_rsync(
    source: str,
    dest: str,
    options: List[str] = None,
    exclusions: Dict[str, str] = None,
    dry_run: bool = False,
    ssh_options: str = None,
    capture_output: bool = False,
    verbose: bool = False,
    log_file: str = None
) -> Tuple[bool, str]:
    """
    Executes rsync to synchronize files
    
    Args:
        source: Source of the synchronization (can be local or remote)
        dest: Destination of the synchronization (can be local or remote)
        options: Additional options for rsync
        exclusions: Dictionary of patterns to exclude (key -> pattern)
        dry_run: If True, does not make real changes (simulation)
        ssh_options: Additional options for SSH
        capture_output: If True, captures the output instead of displaying it
        verbose: If True, shows detailed output in real time
        log_file: Path to log file to write output to
        
    Returns:
        Tuple[bool, str]: True if the synchronization was successful, False otherwise,
                          and the command output
    """
    # Default options
    if options is None:
        options = ["-avzh", "--delete"]
        
    # Add simulation option if necessary
    if dry_run:
        options.append("--dry-run")
        
    # Configure SSH
    ssh_cmd = "ssh"
    if ssh_options:
        ssh_cmd = f"ssh {ssh_options}"
        
    # Build base command
    cmd = ["rsync", "-e", ssh_cmd]
    
    # Add options
    cmd.extend(options)
    
    # Verify exclusions
    if exclusions is None:
        print("⚠️ No exclusions provided")
        exclusions = {}
    elif not isinstance(exclusions, dict):
        print("⚠️ The exclusion format is not valid, they will be ignored")
        exclusions = {}
    
    # Create temporary exclusion file if necessary
    exclude_file = None
    exclusion_count = 0
    
    if exclusions and len(exclusions) > 0:
        import tempfile
        exclude_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
        
        # Only show patterns if we are in verbose mode
        if verbose:
            print(f"📋 Applying {len(exclusions)} exclusion patterns:")
        
        try:
            # Make sure exclusions is a dictionary
            if isinstance(exclusions, dict):
                for key, pattern in exclusions.items():
                    if pattern:  # Only add if the pattern is not None or empty
                        if verbose:
                            print(f"   - {key}: {pattern}")
                        exclude_file.write(f"- {pattern}\n")
                        exclusion_count += 1
        except Exception as e:
            print(f"⚠️ Error processing exclusions: {str(e)}")
            print("Continuing without exclusions...")
            
            # Close and delete the temporary file
            try:
                exclude_file.close()
                os.unlink(exclude_file.name)
            except:
                pass
            
            exclude_file = None
            
        if exclude_file:
            exclude_file.close()
            cmd.extend(["--filter", f"merge {exclude_file.name}"])
            if verbose:
                print(f"✅ Applied {exclusion_count} exclusion patterns")
    elif verbose:
        print("⚠️ No exclusions defined, all files will be synchronized")
    
    # Add source and destination
    cmd.append(source)
    cmd.append(dest)
    
    # Execute command
    cmd_str = " ".join([shlex.quote(str(arg)) for arg in cmd])
    print(f"🔄 Executing: {cmd_str}")
    
    try:
        output = []
        log_fh = None
        
        # Open log file if provided
        if log_file:
            try:
                # Ensure directory exists
                log_path = Path(log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_fh = open(log_file, 'w')
                print(f"📝 Rsync output will be written to: {log_file}")
                # Write command to log file
                log_fh.write(f"Command: {cmd_str}\n\n")
            except Exception as e:
                print(f"⚠️ Error opening log file '{log_file}': {str(e)}")
        
        if capture_output and not verbose and not log_file:
            # Capture output without displaying it in real time
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False
            )
            
            output_text = process.stdout
            output = output_text.splitlines()
            return_code = process.returncode
            
        else:
            # Execute with real-time output
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in process.stdout:
                line = line.rstrip()
                
                # Write to log file if available
                if log_fh:
                    log_fh.write(line + "\n")
                    
                # Print to stdout based on logic:
                # 1. If verbose is True -> Print everything
                # 2. If capture_output is False AND log_file is None -> Print everything (default behavior)
                # 3. If log_file is present AND verbose is False -> DO NOT PRINT (quiet mode)
                if verbose or (not capture_output and not log_file):
                    print(line)
                    
                output.append(line)
                
            process.wait()
            return_code = process.returncode
        
        # Close log file
        if log_fh:
            log_fh.close()
        
        # Clean up temporary file
        if exclude_file:
            try:
                os.unlink(exclude_file.name)
            except:
                pass
            
        if return_code == 0:
            print("✅ Synchronization completed successfully")
            return True, "\n".join(output)
        else:
            print(f"❌ Error in synchronization (code {return_code})")
            if log_file:
                 print(f"📄 Check the log file for details: {log_file}")
            return False, "\n".join(output)
            
    except Exception as e:
        # Clean up temporary file in case of error
        if exclude_file:
            try:
                os.unlink(exclude_file.name)
            except:
                pass
        
        # Close log file
        if 'log_fh' in locals() and log_fh:
            log_fh.close()
        
        print(f"❌ Error executing rsync: {str(e)}")
        return False, str(e)
 