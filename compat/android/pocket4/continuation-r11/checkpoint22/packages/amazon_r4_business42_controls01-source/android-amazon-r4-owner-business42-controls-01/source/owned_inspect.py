#!/usr/bin/env python3
"""One actual-bound Amazon launch, public search-entry click and owned cleanup.

One fixed public search-entry click. No text entry, old helper, screenshot, audio, package change, permission
grant or settings write. Raw helper tree stays in the new root-private flow.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

HERE=Path(__file__).resolve().parent
ROOT=Path("/home/alex/work/pocket4-amazon-r4-current-search-entry-01")
SOURCE=ROOT/'source'
NONCE='973c8962a6356166e145c3a05368d814'
FLOW=Path('/home/alex/work/pocket4-amazon-owned-qa-r4-flow-'+NONCE)
PACKAGE='com.amazon.mShop.android.shopping'
UID=10129
SELF="org.droidloom.qa.amazon.r4"
HELPER_UID=10159

CURRENT_HOST_MANIFEST="002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff"
CURRENT_BASELINE_SCHEMA="pocket4-main-current-baseline-v2"
CURRENT_EPOCH="7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c"
CURRENT_BASELINE_SHA="633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364"
CURRENT_QUALIFICATION_SHA="ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e"
COMPONENT=PACKAGE+'/com.amazon.mShop.home.HomeActivity'
PLAN={"entry":{"nonces":{"action":"24b521ec19758b4c18e20332cfe27157","after":"caf81af1b4ed9b021c556ce85c4ab561","before":"1541d08c796b408c34a4ec9a26709c47","inspect":"858340d3f74b1dbe2fb8762a7d015222"},"operation":"click","schema":1,"selector":{"class":"android.widget.ImageButton","content_desc":"Search","resource_id":"com.amazon.mShop.android.shopping:id/chrome_search_box"}},"operation":"search_entry","post":{"nonces":{"after":"7fa98495657031ad07e693914e7957ed","before":"13a17fdb8cb74e00634503f4ef6dc2a7","inspect":"c8767cc3811bf872128005644d0947c5"},"operation":"inspect","schema":1},"schema":1,"stability":[{"nonces":{"after":"686420cc9a63f1df328d951546325d3a","before":"4304f1a7ff94add60f198e9e6e416b5a","inspect":"d3a404935de5cd6d8aa12581a31a1721"},"operation":"inspect","schema":1},{"nonces":{"after":"65eae027cbb3c1d90b597fcaadf1d950","before":"4c69b33c2f395fcea9bb2d9d46b12e0a","inspect":"6e2fd93b0e9f33397d28ccec1aece6b5"},"operation":"inspect","schema":1},{"nonces":{"after":"e312af369605c30008e64a63cfd545da","before":"f41450b96ee4747d79b931bfe03165b2","inspect":"79df981326cbb809a165243e1dbcf3b4"},"operation":"inspect","schema":1},{"nonces":{"after":"eb218365091b7928fccd22e5abdc90ac","before":"9e2e24ce7e1308eb24e7f603896a3630","inspect":"8ec3da7ef0c773e5c6334218c11bc575"},"operation":"inspect","schema":1},{"nonces":{"after":"aa25239408c599268cbf2ab9e41d3590","before":"ffd751558d7ce6d1ac2f7dd582745a68","inspect":"88d662a142db608bbfeb4529d0093d51"},"operation":"inspect","schema":1},{"nonces":{"after":"73ff9a0eee0c06979739dd8ee60a008a","before":"3795b440eac2fe22ab72fee6899d4763","inspect":"f9bc4b5a9c662cdb5dd43697085f25a6"},"operation":"inspect","schema":1},{"nonces":{"after":"2f90fb8e13b8968d6489b0fa7ee4a28b","before":"30f6eabe4faf719b137619d5ed9fb54f","inspect":"408ea8c45dae4b4f234c05e781dae711"},"operation":"inspect","schema":1},{"nonces":{"after":"40ec5881ff1e8e1435fab1d4864bf563","before":"abcd4e1dd9c5bc651ab44d7ffb0847e8","inspect":"66b25b379464bb58197e4722b417b7f6"},"operation":"inspect","schema":1}]}
INSTALL_ROOT=Path("/home/alex/work/pocket4-owned-amazon-qa-r4-install-state-02")
INSTALL_SOURCE=INSTALL_ROOT/'source'
INSTALL_SOURCE_SHA="ed611217d1721dc5f0e30a4a6c5163c9f35c6f50404e0118e2e2deff6679b7bc"
UTIL_SHA="dea588899bd93d9a658f875aedd071456a1ce2d16180f60f697a6528f13420e1"
UTIL_BYTES=40152
CONTEXT_SHA="d081ba9b8d6da9cdaa4a071ae40b5c74efe2428921bae947a5f93e8afa8add37"
TRANSPORT_SHA="d9a682696cac2e28987b04f3e59f0fa783028fdc069c145816cd87c40eb6ca63"
STATE_NONCE="7e2b1d49365866364ecaa9bf59942c87"
STATE_WIRE="127c3094679c80a4eb1b13a5023c0959c47776fc56ef39dd9d14fff88f57c9ac"
INSTALLED={"apk_sha256":"0fcd5b21fb1dfeabd5fa5dede9805217a6f915a75f52cdb1b74216dbaa66a71d","base_apk":"/data/app/~~ltijd-ew7pYbq3vrboU8EQ==/org.droidloom.qa.amazon.r4-f4ISashDuJbVeEczF4BF6Q==/base.apk","bytes":24720,"held_file":{"bytes":24720,"device":1811,"gid":1000,"inode":656335,"mode":33188,"mtime_ns":1793982243720689487,"nlink":1,"uid":1000},"package":"org.droidloom.qa.amazon.r4","signer_bound_by_exact_signed_apk_bytes":"40022ce8b76fe6262a1d3248172351c4222f68cdfa8a30eb71236ab3db2811d5","uid":10159}
PRIOR={"coordinator":("result.json",4477,"2847a9bbe0ba6ff88a1c447e07289594ab109b0acb9e21eb16526f15578dbe7e"),"stage":("stage-result.json",10458,"bf272bce96a63693a10d598e6d88dfd743b62633cddcf61a376471476a7b52ed"),"worker":("worker/result.json",15579,"d4d421e64403afcbcd7208d5d51768e8c7a87da978696291e0c7619a9f464567")}
RESOLVER_ROOT=Path('/home/alex/work/pocket4-amazon-launcher-resolve-readonly-01')
RESOLVER_SOURCE=RESOLVER_ROOT/'source/resolve_amazon.py'
RESOLVER_SHA='b963fde5ba1638702623ee707ec21b43f0a86f87f54550f1e0d2df474cb7b058'
RESOLVER_BYTES=15453
RESOLVER_NONCE='def3447572e718bc263b37bd39393b90'
RESOLVER_RECORDS={
    'worker':('result.json',12204,'ebeaecf791eba4906502cd3167c08e735d826ffd565f7fdd45d66775c016c534'),
    'stage':('stage-result.json',1599,'9dfa012752b241b1c881514089684d13b56bcaa0250fb7fcb3d2c72633fdb29d')}
RUNTIME_FILES={'owned_inspect.py','amazon_task_context.py','search_navigation.py','INPUTS.json'}
PHASE_SECONDS={'launch':175,'inspect':175,'cleanup':115}


def need(value,message):
    if not value:raise RuntimeError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def read(path,maximum=1048576,expected=None,size=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        first=os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and 0<=first.st_size<=maximum,
             'EXACT_BOUNDED_REGULAR_INPUT:'+str(path))
        value=bytearray()
        while len(value)<=maximum:
            part=os.read(fd,min(65536,maximum+1-len(value)))
            if not part:break
            value.extend(part)
        last=os.fstat(fd)
        fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        need(len(value)==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),
             'FIXED_INPUT_CHANGED:'+str(path))
        value=bytes(value)
        need(expected is None or sha(value)==expected,'FIXED_INPUT_SHA:'+str(path))
        need(size is None or len(value)==size,'FIXED_INPUT_BYTES:'+str(path))
        return value
    finally:os.close(fd)


def load(path,digest,name,size=None):
    raw=read(path,expected=digest,size=size);m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(raw,str(path),'exec'),m.__dict__)
    return m


def verify_source(expected):
    need(isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected),'EXTERNAL_SOURCE_PIN_REQUIRED')
    manifest=json.loads(read(HERE/'SOURCE_PINS.json',131072,expected))
    need(set(manifest['files'])==RUNTIME_FILES,'EXACT_AMAZON_TASK_SOURCE_SET')
    for name,row in manifest['files'].items():read(HERE/name,65536,row['sha256'],row['bytes'])
    return manifest


def actual_resolver(rows,installed):
    worker,stage=rows['worker'],rows['stage']
    for value in (worker,stage):
        need(value['ok'] is True and value['error'] is None and value['secondary_errors']==[] and
             value['nonce']==RESOLVER_NONCE and value['source_sha256']==RESOLVER_SHA and
             value['package']==PACKAGE and value['App_launches']==0 and value['instrumentation_calls']==0,
             'EXACT_ACTUAL_READ_ONLY_RESOLVER_REQUIRED')
    need(stage['worker_result']=={'path':str(RESOLVER_ROOT/'result.json'),
         'bytes':RESOLVER_RECORDS['worker'][1],'sha256':RESOLVER_RECORDS['worker'][2]},
         'ACTUAL_RESOLVER_PARENT_CHAIN_REQUIRED')
    need(worker['launcher']['component']==COMPONENT and worker['launcher']['package']==PACKAGE and
         worker['launcher']['user']==0 and worker['launcher']['fallback_used'] is False and
         worker['launcher']['launch_performed'] is False and worker['exact_command_count']==9 and
         worker['action_attempted'] is False and worker['outcome_unknown'] is False,
         'ACTUAL_RESOLVER_EXACT_COMPONENT_REQUIRED')
    need(worker['helper_before']==worker['helper_after']==installed and
         worker['target_before']==worker['target_after'] and
         worker['Main_before_lock']==worker['Main_before']==worker['Main_after']==stage['Main_before']==stage['Main_after'],
         'ACTUAL_RESOLVER_SCOPE_STABILITY_REQUIRED')
    need(worker['target_FD_cleanup']['held_APK_FDs_closed']==3 and
         all(worker[k] is True for k in ('final_Main_guard_passed','held_binding_released','action_lock_released','source_and_build_unchanged'))
         and stage['source_unchanged'] is True,'ACTUAL_RESOLVER_RETIRED_REQUIRED')
    return {'component':COMPONENT,'actual_resolve_stdout_sha256':worker['launcher']['resolve_stdout_sha256'],
        'prior_receipts':{k:{'path':str(RESOLVER_ROOT/v[0]),'bytes':v[1],'sha256':v[2]}
                          for k,v in RESOLVER_RECORDS.items()},
        'historical_resolution_not_launch_authority':True,'new_prelaunch_resolution_required':True}


def actual_install(rows):
    c,s,w=(rows[k] for k in ('coordinator','stage','worker'))
    for value in (c,s,w):
        need(value.get('ok') is True and value.get('error') is None and
             value.get('secondary_errors')==[],'ACTUAL_PRIOR_INSTALL_FAILED')
        need(value.get('source_manifest_sha256')==INSTALL_SOURCE_SHA,'ACTUAL_INSTALL_SOURCE_CHANGED')
    need(c['worker_result']=={'path':str(INSTALL_ROOT/PRIOR['worker'][0]),
         'bytes':PRIOR['worker'][1],'sha256':PRIOR['worker'][2]},'ACTUAL_INSTALL_WORKER_CHAIN')
    need(s['coordinator_result']=={'path':str(INSTALL_ROOT/PRIOR['coordinator'][0]),
         'bytes':PRIOR['coordinator'][1],'sha256':PRIOR['coordinator'][2]},'ACTUAL_INSTALL_STAGE_CHAIN')
    need(w['installed_before_state']==w['installed_after_state']==INSTALLED and
         w['owned_package_uid']==c['owned_package_uid']==HELPER_UID,
         'ACTUAL_INSTALLED_HELPER_IDENTITY_CHANGED')
    need(w['runtime_amazon_context_sha256']==CONTEXT_SHA and
         w['runtime_amazon_transport_sha256']==TRANSPORT_SHA and
         w['exact_command_count']==13,'ACTUAL_INSTALL_RUNTIME_CHAIN')
    state=w['state'];helper=state['helper']
    need(state['wire_sha256']==STATE_WIRE and state['actual_command_returncode']==0 and
         state['actual_instrumentation_finish_code']==-1 and
         state['held_transport_returned_after_post_guard'] is True and
         helper['nonce']==STATE_NONCE and helper['self_uid']==HELPER_UID and
         helper['protocol']=='pocket4-owned-amazon-qa-v4' and helper['op']=='state' and
         helper['ok'] is True and helper['ui_automation_connected'] is False,
         'ACTUAL_NO_AUTOMATION_STATE_REQUIRED')
    need(w['target_before']==w['target_after'] and
         w['Main_before_lock']==w['Main_before']==w['Main_after']==c['Main_before']==c['Main_after']==s['Main_before']==s['Main_after'],
         'ACTUAL_INSTALL_MAIN_OR_TARGET_CHAIN')
    need(w['Main_before']=={"Main_epoch_sha256":"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c","authenticated_owner_chain_matches":True,"config_sha256":"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc","current_baseline_qualification_sha256":"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e","current_baseline_sha256":"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364","current_executable_and_root_backing_match":True,"current_user_namespaces_match":True,"framework_exit_cause_resolved":False,"historical_activation_sha256":"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615","historical_verified_sha256":"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387","old_helpers_and_tasks_reauthorized":False,"previous_current_baseline_sha256":"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266","production_ready":False,"resource_limits_match":True,"schema":"pocket4-current-main-guard-v2","seven_processes_match":True,"three_host_processes_match":True},
         'ACTUAL_INSTALL_TYPED_CURRENT_BASELINE_REQUIRED')
    need(w['staging_cleanup']['staged_apk_removed'] is True and
         w['staging_cleanup']['staged_directory_removed'] is True and
         w['target_FD_cleanup']['held_APK_FDs_closed']==3 and
         w['held_binding_released'] is True and w['action_lock_released'] is True and
         w['final_Main_guard_passed'] is True and w['outcome_unknown'] is False,
         'ACTUAL_INSTALL_RETIREMENT_REQUIRED')
    return {'prior_install_source_sha256':INSTALL_SOURCE_SHA,
        'prior_receipts':{k:{'bytes':v[1],'sha256':v[2]} for k,v in PRIOR.items()},
        'installed':INSTALLED,'actual_state_wire_sha256':STATE_WIRE,
        'no_prior_install_or_state_replayed':True}


def qualified(expected):
    need(type(HELPER_UID) is int and 10000<=HELPER_UID<100000 and HELPER_UID not in (10129,10175,10154) and isinstance(INSTALLED,dict) and
         isinstance(STATE_WIRE,str) and re.fullmatch('[0-9a-f]{64}',STATE_WIRE) and
         isinstance(PRIOR,dict) and set(PRIOR)=={'coordinator','stage','worker'} and
         isinstance(PRIOR['worker'],tuple),'ACTUAL_AMAZON_INSTALL_BINDING_NOT_READY')
    manifest=verify_source(expected)
    historical_resolver=load(RESOLVER_SOURCE,RESOLVER_SHA,'amazon_historical_launcher_reference',RESOLVER_BYTES)
    util=load(INSTALL_SOURCE/'install_state.py',UTIL_SHA,'amazon_current_install_primitives',UTIL_BYTES)
    install_manifest=util.verify_source(INSTALL_SOURCE_SHA)
    prior={k:json.loads(read(INSTALL_ROOT/v[0],expected=v[2],size=v[1])) for k,v in PRIOR.items()}
    install_observation=actual_install(prior)
    records={k:json.loads(read(RESOLVER_ROOT/v[0],expected=v[2],size=v[1])) for k,v in RESOLVER_RECORDS.items()}
    actual_component=actual_resolver(records,historical_resolver.INSTALLED)
    adapter,qa,proof,apk=util.qualified_inputs();del apk
    navigation=load(HERE/'search_navigation.py',manifest['files']['search_navigation.py']['sha256'],'amazon_search_navigation')
    all_plans=navigation.plans(PLAN)
    for plan in all_plans:adapter.validate_plan(plan,qa)
    need(qa.PACKAGE==PACKAGE and qa.UID==UID and qa.SELF==SELF and adapter.SELF==SELF,
         'DEDICATED_AMAZON_HELPER_SOURCE_REQUIRED')
    values=[NONCE,*[n for plan in all_plans for n in plan['nonces'].values()]]
    need(len(values)==len(set(values))==32 and all(re.fullmatch('[0-9a-f]{32}',v) for v in values),
         'EXACT_NEW_FLOW_AND_THIRTY_ONE_HELPER_NONCES')
    inputs=json.loads(read(HERE/'INPUTS.json',65536))
    need(inputs['nonce']==NONCE and inputs['component']==COMPONENT and inputs['installed_helper']==INSTALLED
         and inputs['resolver_records']=={k:{'relative_path':v[0],'bytes':v[1],'sha256':v[2]} for k,v in RESOLVER_RECORDS.items()},
         'EXACT_RUNTIME_INPUT_RECORD_REQUIRED')
    need(inputs['search_entry_plan']==PLAN and inputs['observed_selector_reference']['raw_retired_nodes_authorize_actions'] is False,
         'EXACT_PUBLIC_ENTRY_PLAN_AND_RETIRED_SCOPE_BOUNDARY')
    # Historical resolver proves only its own old receipt; current execution uses the new install closure.
    resolver=types.SimpleNamespace(INSTALL_SOURCE=INSTALL_SOURCE,INSTALL_SOURCE_SHA=INSTALL_SOURCE_SHA,
        CONTEXT_SHA=CONTEXT_SHA,TRANSPORT_SHA=TRANSPORT_SHA,RESOLVE=historical_resolver.RESOLVE,
        component=historical_resolver.component,INSTALLED=INSTALLED)
    return types.SimpleNamespace(manifest=manifest,navigation=navigation,resolver=resolver,util=util,ref=util.references(),
        install_manifest=install_manifest,install=install_observation,resolution=actual_component,
        adapter=adapter,qa=qa,proof=proof,installed=INSTALLED)


def scope_record(q,expected):
    baseline=q.ref.current_baseline()
    need(baseline.get('schema')==CURRENT_BASELINE_SCHEMA and
         baseline.get('kind')=='current-cell-generation' and
         'main_deployed' not in baseline and baseline.get('deployment_performed') is False and
         baseline.get('framework_exit_cause_resolved') is False and
         baseline.get('whole_app_production_ready') is False and
         baseline['framework_epoch']['sha256']==CURRENT_EPOCH==q.ref.EPOCH and
         q.ref.BASELINE_SHA==CURRENT_BASELINE_SHA and
         q.ref.QUALIFICATION_SHA==CURRENT_QUALIFICATION_SHA and
         type(baseline['packages'].get(PACKAGE)) is int and baseline['packages'][PACKAGE]==UID,
         'CURRENT_TYPED_OWN_TARGET_SCOPE_REQUIRED')
    return {'schema':'pocket4-current-recorder-scope-v2','current_baseline_schema':baseline['schema'],
        'package':PACKAGE,'component':COMPONENT,'uid':baseline['packages'][PACKAGE],'user':0,'nonce':NONCE,
        'epoch_sha256':baseline['framework_epoch']['sha256'],
        'current_baseline_sha256':q.ref.BASELINE_SHA,
        'current_baseline_qualification_sha256':q.ref.QUALIFICATION_SHA,
        'amazon_task_source_manifest_sha256':expected,'automatic_retry':False,
        'original_recorder_manifest_sha256':q.adapter.RECORDER_MANIFEST_SHA,
        'actual_resolution_result_sha256':RESOLVER_RECORDS['worker'][2]}


def owned_scope(q):
    raw=read(FLOW/'launch-scope.json',65536);value=json.loads(raw)
    need(set(value)=={'task','package','epoch_sha256','prelaunch_absent','cleanup_allowed',
        'launch_step','prelaunch_task_ids','native_receipt_sha256'} and value['package']==PACKAGE and
        value['epoch_sha256']==q.ref.EPOCH and value['prelaunch_absent'] is True and
        value['cleanup_allowed'] is True and value['launch_step']=='launch-01' and
        type(value['task']) is int and value['task']>0 and isinstance(value['prelaunch_task_ids'],list) and
        all(type(x) is int and x>=0 for x in value['prelaunch_task_ids']) and
        value['task'] not in value['prelaunch_task_ids'] and
        re.fullmatch('[0-9a-f]{64}',value['native_receipt_sha256']), 'EXACT_NEW_NATIVE_LAUNCH_SCOPE_REQUIRED')
    return value,{'path':str(FLOW/'launch-scope.json'),'bytes':len(raw),'sha256':sha(raw)}


def assessment_summary(q,step,sequence,plan):
    """No raw UI text, node list, screenshots or recommendations in the result."""
    result={}
    for phase,nonce in plan['nonces'].items():
        path=step/(nonce+'.assessment.json');raw=read(path);value=json.loads(raw);helper=value['helper']
        need(helper['nonce']==nonce and helper['self_uid']==HELPER_UID and
             helper['op']==('inspect' if phase=='inspect' else plan['operation'] if phase=='action' else 'state') and
             value['actual_command_returncode']==0 and value['actual_instrumentation_finish_code']==-1 and
             value['held_transport_returned_after_post_guard'] is True and helper['ok'] is True and
             helper['error'] is None and helper['secondary_errors']==[] and
             value['wire_sha256']==sha(q.qa.canonical(helper)), 'ACTUAL_CURRENT_ASSESSMENT_REQUIRED')
        row={'nonce':nonce,'operation':helper['op'],'assessment_bytes':len(raw),'assessment_sha256':sha(raw),
            'wire_sha256':value['wire_sha256'],'recorder_command_result_sha256':value['recorder_command_result_sha256'],
            'actual_command_returncode':0,'actual_instrumentation_finish_code':-1}
        if phase=='inspect':
            inspection=q.qa.inspect_record(helper['inspection'])
            need(value['wire_sha256']==sequence['inspection_wire_sha256'],'INSPECTION_WIRE_CHANGED')
            row.update(tree_sha256=inspection['tree_sha256'],window_sha256=inspection['window_sha256'],
                node_count=len(inspection['nodes']),window={k:inspection['window'][k] for k in ('package','display','type','focused')},
                window_observation=q.qa.window_observation(helper['window_observation']),
                connection_scoped_window_id=inspection['connection_scoped_window_id'],
                tree_observations=q.qa.tree_observations(helper['tree_observations'],'inspect',True),
                complete=True,raw_tree_private_only=True)
        elif phase=='action':
            need(helper['op']=='click' and helper['node_action_returned'] is True and
                 helper['node_action']=='ACTION_CLICK' and helper['inspection_nonce']==plan['nonces']['inspect'],
                 'ONE_ACTUAL_SOURCE_BOUND_SEARCH_ENTRY_ACTION')
            row.update(action_acknowledged=True,node_action='ACTION_CLICK',
                inspection_nonce=helper['inspection_nonce'],action_window=helper['action_window'])
        result[phase]=row
    return result


def retain_navigation_failure_observations(result):
    """Copy only the navigation's retained first-failure and independent post records."""
    navigation=result.get('search_entry')
    if type(navigation) is not dict:
        return
    if 'failed_sequence_observation' in navigation:
        result['failed_sequence_observation']=navigation['failed_sequence_observation']
    else:
        first=navigation.get('error')
        if type(first) is dict and first.get('phase')=='independent_post_entry_inspection' and \
                'failed_post_sequence_observation' in navigation:
            result['failed_sequence_observation']=navigation['failed_post_sequence_observation']
    if 'post_sequence' in navigation:
        result['independent_post_sequence_observation']=navigation['post_sequence']
    if 'failed_post_sequence_observation' in navigation:
        result['independent_failed_post_sequence_observation']=navigation['failed_post_sequence_observation']


