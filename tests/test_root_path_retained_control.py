"""Closed source correspondence; privileged kernel tests supply actual facts."""
import copy
import json
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "crates/hepta-peer-attestation/src/control_owner/root_path.rs"
CONTRACT = "contracts/root-path-retained-control.v1.json"
KERNEL = "apps/hepta-browserd/tests/product_root_path_kernel.rs"
EXPECTED = json.loads(r"""{
  "schema": "trillionnium.desktop.root-path-retained-control.v1",
  "status": "SOURCE_SAME_FD_PATH_AND_LIVE_CONTROL_BRIDGE",
  "platform": "Linux",
  "implementation": {
    "bridge": "crates/hepta-peer-attestation/src/control_owner/root_path.rs",
    "peer": "crates/hepta-peer-attestation/src/control_owner.rs",
    "request": "crates/hepta-peer-attestation/src/control_owner/control_request.rs",
    "retained": "crates/hepta-peer-attestation/src/control_owner/retained_request.rs",
    "coordinator": "apps/hepta-browserd/src/product_dispatch/product_control_wait.rs"
  },
  "ownership": {
    "consumed_original_fd": true,
    "unique_root_path_custody_retained": true,
    "private_shared_path_lifetime": "one private Arc owns the sole non-cloneable path custody; reporting and action verifiers cannot mint another custody",
    "bare_fd_or_legacy_receive_export": false,
    "path_at_every_alive_and_current_boundary": true,
    "action_drop_or_revoke": "permanently revokes execution; independent original reporting identity can still publish one existing sealed journal terminal while its path remains current",
    "path_failure": "original path latch is irreversible; restore or replacement cannot revive the bridge",
    "fork": "creator PID before path/peer/atomic checks; Drop closes only child descriptor copies, never shutdown/unlink or inherited channel synchronization",
    "reconnect_or_retry": false
  },
  "deadline": {
    "maximum_seconds": 20,
    "input": "exact existing RootPathControlConnection Instant and opaque AcceptedStreamCustody original native ceiling; neither is recaptured or allocated another Duration",
    "request": "minimum of received original accepted Instant and original root-control Instant; neither can increase",
    "report": "original existing minimum accepted/control wait deadline; no renewal",
    "renewal": false,
    "synchronous_procfs_or_path_reads_preemptively_timed_out": false,
    "sender_before_publication": "ensure_control_current checks only the original root-control ceiling; low-level send_retained checks the opaque accepted original ceiling before any descriptor packet",
    "pre_custody_accept_wait_covered": false
  },
  "approval": {
    "control_policy": "explicit existing ControlOwnerPolicy with approved executable SHA256 and unit/cgroup/UID/GID; fixed live /proc measurements only",
    "observed_peer_grants_approval": false,
    "static_fallback": false,
    "cross_uid_procfs_permission_failure": "typed refusal; actual root fixture may read its own nobody child but nobody cannot substitute for inaccessible root executable",
    "root_path_is_executable_unit_or_principal_approval": false
  },
  "public_api": {
    "RootPathAttestedHandoffSender::from_accepted": "pub fn from_accepted( connection: RootPathControlConnection, accepted: AcceptedStreamCustody, policy: ControlOwnerPolicy, ) -> Result<Self, ControlOwnerError>",
    "RootPathAttestedHandoffSender::ensure_control_current": "pub fn ensure_control_current(&mut self) -> Result<Instant, ControlOwnerError>",
    "RootPathAttestedHandoffSender::send_retained": "pub fn send_retained(&mut self) -> Result<AttestedPendingHandoff, ControlOwnerError>",
    "RootPathAttestedHandoffSender::cancel": "pub fn cancel(&mut self) -> Result<(), ControlOwnerError>",
    "RootPathAttestedHandoffReceiver::from_control": "pub fn from_control( connection: RootPathControlConnection, policy: ControlOwnerPolicy, expected_local_path: &Path, ) -> Result<Self, ControlOwnerError>",
    "RootPathAttestedHandoffReceiver::ensure_current": "pub fn ensure_current(&mut self) -> Result<Instant, ControlOwnerError>",
    "RootPathAttestedHandoffReceiver::receive_retained_custodied": "pub fn receive_retained_custodied( &mut self, ) -> Result<ControlRetainedAcceptedStream, ControlOwnerError>",
    "RootPathAttestedHandoffReceiver::cancel": "pub fn cancel(&mut self) -> Result<(), ControlOwnerError>"
  },
  "evidence": {
    "kernel": "apps/hepta-browserd/tests/product_root_path_kernel.rs",
    "contract_only": "tests/test_root_path_retained_control.py",
    "workflow": ".github/workflows/agent-port-custody.yml",
    "required_privileged_kernel_groups": 11,
    "individual_verifier_entrypoints": 5,
    "Agent": "actual distinct subprocess with fixed default live /proc, explicit pre-launch owned fixture policy",
    "native_completion": "synthetic queued source callback only; never Servo execution",
    "terminal": "existing private coordinator own complete managed journal readback and report request/record binding",
    "fixture": "temporary owned root/nobody filesystem and root executable copy; missing sudo/kernel facts fail, no skip"
  },
  "non_claims": {
    "installed_broker": false,
    "approved_policy_loader": false,
    "cross_uid_live_broker_qualified": false,
    "product_ready": false,
    "default_activation_changed": false,
    "semantic_principal": false,
    "actual_native_Servo_effect": false,
    "all_async_windows_closed": false
  }
}
""")


