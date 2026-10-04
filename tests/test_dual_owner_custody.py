"""Closed source/API correspondence only; real Linux custody is the Rust target."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/dual-owner-request-custody.v1.json"
API = {'AttestedHandoffReceiver::receive_custodied': '(&mut self) -> Result<ControlReceivedAcceptedStream, '
                                               'ControlOwnerError>',
 'ControlReceivedAcceptedStream::deadline': '(&self) -> Result<Instant, ControlOwnerError>',
 'ControlReceivedAcceptedStream::control_verifier': '(&self) -> Result<ControlRequestVerifier, '
                                                    'ControlOwnerError>',
 'ControlReceivedAcceptedStream::consume_before': '(self, impl FnOnce(UnixStream, Instant, '
                                                  'ControlRequestCustody) -> T) -> Result<T, '
                                                  'ControlOwnerError>',
 'ControlRequestCustody::verifier': '(&self) -> Result<ControlRequestVerifier, ControlOwnerError>',
 'ControlRequestCustody::revoke': '(&self) -> Result<(), ControlOwnerError>',
 'ControlRequestVerifier::ensure_alive': '(&self) -> Result<(), ControlOwnerError>',
 'ControlRequestVerifier::verify_current': '(&self) -> Result<(), ControlOwnerError>',
 'ControlRequestVerifier::deadline': '(&self) -> Result<Instant, ControlOwnerError>',
 'ControlRequestVerifier::ensure_pair_alive': '(&self, &PeerRequestVerifier) -> Result<(), '
                                              'ControlOwnerError>',
 'ControlRequestVerifier::verify_pair_current': '(&self, &PeerRequestVerifier) -> Result<(), '
                                                'ControlOwnerError>',
 'AcceptedProductConnection::from_control_received': '(ControlReceivedAcceptedStream, &PeerRuntimePolicy, '
                                                     '&str) -> Result<AcceptedProductConnection, '
                                                     'ProductDispatchError>',
 'BrowserActor::preflight_attested_controlled': '(&mut self, &DispatchContext, &BrowserRequest, '
                                                '&ProcfsPeerAttestor, &AttestedPeer, '
                                                '&ControlRequestVerifier) -> '
                                                'Result<Option<BrowserWireError>, AgentPortError>',
 'BrowserActor::handle_attested_controlled': '(&mut self, &DispatchContext, &BrowserRequest, '
                                             '&ProcfsPeerAttestor, &AttestedPeer, &ControlRequestVerifier) '
                                             '-> Result<HandlerOutcome, AgentPortError>',
 'ServoBrowserActor::preflight_attested_controlled': '(&mut self, &DispatchContext, &BrowserRequest, '
                                                     '&ProcfsPeerAttestor, &AttestedPeer, '
                                                     '&ControlRequestVerifier) -> '
                                                     'Result<Option<BrowserWireError>, AgentPortError>',
 'ServoBrowserActor::handle_attested_controlled': '(&mut self, &DispatchContext, &BrowserRequest, '
                                                  '&ProcfsPeerAttestor, &AttestedPeer, '
                                                  '&ControlRequestVerifier) -> Result<HandlerOutcome, '
                                                  'AgentPortError>',
 'BrowserActor::retire_prepared_request': '(&mut self, &str) -> Result<(), AgentPortError>',
 'ServoBrowserActor::retire_prepared_request': '(&mut self, &str) -> Result<(), AgentPortError>'}
POLICY = {'control_constructor': 'only existing ControlPeerOwner with fixed default /proc live executable source and '
                        'explicit approved ControlOwnerPolicy',
 'original_agent_constructor': 'from_control_received uses fixed default ProcfsPeerAttestor; explicit '
                               'PeerRuntimePolicy and canonical approved executable pin',
 'approved_agent_pin': '64 lowercase hexadecimal SHA256 compared to actual original Agent executable bytes; '
                       'observation never auto-approves production policy',
 'principal_issued': False,
 'policy_provisioned': False,
 'injected_control_attestor': False,
 'static_control_source': False}
IMPLEMENTATION = {'control': 'crates/hepta-peer-attestation/src/control_owner/control_request.rs',
 'product': 'apps/hepta-browserd/src/product_dispatch.rs',
 'actor': 'crates/hepta-browser-actor-simulation/src/lib.rs',
 'facade': 'crates/hepta-browser-actor/src/servo_runtime.rs'}
FIELDS = {'implementation': {'facade', 'actor', 'product', 'control'},
 'policy': {'approved_agent_pin',
            'control_constructor',
            'injected_control_attestor',
            'original_agent_constructor',
            'policy_provisioned',
            'principal_issued',
            'static_control_source'},
 'ownership': {'control_custodian',
               'custody_cloneable',
               'fork',
               'observed_identity_failure_latched',
               'opaque_received_cloneable',
               'original_agent',
               'prepared_request_retirement',
               'raw_stream_extraction',
               'retirement',
               'transactions_per_receiver',
               'verifier_cloneable'},
 'deadline': {'accepted',
              'control_wait',
              'maximum_seconds',
              'preemptive_procfs_timeout',
              'queue_capacity_maximum',
              'renewal_api'},
 'control_channel': {'custodian_must_remain_same_live_incarnation',
                     'one_shot_local_close_is_peer_exit',
                     'remote_cancel_or_terminal_ack_protocol',
                     'terminal_wait_protocol'},
 'public_api': {'AcceptedProductConnection::from_control_received',
                'AttestedHandoffReceiver::receive_custodied',
                'BrowserActor::handle_attested_controlled',
                'BrowserActor::preflight_attested_controlled',
                'BrowserActor::retire_prepared_request',
                'ControlReceivedAcceptedStream::consume_before',
                'ControlReceivedAcceptedStream::control_verifier',
                'ControlReceivedAcceptedStream::deadline',
                'ControlRequestCustody::revoke',
                'ControlRequestCustody::verifier',
                'ControlRequestVerifier::deadline',
                'ControlRequestVerifier::ensure_alive',
                'ControlRequestVerifier::ensure_pair_alive',
                'ControlRequestVerifier::verify_current',
                'ControlRequestVerifier::verify_pair_current',
                'ServoBrowserActor::handle_attested_controlled',
                'ServoBrowserActor::preflight_attested_controlled',
                'ServoBrowserActor::retire_prepared_request'},
 'evidence': {'source_callback', 'actual_kernel', 'contract_tests'},
 'non_claims': {'all_asynchronous_syscall_windows_closed',
                'approved_policy_provisioned',
                'cross_uid_live_attestation_qualified',
                'default_activation_changed',
                'installed_daemon_owner',
                'native_final_effect_gate',
                'product_ready',
                'remote_terminal_protocol',
                'root_owned_control_path_custody',
                'semantic_principal'}}
TOP = {'implementation', 'platform', 'non_claims', 'request_chain', 'public_api', 'evidence', 'schema', 'policy', 'deadline', 'ownership', 'control_channel', 'status'}
NON_CLAIMS = {'remote_terminal_protocol', 'root_owned_control_path_custody', 'default_activation_changed', 'all_asynchronous_syscall_windows_closed', 'cross_uid_live_attestation_qualified', 'native_final_effect_gate', 'installed_daemon_owner', 'product_ready', 'approved_policy_provisioned', 'semantic_principal'}


def check_contract(v: dict) -> None:
    if type(v) is not dict or set(v) != TOP:
        raise ValueError("closed dual-owner fields")
    if (v["schema"], v["status"], v["platform"]) != (
        "trillionnium.desktop.dual-owner-request-custody.v1",
        "SOURCE_CANDIDATE_TWO_LIVE_INCARNATIONS_ONLY", "Linux"):
        raise ValueError("dual-owner scope")
    for key, fields in FIELDS.items():
        if type(v[key]) is not dict or set(v[key]) != fields:
            raise ValueError("closed dual-owner nested fields")
    if v["public_api"] != API or v["policy"] != POLICY or v["implementation"] != IMPLEMENTATION:
        raise ValueError("exact API and configured policy")
    for key in ("principal_issued", "policy_provisioned", "injected_control_attestor", "static_control_source"):
        if v["policy"][key] is not False:
            raise ValueError("typed false policy authority")
    if any(v["non_claims"][key] is not False for key in NON_CLAIMS):
        raise ValueError("source claim ceiling")
    for key in ("maximum_seconds", "queue_capacity_maximum"):
        if type(v["deadline"][key]) is not int or v["deadline"][key] != {"maximum_seconds":20,"queue_capacity_maximum":8}[key]:
            raise ValueError("fixed deadline/queue bound")
    false_fields = {"ownership": ["custody_cloneable", "opaque_received_cloneable", "raw_stream_extraction"],
                    "deadline": ["renewal_api", "preemptive_procfs_timeout"],
                    "control_channel": ["one_shot_local_close_is_peer_exit", "remote_cancel_or_terminal_ack_protocol", "terminal_wait_protocol"]}
    true_fields = {"ownership": ["verifier_cloneable", "observed_identity_failure_latched"],
                   "control_channel": ["custodian_must_remain_same_live_incarnation"]}
    for wanted, groups in [(False, false_fields), (True, true_fields)]:
        for group, keys in groups.items():
            if any(v[group][key] is not wanted for key in keys):
                raise ValueError("ownership/terminal authority")
    if type(v["ownership"]["transactions_per_receiver"]) is not int or v["ownership"]["transactions_per_receiver"] != 1:
        raise ValueError("one-shot owner")
    if v["ownership"]["retirement"] != ["owner_drop", "explicit_revoke", "connection_cancel", "observed_agent_death_or_exec", "observed_control_death_or_exec", "original_deadline_expiry"]:
        raise ValueError("irreversible retirement")
    if v["ownership"]["prepared_request_retirement"] != "creator PID before cleanup; every controlled preflight refusal/error and handler return cancels and removes that request token/marker, including successful preflight followed by revoked custody or expiry; no dispatch or replay grant":
        raise ValueError("prepared revocation-only retirement")
    if v["request_chain"] != ["receive_custodied", "from_control_received", "queue_submit_and_dequeue", "semantic_preflight_before_durable_facts", "handle_attested_controlled", "RequestControl_pair", "ServoRuntimeCompletion_ensure_current_peer"]:
        raise ValueError("ordered concrete request chain")


class DualOwnerContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text())
        self.control = (ROOT / self.contract["implementation"]["control"]).read_text()
        self.product = (ROOT / self.contract["implementation"]["product"]).read_text()
        self.actor = (ROOT / self.contract["implementation"]["actor"]).read_text()
        self.facade = (ROOT / self.contract["implementation"]["facade"]).read_text()

    def test_closed_positive_inventory_and_production_ceiling(self):
        check_contract(self.contract)
        self.assertEqual(len(API), 18)
        for group in ("implementation",):
            for path in self.contract[group].values():
                self.assertTrue((ROOT/path).is_file())
        self.assertIn("Duration::from_secs(20)", self.product)
        self.assertIn("MAX_PRODUCT_PENDING_CONNECTIONS: usize = 8", self.product)

    def test_extra_missing_nested_api_flags_and_numeric_coercions_refused(self):
        for group in [None, *FIELDS]:
            for mutation in ("extra", "missing"):
                v=copy.deepcopy(self.contract); node=v if group is None else v[group]
                if mutation == "extra": node["new_authority"] = False
                else: node.pop(next(iter(node)))
                with self.subTest(group=group,mutation=mutation), self.assertRaises(ValueError):check_contract(v)
        for key in NON_CLAIMS:
            for bad in (True,0,"false"):
                v=copy.deepcopy(self.contract);v["non_claims"][key]=bad
                with self.subTest(key=key,bad=bad), self.assertRaises(ValueError):check_contract(v)
        for key in ("maximum_seconds","queue_capacity_maximum"):
            for bad in (True,21,20.0,"20"):
                v=copy.deepcopy(self.contract);v["deadline"][key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):check_contract(v)
        for key,bad in [("policy_provisioned",True),("policy_provisioned",0),("injected_control_attestor",True),("injected_control_attestor",0),("approved_agent_pin","actual peer hash auto-approved")]:
            v=copy.deepcopy(self.contract);v["policy"][key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):check_contract(v)

    def test_terminal_and_ownership_claim_mutations_refused(self):
        for group,key in [("control_channel", "one_shot_local_close_is_peer_exit"),("control_channel","remote_cancel_or_terminal_ack_protocol"),("control_channel","terminal_wait_protocol"),("ownership","raw_stream_extraction"),("ownership","custody_cloneable"),("deadline","renewal_api")]:
            v=copy.deepcopy(self.contract);v[group][key]=True
            with self.subTest(group=group,key=key),self.assertRaises(ValueError):check_contract(v)
        v=copy.deepcopy(self.contract);v["request_chain"].reverse()
        with self.assertRaises(ValueError):check_contract(v)
        v=copy.deepcopy(self.contract);v["ownership"]["retirement"].remove("observed_agent_death_or_exec")
        with self.assertRaises(ValueError):check_contract(v)

    def test_exact_additive_control_signatures_and_no_public_constructor(self):
        normalized = re.sub(r"\s+", " ", self.control)
        expected = [
            "pub fn receive_custodied( &mut self, ) -> Result<ControlReceivedAcceptedStream, ControlOwnerError>",
            "pub fn consume_before<T>( mut self, consumer: impl FnOnce(UnixStream, Instant, ControlRequestCustody) -> T, ) -> Result<T, ControlOwnerError>",
            "pub fn control_verifier(&self) -> Result<ControlRequestVerifier, ControlOwnerError>",
            "pub fn verifier(&self) -> Result<ControlRequestVerifier, ControlOwnerError>",
            "pub fn revoke(&self) -> Result<(), ControlOwnerError>",
            "pub fn ensure_alive(&self) -> Result<(), ControlOwnerError>",
            "pub fn verify_current(&self) -> Result<(), ControlOwnerError>",
            "pub fn deadline(&self) -> Result<Instant, ControlOwnerError>",
            "pub fn ensure_pair_alive( &self, original: &PeerRequestVerifier, ) -> Result<(), ControlOwnerError>",
            "pub fn verify_pair_current( &self, original: &PeerRequestVerifier, ) -> Result<(), ControlOwnerError>",
        ]
        for signature in expected:self.assertIn(signature, normalized)
        self.assertEqual(sorted(re.findall(r"pub fn (\w+)(?:<[^>]+>)?\s*\(", self.control)),sorted(["receive_custodied","consume_before","control_verifier","verifier","revoke","ensure_alive","verify_current","deadline","deadline","ensure_pair_alive","verify_pair_current"]))
        for bad in ("pub fn new", "pub fn from_control_peer", "pub state:", "pub received:", "pub fn renew"):
            self.assertNotIn(bad,self.control)
        self.assertIn("pidfd\n                .try_clone()",self.control)
        self.assertIn('peer.attestor.proc_root != Path::new("/proc")',self.control)
        self.assertIn("ExecutableSource::Live",self.control)
        self.assertIn("attestor: ProcfsPeerAttestor::default()",self.control)
        self.assertNotIn("pidfd_open",self.control)
        self.assertNotIn("shutdown",self.control.split("impl Drop for ControlRequestCustody",1)[1].split("impl ControlRequestVerifier",1)[0].split("// Arc",1)[0])

    def test_default_agent_pin_and_opaque_original_deadline_admission(self):
        normalized=re.sub(r"\s+"," ",self.product)
        self.assertIn("pub fn from_control_received( received: ControlReceivedAcceptedStream, policy: &PeerRuntimePolicy, approved_executable_sha256: &str, ) -> Result<Self, ProductDispatchError>",normalized)
        admission=self.product.split("pub fn from_control_received",1)[1].split("fn control_verifier",1)[0]
        self.assertIn("Self::attest_before(stream, ProcfsPeerAttestor::default(), policy, deadline)",admission)
        self.assertIn("connection.attested.snapshot().executable_sha256 != approved_executable_sha256",admission)
        self.assertLess(admission.index("approved_executable_sha256.len() != 64"),admission.index("Self::attest_before"))
        self.assertNotIn("Instant::now",admission)
        self.assertNotIn("Self::attest(",admission)
        self.assertNotIn("Duration::from",admission)
        self.assertIn("deadline != verifier.deadline()?",self.control)
        receive=self.control.split("pub fn receive_custodied",1)[1]
        self.assertLess(receive.index("ControlReceivedAcceptedStream::new(received, &owner.attested)"),receive.index("self.retire()?"))

    def test_both_verifiers_reach_concrete_completion_and_retirement(self):
        for source in (self.actor,self.facade):
            for name,result in [("preflight_attested_controlled","Result<Option<BrowserWireError>, AgentPortError>"),("handle_attested_controlled","Result<HandlerOutcome, AgentPortError>")]:
                signatures=re.findall(r"pub fn "+name+r"\s*\([^)]*\)\s*->[^\{]+", source)
                self.assertEqual(len(signatures),1)
                s=re.sub(r"\s+"," ",signatures[0]).replace("hepta_peer_attestation::","")
                self.assertIn("custodian: &ControlRequestVerifier",s);self.assertIn(result,s)
                expected = f"pub fn {name}( &mut self, context: &DispatchContext, request: &BrowserRequest, attestor: &ProcfsPeerAttestor, attested: &AttestedPeer, custodian: &ControlRequestVerifier, ) -> {result}"
                self.assertEqual(s.strip(), expected)
        for token in ("custodian: Option<ControlRequestVerifier>","custodian .ensure_pair_alive(&self.agent)","custodian .verify_pair_current(&self.agent)","self.runtime_authority()"):
            self.assertIn(token,re.sub(r"\s+", " ", self.actor))
        for token in ("custodian.revoke()","connection.ensure_control_current()?","bootstrap.ensure_control_current()?","self.actor.handle_attested_controlled"):
            self.assertIn(token,self.product)
        completion=self.facade.split("pub fn ensure_current_peer",1)[1].split("pub fn",1)[0]
        self.assertIn("self.inner.ensure_current_peer()",re.sub(r"\s+", " ", completion))
        self.assertIn("self.original_peer_result(original.verify_current())?",self.control)
        self.assertIn("self.state.revoked.store(true, Ordering::SeqCst)",self.control)

    def test_refused_preparation_has_explicit_revocation_only_api(self):
        for source in (self.actor, self.facade):
            normalized = re.sub(r"\s+", " ", source)
            self.assertIn("pub fn retire_prepared_request(&mut self, request_id: &str) -> Result<(), AgentPortError>", normalized)
        body = self.actor.split("pub fn retire_prepared_request", 1)[1].split("pub fn", 1)[0]
        self.assertLess(body.index("self.ensure_prepared_request_owner()?"), body.index("self.cancellation_tokens.remove"))
        self.assertIn("token.cancel()", body)
        self.assertIn("self.cancelled_requests.remove(request_id)", body)
        for source, start in [(self.actor, "pub fn preflight_attested_controlled"), (self.actor, "pub fn handle_attested_controlled")]:
            body = source.split(start, 1)[1].split("pub fn", 1)[0]
            self.assertIn("self.ensure_prepared_request_owner()?", body)
            self.assertIn("self.retire_prepared_request(&request.request_id)?", body)
        handler = self.product.split("impl BrowserRequestHandler for AttestedProductHandler", 1)[1].split("struct DurableProductLifecycle", 1)[0]
        self.assertEqual(handler.count("self.actor.retire_prepared_request(&request.request_id)?"), 2)
        self.assertEqual(handler.count("product_owner(self.owner_pid)?"), 2)
        for public in ("BrowserActor::retire_prepared_request", "ServoBrowserActor::retire_prepared_request"):
            v = copy.deepcopy(self.contract); v["public_api"].pop(public)
            with self.assertRaises(ValueError): check_contract(v)
        v = copy.deepcopy(self.contract); v["ownership"]["prepared_request_retirement"] = "caller may renew cancelled request"
        with self.assertRaises(ValueError): check_contract(v)

    def test_kernel_target_runs_without_feature_or_skip_in_both_ci_lanes(self):
        manifest=tomllib.loads((ROOT/"apps/hepta-browserd/Cargo.toml").read_text())
        target=next(v for v in manifest["test"] if v["name"]=="product_control_custody_kernel")
        self.assertIs(target["harness"],False);self.assertNotIn("required-features",target)
        source=(ROOT/"apps/hepta-browserd"/target["path"]).read_text()
        for token in ("libc::SOCK_SEQPACKET","receive_custodied()","ProcfsPeerAttestor::default()","libc::fork()","descriptor_snapshot()","changed_image()","Duration::from_secs(20)","actual three-process dual-owner case groups","synthetic Agent facts"):
            self.assertIn(token,source)
        self.assertNotIn("#[ignore]",source);self.assertNotIn("SKIP",source)
        wf=(ROOT/".github/workflows/s04-transport-custody.yml").read_text()
        self.assertEqual(wf.count("cargo test --workspace --all-targets --all-features --locked"),2)
        self.assertEqual(wf.count("python3 -m unittest discover -s tests -p test_dual_owner_custody.py -v"),2)
        self.assertEqual(wf.count('"contracts/dual-owner-request-custody.v1.json"'),2)
        registry=json.loads((ROOT/"manifests/modules.v1.json").read_text())
        for module in registry["modules"]:
            if module["id"] in ("hepta-peer-attestation","hepta-browserd","hepta-browser-actor","hepta-browser-actor-simulation"):
                self.assertIn("contracts/dual-owner-request-custody.v1.json",module["contracts"])
                self.assertIn("tests/test_dual_owner_custody.py",module["tests"])


if __name__ == "__main__":unittest.main()
