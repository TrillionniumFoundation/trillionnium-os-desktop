#!/usr/bin/python3
"""Independent diskless guest check; no host install, module or policy load."""
import fcntl, hashlib, json, os, pathlib, select, signal, stat, subprocess, sys, time

B = pathlib.Path('/home/alex/work/p4-context-provider-runtime-8764-r1')
MODE = sys.argv[1]
assert MODE == 'baseline'
LOCK_FD = int(sys.argv[2])
assert os.getuid() == os.geteuid() == 1000
ls = os.fstat(LOCK_FD)
assert stat.S_ISREG(ls.st_mode) and ls.st_uid == 0 and ls.st_nlink == 1 and ls.st_size == 0
assert ls.st_ino == 41719533 and stat.S_IMODE(ls.st_mode) == 0o600
fcntl.flock(LOCK_FD, fcntl.LOCK_EX | fcntl.LOCK_NB)
os.umask(0o077)
D = B / (MODE + '-vm-r5')
D.mkdir(mode=0o700)
UNIT = 'p4-context-runtime-8764-' + MODE + '-r5.service'
DESC = 'Independent diskless p4ctx1 baseline context ancillary baseline 8764-r5'
R = {'schema':'p4ctx1-context-provider-baseline-runtime-v5', 'mode':MODE,
     'started_ns':time.time_ns(), 'Android_started':False, 'guest_disks':0,
     'guest_network_devices':0, 'host_installations':0, 'host_policy_loads':0,
     'host_module_loads':0, 'host_reboots':0, 'lock_inode':ls.st_ino,
     'unit':UNIT, 'errors':[], 'samples':[]}
def need(x,m):
    if not x: raise RuntimeError(m)
def run(argv, timeout=20):
    p=subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    need(len(p.stdout)+len(p.stderr)<2*1024**2,'output bound')
    return {'argv':argv,'rc':p.returncode,'stdout':p.stdout.decode(errors='replace'),'stderr':p.stderr.decode(errors='replace')}
def pin(p, expected=None):
    p=pathlib.Path(p); a=p.lstat()
    need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_size<64*1024**2,'regular bounded input '+str(p))
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s=os.fstat(fd); need((s.st_dev,s.st_ino)==(a.st_dev,a.st_ino),'changed input identity')
        with os.fdopen(os.dup(fd),'rb') as f: data=f.read()
        z=p.lstat(); need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns),'changed input')
    finally: os.close(fd)
    r={'path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'dev':a.st_dev,'ino':a.st_ino}
    if expected: need((r['bytes'],r['sha256'])==expected,'pin mismatch '+str(p))
    return r
def create(p,data):
    if not isinstance(data,bytes):data=(json.dumps(data,indent=2,sort_keys=True)+'\n').encode()
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data); f.flush(); os.fsync(f.fileno())
    return pin(p)
