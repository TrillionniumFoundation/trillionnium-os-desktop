#!/usr/bin/env python3
"""One bounded Main identity diagnostic; no mutation, namespace entry, or Android command."""
import hashlib,json,os,select,stat,subprocess,time
DEADLINE=time.monotonic()+12
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
def main():
    result={'schema':1,'kind':'fixed-Main-framework-identity-observation01','old_epoch_sha256':'48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f','errors':[],'Main_mutations':0,'Android_commands':0,'namespace_entry':False,'private_log_or_UI_read':False,'old_epoch_reauthorized':False,'system_server_cause_proved':False}
    try:
        result['service_before']=service();result['cgroup_before']=cg()
        result['original_processes']={name:process(pid,birth) for name,(pid,birth) in EXPECTED.items()}
        z=result['original_processes']['zygote']
        if z.get('alive_identity_verified') and result['service_before']['properties'].get('InvocationID')=='67cdc2375f394012ad9d7f39b0d77426':
            raw=read('/proc/3588887/task/3588887/children',16384);items=raw.split()
            need(len(items)<=256 and all(x.isdigit() for x in items),'FIXED_ZYGOTE_CHILD_LIST_BOUND')
            ids=[int(x) for x in items];need(len(ids)==len(set(ids)),'DUPLICATE_ZYGOTE_CHILD')
            result['zygote_child_count']=len(ids);matches=[];raced=0
            for pid in ids:
                try:
                    first=statrow(pid);cmd=read('/proc/%d/cmdline'%pid,4096)
                    if cmd.split(b'\0',1)[0]!=b'system_server':continue
                    row=process(pid,first['start_ticks']);row['system_server_cmdline_exact']=True
                    row['same_cgroup_as_original_zygote']=row.get('cgroup')==z.get('cgroup')
                    row['same_mount_namespace_as_original_zygote']=row.get('namespaces',{}).get('mnt')==z['namespaces']['mnt']
                    row['same_root_identity_as_original_zygote']=row.get('root_identity')==z['root_identity']
                    matches.append(row)
                except (OSError,RuntimeError):raced+=1
            result['current_system_server_candidates']=matches;result['child_metadata_read_failures']=raced
            result['zygote_after_children']=process(3588887,80797153)
        result['service_after']=service();result['cgroup_after']=cg()
        result['service_identity_unchanged']=all(result['service_before']['properties'][k]==result['service_after']['properties'][k] for k in ('MainPID','ControlGroup','InvocationID'))
    except BaseException as e:result['errors'].append({'type':type(e).__name__,'code':str(e) if isinstance(e,RuntimeError) else 'FIXED_DIAGNOSTIC_READ_FAILED'})
    result['deadline_met']=time.monotonic()<DEADLINE
    raw=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode();need(len(raw)<=65536,'REPORT_BOUND');print(raw.decode(),end='',flush=True)
    return 0 if not result['errors'] and result['deadline_met'] else 1
raise SystemExit(main())
