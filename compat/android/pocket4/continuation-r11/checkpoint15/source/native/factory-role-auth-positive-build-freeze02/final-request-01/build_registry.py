#!/usr/bin/env python3
import ctypes,datetime,hashlib,json,os,re,signal,stat,subprocess,sys,time,shlex
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

def command(argv, cwd, env, label, records, maximum_seconds=180):
    require(not children(), 'unreaped child before command')
    maximum_seconds = min(maximum_seconds, DEADLINE-time.monotonic())
    require(maximum_seconds > 0, 'owned overall deadline exhausted')
    stdout = OUT/(label+'.stdout')
    stderr = OUT/(label+'.stderr')
    started = utc()
    with stdout.open('xb') as out, stderr.open('xb') as err:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, start_new_session=True)
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
    require(fields['memory.max'] == '536870912' and fields['cpu.max'] == '100000 100000', 'owned resource limits do not match the request')
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

def verify_resolved(rows):
    changes=[]
    for row in rows:
        try:
            path=Path(row['requested_path'])
            resolved=path.resolve(strict=True)
            after=hash_held(resolved)
            if str(resolved)!=row['resolved_path'] or after!={k:row[k] for k in ['path','bytes','sha256','identity']}:
                changes.append(str(path))
        except Exception as error:
            changes.append({'path':row['requested_path'],'error':repr(error)})
    return changes

def pin_tool(path):
    original=Path(path);resolved=original.resolve(strict=True)
    require(any(resolved.is_relative_to(root) for root in [Path('/usr/bin'),Path('/usr/lib'),Path('/usr/libexec/gcc')]),
            'tool/library outside fixed system roots: '+str(resolved))
    row=hash_held(resolved,128*1024*1024)
    row.update({'requested_path':str(original),'resolved_path':str(resolved)})
    require(original.resolve(strict=True)==resolved,'tool resolution changed')
    return row

def dependency_files(raw):
    text=raw.decode().replace(chr(92)+chr(10),' ')
    require(text.startswith('CONTROL:') and text.count('CONTROL:')==1,'unexpected compiler dependency format')
    words=shlex.split(text[len('CONTROL:'):]);require(0<len(words)<=1024,'compiler dependency bound exceeded')
    rows={}
    for name in words:
        requested=Path(os.path.abspath(str(SOURCE/name))) if not Path(name).is_absolute() else Path(name)
        resolved=requested.resolve(strict=True)
        require(any(resolved.is_relative_to(p) for p in [SOURCE,Path('/usr/include'),Path('/usr/lib/gcc')]),
                'compiler header escaped staged source/system include roots: '+str(resolved))
        row=hash_held(resolved,16*1024*1024)
        row.update({'requested_path':str(requested),'resolved_path':str(resolved)})
        rows[str(requested)]=row
    return rows

SOURCE_INPUTS={'source/role_authorization.cc': {'bytes': 38998, 'sha256': '5d9a43b4f9d51ddfe7896de563353c96f75856171d39c1af9a5816394247a03c'}, 'source/role_authorization.h': {'bytes': 5539, 'sha256': '320933ecda593fdb98b16b7bcd506d48ab81e15c0bd5903b38fe4dde49404d8c'}, 'source/factory_context.cc': {'bytes': 5377, 'sha256': 'afd7ed0688ac5d4ea5cfc5611c7a7f17572184547c2628f1fe888d491ee1479a'}, 'source/factory_context.h': {'bytes': 954, 'sha256': 'b27148d779b5626a1677f7b2e10333645de90c68b67716b851104eab7ad6c7d1'}, 'controls/registry_controls.cc': {'bytes': 33258, 'sha256': '5ea30aeb58eebeb09542e9ee68c07e1be7ff92fedcc3141f4d336490458e1a94'}}
ROOT=Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/role-authorization-positive-host-build-02-20261105')
SOURCE=ROOT/'source'
OUT=ROOT/'build01'
SOURCE_MANIFEST_SHA='fda076982c0a26682eb3b6a596a6964e6645cf1eddc7b175e56d9b499c06fda2'
DEADLINE=None


