"""Fixed action-lock metadata and two bounded /proc/locks snapshots.
This reader never requests, releases, creates, or modifies any lock.
Only the exact lock inode is projected. No holder process is inspected.
"""
import hashlib
import json
import os
import re
import signal
import stat
import sys
import time

KIND='p4-ndk-residual-action-lock-metadata01'
TARGET='/run/lock/android-digitalis-actions.lock'
HISTORICAL={'job_id':'1a1b2a4e11f-fc05-7f1d','bytes':4749,
 'sha256':'642be65fb1edc94b866c1f0bc578ae1d8801100f6d25ced64de4505c52fba6e8',
 'stage':'existing_global_lock','errno':11,'lock_acquired':False,
 'package_or_data_observed':False,'old_install_status':'UNKNOWN'}
LOCKS_LIMIT=1048576
LOCKS_LINES=16384
LINE_LIMIT=1024
SELECTED_LIMIT=64
FDINFO_LIMIT=16384
OUTPUT_LIMIT=65536
OBSERVATION_SECONDS=10.0
HARD_SECONDS=12.0
START=None

def need(value,code):
    if not value:
        raise RuntimeError(code)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def tick():
    need(START is not None and time.monotonic()-START<OBSERVATION_SECONDS,
         'FIXED_LOCK_METADATA_DEADLINE')

def error_row(stage,error):
    text=str(error)
    value={'stage':stage,'type':type(error).__name__,'errno':getattr(error,'errno',None)}
    if re.fullmatch('[A-Z][A-Z0-9_]{0,127}',text):
        value['code']=text
    else:
        value['message_bytes']=len(text.encode('utf-8','replace'))
        value['message_sha256']=digest(text.encode('utf-8','replace'))
    return value

def remember(result,stage,error):
    row=error_row(stage,error)
    if result['first_error'] is None:
        result['first_error']=row
    else:
        result['secondary_errors'].append(row)

def identity(fd):
    x=os.fstat(fd)
    return {name:getattr(x,key) for name,key in (
        ('device','st_dev'),('inode','st_ino'),('mode','st_mode'),
        ('uid','st_uid'),('gid','st_gid'),('nlink','st_nlink'),
        ('bytes','st_size'),('mtime_ns','st_mtime_ns'),('ctime_ns','st_ctime_ns'))}

def named_identity(parent,name):
    x=os.stat(name,dir_fd=parent,follow_symlinks=False)
    return {field:getattr(x,key) for field,key in (
        ('device','st_dev'),('inode','st_ino'),('mode','st_mode'),
        ('uid','st_uid'),('gid','st_gid'),('nlink','st_nlink'),
        ('bytes','st_size'),('mtime_ns','st_mtime_ns'),('ctime_ns','st_ctime_ns'))}

def directory_identity(row):
    return {k:row[k] for k in ('device','inode','mode','uid','gid')}

class Journal:
    def __init__(self):
        self.rows=[]
        self.active={}
    def own(self,fd,label):
        row={'fd':fd,'label':label,'close_attempted':False,'closed':False,'close_error':None}
        self.rows.append(row)
        need(fd not in self.active,'DUPLICATE_OWNED_FD')
        self.active[fd]=row
        need(type(fd) is int and fd>=3,'OWN_FD_ALIASED_STANDARD_STREAM')
        return fd
    def close(self,fd):
        row=self.active.pop(fd)
        row['close_attempted']=True
        try:
            os.close(fd)
            row['closed']=True
        except BaseException as error:
            row['close_error']=error_row('owned_close',error)
            raise
    def finish(self,result):
        for fd in reversed(tuple(self.active)):
            try:
                self.close(fd)
            except BaseException as error:
                remember(result,'owned_FD_close',error)
        result['owned_FDs']=self.rows
        result['all_owned_FDs_closed']=bool(not self.active and
            all(x['close_attempted'] and x['closed'] and x['close_error'] is None
                for x in self.rows))

