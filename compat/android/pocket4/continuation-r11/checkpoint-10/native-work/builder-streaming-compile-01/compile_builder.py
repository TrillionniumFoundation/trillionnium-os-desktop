#!/usr/bin/env python3
"""Compile only an isolated normal builder with a frozen 1-change/1-addition source delta."""
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import tomllib

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
    require(fields['memory.max'] == '1073741824' and fields['cpu.max'] == '100000 100000', 'owned resource limits do not match the request')
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

BASE_SOURCE = Path('/home/alex/work/pocket4-signal-mask-r11-build-memory-01/builder-source')
ROOT = Path('/home/alex/work/pocket4-blueprint-streaming-builder-450-compile-01-20261105')
HERE = ROOT/'control-source'
OUT = ROOT/'attempt01'
COPIED = ROOT/'builder-source'
RUSTUP = Path('/home/alex/.cargo/bin/rustup')
RUSTUP_HOME = Path('/home/alex/.rustup')
CARGO_HOME = Path('/home/alex/.cargo')
TOOLCHAIN = '1.93.0'
MANIFEST_449 = 'e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017'
MANIFEST_450 = '6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4'
RUST_DELTA = '425f3a5bdeafec1f5f7e821cc575597c1075677715341d08a8588c8bd25a4a28'
GO_PATCH = '9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307'
OBSERVATION = 'PENDING_ACTUAL_RUST193_RESULT_SHA256'
GO_CONTROL = 'PENDING_ACTUAL_GO_CONTROL_RESULT_SHA256'
PATCH_PATH = 'android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch'
TESTS = [
    'android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes',
    'android::tests::restoration_preserves_original_and_removes_created_file',
    'android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch',
    'android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout',
    'android::patch_tests::interrupted_projection_recovers_before_next_build',
    'tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets',
    'tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory',
]
DEADLINE = None
OBSERVED_SIGNALS = []

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

def pinned_packet(name, digest):
    raw,row=held(HERE/name,1024*1024)
    require(row['sha256']==digest,'staged input changed: '+name)
    return raw,row

def exact_source_copy(expected):
    before=regular_tree(BASE_SOURCE)
    portable(before,expected)
    require(not COPIED.exists() and not COPIED.is_symlink(),'create-only builder copy already exists')
    COPIED.mkdir(mode=0o700)
    for name,row in before.items():
        data,pin=held(BASE_SOURCE/name,4*1024*1024)
        require(pin==row,'original source changed while copying: '+name)
        destination=COPIED/name
        write_new(destination,data)
        os.chmod(destination,stat.S_IMODE(row['identity'][2]),follow_symlinks=False)
    copied=regular_tree(COPIED)
    portable(copied,expected)
    require(regular_tree(BASE_SOURCE)==before,'original source changed during copy')
    return before,copied

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

def pin_resolved(path, allowed):
    resolved=path.resolve(strict=True)
    require(any(resolved.is_relative_to(root) for root in allowed) or resolved==Path('/usr/libexec/gcc/x86_64-linux-gnu/15/collect2'),
            'resolved tool/library outside allowed roots/exact observed collect2: '+str(path))
    row=hash_held(resolved)
    row['requested_path']=str(path)
    row['resolved_path']=str(resolved)
    require(path.resolve(strict=True)==resolved,'tool resolution changed during observation')
    return row

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

