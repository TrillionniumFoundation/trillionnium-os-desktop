#!/usr/bin/env python3
import ctypes,datetime,fcntl,hashlib,json,os,re,signal,stat,subprocess,sys,time
from pathlib import Path

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def identity(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def held(path, maximum=4*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'unexpected file type/size: '+str(path))
        parts = []
        total = 0
        while total <= maximum:
            chunk = os.read(fd, min(65536, maximum+1-total))
            if not chunk:
                break
            parts.append(chunk)
            total += len(chunk)
        data = b''.join(parts)
        require(total == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()), 'source changed during read: '+str(path))
        return data, {'path': str(path), 'bytes': total, 'sha256': sha(data), 'identity': identity(before)}
    finally:
        os.close(fd)

def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(data, bytes):
        data = (json.dumps(data, indent=2, sort_keys=True)+'\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}

def real_directory(path):
    for item in (path, *path.parents):
        require(stat.S_ISDIR(item.lstat().st_mode), 'directory alias rejected: '+str(item))

def children():
    return [int(x) for x in Path('/proc/self/task/%d/children' % os.getpid()).read_text().split()]

def cleanup_children():
    initial = children()
    errors = []
    reaped = []
    deadline = time.monotonic()+8
    while children() and time.monotonic() < deadline:
        for pid in children():
            try:
                got, status = os.waitpid(pid, os.WNOHANG)
                if got:
                    reaped.append({'pid': got, 'status': status})
                    continue
                fd = os.pidfd_open(pid, 0)
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                finally:
                    os.close(fd)
            except ChildProcessError:
                continue
            except ProcessLookupError:
                continue
            except Exception as error:
                errors.append(repr(error))
        time.sleep(0.02)
    remaining = children()
    return {'initial_owned_children': initial, 'forced_cleanup': bool(initial), 'reaped': reaped, 'remaining': remaining, 'errors': errors}

def command(argv, cwd, env, label, records, maximum_seconds=180, pass_fds=()):
    require(not children(), 'unreaped child before command')
    maximum_seconds = min(maximum_seconds, DEADLINE-time.monotonic())
    require(maximum_seconds > 0, 'owned overall deadline exhausted')
    stdout = OUT/(label+'.stdout')
    stderr = OUT/(label+'.stderr')
    started = utc()
    with stdout.open('xb') as out, stderr.open('xb') as err:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, start_new_session=True, pass_fds=pass_fds)
        timeout = False
        try:
            code = proc.wait(timeout=maximum_seconds)
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                code = proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                code = proc.wait(timeout=3)
    output, outrow = held(stdout, 32*1024*1024)
    _, errrow = held(stderr, 4*1024*1024)
    row = {'argv': [str(x) for x in argv], 'cwd': str(cwd), 'label': label,
           'started_utc': started, 'finished_utc': utc(), 'returncode': code,
           'timed_out': timeout, 'stdout': outrow, 'stderr': errrow}
    records.append(row)
    require(code == 0 and not timeout, 'command failed: '+label)
    require(not children(), 'command left owned children: '+label)
    return output

def resource_text(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        raw = os.read(fd, 32769)
        require(len(raw) <= 32768, 'owned resource observation exceeds bound')
        return raw.decode('ascii').strip()
    finally:
        os.close(fd)

def resource_events(text):
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows), 'malformed owned memory.events')
    events = {row[0]:int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(k in events for k in ['oom','oom_kill','oom_group_kill']), 'incomplete or duplicate owned memory.events')
    return events

