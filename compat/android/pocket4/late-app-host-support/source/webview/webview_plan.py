"""Create-only fresh-Main factories for the two original fixture cases."""
import os
from pathlib import Path
import re
import secrets

BASE_FIELDS = {'schema', 'kind', 'baseline', 'qualification', 'target_identity', 'helper_identity', 'protection_identity',
    'framework_epoch_sha256', 'support_manifest', 'target_profile', 'helper_profile', 'limits',
    'source_preparation', 'task_source_manifest', 'original_gates', 'flows', 'case_root', 'run_id',
    'whole_app_business_accepted', 'automatic_retry'}
ACTIVE_FIELDS = BASE_FIELDS | {'base_plan', 'lease', 'action_lock'}
KINDS = ('webview_business10', 'webview_media11')

def named(c, packet, name):
    found = [r for r in packet['files'] if Path(r['path']).name == name]
    c.need(len(found) == 1, 'ONE_PINNED_NEW_WEBVIEW_MODULE:' + name)
    return c.module(found[0], 'new_webview_case_' + Path(name).stem)

def preparation(c, ref):
    value = c.parse(c.read_ref(ref))
    c.need(value.get('schema') == 'pocket4-final-webview-preparation-v1'
        and value.get('code_entrypoints_complete') is True
        and value.get('Android_execution_authorized_by_publication') is False
        and type(value.get('files')) is list and 15 <= len(value['files']) <= 64
        and len({Path(r['path']).name for r in value['files']}) == len(value['files'])
        and type(value.get('origins')) is list and 1 <= len(value['origins']) <= 64,
        'COMPLETE_REVIEWED_NEW_WEBVIEW_SOURCE_REQUIRED')
    for row in value['files'] + value['origins']:
        c.read_ref(row)
    return value

def source_packet(c, value, packet):
    active = value.get('schema') == 'pocket4-final-webview-active-plan-v1'
    kind = value.get('kind')
    c.need(set(value) == (ACTIVE_FIELDS if active else BASE_FIELDS)
        and value['schema'] in ('pocket4-final-webview-plan-v1', 'pocket4-final-webview-active-plan-v1')
        and kind in KINDS, 'SOURCE_PACKET_NEEDS_EXACT_NEW_WEBVIEW_PLAN')
    root = Path(value['case_root'])
    c.need(root.parent == c.FINAL / 'qualification'
        and re.fullmatch('business-' + kind.replace('_', '-') + '-plan-[0-9a-f]{32}', root.name)
        and Path(value['task_source_manifest']['path']) == root / 'task-source.json',
        'EXACT_CREATE_ONLY_TASK_SOURCE_LOCATION')
    task = c.parse(c.read_ref(value['task_source_manifest']))
    c.need(type(task) is dict and set(task) == {'schema', 'files', 'origins', 'guard_source', 'recorder_source',
        'target_package', 'target_uid', 'old_runtime_authority_transferred'}
        and task['schema'] == 'pocket4-final-business-task-source-v1'
        and task['old_runtime_authority_transferred'] is False, 'EXACT_NEW_TASK_SOURCE_SCHEMA')
    expected = [{'path': str(root / 'source' / Path(row['path']).name), 'bytes': row['bytes'],
                 'sha256': row['sha256']} for row in packet['files']]
    c.need(task['files'] == expected, 'TASK_CODE_MUST_MATCH_EXTERNALLY_PINNED_PREPARATION')
    by_name = {Path(row['path']).name: row for row in expected}
    target, _, _ = named(c, packet, 'webview_profiles.py').profiles(kind)
    origins = []
    for row in [value['source_preparation']] + packet['files'] + packet['origins']:
        if row not in origins:
            origins.append(row)
    c.need(task['origins'] == origins and len(origins) <= 128
        and task['guard_source'] == by_name['webview_guard.py']
        and task['recorder_source'] == by_name['webview_flow.py']
        and task['target_package'] == target['package'] and type(task['target_uid']) is int
        and task['target_uid'] == target['uid'], 'EXACT_FROZEN_TASK_TARGET_GUARD_RECORDER_AND_ORIGINS')
    for row in task['files'] + task['origins']:
        c.read_ref(row)
    return task

