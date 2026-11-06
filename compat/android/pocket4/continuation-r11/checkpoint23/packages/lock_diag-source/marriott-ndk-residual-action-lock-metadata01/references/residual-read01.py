"""One independent, childless metadata observation after failed NDK install01.
No command, namespace entry, install, process signal, package/data cleanup, or
directory-content read is reachable. Historical UNKNOWN remains unchanged.
"""
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time
import types

KIND='pocket4-original-ndk-install01-residual-read01'
PACKAGE='com.example.ndk_tests'
FAILED_JOB='1a1b271b3a6-fc05-7e09'
FAILED_RESULT='/home/alex/work/pocket4-original-ndk-fixture-APK03-install-01/result.json'
FAILED_PIN={'bytes':8994,'sha256':'0c3669215137fc4b8fce1603c586a6e8d8451777a359c926a29e9b43200cf202'}
FAILED_NONCE='e4b5a1bdac8be04ff2ea3188a6d946d6'
SHARED=Path('/home/alex/work/pocket4-current-host-r6-source-01')
SHARED_MANIFEST='002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff'
SOURCE_PIN={'bytes':11359,'sha256':'f92d2598221c5bf65e783df39864879a2056da47f794680668b34df11f97da49'}
CURRENT_GUARD_SHA='96dbdaf7673d5298e6fe17cb1b7ebae29b37110ee59f31b0c927e2cb0ef4b150'
EPOCH='7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
BASELINE='633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION='ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
ACTION_LOCK='/run/lock/android-digitalis-actions.lock'
PACKAGE_LIST='/data/system/packages.list'
PARENTS=('/data/user/0','/data/user_de/0')
OBSERVATION_SECONDS=20
FINAL_GUARD_SECONDS=25
ALARM_SECONDS=30
OUTPUT_LIMIT=262144
TABLE_LIMIT=1048576
START=None

def need(value,code):
    if not value:
        raise RuntimeError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read_exact_file(path,limit,pin=None,expected_identity=None):
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
        if expected_identity is not None:
            actual={k:getattr(before,v) for k,v in {
                'device':'st_dev','inode':'st_ino','mode':'st_mode','uid':'st_uid',
                'gid':'st_gid','nlink':'st_nlink','bytes':'st_size',
                'mtime_ns':'st_mtime_ns','ctime_ns':'st_ctime_ns'}.items()}
            need(type(expected_identity) is dict and actual==expected_identity,
                 'FIXED_ACTUAL_INPUT_IDENTITY_CHANGED')
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


def public_error(stage,error):
    message=str(error)
    raw=message.encode('utf-8','backslashreplace')
    return {'stage':stage,'type':type(error).__name__,'errno':getattr(error,'errno',None),
            'code':message if re.fullmatch('[A-Z][A-Z0-9_]{0,95}',message) else None,
            'message_bytes':len(raw),'message_sha256':sha(raw),
            'private_message_exported':False}

def remember(result,stage,error):
    value=public_error(stage,error)
    if result['first_error'] is None:
        result['first_error']=value
    else:
        result['secondary_errors'].append(value)

def deadline(final=False):
    limit=FINAL_GUARD_SECONDS if final else OBSERVATION_SECONDS
    need(time.monotonic()<START+limit,'FIXED_RESIDUAL_OBSERVATION_DEADLINE')

def identity(fd):
    s=os.fstat(fd)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,
            'uid':s.st_uid,'gid':s.st_gid,'nlink':s.st_nlink,'bytes':s.st_size,
            'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}

def stable_directory(row):
    return {k:row[k] for k in ('device','inode','mode','uid','gid')}

def named_identity(parent,name):
    s=os.stat(name,dir_fd=parent,follow_symlinks=False)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,
            'uid':s.st_uid,'gid':s.st_gid,'nlink':s.st_nlink,'bytes':s.st_size,
            'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}

