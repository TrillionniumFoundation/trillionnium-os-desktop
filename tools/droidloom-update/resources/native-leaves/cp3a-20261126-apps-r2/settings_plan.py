"""Fresh Main, exact package identities and immutable Settings task source."""
import os
from pathlib import Path
import re
import secrets

BASE_FIELDS = {'schema','kind','baseline','qualification','target_identity','helper_identity',
    'framework_epoch_sha256','support_manifest','target_profile','helper_profile','limits',
    'source_preparation','task_source_manifest','original_gates','flows','case_root',
    'whole_app_business_accepted','automatic_retry'}
ACTIVE_FIELDS = BASE_FIELDS | {'base_plan','lease'}


def named(c, packet, name):
    rows = [r for r in packet['files'] if Path(r['path']).name == name]
    c.need(len(rows) == 1, 'ONE_PINNED_SETTINGS_SOURCE:' + name)
    return c.module(rows[0], 'settings_' + Path(name).stem)


def preparation(c, ref):
    value = c.parse(c.read_ref(ref))
    c.need(type(value) is dict and value.get('schema') == 'pocket4-settings-pages-preparation-v1'
           and value.get('whole_app_business_accepted') is False
           and value.get('Android_execution_authorized_by_publication') is False
           and value.get('native_profile') == 'settings-pages'
           and value.get('route') == 'settings_supported_pages'
           and type(value.get('files')) is list and 8 <= len(value['files']) <= 32
           and len({Path(r['path']).name for r in value['files']}) == len(value['files'])
           and type(value.get('origins')) is list and 1 <= len(value['origins']) <= 32,
           'EXACT_NEW_SETTINGS_SOURCE_PREPARATION_REQUIRED')
    for row in value['files'] + value['origins']:
        c.read_ref(row)
    return value


def inputs(c, request, packet):
    c.need(set(request) == {'baseline','qualification','target_identity','helper_identity'},
           'FRESH_MAIN_AND_TWO_ACTUAL_SETTINGS_IDENTITIES_REQUIRED')
    _, support = c.support(c.SUPPORT_REF)
    baseline = support['business_baseline.py'].BusinessBaseline(request['baseline'], request['qualification'])
    c.need(c.current_qualification_support(request['baseline'], request['qualification']) == c.SUPPORT_REF,
           'SETTINGS_IDENTITY_AND_BASELINE_SOURCE_COHORT_CHANGED')
    profile = named(c, packet, 'settings_profiles.py')
    for key, expected in (('target_identity', profile.TARGET), ('helper_identity', profile.HELPER)):
        identity = c.parse(c.read_ref(request[key]))
        c.validate_identity(identity, expected, request['baseline'], request['qualification'])
    c.need(baseline.value['data_continuity']['package_uids'].get(profile.PACKAGE) == 1000,
           'ORIGINAL_SETTINGS_SYSTEM_UID_MUST_BE_PRESERVED')
    gates = c.parse(c.read_ref(c.GATES))
    c.need(gates['packages'][profile.PACKAGE]['profile'] == 'settings'
           and set(gates['profiles']['settings']['checks']) == set(profile.ORIGINAL_GATES),
           'ORIGINAL_COMPLETE_SETTINGS_CONTRACT_CHANGED')
    baseline.guard()
    return baseline, profile


