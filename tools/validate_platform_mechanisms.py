#!/usr/bin/env python3
"""Check source documentation/API registration; never certify execution gates."""
from __future__ import annotations

import argparse
import ast
import json
import os
import secrets
from pathlib import Path

try:
    from .browser_codec_reference_security import load_json_strict, open_regular_beneath
except ImportError:
    from browser_codec_reference_security import load_json_strict, open_regular_beneath

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "manifests/platform-mechanisms.v1.json"
MAX_BYTES = 2 * 1024 * 1024
FIELDS = {"id", "requirements", "implementation", "documentation", "contract", "tests", "source_defined_api"}
MODULES = {"signed_apps", "app_storage", "taskflow", "controlled_egress", "signed_update", "durable_update_owner"}
EXPECTED_MODULES = {
    "signed_apps": ("trusted_apps", "TRUSTED_APP_BUNDLES", "trusted-app-bundle", "test_trusted_apps", ["G5", "D5"]),
    "app_storage": ("app_storage", "APP_STORAGE", "app-storage", "test_app_storage", ["G5", "D5"]),
    "taskflow": ("taskflow", "TASKFLOW_CAPABILITIES", "taskflow-execution", "test_taskflow", ["G5", "D6"]),
    "controlled_egress": ("controlled_egress", "CONTROLLED_EGRESS", "controlled-egress", "test_controlled_egress", ["G5", "D6"]),
    "signed_update": ("update_recovery", "S11_UPDATE_RECOVERY", "s11-update-recovery", "test_s11_update_recovery", ["G6", "D7", "S11"]),
    "durable_update_owner": ("durable_update_owner", "DURABLE_UPDATE_OWNER", "durable-update-owner", "test_durable_update_owner", ["G6", "D7", "S11"]),
}
# Reviewed contract identity, closed top-level fields and source-only claim paths.
# This fixed profile is not refreshed by --refresh-api.
CONTRACT_PROFILES = {'signed_apps': {'fields': ['archive',
                            'content_index',
                            'implementation',
                            'limits',
                            'local_response',
                            'manifest',
                            'remaining_installed_obligations',
                            'schema',
                            'status',
                            'trust'],
                 'claims': {'schema': 'trillionnium.desktop.trusted-app-bundle.v1',
                            'status': 'SOURCE_CANDIDATE',
                            'trust/default_roots': [],
                            'trust/persistent_rollback_anchor_implemented': False,
                            'local_response/network_fallback': False,
                            'local_response/redirects': False,
                            'local_response/installed_origin_interception_implemented': False,
                            'local_response/installed_csp_and_egress_qualification': False},
                 'objects': {'manifest': ['archive_path',
                                          'capabilities',
                                          'closed_field_set',
                                          'data_schema_version',
                                          'encoding',
                                          'entrypoint',
                                          'minimum_shell_version',
                                          'origin_host',
                                          'schema_reference',
                                          'signature_algorithm',
                                          'signature_value_encoding',
                                          'signing_domain_utf8',
                                          'signing_preimage',
                                          'version_profile'],
                             'content_index': ['content_root_sha256',
                                               'encoding',
                                               'hash_domain_utf8',
                                               'manifest_excluded',
                                               'object',
                                               'ordering',
                                               'schema',
                                               'self_reference'],
                             'archive': ['allowed_general_flags',
                                         'checks',
                                         'collisions_rejected',
                                         'creator_systems',
                                         'extraction',
                                         'format',
                                         'local_central_metadata_match',
                                         'maximum_extraction_version',
                                         'methods',
                                         'path_profile',
                                         'rejected'],
                             'limits': ['archive_bytes',
                                        'asset_bytes',
                                        'asset_count',
                                        'compression_ratio',
                                        'content_bytes',
                                        'manifest_bytes',
                                        'path_characters',
                                        'segment_characters'],
                             'trust': ['bounds',
                                       'default_roots',
                                       'owner',
                                       'persistent_rollback_anchor_implemented',
                                       'pin',
                                       'policy_fields',
                                       'revocation',
                                       'root_fields',
                                       'root_source',
                                       'rotation',
                                       'scope',
                                       'time',
                                       'verification'],
                             'trust/bounds': ['active_roots', 'remembered_key_pins', 'revocations'],
                             'local_response': ['access_control_allow_origin',
                                                'content_security_policy',
                                                'headers',
                                                'installed_csp_and_egress_qualification',
                                                'installed_origin_interception_implemented',
                                                'method',
                                                'mime',
                                                'network_fallback',
                                                'redirects',
                                                'reject',
                                                'source',
                                                'supported_extensions',
                                                'url'],
                             'local_response/headers': ['Cache-Control',
                                                        'Cross-Origin-Resource-Policy',
                                                        'Referrer-Policy',
                                                        'X-Content-Type-Options']}},
 'app_storage': {'fields': ['admission_dependency',
                            'custody',
                            'data',
                            'durability',
                            'garbage_collection',
                            'implementation',
                            'installed_csp_or_egress_qualification',
                            'installed_engine_storage_enforcement',
                            'installed_origin_interception',
                            'lifecycle',
                            'limits',
                            'owner',
                            'partition',
                            'policy',
                            'remaining_obligations',
                            'schema',
                            'status',
                            'whole_directory_rollback_protection'],
                 'claims': {'schema': 'trillionnium.desktop.app-storage.v1',
                            'status': 'SOURCE_CANDIDATE',
                            'custody/deletion_or_auto_repair': False,
                            'policy/default_roots': [],
                            'installed_engine_storage_enforcement': False,
                            'installed_origin_interception': False,
                            'installed_csp_or_egress_qualification': False,
                            'whole_directory_rollback_protection': False},
                 'objects': {'partition': ['caller_authentication',
                                           'digest_domain_utf8',
                                           'digest_preimage',
                                           'handle',
                                           'identity'],
                             'custody': ['ancestors',
                                         'deletion_or_auto_repair',
                                         'files',
                                         'lease',
                                         'root'],
                             'lifecycle': ['assets',
                                           'migration',
                                           'reinstall',
                                           'transaction',
                                           'uninstall',
                                           'version_profile'],
                             'data': ['key', 'namespace', 'quotas', 'value'],
                             'policy': ['clock',
                                        'current_revalidation',
                                        'default_roots',
                                        'durable_floor',
                                        'historical_consistency',
                                        'provisioning',
                                        'refused_target_or_capacity'],
                             'durability': ['close_barrier_failure',
                                            'operator_recovery',
                                            'persistent_refusal',
                                            'protocol',
                                            'return_window'],
                             'limits': ['canonical_archive_bytes',
                                        'data_value_bytes',
                                        'events',
                                        'live_partition_data_bytes',
                                        'owner_sessions',
                                        'partitions',
                                        'record_bytes',
                                        'retained_partition_key_identities',
                                        'retained_store_bytes',
                                        'root_files']}},
 'taskflow': {'fields': ['budgets',
                         'claim_ceiling',
                         'default_authority',
                         'documentation',
                         'durable_consumption',
                         'implementation',
                         'json_profile',
                         'native_binding_fields',
                         'native_resource_fields',
                         'operations',
                         'permit_resource_fields',
                         'permit_schema',
                         'plan_revision',
                         'proposal_fields',
                         'proposal_schema',
                         'remaining_integration',
                         'schema',
                         'signing',
                         'states',
                         'status',
                         'tests',
                         'transitions'],
              'claims': {'schema': 'trillionnium.desktop.taskflow-execution.v1',
                         'status': 'candidate_source_enforcement',
                         'claim_ceiling': 'typed externally signed TaskFlow admission and concrete '
                                          'local durable single-use consumption source only; no '
                                          'trusted approval UI, installed effect adapter, native '
                                          'retained-target qualification, network egress, operator '
                                          'recovery decision, protected anti-rollback, hardware or '
                                          'release authority',
                         'default_authority': {'trust_roots': [],
                                               'durable_store': None,
                                               'approval_without_valid_external_signature': False,
                                               'dispatch_without_concrete_durable_store': False,
                                               'automatic_retry': False,
                                               'automatic_handoff_clear': False,
                                               'resume_any_previously_reserved_task_after_restart': False,
                                               'reuse_inherited_fork_authority': False},
                         'default_authority/approval_without_valid_external_signature': False,
                         'default_authority/dispatch_without_concrete_durable_store': False,
                         'default_authority/automatic_retry': False,
                         'default_authority/automatic_handoff_clear': False,
                         'default_authority/resume_any_previously_reserved_task_after_restart': False,
                         'default_authority/reuse_inherited_fork_authority': False},
              'objects': {'default_authority': ['approval_without_valid_external_signature',
                                                'automatic_handoff_clear',
                                                'automatic_retry',
                                                'dispatch_without_concrete_durable_store',
                                                'durable_store',
                                                'resume_any_previously_reserved_task_after_restart',
                                                'reuse_inherited_fork_authority',
                                                'trust_roots'],
                          'operations': ['page.act',
                                         'page.extract',
                                         'page.navigate',
                                         'page.observe'],
                          'operations/page.observe': ['arguments', 'resource_kind'],
                          'operations/page.observe/arguments': ['mode'],
                          'operations/page.act': ['arguments', 'resource_kind'],
                          'operations/page.act/arguments': ['action'],
                          'operations/page.navigate': ['arguments', 'resource_kind'],
                          'operations/page.navigate/arguments': ['url'],
                          'operations/page.extract': ['arguments', 'resource_kind'],
                          'operations/page.extract/arguments': ['schema_id'],
                          'json_profile': ['canonicalization',
                                           'identifiers',
                                           'numbers',
                                           'objects',
                                           'origin',
                                           'sha256',
                                           'signature'],
                          'signing': ['algorithm',
                                      'excluded_field',
                                      'included_signature_fields',
                                      'key_encoding',
                                      'key_pin',
                                      'permit_domain',
                                      'proposal_domain',
                                      'revocation',
                                      'root_scope',
                                      'untrusted_source_cannot_configure_roots',
                                      'verification'],
                          'transitions': ['approved_to_dispatched',
                                          'clock_regression',
                                          'dispatched_to_indeterminate',
                                          'dispatched_to_terminal',
                                          'new_task_after_revisions_change',
                                          'predispatch_cancel_or_handoff',
                                          'proposed_to_approved'],
                          'budgets': ['max_action_budget_ms',
                                      'max_actions_per_task',
                                      'max_consumptions_per_store',
                                      'max_json_depth',
                                      'max_permit_lifetime_ms',
                                      'max_revocations',
                                      'max_roots',
                                      'max_task_budget_ms',
                                      'max_task_reservations_per_store',
                                      'max_tasks_per_coordinator',
                                      'max_wire_bytes',
                                      'signature_verification_timeout_seconds'],
                          'durable_consumption': ['anti_rollback',
                                                  'capacity',
                                                  'commit',
                                                  'failure',
                                                  'fields',
                                                  'namespaces',
                                                  'replay',
                                                  'root',
                                                  'schema',
                                                  'task_reservation',
                                                  'task_reservation_fields',
                                                  'task_reservation_schema']}},
 'controlled_egress': {'fields': ['address_policy',
                                  'authority',
                                  'default',
                                  'https',
                                  'implementation',
                                  'limits',
                                  'outcome',
                                  'qualification',
                                  'remaining_installed_obligations',
                                  'resolver',
                                  'schema',
                                  'status'],
                       'claims': {'schema': 'trillionnium.desktop.controlled-egress.v1',
                                  'status': 'SOURCE_CANDIDATE',
                                  'default/external_mutation_enabled': False,
                                  'default/browser_namespace_enforced': False,
                                  'authority/approval_surface_implemented': False,
                                  'authority/persistent_permit_or_indeterminate_journal_implemented': False,
                                  'address_policy/synthetic_origins_reach_public_dns': False,
                                  'https/caller_headers_credentials_cookies_body': False,
                                  'outcome/automatic_retry': False,
                                  'outcome/durable_delivery_or_external_effect_proof': False,
                                  'qualification/installed_browser_or_hardware_success': False,
                                  'default': {'hosts': [],
                                              'initiating_origins': [],
                                              'resolver': None,
                                              'certificate_roots': None,
                                              'external_mutation_enabled': False,
                                              'browser_namespace_enforced': False},
                                  'qualification': {'profile': 'explicit exact '
                                                               'QualificationProfile accepted only '
                                                               'by QualificationEgressClient; '
                                                               'rejected by production '
                                                               'ControlledEgress',
                                                    'addresses': ['127.0.0.1', '::1'],
                                                    'socket_tls_code': 'same resolver, TLS, peer, '
                                                                       'redirect, deadline and '
                                                                       'body path as production; '
                                                                       'exact loopback address '
                                                                       'policy is the sole network '
                                                                       'allowance',
                                                    'keys': 'temporary test-only OpenSSL CA/server '
                                                            'fixtures; no production keys or roots',
                                                    'qualification_only': True,
                                                    'installed_browser_or_hardware_success': False}},
                       'objects': {'default': ['browser_namespace_enforced',
                                               'certificate_roots',
                                               'external_mutation_enabled',
                                               'hosts',
                                               'initiating_origins',
                                               'resolver'],
                                   'authority': ['approval_surface_implemented',
                                                 'cancellation',
                                                 'clock',
                                                 'configuration',
                                                 'hosts',
                                                 'native_io_gate',
                                                 'origin',
                                                 'permit',
                                                 'persistent_permit_or_indeterminate_journal_implemented',
                                                 'process',
                                                 'revocation',
                                                 'session'],
                                   'resolver': ['address_selection',
                                                'checks',
                                                'fresh_resolution',
                                                'protocol',
                                                'queries',
                                                'unsupported_answers'],
                                   'address_policy': ['all_answers_must_pass',
                                                      'ipv4',
                                                      'ipv6',
                                                      'synthetic_origins_reach_public_dns'],
                                   'https': ['alpn',
                                             'caller_headers_credentials_cookies_body',
                                             'certificate',
                                             'charset',
                                             'content_types',
                                             'disabled',
                                             'method',
                                             'minimum_tls_version',
                                             'peer',
                                             'redirect',
                                             'redirect_statuses',
                                             'rejected_response_headers',
                                             'request_headers',
                                             'resource_class',
                                             'response'],
                                   'limits': ['active_operations',
                                              'approved_hosts',
                                              'approved_origins',
                                              'body_bytes_each_hop',
                                              'ca_bytes_each',
                                              'cancellation_poll_seconds_max',
                                              'deadline_seconds_max',
                                              'deadline_seconds_min',
                                              'dns_packet_bytes',
                                              'dns_records_each_packet',
                                              'header_bytes_each_hop',
                                              'header_count_each_hop',
                                              'pending_permits',
                                              'redirects',
                                              'resolved_addresses_each_hop',
                                              'url_bytes'],
                                   'outcome': ['after_http_send_attempt',
                                               'automatic_retry',
                                               'before_http_send',
                                               'cleanup',
                                               'durable_delivery_or_external_effect_proof',
                                               'interruption_evidence_scope',
                                               'policy_digest',
                                               'policy_object_fields',
                                               'receipt_identity',
                                               'response'],
                                   'outcome/policy_object_fields': ['ca_sha256',
                                                                    'hosts',
                                                                    'origins',
                                                                    'qualification_addresses',
                                                                    'resolver'],
                                   'qualification': ['addresses',
                                                     'installed_browser_or_hardware_success',
                                                     'keys',
                                                     'profile',
                                                     'qualification_only',
                                                     'socket_tls_code']}},
 'signed_update': {'fields': ['authority_ownership',
                              'claim_ceiling',
                              'durability',
                              'fault_model',
                              'image_staging',
                              'journal_reconciliation',
                              'manifest',
                              'non_claims',
                              'operator_recovery',
                              'schema',
                              'signature_admission',
                              'stage',
                              'state_machine'],
                   'claims': {'schema': 'trillionnium.desktop.s11-update-recovery.v1',
                              'claim_ceiling': 'source_and_host_mechanism_candidate_only_no_installed_update_no_hardware_no_signing_no_release',
                              'stage': 'S11',
                              'state_machine/automatic_effect_replay': False,
                              'non_claims/installed_qemu_update_executed': False,
                              'non_claims/raw_power_loss_executed': False,
                              'non_claims/physical_hardware_qualified': False,
                              'non_claims/production_signature_verified': False,
                              'non_claims/release_published': False,
                              'signature_admission/default_admission_enabled': False,
                              'signature_admission/external_monotonic_floor_persistence_implemented': False,
                              'authority_ownership/inherited_fork_authority': False,
                              'authority_ownership/thread_transfer_or_concurrent_use': False,
                              'authority_ownership/caller_verification_or_persistence_callbacks': False,
                              'image_staging/production_activation_enabled': False,
                              'operator_recovery/default_approved_operator_uids': [],
                              'operator_recovery/bootloader_or_block_device_mutation': False,
                              'journal_reconciliation/default_authority_enabled': False,
                              'journal_reconciliation/caller_digest_or_status_assertion_accepted': False,
                              'journal_reconciliation/installed_journal_authority_provisioned': False,
                              'non_claims': {'installed_qemu_update_executed': False,
                                             'raw_power_loss_executed': False,
                                             'physical_hardware_qualified': False,
                                             'production_signature_verified': False,
                                             'release_published': False}},
                   'objects': {'manifest': ['downgrade_refused',
                                            'exact_fields',
                                            'expiry_enforced',
                                            'inactive_slot_required',
                                            'repository',
                                            'rollback_floor_enforced',
                                            'schema',
                                            'source_identity_required',
                                            'whole_image_digest_required',
                                            'whole_image_length_required'],
                               'state_machine': ['automatic_effect_replay',
                                                 'commit_requires_health_receipt',
                                                 'health_permits_invalidated_by_boot_failure_or_repeated_boot',
                                                 'maximum_boot_failures',
                                                 'minimum_stable_health_seconds',
                                                 'permits_bound_to_actual_coordinator_instance',
                                                 'reconciliation_required_after_possible_dispatch',
                                                 'states'],
                               'durability': ['descriptor_lifecycle',
                                              'exclusive_coordinator_lease',
                                              'lease_release',
                                              'path_walk',
                                              'post_replace_failure',
                                              'publication',
                                              'replace_call_failure',
                                              'state_directory_mode',
                                              'state_file_mode'],
                               'fault_model': ['cutpoints',
                                               'missing_or_mismatched_slot',
                                               'torn_or_malformed_state'],
                               'non_claims': ['installed_qemu_update_executed',
                                              'physical_hardware_qualified',
                                              'production_signature_verified',
                                              'raw_power_loss_executed',
                                              'release_published'],
                               'signature_admission': ['default_admission_enabled',
                                                       'detached_signature_digest_required',
                                                       'external_monotonic_floor_persistence_implemented',
                                                       'maximum_public_key_bytes',
                                                       'maximum_signature_bytes',
                                                       'maximum_trust_roots',
                                                       'protected_floor_and_root_minimum_required',
                                                       'signing_preimage_domain',
                                                       'signing_preimage_encoding',
                                                       'trust_roots',
                                                       'trusted_clock_and_revalidation_before_commit',
                                                       'trusted_clock_and_revalidation_before_publication_and_boot',
                                                       'unknown_revoked_or_expired_signer_refused',
                                                       'unsigned_envelope_fields',
                                                       'verification',
                                                       'verification_environment',
                                                       'verification_input_custody',
                                                       'verification_input_seals',
                                                       'verifier_timeout_seconds'],
                               'signature_admission/verification_environment': ['LC_ALL',
                                                                                'OPENSSL_CONF',
                                                                                'PATH'],
                               'authority_ownership': ['callbacks',
                                                       'caller_verification_or_persistence_callbacks',
                                                       'configuration_types',
                                                       'fork_child_descriptor_cleanup_only',
                                                       'guard_before_authority_use',
                                                       'inherited_fork_authority',
                                                       'scope',
                                                       'thread_transfer_or_concurrent_use'],
                               'image_staging': ['active_slot_source_digest_verified',
                                                 'backend',
                                                 'coordinator_intent_recorded_before_replace_call',
                                                 'full_digest_and_length_verified_before_temp_write',
                                                 'post_replace_failure',
                                                 'production_activation_enabled',
                                                 'publication',
                                                 'reconciliation',
                                                 'replace_call_failure',
                                                 'retained_temp_and_named_inode_verified',
                                                 'slot_names',
                                                 'stream_chunk_bytes'],
                               'operator_recovery': ['action',
                                                     'bootloader_or_block_device_mutation',
                                                     'complete_source_digest_and_protected_floor_required',
                                                     'default_approved_operator_uids',
                                                     'identity',
                                                     'possible_dispatch_latch_clear'],
                               'journal_reconciliation': ['actual_issued_fact_and_current_record_identity_required',
                                                          'caller_digest_or_status_assertion_accepted',
                                                          'clear_target_phase',
                                                          'complete_bounded_record_required',
                                                          'default_authority_enabled',
                                                          'exact_fields',
                                                          'file_and_directory_fsync_before_fact_and_clear',
                                                          'installed_journal_authority_provisioned',
                                                          'operation_identity',
                                                          'private_retained_root_lease_and_record_inode_required',
                                                          'schema']}}}


