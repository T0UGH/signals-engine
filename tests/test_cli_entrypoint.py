"""Tests for CLI module entrypoint."""
import subprocess
import sys
import unittest
from pathlib import Path


class TestCliEntrypoint(unittest.TestCase):
    """Verify CLI module can be invoked as `python -m signal_engine.cli`."""

    def test_cli_module_invocation_runs_main(self):
        """Invoking `python -m signal_engine.cli --help` should exit with code 0."""
        result = subprocess.run(
            [sys.executable, "-m", "signal_engine.cli", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env={**subprocess.os.environ, "PYTHONPATH": "src"},
        )
        # If __main__ is missing, the module imports silently and exits with non-zero
        self.assertEqual(
            result.returncode, 0,
            f"CLI module should exit 0 on --help, got {result.returncode}. "
            f"stderr: {result.stderr[:200]}"
        )
        self.assertIn("signal-engine", result.stdout.lower())

    def test_collect_command_is_executable(self):
        """`python -m signal_engine.cli collect --help` should succeed."""
        result = subprocess.run(
            [sys.executable, "-m", "signal_engine.cli", "collect", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env={**subprocess.os.environ, "PYTHONPATH": "src"},
        )
        self.assertEqual(result.returncode, 0, f"collect --help failed: {result.stderr[:200]}")

    def test_diagnose_command_is_executable(self):
        """`python -m signal_engine.cli diagnose --help` should succeed."""
        result = subprocess.run(
            [sys.executable, "-m", "signal_engine.cli", "diagnose", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env={**subprocess.os.environ, "PYTHONPATH": "src"},
        )
        self.assertEqual(result.returncode, 0, f"diagnose --help failed: {result.stderr[:200]}")


if __name__ == "__main__":
    unittest.main()