def inputs(c, kind, request, packet):
    c.need(set(request) == {'baseline', 'qualification', 'target_identity', 'helper_identity', 'protection_identity'},
           'REAL_TARGET_AND_HELPER_IDENTITIES_AND_FRESH_MAIN_REQUIRED')
    _, support = c.support(c.SUPPORT_REF)
    baseline = support['business_baseline.py'].BusinessBaseline(request['baseline'], request['qualification'])
    c.need(baseline.qualification['source_manifest'] == c.SUPPORT_REF, 'SAME_CURRENT_FROZEN_BASELINE_REQUIRED')
    p = named(c, packet, 'webview_profiles.py'); target, helper, limits = p.profiles(kind)
    identities = []
    for role, profile in [('target', target), ('helper', helper)]:
        identity = c.parse(c.read_ref(request[role + '_identity']))
        c.validate_identity(identity, profile, request['baseline'], request['qualification'])
        identities.append(identity)
    c.need(baseline.value['data_continuity']['package_uids'][target['package']] == target['uid'],
           'ORIGINAL_TARGET_DATA_UID_REQUIRED')
    protection = c.parse(c.read_ref(request['protection_identity']))
    source = next(row for row in packet['files'] if Path(row['path']).name == 'webview_protection.py')
    named(c, packet, 'webview_protection.py').validate(c, protection,
        {k: request[k] for k in ('baseline', 'qualification', 'target_identity')}, p, source)
    baseline.guard()
    return baseline, target, helper, limits, identities

def create(c, kind, request, output, preparation_ref):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_FRESH_WEBVIEW_FACTORY_REQUIRED')
    packet = preparation(c, preparation_ref)
    baseline, target, helper, limits, _ = inputs(c, kind, request, packet)
    root = Path(output)
    c.need(root.parent == c.FINAL / 'qualification'
        and re.fullmatch('business-' + kind.replace('_', '-') + '-plan-[0-9a-f]{32}', root.name),
        'NEW_CREATE_ONLY_WEBVIEW_CASE_ROOT')
    root = c.private_dir(root, create=True); source = c.private_dir(root / 'source', create=True)
    files = [c.write_new(source / Path(row['path']).name, c.read_ref(row), 0o400) for row in packet['files']]
    by_name = {Path(r['path']).name: r for r in files}
    origins = []
    for row in [preparation_ref] + packet['files'] + packet['origins']:
        if row not in origins:
            origins.append(row)
    c.need(len(origins) <= 128, 'BOUNDED_ORIGINAL_SOURCE_CHAIN')
    task = {'schema': 'pocket4-final-business-task-source-v1', 'files': files, 'origins': origins,
        'guard_source': by_name['webview_guard.py'], 'recorder_source': by_name['webview_flow.py'],
        'target_package': target['package'], 'target_uid': target['uid'], 'old_runtime_authority_transferred': False}
    task_ref = c.write_new(root / 'task-source.json', task, 0o400)
    flows = []
    for _ in range(2):
        nonce = secrets.token_hex(16)
        c.need(nonce not in {r['nonce'] for r in flows}, 'DISTINCT_NEW_LAUNCH_NONCES')
        flows.append({'nonce': nonce, 'flow_root': str(c.FINAL / 'qualification' /
            ('business-flow-' + kind.replace('_', '-') + '-' + nonce))})
    run_id = secrets.token_hex(16)
    plan = {'schema': 'pocket4-final-webview-plan-v1', 'kind': kind, **request,
        'framework_epoch_sha256': baseline.value['framework_epoch']['sha256'], 'support_manifest': c.SUPPORT_REF,
        'target_profile': target, 'helper_profile': helper, 'limits': limits, 'source_preparation': preparation_ref,
        'task_source_manifest': task_ref, 'original_gates': c.GATES, 'flows': flows, 'case_root': str(root),
        'run_id': run_id, 'whole_app_business_accepted': False, 'automatic_retry': False}
    c.read_ref(c.GATES); baseline.guard()
    return c.write_new(root / 'plan.json', plan, 0o400)

