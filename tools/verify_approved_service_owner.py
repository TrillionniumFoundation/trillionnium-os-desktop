#!/usr/bin/env python3
"""Finite FOUNDATION source profile; kernel/runtime/installed facts stay separate.

Raw hashes bind all literals, attributes and macros. The supplemental finite
Rust inventory documents the reviewed opaque API; it is not a Rust compiler.
Legacy inverse accepts only the old source or one exact reviewed tail append.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

try:
    from . import verify_approved_native_startup as source_gate
except ImportError:
    import verify_approved_native_startup as source_gate

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/approved-service-owner-foundation.v2.json"
CORE = "crates/hepta-peer-attestation/src/approved_policy/service_policy.rs"
CREATOR = "crates/hepta-peer-attestation/src/approved_policy/service_policy/creator_context.rs"
EXPECTED = {'schema': 'trillionnium.desktop.approved-service-owner-foundation.v2',
 'status': 'FOUNDATION_SOURCE_ONLY',
 'requirements': ['G1', 'G2'],
 'platform': 'Linux',
 'default_product_activation': False,
 'policy': {'schema': 'trillionnium.approved-mechanisms.v2',
            'default_path': '/etc/hepta/approved-mechanisms.v2.conf',
            'maximum_bytes': 8192,
            'fields': ['schema',
                       'control.uid',
                       'control.gid',
                       'control.unit',
                       'control.cgroup',
                       'control.elf_sha256',
                       'control.principal_id',
                       'agent.uid',
                       'agent.gid',
                       'agent.unit',
                       'agent.cgroup',
                       'agent.elf_sha256',
                       'agent.principal_id',
                       'owner.uid',
                       'owner.gid',
                       'owner.unit',
                       'owner.cgroup',
                       'owner.elf_sha256',
                       'owner.principal_id'],
            'distinct_principal_ids': True,
            'source': 'root_owned_nofollow_retained_directory_and_leaf_full_identity_and_digest',
            'canonical_ascii_lines': True,
            'numeric_ids': 'canonical_decimal_u32_excluding_MAX',
            'bounds': {'path_bytes': 1024,
                       'path_components': 32,
                       'unit_bytes': 128,
                       'cgroup_bytes': 512,
                       'component_bytes': 128,
                       'principal_bytes': 64,
                       'elf_hex_bytes': 64}},
 'public_api': {'ApprovedServicePolicyDocument::open_default': 'pub fn open_default ( ) - > Result < Self , '
                                                               'ApprovedPolicyError >',
                'ApprovedServicePolicyDocument::open_root_owned': 'pub fn open_root_owned ( path : & Path ) '
                                                                  '- > Result < Self , ApprovedPolicyError >',
                'ApprovedServicePolicyDocument::ensure_current': 'pub fn ensure_current ( & self ) - > '
                                                                 'Result < ( ) , ApprovedPolicyError >',
                'ApprovedServicePolicyDocument::select_current_owner': 'pub fn select_current_owner ( & self '
                                                                       ') - > Result < '
                                                                       'ApprovedServiceOwnerBinding , '
                                                                       'ApprovedPolicyError >',
                'ApprovedServiceOwnerBinding::ensure_current': 'pub fn ensure_current ( & self ) - > Result '
                                                               '< ( ) , ApprovedPolicyError >',
                'ApprovedServiceOwnerBinding::verifier': 'pub fn verifier ( & self ) - > Result < '
                                                         'ApprovedServiceOwnerVerifier , ApprovedPolicyError '
                                                         '>',
                'ApprovedServiceOwnerVerifier::ensure_current': 'pub fn ensure_current ( & self ) - > Result '
                                                                '< ( ) , ApprovedPolicyError >'},
 'opaque_types': {'ApprovedServicePolicyDocument': 'state:Arc<ServiceState>,',
                  'ApprovedServiceOwnerBinding': 'state:Arc<ServiceState>,original:PeerRequestCustody,',
                  'ApprovedServiceOwnerVerifier': 'state:Arc<ServiceState>,original:crate::PeerRequestVerifier,'},
 'creator': {'capture_before_policy_IO': True,
             'ordinary_pid_mismatch_before_FD_access': True,
             'numeric_collision_checks_private_socket_endpoints_and_fixed_pid_namespace': True,
             'actual_endpoint_fields': ['device', 'inode', 'cookie', 'SO_PEERCRED', 'FD_CLOEXEC', 'SO_TYPE'],
             'namespace_path': '/proc/thread-self/ns/pid',
             'namespace_kind': 'NS_GET_NSTYPE_CLONE_NEWPID',
             'namespace_follow': 'intentional_fixed_proc_magic_link',
             'numeric_collision_FD_free': False,
             'creator_credentials': 'creation_time_cached_peer_credentials_not_live_owner_authority'},
 'owner': {'selection': 'one_CAS_attempt_per_ServiceState',
           'global_principal_singleton': False,
           'observed_fields_mint_policy': False,
           'caller_attestor_or_snapshot': False,
           'fixed_attestor': 'ProcfsPeerAttestor::default().attest(Live)',
           'original_custody': 'PeerRequestCustody',
           'drop_binding': 'sequential_verifiers_refuse_after_original_custody_drop',
           'drop_document': 'binding_retains_same_source',
           'drop_verifier': 'does_not_revoke_binding',
           'source_failure': 'sticky_retirement_same_creating_process',
           'foreign_process_failure': 'ProcessChanged_parent_not_retired',
           'overlapping_revoke_completion_guarantee': False},
 'errors': {'InvalidConfiguration': 'strict_policy_or_path_shape_refused',
            'SourceRefused': 'root_source_or_kernel_creator_resource_cannot_be_acquired_or_checked',
            'Changed': 'source_identity_digest_namespace_or_creator_resource_changed_or_retired',
            'ProcessChanged': 'original_creator_numeric_or_actual_creator_context_refused',
            'PeerRefused': 'second_selection_owner_identity_pin_original_custody_or_current_peer_refused',
            'DeadlineExceeded': 'legacy_variant_not_new_source_lifetime_authority'},
 'legacy_inverse': {'crates/hepta-peer-attestation/src/lib.rs': {'bytes': 61121,
                                                                 'sha256': '91a879f50a94954a6679ee5e973eb70f0aa3c086743c83e9c2858091a8ff6210',
                                                                 'tail': '\n'
                                                                         '#[cfg(target_os = "linux")]\n'
                                                                         'pub use approved_policy::{\n'
                                                                         '    ApprovedServiceOwnerBinding, '
                                                                         'ApprovedServiceOwnerVerifier, '
                                                                         'ApprovedServicePolicyDocument,\n'
                                                                         '    '
                                                                         'DEFAULT_APPROVED_SERVICE_POLICY_PATH, '
                                                                         'MAX_APPROVED_SERVICE_POLICY_BYTES,\n'
                                                                         '};\n'},
                    'crates/hepta-peer-attestation/src/approved_policy.rs': {'bytes': 28173,
                                                                             'sha256': '0a6a079336ad842bc55c34fe3930707ece098182bd976e78c2dfb21e18d87882',
                                                                             'tail': '\n'
                                                                                     '// Additive '
                                                                                     'service-policy v2; '
                                                                                     'original '
                                                                                     'request-scoped v1 '
                                                                                     'stays unchanged.\n'
                                                                                     'mod service_policy;\n'
                                                                                     'pub use '
                                                                                     'service_policy::{\n'
                                                                                     '    '
                                                                                     'ApprovedServiceOwnerBinding, '
                                                                                     'ApprovedServiceOwnerVerifier, '
                                                                                     'ApprovedServicePolicyDocument,\n'
                                                                                     '    '
                                                                                     'DEFAULT_APPROVED_SERVICE_POLICY_PATH, '
                                                                                     'MAX_APPROVED_SERVICE_POLICY_BYTES,\n'
                                                                                     '};\n'}},
 'whole_source_sha256': {'crates/hepta-peer-attestation/src/approved_policy/service_policy.rs': 'a8f710d4f0cab66e6a8753807d543de63ba67e45cdf598f3099f0cf254e7c659',
                         'crates/hepta-peer-attestation/src/approved_policy/service_policy/creator_context.rs': '31c3b36ecb47b700b08df7e374b6ceadddb44527acf1ae6d8c5efb83a090eb06'},
 'preserved_source_sha256': {'crates/hepta-peer-attestation/src/request_lease.rs': '54b80b2e94f4dc149d9af8f6e92815a2a8b88a9db987c34ec9a0b59d53850681'},
 'kernel_corpus': {'path': 'crates/hepta-peer-attestation/tests/approved_service_owner_kernel.rs',
                   'harness': False,
                   'groups': 12,
                   'source_continuity_seconds_minimum': 61,
                   'transient_unit_runtime_maximum_seconds': 90,
                   'root_policy_selected_before_owner_execution': True,
                   'default_proc_live_owner': True,
                   'nested_pid_collision_actual_API_required': True,
                   'new_proc_mount': False,
                   'unavailable_returncode': 77,
                   'unavailable_is_pass': False},
 'non_claims': {'per_request_twenty_second_bridge': False,
                'actor_coordinator_page': False,
                'journal_integration': False,
                'native_Servo': False,
                'native_sixty_second_health': False,
                'installed_activation': False,
                'hardware': False,
                'independent_human_approval': False,
                'production_ready': False},
 'kernel_source_sha256': {'crates/hepta-peer-attestation/tests/approved_service_owner_kernel.rs': '17be60a757254cf07adbb6dd3d6158ae6f990bc2cd6aecf4130c94965b785bda'},
 'cargo_inverse': {'path': 'crates/hepta-peer-attestation/Cargo.toml',
                   'old_bytes': 996,
                   'old_sha256': '1fac9d1b123cdfd9bb47321bcb98b2b3ce936a88f0fe6fdafe5cdfed0ca7bb83',
                   'tail': '\n'
                           '# Persistent service-source continuity is a separate actual root test profile.\n'
                           '[[test]]\n'
                           'name = "approved_service_owner_kernel"\n'
                           'path = "tests/approved_service_owner_kernel.rs"\n'
                           'harness = false\n'},
 'mandatory_make_inverse': {'path': 'Makefile',
                            'old_sha256': '6df4be64e5ffe527caf41e00cb996d26e53e4f12c43200d751c62c2da8c1f329',
                            'line': '\tpython3 tools/verify_approved_service_owner.py\n'}}

EXPECTED['composition_receiver'] = {'baseline_head': '99c4eb9ff6f11b5075487c7e9fc4b4f0ca794320',
 'foundation_head': '67c092aed55b97ac68afd15b3d7aee0f6bdffdbb',
 'source_boundaries': {'crates/hepta-peer-attestation/src/approved_policy.rs': {'baseline': {'bytes': 28911,
                                                                                             'sha256': 'dfb42050e73dd7f1fc6ef46aa6b839b4bc3c1c3f201ac47c5106acaada27815e'},
                                                                                'composed': {'bytes': 29207,
                                                                                             'sha256': '706254153615871c6a88d0b68bd36d1eb3288f3b23d7fb7688494142c98f953d'},
                                                                                'detach_suffix': '\n'
                                                                                                 '// '
                                                                                                 'Additive '
                                                                                                 'service-policy '
                                                                                                 'v2; '
                                                                                                 'original '
                                                                                                 'request-scoped '
                                                                                                 'v1 '
                                                                                                 'stays '
                                                                                                 'unchanged.\n'
                                                                                                 'mod '
                                                                                                 'service_policy;\n'
                                                                                                 'pub '
                                                                                                 'use '
                                                                                                 'service_policy::{\n'
                                                                                                 '    '
                                                                                                 'ApprovedServiceOwnerBinding, '
                                                                                                 'ApprovedServiceOwnerVerifier, '
                                                                                                 'ApprovedServicePolicyDocument,\n'
                                                                                                 '    '
                                                                                                 'DEFAULT_APPROVED_SERVICE_POLICY_PATH, '
                                                                                                 'MAX_APPROVED_SERVICE_POLICY_BYTES,\n'
                                                                                                 '};\n',
                                                                                'original_foundation': {'bytes': 28469,
                                                                                                        'sha256': '018612ed96c97f63d673487addacfe2bb4a48b55ca8d27048ffffa340a499dfc'}},
                       'tools/verify_approved_composition_scope.py': {'baseline': {'bytes': 9836,
                                                                                   'sha256': '7d7599a5cdd6aa27a0148d931f39677ad8851fb6d38b6e2bb973e893e625e4e8'},
                                                                      'composed': {'bytes': 10019,
                                                                                   'sha256': 'c5d8c547ccb6156c9e824339511bd76e35d429de6d4e85e70041c7493b92fe8c'},
                                                                      'inverse': [{'actual': '    '
                                                                                             'try:\n'
                                                                                             '        '
                                                                                             'from '
                                                                                             '.verify_approved_service_owner '
                                                                                             'import '
                                                                                             'legacy_source\n'
                                                                                             '    '
                                                                                             'except '
                                                                                             'ImportError:\n'
                                                                                             '        '
                                                                                             'from '
                                                                                             'verify_approved_service_owner '
                                                                                             'import '
                                                                                             'legacy_source\n',
                                                                                   'baseline': ''},
                                                                                  {'actual': 'hashlib.sha256(legacy_source(path, '
                                                                                             'texts[path]).encode("utf-8")).hexdigest()',
                                                                                   'baseline': 'hashlib.sha256(texts[path].encode("utf-8")).hexdigest()'}],
                                                                      'original_foundation': {'bytes': 9740,
                                                                                              'sha256': '3dd535955e3853ed5e1f40e547385951767384bdd2606f9363f04156ec5794f1'},
                                                                      'original_foundation_forward': [{'baseline': 'def '
                                                                                                                   'check(contract, '
                                                                                                                   'texts):\n',
                                                                                                       'actual': 'def '
                                                                                                                 'check(contract, '
                                                                                                                 'texts):\n'
                                                                                                                 '    '
                                                                                                                 'try:\n'
                                                                                                                 '        '
                                                                                                                 'from '
                                                                                                                 '.verify_approved_service_owner '
                                                                                                                 'import '
                                                                                                                 'legacy_source\n'
                                                                                                                 '    '
                                                                                                                 'except '
                                                                                                                 'ImportError:\n'
                                                                                                                 '        '
                                                                                                                 'from '
                                                                                                                 'verify_approved_service_owner '
                                                                                                                 'import '
                                                                                                                 'legacy_source\n'},
                                                                                                      {'baseline': 'hashlib.sha256(texts[path].encode("utf-8")).hexdigest()',
                                                                                                       'actual': 'hashlib.sha256(legacy_source(path, '
                                                                                                                 'texts[path]).encode("utf-8")).hexdigest()'}]},
                       'tools/verify_approved_constructor_route.py': {'baseline': {'bytes': 12629,
                                                                                   'sha256': '50f2c13bc28324cfabc217ea1290cb9c511a5f885437c0ed890d3563020ca366'},
                                                                      'composed': {'bytes': 12812,
                                                                                   'sha256': '1587db427042ba267d36ea863bd3113f31db5754f6ecc7e43824e7bf43b236b6'},
                                                                      'inverse': [{'actual': '    '
                                                                                             'try:\n'
                                                                                             '        '
                                                                                             'from '
                                                                                             '.verify_approved_service_owner '
                                                                                             'import '
                                                                                             'legacy_source\n'
                                                                                             '    '
                                                                                             'except '
                                                                                             'ImportError:\n'
                                                                                             '        '
                                                                                             'from '
                                                                                             'verify_approved_service_owner '
                                                                                             'import '
                                                                                             'legacy_source\n',
                                                                                   'baseline': ''},
                                                                                  {'actual': 'hashlib.sha256(legacy_source(path, '
                                                                                             'texts[path]).encode("utf-8")).hexdigest()',
                                                                                   'baseline': 'hashlib.sha256(texts[path].encode("utf-8")).hexdigest()'}],
                                                                      'original_foundation': {'bytes': 12533,
                                                                                              'sha256': 'b732cdaad0e1c6f2c67ddfbb4a32e7f289cd7850415b034df3d2d44b0989a525'},
                                                                      'original_foundation_forward': [{'baseline': 'def '
                                                                                                                   'check(contract, '
                                                                                                                   'texts):\n',
                                                                                                       'actual': 'def '
                                                                                                                 'check(contract, '
                                                                                                                 'texts):\n'
                                                                                                                 '    '
                                                                                                                 'try:\n'
                                                                                                                 '        '
                                                                                                                 'from '
                                                                                                                 '.verify_approved_service_owner '
                                                                                                                 'import '
                                                                                                                 'legacy_source\n'
                                                                                                                 '    '
                                                                                                                 'except '
                                                                                                                 'ImportError:\n'
                                                                                                                 '        '
                                                                                                                 'from '
                                                                                                                 'verify_approved_service_owner '
                                                                                                                 'import '
                                                                                                                 'legacy_source\n'},
                                                                                                      {'baseline': 'hashlib.sha256(texts[path].encode("utf-8")).hexdigest()',
                                                                                                       'actual': 'hashlib.sha256(legacy_source(path, '
                                                                                                                 'texts[path]).encode("utf-8")).hexdigest()'}]}},
 'make': {'path': 'Makefile',
          'original_foundation': {'bytes': 2492,
                                  'sha256': '27ff7704fc6f326b24d725c34929aa3a73d11023773e43a4a946abb52acf42d9'},
          'composed': {'bytes': 2595,
                       'sha256': '1906e964907c3f5e90886a64e60f0ade52146511c78cc360218378e640b5deef'},
          'remove_only_lines': ['\tpython3 tools/verify_retained_control_readiness.py\n',
                                '\tpython3 tools/verify_mozjs_authenticated_input.py\n']}}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def legacy_source(path: str, text: str) -> str:
    """Check the exact original byte prefix and sole reviewed additive tail.

    Older profiles may also be tested alone: their exact original bytes remain
    accepted. An arbitrary module/comment tail, altered old byte or same-tail
    decoy fails. Full new source correspondence is a separate mandatory gate.
    """
    if type(text) is not str:
        raise ValueError('exact Foundation source text type differs')
    receiver = EXPECTED['composition_receiver']['source_boundaries'].get(path)
    if receiver is not None and 'detach_suffix' in receiver and type(text) is str:
        raw_receiver = text.encode('utf-8')
        boundary = receiver['baseline']['bytes']
        prefix_receiver = raw_receiver[:boundary].decode('utf-8', 'strict')
        if _pinned_receiver_text(prefix_receiver, receiver['baseline']):
            tail_receiver = raw_receiver[boundary:]
            if tail_receiver not in (b'', receiver['detach_suffix'].encode('utf-8')):
                raise ValueError('exact composed v2 additive tail differs')
            return prefix_receiver
    rule = EXPECTED['legacy_inverse'].get(path)
    if rule is None:
        return text
    raw = text.encode('utf-8')
    prefix = raw[:rule['bytes']]
    tail = raw[rule['bytes']:]
    if len(prefix) != rule['bytes'] or hashlib.sha256(prefix).hexdigest() != rule['sha256']:
        raise ValueError('original v1 byte prefix differs')
    if tail not in (b'', rule['tail'].encode('utf-8')):
        raise ValueError('reviewed v2 additive tail differs')
    return prefix.decode('utf-8', 'strict')


def _pinned_receiver_text(text, rule):
    if type(text) is not str:
        return False
    raw = text.encode('utf-8')
    return len(raw) == rule['bytes'] and hashlib.sha256(raw).hexdigest() == rule['sha256']


def detach_for_readiness(path, text):
    """Restore only exact reviewed receiver files at its whole-hash boundary."""
    rule = EXPECTED['composition_receiver']['source_boundaries'].get(path)
    if rule is None:
        return text
    if _pinned_receiver_text(text, rule['baseline']):
        return text
    if not _pinned_receiver_text(text, rule['composed']):
        raise ValueError('exact Foundation receiver source differs')
    if 'detach_suffix' in rule:
        tail = rule['detach_suffix']
        if not text.endswith(tail):
            raise ValueError('exact Foundation receiver tail differs')
        text = text[:-len(tail)]
    else:
        for pair in rule['inverse']:
            if text.count(pair['actual']) != 1:
                raise ValueError('exact Foundation receiver plumbing differs')
            text = text.replace(pair['actual'], pair['baseline'], 1)
    if not _pinned_receiver_text(text, rule['baseline']):
        raise ValueError('complete Foundation receiver restoration differs')
    return text


def receiver_profile_inputs(texts):
    """Require complete exact bare or combined profiles before original rules."""
    result = dict(texts)
    receiver = EXPECTED['composition_receiver']
    rule = receiver['make']
    text = result[rule['path']]
    combined = _pinned_receiver_text(text, rule['composed'])
    if combined:
        for line in rule['remove_only_lines']:
            if text.count(line) != 1:
                raise ValueError('required receiver source gate differs')
            text = text.replace(line, '', 1)
    if not _pinned_receiver_text(text, rule['original_foundation']):
        raise ValueError('exact original or composed mandatory Make profile differs')
    result[rule['path']] = text
    profile = 'composed' if combined else 'original_foundation'
    for path, rule in receiver['source_boundaries'].items():
        text = result[path]
        if not _pinned_receiver_text(text, rule[profile]):
            raise ValueError('complete Foundation receiver profile differs')
        if combined:
            try:
                from .verify_retained_control_readiness import parent_source
            except ImportError:
                from verify_retained_control_readiness import parent_source
            if 'detach_suffix' in rule:
                text = parent_source(path, detach_for_readiness(path, text)) + rule['detach_suffix']
            else:
                text = parent_source(path, detach_for_readiness(path, text))
                for pair in rule['original_foundation_forward']:
                    if text.count(pair['baseline']) != 1:
                        raise ValueError('original Foundation plumbing insertion differs')
                    text = text.replace(pair['baseline'], pair['actual'], 1)
        if not _pinned_receiver_text(text, rule['original_foundation']):
            raise ValueError('complete original Foundation profile restoration differs')
        result[path] = text
    return result


def inputs(root=ROOT):
    paths = (set(EXPECTED['whole_source_sha256']) |
             set(EXPECTED['preserved_source_sha256']) |
             set(EXPECTED['legacy_inverse']) |
             set(EXPECTED['kernel_source_sha256']) |
             set(EXPECTED['composition_receiver']['source_boundaries']) |
             {EXPECTED['cargo_inverse']['path'], EXPECTED['mandatory_make_inverse']['path']})
    return {path: source_gate.source(root, path) for path in sorted(paths)}


def check(value, texts):
    source_gate.typed_equal(value, EXPECTED)
    texts = receiver_profile_inputs(texts)
    for path, rule in EXPECTED['legacy_inverse'].items():
        # FOUNDATION is not valid if its public module is detached from the
        # exact reviewed old prefix. The old-checker helper alone accepts v1.
        if not texts[path].endswith(rule['tail']):
            raise ValueError('v2 public module is detached')
        legacy_source(path, texts[path])
    for group in ['whole_source_sha256', 'preserved_source_sha256', 'kernel_source_sha256']:
        for path, wanted in EXPECTED[group].items():
            if sha256(texts[path]) != wanted:
                raise ValueError('finite FOUNDATION complete source differs')
    rule = EXPECTED['cargo_inverse']
    raw = texts[rule['path']].encode('utf-8')
    if (len(raw) != rule['old_bytes'] + len(rule['tail'].encode('utf-8')) or
            hashlib.sha256(raw[:rule['old_bytes']]).hexdigest() != rule['old_sha256'] or
            raw[rule['old_bytes']:] != rule['tail'].encode('utf-8')):
        raise ValueError('original Cargo prefix or sole actual harness target differs')
    rule = EXPECTED['mandatory_make_inverse']
    text = texts[rule['path']]
    if text.count(rule['line']) != 1 or sha256(text.replace(rule['line'], '', 1)) != rule['old_sha256']:
        raise ValueError('original Make graph or mandatory source gate differs')
    inventory = source_gate.rust_inventory(texts[CORE])
    if set(inventory['public_api']) != set(EXPECTED['public_api']):
        raise ValueError('FOUNDATION public method inventory differs')
    for name, wanted in EXPECTED['public_api'].items():
        if source_gate.signature(inventory['public_api'][name]) != source_gate.signature(wanted):
            raise ValueError('FOUNDATION public signature differs')
    actual = {name for name, item in inventory['types'].items() if item['public']}
    if actual != set(EXPECTED['opaque_types']):
        raise ValueError('FOUNDATION opaque type inventory differs')
    for name, fields in EXPECTED['opaque_types'].items():
        body = inventory['types'][name]['body']
        if 'pub' in body or source_gate.signature(' '.join(body)) != source_gate.signature(fields):
            raise ValueError('FOUNDATION state is externally replaceable')
    creator = source_gate.rust_inventory(texts[CREATOR])
    if creator['public_api']:
        raise ValueError('creator context becomes caller authority')
    source_gate.ordered(source_gate.function(creator, 'CreatorContext::verify'),
                        ['self.pid != std::process::id()', 'endpoint.verify()?',
                         'namespace_identity(&self.pid_namespace)?', 'current_pid_namespace()?'],
                        'actual original creator before namespace/policy access')
    source_gate.ordered(source_gate.function(inventory, 'ApprovedServicePolicyDocument::select_current_owner'),
                        ['self.state.creator_current()?', 'self.state.inspect()?',
                         '.compare_exchange(false, true,', 'UnixStream::pair()',
                         'ProcfsPeerAttestor::default()', '.attest(peer, &entry.runtime())',
                         '.request_custody()', 'binding.ensure_current()?'],
                        'fixed actual owner selection and original custody')


def validate(root=ROOT):
    check(source_gate.load(root / CONTRACT), inputs(root))


def main():
    try:
        validate()
    except (OSError, ValueError, KeyError, UnicodeError):
        print('SOURCE_INVALID approved service Owner FOUNDATION', file=sys.stderr)
        return 1
    print(json.dumps({'source_contract': 'PASS', 'scope': 'FOUNDATION_ONLY',
                      'actual_kernel_execution': False, 'native_sixty_second_health': False,
                      'installed_activation': False, 'production_ready': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
