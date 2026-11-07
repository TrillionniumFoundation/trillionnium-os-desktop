#!/usr/bin/python3 -I
"""Pinned read-only task snapshot and normal removal of one proven new leaf.

No launch, force-stop, input, permission, account, data, or lifecycle operation.
The only removal target must be absent in this run's pre-launch snapshot and
present in the matching successful native launch receipt.
"""
import argparse, fcntl, hashlib, json, os, re, resource, stat, sys, time, types
from datetime import datetime, timezone
from pathlib import Path

WORK=Path('/home/alex/work/pocket4-app-production-20261104/native-acceptance-09')
RUNS={'remaining':WORK.parent/'native-baseline-09'}
RUN=None
OLD=Path('/home/alex/work/pocket4-app-production-20261103')
HELPER=Path('/usr/local/libexec/android-digitalis-observe-helper')
HELPER_SHA='088be6d783e80006645a05b8c5b90cd100d3e38b6f3d4634dd499ab1de7898ae'
PINS={HELPER:HELPER_SHA,
 WORK/'verified-main.json':'8531fcf3209765145727953784231163dbf6c7a563259db25c903ab1aa7c2a52',
 WORK/'remaining-13-plan.json':'908078663b698c6d9cefe703ee15cb869173815a7ac38550358d1efa6919be47',
 WORK.parent/'native-baseline-07/epoch-run-result.json':'580e002cbbb0ec566f08e519eaa4f9a753ae8c7a6a6054993cb81cb51ec956ee',
 WORK.parent/'native-baseline-06/epoch-run-result.json':'ec752dcb79973ab1616d9666b464948b1379eb87f50f4344ae12ac6cbd76cc90',
 WORK.parent/'native-baseline-05/epoch-run-result.json':'3e5d18cad22fcbf2b4c0c0d5b6c63b374d7ee4f74569e37e5d41c417f8624649',
 Path('/usr/bin/droidloomctl'):'f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79',
 OLD/'normal-task-close-02/result.json':'c5ab735b470adf3c9fbab24f48ee41cd4980dee5ab449fa19c9b6d5ee707204d',
 OLD/'native-baseline-03/guard-stop.json':'5c11e5fe6a852b335942c2b199ac3d08493e2bc022cf60b163bf1ea4616cbbc0'}
HOST_PID,INIT_PID=2773535,2773545
TICKS={HOST_PID:78212591,INIT_PID:78212593}
FIXTURE='local.pocket4.fixture'
FIXTURE_COMPONENT=FIXTURE+'/local.pocket4.fixture.ProbeActivity'
NAMESPACES={'pid':'pid:[4026533368]','mnt':'mnt:[4026533318]'}

def entries(stage):
    require(stage in RUNS,'STAGE_INVALID')
    if stage=='smoke':
        return [{'entry_id':'fixture-'+mode,'package':FIXTURE,'component':FIXTURE_COMPONENT,'mode':mode}
                for mode in ('implicit','explicit')]
    data=(WORK/'remaining-13-plan.json').read_bytes()
    require(sha(data)==PINS[WORK/'remaining-13-plan.json'],'PLAN_CHANGED')
    return [dict(row,entry_id=row['package'],mode='explicit') for row in json.loads(data)['plan']]

def now():return datetime.now(timezone.utc).isoformat()
def sha(data):return hashlib.sha256(data).hexdigest()
def require(ok,code):
    if not ok:raise ValueError(code)

def verify_identity():
    for path,expected in PINS.items():require(sha(path.read_bytes())==expected,'PIN_DRIFT')
    for pid,expected in TICKS.items():
        raw=Path('/proc/%d/stat'%pid).read_text()
        require(int(raw[raw.rfind(')')+2:].split()[19])==expected,'MAIN_CHANGED')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='981ff371-cd72-4f81-9be3-a862111afdb1','BOOT_CHANGED')
    ns_pid=[l for l in Path('/proc/%d/status'%INIT_PID).read_text().splitlines() if l.startswith('NSpid:')]
    require(len(ns_pid)==1 and ns_pid[0].split()[-1]=='1','NOT_NAMESPACE_INIT')
    for name,value in NAMESPACES.items():
        require(os.readlink('/proc/%d/ns/%s'%(INIT_PID,name))==value,'NAMESPACE_CHANGED')
    cgroup=Path('/sys/fs/cgroup/system.slice/droidloomd.service').stat()
    require((cgroup.st_dev,cgroup.st_ino)==(30,25507479),'CGROUP_CHANGED')
    verified=json.loads((WORK/'verified-main.json').read_bytes())
    for item in verified['pair'].values():
        for location in ('host','guest'):
            spec=item[location];p=Path(spec['path']);st=p.stat()
            require((st.st_dev,st.st_ino,st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode),st.st_nlink)==
                    (spec['device'],spec['inode'],spec['uid'],spec['gid'],spec['mode'],1),'NATIVE_PAIR_METADATA_CHANGED')
            require(st.st_size==spec['bytes'] and sha(p.read_bytes())==spec['sha256'],'NATIVE_PAIR_CHANGED')

