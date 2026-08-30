from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_validator(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REPOSITORY = load_validator("validate_repository_under_test", "validate_repository.py")
SYSTEMD = load_validator(
    "verify_systemd_socket_custody_under_test", "verify_systemd_socket_custody.py"
)


class CargoLockIdentityTests(unittest.TestCase):
    def test_repository_index_rejects_duplicate_identity(self) -> None:
        package = {"name": "serde", "version": "1.0.0", "source": "registry"}
        with self.assertRaisesRegex(AssertionError, "duplicate package identity"):
            REPOSITORY.index_lock_packages({"package": [package, dict(package)]})

    def test_systemd_index_rejects_duplicate_identity(self) -> None:
        package = {"name": "hepta-agent-portd", "version": "0.1.0"}
        with self.assertRaisesRegex(AssertionError, "duplicate package identity"):
            SYSTEMD.index_lock_packages({"package": [package, dict(package)]})

    def test_distinct_versions_are_retained_and_ambiguous_lookup_fails(self) -> None:
        lock = {
            "package": [
                {"name": "serde", "version": "1.0.0", "source": "registry"},
                {"name": "serde", "version": "1.0.1", "source": "registry"},
            ]
        }
        packages = SYSTEMD.index_lock_packages(lock)
        self.assertEqual(len(packages["serde"]), 2)
        with self.assertRaisesRegex(AssertionError, "ambiguous"):
            SYSTEMD.one_lock_package(packages, "serde")

    def test_malformed_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(AssertionError, "invalid source"):
            REPOSITORY.index_lock_packages(
                {"package": [{"name": "serde", "version": "1.0.0", "source": []}]}
            )


if __name__ == "__main__":
    unittest.main()
