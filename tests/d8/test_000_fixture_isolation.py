from __future__ import annotations

import shutil
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import hardware_evidence_verifier as verifier  # noqa: E402

_ORIGINAL_CREATE_FIXTURE_BUNDLE = verifier.create_fixture_bundle


def isolated_fixture_bundle(contract, root: Path, seed: bytes):
    root.mkdir(parents=True, exist_ok=True)
    for child in list(root.iterdir()):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    evidence, trust = _ORIGINAL_CREATE_FIXTURE_BUNDLE(contract, root, seed)
    # Physical-shaped negative tests cover a complete 72-hour interval. The
    # deterministic fixture key remains non-production but its validity window
    # must encompass that interval so tests reach the intended policy check.
    trust["labs"]["fixture-lab"]["keys"]["fixture-lab-key-1"][
        "expires_at_epoch"
    ] = 10**9
    return evidence, trust


verifier.create_fixture_bundle = isolated_fixture_bundle


class FixtureIsolationTests(unittest.TestCase):
    def test_fixture_factory_is_patched_before_other_test_modules_import_it(self) -> None:
        self.assertIs(verifier.create_fixture_bundle, isolated_fixture_bundle)


if __name__ == "__main__":
    unittest.main()