def execute():
    global DEADLINE
    require(os.getuid()==1000 and os.geteuid()==1000,'ordinary operator UID1000 required')
    require(Path(__file__).absolute()==SOURCE/'build_registry.py','fixed staged controller required')
    real_directory(SOURCE);os.umask(0o077);OUT.mkdir(mode=0o700);(OUT/'tmp').mkdir(mode=0o700)
    DEADLINE=time.monotonic()+180
    require(ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0 and not children(),'owned subreaper required')
    allowed=sorted(os.sched_getaffinity(0));require(len(allowed)>=3,'cannot leave two logical CPUs free')
    os.sched_setaffinity(0,[allowed[-1]])
    report={'schema':1,'state':'RUNNING','scope':'matching registry mechanism compile and default PLAN only',
            'started_utc':utc(),'Main_actions':0,'Main_identity_observed':False,
            'registry_positive_executed':False,'platform_policy_qualified':False,
            'factory_service_started':False,'snapshot_created':False,
            'source_manifest_sha256':SOURCE_MANIFEST_SHA,'selected_cpus':[allowed[-1]],
            'commands':[],'objects':{},'artifacts':{}}
    def interrupted(number,frame):raise RuntimeError('owned compiler interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    source_before={};tools={};dependencies={};resource_fd=-1;resource_before=None;artifact_pins={}
    try:
        resource_fd,resource_before=begin_resources();report['owned_resources_before']=resource_before
        authority,authority_pin=held(SOURCE/'role-source-pins.json',32768)
        require(sha(authority)==SOURCE_MANIFEST_SHA,'positive fixture source authority differs')
        frozen={row['path']:row for row in json.loads(authority)['files']}
        require(len(SOURCE_INPUTS)==5,'reviewed exact five compile inputs required')
        for name,pin in SOURCE_INPUTS.items():
            require(all(frozen[name][key]==pin[key] for key in ['bytes','sha256']),
                    'reviewed compile input not bound by source authority: '+name)
        stage_raw,stage_pin=held(ROOT/'stage-receipt.json',32768);stage=json.loads(stage_raw)['files']
        source_before=regular_tree(SOURCE,12,512*1024)
        require(set(source_before)==set(stage),'staged source membership differs')
        for name,pin in source_before.items():
            require(pin['bytes']==stage[name]['bytes'] and pin['sha256']==stage[name]['sha256'],
                    'staged source pin mismatch: '+name)
        for name,pin in SOURCE_INPUTS.items():
            require(source_before[name]['bytes']==pin['bytes'] and source_before[name]['sha256']==pin['sha256'],
                    'reviewed input changed: '+name)
        report['source_inputs']=source_before;report['source_authority']=authority_pin;report['stage_authority']=stage_pin
        env={'PATH':'/usr/bin:/bin','HOME':'/home/alex','LC_ALL':'C','LANG':'C','TMPDIR':str(OUT/'tmp')}
        report['environment']=env
        for path in ['/usr/bin/g++','/usr/bin/ldd','/usr/bin/python3']:tools[path]=pin_tool(path)
        compiler='/usr/bin/g++'
        report['compiler_version']=command([compiler,'--version'],SOURCE,env,'compiler-version',report['commands'],10).decode()
        for name in ['cc1plus','collect2','as','ld']:
            raw=command([compiler,'-print-prog-name='+name],SOURCE,env,'resolve-'+name,report['commands'],10).decode().strip()
            path=Path(raw) if Path(raw).is_absolute() else Path('/usr/bin')/raw
            require(path.name==name or(name in ['as','ld']and path.name.endswith('-'+name)),
                    'unexpected compiler program name')
            tools[str(path)]=pin_tool(path)
        for name in ['crt1.o','crti.o','crtn.o','crtbeginS.o','crtendS.o','libgcc.a','libgcc_s.so','libstdc++.so','libc.so']:
            raw=command([compiler,'-print-file-name='+name],SOURCE,env,'resolve-file-'+name,report['commands'],10).decode().strip()
            require(Path(raw).is_absolute(),'compiler runtime file not resolved: '+name);tools[raw]=pin_tool(raw)
        for index,row in enumerate(list(tools.values())):
            path=Path(row['resolved_path'])
            with path.open('rb')as stream:magic=stream.read(4)
            if magic!=b'\x7fELF' or path.suffix=='.o' or path.name.endswith('.a'):continue
            raw=command(['/usr/bin/ldd',str(path)],SOURCE,env,'tool-libraries-'+str(index),report['commands'],10).decode()
            require('not found'not in raw,'compiler runtime library missing')
            for line in raw.splitlines():
                match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
                if match:tools[match[1]]=pin_tool(match[1])
        flags=['-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(SOURCE/'source')]
        units=[('authorization','source/role_authorization.cc'),('context','source/factory_context.cc'),
               ('control','controls/registry_controls.cc')]
        before_units={}
        for label,name in units:
            raw=command([compiler,*flags,'-M','-MT','CONTROL',str(SOURCE/name)],SOURCE,env,
                        'dependencies-'+label,report['commands'],30)
            before_units[label]=dependency_files(raw);dependencies.update(before_units[label])
        require(0<len(dependencies)<=1024,'complete dependency closure out of bound')
        report['dependency_inputs']=write_new(OUT/'dependency-inputs-before.json',dependencies)
        report['dependency_count']=len(dependencies)
        objects=[]
        for label,name in units:
            target=OUT/(label+'.o');md=OUT/(label+'.d')
            command([compiler,*flags,'-MD','-MF',str(md),'-MT','CONTROL','-c',str(SOURCE/name),'-o',str(target)],
                    SOURCE,env,'compile-'+label,report['commands'],45)
            raw,md_pin=held(md,256*1024)
            require(dependency_files(raw)==before_units[label],
                    'actual compiler dependency bytes/identities differ: '+label)
            artifact_pins[label]=hash_held(target,8*1024*1024)
            report['objects'][label]={'object':artifact_pins[label],'actual_md':md_pin,
                                      'dependency_count':len(before_units[label])}
            objects.append(str(target))
        binary=OUT/'registry_controls'
        command([compiler,*flags,*objects,'-o',str(binary)],SOURCE,env,'link-control',report['commands'],30)
        artifact=hash_held(binary,8*1024*1024);artifact_pins['control']=artifact
        with binary.open('rb')as stream:require(stream.read(4)==b'\x7fELF','actual result is not ELF')
        require(binary.stat().st_mode&0o111,'actual ELF not executable')
        raw=command(['/usr/bin/ldd',str(binary)],SOURCE,env,'control-libraries',report['commands'],10).decode()
        require('not found'not in raw,'actual control runtime missing')
        runtime={}
        for line in raw.splitlines():
            match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:runtime[match[1]]=pin_tool(match[1]);tools[match[1]]=runtime[match[1]]
        require(runtime,'actual control library closure empty')
        report['runtime_libraries']=runtime
        plan=json.loads(command([str(binary)],SOURCE,env,'default-plan',report['commands'],10))
        require(plan=={'state':'PLAN_ONLY','actual_role_registry':False,'owned_cases':10,
                       'factory_service_started':False,'Main_actions':0},'default PLAN contract differs')
        report['artifacts']['control']={'elf':artifact,'default_plan':plan}
        report['tool_inputs']=write_new(OUT/'tool-inputs-before.json',tools)
        report['state']='PASS_BUILD_ONLY'
    except Exception as error:
        report['state']='FAIL';report['error']={'type':type(error).__name__,'message':str(error),
                                               'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['cleanup']=cleanup_children()
        try:
            report['source_unchanged_after']=bool(source_before)and regular_tree(SOURCE,12,512*1024)==source_before
            report['tool_changes']=verify_resolved(list(tools.values()))
            report['dependency_changes']=verify_resolved(list(dependencies.values()))
            report['artifacts_unchanged_after']=all(hash_held(Path(row['path']),8*1024*1024)==row for row in artifact_pins.values())
            require(report['source_unchanged_after']and not report['tool_changes']and
                    not report['dependency_changes']and report['artifacts_unchanged_after'],
                    'compiled input or output changed')
        except Exception as error:report['after_error']=repr(error);report['state']='FAIL'
        try:
            require(resource_fd>=0 and resource_before is not None,'missing before resource observation')
            report['owned_resource_gate']=finish_resources(resource_fd,resource_before,report)
        except Exception as error:report['resource_error']=repr(error);report['state']='FAIL'
        finally:
            if resource_fd>=0:os.close(resource_fd)
        if report['cleanup']['forced_cleanup']or report['cleanup']['remaining']or report['cleanup']['errors']:
            report['state']='FAIL'
    report['finished_utc']=utc();result=write_new(OUT/'result.json',report)
    print(json.dumps({'state':report['state'],'result':result}),flush=True)
    return 0 if report['state']=='PASS_BUILD_ONLY'else 1


if __name__=='__main__':
    if sys.argv[1:]!=['--execute-once']:
        print(json.dumps({'state':'PLAN_ONLY','build_root':str(ROOT),'source_count':len(SOURCE_INPUTS),
                          'registry_positive_executed':False,'Main_actions':0}))
    else:raise SystemExit(execute())