class Names:
    def __init__(self,journal):
        self.journal=journal
        self.edges=[]
    def directory(self,parent,name,label):
        tick()
        fd=self.journal.own(os.open(name,os.O_PATH|os.O_DIRECTORY|
            os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent),label)
        held=directory_identity(identity(fd))
        need(stat.S_ISDIR(held['mode']) and
             directory_identity(named_identity(parent,name))==held,
             'HELD_DIRECTORY_NAME_MISMATCH')
        self.edges.append((parent,name,fd,held))
        return fd
    def verify(self):
        for parent,name,fd,expected in self.edges:
            tick()
            need(directory_identity(identity(fd))==expected and
                 directory_identity(named_identity(parent,name))==expected,
                 'HELD_ANCESTOR_NAME_CHANGED')

def read_leaf(journal,parent,name,maximum,label):
    tick()
    fd=journal.own(os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,
                          dir_fd=parent),label)
    primary=None
    try:
        before=identity(fd)
        need(stat.S_ISREG(before['mode']),'FIXED_PROC_LEAF_NOT_REGULAR')
        chunks=[]
        count=0
        while True:
            tick()
            part=os.read(fd,min(16384,maximum+1-count))
            if not part:
                break
            chunks.append(part)
            count+=len(part)
            need(count<=maximum,'FIXED_PROC_LEAF_BYTE_BOUND')
        raw=b''.join(chunks)
        need(identity(fd)==before and named_identity(parent,name)==before,
             'FIXED_PROC_LEAF_IDENTITY_CHANGED')
        return raw,{'file':before,'bytes':len(raw),'sha256':digest(raw),
                    'complete_to_EOF':True}
    except BaseException as error:
        primary=error
        raise
    finally:
        try:
            journal.close(fd)
        except BaseException as close_error:
            if primary is None:
                raise
            primary.add_note('OWNED_PROC_LEAF_CLOSE_FAILED')

LOCK_LINE=re.compile(r'([0-9]{1,20}):\s+(?:(->)\s+)?([A-Z][A-Z0-9_]{0,31})\s+'
    r'([A-Z][A-Z0-9_]{0,31})\s+([A-Z][A-Z0-9_]{0,31})\s+(-?[0-9]{1,20})\s+'
    r'([0-9a-fA-F]{1,16}):([0-9a-fA-F]{1,16}):([0-9]{1,20})\s+'
    r'([0-9]{1,20})\s+([0-9]{1,20}|EOF)')

def project_locks(raw,target,pid):
    need(type(raw) is bytes and len(raw)<=LOCKS_LIMIT and b'\0' not in raw and
         (not raw or raw.endswith(b'\n')),'COMPLETE_LOCK_TABLE_BYTE_SHAPE')
    lines=raw.decode('ascii','strict').splitlines()
    need(len(lines)<=LOCKS_LINES,'LOCK_TABLE_LINE_BOUND')
    selected=[]
    for line in lines:
        tick()
        need(0<len(line)<=LINE_LIMIT,'LOCK_TABLE_RECORD_LENGTH')
        match=LOCK_LINE.fullmatch(line)
        need(match is not None,'LOCK_TABLE_RECORD_GRAMMAR')
        order,arrow,kind,mechanism,access,owner,major,minor,inode,start,end=match.groups()
        major,minor,inode=int(major,16),int(minor,16),int(inode)
        need(major<2**32 and minor<2**32 and 0<inode<2**64,'LOCK_TABLE_DEVICE_INODE_BOUND')
        if (major,minor,inode)!=(target['device_major'],target['device_minor'],target['inode']):
            continue
        owner=int(owner);start=int(start);end_value=None if end=='EOF' else int(end)
        need(kind in ('FLOCK','POSIX','OFDLCK','LEASE') and
             mechanism in ('ADVISORY','MANDATORY','ACTIVE','BREAKING','BREAKER') and
             access in ('READ','WRITE','UNLCK') and -1<=owner<=2147483647 and
             0<=start<2**64 and (end_value is None or start<=end_value<2**64),
             'SELECTED_LOCK_RECORD_UNSUPPORTED')
        selected.append({'ordinal':int(order),'blocked_waiter':arrow is not None,
            'type':kind,'mechanism':mechanism,'access':access,'reported_pid':owner,
            'device_major':major,'device_minor':minor,'inode':inode,
            'start':start,'end':'EOF' if end_value is None else end_value,
            'reported_pid_is_this_reader':owner==pid,
            'reported_pid_identity_or_liveness_qualified':False,
            'single_owner_attribution_available':owner>0 and kind!='OFDLCK'})
        need(len(selected)<=SELECTED_LIMIT,'SELECTED_LOCK_RECORD_BOUND')
    owners=sorted({x['reported_pid'] for x in selected if not x['blocked_waiter'] and
                   x['reported_pid']>0 and x['type']!='OFDLCK'})
    return {'bytes':len(raw),'sha256':digest(raw),'line_count':len(lines),
            'selected':selected,'candidate_holder_pids_from_this_view':owners,
            'waiter_pids_from_this_view':sorted({x['reported_pid'] for x in selected
                if x['blocked_waiter'] and x['reported_pid']>0}),
            'unrelated_lock_records_exported':False,'raw_table_exported':False,
            'holder_processes_inspected':False,'absence_is_global_or_historical_proof':False}