def source_packet(c, value, prepared):
    root = Path(value['case_root'])
    c.need(c.case_root_matches(root,'settings-supported-pages','business-settings-pages-plan-[0-9a-f]{32}')
           and Path(value['task_source_manifest']['path']) == root / 'task-source.json',
           'SETTINGS_EXACT_CREATE_ONLY_TASK_SOURCE_ROOT')
    task = c.parse(c.read_ref(value['task_source_manifest']))
    expected = [{'path':str(root/'source'/Path(row['path']).name),'bytes':row['bytes'],'sha256':row['sha256']}
                for row in prepared['files']]
    by_name = {Path(row['path']).name:row for row in expected}
    origins = []
    for row in [value['source_preparation']] + prepared['files'] + prepared['origins']:
        if row not in origins: origins.append(row)
    c.need(task == {'schema':'pocket4-final-business-task-source-v1','files':expected,'origins':origins,
                   'guard_source':by_name['settings_guard.py'],'recorder_source':by_name['app_flow.py'],
                   'target_package':'com.android.settings','target_uid':1000,
                   'old_runtime_authority_transferred':False},
           'SETTINGS_TASK_COPY_MUST_MATCH_FROZEN_PREPARATION')
    for row in task['files'] + task['origins']: c.read_ref(row)
    return task


def validate(c, value, baseline, scope=None):
    active = value.get('schema') == 'pocket4-settings-pages-active-plan-v2'
    c.need(set(value) == (ACTIVE_FIELDS if active else BASE_FIELDS)
           and value['schema'] in ('pocket4-settings-pages-plan-v2','pocket4-settings-pages-active-plan-v2')
           and value['kind'] == 'settings_supported_pages'
           and value['whole_app_business_accepted'] is False and value['automatic_retry'] is False,
           'EXACT_BOUNDED_SETTINGS_PLAN_REQUIRED')
    prepared = preparation(c, value['source_preparation'])
    request = {k:value[k] for k in ('baseline','qualification','target_identity','helper_identity')}
    checked, profile = inputs(c, request, prepared)
    c.need(checked.baseline_ref == baseline.baseline_ref == value['baseline']
           and checked.qualification_ref == baseline.qualification_ref == value['qualification']
           and value['support_manifest'] == c.SUPPORT_REF
           and value['framework_epoch_sha256'] == baseline.value['framework_epoch']['sha256']
           and value['target_profile'] == profile.TARGET and value['helper_profile'] == profile.HELPER
           and value['limits'] == profile.LIMITS and value['original_gates'] == c.GATES,
           'SETTINGS_MAIN_PROFILES_AND_BUDGETS_CHANGED')
    task = source_packet(c, value, prepared)
    flows = value['flows']
    c.need(type(flows) is list and len(flows) == 2 and len({f['nonce'] for f in flows}) == 2,
           'TWO_DISTINCT_SETTINGS_LAUNCH_SCOPES_REQUIRED')
    for flow in flows:
        c.need(set(flow) == {'nonce','flow_root'} and re.fullmatch('[0-9a-f]{32}', flow['nonce'])
               and flow['flow_root'] == str(c.flow_root('settings-supported-pages',flow['nonce'],'settings-pages')),
               'EXACT_NONCE_OWNED_SETTINGS_FLOW_REQUIRED')
    if active:
        original = c.parse(c.read_ref(value['base_plan']))
        c.need(original == {k:v for k,v in value.items() if k not in ('base_plan','lease','schema')} |
               {'schema':'pocket4-settings-pages-plan-v2'}, 'SETTINGS_ACTIVE_PLAN_CHANGED_BASE_INPUTS')
        c.read_ref(value['lease'])
    if scope is not None:
        c.need(active and any(scope['nonce'] == f['nonce'] and scope['flow_root'] == f['flow_root'] for f in flows)
               and scope['business_baseline'] == value['baseline']
               and scope['business_qualification'] == value['qualification']
               and scope['support_manifest'] == value['support_manifest']
               and scope['package'] == profile.PACKAGE and scope['uid'] == 1000 and scope['user'] == 0
               and scope['component'] == profile.TARGET['component']
               and scope['task_source_manifest'] == value['task_source_manifest']
               and scope['actual_resolution_receipt'] == value['target_identity']
               and scope['installed_helper_receipts'] == [value['helper_identity']]
               and scope['guard_source'] == task['guard_source'] and scope['recorder_source'] == task['recorder_source'],
               'SETTINGS_FLOW_NOT_THE_NEW_PLAN_AND_ACTUAL_IDENTITIES')
    return prepared, profile