# Reviewed G6 wrapper snapshot: every nested object is closed, and every leaf
# (including null, false defaults and source-only status) is fixed. API refresh
# only updates the registry; contract changes require a separate profile review.
CONTRACT_PROFILES["durable_update_owner"] = {'fields': ['artifacts',
            'claim_ceiling',
            'defaults',
            'history',
            'non_claims',
            'ownership',
            'public_api',
            'recovery',
            'schema',
            'stage',
            'staging',
            'status'],
 'objects': {'artifacts': ['dependency', 'documentation', 'implementation', 'tests'],
             'public_api': ['DurableUpdateOwner', 'errors', 'operation_fields', 'result_fields'],
             'public_api/DurableUpdateOwner': ['constructor', 'methods', 'properties'],
             'public_api/DurableUpdateOwner/methods': ['arm_first_boot',
                                                       'close',
                                                       'confirm_result',
                                                       'inspect',
                                                       'stage_image_file',
                                                       'verify_manifest'],
             'defaults': ['bootloader_effect_performed',
                          'clock',
                          'production_activation_enabled',
                          'protected_rollback_floor',
                          'signature_verifier',
                          'update_admission_enabled'],
             'ownership': ['authority_scope',
                           'fork_authority',
                           'fork_cleanup',
                           'garbage_collection',
                           'operation_and_result_acceptance',
                           'reentrant_callbacks',
                           'stores',
                           'verifier'],
             'history': ['admission_exact_fields',
                         'binding',
                         'clock',
                         'complete_readback',
                         'configuration_change',
                         'configuration_exact_fields',
                         'encoding',
                         'event_exact_fields',
                         'event_name_format',
                         'event_phases',
                         'event_schema',
                         'history_compaction_or_deletion',
                         'live_record_replacement',
                         'maximum_directory_entries',
                         'maximum_events',
                         'maximum_record_bytes',
                         'maximum_retained_scan_record_descriptors',
                         'operation_exact_fields',
                         'record_custody',
                         'record_mode',
                         'stage_receipt_exact_fields',
                         'state_directory_mode',
                         'transitions'],
             'history/transitions': ['arm_intent',
                                     'boot_policy_armed',
                                     'initial',
                                     'manifest_verified',
                                     'owner_clean',
                                     'owner_open',
                                     'stage_completed',
                                     'stage_intent'],
             'history/event_phases': ['arm_intent',
                                      'boot_policy_armed',
                                      'manifest_verified',
                                      'owner_clean',
                                      'owner_open',
                                      'stage_completed',
                                      'stage_intent'],
             'staging': ['admission',
                         'arm_first_boot',
                         'backend',
                         'caller_boot_health_commit_rollback_api',
                         'cutpoint_checks',
                         'maximum_image_bytes',
                         'pre_effect',
                         'publication',
                         'result',
                         'slot_names',
                         'stream_chunk_bytes'],
             'recovery': ['automatic_replay',
                          'automatic_resume',
                          'caller_digest_status_or_health_assertion_accepted',
                          'diagnostics',
                          'exact_fields',
                          'explicit_clean_close',
                          'file',
                          'gap_unknown_corrupt_or_substituted_record',
                          'known_durable_completion_response_unavailable',
                          'marker_binding',
                          'marker_clear_api',
                          'marker_write_failure',
                          'possibly_effectful_or_unconfirmed_completion_failure',
                          'schema',
                          'unclean_or_nonterminal_restart'],
             'non_claims': ['block_device_write',
                            'boot_commit_or_rollback_performed',
                            'installed_qemu_update_executed',
                            'installed_service_wiring',
                            'observed_installed_boot_or_health',
                            'physical_hardware_qualified',
                            'privileged_arbitrary_in_process_or_filesystem_writer_isolated',
                            'production_activation_enabled',
                            'production_signature_verified',
                            'production_trust_roots_provisioned',
                            'protected_monotonic_floor_storage',
                            'raw_power_loss_executed',
                            'real_bootloader_integration',
                            'release_published',
                            'trusted_production_clock_provisioned',
                            'whole_directory_rollback_protection']},
 'claims': {'schema': 'trillionnium.desktop.durable-update-owner.v1',
            'stage': 'G6',
            'status': 'source_and_host_candidate_only',
            'claim_ceiling': 'real_signed_regular_file_staging_with_durable_intent_no_installed_boot_or_release_qualification',
            'artifacts/implementation': 'platform/durable_update_owner.py',
            'artifacts/dependency': 'platform/update_recovery.py',
            'artifacts/tests': 'tests/test_durable_update_owner.py',
            'artifacts/documentation': 'docs/architecture/DURABLE_UPDATE_OWNER.md',
            'public_api/DurableUpdateOwner/constructor': ['state_root',
                                                          'slot_root',
                                                          'active_slot',
                                                          'current_version',
                                                          'current_image_sha256',
                                                          'signature_verifier',
                                                          'protected_rollback_floor',
                                                          'clock'],
            'public_api/DurableUpdateOwner/methods/verify_manifest': ['payload',
                                                                      'now_unix',
                                                                      'signature',
                                                                      'fault'],
            'public_api/DurableUpdateOwner/methods/stage_image_file': ['operation',
                                                                       'image_path',
                                                                       'now_unix',
                                                                       'state_fault',
                                                                       'slot_fault'],
            'public_api/DurableUpdateOwner/methods/arm_first_boot': ['operation', 'now_unix', 'fault'],
            'public_api/DurableUpdateOwner/methods/confirm_result': ['result'],
            'public_api/DurableUpdateOwner/methods/inspect': [],
            'public_api/DurableUpdateOwner/methods/close': [],
            'public_api/DurableUpdateOwner/properties': ['phase'],
            'public_api/operation_fields': ['operation_id', 'manifest_sha256', 'signature_sha256'],
            'public_api/result_fields': ['operation_id',
                                         'manifest_sha256',
                                         'event_sequence',
                                         'event_sha256',
                                         'phase',
                                         'target_slot',
                                         'image_sha256',
                                         'image_bytes',
                                         'slot_root_identity',
                                         'production_activation_enabled',
                                         'bootloader_effect_performed'],
            'public_api/errors': ['DurableUpdateError',
                                  'DurableRecoveryRequired',
                                  'DurableResultUnavailable'],
            'defaults/signature_verifier': None,
            'defaults/update_admission_enabled': False,
            'defaults/protected_rollback_floor': 'current_version_if_not_explicitly_configured',
            'defaults/clock': 'system_unix_time_requires_external_trust_for_installation',
            'defaults/production_activation_enabled': False,
            'defaults/bootloader_effect_performed': False,
            'ownership/stores': 'exact_bundled_AtomicStateStore_and_ImageSlotStore_created_by_owner',
            'ownership/verifier': 'exact_bundled_ExternalUpdateSignatureVerifier',
            'ownership/authority_scope': 'creating_process_and_creating_thread_only',
            'ownership/operation_and_result_acceptance': 'actual_retained_issuer_bound_object_identity_not_copies_hashes_or_status',
            'ownership/reentrant_callbacks': False,
            'ownership/fork_authority': False,
            'ownership/fork_cleanup': 'close_descriptor_copies_only_no_explicit_unlock_no_durable_event',
            'ownership/garbage_collection': 'descriptor_only_never_clean_close_or_recovery_acknowledgment',
            'history/event_schema': 'trillionnium.desktop.durable-update-event.v1',
            'history/event_name_format': 'update-event-%06d.json',
            'history/maximum_events': 256,
            'history/maximum_record_bytes': 65536,
            'history/maximum_directory_entries': 258,
            'history/maximum_retained_scan_record_descriptors': 257,
            'history/state_directory_mode': '0700',
            'history/record_mode': '0600',
            'history/record_custody': 'regular_one_link_owner_or_root_no_follow_retained_root_lease_and_named_inode',
            'history/encoding': 'canonical_ascii_json_sorted_keys_compact_no_nan_no_trailing_newline',
            'history/event_exact_fields': ['schema',
                                           'sequence',
                                           'previous_sha256',
                                           'owner_id',
                                           'kind',
                                           'phase',
                                           'observed_unix',
                                           'configuration',
                                           'operation',
                                           'stage_receipt',
                                           'production_activation_enabled',
                                           'bootloader_effect_performed'],
            'history/configuration_exact_fields': ['active_slot',
                                                   'current_version',
                                                   'current_image_sha256',
                                                   'protected_rollback_floor',
                                                   'trust_policy_sha256',
                                                   'state_root_identity',
                                                   'slot_root_identity'],
            'history/operation_exact_fields': ['operation_id',
                                               'owner_id',
                                               'ticket_sequence',
                                               'manifest',
                                               'signature_admission'],
            'history/admission_exact_fields': ['signer_id',
                                               'public_key_sha256',
                                               'signature_sha256',
                                               'signing_preimage_sha256',
                                               'trust_policy_sha256',
                                               'minimum_version',
                                               'verified_unix'],
            'history/stage_receipt_exact_fields': ['target_slot',
                                                   'image_sha256',
                                                   'image_bytes',
                                                   'manifest_sha256',
                                                   'signature_sha256',
                                                   'production_activation_enabled'],
            'history/transitions/initial': ['owner_open'],
            'history/transitions/owner_open': ['manifest_verified', 'owner_clean'],
            'history/transitions/manifest_verified': ['stage_intent'],
            'history/transitions/stage_intent': ['stage_completed'],
            'history/transitions/stage_completed': ['arm_intent'],
            'history/transitions/arm_intent': ['boot_policy_armed'],
            'history/transitions/boot_policy_armed': [],
            'history/transitions/owner_clean': ['owner_open'],
            'history/event_phases/owner_open': 'idle',
            'history/event_phases/manifest_verified': 'verified',
            'history/event_phases/stage_intent': 'stage_intent',
            'history/event_phases/stage_completed': 'staged',
            'history/event_phases/arm_intent': 'arm_intent',
            'history/event_phases/boot_policy_armed': 'boot_pending',
            'history/event_phases/owner_clean': 'closed',
            'history/binding': 'consecutive_sequence_previous_actual_canonical_sha256_unique_owner_id_complete_configuration_and_operation',
            'history/complete_readback': 'retain_every_scan_record_fd_fsync_leaf_and_directory_recheck_all_named_and_retained_metadata_root_lease_and_inventory',
            'history/live_record_replacement': 'refuse_even_if_complete_bytes_match_prior_record',
            'history/clock': 'nondecreasing_actual_configured_clock_events_no_authority_renewal_after_regression',
            'history/configuration_change': 'recovery_required_no_implicit_policy_migration',
            'history/history_compaction_or_deletion': False,
            'staging/backend': 'private_leased_regular_file_inactive_slot_only',
            'staging/slot_names': ['slot-A.img', 'slot-B.img'],
            'staging/maximum_image_bytes': 17179869184,
            'staging/stream_chunk_bytes': 1048576,
            'staging/admission': 'actual_detached_signature_verification_using_S11_external_roots_domain_and_sealed_memfds',
            'staging/pre_effect': 'complete_candidate_digest_length_and_durable_stage_intent_full_readback_before_concrete_slot_publication',
            'staging/cutpoint_checks': 'owner_and_complete_durable_intent_before_and_after_each_core_slot_fault_cutpoint',
            'staging/publication': 'complete_stream_digest_retained_temp_file_fsync_atomic_replace_directory_fsync_bound_readback',
            'staging/result': 'complete_durable_stage_completed_chain_and_actual_active_and_target_image_readback_current_signature_time_and_floor_then_final_history_readback',
            'staging/arm_first_boot': 'durable_arm_intent_before_in_memory_source_policy_then_durable_boot_policy_armed_no_bootloader_effect',
            'staging/caller_boot_health_commit_rollback_api': False,
            'recovery/schema': 'trillionnium.desktop.durable-update-recovery.v1',
            'recovery/file': 'update-recovery-required.json',
            'recovery/exact_fields': ['schema',
                                      'phase',
                                      'reason',
                                      'state_root_identity',
                                      'slot_root_identity',
                                      'history_count',
                                      'last_event_sha256',
                                      'operation_id',
                                      'production_activation_enabled',
                                      'bootloader_effect_performed'],
            'recovery/marker_binding': 'last_confirmed_actual_history_prefix_digest_and_operation_not_total_unconfirmed_files',
            'recovery/unclean_or_nonterminal_restart': 'persist_recovery_required_refuse_new_operation_no_ticket_or_result_reconstruction',
            'recovery/gap_unknown_corrupt_or_substituted_record': 'retain_evidence_refuse_no_repair_or_history_clear',
            'recovery/marker_write_failure': 'in_memory_recovery_required_confirmed_pending_chain_still_refuses_restart_marker_durability_not_claimed',
            'recovery/explicit_clean_close': 'only_idle_owner_no_admitted_or_staged_or_armed_update',
            'recovery/known_durable_completion_response_unavailable': 'DurableResultUnavailable_preserves_known_phase_no_replay_no_claim_of_caller_acknowledgment',
            'recovery/possibly_effectful_or_unconfirmed_completion_failure': 'DurableRecoveryRequired_preserve_intent_and_marker_no_replay',
            'recovery/diagnostics': 'bounded_complete_file_readback_without_issuing_resumed_operation_result_or_activation_permit',
            'recovery/automatic_replay': False,
            'recovery/automatic_resume': False,
            'recovery/caller_digest_status_or_health_assertion_accepted': False,
            'recovery/marker_clear_api': False,
            'non_claims/installed_service_wiring': False,
            'non_claims/installed_qemu_update_executed': False,
            'non_claims/real_bootloader_integration': False,
            'non_claims/observed_installed_boot_or_health': False,
            'non_claims/boot_commit_or_rollback_performed': False,
            'non_claims/block_device_write': False,
            'non_claims/raw_power_loss_executed': False,
            'non_claims/physical_hardware_qualified': False,
            'non_claims/production_signature_verified': False,
            'non_claims/production_trust_roots_provisioned': False,
            'non_claims/protected_monotonic_floor_storage': False,
            'non_claims/trusted_production_clock_provisioned': False,
            'non_claims/whole_directory_rollback_protection': False,
            'non_claims/privileged_arbitrary_in_process_or_filesystem_writer_isolated': False,
            'non_claims/release_published': False,
            'non_claims/production_activation_enabled': False}}

