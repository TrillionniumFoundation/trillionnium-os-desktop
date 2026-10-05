"""Closed source/API correspondence; actual Linux tests are separate Rust targets."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import re
import tomllib
import unittest
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/retained-control-terminal.v1.json"
EXPECTED = {'schema': 'trillionnium.desktop.retained-control-terminal.v1',
 'status': 'SOURCE_CANDIDATE_JOURNAL_ASSOCIATION_ONLY',
 'platform': 'Linux',
 'implementation': {'transport': 'crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs',
                    'peer': 'crates/hepta-peer-attestation/src/control_owner/retained_request.rs',
                    'product': 'apps/hepta-browserd/src/product_dispatch/product_control_wait.rs'},
 'wire': {'bytes': 192,
          'magic': 'HPTAFDS1',
          'version': 1,
          'kinds': ['Cancel', 'TerminalReport'],
          'states': ['Completed', 'Interrupted', 'Indeterminate'],
          'rights': 0,
          'binding': ['original_control_channel',
                      'original_SO_PEERCRED_and_actual_SCM_CREDENTIALS',
                      'original_nonce',
                      'original_submission_sequence',
                      'original_socket_cookie',
                      'original_path_device_inode',
                      'original_boot',
                      'original_time_namespace',
                      'original_started_and_native_deadline'],
          'report': ['canonical_request_sha256', 'terminal_record_sha256', 'remote_terminal_lifecycle'],
          'application_response_or_success_boolean': False,
          'transport_report_is_local_durable_proof': False},
 'ownership': {'transactions': 1,
               'report_publication_attempts': 1,
               'cancel_publication_attempts': 1,
               'original_sender_retired_before_native_send': True,
               'report_authority_retired_before_native_send': True,
               'reporting_identity': 'same original live default /proc approved control incarnation '
                                     'retained independently of revoked execution custody',
               'fork': 'creator PID before mutation or copied mutex/channel; foreign Drop closes only '
                       'owned FD copies and forgets child channel heap references',
               'drop_joins_thread': False,
               'automatic_replay': False,
               'automatic_reconnect': False},
 'deadline': {'maximum_seconds': 20,
              'monitor_poll_ms': 5,
              'accepted': 'unchanged received absolute Instant; queue/attestation/dispatch/response '
                          'consume original ceiling',
              'report': 'minimum of original accepted and original local control ceiling; no fresh '
                        'Duration allocation',
              'renewal': False,
              'preemptive_procfs_timeout': False},
 'journal_association': {'issuer': 'only current ProductRequestCoordinator private invocation and own '
                                   'managed ReceiptLifecycleObserver',
                         'source': 'private OperationTrace exact request ID and digest plus original '
                                   'terminal record digest; reread complete own journal chain after '
                                   'Agent response attempt',
                         'accepted_proof_parameters': [],
                         'public_ServiceEvidence_is_proof': False,
                         'foreign_DurableReceiptFact_is_proof': False,
                         'report_is_Agent_response_delivery': False,
                         'report_is_effect_success': False,
                         'sealed_terminal_rewritten_on_lost_report_or_peer_exit': False,
                         'preflight_refusal': 'no admission facts: no terminal report, even if '
                                              'unrelated terminal history exists',
                         'ambiguous_effect': 'keep Indeterminate or interrupted-after-dispatch recovery '
                                             'latch; report never clears it'},
 'evidence': {'transport_kernel': 'crates/hepta-agent-transport/tests/retained_control_kernel.rs',
              'three_process_kernel': 'apps/hepta-browserd/tests/product_terminal_wait_kernel.rs',
              'contract_only': 'tests/test_retained_control_terminal.py',
              'native_completion': 'controlled source callback only; no Servo execution',
              'policy': 'test controller selects known fixture executable; no installed approved policy '
                        'provisioning'},
 'non_claims': {'installed_daemon_owner': False,
                'product_ready': False,
                'default_activation_changed': False,
                'cross_uid_live_attestation_qualified': False,
                'root_owned_control_path_custody': False,
                'semantic_principal': False,
                'native_final_effect_gate': False,
                'all_asynchronous_syscall_windows_closed': False,
                'independent_hardware_qualification': False}}
API_KEYS = {'AttestedHandoffReceiver::receive_retained_custodied',
 'AttestedHandoffSender::send_retained',
 'AttestedPendingHandoff::ensure_current',
 'AttestedPendingHandoff::poll_retirement',
 'AttestedPendingHandoff::request_cancel',
 'AttestedPendingHandoff::wait_retirement',
 'AttestedRetainedReceiver::ensure_current',
 'AttestedRetainedReceiver::poll_cancel',
 'AttestedRetainedReceiver::send_remote_report',
 'ControlRetainedAcceptedStream::consume_before',
 'ControlRetainedAcceptedStream::deadline',
 'HandoffReceiver::receive_retained',
 'HandoffSender::send_retained',
 'PeerReportedRetirement::record_sha256',
 'PeerReportedRetirement::request_sha256',
 'PeerReportedRetirement::state',
 'PendingHandoffReceiver::deadline',
 'PendingHandoffReceiver::ensure_current',
 'PendingHandoffReceiver::poll_cancel',
 'PendingHandoffReceiver::send_report',
 'PendingHandoffSender::deadline',
 'PendingHandoffSender::ensure_current',
 'PendingHandoffSender::poll_report',
 'PendingHandoffSender::request_cancel',
 'PendingHandoffSender::wait_report',
 'ProductControlMonitor::run',
 'ProductRequestCoordinator::from_retained_connection',
 'ProductRequestCoordinator::serve_retained_connection',
 'RemoteRetirementReport::new',
 'RemoteRetirementReport::record_sha256',
 'RemoteRetirementReport::request_sha256',
 'RemoteRetirementReport::state',
 'RetainedProductConnection::cancellation',
 'RetainedProductConnection::deadline',
 'RetainedProductConnection::from_control_retained_received',
 'RetainedReceivedAcceptedStream::into_parts'}

def exact(value, expected):
    if type(value) is not type(expected):
        raise ValueError("strict typed contract")
    if isinstance(expected, dict):
        if set(value) != set(expected):
            raise ValueError("closed contract fields")
        for key in expected:
            exact(value[key], expected[key])
    elif isinstance(expected, list):
        if len(value) != len(expected):
            raise ValueError("exact contract list")
        for current, wanted in zip(value, expected):
            exact(current, wanted)
    elif value != expected:
        raise ValueError("exact contract value")

def source_signatures(text):
    result = {}
    for match in re.finditer(r"impl (\w+)\s*\{", text):
        start = match.end()
        end, depth = start, 1
        while depth:
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
            end += 1
        block = text[start:end-1]
        for function in re.finditer(r"pub (?:const )?fn (\w+)", block):
            opening = block.index("{", function.end())
            key = match[1] + "::" + function[1]
            if key in result:
                raise ValueError("duplicate public source signature")
            result[key] = " ".join(block[function.start():opening].split())
    if len(re.findall(r"\bpub (?:const )?fn \w+", text)) != len(result):
        raise ValueError("unregistered free or unparsed public API")
    return result

def check_contract(value, signatures):
    if type(value) is not dict or set(value) != set(EXPECTED) | {"public_api"}:
        raise ValueError("closed top level")
    exact({key: value[key] for key in EXPECTED}, EXPECTED)
    api = value["public_api"]
    if type(api) is not dict or set(api) != API_KEYS:
        raise ValueError("exact additive API keys")
    if any(type(signature) is not str for signature in api.values()) or api != signatures:
        raise ValueError("exact actual source signatures")

class RetainedTerminalContractTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(CONTRACT.read_text())
        self.signatures = {}
        for path in EXPECTED["implementation"].values():
            self.signatures.update(source_signatures((ROOT/path).read_text()))

    def test_closed_positive_all_actual_public_signatures(self):
        check_contract(self.value, self.signatures)
        self.assertEqual(len(self.signatures), 36)

    def test_closed_new_removed_or_retyped_authority_rejected(self):
        mutations = []
        for key in EXPECTED["non_claims"]:
            for bad in (True, 0, "false", None):
                value = copy.deepcopy(self.value)
                value["non_claims"][key] = bad
                mutations.append(value)
        for parent, key, bad in (("deadline", "maximum_seconds", 20.0), ("wire", "rights", False),
                                 ("ownership", "transactions", True),
                                 ("journal_association", "public_ServiceEvidence_is_proof", True)):
            value = copy.deepcopy(self.value)
            value[parent][key] = bad
            mutations.append(value)
        value = copy.deepcopy(self.value)
        value["journal_association"]["caller_terminal_boolean"] = False
        mutations.append(value)
        value = copy.deepcopy(self.value)
        del value["non_claims"]["product_ready"]
        mutations.append(value)
        for value in mutations:
            with self.assertRaises(ValueError):
                check_contract(value, self.signatures)

    def test_new_removed_or_changed_source_api_rejected(self):
        for change in ("new", "removed", "changed"):
            value = copy.deepcopy(self.value)
            if change == "new":
                value["public_api"]["ProductRequestCoordinator::accept_caller_terminal"] = "pub fn (bool)"
            elif change == "removed":
                value["public_api"].pop("ProductRequestCoordinator::serve_retained_connection")
            else:
                value["public_api"]["ProductRequestCoordinator::serve_retained_connection"] += " bool"
            with self.assertRaises(ValueError):
                check_contract(value, self.signatures)

    def test_private_seal_owns_exact_current_journal_source(self):
        source = (ROOT/EXPECTED["implementation"]["product"]).read_text()
        self.assertIn("struct SealedTerminal {", source)
        self.assertNotIn("pub struct SealedTerminal", source)
        self.assertIn(".receipt_fact(&request.id, request.digest)", source)
        self.assertIn("fact.record_sha256()", re.sub(r"\s+", "", source))
        self.assertIn("self.last_retirement = None", source)
        self.assertIn("self.last_retirement.take()", source)
        self.assertIn("sync_channel(1)", source)
        self.assertIn("std::mem::forget(self.receiver.take())", source)
        self.assertIn("std::mem::forget(self.terminal.take())", source)
        self.assertNotIn("join(", source)
        transport = (ROOT/EXPECTED["implementation"]["transport"]).read_text()
        self.assertIn("const SIDEBAND_BYTES: usize = 192;", transport)
        self.assertIn('const SIDEBAND_MAGIC: &[u8; 8] = b"HPTAFDS1";', transport)
        state = re.search(r"pub enum RemoteTerminalState\s*\{([^}]+)\}", transport).group(1)
        self.assertEqual([item.strip() for item in state.split(",") if item.strip()],
                         ["Completed", "Interrupted", "Indeterminate"])
        peer = (ROOT/EXPECTED["implementation"]["peer"]).read_text()
        self.assertIn("ControlRequestCustody::from_control_peer", peer)
        self.assertNotIn("ProcfsPeerAttestor::new", peer)
        self.assertIn("self.deadline.min(deadline)", peer)
        product = (ROOT/"apps/hepta-browserd/src/product_dispatch.rs").read_text()
        self.assertIn("trace.terminal_record", product)
        self.assertIn("trace.requested", product)

    def test_actual_targets_registered_and_ci_runs_all_targets(self):
        for directory, name in (("crates/hepta-agent-transport", "retained_control_kernel"),
                                ("apps/hepta-browserd", "product_terminal_wait_kernel")):
            cargo = tomllib.loads((ROOT/directory/"Cargo.toml").read_text())
            target = next(item for item in cargo["test"] if item["name"] == name)
            self.assertIs(target["harness"], False)
            source = (ROOT/directory/target["path"]).read_text()
            self.assertIn("fn main()", source)
            self.assertIn("libc::fork()", source)
        workflow = (ROOT/".github/workflows/s08-product-servo-runtime.yml").read_text()
        self.assertEqual(workflow.count("cargo test --locked -p hepta-browserd --all-targets"), 2)
        self.assertEqual(workflow.count("-p test_retained_control_terminal.py -v"), 2)

    def test_product_binaries_and_activation_remain_closed(self):
        daemon = (ROOT/"apps/hepta-agent-portd/src/main.rs").read_text()
        browser = (ROOT/"apps/hepta-browserd/src/main.rs").read_text()
        self.assertIn("ProductHandlerUnavailable", daemon)
        for source in (daemon, browser):
            self.assertNotIn("serve_retained_connection", source)
            self.assertNotIn("send_retained", source)
            self.assertNotIn("UnixListener", source)
        self.assertIn("disable hepta-browserd-agent.socket", (ROOT/"packaging/debian/systemd-preset/90-trillionnium-desktop.preset").read_text())

if __name__ == "__main__":
    unittest.main()
