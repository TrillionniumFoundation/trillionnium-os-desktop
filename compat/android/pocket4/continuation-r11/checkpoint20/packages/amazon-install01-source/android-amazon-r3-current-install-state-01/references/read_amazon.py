#!/usr/bin/env python3
"""One fixed Amazon metadata read, with the qualified held Main primitives.

No App launch, instrumentation, v2 helper, permission or settings operation.
The original Bili Flow/BoundArun business scope is never instantiated or patched.
Only its pinned command-observation function and shared held-entry primitives
are reused. Default PLAN performs no file or device read.
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

ROOT = Path('/home/alex/work/pocket4-amazon-artifact-readonly-01')
SOURCE_PATH = ROOT/'source/read_amazon.py'
NONCE = '42110205266d417c33e33607204a5d8d'
PACKAGE = 'com.amazon.mShop.android.shopping'
USER = 0
HISTORICAL_VERSION = 1243240206
INSTALLED_SOURCE = Path('/home/alex/work/pocket4-owned-bili-qa-r5-install-state-03/source')
INSTALL_SHA = '6614f2eb92ffd2a339c733d6fc58262fbb918d3e9c8eb15cfca3fa275b8bd329'
INSTALL_BYTES = 34852
REFERENCE_SHA = 'e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd'
RECORDER_ROOT = INSTALLED_SOURCE/'recorder-r4'
RECORDER_MANIFEST = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
SOURCE_CONTRACT_SHA = '51c2b3dd7df80a8fcd4881eb7216f7292db77d39c01920f10feb650824919a7d'
LIST = ['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',PACKAGE]
PATHS = ['/system/bin/cmd','package','path','--user','0',PACKAGE]
COMMANDS = [LIST, PATHS, PATHS, LIST]
FILE_LIMIT = 256 * 1024 * 1024
TOTAL_LIMIT = 512 * 1024 * 1024
HASH_SECONDS = 45
FILE_COUNT = 16
WORK_SECONDS = 140


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=131072, expected=None, size=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        first=os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and 0<=first.st_size<=maximum,
             'FIXED_INPUT_SHAPE_OR_BOUND')
        data=bytearray()
        while len(data)<=maximum:
            block=os.read(fd,min(65536,maximum+1-len(data)))
            if not block:break
            data.extend(block)
        last=os.fstat(fd)
        keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        need(len(data)==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),
             'FIXED_INPUT_CHANGED')
        raw=bytes(data)
        need(expected is None or sha(raw)==expected,'FIXED_INPUT_SHA_CHANGED')
        need(size is None or len(raw)==size,'FIXED_INPUT_SIZE_CHANGED')
        return raw
    finally:os.close(fd)


def load(path, expected, name, size=None):
    raw=read(path,expected=expected,size=size)
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__)
    return value


def error_row(phase, error):
    value={'phase':phase,'type':type(error).__name__,'message':str(error)}
    if isinstance(error,OSError):value['errno']=error.errno
    for key in ('command_observation','__notes__'):
        if hasattr(error,key):value[key]=getattr(error,key)
    return value


def remember(result, phase, error):
    row=error_row(phase,error)
    if result['error'] is None:result['error']=row
    else:result['secondary_errors'].append(row)
    result['ok']=False


def metadata(raw):
    match=re.fullmatch(re.escape('package:'+PACKAGE)+r' versionCode:([0-9]+) uid:([0-9]+)\n',
                       raw.decode('utf-8','strict'))
    need(match is not None,'ONE_EXACT_AMAZON_USER0_METADATA_ROW_REQUIRED')
    version,uid=map(int,match.groups())
    need(0<version<2**63 and 10000<=uid<100000,'AMAZON_METADATA_RANGE')
    return {'package':PACKAGE,'user':USER,'uid':uid,'version_code':version}


def apk_paths(raw):
    text=raw.decode('utf-8','strict')
    need(text.endswith('\n') and len(raw)<=16384,'AMAZON_PATH_OUTPUT_BOUND')
    lines=text.splitlines()
    need(1<=len(lines)<=FILE_COUNT and all(x.startswith('package:') for x in lines),
         'AMAZON_APK_PATH_ROWS_REQUIRED')
    paths=[x[len('package:'):] for x in lines]
    need(len(set(paths))==len(paths),'DUPLICATE_APK_PATH')
    parents=set()
    for path in paths:
        need(isinstance(path,str) and '\x00' not in path and len(path.encode())<=4096,
             'AMAZON_PATH_SHAPE')
        parts=Path(path).parts
        need(len(parts)==6 and parts[:3]==('/','data','app') and
             re.fullmatch(r'~~[A-Za-z0-9_=-]+',parts[3]) and
             re.fullmatch(re.escape(PACKAGE)+r'-[A-Za-z0-9_=-]+',parts[4]) and
             (parts[5]=='base.apk' or re.fullmatch(r'split_[A-Za-z0-9_.-]+\.apk',parts[5])),
             'ONLY_EXACT_AMAZON_INSTALL_DIRECTORY_APKS_MAY_BE_READ')
        parents.add(str(Path(path).parent))
    need(len(parents)==1 and sum(Path(x).name=='base.apk' for x in paths)==1,
         'ONE_AMAZON_BASE_AND_ONE_INSTALL_DIRECTORY_REQUIRED')
    return sorted(paths)


def identity(fd):
    s=os.fstat(fd)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,
            'nlink':s.st_nlink,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}


class Context:
    """Only the exact pinned Flow.command method is used, never Flow.init/launch."""
    def __init__(self, recorder, contract, target, guard, result):
        self.recorder=recorder;self.contract=contract;self.target=target;self.check_main=guard
        self.result=result;self.step=ROOT/'evidence';self.command_index=0
        self.action_attempted=False;self.binding=types.SimpleNamespace(target=target)
        self.observations=[]

    def guard(self, attempted=False):
        need(attempted is False and self.action_attempted is False,'READ_ONLY_ACTION_SCOPE_CHANGED')
        self.check_main();self.target.verify()

    def command(self, arguments, environment):
        need(self.command_index<len(COMMANDS) and arguments==COMMANDS[self.command_index],
             'ONLY_FOUR_ORDERED_FIXED_READ_ONLY_COMMANDS_ALLOWED')
        self.guard()
        expected_index=self.command_index+1
        command=['/system/bin/env','-i']
        command += [key+'='+environment[key] for key in sorted(environment)]
        command += ['/system/xbin/su','2000','/system/bin/timeout','-k','2','10',*arguments]
        manager=None;entered=False;completed=None;primary=None;secondary=[]
        def fail(phase,error):
            nonlocal primary
            if primary is None:primary=error
            else:secondary.append(error_row(phase,error))
        try:
            manager=self.target.entry(command);argv,descriptors=manager.__enter__();entered=True
            need(len(descriptors)==7 and len(set(descriptors))==7 and
                 all(type(fd) is int and fd>=3 for fd in descriptors),'HELD_AUTHORITY_SET_DIFFERS')
            expected=[str(self.target.helper_path),'--parent-pid='+str(os.getpid()),
                      '--root-fd='+str(descriptors[0])]
            expected += ['--'+name+'-fd='+str(fd) for name,fd in
                         zip(('mnt','pid','uts','ipc','net','cgroup'),descriptors[1:])]
            need(list(argv)==expected+['--',*command],'EXACT_R4_HELD_PREFIX_AND_COMMAND_REQUIRED')
            completed=self.recorder.Flow.command(self,argv,15,mutation=False,label='Android command',
                pass_fds=tuple(descriptors),check=False,
                host_env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8'})
            need(completed.recorder_spawned and completed.recorder_joined and
                 not completed.host_timed_out and completed.returncode==0 and
                 completed.recorder_errors==[],'EXACT_JOINED_READ_ONLY_COMMAND_REQUIRED')
            need(len(completed.stdout)<=16384 and completed.stderr==b'',
                 'ONE_PACKAGE_COMMAND_OUTPUT_BOUND_OR_STDERR')
        except BaseException as error:fail('read_command',error)
        finally:
            # Flow.command has already saved the first command observation.
            # Release and post-guard must run independently and cannot erase it.
            if entered:
                try:manager.__exit__(None,None,None)
                except BaseException as error:fail('entry_release',error)
            try:self.guard()
            except BaseException as error:fail('post_command_Main_guard',error)
            row={'index':self.command_index,'argv':arguments,'operation':'package_metadata_read',
                 'Android_UI_action':False,'entry_entered':entered,
                 'first_error':error_row('command',primary) if primary else None,
                 'secondary_errors':secondary}
            if completed is not None:
                row.update(returncode=completed.returncode,joined=completed.recorder_joined,
                           spawned=completed.recorder_spawned,host_timed_out=completed.host_timed_out,
                           recorder_errors=completed.recorder_errors,
                           stdout_sha256=sha(completed.stdout),stdout_bytes=len(completed.stdout),
                           stderr_sha256=sha(completed.stderr),stderr_bytes=len(completed.stderr))
            row['command_receipt_path']=str(self.step/('command-%03d.result.json'%expected_index))
            self.observations.append(row)
        if primary is not None:
            for row in secondary:primary.add_note(json.dumps(row,sort_keys=True))
            raise primary
        return completed.stdout


def execute(source_sha):
    need(os.getuid()==os.geteuid()==0,'ROOT_FIXED_READ_ONLY_REQUIRED')
    need(Path(__file__).resolve()==SOURCE_PATH and re.fullmatch('[0-9a-f]{64}',source_sha),
         'EXACT_NEW_SOURCE_PATH_AND_EXTERNAL_PIN_REQUIRED')
    read(SOURCE_PATH,expected=source_sha)
    need(ROOT.is_dir() and not (ROOT/'claim.json').exists(),'FRESH_SINGLE_ATTEMPT_ROOT_REQUIRED')
    reference=load(INSTALLED_SOURCE/'references/readonly_r3_coordinator.py',REFERENCE_SHA,'amazon_main_reference')
    root_stat=ROOT.lstat()
    need(stat.S_ISDIR(root_stat.st_mode) and root_stat.st_uid==0 and not root_stat.st_mode&0o077,
         'ROOT_PRIVATE_NEW_EVIDENCE_DIRECTORY_REQUIRED')
    reference.write_new(ROOT/'claim.json',{'schema':1,'nonce':NONCE,'package':PACKAGE,
                                         'source_sha256':source_sha,'automatic_retry':False})
    (ROOT/'evidence').mkdir(mode=0o700)
    result={'schema':1,'scope':'one exact Amazon user0 installed artifact metadata read',
            'nonce':NONCE,'package':PACKAGE,'source_sha256':source_sha,'ok':False,
            'error':None,'secondary_errors':[],'UI_actions':0,'App_launches':0,
            'instrumentation_calls':0,'permission_grants':0,'settings_writes':0,
            'old_v2_helper_called':False,'Bili_scope_modified':False,'automatic_retry':False,
            'whole_app_production_ready':False,'signer_certificate_independently_verified':False,
            'APK_bytes_exported':False,'current_package_inventory_scanned_or_exported':False}
    target=ctx=None;lock=None;opened=[];phase='source';started=time.monotonic();guard=None
    try:
        source=load(RECORDER_ROOT/'source_contract.py',SOURCE_CONTRACT_SHA,'amazon_shared_source_contract')
        contract=source.SourceContract(RECORDER_ROOT/'source-manifest.json',RECORDER_MANIFEST)
        recorder=contract.load('recorder.py','amazon_command_reference')
        held=contract.load('references/held_runtime_r5.py','amazon_held_reference')
        binding=contract.load('main_binding.py','amazon_classpath_reference')
        transport=contract.load('bound_android_transport.py','amazon_environment_reference')
        install=load(INSTALLED_SOURCE/'install_state.py',INSTALL_SHA,'amazon_lock_reference',INSTALL_BYTES)
        activation=json.loads(reference.read(reference.ACTIVATION,expected=reference.ACTIVATION_SHA))
        verified=json.loads(reference.read(reference.VERIFIED,expected=reference.VERIFIED_SHA))
        need(activation['main_deployed'] is True and verified['main_deployed'] is True and
             verified['framework_epoch_sha256']==reference.EPOCH,'ACTIVATION_NOT_VERIFIED')
        epoch=reference.module(reference.read(reference.EPOCH_SOURCE,expected=reference.EPOCH_SOURCE_SHA),
                               reference.EPOCH_SOURCE,'amazon_epoch_reference')
        def fixed_guard(check_deadline=True):
            if check_deadline:
                need(time.monotonic()-started<WORK_SECONDS,'WHOLE_READ_DEADLINE')
            contract.verify();read(SOURCE_PATH,expected=source_sha)
            read(INSTALLED_SOURCE/'references/readonly_r3_coordinator.py',expected=REFERENCE_SHA)
            read(INSTALLED_SOURCE/'install_state.py',expected=INSTALL_SHA,size=INSTALL_BYTES)
            reference.read(recorder.APP,expected=recorder.APP_SHA)
            read(source.HELPER_PATH,maximum=source.HELPER_BYTES,
                 expected=source.HELPER_SHA,size=source.HELPER_BYTES)
            return reference.main_guard(activation,epoch)
        guard=fixed_guard
        result['Main_before']=guard()
        result['shared_helper']=source.verify_shared_helper()
        result['action_lock']={};phase='action_lock_admission'
        lock=install.acquire_action_lock(recorder.ACTION_LOCK,result['action_lock'])
        guard()
        expected=activation['framework_epoch']['binding']['processes']['init']
        phase='held_Main_binding'
        proc=os.open('/proc/'+str(expected['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:actual=held.proc_identity_at(proc,expected['host_pid'],time.monotonic()+3)
        finally:os.close(proc)
        need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')
        target=held.HeldTarget(actual,source.HELPER_PATH,source.HELPER_SHA)
        guard()
        app=load(Path(recorder.APP),recorder.APP_SHA,'amazon_existing_discovery_reference',37574)
        init,discovered,status=app.discover()
        need(init==expected['host_pid'] and status['host_pid']==activation['status']['host_pid'],
             'FIXED_MAIN_DISCOVERY_CHANGED')
        values,classpath=binding.main_classpaths(held,target,activation['framework_epoch'],epoch,guard)
        need(all(discovered.get(key)==value for key,value in values.items()),'CLASSPATH_DISCOVERY_CHANGED')
        environment=transport.environment_values(discovered)
        reference.write_new(ROOT/'held-main-binding.json',{'target':target.record,'classpath':classpath,
                             'shared_helper':result['shared_helper'],'package_scope':PACKAGE})
        ctx=Context(recorder,contract,target,guard,result)
        phase='before_package_metadata';before=metadata(ctx.command(LIST,environment))
        result['metadata_before']=before
        need(activation['packages'].get(PACKAGE)==before['uid'],'AMAZON_UID_CHANGED_FROM_FIXED_ACTIVATION')
        result['historical_version_code']=HISTORICAL_VERSION
        result['historical_version_still_matches']=before['version_code']==HISTORICAL_VERSION
        phase='before_package_paths';paths=apk_paths(ctx.command(PATHS,environment));result['apk_paths_before']=paths
        total=0;deadline=min(started+WORK_SECONDS,time.monotonic()+HASH_SECONDS);artifacts=[]
        phase='held_APK_hash'
        for path in paths:
            need(time.monotonic()<deadline,'APK_STREAM_HASH_DEADLINE')
            fd=target.open_root(path,os.O_RDONLY|os.O_NOFOLLOW);opened.append(fd)
            first=identity(fd)
            need(stat.S_ISREG(first['mode']) and first['nlink']==1 and
                 first['uid']==first['gid']==1000 and not first['mode']&0o022 and
                 0<first['bytes']<=FILE_LIMIT,'AMAZON_INSTALLED_APK_SHAPE_OR_BOUND')
            need(total+first['bytes']<=TOTAL_LIMIT,'AMAZON_APK_TOTAL_BOUND')
            digest=hashlib.sha256();count=0
            while True:
                need(time.monotonic()<deadline,'APK_STREAM_HASH_DEADLINE')
                block=os.read(fd,min(65536,first['bytes']+1-count))
                if not block:break
                count+=len(block);need(count<=first['bytes'],'APK_GREW_DURING_HASH');digest.update(block)
            need(count==first['bytes'] and identity(fd)==first,'APK_CHANGED_DURING_HASH')
            artifacts.append({'path':path,'sha256':digest.hexdigest(),'held_file':first})
            total+=count
        phase='after_package_paths'
        need(apk_paths(ctx.command(PATHS,environment))==paths,'AMAZON_INSTALL_PATHS_CHANGED')
        phase='after_package_metadata';after=metadata(ctx.command(LIST,environment))
        result['metadata_after']=after;need(after==before,'AMAZON_PACKAGE_METADATA_CHANGED')
        phase='held_APK_revalidation'
        for fd,row in zip(opened,artifacts):
            need(identity(fd)==row['held_file'],'HELD_APK_CHANGED_AFTER_PACKAGE_RECHECK')
            again=target.open_root(row['path'],os.O_RDONLY|os.O_NOFOLLOW)
            try:need(identity(again)==row['held_file'],'APK_PATH_NO_LONGER_NAMES_HELD_FILE')
            finally:os.close(again)
        target.verify();guard()
        result.update(artifacts=artifacts,total_apk_bytes=total,actual_package_UID_version_APK_chain_stable=True,
                      package_read_commands_completed=ctx.command_index,ok=True)
    except BaseException as error:remember(result,phase,error)
    finally:
        if ctx is not None:result['command_observations']=ctx.observations
        for fd in reversed(opened):
            try:os.close(fd)
            except BaseException as error:remember(result,'held_APK_fd_close',error)
        if target is not None:
            try:target.close();result['held_binding_released']=True
            except BaseException as error:remember(result,'held_binding_release',error)
        if guard is not None:
            try:
                result['Main_after']=guard(False)
                need(result.get('Main_before')==result['Main_after'],'MAIN_BEFORE_AFTER_DIFFER')
                result['final_Main_guard_passed']=True
            except BaseException as error:remember(result,'final_Main_guard',error)
        if lock is not None:
            try:os.close(lock);result['action_lock_released']=True
            except BaseException as error:remember(result,'action_lock_release',error)
        result['seconds']=time.monotonic()-started
    pin=reference.write_new(ROOT/'result.json',result)
    # This complete bounded result has no raw UI, unrelated package list or APK.
    envelope={'result_file':pin,'result':result}
    output=json.dumps(envelope,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    need(len(output.encode())<=98304,'ONE_PACKAGE_RESULT_BOUND')
    print(output,flush=True)
    return 0 if result['ok'] else 1


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collect-once',action='store_true');p.add_argument('--source-sha256')
    a=p.parse_args(argv)
    if not a.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','package':PACKAGE,'root':str(ROOT),'nonce':NONCE,
                          'ordered_commands':COMMANDS,'Android_UI_actions':0,'remote_actions':0}))
        return 0
    return execute(a.source_sha256)


if __name__=='__main__':raise SystemExit(main())