def host():
    return {'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'kernel':os.uname().release,'active_lsm':pathlib.Path('/sys/kernel/security/lsm').read_text().strip()}
def qemus():
    found=[]
    for p in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            a=(p/'cmdline').read_bytes().split(b'\0')
            if a and os.path.basename(a[0].decode()).startswith('qemu-system'):found.append({'pid':int(p.name),'args':[x.decode() for x in a if x]})
        except (OSError,UnicodeError):pass
    return found
def state():
    r=run(['/usr/bin/systemctl','--user','show',UNIT,'--property=LoadState,ActiveState,SubState,MainPID,InvocationID,Description,ControlGroup,Result,ExecMainStatus,MemoryMax,MemorySwapMax,CPUQuotaPerSecUSec,CPUAffinity,TasksMax,KillMode,RuntimeMaxUSec,MemoryPeak'])
    s=dict(x.split('=',1) for x in r['stdout'].splitlines() if '=' in x)
    cg=s.get('ControlGroup');s['resources']={}
    if cg:
        p=pathlib.Path('/sys/fs/cgroup'+cg)
        for n in ('memory.events','memory.current','memory.peak','cpu.stat','pids.current','cgroup.events'):
            try:s['resources'][n]=(p/n).read_text()
            except FileNotFoundError:pass
    return s
def cpio(entries):
    buf=bytearray()
    for ino,(name,mode,data,maj,minr) in enumerate(entries+[('TRAILER!!!',0,b'',0,0)],1):
        n=name.encode()+b'\0'; fields=[ino,mode,0,0,2 if stat.S_ISDIR(mode) else 1,0,len(data),0,0,maj,minr,len(n),0]
        buf+=b'070701'+''.join('%08x'%v for v in fields).encode()+n
        buf+=b'\0'*((-len(buf))%4);buf+=data;buf+=b'\0'*((-len(buf))%4)
    buf+=b'\0'*((-len(buf))%512);return bytes(buf)

launcher=None; pidfd=None; invocation=None; actual=None; cg=None; stopped=False
def interrupt(signum, frame): raise RuntimeError('controller signal '+str(signum))
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupt)
try:
    R['host_before']=host()
    R['before_qemu']=qemus();need(not R['before_qemu'],'another QEMU active; no concurrent launch')
    need(os.access('/dev/kvm',os.R_OK|os.W_OK),'KVM unavailable')
    need(len(os.sched_getaffinity(0))>=4 and {20,21,22,23}.issubset(os.sched_getaffinity(0)),'CPU reserve unavailable')
    mem=int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
    need(mem>=3*1024**3,'memory reserve unavailable')
    R['admission']={'memory_available_bytes':mem,'cpus':sorted(os.sched_getaffinity(0)),'qemu_affinity':[20,21],'guest_memory_mib':768,'cpu_quota_percent':200,'memory_max':1610612736}
    R['unit_before']=state();need(R['unit_before'].get('LoadState')=='not-found','unit already exists')
    normal_pin = pin(B / 'build-r5/result.json', (21188, '0bde85c23e49afd99873923892c3d6404c9cfd0ab2fbc6e7c27ecfd1ddaeda39'))
    normal = json.loads(pathlib.Path(normal_pin['path']).read_bytes())
    need(normal['passed'] and normal['inputs_unchanged'] and len(normal['commands']) == 12,
         'qualified ordinary static/no-load build required')
    need([row['exit_code'] for row in normal['commands']] == [0,0,0,64,0,0,64,0,0,64,0,0] and
         all(row['pidfd_exit'] for row in normal['commands']), 'normal compiler or wrong-PID guard failed')
    unit = 'p4-context-probe-8764-r5-build.service'
    prior = run(['/usr/bin/systemctl', '--user', 'show', unit,
                 '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'])
    prior_state = dict(line.split('=', 1) for line in prior['stdout'].splitlines() if '=' in line)
    need(prior_state.get('ActiveState') in ('inactive', 'failed') and prior_state.get('MainPID') == '0' and
         prior_state.get('ControlGroup') == '' and not pathlib.Path(normal['cgroup']).exists(), 'ordinary compiler cgroup not retired')
    prior_cgroup = normal['cgroup'].removeprefix('/sys/fs/cgroup')
    remaining = []
    for proc in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            if proc.stat().st_uid != 1000: continue
            if any(line.split('::',1)[-1] == prior_cgroup or line.split('::',1)[-1].startswith(prior_cgroup + '/')
                   for line in (proc/'cgroup').read_text().splitlines()): remaining.append(int(proc.name))
        except FileNotFoundError: pass
    need(not remaining, 'ordinary compiler descendants remain')
    R['normal_build_retirement'] = {'unit': prior_state, 'cgroup_absent': True, 'remaining_pids': remaining}
    inputs={'kernel':pin(B/'baseline-artifacts/bzImage',(17142272,'1724c52b575e4574b40598ba751ab6d9410b1efbdb29e67c2634b2e615a70d5e')),
            'module':pin(B/'baseline-artifacts/binder_linux.ko',(3826912,'1919a4d2898537f9c7da6cf57969315cdaa9980f566ffafa740043d89e3d239d')),
            'controller':pin(__file__), 'normal_result':normal_pin,
            'source_packet':pin(B/'control/build-inputs-r5.json',(158854,'5de24cacc89838d5bbf2446a7b2f6d1bbe3ad3039dbca452788cae14e4fb4d9d')),
            'init':pin(B/'build-r5/context-probe-baseline',(903968,'419ed41f93764bcbb8f90e738bf85e126135c0913b5585416276a66049325904')),
            'aa_policy':pin(B/'build-r5/context-apparmor.bin',(13650,'e855ef63544cfd87f48d2ddd4078a291fd0734b67d73f49fede7829a52a7a95c')),
            'selinux_policy':pin(B/'build-r5/context-selinux.bin',(18008,'19bbb3a89b9895fa0055b320fc5e20d5d1c559ebb04c6c81c268fe2732d433ec'))}
    entries=[(n,stat.S_IFDIR|0o755,b'',0,0) for n in ('.','dev','proc','sys')]
    entries += [('dev/console',stat.S_IFCHR|0o600,b'',5,1),
                ('init',stat.S_IFREG|0o755,pathlib.Path(inputs['init']['path']).read_bytes(),0,0),
                ('binder_linux.ko',stat.S_IFREG|0o400,pathlib.Path(inputs['module']['path']).read_bytes(),0,0),
                ('context-apparmor.bin',stat.S_IFREG|0o400,pathlib.Path(inputs['aa_policy']['path']).read_bytes(),0,0),
                ('context-selinux.bin',stat.S_IFREG|0o400,pathlib.Path(inputs['selinux_policy']['path']).read_bytes(),0,0),
                ('p4-context-marker',stat.S_IFREG|0o444,b'p4-context-provider-8764-diskless-v1\n',0,0),
                ('p4-context-arm',stat.S_IFREG|0o444,b'combined\n',0,0)]
    R['inputs']=inputs
    R['initramfs']=create(D/'initramfs.cpio',cpio(entries))
    q=['/usr/bin/qemu-system-x86_64','-no-user-config','-nodefaults','-machine','q35,accel=kvm','-cpu','host','-m','768','-smp','2','-display','none','-serial','stdio','-monitor','none','-nic','none','-no-reboot',
       '-smbios','type=1,manufacturer=Pocket4KernelQualification,product=P4Context8764Diskless,serial=p4-context-provider-8764-r1',
       '-kernel',str(B/'baseline-artifacts/bzImage'),'-initrd',str(D/'initramfs.cpio'),'-append',
       'console=ttyS0,115200 rdinit=/init panic=1 oops=panic lsm=landlock,lockdown,yama,integrity,apparmor,selinux,bpf apparmor=1 selinux=1 enforcing=1 audit=1 loglevel=3']
    R['qemu_argv']=q
    argv=['/usr/bin/systemd-run','--user','--unit='+UNIT,'--description='+DESC,'--wait','--pipe','--collect','--quiet','-p','MemoryMax=1536M','-p','MemorySwapMax=0','-p','CPUQuota=200%','-p','CPUAffinity=20-21','-p','TasksMax=64','-p','KillMode=control-group','-p','RuntimeMaxSec=240','-p','TimeoutStopSec=10','-p','OOMPolicy=stop','-p','Nice=15','-p','UMask=0077',*q]
    R['launch_argv']=argv
    with open(D/'serial.log','xb') as out,open(D/'launcher.stderr','xb') as err:
        launcher=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
        start=time.monotonic(); last=0
        while launcher.poll() is None and time.monotonic()-start<255:
            s=state();now=time.monotonic()
            if s.get('InvocationID'):
                need(s.get('Description')==DESC,'unit identity differs')
                if invocation:need(invocation==s['InvocationID'],'unit invocation changed')
                invocation=s['InvocationID'];cg=s.get('ControlGroup') or cg
            p=int(s.get('MainPID','0') or 0)
            if p and actual is None:
                try:
                    exe=os.readlink('/proc/%d/exe'%p)
                    if os.path.basename(exe).startswith('qemu-system'):
                        actual={'pid':p,'exe':exe,'starttime':pathlib.Path('/proc/%d/stat'%p).read_text().split(') ')[1].split()[19],'affinity':sorted(os.sched_getaffinity(p)),'invocation':invocation}
                        need(actual['affinity']==[20,21],'unexpected QEMU affinity')
                        pidfd=os.pidfd_open(p,0);R['actual_process']=actual
                except (FileNotFoundError,PermissionError) as e:
                    R['exec_observation_pending']=R.get('exec_observation_pending',0)+1
            if now-last>=1:
                R['samples'].append(s);last=now
            time.sleep(0.15)
        need(launcher.poll() is not None,'VM exceeded controller deadline')
        R['launcher_exit']=launcher.wait(timeout=10)
    need(actual is not None and pidfd is not None,'QEMU process identity not captured')
    need(R['launcher_exit']==0,'VM launcher failed')
    need(select.select([pidfd],[],[],0)[0],'actual QEMU not retired')
    R['actual_qemu_exited']=True
    log=(D/'serial.log').read_text(errors='replace')
    need(len(log)<4*1024**2,'guest log bound exceeded')
    boots=[json.loads(line[len('P4CTX_BOOT '):]) for line in log.splitlines() if line.startswith('P4CTX_BOOT ')]
    cases=[json.loads(line[len('P4CTX_CASE '):]) for line in log.splitlines() if line.startswith('P4CTX_CASE ')]
    summaries=[json.loads(line[len('P4CTX_SUMMARY '):]) for line in log.splitlines() if line.startswith('P4CTX_SUMMARY ')]
    R['guest_boot']=boots;R['guest_cases']=cases;R['guest_summary']=summaries
    need(len(boots)==1 and boots[0]['kernel']=='7.0.14-p4ctx1' and boots[0]['arm']=='combined' and
         boots[0]['selinux_enforcing']=='1' and boots[0]['lsm'].index('apparmor') < boots[0]['lsm'].index('selinux'),
         'actual AppArmor-first / SELinux enforcing baseline boot required')
    need(len(summaries)==1 and summaries[0]['setup_error']==0, 'guest setup failed')
    need(len(cases)==47 and len({case['name'] for case in cases})==47 and summaries[0]['cases']==47,
         'complete finite baseline controls required')
    expected_failures={'scm_selected_stream_queued_before_accept','scm_selected_dgram_queued_identity','ip_passsec_selected_cipso_after_fd_netns_transfer','stream_typed_boundary_without_credentials','stream_typed_boundary_credentials_pidfd','stream_typed_boundary_credentials_pidfd_rights'}
    failed={case['name'] for case in cases if not case['passed']}
    R['baseline_expected_missing_typed_ancillary'] = sorted(expected_failures)
    R['guest_all_cases_passed'] = not failed
    R['production_acceptance'] = False
    need(failed==expected_failures and summaries[0]['failed']==6 and summaries[0]['passed']==41,
         'baseline result differs beyond the original omitted typed SCM path')
    need(all(case['error']==0 and 'SCM=[,] counts=[0,0]' in case['detail'] for case in cases
             if case['name'].startswith('scm_selected_')), 'baseline SCM negative is confounded by another failure')
    need(all(case['error']==71 and 'creator_caps_zero=1' in case['detail'] and 'MSG_WAITALL PEEK then consume typed boundary' in case['detail'] for case in cases if case['name'].startswith('stream_typed_boundary_')),
         'baseline stream controls did not reach real data path')
    packet=next(case for case in cases if case['name']=='ip_passsec_selected_cipso_after_fd_netns_transfer')
    need(packet['error']==0 and 'payload=28 SCM= count=0' in packet['detail'], 'baseline IP negative is confounded')
    need(not any(text in log for text in ('BUG:','Oops:','Kernel panic','WARNING: CPU:')),
         'kernel diagnostic fault in finite baseline')
    R['passed']=True
