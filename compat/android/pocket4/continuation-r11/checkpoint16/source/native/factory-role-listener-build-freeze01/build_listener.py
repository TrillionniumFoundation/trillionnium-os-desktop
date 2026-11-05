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

SOURCE_INPUTS={'source/factory_context.cc': {'bytes': 5377, 'sha256': 'afd7ed0688ac5d4ea5cfc5611c7a7f17572184547c2628f1fe888d491ee1479a', 'authority': 'listener-source-pins.json', 'authority_path': 'source/factory_context.cc'}, 'source/factory_context.h': {'bytes': 954, 'sha256': 'b27148d779b5626a1677f7b2e10333645de90c68b67716b851104eab7ad6c7d1', 'authority': 'listener-source-pins.json', 'authority_path': 'source/factory_context.h'}, 'source/role_authorization.cc': {'bytes': 39949, 'sha256': 'd860c7222e8f5025b19de98a8ed7aceb01d72cd12351a80c93876d8fb8ce5cf5', 'authority': 'listener-source-pins.json', 'authority_path': 'source/role_authorization.cc'}, 'source/role_authorization.h': {'bytes': 6393, 'sha256': 'aa1baefc5b86091d3c9679182356c0be69896958ad472e1aee8d14c0218e4780', 'authority': 'listener-source-pins.json', 'authority_path': 'source/role_authorization.h'}, 'source/role_session.cc': {'bytes': 20238, 'sha256': '696c6065216fb2b608c038876f7615bd04926b973f1fa1e0b428c895e47e4e85', 'authority': 'listener-source-pins.json', 'authority_path': 'source/role_session.cc'}, 'source/role_session.h': {'bytes': 3987, 'sha256': '958eda04a3236ce58482e714a4bf83e50222bc4fc9134adbd6685821f31dddcf', 'authority': 'listener-source-pins.json', 'authority_path': 'source/role_session.h'}, 'source/role_snapshot.cc': {'bytes': 11168, 'sha256': 'f234d00e9823411c9cd55a7e3c6ea52cac505b08c7dbf96894e5b8487dd3e335', 'authority': 'listener-source-pins.json', 'authority_path': 'source/role_snapshot.cc'}, 'source/role_snapshot.h': {'bytes': 1868, 'sha256': 'ee2f92791ad055959f4444e7078553780c53d27e0f649e6920bad954f9bc4ca4', 'authority': 'listener-source-pins.json', 'authority_path': 'source/role_snapshot.h'}, 'source/proc_maps_factory_wire.cc': {'bytes': 8661, 'sha256': '4a39b504188c5eaf56320f4e10d48285ea8954d816a98a2d5b7b684d38c48608', 'authority': 'listener-source-pins.json', 'authority_path': 'source/proc_maps_factory_wire.cc'}, 'source/role_admission.cc': {'bytes': 11019, 'sha256': '25d161ebf96e50442725df9231833dae032d890954890c691c0f985f4b31bf77', 'authority': 'listener-source-pins.json', 'authority_path': 'source/role_admission.cc'}, 'source/role_admission.h': {'bytes': 2505, 'sha256': '1813fd99e8e8335e7bf45859ceae236d4c2f0dd1bb7dfb44bb78f27609eece4b', 'authority': 'listener-source-pins.json', 'authority_path': 'source/role_admission.h'}, 'include/berberis/kernel_api/proc_maps_factory_protocol.h': {'bytes': 5051, 'sha256': 'b942f4c76fc34d8a124ecc8bb1af8503e4bc93a58f87b654771b3793072f2df9', 'authority': 'listener-source-pins.json', 'authority_path': 'include/berberis/kernel_api/proc_maps_factory_protocol.h'}, 'include/berberis/kernel_api/proc_maps_kernel_statfs.h': {'bytes': 2480, 'sha256': '77f72e71bb8e5f9239287cfb4899fc4d83c38b61f3cd78cd93909da792d751a0', 'authority': 'listener-source-pins.json', 'authority_path': 'include/berberis/kernel_api/proc_maps_kernel_statfs.h'}, 'include/berberis/kernel_api/proc_maps_linux_compat.h': {'bytes': 2072, 'sha256': '131d1eef8d9f789876c965fa2d827b21a59fc64ab7886fa1f78d95623114370c', 'authority': 'listener-source-pins.json', 'authority_path': 'include/berberis/kernel_api/proc_maps_linux_compat.h'}, 'include/berberis/kernel_api/proc_maps_snapshot_reopen.h': {'bytes': 2557, 'sha256': '175107cadc296ab714acb83d40f0559fd8bd5f4505ca73f48861d509d3a07977', 'authority': 'listener-source-pins.json', 'authority_path': 'include/berberis/kernel_api/proc_maps_snapshot_reopen.h'}, 'controls/admission_controls.cc': {'bytes': 26498, 'sha256': '89d1efb34d449494bd4138d7c590406b8fda5878bb045408cb7ad6c002e74d46', 'authority': 'listener-source-pins.json', 'authority_path': 'controls/admission_controls.cc'}, 'references/registry_controls.cc': {'bytes': 33258, 'sha256': '5ea30aeb58eebeb09542e9ee68c07e1be7ff92fedcc3141f4d336490458e1a94', 'authority': 'listener-source-pins.json', 'authority_path': 'references/registry_controls.cc'}, 'references/snapshot_verification.h': {'bytes': 3409, 'sha256': '685f329d9cbe7aa663fac37d71373655fe9ba95473bbcc3e14cf64d5ce0cb9a2', 'authority': 'listener-source-pins.json', 'authority_path': 'references/snapshot_verification.h'}, 'controls/lease_destruction_controls.cc': {'bytes': 15017, 'sha256': '0d487929a3f1a7668266eda2a8585fd987723bf8ef81fe501c9bbaffe05105cc', 'authority': 'owner-lifetime-source-pins.json', 'authority_path': 'controls/lease_destruction_controls.cc'}, 'preimage/source/role_session.cc': {'bytes': 17240, 'sha256': 'ba298a4d5bce4bf1079fdbdccc867ee0ac837f6a7d6e7f78e25268f97db22bdb', 'authority': 'owner-lifetime-source-pins.json', 'authority_path': 'preimage/source/role_session.cc'}, 'preimage/source/role_session.h': {'bytes': 3741, 'sha256': 'f4b31944536a286d38151e5c1e736fe73b4886373f33dc295518708bb24decc4', 'authority': 'owner-lifetime-source-pins.json', 'authority_path': 'preimage/source/role_session.h'}}
SOURCE_AUTHORITIES={'listener-source-pins.json': {'bytes': 9518, 'sha256': '7adaade107d05204015482abcee84431d8cd1bcc7776fea2a97dcd6488d210fb'}, 'owner-lifetime-source-pins.json': {'bytes': 7698, 'sha256': '072315957a20bd8fdd83efccbea0ca633a3815f867bb07d6091bc42b07762db5'}}
ROOT=Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/role-listener-lifetime-host-build-01-20261105')
SOURCE=ROOT/'source'
OUT=ROOT/'build01'
SOURCE_MANIFEST_SHA='7adaade107d05204015482abcee84431d8cd1bcc7776fea2a97dcd6488d210fb'
BASE_BUILD={'path': '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/registry-owner-destruction-host-build-01-20261105/build01/result.json', 'bytes': 88374, 'sha256': 'e2ac7f9204b7bf9a2f53f11f28f02ac0c7f9e56202a33e1b4f71b69636e5116d'}
BASE_TOOLS={'path': '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/registry-owner-destruction-host-build-01-20261105/build01/tool-inputs-before.json', 'bytes': 15101, 'sha256': '51cd6fca573cd7d9db0fe2b5e49cd64cb6f2167b12a36ea76cb1e28965d33870'}
DEADLINE=None