def resource_snapshot(directory_fd, membership):
    observed = Path('/proc/self/cgroup').read_text().strip()
    require(observed == membership, 'controller cgroup membership changed')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    held_st = os.fstat(directory_fd)
    named_st = path.lstat()
    require(stat.S_ISDIR(held_st.st_mode) and stat.S_ISDIR(named_st.st_mode) and
            (held_st.st_dev,held_st.st_ino) == (named_st.st_dev,named_st.st_ino), 'owned invocation cgroup identity changed')
    fields = {name:resource_text(directory_fd,name) for name in [
        'cgroup.procs','memory.events','memory.current','memory.peak','memory.high','memory.max',
        'memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max']}
    require(str(os.getpid()) in fields['cgroup.procs'].split(), 'controller is not in the held invocation')
    require(fields['memory.max'] == '268435456' and fields['cpu.max'] == '50000 100000', 'owned resource limits do not match the request')
    for key in ['memory.current','memory.peak','memory.swap.current','memory.swap.peak']:
        require(fields[key].isdigit(), 'invalid owned resource counter: '+key)
    return {'observed_utc':utc(), 'membership':membership, 'path':str(path),
            'directory_identity':[held_st.st_dev,held_st.st_ino],
            'controller_pid':os.getpid(), 'fields':fields, 'events':resource_events(fields['memory.events'])}

def begin_resources():
    membership = Path('/proc/self/cgroup').read_text().strip()
    require('\n' not in membership and membership.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'), 'not the exact owned user invocation')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    require(path.name.startswith('hepta-runtime-job-') and path.name.endswith('.service') and '..' not in path.parts, 'unexpected owned unit path')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = resource_snapshot(fd,membership)
        require(all(before['events'][k] == 0 for k in ['oom','oom_kill','oom_group_kill']), 'owned invocation already recorded OOM before the control')
        return fd,before
    except BaseException:
        os.close(fd)
        raise

def finish_resources(directory_fd, before, report):
    after = resource_snapshot(directory_fd,before['membership'])
    report['owned_resources_after'] = after
    report['owned_memory_peak'] = int(after['fields']['memory.peak'])
    report['owned_memory_swap_peak'] = int(after['fields']['memory.swap.peak'])
    require(after['directory_identity'] == before['directory_identity'], 'owned cgroup object replaced')
    require(set(before['events']) == set(after['events']), 'owned memory event fields changed')
    delta = {key:after['events'][key]-value for key,value in before['events'].items()}
    report['owned_memory_events_delta'] = delta
    require(all(value >= 0 for value in delta.values()), 'owned memory event counters went backwards')
    require(all(delta[key] == 0 for key in ['oom','oom_kill','oom_group_kill']), 'owned OOM event occurred; control is not qualified')
    require(all(before['fields'][key] == after['fields'][key] for key in ['memory.max','memory.high','memory.swap.max','cpu.max']), 'owned cgroup limits changed during control')
    return {'pass':True, 'before':before, 'after':after, 'memory_events_delta':delta,
            'memory_peak':int(after['fields']['memory.peak']), 'memory_swap_peak':int(after['fields']['memory.swap.peak']),
            'resource_settings_changed':False, 'swap_max_observed_only':after['fields']['memory.swap.max']}

def hash_held(path, maximum=512*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'unexpected held file type/size: '+str(path))
        digest = hashlib.sha256()
        total = 0
        while True:
            raw = os.read(fd,65536)
            if not raw:
                break
            total += len(raw)
            require(total <= maximum, 'held file grew beyond bound: '+str(path))
            digest.update(raw)
        require(total == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
                'held file changed: '+str(path))
        return {'path':str(path),'bytes':total,'sha256':digest.hexdigest(),'identity':identity(before)}
    finally:
        os.close(fd)

def regular_tree(root, file_bound=2048, byte_bound=32*1024*1024):
    real_directory(root)
    rows = {}
    total = 0
    def walk_error(error):
        raise error
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=walk_error):
        dirs.sort()
        for name in dirs:
            path=Path(directory)/name
            require(stat.S_ISDIR(path.lstat().st_mode),'source directory alias rejected: '+str(path))
        for name in sorted(files):
            path=Path(directory)/name
            relative=str(path.relative_to(root))
            require(relative not in rows and len(rows)<file_bound,'source inventory bound or duplicate')
            row=hash_held(path)
            total+=row['bytes']
            require(total<=byte_bound,'source inventory byte bound exceeded')
            rows[relative]=row
    require(rows,'empty source inventory: '+str(root))
    return rows

