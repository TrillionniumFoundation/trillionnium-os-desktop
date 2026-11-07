#!/usr/bin/env python3
"""Build fixed host Status/Readiness sources and run owned dispatch regressions."""
import ctypes
import datetime
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import select
import signal
import shutil
import stat
import subprocess
import sys
import time
import tomllib
import tarfile

BASE_SOURCE = Path('/home/alex/work/pocket4-native-builder474-composer-audiocontrol-projection-compile-01-20261106/builder-source')
ROOT = Path('/home/alex/work/p4-st02-20261106')
HERE = ROOT/'control-source'
OUT = ROOT/'attempt01'
COPIED = ROOT/'builder-source'
RUST_SYSROOT = Path('/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu')
CARGO_HOME = Path('/home/alex/.cargo')
TOOLCHAIN = '1.93.0'
OBSERVATION = '60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb'
MANIFEST_PARENT = 'e18fe837795e9c3bd684592f3c91228604b2b21ca9d918ac56cebdb4b40754dd'
MANIFEST_CANDIDATE = 'd8f6213f73726bd3766645e7decb5ebfac852f49852c49545e511a54b689d16e'
PARENT_RESULT_SHA = 'd3b0264441b2af0684c9f147bbb32e274a6d42f96fd83c19f0f24ba6937ad294'
DELTAS = {"runtime/droidloom-supervisor/src/control.rs":{"kind":"file","mode":436,"bytes":71588,"sha256":"50d7bc3abd94f83233ef7d461f93cb714f843cacb3fd5c0e929d06671a95f89b"},"runtime/droidloom-supervisor/src/development.rs":{"kind":"file","mode":436,"bytes":101645,"sha256":"37645978b33d443313694609625a97ac9dd7f6e14053664a48d02ff6d8daea90"},"runtime/droidloom-supervisor/src/bin/droidloomctl.rs":{"kind":"file","mode":436,"bytes":20606,"sha256":"3733dd7586ebf534aef3d4a5d176a76b8822dd0c6a6b8b39fb64adf8e70cd484"},"runtime/droidloom-supervisor/tests/cli_lifecycle.rs":{"kind":"file","mode":436,"bytes":11717,"sha256":"5310bfdb21b006ae1432b584c03fbbfb4c1f3a7cbd3ce226b54770ff4bbca317"},"runtime/droidloom-supervisor/src/control_status_tests.rs":{"kind":"file","mode":436,"bytes":11843,"sha256":"0bafad33112df280c73ceedf675305236275bb043d0909fc4a71f6366c0a6727"}}
CHANGED_PATHS = ["runtime/droidloom-supervisor/src/control.rs","runtime/droidloom-supervisor/src/development.rs","runtime/droidloom-supervisor/src/bin/droidloomctl.rs","runtime/droidloom-supervisor/tests/cli_lifecycle.rs"]
NEW_TEST_PATH = 'runtime/droidloom-supervisor/src/control_status_tests.rs'
LIB_TESTS = ["control::status_lifecycle_tests::status_and_readiness_are_distinct_explicit_wire_requests","control::status_lifecycle_tests::stopped_dispatch_does_not_claim_android_ready","control::status_lifecycle_tests::running_status_dispatch_creates_no_child_and_cannot_replace_fresh_readiness","control::tests::boot_complete_does_not_hide_a_failed_input_service","control::tests::boot_progress_uses_observed_services_and_checks_every_readiness_gate","control::tests::boot_wait_reports_changes_and_a_stall_has_the_last_phase_and_log_commands","control::tests::only_missing_android_services_are_treated_as_boot_progress","control::tests::only_root_or_the_exact_cell_owner_is_authorized"]
OWNED_FIXTURE_TEST = 'control::status_lifecycle_tests::owned_lifecycle_process_fixture'
CLI_TESTS = ["start_waits_for_boot_and_keeps_progress_out_of_json","lifecycle_controls_the_whole_user_service","service_failure_is_reported","internal_cell_operations_do_not_recurse_into_systemd","explicit_mode_reaches_service_and_restart_preserves_it","lifecycle_rejects_a_symlink_runtime_directory","status_and_readiness_use_distinct_single_requests_without_wait_fallback"]
HOST_BINARIES = [["droidloom-supervisor","droidloom-supervisor","runtime/droidloom-supervisor/src/main.rs"],["droidloom-supervisor","droidloomd","runtime/droidloom-supervisor/src/bin/droidloomd.rs"],["droidloom-supervisor","droidloomctl","runtime/droidloom-supervisor/src/bin/droidloomctl.rs"],["droidloom-applications","droidloom-applications","runtime/droidloom-applications/src/main.rs"]]
DEADLINE = None
CHILD_REAPER = None
OBSERVED_SIGNALS = []

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
    observation,observation_pin=pinned_packet('rust193-tools-recheck-read03-result.json',OBSERVATION)
    actual=json.loads(observation)
    require(actual['state']=='PASS_FIXED_TOOL_OBSERVATION_NOT_EXECUTION_APPROVAL' and
            actual['complete'] is True and actual['repository_channel']==TOOLCHAIN and
            actual['repository_toolchain']['sha256']=='8bc51ecab82415fddd8489604f2424e137d71856e7f65cbdcfaa48850d794b46' and
            actual['all_observed_tool_contents_and_aliases_unchanged_after'] is True and
            actual['owned_resource_gate']['pass'] is True and actual['first_error'] is None and
            not actual['secondary_errors'] and actual['commands_executed']==0 and actual['tool_execution'] is False,
            'fixed installed toolchain reobservation is not complete')
    previous,previous_pin=pinned_packet('prior-compile01-failure.json',
            '44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3')
    failed=json.loads(previous)
    require(previous_pin['bytes']==7681 and actual['actual_build_failure']==
                {'bytes':previous_pin['bytes'],'sha256':previous_pin['sha256']} and
            failed['state']=='FAIL' and failed['commands']==[] and
            failed['error']=="RuntimeError('observed tool changed before compilation: /home/alex/.cargo/bin/rustup')" and
            not failed['cleanup']['errors'] and not failed['cleanup']['remaining'] and
            not failed['cleanup']['forced_cleanup'],
            'prior compile01 failure authority differs')
    observed={r['requested_path']:r for r in actual['tools']}
    proxy='/home/alex/.cargo/bin/rustup'
    require(len(observed)==len(actual['tools'])==12 and proxy in observed and
            actual['changed_tools']==[{'changed_admission_fields':['sha256','bytes'],
                'original_object_metadata_equal':False,'path':proxy}],
            'reobservation is not the exact single proxy-content change')
    require(all(row['error'] is None and row['content_read'] is True and
                row['resolution_changed'] is False and
                row['held_before']==row['held_after']==row['resolved_named_after'] and
                row['requested_named_before']==row['requested_named_after'] and
                row['requested_link_text_before']==row['requested_link_text_after']
                for row in actual['tools']),
            'fixed observed tool closure changed during reobservation')
    expected={path:row for path,row in observed.items() if path!=proxy}
    require(len(expected)==11 and all(row['compilation_admission_fields_equal'] is True and
                row['changed_compilation_admission_fields']==[] and
                row['original_object_metadata_equal'] is True for row in expected.values()),
            'a directly used tool differs from the original installed authority')
    require(not any(name.startswith('RUSTUP') for name in base_env) and
            all(name not in base_env for name in ('LD_PRELOAD','LD_LIBRARY_PATH','RUSTC_BOOTSTRAP')) and
            base_env['PATH']=='/usr/bin:/bin' and
            base_env['RUSTC']==str(RUST_SYSROOT/'bin/rustc') and
            base_env['RUSTDOC']==str(RUST_SYSROOT/'bin/rustdoc'),
            'direct toolchain environment contains a proxy selection or inherited override')
    real_directory(RUST_SYSROOT)
    allowed=[Path('/usr/bin'),Path('/usr/lib'),RUST_SYSROOT]
    rows=[]
    for path,wanted in expected.items():
        row=pin_resolved(Path(path),allowed)
        require(row['sha256']==wanted['sha256'] and row['bytes']==wanted['bytes'] and
                row['resolved_path']==wanted['resolved_path'],
                'observed direct tool changed before compilation: '+path)
        rows.append(row)
    selected={name:RUST_SYSROOT/'bin'/name for name in ['cargo','rustc','rustdoc']}
    for name in ['cargo','rustc']:
        path=selected[name]
        require(str(path) in expected and path.resolve(strict=True)==path and
                expected[str(path)]['resolved_path']==str(path),
                'direct compiler path differs from the fixed Rust 1.93 authority: '+name)
    # No doctest is requested. Bind the absolute RUSTDOC path to the same
    # installed sysroot closure now and recheck it with all other tool inputs.
    # Its bytes were not included in the old read02/read03 observation.
    rustdoc=pin_resolved(selected['rustdoc'],allowed)
    require(rustdoc['resolved_path']==str(selected['rustdoc']) and
            stat.S_ISREG(rustdoc['identity'][2]) and rustdoc['identity'][2]&0o111,
            'fixed sysroot rustdoc is aliased or not an executable regular file')
    rows.append(rustdoc)
    sysroot=RUST_SYSROOT
    require(selected['cargo'].parent.parent==selected['rustc'].parent.parent==sysroot,
            'cargo/rustc toolchain mismatch')
    cargo_version=command([str(selected['cargo']),'--version'],COPIED,base_env,'cargo-version',report['commands'],10).decode()
    rustc_version=command([str(selected['rustc']),'-vV'],COPIED,base_env,'rustc-version',report['commands'],10).decode()
    require(cargo_version.startswith('cargo '+TOOLCHAIN+' ') and '\nrelease: '+TOOLCHAIN+'\n' in rustc_version,
            'actual toolchain version differs from repository pin')
    for path in [Path('/usr/bin/git'),Path('/usr/bin/timeout'),Path('/usr/bin/ninja'),Path('/usr/bin/cp'),Path('/usr/bin/ldd')]:
        rows.append(pin_resolved(path,allowed))
    library_rows=regular_tree(sysroot/'lib/rustlib/x86_64-unknown-linux-gnu/lib',512,1536*1024*1024)
    for row in library_rows.values():
        row.update({'requested_path':row['path'],'resolved_path':row['path']})
        rows.append(row)
    for path in sorted((sysroot/'lib').glob('*.so*')):
        rows.append(pin_resolved(path,allowed))
    linked=set()
    for index,path in enumerate([selected['cargo'],selected['rustc'],Path('/usr/bin/cc'),Path('/usr/bin/ld'),
                                Path('/usr/bin/git'),Path('/usr/bin/timeout'),Path('/usr/bin/ninja'),selected['rustdoc']]):
        raw=command(['/usr/bin/ldd',str(path)],COPIED,base_env,'linked-libraries-'+str(index),report['commands'],10).decode()
        require('not found' not in raw,'tool runtime library missing')
        for line in raw.splitlines():
            match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:
                linked.add(match.group(1))
    for name in sorted(linked):
        rows.append(pin_resolved(Path(name),allowed+[Path('/usr/lib'),Path('/lib')]))
    unique={row['requested_path']:row for row in rows}
    require(proxy not in unique,'unused rustup proxy was retained as a compilation input')
    report['actual_tool_reobservation']=observation_pin
    report['prior_compile01_failure_authority']=previous_pin
    report['unused_proxy_observation']={key:observed[proxy][key] for key in
            ['requested_path','resolved_path','bytes','sha256','changed_compilation_admission_fields']}
    report['actual_toolchain']={'repository_version':TOOLCHAIN,'cargo':str(selected['cargo']),
            'rustc':str(selected['rustc']),'rustdoc':str(selected['rustdoc']),
            'cargo_version':cargo_version,'rustc_verbose_version':rustc_version,
            'selection':'explicit observed installed 1.93 cargo/rustc paths; no rustup command',
            'selection_installs_or_updates':False,'global_stable_1_95_not_used':True,
            'rustup_proxy_executed':False,'rustup_proxy_is_compilation_input':False,
            'rustup_proxy_changed_bytes_approved_for_execution':False,
            'rustdoc_observed_with_sysroot_closure_this_attempt':rustdoc,
            'rustdoc_old_hash_prequalified':False,'doctests_requested':False}
    return selected,list(unique.values())