def toolchain(report, base_env):
    observation,_=pinned_packet('rust193-tools-read02-result.json',OBSERVATION)
    actual=json.loads(observation)
    require(actual['complete'] is True and actual['repository_channel']==TOOLCHAIN and
            actual['repository_toolchain']['sha256']=='8bc51ecab82415fddd8489604f2424e137d71856e7f65cbdcfaa48850d794b46',
            'tool authority is not the observed installed repository channel')
    expected={r['requested_path']:r for r in actual['tools']}
    require(len(expected)==12,'fixed observed repository/linker tool pins missing')
    allowed=[Path('/usr/bin'),Path('/usr/lib'),Path('/home/alex/.cargo/bin'),RUSTUP_HOME/'toolchains']
    rows=[]
    for path,wanted in expected.items():
        row=pin_resolved(Path(path),allowed)
        require(row['sha256']==wanted['sha256'] and row['bytes']==wanted['bytes'] and row['resolved_path']==wanted['resolved_path'],
                'observed tool changed before compilation: '+path)
        rows.append(row)
    selected={}
    for name in ['cargo','rustc']:
        raw=command([str(RUSTUP),'which','--toolchain',TOOLCHAIN,name],COPIED,base_env,'resolve-'+name,report['commands'],10)
        path=Path(raw.decode().strip())
        require(path.is_absolute() and path.name==name and path.is_relative_to(RUSTUP_HOME/'toolchains') and
                path.parent.parent.name==TOOLCHAIN+'-x86_64-unknown-linux-gnu','fixed repository toolchain not installed: '+str(path))
        selected[name]=path
        require(str(path) in expected,'resolved compiler was not pinned by the read-only authority')
        observed=pin_resolved(path,allowed)
        require(observed['sha256']==expected[str(path)]['sha256'],'repository compiler changed since authority read')
        rows.append(observed)
    sysroot=selected['rustc'].parent.parent
    require(selected['cargo'].parent.parent==sysroot,'cargo/rustc toolchain mismatch')
    cargo_version=command([str(selected['cargo']),'--version'],COPIED,base_env,'cargo-version',report['commands'],10).decode()
    rustc_version=command([str(selected['rustc']),'-vV'],COPIED,base_env,'rustc-version',report['commands'],10).decode()
    require(cargo_version.startswith('cargo '+TOOLCHAIN+' ') and '\nrelease: '+TOOLCHAIN+'\n' in rustc_version,
            'actual toolchain version differs from repository pin')
    for path in [Path('/usr/bin/git'),Path('/usr/bin/ninja'),Path('/usr/bin/cp'),Path('/usr/bin/ldd')]:
        rows.append(pin_resolved(path,allowed))
    # Capture the installed compiler and target-library closure, not just the small rustc driver executable.
    library_rows=regular_tree(sysroot/'lib/rustlib/x86_64-unknown-linux-gnu/lib',512,1536*1024*1024)
    for row in library_rows.values():
        row.update({'requested_path':row['path'],'resolved_path':row['path']})
        rows.append(row)
    for path in sorted((sysroot/'lib').glob('*.so*')):
        rows.append(pin_resolved(path,allowed))
    linked=set()
    for index,path in enumerate([selected['cargo'],selected['rustc'],Path('/usr/bin/cc'),Path('/usr/bin/ld'),Path('/usr/bin/git'),Path('/usr/bin/ninja')]):
        raw=command(['/usr/bin/ldd',str(path)],COPIED,base_env,'linked-libraries-'+str(index),report['commands'],10).decode()
        require('not found' not in raw,'tool runtime library missing')
        for line in raw.splitlines():
            match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:
                linked.add(match.group(1))
    for name in sorted(linked):
        rows.append(pin_resolved(Path(name),allowed+[Path('/usr/lib'),Path('/lib')]))
    unique={row['requested_path']:row for row in rows}
    report['actual_toolchain']={'repository_version':TOOLCHAIN,'cargo':str(selected['cargo']),
                              'rustc':str(selected['rustc']),'cargo_version':cargo_version,'rustc_verbose_version':rustc_version,
                              'selection_installs_or_updates':False,'global_stable_1_95_not_used':True}
    return selected,list(unique.values())

