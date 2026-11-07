#!/usr/bin/env python3
"""Resolve the current Amazon launcher with the already qualified held context.

Only nine fixed read-only package commands are admitted. The exact actual
Amazon QA install is consumed, never replayed. No launch, instrumentation,
UiAutomation connection, screenshot, legacy helper or package mutation.
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

ROOT = Path('/home/alex/work/pocket4-amazon-launcher-resolve-readonly-01')
SOURCE_PATH = ROOT/'source/resolve_amazon.py'
NONCE = 'def3447572e718bc263b37bd39393b90'
PACKAGE = 'com.amazon.mShop.android.shopping'
SELF = 'org.droidloom.qa.amazon.r1'
HELPER_UID = 10175
INSTALL_ROOT = Path('/home/alex/work/pocket4-owned-amazon-qa-r1-install-state-01')
INSTALL_SOURCE = INSTALL_ROOT/'source'
INSTALL_SOURCE_SHA = '9179d58761fbf41c04c1a32c4398c9d7a7a7b36add5bf75f8ec89e189a4ed7cf'
UTIL_SHA = '8036635bac509beac9f510534565721ab82f3e3b3f9574e47c5074558afde672'
UTIL_BYTES = 32646
CONTEXT_SHA = '59e4aac802aba1ac90800929e38dafd6455425d7fc97425b7ca640658d7934c1'
TRANSPORT_SHA = '7fd7cce15b902aa41f9abd32e5a64f2d0d26799e86afbe2c80984bdeccf22ed2'
REFERENCE = INSTALL_SOURCE/'references/readonly_r3_coordinator.py'
REFERENCE_SHA = 'e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd'
STATE_NONCE = '918bf87b0f3f08c62ab630a96b2bfcdc'
STATE_WIRE = 'b271e86f7a9307be448e3145de16a16606894b864124f13020d375b47a89be21'
PRIOR = {
    'coordinator':('result.json',3091,'2dadd1044b847c7966d5c01c04a8962c401dd3ff60388f3b4ea4e6d2367f8e30'),
    'stage':('stage-result.json',1617,'633c0cc3dfaae3f434216956cf4046471222377d5a312f79e02eebd6d6e22def'),
    'worker':('worker/result.json',13459,'cd9cb834229c299c065d3934b0e5ed60d8af7e82369e6fb7087e533f4d4a6d2d'),
}
INSTALLED = {
    'package':SELF,'uid':HELPER_UID,
    'base_apk':'/data/app/~~GFIKD7lsOsvDFpGij6NI2w==/org.droidloom.qa.amazon.r1-yITq1-IsucEPX6hgN-6TqA==/base.apk',
    'apk_sha256':'f3a7bb2133049022a7d622d35ea2db3390d2804e51ebe344b1d5adcde4437118',
    'bytes':24720,
    'held_file':{'device':1811,'inode':787880,'uid':1000,'gid':1000,'mode':33188,
        'nlink':1,'bytes':24720,'mtime_ns':1793875272105926629},
    'signer_bound_by_exact_signed_apk_bytes':'1f63759487a0b04e8da9b4088c11dbac8140bf63cb2d64d91460e2525924f424',
}
# Same MAIN/LAUNCHER query as the pinned original backend, with user 0
# explicit. There is no applications-list fallback and no activity start.
RESOLVE = ['/system/bin/cmd','package','resolve-activity','--brief','--user','0',
    '-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER',PACKAGE]
WORK_SECONDS = 175


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=131072, expected=None, size=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        first=os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and
             0<=first.st_size<=maximum,'FIXED_INPUT_SHAPE_OR_BOUND: '+str(path))
        raw=bytearray()
        while len(raw)<=maximum:
            part=os.read(fd,min(65536,maximum+1-len(raw)))
            if not part:break
            raw.extend(part)
        last=os.fstat(fd)
        fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        need(len(raw)==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),
             'FIXED_INPUT_CHANGED: '+str(path))
        raw=bytes(raw)
        need(expected is None or sha(raw)==expected,'FIXED_INPUT_SHA_CHANGED: '+str(path))
        need(size is None or len(raw)==size,'FIXED_INPUT_SIZE_CHANGED: '+str(path))
        return raw
    finally:
        os.close(fd)


def load(path, expected, name, size=None):
    raw=read(path,expected=expected,size=size)
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


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
         helper['protocol']=='pocket4-owned-amazon-qa-v1' and helper['op']=='state' and
         helper['ok'] is True and helper['ui_automation_connected'] is False,
         'ACTUAL_NO_AUTOMATION_STATE_REQUIRED')
    need(w['target_before']==w['target_after'] and
         w['Main_before_lock']==w['Main_before']==w['Main_after']==c['Main_before']==c['Main_after']==s['Main_before']==s['Main_after'],
         'ACTUAL_INSTALL_MAIN_OR_TARGET_CHAIN')
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


def component(raw):
    need(isinstance(raw,bytes) and 0<len(raw)<=4096,'RESOLVE_OUTPUT_BOUND')
    text=raw.decode('ascii','strict')
    need(text.endswith('\n') and '\x00' not in text and
         all(c=='\n' or 32<=ord(c)<127 for c in text),'RESOLVE_OUTPUT_TEXT_SHAPE')
    lines=text.splitlines()
    need(1<=len(lines)<=16,'RESOLVE_OUTPUT_LINE_BOUND')
    candidates=[line.strip() for line in lines if
        re.fullmatch(r'[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+',line.strip())]
    need(len(candidates)==1,'ONE_CURRENT_LAUNCHER_COMPONENT_REQUIRED')
    value=candidates[0]
    need(re.fullmatch(re.escape(PACKAGE)+r'/(?:\.[A-Za-z_][A-Za-z0-9_.$]*|[A-Za-z_][A-Za-z0-9_.$]*)',value)
         is not None,'LAUNCHER_MUST_BELONG_TO_EXACT_AMAZON_PACKAGE')
    return {'package':PACKAGE,'user':0,'component':value,
        'query_action':'android.intent.action.MAIN','query_category':'android.intent.category.LAUNCHER',
        'resolve_stdout_sha256':sha(raw),'fallback_used':False,
        'launch_performed':False,'later_launch_requires_new_current_binding':True}


def command_plan(context):
    own_uid=['/system/bin/cmd','package','list','packages','-U','--user','0',SELF]
    own_path=['/system/bin/cmd','package','path','--user','0',SELF]
    return [(context.LIST,15,False),(context.PATHS,15,False),(own_uid,8,False),
        (own_path,8,False),(RESOLVE,15,False),(own_uid,8,False),(own_path,8,False),
        (context.PATHS,15,False),(context.LIST,15,False)]


def execute(expected):
    need(os.getuid()==os.geteuid()==0 and Path(__file__)==SOURCE_PATH,
         'EXACT_ROOT_READ_ONLY_SOURCE_REQUIRED')
    need(isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected),'EXTERNAL_SOURCE_PIN_REQUIRED')
    util=load(INSTALL_SOURCE/'install_state.py',UTIL_SHA,'amazon_installed_source_primitives',UTIL_BYTES)
    ref=util.references()
    manifest=util.verify_source(INSTALL_SOURCE_SHA)
    def verify(value):
        need(value==expected,'CURRENT_RESOLVER_SOURCE_PIN_REQUIRED')
        read(SOURCE_PATH,32768,expected)
        util.verify_source(INSTALL_SOURCE_SHA)
    def verify_runtime(value):
        need(value==INSTALL_SOURCE_SHA,'EXACT_REUSED_AMAZON_CONTEXT_MANIFEST_REQUIRED')
        verify(expected)
    verify(expected)
    step=ROOT/'evidence';step.mkdir(mode=0o700)
    ref.write_new(ROOT/'once.claim.json',{'nonce':NONCE,'source_sha256':expected,'automatic_retry':False})
    result={'schema':1,'ok':False,'error':None,'secondary_errors':[],
        'nonce':NONCE,'source_sha256':expected,'package':PACKAGE,'helper_package':SELF,
        'Android_UI_actions':0,'App_launches':0,'instrumentation_calls':0,'permission_grants':0,
        'settings_writes':0,'package_mutations':0,'audio_actions':0,'old_v2_helper_called':False,
        'Bili_Flow_instantiated':False,'automatic_retry':False,'whole_app_production_ready':False}
    ctx=artifacts=guard=before_resources=None;lock=None;phase='actual_install_binding'
    began=time.monotonic()
    try:
        before_resources=util.prepare_owned_limits();result['owned_before']=before_resources
        rows={k:json.loads(read(INSTALL_ROOT/v[0],expected=v[2],size=v[1])) for k,v in PRIOR.items()}
        result['actual_install']=actual_install(rows)
        adapter,qa,proof,apk=util.qualified_inputs();del apk
        result['build']=proof
        context=util.module(INSTALL_SOURCE/'amazon_context.py',CONTEXT_SHA,'amazon_qualified_context')
        transport=util.module(INSTALL_SOURCE/'amazon_transport.py',TRANSPORT_SHA,'amazon_qualified_transport')
        reader=util.module(INSTALL_SOURCE/'references/read_amazon.py',util.READER_SHA,'amazon_metadata_parser')
        activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
        epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'amazon_resolve_epoch')
        guard=lambda:ref.main_guard(activation,epoch)
        result['Main_before_lock']=guard()
        shared=util.module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,'amazon_resolve_contract')
        contract=shared.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
        recorder=contract.load('recorder.py','amazon_resolve_actual_command')
        phase='action_lock';result['action_lock_admission']={}
        lock=util.acquire_action_lock(recorder.ACTION_LOCK,result['action_lock_admission']);guard()
        phase='held_Main_binding';plan=command_plan(context)
        ctx,recorder,guard=context.open_context(ref,util,INSTALL_SOURCE_SHA,verify_runtime,INSTALL_SOURCE,step,
            transport,plan,result,began+WORK_SECONDS)
        reference=json.loads(util.read(INSTALL_SOURCE/'target-artifact-reference.json',expected=
            manifest['files']['target-artifact-reference.json']['sha256']))
        artifacts=context.ArtifactSet(ctx,reference,reader)
        phase='target_before';result['target_before']=artifacts.before()
        session=adapter.Session(ctx,recorder,qa,proof,HELPER_UID)
        phase='helper_before';result['helper_before']=session.installed()
        need(result['helper_before']==INSTALLED,'CURRENT_HELPER_DIFFERS_FROM_ACTUAL_INSTALL')
        phase='single_read_only_resolution'
        raw,observation=util.command(ctx,RESOLVE,15)
        result['resolve_command']=observation
        result['launcher']=component(raw)
        phase='helper_after';result['helper_after']=session.installed()
        need(result['helper_after']==result['helper_before'],'HELPER_CHANGED_DURING_RESOLUTION')
        phase='target_after';result['target_after']=artifacts.after()
        need(result['target_after']==result['target_before'],'TARGET_CHANGED_DURING_RESOLUTION')
        need(ctx.command_index==ctx.next_command==len(plan)==9 and ctx.action_attempted is False,
             'NINE_JOINED_READ_ONLY_COMMANDS_REQUIRED')
        result['exact_command_count']=9;result['ok']=True
    except BaseException as error:
        util.remember(result,phase,error)
    finally:
        if artifacts is not None:
            try:
                if len(artifacts.records)==3 and 'target_after' not in result:
                    result['failed_scope_files_revalidated']=artifacts.revalidate_files()
            except BaseException as error:util.remember(result,'failed_scope_revalidation',error)
            try:result['target_FD_cleanup']=artifacts.close()
            except BaseException as error:util.remember(result,'target_FD_cleanup',error)
        if ctx is not None:
            try:ctx.guard();result['final_Main_guard_passed']=True
            except BaseException as error:util.remember(result,'final_Main_guard',error)
            try:ctx.close();result['held_binding_released']=True
            except BaseException as error:util.remember(result,'held_binding_release',error)
        if guard is not None:
            try:
                result['Main_after']=guard()
                need(result.get('Main_before_lock')==result['Main_after'],'MAIN_BEFORE_AFTER_DIFFER')
            except BaseException as error:util.remember(result,'independent_final_Main',error)
        if lock is not None:
            try:os.close(lock);result['action_lock_released']=True
            except BaseException as error:util.remember(result,'action_lock_release',error)
        try:verify(expected);util.qualified_inputs();result['source_and_build_unchanged']=True
        except BaseException as error:util.remember(result,'final_source_and_build',error)
        if before_resources is not None:
            try:
                result['owned_after']=util.owned_resources()
                util.resources_qualified(before_resources,result['owned_after'])
            except BaseException as error:util.remember(result,'final_owned_resources',error)
    result['action_attempted']=bool(ctx is not None and ctx.action_attempted)
    result['outcome_unknown']=bool(result['action_attempted'] and not result['ok'])
    result['seconds']=time.monotonic()-began
    try:pin=ref.write_new(ROOT/'result.json',result)
    except BaseException as error:util.remember(result,'result_write',error);pin=None
    print(json.dumps({'result':pin,'worker':result},ensure_ascii=False,sort_keys=True,separators=(',',':')),flush=True)
    return 0 if result['ok'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-once',action='store_true')
    parser.add_argument('--source-sha256')
    args=parser.parse_args()
    if not args.execute_once:
        print(json.dumps({'state':'PLAN_ONLY','package':PACKAGE,'helper_uid':HELPER_UID,'nonce':NONCE,
            'App_launches':0,'instrumentation_calls':0,'submission':False}))
        return 0
    return execute(args.source_sha256)


if __name__=='__main__':
    raise SystemExit(main())