def own_fdinfo(journal,fdinfo,fd,expected_inode):
    raw,row=read_leaf(journal,fdinfo,str(fd),FDINFO_LIMIT,'own_target_fdinfo')
    text=raw.decode('ascii','strict')
    need(text.endswith('\n') and '\0' not in text,'OWN_FDINFO_BYTE_SHAPE')
    fields={}
    for line in text.splitlines():
        name,sep,value=line.partition(':')
        need(sep and name in ('pos','flags','mnt_id','ino') and name not in fields,
             'OWN_OPATH_FDINFO_FIELDS')
        fields[name]=value.strip()
    need(set(fields)=={'pos','flags','mnt_id','ino'} and
         re.fullmatch('[0-9]+',fields['pos']) and
         re.fullmatch('[0-7]+',fields['flags']) and
         re.fullmatch('[0-9]+',fields['mnt_id']) and
         re.fullmatch('[0-9]+',fields['ino']),'OWN_OPATH_FDINFO_SCHEMA')
    flags=int(fields['flags'],8)
    need(flags&os.O_PATH and flags&os.O_CLOEXEC and int(fields['ino'])==expected_inode,
         'OWN_OPATH_FDINFO_IDENTITY')
    row['fields']={'pos':int(fields['pos']),'flags_octal':fields['flags'],
                   'mnt_id':int(fields['mnt_id']),'inode':int(fields['ino'])}
    return row

def own_namespaces(proc):
    tick()
    out={}
    for name in ('pid','mnt'):
        value=os.readlink('ns/'+name,dir_fd=proc)
        need(len(value)<=128 and re.fullmatch(name+r':\[[0-9]{1,20}\]',value),
             'OWN_NAMESPACE_LINK_SHAPE')
        out[name]=value
    return out