def dependency_sources(metadata):
    lock=tomllib.loads((COPIED/'Cargo.lock').read_text())
    checksums_by_package={(p['name'],p['version'],p.get('source')):p.get('checksum') for p in lock['package']}
    packages={p['id']:p for p in metadata['packages']}
    roots=[p['id'] for p in packages.values() if p['name']=='droidloom-update' and Path(p['manifest_path'])==COPIED/'tools/droidloom-update/Cargo.toml']
    require(len(roots)==1,'selected package not the exact copied builder')
    edges={n['id']:n['dependencies'] for n in metadata['resolve']['nodes']}
    pending=list(roots);reachable=set()
    while pending:
        current=pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        require(len(reachable)<=512 and current in packages and current in edges,'dependency graph bound/incompleteness')
        pending.extend(edges[current])
    collected={};descriptions=[]
    for package_id in sorted(reachable):
        package=packages[package_id]
        directory=Path(package['manifest_path']).parent
        if directory.is_relative_to(COPIED):
            descriptions.append({'id':package_id,'kind':'pinned-builder-source','manifest':package['manifest_path']})
            continue
        require(directory.is_relative_to(CARGO_HOME/'registry/src') and (package.get('source') or '').startswith('registry+'),
                'dependency is not an offline registry source or copied workspace member: '+package_id)
        rows=regular_tree(directory,4096,64*1024*1024)
        checksum_raw,_=held(directory/'.cargo-checksum.json',4*1024*1024)
        checksums=json.loads(checksum_raw)
        require(checksums['package']==checksums_by_package[(package['name'],package['version'],package['source'])],
                'registry package checksum differs from original Cargo.lock: '+package_id)
        for name,digest in checksums['files'].items():
            require(name in rows and rows[name]['sha256']==digest,'registry source checksum mismatch: '+package_id+'/'+name)
        for row in rows.values():
            require(len(collected)<16384,'complete dependency inventory too large')
            collected[row['path']]=row
        descriptions.append({'id':package_id,'kind':'offline-registry','manifest':package['manifest_path'],
                             'recorded_files':len(rows),'package_checksum':checksums['package']})
    return roots[0],descriptions,collected

def build_artifact(raw, package_id, test):
    artifacts=[]
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        item=json.loads(line)
        if item.get('reason')=='compiler-artifact' and item.get('package_id')==package_id and item['target']['name']=='droidloom-update' and item.get('executable') and bool(item['profile']['test'])==test:
            artifacts.append(Path(item['executable']))
    require(len(artifacts)==1,'actual Cargo artifact set is not the one selected builder')
    artifact=artifacts[0]
    require(artifact.is_relative_to(OUT/'cargo-target'),'artifact escaped fresh owned target')
    return artifact

