#!/usr/bin/env python3
"""One actual-bound 12306 launch, read-only QA sequence and owned task cleanup.

No click, text entry, old v2 helper, screenshot, audio, package change, permission
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
ROOT=Path('/home/alex/work/pocket4-ticket-owned-launch-inspect-01')
SOURCE=ROOT/'source'
NONCE='c398efeb8c07781670825f5ad68e13af'
FLOW=Path('/home/alex/work/pocket4-ticket-owned-qa-r1-flow-'+NONCE)
PACKAGE='com.MobileTicket'
UID=10121
SELF='org.droidloom.qa.ticket.r1'
HELPER_UID=10190
COMPONENT=PACKAGE+'/.ui.activity.WelcomeGuideActivity'
PLAN={'schema':1,'operation':'inspect','nonces':{
    'before':'e3900171d0a9e758b69a3e422f07fadb',
    'inspect':'5f90529456394889c097122a7fc15c4e',
    'after':'c17c36f9bb77a56733139530cd77c242'}}
INSTALL_ROOT=Path('/home/alex/work/pocket4-owned-ticket-qa-r1-install-state-01')
INSTALL_SOURCE=INSTALL_ROOT/'source'
INSTALL_SOURCE_SHA='241b8d26caa2279001f32db3895efab87b07723c2b8fce61a971381c26f7cd69'
UTIL_SHA='a2e26701436053bf9bca03f7a22ab84c899ab1bbc6ec609ac49caedb53115fd8'
UTIL_BYTES=32582
CONTEXT_SHA='e476b2383d884c70c31c4e87b0f8d92fe581f8ae38a2bf91f160208ae6d50d7e'
TRANSPORT_SHA='b236f9d7a81f4bd45a05804d0b0a98e25e5c34dfcd44c391cd5103a71d6df771'
STATE_NONCE='3e666f36e9eb4a9a4260408c325b420d'
STATE_WIRE='5e7878675d14282e0218735db7486461a508a3f776831b6a83fa936120fed907'
INSTALLED={'apk_sha256': 'b138eee4a638e90e02b4ea55a4cad3a6c5d24f7fb09b9e2536d4378f19a1dbdb', 'base_apk': '/data/app/~~HavxtLWUa1UnMAYK0YH31A==/org.droidloom.qa.ticket.r1-pnTW5dPyxhMgz63tfOmkTA==/base.apk', 'bytes': 24720, 'held_file': {'bytes': 24720, 'device': 1811, 'gid': 1000, 'inode': 789223, 'mode': 33188, 'mtime_ns': 1793902188809997047, 'nlink': 1, 'uid': 1000}, 'package': 'org.droidloom.qa.ticket.r1', 'signer_bound_by_exact_signed_apk_bytes': '91fbef4532e24cce6667f7f049e50ab227c14c622f3f6c7d7b05a3959595138b', 'uid': 10190}
PRIOR={
    'coordinator':('result.json',3074,'68ffcc7972aeff8943f6b206d04d974ca80d73d8d4defa4d5028231b519cac97'),
    'stage':('stage-result.json',1617,'c96402490ce14d783e999ddc18beaf7c3e29ffab783057291be72d59ab53fa94'),
    'worker':('worker/result.json',11213,'89f9880cf0ba18c52ec843eadee079433aa32c476a8a780ee5ddd9738fd51d9a'),
}
RESOLVER_ROOT=Path('/home/alex/work/pocket4-12306-artifact-launcher-readonly-01')
# The five-command metadata source is already an exact pinned install input.
RESOLVER_SOURCE=INSTALL_SOURCE/'references/read_12306.py'
RESOLVER_SHA='77e6a5056f0de303ab8d81b0864999cdbf5d244442eb31d48c65ce49f4981d9d'
RESOLVER_BYTES=21051
RESOLVER_NONCE='a08bcaaa2480f0aafcdaa0d5ac6c315a'
RESOLVER_RECORDS={
    'worker':('result.json',8835,'7ec1d8756cefd536a04d3459041dd302b49bc0e50047c8ddf1f83418bc444abb'),
    'stage':('stage-result.json',1581,'a1b9008ac0dcc86d7b5e2bb51d65e92ee2a82ffe369d3533101c2ed36f93cd12')}
RUNTIME_FILES={'owned_inspect.py','ticket_task_context.py','INPUTS.json'}
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
             'EXACT_ACTUAL_TICKET_READ_ONLY_RESOLVER_REQUIRED')
    need(stage['worker_result']=={'path':str(RESOLVER_ROOT/'result.json'),
         'bytes':RESOLVER_RECORDS['worker'][1],'sha256':RESOLVER_RECORDS['worker'][2]} and
         stage['worker_returncode']==0,'ACTUAL_TICKET_RESOLVER_PARENT_CHAIN_REQUIRED')
    launcher=worker['launcher_resolution']
    need(launcher['component']==COMPONENT and launcher['package']==PACKAGE and
         launcher['user']==0 and launcher['fallback_used'] is False and launcher['launch_performed'] is False and
         launcher['later_launch_requires_new_current_binding'] is True and
         worker['package_read_commands_completed']==5 and worker['UI_actions']==0,
         'ACTUAL_TICKET_RESOLVER_EXACT_COMPONENT_REQUIRED')
    need(worker['metadata_before']==worker['metadata_after']=={'package':PACKAGE,'uid':UID,'user':0,'version_code':275} and
         worker['actual_package_UID_version_APK_chain_stable'] is True and
         worker['Main_before']==worker['Main_after']==stage['Main_before']==stage['Main_after'] and
         len(worker['artifacts'])==1 and worker['total_apk_bytes']==150377492 and
         worker['artifacts'][0]['sha256']=='c7e56101e5753002bba220ce40d07b00d4bc822e1eeef12bbe36ec9e2f8e272d',
         'ACTUAL_TICKET_RESOLVER_SCOPE_STABILITY_REQUIRED')
    observations=worker['command_observations']
    need(len(observations)==5 and all(row['index']==i+1 and row['returncode']==0 and row['joined'] is True and
         row['host_timed_out'] is False and row['first_error'] is None and row['secondary_errors']==[] and
         row['recorder_errors']==[] for i,row in enumerate(observations)),
         'FIVE_ORIGINAL_JOINED_READ_ONLY_COMMANDS_REQUIRED')
    need(all(worker[k] is True for k in ('final_Main_guard_passed','held_binding_released','action_lock_released'))
         and stage['source_unchanged'] is True,'ACTUAL_TICKET_RESOLVER_RETIRED_REQUIRED')
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
         helper['protocol']=='pocket4-owned-ticket-qa-v1' and helper['op']=='state' and
         helper['ok'] is True and helper['ui_automation_connected'] is False,
         'ACTUAL_NO_AUTOMATION_STATE_REQUIRED')
    need(w['target_before']==w['target_after'] and
         w['Main_before_lock']==w['Main_before']==w['Main_after']==c['Main_before']==c['Main_after']==s['Main_before']==s['Main_after'],
         'ACTUAL_INSTALL_MAIN_OR_TARGET_CHAIN')
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
    need(type(HELPER_UID) is int and 10000<=HELPER_UID<100000 and isinstance(INSTALLED,dict) and
         isinstance(STATE_WIRE,str) and re.fullmatch('[0-9a-f]{64}',STATE_WIRE) and
         isinstance(PRIOR['worker'],tuple),'ACTUAL_TICKET_INSTALL_BINDING_NOT_READY')
    manifest=verify_source(expected)
    util=load(INSTALL_SOURCE/'install_state.py',UTIL_SHA,'ticket_qualified_install_primitives',UTIL_BYTES)
    install_manifest=util.verify_source(INSTALL_SOURCE_SHA)
    prior={k:json.loads(read(INSTALL_ROOT/v[0],expected=v[2],size=v[1])) for k,v in PRIOR.items()}
    install_observation=actual_install(prior)
    reader=load(RESOLVER_SOURCE,RESOLVER_SHA,'ticket_qualified_launcher_reference',RESOLVER_BYTES)
    records={k:json.loads(read(RESOLVER_ROOT/v[0],expected=v[2],size=v[1])) for k,v in RESOLVER_RECORDS.items()}
    actual_component=actual_resolver(records,INSTALLED)
    adapter,qa,proof,apk=util.qualified_inputs();del apk
    adapter.validate_plan(PLAN,qa)
    need(qa.PACKAGE==PACKAGE and qa.UID==UID and qa.SELF==SELF and adapter.SELF==SELF,
         'DEDICATED_TICKET_HELPER_SOURCE_REQUIRED')
    values=[NONCE,*PLAN['nonces'].values()]
    need(len(values)==len(set(values))==4 and all(re.fullmatch('[0-9a-f]{32}',v) for v in values),
         'EXACT_NEW_FLOW_AND_THREE_HELPER_NONCES')
    inputs=json.loads(read(HERE/'INPUTS.json',65536))
    need(inputs['nonce']==NONCE and inputs['component']==COMPONENT and inputs['installed_helper']==INSTALLED
         and inputs['resolver_records']=={k:{'relative_path':v[0],'bytes':v[1],'sha256':v[2]} for k,v in RESOLVER_RECORDS.items()},
         'EXACT_RUNTIME_INPUT_RECORD_REQUIRED')
    # Interface-only binding for the unchanged phase body; no resolver action
    # is run here and the prior five-command receipt has no helper assertion.
    resolver=types.SimpleNamespace(INSTALL_SOURCE=INSTALL_SOURCE,INSTALL_SOURCE_SHA=INSTALL_SOURCE_SHA,
        CONTEXT_SHA=CONTEXT_SHA,TRANSPORT_SHA=TRANSPORT_SHA,RESOLVE=reader.RESOLVE,component=reader.component,
        INSTALLED=INSTALLED)
    return types.SimpleNamespace(manifest=manifest,resolver=resolver,util=util,ref=util.references(),
        install_manifest=install_manifest,install=install_observation,resolution=actual_component,
        adapter=adapter,qa=qa,proof=proof,installed=INSTALLED)


def scope_record(q,expected):
    return {'package':PACKAGE,'component':COMPONENT,'uid':UID,'user':0,'nonce':NONCE,
        'epoch_sha256':q.ref.EPOCH,'activation_sha256':q.ref.ACTIVATION_SHA,'verified_sha256':q.ref.VERIFIED_SHA,
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


def assessment_summary(q,step,sequence):
    """No raw UI text, node list, screenshots or recommendations in the result."""
    result={}
    for phase,nonce in PLAN['nonces'].items():
        path=step/(nonce+'.assessment.json');raw=read(path);value=json.loads(raw);helper=value['helper']
        need(helper['nonce']==nonce and helper['self_uid']==HELPER_UID and
             helper['op']==('inspect' if phase=='inspect' else 'state') and
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
        result[phase]=row
    return result


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
            'automatic_retry':False,'mutation':phase in ('launch','cleanup'),'request':PLAN if phase=='inspect' else None})
        context=u.module(q.resolver.INSTALL_SOURCE/'ticket_context.py',q.resolver.CONTEXT_SHA,'amazon_exact_artifact_context')
        transport=u.module(q.resolver.INSTALL_SOURCE/'ticket_transport.py',q.resolver.TRANSPORT_SHA,'amazon_exact_transport')
        task_module=load(HERE/'ticket_task_context.py',q.manifest['files']['ticket_task_context.py']['sha256'],'amazon_task_context')
        shared=u.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,'amazon_task_admission_contract')
        contract=shared.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
        recorder=contract.load('recorder.py','amazon_task_admission_recorder')
        activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
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
            transport,result,began+PHASE_SECONDS[phase],phase,q.qa,PLAN,q.resolver.RESOLVE,scope_record(q,expected))
        reference=json.loads(u.read(q.resolver.INSTALL_SOURCE/'target-artifact-reference.json',expected=
            q.install_manifest['files']['target-artifact-reference.json']['sha256']))
        reader=u.module(q.resolver.INSTALL_SOURCE/'references/read_12306.py',u.READER_SHA,'amazon_artifact_parser')
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
            current='state_inspect_state';result['sequence']=session.sequence(json.loads(json.dumps(PLAN)))
            seq=result['sequence']
            need(seq['installed_before']==seq['installed_after']==q.installed and
                 seq['after_state_completed'] is True and seq['restoration_qualified'] is True and
                 seq['foreground_before']==seq['foreground_after'],'EXACT_READ_ONLY_INSPECTION_SCOPE_REQUIRED')
            result['assessments']=assessment_summary(q,step,seq)
            result['inspection_completed']=True
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
            need(flow.policy.counts=={'target_uid':2,'target_path':2,'helper_uid':4,'helper_path':4,
                'stacks':2,'instrument':3,'foreground':3} and flow.command_index==17 and
                flow.policy.used_nonces==set(PLAN['nonces'].values()) and flow.action_attempted is False,
                'EXACT_READ_ONLY_INSPECTION_COMMAND_COUNTS_REQUIRED')
        result['ok']=True
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
         value['target_FD_cleanup']['held_APK_FDs_closed']==1 and value['target_before']==value['target_after'] and
         value['helper_before']==value['helper_after'] and value['source_and_artifact_unchanged'] is True,
         'EXACT_SUCCESSFUL_DURABLE_AMAZON_PHASE:'+phase)
    if phase!='cleanup':need(value['action_lock_released'] is True,'PHASE_ACTION_LOCK_RELEASE')
    if phase=='launch':need(value['launch']['native_launch_acknowledged'] is True,'ACTUAL_LAUNCH_ACK')
    if phase=='inspect':
        need(value['inspection_completed'] is True and value['sequence']['restoration_qualified'] is True
             and value['sequence']['after_state_completed'] is True,'ACTUAL_INSPECT_AND_RESTORATION_REQUIRED')
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
        activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
        epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'amazon_coordinator_epoch')
        guard=lambda:ref.main_guard(activation,epoch)
        result['Main_before']=guard()
        FLOW.mkdir(mode=0o700)
        ref.write_new(FLOW/'scope.json',scope_record(q,expected))
        ref.write_new(FLOW/'activation.json',ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
        ref.write_new(FLOW/'activation-verified.json',ref.read(ref.VERIFIED,expected=ref.VERIFIED_SHA))
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
        result['assessments']=inspection['assessments']
        result['foreground']=inspection['sequence']['foreground_after']
        result['restoration']=inspection['sequence']['accessibility_restoration']
        result['read_only_inspection_completed']=True
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
        'helper_uid':HELPER_UID,'maximum_native_launches':1,'new_helper_operations':['state','inspect','state'],
        'clicks':0,'text_actions':0,'screenshots':0,'audio':0,'device_calls':0,'submitted':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
