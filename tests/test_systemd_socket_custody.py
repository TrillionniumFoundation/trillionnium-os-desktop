from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import verify_systemd_socket_custody as custody


class SystemdSocketCustodyFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        paths = (
            custody.SOCKET, custody.SERVICE, custody.SYSUSERS, custody.TMPFILES,
            custody.PRESET, custody.INSTALL, custody.CONTRACT, custody.PORTD,
            custody.FIXTURE, custody.PORTD_CARGO, custody.ATTESTOR,
            custody.ATTESTOR_CARGO, custody.ROOT / "Cargo.toml",
            custody.ROOT / "Cargo.lock", Path(custody.__file__),
        )
        for source in paths:
            destination = self.root / source.relative_to(custody.ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    def audit(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.root / "tools/verify_systemd_socket_custody.py")],
            capture_output=True, text=True, timeout=15,
        )

    def mutate(self, relative: str, before: str, after: str) -> None:
        path = self.root / relative
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(before), 1, "mutation must change exactly one source input")
        path.write_text(text.replace(before, after), encoding="utf-8")

    def assert_refused(self, message: str) -> None:
        result = self.audit()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)

    def test_reviewed_fixture_configuration_passes_full_static_audit(self) -> None:
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fixture separation audit: PASS", result.stdout)
        self.assertIn("listener enabled by default: false", result.stdout)

    def test_fixture_feature_mapping_stays_exact(self) -> None:
        relative = "apps/hepta-agent-portd/Cargo.toml"
        path = self.root / relative
        baseline = path.read_text(encoding="utf-8")
        mutations = (
            ('  "dep:hepta-browser-codec",\n', ""),
            ('"hepta-peer-attestation/qualification-static-attestation"',
             '"hepta-peer-attestation/development-static-attestation"'),
            ('  "dep:hepta-agent-port",\n', '  "dep:hepta-agent-port",\n  "libc/std",\n'),
            ("[dependencies]", 'other-profile = []\n\n[dependencies]'),
        )
        for before, after in mutations:
            with self.subTest(mutation=after):
                path.write_text(baseline, encoding="utf-8")
                self.mutate(relative, before, after)
                self.assert_refused("fixture feature mapping changed")

    def test_each_fixture_dependency_must_remain_optional(self) -> None:
        relative = "apps/hepta-agent-portd/Cargo.toml"
        path = self.root / relative
        baseline = path.read_text(encoding="utf-8")
        for name in ("hepta-agent-port", "hepta-browser-codec"):
            with self.subTest(dependency=name):
                path.write_text(baseline, encoding="utf-8")
                before = f'{name} = {{ path = "../../crates/{name}", optional = true }}'
                self.mutate(relative, before, before.replace("optional = true", "optional = false"))
                self.assert_refused(f"fixture dependency {name} is not optional")

    def test_d1_example_cannot_enter_the_default_graph(self) -> None:
        self.mutate(
            "apps/hepta-agent-portd/Cargo.toml",
            'path = "examples/hepta-agent-d1-fixture.rs"\nrequired-features = ["fixture"]',
            'path = "examples/hepta-agent-d1-fixture.rs"',
        )
        self.assert_refused("D1 fixture example is not explicitly feature-gated")

    def test_product_default_cannot_enable_fixture(self) -> None:
        self.mutate("apps/hepta-agent-portd/Cargo.toml", "default = []", 'default = ["fixture"]')
        self.assert_refused("fixture feature is enabled by default")

    def test_attestor_default_cannot_enable_qualification(self) -> None:
        self.mutate("crates/hepta-peer-attestation/Cargo.toml", "default = []",
                    'default = ["qualification-static-attestation"]')
        self.assert_refused("peer attestor features are enabled by default")

    def test_product_dependency_cannot_enable_qualification(self) -> None:
        self.mutate(
            "apps/hepta-agent-portd/Cargo.toml",
            'hepta-peer-attestation = { path = "../../crates/hepta-peer-attestation" }',
            'hepta-peer-attestation = { path = "../../crates/hepta-peer-attestation", features = ["qualification-static-attestation"] }',
        )
        self.assert_refused("product dependency enables peer attestor features")


if __name__ == "__main__":
    unittest.main()
