#!/usr/bin/env python3
import datetime,hashlib,json,os,re,signal,stat,subprocess,sys,time,tarfile,tomllib
from pathlib import Path,PurePosixPath

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

ROOT=Path('/home/alex/work/pocket4-blueprint-streaming-builder-registry-readonly-01-20261105')
SOURCE=Path('/home/alex/work/pocket4-blueprint-streaming-builder-450-compile-02-20261105/builder-source')
LOCK=SOURCE/'Cargo.lock'
TREE=SOURCE.parent/'control-source/selected-build.stdout'
SOURCE_ROOT=Path('/home/alex/.cargo/registry/src')
CACHE_ROOT=Path('/home/alex/.cargo/registry/cache')
LOCK_SHA='c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62'
TREE_SHA='82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d'
DEADLINE=None

def error_detail(error):
    return {'type':type(error).__name__,'message':str(error),
            'errno':getattr(error,'errno',None),'filename':str(getattr(error,'filename',None))}

def observe_file(path,maximum,include_text=False):
    try:
        raw,row=held(path,maximum)
        if include_text:row['text']=raw.decode('utf-8')
        return row
    except OSError as error:return {'path':str(path),'error':error_detail(error)}

def archive_source_comparison(archive,directory,name,version,expected):
    fd=os.open(archive,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=32*1024*1024,'archive type/size outside bound')
        digest=hashlib.sha256();size=0
        while True:
            chunk=os.read(fd,65536)
            if not chunk:break
            size+=len(chunk);require(size<=32*1024*1024,'archive grew beyond bound');digest.update(chunk)
        archive_pin={'path':str(archive),'bytes':size,'sha256':digest.hexdigest(),'identity':identity(before)}
        require(size==before.st_size and digest.hexdigest()==expected,'existing archive checksum differs from original Cargo.lock')
        source_before=regular_tree(directory,4096,64*1024*1024)
        os.lseek(fd,0,os.SEEK_SET)
        files={};directories=set();total=0;prefix=name+'-'+version+'/'
        with os.fdopen(os.dup(fd),'rb') as stream,tarfile.open(fileobj=stream,mode='r:gz') as packed:
            for member in packed:
                require(time.monotonic()<DEADLINE,'bounded registry observation deadline exhausted')
                if member.isdir() and member.name.rstrip('/')==name+'-'+version:
                    require('' not in directories,'duplicate archive root directory')
                    directories.add('');continue
                require(member.name.startswith(prefix) and not member.name.startswith('/'),'unexpected archive root')
                relative=member.name[len(prefix):]
                path=PurePosixPath(relative)
                require(relative and '..' not in path.parts and str(path)==relative.rstrip('/'),'noncanonical archive member')
                require(len(files)+len(directories)<4096,'archive member count exceeds bound')
                if member.isdir():
                    require(relative not in directories,'duplicate archive directory')
                    directories.add(relative);continue
                require(member.isfile() and relative not in files,'archive alias, special file or duplicate rejected')
                require(0<=member.size<=16*1024*1024 and total+member.size<=64*1024*1024,'archive expansion exceeds bound')
                reader=packed.extractfile(member);require(reader is not None,'archive regular member unreadable')
                member_hash=hashlib.sha256();member_size=0
                while True:
                    chunk=reader.read(65536)
                    if not chunk:break
                    member_size+=len(chunk);require(member_size<=member.size,'archive member exceeded declared size');member_hash.update(chunk)
                require(member_size==member.size,'archive member truncated')
                total+=member_size
                require(relative in source_before and source_before[relative]['bytes']==member_size and
                        source_before[relative]['sha256']==member_hash.hexdigest(),'extracted source differs from locked archive: '+str(directory/relative))
                files[relative]={'bytes':member_size,'sha256':member_hash.hexdigest(),'extracted':source_before[relative]}
        require(files,'empty source archive')
        extra={name:row for name,row in source_before.items() if name not in files}
        require(regular_tree(directory,4096,64*1024*1024)==source_before,'extracted source changed during archive comparison')
        require(identity(before)==identity(os.fstat(fd))==identity(archive.lstat()),'archive changed during comparison')
        return {'archive':archive_pin,'archive_matches_lock':True,'archive_files':len(files),'archive_bytes':total,
                'every_archive_file_matches_held_extracted_source':True,'extra_extracted_files':extra,
                'extra_files_are_only_cargo_marker':set(extra)<=set(['.cargo-ok']),
                'source_inventory':write_new(ROOT/(name+'-'+version+'-source.json'),{'archive_files':files,'extras':extra}),
                'source_unchanged_after':True}
    finally:os.close(fd)

