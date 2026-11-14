"""New Camera/Player scopes, exact source copies and one fresh acoustic nonce."""
import copy
import os
from pathlib import Path
import re
import secrets

IDENTITIES = ('target_identity', 'player_identity', 'helper_identity')
BASE_FIELDS = {'schema', 'kind', 'baseline', 'qualification', *IDENTITIES,
    'framework_epoch_sha256', 'support_manifest', 'target_profile', 'player_profile',
    'helper_profile', 'limits', 'source_preparation', 'task_source_manifests',
    'original_gates', 'flows', 'case_root', 'audio_nonce', 'whole_app_business_accepted', 'automatic_retry'}
ACTIVE_FIELDS = BASE_FIELDS | {'base_plan', 'lease', 'action_lock'}

def named(c, packet, name):
    rows = [r for r in packet['files'] if Path(r['path']).name == name]
    c.need(len(rows) == 1, 'ONE_FROZEN_CAMERA_VIDEO_COMPONENT:' + name)
    return c.module(rows[0], 'current_camera_video_' + Path(name).stem)

def preparation(c, ref):
    v = c.parse(c.read_ref(ref))
    c.need(v.get('schema') == 'pocket4-current-camera-video-preparation-v1'
        and v.get('code_entrypoints_complete') is True
        and v.get('Android_execution_authorized_by_publication') is False
        and v.get('whole_app_business_accepted') is False
        and type(v.get('files')) is list and 16 <= len(v['files']) <= 64
        and len({Path(r['path']).name for r in v['files']}) == len(v['files'])
        and type(v.get('origins')) is list and 1 <= len(v['origins']) <= 64,
        'COMPLETE_CURRENT_VIDEO_SOURCE_PREPARATION_REQUIRED')
    for row in v['files'] + v['origins']:
        c.read_ref(row)
    return v

def source_packet(c, value, packet):
    active = value.get('schema') == 'pocket4-current-camera-video-active-plan-v1'
    c.need(set(value) == (ACTIVE_FIELDS if active else BASE_FIELDS)
        and value['schema'] in ('pocket4-current-camera-video-plan-v1', 'pocket4-current-camera-video-active-plan-v1')
        and value['kind'] == 'camera_video', 'EXACT_VIDEO_SOURCE_PLAN')
    root = Path(value['case_root']); refs = value['task_source_manifests']
    c.need(root.parent == c.FINAL / 'qualification'
        and re.fullmatch('business-camera-video-plan-[0-9a-f]{32}', root.name)
        and set(refs) == {'camera', 'player'} and all(Path(refs[k]['path']) == root / ('task-' + k + '.json')
            for k in refs), 'TWO_EXACT_PACKAGE_SPECIFIC_TASK_SOURCE_PATHS')
    expected = [{'path': str(root / 'source' / Path(row['path']).name),
        'bytes': row['bytes'], 'sha256': row['sha256']} for row in packet['files']]
    by_name = {Path(r['path']).name: r for r in expected}
    target, player, _, _ = named(c, packet, 'camera_profiles.py').profiles(value['kind'])
    origins = []
    for row in [value['source_preparation']] + packet['files'] + packet['origins']:
        if row not in origins: origins.append(row)
    c.need(len(origins) <= 128, 'BOUNDED_VIDEO_PROVENANCE')
    result = {}
    for role, profile in (('camera', target), ('player', player)):
        task = c.parse(c.read_ref(refs[role]))
        wanted = {'schema': 'pocket4-final-business-task-source-v1', 'files': expected, 'origins': origins,
            'guard_source': by_name['camera_guard.py'], 'recorder_source': by_name['camera_flow.py'],
            'target_package': profile['package'], 'target_uid': profile['uid'],
            'old_runtime_authority_transferred': False}
        c.need(task == wanted, 'EXTERNAL_PREPARATION_MUST_MATCH_EVERY_TASK_BYTE_AND_ROLE:' + role)
        for row in task['files'] + task['origins']: c.read_ref(row)
        result[role] = task
    return result