def parse_stacks(raw):
    roots={};tasks=set()
    for block in re.split(r'(?=^RootTask id=)',raw,flags=re.M):
        if not block.startswith('RootTask id='):continue
        head=block.splitlines()[0]
        rid=int(re.search(r'^RootTask id=(\d+)\b',head)[1])
        display=int(re.search(r'\bdisplayId=(\d+)\b',head)[1])
        user=int(re.search(r'\buserId=(\d+)\b',head)[1]);children=[]
        for line in block.splitlines():
            match=re.match(r'\s*taskId=(\d+):\s+(\S+)\s+.*?\buserId=(\d+)\b',line)
            require(not re.match(r'\s*taskId=',line) or match is not None,'UNPARSED_TASK_LINE')
            if match:
                tid=int(match[1]);require(tid not in tasks,'DUPLICATE_TASK');tasks.add(tid)
                children.append({'id':tid,'component':match[2],'user':int(match[3])})
        require(rid not in roots,'DUPLICATE_ROOT')
        roots[rid]={'display':display,'user':user,'freeform':'mWindowingMode=freeform' in block,'children':children}
    require(bool(roots) and bool(tasks),'UNRECOGNIZED_STACK_LIST')
    return roots,tasks

def exact_leaf(roots,task,pkg):
    root=roots.get(task)
    return bool(root and root['display']==0 and root['user']==0 and root['freeform']
                and len(root['children'])==1 and root['children'][0]['id']==task
                and root['children'][0]['user']==0
                and root['children'][0]['component'].split('/')[0]==pkg)

def native_task(value):
    require(type(value) is dict and value.get('ok') is True and value.get('host_pid')==HOST_PID
            and value.get('state')=='running' and value.get('outcome_unknown') is not True,'NATIVE_RECEIPT_INVALID')
    match=re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)',value.get('launch',''))
    require(match is not None and int(match[3])==0,'NATIVE_TASK_ID_INVALID')
    return int(match[4])

def private_bytes(path):
    require(path.resolve()==path and path.is_relative_to(RUN),'EVIDENCE_PATH_INVALID')
    st=path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==1000
            and stat.S_IMODE(st.st_mode)==0o600 and st.st_size<=4*1024*1024,'EVIDENCE_METADATA_INVALID')
    return path.read_bytes()

def source_scope(stage,entry_id):
    selected=[row for row in entries(stage) if row['entry_id']==entry_id]
    require(len(selected)==1,'ENTRY_NOT_IN_BATCH')
    item=selected[0];package=item['package'];folder=RUN/entry_id
    pre_raw=private_bytes(folder/'task-before.stdout')
    pre=json.loads(pre_raw);launch_raw=private_bytes(folder/'launch.stdout');launch=json.loads(launch_raw)
    pre_capture=json.loads(private_bytes(folder/'task-before.capture.json'))
    launch_capture=json.loads(private_bytes(folder/'launch.capture.json'))
    for capture,raw in ((pre_capture,pre_raw),(launch_capture,launch_raw)):
        require(capture.get('rc')==0 and capture.get('stdout_sha256')==sha(raw)
                and not any(capture.get(k) is not False for k in ('timed_out','output_limit','spawn_failed','interrupted')),
                'SOURCE_CAPTURE_UNCERTAIN')
    command=['/usr/bin/droidloomctl','launch',package]
    if item['mode']=='explicit':command+=['--component',item['component']]
    command+=['--json']
    require(launch_capture.get('argv')==command,'SOURCE_LAUNCH_SCOPE_CHANGED')
    require(pre_capture.get('argv')==['/usr/bin/sudo','-n','/usr/bin/python3','-I',str(WORK/'task_scope.py'),
                                    'snapshot','--stage',stage,'--entry',entry_id],
            'SOURCE_SNAPSHOT_SCOPE_CHANGED')
    end=datetime.fromisoformat(pre_capture['ended_utc']);begin=datetime.fromisoformat(launch_capture['started_utc'])
    require(end.tzinfo is not None and begin.tzinfo is not None and 0<=(begin-end).total_seconds()<=30,
            'SOURCE_SEQUENCE_INVALID')
    require(0<=(datetime.now(timezone.utc)-begin).total_seconds()<=150,'SOURCE_LAUNCH_TOO_OLD')
    require(pre.get('ok') is True and pre.get('host_pid')==HOST_PID and pre.get('init_pid')==INIT_PID
            and pre.get('entry_id')==entry_id and pre.get('package')==package
            and pre.get('start_ticks')=={str(k):v for k,v in TICKS.items()},'SOURCE_GENERATION_CHANGED')
    roots,tasks=parse_stacks(pre['raw_stacks'])
    require(pre.get('task_ids')==sorted(tasks),'SOURCE_TASK_SET_INVALID')
    return folder,package,native_task(launch),roots,tasks