def parser_controls():
    target={'device_major':0,'device_minor':28,'inode':987}
    cases=[]
    def run(name,fn):
        fn()
        cases.append({'name':name,'passed':True})
    def real_holder():
        x=project_locks(b'1: FLOCK ADVISORY WRITE 123 00:1c:987 0 EOF\n',target,456)
        need(x['candidate_holder_pids_from_this_view']==[123] and
             x['waiter_pids_from_this_view']==[] and len(x['selected'])==1,
             'PARSER_HOLDER_PROJECTION')
    run('one_FLOCK_holder_exact_dev_inode',real_holder)
    def waiter():
        x=project_locks(b'2: -> FLOCK ADVISORY WRITE 123 00:1c:987 0 EOF\n',target,456)
        need(x['candidate_holder_pids_from_this_view']==[] and
             x['waiter_pids_from_this_view']==[123],'PARSER_WAITER_NOT_HOLDER')
    run('blocked_waiter_not_promoted_to_holder',waiter)
    def ofd():
        x=project_locks(b'3: OFDLCK ADVISORY WRITE -1 00:1c:987 0 EOF\n',target,456)
        need(x['candidate_holder_pids_from_this_view']==[] and
             x['selected'][0]['single_owner_attribution_available'] is False,
             'PARSER_OFD_NOT_PROCESS_OWNER')
    run('OFD_minus_one_has_no_single_PID_authority',ofd)
    def other():
        x=project_locks(b'1: FLOCK ADVISORY WRITE 123 00:1c:988 0 EOF\n',target,456)
        need(x['selected']==[] and x['candidate_holder_pids_from_this_view']==[],
             'PARSER_WRONG_INODE_MUST_NOT_MATCH')
    run('same_device_wrong_inode_excluded',other)
    def malformed():
        try:
            project_locks(b'1: malformed 00:1c:987\n',target,456)
        except RuntimeError as error:
            need(str(error)=='LOCK_TABLE_RECORD_GRAMMAR','PARSER_WRONG_REJECTION')
        else:
            raise RuntimeError('PARSER_MALFORMED_ACCEPTED')
    run('malformed_complete_table_fails_closed',malformed)
    return cases

class ReadDeadline(BaseException):
    pass

def alarm_handler(signum,frame):
    raise ReadDeadline('FIXED_LOCK_METADATA_HARD_DEADLINE')

