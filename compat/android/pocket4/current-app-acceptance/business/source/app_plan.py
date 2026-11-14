"""Actual-Main plan factory and independent per-App source/scope binding.

Publication creates no runtime authority. Both identity receipts and, for IHG,
the actual new helper build/install chain must exist before a plan can be made.
No App/UI command is sent by these factories.
"""
import os
from pathlib import Path
import re
import secrets
import time

BASE_FIELDS = {'schema', 'kind', 'baseline', 'qualification', 'framework_epoch_sha256',
    'support_manifest', 'target_identity', 'helper_identity', 'helper_build', 'helper_install',
    'source_preparation', 'task_source_manifest', 'original_gates', 'limits', 'flows',
    'whole_app_business_accepted', 'automatic_retry', 'case_root', 'target_profile', 'helper_profile'}
ACTIVE_FIELDS = BASE_FIELDS | {'base_plan', 'lease', 'protected_before', 'action_lock'}


def preparation(common, ref):
    value = common.parse(common.read_ref(ref))
    common.need(value['schema'] == 'pocket4-final-app-preparation-source-v1' and
        value['Android_execution_authorized_by_publication'] is False and value['code_entrypoints_complete'] is True and
        type(value['files']) is list and 1 <= len(value['files']) <= 128 and
        len({Path(r['path']).name for r in value['files']}) == len(value['files']) and
        type(value['origins']) is list and 1 <= len(value['origins']) <= 128,
        'COMPLETE_DISTINCT_FROZEN_APP_PREPARATION_SOURCE_REQUIRED')
    for row in value['files'] + value['origins']:
        common.read_ref(row)
    return value


def named(common, packet, name):
    rows = [r for r in packet['files'] if Path(r['path']).name == name]
    common.need(len(rows) == 1, 'EXACT_NEW_APP_SOURCE_MODULE_REQUIRED:' + name)
    return common.module(rows[0], 'new_case_' + Path(name).stem)


def validate_inputs(common, kind, request, packet):
    common.need(kind in ('clock_timer', 'ihg_london'), 'ORIGINAL_TWO_CASE_KINDS_ONLY')
    expected = {'baseline', 'qualification', 'target_identity', 'helper_identity'}
    if kind == 'ihg_london':
        expected |= {'helper_build', 'helper_install'}
    common.need(set(request) == expected, 'EXACT_ACTUAL_CASE_INPUTS_REQUIRED')
    support = common.CLOCK_SUPPORT_REF if kind == 'clock_timer' else common.SUPPORT_REF
    _, modules = common.support(support)
    baseline = modules['business_baseline.py'].BusinessBaseline(request['baseline'], request['qualification'])
    profiles = named(common, packet, 'app_profiles.py')
    target_profile = profiles.CLOCK if kind == 'clock_timer' else profiles.IHG
    identity = common.parse(common.read_ref(request['target_identity']))
    common.validate_identity(identity, target_profile, request['baseline'], request['qualification'])
    extra = []; source = None
    if kind == 'clock_timer':
        helper_profile = profiles.CLOCK_HELPER
    else:
        builder = named(common, packet, 'ihg_helper_build.py')
        build, source, helper_baseline, _ = builder.verify_build(common, request['helper_build'])
        common.need(source['baseline'] == request['baseline'] and source['qualification'] == request['qualification'],
                    'ACTUAL_HELPER_WAS_NOT_BOUND_TO_THIS_MAIN')
        installer = named(common, packet, 'ihg_helper_install.py')
        qa = common.module(source['files']['qa_contract.py'], 'actual_installed_helper_protocol')
        installed = installer.verify_install(common, request['helper_install'], build, source, qa, request['target_identity'])
        common.need(installed['build'] == request['helper_build'], 'ACTUAL_HELPER_INSTALL_BUILD_CHAIN_CHANGED')
        helper_profile = profiles.helper_expected(common, build, installed['helper_uid'])
        extra = [build, source, installed]
    helper = common.parse(common.read_ref(request['helper_identity']))
    common.validate_identity(helper, helper_profile, request['baseline'], request['qualification'])
    if kind == 'ihg_london':
        actual = helper['artifacts'][0]
        common.need(actual['guest_path'] == installed['installed_after_state']['base_apk'] and
            actual['held_file'] == installed['installed_after_state']['held_file'], 'INSTALLED_HELPER_IDENTITY_RECEIPT_DIFFERS')
    common.need(baseline.value['data_continuity']['package_uids'][target_profile['package']] == target_profile['uid'],
                'ORIGINAL_PRESERVED_APP_UID_CHANGED')
    baseline.guard()
    return baseline, profiles, target_profile, helper_profile, identity, helper, extra, source