def read(root: Path, relative: str) -> str:
    if type(relative) is not str:
        raise ValueError("registry path must be a string")
    path = Path(relative)
    if path.is_absolute() or path.as_posix() != relative or any(part in {".", ".."} for part in relative.split("/")):
        raise ValueError("registry path is not a canonical repository-relative path")
    descriptor = open_regular_beneath(root, root / relative, label="platform registry input")
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if metadata.st_nlink != 1:
            raise ValueError("registered source must have one link")
        if metadata.st_size > MAX_BYTES:
            raise ValueError("registered source exceeds the byte bound")
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("registered source exceeds the byte bound")
    return data.decode("utf-8", "strict")


def public_method(name: str) -> bool:
    return not name.startswith("_") or (name.startswith("__") and name.endswith("__"))


def reject_conditional_api(node: ast.AST, *, class_scope: bool = False) -> None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if not node.name.startswith("_") or (class_scope and public_method(node.name)):
            raise ValueError("conditional public API declaration is unsupported; declare it directly")
        return  # Local declarations in a private function/class are not exports.
    if class_scope and isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and not node.target.id.startswith("_"):
        raise ValueError("conditional public field declaration is unsupported")
    for child in ast.iter_child_nodes(node):
        reject_conditional_api(child, class_scope=class_scope)


