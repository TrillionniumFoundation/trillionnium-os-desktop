"""Expose the complete frozen QuickSearch, Settings and WebView controls.

Verify the entire capsule with explicit checks before discovery, including
under Python -O. Source-only fixtures do not authorize device execution.
"""

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import unittest


ROOT = Path(__file__).resolve().parents[3]
CAPSULE = ROOT / "compat/android/pocket4/late-app-host-support"
MANIFEST_SHA256 = "a0bee3f5d10e20448baf0a461418af85c74ad594f0dfefd5bdf387b696d03c32"
EXPECTED_TESTS = 15


def verify_capsule():
    """Keep optimized discovery bound to all 71 reviewed text inputs."""
    inventory = CAPSULE / "PACKAGE-MANIFEST.json"
    if inventory.is_symlink() or not inventory.is_file():
        raise RuntimeError("Pocket4 late-app inventory is not a regular source file")
    raw = inventory.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise RuntimeError("Pocket4 late-app capsule inventory changed")
    manifest = json.loads(raw)
    if manifest["file_count"] != 70 or len(manifest["files"]) != 70:
        raise RuntimeError("Pocket4 late-app capsule inventory is incomplete")
    names = {"PACKAGE-MANIFEST.json"}
    for row in manifest["files"]:
        relative = row["path"]
        parsed = PurePosixPath(relative)
        if parsed.is_absolute() or ".." in parsed.parts or str(parsed) != relative or relative in names:
            raise RuntimeError("Pocket4 late-app capsule path is invalid")
        names.add(relative)
        path = CAPSULE / relative
        if path.is_symlink() or not path.resolve().is_relative_to(CAPSULE.resolve()):
            raise RuntimeError("Pocket4 late-app capsule path escapes its source")
        data = path.read_bytes()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise RuntimeError(f"Pocket4 late-app capsule input changed: {relative}")
        data.decode("utf-8")
        if b"\x00" in data:
            raise RuntimeError(f"Pocket4 late-app capsule input is not text: {relative}")
    actual = {path.relative_to(CAPSULE).as_posix() for path in CAPSULE.rglob("*")
              if path.is_file() and "__pycache__" not in path.parts}
    if actual != names:
        raise RuntimeError("Pocket4 late-app capsule file set differs")


def load_tests(loader, _standard_tests, _pattern):
    verify_capsule()
    controls = CAPSULE / "tests/test_host_support_binding.py"
    spec = importlib.util.spec_from_file_location("pocket4_late_app_host_support_controls", controls)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Pocket4 late-app controls: {controls}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = loader.loadTestsFromModule(module)
    observed = suite.countTestCases()
    if observed != EXPECTED_TESTS:
        raise RuntimeError(f"Expected {EXPECTED_TESTS} Pocket4 late-app controls, found {observed}")
    return suite


if __name__ == "__main__":
    unittest.main(verbosity=2)
