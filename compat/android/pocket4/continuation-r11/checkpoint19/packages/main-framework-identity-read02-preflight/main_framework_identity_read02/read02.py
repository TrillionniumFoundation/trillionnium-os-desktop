#!/usr/bin/env python3
"""Bounded read-only framework discovery under one surviving, birth-pinned Android init."""
import hashlib,json,os,select,stat,subprocess,time
DEADLINE=time.monotonic()+20
EXPECTED={'daemon':(3588022,80796995),'launcher':(3588089,80797013),'presenter':(3588024,80796995),'android_init':(3588093,80797014),'zygote':(3588887,80797153),'surfaceflinger':(3588912,80797155),'system_server':(3589120,80797249)}
CG='/sys/fs/cgroup/system.slice/droidloomd.service'
PROPERTIES=('MainPID','ControlGroup','InvocationID','ActiveState','SubState','Result','NRestarts','ExecMainStartTimestampMonotonic','StateChangeTimestampMonotonic','MemoryCurrent','MemoryPeak','TasksCurrent')
STATUS_KEYS={'Uid','Gid','Groups','NSpid','CapInh','CapPrm','CapEff','CapBnd','CapAmb','Threads','State','PPid'}
def need(v,m):
    if not v:raise RuntimeError(m)
def check():need(time.monotonic()<DEADLINE,'DIAGNOSTIC_DEADLINE')
def read(path,limit):
    check();fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        chunks=[];n=0
        while True:
            check();b=os.read(fd,min(8192,limit+1-n))
            if not b:break
            chunks.append(b);n+=len(b);need(n<=limit,'FIXED_READ_BOUND')
        return b''.join(chunks)
    finally:os.close(fd)
def statrow(pid):
    b=read('/proc/%d/stat'%pid,8192);at=b.rfind(b') ')
    need(at>0 and b[:at].startswith(str(pid).encode()+b' ('),'PROC_STAT_SCHEMA')
    f=b[at+2:].split();need(len(f)>=20,'PROC_STAT_FIELDS')
    return {'pid':pid,'start_ticks':int(f[19]),'state':f[0].decode('ascii'),'ppid':int(f[1])}
def process(pid,birth):
    row={'pid':pid,'expected_start_ticks':birth};held=None
    try:
        first=statrow(pid);row['before']=first
        if birth is not None:need(first['start_ticks']==birth,'ORIGINAL_PID_REUSED')
        held=os.pidfd_open(pid,0)
        poll=select.poll();poll.register(held,select.POLLIN)
        need(not poll.poll(0),'PROCESS_ALREADY_DEAD')
        status=read('/proc/%d/status'%pid,65536).decode('ascii','strict')
        row['status']={k:v.strip() for k,v in (line.split(':',1) for line in status.splitlines() if ':' in line) if k in STATUS_KEYS}
        row['cgroup']=read('/proc/%d/cgroup'%pid,8192).decode('ascii','strict')
        row['namespaces']={k:os.readlink('/proc/%d/ns/%s'%(pid,k)) for k in ('mnt','pid','user')}
        st=os.stat('/proc/%d/root'%pid);row['root_identity']={'device':st.st_dev,'inode':st.st_ino}
        last=statrow(pid);row['after']=last
        need(first['start_ticks']==last['start_ticks'] and not poll.poll(0),'PROCESS_CHANGED_DURING_READ')
        row['alive_identity_verified']=True
    except OSError as e:row['error']={'type':type(e).__name__,'errno':e.errno}
    except RuntimeError as e:row['error']={'type':type(e).__name__,'code':str(e)}
    finally:
        if held is not None:os.close(held)
    return row
