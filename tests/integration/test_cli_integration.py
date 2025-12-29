"""Integration test for Svalinn AI CLI - tests the exact working command"""

import subprocess
import sys
from pathlib import Path


def test_cli_basic_functionality():
    """Test that CLI runs without errors and returns expected output structure"""

    # Test input - use a simple, safe prompt
    test_input = "Hello, how are you today?"

    # Run the exact command that we know works
    cmd = [sys.executable, "-m", "svalinn_ai.cli.main", "--input", test_input]

    print(f"Running command: {' '.join(cmd)}")

    # Execute the command
    result = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,  # Run from project root
        check=False,  # Don't raise exception on non-zero return code
    )

    # Print debug info
    print("Return code:", result.returncode)
    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    # Basic assertions
    assert result.returncode == 0, f"CLI failed with return code {result.returncode}"
    assert "Final Verdict:" in result.stdout, "Should contain verdict in output"
    assert "Request ID:" in result.stdout, "Should contain request ID in output"
    assert "UNSAFE" in result.stdout, "Should block"

    print("✅ CLI integration test passed!")


if __name__ == "__main__":
    # Allow running directly for debugging
    test_cli_basic_functionality()
