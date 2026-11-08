"""Create-only Settings plans bound to final Main, three signed identities and original gates."""
import os
from pathlib import Path
import re
import secrets

REQUEST_FIELDS = {'baseline', 'qualification', 'target_identity', 'helper_identity'}
BASE_FIELDS = REQUEST_FIELDS | {'schema', 'kind', 'framework_epoch_sha256', 'support_manifest',
    'target_profile', 'helper_profile', 'limits', 'routes', 'source_preparation',
    'task_source_manifest', 'original_gates', 'original_business_checks', 'flows', 'case_root',
    'whole_app_business_accepted', 'automatic_retry'}
ACTIVE_FIELDS = BASE_FIELDS | {'base_plan', 'lease', 'action_lock'}
KINDS = ('settings_pages', 'settings_permissions', 'settings_roundtrip')

def named(c, packet, name):
    rows = [r for r in packet['files'] if Path(r['path']).name == name]
    c.need(len(rows) == 1, 'ONE_PINNED_SETTINGS_MODULE:' + name)
    return c.module(rows[0], 'fresh_settings_' + Path(name).stem)

def preparation(c, ref):
    p = c.parse(c.read_ref(ref))
    c.need(p.get('schema') == 'pocket4-final-settings-preparation-v1'
        and p.get('code_entrypoints_complete') is True
        and p.get('Android_execution_authorized_by_publication') is False
        and isinstance(p.get('files'), list) and 12 <= len(p['files']) <= 48
        and len({Path(r['path']).name for r in p['files']}) == len(p['files'])
        and isinstance(p.get('origins'), list) and 1 <= len(p['origins']) <= 64,
        'COMPLETE_SOURCE_BOUND_SETTINGS_PREPARATION')
    for row in p['files'] + p['origins']:
        c.read_ref(row)
    return p

def inputs(c, kind, request, packet):
    c.need(kind in KINDS and set(request) == REQUEST_FIELDS, 'EXACT_NEW_SETTINGS_INPUTS')
    _, support = c.support(c.SUPPORT_REF)
    baseline = support['business_baseline.py'].BusinessBaseline(request['baseline'], request['qualification'])
    c.need(c.parse(c.read_ref(request['qualification']))['source_manifest'] == c.SUPPORT_REF,
        'CURRENT_SAME_BASELINE_SUPPORT')
    p = named(c, packet, 'settings_profiles.py')
    target, helper, limits = p.profiles(kind)
    for role, profile in [('target', target), ('helper', helper)]:
        identity = c.parse(c.read_ref(request[role + '_identity']))
        c.validate_identity(identity, profile, request['baseline'], request['qualification'])
        if role == 'target':
            c.need(baseline.value['data_continuity']['package_uids'][profile['package']] == profile['uid'],
                'PRESERVED_ORIGINAL_PACKAGE_UID:' + role)
    gates = c.parse(c.read_ref(c.GATES))
    c.need(gates['profiles']['settings']['checks'] == p.GATES, 'ALL_THREE_ORIGINAL_SETTINGS_GATES_UNCHANGED')
    baseline.guard()
    return baseline, target, helper, limits, p.ROUTES, p.GATES