def verify_rows(rows):
    changed=[]
    for row in rows:
        try:
            requested=Path(row['requested_path']);resolved=requested.resolve(strict=True)
            current=hash_held(resolved)
            if str(resolved)!=row['resolved_path'] or current!={k:row[k] for k in ['path','bytes','sha256','identity']}:
                changed.append(str(requested))
        except Exception as error:changed.append({'path':row['requested_path'],'error':str(error)})
    return changed

def held_executable(path,expected):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and st.st_mode&0o111 and st.st_size<=8*1024*1024,'bounded regular executable required')
        digest=hashlib.sha256();total=0;magic=None
        while True:
            raw=os.read(fd,65536)
            if not raw:break
            if magic is None:magic=raw[:4]
            total+=len(raw);digest.update(raw)
        pin={'path':str(path),'bytes':total,'sha256':digest.hexdigest(),'identity':identity(st)}
        require(magic==b'\x7fELF' and pin==expected and identity(st)==identity(os.fstat(fd))==identity(path.lstat()),
                'held runtime executable differs from actual matching build')
        require(fcntl.fcntl(fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC,'held ELF must close across exec')
        return fd,pin
    except BaseException:os.close(fd);raise

ROOT=Path('/run/pocket4-snapshot-nofollow-host-run-01-20261105')
HERE=ROOT/'control-source'
OUT=ROOT/'run01'
BUILD_ROOT=Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/snapshot-nofollow-host-build-01-20261105')
SOURCE=BUILD_ROOT/'source'
BUILD_RESULT=BUILD_ROOT/'build01/result.json'
BUILD_RESULT_SHA='PENDING_ACTUAL_BUILD_RESULT_SHA256'
CASE_PLAN_SHA='5e50f0ae3bc7a2458e71d30fef0f859c5466f343ebe9c18ffcc0c8f2989b63c8'
SOURCE_MANIFEST_SHA='310e7370a78cc63f0ad72527fbeb37f58f884fdf3ca45ee0acc37e1aee46ad36'
DEADLINE=None


def qualified_build(build):
    require(build['state']=='PASS_BUILD_ONLY' and build['source_manifest_sha256']==SOURCE_MANIFEST_SHA and
            build['registry_positive_executed'] is False and build['snapshot_positive_executed'] is False and
            build['platform_policy_qualified'] is False and
            build['factory_service_started'] is False and build['snapshot_created'] is False and
            build['Main_actions']==0 and build['source_unchanged_after'] is True and
            build['artifacts_unchanged_after'] is True and not build['tool_changes'] and
            not build['dependency_changes'] and build['owned_resource_gate']['pass'] is True and
            not build['cleanup']['forced_cleanup'] and not build['cleanup']['remaining'] and
            not build['cleanup']['errors'] and set(build['artifacts'])=={'control'},
            'complete matching build-only authority required')
    labels=[row['label'] for row in build['commands']]
    require(len(labels)==len(set(labels)) and all(row['returncode']==0 and not row['timed_out']
            for row in build['commands']), 'matching build command failure or duplicate')
    for name in ['dependencies-authorization','dependencies-context','dependencies-wire',
                 'dependencies-snapshot','dependencies-control','dependencies-factory','compile-authorization','compile-context',
                 'compile-wire','compile-snapshot','compile-control','compile-factory','link-control',
                 'control-libraries','default-plan','link-factory','factory-libraries','factory-default-plan']:
        require(labels.count(name)==1, 'matching build omitted required command: '+name)
    require(set(build['objects'])=={'authorization','context','wire','snapshot','control','factory'} and
            all(row['dependency_count']>0 for row in build['objects'].values()),
            'complete actual compiler dependency observations required')
    require(build['artifacts']['control']['default_plan']=={
        'state':'PLAN_ONLY','owned_cases':5,
        'factory_service_started':False,'Main_actions':0}, 'matching default PLAN differs')
    require(set(build['artifacts'])=={'control','factory'} and
            build['artifacts']['factory']['default_plan']=={
                'state':'DISABLED_REQUIRES_PINNED_INHERITED_OWNER','protocol':2,
                'service_started':False,'production_ready':False},
            'matching standalone V2 factory default-disabled contract differs')


def root_scope():
    require(os.getuid()==0 and os.geteuid()==0 and os.getgid()==0 and os.getegid()==0,
            'root controller identity required')
    require(os.getpid()==int(Path('/proc/thread-self/status').read_text().split('Pid:\t',1)[1].splitlines()[0]),
            'root controller requires current proc PID view')
    require(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,
            'owned root controller requires default SIGCHLD')
    for path in [ROOT,HERE,OUT]:
        value=path.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid==0 and value.st_gid==0 and
                stat.S_IMODE(value.st_mode)==0o700, 'root-private runtime directory differs: '+str(path))
    # Only this fixture UID/GID is used by owned children. No system account or
    # process is modified, and no search is made for alternative identities.
    import pwd,grp
    for lookup in [pwd.getpwuid,grp.getgrgid]:
        try:lookup(61179)
        except KeyError:continue
        raise RuntimeError('fixed fixture UID/GID is a configured system account')