class Journal:
    def __init__(self):
        self.rows=[]

    def take(self,fd,label):
        # Registration precedes all fallible FD qualification.
        row={'fd':fd,'label':label,'closed':False,'close_error':None}
        self.rows.append(row)
        need(type(fd) is int and fd>=3 and len(self.rows)<=96 and
             sum(x['fd']==fd and x['closed'] is False for x in self.rows)==1,
             'OWN_FD_REGISTRATION_SHAPE')
        need(os.get_inheritable(fd) is False,'OWN_FD_CLOEXEC_REQUIRED')
        return fd

    def close(self,fd):
        rows=[x for x in self.rows if x['fd']==fd and x['closed'] is False]
        need(len(rows)==1,'EXACT_LIVE_OWN_FD_REQUIRED')
        row=rows[0]
        try:
            os.close(fd)
            row['closed']=True
        except BaseException as error:
            # A failed close is not retried, because the FD number may be reused.
            row['closed']=None
            row['close_error']=public_error('close',error)
            raise

    def finish(self,result):
        for row in reversed(self.rows):
            if row['closed'] is False:
                try:
                    self.close(row['fd'])
                except BaseException as error:
                    remember(result,'owned_FD_close',error)
        result['owned_FD_journal']=self.rows
        result['all_journal_FDs_closed']=all(x['closed'] is True for x in self.rows)

class ActionLock:
    def __init__(self,journal):
        self.journal=journal;self.edges=[];self.fd=None;self.parent=None
        self.expected=None;self.acquired=False
        self.observation={'path':ACTION_LOCK,'attempts':0,'acquired':False,
                          'released':False,'created':False,'chmod_or_truncate':False}

    def _edge(self,parent,name,fd):
        held=stable_directory(identity(fd))
        need(stat.S_ISDIR(held['mode']) and
             stable_directory(named_identity(parent,name))==held,
             'ACTION_LOCK_ANCESTOR_NAME_DIFFERS')
        self.edges.append((parent,name,fd,held))

    def acquire(self):
        deadline()
        current=self.journal.take(os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC),
                                  'action_lock:/')
        self._edge(None,'/',current)
        for part in ('run','lock'):
            parent=current
            current=self.journal.take(os.open(part,os.O_PATH|os.O_DIRECTORY|
                os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent),'action_lock:'+part)
            self._edge(parent,part,current)
        self.parent=current
        self.fd=self.journal.take(os.open('android-digitalis-actions.lock',
            os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current),'action_lock:file')
        self.expected=identity(self.fd)
        need(stat.S_ISREG(self.expected['mode']) and self.expected['nlink']==1 and
             self.expected['uid']==self.expected['gid']==0 and
             not self.expected['mode']&0o022,'EXISTING_ROOT_ACTION_LOCK_SHAPE')
        self.verify()
        self.observation['attempts']=1
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.acquired=True
        self.observation['acquired']=True
        self.verify()

    def verify(self):
        for parent,name,fd,expected in self.edges:
            need(stable_directory(identity(fd))==expected and
                 stable_directory(named_identity(parent,name))==expected,
                 'ACTION_LOCK_ANCESTOR_CHANGED')
        if self.fd is not None:
            need(identity(self.fd)==self.expected and
                 named_identity(self.parent,'android-digitalis-actions.lock')==self.expected,
                 'ACTION_LOCK_HELD_OR_NAMED_CHANGED')

    def release(self,result):
        try:
            self.verify()
        except BaseException as error:
            remember(result,'action_lock_final_identity',error)
        if self.acquired:
            try:
                fcntl.flock(self.fd,fcntl.LOCK_UN)
                self.observation['released']=True
            except BaseException as error:
                remember(result,'action_lock_release',error)
        result['action_lock']=self.observation

def package_projection(raw):
    need(type(raw) is bytes and 0<len(raw)<=TABLE_LIMIT and
         b'\0' not in raw,'PACKAGE_TABLE_BYTE_SHAPE')
    found=[]
    for line in raw.decode('utf-8','strict').splitlines():
        fields=line.split()
        if not fields or fields[0]!=PACKAGE:
            continue
        need(len(fields)>=2 and re.fullmatch('[0-9]{1,6}',fields[1]) is not None,
             'SELECTED_PACKAGE_UID_ROW_INVALID')
        uid=int(fields[1])
        need(10000<=uid<100000,'SELECTED_PACKAGE_UID_NOT_USER_ZERO_APP')
        found.append(uid)
    need(len(found)<=1,'SELECTED_PACKAGE_ROW_DUPLICATED')
    return {'package':PACKAGE,'present':bool(found),'observed_UID':found[0] if found else None,
            'source':'held /data/system/packages.list','private_row_exported':False,
            'all_user_PM_or_uninstalled_records_qualified':False}

