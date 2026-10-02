"""Closed source correspondence only; real Rust kernel corpora supply facts."""
import copy
import json
from pathlib import Path
import re
import tomllib
import unittest
from test_root_path_retained_control import signatures, exact
ROOT=Path(__file__).resolve().parents[1]
CONTRACT="contracts/approved-mechanism-policy.v1.json"
SOURCE="crates/hepta-peer-attestation/src/approved_policy.rs"
PRODUCT="apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs"
EXPECTED=json.loads(r'''{
  "schema": "trillionnium.desktop.approved-mechanism-policy.v1",
  "status": "SOURCE_ROOTED_CONFIGURATION_WITH_LIVE_RETAINED_CHECKS",
  "platform": "Linux",
  "implementation": {
    "loader": "crates/hepta-peer-attestation/src/approved_policy.rs",
    "control": "crates/hepta-peer-attestation/src/control_owner.rs",
    "lease": "crates/hepta-peer-attestation/src/control_owner/control_request.rs",
    "root_bridge": "crates/hepta-peer-attestation/src/control_owner/root_path/approved.rs",
    "retained": "crates/hepta-peer-attestation/src/control_owner/retained_request.rs",
    "coordinator": "apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs"
  },
  "format": {
    "schema_line": "schema=trillionnium.approved-mechanisms.v1",
    "maximum_bytes": 8192,
    "maximum_path_bytes": 1024,
    "maximum_path_components": 32,
    "field_count": 13,
    "encoding": "ASCII; LF terminated; exactly one key=value per nonempty line; keys may be permuted; no comments, whitespace, escaping, include, environment or NSS",
    "fields": [
      "schema",
      "control.uid",
      "control.gid",
      "control.unit",
      "control.cgroup",
      "control.elf_sha256",
      "control.principal_id",
      "agent.uid",
      "agent.gid",
      "agent.unit",
      "agent.cgroup",
      "agent.elf_sha256",
      "agent.principal_id"
    ],
    "uid_gid": "canonical decimal 0..4294967294; no leading zeros except 0, sign, boolean, float or whitespace; explicit same UID/GID roles allowed",
    "unit": "ASCII alphanumeric or @_.:-, at most128 bytes, nonempty .service stem; exact unit, no pattern",
    "cgroup": "absolute ASCII path at most512 bytes; nonempty components at most128 bytes; alphanumeric or @_.:-; no . or .. components; final component equals configured unit",
    "elf_sha256": "exactly64 lowercase hexadecimal characters; hash of live executable must match this configured pin",
    "principal_id": "1..64 ASCII bytes, starts alphanumeric, remaining alphanumeric or _.-; Control and Agent tags must differ; no TaskFlow, PageOwner or capability grant",
    "golden": "contracts/fixtures/approved-mechanisms.v1.conf",
    "golden_is_approved_production_configuration": false
  },
  "custody": {
    "default_path": "/etc/hepta/approved-mechanisms.v1.conf",
    "missing_or_empty": "typed refusal; never create or repair configuration",
    "directories": "every absolute component retained O_PATH/O_DIRECTORY/O_NOFOLLOW; UID0, no group/other write; named/retained dev+ino+mode+UID+GID checked before and after",
    "leaf": "retained O_RDONLY/O_NONBLOCK/O_NOFOLLOW/CLOEXEC; regular UID0, nlink1, no group/other write, size1..8192; retained/named dev+ino+mode+UID+GID+size+nlink+mtime+ctime and same pread bytes SHA256 rechecked; access time excluded",
    "namespaces": "actual /proc/thread-self/ns/user,mnt,time dev/inode before and after; selected local namespaces only, not host production root",
    "observed_change": "irreversibly retires this shared loaded source; byte/path/namespace restore cannot revive it",
    "source_drift_at_action_and_reporting": true,
    "reload_can_approve_old_received_stream": false,
    "public_policy_export": false,
    "fork": "creator PID before state/atomic/alias inspection and callbacks; child Drop only closes its descriptor copies; no shutdown, unlock, unlink or inherited channel synchronization",
    "fixed_live_procfs_only": true,
    "static_or_permission_fallback": false,
    "observed_peer_mints_approval": false
  },
  "deadline": {
    "maximum_seconds": 20,
    "input": "one caller-supplied absolute Instant captured by trusted entrance, bounded at load; each bound connection uses minimum policy, root-control and accepted original ceilings",
    "action_and_report": "same minimum original ceilings; no renewed duration budget or accepted capture in approved route",
    "renewal": false,
    "late_return": "typed refusal after original ceiling; synchronous filesystem/procfs syscalls are not preemptively interrupted",
    "pre_custody_wait_covered": false
  },
  "public_api": {
    "ApprovedPolicyDocument::open_default_before": "pub fn open_default_before(deadline: Instant) -> Result<Self, ApprovedPolicyError>",
    "ApprovedPolicyDocument::open_root_owned_before": "pub fn open_root_owned_before( path: &Path, deadline: Instant, ) -> Result<Self, ApprovedPolicyError>",
    "ApprovedPolicyDocument::ensure_current": "pub fn ensure_current(&self) -> Result<(), ApprovedPolicyError>",
    "ApprovedPolicyDocument::select_control": "pub fn select_control(&self) -> Result<ApprovedControlSelection, ApprovedPolicyError>",
    "ApprovedPolicyDocument::select_agent": "pub fn select_agent(&self) -> Result<ApprovedAgentSelection, ApprovedPolicyError>",
    "ApprovedControlSelection::bind_sender": "pub fn bind_sender( self, connection: RootPathControlConnection, accepted: AcceptedStreamCustody, ) -> Result<RootPathAttestedHandoffSender, ApprovedPolicyError>",
    "ApprovedControlSelection::bind_receiver": "pub fn bind_receiver( self, connection: RootPathControlConnection, expected_local_path: &Path, ) -> Result<RootPathAttestedHandoffReceiver, ApprovedPolicyError>",
    "ApprovedAgentSelection::admit_retained": "pub fn admit_retained( self, received: ControlRetainedAcceptedStream, ) -> Result<ApprovedAgentReceivedStream, ApprovedPolicyError>",
    "ApprovedAgentReceivedStream::consume_before": "pub fn consume_before<T>( mut self, consumer: impl FnOnce( UnixStream, Instant, ControlRequestCustody, AttestedRetainedReceiver, AttestedPeer, &str, ) -> T, ) -> Result<T, ApprovedPolicyError>",
    "ApprovedRetainedProductConnection::from_received": "pub fn from_received( received: ControlRetainedAcceptedStream, selection: hepta_peer_attestation::ApprovedAgentSelection, ) -> Result<(Self, ProductControlMonitor), ProductDispatchError>",
    "ApprovedRetainedProductConnection::deadline": "pub fn deadline(&self) -> Result<Instant, ProductDispatchError>",
    "ApprovedRetainedProductConnection::cancellation": "pub fn cancellation(&self) -> Result<ProductConnectionCancellation, ProductDispatchError>",
    "ProductRequestCoordinator::from_approved_retained_connection": "pub fn from_approved_retained_connection( bootstrap: &ApprovedRetainedProductConnection, endpoint: ServoRuntimeEndpoint, journal: ReceiptJournal, image_id: String, restart_policy: RestartPolicy, ) -> Result<Self, ProductDispatchError>",
    "ProductRequestCoordinator::serve_approved_retained_connection": "pub fn serve_approved_retained_connection( &mut self, connection: ApprovedRetainedProductConnection, ) -> Result<ServiceEvidence, ProductDispatchError>"
  },
  "evidence": {
    "source_kernel": "crates/hepta-peer-attestation/tests/approved_policy_kernel.rs",
    "source_kernel_groups": 17,
    "product_kernel": "apps/hepta-browserd/tests/approved_policy_product_kernel.rs",
    "product_kernel_groups": 12,
    "verifier_entrypoints": 5,
    "source_contract_tests": "tests/test_approved_mechanism_policy.py",
    "workflow": ".github/workflows/approved-mechanism-policy.yml",
    "live_fixture": "actual transient systemd unit selected before launch; root-owned copied known ELF pinned before Control and Agent launch; root/nobody filesystem and live procfs permission refusal",
    "native_completion": "synthetic source callback; existing own-journal durable terminal and remote assertion only, never Servo effect"
  },
  "non_claims": {
    "installed_configuration": false,
    "host_root_authority": false,
    "broker_or_service_handoff": false,
    "TaskFlow_action_authority": false,
    "PageOwner_mapping": false,
    "native_Servo_effect": false,
    "persistent_revision_or_rollback_floor": false,
    "all_async_windows_closed": false,
    "product_ready": false,
    "default_activation_changed": false
  }
}
''')
def apis(source, product):
    values=signatures(source)
    values.update(signatures(product))
    return values

