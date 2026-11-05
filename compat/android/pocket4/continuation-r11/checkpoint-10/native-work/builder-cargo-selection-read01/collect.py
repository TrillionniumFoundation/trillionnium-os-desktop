#!/usr/bin/env python3
"""Offline, locked package-selection observations only; no compilation or build scripts."""
import ctypes,datetime,hashlib,json,os,signal,stat,subprocess,sys,time
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

def portable(rows, expected):
    require(set(rows)==set(expected),'complete source path set changed')
    result={}
    for name in expected:
        row=rows[name]
        result[name]={'kind':'file','sha256':row['sha256'],'bytes':row['bytes'],
                      'mode':stat.S_IMODE(row['identity'][2])}
    require(result==expected,'complete source manifest differs')
    return result

def read_existing_config(paths):
    rows=[]
    for path in paths:
        try:
            path.lstat()
        except FileNotFoundError:
            rows.append({'path':str(path),'absent':True})
            continue
        rows.append(hash_held(path,1024*1024))
    return rows

ROOT=Path('/home/alex/work/pocket4-blueprint-streaming-builder-cargo-selection-readonly-01-20261105')
OUT=ROOT
SOURCE=Path('/home/alex/work/pocket4-blueprint-streaming-builder-450-compile-01-20261105/builder-source')
AUTHORITY=SOURCE.parent/'control-source/expected-builder-450-manifest.json'
MANIFEST_SHA='6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4'
TOOLS={
 '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/cargo':'9548937d530bf439ff1ba47a3b2bd26eeb9c3aff1961c20c01798613de922578',
 '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/rustc':'d32249a7c3bfcfc67b471460386e46323accae7125e344567a12d5664d99bb57'}
DEADLINE=None

def execute():
 global DEADLINE
 require(os.getuid()==1000 and os.geteuid()==1000,'ordinary operator UID1000 required')
 real_directory(ROOT.parent);os.umask(0o077);ROOT.mkdir(mode=0o700);(ROOT/'tmp').mkdir(mode=0o700)
 DEADLINE=time.monotonic()+50
 require(ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0,'cannot establish owned subreaper')
 require(not children(),'unexpected initial child')
 allowed=sorted(os.sched_getaffinity(0));require(len(allowed)>=3,'cannot leave two logical CPUs free')
 os.sched_setaffinity(0,[allowed[-1]])
 report={'schema':1,'state':'RUNNING','started_utc':utc(),'scope':'offline locked metadata no-deps and selected cargo tree; no Rust compilation or build-script execution',
  'Main_actions':0,'builds_started':0,'network_downloads_permitted':False,'source_changes_permitted':False,'commands':[],
  'cargo_cache_locks_or_already_cached_archive_extraction_not_prohibited':True,'selected_cpus':[allowed[-1]]}
 def interrupted(number,frame):raise RuntimeError('selection query interrupted by signal '+str(number))
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
 resource_fd=-1;resource_before=None;source_before={};tools_before={};config_before=[];config_paths=[];authority_before=None
 try:
  resource_fd,resource_before=begin_resources();report['owned_resources_before']=resource_before
  raw,authority_before=held(AUTHORITY,131072);require(sha(raw)==MANIFEST_SHA,'450 source authority changed')
  expected=json.loads(raw);require(len(expected)==450,'expected full 450 map')
  source_before=regular_tree(SOURCE);portable(source_before,expected)
  report['source_authority']=authority_before;report['source_before']=write_new(ROOT/'source-before.json',source_before)
  for path,digest in TOOLS.items():
   row=hash_held(Path(path),64*1024*1024);require(row['sha256']==digest,'pinned 1.93 tool changed: '+path);tools_before[path]=row
  report['tools_before']=tools_before
  config_paths=[Path('/home/alex/.cargo/config'),Path('/home/alex/.cargo/config.toml')]
  for parent in [SOURCE,*SOURCE.parents]:config_paths.extend([parent/'.cargo/config',parent/'.cargo/config.toml'])
  config_before=read_existing_config(config_paths);report['cargo_configs_before']=config_before
  cargo,rustc=list(TOOLS)
  env={'PATH':str(Path(cargo).parent)+':/usr/bin:/bin','HOME':'/home/alex','CARGO_HOME':'/home/alex/.cargo','RUSTUP_HOME':'/home/alex/.rustup',
   'RUSTUP_SKIP_UPDATE_CHECK':'1','RUSTUP_TOOLCHAIN':'1.93.0','CARGO_NET_OFFLINE':'true','LC_ALL':'C','LANG':'C','TMPDIR':str(ROOT/'tmp'),
   'RUSTC':rustc,'RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'',
   'CARGO_TARGET_DIR':str(ROOT/'unused-target'),'CARGO_BUILD_JOBS':'1'}
  report['environment']=env
  raw=command([cargo,'metadata','--offline','--locked','--no-deps','--format-version','1'],SOURCE,env,'workspace-no-deps',report['commands'],15)
  metadata=json.loads(raw);roots=[p for p in metadata['packages'] if p['name']=='droidloom-update' and p['manifest_path']==str(SOURCE/'tools/droidloom-update/Cargo.toml')]
  require(len(roots)==1 and metadata['resolve'] is None,'no-deps result must not be presented as registry closure')
  report['workspace_package_count']=len(metadata['packages']);report['selected_package_id']=roots[0]['id']
  for label,edges in [('selected-build','normal,build'),('selected-test','normal,build,dev')]:
   raw=command([cargo,'tree','--offline','--locked','-p','droidloom-update','--target','x86_64-unknown-linux-gnu',
    '--edges',edges,'--prefix','none','--format','{p}','--color','never'],SOURCE,env,label,report['commands'],15)
   require(raw.strip() and len(raw)<=131072,'selected tree output missing or outside bound')
  report['state']='PASS'
 except Exception as error:report['error']=repr(error);report['state']='FAIL'
 finally:
  signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
  report['cleanup']=cleanup_children()
  try:
   report['source_unchanged_after']=bool(source_before) and regular_tree(SOURCE)==source_before
   report['tools_unchanged_after']=bool(tools_before) and all(hash_held(Path(path),64*1024*1024)==row for path,row in tools_before.items())
   report['configs_unchanged_after']=read_existing_config(config_paths)==config_before
   report['authority_unchanged_after']=authority_before is not None and held(AUTHORITY,131072)[1]==authority_before
   require(all(report[k] for k in ['source_unchanged_after','tools_unchanged_after','configs_unchanged_after','authority_unchanged_after']),'authority changed during read')
  except Exception as error:report['after_error']=repr(error);report['state']='FAIL'
  try:
   require(resource_fd>=0 and resource_before is not None,'owned resource pre-observation missing')
   report['owned_resource_gate']=finish_resources(resource_fd,resource_before,report)
  except Exception as error:report['resource_error']=repr(error);report['state']='FAIL'
  finally:
   if resource_fd>=0:os.close(resource_fd)
  if report['cleanup']['forced_cleanup'] or report['cleanup']['remaining'] or report['cleanup']['errors']:report['state']='FAIL'
 report['finished_utc']=utc();result=write_new(ROOT/'result.json',report)
 print(json.dumps({'state':report['state'],'result':result}),flush=True)
 return 0 if report['state']=='PASS' else 1

if __name__=='__main__':
 if sys.argv[1:]!=['--execute-once']:
  print(json.dumps({'mode':'PLAN','Main_actions':0,'builds_started':0,'source_changes':0,'offline_locked':True,'execute_requires_exact_flag':True}))
 else:raise SystemExit(execute())