def execute():
    global DEADLINE
    require(os.getuid()==1000 and os.geteuid()==1000,'ordinary operator UID1000 required')
    require(Path(__file__).absolute()==SOURCE/'build_listener.py','fixed staged controller required')
    real_directory(SOURCE);os.umask(0o077);OUT.mkdir(mode=0o700);(OUT/'tmp').mkdir(mode=0o700)
    DEADLINE=time.monotonic()+180
    require(ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0 and not children(),'owned subreaper required')
    allowed=sorted(os.sched_getaffinity(0));require(len(allowed)>=3,'cannot leave two logical CPUs free')
    os.sched_setaffinity(0,[allowed[-1]])
    report={'schema':1,'state':'RUNNING','scope':'matching OwnerLease preimage/candidate and listener controls; default PLAN only',
            'started_utc':utc(),'Main_actions':0,'Main_identity_observed':False,
            'registry_positive_executed':False,'lease_destruction_controls_executed':False,'listener_controls_executed':False,'platform_policy_qualified':False,
            'factory_service_started':False,'snapshot_created':False,
            'source_manifest_sha256':SOURCE_MANIFEST_SHA,'selected_cpus':[allowed[-1]],
            'commands':[],'objects':{},'artifacts':{}}
    def interrupted(number,frame):raise RuntimeError('owned compiler interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    source_before={};tools={};dependencies={};resource_fd=-1;resource_before=None;artifact_pins={}
    prior_build_pin=None;prior_tools_pin=None;prior_tools={}
    try:
        resource_fd,resource_before=begin_resources();report['owned_resources_before']=resource_before
        prior_raw,prior_build_pin=held(Path(BASE_BUILD['path']),131072)
        require(prior_build_pin['bytes']==BASE_BUILD['bytes'] and prior_build_pin['sha256']==BASE_BUILD['sha256'],
                'prior qualified compiler build receipt differs')
        prior=json.loads(prior_raw)
        require(prior['state']=='PASS_BUILD_ONLY' and prior['source_unchanged_after'] and
                prior['artifacts_unchanged_after'] and not prior['tool_changes'] and
                not prior['dependency_changes'] and prior['owned_resource_gate']['pass'] and
                not any(prior['cleanup'][key] for key in ['forced_cleanup','remaining','errors']) and
                prior['tool_inputs']==BASE_TOOLS, 'prior qualified compiler closure differs')
        prior_tool_raw,prior_tools_pin=held(Path(BASE_TOOLS['path']),32768)
        require(prior_tools_pin['bytes']==BASE_TOOLS['bytes'] and prior_tools_pin['sha256']==BASE_TOOLS['sha256'],
                'prior exact tool manifest differs')
        prior_tools=json.loads(prior_tool_raw)
        require(isinstance(prior_tools,dict) and 0<len(prior_tools)<=64 and
                not verify_resolved(list(prior_tools.values())), 'prior compiler/runtime inputs changed')
        report['prior_build_authority']=prior_build_pin
        report['prior_tool_authority']=prior_tools_pin
        authorities={};authority_pins={}
        for name,pin in SOURCE_AUTHORITIES.items():
            raw,observed=held(SOURCE/name,32768)
            require(observed['bytes']==pin['bytes'] and observed['sha256']==pin['sha256'],
                    'frozen source authority differs: '+name)
            authorities[name]={row['path']:row for row in json.loads(raw)['files']}
            authority_pins[name]=observed
        require(len(SOURCE_INPUTS)==21,'reviewed exact twenty-one source/reference inputs required')
        for name,pin in SOURCE_INPUTS.items():
            frozen=authorities[pin['authority']][pin['authority_path']]
            require(all(frozen[key]==pin[key] for key in ['bytes','sha256']),
                    'reviewed compile input not bound by exact source authority: '+name)
        stage_raw,stage_pin=held(ROOT/'stage-receipt.json',32768);stage=json.loads(stage_raw)['files']
        source_before=regular_tree(SOURCE,25,1024*1024)
        require(set(source_before)==set(stage),'staged source membership differs')
        for name,pin in source_before.items():
            require(pin['bytes']==stage[name]['bytes'] and pin['sha256']==stage[name]['sha256'],
                    'staged source pin mismatch: '+name)
        for name,pin in SOURCE_INPUTS.items():
            require(source_before[name]['bytes']==pin['bytes'] and source_before[name]['sha256']==pin['sha256'],
                    'reviewed input changed: '+name)
        report['source_inputs']=source_before;report['source_authorities']=authority_pins;report['stage_authority']=stage_pin
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
        common_flags=['-std=c++17','-O2','-Wall','-Wextra','-Werror']
        flags={arm:common_flags+(['-I'+str(SOURCE/'preimage/source')] if arm=='preimage' else [])+
                    ['-I'+str(SOURCE/'source'),'-I'+str(SOURCE/'include')] for arm in ['preimage','candidate']}
        units=[('context','source/factory_context.cc','candidate'),
               ('authorization','source/role_authorization.cc','candidate'),
               ('snapshot','source/role_snapshot.cc','candidate'),
               ('wire','source/proc_maps_factory_wire.cc','candidate'),
               ('preimage-session','preimage/source/role_session.cc','preimage'),
               ('candidate-session','source/role_session.cc','candidate'),
               ('admission','source/role_admission.cc','candidate'),
               ('preimage-lease-control','controls/lease_destruction_controls.cc','preimage'),
               ('candidate-lease-control','controls/lease_destruction_controls.cc','candidate'),
               ('listener-control','controls/admission_controls.cc','candidate')]
        before_units={}
        for label,name,arm in units:
            raw=command([compiler,*flags[arm],'-M','-MT','CONTROL',str(SOURCE/name)],SOURCE,env,
                        'dependencies-'+label,report['commands'],30)
            before_units[label]=dependency_files(raw);dependencies.update(before_units[label])
            resolved={row['resolved_path'] for row in before_units[label].values()}
            if label not in ['context','wire']:
                require(str(SOURCE/'source/role_authorization.h') in resolved,
                        'unit did not use the exact repaired Registry header: '+label)
            if label in ['preimage-session','candidate-session','admission','preimage-lease-control',
                         'candidate-lease-control','listener-control']:
                header=SOURCE/('preimage/source/role_session.h' if arm=='preimage' else 'source/role_session.h')
                require(str(header) in resolved, 'arm did not use its exact OwnerLease header: '+label)
        require(0<len(dependencies)<=1024,'complete dependency closure out of bound')
        report['dependency_inputs']=write_new(OUT/'dependency-inputs-before.json',dependencies)
        report['dependency_count']=len(dependencies)
        objects={}
        for label,name,arm in units:
            target=OUT/(label+'.o');md=OUT/(label+'.d')
            command([compiler,*flags[arm],'-MD','-MF',str(md),'-MT','CONTROL','-c',str(SOURCE/name),'-o',str(target)],
                    SOURCE,env,'compile-'+label,report['commands'],45)
            raw,md_pin=held(md,256*1024)
            require(dependency_files(raw)==before_units[label],
                    'actual compiler dependency bytes/identities differ: '+label)
            artifact_pins[label]=hash_held(target,8*1024*1024)
            report['objects'][label]={'object':artifact_pins[label],'actual_md':md_pin,
                                      'dependency_count':len(before_units[label])}
            objects[label]=str(target)
        runtime={}
        common=['context','authorization','snapshot','wire']
        targets={'lease-preimage':common+['preimage-session','preimage-lease-control'],
                 'lease-candidate':common+['candidate-session','candidate-lease-control'],
                 'listener':common+['candidate-session','admission','listener-control']}
        for target,unit_names in targets.items():
            binary=OUT/(target+'_controls')
            command([compiler,*common_flags,*[objects[name] for name in unit_names],'-o',str(binary)],
                    SOURCE,env,'link-'+target,report['commands'],30)
            artifact=hash_held(binary,8*1024*1024);artifact_pins[target+'-elf']=artifact
            with binary.open('rb')as stream:require(stream.read(4)==b'\x7fELF','actual result is not ELF')
            require(binary.stat().st_mode&0o111,'actual ELF not executable')
            raw=command(['/usr/bin/ldd',str(binary)],SOURCE,env,target+'-libraries',report['commands'],10).decode()
            require('not found'not in raw,'actual control runtime missing')
            target_runtime={}
            for line in raw.splitlines():
                match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
                if match:target_runtime[match[1]]=pin_tool(match[1]);tools[match[1]]=target_runtime[match[1]]
            require(target_runtime,'actual control library closure empty');runtime.update(target_runtime)
            plan=json.loads(command([str(binary)],SOURCE,env,target+'-default-plan',report['commands'],10))
            expected=({'state':'PLAN_ONLY','owned_cases':9,'root_children':9,'role_children':9,
                       'factory_service_started':False,'Main_actions':0} if target=='listener' else
                      {'state':'PLAN_ONLY','candidate_cases':4,'preimage_cases':2,'Main_actions':0})
            require(plan==expected,'default PLAN contract differs: '+target)
            report['artifacts'][target]={'elf':artifact,'default_plan':plan,'runtime_libraries':target_runtime}
        report['runtime_libraries']=runtime
        require(all(name in prior_tools and row==prior_tools[name] for name,row in tools.items()),
                'a compiler/runtime input differs from the prior qualified build')
        report['compiler_tools_match_prior_build']=True
        report['tool_inputs']=write_new(OUT/'tool-inputs-before.json',tools)
        report['state']='PASS_BUILD_ONLY'
    except Exception as error:
        report['state']='FAIL';report['error']={'type':type(error).__name__,'message':str(error),
                                               'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['cleanup']=cleanup_children()
        try:
            report['source_unchanged_after']=bool(source_before)and regular_tree(SOURCE,25,1024*1024)==source_before
            require(prior_build_pin is not None and prior_tools_pin is not None and
                    held(Path(BASE_BUILD['path']),131072)[1]==prior_build_pin and
                    held(Path(BASE_TOOLS['path']),32768)[1]==prior_tools_pin,
                    'prior build/tool authorities changed')
            report['prior_tool_changes']=verify_resolved(list(prior_tools.values()))
            require(not report['prior_tool_changes'],'prior compiler/runtime source changed during build')
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