def signatures(source):
    result = {}
    for match in re.finditer(r"impl (\w+)\s*\{", source):
        start = match.end()
        end, depth = start, 1
        while depth:
            depth += (source[end] == "{") - (source[end] == "}")
            end += 1
        for fn in re.finditer(r"pub fn (\w+)([^\{]+)\{", source[start:end - 1]):
            key = match[1] + "::" + fn[1]
            if key in result:
                raise ValueError("duplicate public API")
            result[key] = " ".join(("pub fn " + fn[1] + fn[2]).split())
    if len(result) != len(re.findall(r"\bpub fn\b", source)):
        raise ValueError("unregistered API")
    return result


def exact(value, expected):
    if type(value) is not type(expected):
        raise ValueError("exact type")
    if type(expected) is dict:
        if set(value) != set(expected):
            raise ValueError("closed fields")
        for key in expected:
            exact(value[key], expected[key])
    elif type(expected) is list:
        if len(value) != len(expected):
            raise ValueError("closed array")
        for left, right in zip(value, expected):
            exact(left, right)
    elif value != expected:
        raise ValueError("exact source ceiling")


def validate(value, source):
    exact(value, EXPECTED)
    if value["public_api"] != signatures(source) or len(value["public_api"]) != 8:
        raise ValueError("actual closed public API")


class RootPathRetainedControlSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = json.loads((ROOT / CONTRACT).read_text())
        cls.source = (ROOT / SOURCE).read_text()

    def test_exact_closed_eight_API_and_scope(self):
        validate(self.value, self.source)
        self.assertEqual(set(signatures(self.source)), set(EXPECTED["public_api"]))
        for name in ("RootPathAttestedHandoffSender", "RootPathAttestedHandoffReceiver"):
            self.assertIn(name, (ROOT / "crates/hepta-peer-attestation/src/lib.rs").read_text())
        self.assertNotIn("pub inner", self.source)
        self.assertNotIn("OwnedFd", self.source)
        self.assertNotIn("Duration", self.source)
        self.assertNotIn("ProcfsPeerAttestor", self.source)
        self.assertNotIn("capture_before", self.source)
        self.assertIn("accepted: AcceptedStreamCustody", self.source)
        self.assertIn("pub fn ensure_control_current", self.source)
        self.assertEqual(len(re.findall(r"connection\s*\.consume_before\(", self.source)), 2)

    def test_closed_fields_exact_numeric_and_false_claim_aliases(self):
        for section in (None, "implementation", "ownership", "deadline", "approval", "public_api", "evidence", "non_claims"):
            expected = self.value if section is None else self.value[section]
            for key in expected:
                mutant = copy.deepcopy(self.value)
                target = mutant if section is None else mutant[section]
                del target[key]
                with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                    validate(mutant, self.source)
            mutant = copy.deepcopy(self.value)
            (mutant if section is None else mutant[section])["foreign_approval"] = False
            with self.assertRaises(ValueError):
                validate(mutant, self.source)
            for key, item in expected.items():
                if type(item) not in (bool, int):
                    continue
                bad = [int(item), None] if type(item) is bool else [True, float(item), str(item), item + 1]
                for wrong in bad:
                    mutant = copy.deepcopy(self.value)
                    (mutant if section is None else mutant[section])[key] = wrong
                    with self.subTest(section=section, key=key, wrong=wrong), self.assertRaises(ValueError):
                        validate(mutant, self.source)

    def test_raw_descriptor_or_replacement_deadline_API_mutations_refuse(self):
        for old, new in (("connection: RootPathControlConnection", "connection: OwnedFd"),
                         ("accepted: AcceptedStreamCustody", "accepted: UnixStream"),
                         ("policy: ControlOwnerPolicy", "policy: bool"),
                         ("expected_local_path: &Path", "expected_local_path: &str")):
            mutant = self.source.replace(old, new)
            self.assertNotEqual(mutant, self.source)
            with self.assertRaises(ValueError):
                validate(self.value, mutant)
        mutant = self.source + "\npub fn escape() -> OwnedFd { panic!() }\n"
        with self.assertRaises(ValueError):
            validate(self.value, mutant)

    def test_all_request_entries_preserve_real_path_and_original_minimum(self):
        request = (ROOT / "crates/hepta-peer-attestation/src/control_owner/control_request.rs").read_text()
        owner = (ROOT / "crates/hepta-peer-attestation/src/control_owner.rs").read_text()
        retained = (ROOT / "crates/hepta-peer-attestation/src/control_owner/retained_request.rs").read_text()
        alive = request[request.index("pub fn ensure_alive"):request.index("pub fn verify_current")]
        self.assertLess(alive.index("creator(self.state.owner_pid)?"), alive.index("self.state.revoked.load"))
        self.assertEqual(alive.count("path.current()?"), 2)
        self.assertIn("root_path: Option<Arc<super::root_path::RetainedRootPath>>", request)
        self.assertIn("Arc::get_mut(&mut self.state)", request)
        self.assertIn("accepted.min(self.deadline)", owner)
        self.assertIn("let effective = owner.request_deadline(deadline)?", retained)
        self.assertIn("custody.retain_root_path(owner.root_path.as_ref())?", retained)
        self.assertIn("consumer(stream, effective, custody, retained)", retained)
        for name in ("ensure_alive", "ensure_pair_alive", "verify_current", "verify_pair_current", "deadline"):
            self.assertIn("pub fn " + name, request)
        self.assertIn("_custody: RootControlPathCustody", self.source)
        self.assertNotIn("RootControlPathCustody {", self.source)
        self.assertNotIn("libc::shutdown", self.source)

    def test_same_workspace_kernel_workflow_and_source_index(self):
        cargo = tomllib.loads((ROOT / "apps/hepta-browserd/Cargo.toml").read_text())
        target = next(item for item in cargo["test"] if item["name"] == "product_root_path_kernel")
        self.assertEqual(target, {"name": "product_root_path_kernel", "path": "tests/product_root_path_kernel.rs", "harness": False})
        workflow = (ROOT / ".github/workflows/agent-port-custody.yml").read_text()
        self.assertIn("cargo test --workspace --all-targets --locked", workflow)
        self.assertIn("test_root_path_retained_control.py -v", workflow)
        self.assertEqual(workflow.count('"contracts/root-path-retained-control.v1.json"'), 2)
        modules = json.loads((ROOT / "manifests/modules.v1.json").read_text())["modules"]
        for module in modules:
            if module["id"] in ("hepta-browserd", "hepta-peer-attestation"):
                self.assertIn(CONTRACT, module["contracts"])
                self.assertIn(KERNEL, module["tests"])
                self.assertIn("docs/architecture/ROOT_PATH_RETAINED_CONTROL.md", module["architecture"])
        self.assertIn("Err(ServiceError::ProductHandlerUnavailable)", (ROOT / "apps/hepta-agent-portd/src/main.rs").read_text())
        self.assertEqual(tomllib.loads((ROOT / "crates/hepta-peer-attestation/Cargo.toml").read_text())["features"]["default"], [])

    def test_real_subprocess_fixture_is_not_native_or_provisioning_qualification(self):
        kernel = (ROOT / KERNEL).read_text()
        self.assertIn('Command::new("/usr/bin/sudo")', kernel)
        self.assertIn("command.uid(NOBODY).gid(NOBODY)", kernel)
        self.assertIn("ProcfsPeerAttestor::default()", kernel)
        self.assertIn("explicit-policy", kernel)
        self.assertIn("REPORT {:?} {} {}", kernel)
        self.assertIn("retained.ensure_current().is_err()", kernel)
        self.assertIn("completion.ensure_active().is_err()", kernel)
        self.assertIn("actual descriptor retirement", kernel)
        self.assertNotIn("#[ignore]", kernel)
        self.assertNotIn("TrustedExecutableDigest", kernel)
        self.assertNotIn("with_proc_root", kernel)
        self.assertEqual(kernel.count('("five-verifier-entrypoints"'), 1)
        for group in ("durable-terminal", "fork-original-owner", "native-final-path-refusal", "terminal-path-refusal", "cancel-keeps-report-only-path", "earlier-original-path-deadline", "earlier-original-accepted-deadline", "expired-original-accepted-no-packet", "cross-uid-procfs-closed", "explicit-wrong-pin"):
            self.assertRegex(kernel, r'\(\s*"' + re.escape(group) + '"')
        doc = (ROOT / "docs/architecture/ROOT_PATH_RETAINED_CONTROL.md").read_text()
        self.assertIn("synthetic", doc)
        self.assertIn("not installed broker", doc)
        self.assertIn("minimum", doc)


if __name__ == "__main__":
    unittest.main()