def api_inventory(source: str) -> list[dict]:
    """Inventory source-defined public signatures without importing the module."""
    tree = ast.parse(source)
    result = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            result.append({"kind": "function", "name": node.name, "async": isinstance(node, ast.AsyncFunctionDef),
                           "decorators": [ast.unparse(value) for value in node.decorator_list], "arguments": ast.unparse(node.args),
                           "returns": ast.unparse(node.returns) if node.returns else None})
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            fields, methods = [], []
            for member in node.body:
                if isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name) and not member.target.id.startswith("_"):
                    fields.append({"name": member.target.id, "type": ast.unparse(member.annotation),
                                   "default": ast.unparse(member.value) if member.value else None})
                elif isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and public_method(member.name):
                    methods.append({"name": member.name, "async": isinstance(member, ast.AsyncFunctionDef), "arguments": ast.unparse(member.args),
                                    "returns": ast.unparse(member.returns) if member.returns else None,
                                    "decorators": [ast.unparse(value) for value in member.decorator_list]})
                elif isinstance(member, ast.ClassDef) and not member.name.startswith("_"):
                    raise ValueError("nested public classes are unsupported; declare them directly")
                elif not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    reject_conditional_api(member, class_scope=True)
            result.append({"kind": "class", "name": node.name, "bases": [ast.unparse(value) for value in node.bases],
                           "decorators": [ast.unparse(value) for value in node.decorator_list],
                           "fields": fields, "methods": methods})
        elif not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            reject_conditional_api(node)
    return result