def worker(expected,phase):
    need(os.getuid()==os.geteuid()==0 and HERE==SOURCE and phase in PHASE_SECONDS,'EXACT_ROOT_PHASE_REQUIRED')
    q=qualified(expected);u,ref=q.util,q.ref
    step=FLOW/'steps'/(phase+'-01')
    result={'schema':1,'ok':False,'error':None,'secondary_errors':[],'phase':phase,'nonce':NONCE,
        'source_manifest_sha256':expected,'package':PACKAGE,'uid':UID,'helper_package':SELF,'helper_uid':HELPER_UID,
        'actual_install':q.install,'actual_resolution':q.resolution,'build':q.proof,
        'automatic_retry':False,'Bili_Flow_instantiated':False,'old_v2_helper_called':False,
        'click_actions':0,'text_actions':0,'screenshots':0,'audio_actions':0,'permission_grants':0,'settings_writes':0,
        'raw_UI_tree_private_only':True,'whole_app_production_ready':False,'business_success_verified':False,
        'host_foreground_display_independently_verified':False,'required_helper_display':0}
    flow=artifacts=session=guard=flow_lock=action_lock=None
    began=time.monotonic();current='phase_admission'
    try:
        need(FLOW.is_dir() and not os.path.lexists(step),'FRESH_PHASE_DIRECTORY_REQUIRED')
        result['flow_lock_admission']={}
        flow_lock=u.acquire_action_lock(FLOW/'flow.lock',result['flow_lock_admission'])
        step.mkdir(mode=0o700)
        ref.write_new(step/'intent.json',{'phase':phase,'nonce':NONCE,'source_manifest_sha256':expected,
            'automatic_retry':False,'mutation':phase in ('launch','inspect','cleanup'),'request':PLAN if phase=='inspect' else None})
        context=u.module(q.resolver.INSTALL_SOURCE/'amazon_context.py',q.resolver.CONTEXT_SHA,'amazon_exact_artifact_context')
        transport=u.module(q.resolver.INSTALL_SOURCE/'amazon_transport.py',q.resolver.TRANSPORT_SHA,'amazon_exact_transport')
        task_module=load(HERE/'amazon_task_context.py',q.manifest['files']['amazon_task_context.py']['sha256'],'amazon_task_context')
        shared=u.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,'amazon_task_admission_contract')
        contract=shared.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
        recorder=contract.load('recorder.py','amazon_task_admission_recorder')
        activation=ref.current_baseline()
        epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'amazon_phase_epoch')
        guard=lambda:ref.main_guard(activation,epoch)
        result['Main_before_lock']=guard()
        if phase!='cleanup':
            current='action_lock';result['action_lock_admission']={}
            action_lock=u.acquire_action_lock(recorder.ACTION_LOCK,result['action_lock_admission']);guard()
        else:
            # Original Flow.cleanup acquires/releases this same global lock.
            # An outer acquisition would self-conflict; metadata reads here are
            # read-only and the actual retirement stays inside its original lock.
            result['action_lock_owner']='original Flow.cleanup for exact retirement'
        current='held_Main_context'
        def verify_runtime(value):
            verify_source(value);u.verify_source(q.resolver.INSTALL_SOURCE_SHA)
            read(RESOLVER_SOURCE,32768,RESOLVER_SHA,RESOLVER_BYTES)
        flow,recorder,guard=task_module.open_task_context(ref,u,context,expected,verify_runtime,FLOW,step,
            transport,result,began+PHASE_SECONDS[phase],phase,q.qa,PLAN,q.resolver.RESOLVE,scope_record(q,expected),
            install_source_manifest=q.resolver.INSTALL_SOURCE_SHA)
        reference=json.loads(u.read(q.resolver.INSTALL_SOURCE/'target-artifact-reference.json',expected=
            q.install_manifest['files']['target-artifact-reference.json']['sha256']))
        reader=u.module(q.resolver.INSTALL_SOURCE/'references/read_amazon.py',u.READER_SHA,'amazon_artifact_parser')
        artifacts=context.ArtifactSet(flow,reference,reader)
        current='target_before';result['target_before']=artifacts.before()
        session=q.adapter.Session(flow,recorder,q.qa,q.proof,HELPER_UID)
        current='helper_before';result['helper_before']=session.installed()
        need(result['helper_before']==q.installed,'ACTUAL_INSTALLED_HELPER_CHANGED')
        if phase=='launch':
            current='current_component'
            raw,result['resolve_command']=u.command(flow,q.resolver.RESOLVE,15)
            result['current_launcher']=q.resolver.component(raw)
            need(result['current_launcher']['component']==COMPONENT,'CURRENT_LAUNCHER_COMPONENT_CHANGED')
            current='one_native_launch';result['launch']=flow.launch_locked()
            need(result['launch']['native_launch_acknowledged'] is True and result['launch']['cleanup_allowed'] is True,
                 'EXACT_NEW_NATIVE_TASK_REQUIRED')
            result['owned_task']=flow.selected_task()
        elif phase=='inspect':
            current='public_search_entry_and_post_inspection'
            q.navigation.run(types.SimpleNamespace(read=read,sha=sha,assessment_summary=assessment_summary),
                q,session,step,PLAN,result)
            seq=result['sequence']
            need(seq['installed_before']==seq['installed_after']==q.installed and
                 seq['after_state_completed'] is True and seq['restoration_qualified'] is True and
                 seq['foreground_before']==seq['foreground_after'],'EXACT_POST_ENTRY_INSPECTION_SCOPE_REQUIRED')
        else:
            current='exact_owned_cleanup';selected=flow.selected_task();result['owned_task']=selected
            completed=flow.cleanup();result['cleanup']=completed
            absent=completed.get('new_task_already_absent') is True and completed.get('removal_attempted') is False
            removed=completed.get('new_leaf_removed_and_verified') is True and completed.get('other_tasks_preserved') is True
            need(absent or removed,'EXACT_OWNED_CLEANUP_COMPLETION_REQUIRED')
            after=flow.last_stack_task_ids if absent else completed['task_ids_after']
            need(after==selected['prelaunch_task_ids'] and selected['task'] not in after,
                 'PREEXISTING_TASK_SET_PRESERVED')
            result['task_ids_after']=after;result['owned_task_absent']=True
        current='helper_after';result['helper_after']=session.installed()
        need(result['helper_after']==result['helper_before'],'HELPER_CHANGED_DURING_PHASE')
        current='target_after';result['target_after']=artifacts.after()
        need(result['target_after']==result['target_before'],'TARGET_APKS_CHANGED_DURING_PHASE')
        if phase=='launch':
            need(flow.policy.counts=={'target_uid':2,'target_path':2,'helper_uid':2,'helper_path':2,
                'resolve':1,'stacks':2} and flow.command_index==12 and flow.launch_claimed is True,
                'EXACT_LAUNCH_COMMAND_COUNTS_REQUIRED')
        if phase=='inspect':
            stable_count=len(result['search_entry']['stability_reads'])
            need(3<=stable_count<=8,'EXACT_BOUNDED_COMPLETED_STABILITY_READS')
            completed=[*PLAN['stability'][:stable_count],PLAN['entry'],PLAN['post']]
            count=len(completed)
            need(flow.policy.counts=={'target_uid':2,'target_path':2,'helper_uid':2+2*count,
                'helper_path':2+2*count,'stacks':2*count,'instrument':3*count+1,'foreground':3*count} and
                flow.command_index==8+9*count+1 and
                flow.policy.used_nonces=={n for plan in completed for n in plan['nonces'].values()} and
                flow.policy.action_nonces=={PLAN['entry']['nonces']['action']} and flow.action_attempted is True,
                'EXACT_SEARCH_ENTRY_COMMAND_AND_NONCE_COUNTS_REQUIRED')
            result['click_actions']=1
        result['ok']=True
    except BaseException as error:
        if phase=='inspect':
            retain_navigation_failure_observations(result)
        elif session is not None and hasattr(session,'sequence_observation'):
            result['failed_sequence_observation']=session.sequence_observation
        u.remember(result,current,error)
    finally:
        if artifacts is not None:
            try:
                if len(artifacts.records)==3 and 'target_after' not in result:
                    result['failed_scope_files_revalidated']=artifacts.revalidate_files()
            except BaseException as error:u.remember(result,'failed_scope_files_revalidation',error)
            try:result['target_FD_cleanup']=artifacts.close()
            except BaseException as error:u.remember(result,'target_FD_cleanup',error)
        if flow is not None:
            result['command_counts']=dict(flow.policy.counts)
            result['click_commands_attempted']=len(flow.policy.action_nonces)
            result['durable_command_count']=flow.command_index
            try:flow.guard(attempted=flow.action_attempted);result['final_Main_guard_passed']=True
            except BaseException as error:u.remember(result,'final_Main_guard',error)
            try:flow.close();result['held_binding_released']=True
            except BaseException as error:u.remember(result,'held_binding_release',error)
        if guard is not None:
            try:
                result['Main_after']=guard()
                need(result['Main_after']==result.get('Main_before_lock'),'PHASE_MAIN_CHANGED')
            except BaseException as error:u.remember(result,'independent_final_Main',error)
        for fd,name in ((action_lock,'action_lock'),(flow_lock,'flow_lock')):
            if fd is not None:
                try:os.close(fd);result[name+'_released']=True
                except BaseException as error:u.remember(result,name+'_release',error)
        try:qualified(expected);result['source_and_artifact_unchanged']=True
        except BaseException as error:u.remember(result,'final_source_and_artifact',error)
    result['action_attempted']=bool(flow is not None and flow.action_attempted)
    result['outcome_unknown']=bool(result['action_attempted'] and not result['ok'])
    result['seconds']=time.monotonic()-began
    try:ref.write_new(step/'result.json',result)
    except BaseException as error:u.remember(result,'durable_phase_result_write',error)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':')),flush=True)
    return 0 if result['ok'] else 2


