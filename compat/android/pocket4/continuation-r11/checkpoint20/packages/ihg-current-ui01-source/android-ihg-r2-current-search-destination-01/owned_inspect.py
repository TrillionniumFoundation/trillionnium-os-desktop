#!/usr/bin/env python3
"""One actual-bound IHG launch, explicit Search then Destination and owned cleanup.

At most one current Search click, then one fresh complete-form Destination
ancestor click after the first sequence qualifies, and an independent read.
No text entry, login, booking or purchase; raw helper trees remain private.
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
ROOT=Path('/home/alex/work/pocket4-ihg-r2-public-search-destination-entry-01')
SOURCE=ROOT/'source'
NONCE='b2cd08fcaad1f2faaed5de2ff5df01af'
FLOW=Path('/home/alex/work/pocket4-ihg-owned-qa-r2-flow-'+NONCE)
PACKAGE='com.ihg.apps.android'
UID=10137
SELF='org.droidloom.qa.ihg.r2'
HELPER_UID=10153

CURRENT_HOST_MANIFEST='6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'
CURRENT_BASELINE_SCHEMA='pocket4-main-current-baseline-v1'
CURRENT_EPOCH='734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'
CURRENT_BASELINE_SHA='163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266'
CURRENT_QUALIFICATION_SHA='f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6'
COMPONENT=PACKAGE+'/.activity.MainActivity'
# The source label is inert; the exact selector is derived from the current complete inspection.
SEARCH_PLAN={"schema":1,"operation":"click","selector":{"text":"Search"},"nonces":{"before":"6cb8830127be3127184ff3de1a3360cb","inspect":"aeaca1e38561e485e1864e0487b00d72","action":"77c81ed7a1e1a4c3f771e7ed78790c24","after":"62a9a3349b45e527fb0048ea45ed621e"}}
PLAN={"schema":1,"operation":"click","selector":{"text":"Destination"},"nonces":{"before":"f785cca2a3c3aded7b9f4693f47e8417","inspect":"7467c0e921207f3a4f2db14fd29d139b","action":"a3bd5d4b4c8b40bd077c68723c7ddfb4","after":"27e8d51fa580384289e71e415ed55642"}}
POST_PLAN={"schema":1,"operation":"inspect","nonces":{"before":"92291c1fd5531298e110d66d86f99de1","inspect":"cbc5587e16902bdaffb4463c7ec48be4","after":"bf222c38e07c2ff5fbd7a8584cd3bd0e"}}
SEARCH_READINESS_PLANS=[{"schema":1,"operation":"inspect","nonces":{"before":"7b1b9c010734df6b8cc91387f2019ca3","inspect":"7c5d635d5abeed5f73a117d5c807b934","after":"5247258a0984f0ab6866681e858befb8"}},{"schema":1,"operation":"inspect","nonces":{"before":"5f446927b595b9413991eba23897dd12","inspect":"e9091cc59d97fc30b59907290b71d48d","after":"461287d7da6340ddda112631768b48dc"}},{"schema":1,"operation":"inspect","nonces":{"before":"30d18b0774d032cd080bb4bdf85f2f25","inspect":"2e9a1c9b501f49c21cd815f76a564cea","after":"ddd0ecb9ca57d12251d52300d469b58c"}},{"schema":1,"operation":"inspect","nonces":{"before":"d09dfad0f6b214cd367a5a8aecb8df65","inspect":"04e509d6b25d7fd1ea4f5ce5cad89c5f","after":"8ed54873b7a0f2306feea3daf9539541"}},{"schema":1,"operation":"inspect","nonces":{"before":"477707c9df3713e9368e5dfd79483631","inspect":"422dd5c92c819a67ec4db025e48a8743","after":"7a1244cb4ff0e18ed7e269f16a85dcbe"}},{"schema":1,"operation":"inspect","nonces":{"before":"15437fbfb9087ca77073cfc5c76e13a7","inspect":"1052ea26086958cbf311e4bc42f8d2b8","after":"f7ed30aa27c66e2f500459dbd2c99887"}},{"schema":1,"operation":"inspect","nonces":{"before":"f4eed9da8eed9f03f7b881d7541c376b","inspect":"e7bbb25d80dcf278949387fab3d5b09c","after":"6a2b6f4bb0ff87a6602241f5349a27a6"}},{"schema":1,"operation":"inspect","nonces":{"before":"0484524ba8d4891d335b85c0ef7b709e","inspect":"f37f434a9000109f1985ef4664f701b7","after":"2e02cc7cb78355d00d2d90b0feda02a8"}}]
INSTALL_ROOT=Path("/home/alex/work/pocket4-owned-ihg-qa-r2-install-state-02")
INSTALL_SOURCE=INSTALL_ROOT/'source'
INSTALL_SOURCE_SHA="e8cf9d4c04025bb092663519a01624fa40e552600dc5643a50ebf9bace915103"
UTIL_SHA="b76a9a81e7c7c2ac11a880c9f8a82cb2209a2abc44468edf5c76bd13af798db3"
UTIL_BYTES=38130
CONTEXT_SHA="a62cebdc4fa1249dbbdfa28f87f0547e529ef9886f8b6bb247c811f96f673768"
TRANSPORT_SHA="27e07fbaaccca4e5113e1750a3b7baa9d05048a1e8588f09cdc8f9ed5cf44089"
STATE_NONCE="6c71a5c324a1c669572981cc38e4f82b"
STATE_WIRE="10d422744e4484db083293e6b7752ef7c1a1ebec0c059b009bfdb632daf9a723"
INSTALLED={"apk_sha256":"db7012b9a66f4177f8b4ac57ac3d39e77b8c9871a8b2c364343c420fb9d42f41","base_apk":"/data/app/~~2Ra07v9TklCSDPAiZXK0qQ==/org.droidloom.qa.ihg.r2-QQ0wWKyusbCYEh7ZGrTsNg==/base.apk","bytes":24720,"held_file":{"bytes":24720,"device":1811,"gid":1000,"inode":789387,"mode":33188,"mtime_ns":1793952064858420740,"nlink":1,"uid":1000},"package":"org.droidloom.qa.ihg.r2","signer_bound_by_exact_signed_apk_bytes":"a2ae584189d8faa5f3705b9278b29b38f2f32e6ca97b1224e80f9b1dfc0d1e5a","uid":10153}
PRIOR={"coordinator":("result.json",3961,"4f7f628b7aa600e686bffcd2eec33f908116db94c7192090b68096b6710b2c78"),"stage":("stage-result.json",6856,"fbee6aa99439b55aa04952665c98122799e3a4135a76ffe9717a0399cf020cc2"),"worker":("worker/result.json",12552,"81f25ba7fcced82ecc0534ce41f70b7b98ce1f152aa1e5e6c132db825d65fb58")}
RESOLVER_ROOT=Path('/home/alex/work/pocket4-ihg-artifact-launcher-readonly-01')
# The five-command metadata source is already an exact pinned install input.
RESOLVER_SOURCE=INSTALL_SOURCE/'references/read_ihg.py'
RESOLVER_SHA='51ecf1c0a12d8bfa9ed721265e14c4f06ef3eff72cbf5840de9569eb09797d40'
RESOLVER_BYTES=21052
RESOLVER_NONCE='70e82b2ce30be099f99c9e46431b2406'
RESOLVER_RECORDS={'worker': ('result.json', 8878, '153ddbfc8393570621b64a478675c2a0180826a7a6ecada0ade8a6aa4ed79722'), 'stage': ('stage-result.json', 1583, '72224eae94c82a258b1a49d5730363f5e3c62cd8db769f083d5b5ec149dd55a8')}
RUNTIME_FILES={'owned_inspect.py','ihg_task_context.py','public_destination.py','INPUTS.json'}
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
    # The original Ticket observation preceded this helper install: it proves
    # target artifacts and launcher only, and never asserts a helper identity.
    worker,stage=rows['worker'],rows['stage']
    for value in (worker,stage):
        need(value['ok'] is True and value['error'] is None and value['secondary_errors']==[] and
             value['nonce']==RESOLVER_NONCE and value['source_sha256']==RESOLVER_SHA and
             value['package']==PACKAGE and value['App_launches']==0 and value['instrumentation_calls']==0,
             'EXACT_ACTUAL_IHG_READ_ONLY_RESOLVER_REQUIRED')
    need(stage['worker_result']=={'path':str(RESOLVER_ROOT/'result.json'),
         'bytes':RESOLVER_RECORDS['worker'][1],'sha256':RESOLVER_RECORDS['worker'][2]} and
         stage['worker_returncode']==0,'ACTUAL_IHG_RESOLVER_PARENT_CHAIN_REQUIRED')
    launcher=worker['launcher_resolution']
    need(launcher['component']==COMPONENT and launcher['package']==PACKAGE and
         launcher['user']==0 and launcher['fallback_used'] is False and launcher['launch_performed'] is False and
         launcher['later_launch_requires_new_current_binding'] is True and
         worker['package_read_commands_completed']==5 and worker['UI_actions']==0,
         'ACTUAL_IHG_RESOLVER_EXACT_COMPONENT_REQUIRED')
    need(worker['metadata_before']==worker['metadata_after']=={'package':PACKAGE,'uid':UID,'user':0,'version_code':50023219} and
         worker['actual_package_UID_version_APK_chain_stable'] is True and
         worker['Main_before']==worker['Main_after']==stage['Main_before']==stage['Main_after'] and
         len(worker['artifacts'])==1 and worker['total_apk_bytes']==44999052 and
         worker['artifacts'][0]['sha256']=='c12bb3bae3514c94caaca0a4ef6e8f1ad4491cbce57fd2a15be48b83b4c85b90',
         'ACTUAL_IHG_RESOLVER_SCOPE_STABILITY_REQUIRED')
    observations=worker['command_observations']
    need(len(observations)==5 and all(row['index']==i+1 and row['returncode']==0 and row['joined'] is True and
         row['host_timed_out'] is False and row['first_error'] is None and row['secondary_errors']==[] and
         row['recorder_errors']==[] for i,row in enumerate(observations)),
         'FIVE_ORIGINAL_JOINED_READ_ONLY_COMMANDS_REQUIRED')
    need(all(worker[k] is True for k in ('final_Main_guard_passed','held_binding_released','action_lock_released'))
         and stage['source_unchanged'] is True,'ACTUAL_IHG_RESOLVER_RETIRED_REQUIRED')
    return {'component':COMPONENT,'actual_resolve_stdout_sha256':launcher['resolve_stdout_sha256'],
        'prior_receipts':{k:{'path':str(RESOLVER_ROOT/v[0]),'bytes':v[1],'sha256':v[2]}
                          for k,v in RESOLVER_RECORDS.items()},
        'historical_resolution_not_launch_authority':True,'new_prelaunch_resolution_required':True,
        'prior_helper_identity_asserted':False}


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
    need(w['runtime_ticket_context_sha256']==CONTEXT_SHA and
         w['runtime_ticket_transport_sha256']==TRANSPORT_SHA and
         w['exact_command_count']==13,'ACTUAL_INSTALL_RUNTIME_CHAIN')
    state=w['state'];helper=state['helper']
    need(state['wire_sha256']==STATE_WIRE and state['actual_command_returncode']==0 and
         state['actual_instrumentation_finish_code']==-1 and
         state['held_transport_returned_after_post_guard'] is True and
         helper['nonce']==STATE_NONCE and helper['self_uid']==HELPER_UID and
         helper['protocol']=='pocket4-owned-ihg-qa-v2' and helper['op']=='state' and
         helper['ok'] is True and helper['ui_automation_connected'] is False,
         'ACTUAL_NO_AUTOMATION_STATE_REQUIRED')
    need(w['target_before']==w['target_after'] and
         w['Main_before_lock']==w['Main_before']==w['Main_after']==c['Main_before']==c['Main_after']==s['Main_before']==s['Main_after'],
         'ACTUAL_INSTALL_MAIN_OR_TARGET_CHAIN')
    need(w['Main_before'].get('schema')=='pocket4-current-main-guard-v1' and
         w['Main_before'].get('Main_epoch_sha256')==CURRENT_EPOCH and
         w['Main_before'].get('current_baseline_sha256')==CURRENT_BASELINE_SHA and
         w['Main_before'].get('current_baseline_qualification_sha256')==CURRENT_QUALIFICATION_SHA and
         w['Main_before'].get('seven_processes_match') is True and
         w['Main_before'].get('three_host_processes_match') is True and
         w['Main_before'].get('resource_limits_match') is True,
         'ACTUAL_INSTALL_TYPED_CURRENT_BASELINE_REQUIRED')
    need(w['staging_cleanup']['staged_apk_removed'] is True and
         w['staging_cleanup']['staged_directory_removed'] is True and
         w['target_FD_cleanup']['held_APK_FDs_closed']==1 and
         w['held_binding_released'] is True and w['action_lock_released'] is True and
         w['final_Main_guard_passed'] is True and w['outcome_unknown'] is False,
         'ACTUAL_INSTALL_RETIREMENT_REQUIRED')
    return {'prior_install_source_sha256':INSTALL_SOURCE_SHA,
        'prior_receipts':{k:{'bytes':v[1],'sha256':v[2]} for k,v in PRIOR.items()},
        'installed':INSTALLED,'actual_state_wire_sha256':STATE_WIRE,
        'no_prior_install_or_state_replayed':True}

def qualified(expected):
    need(type(HELPER_UID) is int and 10000<=HELPER_UID<100000 and HELPER_UID not in (10137,10196) and isinstance(INSTALLED,dict) and
         isinstance(STATE_WIRE,str) and re.fullmatch('[0-9a-f]{64}',STATE_WIRE) and
         isinstance(PRIOR,dict) and set(PRIOR)=={'coordinator','stage','worker'} and
         isinstance(PRIOR['worker'],tuple),'ACTUAL_IHG_INSTALL_BINDING_NOT_READY')
    manifest=verify_source(expected)
    util=load(INSTALL_SOURCE/'install_state.py',UTIL_SHA,'ticket_qualified_install_primitives',UTIL_BYTES)
    install_manifest=util.verify_source(INSTALL_SOURCE_SHA)
    prior={k:json.loads(read(INSTALL_ROOT/v[0],expected=v[2],size=v[1])) for k,v in PRIOR.items()}
    install_observation=actual_install(prior)
    reader=load(RESOLVER_SOURCE,RESOLVER_SHA,'ticket_qualified_launcher_reference',RESOLVER_BYTES)
    records={k:json.loads(read(RESOLVER_ROOT/v[0],expected=v[2],size=v[1])) for k,v in RESOLVER_RECORDS.items()}
    actual_component=actual_resolver(records,INSTALLED)
    adapter,qa,proof,apk=util.qualified_inputs();del apk
    adapter.validate_plan(SEARCH_PLAN,qa);adapter.validate_plan(PLAN,qa);adapter.validate_plan(POST_PLAN,qa)
    need(len(SEARCH_READINESS_PLANS)==8,'EIGHT_READINESS_PLANS_REQUIRED')
    for plan in SEARCH_READINESS_PLANS:
        adapter.validate_plan(plan,qa)
        need(plan['operation']=='inspect','READINESS_MUST_BE_NO_ACTION')
    need(qa.PACKAGE==PACKAGE and qa.UID==UID and qa.SELF==SELF and adapter.SELF==SELF,
         'DEDICATED_IHG_HELPER_SOURCE_REQUIRED')
    values=[NONCE,*SEARCH_PLAN['nonces'].values(),*PLAN['nonces'].values(),*POST_PLAN['nonces'].values(),
            *(nonce for plan in SEARCH_READINESS_PLANS for nonce in plan['nonces'].values())]
    need(len(values)==len(set(values))==36 and STATE_NONCE not in values and
         all(re.fullmatch('[0-9a-f]{32}',v) for v in values),'EXACT_NEW_FLOW_AND_THIRTY_FIVE_HELPER_NONCES')
    inputs=json.loads(read(HERE/'INPUTS.json',65536))
    need(inputs['nonce']==NONCE and inputs['component']==COMPONENT and inputs['installed_helper']==INSTALLED
         and inputs['resolver_records']=={k:{'relative_path':v[0],'bytes':v[1],'sha256':v[2]} for k,v in RESOLVER_RECORDS.items()},
         'EXACT_RUNTIME_INPUT_RECORD_REQUIRED')
    need(inputs['explicit_search_click_plan']==SEARCH_PLAN and inputs['public_destination_click_plan']==PLAN and
         inputs['independent_post_plan']==POST_PLAN and inputs['search_readiness_plans']==SEARCH_READINESS_PLANS,
         'EXACT_SEARCH_READINESS_AND_SEARCH_DESTINATION_PLANS_REQUIRED')
    public_destination=load(HERE/'public_destination.py',manifest['files']['public_destination.py']['sha256'],'fresh_public_destination_observation')
    # Interface-only binding for the unchanged phase body; no resolver action
    # is run here and the prior five-command receipt has no helper assertion.
    resolver=types.SimpleNamespace(INSTALL_SOURCE=INSTALL_SOURCE,INSTALL_SOURCE_SHA=INSTALL_SOURCE_SHA,
        CONTEXT_SHA=CONTEXT_SHA,TRANSPORT_SHA=TRANSPORT_SHA,RESOLVE=reader.RESOLVE,component=reader.component,
        INSTALLED=INSTALLED)
    return types.SimpleNamespace(manifest=manifest,resolver=resolver,util=util,ref=util.references(),
        install_manifest=install_manifest,install=install_observation,resolution=actual_component,
        adapter=adapter,qa=qa,proof=proof,installed=INSTALLED,public_destination=public_destination)


def scope_record(q,expected):
    baseline=q.ref.current_baseline()
    need(baseline.get('schema')==CURRENT_BASELINE_SCHEMA and
         baseline['framework_epoch']['sha256']==CURRENT_EPOCH==q.ref.EPOCH and
         q.ref.BASELINE_SHA==CURRENT_BASELINE_SHA and
         q.ref.QUALIFICATION_SHA==CURRENT_QUALIFICATION_SHA and
         type(baseline['packages'].get(PACKAGE)) is int and baseline['packages'][PACKAGE]==UID,
         'CURRENT_TYPED_OWN_TARGET_SCOPE_REQUIRED')
    return {'schema':'pocket4-current-recorder-scope-v1','current_baseline_schema':baseline['schema'],
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
             helper['op']==('click' if phase=='action' else 'inspect' if phase=='inspect' else 'state') and
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
            need(helper['node_action']=='ACTION_CLICK' and helper['node_action_returned'] is True and
                 helper['action_attempted'] is True and helper['outcome_unknown'] is True and
                 helper['inspection_nonce']==plan['nonces']['inspect'] and
                 helper['inspection_sha256']==sequence['inspection_wire_sha256'],'ACTUAL_CURRENT_SEARCH_CLICK_ACK_REQUIRED')
            row.update(node_action='ACTION_CLICK',node_action_returned=True,action_attempted=True,outcome_unknown=True,
                target_node_sha256=helper['target_node_sha256'],inspection_nonce=helper['inspection_nonce'],
                inspection_sha256=helper['inspection_sha256'],
                action_window={k:helper['action_window'][k] for k in ('package','display','type','focused')},
                window_observation=q.qa.window_observation(helper['window_observation']),
                tree_observations=q.qa.tree_observations(helper['tree_observations'],'click',True))
        result[phase]=row
    return result


def worker(expected,phase):
    need(os.getuid()==os.geteuid()==0 and HERE==SOURCE and phase in PHASE_SECONDS,'EXACT_ROOT_PHASE_REQUIRED')
    q=qualified(expected);u,ref=q.util,q.ref
    search_plan=json.loads(json.dumps(SEARCH_PLAN));click_plan=json.loads(json.dumps(PLAN))
    post_plan=json.loads(json.dumps(POST_PLAN));readiness_plans=json.loads(json.dumps(SEARCH_READINESS_PLANS))
    plans={'search':search_plan,'destination':click_plan,'post':post_plan,'readiness':readiness_plans}
    step=FLOW/'steps'/(phase+'-01')
    result={'schema':1,'ok':False,'error':None,'secondary_errors':[],'phase':phase,'nonce':NONCE,
        'source_manifest_sha256':expected,'package':PACKAGE,'uid':UID,'helper_package':SELF,'helper_uid':HELPER_UID,
        'actual_install':q.install,'actual_resolution':q.resolution,'build':q.proof,
        'automatic_retry':False,'Bili_Flow_instantiated':False,'old_v2_helper_called':False,
        'maximum_click_actions':2,'maximum_no_action_search_readiness_sequences':8,'text_actions':0,'screenshots':0,'audio_actions':0,'permission_grants':0,'settings_writes':0,
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
            'automatic_retry':False,'mutation':True,'request':plans if phase=='inspect' else None})
        context=u.module(q.resolver.INSTALL_SOURCE/'ihg_context.py',q.resolver.CONTEXT_SHA,'amazon_exact_artifact_context')
        transport=u.module(q.resolver.INSTALL_SOURCE/'ihg_transport.py',q.resolver.TRANSPORT_SHA,'amazon_exact_transport')
        task_module=load(HERE/'ihg_task_context.py',q.manifest['files']['ihg_task_context.py']['sha256'],'amazon_task_context')
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
            transport,result,began+PHASE_SECONDS[phase],phase,q.qa,plans,q.resolver.RESOLVE,scope_record(q,expected))
        reference=json.loads(u.read(q.resolver.INSTALL_SOURCE/'target-artifact-reference.json',expected=
            q.install_manifest['files']['target-artifact-reference.json']['sha256']))
        reader=u.module(q.resolver.INSTALL_SOURCE/'references/read_ihg.py',u.READER_SHA,'amazon_artifact_parser')
        artifacts=context.ArtifactSet(flow,reference,reader)
        current='target_before';result['target_before']=artifacts.before()
        session=(q.public_destination.make_session(q.adapter,flow,recorder,q.qa,q.proof,HELPER_UID,search_plan,click_plan,post_plan,readiness_plans)
                 if phase=='inspect' else q.adapter.Session(flow,recorder,q.qa,q.proof,HELPER_UID))
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
            current='explicit_search_destination_sequences'
            q.public_destination.run_sequences(q.qa,session,q.installed,search_plan,click_plan,post_plan,readiness_plans,result,
                lambda seq,plan:assessment_summary(q,step,seq,plan),lambda phase,error:u.remember(result,phase,error))
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
        if phase=='inspect' and result['error'] is None:
            count=result.get('search_readiness_count')
            need(type(count) is int and 3<=count<=8 and result.get('search_readiness_qualified') is True and
                 len(result['search_readiness_observations'])==count,
                 'EXACT_QUALIFIED_NO_ACTION_READINESS_COUNT_REQUIRED')
            used_readiness={nonce for plan in SEARCH_READINESS_PLANS[:count] for nonce in plan['nonces'].values()}
            need(flow.policy.counts=={'target_uid':2,'target_path':2,'helper_uid':8+2*count,'helper_path':8+2*count,
                'stacks':6+2*count,'instrument':11+3*count,'foreground':9+3*count,'click':2} and
                flow.command_index==37+9*count and
                flow.policy.used_nonces==set(SEARCH_PLAN['nonces'].values())|set(PLAN['nonces'].values())|set(POST_PLAN['nonces'].values())|used_readiness and
                flow.action_attempted is True and result.get('destination_click_and_observation_completed') is True and
                result.get('explicit_search_then_destination_completed') is True,
                'EXACT_BOUNDED_READINESS_TWO_PUBLIC_CLICKS_AND_POST_COUNTS_REQUIRED')
        result['ok']=result['error'] is None and result['secondary_errors']==[]
    except BaseException as error:
        if session is not None and hasattr(session,'sequence_observation'):
            result['failed_sequence_observation']=session.sequence_observation
        u.remember(result,current,error)
    finally:
        if artifacts is not None:
            try:
                if len(artifacts.records)==1 and 'target_after' not in result:
                    result['failed_scope_files_revalidated']=artifacts.revalidate_files()
            except BaseException as error:u.remember(result,'failed_scope_files_revalidation',error)
            try:result['target_FD_cleanup']=artifacts.close()
            except BaseException as error:u.remember(result,'target_FD_cleanup',error)
        if flow is not None:
            result['command_counts']=dict(flow.policy.counts)
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
    result['outcome_unknown']=bool(result['action_attempted'] and (phase=='inspect' or not result['ok']))
    result['click_requests_admitted']=0 if session is None else len(getattr(session,'action_requests_admitted',set()))
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
         value['outcome_unknown'] is (phase=='inspect') and value['final_Main_guard_passed'] is True and
         value['held_binding_released'] is True and value['flow_lock_released'] is True and
         value['target_FD_cleanup']['held_APK_FDs_closed']==1 and value['target_before']==value['target_after'] and
         value['helper_before']==value['helper_after'] and value['source_and_artifact_unchanged'] is True,
         'EXACT_SUCCESSFUL_DURABLE_AMAZON_PHASE:'+phase)
    if phase!='cleanup':need(value['action_lock_released'] is True,'PHASE_ACTION_LOCK_RELEASE')
    if phase=='launch':need(value['launch']['native_launch_acknowledged'] is True,'ACTUAL_LAUNCH_ACK')
    if phase=='inspect':
        need(value['inspection_completed'] is True and
             value['search_sequence']['restoration_qualified'] is True and value['search_sequence']['after_state_completed'] is True and
             value['search_sequence']['click_acknowledged'] is True and value['search_sequence_qualified'] is True and
             value['public_search_entry']['public_search_entry_selection_verified'] is True and
             value['explicit_search_then_destination_completed'] is True and
             value['search_sequence']['owned_task']==value['sequence']['owned_task']==value['post_sequence']['owned_task'] and
             value['sequence']['restoration_qualified'] is True and
             value['sequence']['after_state_completed'] is True and value['sequence']['click_acknowledged'] is True and
             value['post_sequence']['after_state_completed'] is True and value['post_sequence']['restoration_qualified'] is True and
             value['destination_click_and_observation_completed'] is True and value['public_destination_observation']['current_public_destination_click_and_independent_read_verified'] is True,
             'ACTUAL_EXPLICIT_SEARCH_DESTINATION_POST_AND_THREE_RESTORATIONS_REQUIRED')
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
        'inspect_worker_requested':False,'cleanup_requested':False,'maximum_click_actions':2,'text_actions':0,
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
        launched=ref.run_cli('01-launch',['/usr/bin/python3','-I',str(HERE/'owned_inspect.py'),
            '--worker-once','launch','--source-manifest-sha256',expected],190,evidence,guard)
        _,result['launch_result']=durable(launched,'launch',expected)
        result['owned_task'],result['owned_scope']=owned_scope(q)
        result['inspect_worker_requested']=True
        observed=ref.run_cli('02-inspect',['/usr/bin/python3','-I',str(HERE/'owned_inspect.py'),
            '--worker-once','inspect','--source-manifest-sha256',expected],190,evidence,guard)
        inspection,result['inspection_result']=durable(observed,'inspect',expected)
        result['search_assessments']=inspection['search_assessments']
        result['search_restoration']=inspection['search_sequence']['accessibility_restoration']
        result['public_search_entry']=inspection['public_search_entry']
        result['explicit_search_then_destination_completed']=True
        result['assessments']=inspection['assessments']
        result['post_assessments']=inspection['post_assessments']
        result['foreground']=inspection['post_sequence']['foreground_after']
        result['restoration']=inspection['sequence']['accessibility_restoration']
        result['post_restoration']=inspection['post_sequence']['accessibility_restoration']
        result['public_destination_observation']=inspection['public_destination_observation']
        result['destination_click_and_observation_completed']=True
        result['business_outcome_unknown']=True
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
                    cleaned=ref.run_cli('03-cleanup',['/usr/bin/python3','-I',str(HERE/'owned_inspect.py'),
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
        'helper_uid':HELPER_UID,'maximum_native_launches':1,'new_helper_operations':['state','inspect','click','state','state','inspect','click','state','state','inspect','state'],
        'maximum_clicks':2,'text_actions':0,'screenshots':0,'audio':0,'device_calls':0,'submitted':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