def create(common, kind, request, output, preparation_ref):
    common.need(os.getuid() == os.geteuid() == 0, 'ROOT_NEW_PLAN_CONSTRUCTION_REQUIRED')
    prepared = preparation(common, preparation_ref)
    baseline, profiles, target, helper, _, _, _, helper_source = validate_inputs(common, kind, request, prepared)
    root = Path(output); prefix = 'business-clock-plan-' if kind == 'clock_timer' else 'business-ihg-plan-'
    common.need(root.parent == common.FINAL / 'qualification' and
                re.fullmatch(re.escape(prefix) + r'[0-9a-f]{32}', root.name), 'NEW_PRIVATE_CASE_PLAN_ROOT_REQUIRED')
    root = common.private_dir(root, create=True); sources = common.private_dir(root / 'source', create=True)
    files = []
    for row in prepared['files']:
        files.append(common.write_new(sources / Path(row['path']).name, common.read_ref(row), 0o400))
    if helper_source is not None:
        files.append(common.write_new(sources / 'qa_contract.py', common.read_ref(helper_source['files']['qa_contract.py']), 0o400))
    guard_name = 'clock_guard.py' if kind == 'clock_timer' else 'ihg_guard.py'
    guard = next(r for r in files if Path(r['path']).name == guard_name)
    recorder = next(r for r in files if Path(r['path']).name == 'app_flow.py')
    origins = []
    for ref in [preparation_ref] + prepared['files'] + prepared['origins']:
        if ref not in origins:
            origins.append(ref)
    if helper_source is not None:
        for ref in helper_source['files'].values():
            if ref not in origins:
                origins.append(ref)
    common.need(len(origins) <= 128, 'BOUNDED_NEW_CASE_SOURCE_ORIGINS_REQUIRED')
    task = {'schema': 'pocket4-final-business-task-source-v1', 'files': files, 'origins': origins,
        'guard_source': guard, 'recorder_source': recorder, 'target_package': target['package'],
        'target_uid': target['uid'], 'old_runtime_authority_transferred': False}
    task_ref = common.write_new(root / 'task-source.json', task, 0o400)
    flows = []
    for i in range(2 if kind == 'clock_timer' else 1):
        nonce = secrets.token_hex(16)
        flows.append({'nonce': nonce, 'flow_root': str(common.FINAL / 'qualification' /
                      ('business-flow-' + kind.replace('_', '-') + '-' + nonce))})
    value = {'schema': 'pocket4-final-app-case-plan-v1', 'kind': kind, **request,
        'helper_build': request.get('helper_build'), 'helper_install': request.get('helper_install'),
        'framework_epoch_sha256': baseline.value['framework_epoch']['sha256'],
        'support_manifest': common.CLOCK_SUPPORT_REF if kind == 'clock_timer' else common.SUPPORT_REF,
        'target_profile': target, 'helper_profile': helper, 'source_preparation': preparation_ref,
        'task_source_manifest': task_ref, 'original_gates': common.GATES,
        'limits': profiles.CLOCK_LIMITS if kind == 'clock_timer' else profiles.IHG_LIMITS,
        'flows': flows, 'case_root': str(root), 'whole_app_business_accepted': False, 'automatic_retry': False}
    if kind == 'ihg_london':
        # These are original logical input plans, freshly allocated once. The
        # observed selectors are filled only by the preserved public UI code.
        value['input_plans'] = input_plans()
    common.read_ref(common.GATES); baseline.guard()
    return common.write_new(root / 'plan.json', value, 0o400)


def input_plans():
    used = set()
    def nonce():
        value = secrets.token_hex(16)
        while value in used:
            value = secrets.token_hex(16)
        used.add(value); return value
    def plan(op, selector=None):
        names = ['before', 'inspect', 'after'] + (['action'] if op in ('click', 'set_text') else [])
        value = {'schema': 1, 'operation': op, 'nonces': {k: nonce() for k in names}}
        if selector is not None:
            value['selector'] = selector
        if op == 'set_text':
            value['value'] = 'London'
        return value
    value = {'search': plan('click', {'text': 'Search'}), 'destination': plan('click', {'text': 'Destination'}),
             'input': plan('set_text'), 'post': plan('inspect'), 'readiness': [plan('inspect') for _ in range(8)]}
    assert len(used) == 39
    return value


