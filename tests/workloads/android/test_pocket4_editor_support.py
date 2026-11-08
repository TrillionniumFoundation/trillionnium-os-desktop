"""Expose the twelve local Editor/Probe source controls to A08 discovery.

The suite uses only its checked-in source fixtures and never contacts Pocket4.
Keep this wrapper in the source-integrity REQUIRED_FILES set so deleting it
cannot silently remove these controls from the discovery denominator.
"""

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTROLS = ROOT / "compat/android/pocket4/editor-probe-host-support/tests/test_support_binding.py"
EXPECTED_TESTS = 12


def load_tests(loader, _standard_tests, _pattern):
    """Fail visibly if the complete pinned control entry is absent or reduced."""
    if not CONTROLS.is_file():
        raise FileNotFoundError(f"Pocket4 Editor/Probe controls are missing: {CONTROLS}")
    spec = importlib.util.spec_from_file_location("pocket4_editor_probe_support_controls", CONTROLS)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Pocket4 Editor/Probe controls: {CONTROLS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = loader.loadTestsFromModule(module)
    observed = suite.countTestCases()
    if observed != EXPECTED_TESTS:
        raise RuntimeError(f"Expected {EXPECTED_TESTS} Pocket4 Editor/Probe controls, found {observed}")
    return suite


if __name__ == "__main__":
    unittest.main(verbosity=2)
