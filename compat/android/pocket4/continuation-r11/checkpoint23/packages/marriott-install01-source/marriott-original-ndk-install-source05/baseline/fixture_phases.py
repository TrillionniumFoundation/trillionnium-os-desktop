"""Fixed NDK install / original instrumentation / independent retirement steps.
SOURCE_ONLY. This module deliberately has no dispatchable CLI, future APK,
installed UID, run directory, or nonce. All runtime routes first hit the
unbound contract gate. No commercial App is adopted or made ready by this fixture.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

PACKAGE='com.example.ndk_tests'
FIXED_SOURCE_NAMES={'fixture_contract.py','fixture_context.py','fixture_transport.py',
                    'fixture_phases.py','current_discovery.py'}
PENDING_SOURCE_ROOT=None
PENDING_SOURCE_MANIFEST=None
ACTION_LOCK='/run/lock/android-digitalis-actions.lock'


def need(ok,code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_exact_file(path,limit,pin=None):
    path=str(path)
    need(path.startswith('/') and not path.startswith('//') and '\0' not in path and
         all(x not in ('','.','..') for x in path[1:].split('/')),'EXACT_FILE_PATH_GRAMMAR')
    fds=[]
    first=None
    errors=[]
    deadline=time.monotonic()+10
    try:
        directory=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
        fds.append(directory)
        parts=path[1:].split('/')
        for component in parts[:-1]:
            need(time.monotonic()<deadline,'FIXED_FILE_DEADLINE')
            directory=os.open(component,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                              dir_fd=directory)
            fds.append(directory)
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
        fds.append(fd)
        before=os.fstat(fd)
        keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
             0<=before.st_size<=limit,'FIXED_REGULAR_FILE_BOUND')
        chunks=[]
        count=0
        while True:
            need(time.monotonic()<deadline,'FIXED_FILE_DEADLINE')
            part=os.read(fd,min(65536,limit+1-count))
            if not part:
                break
            count+=len(part)
            need(count<=limit,'FIXED_FILE_GREW')
            chunks.append(part)
        raw=b''.join(chunks)
        after=os.fstat(fd)
        named=os.stat(parts[-1],dir_fd=directory,follow_symlinks=False)
        need(len(raw)==before.st_size and
             all(getattr(x,k)==getattr(before,k) for x in (after,named) for k in keys),
             'FIXED_HELD_NAMED_FILE_CHANGED')
        if pin is not None:
            need(set(pin)=={'bytes','sha256'} and len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],
                 'FIXED_WHOLE_FILE_PIN_CHANGED')
        return raw
    except BaseException as error:
        first=error
        raise
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except BaseException as close_error:
                errors.append(type(close_error).__name__)
        if errors:
            if first is None:
                raise RuntimeError('FIXED_FILE_FD_CLOSE_FAILED')
            first.add_note('FIXED_FILE_FD_CLOSE_FAILED')


class FixedSources:
    """Exactly five local source leaves; not a generic loader or command bridge."""
    def __init__(self):
        need(PENDING_SOURCE_ROOT is not None and PENDING_SOURCE_MANIFEST is not None,
             'SOURCE_ONLY_OWN_ROOT_AND_MANIFEST_UNBOUND')
        self.root=Path(PENDING_SOURCE_ROOT)
        self.pin=PENDING_SOURCE_MANIFEST
        raw=read_exact_file(self.root/'SOURCE_PINS.json',65536,self.pin)
        data=json.loads(raw)
        need(data.get('schema')=='pocket4-original-ndk-fixture-source-v1' and
             set(data.get('files',{}))==FIXED_SOURCE_NAMES,'FIXED_FIVE_SOURCE_SET')
        self.files=data['files']
        self.sha256=self.pin['sha256']
        self.verify()

    def verify(self):
        read_exact_file(self.root/'SOURCE_PINS.json',65536,self.pin)
        for name,pin in self.files.items():
            read_exact_file(self.root/name,131072,pin)

    @staticmethod
    def module(raw,path,name):
        module=types.ModuleType(name)
        module.__file__=str(path)
        exec(compile(raw,str(path),'exec'),module.__dict__)
        return module

    def load(self,name,module_name):
        need(name in FIXED_SOURCE_NAMES,'UNPINNED_FIXTURE_MODULE')
        return self.module(read_exact_file(self.root/name,131072,self.files[name]),
                           self.root/name,module_name)

    @staticmethod
    def fixed_reference(path,size,digest):
        need(str(path)=='/home/alex/work/pocket4-current-host-r6-source-01/source_contract.py' and
             size==11359 and digest=='f92d2598221c5bf65e783df39864879a2056da47f794680668b34df11f97da49',
             'ONLY_EXACT_CURRENT_SOURCE_CONTRACT_REFERENCE')
        return read_exact_file(path,131072,{'bytes':size,'sha256':digest})


def failure(result,phase,error):
    record={'stage':phase,'type':type(error).__name__,'errno':getattr(error,'errno',None)}
    # Exceptions from the new fixed contract are public codes. Other arbitrary
    # exception strings / traceback / Android output remain in private evidence.
    code=str(error)
    if re.fullmatch('[A-Z][A-Z0-9_: ]{0,159}',code):
        record['code']=code
    else:
        record['error_utf8_bytes']=len(code.encode('utf-8'))
        record['error_sha256']=sha(code.encode('utf-8'))
    if result['error'] is None:
        result['error']=record
    else:
        result['secondary_errors'].append(record)
    result['ok']=False


def empty_result(scope,source_pin):
    return {'schema':1,'kind':'pocket4-original-ndk-fixture-'+scope['phase']+'-v1',
        'scope':json.loads(json.dumps(scope,sort_keys=True)),'source_manifest':source_pin,
        'ok':False,'error':None,'secondary_errors':[],'automatic_retry':False,
        'instrumentation_verified':False,'force_stop_completed':False,
        'action_attempted':False,'outcome_unknown':False,'exact_command_count':0,
        'commercial_App_readiness_qualified':False,'Main_deployment_or_restart':False,
        'all_tracked_artifact_FDs_closed':False,'held_binding_released':False,
        'current_Main_after_qualified':False,'runtime_dispatched_by_this_source':False}


def joined_command(context,argv,timeout,mutation=False):
    before=context.command_index
    output=context.android(argv,timeout,mutation=mutation)
    need(context.command_index==before+1,'ONE_ACTUAL_JOINED_COMMAND_REQUIRED')
    stem=context.step/('command-%03d'%context.command_index)
    raw=read_exact_file(str(stem)+'.result.json',65536)
    row=json.loads(raw)
    stderr=read_exact_file(str(stem)+'.stderr',262144)
    need(row.get('returncode')==0 and row.get('spawned') is True and
         row.get('owned_command_joined') is True and row.get('timed_out') is False and
         row.get('error') is None and row.get('errors')==[] and
         row.get('stdout_sha256')==sha(output) and row.get('stderr_sha256')==sha(stderr) and
         stderr==b'','COMPLETE_QUIET_FIXED_COMMAND_REQUIRED')
    return output,{'sequence':context.command_index,'private_result_sha256':sha(raw),
        'stdout_bytes':len(output),'stdout_sha256':sha(output),'stderr_bytes':len(stderr),
        'stderr_sha256':sha(stderr),'owned_command_joined':True,'Android_process_tree_owned':False}


def task_table(context,raw):
    need(type(raw) is bytes and len(raw)<=context.fixture.MAX_PUBLIC_OUTPUT,'BOUNDED_TASK_TABLE_REQUIRED')
    parser=context.recorder.task_functions(context.contract.root/'references/task_scope_baseline.py')
    roots,tasks=parser.parse_stacks(raw.decode('utf-8','strict'))
    need(not any(child['component'].split('/')[0]==PACKAGE
                 for root in roots.values() for child in root['children']),
         'ORIGINAL_INSTRUMENTATION_MUST_NOT_OWN_AN_ACTIVITY_TASK')
    return {'task_ids':sorted(tasks),'root_ids':sorted(roots),'fixture_tasks':0,
            'raw_table_sha256':sha(raw),'raw_table_bytes':len(raw),'raw_table_exported':False}


def metadata_equal(fixture,raw,installed,protected):
    value=fixture.package_metadata(raw,protected)
    need(value=={k:installed[k] for k in ('package','uid','user','version_code')},
         'INSTALLED_PACKAGE_METADATA_CHANGED')
    return value


def finish_context(context,artifact,result,independent_guard):
    if artifact is not None:
        try:
            result['artifact_after']=artifact.revalidate()
        except BaseException as error:
            failure(result,'artifact_after',error)
        try:
            result['artifact_FD_cleanup']=artifact.close()
            result['all_tracked_artifact_FDs_closed']=True
        except BaseException as error:
            failure(result,'artifact_FD_cleanup',error)
    else:
        result['all_tracked_artifact_FDs_closed']=True
    if context is not None:
        try:
            context.guard(attempted=context.action_attempted)
        except BaseException as error:
            failure(result,'final_context_guard',error)
        try:
            context.close()
            result['held_binding_released']=True
        except BaseException as error:
            failure(result,'held_binding_release',error)
        result['action_attempted']=context.action_attempted
        result['exact_command_count']=context.command_index
    if independent_guard is not None:
        try:
            result['Main_after']=independent_guard()
            need(result['Main_after']==result['Main_before'],'MAIN_BEFORE_AFTER_CHANGED')
            result['current_Main_after_qualified']=True
        except BaseException as error:
            failure(result,'independent_final_Main',error)
    result['outcome_unknown']=bool(result['action_attempted'] and result['error'] is not None)


class OwnedApk:
    """Single new staging file, original IHG owned staging shape with fixed NDK identity."""
    def __init__(self,target,scope,build):
        self.target,self.scope,self.build=target,scope,build
        self.name='p4-ndk-'+scope['attempt_nonce']
        self.guest='/data/local/tmp/'+self.name+'/owned-ndk-fixture.apk'
        self.parent=self.directory=self.file=-1
        self.directory_created=self.file_created=False
        self.file_identity=self.directory_identity=None

    @staticmethod
    def identity_of(fd):
        s=os.fstat(fd)
        return {k:getattr(s,v) for k,v in
            {'device':'st_dev','inode':'st_ino','mode':'st_mode','uid':'st_uid','gid':'st_gid',
             'nlink':'st_nlink','bytes':'st_size'}.items()}

    def stage(self,raw):
        need(len(raw)==self.build['APK']['bytes'] and sha(raw)==self.build['APK']['sha256'],
             'ACTUAL_SIGNED_APK_BYTES_REQUIRED')
        self.parent=self.target.open_root('/data/local/tmp',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        os.mkdir(self.name,0o711,dir_fd=self.parent)
        self.directory_created=True
        self.directory=os.open(self.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                               dir_fd=self.parent)
        need(os.fstat(self.directory).st_uid==0,'OWN_STAGING_DIRECTORY_UID')
        os.fchmod(self.directory,0o711)
        self.directory_identity=self.identity_of(self.directory)
        self.file=os.open('owned-ndk-fixture.apk',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,
                          0o600,dir_fd=self.directory)
        self.file_created=True
        count=0
        while count<len(raw):
            amount=os.write(self.file,raw[count:])
            need(amount>0,'OWN_APK_WRITE_STALLED')
            count+=amount
        os.fsync(self.file)
        os.fchmod(self.file,0o444)
        self.file_identity=self.identity_of(self.file)
        need(self.file_identity['uid']==0 and self.file_identity['nlink']==1 and
             stat.S_ISREG(self.file_identity['mode']) and self.file_identity['bytes']==len(raw),
             'OWN_STAGED_APK_SHAPE')
        os.fsync(self.directory)
        os.fsync(self.parent)
        again,meta=self.target.read_file(self.guest,len(raw),single_link=True)
        need(again==raw and all(meta[k]==self.file_identity[k] for k in
             ('device','inode','mode','uid','gid','nlink','bytes')),'STAGED_GUEST_PATH_NOT_OWN_APK')
        return {'path':self.guest,'sha256':sha(raw),'file':self.file_identity,
                'directory':self.directory_identity}

    def close(self):
        errors=[]
        if self.file_created:
            try:
                need(self.file>=0 and self.directory>=0,'OWN_STAGED_FILE_FDS_REQUIRED')
                held=os.fstat(self.file)
                named=os.stat('owned-ndk-fixture.apk',dir_fd=self.directory,follow_symlinks=False)
                need(stat.S_ISREG(named.st_mode) and named.st_nlink==1 and
                     (named.st_dev,named.st_ino)==(held.st_dev,held.st_ino),
                     'OWN_STAGED_FILE_NAME_CHANGED')
                os.unlink('owned-ndk-fixture.apk',dir_fd=self.directory)
                os.fsync(self.directory)
            except BaseException as error:
                errors.append(('own_file',type(error).__name__))
        if self.directory_created:
            try:
                need(self.parent>=0 and self.directory>=0,'OWN_STAGED_DIRECTORY_FDS_REQUIRED')
                held=os.fstat(self.directory)
                named=os.stat(self.name,dir_fd=self.parent,follow_symlinks=False)
                need(stat.S_ISDIR(named.st_mode) and
                     (named.st_dev,named.st_ino)==(held.st_dev,held.st_ino),
                     'OWN_STAGED_DIRECTORY_NAME_CHANGED')
                # rmdir itself rejects all unexpected children. No recursive scan or delete.
                os.rmdir(self.name,dir_fd=self.parent)
                os.fsync(self.parent)
            except BaseException as error:
                errors.append(('own_directory',type(error).__name__))
        for name in ('file','directory','parent'):
            fd=getattr(self,name)
            setattr(self,name,-1)
            if fd>=0:
                try:
                    os.close(fd)
                except BaseException as error:
                    errors.append(('close_'+name,type(error).__name__))
        need(not errors,'OWN_STAGING_CLEANUP_FAILED')
        return {'staged_file_created':self.file_created,'staged_directory_created':self.directory_created,
                'staged_file_removed':self.file_created,'staged_directory_removed':self.directory_created,
                'all_staging_FDs_closed':True,'recursive_cleanup':False}


def install_once(sources,fixture,context_module,scope,build,apk_raw,step,deadline):
    fixture.pending_gate()
    fixture.validate_scope(scope)
    guest='/data/local/tmp/p4-ndk-'+scope['attempt_nonce']+'/owned-ndk-fixture.apk'
    plan=fixture.installation_plan(scope,guest)
    result=empty_result(scope,sources.pin)
    context=artifact=staged=guard=None
    try:
        context,binding,guard=context_module.open_context(
            sources,fixture,scope,step,plan,result,deadline)
        raw,row=joined_command(context,*plan[0])
        result['package_absence']=fixture.package_absent(raw)
        for kind in ('user','user_de'):
            need(not context.target.exists('/data/'+kind+'/0/'+PACKAGE),
                 'PREEXISTING_FIXTURE_DATA_MUST_NOT_BE_ADOPTED')
        result['own_data_absent_before_install']=True
        staged=OwnedApk(context.target,scope,build)
        result['staged']=staged.stage(apk_raw)
        result['install_attempted']=True
        raw,row=joined_command(context,*plan[1])
        need(raw==b'Success\n','PACKAGE_MANAGER_DID_NOT_ACCEPT_ORIGINAL_TARGET23_APK')
        result['install_success_observed']=True
        first,_=joined_command(context,*plan[2])
        second,_=joined_command(context,*plan[3])
        need(first==second,'TWO_INSTALLED_PACKAGE_ROWS_DIFFER')
        metadata=fixture.package_metadata(first,context.protected_uids)
        raw,_=joined_command(context,*plan[4])
        path=fixture.package_path(raw)
        raw,_=joined_command(context,*plan[5])
        result['ABI']=fixture.package_abi(raw)
        artifact=context_module.InstalledFixture(context,metadata,path,build,binding)
        result['installed_before']=artifact.record
        raw,_=joined_command(context,*plan[6])
        need(raw==('package:'+PACKAGE+' uid:'+str(metadata['uid'])+'\n').encode(),
             'FIXTURE_APPEARED_WITH_OTHER_USER_OR_UID')
        raw,_=joined_command(context,*plan[7])
        result['post_install_processes']=fixture.own_processes(raw,metadata['uid'])
        need(result['post_install_processes']['own_count']==0,'INSTALL_UNEXPECTEDLY_LEFT_FIXTURE_RUNNING')
        need(context.command_index==context.next_command==len(plan)==8,'EXACT_EIGHT_INSTALL_COMMANDS')
        result['owned_package_uid']=metadata['uid']
        result['build_result']=build['build_result']
        result['package_retained_for_separate_run_admission']=True
        result['ok']=True
    except BaseException as error:
        failure(result,'install',error)
    finally:
        if staged is not None:
            try:
                result['staging_cleanup']=staged.close()
            except BaseException as error:
                failure(result,'staging_cleanup',error)
        finish_context(context,artifact,result,guard)
    result['owned_install_qualified']=bool(result['ok'] and result['error'] is None and
        result.get('installed_before')==result.get('artifact_after') and
        result.get('staging_cleanup',{}).get('all_staging_FDs_closed') is True and
        result['held_binding_released'] and result['current_Main_after_qualified'])
    result['possible_owned_package_retained']=bool(result.get('install_attempted') and
                                                   not result['owned_install_qualified'])
    return result


def run_original_once(sources,fixture,context_module,scope,build,installed,step,deadline):
    fixture.pending_gate()
    plan=fixture.run_plan(scope)
    result=empty_result(scope,sources.pin)
    context=artifact=guard=None
    try:
        context,binding,guard=context_module.open_context(sources,fixture,scope,step,plan,result,deadline)
        raw,_=joined_command(context,*plan[0])
        metadata=metadata_equal(fixture,raw,installed,context.protected_uids)
        raw,_=joined_command(context,*plan[1])
        path=fixture.package_path(raw)
        need(path==installed['artifact']['path'],'ACTUAL_INSTALLED_APK_PATH_CHANGED')
        artifact=context_module.InstalledFixture(context,metadata,path,build,binding,expected=installed)
        result['installed_before']=artifact.record
        raw,_=joined_command(context,*plan[2])
        result['pre_run_processes']=fixture.own_processes(raw,metadata['uid'])
        need(result['pre_run_processes']['own_count']==0,'PREEXISTING_FIXTURE_PROCESS_MUST_NOT_BE_ADOPTED')
        raw,_=joined_command(context,*plan[3])
        result['pre_run_tasks']=task_table(context,raw)
        artifact.xml_absent()
        result['pre_run_XML_absent']=True
        result['instrumentation_attempted']=True
        raw,row=joined_command(context,*plan[4])
        result['instrumentation']=fixture.instrumentation_result(raw)
        result['instrumentation_command']=row
        result['instrumentation_verified']=True
        need(context.command_index==context.next_command==len(plan)==5,'EXACT_FIVE_RUN_COMMANDS')
        result['ok']=True
    except BaseException as error:
        failure(result,'original_instrumentation',error)
    finally:
        finish_context(context,artifact,result,guard)
    # Even successful testMain is not accepted until independent retirement/XML.
    result['native_twelve_tests_qualified']=False
    result['retirement_required']=bool(result.get('instrumentation_attempted'))
    return result


def retire_once(sources,fixture,context_module,scope,build,installed,run_result,step,deadline):
    fixture.pending_gate()
    plan=fixture.retirement_plan(scope)
    result=empty_result(scope,sources.pin)
    context=artifact=guard=None
    try:
        need(run_result['scope']['phase']=='run' and scope['phase']=='retire' and
             run_result['scope']['attempt_nonce']!=scope['attempt_nonce'] and
             run_result['scope']['uid']==scope['uid']==installed['uid'] and
             run_result['scope']['build_result']==scope['build_result']==build['build_result'] and
             run_result.get('held_binding_released') is True,
             'NEW_INDEPENDENT_RETIREMENT_SCOPE_REQUIRED')
        context,binding,guard=context_module.open_context(sources,fixture,scope,step,plan,result,deadline)
        raw,_=joined_command(context,*plan[0])
        metadata=metadata_equal(fixture,raw,installed,context.protected_uids)
        raw,_=joined_command(context,*plan[1])
        path=fixture.package_path(raw)
        need(path==installed['artifact']['path'],'OWN_APK_PATH_BEFORE_RETIREMENT_CHANGED')
        artifact=context_module.InstalledFixture(context,metadata,path,build,binding,expected=installed)
        result['installed_before']=artifact.record
        raw,row=joined_command(context,*plan[2])
        need(raw==b'','OWN_FORCE_STOP_RETURNED_UNEXPECTED_OUTPUT')
        result['force_stop_completed']=True
        result['force_stop_command']=row
        rows=[]
        for index in (3,4):
            raw,_=joined_command(context,*plan[index])
            item=fixture.own_processes(raw,metadata['uid'])
            need(item['own_count']==0,'OWN_UID_PROCESS_REMAINS_AFTER_STOP')
            rows.append(item)
        result['post_stop_processes']=rows
        result['two_complete_empty_own_UID_tables']=True
        raw,_=joined_command(context,*plan[5])
        after=task_table(context,raw)
        result['post_stop_tasks']=after
        prior=run_result.get('pre_run_tasks')
        need(type(prior) is dict and after['task_ids']==prior['task_ids'] and
             after['root_ids']==prior['root_ids'],'INSTRUMENTATION_TASK_SET_NOT_RESTORED')
        result['task_set_restored']=True
        raw,_=joined_command(context,*plan[6])
        need(fixture.package_path(raw)==path,'OWN_APK_PATH_AFTER_RETIREMENT_CHANGED')
        raw,_=joined_command(context,*plan[7])
        metadata_equal(fixture,raw,installed,context.protected_uids)
        need(context.command_index==context.next_command==len(plan)==8,'EXACT_EIGHT_RETIREMENT_COMMANDS')
        if run_result.get('instrumentation_verified') is True:
            result['native_XML']=artifact.read_fresh_xml(run_result,result)
        result['ok']=True
    except BaseException as error:
        failure(result,'independent_retirement',error)
    finally:
        finish_context(context,artifact,result,guard)
    result['original_NdkTests_testMain_accepted']=bool(result['ok'] and result['error'] is None and
        run_result.get('ok') is True and run_result.get('error') is None and
        result.get('native_XML',{}).get('tests')==12 and
        result['held_binding_released'] and result['current_Main_after_qualified'] and
        result.get('installed_before')==result.get('artifact_after'))
    result['commercial_App_readiness_qualified']=False
    result['engine_feature_default_enabled']=False
    result['new_process_engine_map_independently_qualified']=False
    result['package_uninstalled']=False
    return result


if __name__=='__main__':
    raise SystemExit('SOURCE_ONLY: actual APK/terminal/UID/nonces/phase wrapper unbound')
