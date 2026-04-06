"""Tests for minimal runtime debug logging."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signal_engine.core.debuglog import debug_log


class TestDebugLog(unittest.TestCase):
    """Tests for the debug_log helper."""

    def test_writes_to_stderr(self):
        """debug_log writes to stderr."""
        import io
        from contextlib import redirect_stderr

        buf = io.StringIO()
        with redirect_stderr(buf):
            debug_log("test message")
        self.assertIn("test message", buf.getvalue())

    def test_writes_to_file_when_path_given(self):
        """debug_log appends to a file when log_file is given."""
        with tempfile.NamedTemporaryFile(mode="r", delete=False, suffix=".log") as f:
            path = f.name

        try:
            debug_log("line one", log_file=Path(path))
            debug_log("line two", log_file=Path(path))

            content = Path(path).read_text()
            self.assertIn("line one", content)
            self.assertIn("line two", content)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_creates_parent_dirs(self):
        """debug_log creates parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "subdir" / "deep" / "debug.log"
            debug_log("test", log_file=log_path)
            self.assertTrue(log_path.exists())
            self.assertIn("test", log_path.read_text())

    def test_format_prefix(self):
        """debug_log output has [debug] prefix."""
        import io
        from contextlib import redirect_stderr

        buf = io.StringIO()
        with redirect_stderr(buf):
            debug_log("hello")
        self.assertIn("[debug] hello", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