def parser_controls():
    cases=[]
    def accepted(name,raw,present,uid):
        value=package_projection(raw)
        need(value['present'] is present and value['observed_UID']==uid,
             'PARSER_POSITIVE_CONTROL_FAILED')
        cases.append({'name':name,'passed':True})
    def rejected(name,raw,code):
        try:
            package_projection(raw)
        except RuntimeError as error:
            need(str(error)==code,'PARSER_WRONG_NEGATIVE_GATE')
        else:
            raise RuntimeError('PARSER_NEGATIVE_CONTROL_ACCEPTED')
        cases.append({'name':name,'passed':True})
    accepted('nonselected-package-absent',b'org.example.synthetic 10123\n',False,None)
    accepted('other-and-suffixed-package-not-selected',
             b'org.example.synthetic 10123\ncom.example.ndk_tests.extra 10124\n',False,None)
    accepted('single-selected-row-present',b'com.example.ndk_tests 10234 synthetic\n',True,10234)
    rejected('duplicate-selected-row',b'com.example.ndk_tests 10234\ncom.example.ndk_tests 10234\n',
             'SELECTED_PACKAGE_ROW_DUPLICATED')
    rejected('malformed-selected-UID',b'com.example.ndk_tests not-a-UID\n',
             'SELECTED_PACKAGE_UID_ROW_INVALID')
    rejected('system-UID-not-fixture-app',b'com.example.ndk_tests 1000\n',
             'SELECTED_PACKAGE_UID_NOT_USER_ZERO_APP')
    need(len(cases)==6 and len({x['name'] for x in cases})==6,'EXACT_SIX_PARSER_CONTROLS')
    return cases

def module(raw,path,name):
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__)
    return value

def qualify_failed_original(raw):
    value=json.loads(raw)
    need(value.get('kind')=='pocket4-original-ndk-fixture-install-v1' and
         value.get('ok') is False and value.get('outcome_unknown') is True and
         value.get('install_attempted') is True and value.get('owned_install_qualified') is False and
         value.get('exact_command_count')==2 and value.get('target_sdk_bypass_used') is False and
         value.get('instrumentation_executed') is False,'ORIGINAL_FAILED_INSTALL_BOUNDARY')
    scope=value.get('scope',{})
    need(scope.get('package')==PACKAGE and scope.get('uid') is None and
         scope.get('phase')=='install' and scope.get('attempt_nonce')==FAILED_NONCE and
         scope.get('Main_epoch')==EPOCH and scope.get('baseline_sha256')==BASELINE and
         scope.get('qualification_sha256')==QUALIFICATION,'ORIGINAL_FAILED_SCOPE_BOUNDARY')
    return {'job_id':FAILED_JOB,'result':dict(FAILED_PIN),'outcome_unknown_preserved':True,
            'failed_install_UID':None,'old_nonce_consumed_not_reused':True}

def read_table(target,journal):
    deadline();target.verify()
    fd=journal.take(target.open_root(PACKAGE_LIST,os.O_RDONLY|os.O_NOFOLLOW),'packages.list')
    before=identity(fd)
    need(stat.S_ISREG(before['mode']) and before['nlink']==1 and
         0<before['bytes']<=TABLE_LIMIT,'PACKAGE_TABLE_REGULAR_BOUND')
    parts=[];count=0
    while True:
        deadline()
        block=os.read(fd,min(65536,TABLE_LIMIT+1-count))
        if not block:
            break
        count+=len(block)
        need(count<=TABLE_LIMIT,'PACKAGE_TABLE_OVER_BOUND')
        parts.append(block)
    raw=b''.join(parts)
    need(len(raw)==before['bytes'] and identity(fd)==before,'PACKAGE_TABLE_CHANGED_DURING_READ')
    named=journal.take(target.open_root(PACKAGE_LIST,os.O_RDONLY|os.O_NOFOLLOW),
                       'packages.list:named')
    need(identity(named)==before,'PACKAGE_TABLE_NAME_CHANGED')
    journal.close(named);journal.close(fd)
    deadline();target.verify()
    return raw,{'path':PACKAGE_LIST,'identity':before,'bytes':len(raw),'sha256':sha(raw),
                'body_exported':False,'complete_to_EOF':True}

