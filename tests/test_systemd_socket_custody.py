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
            custody.SOCKET_CUSTODY, custody.SERVICE_CUSTODY,
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


class SystemdEffectiveCustodyGrammarTests(unittest.TestCase):
    setUp = SystemdSocketCustodyFeatureTests.setUp
    audit = SystemdSocketCustodyFeatureTests.audit
    mutate = SystemdSocketCustodyFeatureTests.mutate
    SYSUSERS = "packaging/debian/sysusers.d/trillionnium-desktop.conf"
    TMPFILES = "packaging/debian/tmpfiles.d/trillionnium-desktop.conf"
    SERVICE_DROPIN = "packaging/debian/systemd/hepta-browserd-agent@.service.d/10-root-path-custody.conf"
    SOCKET_DROPIN = "packaging/debian/systemd/hepta-browserd-agent.socket.d/10-root-path-custody.conf"

    def refuse_mutation(self, relative, mutate):
        path = self.root / relative
        baseline = path.read_text()
        try:
            path.write_text(mutate(baseline))
            completed = self.audit()
        finally:
            path.write_text(baseline)
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertTrue(completed.stderr.startswith("AgentPort custody and fixture separation audit: FAIL: "), completed.stderr)
        self.assertEqual(len(completed.stderr.splitlines()), 1, completed.stderr)
        self.assertNotIn("CONTROLLED-CUSTODY-CANARY", completed.stderr)

    def test_actual_gate_accepts_safe_spaces_tabs_and_effective_empty_lists(self):
        for relative in (self.SYSUSERS, self.TMPFILES):
            path = self.root / relative
            text = path.read_text()
            if relative == self.SYSUSERS:
                text = text.replace("m      hepta-browserd   hepta-agent", "  m\thepta-browserd\thepta-agent  ")
                text = text.replace("m      hepta-agent      hepta-agent-socket", "m hepta-agent hepta-agent-socket")
            else:
                text = "\n".join("\t".join(line.split()) if line.startswith("d ") else line for line in text.splitlines()) + "\n"
            path.write_text(text)
        for relative in (self.SERVICE_DROPIN, self.SOCKET_DROPIN):
            path = self.root / relative
            text = path.read_text().replace("[Service]", "  [Service]  ").replace("[Socket]", "\t[Socket]\t")
            path.write_text(text.replace("=", " \t=\t "))
        completed = self.audit()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("fixture separation audit: PASS", completed.stdout)

    def test_actual_gate_rejects_browser_parent_group_with_spaces_and_tabs(self):
        for record in ("m hepta-browserd hepta-agent-socket\n", "m\thepta-browserd\thepta-agent-socket\n"):
            with self.subTest(record=record):
                self.refuse_mutation(self.SYSUSERS, lambda text: text + record)

    def test_actual_gate_rejects_comment_only_agent_membership(self):
        self.refuse_mutation(self.SYSUSERS, lambda text: text.replace(
            "m      hepta-agent      hepta-agent-socket", "# m      hepta-agent      hepta-agent-socket"))

    def test_actual_gate_rejects_duplicate_or_conflicting_membership(self):
        for record in ("m hepta-agent hepta-agent-socket\n", "m hepta-agent hepta-browserd\n"):
            with self.subTest(record=record):
                self.refuse_mutation(self.SYSUSERS, lambda text: text + record)

    def test_actual_gate_rejects_comment_decoy_parent_mapping(self):
        self.refuse_mutation(self.TMPFILES, lambda text: text.replace(
            "d      /run/hepta/browserd          0750 root            hepta-agent-socket   -   -",
            "# d      /run/hepta/browserd          0750 root            hepta-agent-socket   -   -\n"
            "d /run/hepta/browserd 0770 root hepta-browserd - -"))

    def test_actual_gate_rejects_duplicate_or_conflicting_parent(self):
        for record in ("d /run/hepta/browserd 0750 root hepta-agent-socket - -\n",
                       "d /run/hepta/browserd 0770 root hepta-browserd - -\n"):
            with self.subTest(record=record):
                self.refuse_mutation(self.TMPFILES, lambda text: text + record)

    def test_actual_gate_rejects_spaced_post_reset_authority(self):
        for record in ("SupplementaryGroups = hepta-agent-socket\n", "ReadWritePaths \t= /run/hepta/browserd\n"):
            with self.subTest(record=record):
                self.refuse_mutation(self.SERVICE_DROPIN, lambda text: text + record)

    def test_actual_gate_rejects_unsupported_unit_syntax_without_disclosure(self):
        for record in ('SupplementaryGroups="hepta-agent-socket"\n', "SupplementaryGroups=hepta-agent-socket\\\n",
                       "SupplementaryGroups=%g\n", "SupplementaryGroups=${CONTROLLED-CUSTODY-CANARY}\n",
                       "UnknownCustodyKey=CONTROLLED-CUSTODY-CANARY\n"):
            with self.subTest(record=record):
                self.refuse_mutation(self.SERVICE_DROPIN, lambda text: text + record)

    def test_actual_gate_rejects_missing_or_uninstalled_dropins(self):
        for relative in (self.SERVICE_DROPIN, self.SOCKET_DROPIN):
            with self.subTest(relative=relative, mutation="missing"):
                path = self.root / relative
                original = path.read_bytes()
                path.unlink()
                try:
                    completed = self.audit()
                finally:
                    path.write_bytes(original)
                self.assertEqual(completed.returncode, 1, completed.stderr)
                self.assertEqual(completed.stdout, "")
                self.assertEqual(completed.stderr,
                    "AgentPort custody and fixture separation audit: FAIL: SOURCE_INVALID\n")
            with self.subTest(relative=relative, mutation="wrong destination"):
                self.refuse_mutation("packaging/debian/hepta-agent-portd.install", lambda text: text.replace(
                    relative + " lib/systemd/system/", relative + " wrong/systemd/system/"))

    def test_actual_gate_keeps_disabled_and_marker_invariants(self):
        self.refuse_mutation("packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
                            lambda text: text.replace("disable ", "enable "))
        self.refuse_mutation("packaging/debian/hepta-agent-portd.install",
                            lambda text: text + "controlled/enable-agent-port etc/hepta\n")

    def test_actual_gate_keeps_unknown_parser_input_out_of_diagnostics(self):
        self.refuse_mutation("apps/hepta-agent-portd/Cargo.toml", lambda text: text + "\n[CONTROLLED-CUSTODY-CANARY\n")
        self.refuse_mutation(self.SYSUSERS, lambda text: text + 'm "CONTROLLED-CUSTODY-CANARY" hepta-agent-socket\n')
        self.refuse_mutation(self.TMPFILES, lambda text: text + "d /CONTROLLED-CUSTODY-CANARY 0750 root root - - extra\n")

    def test_actual_gate_rejects_internal_section_spaces_and_tabs(self):
        for relative, section in ((self.SERVICE_DROPIN, "Service"), (self.SOCKET_DROPIN, "Socket")):
            for header in ("[ " + section + "]", "[" + section + " ]",
                           "[\t" + section + "]", "[" + section + "\t]", "[ " + section + " ]"):
                with self.subTest(relative=relative, header=header):
                    self.refuse_mutation(relative, lambda text: text.replace("[" + section + "]", header, 1))


if __name__ == "__main__":
    unittest.main()