def validate(common, value, baseline, scope=None, *, semantic=True):
    kind = value.get('kind'); active = value.get('schema') == 'pocket4-final-app-active-plan-v1'
    fields = (ACTIVE_FIELDS if active else BASE_FIELDS) | ({'input_plans'} if kind == 'ihg_london' else set())
    common.need(type(value) is dict and set(value) == fields and
        value['schema'] in ('pocket4-final-app-case-plan-v1', 'pocket4-final-app-active-plan-v1') and
        kind in ('clock_timer', 'ihg_london') and value['whole_app_business_accepted'] is False and value['automatic_retry'] is False,
        'DISTINCT_COMPLETE_NEW_CASE_PLAN_REQUIRED')
    prepared = preparation(common, value['source_preparation'])
    profiles = named(common, prepared, 'app_profiles.py')
    expected_support = common.CLOCK_SUPPORT_REF if kind == 'clock_timer' else common.SUPPORT_REF
    expected_target = profiles.CLOCK if kind == 'clock_timer' else profiles.IHG
    common.need(value['support_manifest'] == expected_support and value['baseline'] == baseline.baseline_ref and
        value['qualification'] == baseline.qualification_ref and
        value['framework_epoch_sha256'] == baseline.value['framework_epoch']['sha256'] and
        value['target_profile'] == expected_target and value['original_gates'] == common.GATES and
        value['limits'] == (profiles.CLOCK_LIMITS if kind == 'clock_timer' else profiles.IHG_LIMITS),
        'ORIGINAL_CASE_LIMITS_OR_ACTUAL_MAIN_BINDING_CHANGED')
    task = common.parse(common.read_ref(value['task_source_manifest']))
    by_name = {Path(r['path']).name: r for r in task['files']}
    for row in prepared['files']:
        copied = by_name.get(Path(row['path']).name)
        common.need(copied is not None and copied['bytes'] == row['bytes'] and copied['sha256'] == row['sha256'],
                    'NEW_TASK_SOURCE_NOT_EXACT_REVIEWED_PREPARATION_COPY')
    common.need(len(value['flows']) == (2 if kind == 'clock_timer' else 1) and
        len({x['nonce'] for x in value['flows']}) == len(value['flows']) and
        all(re.fullmatch('[0-9a-f]{32}', x['nonce']) and Path(x['flow_root']).parent == common.FINAL / 'qualification'
            and Path(x['flow_root']).name.endswith(x['nonce']) for x in value['flows']), 'FRESH_DISTINCT_ORIGINAL_LAUNCH_SCOPES_REQUIRED')
    if scope is not None:
        common.need(active and scope['task_source_manifest'] == value['task_source_manifest'] and
            scope['actual_resolution_receipt'] == value['target_identity'] and
            scope['installed_helper_receipts'] == [value['helper_identity']] and
            scope['support_manifest'] == expected_support and scope['package'] == expected_target['package'] and
            scope['uid'] == expected_target['uid'] and scope['component'] == expected_target['component'] and
            {'nonce': scope['nonce'], 'flow_root': scope['flow_root']} in value['flows'], 'NEW_SCOPE_NOT_THIS_ORIGINAL_CASE')
    if kind == 'ihg_london':
        policy = named(common, prepared, 'ihg_policy.py')
        qa = common.module(by_name['qa_contract.py'], 'new_case_actual_helper_protocol')
        policy.Policy('inspect', qa, common.package_commands(expected_target['package'], True)[2], value['input_plans'],
            Path(value['case_root']), lambda *args: b'', lambda: {})
    if semantic:
        request = {k: value[k] for k in ('baseline', 'qualification', 'target_identity', 'helper_identity')}
        if kind == 'ihg_london':
            request.update(helper_build=value['helper_build'], helper_install=value['helper_install'])
        found = validate_inputs(common, kind, request, prepared)
        common.need(found[3] == value['helper_profile'], 'ACTUAL_NEW_HELPER_PROFILE_CHANGED')
        return found
    return None


def activate(common, base_plan_ref, lease_ref, protected_before_ref=None, action_lock_ref=None):
    base = common.parse(common.read_ref(base_plan_ref)); _, modules = common.support(base['support_manifest'])
    baseline = modules['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    validate(common, base, baseline)
    common.read_ref(lease_ref)
    if base['kind'] == 'clock_timer':
        common.need(protected_before_ref is not None and action_lock_ref is not None,
                    'ACTUAL_CLOCK_PROTECTED_PREIMAGE_AND_ORIGINAL_ACTION_LOCK_REQUIRED')
        common.read_ref(protected_before_ref)
        common.read_ref(action_lock_ref)
    else:
        common.need(protected_before_ref is action_lock_ref is None, 'NO_UNDECLARED_IHG_PROTECTED_PREIMAGE_OR_CASE_LOCK')
    active = {**base, 'schema': 'pocket4-final-app-active-plan-v1', 'base_plan': base_plan_ref,
              'lease': lease_ref, 'protected_before': protected_before_ref, 'action_lock': action_lock_ref}
    root = Path(base['case_root']); active_ref = common.write_new(root / 'active-plan.json', active, 0o400)
    task = common.parse(common.read_ref(base['task_source_manifest'])); refs = []
    for flow in base['flows']:
        target = common.private_dir(flow['flow_root'], create=True)
        common.private_dir(target / 'steps', create=True)
        scope = {'schema': 'pocket4-final-business-recorder-scope-v1',
            'business_baseline': base['baseline'], 'business_qualification': base['qualification'],
            'support_manifest': base['support_manifest'], 'framework_epoch_sha256': base['framework_epoch_sha256'],
            'package': base['target_profile']['package'], 'uid': base['target_profile']['uid'], 'user': 0,
            'component': base['target_profile']['component'], **flow, 'task_source_manifest': base['task_source_manifest'],
            'phase_plan': active_ref, 'actual_resolution_receipt': base['target_identity'],
            'installed_helper_receipts': [base['helper_identity']], 'recorder_source': task['recorder_source'],
            'guard_source': task['guard_source'], 'automatic_retry': False}
        refs.append(common.write_new(target / 'scope.json', scope, 0o400))
    return active_ref, refs