def validate(c, value, baseline, scope=None, *, semantic=True):
    active = value.get('schema') == 'pocket4-final-webview-active-plan-v1'; kind = value.get('kind')
    c.need(set(value) == (ACTIVE_FIELDS if active else BASE_FIELDS)
        and value['schema'] in ('pocket4-final-webview-plan-v1', 'pocket4-final-webview-active-plan-v1')
        and kind in KINDS and value['whole_app_business_accepted'] is False and value['automatic_retry'] is False,
        'EXACT_NEW_WEBVIEW_PLAN')
    packet = preparation(c, value['source_preparation'])
    target, helper, limits = named(c, packet, 'webview_profiles.py').profiles(kind)
    c.need(value['support_manifest'] == c.SUPPORT_REF and value['baseline'] == baseline.baseline_ref
        and value['qualification'] == baseline.qualification_ref
        and value['framework_epoch_sha256'] == baseline.value['framework_epoch']['sha256']
        and (value['target_profile'], value['helper_profile'], value['limits']) == (target, helper, limits)
        and value['original_gates'] == c.GATES, 'ORIGINAL_INPUTS_OR_ACTUAL_MAIN_CHANGED')
    c.need(type(value['run_id']) is str and re.fullmatch('[0-9a-f]{32}', value['run_id']),
        'FRESH_ORIGINAL_RANDOM_WEBVIEW_RUN_NAMESPACE')
    source_packet(c, value, packet)
    c.need(len(value['flows']) == 2 and len({r['nonce'] for r in value['flows']}) == 2
        and all(set(r) == {'nonce', 'flow_root'} and re.fullmatch('[0-9a-f]{32}', r['nonce'])
            and Path(r['flow_root']) == c.FINAL / 'qualification' /
                ('business-flow-' + kind.replace('_', '-') + '-' + r['nonce']) for r in value['flows']),
        'TWO_INDEPENDENT_FRESH_LAUNCH_SCOPES')
    if scope is not None:
        c.need(active and scope['task_source_manifest'] == value['task_source_manifest']
            and scope['actual_resolution_receipt'] == value['target_identity']
            and scope['installed_helper_receipts'] == [value['helper_identity']]
            and scope['support_manifest'] == c.SUPPORT_REF and scope['package'] == target['package']
            and scope['uid'] == target['uid'] and scope['component'] == target['component']
            and {'nonce': scope['nonce'], 'flow_root': scope['flow_root']} in value['flows'],
            'RECORDER_SCOPE_NOT_THIS_FRESH_ORIGINAL_CASE')
    if semantic:
        return inputs(c, kind, {k: value[k] for k in ('baseline', 'qualification', 'target_identity', 'helper_identity', 'protection_identity')}, packet)

def activate(c, base_ref, lease_ref, lock_ref):
    base = c.parse(c.read_ref(base_ref)); _, modules = c.support(base['support_manifest'])
    baseline = modules['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    validate(c, base, baseline); c.read_ref(lease_ref); c.read_ref(lock_ref)
    active = {**base, 'schema': 'pocket4-final-webview-active-plan-v1', 'base_plan': base_ref,
              'lease': lease_ref, 'action_lock': lock_ref}
    active_ref = c.write_new(Path(base['case_root']) / 'active-plan.json', active, 0o400)
    task = c.parse(c.read_ref(base['task_source_manifest'])); refs = []
    for flow in base['flows']:
        root = c.private_dir(flow['flow_root'], create=True); c.private_dir(root / 'steps', create=True)
        scope = {'schema': 'pocket4-final-business-recorder-scope-v1', 'business_baseline': base['baseline'],
            'business_qualification': base['qualification'], 'support_manifest': base['support_manifest'],
            'framework_epoch_sha256': base['framework_epoch_sha256'], 'package': base['target_profile']['package'],
            'uid': base['target_profile']['uid'], 'user': 0, 'component': base['target_profile']['component'], **flow,
            'task_source_manifest': base['task_source_manifest'], 'phase_plan': active_ref,
            'actual_resolution_receipt': base['target_identity'], 'installed_helper_receipts': [base['helper_identity']],
            'recorder_source': task['recorder_source'], 'guard_source': task['guard_source'], 'automatic_retry': False}
        refs.append(c.write_new(root / 'scope.json', scope, 0o400))
    return active_ref, refs
