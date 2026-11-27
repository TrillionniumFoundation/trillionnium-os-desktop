"""Create-only fresh-Main factories. No Android operation or old runtime load."""
import os
from pathlib import Path
import re
import secrets

BASE_FIELDS = {'schema', 'kind', 'baseline', 'qualification', 'target_identity', 'provider_identity',
    'helper_identity', 'framework_epoch_sha256', 'support_manifest', 'target_profile', 'provider_profile',
    'helper_profile', 'limits', 'source_preparation', 'task_source_manifest', 'original_gates',
    'flows', 'case_root', 'whole_app_business_accepted', 'automatic_retry'}
ACTIVE_FIELDS = BASE_FIELDS | {'base_plan', 'lease', 'action_lock'}


def named(c, packet, name):
    found = [r for r in packet['files'] if Path(r['path']).name == name]
    c.need(len(found) == 1, 'ONE_PINNED_NEW_SYSTEM_MODULE:' + name)
    return c.module(found[0], 'new_system_case_' + Path(name).stem)


def preparation(c, ref):
    value = c.parse(c.read_ref(ref))
    c.need(value.get('schema') == 'pocket4-final-system-case-preparation-v1'
        and value.get('code_entrypoints_complete') is True
        and value.get('Android_execution_authorized_by_publication') is False
        and type(value.get('files')) is list and 20 <= len(value['files']) <= 128
        and len({Path(r['path']).name for r in value['files']}) == len(value['files'])
        and type(value.get('origins')) is list and 1 <= len(value['origins']) <= 128,
        'COMPLETE_REVIEWED_NEW_SYSTEM_SOURCE_REQUIRED')
    for row in value['files'] + value['origins']:
        c.read_ref(row)
    return value


def source_packet(c, value, packet):
    """Bind every task module to the externally pinned preparation before exec.

    This is source admission only. Actual Main, identities, phase, owner and
    original per-App predicates are still checked by validate/ScopeBinding.
    """
    active = value.get('schema') == 'pocket4-final-system-active-plan-v1'
    kind = value.get('kind')
    c.need(set(value) == (ACTIVE_FIELDS if active else BASE_FIELDS)
        and value['schema'] in ('pocket4-final-system-case-plan-v1', 'pocket4-final-system-active-plan-v1')
        and kind == 'calendar_reminder', 'SOURCE_PACKET_NEEDS_EXACT_NEW_PLAN')
    root = Path(value['case_root'])
    c.need(c.case_root_matches(root,kind.replace('_','-'),
            'business-'+kind.replace('_','-')+'-plan-[0-9a-f]{32}')
        and Path(value['task_source_manifest']['path']) == root / 'task-source.json',
        'EXACT_CREATE_ONLY_TASK_SOURCE_LOCATION')
    task = c.parse(c.read_ref(value['task_source_manifest']))
    c.need(type(task) is dict and set(task) == {'schema', 'files', 'origins', 'guard_source',
        'recorder_source', 'target_package', 'target_uid', 'old_runtime_authority_transferred'}
        and task['schema'] == 'pocket4-final-business-task-source-v1'
        and task['old_runtime_authority_transferred'] is False, 'EXACT_NEW_TASK_SOURCE_SCHEMA')
    expected = [{'path': str(root / 'source' / Path(row['path']).name),
                 'bytes': row['bytes'], 'sha256': row['sha256']} for row in packet['files']]
    c.need(task['files'] == expected, 'TASK_CODE_MUST_MATCH_EXTERNALLY_PINNED_PREPARATION')
    by_name = {Path(row['path']).name: row for row in expected}
    p = named(c, packet, 'system_profiles.py'); target, _, _, _ = p.profiles(kind)
    origins = []
    for row in [value['source_preparation']] + packet['files'] + packet['origins']:
        if row not in origins:
            origins.append(row)
    c.need(task['origins'] == origins and len(origins) <= 128
        and task['guard_source'] == by_name['system_guard.py']
        and task['recorder_source'] == by_name['system_flow.py']
        and task['target_package'] == target['package'] and type(task['target_uid']) is int
        and task['target_uid'] == target['uid'], 'EXACT_FROZEN_TASK_TARGET_GUARD_RECORDER_AND_ORIGINS')
    for row in task['files'] + task['origins']:
        c.read_ref(row)
    return task