def source_packet(c, value, packet):
    active = value.get('schema') == 'pocket4-final-settings-active-plan-v1'
    c.need(set(value) == (ACTIVE_FIELDS if active else BASE_FIELDS)
        and value.get('schema') in ('pocket4-final-settings-plan-v1', 'pocket4-final-settings-active-plan-v1')
        and value.get('kind') in KINDS, 'EXACT_SOURCE_BOUND_SETTINGS_PLAN')
    root = Path(value['case_root'])
    c.need(root.parent == c.FINAL / 'qualification'
        and re.fullmatch('business-' + value['kind'].replace('_', '-') + '-plan-[0-9a-f]{32}', root.name)
        and Path(value['task_source_manifest']['path']) == root / 'task-source.json', 'NEW_SETTINGS_TASK_SOURCE_LOCATION')
    task = c.parse(c.read_ref(value['task_source_manifest']))
    expected = [{'path': str(root / 'source' / Path(r['path']).name), 'bytes': r['bytes'], 'sha256': r['sha256']}
        for r in packet['files']]
    by_name = {Path(r['path']).name: r for r in expected}
    origins = []
    for row in [value['source_preparation']] + packet['files'] + packet['origins']:
        if row not in origins:
            origins.append(row)
    p = named(c, packet, 'settings_profiles.py')
    c.need(task == {'schema': 'pocket4-final-business-task-source-v1', 'files': expected, 'origins': origins,
        'guard_source': by_name['settings_guard.py'], 'recorder_source': by_name['settings_flow.py'],
        'target_package': p.SETTINGS['package'], 'target_uid': p.SETTINGS['uid'],
        'old_runtime_authority_transferred': False}, 'EXTERNALLY_PINNED_TASK_SOURCE_AND_ORIGINS')
    for row in expected + origins:
        c.read_ref(row)
    return task

def create(c, kind, request, output, preparation_ref):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_SOURCE_BOUND_SETTINGS_FACTORY')
    packet = preparation(c, preparation_ref)
    baseline, target, helper, limits, routes, checks = inputs(c, kind, request, packet)
    root = Path(output)
    c.need(root.parent == c.FINAL / 'qualification'
        and re.fullmatch('business-' + kind.replace('_', '-') + '-plan-[0-9a-f]{32}', root.name),
        'NEW_CREATE_ONLY_SETTINGS_PLAN_ROOT')
    root = c.private_dir(root, create=True); source = c.private_dir(root / 'source', create=True)
    files = [c.write_new(source / Path(r['path']).name, c.read_ref(r), 0o400) for r in packet['files']]
    by_name = {Path(r['path']).name: r for r in files}
    origins = []
    for row in [preparation_ref] + packet['files'] + packet['origins']:
        if row not in origins:
            origins.append(row)
    c.need(len(origins) <= 128, 'BOUNDED_SETTINGS_SOURCE_CHAIN')
    task = {'schema': 'pocket4-final-business-task-source-v1', 'files': files, 'origins': origins,
        'guard_source': by_name['settings_guard.py'], 'recorder_source': by_name['settings_flow.py'],
        'target_package': target['package'], 'target_uid': target['uid'], 'old_runtime_authority_transferred': False}
    task_ref = c.write_new(root / 'task-source.json', task, 0o400)
    flows = []
    for _ in range(2):
        nonce = secrets.token_hex(16)
        c.need(nonce not in {r['nonce'] for r in flows}, 'TWO_DISTINCT_NEW_NATIVE_LAUNCH_SCOPES')
        flows.append({'nonce': nonce, 'flow_root': str(c.FINAL / 'qualification' /
            ('business-flow-' + kind.replace('_', '-') + '-' + nonce))})
    plan = {'schema': 'pocket4-final-settings-plan-v1', 'kind': kind, **request,
        'framework_epoch_sha256': baseline.value['framework_epoch']['sha256'], 'support_manifest': c.SUPPORT_REF,
        'target_profile': target, 'helper_profile': helper, 'limits': limits,
        'routes': routes, 'source_preparation': preparation_ref, 'task_source_manifest': task_ref,
        'original_gates': c.GATES, 'original_business_checks': checks, 'flows': flows, 'case_root': str(root),
        'whole_app_business_accepted': False, 'automatic_retry': False}
    baseline.guard()
    return c.write_new(root / 'plan.json', plan, 0o400)