except BaseException as e:
    R['errors'].append({'type':type(e).__name__,'message':str(e)});R['passed']=False
finally:
    try:
        s=state()
        if s.get('ActiveState') in ('active','activating','deactivating'):
            need(invocation and s.get('InvocationID')==invocation and s.get('Description')==DESC,'cannot retire unknown unit identity')
            R['stop']=run(['/usr/bin/systemctl','--user','stop',UNIT],timeout=20);stopped=True
        if launcher and launcher.poll() is None:launcher.wait(timeout=15)
        if pidfd is not None:
            R['actual_qemu_exited']=bool(select.select([pidfd],[],[],0)[0]);os.close(pidfd)
        R['unit_after']=state()
        R['cgroup_retired']=bool(cg) and not pathlib.Path('/sys/fs/cgroup'+cg).exists()
        R['owned_unit_retired']=R['unit_after'].get('ActiveState') in ('inactive','failed') and not int(R['unit_after'].get('MainPID','0') or 0) and R['cgroup_retired']
        R['host_after']=host();R['host_identity_unchanged']=R.get('host_before')==R['host_after']
        R['after_qemu']=qemus()
        events=[dict(line.split() for line in sample.get('resources',{}).get('memory.events','').splitlines())
                for sample in R['samples'] if sample.get('resources',{}).get('memory.events')]
        R['memory_events_observed']=events
        R['memory_events_clean']=bool(events) and all(all(event.get(key)=='0' for key in ('oom','oom_kill','oom_group_kill')) for event in events)
        if R['after_qemu'] or not R['memory_events_clean']: R['passed']=False
        R['inputs_unchanged']=all(pin(v['path'])==v for v in R.get('inputs',{}).values())
        if not R['owned_unit_retired'] or not R['inputs_unchanged'] or not R['host_identity_unchanged'] or (actual and not R.get('actual_qemu_exited')): R['passed']=False;R['errors'].append({'type':'postcondition','message':'retirement or immutable input check failed'})
        R['finished_ns']=time.time_ns()
        create(D/'result.json',R)
        for f in ('serial.log','launcher.stderr'):
            if (D/f).exists():print(f+' '+json.dumps(pin(D/f)))
        print(json.dumps({'result':pin(D/'result.json'),'passed':R['passed'],'errors':R['errors'],'actual_process':R.get('actual_process'),'owned_unit_retired':R.get('owned_unit_retired'),'actual_qemu_exited':R.get('actual_qemu_exited'),'guest_summary':R.get('guest_summary'),'guest_cases':R.get('guest_cases'),'guest_result':R.get('guest_result')}))
    finally:os.close(LOCK_FD)
sys.exit(0 if R['passed'] else 1)