class DirectoryView:
    def __init__(self,target,journal,parent):
        need(parent in PARENTS,'ONLY_TWO_FIXED_DATA_PARENTS')
        self.target=target;self.journal=journal;self.parent=parent
        self.fd=journal.take(target.open_root(parent,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW),
                             'parent:'+parent)
        self.parent_identity=stable_directory(identity(self.fd))
        need(stat.S_ISDIR(self.parent_identity['mode']),'FIXED_DATA_PARENT_DIRECTORY')
        self.leaf=None;self.initial=None

    def parent_current(self):
        deadline();self.target.verify()
        need(stable_directory(identity(self.fd))==self.parent_identity,
             'HELD_DATA_PARENT_CHANGED')
        fd=self.journal.take(self.target.open_root(self.parent,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW),
                             'parent:named:'+self.parent)
        need(stable_directory(identity(fd))==self.parent_identity,'NAMED_DATA_PARENT_CHANGED')
        self.journal.close(fd)

    def observe(self,initial):
        self.parent_current()
        fd=None
        try:
            fd=self.journal.take(os.open(PACKAGE,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.fd),
                                 'leaf:'+self.parent+'/'+PACKAGE)
        except FileNotFoundError as error:
            need(error.errno==errno.ENOENT,'ONLY_EXACT_ENOENT_IS_ABSENT')
            row={'path':self.parent+'/'+PACKAGE,'present':False,'identity':None,
                 'contents_read':False,'directory_enumerated':False,'leaf_symlink_followed':False}
        else:
            value=identity(fd)
            kind='directory' if stat.S_ISDIR(value['mode']) else (
                 'symlink' if stat.S_ISLNK(value['mode']) else 'other')
            need(named_identity(self.fd,PACKAGE)==value,'FIXED_LEAF_NAMED_IDENTITY_CHANGED')
            row={'path':self.parent+'/'+PACKAGE,'present':True,'kind':kind,'identity':value,
                 'contents_read':False,'directory_enumerated':False,'leaf_symlink_followed':False}
        if initial:
            self.initial=row
            self.leaf=fd
        else:
            need(row==self.initial,'FIXED_DATA_LEAF_CHANGED_BETWEEN_OBSERVATIONS')
            if self.leaf is not None:
                need(identity(self.leaf)==self.initial['identity'],'HELD_DATA_LEAF_CHANGED')
            if fd is not None:
                self.journal.close(fd)
        self.parent_current()
        return row

class ReadDeadline(BaseException):
    pass

def alarm_handler(signum,frame):
    raise ReadDeadline('FIXED_READER_SELF_DEADLINE')