def refresh_registry(root: Path, original: str, value: dict) -> None:
    """Publish through a retained no-follow parent; never truncate an alias."""
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    if len(payload) > MAX_BYTES:
        raise ValueError("refreshed registry exceeds the byte bound before publication")
    temporary = ".platform-registry-" + secrets.token_hex(16)
    parent = os.open(root / "manifests", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    descriptor = None
    temporary_identity = None
    publication_attempted = False
    def identity(metadata):
        return metadata.st_dev, metadata.st_ino
    try:
        parent_identity = os.fstat(parent)
        registry_identity = os.stat("platform-mechanisms.v1.json", dir_fd=parent, follow_symlinks=False)
        def verify_parent():
            if identity(os.stat(root / "manifests", follow_symlinks=False)) != identity(parent_identity):
                raise ValueError("registry parent custody changed during refresh")
        def verify_original():
            verify_parent()
            if identity(os.stat("platform-mechanisms.v1.json", dir_fd=parent, follow_symlinks=False)) != identity(registry_identity) or read(root, REGISTRY) != original:
                raise ValueError("registry custody or bytes changed during refresh")
        verify_original()
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644, dir_fd=parent)
        temporary_identity = identity(os.fstat(descriptor))
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("registry refresh write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        verify_original()
        staged = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
        retained = os.fstat(descriptor)
        if identity(staged) != temporary_identity or staged.st_nlink != 1 or retained.st_nlink != 1 or retained.st_size != len(payload):
            raise ValueError("registry staged inode custody changed during refresh")
        publication_attempted = True
        os.replace(temporary, "platform-mechanisms.v1.json", src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
        verify_parent()
        published = os.stat("platform-mechanisms.v1.json", dir_fd=parent, follow_symlinks=False)
        if identity(published) != temporary_identity or read(root, REGISTRY).encode() != payload:
            raise ValueError("registry publication readback changed")
    except BaseException as error:
        if publication_attempted:
            raise ValueError("registry publication uncertain; inspect actual file before refreshing again") from error
        raise
    finally:
        try:
            if descriptor is not None:
                os.close(descriptor)
        finally:
            try:
                try:
                    current = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
                    if identity(current) == temporary_identity:
                        os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
            finally:
                os.close(parent)


# Independently reviewed read-only source inventory. This is not a seventh
# authority mechanism; --refresh-api cannot refresh this closed profile.
_READONLY_OBSERVER_INDEX = {'schema': 'trillionnium.desktop.update-observation-source-index.v1',
 'plan_revision': '2026-08-29-d6',
 'requirements': ['G6', 'D7', 'S11'],
 'implementation': 'platform/update_boot_observer.py',
 'entrypoint': 'tools/inspect_pending_update.py',
 'documentation': 'docs/architecture/UPDATE_BOOT_OBSERVER.md',
 'contract': 'contracts/update-boot-observer.v1.json',
 'tests': 'tests/test_update_boot_observer.py',
 'workflow': '.github/workflows/update-boot-observer.yml',
 'dependencies': ['platform/update_recovery.py', 'platform/durable_update_owner.py'],
 'claim_ceiling': 'source-only read-only locked structural journal and fixed actual kernel observations; no '
                  'signing, boot-image mapping, health, continuation, external effect, installed two-boot or '
                  'hardware qualification authority',
 'authority_mechanism': False,
 'production_activation_enabled': False}
_READONLY_OBSERVER_CONTRACT = {'schema': 'trillionnium.desktop.update-boot-observer-contract.v1',
 'status': 'SOURCE_CANDIDATE',
 'implementation': 'platform/update_boot_observer.py',
 'api': {'inspect_pending_update': "(state_root: 'Path', slot_root: 'Path') -> 'BootObservation'",
         'BootObservation.public_json': "(self) -> 'bytes'",
         'BootObservation.private_json': "(self) -> 'bytes'"},
 'observation_schema': 'trillionnium.desktop.update-boot-observation.v1',
 'public_fields': ['booted_image_verified',
                   'bootloader_effect_performed',
                   'continuation_authorized',
                   'production_activation_enabled',
                   'reason_codes',
                   'schema',
                   'signature_authority',
                   'signed_boot_image_mapping',
                   'status'],
 'status_codes': ['no_pending_update', 'pending_identity_unknown', 'recovery_required', 'observation_unavailable'],
 'reason_codes': ['owner_busy',
                  'custody_unavailable',
                  'journal_invalid',
                  'kernel_observation_unavailable',
                  'kernel_observation_changed',
                  'unfinished_owner',
                  'recovery_marker_present',
                  'signature_authority_unavailable',
                  'signed_boot_image_mapping_unknown'],
 'limits': {'events': 256,
            'record_bytes': 65536,
            'mountinfo_bytes': 524288,
            'mounts': 4096,
            'private_diagnostic_bytes': 65536,
            'absolute_path_components': 32},
 'kernel_sources': ['/proc/self',
                    '/proc/sys/kernel/random/boot_id',
                    '/proc/<creator-pid>/mountinfo',
                    '/proc/<creator-pid>/ns/mnt',
                    '/'],
 'kernel_measurement': {'filesystem_magic': {'procfs': 40864, 'nsfs': 1853056627},
                        'samples': 'before and after the complete scan; exact boot id, namespace identity, root '
                                   'device/inode and mountinfo bytes digest must match',
                        'root_mapping': 'one root mount with the actual root st_dev major/minor; no mapping to a '
                                        'signed image or slot',
                        'procfs_zero_size': 'bounded fixed procfs reads only; ordinary journal/image files must '
                                            'have positive size'},
 'custody': {'existing_roots': 'absolute bounded nofollow component walk; final private directory owned by root '
                               'or actual euid; retain directory descriptors',
             'existing_leases': 'open the exact named .coordinator.lock inode read-only, one private regular hard '
                                'link; LOCK_SH|LOCK_NB on both state and slots; retain and compare named inode '
                                'before completion',
             'writer_exclusion': 'the existing coordinator uses LOCK_EX on the same named inode; busy is typed '
                                 'and no repair is attempted',
             'journal': 'canonical closed JSON; complete consecutive sha256 chain, source transitions, original '
                        'root identities, immutable operation and receipt bindings, marker confirmed prefix; '
                        'retain every opened record until final fstat/named-leaf and inventory checks',
             'slot_files': 'private 0600 regular single-link slot-A.img and slot-B.img; bounded positive size; '
                           'retained inode/size/mtime/ctime only; no image reads or hashes',
             'process_thread': 'scan methods check actual creator PID and thread before descriptor acquisition or '
                               'inspection',
             'cleanup': 'detach each owned descriptor before close; attempt all retained descriptors; fork and GC '
                        'only close copied descriptors and never explicitly unlock or write',
             'interruption_scope': 'finite tested read/substitution/fork/close-and-reuse boundaries; not every '
                                   'C-to-Python-store or asynchronous interruption window'},
 'cli': {'entrypoint': 'tools/inspect_pending_update.py',
         'arguments': ['--state-root', '--slot-root', '--output'],
         'default': 'read-only; stdout contains only the public closed enum/false-claim object',
         'raw_output': 'only explicit --output; exclusive nofollow new 0600 file under a pre-existing private '
                       'retained parent, outside authority-root ancestry; same-fd fsync/readback and final '
                       'metadata checks; no overwrite or recursive creation',
         'exit_codes': {'no_pending_update': 0, 'unknown_recovery_unavailable_output_or_argument_refusal': 2}},
 'claims': {'approved_roots': [],
            'signature_authority': 'unavailable',
            'signed_boot_image_mapping': 'unknown',
            'booted_image_verified': False,
            'continuation_authorized': False,
            'production_activation_enabled': False,
            'bootloader_effect_performed': False,
            'health_qualified': False,
            'installed_two_boot_qualified': False,
            'hardware_power_loss_qualified': False},
 'remaining_installed_obligations': ['persisted detached signature plus separately provisioned production '
                                     'public-root policy and protected version/time anchors',
                                     'immutable signed-image-to-actual-root/block-device mapping before any '
                                     'resume or effect; writable ext4 observation is insufficient',
                                     'installed bootloader arm, root selection, monotonic measured health, '
                                     'durable commit/rollback and authenticated operator recovery',
                                     'separate actual QEMU two-boot update/recovery corpus and hardware power-cut '
                                     'qualification']}
_READONLY_OBSERVER_API = [{'kind': 'class',
  'name': 'ObservationStatus',
  'bases': ['str', 'Enum'],
  'decorators': [],
  'fields': [],
  'methods': []},
 {'kind': 'class',
  'name': 'ObservationReason',
  'bases': ['str', 'Enum'],
  'decorators': [],
  'fields': [],
  'methods': []},
 {'kind': 'class',
  'name': 'BootObservation',
  'bases': [],
  'decorators': ['dataclass(frozen=True)'],
  'fields': [{'name': 'status', 'type': 'ObservationStatus', 'default': None},
             {'name': 'reasons', 'type': 'tuple[ObservationReason, ...]', 'default': None}],
  'methods': [{'name': 'public_json', 'async': False, 'arguments': 'self', 'returns': 'bytes', 'decorators': []},
              {'name': 'private_json',
               'async': False,
               'arguments': 'self',
               'returns': 'bytes',
               'decorators': []}]},
 {'kind': 'function',
  'name': 'inspect_pending_update',
  'async': False,
  'decorators': [],
  'arguments': 'state_root: Path, slot_root: Path',
  'returns': 'BootObservation'}]


def _readonly_observer(root: Path) -> set[str]:
    relative = "manifests/update-observation.v1.json"
    registered_paths = [relative, *[_READONLY_OBSERVER_INDEX[field] for field in
                        ("implementation", "entrypoint", "documentation", "contract", "tests", "workflow")]]
    # Legacy six-mechanism snapshots remain valid. A partial new package cannot
    # hide an unregistered source or skip the independent complete profile.
    if not any(os.path.lexists(root / path) for path in registered_paths):
        return set()
    index = load_json_strict(read(root, relative))
    canonical = lambda value: json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if canonical(index) != canonical(_READONLY_OBSERVER_INDEX):
        raise ValueError("read-only observer source index identity, paths or claim ceiling changed")
    contract = load_json_strict(read(root, index["contract"]))
    if canonical(contract) != canonical(_READONLY_OBSERVER_CONTRACT):
        raise ValueError("read-only observer contract fields, API or claim ceiling changed")
    source = read(root, index["implementation"])
    if api_inventory(source) != _READONLY_OBSERVER_API:
        raise ValueError("read-only observer public API inventory drift")
    document = read(root, index["documentation"])
    if not document.startswith("# ") or index["implementation"] not in document:
        raise ValueError("read-only observer documentation source mapping changed")
    read(root, index["entrypoint"])
    workflow = read(root, index["workflow"])
    if "test_update_boot_observer.py" not in workflow or "result.skipped" not in workflow:
        raise ValueError("read-only observer actual non-skipping corpus workflow is absent")
    tests = ast.parse(read(root, index["tests"]))
    cases = [node for node in tests.body if isinstance(node, ast.ClassDef)
             and any(ast.unparse(base) == "unittest.TestCase" for base in node.bases)]
    if not any(isinstance(member, ast.FunctionDef) and member.name.startswith("test_")
               for case in cases for member in case.body):
        raise ValueError("read-only observer regression source is absent")
    return {index["implementation"]}



_AUTHENTICATED_UPDATE_INDEX = {'schema': 'trillionnium.desktop.authenticated-update-source-index.v2',
 'plan_revision': '2026-08-29-d6',
 'requirements': ['G6', 'D7', 'S11'],
 'implementations': ['platform/authenticated_update_owner.py',
                     'platform/authenticated_update_observer.py'],
 'documentation': 'docs/architecture/AUTHENTICATED_UPDATE_READBACK.md',
 'contract': 'contracts/authenticated-update.v2.json',
 'tests': 'tests/test_authenticated_update_readback.py',
 'workflow': '.github/workflows/authenticated-update-readback.yml',
 'dependencies': ['platform/update_recovery.py',
                  'platform/durable_update_owner.py',
                  'platform/update_boot_observer.py'],
 'claim_ceiling': 'source_and_host_exact_persisted_detached_signature_and_regular_file_slot_readback_no_boot_health_replay_or_installed_qualification',
 'authority_mechanism': False,
 'production_activation_enabled': False}
_AUTHENTICATED_UPDATE_CONTRACT = {'schema': 'trillionnium.desktop.authenticated-update-contract.v2',
 'status': 'SOURCE_CANDIDATE',
 'domains': {'event': 'trillionnium.desktop.durable-update-event.v2',
             'capsule': 'trillionnium.desktop.update-signature-capsule.v2',
             'signature': 'trillionnium.desktop.update-manifest-signature.v1\\0',
             'readback': 'trillionnium.desktop.authenticated-update-readback.v2',
             'owner_diagnostic': 'trillionnium.desktop.authenticated-update-owner.v2'},
 'api': {'AuthenticatedUpdateOwner': 'inherits exact DurableUpdateOwner v1 constructor, methods, '
                                     'operation and result objects; profile-specific private hooks '
                                     'only',
         'inspect_authenticated_update': "(state_root: 'Path', slot_root: 'Path', *, "
                                         'signature_verifier, clock, protected_rollback_floor: '
                                         "'int') -> 'AuthenticatedUpdateReadback'",
         'AuthenticatedUpdateReadback.public_json': "(self) -> 'bytes'",
         'AuthenticatedUpdateReadback.private_json': "(self) -> 'bytes'",
         'fact_construction': 'observer factory only; dataclass init disabled; creator PID/thread '
                              'required for delivery; no API consumes it as permission'},
 'public_fields': ['booted_image_verified',
                   'bootloader_effect_performed',
                   'continuation_authorized',
                   'health_qualified',
                   'production_activation_enabled',
                   'reason_codes',
                   'schema',
                   'signatures_verified',
                   'signed_boot_image_mapping',
                   'status',
                   'stored_slot_images_verified'],
 'status_codes': ['no_pending_update',
                  'pending_identity_unknown',
                  'recovery_required',
                  'observation_unavailable'],
 'reason_codes': ['external_signature_configuration_unavailable',
                  'no_signed_pending_operation',
                  'legacy_detached_signature_unavailable',
                  'staging_completion_unconfirmed',
                  'signed_boot_image_mapping_unknown',
                  'recovery_marker_present',
                  'journal_invalid',
                  'custody_unavailable',
                  'owner_busy',
                  'kernel_observation_unavailable',
                  'kernel_observation_changed',
                  'persisted_signature_or_image_refused',
                  'unfinished_owner'],
 'limits': {'events': 256,
            'record_bytes': 65536,
            'exact_manifest_bytes': 16384,
            'exact_signature_bytes': 16384,
            'capsules': 1,
            'v2_directory_entries': 259,
            'v2_retained_scan_records': 258,
            'v1_directory_entries_unchanged': 258,
            'v1_retained_scan_records_unchanged': 257,
            'image_bytes': 17179869184,
            'image_stream_chunk_bytes': 1048576,
            'private_diagnostic_bytes': 65536},
 'capsule': {'name': 'update-signature-<operation_id>.json',
             'mode': '0600',
             'root_mode': '0700',
             'exact_fields': ['schema',
                              'operation_id',
                              'owner_id',
                              'configuration',
                              'signature_admission',
                              'manifest_bytes_b64',
                              'signature_bytes_b64'],
             'reference_exact_fields': ['name',
                                        'sha256',
                                        'manifest_bytes_sha256',
                                        'signature_sha256'],
             'event_operation_fields': 'exact v1 operation fields plus signature_capsule; all '
                                       'subsequent phases retain identical complete reference',
             'binding': 'canonical capsule digest, exact original byte digests, owner, operation, '
                        'complete policy/admission/configuration and actual state/slot root '
                        'identities',
             'publication': 'before manifest_verified; exact private one-link nofollow retained '
                            'inode fsync and directory fsync readback using concrete '
                            'AtomicStateStore; no overwrite of named capsule',
             'restart_orphan': 'capsule without its complete v2 operation is unknown evidence; '
                               'refuse and retain, never adopt or replay',
             'encoding': 'canonical ASCII JSON, canonical padded base64 of exact byte envelopes; '
                         'no normalization of original manifest bytes'},
 'verification': {'default_roots': [],
                  'configured_roots': 'separately approved exact bundled '
                                      'ExternalUpdateSignatureVerifier; no key in capsule is '
                                      'authoritative',
                  'native_process': 'actual /usr/bin/openssl with v1 detached signature domain and '
                                    'sealed memfd preimage/signature/approved public key snapshots',
                  'policy': 'current separately supplied policy must equal history configuration '
                            'and actual admission '
                            'signer/key/signature/preimage/policy/minimum_version fields',
                  'anchors': 'explicit trusted configuration clock and protected floor; initial '
                             'time at least original admission and last event; nondecreasing final '
                             'time and current root/manifest validity; floor cannot weaken '
                             'recorded or actual signer minimum',
                  'slots': 'complete bounded actual active digest and target digest/length '
                           'readback through private retained named single-link 0600 descriptors; '
                           'no mapping of kernel root to either signed slot',
                  'final_readback': 'complete retained event/capsule/image/root/lease metadata and '
                                    'inventory before and after trusted final clock callback; '
                                    'exact fixed kernel samples before and after read scan',
                  'failure': 'signature, custody, interruption, stale policy, time or floor '
                             'refusal cannot become a success fact, owner permit or effect'},
 'compatibility': {'v1_record_reading': 'structural history only; old pending v1 never becomes '
                                        'cryptographic authority',
                   'v1_to_v2': 'only new owner_open after clean prior owner; no within-operation '
                               'schema migration',
                   'v1_tools': 'unchanged v1 structural observer rejects v2 evidence rather than '
                               'claiming success',
                   'v1_tests': 'unchanged test bodies and fixed v1 record/directory/descriptor '
                               'budgets'},
 'custody': {'reader': 'unchanged bundled read-only observer component walk and shared nonblocking '
                       'named leases; never constructs writable stores',
             'cleanup': 'retain managed record/image descriptors through final checks; '
                        'detach-before-close all acquired descriptors; fork cleanup never LOCK_UN '
                        'or writes',
             'creator_scope': 'actual creating process and thread; forked or foreign thread '
                              'verifier/readback delivery refuses',
             'interruption_scope': 'finite actual OpenSSL/FS/substitution/fork/read interruption '
                                   'boundaries, not every asynchronous C-to-Python-store window'},
 'claims': {'signature_and_stored_slot_readback': 'only after complete current actual OpenSSL and '
                                                  'actual stored file readback',
            'signed_boot_image_mapping': 'unknown',
            'booted_image_verified': False,
            'health_qualified': False,
            'continuation_authorized': False,
            'automatic_replay': False,
            'automatic_resume': False,
            'caller_health_commit_accepted': False,
            'bootloader_effect_performed': False,
            'production_activation_enabled': False,
            'installed_two_boot_qualified': False,
            'hardware_power_loss_qualified': False,
            'production_trust_roots_provisioned': False,
            'protected_monotonic_floor_storage': False,
            'trusted_production_clock_provisioned': False,
            'whole_directory_rollback_protection': False,
            'privileged_arbitrary_in_process_or_filesystem_writer_isolated': False},
 'remaining_installed_obligations': ['separately provisioned production roots and protected '
                                     'monotonic version/time anchors',
                                     'immutable signed image to actual root/block device mapping',
                                     'installed bootloader arm and root selection, measured '
                                     'monotonic health, durable commit/rollback and independently '
                                     'authorized recovery',
                                     'actual QEMU two-boot corpus and physical hardware '
                                     'power-cut/long-duration qualification']}
_AUTHENTICATED_UPDATE_API = {'platform/authenticated_update_owner.py': [{'kind': 'class',
                                             'name': 'AuthenticatedUpdateOwner',
                                             'bases': ['durable.DurableUpdateOwner'],
                                             'decorators': [],
                                             'fields': [],
                                             'methods': []}],
 'platform/authenticated_update_observer.py': [{'kind': 'class',
                                                'name': 'AuthenticatedUpdateReadback',
                                                'bases': [],
                                                'decorators': ['dataclass(frozen=True, '
                                                               'init=False)'],
                                                'fields': [{'name': 'status',
                                                            'type': 'str',
                                                            'default': None},
                                                           {'name': 'reason_codes',
                                                            'type': 'tuple[str, ...]',
                                                            'default': None},
                                                           {'name': 'signatures_verified',
                                                            'type': 'bool',
                                                            'default': None},
                                                           {'name': 'stored_slot_images_verified',
                                                            'type': 'bool',
                                                            'default': None}],
                                                'methods': [{'name': '__post_init__',
                                                             'async': False,
                                                             'arguments': 'self',
                                                             'returns': None,
                                                             'decorators': []},
                                                            {'name': '__getattribute__',
                                                             'async': False,
                                                             'arguments': 'self, name',
                                                             'returns': None,
                                                             'decorators': []},
                                                            {'name': 'public_json',
                                                             'async': False,
                                                             'arguments': 'self',
                                                             'returns': 'bytes',
                                                             'decorators': []},
                                                            {'name': 'private_json',
                                                             'async': False,
                                                             'arguments': 'self',
                                                             'returns': 'bytes',
                                                             'decorators': []}]},
                                               {'kind': 'function',
                                                'name': 'inspect_authenticated_update',
                                                'async': False,
                                                'decorators': [],
                                                'arguments': 'state_root: Path, slot_root: Path, '
                                                             '*, signature_verifier, clock, '
                                                             'protected_rollback_floor: int',
                                                'returns': 'AuthenticatedUpdateReadback'}]}

def _authenticated_update(root: Path) -> set[str]:
    relative = "manifests/authenticated-update.v2.json"
    registered = [relative, *_AUTHENTICATED_UPDATE_INDEX["implementations"],
                  *[_AUTHENTICATED_UPDATE_INDEX[field] for field in ("documentation", "contract", "tests", "workflow")]]
    if not any(os.path.lexists(root / path) for path in registered):
        return set()
    canonical = lambda value: json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    index = load_json_strict(read(root, relative))
    if canonical(index) != canonical(_AUTHENTICATED_UPDATE_INDEX):
        raise ValueError("authenticated update source index identity, mappings or claim ceiling changed")
    contract = load_json_strict(read(root, index["contract"]))
    if canonical(contract) != canonical(_AUTHENTICATED_UPDATE_CONTRACT):
        raise ValueError("authenticated update profile, limits, claims or domain changed")
    for path, expected in _AUTHENTICATED_UPDATE_API.items():
        if api_inventory(read(root, path)) != expected:
            raise ValueError("authenticated update API inventory drift")
    document = read(root, index["documentation"])
    if not document.startswith("# ") or not all(path in document for path in index["implementations"]):
        raise ValueError("authenticated update source documentation mapping changed")
    tests = ast.parse(read(root, index["tests"]))
    cases = [node for node in tests.body if isinstance(node, ast.ClassDef)
             and any(ast.unparse(base) == "unittest.TestCase" for base in node.bases)]
    if not any(isinstance(member, ast.FunctionDef) and member.name.startswith("test_")
               for case in cases for member in case.body):
        raise ValueError("authenticated update actual regression source absent")
    workflow = read(root, index["workflow"])
    if "test_authenticated_update_readback.py" not in workflow or "result.skipped" not in workflow:
        raise ValueError("authenticated update actual non-skipping corpus workflow absent")
    return set(index["implementations"])


def validate(root: Path, *, refresh: bool = False) -> dict:
    original = read(root, REGISTRY)
    value = load_json_strict(original)
    if type(value) is not dict or set(value) != {"schema", "claim_ceiling", "qualification_changed", "modules"}:
        raise ValueError("platform registry has an open or malformed field set")
    if value["schema"] != "trillionnium.desktop.platform-mechanisms.v1" or value["claim_ceiling"] != "source_contract_and_api_inventory_only":
        raise ValueError("platform registry identity or claim ceiling changed")
    if value["qualification_changed"] is not False or type(value["modules"]) is not list or len(value["modules"]) != len(MODULES):
        raise ValueError("platform registry is not the closed source-only candidate inventory")
    seen, implementations = set(), set()
    for module in value["modules"]:
        if type(module) is not dict or set(module) != FIELDS or type(module["id"]) is not str or module["id"] not in MODULES or module["id"] in seen:
            raise ValueError("platform mechanism identity is missing, unknown or duplicated")
        seen.add(module["id"])
        source_name, doc_name, contract_name, test_name, requirements = EXPECTED_MODULES[module["id"]]
        expected = {"requirements": requirements, "implementation": f"platform/{source_name}.py",
                    "documentation": f"docs/architecture/{doc_name}.md", "contract": f"contracts/{contract_name}.v1.json",
                    "tests": f"tests/{test_name}.py"}
        if any(module[field] != expected_value for field, expected_value in expected.items()):
            raise ValueError("platform mechanism requirement or source mapping changed")
        implementation = module["implementation"]
        if type(implementation) is not str or not implementation.startswith("platform/") or not implementation.endswith(".py") or implementation in implementations:
            raise ValueError("platform implementation registration is invalid")
        implementations.add(implementation)
        inventory = api_inventory(read(root, implementation))
        if refresh:
            module["source_defined_api"] = inventory
        elif module["source_defined_api"] != inventory:
            raise ValueError(f"public API inventory drift: {implementation}")
        document = read(root, module["documentation"])
        contract = load_json_strict(read(root, module["contract"]))
        tests = ast.parse(read(root, module["tests"]))
        if type(contract) is not dict or type(contract.get("schema")) is not str:
            raise ValueError("registered mechanism contract is invalid")
        profile = CONTRACT_PROFILES[module["id"]]
        if set(contract) != set(profile["fields"]):
            raise ValueError("registered contract has an open or changed field set")
        for object_path, fields in profile["objects"].items():
            observed = contract
            for part in object_path.split("/"):
                if type(observed) is not dict or part not in observed:
                    raise ValueError("registered contract object path is missing")
                observed = observed[part]
            if type(observed) is not dict or set(observed) != set(fields):
                raise ValueError("registered contract nested object has an open or changed field set")
        for claim_path, expected_claim in profile["claims"].items():
            observed = contract
            for part in claim_path.split("/"):
                if type(observed) is not dict or part not in observed:
                    raise ValueError("registered contract claim path is missing")
                observed = observed[part]
            if type(observed) is not type(expected_claim) or observed != expected_claim:
                raise ValueError("registered contract identity, default or claim ceiling changed")
        if contract.get("implementation", implementation) != implementation:
            raise ValueError("mechanism contract references a different implementation")
        if not document.startswith("# ") or implementation not in document:
            raise ValueError("technical document does not identify its implementation")
        cases = [node for node in tests.body if isinstance(node, ast.ClassDef)
                 and any(ast.unparse(base) == "unittest.TestCase" for base in node.bases)]
        if not any(isinstance(member, ast.FunctionDef) and member.name.startswith("test_")
                   for case in cases for member in case.body):
            raise ValueError("registered test source has no direct unittest.TestCase test methods")
    implementations.update(_readonly_observer(root))
    implementations.update(_authenticated_update(root))
    actual = {path.relative_to(root).as_posix() for path in (root / "platform").glob("*.py") if path.name != "__init__.py"}
    if actual != implementations:
        raise ValueError("top-level platform module is unregistered or absent")
    if refresh:
        refresh_registry(root, original, value)
    return {"schema": "trillionnium.desktop.platform-source-validation.v1", "status": "PASS_SOURCE_INVENTORY",
            "registered_modules": len(seen), "execution_observed": False, "qualification_changed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-api", action="store_true", help="refresh signatures after a reviewed public API change")
    args = parser.parse_args()
    try:
        result = validate(ROOT, refresh=args.refresh_api)
    except (OSError, UnicodeError, SyntaxError, ValueError, TypeError) as error:
        parser.exit(1, f"platform mechanism source validation failed: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