def inputs(c, kind, request, packet):
    c.need(set(request) == {'baseline', 'qualification', *IDENTITIES}, 'THREE_FRESH_IDENTITIES_REQUIRED')
    _, modules = c.support(c.SUPPORT_REF)
    baseline = modules['business_baseline.py'].BusinessBaseline(request['baseline'], request['qualification'])
    c.need(baseline.qualification['source_manifest'] == c.SUPPORT_REF, 'ACTUAL_CURRENT_MAIN_SUPPORT')
    target, player, helper, limits = named(c, packet, 'camera_profiles.py').profiles(kind)
    identities = []
    for role, profile in (('target', target), ('player', player), ('helper', helper)):
        actual = c.parse(c.read_ref(request[role + '_identity']))
        c.validate_identity(actual, profile, request['baseline'], request['qualification'])
        identities.append(actual)
        if role != 'helper':
            c.need(baseline.value['data_continuity']['package_uids'][profile['package']] == profile['uid'],
                'ORIGINAL45_CAMERA_AND_PLAYER_DATA_UID')
    baseline.guard()
    return baseline, target, player, helper, limits, identities

def create(c, kind, request, output, preparation_ref):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_CURRENT_VIDEO_PLAN_FACTORY')
    packet = preparation(c, preparation_ref)
    baseline, target, player, helper, limits, _ = inputs(c, kind, request, packet)
    root = Path(output)
    c.need(root.parent == c.FINAL / 'qualification'
        and re.fullmatch('business-camera-video-plan-[0-9a-f]{32}', root.name), 'CREATE_ONLY_NEW_VIDEO_PLAN')
    root = c.private_dir(root, create=True); source = c.private_dir(root / 'source', create=True)
    files = [c.write_new(source / Path(r['path']).name, c.read_ref(r), 0o400) for r in packet['files']]
    by_name = {Path(r['path']).name: r for r in files}; origins = []
    for r in [preparation_ref] + packet['files'] + packet['origins']:
        if r not in origins: origins.append(r)
    c.need(len(origins) <= 128, 'BOUNDED_VIDEO_PROVENANCE')
    tasks = {}
    for role, profile in (('camera', target), ('player', player)):
        tasks[role] = c.write_new(root / ('task-' + role + '.json'), {
            'schema': 'pocket4-final-business-task-source-v1', 'files': files, 'origins': origins,
            'guard_source': by_name['camera_guard.py'], 'recorder_source': by_name['camera_flow.py'],
            'target_package': profile['package'], 'target_uid': profile['uid'],
            'old_runtime_authority_transferred': False}, 0o400)
    flows = []
    for role in ('camera', 'player', 'camera'):
        nonce = secrets.token_hex(16)
        c.need(nonce not in {r['nonce'] for r in flows}, 'DISTINCT_NORMAL_LAUNCH_SCOPES')
        flows.append({'role': role, 'nonce': nonce,
            'flow_root': str(c.FINAL / 'qualification' / ('business-flow-camera-video-' + nonce))})
    audio_nonce = secrets.token_hex(8)
    c.need(audio_nonce != '0' * 16, 'ZERO_ACOUSTIC_NONCE_REFUSED_WITHOUT_REDRAW')
    value = {'schema': 'pocket4-current-camera-video-plan-v1', 'kind': kind, **request,
        'framework_epoch_sha256': baseline.value['framework_epoch']['sha256'], 'support_manifest': c.SUPPORT_REF,
        'target_profile': target, 'player_profile': player, 'helper_profile': helper, 'limits': limits,
        'source_preparation': preparation_ref, 'task_source_manifests': tasks,
        'original_gates': c.GATES, 'flows': flows, 'audio_nonce': audio_nonce, 'case_root': str(root),
        'whole_app_business_accepted': False, 'automatic_retry': False}
    c.read_ref(c.GATES); baseline.guard()
    return c.write_new(root / 'plan.json', value, 0o400)

