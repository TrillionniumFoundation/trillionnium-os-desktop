#!/usr/bin/env python3
"""Finite opt-in Control readiness correspondence, not runtime qualification.

Inverse transfer is exact, bounded and denial-only. Mandatory actual-profile
validation separately rejects any source or contract not in this finite map.
Legacy EXPECTED values and old tests remain unchanged. No FD or clock enters
this checker as live authority, and hashes never replace default-proc checks.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

try:
    from . import verify_approved_native_startup as composition
except ImportError:
    import verify_approved_native_startup as composition

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/retained-control-readiness.v1.json"
TRANSPORT = "crates/hepta-agent-transport/src/accepted_handoff.rs"
RETAINED = "crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs"
TRANSPORT_READINESS = "crates/hepta-agent-transport/src/accepted_handoff/retained_control/readiness.rs"
PEER_READINESS = "crates/hepta-peer-attestation/src/control_owner/retained_request/readiness.rs"
OWNER = "crates/hepta-peer-attestation/src/control_owner.rs"
REQUEST = "crates/hepta-peer-attestation/src/control_owner/retained_request.rs"
POLICY = "crates/hepta-peer-attestation/src/approved_policy.rs"
MONITOR = "apps/hepta-browserd/src/product_dispatch/product_control_wait.rs"
PRODUCT = "apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs"
CARGO = "apps/hepta-browserd/Cargo.toml"
SENDER_SOURCE_SHA256 = {'crates/hepta-agent-transport/src/accepted_handoff/retained_control/readiness.rs': '4f8fbaa6c940bff8eb471d255dc54096462dac84352d0fef82e2870eef060b48', 'crates/hepta-peer-attestation/src/control_owner/retained_request/readiness.rs': 'f67fde7fc98aadaf66c07589aca61593e1bcee6353a70ca18011f04325ef942c', 'crates/hepta-agent-transport/src/accepted_handoff/retained_control/readiness_tests.rs': '7fa2c5aff2235ce62af7d3f0e5bfb3984a267d37f74403ccabfce7e985d3e68d', 'apps/hepta-browserd/tests/control_readiness_kernel.rs': 'a127d33bfe1775cfb4762e6001c0a5a470ede2d8fd414c21748d06e36c49eb45'}
EXPECTED = {'schema': 'trillionnium.desktop.retained-control-readiness.v1',
 'default_activation': False,
 'parent_source_commit': 'c875ed3e3c6c876b716f415f7b766992d48e1572',
 'status': 'SOURCE_CANDIDATE_NATIVE_REQUALIFICATION_PENDING',
 'authority': {'caller_fd_deadline_snapshot_or_permit': False,
               'control_identity_creation_time_capture': True,
               'identity_is_agent_socket_cookie': False,
               'idle_result_grants_action_or_report_permission': False,
               'idle_reporting_owner_independent_of_action_revocation': True,
               'idle_full_executable_hash': False,
               'cross_call_executable_cache': False,
               'full_ready_packet_and_terminal_report_checks': True},
 'lifetime': {'accepted_seconds_maximum': 20,
              'native_seconds_maximum': 5,
              'service_health_seconds': 60,
              'original_instant_extended': False},
 'public_api': {'PendingHandoffSender::report_readable_now': 'pub fn report_readable_now(&mut self) -> Result<bool, HandoffError>',
                'AttestedPendingHandoff::poll_retirement_when_readable': 'pub fn poll_retirement_when_readable(&mut self) -> Result<Option<PeerReportedRetirement>, ControlOwnerError>',
                'PendingHandoffReceiver::cancel_readable_now': 'pub fn cancel_readable_now(&mut self) -> '
                                                               'Result<bool, HandoffError>',
                'AttestedRetainedReceiver::poll_cancel_when_readable': 'pub fn '
                                                                       'poll_cancel_when_readable(&mut self) '
                                                                       '-> Result<bool, ControlOwnerError>'},
 'actual_source_sha256': {'apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs': '00c9c70bc516d2b78253f7b5502defd3e279ad5a1d4fd77ea949aa4784708745',
                          'apps/hepta-browserd/src/product_dispatch/product_control_wait.rs': 'b2aa3e94e15030aa5d814a0e802e34ccce213efb6e7120736947575583d8c1db',
                          'crates/hepta-agent-transport/src/accepted_handoff.rs': '988ab3003afd3f4c4381b989b7581376c970e30af958470e0f47561cb4eea84f',
                          'crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs': 'c011fd826aacdc21a235b301b8a3fb4b8d16258cb652030bd9647a049040a4cb',
                          'crates/hepta-peer-attestation/src/approved_policy.rs': 'dfb42050e73dd7f1fc6ef46aa6b839b4bc3c1c3f201ac47c5106acaada27815e',
                          'crates/hepta-peer-attestation/src/control_owner.rs': '486e09d97822a20132765447edfd68b7c1f5c58b14e9b9984cfe4b496e530735',
                          'crates/hepta-peer-attestation/src/control_owner/retained_request.rs': '433a0226e21135d21e6337d3adc6928ae53ed00cd4523aab687745142215aceb',
                          'tools/verify_approved_composition_scope.py': '7d7599a5cdd6aa27a0148d931f39677ad8851fb6d38b6e2bb973e893e625e4e8',
                          'tools/verify_approved_constructor_route.py': '50f2c13bc28324cfabc217ea1290cb9c511a5f885437c0ed890d3563020ca366',
                          'tools/verify_approved_native_startup.py': 'e86ac78e4b35e9856f545c96b6cdc25d9b4b84ea3317aeeb6bc9506199f85b38',
                          'apps/hepta-browserd/tests/control_readiness_kernel.rs': 'a127d33bfe1775cfb4762e6001c0a5a470ede2d8fd414c21748d06e36c49eb45',
                          'crates/hepta-agent-transport/src/accepted_handoff/retained_control/readiness_tests.rs': '7fa2c5aff2235ce62af7d3f0e5bfb3984a267d37f74403ccabfce7e985d3e68d',
                          'crates/hepta-agent-transport/src/accepted_handoff/retained_control/readiness.rs': '4f8fbaa6c940bff8eb471d255dc54096462dac84352d0fef82e2870eef060b48',
                          'crates/hepta-peer-attestation/src/control_owner/retained_request/readiness.rs': 'f67fde7fc98aadaf66c07589aca61593e1bcee6353a70ca18011f04325ef942c',
                          'apps/hepta-browserd/Cargo.toml': '7871b88e3211d5a3348af124286d096af99be30143797ed8bb9a5cb231c20b0d'},
 'parent_source_sha256': {'apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs': '39c227ccba6bdf249402cf1f48cc8e2e09e7bc8e74067f619b1a134275c4aea5',
                          'apps/hepta-browserd/src/product_dispatch/product_control_wait.rs': 'd87efdb8cdd22e38cca90aae0f776f823478bf3b2045482c81ba608eb79a019f',
                          'crates/hepta-agent-transport/src/accepted_handoff.rs': '2d1af7577246ba17911db701f0b4c55512734c2de25dbc0df24889fa6248842e',
                          'crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs': 'f45d4dbbb254522ea043ad42e4fbe7df33b7e1a2f898d6d6c911d8cc203c8e60',
                          'crates/hepta-peer-attestation/src/approved_policy.rs': '0a6a079336ad842bc55c34fe3930707ece098182bd976e78c2dfb21e18d87882',
                          'crates/hepta-peer-attestation/src/control_owner.rs': 'a5d143ccbf05ea6cec8747bff6a3df847f88a2eff0a8d0d0f34b9c2057ee55dd',
                          'crates/hepta-peer-attestation/src/control_owner/retained_request.rs': 'f6f70998cf1b2b1e20857263a07d3101cf5f67ca4fcaa930b88a527445bdf754',
                          'tools/verify_approved_composition_scope.py': '58b7802b64f8ef615e3745c999326d18fdac4a0dad5e0263d5009a321bc2fb29',
                          'tools/verify_approved_constructor_route.py': 'ec669a4c8af80ffea07751edc83a32e2ed415e51c7c00351c6525bb960957bac',
                          'tools/verify_approved_native_startup.py': 'ddc1baa5bf716868e9abbe251f97547bdd28f26c1cde8d75830fbfb61ccbe048',
                          'apps/hepta-browserd/Cargo.toml': '8eb40509d8f83d96534811429cdbe6d3e6db3e0d97af3bf23b2843a76e847076'},
 'preserved_sha256': {'Cargo.toml': 'dc90e547920d9559671d09599bc2b0df55f2c1a73b3c3b7eb015667445d56814',
                      'Cargo.lock': 'fde6ce60b8b1564562efc6a15848dda3a07bf6d7a9b51e3322d0c42d25e356a2',
                      'rust-toolchain.toml': '8bc51ecab82415fddd8489604f2424e137d71856e7f65cbdcfaa48850d794b46',
                      'tests/test_retained_control_terminal.py': 'd2f174fafb41a5e039436c7ed8bdd042eeb5e3833c66935ff324ab1d5495b176',
                      'contracts/retained-control-terminal.v1.json': 'a5c8885cf6431685e69fbefc3afa8f9d21a46dd2dac2dfef991283db467095ac',
                      'tests/test_approved_composition_scope.py': '40d631f98f3119236a3443521919602fd803a551f0a9d603f7f69531a4a22a21',
                      'tests/test_approved_constructor_route.py': '859eb71a27d7a01f6d21faeda6dea84626df178229141738e44410184677df73',
                      'tests/test_approved_native_startup.py': 'eb032b474dca0bc11333f64c84c91ef795aaeb3e4301b517e225cf79410919d7',
                      'contracts/approved-composition-scope.v1.json': '5f9738e8ccae72b8492f38b2dec8c7556863960addffdd5e8308da74f9a18d77',
                      'contracts/approved-constructor-route.v1.json': 'c1ca56e20fca6093be4cdbeec7c3afd6c3bc26cd059061af6f4fb4a915c158d2',
                      'contracts/approved-native-startup.v1.json': '3d918519791af864bcfa4a423f14039e024eb1e14eaa7d8686f8a95a0d4ebe7e',
                      'apps/hepta-browserd/tests/approved_request_binding_kernel.rs': 'ec8eb609f0e41d95ab95e8d2b27fb0766d7005a5b13291c1e45329576bcb76fb',
                      'apps/hepta-browserd/tests/approved_native_startup_kernel.rs': '0aed2dfaabfd529ddfb21ca1791091c864ad79b4787e42bba23621f625fec365',
                      'apps/hepta-browserd/tests/configured_retained_bootstrap_kernel.rs': 'b8417a869e41b9dbf21028613ce754525f6a54aa9fdee90c5358c42afbb10118',
                      'crates/hepta-agent-transport/tests/retained_control_kernel.rs': 'db40ec626b0c6128a5a07f38291cdba6a34afed00647dc46dd11744268aba6c6',
                      'apps/hepta-browserd/tests/product_terminal_wait_kernel.rs': '1e94b3cc7243e7b6ee34373e5a5b368ba846ebb88e36c0cd85b5505f72f2d9cd',
                      'experiments/servo-product-owner/src/approved_test_support.rs': '19e1e5269027ab4b81fa4a5ac41517dd6dfea5665141486297f351bf01e4745d',
                      'experiments/servo-product-owner/src/approved_connected_tests.rs': '1825c758d95b46958ec71edeb747782e287df40019f5850a5439bc80deddc442',
                      'experiments/servo-product-owner/src/approved_startup.rs': '582242f4826110a81f26fdec3ad497a2eb1dd76fb20d1e7601d95559b3296b25',
                      'experiments/servo-product-owner/src/native_owner.rs': '5b9d5a3116617f1e4d5f973464e3f5e4c82466f40a98f870f272381b6be685e1',
                      'experiments/servo-product-owner/src/connected_tests.rs': 'e22417fdccfadfb0eccaa7d253a7af9ed93f210d739cd16e32e952c29ccb7f5f',
                      'tools/prepare_approved_native_startup.py': '46ceb77d114f9ada6bec73377d0968c896a93c16c4f1e2caeff8412e3864c061',
                      'tools/prepare_native_product_owner.py': '5143645a7e7bcfb10cc8813787f9f73e02f805cd15de7ccbc91dfdc1bf3af0a7',
                      '.github/workflows/g2-approved-native-startup.yml': '872e6157fb2fba02a088a2d9e209652c8039b635e1a045a0d3fb5161b0d4756a',
                      'manifests/servo.lock.json': 'a64fc7f64926d0a3726ce50551aa879065bcfac285caa553494c7be59ad953f4',
                      'manifests/rust-toolchain.lock.json': '417f63317d52a3f4cbbd4160966e50a3b17824e096c823ce499481d866c319d7',
                      'manifests/cargo-external-allowlist.json': '65cdc01e7cc6de76827badbb9f4500119fdb12a98147d750b6d167f60c6a17ed'},
 'legacy_public_api': {'RemoteRetirementReport::new': 'pub fn new( state: RemoteTerminalState, '
                                                      'request_sha256: [u8; 32], record_sha256: [u8; 32], ) '
                                                      '-> Result<Self, HandoffError>',
                       'RemoteRetirementReport::state': 'pub const fn state(&self) -> RemoteTerminalState',
                       'RemoteRetirementReport::request_sha256': 'pub const fn request_sha256(&self) -> [u8; '
                                                                 '32]',
                       'RemoteRetirementReport::record_sha256': 'pub const fn record_sha256(&self) -> [u8; '
                                                                '32]',
                       'PendingHandoffSender::ensure_current': 'pub fn ensure_current(&mut self) -> '
                                                               'Result<Instant, HandoffError>',
                       'PendingHandoffSender::deadline': 'pub fn deadline(&mut self) -> Result<Instant, '
                                                         'HandoffError>',
                       'PendingHandoffSender::request_cancel': 'pub fn request_cancel(&mut self) -> '
                                                               'Result<(), HandoffError>',
                       'PendingHandoffSender::wait_report': 'pub fn wait_report(&mut self) -> '
                                                            'Result<RemoteRetirementReport, HandoffError>',
                       'PendingHandoffSender::poll_report': 'pub fn poll_report(&mut self) -> '
                                                            'Result<Option<RemoteRetirementReport>, '
                                                            'HandoffError>',
                       'PendingHandoffReceiver::ensure_current': 'pub fn ensure_current(&mut self) -> '
                                                                 'Result<Instant, HandoffError>',
                       'PendingHandoffReceiver::deadline': 'pub fn deadline(&mut self) -> Result<Instant, '
                                                           'HandoffError>',
                       'PendingHandoffReceiver::poll_cancel': 'pub fn poll_cancel(&mut self) -> Result<bool, '
                                                              'HandoffError>',
                       'PendingHandoffReceiver::send_report': 'pub fn send_report(&mut self, report: '
                                                              'RemoteRetirementReport) -> Result<(), '
                                                              'HandoffError>',
                       'RetainedReceivedAcceptedStream::into_parts': 'pub fn into_parts( mut self, ) -> '
                                                                     'Result<(ReceivedAcceptedStream, '
                                                                     'PendingHandoffReceiver), HandoffError>',
                       'HandoffSender::send_retained': 'pub fn send_retained( mut self, custody: '
                                                       'AcceptedStreamCustody, ) -> '
                                                       'Result<PendingHandoffSender, HandoffError>',
                       'HandoffReceiver::receive_retained': 'pub fn receive_retained( mut self, wait_budget: '
                                                            'std::time::Duration, ) -> '
                                                            'Result<RetainedReceivedAcceptedStream, '
                                                            'HandoffError>',
                       'PeerReportedRetirement::state': 'pub fn state(&self) -> RemoteTerminalState',
                       'PeerReportedRetirement::request_sha256': 'pub fn request_sha256(&self) -> [u8; 32]',
                       'PeerReportedRetirement::record_sha256': 'pub fn record_sha256(&self) -> [u8; 32]',
                       'AttestedPendingHandoff::ensure_current': 'pub fn ensure_current(&mut self) -> '
                                                                 'Result<Instant, ControlOwnerError>',
                       'AttestedPendingHandoff::request_cancel': 'pub fn request_cancel(&mut self) -> '
                                                                 'Result<(), ControlOwnerError>',
                       'AttestedPendingHandoff::wait_retirement': 'pub fn wait_retirement(&mut self) -> '
                                                                  'Result<PeerReportedRetirement, '
                                                                  'ControlOwnerError>',
                       'AttestedPendingHandoff::poll_retirement': 'pub fn poll_retirement(&mut self) -> '
                                                                  'Result<Option<PeerReportedRetirement>, '
                                                                  'ControlOwnerError>',
                       'AttestedRetainedReceiver::ensure_current': 'pub fn ensure_current(&mut self) -> '
                                                                   'Result<Instant, ControlOwnerError>',
                       'AttestedRetainedReceiver::poll_cancel': 'pub fn poll_cancel(&mut self) -> '
                                                                'Result<bool, ControlOwnerError>',
                       'AttestedRetainedReceiver::send_remote_report': 'pub fn send_remote_report( &mut '
                                                                       'self, report: '
                                                                       'RemoteRetirementReport, ) -> '
                                                                       'Result<(), ControlOwnerError>',
                       'ControlRetainedAcceptedStream::deadline': 'pub fn deadline(&self) -> Result<Instant, '
                                                                  'ControlOwnerError>',
                       'ControlRetainedAcceptedStream::consume_before': 'pub fn consume_before<T>( mut self, '
                                                                        'consumer: impl FnOnce(UnixStream, '
                                                                        'Instant, ControlRequestCustody, '
                                                                        'AttestedRetainedReceiver) -> T, ) '
                                                                        '-> Result<T, ControlOwnerError>',
                       'AttestedHandoffSender::send_retained': 'pub fn send_retained(&mut self) -> '
                                                               'Result<AttestedPendingHandoff, '
                                                               'ControlOwnerError>',
                       'AttestedHandoffReceiver::receive_retained_custodied': 'pub fn '
                                                                              'receive_retained_custodied( '
                                                                              '&mut self, ) -> '
                                                                              'Result<ControlRetainedAcceptedStream, '
                                                                              'ControlOwnerError>',
                       'RetainedProductConnection::from_control_retained_received': 'pub fn '
                                                                                    'from_control_retained_received( '
                                                                                    'received: '
                                                                                    'ControlRetainedAcceptedStream, '
                                                                                    'policy: '
                                                                                    '&PeerRuntimePolicy, '
                                                                                    'approved_executable_sha256: '
                                                                                    '&str, ) -> '
                                                                                    'Result<(Self, '
                                                                                    'ProductControlMonitor), '
                                                                                    'ProductDispatchError>',
                       'RetainedProductConnection::deadline': 'pub fn deadline(&self) -> Result<Instant, '
                                                              'ProductDispatchError>',
                       'RetainedProductConnection::cancellation': 'pub fn cancellation(&self) -> '
                                                                  'Result<ProductConnectionCancellation, '
                                                                  'ProductDispatchError>',
                       'ProductControlMonitor::run': 'pub fn run(mut self) -> '
                                                     'Result<ProductControlMonitorOutcome, '
                                                     'ProductDispatchError>',
                       'ProductRequestCoordinator::from_retained_connection': 'pub fn '
                                                                              'from_retained_connection( '
                                                                              'principal: TaskFlowPrincipal, '
                                                                              'bootstrap: '
                                                                              '&RetainedProductConnection, '
                                                                              'endpoint: '
                                                                              'ServoRuntimeEndpoint, '
                                                                              'journal: ReceiptJournal, '
                                                                              'image_id: String, '
                                                                              'restart_policy: '
                                                                              'RestartPolicy, ) -> '
                                                                              'Result<Self, '
                                                                              'ProductDispatchError>',
                       'ProductRequestCoordinator::serve_retained_connection': 'pub fn '
                                                                               'serve_retained_connection( '
                                                                               '&mut self, mut connection: '
                                                                               'RetainedProductConnection, ) '
                                                                               '-> Result<ServiceEvidence, '
                                                                               'ProductDispatchError>'},
 'qualification': {'source_correspondence_only': True,
                   'transport_default_parallel_test_groups': 20,
                   'actual_default_proc_host_groups': 9,
                   'sender_default_proc_host_groups': 13,
                   'sender_default_proc_host_execution_proven': False,
                   'sender_caller_adopted': False,
                   'actual_host_execution_not_proven_by_contract': True,
                   'native_original_six_and_budgets_preserved': True,
                   'measured_speedup_claim': False,
                   'installed_activation': False,
                   'production_ready': False,
                   'substituted_fd_cleanup_guarantee': False,
                   'arbitrary_concurrent_same_process_fd_tampering_safe': False}}
TRANSFER = {'apps/hepta-browserd/src/product_dispatch/product_approved_policy.rs': [{'actual': '//! its legacy module; '
                                                                                    'this additive entry '
                                                                                    'supplies no public '
                                                                                    'principal grant.\n'
                                                                                    '\n'
                                                                                    'use '
                                                                                    'super::product_control_wait::{\n'
                                                                                    '    CancelPollProfile, '
                                                                                    'ProductControlMonitor, '
                                                                                    'RetainedProductConnection,\n'
                                                                                    '};\n'
                                                                                    'use super::*;\n'
                                                                                    'use '
                                                                                    'hepta_peer_attestation::ControlRetainedAcceptedStream;\n',
                                                                          'parent': '//! its legacy module; '
                                                                                    'this additive entry '
                                                                                    'supplies no public '
                                                                                    'principal grant.\n'
                                                                                    '\n'
                                                                                    'use '
                                                                                    'super::product_control_wait::{ProductControlMonitor, '
                                                                                    'RetainedProductConnection};\n'
                                                                                    'use super::*;\n'
                                                                                    'use '
                                                                                    'hepta_peer_attestation::ControlRetainedAcceptedStream;\n'},
                                                                         {'actual': '                            '
                                                                                    'receiver: '
                                                                                    'Some(receiver),\n'
                                                                                    '                            '
                                                                                    'finished: false,\n'
                                                                                    '                            '
                                                                                    'cancel_profile: '
                                                                                    'CancelPollProfile::ApprovedReadinessV1,\n'
                                                                                    '                        '
                                                                                    '},\n'
                                                                                    '                    '
                                                                                    '))\n',
                                                                          'parent': '                            '
                                                                                    'receiver: '
                                                                                    'Some(receiver),\n'
                                                                                    '                            '
                                                                                    'finished: false,\n'
                                                                                    '                        '
                                                                                    '},\n'
                                                                                    '                    '
                                                                                    '))\n'}],
 'apps/hepta-browserd/src/product_dispatch/product_control_wait.rs': [{'actual': '                        '
                                                                                 'receiver: Some(receiver),\n'
                                                                                 '                        '
                                                                                 'finished: false,\n'
                                                                                 '                        '
                                                                                 'cancel_profile: '
                                                                                 'CancelPollProfile::FullV1,\n'
                                                                                 '                    },\n'
                                                                                 '                ))\n',
                                                                       'parent': '                        '
                                                                                 'receiver: Some(receiver),\n'
                                                                                 '                        '
                                                                                 'finished: false,\n'
                                                                                 '                    },\n'
                                                                                 '                ))\n'},
                                                                      {'actual': '    pub(super) receiver: '
                                                                                 'Option<mpsc::Receiver<MonitorMessage>>,\n'
                                                                                 '    pub(super) finished: '
                                                                                 'bool,\n'
                                                                                 '    pub(super) '
                                                                                 'cancel_profile: '
                                                                                 'CancelPollProfile,\n'
                                                                                 '}\n'
                                                                                 'pub(super) enum '
                                                                                 'CancelPollProfile {\n'
                                                                                 '    FullV1,\n'
                                                                                 '    ApprovedReadinessV1,\n'
                                                                                 '}\n'
                                                                                 'impl ProductControlMonitor '
                                                                                 '{\n',
                                                                       'parent': '    pub(super) receiver: '
                                                                                 'Option<mpsc::Receiver<MonitorMessage>>,\n'
                                                                                 '    pub(super) finished: '
                                                                                 'bool,\n'
                                                                                 '}\n'
                                                                                 'impl ProductControlMonitor '
                                                                                 '{\n'},
                                                                      {'actual': '}\n'
                                                                                 'impl ProductControlMonitor '
                                                                                 '{\n'
                                                                                 '    fn '
                                                                                 'poll_original_cancel(&mut '
                                                                                 'self) -> Result<bool, '
                                                                                 'ProductDispatchError> {\n'
                                                                                 '        if self.owner_pid '
                                                                                 '!= std::process::id() {\n'
                                                                                 '            return '
                                                                                 'Err(ProductDispatchError::PeerRefused);\n'
                                                                                 '        }\n'
                                                                                 '        let retained = '
                                                                                 'self.retained.as_mut().ok_or(ProductDispatchError::Closed)?;\n'
                                                                                 '        match '
                                                                                 'self.cancel_profile {\n'
                                                                                 '            '
                                                                                 'CancelPollProfile::FullV1 '
                                                                                 '=> '
                                                                                 'retained.poll_cancel().map_err(control_error),\n'
                                                                                 '            '
                                                                                 'CancelPollProfile::ApprovedReadinessV1 '
                                                                                 '=> {\n'
                                                                                 '                '
                                                                                 'retained.poll_cancel_when_readable().map_err(control_error)\n'
                                                                                 '            }\n'
                                                                                 '        }\n'
                                                                                 '    }\n'
                                                                                 '    pub fn run(mut self) '
                                                                                 '-> '
                                                                                 'Result<ProductControlMonitorOutcome, '
                                                                                 'ProductDispatchError> {\n'
                                                                                 '        if self.owner_pid '
                                                                                 '!= std::process::id() {\n',
                                                                       'parent': '}\n'
                                                                                 'impl ProductControlMonitor '
                                                                                 '{\n'
                                                                                 '    pub fn run(mut self) '
                                                                                 '-> '
                                                                                 'Result<ProductControlMonitorOutcome, '
                                                                                 'ProductDispatchError> {\n'
                                                                                 '        if self.owner_pid '
                                                                                 '!= std::process::id() {\n'},
                                                                      {'actual': '        loop {\n'
                                                                                 '            '
                                                                                 'product_time_remaining(self.deadline)?;\n'
                                                                                 '            if '
                                                                                 'self.poll_original_cancel()? '
                                                                                 '{\n'
                                                                                 '                '
                                                                                 'self.cancellation.cancel();\n'
                                                                                 '            }\n',
                                                                       'parent': '        loop {\n'
                                                                                 '            '
                                                                                 'product_time_remaining(self.deadline)?;\n'
                                                                                 '            let retained = '
                                                                                 'self.retained.as_mut().ok_or(ProductDispatchError::Closed)?;\n'
                                                                                 '            // poll_cancel '
                                                                                 'performs the complete '
                                                                                 'current check before and '
                                                                                 'after\n'
                                                                                 '            // its own '
                                                                                 'channel observation, '
                                                                                 'retiring the same scope on '
                                                                                 'failure.\n'
                                                                                 '            if '
                                                                                 'retained.poll_cancel().map_err(control_error)? '
                                                                                 '{\n'
                                                                                 '                '
                                                                                 'self.cancellation.cancel();\n'
                                                                                 '            }\n'},
                                                                      {'actual': '                '
                                                                                 'self.cancellation.cancel();\n'
                                                                                 '            }\n'
                                                                                 '            let retained = '
                                                                                 'self.retained.as_mut().ok_or(ProductDispatchError::Closed)?;\n'
                                                                                 '            let wait = '
                                                                                 'product_time_remaining(self.deadline)?.min(Duration::from_millis(5));\n'
                                                                                 '            if '
                                                                                 'self.owner_pid != '
                                                                                 'std::process::id() {\n',
                                                                       'parent': '                '
                                                                                 'self.cancellation.cancel();\n'
                                                                                 '            }\n'
                                                                                 '            let wait = '
                                                                                 'product_time_remaining(self.deadline)?.min(Duration::from_millis(5));\n'
                                                                                 '            if '
                                                                                 'self.owner_pid != '
                                                                                 'std::process::id() {\n'}],
 'crates/hepta-agent-transport/src/accepted_handoff.rs': [{'actual': '    device: u64,\n'
                                                                     '    inode: u64,\n'
                                                                     '}\n'
                                                                     '\n'
                                                                     '// This is the Control endpoint '
                                                                     'captured at construction, not the '
                                                                     'submitted\n'
                                                                     '// Agent stream identity carried by a '
                                                                     'handoff/sideband packet.\n'
                                                                     '#[derive(Clone, Copy, PartialEq, Eq)]\n'
                                                                     'struct '
                                                                     'OriginalControlIdentity(SocketIdentity);\n'
                                                                     'impl OriginalControlIdentity {\n'
                                                                     '    fn capture(fd: RawFd) -> '
                                                                     'Result<Self, HandoffError> {\n'
                                                                     '        socket_identity(fd).map(Self)\n'
                                                                     '    }\n'
                                                                     '    fn verify(&self, fd: RawFd) -> '
                                                                     'Result<(), HandoffError> {\n'
                                                                     '        if socket_identity(fd)? != '
                                                                     'self.0 {\n'
                                                                     '            return '
                                                                     'Err(HandoffError::WrongDescriptor);\n'
                                                                     '        }\n'
                                                                     '        Ok(())\n'
                                                                     '    }\n'
                                                                     '}\n'
                                                                     '\n',
                                                           'parent': '    device: u64,\n'
                                                                     '    inode: u64,\n'
                                                                     '}\n'
                                                                     '\n'},
                                                          {'actual': '    peer: PeerIdentity,\n'
                                                                     '    policy: PeerPolicy,\n'
                                                                     '    original_identity: '
                                                                     'OriginalControlIdentity,\n'
                                                                     '}\n'
                                                                     'impl ControlChannel {\n',
                                                           'parent': '    peer: PeerIdentity,\n'
                                                                     '    policy: PeerPolicy,\n'
                                                                     '}\n'
                                                                     'impl ControlChannel {\n'},
                                                          {'actual': '            }\n'
                                                                     '        }\n'
                                                                     '        let original_identity = '
                                                                     'OriginalControlIdentity::capture(fd)?;\n'
                                                                     '        Ok(Self {\n'
                                                                     '            stream: Some(stream),\n',
                                                           'parent': '            }\n'
                                                                     '        }\n'
                                                                     '        Ok(Self {\n'
                                                                     '            stream: Some(stream),\n'},
                                                          {'actual': '            peer,\n'
                                                                     '            policy,\n'
                                                                     '            original_identity,\n'
                                                                     '        })\n'
                                                                     '    }\n',
                                                           'parent': '            peer,\n'
                                                                     '            policy,\n'
                                                                     '        })\n'
                                                                     '    }\n'}],
 'crates/hepta-agent-transport/src/accepted_handoff/retained_control.rs': [{'actual': '    '
                                                                                      'monotonic_deadline: '
                                                                                      'u64,\n'
                                                                                      '    deadline: '
                                                                                      'Instant,\n'
                                                                                      '    '
                                                                                      'readiness_enabled: '
                                                                                      'bool,\n'
                                                                                      '}\n'
                                                                                      'impl Transaction {\n',
                                                                            'parent': '    '
                                                                                      'monotonic_deadline: '
                                                                                      'u64,\n'
                                                                                      '    deadline: '
                                                                                      'Instant,\n'
                                                                                      '}\n'
                                                                                      'impl Transaction {\n'},
                                                                           {'actual': '        '
                                                                                      'channel.owner()?;\n'
                                                                                      '        let fd = '
                                                                                      'channel.verify()?;\n'
                                                                                      '        if '
                                                                                      'self.readiness_enabled '
                                                                                      '{\n'
                                                                                      '            '
                                                                                      'channel.original_identity.verify(fd)?;\n'
                                                                                      '        }\n'
                                                                                      '        check_time(\n'
                                                                                      '            '
                                                                                      '&self.boot,\n',
                                                                            'parent': '        '
                                                                                      'channel.owner()?;\n'
                                                                                      '        let fd = '
                                                                                      'channel.verify()?;\n'
                                                                                      '        check_time(\n'
                                                                                      '            '
                                                                                      '&self.boot,\n'},
                                                                           {'actual': '        if '
                                                                                      'Instant::now() >= '
                                                                                      'self.deadline {\n'
                                                                                      '            return '
                                                                                      'Err(HandoffError::DeadlineExceeded);\n'
                                                                                      '        }\n'
                                                                                      '        if '
                                                                                      'self.readiness_enabled '
                                                                                      '{\n'
                                                                                      '            '
                                                                                      'channel.original_identity.verify(fd)?;\n'
                                                                                      '        }\n'
                                                                                      '        Ok(fd)\n',
                                                                            'parent': '        if '
                                                                                      'Instant::now() >= '
                                                                                      'self.deadline {\n'
                                                                                      '            return '
                                                                                      'Err(HandoffError::DeadlineExceeded);\n'
                                                                                      '        }\n'
                                                                                      '        Ok(fd)\n'},
                                                                           {'actual': '            peer: '
                                                                                      'self.channel.peer,\n'
                                                                                      '            policy: '
                                                                                      'self.channel.policy,\n'
                                                                                      '            '
                                                                                      'original_identity: '
                                                                                      'self.channel.original_identity,\n'
                                                                                      '        })\n'
                                                                                      '    }\n',
                                                                            'parent': '            peer: '
                                                                                      'self.channel.peer,\n'
                                                                                      '            policy: '
                                                                                      'self.channel.policy,\n'
                                                                                      '        })\n'
                                                                                      '    }\n'},
                                                                           {'actual': '                '
                                                                                      'monotonic_deadline: '
                                                                                      'custody.deadline,\n'
                                                                                      '                '
                                                                                      'deadline,\n'
                                                                                      '                '
                                                                                      'readiness_enabled: '
                                                                                      'false,\n'
                                                                                      '            },\n'
                                                                                      '            '
                                                                                      'cancellation_attempted: '
                                                                                      'false,\n',
                                                                            'parent': '                '
                                                                                      'monotonic_deadline: '
                                                                                      'custody.deadline,\n'
                                                                                      '                '
                                                                                      'deadline,\n'
                                                                                      '            },\n'
                                                                                      '            '
                                                                                      'cancellation_attempted: '
                                                                                      'false,\n'},
                                                                           {'actual': '                '
                                                                                      'monotonic_deadline: '
                                                                                      'received.monotonic_deadline,\n'
                                                                                      '                '
                                                                                      'deadline: '
                                                                                      'received.deadline,\n'
                                                                                      '                '
                                                                                      'readiness_enabled: '
                                                                                      'false,\n'
                                                                                      '            },\n'
                                                                                      '            '
                                                                                      'cancellation_received: '
                                                                                      'false,\n',
                                                                            'parent': '                '
                                                                                      'monotonic_deadline: '
                                                                                      'received.monotonic_deadline,\n'
                                                                                      '                '
                                                                                      'deadline: '
                                                                                      'received.deadline,\n'
                                                                                      '            },\n'
                                                                                      '            '
                                                                                      'cancellation_received: '
                                                                                      'false,\n'},
                                                                           {'actual': '    Ok(result != 0)\n'
                                                                                      '}\n'
                                                                                      '\n'
                                                                                      '#[cfg(test)]\n'
                                                                                      'mod readiness_tests;\n'
                                                                                      '\n'
                                                                                      'mod readiness;\n',
                                                                            'parent': '    Ok(result != 0)\n'
                                                                                      '}\n'}],
 'crates/hepta-peer-attestation/src/approved_policy.rs': [{'actual': '}\n'
                                                                     'impl ApprovedGuard {\n'
                                                                     '    pub(crate) fn '
                                                                     'verify_control_reporting_source(\n'
                                                                     '        &self,\n'
                                                                     '        attested: &AttestedPeer,\n'
                                                                     '    ) -> Result<(), '
                                                                     'crate::ControlOwnerError> {\n'
                                                                     '        self.current()?;\n'
                                                                     '        if self.role != 0 {\n'
                                                                     '            return '
                                                                     'Err(crate::ControlOwnerError::PeerRefused);\n'
                                                                     '        }\n'
                                                                     '        let entry = '
                                                                     '&self.state.entries[0];\n'
                                                                     '        let snapshot = '
                                                                     'attested.snapshot();\n'
                                                                     '        if snapshot.uid != entry.uid\n'
                                                                     '            || snapshot.gid != '
                                                                     'entry.gid\n'
                                                                     '            || '
                                                                     'snapshot.systemd_unit.as_deref() != '
                                                                     'Some(entry.unit.as_str())\n'
                                                                     '            || snapshot.cgroup_v2_path '
                                                                     '!= entry.cgroup\n'
                                                                     '            || '
                                                                     'snapshot.executable_sha256 != '
                                                                     'entry.pin\n'
                                                                     '        {\n'
                                                                     '            return '
                                                                     'Err(crate::ControlOwnerError::PeerRefused);\n'
                                                                     '        }\n'
                                                                     '        self.current()\n'
                                                                     '    }\n'
                                                                     '    pub(crate) fn current(&self) -> '
                                                                     'Result<(), crate::ControlOwnerError> '
                                                                     '{\n'
                                                                     '        '
                                                                     'self.state.inspect().map_err(control_error)\n',
                                                           'parent': '}\n'
                                                                     'impl ApprovedGuard {\n'
                                                                     '    pub(crate) fn current(&self) -> '
                                                                     'Result<(), crate::ControlOwnerError> '
                                                                     '{\n'
                                                                     '        '
                                                                     'self.state.inspect().map_err(control_error)\n'}],
 'crates/hepta-peer-attestation/src/control_owner.rs': [{'actual': '        for policy in &self.approved {\n'
                                                                   '            policy.current()?;\n'
                                                                   '        }\n'
                                                                   '        remaining(self.owner_pid, '
                                                                   'self.deadline)\n'
                                                                   '    }\n'
                                                                   '    // Denial-only reporting scope. The '
                                                                   'original action may already be revoked;\n'
                                                                   '    // actual packet consumption and '
                                                                   'reporting still use complete current().\n'
                                                                   '    fn idle_reporting_scope(&self) -> '
                                                                   'Result<Duration, ControlOwnerError> {\n'
                                                                   '        remaining(self.owner_pid, '
                                                                   'self.deadline)?;\n'
                                                                   '        let path = self\n'
                                                                   '            .root_path\n'
                                                                   '            .as_ref()\n'
                                                                   '            '
                                                                   '.ok_or(ControlOwnerError::PeerRefused)?;\n'
                                                                   '        path.current()?;\n'
                                                                   '        if self.approved.is_empty() {\n'
                                                                   '            return '
                                                                   'Err(ControlOwnerError::PeerRefused);\n'
                                                                   '        }\n'
                                                                   '        for policy in &self.approved {\n'
                                                                   '            '
                                                                   'policy.verify_control_reporting_source(&self.attested)?;\n'
                                                                   '        }\n'
                                                                   '        self.attested\n'
                                                                   '            .ensure_alive()\n'
                                                                   '            .map_err(|_| '
                                                                   'ControlOwnerError::PeerRefused)?;\n'
                                                                   '        path.current()?;\n'
                                                                   '        for policy in &self.approved {\n'
                                                                   '            '
                                                                   'policy.verify_control_reporting_source(&self.attested)?;\n'
                                                                   '        }\n'
                                                                   '        remaining(self.owner_pid, '
                                                                   'self.deadline)\n',
                                                         'parent': '        for policy in &self.approved {\n'
                                                                   '            policy.current()?;\n'
                                                                   '        }\n'
                                                                   '        remaining(self.owner_pid, '
                                                                   'self.deadline)\n'}],
 'crates/hepta-peer-attestation/src/control_owner/retained_request.rs': [{'actual': '    }\n'
                                                                                    '}\n'
                                                                                    '\n'
                                                                                    'mod readiness;\n',
                                                                          'parent': '    }\n}\n'}],
 'tools/verify_approved_composition_scope.py': [{'actual': '\n'
                                                           'def check(contract, texts):\n'
                                                           '    # Explicit finite successor inverse; '
                                                           'original EXPECTED and rules are kept.\n'
                                                           '    try:\n'
                                                           '        from .verify_retained_control_readiness '
                                                           'import legacy_texts\n'
                                                           '    except ImportError:\n'
                                                           '        from verify_retained_control_readiness '
                                                           'import legacy_texts\n'
                                                           '    texts = legacy_texts(texts)\n'
                                                           '    composition.typed_equal(contract, EXPECTED)\n'
                                                           '    inventories = {}\n',
                                                 'parent': '\n'
                                                           'def check(contract, texts):\n'
                                                           '    composition.typed_equal(contract, EXPECTED)\n'
                                                           '    inventories = {}\n'}],
 'tools/verify_approved_constructor_route.py': [{'actual': '\n'
                                                           'def check(contract, texts):\n'
                                                           '    # Explicit finite successor inverse; '
                                                           'original EXPECTED and rules are kept.\n'
                                                           '    try:\n'
                                                           '        from .verify_retained_control_readiness '
                                                           'import legacy_texts\n'
                                                           '    except ImportError:\n'
                                                           '        from verify_retained_control_readiness '
                                                           'import legacy_texts\n'
                                                           '    texts = legacy_texts(texts)\n'
                                                           '    composition.typed_equal(contract, EXPECTED)\n'
                                                           '    for path, expected in '
                                                           'EXPECTED["whole_source_sha256"].items():\n',
                                                 'parent': '\n'
                                                           'def check(contract, texts):\n'
                                                           '    composition.typed_equal(contract, EXPECTED)\n'
                                                           '    for path, expected in '
                                                           'EXPECTED["whole_source_sha256"].items():\n'}],
 'tools/verify_approved_native_startup.py': [{'actual': '\n'
                                                        'def validate(root: Path = ROOT) -> None:\n'
                                                        '    # Mandatory actual readiness profile plus exact '
                                                        'bounded legacy transfer.\n'
                                                        '    try:\n'
                                                        '        from .verify_retained_control_readiness '
                                                        'import validate as check_readiness\n'
                                                        '    except ImportError:\n'
                                                        '        from verify_retained_control_readiness '
                                                        'import validate as check_readiness\n'
                                                        '    check_readiness(root)\n'
                                                        '    check_composition(load(root / CONTRACT), '
                                                        'source(root, QUEUE), source(root, NATIVE),\n'
                                                        '                      source(root, '
                                                        '"apps/hepta-browserd/src/product_dispatch.rs"),\n',
                                              'parent': '\n'
                                                        'def validate(root: Path = ROOT) -> None:\n'
                                                        '    check_composition(load(root / CONTRACT), '
                                                        'source(root, QUEUE), source(root, NATIVE),\n'
                                                        '                      source(root, '
                                                        '"apps/hepta-browserd/src/product_dispatch.rs"),\n'}]}
CARGO_SUFFIX = '\n# Additive actual Control-readiness source corpus; original targets unchanged.\n[[test]]\nname = "control_readiness_kernel"\npath = "tests/control_readiness_kernel.rs"\nharness = false\n'


def parent_source(path, text):
    """Inverse only this reviewed additive profile; preserve all other bytes.

    Legacy mutation tests may append comments. They continue to exercise their
    original token/whole-source rules after this bounded inverse transfer.
    Actual-profile check() additionally requires whole exact bytes below.
    """
    try:
        from .verify_approved_service_owner import detach_for_readiness
        from .verify_approved_service_runtime import parent_source as service_runtime_parent_source
    except ImportError:
        from verify_approved_service_owner import detach_for_readiness
        from verify_approved_service_runtime import parent_source as service_runtime_parent_source
    text = detach_for_readiness(path, service_runtime_parent_source(path, text))
    for step in reversed(TRANSFER.get(path, [])):
        if text.count(step["actual"]) != 1:
            raise ValueError("finite readiness inverse differs: " + path)
        text = text.replace(step["actual"], step["parent"], 1)
    if path == CARGO:
        if not text.endswith(CARGO_SUFFIX):
            raise ValueError("additive readiness target suffix differs")
        text = text[:-len(CARGO_SUFFIX)]
    return text


def legacy_texts(texts):
    return {path: parent_source(path, text) for path, text in texts.items()}


def unique_body(text, name):
    values = composition.tokens(text)
    starts = [i for i in range(len(values) - 1) if values[i:i + 2] == ["fn", name]]
    if len(starts) != 1:
        raise ValueError("finite readiness helper count differs: " + name)
    start = values.index("{", starts[0])
    depth = 1
    end = start + 1
    while end < len(values) and depth:
        depth += (values[end] == "{") - (values[end] == "}")
        end += 1
    if depth:
        raise ValueError("unbalanced readiness helper")
    return values[start + 1:end - 1]


def check(contract, texts):
    try:
        from .verify_approved_service_owner import detach_for_readiness
        from .verify_approved_service_runtime import parent_source as service_runtime_parent_source
    except ImportError:
        from verify_approved_service_owner import detach_for_readiness
        from verify_approved_service_runtime import parent_source as service_runtime_parent_source
    texts = {path: detach_for_readiness(path, service_runtime_parent_source(path, text)) for path, text in texts.items()}
    composition.typed_equal(contract, EXPECTED)
    for path, digest in SENDER_SOURCE_SHA256.items():
        if hashlib.sha256(texts[path].encode()).hexdigest() != digest:
            raise ValueError("independent sender readiness physical Source differs")
    for path, wanted in EXPECTED["actual_source_sha256"].items():
        if hashlib.sha256(texts[path].encode()).hexdigest() != wanted:
            raise ValueError("complete readiness source differs: " + path)
    for path, wanted in EXPECTED["preserved_sha256"].items():
        if hashlib.sha256(texts[path].encode()).hexdigest() != wanted:
            raise ValueError("preserved legacy source differs: " + path)
    for path, wanted in EXPECTED["parent_source_sha256"].items():
        restored = parent_source(path, texts[path])
        if hashlib.sha256(restored.encode()).hexdigest() != wanted:
            raise ValueError("finite whole-byte parent restoration differs: " + path)
    legacy_api = {}
    for path in [RETAINED, REQUEST, MONITOR]:
        legacy_api.update(composition.rust_inventory(texts[path])["public_api"])
    const_headers = {}
    for match in re.finditer(r"pub const fn (\w+)", texts[RETAINED]):
        opening = texts[RETAINED].index("{", match.end())
        key = "RemoteRetirementReport::" + match[1]
        if key in const_headers:
            raise ValueError("duplicate retained constant API")
        const_headers[key] = texts[RETAINED][match.start():opening].strip()
    if set(const_headers) != {"RemoteRetirementReport::state", "RemoteRetirementReport::request_sha256", "RemoteRetirementReport::record_sha256"}:
        raise ValueError("closed legacy constant API inventory differs")
    legacy_api.update(const_headers)
    if {key: composition.signature(value) for key, value in legacy_api.items()} != {key: composition.signature(value) for key, value in EXPECTED["legacy_public_api"].items()}:
        raise ValueError("closed legacy 36 API inventory differs")
    for path, keys in [(TRANSPORT_READINESS, {"PendingHandoffReceiver::cancel_readable_now", "PendingHandoffSender::report_readable_now"}),
                       (PEER_READINESS, {"AttestedRetainedReceiver::poll_cancel_when_readable", "AttestedPendingHandoff::poll_retirement_when_readable"})]:
        if set(composition.rust_inventory(texts[path])["public_api"]) != keys:
            raise ValueError("new versioned module API inventory differs")
    inventory = composition.rust_inventory(texts[TRANSPORT])
    composition.ordered(composition.function(inventory, "ControlChannel::new"),
                        ["socket_shape(&stream, libc::SOCK_SEQPACKET)?", "PeerIdentity::from_stream(&stream)",
                         "OriginalControlIdentity::capture(fd)?", "Ok(Self"],
                        "creation-time actual Control identity capture")
    transaction = composition.rust_inventory(texts[RETAINED])
    composition.ordered(composition.function(transaction, "Transaction::verify_channel"),
                        ["channel.owner()?", "channel.verify()?", "channel.original_identity.verify(fd)?",
                         "check_time", "Instant::now() >= self.deadline", "channel.original_identity.verify(fd)?", "Ok(fd)"],
                        "creator/original cookie/clock pre and post packet access")
    readiness = composition.rust_inventory(texts[TRANSPORT_READINESS])
    composition.ordered(composition.function(readiness, "PendingHandoffReceiver::cancel_readable_now"),
                        ["self.transaction.channel.owner()?", "self.transaction.readiness_enabled = true",
                         "readable_now(self.transaction.verify()?)?", "self.transaction.verify()?",
                         "result.is_err()", "self.transaction.channel.retire()"],
                        "nonconsuming original Control ready observation")
    if composition.function(transaction, "Transaction::take_channel").count("original_identity") != 2:
        raise ValueError("detached report loses original Control identity")
    for path, method, signature in [(TRANSPORT_READINESS, "PendingHandoffSender::report_readable_now", EXPECTED["public_api"]["PendingHandoffSender::report_readable_now"]),
                                    (PEER_READINESS, "AttestedPendingHandoff::poll_retirement_when_readable", EXPECTED["public_api"]["AttestedPendingHandoff::poll_retirement_when_readable"]),
                                    (TRANSPORT_READINESS, "PendingHandoffReceiver::cancel_readable_now", EXPECTED["public_api"]["PendingHandoffReceiver::cancel_readable_now"]),
                                    (PEER_READINESS, "AttestedRetainedReceiver::poll_cancel_when_readable", EXPECTED["public_api"]["AttestedRetainedReceiver::poll_cancel_when_readable"])]:
        actual = composition.rust_inventory(texts[path])["public_api"][method]
        if composition.signature(actual) != composition.signature(signature):
            raise ValueError("readiness API admits caller FD/clock/authority")
    idle = unique_body(texts[OWNER], "idle_reporting_scope")
    composition.ordered(idle, ["remaining(self.owner_pid, self.deadline)?", ".root_path", "path.current()?",
                              "self.approved.is_empty()", "policy.verify_control_reporting_source(&self.attested)?",
                              "self.attested", ".ensure_alive()", "path.current()?",
                              "policy.verify_control_reporting_source(&self.attested)?", "remaining(self.owner_pid, self.deadline)"],
                        "original reporting owner/root/Control pidfd scope")
    if "action" in idle or "refresh_snapshot" in idle or "len" in idle:
        raise ValueError("idle report scope adopts action or positional authority")
    composition.ordered(unique_body(texts[POLICY], "verify_control_reporting_source"),
                        ["self.current()?", "self.role != 0", "attested.snapshot()", "snapshot.uid", "snapshot.gid",
                         "snapshot.systemd_unit", "snapshot.cgroup_v2_path", "snapshot.executable_sha256", "self.current()"],
                        "whole approved source plus original Control role")
    composition.ordered(unique_body(texts[PEER_READINESS], "poll_cancel_when_readable"),
                        ["creator(self.owner_pid)?", "remaining(self.owner_pid, self.deadline)?", ".idle_reporting_scope()?",
                         ".cancel_readable_now()", ".idle_reporting_scope()?", "remaining(self.owner_pid, self.deadline)?",
                         "if ready", "self.poll_cancel()", "Ok(false)", "checked.is_err()", "self.retire()?"],
                        "idle refusal and ready unchanged full consumption")
    if "action" in unique_body(texts[PEER_READINESS], "poll_cancel_when_readable"):
        raise ValueError("idle wait depends on retired action")
    composition.ordered(unique_body(texts[MONITOR], "poll_original_cancel"),
                        ["self.owner_pid != std::process::id()", "self.retained.as_mut()", "match self.cancel_profile",
                         "CancelPollProfile::FullV1", "retained.poll_cancel()", "CancelPollProfile::ApprovedReadinessV1",
                         "retained.poll_cancel_when_readable()"], "legacy/full and opaque profile monitor routes")
    composition.ordered(composition.function(readiness, "PendingHandoffSender::report_readable_now"),
                        ["self.transaction.channel.owner()?", "self.transaction.readiness_enabled = true",
                         "readable_now(self.transaction.verify()?)?", "self.transaction.verify()?",
                         "result.is_err()", "self.transaction.channel.retire()"],
                        "sender original Control nonconsuming observation")
    sender = unique_body(texts[PEER_READINESS], "poll_retirement_when_readable")
    composition.ordered(sender,
                        ["creator(self.owner_pid)?", "remaining(self.owner_pid, self.deadline)?", ".idle_reporting_scope()?",
                         ".report_readable_now()", ".idle_reporting_scope()?", "remaining(self.owner_pid, self.deadline)?",
                         "if ready", "self.poll_retirement()", "Ok(None)", "checked.is_err()", "self.retire()?"],
                        "sender idle denial and original full report consumption")
    if any(value in sender for value in ("action", "Instant", "Duration", "refresh_snapshot", "mint_report_permission")):
        raise ValueError("sender idle scope grants authority or changes original budget")
    if texts[PRODUCT].count("cancel_profile: CancelPollProfile::ApprovedReadinessV1") != 1:
        raise ValueError("approved private profile factory differs")
    if texts[MONITOR].count("cancel_profile: CancelPollProfile::FullV1") != 1:
        raise ValueError("legacy full profile factory differs")


def validate(root=ROOT):
    paths = set(EXPECTED["actual_source_sha256"]) | set(EXPECTED["preserved_sha256"])
    check(composition.load(root / CONTRACT), {path: composition.source(root, path) for path in paths})


def main():
    try:
        validate()
    except (ValueError, OSError) as error:
        print("retained Control readiness validation failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"source_contract": "PASS", "runtime_qualification": "PENDING",
                      "idle_permission": False, "installed_activation": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