def create(c, request, output, preparation_ref):
    c.need(os.getuid() == os.geteuid() == 0, 'ROOT_SETTINGS_FACTORY_REQUIRED')
    prepared = preparation(c, preparation_ref); baseline, profile = inputs(c, request, prepared)
    root = Path(output)
    c.need(c.case_root_matches(root,'settings-supported-pages','business-settings-pages-plan-[0-9a-f]{32}'),
           'NEW_SETTINGS_CASE_DIRECTORY_REQUIRED')
    c.private_dir(root, create=True); c.private_dir(root/'source', create=True)
    files = [c.write_new(root/'source'/Path(row['path']).name, c.read_ref(row), 0o400)
             for row in prepared['files']]
    by_name = {Path(row['path']).name:row for row in files}; origins=[]
    for row in [preparation_ref] + prepared['files'] + prepared['origins']:
        if row not in origins: origins.append(row)
    c.need(len(origins) <= 128, 'SETTINGS_SOURCE_ORIGIN_BOUND')
    task = {'schema':'pocket4-final-business-task-source-v1','files':files,'origins':origins,
            'guard_source':by_name['settings_guard.py'],'recorder_source':by_name['app_flow.py'],
            'target_package':profile.PACKAGE,'target_uid':1000,'old_runtime_authority_transferred':False}
    task_ref = c.write_new(root/'task-source.json', task, 0o400); flows=[]
    for _ in range(2):
        nonce=secrets.token_hex(16)
        c.need(nonce not in {x['nonce'] for x in flows}, 'DISTINCT_NEW_SETTINGS_NONCES')
        flows.append({'nonce':nonce,'flow_root':str(c.flow_root('settings-supported-pages',nonce,'settings-pages'))})
    value={'schema':'pocket4-settings-pages-plan-v2','kind':'settings_supported_pages',**request,
           'framework_epoch_sha256':baseline.value['framework_epoch']['sha256'],
           'support_manifest':c.SUPPORT_REF,'target_profile':profile.TARGET,'helper_profile':profile.HELPER,
           'limits':profile.LIMITS,'source_preparation':preparation_ref,'task_source_manifest':task_ref,
           'original_gates':c.GATES,'flows':flows,'case_root':str(root),
           'whole_app_business_accepted':False,'automatic_retry':False}
    validate(c, value, baseline)
    return c.write_new(root/'plan.json', value, 0o400)


def activate(c, base_ref, lease_ref):
    base = c.parse(c.read_ref(base_ref)); c.read_ref(lease_ref)
    _, modules = c.support(base['support_manifest'])
    baseline = modules['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
    validate(c, base, baseline)
    active = {**base,'schema':'pocket4-settings-pages-active-plan-v2','base_plan':base_ref,'lease':lease_ref}
    active_ref=c.write_new(Path(base['case_root'])/'active-plan.json', active, 0o400)
    task=c.parse(c.read_ref(base['task_source_manifest'])); refs=[]
    for flow in base['flows']:
        root=c.private_dir(flow['flow_root'], create=True); c.private_dir(root/'steps', create=True)
        value={'schema':'pocket4-final-business-recorder-scope-v1','business_baseline':base['baseline'],
               'business_qualification':base['qualification'],'support_manifest':base['support_manifest'],
               'framework_epoch_sha256':base['framework_epoch_sha256'],'package':'com.android.settings',
               'uid':1000,'user':0,'component':base['target_profile']['component'],**flow,
               'task_source_manifest':base['task_source_manifest'],'phase_plan':active_ref,
               'actual_resolution_receipt':base['target_identity'],
               'installed_helper_receipts':[base['helper_identity']],
               'recorder_source':task['recorder_source'],'guard_source':task['guard_source'],'automatic_retry':False}
        refs.append(c.write_new(root/'scope.json', value, 0o400))
    return active_ref, refs