def validate(c, value, baseline, scope=None, *, semantic=True):
    active = value.get('schema') == 'pocket4-final-settings-active-plan-v1'
    c.need(set(value) == (ACTIVE_FIELDS if active else BASE_FIELDS) and value.get('kind') in KINDS
        and value.get('schema') in ('pocket4-final-settings-plan-v1', 'pocket4-final-settings-active-plan-v1')
        and value['whole_app_business_accepted'] is False and value['automatic_retry'] is False, 'EXACT_SETTINGS_PLAN')
    packet = preparation(c, value['source_preparation']); p = named(c, packet, 'settings_profiles.py')
    target, helper, limits = p.profiles(value['kind'])
    c.need(value['support_manifest'] == c.SUPPORT_REF and value['baseline'] == baseline.baseline_ref
        and value['qualification'] == baseline.qualification_ref
        and value['framework_epoch_sha256'] == baseline.value['framework_epoch']['sha256']
        and (value['target_profile'], value['helper_profile'], value['limits']) ==
            (target, helper, limits)
        and value['routes'] == p.ROUTES and value['original_gates'] == c.GATES
        and value['original_business_checks'] == p.GATES, 'SETTINGS_IDENTITY_LIMITS_OR_GATES_CHANGED')
    source_packet(c, value, packet)
    c.need(len(value['flows']) == 2 and len({r['nonce'] for r in value['flows']}) == 2
        and all(set(r) == {'nonce', 'flow_root'} and re.fullmatch('[0-9a-f]{32}', r['nonce'])
            and Path(r['flow_root']) == c.FINAL / 'qualification' /
                ('business-flow-' + value['kind'].replace('_', '-') + '-' + r['nonce']) for r in value['flows']),
        'TWO_NEW_SINGLE_NATIVE_LAUNCH_SCOPES')
    if scope is not None:
        c.need(active and scope['task_source_manifest'] == value['task_source_manifest']
            and scope['actual_resolution_receipt'] == value['target_identity']
            and scope['installed_helper_receipts'] == [value['helper_identity']]
            and scope['support_manifest'] == c.SUPPORT_REF and scope['package'] == target['package']
            and scope['uid'] == target['uid'] and scope['component'] == target['component']
            and {'nonce': scope['nonce'], 'flow_root': scope['flow_root']} in value['flows'],
            'SETTINGS_SCOPE_AND_EXACT_COMPANION_IDENTITY')
    if semantic:
        return inputs(c, value['kind'], {k: value[k] for k in REQUEST_FIELDS}, packet)

def activate(c, base_ref, lease_ref, lock_ref):
    base = c.parse(c.read_ref(base_ref)); _, support = c.support(base['support_manifest'])
    baseline = support['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    validate(c, base, baseline); c.read_ref(lease_ref); c.read_ref(lock_ref)
    active = {**base, 'schema': 'pocket4-final-settings-active-plan-v1', 'base_plan': base_ref,
        'lease': lease_ref, 'action_lock': lock_ref}
    active_ref = c.write_new(Path(base['case_root']) / 'active-plan.json', active, 0o400)
    task = c.parse(c.read_ref(base['task_source_manifest'])); scopes = []
    for flow in base['flows']:
        root = c.private_dir(flow['flow_root'], create=True); c.private_dir(root / 'steps', create=True)
        scope = {'schema': 'pocket4-final-business-recorder-scope-v1', 'business_baseline': base['baseline'],
            'business_qualification': base['qualification'], 'support_manifest': base['support_manifest'],
            'framework_epoch_sha256': base['framework_epoch_sha256'], 'package': base['target_profile']['package'],
            'uid': base['target_profile']['uid'], 'user': 0, 'component': base['target_profile']['component'], **flow,
            'task_source_manifest': base['task_source_manifest'], 'phase_plan': active_ref,
            'actual_resolution_receipt': base['target_identity'],
            'installed_helper_receipts': [base['helper_identity']],
            'recorder_source': task['recorder_source'], 'guard_source': task['guard_source'], 'automatic_retry': False}
        scopes.append(c.write_new(root / 'scope.json', scope, 0o400))
    return active_ref, scopes
