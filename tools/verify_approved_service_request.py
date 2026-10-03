"""P1 source correspondence only; no process or installed authorization."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import sys
try:
    from . import verify_approved_native_startup as source_gate
except ImportError:
    import verify_approved_native_startup as source_gate
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/approved-service-request-bridge.v2.json"
EXPECTED = json.loads('{"schema":"trillionnium.desktop.approved-service-original-request.v2","status":"SOURCE_CANDIDATE_RUNTIME_REQUALIFICATION_PENDING","requirements":["G1","G2"],"default_activation":false,"actual_parent":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","tree":"fcac28d8cd3f24ab34f48676648d062850830464","scope":"SOURCE_ONLY"},"public_api":{"HandoffReceiver::receive_retained_service_control":"pub fn receive_retained_service_control(self, wait_budget: Duration) -> Result<RetainedReceivedAcceptedStream, HandoffError>","HandoffSender::send_retained_service_control":"pub fn send_retained_service_control(self, custody: AcceptedStreamCustody) -> Result<PendingHandoffSender, HandoffError>","ApprovedServiceRequests::from_owner":"pub fn from_owner(owner: ApprovedServiceOwnerBinding) -> Result<Self, ApprovedPolicyError>","ApprovedServiceRequests::ensure_current":"pub fn ensure_current(&self) -> Result<(), ApprovedPolicyError>","ApprovedServiceRequests::session_verifier":"pub fn session_verifier(&self) -> Result<ApprovedServiceSessionVerifier, ApprovedPolicyError>","ApprovedServiceRequests::bind_control":"pub fn bind_control(&mut self, connection: RootPathControlConnection, expected_agent_path: &Path) -> Result<ApprovedServiceControlReceiver, ApprovedPolicyError>","ApprovedServiceSessionVerifier::ensure_current":"pub fn ensure_current(&self) -> Result<(), ApprovedPolicyError>","ApprovedServiceControlReceiver::receive_request":"pub fn receive_request(self) -> Result<ApprovedServiceReceivedRequest, ApprovedPolicyError>","ApprovedServiceReceivedRequest::original_deadline":"pub fn original_deadline(&self) -> Result<Instant, ApprovedPolicyError>","ApprovedServiceReceivedRequest::consume_with_request_binding":"pub fn consume_with_request_binding<T>(self, consumer: impl FnOnce(UnixStream, Instant, ControlRequestCustody, ApprovedServiceRetainedReporter, AttestedPeer, &str, ApprovedServiceRequestBinding) -> T) -> Result<T, ApprovedPolicyError>","ApprovedServiceRequestBinding::verify_for_service":"pub fn verify_for_service(&self, session: &ApprovedServiceSessionVerifier) -> Result<(PeerIdentity, PeerRuntimeSnapshot, String), ApprovedPolicyError>","ApprovedServiceRequestBinding::verifier_for_service":"pub fn verifier_for_service(&self, session: &ApprovedServiceSessionVerifier) -> Result<ApprovedServiceRequestVerifier, ApprovedPolicyError>","ApprovedServiceRequestVerifier::verify_for_service":"pub fn verify_for_service(&self, session: &ApprovedServiceSessionVerifier) -> Result<(), ApprovedPolicyError>","ApprovedServiceRequestVerifier::with_original_pair":"pub fn with_original_pair<T>(&self, session: &ApprovedServiceSessionVerifier, consumer: impl FnOnce(&ProcfsPeerAttestor, &AttestedPeer, &ControlRequestVerifier, Instant) -> T) -> Result<T, ApprovedPolicyError>","ApprovedServiceRetainedReporter::original_deadline":"pub fn original_deadline(&mut self) -> Result<Instant, ApprovedPolicyError>","ApprovedServiceRetainedReporter::poll_cancel":"pub fn poll_cancel(&mut self) -> Result<bool, ApprovedPolicyError>","ApprovedServiceRetainedReporter::send_remote_report":"pub fn send_remote_report(&mut self, report: RemoteRetirementReport) -> Result<(), ApprovedPolicyError>","RootPathControlConnection::consume_service_control_before":"pub fn consume_service_control_before<T>(self, consumer: impl FnOnce(OwnedFd, Instant, RootControlPathCustody) -> T) -> Result<T, RootControlPathError>"},"opaque_types":{"ApprovedServiceRequests":"original_owner:Option<ApprovedServiceOwnerBinding>,session:Arc<ServiceSessionState>,","ApprovedServiceSessionVerifier":"session:Arc<ServiceSessionState>,","ApprovedServiceControlReceiver":"session:Arc<ServiceSessionState>,receiver:Option<RootPathAttestedHandoffReceiver>,slot:Arc<ServiceRequestSlot>,original_control_deadline:Instant,","ApprovedServiceReceivedRequest":"session:Arc<ServiceSessionState>,stream:UnixStream,deadline:Instant,custody:ControlRequestCustody,reporter:ApprovedServiceRetainedReporter,attested:AttestedPeer,binding:ApprovedServiceRequestBinding,","ApprovedServiceRequestBinding":"state:Arc<ServiceRequestState>,original:PeerRequestCustody,slot:Arc<ServiceRequestSlot>,","ApprovedServiceRequestVerifier":"state:Arc<ServiceRequestState>,original:PeerRequestVerifier,","ApprovedServiceRetainedReporter":"session:Arc<ServiceSessionState>,retained:Option<AttestedRetainedReceiver>,deadline:Instant,slot:Arc<ServiceRequestSlot>,"},"private_helpers":{"RootPathAttestedHandoffReceiver::from_service_control":"pub(crate) fn from_service_control(connection: RootPathControlConnection, session: &ServiceSessionState, expected_agent_path: &Path) -> Result<Self, ControlOwnerError>","RootPathAttestedHandoffReceiver::receive_service_control":"pub(crate) fn receive_service_control(&mut self, session: &ServiceSessionState) -> Result<ControlRetainedAcceptedStream, ControlOwnerError>","AttestedHandoffReceiver::receive_service_control":"pub(in crate::control_owner) fn receive_service_control(&mut self, session: &ServiceSessionState) -> Result<ControlRetainedAcceptedStream, ControlOwnerError>","ServiceSessionState::ensure_current":"pub(crate) fn ensure_current(&self) -> Result<(), ApprovedPolicyError>","ServiceSessionState::control_policy":"pub(crate) fn control_policy(&self) -> Result<ControlOwnerPolicy, ApprovedPolicyError>","ServiceSessionState::verify_control":"pub(crate) fn verify_control(&self, attested: &AttestedPeer) -> Result<(), ApprovedPolicyError>"},"whole_production_source_sha256":{"crates/hepta-agent-transport/src/accepted_handoff/retained_control/service_control.rs":"7910294fbb13f09f8f9259b2b762cf4cac0a1e187150986a8aa827fa238e4baa","crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs":"cbe3ff799af0be7dcc5cfa884e9ac43c494c7ce365ae5aa190ff5a9ca85674b6","crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs":"2e4b7669bc2f645ad1ee0ed328ee6cda7f0bed7e2daaaa951ec9a56ef0471de8","crates/hepta-peer-attestation/src/control_owner/retained_request/service_request.rs":"97acc34300e354f81b348ff8ed82384ef5845c3e8f38bd9e3136e2cfbb77b3dd","crates/hepta-agent-transport/src/root_control_path/service_control.rs":"b5f0ab8b979faf96a2d5c1e3f3bb8a6d1a532ff09cc5a7827b0f6eda90634054"},"original_source_inverse":{"crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs":{"parent_bytes":16469,"parent_sha256":"c011fd826aacdc21a235b301b8a3fb4b8d16258cb652030bd9647a049040a4cb","offset":16418,"block":"\\nmod service_control;\\n","anchor":"\\n#[cfg(test)]\\nmod readiness_tests;\\n","complete_bytes":16491,"complete_sha256":"8b92ac76f1ceda055be0f4a56a8a41e2d704229b24f337f65c028c443957eb35","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs","mode":"100644","blob":"bd35c2f9d53955fe360d2e88b23f5ad8131c8c3b","scope":"SOURCE_ONLY_ACCEPTED_DB9"}},"crates/hepta-peer-attestation/src/approved_policy/service_policy.rs":{"parent_bytes":19753,"parent_sha256":"ace7e68730c50bf007863e39a83545892ecd392fb8f323d11e905da03b08168a","offset":15444,"block":"\\nmod request_bridge;\\npub(crate) use request_bridge::ServiceSessionState;\\npub use request_bridge::{\\n    ApprovedServiceControlReceiver, ApprovedServiceReceivedRequest, ApprovedServiceRequestBinding,\\n    ApprovedServiceRequestVerifier, ApprovedServiceRequests, ApprovedServiceRetainedReporter,\\n    ApprovedServiceSessionVerifier,\\n};\\n","anchor":"\\n#[cfg(test)]\\nmod tests {\\n","complete_bytes":20084,"complete_sha256":"4eaa341de7bc90935b993fe0fe5df6a04d282d637e8fce2da52498eb4e4fe033","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"crates/hepta-peer-attestation/src/approved_policy/service_policy.rs","mode":"100644","blob":"6199f4547d7d66b84f51099a85f634d5890e2890","scope":"SOURCE_ONLY_ACCEPTED_DB9"}},"crates/hepta-peer-attestation/src/approved_policy.rs":{"parent_bytes":29207,"parent_sha256":"706254153615871c6a88d0b68bd36d1eb3288f3b23d7fb7688494142c98f953d","offset":25322,"block":"\\npub(crate) use service_policy::ServiceSessionState;\\npub use service_policy::{\\n    ApprovedServiceControlReceiver, ApprovedServiceReceivedRequest, ApprovedServiceRequestBinding,\\n    ApprovedServiceRequestVerifier, ApprovedServiceRequests, ApprovedServiceRetainedReporter,\\n    ApprovedServiceSessionVerifier,\\n};\\n","anchor":"\\n#[cfg(test)]\\nmod tests {\\n","complete_bytes":29518,"complete_sha256":"61f191a620ad65b111b4da467d6ca13d96d6ef98425a9ba095d60054fc32c808","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"crates/hepta-peer-attestation/src/approved_policy.rs","mode":"100644","blob":"a1fcf36ed7eb643049c4c029aa4bffc6c07d606f","scope":"SOURCE_ONLY_ACCEPTED_DB9"}},"crates/hepta-peer-attestation/src/lib.rs":{"parent_bytes":61351,"parent_sha256":"eb30e7800ade6089bfe26b05bd5c0f0cb3d669b2fd378436bbd1e15465c868ce","offset":44143,"block":"\\n#[cfg(target_os = \\"linux\\")]\\npub use approved_policy::{\\n    ApprovedServiceControlReceiver, ApprovedServiceReceivedRequest, ApprovedServiceRequestBinding,\\n    ApprovedServiceRequestVerifier, ApprovedServiceRequests, ApprovedServiceRetainedReporter,\\n    ApprovedServiceSessionVerifier,\\n};\\n","anchor":"\\n#[cfg(test)]\\nmod tests {\\n","complete_bytes":61639,"complete_sha256":"a2ee51523eee9cd55cd759ffc6b1d9b746451558f7f5281fa273a8d269937323","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"crates/hepta-peer-attestation/src/lib.rs","mode":"100644","blob":"24054aa9635ba4af1fdc7e5d2d3960057fa98f41","scope":"SOURCE_ONLY_ACCEPTED_DB9"}},"crates/hepta-peer-attestation/src/control_owner/root_path.rs":{"parent_bytes":6485,"parent_sha256":"e3ee16c894142326bf1c612216064ce83d30893f307dee63029e9140017068b1","offset":6485,"block":"\\nmod service_request;\\n","anchor":"","complete_bytes":6507,"complete_sha256":"a0078b77190ab5a7f935ce6e7fbff6522bf4704061748498edd2aee07d234c3c","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"crates/hepta-peer-attestation/src/control_owner/root_path.rs","mode":"100644","blob":"9cfda3030ebf3e79437b1a44bc1097a8ae223433","scope":"SOURCE_ONLY_ACCEPTED_DB9"}},"crates/hepta-peer-attestation/src/control_owner/retained_request.rs":{"parent_bytes":12823,"parent_sha256":"433a0226e21135d21e6337d3adc6928ae53ed00cd4523aab687745142215aceb","offset":12823,"block":"\\nmod service_request;\\n","anchor":"","complete_bytes":12845,"complete_sha256":"fdac96f19d799e744236d0b49d9635e7a59e062018906ac88355c1b9be40eefc","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"crates/hepta-peer-attestation/src/control_owner/retained_request.rs","mode":"100644","blob":"d527a6d713e588b22f7f3f3477f7f2a4075892a3","scope":"SOURCE_ONLY_ACCEPTED_DB9"}},"crates/hepta-peer-attestation/Cargo.toml":{"parent_bytes":1188,"parent_sha256":"9e1a18ac5883de240d757085d6aa0db98d37ba75eb63692b9d406eb5ee4192bc","offset":1188,"block":"\\n# Original requests bridge retained service identity, independently of health.\\n[[test]]\\nname = \\"approved_service_request_kernel\\"\\npath = \\"tests/approved_service_request_kernel.rs\\"\\nharness = false\\n","anchor":"","complete_bytes":1384,"complete_sha256":"97cad7ebca925e745468ee6959d38c0734619493ad5d9e789e72515cb36221d8","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"crates/hepta-peer-attestation/Cargo.toml","mode":"100644","blob":"0129e89d09365e15f163d04ad5b06ca93c00648c","scope":"SOURCE_ONLY_ACCEPTED_DB9"}},"Makefile":{"parent_bytes":2595,"parent_sha256":"1906e964907c3f5e90886a64e60f0ade52146511c78cc360218378e640b5deef","offset":696,"block":"\\tpython3 tools/verify_approved_service_request.py\\n","anchor":"\\tpython3 tools/verify_retained_control_readiness.py\\n\\tpython3 too","complete_bytes":2645,"complete_sha256":"fc645701d1bcfa3db0bc7cc737fed704dd71a2337ea356042304b7e8e47dd03e","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"Makefile","mode":"100644","blob":"c249c875b622070392d11268a316a7e8559c5fd4","scope":"SOURCE_ONLY_ACCEPTED_DB9"}},"tools/verify_approved_service_owner.py":{"kind":"exact_plumbing","parent_bytes":40301,"parent_sha256":"91cad98255054747cbfcf5f78a5077e44ba6740c5b8f96f0f59d8f91066e95f2","steps":[{"parent":"    if type(text) is not str:\\n        raise ValueError(\'exact Foundation source text type differs\')","actual":"    try:\\n        from .verify_approved_service_request import parent_source as service_request_parent_source\\n    except ImportError:\\n        from verify_approved_service_request import parent_source as service_request_parent_source\\n    text = service_request_parent_source(path, text)\\n    if type(text) is not str:\\n        raise ValueError(\'exact Foundation source text type differs\')","offset_in_sequential_parent_bytes":29803,"parent_bytes":99,"actual_bytes":384,"parent_sha256":"6dbd786688e06c6b645c0fa038df0ff36ce62f8c199870eb1f0bc79d5477b8ad","actual_sha256":"d884009bd93fc66b91413138825c75ebd0f1d049491edee7703e5d30ae1ff69c"},{"parent":"    rule = EXPECTED[\'composition_receiver\'][\'source_boundaries\'].get(path)\\n","actual":"    try:\\n        from .verify_approved_service_request import parent_source as service_request_parent_source\\n    except ImportError:\\n        from verify_approved_service_request import parent_source as service_request_parent_source\\n    text = service_request_parent_source(path, text)\\n    rule = EXPECTED[\'composition_receiver\'][\'source_boundaries\'].get(path)\\n","offset_in_sequential_parent_bytes":32956,"parent_bytes":75,"actual_bytes":360,"parent_sha256":"e36dd0a26595970a3a212a0274cff846f46e50b63aa998b88c5e6721ab39663d","actual_sha256":"48c0ff064837277a7a31194e96c6eca028b3e8ba03e1c057b01392bc8da44ea4"},{"parent":"    result = dict(texts)\\n","actual":"    try:\\n        from .verify_approved_service_request import parent_source as service_request_parent_source\\n    except ImportError:\\n        from verify_approved_service_request import parent_source as service_request_parent_source\\n    texts = {path: service_request_parent_source(path, text) for path, text in texts.items()}\\n    result = dict(texts)\\n","offset_in_sequential_parent_bytes":34281,"parent_bytes":25,"actual_bytes":351,"parent_sha256":"3c4921f873d60c741ae3f1d89d1f7781ec690c8c1ebbdeb393cb168cf7a4fd70","actual_sha256":"ed67847b04cca33cdabc53877ac3aad66238a4a866f1add583d830d85cf91433"},{"parent":"    return {path: source_gate.source(root, path) for path in sorted(paths)}\\n","actual":"    try:\\n        from .verify_approved_service_request import parent_source as service_request_parent_source\\n    except ImportError:\\n        from verify_approved_service_request import parent_source as service_request_parent_source\\n    return {path: service_request_parent_source(path, source_gate.source(root, path)) for path in sorted(paths)}\\n","offset_in_sequential_parent_bytes":36857,"parent_bytes":76,"actual_bytes":345,"parent_sha256":"7c94c39a0c4ce49e124967d70ab1f41cefa3fc45fe9c89a3b82aa394028014bd","actual_sha256":"b9f12eedcf28682c9ea2bcb5060cdf9b161dbf0052813fec13a7eeea8c18cf82"}],"complete_bytes":41466,"complete_sha256":"d7c0f744b5dd05100f51869f5027fce8f1240337d500f02b980d5122dbc86bc9","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"tools/verify_approved_service_owner.py","mode":"100644","blob":"5cdab6590d70897240569d844658b13e54eff91e","scope":"SOURCE_ONLY_ACCEPTED_DB9"}},"crates/hepta-agent-transport/src/root_control_path.rs":{"parent_bytes":25926,"parent_sha256":"c9363b23989c45ec2133f43d8e8f81c819a700fa1c58d792c683aefc2cd6a71e","offset":25926,"block":"\\nmod service_control;\\n","anchor":"","complete_bytes":25948,"complete_sha256":"9f06f4c71a08a346b89d8f09ce071aa16ace6d10e2d9213cd2db5edca306bb9c","parent_source":{"head":"db9cb5399a16f794407be2c3561255e8d69fa537","path":"crates/hepta-agent-transport/src/root_control_path.rs","mode":"100644","blob":"2b9b4def2517a2bb31f4fd08c2eff88b33880bf4","scope":"SOURCE_ONLY_ACCEPTED_DB9"}}},"lifetimes":{"source_owner":"original nineteen-field Source and current actual third Owner; no deadline manufactured","request":"min original RootPath Control Instant and accepted SCM ceiling, <=20","maximum_active_mechanism_slots":1,"slot_released":"last original receiver/binding/report owner Drop, not readonly verifier","clock_from_caller":false,"source_reopen_in_factory":false,"old_request_renewal":false},"identity":{"source_and_session":"original Arc pointer equality, not nineteen-field equality substitute","attestor":"actual default /proc Live only","control_socket":"creation dev/ino/SO_COOKIE before SCM and actual returned Pending after; private transaction bit remains on detached send","logical_principal":"readonly root-selected metadata, not measured kernel field","sender_scope":"lowlevel mechanism continuity only; no Source-approved sender product factory"},"retirement":{"request_failure":"request lease/transport only","source_or_owner_failure":"same original service sticky retirement","report_action_independence":true,"unknown_journal_recovery":"not_implemented"},"preservation":{"raw_poll_none_whole_body":true,"raw_receive_send_report_wait_body":true,"old_v1_api_test_body":true,"native_six_budget_fixture":true,"foundation_kernel_budget":true,"workflow_Cargo_PIN":"whole old prefix/bytes; only separately approved new registered target suffix"},"execution":{"Rust_compiled":false,"kernel_executed":false,"all_feature_graphs":false,"source_gate_correspondence_only":true},"non_claims":{"Actor":false,"Coordinator":false,"PageOwner":false,"managed_journal":false,"native":false,"sixty_second_health":false,"installed":false,"cross_uid":false,"global_single_service":false,"G6":false,"production_ready":false},"kernel_corpus":{"path":"crates/hepta-peer-attestation/tests/approved_service_request_kernel.rs","harness":false,"groups":19,"two_requests_minimum_seconds":21,"request_seconds_maximum":20,"unit_seconds_maximum":120,"default_proc":true,"mock_or_observed_policy":false,"unsafe_fault_groups":[14,15,16,17],"execution":"NOT_EXECUTED","protocol_fault_groups":[10],"exec_scope":"Actual unapproved ELF new Owner admission; no old proof survives exec","fd_fault_scope":"Mechanism-only real same-credential endpoints, isolated single-thread syscall injection; no cleanup immunity","same_source_two_requests":true,"observed_policy_used":false,"early_root_transfer_groups":[16,17,18,19]},"known_legacy_inputs":{"crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs":[{"head":"c875ed3e3c6c876b716f415f7b766992d48e1572","bytes":16048,"sha256":"f45d4dbbb254522ea043ad42e4fbe7df33b7e1a2f898d6d6c911d8cc203c8e60","source_path":"crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs","git_mode":"100644","blob":"69aa6c9416028787b96b26931c8f7e512de245da","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"},{"head":"99c4eb9ff6f11b5075487c7e9fc4b4f0ca794320","bytes":16469,"sha256":"c011fd826aacdc21a235b301b8a3fb4b8d16258cb652030bd9647a049040a4cb","source_path":"crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs","git_mode":"100644","blob":"bd35c2f9d53955fe360d2e88b23f5ad8131c8c3b","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"}],"crates/hepta-peer-attestation/src/approved_policy/service_policy.rs":[{"head":"d3353229c3574f3125e479e3616e2f4881d259fc","bytes":19753,"sha256":"ace7e68730c50bf007863e39a83545892ecd392fb8f323d11e905da03b08168a","source_path":"crates/hepta-peer-attestation/src/approved_policy/service_policy.rs","git_mode":"100644","blob":"6199f4547d7d66b84f51099a85f634d5890e2890","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"}],"crates/hepta-peer-attestation/src/approved_policy.rs":[{"head":"c875ed3e3c6c876b716f415f7b766992d48e1572","bytes":28173,"sha256":"0a6a079336ad842bc55c34fe3930707ece098182bd976e78c2dfb21e18d87882","source_path":"crates/hepta-peer-attestation/src/approved_policy.rs","git_mode":"100644","blob":"58e24ead551345fe21858e4b5f7579b296b48108","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"},{"head":"99c4eb9ff6f11b5075487c7e9fc4b4f0ca794320","bytes":28911,"sha256":"dfb42050e73dd7f1fc6ef46aa6b839b4bc3c1c3f201ac47c5106acaada27815e","source_path":"crates/hepta-peer-attestation/src/approved_policy.rs","git_mode":"100644","blob":"64f477ee349426bbb32edc1d123c895d926690fb","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"},{"head":"d3353229c3574f3125e479e3616e2f4881d259fc","bytes":28469,"sha256":"018612ed96c97f63d673487addacfe2bb4a48b55ca8d27048ffffa340a499dfc","source_path":"crates/hepta-peer-attestation/src/approved_policy.rs","git_mode":"100644","blob":"6d48b9ec8882a277da28e48eae47f41a37386528","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"}],"crates/hepta-peer-attestation/src/lib.rs":[{"head":"c875ed3e3c6c876b716f415f7b766992d48e1572","bytes":61121,"sha256":"91a879f50a94954a6679ee5e973eb70f0aa3c086743c83e9c2858091a8ff6210","source_path":"crates/hepta-peer-attestation/src/lib.rs","git_mode":"100644","blob":"80c105465863d73b5ea6d888e340542511de8033","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"},{"head":"d3353229c3574f3125e479e3616e2f4881d259fc","bytes":61351,"sha256":"eb30e7800ade6089bfe26b05bd5c0f0cb3d669b2fd378436bbd1e15465c868ce","source_path":"crates/hepta-peer-attestation/src/lib.rs","git_mode":"100644","blob":"24054aa9635ba4af1fdc7e5d2d3960057fa98f41","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"}],"crates/hepta-peer-attestation/src/control_owner/root_path.rs":[{"head":"c875ed3e3c6c876b716f415f7b766992d48e1572","bytes":6485,"sha256":"e3ee16c894142326bf1c612216064ce83d30893f307dee63029e9140017068b1","source_path":"crates/hepta-peer-attestation/src/control_owner/root_path.rs","git_mode":"100644","blob":"9cfda3030ebf3e79437b1a44bc1097a8ae223433","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"}],"crates/hepta-peer-attestation/src/control_owner/retained_request.rs":[{"head":"c875ed3e3c6c876b716f415f7b766992d48e1572","bytes":12807,"sha256":"f6f70998cf1b2b1e20857263a07d3101cf5f67ca4fcaa930b88a527445bdf754","source_path":"crates/hepta-peer-attestation/src/control_owner/retained_request.rs","git_mode":"100644","blob":"9d983a59b85f7fba2a4909bef71e5649ff778a62","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"},{"head":"99c4eb9ff6f11b5075487c7e9fc4b4f0ca794320","bytes":12823,"sha256":"433a0226e21135d21e6337d3adc6928ae53ed00cd4523aab687745142215aceb","source_path":"crates/hepta-peer-attestation/src/control_owner/retained_request.rs","git_mode":"100644","blob":"d527a6d713e588b22f7f3f3477f7f2a4075892a3","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"}],"crates/hepta-peer-attestation/Cargo.toml":[{"head":"c875ed3e3c6c876b716f415f7b766992d48e1572","bytes":996,"sha256":"1fac9d1b123cdfd9bb47321bcb98b2b3ce936a88f0fe6fdafe5cdfed0ca7bb83","source_path":"crates/hepta-peer-attestation/Cargo.toml","git_mode":"100644","blob":"094b1bb4b7bcbc23a0a18ff416d3f344c8c7a524","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"},{"head":"d3353229c3574f3125e479e3616e2f4881d259fc","bytes":1188,"sha256":"9e1a18ac5883de240d757085d6aa0db98d37ba75eb63692b9d406eb5ee4192bc","source_path":"crates/hepta-peer-attestation/Cargo.toml","git_mode":"100644","blob":"0129e89d09365e15f163d04ad5b06ca93c00648c","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"}],"Makefile":[{"head":"c875ed3e3c6c876b716f415f7b766992d48e1572","bytes":2444,"sha256":"6df4be64e5ffe527caf41e00cb996d26e53e4f12c43200d751c62c2da8c1f329","source_path":"Makefile","git_mode":"100644","blob":"e64e27df73f44f41d52bcd30a2daec983cca9935","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"},{"head":"99c4eb9ff6f11b5075487c7e9fc4b4f0ca794320","bytes":2547,"sha256":"4ee82da56cabf7315bd38967a6a9340b01b8d2642224c35950ee142842168c30","source_path":"Makefile","git_mode":"100644","blob":"014384f5cf76fe6c7cc95f209107ca845e95b2d1","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"},{"head":"d3353229c3574f3125e479e3616e2f4881d259fc","bytes":2492,"sha256":"27ff7704fc6f326b24d725c34929aa3a73d11023773e43a4a946abb52acf42d9","source_path":"Makefile","git_mode":"100644","blob":"77fd0c64955adfa7c0e2d684adc34128bcee124e","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"}],"tools/verify_approved_service_owner.py":[{"head":"d3353229c3574f3125e479e3616e2f4881d259fc","bytes":19878,"sha256":"105a942c9d9f998c82825e4c3d40a35fb024d2b5ab82a105d815c28df375a90f","source_path":"tools/verify_approved_service_owner.py","git_mode":"100644","blob":"4124efe69a038ad4a4efa006bdf875895b38b70d","source":"actual_git_object_in_owned_db9_clone","scope":"DENIAL_ONLY_NORMALIZATION_NOT_CURRENT_P1"}]},"private_helper_inventory":{"RootPathAttestedHandoffReceiver::from_service_control":{"path":"crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs","signature":"pub(crate) fn from_service_control(connection: RootPathControlConnection, session: &ServiceSessionState, expected_agent_path: &Path) -> Result<Self, ControlOwnerError>"},"RootPathAttestedHandoffReceiver::receive_service_control":{"path":"crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs","signature":"pub(crate) fn receive_service_control(&mut self, session: &ServiceSessionState) -> Result<ControlRetainedAcceptedStream, ControlOwnerError>"},"AttestedHandoffReceiver::receive_service_control":{"path":"crates/hepta-peer-attestation/src/control_owner/retained_request/service_request.rs","signature":"pub(in crate::control_owner) fn receive_service_control(&mut self, session: &ServiceSessionState) -> Result<ControlRetainedAcceptedStream, ControlOwnerError>"},"ServiceSessionState::ensure_current":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","signature":"pub(crate) fn ensure_current(&self) -> Result<(), ApprovedPolicyError>"},"ServiceSessionState::control_policy":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","signature":"pub(crate) fn control_policy(&self) -> Result<ControlOwnerPolicy, ApprovedPolicyError>"},"ServiceSessionState::verify_control":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","signature":"pub(crate) fn verify_control(&self, attested: &AttestedPeer) -> Result<(), ApprovedPolicyError>"}},"effect_orders":{"HandoffReceiver::receive_retained_service_control":{"path":"crates/hepta-agent-transport/src/accepted_handoff/retained_control/service_control.rs","markers":["self.channel.owner()?","self.channel.original_identity.verify(fd)?","self.receive_retained(wait_budget)?","pending.transaction.channel.original_identity.verify(fd)?","pending.transaction.readiness_enabled = true","pending.ensure_current()?","transferred.received.verify()?"]},"HandoffSender::send_retained_service_control":{"path":"crates/hepta-agent-transport/src/accepted_handoff/retained_control/service_control.rs","markers":["self.channel.owner()?","self.channel.original_identity.verify(fd)?","self.send_retained(custody)?","pending.transaction.channel.original_identity.verify(fd)?","pending.transaction.readiness_enabled = true","pending.ensure_current()?"]},"RootPathAttestedHandoffReceiver::from_service_control":{"path":"crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs","markers":["session.ensure_current()","connection.consume_service_control_before","session.original_owner_root_scope()","RetainedRootPath::new(custody, deadline)?","session.control_policy()","ControlPeerOwner::admit","owner.current_for_service(session)?","remaining(owner_pid, deadline)?","HandoffReceiver::from_control","owner.current_for_service(session)?"]},"AttestedHandoffReceiver::receive_service_control":{"path":"crates/hepta-peer-attestation/src/control_owner/retained_request/service_request.rs","markers":["creator(self.owner_pid)?","session.ensure_current()","self.ensure_service_current(session)?","let wait = remaining(self.owner_pid, self.deadline)?","receive_retained_service_control(wait)","transferred.into_parts()","owner.current_for_service(session)?","owner.request_deadline(deadline)?","custody.retain_root_path","retained.ensure_current()?","session.ensure_current()"]},"ApprovedServiceRequests::from_owner":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["owner.ensure_current()?","Arc::clone(&owner.state)","owner.verifier()?","Arc::ptr_eq(&source, &verifier.state)","original_owner: Some(owner)","result.ensure_current()?"]},"ServiceSessionState::ensure_current":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.source.creator_current()?","self.owner.ensure_current()?","self.source.inspect()"]},"ServiceRequestState::same_session":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.session.source.creator_current()?","Arc::ptr_eq(&self.session, &session.session)","self.session.ensure_current()"]},"ServiceRequestState::current":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.session.ensure_current()?","remaining(self.session.source.creator.pid, self.deadline)?","self.control.verify_pair_current(original)","self.session.ensure_current()?","remaining(self.session.source.creator.pid, self.deadline)"]},"ApprovedServiceControlReceiver::receive_request":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.session.ensure_current()?","remaining(self.session.source.creator.pid, self.original_control_deadline)?","receiver.receive_service_control(&self.session)","transferred.consume_before","deadline > original_control_deadline","ProcfsPeerAttestor::default().attest(peer, &entry.runtime())","attested.request_custody()","control.verify_pair_current","retained.ensure_current()","session.ensure_current()?","remaining(session.source.creator.pid, deadline)?","ApprovedServiceReceivedRequest"]},"ApprovedServiceReceivedRequest::consume_with_request_binding":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.binding.slot_current()?","remaining(self.session.source.creator.pid, self.deadline)?","let mut received = self","received.ensure_consume_current()?","let Self","} = received","let principal = session.source.entries[1].principal.as_str()","let result = consumer(","session.ensure_current()?","remaining(session.source.creator.pid, deadline)?","Ok(result)"]},"ApprovedServiceRetainedReporter::ensure_current":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.session.source.creator_current()?","Arc::ptr_eq(&self.slot.session, &self.session)","self.session.ensure_current()?","remaining(self.session.source.creator.pid, self.deadline)?","self.retained.as_mut()","self.session.ensure_current()?","remaining(self.session.source.creator.pid, deadline)?"]},"ApprovedServiceRetainedReporter::poll_cancel":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.ensure_current()?",".poll_cancel()","self.session.ensure_current()?","remaining(self.session.source.creator.pid, self.deadline)?"]},"ApprovedServiceRetainedReporter::send_remote_report":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.ensure_current()?","self.retained.take()","retained.send_remote_report(report)","self.session.ensure_current()?","remaining(self.session.source.creator.pid, self.deadline)"]},"RootPathControlConnection::consume_service_control_before":{"path":"crates/hepta-agent-transport/src/root_control_path/service_control.rs","markers":["creator(self.owner_pid)?","let mut guard = OriginalTransferGuard","completed: false","remaining(self.owner_pid, self.deadline)?","self.deadline()?","let fd = self.socket.as_ref()","verify_moved(&guard.scope, fd)?","self.consume_before(consumer)?","if let Err(error) = verify_moved(&guard.scope, fd)","guard.scope.current.store(false, Ordering::Release)","return Err(error)","guard.completed = true","Ok(result)"]},"verify_moved":{"path":"crates/hepta-agent-transport/src/root_control_path/service_control.rs","markers":["creator(scope.owner_pid)?","remaining(scope.owner_pid, scope.deadline)?","scope.check()?","libc::fcntl(fd, libc::F_GETFD)","scope.socket_identity != Identity::from(&stat(fd)?)","scope.cookie != option::<u64>(fd, libc::SO_COOKIE)?","scope.identity !=","scope.check()?","remaining(scope.owner_pid, scope.deadline)?"]},"Drop:OriginalTransferGuard::drop":{"path":"crates/hepta-agent-transport/src/root_control_path/service_control.rs","markers":["if !self.completed","self.scope.current.store(false, Ordering::Release)"]},"ServiceSessionState::original_owner_root_scope":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.source.creator_current()?","Arc::ptr_eq(&self.source, &self.owner.state)","self.source.inspect()?","self.owner.original.ensure_alive()","self.owner.original.original_attested_peer()","original.attestor.proc_root != Path::new(\\"/proc\\")","crate::ExecutableSource::Live","snapshot.pid != self.source.creator.pid","snapshot.uid != entry.uid","snapshot.gid != entry.gid","snapshot.systemd_unit.as_deref()","snapshot.cgroup_v2_path != entry.cgroup","snapshot.executable_sha256 != entry.pin","self.source.inspect()?","self.owner.original.ensure_alive()","self.source.creator_current()?","if checked.is_err()","self.source.retired.store(true, Ordering::SeqCst)","checked"]},"ServiceSessionState::control_policy":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.original_owner_root_scope()?","let policy = self.source.entries[0].control()?","self.original_owner_root_scope()?","Ok(policy)"]},"ControlPeerOwner::current_for_service":{"path":"crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs","markers":["creator(self.owner_pid)?","remaining(self.owner_pid, self.deadline)?","self.attestor.proc_root != Path::new(\\"/proc\\")","crate::ExecutableSource::Live","!self.approved.is_empty()","self.root_path.as_ref()","path.current()?","session.verify_control(&self.attested)","path.current()?","remaining(self.owner_pid, self.deadline)"]},"AttestedHandoffReceiver::ensure_service_current":{"path":"crates/hepta-peer-attestation/src/control_owner/retained_request/service_request.rs","markers":["creator(self.owner_pid)?","if self.cancelled","Err(ControlOwnerError::Cancelled)","self.owner.as_ref().ok_or(ControlOwnerError::ChannelRetired)","owner.current_for_service(session)",".map(|_| self.deadline)","if result.is_err()","self.retire()?","result"]},"ApprovedServiceReceivedRequest::ensure_consume_current":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","markers":["self.session.source.creator_current()?","!Arc::ptr_eq(&self.session, &self.reporter.session)","!Arc::ptr_eq(&self.session, &self.binding.state.session)","!Arc::ptr_eq(&self.reporter.slot, &self.binding.slot)","self.deadline != self.reporter.deadline","self.deadline != self.binding.state.deadline","self.reporter.ensure_current()?","let state = &self.binding.state","let checked = (||","remaining(state.session.source.creator.pid, state.deadline)?","state.retired.load(Ordering::SeqCst)","state.control.verify_pair_current(&self.binding.original.verifier())","state.session.ensure_current()?","remaining(state.session.source.creator.pid, state.deadline)","if checked.is_err()","state.retired.store(true, Ordering::SeqCst)","checked"]}},"preserved_source_sha256":{"crates/hepta-peer-attestation/src/request_lease.rs":"54b80b2e94f4dc149d9af8f6e92815a2a8b88a9db987c34ec9a0b59d53850681","crates/hepta-peer-attestation/src/approved_policy/service_policy/creator_context.rs":"31c3b36ecb47b700b08df7e374b6ceadddb44527acf1ae6d8c5efb83a090eb06","crates/hepta-agent-transport/src/accepted_handoff.rs":"988ab3003afd3f4c4381b989b7581376c970e30af958470e0f47561cb4eea84f","crates/hepta-peer-attestation/tests/approved_service_owner_kernel.rs":"17be60a757254cf07adbb6dd3d6158ae6f990bc2cd6aecf4130c94965b785bda","experiments/servo-product-owner/src/approved_connected_tests.rs":"1825c758d95b46958ec71edeb747782e287df40019f5850a5439bc80deddc442","experiments/servo-product-owner/src/approved_test_support.rs":"19e1e5269027ab4b81fa4a5ac41517dd6dfea5665141486297f351bf01e4745d","experiments/servo-product-owner/src/connected_tests.rs":"e22417fdccfadfb0eccaa7d253a7af9ed93f210d739cd16e32e952c29ccb7f5f","manifests/servo.lock.json":"a64fc7f64926d0a3726ce50551aa879065bcfac285caa553494c7be59ad953f4","manifests/rust-toolchain.lock.json":"417f63317d52a3f4cbbd4160966e50a3b17824e096c823ce499481d866c319d7","Cargo.lock":"fde6ce60b8b1564562efc6a15848dda3a07bf6d7a9b51e3322d0c42d25e356a2","Cargo.toml":"dc90e547920d9559671d09599bc2b0df55f2c1a73b3c3b7eb015667445d56814","tests/test_approved_service_owner.py":"a2a8236203d1d9b0800fd8807fa4dce875960f88133bb2e5a422c74a04d0cdac","tests/test_approved_composition_scope.py":"40d631f98f3119236a3443521919602fd803a551f0a9d603f7f69531a4a22a21","tests/test_approved_constructor_route.py":"859eb71a27d7a01f6d21faeda6dea84626df178229141738e44410184677df73","tests/test_retained_control_readiness.py":"a94c33c71c8be280adf73675c0f711c7989868cb035a0e953d2deec69a484e35","crates/hepta-agent-transport/src/accepted_handoff/retained_control/readiness_tests.rs":"52968e54e45baf3cacb7beb03c6f4df6bb7e1c467156c6f564a32e859853a444","apps/hepta-browserd/tests/control_readiness_kernel.rs":"10d846a7e356056d80895ff01bc82c08504e76fdf422c80ddbb96d27093c2453"},"kernel_source_sha256":{"crates/hepta-peer-attestation/tests/approved_service_request_kernel.rs":"6f099409079351f5793a669e43f71cd9f0441befaec20f3003e910156ed5c8fa"},"early_root_transfer":{"creation_identity":"original RootPathControlConnection admission capture; no channel-time recapture authority","actual_fd_pre_and_post":true,"held_original_scope_pre_and_post":true,"unchanged_old_consume_delegate_once":true,"failure_or_unwind_retires":"only original ConnectionScope.current; no extra shared PathSnapshot or service Source writes","shared_path_failure":"legacy full check retains its existing direct pathname-drift retirement semantics","completed_false_until_post_proof":true,"escaping_custody_or_verifier_revoked":true,"callback_side_effect_authority":false,"expected_public_methods":18,"expected_opaque_types":7,"production_children":5,"previous_source_draft":"93a73c063a6b19e0bb36f438e74465f2190524ca","previous_qualification":"NONE_EARLY_GAP_KNOWN","post_failure_before_T_drop":true},"denial_scope_helper_inventory":{"ServiceSessionState::original_owner_root_scope":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","signature":"pub(crate) fn original_owner_root_scope(&self) -> Result<(), ApprovedPolicyError>"}},"private_helper_full_tokens_sha256":{"RootPathAttestedHandoffReceiver::from_service_control":"40d5923e6d7237e9f2a0b3e87709e653f5b6180ded9da9d2904e6faa83a37a6f","RootPathAttestedHandoffReceiver::receive_service_control":"a290425da7df59efcaa4e0c7bb77262c56e96e5cf5d6cd2488826c52c818cf32","AttestedHandoffReceiver::receive_service_control":"e832350cf1b06b3819ff2261435edb93b3777633265ef21177195bf4d0c64a79","ServiceSessionState::ensure_current":"fe3acf90888b2016273b0e64d562281105eac9b0747e5def32a6b065e59d0700","ServiceSessionState::control_policy":"96d709fbdc5d722af5669abd9b1051e4764a1676c19147ccbd507b689d70ac4f","ServiceSessionState::verify_control":"bb037672973fb753ca44e3096b74a6cbbe2147ecce1f40f3cc9f7d8d60a557c8","ServiceSessionState::original_owner_root_scope":"a657ae8854f03207f23a2e25dfc7ef2132c4708287a9c5d368a5543f9ac50d38","ControlPeerOwner::current_for_service":"2f427d5ade33ff1c184eae3e2ba872d80571e8c5770e2a362a735250d2b72fa2","AttestedHandoffReceiver::ensure_service_current":"6793d5816f8560bb0c34b746590b1b044200eda2771275c3b2f108712cd8f480"},"all_function_body_tokens_sha256":{"crates/hepta-agent-transport/src/accepted_handoff/retained_control/service_control.rs":{"HandoffReceiver::receive_retained_service_control":"fc6434cb56f02d4deb5bba0f8e2f4a29eea9716fcd02260211f38fd7bae3670d","HandoffSender::send_retained_service_control":"e57e82acc94d53782aab6df31719d2ee3624a55a28ab42f296555fe8370ade15"},"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs":{"ServiceSessionState::ensure_current":"db28511bdedd273cb0fec7608aab9ddfaee43128880afede9cc584fb1fed1f38","ServiceSessionState::original_owner_root_scope":"ba621e70dbf0d93586ec0115ab29c554981d955116aa1f117331a22b7c3feb12","ServiceSessionState::control_policy":"d2b0f36ae12599560bad16d485e2a5d24a392701ff5a55cce24de6193c7b2655","ServiceSessionState::verify_control":"1a6aedc2dafd574a25675b86a5bd3f812e94eac03329a6659a5c576f6f0de176","Drop:ServiceRequestSlot::drop":"73837881e3eeb4390bd5fcad92dffb5a65f14520f223f4f6bb0c5d4692eaea45","ServiceRequestState::same_session":"50e48fbe51c6911af07b47affdf513febe7397dfbacffe2522a989e330079025","ServiceRequestState::current":"c3924afb83c4d19ad72812a8da86a8b9119cc87007bf388e0e462ee389571f00","ApprovedServiceRequests::from_owner":"b212ec0eead39f8f63f255c2e32427db2a7fd4bee74facde0db77190ecd5dc7c","ApprovedServiceRequests::ensure_current":"14c40eb9e5c71776fc8033f3b9da996c14611d676a2e2d7892d4691bd6495fe6","ApprovedServiceRequests::session_verifier":"b31995605b9acc275b35970612c0c6ac704de039d3ef3414bd47f42619aee2a6","ApprovedServiceRequests::bind_control":"1e87e35df571e7596cd6f2beb9f0c0137352c92b15cd5e3bdff9431f8d868e2d","ApprovedServiceSessionVerifier::ensure_current":"5d56b69de50d4a76a9f6284bb4a54d9852f6f4356117f1748b42da3969fb8ea3","ApprovedServiceControlReceiver::receive_request":"861f035583b3285e448e0c85bacf3c759d7d6c8d63abdd38993c8092bc7fd39d","ApprovedServiceReceivedRequest::original_deadline":"baf14ce04ebcf23ea56d06084fdd0dd445fac0cec98391d14ef1cddb519c1bbe","ApprovedServiceReceivedRequest::consume_with_request_binding":"05e90ce06e37c67d005b3fdb83fea590b0b14673171e8b4b7e20baedd29e17a2","ApprovedServiceRequestBinding::slot_current":"7f2997eb99141e9a588c784479903e861983d0dcf41b79cc7ee804a6c3d8ce7e","ApprovedServiceRequestBinding::verify_for_service":"1eb76976c660040e6ddca326ae91b7b4685d815750ea3febd5768794a796844f","ApprovedServiceRequestBinding::verifier_for_service":"9ef9be32ec23e33ecfb9d6c82b7157dc07e13ee3e900a97a51c3ceff5e556c10","ApprovedServiceRequestVerifier::verify_for_service":"9007e7ec70eed0a9ec53fd392c1d73639d78695389f422c9eb458b7c72b4b18f","ApprovedServiceRequestVerifier::with_original_pair":"e7951c9578af2e573b3bc6e305732caaedeca7514fd8b0affe92616110a79eca","ApprovedServiceRetainedReporter::ensure_current":"777fd7af635a784bc282fd9aa1fb81d3cfc95d7dc5211f82fbed0ce30aa50372","ApprovedServiceRetainedReporter::original_deadline":"34436a63d3fc3c926b5d0b6e809e0dd4b592b3dc666969f1706f31a0aa9d1f96","ApprovedServiceRetainedReporter::poll_cancel":"24f9cc30a10577a84b29bb052ebd93d131f3112eeefba138e105edfd7c5e90c8","ApprovedServiceRetainedReporter::send_remote_report":"9bb269aa7d09cb48b809637b03f8d96e808df1e45410660a773c094b0b613ca6","ApprovedServiceReceivedRequest::ensure_consume_current":"524bd1ae14390182e6e3b7b5f984e3663072ffc9ae279d7b773b255657629850"},"crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs":{"service_error":"bac7640713b5e64ad4471d246437914b3dae31f3c18ee1dbd978701919b56836","RootPathAttestedHandoffReceiver::from_service_control":"f87779927657811a33029c93e8156898a1e576bc1f4b7389386099d2e57bda5c","RootPathAttestedHandoffReceiver::receive_service_control":"75d45e56cf8b2f0738bced5e929920ddc961cc2985f2e17b5bcc27694b6c016e","ControlPeerOwner::current_for_service":"a0883a5288368a9a8f97b014bc236e099bda644e636b5056e605213fdea5c164"},"crates/hepta-peer-attestation/src/control_owner/retained_request/service_request.rs":{"service_error":"bac7640713b5e64ad4471d246437914b3dae31f3c18ee1dbd978701919b56836","AttestedHandoffReceiver::receive_service_control":"b4b08c43d1f83b182dacfbaee2e7a865739c98bc8079f51eb65bdab74f57b4a5","AttestedHandoffReceiver::ensure_service_current":"ada6c1539bb63975f8ae2b8014e4cd4150b05140a77969cf1768b3cb8cbd1633"},"crates/hepta-agent-transport/src/root_control_path/service_control.rs":{"Drop:OriginalTransferGuard::drop":"7cb21670d4e2e579529f7668d9d6c3ab0c0058ca32126e75a5972a6d781a06e2","verify_moved":"e2c37265c02c2efd9348735f2fb9c9ed8be0daffc71256dacf4fdcc1ab1d5dfe","RootPathControlConnection::consume_service_control_before":"6eed48eab29f7c924aceb0ce112ce68371f3daecf814318f98a2f14bdff2da6e"}},"denial_scope_call_inventory":{"ServiceSessionState::control_policy":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","count":2},"RootPathAttestedHandoffReceiver::from_service_control":{"path":"crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs","count":1}},"private_owner_scope":{"status":"SOURCE_PRIVATE_PURE_POLICY_COMPOSITION","total_restricted_helpers":9,"old_six_table_unchanged":true,"new_scope_helper_count":1,"allowed_original_pure_stage_calls":3,"fresh_current_owner_executable_observed":false,"same_original_owner_lease_pidfd":true,"stored_root_selected_metadata_only":true,"default_proc_live_original_binding":true,"original_creator_and_root_path_namespaces":true,"root_source_bytes_and_names_checked_before_after":true,"real_effect_source_owner_control_full_before_after_unchanged":true,"public_and_raw_full_methods_whole_unchanged":true,"cross_transaction_cached_approval":false,"new_action_or_report_authority":false,"kernel_current_source_execution":"NOT_EXECUTED","performance_improvement":"NOT_MEASURED_OR_QUALIFIED"},"composed_service_helper_inventory":{"ControlPeerOwner::current_for_service":{"path":"crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs","signature":"pub(in crate::control_owner) fn current_for_service(&self, session: &ServiceSessionState) -> Result<Duration, ControlOwnerError>"},"AttestedHandoffReceiver::ensure_service_current":{"path":"crates/hepta-peer-attestation/src/control_owner/retained_request/service_request.rs","signature":"pub(in crate::control_owner) fn ensure_service_current(&mut self, session: &ServiceSessionState) -> Result<Instant, ControlOwnerError>"}},"service_control_composition":{"status":"SOURCE_PRIVATE_FULL_GUARD_COMPOSITION_RUNTIME_PENDING","old_six_helpers_and_denial_scope_one_unchanged":true,"new_composed_helper_count":2,"actual_total_restricted_helpers":9,"actual_original_Control_challenge_count":1,"full_Source_Owner_prepost_and_original_live_Control_snapshot":true,"Creator_original_deadline_before_after_and_Root_path_before_after":true,"only_default_proc_Live_rooted_empty_legacy_guard_owner":true,"original_cancellation_and_error_retirement":true,"four_static_duplicate_Control_refresh_calls_removed":true,"snapshot_call_counts_or_latency_actually_measured":false,"original_source_parent":"0c94d5e66d35cd575028f51961c40af36c7f19cc","kernel_on_current_source":"NOT_EXECUTED","performance_improvement":"NOT_MEASURED_OR_QUALIFIED","production_ready":false},"service_consume_guard_composition":{"status":"SOURCE_SINGLE_PUBLIC_BODY_GUARD_COMPOSITION_RUNTIME_PENDING","only_public_body_changed":"ApprovedServiceReceivedRequest::consume_with_request_binding","public_signatures18_and_opaque7_unchanged":true,"other_public17_and_nine_private_helpers_whole_unchanged":true,"same_original_Creator_slot_and_absolute_deadline":true,"full_independent_reporter_Source_Owner_Control_channel_prepost":true,"full_same_original_Agent_Control_pair_immediately_before_consumer":true,"full_Source_Owner_and_original_deadline_after_callback":true,"legitimate_callback_request_retirement_still_allowed":true,"cross_transaction_or_cross_stage_cached_approval":false,"static_removed_first_duplicate_request_current":true,"actual_snapshot_call_counts_or_latency_measured":false,"kernel_on_current_source":"NOT_EXECUTED","performance_improvement":"NOT_MEASURED_OR_QUALIFIED","production_ready":false},"consume_pair_boundary_helper_inventory":{"ApprovedServiceReceivedRequest::ensure_consume_current":{"path":"crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs","signature":"fn ensure_consume_current(&mut self) -> Result<(), ApprovedPolicyError>","full_tokens_sha256":"b5a532294250f5abd756a3e92c95fae1f6694352f7c47ba73aecb564ae7d8355"}},"service_consume_reporter_pair_boundary":{"status":"SOURCE_PRIVATE_OWNED_ADJACENT_FULL_BOUNDARY_COMPOSITION_RUNTIME_PENDING","only_public_body_changed":"ApprovedServiceReceivedRequest::consume_with_request_binding","new_plain_private_helper":"ApprovedServiceReceivedRequest::ensure_consume_current","sole_owned_consume_call_count":1,"legacy_restricted_helpers9_whole":true,"public18_signatures_and_opaque7_whole":true,"Reporter_complete_guard_whole":true,"same_original_session_slot_and_exact_captured_deadline":true,"same_original_Agent_Control_full_pair_and_post_Source_Owner":true,"original_clock_and_sticky_request_report_retirement":true,"legitimate_callback_action_retirement_allowed":true,"new_caller_proof_or_shared_authority_object_or_cache":false,"static_adjacent_full_Owner_refreshes_before_callback_4_to_3":true,"temporary_drift_identical_sampling_time_claim":false,"runtime_snapshot_counts_or_latency_measured":false,"kernel_on_current_source":"NOT_EXECUTED","production_ready":false}}')

def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _pinned(text, rule, prefix='parent'):
    if type(text) is not str:
        return False
    raw = text.encode('utf-8')
    return len(raw) == rule[prefix + '_bytes'] and hashlib.sha256(raw).hexdigest() == rule[prefix + '_sha256']


def parent_source(path, text):
    """Bounded denial-only inverse; hashes never grant process authority."""
    if type(text) is not str:
        raise ValueError('exact service bridge source type differs')
    rule = EXPECTED['original_source_inverse'].get(path)
    if rule is None:
        return text
    if _pinned(text, rule):
        return text
    for known in EXPECTED['known_legacy_inputs'].get(path, []):
        raw = text.encode('utf-8')
        if len(raw) == known['bytes'] and hashlib.sha256(raw).hexdigest() == known['sha256']:
            return text
    if not _pinned(text, rule, 'complete'):
        raise ValueError('complete service bridge source differs')
    if rule.get('kind') == 'exact_plumbing':
        for step in reversed(rule['steps']):
            if text.count(step['actual']) != 1:
                raise ValueError('unique service bridge reader transfer differs')
            text = text.replace(step['actual'], step['parent'], 1)
    else:
        raw = text.encode('utf-8')
        block = rule['block'].encode('utf-8')
        offset = rule['offset']
        if raw[offset:offset + len(block)] != block:
            raise ValueError('exact service bridge insertion position differs')
        text = (raw[:offset] + raw[offset + len(block):]).decode('utf-8', 'strict')
        anchor = rule['anchor']
        if anchor and not text.encode('utf-8')[offset:].startswith(anchor.encode('utf-8')):
            raise ValueError('exact service bridge parent anchor differs')
    if not _pinned(text, rule):
        raise ValueError('whole service bridge parent restoration differs')
    return text


def inputs(root=ROOT):
    paths = (set(EXPECTED['original_source_inverse']) |
             set(EXPECTED['whole_production_source_sha256']) |
             set(EXPECTED['preserved_source_sha256']) |
             set(EXPECTED['kernel_source_sha256']) | set(_CONSUME_GUARD_MODULES))
    return {path: source_gate.source(root, path) for path in sorted(paths)}


def _private_header(text, name):
    # Finite reviewed declarations only. Actual compilation remains required.
    items = source_gate.tokens(text)
    owner, method = name.rsplit('::', 1)
    declarations = [index for index in range(len(items) - 2)
                    if items[index:index + 3] == ['impl', owner, '{']]
    if len(declarations) != 1:
        raise ValueError('unique private service implementation differs')
    opening = declarations[0] + 2
    end = source_gate.closing(items, opening)
    starts = [index for index in range(opening + 1, end - 1)
              if items[index] == 'fn' and items[index + 1] == method]
    if len(starts) != 1:
        raise ValueError('unique private service declaration differs')
    index = starts[0]
    stop = items.index('{', index)
    start = index
    if index and items[index - 1] == ')':
        start = index - 2
        while start >= 0 and items[start] != 'pub':
            start -= 1
    if start < 0:
        raise ValueError('private service declaration visibility differs')
    return ' '.join(items[start:stop])


def _restricted_helpers(text):
    """Complete finite restricted-visibility method closure, not Rust approval."""
    items = source_gate.tokens(text)
    found = {}
    def walk(start, stop, owner=None):
        index = start
        while index < stop:
            item = items[index]
            if item == 'impl':
                opening = items.index('{', index + 1, stop)
                header = items[index + 1:opening]
                context = ('Drop:' + header[header.index('for') + 1]
                           if header[:2] == ['Drop', 'for'] else header[0])
                end = source_gate.closing(items, opening)
                walk(opening + 1, end, context)
                index = end + 1
                continue
            if item == 'fn':
                opening = items.index('{', index + 2, stop)
                end = source_gate.closing(items, opening)
                if index and items[index - 1] == ')':
                    cursor, depth = index - 1, 1
                    while depth and cursor > start:
                        cursor -= 1
                        depth += (items[cursor] == ')') - (items[cursor] == '(')
                    if depth == 0 and cursor > start and items[cursor - 1] == 'pub':
                        name = (owner + '::' if owner else '') + items[index + 1]
                        if name in found:
                            raise ValueError('duplicate restricted service helper')
                        found[name] = ' '.join(items[cursor - 1:opening])
                index = end + 1
                continue
            if item in {'struct', 'enum'}:
                opening = index + 2
                while items[opening] not in {'{', '(', ';'}:
                    opening += 1
                index = (opening + 1 if items[opening] == ';'
                         else source_gate.closing(items, opening) + 1)
                continue
            if item == '{':
                index = source_gate.closing(items, index) + 1
            else:
                index += 1
    walk(0, len(items))
    return found

def _composed_service_semantics(texts, inventories):
    """Reviewed finite guard composition, independent of rebound digests/orders.

    This is Source correspondence only. It cannot approve a process, prove Rust
    compilation or establish latency. The exact two helper bodies preserve the
    original guards; every actual effect route remains separately ordered.
    """
    rooted = 'crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs'
    packed = 'crates/hepta-peer-attestation/src/control_owner/retained_request/service_request.rs'
    helpers = {
        'ControlPeerOwner::current_for_service': (rooted,
            'pub(in crate::control_owner) fn current_for_service(&self, session: &ServiceSessionState) -> Result<Duration, ControlOwnerError>',
            '''creator(self.owner_pid)?;
               remaining(self.owner_pid, self.deadline)?;
               if self.attestor.proc_root != Path::new("/proc")
                  || !matches!(self.attested.executable_source, crate::ExecutableSource::Live)
                  || !self.approved.is_empty() {
                   return Err(ControlOwnerError::PeerRefused);
               }
               let path = self.root_path.as_ref().ok_or(ControlOwnerError::PeerRefused)?;
               path.current()?;
               session.verify_control(&self.attested).map_err(service_error)?;
               path.current()?;
               remaining(self.owner_pid, self.deadline)'''),
        'AttestedHandoffReceiver::ensure_service_current': (packed,
            'pub(in crate::control_owner) fn ensure_service_current(&mut self, session: &ServiceSessionState) -> Result<Instant, ControlOwnerError>',
            '''creator(self.owner_pid)?;
               let result = if self.cancelled {
                   Err(ControlOwnerError::Cancelled)
               } else {
                   self.owner.as_ref().ok_or(ControlOwnerError::ChannelRetired)
                       .and_then(|owner| owner.current_for_service(session))
                       .map(|_| self.deadline)
               };
               if result.is_err() { self.retire()?; }
               result'''),
    }
    if set(EXPECTED['composed_service_helper_inventory']) != set(helpers):
        raise ValueError('closed two full service composition helpers differ')
    if EXPECTED['private_owner_scope']['total_restricted_helpers'] != 9:
        raise ValueError('complete service helper total differs')
    for name, (path, header, body) in helpers.items():
        if source_gate.signature(_private_header(texts[path], name)) != source_gate.signature(header):
            raise ValueError('full service composition signature differs')
        actual = source_gate.function(inventories[path], name)
        # Complete reviewed bodies, including cancellation/error branches and
        # both original deadlines/paths, cannot be rebound into weaker guards.
        if source_gate.signature(' '.join(actual)) != source_gate.signature(body):
            raise ValueError('full service composition guard body differs')
    # The same original full method must remain complete: its name alone cannot
    # become a rebound substitute for Source/Owner pre/post or the actual fresh
    # default-proc Control snapshot and every originally selected role field.
    bridge = 'crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs'
    original_full = {
        'ServiceSessionState::ensure_current': '''
            self.source.creator_current()?;
            self.owner.ensure_current()?;
            self.source.inspect()''',
        'ServiceSessionState::verify_control': '''
            self.ensure_current()?;
            if attested.attestor.proc_root != Path::new("/proc")
                || !matches!(attested.executable_source, crate::ExecutableSource::Live) {
                return Err(ApprovedPolicyError::PeerRefused);
            }
            attested.refresh_snapshot(&ProcfsPeerAttestor::default())
                .map_err(|_| ApprovedPolicyError::PeerRefused)?;
            let entry = &self.source.entries[0];
            let snapshot = attested.snapshot();
            if snapshot.uid != entry.uid || snapshot.gid != entry.gid
                || snapshot.systemd_unit.as_deref() != Some(entry.unit.as_str())
                || snapshot.cgroup_v2_path != entry.cgroup
                || snapshot.executable_sha256 != entry.pin {
                return Err(ApprovedPolicyError::PeerRefused);
            }
            self.ensure_current()''',
    }
    for name, body in original_full.items():
        actual = source_gate.function(inventories[bridge], name)
        if source_gate.signature(' '.join(actual)) != source_gate.signature(body):
            raise ValueError('original full Source Owner Control body differs')
    # The supplemental lexer discards literals. Check the actual sole proc-root
    # comparison separately, after removing comments so a decoy cannot qualify.
    raw = texts[rooted]
    start = raw.index('pub(in crate::control_owner) fn current_for_service(')
    raw = raw[start:]
    raw = re.sub(r'/\*.*?\*/|//[^\n]*', '', raw, flags=re.DOTALL)
    proc = re.findall(r'self\.attestor\.proc_root\s*!=\s*Path::new\(("[^"\n]*")\)', raw)
    if proc != ['"/proc"']:
        raise ValueError('actual original default proc-root literal differs')
    raw = texts[bridge]
    start = raw.index('pub(crate) fn verify_control(')
    stop = raw.index('\n    }', start)
    raw = re.sub(r'/\*.*?\*/|//[^\n]*', '', raw[start:stop], flags=re.DOTALL)
    proc = re.findall(r'attested\.attestor\.proc_root\s*!=\s*Path::new\(("[^"\n]*")\)', raw)
    if proc != ['"/proc"']:
        raise ValueError('actual full Control default proc-root literal differs')
    wanted_calls = {
        'ControlPeerOwner::current_for_service': {
            'RootPathAttestedHandoffReceiver::from_service_control': {'path': rooted, 'count': 2},
            'AttestedHandoffReceiver::receive_service_control': {'path': packed, 'count': 1},
            'AttestedHandoffReceiver::ensure_service_current': {'path': packed, 'count': 1},
        },
        'AttestedHandoffReceiver::ensure_service_current': {
            'AttestedHandoffReceiver::receive_service_control': {'path': packed, 'count': 1},
        },
    }
    for helper, wanted in wanted_calls.items():
        method = helper.rsplit('::', 1)[1]
        actual = {}
        for path, inventory in inventories.items():
            for name, body in inventory['functions'].items():
                count = body.count(method)
                if count:
                    if name in actual:
                        raise ValueError('duplicate full service composition route')
                    actual[name] = {'path': path, 'count': count}
        source_gate.typed_equal(actual, wanted)
    # These orders are independent of EXPECTED's correspondence table: rebinding
    # every token digest and every configurable order cannot weaken an ingress.
    routes = {
        'RootPathAttestedHandoffReceiver::from_service_control': (rooted, [
            'session.ensure_current()', 'connection.consume_service_control_before',
            'session.original_owner_root_scope()', 'RetainedRootPath::new(custody, deadline)?',
            'path.current()?', 'session.control_policy()', 'ControlPeerOwner::admit',
            'owner.root_path = Some(path)', 'owner.current_for_service(session)?',
            'remaining(owner_pid, deadline)?', 'HandoffReceiver::from_control',
            'owner.current_for_service(session)?', 'owner: Some(owner)', 'cancelled: false',
        ]),
        'AttestedHandoffReceiver::receive_service_control': (packed, [
            'creator(self.owner_pid)?', 'session.ensure_current()',
            'self.ensure_service_current(session)?',
            'let wait = remaining(self.owner_pid, self.deadline)?',
            'receive_retained_service_control(wait)', 'transferred.into_parts()',
            'self.owner.take().ok_or(ControlOwnerError::ChannelRetired)?',
            'owner.current_for_service(session)?', 'owner.request_deadline(deadline)?',
            'ControlRequestCustody::from_control_peer', 'custody.retain_root_path',
            'retained.ensure_current()?', 'session.ensure_current()',
            'received.deadline()?', 'Ok(received)', 'self.retire()?', 'result',
        ]),
    }
    for name, (path, markers) in routes.items():
        body = source_gate.signature(' '.join(source_gate.function(inventories[path], name)))
        source_gate.ordered(body, [' '.join(source_gate.signature(marker)) for marker in markers], name)

_CONSUME_GUARD_MODULES = {'crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs': 'cbe3ff799af0be7dcc5cfa884e9ac43c494c7ce365ae5aa190ff5a9ca85674b6', 'crates/hepta-peer-attestation/src/approved_policy/service_policy.rs': '4eaa341de7bc90935b993fe0fe5df6a04d282d637e8fce2da52498eb4e4fe033', 'crates/hepta-peer-attestation/src/control_owner/control_request.rs': '4d4d6a80d2c6f93660b9ad09a1cefac43faa32177212d812c620315017a23eca', 'crates/hepta-peer-attestation/src/request_lease.rs': '54b80b2e94f4dc149d9af8f6e92815a2a8b88a9db987c34ec9a0b59d53850681', 'crates/hepta-peer-attestation/src/control_owner/retained_request.rs': 'fdac96f19d799e744236d0b49d9635e7a59e062018906ac88355c1b9be40eefc', 'crates/hepta-peer-attestation/src/control_owner.rs': '486e09d97822a20132765447edfd68b7c1f5c58b14e9b9984cfe4b496e530735', 'crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs': '8b92ac76f1ceda055be0f4a56a8a41e2d704229b24f337f65c028c443957eb35'}

def _consume_service_semantics(texts, inventories):
    """Whole owned consume composition independent of rebound catalog fields.

    This is finite Source correspondence. No proof escapes the private helper;
    Rust, exact deadline, latency and production remain independently pending.
    """
    bridge = 'crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs'
    for path, wanted in _CONSUME_GUARD_MODULES.items():
        if type(texts[path]) is not str or sha256(texts[path]) != wanted:
            raise ValueError('complete original consume guard module differs')
    name = 'ApprovedServiceReceivedRequest::consume_with_request_binding'
    header = 'pub fn consume_with_request_binding<T>(self, consumer: impl FnOnce(UnixStream, Instant, ControlRequestCustody, ApprovedServiceRetainedReporter, AttestedPeer, &str, ApprovedServiceRequestBinding) -> T) -> Result<T, ApprovedPolicyError>'
    if source_gate.signature(inventories[bridge]['public_api'][name]) != source_gate.signature(header):
        raise ValueError('original consume signature differs')
    helper = 'ApprovedServiceReceivedRequest::ensure_consume_current'
    helper_header = 'fn ensure_consume_current(&mut self) -> Result<(), ApprovedPolicyError>'
    if source_gate.signature(_private_header(texts[bridge], helper)) != source_gate.signature(helper_header):
        raise ValueError('private owned consume signature differs')
    # The generic private-header lexer omits plain pub, so visibility is also
    # checked independently at the actual declaration, before rebound API data.
    items = source_gate.tokens(texts[bridge])
    declarations = [i for i in range(len(items) - 1)
                    if items[i:i + 2] == ['fn', 'ensure_consume_current']]
    if len(declarations) != 1 or items[declarations[0] - 1] in {'pub', ')'}:
        raise ValueError('owned consume helper is not sole plain private declaration')
    bodies = {'ApprovedServiceReceivedRequest::consume_with_request_binding': '\n        self.binding.slot_current()?;\n        remaining(self.session.source.creator.pid, self.deadline)?;\n        let mut received = self;\n        received.ensure_consume_current()?;\n        let Self {\n            session,\n            stream,\n            deadline,\n            custody,\n            reporter,\n            attested,\n            binding,\n        } = received;\n        let principal = session.source.entries[1].principal.as_str();\n        let result = consumer(\n            stream, deadline, custody, reporter, attested, principal, binding,\n        );\n        // Consumer may legitimately retire action/report custody. Do not make\n        // those retired requests a prerequisite of persistent Source lifetime.\n        session.ensure_current()?;\n        remaining(session.source.creator.pid, deadline)?;\n        Ok(result)\n    ', 'ApprovedServiceReceivedRequest::ensure_consume_current': '\n        self.session.source.creator_current()?;\n        if !Arc::ptr_eq(&self.session, &self.reporter.session)\n            || !Arc::ptr_eq(&self.session, &self.binding.state.session)\n            || !Arc::ptr_eq(&self.reporter.slot, &self.binding.slot)\n            || self.deadline != self.reporter.deadline\n            || self.deadline != self.binding.state.deadline\n        {\n            return Err(ApprovedPolicyError::PeerRefused);\n        }\n        self.reporter.ensure_current()?;\n        let state = &self.binding.state;\n        let checked = (|| {\n            remaining(state.session.source.creator.pid, state.deadline)?;\n            if state.retired.load(Ordering::SeqCst) {\n                return Err(ApprovedPolicyError::PeerRefused);\n            }\n            state.control\n                .verify_pair_current(&self.binding.original.verifier())\n                .map_err(approval_error)?;\n            state.session.ensure_current()?;\n            remaining(state.session.source.creator.pid, state.deadline)\n        })();\n        if checked.is_err() {\n            state.retired.store(true, Ordering::SeqCst);\n        }\n        checked\n    ', 'ApprovedServiceRequestBinding::slot_current': '\n        self.state.session.source.creator_current()?;\n        if !Arc::ptr_eq(&self.slot.session, &self.state.session)\n            || !self.state.session.active.load(Ordering::SeqCst)\n        {\n            return Err(ApprovedPolicyError::PeerRefused);\n        }\n        Ok(())\n    ', 'ServiceRequestState::current': '\n        self.session.ensure_current()?;\n        let checked = (|| {\n            remaining(self.session.source.creator.pid, self.deadline)?;\n            if self.retired.load(Ordering::SeqCst) {\n                return Err(ApprovedPolicyError::PeerRefused);\n            }\n            self.control\n                .verify_pair_current(original)\n                .map_err(approval_error)?;\n            self.session.ensure_current()?;\n            remaining(self.session.source.creator.pid, self.deadline)\n        })();\n        if checked.is_err() {\n            self.retired.store(true, Ordering::SeqCst);\n        }\n        checked\n    ', 'ApprovedServiceRetainedReporter::ensure_current': '\n        self.session.source.creator_current()?;\n        if !Arc::ptr_eq(&self.slot.session, &self.session)\n            || !self.session.active.load(Ordering::SeqCst)\n        {\n            return Err(ApprovedPolicyError::PeerRefused);\n        }\n        let checked = (|| {\n            self.session.ensure_current()?;\n            remaining(self.session.source.creator.pid, self.deadline)?;\n            let deadline = self\n                .retained\n                .as_mut()\n                .ok_or(ApprovedPolicyError::PeerRefused)?\n                .ensure_current()\n                .map_err(approval_error)?;\n            if deadline != self.deadline {\n                return Err(ApprovedPolicyError::PeerRefused);\n            }\n            self.session.ensure_current()?;\n            remaining(self.session.source.creator.pid, deadline)?;\n            Ok(deadline)\n        })();\n        if checked.is_err() {\n            self.retained.take();\n        }\n        checked\n    ', 'ServiceSessionState::ensure_current': '\n        self.source.creator_current()?;\n        self.owner.ensure_current()?;\n        self.source.inspect()\n    '}
    for name, body in bodies.items():
        actual = source_gate.function(inventories[bridge], name)
        if source_gate.signature(' '.join(actual)) != source_gate.signature(body):
            raise ValueError('complete consume slot pair reporter Source Owner guard differs')
    opaque = {'ApprovedServiceRequests': 'original_owner:Option<ApprovedServiceOwnerBinding>,session:Arc<ServiceSessionState>,', 'ApprovedServiceSessionVerifier': 'session:Arc<ServiceSessionState>,', 'ApprovedServiceControlReceiver': 'session:Arc<ServiceSessionState>,receiver:Option<RootPathAttestedHandoffReceiver>,slot:Arc<ServiceRequestSlot>,original_control_deadline:Instant,', 'ApprovedServiceReceivedRequest': 'session:Arc<ServiceSessionState>,stream:UnixStream,deadline:Instant,custody:ControlRequestCustody,reporter:ApprovedServiceRetainedReporter,attested:AttestedPeer,binding:ApprovedServiceRequestBinding,', 'ApprovedServiceRequestBinding': 'state:Arc<ServiceRequestState>,original:PeerRequestCustody,slot:Arc<ServiceRequestSlot>,', 'ApprovedServiceRequestVerifier': 'state:Arc<ServiceRequestState>,original:PeerRequestVerifier,', 'ApprovedServiceRetainedReporter': 'session:Arc<ServiceSessionState>,retained:Option<AttestedRetainedReceiver>,deadline:Instant,slot:Arc<ServiceRequestSlot>,'}
    for name, fields in opaque.items():
        if source_gate.signature(' '.join(inventories[bridge]['types'][name]['body'])) != source_gate.signature(fields):
            raise ValueError('original consume private proof fields differ')
    calls = {}
    for path, inventory in inventories.items():
        for name, body in inventory['functions'].items():
            count = body.count('ensure_consume_current')
            if count:
                calls[(path, name)] = count
    if calls != {(bridge, 'ApprovedServiceReceivedRequest::consume_with_request_binding'): 1}:
        raise ValueError('sole owned consume helper call differs')
    # Independently retain the entire checked/error-retirement tail of the
    # unchanged full State.current, with only the owned variable mapping.
    actual = source_gate.signature(' '.join(inventories[bridge]['functions'][helper]))
    marker = source_gate.signature('let checked = (||')
    start = next(i for i in range(len(actual) - len(marker) + 1)
                 if actual[i:i + len(marker)] == marker)
    tail = actual[start:]
    argument = source_gate.signature('&self.binding.original.verifier()')
    hits = [i for i in range(len(tail) - len(argument) + 1)
            if tail[i:i + len(argument)] == argument]
    if len(hits) != 1:
        raise ValueError('same original Agent verifier argument differs')
    i = hits[0]
    tail = tail[:i] + ['original'] + tail[i + len(argument):]
    tail = ['self' if token == 'state' else token for token in tail]
    parent = source_gate.signature(' '.join(inventories[bridge]['functions']['ServiceRequestState::current']))
    first = source_gate.signature('self.session.ensure_current()?;')
    if parent[:len(first)] != first or tail != parent[len(first):]:
        raise ValueError('whole original pair checked and retirement tail differs')


def inventory_and_orders(texts):
    inventories = {path: source_gate.rust_inventory(texts[path])
                   for path in EXPECTED['whole_production_source_sha256']}
    public = {}
    types = {}
    for path, inventory in inventories.items():
        for name, signature in inventory['public_api'].items():
            if name in public:
                raise ValueError('duplicate public service method')
            public[name] = signature
        for name, value in inventory['types'].items():
            if value['public']:
                if name in types:
                    raise ValueError('duplicate public service opaque type')
                types[name] = value
    if set(public) != set(EXPECTED['public_api']) or set(types) != set(EXPECTED['opaque_types']):
        raise ValueError('complete service method/type inventory differs')
    for name, wanted in EXPECTED['public_api'].items():
        if source_gate.signature(public[name]) != source_gate.signature(wanted):
            raise ValueError('service public signature differs')
    for name, fields in EXPECTED['opaque_types'].items():
        body = types[name]['body']
        if 'pub' in body or source_gate.signature(' '.join(body)) != source_gate.signature(fields):
            raise ValueError('service proof fields are externally replaceable')
    # Keep the old closed six-helper table and check the new scope independently.
    if len(EXPECTED['private_helper_inventory']) != 6 or set(EXPECTED['denial_scope_helper_inventory']) != {
            'ServiceSessionState::original_owner_root_scope'}:
        raise ValueError('closed six plus one service helper tables differ')
    wanted = dict(EXPECTED['private_helper_inventory'])
    for name, rule in EXPECTED['denial_scope_helper_inventory'].items():
        if name in wanted:
            raise ValueError('duplicate service scope helper declaration')
        wanted[name] = rule
    for name, rule in EXPECTED['composed_service_helper_inventory'].items():
        if name in wanted:
            raise ValueError('duplicate full service composition helper')
        wanted[name] = rule
    actual_helpers = {}
    for path in EXPECTED['whole_production_source_sha256']:
        for name, header in _restricted_helpers(texts[path]).items():
            if name in actual_helpers:
                raise ValueError('duplicate actual service helper')
            actual_helpers[name] = (path, header)
    if len(actual_helpers) != 9 or set(actual_helpers) != set(wanted):
        raise ValueError('complete nine restricted service helper closure differs')
    for name, rule in wanted.items():
        path, actual = actual_helpers[name]
        if path != rule['path'] or source_gate.signature(actual) != source_gate.signature(rule['signature']):
            raise ValueError('private service helper signature differs')
        body = source_gate.function(inventories[path], name)
        full = source_gate.signature(actual) + body
        if hashlib.sha256(' '.join(full).encode()).hexdigest() != EXPECTED['private_helper_full_tokens_sha256'][name]:
            raise ValueError('whole nine-helper token correspondence differs')
    if set(EXPECTED['private_helper_full_tokens_sha256']) != set(wanted):
        raise ValueError('complete nine helper token inventory differs')
    actual_bodies = {path: {name: hashlib.sha256(' '.join(body).encode()).hexdigest()
                           for name, body in inventory['functions'].items()}
                     for path, inventory in inventories.items()}
    source_gate.typed_equal(actual_bodies, EXPECTED['all_function_body_tokens_sha256'])
    actual_scope_calls = {}
    for path, inventory in inventories.items():
        for name, body in inventory['functions'].items():
            count = body.count('original_owner_root_scope')
            if count:
                if name in actual_scope_calls:
                    raise ValueError('duplicate denial-only scope route')
                actual_scope_calls[name] = {'path': path, 'count': count}
    source_gate.typed_equal(actual_scope_calls, EXPECTED['denial_scope_call_inventory'])
    _composed_service_semantics(texts, inventories)
    _consume_service_semantics(texts, inventories)
    for name, rule in EXPECTED['effect_orders'].items():
        body = source_gate.signature(' '.join(source_gate.function(inventories[rule['path']], name)))
        markers = [' '.join(source_gate.signature(marker)) for marker in rule['markers']]
        source_gate.ordered(body, markers, name)


def check(contract, texts):
    source_gate.typed_equal(contract, EXPECTED)
    for path, rule in EXPECTED['original_source_inverse'].items():
        if not _pinned(texts[path], rule, 'complete'):
            raise ValueError('current service profile is detached or altered')
        restored = parent_source(path, texts[path])
        if not _pinned(restored, rule):
            raise ValueError('current service profile does not restore its parent')
    for group in ['whole_production_source_sha256', 'preserved_source_sha256', 'kernel_source_sha256']:
        for path, wanted in EXPECTED[group].items():
            if type(texts[path]) is not str or sha256(texts[path]) != wanted:
                raise ValueError('whole service bridge source differs')
    inventory_and_orders(texts)


def validate(root=ROOT):
    check(source_gate.load(root / CONTRACT), inputs(root))


def main():
    try:
        validate()
    except (OSError, ValueError, KeyError, UnicodeError):
        print('SOURCE_INVALID approved service original request bridge', file=sys.stderr)
        return 1
    print(json.dumps({'source_contract': 'PASS', 'scope': 'P1_SOURCE_ONLY',
                      'public_methods': 18, 'opaque_types': 7,
                      'actual_kernel': False, 'native_health': False,
                      'installed': False, 'production_ready': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
