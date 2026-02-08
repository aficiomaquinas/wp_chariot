
import sys
import os
from pathlib import Path

# Add the current directory to sys.path to ensure we can import utils
sys.path.append(os.getcwd())

from utils.wp_cli import run_wp_cli

print("🧪 Running fail-fast validation test against staging server...")

remote_host = "stagingTiendaTestTtamayoCom"
remote_path = "/var/www/wordpress/"

# 1. Test with a simulated fatal error (Exit Code 255)
# This mimics the PHP Fatal Error we saw earlier
print(f"\n[Test 1] Simulating PHP Fatal Error (exit 255) on {remote_host}...")
command_fatal = ["eval", "'exit(255);'"]

code_fatal, stdout_fatal, stderr_fatal = run_wp_cli(
    command_fatal,
    path=".", 
    remote=True,
    remote_host=remote_host,
    remote_path=remote_path
)

print(f"   ➔ Exit Code: {code_fatal}")
if code_fatal == 255:
    print("   ✅ SUCCESS: Caught Fatal Error code 255.")
else:
    print(f"   ❌ FAILURE: Expected 255, got {code_fatal}")


# 2. Test with an invalid WP-CLI argument
# This ensures we catch syntax/argument errors too
print(f"\n[Test 2] Execution with invalid argument (--invalid-flag)...")
command_invalid = ["search-replace", "foo", "bar", "--dry-run", "--invalid-flag-test"]

code_invalid, stdout_invalid, stderr_invalid = run_wp_cli(
    command_invalid,
    path=".", 
    remote=True,
    remote_host=remote_host,
    remote_path=remote_path
)

print(f"   ➔ Exit Code: {code_invalid}")
print(f"   ➔ Stderr snippet: {stderr_invalid.strip().splitlines()[0] if stderr_invalid else 'None'}")

if code_invalid != 0:
    print(f"   ✅ SUCCESS: Caught invalid argument error (Code {code_invalid}).")
else:
    print(f"   ❌ FAILURE: Command should have failed but returned 0.")

# Final Verdict
if code_fatal == 255 and code_invalid != 0:
    print("\n🏆 VERDICT: FAIL-FAST IMPLEMENTATION VERIFIED. The logic will correctly abort on errors.")
else:
    print("\n💥 VERDICT: VERIFICATION FAILED.")