def main():
    global START
    START=time.monotonic()
    result={'schema':1,'kind':KIND,'package':PACKAGE,'user':0,'collection_complete':False,
            'first_error':None,'secondary_errors':[],'Main_actions':0,'Android_commands':0,
            'namespace_entry':False,'children_spawned':0,'files_created_or_modified':0,
            'process_signals_sent':0,'directory_enumeration':False,'data_contents_read':False,
            'private_baseline_or_package_table_exported':False,'automatic_retry':False,
            'old_install_status':'UNKNOWN','installed_UID_qualified':None,
            'future_install_authorized':False,'run_or_retire_authorized':False,
            'PM_all_user_absence_qualified':False,'APK_path_residue_qualified':False,
            'whole_invocation_resource_observed':False,'global_ambient_FD_equality_asserted':False,
            'observation_seconds':OBSERVATION_SECONDS,'final_guard_seconds':FINAL_GUARD_SECONDS,
            'hard_alarm_seconds':ALARM_SECONDS,'fixed_file_helpers_returned_after_close':0,
            'held_target_started':False,'held_target_constructed':False,'held_target_closed':False,
            'timer_and_handler_restored':False}
    journal=Journal();lock=None;target=None;guard=None;source=None;contract=None
    timer_set=False;handler_set=False;old_handler=None;observed=False;stage='preconditions'
    try:
        need(len(sys.argv)==1 and os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,
             'ROOT_CHILDLESS_FIXED_READER_REQUIRED')
        need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'AMBIENT_TIMER_NOT_EMPTY')
        need(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,set()),
             'SIGALRM_IS_BLOCKED')
        old_handler=signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM,alarm_handler);handler_set=True
        signal.setitimer(signal.ITIMER_REAL,ALARM_SECONDS);timer_set=True
        result['parser_controls']=parser_controls()
        stage='original_failed_result'
        original=read_exact_file(FAILED_RESULT,1048576,FAILED_PIN)
        result['fixed_file_helpers_returned_after_close']+=1
        result['historical_failed_install']=qualify_failed_original(original)
        stage='original_R6_source_contract'
        source_raw=read_exact_file(SHARED/'source_contract.py',131072,SOURCE_PIN)
        result['fixed_file_helpers_returned_after_close']+=1
        source=module(source_raw,SHARED/'source_contract.py','fixed_ndk_residual_source')
        contract=source.SourceContract(SHARED/'source-manifest.json',SHARED_MANIFEST)
        held=contract.load('references/held_runtime_r5.py','fixed_ndk_residual_held')
        binding=contract.load('main_binding.py','fixed_ndk_residual_identity_only')
        current=contract.load('current_baseline_guard.py','fixed_ndk_residual_guard')
        need(contract.files['current_baseline_guard.py']['sha256']==CURRENT_GUARD_SHA,
             'CURRENT_MAIN_GUARD_PIN_CHANGED')
        baseline=current.current_baseline()
        need(baseline.get('schema')=='pocket4-main-current-baseline-v2' and
             baseline.get('kind')=='current-cell-generation' and
             baseline.get('deployment_performed') is False and 'main_deployed' not in baseline and
             baseline['framework_epoch']['sha256']==EPOCH==current.MAIN_EPOCH and
             current.BASELINE_SHA==BASELINE and current.QUALIFICATION_SHA==QUALIFICATION and
             PACKAGE not in baseline['packages'],'EXACT_SEPARATE_CURRENT_MAIN_BASELINE')
        protected=set(baseline['packages'].values())
        need(all(type(x) is int for x in protected),'ORIGINAL_BASELINE_UID_SHAPE')
        def original_guard(final=False):
            deadline(final)
            read_exact_file(SHARED/'source_contract.py',131072,SOURCE_PIN)
            result['fixed_file_helpers_returned_after_close']+=1
            contract.verify()
            helper=source.bounded_file(source.HELPER_PATH,source.HELPER_BYTES)
            need(len(helper)==source.HELPER_BYTES and sha(helper)==source.HELPER_SHA,
                 'ORIGINAL_SHARED_HELPER_CHANGED')
            proof=current.current_guard(baseline,action_attempted=False)
            if lock is not None and lock.expected is not None:
                lock.verify()
            if target is not None:
                target.verify()
            deadline(final)
            return proof
        guard=original_guard
        result['shared_helper']=source.verify_shared_helper()
        result['Main_before']=guard()
        stage='existing_global_lock'
        lock=ActionLock(journal);lock.acquire()
        result['Main_after_lock']=guard()
        need(result['Main_after_lock']==result['Main_before'],'MAIN_CHANGED_WHILE_ACQUIRING_LOCK')
        stage='held_current_init'
        expected=baseline['framework_epoch']['binding']['processes']['init']
        proc=journal.take(os.open('/proc/'+str(expected['host_pid']),
             os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),'current_init_proc')
        actual=held.proc_identity_at(proc,expected['host_pid'],min(START+OBSERVATION_SECONDS,time.monotonic()+3))
        journal.close(proc)
        need(binding.same_epoch_identity(actual,expected),'CURRENT_INIT_IDENTITY_DIFFERS')
        result['held_target_started']=True
        target=held.HeldTarget(actual,source.HELPER_PATH,source.HELPER_SHA)
        result['held_target_constructed']=True
        result['held_authority_count']=len(target._fds)
        guard()
        stage='package_table_before'
        first_raw,first_file=read_table(target,journal)
        first=package_projection(first_raw)
        result['package_before']=first;result['package_file_before']=first_file
        if first['present']:
            need(first['observed_UID'] not in protected,'OBSERVED_FIXTURE_UID_ALIASES_BASELINE_APP')
            binding.package_uids(first_raw,{PACKAGE:first['observed_UID']})
        stage='fixed_data_leaves_before'
        views=[]
        result['data_directories_before']=[]
        for parent in PARENTS:
            deadline()
            view=DirectoryView(target,journal,parent)
            views.append(view)
            result['data_directories_before'].append(view.observe(True))
        guard()
        stage='package_table_after'
        last_raw,last_file=read_table(target,journal)
        last=package_projection(last_raw)
        result['package_after']=last;result['package_file_after']=last_file
        need(last_raw==first_raw and last_file==first_file and last==first,
             'PACKAGE_TABLE_CHANGED_BETWEEN_OBSERVATIONS')
        if last['present']:
            binding.package_uids(last_raw,{PACKAGE:last['observed_UID']})
        del first_raw,last_raw
        stage='fixed_data_leaves_after'
        result['data_directories_after']=[view.observe(False) for view in views]
        need(result['data_directories_after']==result['data_directories_before'],
             'DATA_DIRECTORY_OBSERVATIONS_DIFFER')
        result['Main_after_observation']=guard()
        need(result['Main_after_observation']==result['Main_before'],'MAIN_CHANGED_DURING_READ')
        result['selected_index_and_two_data_leaves_absent']=(not first['present'] and
            all(not x['present'] for x in result['data_directories_before']))
        result['observed_package_UID']=first['observed_UID']
        result['absence_scope']='Only two complete packages.list reads and two exact data leaves; no PM all-user or APK-path assertion.'
        result['observation_completed_seconds']=time.monotonic()-START
        need(result['observation_completed_seconds']<OBSERVATION_SECONDS,
             'PACKAGE_AND_DATA_OBSERVATION_COMPLETED_TOO_LATE')
        stage='original_result_after'
        again=read_exact_file(FAILED_RESULT,1048576,FAILED_PIN)
        result['fixed_file_helpers_returned_after_close']+=1
        need(again==original,'ORIGINAL_FAILED_RESULT_CHANGED')
        qualify_failed_original(again)
        observed=True
    except BaseException as error:
        remember(result,stage,error)
    finally:
        if guard is not None:
            try:
                result['Main_final']=guard(True)
                need(result.get('Main_before')==result['Main_final'],'MAIN_FINAL_CHANGED')
                result['final_Main_guard_passed']=True
            except BaseException as error:
                remember(result,'final_original_Main_guard',error)
        if target is not None:
            try:
                target.close()
                need(target._closed and not target._fds,'HELD_TARGET_CLOSE_INCOMPLETE')
                result['held_target_closed']=True
            except BaseException as error:
                remember(result,'held_current_init_close',error)
        if lock is not None:
            lock.release(result)
        journal.finish(result)
        if timer_set:
            try:
                signal.setitimer(signal.ITIMER_REAL,0)
            except BaseException as error:
                remember(result,'self_timer_cancel',error)
        if handler_set:
            try:
                signal.signal(signal.SIGALRM,old_handler)
                need(signal.getsignal(signal.SIGALRM)==old_handler and
                     signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'SELF_TIMER_RESTORE_FAILED')
                result['timer_and_handler_restored']=True
            except BaseException as error:
                remember(result,'self_handler_restore',error)
    result['collection_complete']=bool(observed and result['first_error'] is None and
        not result['secondary_errors'] and result['all_journal_FDs_closed'] and
        result['held_target_constructed'] and result['held_target_closed'] and
        result.get('final_Main_guard_passed') is True and
        result.get('action_lock',{}).get('released') is True and result['timer_and_handler_restored'])
    result['elapsed_seconds']=time.monotonic()-START
    encoded=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(encoded)<=OUTPUT_LIMIT,'SAFE_RESIDUAL_REPORT_BOUND')
    sys.stdout.write(encoded.decode('utf-8'));sys.stdout.flush()
    return 0 if result['collection_complete'] else 1

if __name__=='__main__':
    raise SystemExit(main())