def parse_selected_tree(raw, copied):
    require(0 < len(raw) <= 131072, 'selected tree output outside bound')
    selected={}
    for line in raw.decode('utf-8').splitlines():
        match=re.fullmatch(r'([A-Za-z0-9_-]+) v([0-9][A-Za-z0-9.+-]*)(?: \(proc-macro\))?(?: \((/[^()\n]+)\))?(?: \(\*\))?',line)
        require(match is not None, 'unrecognized pinned Cargo tree line: '+line)
        name,version,directory=match.groups()
        if directory is not None:
            path=Path(directory)
            require(path.is_relative_to(copied) and '..' not in path.parts and str(path)==directory,
                    'selected path package escaped the exact copied source')
        key=(name,version)
        require(key not in selected or selected[key]==directory, 'ambiguous selected package source')
        selected[key]=directory
        require(len(selected)<=128, 'selected package bound exceeded')
    require(selected, 'empty selected dependency tree')
    return selected

def qualify_cached_archive(archive,directory,name,version,expected):
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
        comparison={'archive':archive_pin,'archive_matches_lock':True,'archive_files':len(files),'archive_bytes':total,
                'every_archive_file_matches_held_extracted_source':True,'extra_extracted_files':extra,
                'extra_files_are_only_cargo_marker':set(extra)<=set(['.cargo-ok']),
                'source_inventory':write_new(OUT/(name+'-'+version+'-source.json'),{'archive_files':files,'extras':extra}),
                'source_unchanged_after':True}
        require(set(extra)=={'.cargo-ok'} and extra['.cargo-ok']['bytes']==7 and
                extra['.cargo-ok']['sha256']=='afbf9d0f3560b0fd7795e81c42a0a79ee6b6fc67e064f77826aee642cad28d91',
                'extracted package has unqualified extra files or an altered Cargo marker')
        return comparison,source_before,archive_pin
    finally:os.close(fd)

def qualify_compiler_inputs(raw,packages,dependency_rows,candidate_rows):
    qualified={p['manifest']:p for p in packages}
    qualified_ids={p['id'] for p in packages}
    observed=set()
    for line in raw.decode().splitlines():
        if not line.strip():continue
        item=json.loads(line)
        if item.get('reason')=='compiler-artifact':
            manifest=item.get('manifest_path')
            require(manifest in qualified and item['package_id']==qualified[manifest]['id'],
                    'Cargo compiled a package outside the pre-qualified source closure')
            path=Path(item['target']['src_path'])
            row=dependency_rows.get(str(path))
            if row is None and path.is_relative_to(COPIED):row=candidate_rows.get(str(path.relative_to(COPIED)))
            require(row is not None and hash_held(path)==row, 'actual compiled target source was not qualified or changed')
            observed.add(item['package_id'])
        elif item.get('reason')=='build-script-executed':
            require(item['package_id'] in qualified_ids, 'Cargo executed an unqualified build script')
    require(observed, 'no actual compiler-artifact inputs observed')
    return sorted(observed)

def limit_child_outputs():
    # Cargo artifacts need more than the C-only fixture's 256 KiB file ceiling.
    # Stdout/stderr still have independent complete-capture bounds below.
    resource.setrlimit(resource.RLIMIT_FSIZE, (128*1024*1024, 128*1024*1024))