def execute():
    global DEADLINE
    require(os.getuid()==1000 and os.geteuid()==1000,'ordinary operator UID1000 required')
    real_directory(ROOT.parent);os.umask(0o077);ROOT.mkdir(mode=0o700);DEADLINE=time.monotonic()+80
    allowed=sorted(os.sched_getaffinity(0));require(len(allowed)>=3,'cannot leave two logical CPUs free');os.sched_setaffinity(0,[allowed[-1]])
    result={'schema':1,'state':'RUNNING','started_utc':utc(),'scope':'fixed selected 45 existing registry packages; no Cargo execution or source writes',
            'Main_actions':0,'builds_started':0,'network_fetches':0,'packages':[],'selected_cpus':[allowed[-1]],'collection_complete':False}
    def interrupted(number,frame):raise RuntimeError('registry read interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    resource_fd=-1;resource_before=None;authorities={}
    try:
        resource_fd,resource_before=begin_resources();result['owned_resources_before']=resource_before
        lock_raw,lock_pin=held(LOCK,65536);tree_raw,tree_pin=held(TREE,4096)
        require(sha(lock_raw)==LOCK_SHA and sha(tree_raw)==TREE_SHA,'fixed dependency authority changed')
        authorities={str(LOCK):lock_pin,str(TREE):tree_pin};result['authority']=authorities
        packages={}
        for line in tree_raw.decode().splitlines():
            match=re.fullmatch(r'([A-Za-z0-9_-]+) v([0-9][A-Za-z0-9.+-]*)(?: \(proc-macro\))?(?: \((/[^()\n]+)\))?(?: \(\*\))?',line)
            require(match is not None,'unrecognized actual selected tree')
            name,version,path=match.groups()
            if path is None:packages[(name,version)]=None
        require(len(packages)==45,'fixed selected registry count differs')
        locked=tomllib.loads(lock_raw.decode())['package']
        real_directory(SOURCE_ROOT);real_directory(CACHE_ROOT)
        roots=sorted(SOURCE_ROOT.iterdir())
        require(0<len(roots)<=16 and all(stat.S_ISDIR(p.lstat().st_mode) for p in roots),'registry source root bound/aliases')
        result['registry_roots']=[{'path':str(p),'identity':identity(p.lstat())} for p in roots]
        for name,version in sorted(packages):
            require(time.monotonic()<DEADLINE,'bounded registry observation deadline exhausted')
            row={'name':name,'version':version};result['packages'].append(row)
            try:
                candidates=[p/(name+'-'+version) for p in roots if os.path.lexists(p/(name+'-'+version))]
                require(len(candidates)==1,'selected source cache directory absent or ambiguous')
                directory=candidates[0];real_directory(directory);row['source_directory']=str(directory)
                children=list(directory.iterdir());require(len(children)<=128,'selected package top-level listing exceeds bound')
                row['top_level']=[{'name':p.name,'mode':p.lstat().st_mode,'bytes':p.lstat().st_size} for p in sorted(children)]
                row['cargo_checksum_manifest']=observe_file(directory/'.cargo-checksum.json',4*1024*1024)
                row['cargo_ok']=observe_file(directory/'.cargo-ok',4096,True)
                row['cargo_manifest']=observe_file(directory/'Cargo.toml',1024*1024)
                matches=[p for p in locked if p['name']==name and p['version']==version and p.get('source')=='registry+https://github.com/rust-lang/crates.io-index']
                require(len(matches)==1,'selected package missing or ambiguous in exact lock')
                archive=CACHE_ROOT/directory.parent.name/(name+'-'+version+'.crate')
                row['expected_archive_path']=str(archive);row['expected_lock_checksum']=matches[0]['checksum']
                real_directory(archive.parent)
                row['comparison']=archive_source_comparison(archive,directory,name,version,matches[0]['checksum'])
            except Exception as error:row['error']=error_detail(error)
        result['collection_complete']=True
        result['all_45_archive_and_source_matches']=len(result['packages'])==45 and all('comparison' in r and
            r['comparison']['archive_matches_lock'] and r['comparison']['every_archive_file_matches_held_extracted_source'] and
            r['comparison']['extra_files_are_only_cargo_marker'] for r in result['packages'])
        result['state']='PASS' if result['all_45_archive_and_source_matches'] else 'FAIL'
    except Exception as error:result['state']='FAIL';result['error']=error_detail(error)
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        try:
            result['authorities_unchanged_after']=bool(authorities) and all(hash_held(Path(p))==row for p,row in authorities.items())
            require(result['authorities_unchanged_after'],'dependency authorities changed')
        except Exception as error:result['after_error']=error_detail(error);result['state']='FAIL'
        try:
            require(resource_fd>=0 and resource_before is not None,'missing owned cgroup before observation')
            result['owned_resource_gate']=finish_resources(resource_fd,resource_before,result)
        except Exception as error:result['resource_error']=error_detail(error);result['state']='FAIL'
        finally:
            if resource_fd>=0:os.close(resource_fd)
    result['finished_utc']=utc();pin=write_new(ROOT/'result.json',result)
    print(json.dumps({'state':result['state'],'result':pin}),flush=True);return 0 if result['state']=='PASS' else 1

if __name__=='__main__':
    if sys.argv[1:]!=['--execute-once']:
        print(json.dumps({'mode':'PLAN','packages':45,'source_writes':0,'Cargo_execution':False,'Main_actions':0}))
    else:raise SystemExit(execute())