def inputs(c, kind, request, packet):
    c.need(set(request) == {'baseline', 'qualification', 'target_identity', 'provider_identity', 'helper_identity'},
           'THREE_REAL_PACKAGE_IDENTITIES_AND_FRESH_MAIN_REQUIRED')
    _, support = c.support(c.SUPPORT_REF)
    baseline = support['business_baseline.py'].BusinessBaseline(request['baseline'], request['qualification'])
    c.need(c.current_qualification_support(request['baseline'], request['qualification']) == c.SUPPORT_REF,
           'SAME_REVIEWED_R7_BASELINE_FOR_SAME_PROCESS_APIS')
    p = named(c, packet, 'system_profiles.py')
    target, provider, helper, limits = p.profiles(kind)
    identities = []
    for role, profile in [('target', target), ('provider', provider), ('helper', helper)]:
        identity = c.parse(c.read_ref(request[role + '_identity']))
        c.validate_identity(identity, profile, request['baseline'], request['qualification'])
        identities.append(identity)
    c.need(baseline.value['data_continuity']['package_uids'][target['package']] == target['uid'],
           'ORIGINAL_TARGET_DATA_UID_REQUIRED')
    if kind == 'calendar_reminder':
        installed = c.parse(c.read_ref(p.CALENDAR_INSTALL))
        c.need(installed['state'] == 'INSTALLED_VERIFIED_NOT_BUSINESS_QUALIFIED'
            and installed['new_sha256'] == target['apks'][0]['sha256'] and installed['install_calls'] == 1
            and installed['install_pending'] is False and installed['data_identity_preserved'] is True,
            'ORIGINAL_REPAIRED_CALENDAR_APK_CUSTODY_REQUIRED')
        proof = c.parse(c.read_ref(p.ATOMIC_REVIEW)); c.read_ref(p.TASK_PROOF)
        c.need(proof['provider_apk_sha256'] == provider['apks'][0]['sha256'],
               'SAME_ACTUAL_PROVIDER_FOR_ORIGINAL_ATOMIC_EMPTY_DELETE')
    baseline.guard()
    return baseline, target, provider, helper, limits, identities


def create(c, kind, request, output, preparation_ref):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_FRESH_SYSTEM_CASE_FACTORY_REQUIRED')
    packet = preparation(c, preparation_ref)
    baseline, target, provider, helper, limits, _ = inputs(c, kind, request, packet)
    root = Path(output)
    c.need(c.case_root_matches(root,kind.replace('_','-'),
            'business-'+kind.replace('_','-')+'-plan-[0-9a-f]{32}'),
        'NEW_CREATE_ONLY_SYSTEM_CASE_ROOT')
    root = c.private_dir(root, create=True); source = c.private_dir(root / 'source', create=True)
    files = [c.write_new(source / Path(row['path']).name, c.read_ref(row), 0o400) for row in packet['files']]
    by_name = {Path(r['path']).name: r for r in files}
    origins = []
    for row in [preparation_ref] + packet['files'] + packet['origins']:
        if row not in origins:
            origins.append(row)
    c.need(len(origins) <= 128, 'BOUNDED_ORIGINAL_SOURCE_CHAIN')
    task = {'schema': 'pocket4-final-business-task-source-v1', 'files': files, 'origins': origins,
        'guard_source': by_name['system_guard.py'], 'recorder_source': by_name['system_flow.py'],
        'target_package': target['package'], 'target_uid': target['uid'], 'old_runtime_authority_transferred': False}
    task_ref = c.write_new(root / 'task-source.json', task, 0o400)
    flows = []
    for _ in range(2):
        nonce = secrets.token_hex(16)
        c.need(nonce not in {r['nonce'] for r in flows}, 'DISTINCT_NEW_LAUNCH_NONCES')
        flows.append({'nonce': nonce, 'flow_root': str(c.flow_root(kind.replace('_','-'),nonce,kind.replace('_','-')))})
    plan = {'schema': 'pocket4-final-system-case-plan-v1', 'kind': kind, **request,
        'framework_epoch_sha256': baseline.value['framework_epoch']['sha256'], 'support_manifest': c.SUPPORT_REF,
        'target_profile': target, 'provider_profile': provider, 'helper_profile': helper, 'limits': limits,
        'source_preparation': preparation_ref, 'task_source_manifest': task_ref, 'original_gates': c.GATES,
        'flows': flows, 'case_root': str(root), 'whole_app_business_accepted': False, 'automatic_retry': False}
    c.read_ref(c.GATES); baseline.guard()
    return c.write_new(root / 'plan.json', plan, 0o400)