def validate(value,source,product):
    exact(value,EXPECTED)
    if value["public_api"]!=apis(source,product) or len(value["public_api"])!=14:
        raise ValueError("actual closed public API")
    for key in ("/proc/thread-self/ns/user", "/proc/thread-self/ns/mnt", "/proc/thread-self/ns/time", "libc::O_NOFOLLOW", "libc::O_NONBLOCK", "Sha256::digest", "read_at", "retired.store(true", "ProcfsPeerAttestor::default()", "verify_approved_agent_source"):
        if key not in source:raise ValueError("source boundary missing")
    if "pub policy" in source or "pub guard" in source or "std::env" in source or "capture_before" in source:
        raise ValueError("detached or observed authority")

class ApprovedMechanismPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value=json.loads((ROOT/CONTRACT).read_text())
        cls.source=(ROOT/SOURCE).read_text()
        cls.product=(ROOT/PRODUCT).read_text()
    def test_closed_fourteen_actual_API_and_exports(self):
        validate(self.value,self.source,self.product)
        peer=(ROOT/"crates/hepta-peer-attestation/src/lib.rs").read_text()
        browser=(ROOT/"apps/hepta-browserd/src/lib.rs").read_text()
        for name in ("ApprovedPolicyDocument","ApprovedControlSelection","ApprovedAgentSelection","ApprovedAgentReceivedStream","ApprovedPolicyError"):
            self.assertIn(name,peer)
        self.assertIn("ApprovedRetainedProductConnection",browser)
    def test_closed_contract_mutations_and_exact_scalar_types(self):
        for section in (None,"implementation","format","custody","deadline","public_api","evidence","non_claims"):
            target=self.value if section is None else self.value[section]
            for key,item in target.items():
                mutant=copy.deepcopy(self.value);part=mutant if section is None else mutant[section];del part[key]
                with self.assertRaises(ValueError):validate(mutant,self.source,self.product)
                if type(item) in (bool,int):
                    for bad in ([int(item),None] if type(item) is bool else [True,float(item),str(item),item+1]):
                        mutant=copy.deepcopy(self.value);(mutant if section is None else mutant[section])[key]=bad
                        with self.assertRaises(ValueError):validate(mutant,self.source,self.product)
            mutant=copy.deepcopy(self.value);(mutant if section is None else mutant[section])["caller_approved"]=True
            with self.assertRaises(ValueError):validate(mutant,self.source,self.product)
    def test_real_source_and_opaque_API_mutations_refuse(self):
        for old,new in (("connection: RootPathControlConnection","connection: OwnedFd"),("accepted: AcceptedStreamCustody","accepted: UnixStream"),("deadline: Instant","deadline: Duration"),("retired.store(true","retired.store(false"),("/proc/thread-self/ns/","/proc/self/ns/"),("ProcfsPeerAttestor::default()","ProcfsPeerAttestor::new(custom)")):
            mutant=self.source.replace(old,new);self.assertNotEqual(mutant,self.source)
            with self.assertRaises(ValueError):validate(self.value,mutant,self.product)
        with self.assertRaises(ValueError):validate(self.value,self.source+"\npub fn escape()->ControlOwnerPolicy { panic!() }\n",self.product)
    def test_golden_exact_thirteen_fields_and_no_production_approval(self):
        raw=(ROOT/self.value["format"]["golden"]).read_bytes()
        self.assertTrue(raw.isascii());self.assertTrue(raw.endswith(b"\n"));self.assertLessEqual(len(raw),8192)
        pairs=[line.decode().split("=") for line in raw.splitlines()]
        self.assertTrue(all(len(item)==2 for item in pairs));self.assertEqual(len(pairs),13)
        fields=dict(pairs);self.assertEqual(set(fields),set(self.value["format"]["fields"]))
        self.assertEqual(fields["schema"],"trillionnium.approved-mechanisms.v1")
        for role in ("control","agent"):
            self.assertEqual(fields[role+".elf_sha256"],"0"*64)
            self.assertIn(role+".principal_id",fields)
        self.assertNotEqual(fields["control.principal_id"],fields["agent.principal_id"])
        self.assertIn('include_bytes!("../../../contracts/fixtures/approved-mechanisms.v1.conf")',self.source)
    def test_all_existing_current_alive_deadline_paths_retain_configuration(self):
        request=(ROOT/"crates/hepta-peer-attestation/src/control_owner/control_request.rs").read_text()
        owner=(ROOT/"crates/hepta-peer-attestation/src/control_owner.rs").read_text()
        retained=(ROOT/"crates/hepta-peer-attestation/src/control_owner/retained_request.rs").read_text()
        alive=request[request.index("pub fn ensure_alive"):request.index("pub fn verify_current")]
        self.assertLess(alive.index("creator(self.state.owner_pid)?"),alive.index("self.state.revoked.load"))
        self.assertEqual(alive.count("policy.current()?"),2)
        self.assertIn("policy.is_agent_for_control(control)",request)
        self.assertIn("Arc::ptr_eq(&self.state, &other.state)",self.source)
        self.assertIn("custody.retain_approved(policy)?",retained)
        self.assertIn("self.deadline.min(policy.deadline()?)",owner)
        self.assertIn("snapshot().executable_sha256 != entry.pin",self.source)
        self.assertIn("attest(peer, &entry.runtime())",self.source)
        for name in ("ensure_alive","ensure_pair_alive","verify_current","verify_pair_current","deadline"):
            self.assertIn("pub fn "+name,request)
        self.assertIn("connection.principal != self.principal",self.product)
        self.assertNotIn("pub principal",self.product)
        bridge=(ROOT/"crates/hepta-peer-attestation/src/control_owner/root_path/approved.rs").read_text()
        for owner_name,channel in (("RootPathAttestedHandoffSender","HandoffSender"),("RootPathAttestedHandoffReceiver","HandoffReceiver")):
            tail=bridge[bridge.index("impl "+owner_name):]
            tail=tail[tail.index("pub(crate) fn from_approved"):]
            self.assertLess(tail.index("owner.retain_approved(&approved)?"),tail.index(channel+"::from_control"))
    def test_actual_required_kernel_targets_prelaunch_configuration_and_workflow(self):
        for package,name in (("crates/hepta-peer-attestation","approved_policy_kernel"),("apps/hepta-browserd","approved_policy_product_kernel")):
            cargo=tomllib.loads((ROOT/package/"Cargo.toml").read_text())
            actual=next(t for t in cargo["test"] if t["name"]==name)
            self.assertEqual(actual,{"name":name,"path":"tests/"+name+".rs","harness":False})
        kernel=(ROOT/self.value["evidence"]["source_kernel"]).read_text()
        product=(ROOT/self.value["evidence"]["product_kernel"]).read_text()
        self.assertIn("groups, 17",kernel);self.assertIn("libc::unshare(libc::CLONE_NEWNS)",kernel)
        self.assertIn("libc::setns",kernel);self.assertIn("65534",kernel)
        self.assertIn("/usr/bin/systemd-run",product);self.assertIn("/usr/bin/sha256sum",product)
        self.assertNotIn("PeerRuntimePolicy::exact",product);self.assertNotIn("read_snapshot(std::process::id())",product)
        self.assertIn("report.state()",product);self.assertIn("actual descriptor retirement",product)
        self.assertIn("completion.ensure_current_peer().is_err()",product)
        self.assertIn("earlier-original-policy-deadline",product)
        self.assertNotIn("#[ignore]",kernel+product)
        workflow=(ROOT/self.value["evidence"]["workflow"]).read_text()
        for command in ("cargo test --locked -p hepta-peer-attestation --test approved_policy_kernel","cargo test --locked -p hepta-browserd --test approved_policy_product_kernel","test_approved_mechanism_policy.py","live_head","live_base","HEAD^1","HEAD^2"):
            self.assertIn(command,workflow)
        self.assertIn("persist-credentials: false",workflow)
        self.assertIn("result.skipped",workflow)
        self.assertNotIn("continue-on-error",workflow)
    def test_module_inventory_and_default_disabled_limits(self):
        modules=json.loads((ROOT/"manifests/modules.v1.json").read_text())["modules"]
        for mod in modules:
            if mod["id"] in ("hepta-peer-attestation","hepta-browserd"):
                self.assertIn(CONTRACT,mod["contracts"]);self.assertIn("docs/architecture/APPROVED_MECHANISM_POLICY.md",mod["architecture"])
                self.assertIn("tests/test_approved_mechanism_policy.py",mod["tests"])
        self.assertEqual(tomllib.loads((ROOT/"crates/hepta-peer-attestation/Cargo.toml").read_text())["features"]["default"],[])
        self.assertIn("Err(ServiceError::ProductHandlerUnavailable)",(ROOT/"apps/hepta-agent-portd/src/main.rs").read_text())
        self.assertNotIn("ApprovedPolicyDocument",(ROOT/"apps/hepta-browserd/src/main.rs").read_text())
        doc=(ROOT/"docs/architecture/APPROVED_MECHANISM_POLICY.md").read_text()
        for word in ("synthetic", "not Servo", "BEFORE", "minimum", "EACCES", "namespace", "TaskFlow", "original"):
            self.assertIn(word,doc)

if __name__=="__main__":unittest.main()