def main():
    global START
    START=time.monotonic()
    result={'schema':1,'kind':KIND,'historical_failure':HISTORICAL,
        'collection_complete':False,'first_error':None,'secondary_errors':[],
        'target_path':TARGET,'flock_calls':0,'lockf_or_fcntl_lock_calls':0,
        'lock_or_unlock_attempts':0,'lock_file_body_reads':0,
        'children_spawned':0,'process_signals_sent':0,'Android_commands':0,
        'Main_reads':0,'files_created_or_modified':0,'directory_enumeration':False,
        'other_process_files_read':False,'package_or_data_read':False,
        'old_install_status':'UNKNOWN','residual_absence_qualified':False,
        'future_install_run_or_retire_authorized':False,
        'initial_PID_namespace_or_unfiltered_proc_locks_proven':False,
        'observation_seconds':OBSERVATION_SECONDS,'hard_deadline_seconds':HARD_SECONDS,
        'whole_invocation_resource_observed':False,
        'global_ambient_FD_equality_asserted':False,'timer_and_handler_restored':False}
    journal=Journal();names=Names(journal);target=None;lock_parent=None;before=None
    handler_set=False;timer_set=False;old_handler=None;completed=False;phase='preconditions'
    try:
        need(len(sys.argv)==1 and os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,
             'ROOT_FIXED_CHILDLESS_READER_REQUIRED')
        need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'AMBIENT_TIMER_NOT_EMPTY')
        need(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,set()),
             'SIGALRM_IS_BLOCKED')
        old_handler=signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM,alarm_handler);handler_set=True
        signal.setitimer(signal.ITIMER_REAL,HARD_SECONDS);timer_set=True
        result['parser_controls']=parser_controls()
        phase='fixed_existing_target'
        root=names.directory(None,'/','root')
        run=names.directory(root,'run','run')
        lock_parent=names.directory(run,'lock','run_lock')
        target=journal.own(os.open('android-digitalis-actions.lock',
            os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=lock_parent),'target_OPATH')
        before=identity(target)
        result['target_before']=before
        result['named_before']=named_identity(lock_parent,'android-digitalis-actions.lock')
        need(stat.S_ISREG(before['mode']) and before['uid']==before['gid']==0 and
             before['nlink']==1 and not before['mode']&0o022 and
             result['named_before']==before,'FIXED_ROOT_LOCK_FILE_SHAPE')
        key={'device_major':os.major(before['device']),
             'device_minor':os.minor(before['device']),'inode':before['inode']}
        result['exact_lock_key']=key
        phase='own_proc_metadata'
        procroot=names.directory(root,'proc','proc_root')
        own_pid=os.getpid()
        own_proc_name=os.readlink('self',dir_fd=procroot)
        need(re.fullmatch('[1-9][0-9]{0,9}',own_proc_name) and
             int(own_proc_name)<=2147483647,'OWN_PROC_SELF_LINK_SHAPE')
        pid=int(own_proc_name)
        proc=names.directory(procroot,own_proc_name,'own_proc')
        fdinfo=names.directory(proc,'fdinfo','own_fdinfo_directory')
        result['self_pid']=own_pid
        result['self_pid_in_this_proc_view']=pid
        result['own_namespaces_before']=own_namespaces(proc)
        result['target_fdinfo_before']=own_fdinfo(journal,fdinfo,target,before['inode'])
        phase='first_proc_locks_snapshot'
        raw,meta=read_leaf(journal,procroot,'locks',LOCKS_LIMIT,'proc_locks_first')
        result['locks_first']=project_locks(raw,key,pid)
        result['locks_first']['file_observation']=meta
        del raw
        names.verify()
        need(identity(target)==before and named_identity(lock_parent,
             'android-digitalis-actions.lock')==before,'FIXED_TARGET_CHANGED_BETWEEN_SNAPSHOTS')
        phase='second_proc_locks_snapshot'
        raw,meta=read_leaf(journal,procroot,'locks',LOCKS_LIMIT,'proc_locks_second')
        result['locks_second']=project_locks(raw,key,pid)
        result['locks_second']['file_observation']=meta
        del raw
        phase='final_current_names_and_self_view'
        result['target_fdinfo_after']=own_fdinfo(journal,fdinfo,target,before['inode'])
        need(result['target_fdinfo_after']['fields']==result['target_fdinfo_before']['fields'],
             'OWN_TARGET_FDINFO_CHANGED')
        need(os.readlink('self',dir_fd=procroot)==own_proc_name and
             os.getpid()==own_pid,'OWN_PROC_SELF_LINK_CHANGED')
        result['own_namespaces_after']=own_namespaces(proc)
        need(result['own_namespaces_after']==result['own_namespaces_before'],
             'OWN_NAMESPACE_VIEW_CHANGED')
        names.verify()
        result['target_after']=identity(target)
        result['named_after']=named_identity(lock_parent,'android-digitalis-actions.lock')
        need(result['target_after']==before and result['named_after']==before,
             'FIXED_TARGET_FINAL_IDENTITY_CHANGED')
        result['selected_rows_equal_at_two_samples']=(
            result['locks_first']['selected']==result['locks_second']['selected'])
        result['candidate_holder_PID_sets_equal_at_two_samples']=(
            result['locks_first']['candidate_holder_pids_from_this_view']==
            result['locks_second']['candidate_holder_pids_from_this_view'])
        result['observation_completed_seconds']=time.monotonic()-START
        tick()
        completed=True
    except BaseException as error:
        remember(result,phase,error)
    finally:
        journal.finish(result)
        try:
            if timer_set:
                signal.setitimer(signal.ITIMER_REAL,0)
            if handler_set:
                signal.signal(signal.SIGALRM,old_handler)
            result['timer_and_handler_restored']=True
        except BaseException as error:
            remember(result,'timer_restore',error)
        result['elapsed_seconds']=time.monotonic()-START
        if result['elapsed_seconds']>=HARD_SECONDS:
            remember(result,'completion_deadline',RuntimeError('FIXED_LOCK_METADATA_FINISHED_LATE'))
        result['collection_complete']=bool(completed and result['first_error'] is None and
            not result['secondary_errors'] and result['all_owned_FDs_closed'] and
            result['timer_and_handler_restored'])
    raw=(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    need(len(raw)<=OUTPUT_LIMIT,'FIXED_LOCK_METADATA_OUTPUT_BOUND')
    print(raw.decode('utf-8'),end='',flush=True)
    return 0 if result['collection_complete'] else 1

if __name__=='__main__':
    raise SystemExit(main())
