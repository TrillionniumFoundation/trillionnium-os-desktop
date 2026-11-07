#!/usr/bin/env python3
"""Local-only validation of actual install/readback before fixed46 source sealing."""
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
INSTALL_ROOT = 'successor_qa/search_helper_coexist_install_r1/host-candidate-r1'
READBACK_ROOT = 'successor_qa/search_helper_coexist_install_r1/post_install_scope_readback_r1/actual'
SCOPE_PIN = {'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/install-search-helper-r2-01/app-scope-after.private.json',
             'bytes': 60614, 'sha256': '7187bc544cf6812ad47efdf141cd111897a1124b9532f84b7cf599b0c0fee1e3'}
PACKAGE = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2'
INSTALL_JOB = '1a1b34fadf6-fc05-81f2'
READBACK_JOB = '1a1b3539bb5-fc05-821a'
EPOCH = 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9'
INPUTS = {
    'original_gate': ('successor_audit_requests/effective_permissions_45_capture_r1/permission_capture_gate.py', 27120, 'dc4fffb3f11e8428db732b96cd1925f0bdce239cdce81ff64ab369dc14c751f4'),
    'installer': (INSTALL_ROOT + '/install_search_helper_full_scope.py', 24933, 'a15d1322c1bbf6001d0870307243bf4509e00111484b042038ad583871f101c6'),
    'owner': (INSTALL_ROOT + '/owned_install_once.py', 39677, '0288098834b039fad646331dce2caa2c4bde7166224a1b770866c7c09b5cae41'),
    'request': (INSTALL_ROOT + '/request.json', 2066, 'b2ed2b01358ff4e15fcc997554042cdf1edf7bfdf6da1d4af73bc58ad70d7324'),
    'install_stdout': (INSTALL_ROOT + '/actual-install/stdout.original.json', 33582, '5d7d4e22f8351a3ab58b99bb9236bda69bcf51a1a3a115f079f2834d8d83fbcf'),
    'install_terminal': (INSTALL_ROOT + '/actual-install/terminal.original.json', 733, '5350ed913cfb078591d6bf2a13a7fc39b7f74990d9e26009f38bb16a67365bfc'),
    'scope48': ('successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/app-scope-after.private.json', 59259, '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a'),
    'scope49': (READBACK_ROOT + '/app-scope-after.private.json', 60614, '7187bc544cf6812ad47efdf141cd111897a1124b9532f84b7cf599b0c0fee1e3'),
    'readback_stdout': (READBACK_ROOT + '/stdout.original.json', 66589, '58956b36d388d34d6ad07632ca1bee28d24a05840e104bc99269c66ff94a93a5'),
    'readback_terminal': (READBACK_ROOT + '/terminal.original.json', 733, 'bb60879d7c42e702fc92e9dff3eb6c3b31cccf6749e751b4b908558c6278659c'),
    'readback_root_validation': (READBACK_ROOT + '/root-validation.actual.json', 1363, '27844d03beb3644ff5cdf2c4932db9d48d4ba5d2ba81d903bc1619daee7620c8'),
    'native46': ('successor_audit_requests/native46_discovery_r1/actual/artifact.original.json', 112546, '69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400'),
    'native46_terminal': ('successor_audit_requests/native46_discovery_r1/actual/status-01.original.json', 733, 'f16d1da55f8afa0da6f91f37186fff39dc50ba12a22e54b048290e723dc797bd'),
    'native46_stdout': ('successor_audit_requests/native46_discovery_r1/actual/stdout.original.jsonl', 31226, '474893612abaf6192653b31d16adb808a2d46e92cf6e1683760e532684d5fe5d'),
    'native46_root_validation': ('successor_audit_requests/native46_discovery_r1/actual/root-validation.actual.json', 5903, '0a9c6e397790adce9e064aa445b13929f44bddbfc616820eee8693df70bc11cc'),
}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def module(raw, path, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def read_inputs():
    values = {}
    for key, (rel, length, digest) in INPUTS.items():
        path = PROJECT / rel
        need(path.is_file() and not path.is_symlink(), 'REGULAR_LOCAL_ORIGINAL_INPUT:' + key)
        raw = path.read_bytes()
        need(len(raw) == length and sha(raw) == digest, 'EXACT_ACTUAL_INPUT_PIN:' + key)
        values[key] = raw
    path = PROJECT / INSTALL_ROOT / 'actual-install/root-validation.actual.json'
    raw = path.read_bytes()
    need(sha(raw) == 'a0f0f236e39d2af99fa68b9b585764471b4e30c53f3081ce490c18d38dba8e61',
         'ACTUAL_ROOT_INSTALL_JOINT_VALIDATION_PIN')
    values['install_root_validation'] = raw
    return values


def owned_exit(life):
    need(type(life) is dict and type(life.get('child_pid')) is int and life['child_pid'] > 0 and
         type(life.get('returncode')) is int and life['returncode'] == 0 and life.get('errors') == [] and
         life.get('owned_child_sigkill_count') == 0 and life.get('timeout') is False and
         all(life.get(key) is True for key in ('parent_descriptors_restored', 'pidfd_acquired',
                                             'pidfd_closed', 'pidfd_exit_observed')),
         'ACTUAL_NORMAL_OWNED_CHILD_RETIREMENT_REQUIRED')


def validate_install(values, gate, g):
    raw = values['install_stdout']; terminal = g.parse(values['install_terminal'])
    gate.terminal_gate(g, terminal, INSTALL_JOB, raw)
    need(len(raw.splitlines()) == 1, 'EXACT_SINGLE_ORIGINAL_INSTALL_OWNER_STREAM')
    outer = g.parse(raw); request = g.parse(values['request'])
    owner = module(values['owner'], PROJECT / INPUTS['owner'][0], 'actual_installer_owner_definitions_not_entry')
    installer = module(values['installer'], PROJECT / INPUTS['installer'][0], 'actual_pure_scope_transition_not_entry')
    expected_source = {'path': owner.ROOT + '/owned_install_once.py', 'bytes': INPUTS['owner'][1], 'sha256': INPUTS['owner'][2]}
    expected_request = {'path': owner.ROOT + '/request.json', 'bytes': INPUTS['request'][1], 'sha256': INPUTS['request'][2]}
    need(outer.get('schema') == 'pocket4-owned-search-helper-coexist-result-v1' and outer.get('ok') is True and
         outer.get('errors') == [] and outer.get('source') == expected_source and outer.get('request') == expected_request and
         outer.get('flow') == owner.FLOW and outer.get('step') == request['step'] == 'install-search-helper-r2-01' and
         outer.get('package') == PACKAGE == installer.SELF and outer.get('helper_uid') == 10167 and
         outer.get('next_app_scope') == SCOPE_PIN and outer.get('observed_explicit_packages') == 49 and
         outer.get('observed_APKs') == 89 and
         all(outer.get(key) is True for key in ('all_original48_unchanged', 'normal_PM_install_success_observed',
             'state_without_UiAutomation_verified', 'original_action_attempted',
             'all_owned_child_resources_retired_by_normal_pidfd_exit', 'parent_whole_process_FD_identity_restored',
             'current_scope_adoption_requires_this_actual_durable_terminal',
             'later_QA_permissions_and_framework_must_rebind_actual_new_scope',
             'acceptance_requires_original_stdout_and_authoritative_durable_terminal')) and
         all(outer.get(key) is False for key in ('automatic_retry', 'original_FAILED_UNKNOWN_rewritten',
             'reconciliation_published', 'production_ready', 'old_helper_uninstalled', 'old_products_deleted',
             'full_PM_or_launcher_inventory_claimed', 'original_action_outcome_unknown', 'outcome_unknown')) and
         all(type(outer.get(key)) is int and outer[key] == 0 for key in ('UI_actions', 'permission_grants', 'target_App_launches')),
         'COMPLETE_ACTUAL_INSTALL_PARENT_AND_SCOPE_JOINT')
    owned_exit(outer['child_lifecycle'])
    need(outer['child_lifecycle']['child_pid'] == 2595254, 'EXACT_ACTUAL_INSTALL_CHILD')
    need(outer['child_stderr_original'] == '' and outer['child_stderr_bytes'] == 0 and
         outer['child_stderr_sha256'] == sha(b''), 'EXACT_EMPTY_ACTUAL_CHILD_STDERR')
    child_raw = outer['child_stdout_original'].encode('utf-8')
    need(len(child_raw) == outer['child_stdout_bytes'] and sha(child_raw) == outer['child_stdout_sha256'],
         'FULL_ACTUAL_CHILD_STREAM')
    child = g.parse(child_raw)
    need(child.get('schema') == 'pocket4-owned-search-helper-coexist-child-v1' and child.get('ok') is True and
         child.get('errors') == [] and child.get('source') == expected_source and child.get('request') == expected_request and
         child.get('flow') == owner.FLOW and child.get('step') == request['step'] and
         child.get('original_entry_invoked') is True and child.get('original_returncode') == 0 and
         child.get('original_action_attempted') is True and child.get('original_action_outcome_unknown') is False and
         child.get('outcome_unknown') is False and child.get('original_namespace_authority_released') is True and
         child.get('normal_process_exit_required_for_lock_and_library') is True and
         child.get('unknown_descriptors_closed') == 0 and child.get('manual_library_close') is False and
         child.get('original_private_UI_nodes_exported') is False and child.get('next_app_scope') == SCOPE_PIN and
         child.get('helper_uid') == 10167, 'COMPLETE_ACTUAL_INSTALL_CHILD')
    inner_raw = child['original_stdout'].encode('utf-8')
    need(len(inner_raw) == child['original_stdout_bytes'] and sha(inner_raw) == child['original_stdout_sha256'],
         'EXACT_ORIGINAL_INSTALLER_STREAM')
    inner = g.parse(inner_raw); proof = child['completed_build']['qualified_build']
    need(inner.get('schema') == 'pocket4-successor-owned-helper-coexist-install-v1' and inner.get('ok') is True and
         inner.get('errors') == [] and inner.get('package') == PACKAGE and inner.get('build') == proof and
         proof['APK'] == owner.APK and proof['signer_certificate_sha256'] == owner.SIGNER_SHA and
         proof['source_manifest_sha256'] == owner.HELPER_MANIFEST['sha256'] and
         proof['build_receipt_sha256'] == owner.BUILD_RESULT['sha256'] and
         inner.get('action_attempted') is True and inner.get('outcome_unknown') is False and
         inner.get('install_attempted') is True and inner.get('install_success_observed') is True and
         inner.get('state_attempted') is True and inner.get('helper_retained') is True and
         inner.get('action_lock_held_through_durable_result') is True and
         inner.get('scope_requires_outer_owned_child_and_durable_terminal') is True and
         all(inner.get(key) is False for key in ('old_v2_helper_called', 'automatic_retry', 'production_ready')) and
         all(type(inner.get(key)) is int and inner[key] == 0 for key in ('UI_actions', 'permission_grants', 'App_launches')),
         'ORIGINAL_NORMAL_INSTALL_STATE_SCOPE_RESULT')
    parent = g.parse(values['scope48']); observed = g.parse(values['scope49'])
    actual = installer.validate_scope_transition(parent, observed, proof, inner['helper_uid'], inner['installed_after_state'])
    transition = inner['whole_scope_after']; observation = transition['observation']
    need(transition['transition'] == actual == child['whole_scope_transition'] and
         transition['parent_app_scope'] == installer.PARENT_SCOPE and
         transition['next_app_scope'] == inner['next_app_scope'] == SCOPE_PIN and
         observation['schema'] == 'pocket4-successor-app-observation-result-v1' and observation['ok'] is True and
         observation['app_scope'] == SCOPE_PIN and
         observation['observation_fds'] == {'acquired': 1334, 'closed': 1334, 'errors': [], 'remaining': 0} and
         observation['UI_or_install_runtime_admitted'] is False and observation['new_signature_verification_performed'] is False and
         inner['whole_scope_before'] == transition['original_48_guard_before'] == transition['original_48_guard_after'] ==
         inner['whole_scope_final_guard'] and inner['installed_before_state'] == inner['installed_after_state'] and
         inner['state']['helper']['ui_automation_connected'] is False and
         inner['state']['helper']['action_attempted'] is False and inner['state']['helper']['outcome_unknown'] is False,
         'PURE_ACTUAL_TRANSITION_AND_COMPLETE_OBSERVER_FDS')
    need(child['completed_build'] == outer['completed_build'] and child['completed_no_action_B'] == outer['completed_no_action_B'] and
         child['original_result'] == outer['original_result'] and
         outer['original_result']['path'] == owner.FLOW + '/steps/' + request['step'] + '/result.json',
         'SAME_PUBLISHED_ORIGINAL_INSTALL_RESULT')
    joint = dict(outer); del joint['joint_artifact']; joint_raw = canonical(joint) + b'\n'
    need(outer['joint_artifact'] == {'path': owner.ROOT + '/owned-install-joint.json', 'bytes': len(joint_raw),
                                   'sha256': sha(joint_raw)}, 'EXACT_ACTUAL_JOINT_PUBLICATION_PIN')
    review = g.parse(values['install_root_validation'])
    need(review.get('state') == 'PASS_NORMAL_INSTALL_STATE_OWNED_EXIT_AND_DURABLE_TERMINAL' and
         review.get('job_id') == INSTALL_JOB and review.get('next_app_scope') == SCOPE_PIN and
         review.get('joint_artifact') == outer['joint_artifact'] and review.get('helper_UID') == 10167,
         'ROOT_ACTUAL_INSTALL_JOINT_REQUIRED')
    return outer, inner, observed, actual


def validate_binding():
    values = read_inputs()
    gate = module(values['original_gate'], PROJECT / INPUTS['original_gate'][0], 'frozen_terminal_and_owned_gate_primitives')
    g = gate.primitives()
    outer, inner, scope, transition = validate_install(values, gate, g)
    gate.terminal_gate(g, g.parse(values['readback_terminal']), READBACK_JOB, values['readback_stdout'])
    reader = g.parse(values['readback_stdout'])
    need(reader.get('schema') == 'pocket4-owned-r2-post-install49-scope-readback-v1' and reader.get('ok') is True and
         reader.get('file') == SCOPE_PIN and reader.get('raw_utf8', '').encode('utf-8') == values['scope49'] and
         reader.get('reconstructed') is False and reader.get('owned_FDs_acquired') == reader.get('owned_FDs_closed') == 9 and
         reader.get('whole_process_FD_identities_restored') is True and
         all(type(reader.get(key)) is int and reader[key] == 0 for key in
             ('Main_commands', 'UI_actions', 'namespace_entries', 'permission_changes')),
         'ACTUAL_COMPLETE_SCOPE49_ORIGINAL_BYTE_READBACK')
    review = g.parse(values['readback_root_validation'])
    need(review.get('state') == 'PASS_ACTUAL49_RAW_SCOPE_AND_NORMAL_INSTALL_JOINT' and
         review.get('normal_install_job') == INSTALL_JOB and review.get('job_id') == READBACK_JOB and
         review.get('actual_scope') == SCOPE_PIN and review.get('all_original48_full_rows_equal') is True and
         review.get('normal_install_root_validation_SHA256') == sha(values['install_root_validation']) and
         review.get('scope_raw_saved_without_reconstruction') is True and
         review.get('whole_FD_identities_restored') is True, 'ROOT_ACTUAL49_JOINT_REQUIRED')
    discovery = g.parse(values['native46'])
    gate.terminal_gate(g, g.parse(values['native46_terminal']), '1a1b307f521-fc05-807a', values['native46_stdout'])
    need(discovery['ok'] is True and discovery['errors'] == [] and discovery['enumeration_samples_equal'] is True and
         discovery['guard_before'] == discovery['guard_after'] and discovery['guard_before']['runtime_epoch_sha256'] == EPOCH and
         discovery['catalog_comparison']['framework_only_components'] == [] and
         discovery['catalog_comparison']['native_only_components'] == [], 'ACTUAL46_FRAMEWORK_AND_NATIVE_REFERENCE')
    components = sorted(row['component'] for row in discovery['MAIN_LAUNCHER_components'])
    launchers = sorted(row['package'] for row in discovery['MAIN_LAUNCHER_components'])
    need(len(components) == len(set(components)) == len(launchers) == len(set(launchers)) == 46 and
         set(scope['apps']) == set(launchers) | {'local.pocket4.actions.v2',
             'org.droidloom.qa.successor.p8f89f253350ba2fa.r1', PACKAGE}, 'EXACT46_PLUS_ACTIONS_AND_TWO_HELPERS')
    need(sum(len(row['apks']) for row in scope['apps'].values()) == 89 and
         scope['runtime_epoch_sha256'] == EPOCH, 'EXACT_ACTUAL49_89_RUNTIME')
    need(read_inputs() == values, 'ACTUAL_INPUTS_CHANGED_DURING_VALIDATION')
    summary = {'schema': 'pocket4-fixed46-actual49-input-binding-v1', 'state': 'ACTUAL49_INPUTS_VERIFIED_NO_NEW_CAPTURE',
        'installer_job': INSTALL_JOB, 'readback_job': READBACK_JOB, 'scope': SCOPE_PIN, 'new_helper': PACKAGE,
        'helper_uid': 10167, 'explicit_packages': 49, 'APKs': 89, 'launcher_packages': 46,
        'all_original48_rows_unchanged': True, 'original_installer_scope_validator_reused': True,
        'joint_reconstructed_from_actual_stdout_only_not_claimed_reread': True,
        'scope_original_bytes_read_back': True, 'new_permission_capture_performed': False,
        'permission_grants': 'UNKNOWN_PENDING_NEW_CAPTURE_AND_LITERAL_INTERPRETATION',
        'Main_or_device_actions': 0, 'production_ready': False, 'cleanup_actions': 0,
        'inputs': {key: {'file': row[0], 'bytes': row[1], 'sha256': row[2]} for key, row in INPUTS.items()}}
    summary['inputs']['install_root_validation'] = {'file': INSTALL_ROOT + '/actual-install/root-validation.actual.json',
        'bytes': len(values['install_root_validation']), 'sha256': sha(values['install_root_validation'])}
    return {'summary': summary, 'scope': scope, 'components': components, 'launchers': launchers,
            'expected_guard': discovery['guard_before'], 'installer': outer, 'original_install': inner}


if __name__ == '__main__':
    print(json.dumps(validate_binding()['summary'], sort_keys=True, indent=2))
