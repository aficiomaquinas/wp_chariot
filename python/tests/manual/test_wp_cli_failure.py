
import sys
import os
from pathlib import Path

# Add the current directory to sys.path to ensure we can import utils
sys.path.append(os.getcwd())

from utils.wp_cli import run_wp_cli

print("Running test to verify exit code capture...")

# Command that is guaranteed to fail with exit code 42
# We use 'eval' with quoted 'exit(42);' to be safe with shell
command = ["eval", "'exit(42);'"]

# Using the staging site details we know
remote_host = "stagingTiendaTestTtamayoCom"
remote_path = "/var/www/wordpress/"

print(f"Executing remote command that should exit with 42 on {remote_host}...")

code, stdout, stderr = run_wp_cli(
    command,
    path=".", # Dummy local path
    remote=True,
    remote_host=remote_host,
    remote_path=remote_path
)

print(f"Return Code: {code}")
print(f"Stdout: {stdout}")
print(f"Stderr: {stderr}")

if code == 42:
    print("✅ SUCCESS: Exit code 42 was correctly captured.")
else:
    print(f"❌ FAILURE: Expected exit code 422, but got {code}.")
    sys.exit(1)