def validate(c, value, baseline, scope=None, *, semantic=True):
    active = value.get('schema') == 'pocket4-final-system-active-plan-v1'; kind = value.get('kind')
    c.need(set(value) == (ACTIVE_FIELDS if active else BASE_FIELDS)
        and value['schema'] in ('pocket4-final-system-case-plan-v1', 'pocket4-final-system-active-plan-v1')
        and kind == 'calendar_reminder' and value['whole_app_business_accepted'] is False
        and value['automatic_retry'] is False, 'EXACT_NEW_SYSTEM_CASE_PLAN')
    packet = preparation(c, value['source_preparation']); p = named(c, packet, 'system_profiles.py')
    target, provider, helper, limits = p.profiles(kind)
    c.need(value['support_manifest'] == c.SUPPORT_REF and value['baseline'] == baseline.baseline_ref
        and value['qualification'] == baseline.qualification_ref
        and value['framework_epoch_sha256'] == baseline.value['framework_epoch']['sha256']
        and (value['target_profile'], value['provider_profile'], value['helper_profile'], value['limits']) ==
            (target, provider, helper, limits) and value['original_gates'] == c.GATES,
        'ORIGINAL_INPUTS_OR_ACTUAL_MAIN_CHANGED')
    source_packet(c, value, packet)
    c.need(len(value['flows']) == 2 and len({r['nonce'] for r in value['flows']}) == 2
        and all(set(r) == {'nonce', 'flow_root'} and re.fullmatch('[0-9a-f]{32}', r['nonce'])
            and Path(r['flow_root']) == c.flow_root(kind.replace('_','-'),r['nonce'],kind.replace('_','-')) for r in value['flows']),
        'TWO_INDEPENDENT_FRESH_LAUNCH_SCOPES')
    if scope is not None:
        c.need(active and scope['task_source_manifest'] == value['task_source_manifest']
            and scope['actual_resolution_receipt'] == value['target_identity']
            and scope['installed_helper_receipts'] == [value['provider_identity'], value['helper_identity']]
            and scope['support_manifest'] == c.SUPPORT_REF and scope['package'] == target['package']
            and scope['uid'] == target['uid'] and scope['component'] == target['component']
            and {'nonce': scope['nonce'], 'flow_root': scope['flow_root']} in value['flows'],
            'RECORDER_SCOPE_NOT_THIS_FRESH_ORIGINAL_CASE')
    if semantic:
        return inputs(c, kind, {k: value[k] for k in ('baseline', 'qualification', 'target_identity',
            'provider_identity', 'helper_identity')}, packet)


def activate(c, base_ref, lease_ref, lock_ref):
    base = c.parse(c.read_ref(base_ref)); _, modules = c.support(base['support_manifest'])
    baseline = modules['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    validate(c, base, baseline); c.read_ref(lease_ref); c.read_ref(lock_ref)
    active = {**base, 'schema': 'pocket4-final-system-active-plan-v1', 'base_plan': base_ref,
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
            'actual_resolution_receipt': base['target_identity'],
            'installed_helper_receipts': [base['provider_identity'], base['helper_identity']],
            'recorder_source': task['recorder_source'], 'guard_source': task['guard_source'], 'automatic_retry': False}
        refs.append(c.write_new(root / 'scope.json', scope, 0o400))
    return active_ref, refs
