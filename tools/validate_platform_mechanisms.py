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
MODULES = {"signed_apps", "app_storage", "taskflow", "controlled_egress", "signed_update"}
EXPECTED_MODULES = {
    "signed_apps": ("trusted_apps", "TRUSTED_APP_BUNDLES", "trusted-app-bundle", "test_trusted_apps", ["G5", "D5"]),
    "app_storage": ("app_storage", "APP_STORAGE", "app-storage", "test_app_storage", ["G5", "D5"]),
    "taskflow": ("taskflow", "TASKFLOW_CAPABILITIES", "taskflow-execution", "test_taskflow", ["G5", "D6"]),
    "controlled_egress": ("controlled_egress", "CONTROLLED_EGRESS", "controlled-egress", "test_controlled_egress", ["G5", "D6"]),
    "signed_update": ("update_recovery", "S11_UPDATE_RECOVERY", "s11-update-recovery", "test_s11_update_recovery", ["G6", "D7", "S11"]),
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
                                                 'clock',
                                                 'configuration',
                                                 'hosts',
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
                                               'durable_delivery_or_external_effect_proof',
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
    parent = os.open(root / "manifests", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    temporary = ".platform-registry-" + secrets.token_hex(16)
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
        payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
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