def run_held(fd,path,env,libc):
    require(not children(), 'unreaped child before the owned snapshot harness')
    require(os.execve in os.supports_fd, 'Python fd-based exec unavailable')
    stdout=OUT/'snapshot.stdout';stderr=OUT/'snapshot.stderr'
    started=utc();parent=os.getpid();pid=-1;pidfd=-1;status=None;timed_out=False
    with stdout.open('xb') as out,stderr.open('xb') as err:
        pid=os.fork()
        if pid==0:
            try:
                require(os.getppid()==parent and libc.prctl(1,signal.SIGKILL,0,0,0)==0 and
                        os.getppid()==parent, 'exec child lost exact owned parent')
                os.setsid()
                null=os.open('/dev/null',os.O_RDONLY|os.O_CLOEXEC)
                os.dup2(null,0);os.dup2(out.fileno(),1);os.dup2(err.fileno(),2)
                if null>2:os.close(null)
                require(fcntl.fcntl(fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC,
                        'held ELF must close across exec')
                os.execve(fd,[str(path),'--execute-once'],env)
            except BaseException:
                os.write(2,b'owned held-ELF exec failed\n');os._exit(126)
        try:
            pidfd=os.pidfd_open(pid,0)
            until=min(time.monotonic()+45,DEADLINE)
            while time.monotonic()<until:
                got,value=os.waitpid(pid,os.WNOHANG)
                if got==pid:status=value;break
                time.sleep(0.02)
            if status is None:
                timed_out=True;signal.pidfd_send_signal(pidfd,signal.SIGKILL)
                until=time.monotonic()+3
                while time.monotonic()<until:
                    got,value=os.waitpid(pid,os.WNOHANG)
                    if got==pid:status=value;break
                    time.sleep(0.02)
                require(status is not None,'owned harness did not reap after exact pidfd kill')
        finally:
            if pidfd>=0:os.close(pidfd)
    raw,outpin=held(stdout,131072);_,errpin=held(stderr,32768)
    return {'held_elf_path':str(path),'fd_exec':True,'started_utc':started,'finished_utc':utc(),
            'child_pid':pid,'child_reaped':status is not None,'wait_status':status,
            'returncode':os.waitstatus_to_exitcode(status) if status is not None else None,
            'timed_out':timed_out,'stdout':outpin,'stderr':errpin},raw


def validate_result(raw,plan):
    lines=raw.decode('ascii').splitlines()
    require(len(lines)==6 and all(lines),'exact five case records and one terminal required')
    records=[json.loads(line) for line in lines]
    expected=plan['cases']
    require(len(expected)==5 and len({row['name'] for row in expected})==5,
            'exact frozen five-case snapshot plan required')
    for wanted,seen in zip(expected,records[:-1]):
        require(seen=={'case':wanted['name'],'state':'PASS','actual_kernel_identity':True,
                       'production_platform_policy':False,'snapshot_created':True,
                       'maps_formatter':'owned_fixture'},
                'owned case failed or unexpected record: '+wanted['name'])
    result=records[-1]
    require(set(result)=={'state','cases','assertions','direct_children_reaped','nested_children_reaped',
                         'forced_cleanup','cleanup_unreaped','platform_policy_qualified','snapshot_created',
                         'maps_formatter','Main_actions','factory_service_started'} and
            result['state']=='PASS_OWNED_ROLE_SNAPSHOT' and result['cases']==5 and
            isinstance(result['assertions'],int) and not isinstance(result['assertions'],bool) and
            result['assertions']>0 and result['direct_children_reaped']==5 and
            result['nested_children_reaped']==0 and result['forced_cleanup']==0 and
            result['cleanup_unreaped']==0 and result['platform_policy_qualified'] is False and
            result['snapshot_created'] is True and result['maps_formatter']=='owned_fixture' and
            result['Main_actions']==0 and result['factory_service_started'] is False,
            'owned snapshot aggregate failed')
    return {'cases':records[:-1],'summary':result}


def execute():
    global DEADLINE
    require(Path(__file__).absolute()==HERE/'run_snapshot.py','fixed staged root runner required')
    require(re.fullmatch(r'[0-9a-f]{64}',BUILD_RESULT_SHA) is not None,
            'actual matching build receipt has not been bound')
    real_directory(HERE);os.umask(0o077);OUT.mkdir(mode=0o700);DEADLINE=time.monotonic()+90
    libc=ctypes.CDLL(None,use_errno=True)
    require(libc.prctl(36,1,0,0,0)==0 and not children(),'owned root subreaper required')
    allowed=sorted(os.sched_getaffinity(0));require(len(allowed)>=3,'cannot leave two logical CPUs free')
    os.sched_setaffinity(0,[allowed[-1]])
    report={'schema':1,'state':'RUNNING','started_utc':utc(),
            'scope':'fixed root / owned O_RDONLY and exact O_NOFOLLOW sealed snapshot; no policy change',
            'Main_actions':0,'Main_identity_observed':False,'Android_execution':False,
            'factory_service_started':False,'snapshot_created':False,'platform_policy_qualified':False,
            'production_source_changed':False,'selected_cpus':[allowed[-1]],'commands':[]}
    def interrupted(number,frame):raise RuntimeError('owned runtime interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    resource_fd=-1;resource_before=None;source_before={};elf_fd=-1;elf_pin=None
    libraries={};tool_rows=[];authority={}
    try:
        resource_fd,resource_before=begin_resources();report['owned_resources_before']=resource_before
        root_scope()
        raw,build_pin=held(BUILD_RESULT,262144)
        require(sha(raw)==BUILD_RESULT_SHA,'actual build receipt changed')
        staged,staged_pin=held(HERE/'actual-build-result.json',262144)
        require(staged==raw,'staged build receipt differs from actual matching receipt')
        build=json.loads(raw);qualified_build(build)
        plan_raw,plan_pin=held(HERE/'CASE_PLAN.json',32768)
        require(sha(plan_raw)==CASE_PLAN_SHA,'frozen five-case snapshot plan changed')
        plan=json.loads(plan_raw)
        require(plan['production_source_manifest_sha256']==SOURCE_MANIFEST_SHA,
                'case plan is not bound to reviewed source')
        source_before=regular_tree(SOURCE,18,512*1024)
        require(source_before==build['source_inputs'],'actual built source changed before runtime')
        authority={str(BUILD_RESULT):build_pin,str(HERE/'actual-build-result.json'):staged_pin,
                   str(HERE/'CASE_PLAN.json'):plan_pin}
        report['actual_build_receipt']=build_pin;report['source_authority']=build['source_authority']
        tools_path=BUILD_ROOT/'build01/tool-inputs-before.json'
        require(build['tool_inputs']['path']==str(tools_path),'build tool inventory path escaped')
        tools_raw,tools_pin=held(tools_path,262144)
        require({key:tools_pin[key]for key in ['path','bytes','sha256']}==build['tool_inputs'],
                'matching tool inventory changed')
        authority[str(tools_path)]=tools_pin
        tools=json.loads(tools_raw);tool_rows=[tools['/usr/bin/python3'],tools['/usr/bin/ldd']]
        require(not verify_rows(tool_rows),'runtime tools changed after matching build')
        path=BUILD_ROOT/'build01/snapshot_controls';artifact=build['artifacts']['control']['elf']
        require(artifact['path']==str(path),'actual control ELF path escaped matching build')
        elf_fd,elf_pin=held_executable(path,artifact)
        env={'PATH':'/usr/bin:/bin','HOME':'/root','LC_ALL':'C','LANG':'C'}
        raw=command(['/usr/bin/ldd','/proc/self/fd/'+str(elf_fd)],SOURCE,env,
                    'runtime-libraries',report['commands'],10,pass_fds=(elf_fd,)).decode()
        require('not found'not in raw,'actual runtime library missing')
        for line in raw.splitlines():
            match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:
                requested=Path(match[1]);resolved=requested.resolve(strict=True)
                require(resolved.is_relative_to('/usr/lib')or resolved.is_relative_to('/lib'),
                        'runtime library outside system roots')
                row=hash_held(resolved,128*1024*1024)
                row.update({'requested_path':str(requested),'resolved_path':str(resolved)})
                libraries[str(requested)]=row
        require(libraries and libraries==build['runtime_libraries'],
                'runtime library closure differs from actual matching build')
        report['runtime_libraries']=write_new(OUT/'runtime-libraries-before.json',libraries)
        row,raw=run_held(elf_fd,path,env,libc);report['execution']=row
        require(row['returncode']==0 and row['child_reaped'] and not row['timed_out'] and
                row['stderr']['bytes']==0,'owned snapshot process failed')
        report['assessment']=validate_result(raw,plan)
        require(not children(),'owned snapshot harness left adopted children')
        report['snapshot_created']=True;report['maps_formatter']='owned_fixture'
        report['state']='PASS_OWNED_ROLE_SNAPSHOT'
    except Exception as error:
        report['state']='FAIL';report['error']={'type':type(error).__name__,'message':str(error),
                                               'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['cleanup']=cleanup_children()
        try:
            report['source_unchanged_after']=bool(source_before)and regular_tree(SOURCE,18,512*1024)==source_before
            report['authority_unchanged_after']=bool(authority)and all(hash_held(Path(path))==pin
                                                                       for path,pin in authority.items())
            report['library_changes']=verify_rows(list(libraries.values()))
            report['tool_changes']=verify_rows(tool_rows)
            report['held_ELF_unchanged_after']=(elf_pin is not None and elf_fd>=0 and
                hash_held(Path(elf_pin['path']),8*1024*1024)==elf_pin and
                identity(os.fstat(elf_fd))==elf_pin['identity'])
            require(report['source_unchanged_after']and report['authority_unchanged_after']and
                    not report['library_changes']and not report['tool_changes']and
                    report['held_ELF_unchanged_after'],'runtime source or authority changed')
        except Exception as error:report['after_error']=str(error);report['state']='FAIL'
        if elf_fd>=0:os.close(elf_fd)
        try:
            require(resource_fd>=0 and resource_before is not None,'missing owned cgroup before observation')
            report['owned_resource_gate']=finish_resources(resource_fd,resource_before,report)
        except Exception as error:report['resource_error']=str(error);report['state']='FAIL'
        finally:
            if resource_fd>=0:os.close(resource_fd)
        if report['cleanup']['forced_cleanup']or report['cleanup']['remaining']or report['cleanup']['errors']:
            report['state']='FAIL'
    report['finished_utc']=utc();pin=write_new(OUT/'result.json',report)
    print(json.dumps({'state':report['state'],'result':pin}),flush=True)
    return 0 if report['state']=='PASS_OWNED_ROLE_SNAPSHOT'else 1


if __name__=='__main__':
    if sys.argv[1:]!=['--execute-once']:
        print(json.dumps({'state':'PLAN_ONLY','requires_actual_matching_build':True,'owned_cases':5,
                          'root_execution':False,'factory_service_started':False,'Main_actions':0}))
    else:raise SystemExit(execute())