class OwnChildReaper:
    """Retire only children of this single-threaded isolated controller."""
    def __init__(self):
        self.pid = os.getpid()
        self.original = None
        self.changed = False
        self.active = False
        self.record = {'pid': self.pid, 'begin_passed': False, 'restored': False,
                       'final_children_empty': False, 'max_adopted_per_command': 128,
                       'cleanup_seconds_per_command': 5}
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.prctl = self.libc.prctl
        self.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                              ctypes.c_ulong, ctypes.c_ulong]
        self.prctl.restype = ctypes.c_int

    def flag(self):
        value = ctypes.c_int(-1)
        if self.prctl(37, ctypes.addressof(value), 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'PR_GET_CHILD_SUBREAPER')
        require(value.value in (0, 1), 'invalid own subreaper flag')
        return value.value

    def set_flag(self, value):
        if self.prctl(36, value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER')

    def single_thread(self):
        require(os.getpid() == self.pid and signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
                'controller PID/SIGCHLD ownership changed')
        names = []
        with os.scandir('/proc/%d/task' % self.pid) as rows:
            for row in rows:
                names.append(row.name)
                require(len(names) <= 1, 'controller is no longer single-threaded')
        require(names == [str(self.pid)], 'controller thread identity changed')

    def children(self):
        # Fixed self task only, never an all-/proc or other-actor enumeration.
        fd = os.open('/proc/%d/task/%d/children' % (self.pid, self.pid),
                     os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            data = os.read(fd, 8193)
            require(len(data) <= 8192 and os.read(fd, 1) == b'', 'own children list exceeds bound')
        finally:
            os.close(fd)
        fields = data.split()
        require(len(fields) <= 128 and len(fields) == len(set(fields)), 'own child count differs')
        require(all(x.isdigit() and x == str(int(x)).encode() and 0 < int(x) < 2**31
                    for x in fields), 'malformed own children list')
        return [int(x) for x in fields]

    def empty(self):
        self.single_thread()
        require(self.children() == [], 'controller retains child processes')
        try:
            os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return True
        raise RuntimeError('kernel wait authority did not confirm ECHILD')

    def begin(self):
        require(hasattr(os, 'P_PIDFD') and hasattr(os, 'WNOWAIT'), 'held nonreaping wait unavailable')
        self.empty()
        self.original = self.flag()
        self.record['original_subreaper_flag'] = self.original
        if self.original == 0:
            self.set_flag(1)
            self.changed = True
        require(self.flag() == 1, 'own subreaper did not become active')
        self.active = True
        self.record['begin_passed'] = True

    def before_command(self):
        require(self.active and self.flag() == 1, 'own subreaper not active')
        self.empty()

    def finish(self):
        self.empty()
        self.record['final_children_empty'] = True
        if self.original is not None:
            require(self.flag() == 1, 'own subreaper flag changed during commands')
            if self.changed:
                self.set_flag(self.original)
                self.changed = False
            require(self.flag() == self.original, 'own subreaper flag not restored')
        self.active = False
        self.record['restored'] = True

    @staticmethod
    def peek(pid, pidfd):
        info = os.waitid(os.P_PIDFD if pidfd is not None else os.P_PID,
                         pidfd if pidfd is not None else pid,
                         os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if info is not None:
            require(info.si_pid == pid and info.si_code in
                    (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED),
                    'owned child wait status differs')
        return info

    @staticmethod
    def observed(info):
        return {'pid': info.si_pid, 'code': info.si_code, 'status': info.si_status}

    def await_exit(self, pid, pidfd, deadline):
        poller = select.poll()
        poller.register(pidfd, select.POLLIN)
        while True:
            info = self.peek(pid, pidfd)
            if info is not None:
                return info
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('owned child exit deadline')
            poller.poll(max(1, min(100, int(remaining * 1000))))

    def retire(self, process, pidfd, record, remember, deadline):
        record['descendants'] = []
        record['owned_tree_cleanup_complete'] = False
        try:
            # WNOWAIT / direct-child relationship reserves the leader PID until
            # after group signalling. No killpg occurs after leader reaping.
            info = self.peek(process.pid, pidfd)
            record['leader_unreaped_before_group_cleanup'] = True
            record['leader_alive_before_group_cleanup'] = info is None
            if info is not None:
                record['leader_observed_before_reap'] = self.observed(info)
            require(os.getpgid(process.pid) == process.pid and
                    os.getsid(process.pid) == process.pid, 'owned session/group identity changed')
            record['owned_group_kill_attempted'] = True
            record['kill_attempted'] = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
                record['owned_group_kill_completed'] = True
            except ProcessLookupError:
                require(info is not None, 'live original group disappeared')
                record['owned_group_already_absent'] = True
        except Exception as error:
            remember(error, 'owned_group_cleanup')
            # If group qualification failed, kill only the known direct child.
            try:
                if self.peek(process.pid, pidfd) is None:
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        # The successful P_PID wait above proves this is still
                        # this controller's unreaped child, so its PID cannot be reused.
                        process.kill()
                    record['direct_child_fallback_kill_attempted'] = True
            except Exception as error:
                remember(error, 'direct_child_fallback_cleanup')
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
            record['returncode'] = process.returncode
            record['child_reaped'] = True
        except Exception as error:
            remember(error, 'reap_direct_child')
        if not record['child_reaped']:
            return
        seen = set()
        while True:
            try:
                children = self.children()
                if not children:
                    self.empty()
                    record['owned_tree_cleanup_complete'] = True
                    break
                require(time.monotonic() < deadline, 'adopted child cleanup deadline')
                require(not (set(children) & seen), 'an earlier adopted child was not reaped')
                require(len(seen) + len(children) <= 128, 'adopted child total bound exceeded')
            except Exception as error:
                remember(error, 'adopted_child_list_or_gate')
                break
            complete = True
            for child in children:
                if time.monotonic() >= deadline:
                    remember(TimeoutError('adopted child cleanup deadline'), 'adopted_child_deadline')
                    complete = False
                    break
                seen.add(child)
                item = {'pid': child, 'kill_attempted': False, 'reaped': False, 'pidfd_closed': True}
                record['descendants'].append(item)
                held = None
                try:
                    # The kernel-listed unreaped direct/adopted child cannot be
                    # reaped by another waiter: this controller is single-threaded.
                    try:
                        held = os.pidfd_open(child, 0)
                        item['pidfd_closed'] = False
                    except Exception as error:
                        # Keep this failure, but still retire the kernel-proven
                        # unreaped child if descriptor allocation itself failed.
                        item['pidfd_open_error'] = repr(error)
                        remember(error, 'adopted_pidfd_open')
                    info = self.peek(child, held)
                    if info is None:
                        item['kill_attempted'] = True
                        if held is not None:
                            signal.pidfd_send_signal(held, signal.SIGKILL)
                            info = self.await_exit(child, held, deadline)
                        else:
                            os.kill(child, signal.SIGKILL)
                            while info is None and time.monotonic() < deadline:
                                time.sleep(0.005)
                                info = self.peek(child, None)
                            require(info is not None, 'owned child fallback wait deadline')
                    item['observed_before_reap'] = self.observed(info)
                    waited, status = os.waitpid(child, os.WNOHANG)
                    require(waited == child, 'observed terminal adopted child was not reaped')
                    item['wait_status'] = status
                    item['reaped'] = True
                except Exception as error:
                    complete = False
                    item['error'] = repr(error)
                    remember(error, 'adopted_child_cleanup')
                finally:
                    if held is not None:
                        value, held = held, None
                        try:
                            os.close(value)
                            item['pidfd_closed'] = True
                        except Exception as error:
                            complete = False
                            remember(error, 'adopted_pidfd_close')
            if not complete:
                break
        record['cleanup_elapsed_seconds'] = time.monotonic() - (deadline - 5)
        if record['descendants']:
            # Successful drivers must normally reap their own helpers. Cleanup
            # success is not permission to count orphaned/forced helpers as a
            # successful compilation.
            remember(RuntimeError('driver left descendant processes after its exit'),
                     'driver_left_descendants')



def owned_command(report, root, argv, timeout=25, pidfd_factory=None, environment=None, cwd=None, label=None):
    index = len(report['commands'])
    output = root / ('command%02d.stdout' % index)
    error_path = root / ('command%02d.stderr' % index)
    record = {'argv': argv, 'cwd': str(cwd or root), 'label': label, 'timeout_seconds': timeout,
              'timed_out': False, 'child_started': False, 'child_reaped': False,
              'kill_attempted': False, 'pidfd_closed': True, 'output_fds_closed': False,
              'first_error': None, 'secondary_errors': [],
              'owned_tree_cleanup_complete': False}
    report['commands'].append(record)
    process = None
    pidfd = None
    streams = []
    first = None

    def remember(error, stage):
        nonlocal first
        item = {'stage': stage, 'error': repr(error)}
        if first is None:
            first = error
            record['first_error'] = item
        else:
            record['secondary_errors'].append(item)

    try:
        CHILD_REAPER.before_command()
        remaining = DEADLINE - time.monotonic()
        require(remaining > 0, 'controller work deadline expired before child admission')
        for path in (output, error_path):
            streams.append(path.open('xb'))
        require(type(environment) is dict and environment.get('CARGO_NET_OFFLINE') == 'true',
                'fixed offline child environment missing')
        process = subprocess.Popen(argv, cwd=cwd or root, stdin=subprocess.DEVNULL,
            stdout=streams[0], stderr=streams[1], close_fds=True, start_new_session=True,
            preexec_fn=limit_child_outputs, env=environment)
        record['pid'] = process.pid
        record['child_started'] = True
        pidfd = (pidfd_factory or os.pidfd_open)(process.pid, 0)
        record['pidfd_closed'] = False
        try:
            info = CHILD_REAPER.await_exit(process.pid, pidfd,
                time.monotonic() + min(timeout, remaining))
            record['leader_observed_without_reap'] = CHILD_REAPER.observed(info)
            if info.si_code != os.CLD_EXITED or info.si_status != 0:
                remember(RuntimeError('original command exited unsuccessfully before cleanup'),
                         'leader_exit_status')
        except TimeoutError:
            record['timed_out'] = True
            raise subprocess.TimeoutExpired(argv, timeout)
    except Exception as error:
        remember(error, 'start_or_wait')
    finally:
        if process is not None:
            cleanup_deadline = time.monotonic() + 5
            try:
                CHILD_REAPER.retire(process, pidfd, record, remember, cleanup_deadline)
            except Exception as error:
                remember(error, 'unexpected_owned_tree_cleanup_error')
                # Do not let an unexpected diagnostic error skip the direct
                # child's final wait. Group/adoption qualification stays false.
                try:
                    if process.returncode is None and CHILD_REAPER.peek(process.pid, pidfd) is None:
                        if pidfd is not None:
                            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                        else:
                            process.kill()
                except Exception as error:
                    remember(error, 'final_direct_kill')
                try:
                    process.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
                    record['returncode'] = process.returncode
                    record['child_reaped'] = True
                except Exception as error:
                    remember(error, 'final_direct_wait')
        if pidfd is not None:
            value, pidfd = pidfd, None
            try:
                os.close(value)
                record['pidfd_closed'] = True
            except Exception as error:
                remember(error, 'close_pidfd')
        closed = True
        for stream in reversed(streams):
            try:
                stream.close()
            except Exception as error:
                closed = False
                remember(error, 'close_output_file')
        record['output_fds_closed'] = closed
    # Each output is retained independently; a capture error cannot hide the
    # earlier child failure or prevent the other stream from being checked.
    for key, path in [('stdout', output), ('stderr', error_path)]:
        try:
            data, pin = held(path, 32*1024*1024 if key == 'stdout' else 4*1024*1024)
            record[key + '_bytes'] = len(data)
            record[key + '_sha256'] = pin['sha256']
            record[key + '_pin'] = pin
            record[key] = data.decode('utf-8')
            record[key + '_complete'] = True
        except Exception as error:
            record[key + '_complete'] = False
            remember(error, 'capture_' + key)
    if first is not None:
        raise first
    require(record.get('returncode') == 0 and record['child_reaped'] and
            record['pidfd_closed'] and record['output_fds_closed'] and
            record['owned_tree_cleanup_complete'] and not record['timed_out'],
            'matching build/control command failed: ' + str(index))
    return record



def command(argv, cwd, env, label, records, maximum_seconds=180):
    row = owned_command({'commands': records}, OUT, [str(x) for x in argv],
                        timeout=maximum_seconds, environment=env, cwd=cwd, label=label)
    raw = row.pop('stdout').encode('utf-8')
    row.pop('stderr')
    row['stdout'] = row.pop('stdout_pin')
    row['stderr'] = row.pop('stderr_pin')
    return raw


HOST_LIFECYCLE_FIXTURE = r"""import os
import sys
import time

mode = sys.argv[1]
if mode == 'pidfd-failure':
    time.sleep(30)
    raise SystemExit(0)
if mode not in ('timeout-descendant', 'escaped-descendant'):
    raise SystemExit(2)
read_end, write_end = os.pipe()
child = os.fork()
if child == 0:
    os.close(read_end)
    if mode == 'escaped-descendant':
        os.setsid()
    os.write(write_end, b'R')
    os.close(write_end)
    time.sleep(30)
    os._exit(0)
os.close(write_end)
if os.read(read_end, 1) != b'R':
    os._exit(3)
os.close(read_end)
print('READY %d %d' % (os.getpid(), child), flush=True)
if mode == 'escaped-descendant':
    os._exit(0)
time.sleep(30)
"""


def run_child_lifecycle_controls(report, root, environment):
    control_root = root / 'host-child-lifecycle-controls'
    control_root.mkdir(mode=0o700)
    report['host_child_lifecycle_controls'] = []
    modes = ('timeout-descendant', 'escaped-descendant', 'pidfd-failure')
    for index, mode in enumerate(modes):
        case_root = control_root / ('case%02d' % index)
        case_root.mkdir(mode=0o700)
        case = {'name': mode, 'passed': False, 'commands': [],
                'Android_executed': False, 'namespace_or_UID_changes': False,
                'pidfd_failure_seam': mode == 'pidfd-failure'}
        report['host_child_lifecycle_controls'].append(case)
        first = None

        def denied_pidfd(pid, flags):
            raise OSError(errno.EMFILE, 'explicit owned-child pidfd-open control seam')

        try:
            owned_command(case, case_root,
                    [sys.executable, '-I', '-B', '-c', HOST_LIFECYCLE_FIXTURE, mode],
                    timeout=1 if mode == 'timeout-descendant' else 5,
                    pidfd_factory=denied_pidfd if mode == 'pidfd-failure' else None, environment=environment)
        except Exception as error:
            first = error
        require(first is not None and len(case['commands']) == 1,
                'lifecycle negative control unexpectedly succeeded')
        row = case['commands'][0]
        require(row['child_started'] and row['child_reaped'] and
                row['owned_tree_cleanup_complete'] and row['pidfd_closed'] and
                row['output_fds_closed'] and row.get('stdout_complete') and row.get('stderr_complete'),
                'lifecycle negative control did not completely retire its owned tree')
        require(row['stderr'] == '' and row['first_error'] is not None,
                'lifecycle negative control lost its first error or had unexpected stderr')
        if mode == 'pidfd-failure':
            require(isinstance(first, OSError) and first.errno == errno.EMFILE and
                    row['first_error']['stage'] == 'start_or_wait' and
                    row['returncode'] == -signal.SIGKILL and not row['descendants'],
                    'post-Popen pidfd failure did not preserve errno and reap the child')
        else:
            fields = row['stdout'].strip().split()
            require(len(fields) == 3 and fields[0] == 'READY' and
                    int(fields[1]) == row['pid'] and len(row['descendants']) == 1 and
                    row['descendants'][0]['pid'] == int(fields[2]) and
                    row['descendants'][0]['reaped'] and row['descendants'][0]['pidfd_closed'] and
                    os.WIFSIGNALED(row['descendants'][0]['wait_status']) and
                    os.WTERMSIG(row['descendants'][0]['wait_status']) == signal.SIGKILL,
                    'real descendant readiness/reaping proof differs')
            if mode == 'timeout-descendant':
                require(isinstance(first, subprocess.TimeoutExpired) and row['timed_out'] and
                        row['returncode'] == -signal.SIGKILL and
                        row['first_error']['stage'] == 'start_or_wait',
                        'timeout control did not retain the original failure')
            else:
                require(row['returncode'] == 0 and not row['timed_out'] and
                        row['descendants'][0]['kill_attempted'] and
                        row['first_error']['stage'] == 'driver_left_descendants',
                        'escaped descendant was not rejected and independently retired')
        CHILD_REAPER.empty()
        case['expected_failure'] = repr(first)
        case['passed'] = True
    require(len(report['host_child_lifecycle_controls']) == 3 and
            all(item['passed'] for item in report['host_child_lifecycle_controls']),
            'owned tree cleanup controls incomplete')

def selected_status_dependencies(metadata, trees, registry_authority, source_map):
    require(metadata.get('resolve') is None and metadata.get('workspace_root') == str(COPIED) and
            metadata.get('target_directory') == str(OUT/'cargo-target') and
            type(metadata.get('packages')) is list and 0 < len(metadata['packages']) <= 128,
            'no-deps metadata must describe the exact copied host workspace')
    packages = {p['id']: p for p in metadata['packages']}
    require(len(packages) == len(metadata['packages']), 'duplicate workspace package identity')
    allowed_paths = {
        'droidloom-supervisor': 'runtime/droidloom-supervisor',
        'droidloom-applications': 'runtime/droidloom-applications',
        'droidloom-contracts': 'runtime/droidloom-contracts',
        'droidloom-cpu-placement': 'runtime/droidloom-cpu-placement',
        'droidloom-window-policy': 'runtime/droidloom-window-policy',
    }
    roots = {}
    for name in ('droidloom-supervisor', 'droidloom-applications'):
        found = [p for p in packages.values() if p['name'] == name and p['source'] is None and
                 p['manifest_path'] == str(COPIED/allowed_paths[name]/'Cargo.toml') and
                 p['id'] in metadata['workspace_members']]
        require(len(found) == 1, 'exact supervisor/application workspace root is absent: '+name)
        roots[name] = found[0]
    require(set(trees) == {'supervisor-build', 'supervisor-test', 'applications-build', 'applications-test'},
            'both real root normal/build and normal/build/dev trees required')
    parsed = {name: parse_selected_tree(raw, COPIED) for name, raw in trees.items()}
    selected = {}
    for root in ('supervisor', 'applications'):
        build, test = parsed[root+'-build'], parsed[root+'-test']
        require(build and all(key in test and test[key] == value for key,value in build.items()),
                'test dependency graph lost or changed a normal/build dependency')
        for key, value in test.items():
            require(key not in selected or selected[key] == value, 'cross-root dependency identity differs')
            selected[key] = value
    require(0 < len(selected) <= 50, 'host root closure exceeds five path plus 45 observed registry packages')
    lock_raw, lock_pin = held(COPIED/'Cargo.lock', 1024*1024)
    require(lock_pin['bytes'] == 51836 and lock_pin['sha256'] ==
            'c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62',
            'host compile changed the immutable original workspace lock')
    lock = tomllib.loads(lock_raw.decode('utf-8'))
    by_key = {}
    for package in lock['package']:
        by_key.setdefault((package['name'], package['version']), []).append(package)
    require(len(registry_authority) == 45, 'original complete 45-package authority is required')
    source_roots = {str(Path(row['source_directory']).parent) for row in registry_authority.values()}
    archive_roots = {str(Path(row['expected_archive_path']).parent) for row in registry_authority.values()}
    require(len(source_roots) == len(archive_roots) == 1, 'paired fixed registry namespaces required')
    source_root, archive_root = Path(next(iter(source_roots))), Path(next(iter(archive_roots)))
    require(source_root.parent == CARGO_HOME/'registry/src' and
            archive_root.parent == CARGO_HOME/'registry/cache' and
            source_root.name == archive_root.name and '..' not in source_root.parts,
            'registry authority escaped the observed Cargo namespace')
    real_directory(source_root)
    real_directory(archive_root)
    descriptions, collected = [], {}
    for (name, version), directory_text in sorted(selected.items()):
        rows = by_key.get((name, version), [])
        require(len(rows) == 1, 'selected package is missing or ambiguous in unchanged Cargo.lock')
        locked = rows[0]
        if directory_text is not None:
            require(name in allowed_paths and directory_text == str(COPIED/allowed_paths[name]) and
                    locked.get('source') is None, 'selected path crate left the five fixed host providers')
            manifest_path = Path(directory_text)/'Cargo.toml'
            relative = str(manifest_path.relative_to(COPIED))
            require(relative in source_map and hash_held(manifest_path)['sha256'] ==
                    source_map[relative]['sha256'], 'path dependency manifest changed')
            matches = [p for p in packages.values() if p['name'] == name and p['version'] == version and
                       p['source'] is None and p['manifest_path'] == str(manifest_path)]
            require(len(matches) == 1 and matches[0]['id'] in metadata['workspace_members'],
                    'path dependency is not the exact observed workspace member')
            descriptions.append({'id':matches[0]['id'], 'name':name, 'version':version,
                                 'kind':'pinned-host-source', 'manifest':str(manifest_path)})
            continue
        observed = registry_authority.get((name, version))
        require(observed is not None and locked.get('source') ==
                'registry+https://github.com/rust-lang/crates.io-index' and
                re.fullmatch(r'[0-9a-f]{64}', locked.get('checksum', '')) is not None,
                'selected registry dependency has no actual fixed archive authority')
        directory, archive = source_root/(name+'-'+version), archive_root/(name+'-'+version+'.crate')
        require(observed['source_directory'] == str(directory) and
                observed['expected_archive_path'] == str(archive) and
                observed['expected_lock_checksum'] == locked['checksum'] and
                observed['comparison']['archive_matches_lock'] is True and
                observed['comparison']['every_archive_file_matches_held_extracted_source'] is True,
                'selected registry source differs from actual archive/source authority')
        comparison, inventory, archive_pin = qualify_cached_archive(
            archive, directory, name, version, locked['checksum'])
        require(archive_pin['sha256'] == observed['comparison']['archive']['sha256'],
                'existing archive differs from historical complete observation')
        manifest_raw, manifest_pin = held(directory/'Cargo.toml', 1024*1024)
        manifest = tomllib.loads(manifest_raw.decode('utf-8'))['package']
        require(manifest['name'] == name and manifest['version'] == version and
                inventory['Cargo.toml'] == manifest_pin, 'selected package manifest differs')
        collected[str(archive)] = archive_pin
        for row in inventory.values():
            require(len(collected) < 16384, 'complete selected dependency inventory exceeds bound')
            collected[row['path']] = row
        descriptions.append({'id':locked['source']+'#'+name+'@'+version,
            'name':name, 'version':version, 'kind':'offline-registry',
            'manifest':str(directory/'Cargo.toml'), 'recorded_files':len(inventory),
            'package_checksum':locked['checksum'], 'archive':archive_pin,
            'archive_to_source':comparison['source_inventory']})
    require(all(any(row['id'] == p['id'] for row in descriptions) for p in roots.values()) and
            sum(p['kind'] == 'offline-registry' for p in descriptions) <= 45 and
            sum(p['kind'] == 'pinned-host-source' for p in descriptions) <= 5,
            'actual selected host closure is incomplete or outside fixed authority')
    return roots, descriptions, collected


def actual_executable(raw, package_id, target_name, target_kind, source_path, test):
    records = []
    for line in raw.decode('utf-8').splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get('reason') == 'compiler-artifact' and item.get('package_id') == package_id and \
                item.get('target', {}).get('name') == target_name and item.get('executable'):
            require(item['target']['kind'] == [target_kind] and
                    item['target']['src_path'] == str(source_path) and
                    item['profile']['test'] is test,
                    'Cargo executable has a wrong target/source/profile')
            records.append(Path(item['executable']))
    require(len(records) == 1, 'expected actual executable missing or duplicate')
    path = records[0]
    require(path.is_relative_to(OUT/'cargo-target') and '..' not in path.parts,
            'actual executable escaped the fresh owned Cargo target')
    real_directory(path.parent)
    data, pin = held(path, 128*1024*1024)
    require(data[:4] == b'\x7fELF' and pin['identity'][2] & 0o111,
            'actual executable is not an executable regular ELF')
    return path, pin


def test_registration(binary, expected, environment, report, label):
    listing = command([str(binary), '--list'], COPIED, environment, label+'-list', report['commands'], 10).decode('utf-8')
    names = [line[:-6] for line in listing.splitlines() if line.endswith(': test')]
    require(0 < len(names) <= 4096 and len(names) == len(set(names)) and
            all(names.count(name) == 1 for name in expected) and
            not any(line.endswith(': benchmark') for line in listing.splitlines()),
            'fixed selected test registrations are missing or duplicated')
    trailer = [line for line in listing.splitlines() if re.fullmatch(r'\d+ tests, \d+ benchmarks', line)]
    require(trailer == [str(len(names))+' tests, 0 benchmarks'], 'complete libtest registry trailer differs')
    help_text = command([str(binary), '--help'], COPIED, environment, label+'-help', report['commands'], 10).decode('utf-8')
    require(re.search(r'^\s*--logfile\s', help_text, re.MULTILINE) is not None and
            'Write logs to the specified file' in help_text, 'actual libtest lacks independent result file')
    return names


def validate_focused_result(name, index, output, log, registered_count):
    require(log == ('ok '+name+'\n').encode(),
            'independent libtest result is not exactly one selected success')
    summaries = [line for line in output.splitlines() if line.startswith('test result:')]
    pattern = r'test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; (\d+) filtered out; finished in \d+(?:\.\d+)?s'
    require(len(summaries) == 1, 'selected test produced an unexpected result count')
    match = re.fullmatch(pattern, summaries[0])
    require(match is not None and int(match.group(1)) == registered_count-1 and
            output.splitlines().count('running 1 test') == 1 and
            output.count('test '+name+' ... ') == 1, 'complete single libtest invocation differs')
    return {'outer_results':1, 'expected_stdout_runs':1, 'registered_tests':registered_count,
            'filtered_out_per_run':registered_count-1, 'exact_name':name,
            'summary_and_independent_result_agree':True}

def focused_test(test_binary, name, index, registered_count, environment, records):
    label = 'projection-test-'+str(index)
    path = OUT/(label+'.libtest')
    # Claim a new regular file and retain the descriptor while libtest opens
    # that exact private path. Replacement, aliases and extra records fail.
    fd = os.open(path, os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC, 0o600)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o600 and
                before.st_size == 0, 'fresh libtest result claim differs')
        output = command([str(test_binary),'--exact',name,'--test-threads=1','--nocapture',
                          '--logfile',str(path)],COPIED,environment,label,records,30).decode()
        after = os.fstat(fd)
        require((after.st_dev,after.st_ino,after.st_mode,after.st_uid,after.st_gid,after.st_nlink) ==
                (before.st_dev,before.st_ino,before.st_mode,before.st_uid,before.st_gid,before.st_nlink) and
                after.st_size <= 4096, 'held libtest result object or bound differs')
        log = os.pread(fd,4097,0)
        final = os.fstat(fd)
        require(len(log) == after.st_size and identity(after) == identity(final) == identity(path.lstat()),
                'libtest result changed while read or named path was replaced')
        records[-1]['independent_libtest_result'] = {
            'path': str(path), 'bytes': len(log), 'sha256': sha(log), 'identity': identity(final)}
        result = validate_focused_result(name,index,output,log,registered_count)
        records[-1]['focused_result_gate'] = result
        return result
    finally:
        os.close(fd)

def staged_inputs(report):
    raw, row = held(ROOT/'stage-receipt.json', 1024*1024)
    receipt = json.loads(raw)
    require(receipt['schema'] == 1 and receipt['Main_actions'] == 0 and
            receipt['only_owned_root_written'] is True and
            type(receipt['files']) is dict and 1 <= len(receipt['files']) <= 32,
            'fixed stage receipt shape differs')
    current = regular_tree(HERE, 32, 2*1024*1024)
    require(set(current) == set(receipt['files']), 'complete staged source set differs')
    for name, wanted in receipt['files'].items():
        require(current[name]['bytes'] == wanted['bytes'] and
                current[name]['sha256'] == wanted['sha256'] and
                stat.S_IMODE(current[name]['identity'][2]) == 0o400,
                'staged source differs: '+name)
    report['stage_receipt'] = row
    report['complete_stage_member_count'] = len(current)
    return current


def qualify_parent_and_patch(report, expected, candidate):
    raw, pin = pinned_packet('compiled-parent474-result.json', PARENT_RESULT_SHA)
    parent = json.loads(raw)
    require(pin['bytes'] == 197750 and parent['state'] == 'PASS' and
            parent['source_delta']['actual_source_file_count'] == 501 and
            parent['copied_manifest'] == {
                'path':str(BASE_SOURCE.parent/'attempt01/copied-builder-source-manifest.json'),
                'bytes':99750, 'sha256':MANIFEST_PARENT} and
            parent['original_source_unchanged_after'] is True and
            parent['copied_source_unchanged_after'] is True and
            parent['dependency_changes'] == [] and parent['tool_changes'] == [] and
            parent['cargo_configs_unchanged_after'] is True and
            parent['owned_resource_gate']['pass'] is True and
            parent['observed_signals'] == [] and
            not parent['cleanup']['forced_cleanup'] and not parent['cleanup']['remaining'] and
            not parent['cleanup']['errors'] and len(parent['commands']) == 74 and
            all(row['returncode'] == 0 and not row['timed_out'] for row in parent['commands']),
            'actual parent474 source/tool/command/cleanup authority is incomplete')
    report['actual_parent474_source_authority'] = pin
    require(len(expected) == 501 and len(candidate) == 502 and
            set(candidate) - set(expected) == {NEW_TEST_PATH} and
            set(expected) - set(candidate) == set() and
            {path for path in expected if expected[path] != candidate[path]} == set(CHANGED_PATHS) and
            set(DELTAS) == set(CHANGED_PATHS) | {NEW_TEST_PATH},
            'Status candidate does not have exactly four changed and one added source')
    for path in ('Cargo.lock', 'Cargo.toml', 'runtime/droidloom-supervisor/Cargo.toml',
                 'runtime/droidloom-applications/Cargo.toml',
                 'runtime/droidloom-applications/src/lib.rs',
                 'runtime/droidloom-applications/src/main.rs'):
        require(candidate[path] == expected[path], 'original dependency or Applications source was changed')
    for relative in sorted(DELTAS):
        wanted = DELTAS[relative]
        raw, delta_pin = pinned_packet('delta/'+relative, wanted['sha256'])
        require(delta_pin['bytes'] == wanted['bytes'] and candidate[relative] == wanted,
                'candidate delta does not match its complete manifest')
        path = COPIED/relative
        if relative in expected:
            before = hash_held(path)
            require(before['sha256'] == expected[relative]['sha256'] and
                    before['bytes'] == expected[relative]['bytes'] and
                    stat.S_IMODE(before['identity'][2]) == expected[relative]['mode'],
                    'candidate changed before its one source replacement')
            fd = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC)
            with os.fdopen(fd, 'wb') as stream:
                require(stream.write(raw) == len(raw), 'short candidate source replacement')
                stream.flush()
                os.fsync(stream.fileno())
        else:
            write_new(path, raw)
        os.chmod(path, wanted['mode'], follow_symlinks=False)
    rows = regular_tree(COPIED)
    portable(rows, candidate)
    report['source_delta'] = {
        'changed_existing':CHANGED_PATHS, 'added':[NEW_TEST_PATH],
        'actual_source_file_count':502, 'unchanged_existing':497,
        'workspace_or_lock_modified':False, 'Applications_sources_modified':False,
        'namespace_or_installed_Main_sources_modified':False,
        'test_only_owned_process_constructor':True,
        'runtime_qualification_or_deployment':False}
    return rows


def execute():
    global DEADLINE, CHILD_REAPER
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'ordinary operator UID1000 required')
    require(Path(__file__).absolute() == HERE/'compile_status.py', 'exact staged controller required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(), 'create-only attempt already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    (OUT/'tmp').mkdir(mode=0o700)
    DEADLINE = time.monotonic() + 550
    report = {
        'schema':1, 'state':'RUNNING', 'started_utc':utc(),
        'scope':'exact host lifecycle Status / explicit fresh Readiness; actual dispatcher and CLI regressions',
        'Main_actions':0, 'Main_identity_observed':False, 'install_actions':0,
        'Android_or_Soong_executed':False, 'namespace_entry':False,
        'installed_Main_source_provenance_qualified':False, 'old_London_cause_proven':False,
        'production_ready':False, 'deployed':False, 'commands':[],
        'network_downloads_permitted':False, 'secondary_errors':[],
        'expected_dispatch_and_preserved_gate_tests':LIB_TESTS,
        'expected_cli_tests':CLI_TESTS,
        'compiled_status_protocol_qualified':False,
        'Main_or_future_App_qualification':False,
    }
    def interrupted(number, frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned controller interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    resource_fd, resource_before = -1, None
    original_rows = candidate_rows = input_rows = None
    dependency_rows, tool_rows, config_rows, config_paths, artifact_pins = {}, [], [], [], {}
    def secondary(stage, error):
        report['state'] = 'FAIL'
        report['secondary_errors'].append({'stage':stage, 'error':repr(error)})
    try:
        resource_fd, resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        CHILD_REAPER = OwnChildReaper()
        CHILD_REAPER.begin()
        allowed = sorted(os.sched_getaffinity(0))
        require(len(allowed) >= 3, 'cannot leave two logical CPUs outside this compile')
        os.sched_setaffinity(0, [allowed[-1]])
        report['allowed_cpus_before'] = allowed
        report['selected_cpus'] = [allowed[-1]]
        input_rows = staged_inputs(report)
        old_raw, _ = pinned_packet('compiled-parent474-manifest.json', MANIFEST_PARENT)
        new_raw, _ = pinned_packet('expected-status-manifest.json', MANIFEST_CANDIDATE)
        expected, candidate = json.loads(old_raw), json.loads(new_raw)
        original_rows, _ = exact_source_copy(expected)
        report['original_manifest'] = write_new(OUT/'original-source-manifest.json', old_raw)
        candidate_rows = qualify_parent_and_patch(report, expected, candidate)
        report['copied_manifest'] = write_new(OUT/'copied-status-source-manifest.json', new_raw)
        env = {'PATH':'/usr/bin:/bin', 'CARGO_HOME':str(CARGO_HOME),
               'RUSTC':str(RUST_SYSROOT/'bin/rustc'), 'RUSTDOC':str(RUST_SYSROOT/'bin/rustdoc'),
               'CARGO_NET_OFFLINE':'true', 'LC_ALL':'C', 'LANG':'C',
               'TMPDIR':str(OUT/'tmp'), 'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null'}
        run_child_lifecycle_controls(report, OUT, env)
        tools, tool_rows = toolchain(report, env)
        report['tool_inputs'] = write_new(OUT/'tool-inputs-before.json', tool_rows)
        env.update({'PATH':str(tools['cargo'].parent)+':/usr/bin:/bin',
                    'RUSTC':str(tools['rustc']), 'RUSTDOC':str(tools['rustdoc']),
                    'RUSTDOCFLAGS':'', 'CARGO_ENCODED_RUSTDOCFLAGS':'',
                    'RUSTC_WRAPPER':'', 'RUSTC_WORKSPACE_WRAPPER':'',
                    'RUSTFLAGS':'', 'CARGO_ENCODED_RUSTFLAGS':'',
                    'CARGO_TARGET_DIR':str(OUT/'cargo-target'), 'CARGO_BUILD_JOBS':'1',
                    'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER':'/usr/bin/cc'})
        require(all(shutil.which(name, path=env['PATH']) == str(tools[name])
                    for name in ('cargo', 'rustc', 'rustdoc')) and
                '/home/alex/.cargo/bin' not in env['PATH'].split(':') and
                not any(name.startswith('RUSTUP') for name in env) and
                all(name not in env for name in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'RUSTC_BOOTSTRAP')),
                'direct observed toolchain was shadowed or overridden')
        config_paths = [CARGO_HOME/'config', CARGO_HOME/'config.toml']
        for parent in [COPIED, *COPIED.parents]:
            config_paths += [parent/'.cargo/config', parent/'.cargo/config.toml']
        config_rows = read_existing_config(config_paths)
        report['cargo_config_inputs_before'] = config_rows
        require(config_rows and all(row.get('absent') is True for row in config_rows),
                'fixed existing registry build requires absent Cargo configuration overrides')
        report['build_environment'] = env
        metadata_raw = command([str(tools['cargo']), 'metadata', '--offline', '--locked',
                                '--no-deps', '--format-version', '1'],
                               COPIED, env, 'workspace-no-deps', report['commands'], 30)
        metadata = json.loads(metadata_raw)
        trees = {}
        for short, package in [('supervisor', 'droidloom-supervisor'), ('applications', 'droidloom-applications')]:
            for suffix, edges in [('build', 'normal,build'), ('test', 'normal,build,dev')]:
                label = short+'-'+suffix
                trees[label] = command([str(tools['cargo']), 'tree', '--offline', '--locked', '-p', package,
                    '--target', 'x86_64-unknown-linux-gnu', '--edges', edges,
                    '--prefix', 'none', '--format', '{p}', '--color', 'never'],
                    COPIED, env, label, report['commands'], 30)
        registry_raw, registry_pin = pinned_packet('registry-result.json',
            'b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993')
        registry = json.loads(registry_raw)
        require(registry['state'] == 'PASS' and registry['collection_complete'] is True and
                registry['all_45_archive_and_source_matches'] is True and
                registry['authorities_unchanged_after'] is True and
                registry['owned_resource_gate']['pass'] is True and len(registry['packages']) == 45,
                'actual original 45-package archive authority is incomplete')
        authority = {(r['name'], r['version']):r for r in registry['packages']}
        roots, packages, dependency_rows = selected_status_dependencies(metadata, trees, authority, candidate)
        report['actual_registry_archive_authority'] = registry_pin
        report['dependency_inputs'] = write_new(OUT/'dependency-inputs-before.json',
                                               {'packages':packages, 'files':dependency_rows})
        report['actual_root_package_ids'] = {name:p['id'] for name,p in roots.items()}
        report['selected_dependency_count'] = len(packages)
        report['normal_build_and_dev_selected_for_both_roots'] = True
        cargo = str(tools['cargo'])
        sup = roots['droidloom-supervisor']
        lib_build = command([cargo, 'test', '--offline', '--locked', '-j', '1',
            '-p', 'droidloom-supervisor', '--lib', '--no-run', '--message-format=json-render-diagnostics'],
            COPIED, env, 'supervisor-libtest-compile', report['commands'], 180)
        report['actual_libtest_compile_packages'] = qualify_compiler_inputs(lib_build, packages, dependency_rows, candidate_rows)
        lib_binary, lib_pin = actual_executable(lib_build, sup['id'], 'droidloom_supervisor', 'lib',
            COPIED/'runtime/droidloom-supervisor/src/lib.rs', True)
        artifact_pins['supervisor-libtest'] = lib_pin
        lib_names = test_registration(lib_binary, LIB_TESTS+[OWNED_FIXTURE_TEST], env, report, 'supervisor-libtest')
        cli_build = command([cargo, 'test', '--offline', '--locked', '-j', '1',
            '-p', 'droidloom-supervisor', '--test', 'cli_lifecycle', '--no-run',
            '--message-format=json-render-diagnostics'],
            COPIED, env, 'cli-lifecycle-compile', report['commands'], 180)
        report['actual_cli_test_compile_packages'] = qualify_compiler_inputs(cli_build, packages, dependency_rows, candidate_rows)
        cli_binary, cli_pin = actual_executable(cli_build, sup['id'], 'cli_lifecycle', 'test',
            COPIED/'runtime/droidloom-supervisor/tests/cli_lifecycle.rs', True)
        artifact_pins['cli-lifecycle-test'] = cli_pin
        cli_names = test_registration(cli_binary, CLI_TESTS, env, report, 'cli-lifecycle')
        require(set(cli_names) == set(CLI_TESTS), 'CLI integration registry differs from original six plus one route test')
        # Compile the normal executables after both test-build phases so their
        # recorded artifact identity cannot be invalidated by Cargo's test setup.
        build = command([cargo, 'build', '--offline', '--locked', '-j', '1',
                         '-p', 'droidloom-supervisor', '-p', 'droidloom-applications',
                         '--bins', '--message-format=json-render-diagnostics'],
                        COPIED, env, 'host-binaries-compile', report['commands'], 240)
        report['actual_binary_compile_packages'] = qualify_compiler_inputs(build, packages, dependency_rows, candidate_rows)
        executables = {}
        for package_name, name, relative in HOST_BINARIES:
            path, pin = actual_executable(build, roots[package_name]['id'], name, 'bin', COPIED/relative, False)
            executables[name] = path
            artifact_pins[name] = pin
        cli_help = command([str(executables['droidloomctl']), '--help'], COPIED, env,
                           'ctl-help', report['commands'], 10)
        require(all(re.search(rb'^\s*'+name+rb'\s', cli_help, re.MULTILINE) for name in
                    (b'status', b'readiness', b'wait', b'launch', b'applications')),
                'compiled CLI is missing an original or explicit readiness command')
        report['actual_registered_test_counts'] = {'supervisor_library':len(lib_names), 'cli_lifecycle':len(cli_names)}
        report['focused_result_gates'] = []
        for binary, names, registered in [(lib_binary, LIB_TESTS, lib_names), (cli_binary, CLI_TESTS, cli_names)]:
            for name in names:
                index = len(report['focused_result_gates'])
                report['focused_result_gates'].append(focused_test(binary, name, index, len(registered), env, report['commands']))
        report['focused_tests_passed'] = len(report['focused_result_gates'])
        require(report['focused_tests_passed'] == 15 and len(report['commands']) == 38 and
                all(row.get('returncode') == 0 and row.get('child_reaped') is True and
                    row.get('owned_tree_cleanup_complete') is True and not row['timed_out'] and
                    row['first_error'] is None and not row['secondary_errors'] for row in report['commands']),
                'host compile or exact selected regressions did not fully complete')
        require(time.monotonic() < DEADLINE, 'host compiler completion deadline exceeded')
        report['actual_elfs'] = artifact_pins
        report['state'] = 'PASS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
        report['error_detail'] = {'type':type(error).__name__, 'message':str(error),
                                  'errno':getattr(error, 'errno', None), 'filename':getattr(error, 'filename', None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        report['observed_signals'] = OBSERVED_SIGNALS
        if OBSERVED_SIGNALS:
            secondary('signals', RuntimeError('owned controller was interrupted'))
        if CHILD_REAPER is not None:
            try:
                CHILD_REAPER.finish()
            except Exception as error:
                secondary('owned_child_reaper_finish', error)
            report['owned_child_reaper'] = CHILD_REAPER.record
        else:
            report['owned_child_reaper'] = None
        for label, directory, rows, bounds in [
                ('original_source', BASE_SOURCE, original_rows, (2048, 32*1024*1024)),
                ('copied_source', COPIED, candidate_rows, (2048, 32*1024*1024)),
                ('control_source', HERE, input_rows, (32, 2*1024*1024))]:
            report[label+'_unchanged_after'] = None
            report[label+'_baseline_established'] = rows is not None
            if rows is not None:
                try:
                    same = regular_tree(directory, *bounds) == rows
                    report[label+'_unchanged_after'] = same
                    require(same, label+' complete source inputs changed')
                except Exception as error:
                    secondary(label+'_after', error)
            elif report['state'] == 'PASS':
                secondary(label+'_after', RuntimeError('complete source baseline was never established'))
        changes = []
        for path, row in dependency_rows.items():
            try:
                if hash_held(Path(path)) != row:
                    changes.append(path)
            except Exception as error:
                changes.append({'path':path, 'error':repr(error)})
        report['dependency_changes'] = changes
        if changes:
            secondary('dependency_after', RuntimeError('qualified archive or extracted source changed'))
        report['tool_changes'] = verify_resolved(tool_rows)
        if report['tool_changes'] or (report['state'] == 'PASS' and not tool_rows):
            secondary('tools_after', RuntimeError('used tool closure missing or changed'))
        report['cargo_configs_unchanged_after'] = None
        if config_rows:
            try:
                same = read_existing_config(config_paths) == config_rows
                report['cargo_configs_unchanged_after'] = same
                require(same, 'Cargo configuration inputs changed')
            except Exception as error:
                secondary('cargo_configs_after', error)
        elif report['state'] == 'PASS':
            secondary('cargo_configs_after', RuntimeError('Cargo configuration baseline missing'))
        report['artifact_changes'] = []
        for name, row in artifact_pins.items():
            try:
                require(hash_held(Path(row['path'])) == row, 'built ELF changed')
            except Exception as error:
                report['artifact_changes'].append({'name':name, 'error':repr(error)})
                secondary('artifact_after', error)
        try:
            require(resource_fd >= 0 and resource_before is not None, 'owned resource admission not observed')
            report['owned_resource_gate'] = finish_resources(resource_fd, resource_before, report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass':False, 'error':repr(error)}
            secondary('owned_resources_after', error)
        finally:
            if resource_fd >= 0:
                value, resource_fd = resource_fd, -1
                try:
                    os.close(value)
                    report['owned_resource_fd_closed'] = True
                except Exception as error:
                    report['owned_resource_fd_closed'] = False
                    secondary('owned_resource_fd_close', error)
        report['compiled_status_protocol_qualified'] = report['state'] == 'PASS'
        report['finished_utc'] = utc()
        result = write_new(OUT/'result.json', report)
        print(json.dumps({'state':report['state'], 'result':result,
            'actual_elfs':report.get('actual_elfs'), 'focused_tests_passed':report.get('focused_tests_passed', 0),
            'Main_actions':0, 'deployed':False, 'production_ready':False,
            'commands':len(report['commands']), 'error':report.get('error'),
            'secondary_errors':report['secondary_errors']}), flush=True)
    return 0 if report['state'] == 'PASS' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode':'PLAN', 'root':str(ROOT), 'base_source':str(BASE_SOURCE),
            'source_files':502, 'requires_explicit_execute_once':True, 'Main_actions':0,
            'Android_execution':False, 'deploy':False, 'lib_tests':LIB_TESTS, 'cli_tests':CLI_TESTS}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: compile_status.py [--execute-once]')