def service():
    check();argv=['/usr/bin/systemctl','show','droidloomd.service','--no-pager']+['--property='+p for p in PROPERTIES]
    p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','LANG':'C'})
    out=err=b'';timed=False
    try:out,err=p.communicate(timeout=min(3,max(.1,DEADLINE-time.monotonic())))
    except subprocess.TimeoutExpired:
        timed=True;p.kill();out,err=p.communicate(timeout=1)
    need(len(out)<=16384 and len(err)<=8192,'SERVICE_OUTPUT_BOUND')
    record={'argv':argv,'pid':p.pid,'joined':p.returncode is not None,'returncode':p.returncode,'timed_out':timed,'stdout_bytes':len(out),'stdout_sha256':hashlib.sha256(out).hexdigest(),'stderr_bytes':len(err),'stderr_sha256':hashlib.sha256(err).hexdigest()}
    need(not timed and p.returncode==0 and not err,'FIXED_SERVICE_QUERY_FAILED')
    rows=dict(line.split('=',1) for line in out.decode('ascii','strict').splitlines())
    need(set(rows)==set(PROPERTIES),'FIXED_SERVICE_FIELDS')
    return {'command':record,'properties':rows}
def cg():
    rows={}
    for name in ('memory.current','memory.peak','memory.events','memory.events.local','memory.max','memory.high','memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max','pids.current','pids.max','pids.events'):
        try:rows[name]=read(CG+'/'+name,8192).decode('ascii','strict').strip()
        except OSError as e:rows[name]={'errno':e.errno}
    return rows
INIT=3588093
INIT_BIRTH=80797014
MAIN_CGROUP='0::/system.slice/droidloomd.service'
EXACT_ZYGOTE_NAMES={b'zygote',b'zygote64',b'zygote32'}
def exact_cmd(pid):
    return read('/proc/%d/cmdline'%pid,4096).split(b'\0',1)[0]
def children(pid):
    raw=read('/proc/%d/task/%d/children'%(pid,pid),16384);items=raw.split()
    need(len(items)<=256 and all(x.isdigit() for x in items),'FIXED_CHILD_LIST_BOUND')
    ids=[int(x) for x in items];need(len(ids)==len(set(ids)),'DUPLICATE_CHILD')
    return ids
def scoped(row,anchor):
    group=row.get('cgroup','').strip()
    return bool(row.get('alive_identity_verified') and row.get('root_identity')==anchor['root_identity'] and row.get('namespaces',{}).get('pid')==anchor['namespaces']['pid'] and (group==MAIN_CGROUP or group.startswith(MAIN_CGROUP+'/')))
