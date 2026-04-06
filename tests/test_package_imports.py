"""Import smoke tests for signals_engine package (post-rename verification)."""
import importlib
import unittest


class TestSignalsEnginePackageImports(unittest.TestCase):
    """Verify signals_engine package is importable after rename."""

    def test_signals_engine_package_importable(self):
        """The signals_engine package can be imported."""
        pkg = importlib.import_module("signals_engine")
        self.assertIsNotNone(pkg)

    def test_signals_engine_cli_module_importable(self):
        """The signals_engine.cli module can be imported and has main()."""
        mod = importlib.import_module("signals_engine.cli")
        self.assertTrue(hasattr(mod, "main"))

    def test_signals_engine_core_submodules_importable(self):
        """Core submodules are importable."""
        from signals_engine.core import RunContext, RunStatus
        self.assertIsNotNone(RunContext)
        self.assertIsNotNone(RunStatus)