def execute():
    global DEADLINE
    require(os.getuid()==1000 and os.geteuid()==1000,'ordinary operator UID1000 required')
    require(Path(__file__).absolute()==HERE/'compile_builder.py','exact staged controller required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(),'create-only attempt already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    (OUT/'tmp').mkdir(mode=0o700)
    DEADLINE=time.monotonic()+550
    libc=ctypes.CDLL(None,use_errno=True)
    require(libc.prctl(36,1,0,0,0)==0,'cannot establish owned subreaper')
    require(not children(),'unexpected initial child')
    allowed=sorted(os.sched_getaffinity(0))
    require(len(allowed)>=3,'cannot leave two logical CPUs free')
    os.sched_setaffinity(0,[allowed[-1]])
    report={'schema':1,'state':'RUNNING','started_utc':utc(),'scope':'fresh normal 450-file Rust builder only; no Android/full-engine/service execution',
            'Main_actions':0,'Main_identity_observed':False,'install_actions':0,'network_downloads_permitted':False,
            'commands':[],'allowed_cpus_before':allowed,'selected_cpus':[allowed[-1]],'expected_test_names':TESTS}
    def interrupted(number,frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned controller interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    resource_fd=-1;resource_before=None
    original_rows={};candidate_rows={};dependency_rows={};tool_rows=[];config_rows=[]
    copied_expected=None;config_paths=[];builder=None;builder_pin=None;test_binary=None;test_pin=None
    try:
        resource_fd,resource_before=begin_resources()
        report['owned_resources_before']=resource_before
        go_control_raw,go_control_pin=pinned_packet('go-control-result.json',GO_CONTROL)
        go_control=json.loads(go_control_raw)
        require(go_control['state']=='PASS' and go_control['patch']['sha256']==GO_PATCH and
                go_control['fixture']['sha256']=='5a928d10fbaabab5a1198c9c4a5abe9281da091abdde923a2e0a500071e8fbc5' and
                go_control['whole_output_files_equal']>0 and go_control['owned_resource_gate']['pass'] is True,
                'actual complete-package comparison gate is not qualified')
        report['actual_Go_comparison_gate']=go_control_pin
        report['upstream_vet_pass_claimed']=False
        old_bytes,_=pinned_packet('original-builder-449-manifest.json',MANIFEST_449)
        new_bytes,_=pinned_packet('expected-builder-450-manifest.json',MANIFEST_450)
        expected=json.loads(old_bytes);copied_expected=json.loads(new_bytes)
        require(len(expected)==449 and len(copied_expected)==450,'source manifest count changed')
        original_rows,_=exact_source_copy(expected)
        original_manifest=portable(original_rows,expected)
        report['original_manifest']=write_new(OUT/'original-builder-source-manifest.json',(json.dumps(original_manifest,indent=2)+'\n').encode())
        env={'PATH':'/usr/bin:/bin','HOME':'/home/alex','CARGO_HOME':str(CARGO_HOME),'RUSTUP_HOME':str(RUSTUP_HOME),
             'RUSTUP_SKIP_UPDATE_CHECK':'1','RUSTUP_TOOLCHAIN':TOOLCHAIN,'CARGO_NET_OFFLINE':'true','LC_ALL':'C','LANG':'C',
             'TMPDIR':str(OUT/'tmp'),'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
        tools,tool_rows=toolchain(report,env)
        report['tool_inputs']=write_new(OUT/'tool-inputs-before.json',tool_rows)
        rust_patch,_=pinned_packet('normal-projection.patch',RUST_DELTA)
        go_patch,_=pinned_packet('0009-blueprint-stream-uncached-module-actions.patch',GO_PATCH)
        require(rust_patch.count(b'--- a/tools/droidloom-update/src/android.rs\n')==1,'unexpected normal projection patch')
        command(['/usr/bin/git','apply','--check',str(HERE/'normal-projection.patch')],COPIED,env,'normal-projection-check',report['commands'],10)
        command(['/usr/bin/git','apply',str(HERE/'normal-projection.patch')],COPIED,env,'normal-projection-apply',report['commands'],10)
        # git apply recreates the worktree file under our 077 umask; restore the exact recorded source mode.
        os.chmod(COPIED/'tools/droidloom-update/src/android.rs',expected['tools/droidloom-update/src/android.rs']['mode'],follow_symlinks=False)
        write_new(COPIED/PATCH_PATH,go_patch)
        os.chmod(COPIED/PATCH_PATH,0o664,follow_symlinks=False)
        candidate_rows=regular_tree(COPIED)
        actual_map=portable(candidate_rows,copied_expected)
        actual_bytes=(json.dumps(actual_map,indent=2)+'\n').encode()
        require(sha(actual_bytes)==MANIFEST_450,'actual copied 450 manifest bytes differ')
        report['copied_manifest']=write_new(OUT/'copied-builder-source-manifest.json',actual_bytes)
        report['source_delta']={'changed_existing':['tools/droidloom-update/src/android.rs'],'added':[PATCH_PATH],
                                'unchanged_existing':448,'engine_source_files_changed':0,'Go6_patch_changed':False}
        env.update({'PATH':str(tools['cargo'].parent)+':/usr/bin:/bin','RUSTC':str(tools['rustc']),
                    'RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'',
                    'CARGO_TARGET_DIR':str(OUT/'cargo-target'),'CARGO_BUILD_JOBS':'1',
                    'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER':'/usr/bin/cc'})
        config_paths=[CARGO_HOME/'config',CARGO_HOME/'config.toml']
        for parent in [COPIED,*COPIED.parents]:
            config_paths += [parent/'.cargo/config',parent/'.cargo/config.toml']
        config_rows=read_existing_config(config_paths)
        report['cargo_config_inputs_before']=config_rows
        report['build_environment']=env
        metadata_raw=command([str(tools['cargo']),'metadata','--offline','--locked','--format-version','1','--filter-platform','x86_64-unknown-linux-gnu'],COPIED,env,'metadata',report['commands'],60)
        metadata=json.loads(metadata_raw)
        package_id,packages,dependency_rows=dependency_sources(metadata)
        report['dependency_inputs']=write_new(OUT/'dependency-inputs-before.json',{'packages':packages,'files':dependency_rows})
        common=[str(tools['cargo']),'--offline','--locked','-j','1','-p','droidloom-update','--bin','droidloom-update']
        build=command([common[0],'build',*common[1:],'--message-format=json-render-diagnostics'],COPIED,env,'builder-compile',report['commands'],240)
        builder=build_artifact(build,package_id,False)
        builder_pin=hash_held(builder)
        require((builder.lstat().st_mode&0o111)!=0,'builder artifact is not executable')
        with builder.open('rb') as stream:
            require(stream.read(4)==b'\x7fELF','builder artifact is not ELF')
        help_output=command([str(builder),'--help'],COPIED,env,'builder-help',report['commands'],10)
        require(b'Usage:' in help_output and b'native-engine-build' in help_output,'normal builder CLI missing target closure command')
        test_build=command([common[0],'test',*common[1:],'--no-run','--message-format=json-render-diagnostics'],COPIED,env,'builder-test-compile',report['commands'],180)
        test_binary=build_artifact(test_build,package_id,True)
        test_pin=hash_held(test_binary)
        test_list=command([str(test_binary),'--list'],COPIED,env,'builder-test-list',report['commands'],10).decode()
        require(all(name+': test' in test_list for name in TESTS),'focused existing tests absent from actual test executable')
        for index,name in enumerate(TESTS):
            output=command([str(test_binary),'--exact',name,'--test-threads=1','--nocapture'],COPIED,env,'projection-test-'+str(index),report['commands'],30).decode()
            require('test result: ok. 1 passed; 0 failed;' in output and 'test '+name+' ... ok' in output,
                    'focused test did not actually execute exactly once: '+name)
        require(hash_held(builder)==builder_pin and hash_held(test_binary)==test_pin,'actual ELF changed while tested')
        report['builder_elf']=builder_pin
        report['test_elf']=test_pin
        report['focused_tests_passed']=len(TESTS)
        report['state']='PASS'
    except Exception as error:
        report['state']='FAIL'
        report['error']=repr(error)
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['observed_signals']=OBSERVED_SIGNALS
        report['cleanup']=cleanup_children()
        for label,source,rows in [('original_source',BASE_SOURCE,original_rows),('copied_source',COPIED,candidate_rows)]:
            try:
                unchanged=bool(rows) and regular_tree(source)==rows
                report[label+'_unchanged_after']=unchanged
                if not unchanged:
                    report['state']='FAIL'
            except Exception as error:
                report[label+'_after_error']=repr(error);report['state']='FAIL'
        changes=[]
        for path,row in dependency_rows.items():
            try:
                if hash_held(Path(path))!=row:
                    changes.append(path)
            except Exception as error:
                changes.append({'path':path,'error':repr(error)})
        report['dependency_changes']=changes
        report['tool_changes']=verify_resolved(tool_rows)
        try:
            report['cargo_configs_unchanged_after']=bool(config_rows) and read_existing_config(config_paths)==config_rows
        except Exception as error:
            report['cargo_configs_unchanged_after']=False;report['cargo_config_after_error']=repr(error)
        if changes or report['tool_changes'] or not report['cargo_configs_unchanged_after']:
            report['state']='FAIL'
        cleanup=report['cleanup']
        if cleanup['forced_cleanup'] or cleanup['remaining'] or cleanup['errors']:
            report['state']='FAIL'
        try:
            require(resource_fd>=0 and resource_before is not None,'owned resource admission not observed')
            report['owned_resource_gate']=finish_resources(resource_fd,resource_before,report)
        except Exception as error:
            report['owned_resource_gate']={'pass':False,'error':repr(error)};report['state']='FAIL'
        finally:
            if resource_fd>=0:
                os.close(resource_fd)
        report['finished_utc']=utc()
        result=write_new(OUT/'result.json',report)
        print(json.dumps({'state':report['state'],'result':result,'builder_elf':report.get('builder_elf'),
                          'Main_actions':0,'full_engine_build':False}),flush=True)
    return 0 if report['state']=='PASS' else 1

if __name__=='__main__':
    if sys.argv[1:]==[]:
        print(json.dumps({'mode':'PLAN','root':str(ROOT),'base_source':str(BASE_SOURCE),'source_files':450,
                          'requires_explicit_execute_once':True,'Rust_toolchain':TOOLCHAIN,'Main_actions':0,
                          'Android_and_full_engine_execution':False,'focused_existing_tests':TESTS}))
    elif sys.argv[1:]==['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: compile_builder.py [--execute-once]')