def validate(c, value, baseline, scope=None, *, semantic=True):
    active = value.get('schema') == 'pocket4-current-camera-video-active-plan-v1'
    c.need(set(value) == (ACTIVE_FIELDS if active else BASE_FIELDS)
        and value['schema'] in ('pocket4-current-camera-video-plan-v1', 'pocket4-current-camera-video-active-plan-v1')
        and value['kind'] == 'camera_video' and value['whole_app_business_accepted'] is False
        and value['automatic_retry'] is False, 'EXACT_CURRENT_VIDEO_PLAN')
    packet = preparation(c, value['source_preparation'])
    target, player, helper, limits = named(c, packet, 'camera_profiles.py').profiles(value['kind'])
    c.need(value['support_manifest'] == c.SUPPORT_REF and value['baseline'] == baseline.baseline_ref
        and value['qualification'] == baseline.qualification_ref
        and value['framework_epoch_sha256'] == baseline.value['framework_epoch']['sha256']
        and (value['target_profile'], value['player_profile'], value['helper_profile'], value['limits'])
            == (target, player, helper, limits) and value['original_gates'] == c.GATES
        and re.fullmatch('[0-9a-f]{16}', value['audio_nonce']) and value['audio_nonce'] != '0' * 16,
        'UNCHANGED_VIDEO_CURRENT_INPUTS_AND_NONCE')
    source_packet(c, value, packet)
    c.need(type(value['flows']) is list and len(value['flows']) == 3
        and [r['role'] for r in value['flows']] == ['camera', 'player', 'camera']
        and len({r['nonce'] for r in value['flows']}) == 3
        and all(set(r) == {'role', 'nonce', 'flow_root'} and re.fullmatch('[0-9a-f]{32}', r['nonce'])
            and Path(r['flow_root']) == c.FINAL / 'qualification' / ('business-flow-camera-video-' + r['nonce'])
            for r in value['flows']), 'THREE_INDEPENDENT_CURRENT_PACKAGE_SCOPES')
    if scope is not None:
        matches = [r for r in value['flows'] if r['nonce'] == scope['nonce'] and r['flow_root'] == scope['flow_root']]
        c.need(active and len(matches) == 1, 'EXACT_ACTIVE_VIDEO_SCOPE')
        role = matches[0]['role']; identity_key = 'target_identity' if role == 'camera' else 'player_identity'
        profile = target if role == 'camera' else player
        companions = [value[k] for k in IDENTITIES if k != identity_key]
        c.need(scope['task_source_manifest'] == value['task_source_manifests'][role]
            and scope['actual_resolution_receipt'] == value[identity_key]
            and scope['installed_helper_receipts'] == companions and scope['support_manifest'] == c.SUPPORT_REF
            and (scope['package'], scope['uid'], scope['component'])
                == (profile['package'], profile['uid'], profile['component']), 'EXACT_ROLE_BOUND_RECORDER_SCOPE')
    if semantic:
        return inputs(c, value['kind'], {k: value[k] for k in ('baseline', 'qualification', *IDENTITIES)}, packet)

def activate(c, base_ref, lease_ref, lock_ref):
    base = c.parse(c.read_ref(base_ref)); _, modules = c.support(base['support_manifest'])
    baseline = modules['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    validate(c, base, baseline); c.read_ref(lease_ref); c.read_ref(lock_ref)
    active = {**base, 'schema': 'pocket4-current-camera-video-active-plan-v1',
        'base_plan': base_ref, 'lease': lease_ref, 'action_lock': lock_ref}
    active_ref = c.write_new(Path(base['case_root']) / 'active-plan.json', active, 0o400); refs = []
    for item in base['flows']:
        role = item['role']; identity_key = 'target_identity' if role == 'camera' else 'player_identity'
        profile = base['target_profile'] if role == 'camera' else base['player_profile']
        task = c.parse(c.read_ref(base['task_source_manifests'][role]))
        root = c.private_dir(item['flow_root'], create=True); c.private_dir(root / 'steps', create=True)
        scope = {'schema': 'pocket4-final-business-recorder-scope-v1', 'business_baseline': base['baseline'],
            'business_qualification': base['qualification'], 'support_manifest': base['support_manifest'],
            'framework_epoch_sha256': base['framework_epoch_sha256'], 'package': profile['package'],
            'uid': profile['uid'], 'user': 0, 'component': profile['component'],
            'nonce': item['nonce'], 'flow_root': item['flow_root'],
            'task_source_manifest': base['task_source_manifests'][role], 'phase_plan': active_ref,
            'actual_resolution_receipt': base[identity_key],
            'installed_helper_receipts': [base[k] for k in IDENTITIES if k != identity_key],
            'recorder_source': task['recorder_source'], 'guard_source': task['guard_source'], 'automatic_retry': False}
        refs.append(c.write_new(root / 'scope.json', scope, 0o400))
    return active_ref, refs