def load_helper():
    verify_identity();raw=HELPER.read_bytes();require(sha(raw)==HELPER_SHA,'HELPER_CHANGED')
    module=types.ModuleType('verified_scope_helper');module.__file__=str(HELPER)
    exec(compile(raw,str(HELPER),'exec'),module.__dict__)
    discover=module.discover
    def pinned_discover():
        verify_identity();init,env,status=discover()
        require(init==INIT_PID and status.get('host_pid')==HOST_PID,'DISCOVERY_CHANGED')
        verify_identity();return init,env,status
    module.discover=pinned_discover
    return module

def create_intent(folder,value):
    fd=os.open(folder/'cleanup.intent.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),1000,1000)

def diagnostic_snapshot(helper,package):
    """Read one bounded package UID/exit/event/crash snapshot; never clear logs."""
    started=now()
    clock=helper.arun(['/system/bin/date','+%s %z'],timeout=5).decode('ascii','strict').strip()
    match=re.fullmatch(r'(\d+) ([+-]\d{4})',clock)
    require(match is not None,'GUEST_CLOCK_UNKNOWN')
    require(abs(time.time()-int(match[1]))<=3,'GUEST_CLOCK_SKEW')
    uid_raw=helper.arun(['/system/bin/cmd','package','list','packages','-U','--user','0',package],timeout=8).decode('utf-8','strict')
    matches=[m for line in uid_raw.splitlines()
             if (m:=re.fullmatch(r'package:(\S+)\s+uid:(\d+)',line.strip())) and m[1]==package]
    require(len(matches)==1,'PACKAGE_UID_UNKNOWN')
    exits=helper.arun(['/system/bin/dumpsys','activity','exit-info',package],timeout=8).decode('utf-8','strict')
    events=helper.arun(['/system/bin/logcat','-b','events','-d','-v','epoch','-t','512'],timeout=8).decode('utf-8','strict')
    crashes=helper.arun(['/system/bin/logcat','-b','crash','-d','-v','epoch','-t','512'],timeout=8).decode('utf-8','strict')
    verify_identity()
    return {'ok':True,'package':package,'uid':int(matches[0][2]),'user':0,
            'host_pid':HOST_PID,'init_pid':INIT_PID,'start_ticks':{str(k):v for k,v in TICKS.items()},
            'guest_epoch_seconds':int(match[1]),'guest_timezone_offset':match[2],
            'started_utc':started,'ended_utc':now(),'log_line_limit':512,
            'exit_info':exits,'events':events,'crash_buffer':crashes,'read_only':True}

def wait_for_removal(read_stacks,task,package,before_tasks,record,*,clock=time.monotonic,sleep=time.sleep):
    """Observe asynchronous completion; never send or resend a removal command.

    Eight-second polling window, no more than 32 read attempts. Existing helper
    discovery/read deadlines and the caller's bounded command remain in force.
    A long in-flight read may overrun the nominal window; no new read starts once
    the deadline expires. Every observation is retained before being accepted.
    """
    started=clock();deadline=started+8.0;others=set(before_tasks)-{task};count=0
    while count<32:
        remaining=deadline-clock()
        require(remaining>0,'CLEANUP_COMPLETION_DEADLINE_UNKNOWN')
        sleep(min(0.25,remaining))
        remaining=deadline-clock()
        require(remaining>0,'CLEANUP_COMPLETION_DEADLINE_UNKNOWN')
        raw=read_stacks(min(3.0,remaining));count+=1
        try:roots,tasks=parse_stacks(raw)
        except Exception as exc:
            record({'kind':'readback','at':now(),'observation':count,'elapsed_seconds':clock()-started,
                    'raw_stacks':raw,'parse_error_type':type(exc).__name__})
            raise
        absent=task not in roots and task not in tasks
        record({'kind':'readback','at':now(),'observation':count,'elapsed_seconds':clock()-started,
                'raw_stacks':raw,'root_ids':sorted(roots),'task_ids':sorted(tasks),'target_absent':absent})
        require(tasks-{task}==others,'OTHER_TASK_SET_CHANGED')
        if absent:return {'observations':count,'elapsed_seconds':clock()-started,'task_ids_after':sorted(tasks)}
        root=roots.get(task)
        shrinking=bool(root and task not in tasks and root['display']==0 and root['user']==0
                       and root['freeform'] and root['children']==[])
        require(exact_leaf(roots,task,package) or shrinking,'TARGET_SCOPE_CHANGED_DURING_COMPLETION')
    raise ValueError('CLEANUP_COMPLETION_OBSERVATION_LIMIT_UNKNOWN')

def main():
    global RUN
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('snapshot','cleanup','diagnostics'))
    parser.add_argument('--stage',choices=tuple(RUNS),required=True);parser.add_argument('--entry',required=True)
    args=parser.parse_args()
    RUN=RUNS[args.stage]
    require(os.geteuid()==0,'ROOT_REQUIRED')
    require(resource.getrlimit(resource.RLIMIT_AS)[0]==resource.RLIM_INFINITY,'AS_LIMIT_NOT_ALLOWED')
    result={'ok':False,'automatic_retry':False,'attempted_task_ids':[],'remove_acknowledged':False,
            'verified_removed_task_ids':[],'outcome_unknown':False,'r3_stop_cleared':False}
    lock=None;journal=None
    try:
        helper=load_helper()
        selected=[row for row in entries(args.stage) if row['entry_id']==args.entry]
        require(len(selected)==1,'ENTRY_NOT_IN_BATCH')
        package=selected[0]['package']
        if args.operation=='snapshot':
            raw=helper.arun(['/system/bin/cmd','activity','stack','list'],timeout=15).decode('utf-8','strict')
            roots,tasks=parse_stacks(raw)
            result.update(ok=True,host_pid=HOST_PID,init_pid=INIT_PID,entry_id=args.entry,package=package,
                          start_ticks={str(k):v for k,v in TICKS.items()},raw_stacks=raw,
                          root_ids=sorted(roots),task_ids=sorted(tasks),at=now())
        elif args.operation=='diagnostics':
            result.update(diagnostic_snapshot(helper,package))
        else:
            folder,package,task,pre_roots,pre_tasks=source_scope(args.stage,args.entry)
            result.update(package=package,entry_id=args.entry,task_id=task)
            if task in pre_tasks or task in pre_roots:
                result.update(ok=True,state='preexisting_task_preserved')
            else:
                lock=os.open('/run/lock/android-digitalis-actions.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                raw=helper.arun(['/system/bin/cmd','activity','stack','list'],timeout=15).decode('utf-8','strict')
                roots,tasks=parse_stacks(raw)
                if task not in roots and task not in tasks:
                    result.update(ok=True,state='new_task_already_absent')
                else:
                    require(exact_leaf(roots,task,package),'NEW_TASK_TOPOLOGY_UNCONFIRMED')
                    fd=os.open(folder/'cleanup-observations.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    journal=os.fdopen(fd,'w');os.fchown(journal.fileno(),1000,1000)
                    def record(value):
                        journal.write(json.dumps(value,ensure_ascii=False)+'\n');journal.flush();os.fsync(journal.fileno())
                    record({'kind':'before_remove','at':now(),'raw_stacks':raw,'root_ids':sorted(roots),'task_ids':sorted(tasks)})
                    create_intent(folder,{'at':now(),'task_id':task,'package':package,
                                         'pre_launch_absent':True,'automatic_retry':False,
                                         'command':['/system/bin/cmd','activity','stack','remove',str(task)]})
                    result['attempted_task_ids']=[task];result['outcome_unknown']=True
                    returned=helper.arun(['/system/bin/cmd','activity','stack','remove',str(task)],timeout=15)
                    result['remove_acknowledged']=True
                    record({'kind':'remove_ack','at':now(),'returncode':0,'stdout_sha256':sha(returned),'remove_calls':1})
                    def read_stacks(timeout):
                        return helper.arun(['/system/bin/cmd','activity','stack','list'],timeout=timeout).decode('utf-8','strict')
                    completed=wait_for_removal(read_stacks,task,package,tasks,record)
                    verify_identity()
                    result.update(ok=True,state='new_leaf_removed_and_verified',outcome_unknown=False,
                                  verified_removed_task_ids=[task],other_task_ids_preserved=True,
                                  task_ids_before=sorted(tasks),**completed)
    except BaseException as exc:
        result.update(ok=False,error_type=type(exc).__name__,error=str(exc)[:180])
    finally:
        if journal is not None:journal.close()
        if lock is not None:os.close(lock)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['ok'] else 2

if __name__=='__main__':raise SystemExit(main())