def durable(observed,phase,expected):
    path=FLOW/'steps'/(phase+'-01')/'result.json';raw=read(path);value=json.loads(raw)
    need(observed==value and value['phase']==phase and value['nonce']==NONCE and
         value['source_manifest_sha256']==expected and value['package']==PACKAGE and value['uid']==UID and
         value['helper_package']==SELF and value['helper_uid']==HELPER_UID and
         value['ok'] is True and value['error'] is None and value['secondary_errors']==[] and
         value['outcome_unknown'] is False and value['final_Main_guard_passed'] is True and
         value['held_binding_released'] is True and value['flow_lock_released'] is True and
         value['target_FD_cleanup']['held_APK_FDs_closed']==3 and value['target_before']==value['target_after'] and
         value['helper_before']==value['helper_after'] and value['source_and_artifact_unchanged'] is True,
         'EXACT_SUCCESSFUL_DURABLE_AMAZON_PHASE:'+phase)
    if phase!='cleanup':need(value['action_lock_released'] is True,'PHASE_ACTION_LOCK_RELEASE')
    if phase=='launch':need(value['launch']['native_launch_acknowledged'] is True,'ACTUAL_LAUNCH_ACK')
    if phase=='inspect':
        need(value['inspection_completed'] is True and value['sequence']['restoration_qualified'] is True
             and value['sequence']['after_state_completed'] is True and value['search_entry_click_completed'] is True
             and value['search_entry']['ok'] is True and value['search_entry']['click_acknowledged'] is True
             and value['search_entry']['post_inspection_completed'] is True and value['click_commands_attempted']==1,
             'ACTUAL_ENTRY_CLICK_POST_INSPECT_AND_RESTORATION_REQUIRED')
    if phase=='cleanup':need(value['owned_task_absent'] is True,'ACTUAL_OWNED_TASK_ABSENT_REQUIRED')
    return value,{'path':str(path),'bytes':len(raw),'sha256':sha(raw)}