def main():
    result={'schema':1,'kind':'fixed-init-child-framework-discovery02','old_epoch_sha256':'48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f','errors':[],'Main_mutations':0,'Android_commands':0,'namespace_entry':False,'private_log_or_UI_read':False,'old_epoch_reauthorized':False,'new_epoch_authorized':False,'system_server_cause_proved':False,'zygote_candidates':[]}
    held_init=None
    try:
        result['boot_id_before']=read('/proc/sys/kernel/random/boot_id',128).decode('ascii','strict').strip()
        need(result['boot_id_before']=='981ff371-cd72-4f81-9be3-a862111afdb1','HOST_BOOT_CHANGED')
        result['service_before']=service();sv=result['service_before']['properties']
        need(sv['MainPID']=='3588022' and sv['ControlGroup']=='/system.slice/droidloomd.service' and sv['InvocationID']=='67cdc2375f394012ad9d7f39b0d77426' and sv['ActiveState']=='active' and sv['SubState']=='running','MAIN_SERVICE_CHANGED')
        result['cgroup_before']=cg()
        result['fixed_surviving_processes_before']={name:process(pid,birth) for name,(pid,birth) in EXPECTED.items() if name not in ('zygote','system_server')}
        need(all(row.get('alive_identity_verified') for row in result['fixed_surviving_processes_before'].values()),'SURVIVING_FIXED_IDENTITY_CHANGED')
        anchor=result['fixed_surviving_processes_before']['android_init']
        need(anchor['root_identity']=={'device':106,'inode':1} and anchor['namespaces']['pid']=='pid:[4026533288]' and anchor['namespaces']['mnt']=='mnt:[4026533284]' and anchor['cgroup'].strip()==MAIN_CGROUP,'INIT_SCOPE_CHANGED')
        held_init=os.pidfd_open(INIT,0);init_poll=select.poll();init_poll.register(held_init,select.POLLIN)
        need(not init_poll.poll(0) and statrow(INIT)['start_ticks']==INIT_BIRTH,'INIT_CHANGED_BEFORE_CHILDREN')
        initial_children=children(INIT);result['init_direct_child_count']=len(initial_children)
        result['unmatched_init_children']=0;result['init_child_read_races']=0
        for pid in initial_children:
            try:
                first=statrow(pid);name=exact_cmd(pid)
                if name not in EXACT_ZYGOTE_NAMES:
                    result['unmatched_init_children']+=1;continue
                need(len(result['zygote_candidates'])<8,'ZYGOTE_CANDIDATE_BOUND')
                row=process(pid,first['start_ticks'])
                row['known_cmdline_name']=name.decode('ascii')
                row['direct_child_of_fixed_init']=first['ppid']==INIT and row.get('before',{}).get('ppid')==INIT and row.get('after',{}).get('ppid')==INIT
                row['init_scope_verified']=scoped(row,anchor)
                row['known_cmdline_still_exact']=exact_cmd(pid)==name
                row['system_server_candidates']=[]
                result['zygote_candidates'].append(row)
                if not (row['direct_child_of_fixed_init'] and row['init_scope_verified'] and row['known_cmdline_still_exact']):continue
                held_z=None
                try:
                    held_z=os.pidfd_open(pid,0);z_poll=select.poll();z_poll.register(held_z,select.POLLIN)
                    need(not z_poll.poll(0) and statrow(pid)['start_ticks']==first['start_ticks'],'ZYGOTE_CHANGED_BEFORE_CHILDREN')
                    z_children=children(pid);row['direct_child_count']=len(z_children);row['unmatched_children']=0;row['child_read_races']=0
                    for child in z_children:
                        try:
                            child_first=statrow(child)
                            if exact_cmd(child)!=b'system_server':
                                row['unmatched_children']+=1;continue
                            need(len(row['system_server_candidates'])<8,'SYSTEM_SERVER_CANDIDATE_BOUND')
                            found=process(child,child_first['start_ticks'])
                            found['system_server_cmdline_exact']=exact_cmd(child)==b'system_server'
                            found['direct_child_of_verified_zygote']=child_first['ppid']==pid and found.get('before',{}).get('ppid')==pid and found.get('after',{}).get('ppid')==pid
                            found['init_scope_verified']=scoped(found,anchor)
                            row['system_server_candidates'].append(found)
                        except OSError:row['child_read_races']+=1
                    row['child_list_unchanged']=z_children==children(pid)
                    row['zygote_after_children']=process(pid,first['start_ticks'])
                    row['held_pidfd_live_after_children']=not bool(z_poll.poll(0))
                    need(row['zygote_after_children'].get('alive_identity_verified') and row['held_pidfd_live_after_children'] and exact_cmd(pid)==name,'ZYGOTE_CHANGED_DURING_CHILDREN')
                finally:
                    if held_z is not None:os.close(held_z)
            except OSError:result['init_child_read_races']+=1
        result['init_child_list_unchanged']=initial_children==children(INIT)
        result['init_after_children']=process(INIT,INIT_BIRTH)
        result['held_init_pidfd_live_after_children']=not bool(init_poll.poll(0))
        need(result['init_after_children'].get('alive_identity_verified') and result['held_init_pidfd_live_after_children'],'INIT_CHANGED_DURING_CHILDREN')
        result['old_framework_processes']={name:process(*EXPECTED[name]) for name in ('zygote','system_server')}
        result['service_after']=service();result['cgroup_after']=cg()
        result['boot_id_after']=read('/proc/sys/kernel/random/boot_id',128).decode('ascii','strict').strip()
        result['service_identity_unchanged']=all(result['service_before']['properties'][k]==result['service_after']['properties'][k] for k in ('MainPID','ControlGroup','InvocationID'))
        need(result['boot_id_before']==result['boot_id_after'] and result['service_identity_unchanged'],'SERVICE_OR_BOOT_CHANGED_DURING_READ')
    except BaseException as e:
        result['errors'].append({'type':type(e).__name__,'code':str(e) if isinstance(e,RuntimeError) else 'FIXED_DISCOVERY_READ_FAILED'})
    finally:
        if held_init is not None:os.close(held_init)
    result['deadline_met']=time.monotonic()<DEADLINE
    raw=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode();need(len(raw)<=65536,'REPORT_BOUND');print(raw.decode(),end='',flush=True)
    return 0 if not result['errors'] and result['deadline_met'] else 1
raise SystemExit(main())
