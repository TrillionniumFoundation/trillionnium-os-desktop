"""Closed source correspondence only; actual kernel results come from Rust."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "crates/hepta-agent-transport/src/root_control_path.rs"
CONTRACT = "contracts/root-owned-control-path.v1.json"
KERNEL = "crates/hepta-agent-transport/tests/root_control_path_kernel.rs"
DOC = "docs/architecture/ROOT_OWNED_CONTROL_PATH.md"
KEYS = {
    "": {"schema", "status", "platform", "implementation", "pathname", "listener", "connector", "custody", "deadline", "public_api", "tests", "non_claims"},
    "pathname": {"maximum_bytes", "maximum_components", "encoding", "ancestor_uid", "ancestor_group_world_write", "direct_parent_modes", "socket_uid", "socket_modes", "socket_group", "socket_links", "all_components_nofollow"},
    "listener": {"consumes_owned_fd", "root_effective_uid_required", "creator", "type", "bound_inode", "ioctl_requires_privileged_profile", "missing_fact_fallback", "bind_relisten_chmod_chown_unlink", "capability_or_service_configuration_changed", "nonblocking_status_retained"},
    "connector": {"approved_kernel_policy", "evidence", "independent_server_kernel_bound_inode_proof", "approved_live_executable", "approved_systemd_unit", "semantic_principal"},
    "custody": {"same_original_fd_transferred", "same_absolute_instant_transferred", "unique_owner", "peer_incarnation", "later_verification", "observed_failure", "foreign_drop", "later_consumer_must_preserve_verifier", "raw_fd_escape_is_retained_proof", "live_exec_drift_detection"},
    "deadline": {"maximum_seconds", "input", "renewal", "synchronous_syscalls_preemptively_timed_out"},
    "tests": {"kernel", "contract_only", "required_privileged_kernel_groups", "profile"},
    "non_claims": {"installed_activation", "product_ready", "approved_policy_loader", "cross_uid_live_attestation_broker", "approved_executable_or_unit", "semantic_principal", "native_effect_authority", "all_async_or_admin_path_races_closed"},
}
FALSE = {
    "pathname": {"ancestor_group_world_write"},
    "listener": {"missing_fact_fallback", "bind_relisten_chmod_chown_unlink", "capability_or_service_configuration_changed"},
    "connector": {"independent_server_kernel_bound_inode_proof", "approved_live_executable", "approved_systemd_unit", "semantic_principal"},
    "custody": {"raw_fd_escape_is_retained_proof", "live_exec_drift_detection"},
    "deadline": {"renewal", "synchronous_syscalls_preemptively_timed_out"},
    "non_claims": KEYS["non_claims"],
}
TRUE = {
    "pathname": {"all_components_nofollow"},
    "listener": {"consumes_owned_fd", "root_effective_uid_required", "ioctl_requires_privileged_profile", "nonblocking_status_retained"},
    "custody": {"same_original_fd_transferred", "same_absolute_instant_transferred", "unique_owner", "later_consumer_must_preserve_verifier"},
}
NUMBERS = {"pathname": {"maximum_bytes": 107, "maximum_components": 32, "ancestor_uid": 0, "socket_uid": 0, "socket_links": 1}, "deadline": {"maximum_seconds": 20}, "tests": {"required_privileged_kernel_groups": 12}}


def signatures(source):
    result = {}
    for found in re.finditer(r"impl (\w+)\s*\{", source):
        start = found.end()
        depth = 1
        end = start
        while depth:
            depth += (source[end] == "{") - (source[end] == "}")
            end += 1
        for fn in re.finditer(r"pub fn (\w+)([^\{]+)\{", source[start:end - 1]):
            result[found[1] + "::" + fn[1]] = " ".join(("pub fn " + fn[1] + fn[2]).split())
    if len(result) != len(re.findall(r"\bpub fn\b", source)):
        raise ValueError("unregistered public function")
    return result


def validate(value, source):
    for section, expected in KEYS.items():
        actual = value if not section else value.get(section)
        if type(actual) is not dict or set(actual) != expected:
            raise ValueError("closed object " + section)
    if (value["schema"], value["status"], value["platform"], value["implementation"]) != (
        "trillionnium.desktop.root-owned-control-path.v1", "SOURCE_PATH_AND_KERNEL_CUSTODY_CANDIDATE", "Linux", SOURCE
    ):
        raise ValueError("source identity")
    for section, fields in FALSE.items():
        if any(value[section][key] is not False for key in fields):
            raise ValueError("claim ceiling " + section)
    for section, fields in TRUE.items():
        if any(value[section][key] is not True for key in fields):
            raise ValueError("custody obligation " + section)
    for section, fields in NUMBERS.items():
        for key, expected in fields.items():
            if type(value[section][key]) is not int or value[section][key] != expected:
                raise ValueError("strict integer " + key)
    if value["pathname"]["direct_parent_modes"] != ["0700", "0750"] or value["pathname"]["socket_modes"] != ["0600", "0660"]:
        raise ValueError("closed supported modes")
    if value["tests"]["kernel"] != KERNEL or value["tests"]["contract_only"] != "tests/test_root_control_path.py":
        raise ValueError("actual corpus registration")
    if type(value["public_api"]) is not dict or value["public_api"] != signatures(source) or len(value["public_api"]) != 8:
        raise ValueError("exact additive public API")
    for section in KEYS:
        if not section or section == "non_claims":
            continue
        for key, item in value[section].items():
            if key in FALSE.get(section, set()) | TRUE.get(section, set()) | set(NUMBERS.get(section, {})):
                continue
            if isinstance(item, list):
                continue
            if type(item) is not str or not item:
                raise ValueError("typed contract prose")


class RootControlPathSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / CONTRACT).read_text())
        cls.source = (ROOT / SOURCE).read_text()

    def test_closed_contract_matches_exact_eight_source_signatures(self):
        validate(self.contract, self.source)
        self.assertEqual(set(self.contract["public_api"]), {
            "RootControlPathPolicy::new", "RootOwnedControlListener::from_inherited", "RootOwnedControlListener::accept_before",
            "RootPathControlConnection::connect_before", "RootPathControlConnection::deadline", "RootPathControlConnection::consume_before",
            "RootControlPathCustody::verifier", "RootControlPathVerifier::verify_current",
        })

    def test_strict_integer_and_false_claim_aliases_are_refused(self):
        for section, fields in NUMBERS.items():
            for key, expected in fields.items():
                for wrong in (True, float(expected), str(expected), expected + 1):
                    mutant = copy.deepcopy(self.contract)
                    mutant[section][key] = wrong
                    with self.subTest(section=section, key=key, wrong=wrong), self.assertRaises(ValueError):
                        validate(mutant, self.source)
        for section, fields in FALSE.items():
            for key in fields:
                for wrong in (True, 0, None):
                    mutant = copy.deepcopy(self.contract)
                    mutant[section][key] = wrong
                    with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                        validate(mutant, self.source)

    def test_missing_extra_and_modified_public_api_are_refused(self):
        for section, fields in KEYS.items():
            for key in fields:
                mutant = copy.deepcopy(self.contract)
                target = mutant[section] if section else mutant
                del target[key]
                with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                    validate(mutant, self.source)
            mutant = copy.deepcopy(self.contract)
            (mutant[section] if section else mutant)["unexpected"] = False
            with self.assertRaises(ValueError):
                validate(mutant, self.source)
        mutant = copy.deepcopy(self.contract)
        mutant["public_api"]["RootPathControlConnection::deadline"] += " invented"
        with self.assertRaises(ValueError):
            validate(mutant, self.source)

    def test_actual_kernel_binding_and_creator_profile_have_no_fallback(self):
        self.assertIn("libc::ioctl(socket.as_raw_fd(), SIOCUNIXFILE)", self.source)
        self.assertIn("SO_PEERPIDFD", self.source)
        self.assertIn("identity.pid != Some(owner_pid)", self.source)
        self.assertIn("!= self.creator_identity", self.source)
        self.assertIn("snapshot.identities.last() != Some(&bound_identity)", self.source)
        self.assertIn("libc::O_NOFOLLOW", self.source)
        for forbidden in ("libc::bind", "libc::listen", "libc::chmod", "libc::chown", "libc::unlink", "libc::shutdown", "SYS_pidfd_open"):
            self.assertNotIn(forbidden, self.source)
        self.assertIn("RootControlPathCustody { scope: panic!() }", self.source)

    def test_kernel_profile_and_source_checks_are_registered_without_skip(self):
        cargo = tomllib.loads((ROOT / "crates/hepta-agent-transport/Cargo.toml").read_text())
        target = next(v for v in cargo["test"] if v["name"] == "root_control_path_kernel")
        self.assertEqual(target, {"name": "root_control_path_kernel", "path": "tests/root_control_path_kernel.rs", "harness": False})
        kernel = (ROOT / KERNEL).read_text()
        self.assertIn('Command::new("/usr/bin/sudo")', kernel)
        self.assertIn("SYS_capset", kernel)
        self.assertIn("actual kernel old bound dentry", kernel)
        self.assertIn("no skip", kernel)
        self.assertNotIn("#[ignore]", kernel)
        workflow = (ROOT / ".github/workflows/agent-port-custody.yml").read_text()
        self.assertIn("cargo test --workspace --all-targets --locked", workflow)
        self.assertIn("test_root_control_path.py", workflow)
        module = next(v for v in json.loads((ROOT / "manifests/modules.v1.json").read_text())["modules"] if v["id"] == "hepta-agent-transport")
        for name, field in ((CONTRACT, "contracts"), (DOC, "architecture"), (KERNEL, "tests")):
            self.assertIn(name, module[field])

    def test_existing_product_entry_and_capability_presets_remain_closed(self):
        main = (ROOT / "apps/hepta-agent-portd/src/main.rs").read_text()
        self.assertIn("Err(ServiceError::ProductHandlerUnavailable)", main)
        service = (ROOT / "packaging/debian/systemd/hepta-browserd-agent@.service").read_text()
        self.assertIn("CapabilityBoundingSet=\n", service)
        self.assertIn("AmbientCapabilities=\n", service)
        self.assertNotIn("CAP_NET_ADMIN", service)
        doc = (ROOT / DOC).read_text()
        self.assertIn("including PID1", doc)
        self.assertIn("not independently", doc)
        self.assertIn("live attestation broker", doc)

    def test_actual_complete_workflow_guards_refuse_matches_and_read_errors(self):
        # Real shell/native grep/strings/cargo on isolated fixtures. These are
        # absence-guard regressions, not daemon, transport or product evidence.
        lines = (ROOT / ".github/workflows/agent-port-custody.yml").read_text().splitlines()

        def block(name):
            start = next(i for i, line in enumerate(lines) if line.strip() == "- name: " + name)
            run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
            indent = len(lines[run]) - len(lines[run].lstrip())
            body = []
            for line in lines[run + 1:]:
                if line.strip() and len(line) - len(line.lstrip()) <= indent:
                    break
                body.append(line[indent + 2:] if len(line) > indent + 2 else "")
            return "\n".join(body) + "\n"

        built_guard = block("Build and audit the production binary graph")
        source_guard = block("Reconfirm closed authority and activation ceiling")
        with tempfile.TemporaryDirectory(prefix="root-path-workflow-guard-") as temporary:
            root = Path(temporary)
            for name in ("apps/hepta-agent-portd/src/main.rs",
                         "apps/hepta-agent-portd/src/bin/hepta-agent-port-fixture.rs",
                         "contracts/agent-port-custody.v1.json",
                         "packaging/debian/hepta-agent-portd.install"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            (root / "crates/hepta-peer-attestation/src").mkdir(parents=True)
            (root / "native-temp").mkdir()
            env = os.environ.copy()
            env.update(RUNNER_TEMP=str(root / "native-temp"),
                       CARGO_TARGET_DIR=str(root / "target"), CARGO_NET_OFFLINE="true")

            def execute(body):
                return subprocess.run(["/bin/bash", "-e", "-o", "pipefail", "-c", body],
                                      cwd=root, env=env, timeout=30, capture_output=True, text=True)

            positive = execute(source_guard)
            self.assertEqual(positive.returncode, 0, positive.stdout + positive.stderr)
            main = root / "apps/hepta-agent-portd/src/main.rs"
            original = main.read_bytes()
            for marker in ("UnixListener", "D0FixtureHandler"):
                main.write_bytes(original + ("\n// absence-guard test: " + marker + "\n").encode())
                self.assertNotEqual(execute(source_guard).returncode, 0)
            main.unlink()
            self.assertNotEqual(execute(source_guard).returncode, 0, "native grep read error")
            main.write_bytes(original)

            # A dependency-free independently built ELF fixture lets the full
            # original cargo-clean/build/strings workflow body run unchanged.
            # The fixture never represents the production binary or identity.
            (root / "Cargo.toml").write_text(
                '[package]\nname = "hepta-agent-portd"\nversion = "0.0.0"\nedition = "2024"\n')
            (root / "Cargo.lock").write_text(
                'version = 4\n\n[[package]]\nname = "hepta-agent-portd"\nversion = "0.0.0"\n')
            (root / "src").mkdir()
            mini_main = root / "src/main.rs"
            mini_main.write_text('fn main() { println!("closed-source-guard-fixture"); }\n')
            positive = execute(built_guard)
            self.assertEqual(positive.returncode, 0, positive.stdout + positive.stderr)
            for marker in ("D0FixtureHandler", "agent-port-fixture-self-check"):
                mini_main.write_text('fn main() { println!("' + marker + '"); }\n')
                self.assertNotEqual(execute(built_guard).returncode, 0)
            mini_main.write_text('fn main() { println!("closed-source-guard-fixture"); }\n')
            install = root / "packaging/debian/hepta-agent-portd.install"
            install_original = install.read_bytes()
            install.write_bytes(install_original + b'hepta-agent-port-fixture\n')
            self.assertNotEqual(execute(built_guard).returncode, 0)
            install.unlink()
            self.assertNotEqual(execute(built_guard).returncode, 0, "native grep read error")
            install.write_bytes(install_original)
            native_error = root / "native-error-bin"
            native_error.mkdir()
            strings = native_error / "strings"
            # Add a missing input to the actual native strings executable;
            # the shim does not manufacture its output or exit status.
            strings.write_text('#!/bin/sh\nexec /usr/bin/strings "$@" "$RUNNER_TEMP/missing-native-input"\n')
            strings.chmod(0o700)
            env["PATH"] = str(native_error) + os.pathsep + env["PATH"]
            self.assertNotEqual(execute(built_guard).returncode, 0, "native strings read error")
            self.assertEqual(list((root / "native-temp").iterdir()), [], "owned strings files retired")


if __name__ == "__main__":
    unittest.main()