def execute(expected):
    need(os.getuid()==os.geteuid()==0 and HERE==SOURCE,'EXACT_ROOT_COORDINATOR_REQUIRED')
    q=qualified(expected);u,ref=q.util,q.ref
    claim=json.loads(read(ROOT/'once.claim.json',65536))
    need(claim=={'nonce':NONCE,'source_manifest_sha256':expected,'automatic_retry':False},'EXACT_ONCE_CLAIM_REQUIRED')
    need(not os.path.lexists(FLOW),'NO_OLD_OR_PARTIAL_FLOW_REPLAY')
    evidence=ROOT/'evidence';evidence.mkdir(mode=0o700)
    result={'schema':1,'ok':False,'error':None,'secondary_errors':[],'nonce':NONCE,
        'source_manifest_sha256':expected,'package':PACKAGE,'uid':UID,'helper_package':SELF,'helper_uid':HELPER_UID,
        'flow':str(FLOW),'component':COMPONENT,'actual_install':q.install,'actual_resolution':q.resolution,
        'automatic_retry':False,'maximum_native_launches':1,'launch_worker_requested':False,
        'inspect_worker_requested':False,'cleanup_requested':False,'click_actions':0,'text_actions':0,
        'screenshots':0,'audio_actions':0,'package_mutations':0,'permission_grants':0,'settings_writes':0,
        'Bili_Flow_instantiated':False,'old_v2_helper_called':False,'raw_UI_tree_private_only':True,
        'business_success_verified':False,'whole_app_production_ready':False}
    activation=epoch=resources=None
    try:
        resources=u.prepare_owned_limits();result['owned_before']=resources
        activation=ref.current_baseline()
        epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'amazon_coordinator_epoch')
        guard=lambda:ref.main_guard(activation,epoch)
        result['Main_before']=guard()
        FLOW.mkdir(mode=0o700)
        ref.write_new(FLOW/'scope.json',scope_record(q,expected))
        ref.write_new(FLOW/'baseline.json',ref.read(ref.BASELINE,expected=ref.BASELINE_SHA))
        ref.write_new(FLOW/'baseline-qualification.json',ref.read(ref.QUALIFICATION,expected=ref.QUALIFICATION_SHA))
        (FLOW/'steps').mkdir(mode=0o700)
        result['launch_worker_requested']=True
        launched=ref.run_cli('01-launch',['/usr/bin/python3','-I','-B',str(HERE/'owned_inspect.py'),
            '--worker-once','launch','--source-manifest-sha256',expected],190,evidence,guard)
        _,result['launch_result']=durable(launched,'launch',expected)
        result['owned_task'],result['owned_scope']=owned_scope(q)
        result['inspect_worker_requested']=True
        observed=ref.run_cli('02-inspect',['/usr/bin/python3','-I','-B',str(HERE/'owned_inspect.py'),
            '--worker-once','inspect','--source-manifest-sha256',expected],190,evidence,guard)
        inspection,result['inspection_result']=durable(observed,'inspect',expected)
        result['assessments']=inspection['assessments']
        result['foreground']=inspection['sequence']['foreground_after']
        result['restoration']=inspection['sequence']['accessibility_restoration']
        result['post_entry_inspection_completed']=True
        result['search_entry_click_completed']=inspection['search_entry_click_completed']
        result['search_entry']=inspection['search_entry']
        result['click_actions']=inspection['click_actions']
        result['ok']=True
    except BaseException as error:u.remember(result,'coordinator',error)
    finally:
        # A failed launch/inspection or evidence write never suppresses an
        # independently authorized original exact-task retirement. Unknown
        # launch identity is retained; it does not authorize a package-wide stop.
        if result['launch_worker_requested']:
            try:
                if os.path.lexists(FLOW/'launch-scope.json'):
                    result['owned_task'],result['owned_scope']=owned_scope(q)
                    need(activation is not None and epoch is not None,'CLEANUP_MAIN_BINDING_REQUIRED')
                    result['cleanup_requested']=True
                    cleaned=ref.run_cli('03-cleanup',['/usr/bin/python3','-I','-B',str(HERE/'owned_inspect.py'),
                        '--worker-once','cleanup','--source-manifest-sha256',expected],130,evidence,
                        lambda:ref.main_guard(activation,epoch))
                    cleaned,result['cleanup_result']=durable(cleaned,'cleanup',expected)
                    result['owned_task_absent_after_cleanup']=True
                    result['task_ids_after']=cleaned['task_ids_after']
                else:
                    result['cleanup_not_authorized_without_exact_owned_scope']=True
                    result['possible_native_launch_outcome_requires_reconciliation']=os.path.lexists(FLOW/'launch-attempted.json')
            except BaseException as error:u.remember(result,'exact_owned_task_retirement',error)
        if result['ok'] and result.get('owned_task_absent_after_cleanup') is not True:
            u.remember(result,'cleanup_completion',RuntimeError('ACTUAL_OWNED_CLEANUP_MISSING'))
        # Bounded pins only; no raw tree or command stdout copied into this result.
        result['retained_phase_results']={}
        for phase in PHASE_SECONDS:
            try:
                path=FLOW/'steps'/(phase+'-01')/'result.json'
                if os.path.lexists(path):
                    raw=read(path);result['retained_phase_results'][phase]={'path':str(path),'bytes':len(raw),'sha256':sha(raw)}
            except BaseException as error:u.remember(result,'retained_phase_result:'+phase,error)
        if activation is not None and epoch is not None:
            try:
                result['Main_after']=ref.main_guard(activation,epoch)
                need(result['Main_after']==result.get('Main_before'),'COORDINATOR_MAIN_CHANGED')
            except BaseException as error:u.remember(result,'final_Main',error)
        try:qualified(expected);result['source_and_artifact_unchanged']=True
        except BaseException as error:u.remember(result,'final_source_and_artifact',error)
        if resources is not None:
            try:
                result['owned_after']=u.owned_resources();u.resources_qualified(resources,result['owned_after'])
            except BaseException as error:u.remember(result,'final_owned_resources',error)
        try:pin=ref.write_new(ROOT/'result.json',result)
        except BaseException as error:u.remember(result,'coordinator_result_write',error);pin=None
        print(json.dumps({'ok':result['ok'],'result':pin,'error':result['error'],
            'secondary_errors':result['secondary_errors'],'whole_app_production_ready':False},sort_keys=True),flush=True)
    return 0 if result['ok'] else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-once',action='store_true');p.add_argument('--worker-once',choices=tuple(PHASE_SECONDS))
    p.add_argument('--source-manifest-sha256');a=p.parse_args()
    need(not(a.execute_once and a.worker_once),'ONE_EXPLICIT_PHASE_ONLY')
    if a.worker_once:return worker(a.source_manifest_sha256,a.worker_once)
    if a.execute_once:return execute(a.source_manifest_sha256)
    print(json.dumps({'state':'PLAN_ONLY','nonce':NONCE,'root':str(ROOT),'flow':str(FLOW),'component':COMPONENT,
        'helper_uid':HELPER_UID,'maximum_native_launches':1,'new_helper_operations':['bounded inspect stability','fresh inspect + one click','independent post inspect'],
        'maximum_clicks':1,'text_actions':0,'screenshots':0,'audio':0,'device_calls':0,'submitted':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
