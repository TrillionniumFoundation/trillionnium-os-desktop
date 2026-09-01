from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_d3_development_profile_under_test",
    ROOT / "tools/validate_d3_development_profile.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class D3PersistentProfileTests(unittest.TestCase):
    def test_repository_profile_passes(self) -> None:
        self.assertEqual(VALIDATOR.main(), 0)

    def test_accept_yes_regression_is_rejected(self) -> None:
        original_root = VALIDATOR.ROOT
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = original_root / "packaging/debian/systemd/hepta-browserd-agent-development.socket"
            target = root / "packaging/debian/systemd/hepta-browserd-agent-development.socket"
            target.parent.mkdir(parents=True)
            target.write_text(
                source.read_text(encoding="utf-8").replace("Accept=no", "Accept=yes"),
                encoding="utf-8",
            )
            VALIDATOR.ROOT = root
            VALIDATOR.ERRORS.clear()
            VALIDATOR.check_units()
            self.assertTrue(any("Accept" in error for error in VALIDATOR.ERRORS))
        VALIDATOR.ROOT = original_root
        VALIDATOR.ERRORS.clear()

    def test_self_bound_listener_regression_is_rejected(self) -> None:
        original_root = VALIDATOR.ROOT
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "crates/hepta-d3-development/src/bin/sessiond.rs"
            path.parent.mkdir(parents=True)
            path.write_text(
                "UnixListener::bind(\"/run/hepta/browserd/agent-development.sock\");\n",
                encoding="utf-8",
            )
            VALIDATOR.ROOT = root
            VALIDATOR.ERRORS.clear()
            VALIDATOR.check_session_daemon()
            self.assertTrue(any("UnixListener::bind" in error for error in VALIDATOR.ERRORS))
        VALIDATOR.ROOT = original_root
        VALIDATOR.ERRORS.clear()


if __name__ == "__main__":
    unittest.main()
