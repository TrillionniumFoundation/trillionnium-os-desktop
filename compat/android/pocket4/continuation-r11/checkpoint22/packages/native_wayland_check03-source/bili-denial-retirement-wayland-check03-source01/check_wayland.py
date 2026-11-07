#!/usr/bin/env python3
"""Check the full exact Wayland binary crate offline; do not run Android or repeat host controls."""
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
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
import tomllib

ROOT = Path("/home/alex/work/p4-retirement-wayland-check03-20261106")
HERE = ROOT/'control-source'
OUT = ROOT/'attempt01'
COPIED = ROOT/'builder-source'
BASE_SOURCE = Path('/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106/builder-source')
RUST_SYSROOT = Path('/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu')
CARGO_HOME = Path('/home/alex/.cargo')
TOOLCHAIN = '1.93.0'
OBSERVATION = '60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb'
PARENT_MANIFEST_SHA = '88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701'
CANDIDATE_MANIFEST_SHA = '3f2320687f074d48b19bc5284e6ba665a6cfaeb7adab9d59f519de5f3c96d2f4'
ENGINE_PATH = 'graphics/droidloom-wayland/src/retirement.rs'
SOURCE_PINS = {"candidate-protocol.rs":{"path":"graphics/droidloom-denial-protocol/src/lib.rs","bytes":105464,"sha256":"6c7f8df133f2a9e55bd375da4b39dcba5b00d0c4c3ba6531a6b8be329ebce41c"},"candidate-endpoint.rs":{"path":"graphics/droidloom-denial-endpoint/src/lib.rs","bytes":63752,"sha256":"062b65857160eb6e3aeba2a78c4ce3d8503c02572f24353f8c944d950e52308c"},"candidate-engine-retirement.rs":{"path":"graphics/droidloom-wayland/src/retirement.rs","bytes":11118,"sha256":"383f4c6f7490c8568f1853af6e9449fdb35bdb088348de4a9856d75f97306873"},"candidate-wayland-main.rs":{"path":"graphics/droidloom-wayland/src/main.rs","bytes":110131,"sha256":"0f56264e971db9f246d8db34d7fd5de157fd389a97bfb34492a6f53376d27459"},"candidate-wayland-layers.rs":{"path":"graphics/droidloom-wayland/src/layers.rs","bytes":35990,"sha256":"d0a81ce5339c5020496e9b73e007d52ee206449827269b272e4ef6ef43df5ecc"},"candidate-provider.rs":{"path":"graphics/droidloom-composer-aidl/src/denial.rs","bytes":50513,"sha256":"d6f13720da4267ff46f369617faecbb8c6446eca2c624e381c1ff51ddaebbf09"},"candidate-core-denial.rs":{"path":"graphics/droidloom-composer/src/denial.rs","bytes":25541,"sha256":"ed0080cd33a3a4fa67b3a0c2e95bc274ab38e992ec073ab01d87b910bf2db3c8"},"candidate-composer-main.rs":{"path":"graphics/droidloom-composer-service/src/main.rs","bytes":19202,"sha256":"567c60fd293f35e2e0957db6f38bc967cc0c3fa90354b98491d461a7decdb4ce"},"candidate-control.rs":{"path":"graphics/droidloom-composer-service/src/control.rs","bytes":42491,"sha256":"d3d9f4b763a6e80b6549119e42b4d6c3c6ab7368359f3cc71d2e090f05a881ca"}}
SOURCE_MAP = {}
DEADLINE = None
CHILD_REAPER = None
OBSERVED_SIGNALS = []
MEMORY_BUDGET = 2147483648
MINIMUM_MEM_AVAILABLE = 4294967296
WORK_SECONDS = 900


OWN_CARGO_HOME = ROOT/'cargo-home'
PREP_OUT = Path("/home/alex/work/p4-retirement-wayland-vendor-prep01-20261106")/'attempt01'
VENDOR_BINDING = {"vendor-prep-result.json":{"bytes":179590,"sha256":"8b9f70cf5f4819b81821cc61ec6ef3d984c22af7b5611e26cfaa410293d4fade"},"prepared-vendor-manifest.json":{"bytes":4087264,"sha256":"6dc3f052db6f9498bfdb73cd3f4b4d3b1f7556c6192ac5dbac3c611e24f4fac7"},"prepared-vendor-config.toml":{"bytes":204,"sha256":"81459dfa6a26d6665e157a219053c0782db24f54eb45bd71043e9e0d29c5e20c"}}
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
    require(fields['memory.max'] == '2147483648' and fields['cpu.max'] == '100000 100000', 'owned resource limits do not match the request')
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





def apply_candidate_sources(expected, candidate_expected, copied_before):
    require(len(expected) == 499 and len(candidate_expected) == 500,
            'original/candidate file counts differ')
    additions = set(candidate_expected)-set(expected)
    differences = {path for path in expected if expected[path] != candidate_expected.get(path)}
    require(additions == {ENGINE_PATH} and len(differences) == 8 and
            differences | additions == {row['path'] for row in SOURCE_PINS.values()} and
            set(expected) <= set(candidate_expected),
            'candidate differs outside eight replacements and one engine ledger')
    for name, wanted in SOURCE_PINS.items():
        path = wanted['path']
        row = candidate_expected[path]
        require(row['kind'] == 'file' and row['mode'] == 0o664 and
                row['bytes'] == wanted['bytes'] and row['sha256'] == wanted['sha256'],
                'candidate map pin differs: '+path)
        data, actual = held(HERE/name, 131072)
        require(actual['bytes'] == wanted['bytes'] and actual['sha256'] == wanted['sha256'],
                'candidate payload changed: '+name)
        target = COPIED/path
        real_directory(target.parent)
        if path in expected:
            require(hash_held(target) == copied_before[path], 'copied baseline changed: '+path)
            flags = os.O_WRONLY|os.O_TRUNC|os.O_CLOEXEC|os.O_NOFOLLOW
        else:
            flags = os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW
        fd = os.open(target,flags,0o600)
        with os.fdopen(fd,'wb') as stream:
            require(stream.write(data) == len(data), 'short owned source write')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(target,0o664,follow_symlinks=False)
    observed = regular_tree(COPIED)
    portable(observed,candidate_expected)
    return observed


def fresh_host_memory_admission(report):
    path = Path('/proc/meminfo')
    fd = os.open(path, os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0,
                'fixed host meminfo is not the expected root-owned proc file')
        pieces, total = [], 0
        while True:
            part = os.read(fd, min(4096,16385-total))
            if not part:
                break
            total += len(part)
            require(total <= 16384, 'fixed meminfo exceeds bound')
            pieces.append(part)
        raw = b''.join(pieces)
        require(identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
                'fixed meminfo object changed during bounded read')
    finally:
        os.close(fd)
    # Preserve the complete actual observation before interpreting admission.
    raw_pin = write_new(OUT/'host-meminfo-before.txt',raw)
    rows = {}
    for line in raw.decode('ascii').splitlines():
        match = re.fullmatch(r'([A-Za-z0-9_()]+):\s+([0-9]+)(?:\s+(kB))?',line)
        require(match is not None and match[1] not in rows, 'malformed or duplicate meminfo field')
        rows[match[1]] = (int(match[2]),match[3])
    wanted = ['MemTotal','MemAvailable','SwapTotal','SwapFree','SwapCached']
    require(all(key in rows and rows[key][1] == 'kB' for key in wanted),
            'required host memory fields lack exact kB units')
    values = {key:rows[key][0]*1024 for key in wanted}
    require(0 <= values['MemAvailable'] <= values['MemTotal'] and
            0 <= values['SwapFree'] <= values['SwapTotal'] and
            0 <= values['SwapCached'] <= values['SwapTotal'], 'inconsistent host memory observation')
    receipt = {'observed_utc':utc(),'raw_meminfo':raw_pin,'fields_bytes':values,
        'owned_memory_budget':MEMORY_BUDGET,'minimum_MemAvailable':MINIMUM_MEM_AVAILABLE,
        'additional_MemAvailable_margin':MINIMUM_MEM_AVAILABLE-MEMORY_BUDGET,
        'global_swap_is_not_an_admission_budget':True,'decision_performed':False,
        'scope':'one fresh host snapshot, not a reservation or Main noninterference proof'}
    report['resource_admission'] = write_new(OUT/'resource-admission.json',receipt)
    report['resource_admission_observed_bytes'] = values
    report['resource_admission_qualified'] = False
    require(values['MemAvailable'] >= MINIMUM_MEM_AVAILABLE,
            'less than 4 GiB MemAvailable for independent 2 GiB Wayland check; no retry')
    report['resource_admission_qualified'] = True


def pkg_config_path_list(raw):
    require(0 < len(raw) <= 8192 and raw.endswith(b'\n') and raw.count(b'\n') == 1,
            'pkg-config default pc_path is not one bounded complete line')
    value = raw[:-1].decode('ascii')
    parts = value.split(':')
    require(0 < len(parts) <= 16 and len(parts) == len(set(parts)) and
            all(parts), 'pkg-config default path has empty/duplicate/excess elements')
    for item in parts:
        path = PurePosixPath(item)
        require(item.startswith('/') and str(path) == item and
                '..' not in path.parts and '.' not in item.split('/') and
                re.fullmatch(r'/[A-Za-z0-9_./+-]+',item) is not None and
                (item.startswith('/usr/') or item.startswith('/lib/')),
                'pkg-config default path is noncanonical or outside fixed public host roots')
    return parts


def absent_pc_directory(requested):
    # A default search entry is not a promise that the directory exists.
    # Bind the nearest existing protected ancestor and prove its first missing
    # child absent through that held directory. No provider or fallback is made.
    path = Path(requested)
    anchor = None
    for candidate in path.parents:
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        anchor = candidate
        break
    require(anchor is not None, 'missing pkg-config path has no existing ancestor')
    resolved = anchor.resolve(strict=True)
    require(resolved == Path('/usr') or resolved.is_relative_to(Path('/usr')) or
            resolved == Path('/lib') or resolved.is_relative_to(Path('/lib')),
            'missing pkg-config path ancestor escaped fixed public host roots')
    real_directory(resolved)
    named_ancestors, real_ancestors = [], []
    for parent in (anchor,*anchor.parents):
        st = parent.lstat()
        require(st.st_uid == 0 and
                (stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)),
                'missing pkg-config path ancestor has wrong type/owner')
        named_ancestors.append({'path':str(parent),'identity':identity(st),
                                'resolved_path':str(parent.resolve(strict=True))})
    for parent in (resolved,*resolved.parents):
        st = parent.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and
                not stat.S_IMODE(st.st_mode)&0o022,
                'missing pkg-config path real ancestor is not protected')
        real_ancestors.append({'path':str(parent),'identity':identity(st)})
    missing_name = path.relative_to(anchor).parts[0]
    fd = -1
    first_error = None
    close_error = None
    result = None
    try:
        fd = os.open(resolved,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        held_identity = identity(os.fstat(fd))
        require(held_identity == real_ancestors[0]['identity'],
                'missing pkg-config path ancestor changed before open')
        for observation in range(2):
            try:
                os.stat(missing_name,dir_fd=fd,follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('pkg-config default entry appeared while proving absence: '+requested)
            for row in named_ancestors:
                current = Path(row['path'])
                require(identity(current.lstat()) == row['identity'] and
                        str(current.resolve(strict=True)) == row['resolved_path'],
                        'missing pkg-config path named ancestor changed')
            for row in real_ancestors:
                require(identity(Path(row['path']).lstat()) == row['identity'],
                        'missing pkg-config path real ancestor changed')
            require(identity(os.fstat(fd)) == held_identity and
                    anchor.resolve(strict=True) == resolved,
                    'missing pkg-config path held ancestor changed')
        result = {'requested_path':requested,'state':'ABSENT',
                  'first_absent_path':str(anchor/missing_name),
                  'resolved_anchor':str(resolved),'held_anchor_identity':held_identity,
                  'named_ancestors':named_ancestors,'real_ancestors':real_ancestors,
                  'absence_observations':2,'provider_qualified':False}
    except BaseException as error:
        first_error = error
    finally:
        if fd >= 0:
            value, fd = fd, -1
            try:
                os.close(value)
            except BaseException as error:
                close_error = error
    if first_error is not None:
        if close_error is not None:
            raise RuntimeError('pkg-config absence primary='+repr(first_error)+
                               '; held ancestor close='+repr(close_error)) from first_error
        raise first_error
    if close_error is not None:
        raise RuntimeError('pkg-config absent ancestor close failed: '+repr(close_error)) from close_error
    require(result is not None, 'pkg-config absence observation did not complete')
    result['held_anchor_fd_closed'] = True
    return result


def native_pc_snapshot(paths):
    # Only immediate entries of the actual fixed tool's bounded default directories.
    # No fallback paths, recursive host walk, or arbitrary directory discovery.
    directories, namespace, files, absent = [], [], {}, []
    total_files, total_bytes = 0, 0
    for requested in paths:
        path = Path(requested)
        try:
            named = path.lstat()
        except FileNotFoundError:
            absent.append(absent_pc_directory(requested))
            continue
        require(named.st_uid == 0, 'pkg-config default directory alias owner differs: '+requested)
        resolved = path.resolve(strict=True)
        require(resolved.is_relative_to(Path('/usr')) or resolved.is_relative_to(Path('/lib')),
                'pkg-config default directory resolution escaped fixed host roots')
        real_directory(resolved)
        for parent in (resolved,*resolved.parents):
            st = parent.lstat()
            require(st.st_uid == 0 and not stat.S_IMODE(st.st_mode)&0o022,
                    'pkg-config directory ancestor is writable by a nonowner: '+str(parent))
        namespace.append((path,resolved,identity(named)))
    for path,resolved,named_identity in namespace:
        fd = os.open(resolved,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            require(stat.S_ISDIR(before.st_mode) and before.st_uid == 0 and
                    not stat.S_IMODE(before.st_mode)&0o022,
                    'pkg-config default input is not a protected real directory')
            names = []
            with os.scandir(fd) as entries:
                for entry in entries:
                    require(len(names) < 4096, 'pkg-config directory entry bound exceeded')
                    names.append(entry.name)
            require(len(names) == len(set(names)), 'duplicate pkg-config directory entry')
            for name in sorted(names):
                if not name.endswith('.pc'):
                    continue
                require(re.fullmatch(r'[A-Za-z0-9_.+-]+\.pc',name) is not None,
                        'noncanonical pkg-config metadata filename')
                total_files += 1
                require(total_files <= 2048, 'pkg-config metadata file bound exceeded')
                requested_file = resolved/name
                named_file = requested_file.lstat()
                require(named_file.st_uid == 0, 'pkg-config metadata alias owner differs')
                target = requested_file.resolve(strict=True)
                require(any(target.is_relative_to(root) for _,root,_ in namespace),
                        'pkg-config metadata alias escaped actual default namespaces')
                real_directory(target.parent)
                held_row = hash_held(target,1024*1024)
                target_st = target.lstat()
                require(stat.S_ISREG(target_st.st_mode) and target_st.st_uid == 0 and
                        not stat.S_IMODE(target_st.st_mode)&0o6022,
                        'pkg-config metadata is not a protected root-owned regular file')
                require(requested_file.resolve(strict=True) == target and
                        identity(requested_file.lstat()) == identity(named_file),
                        'pkg-config metadata alias changed while reading')
                total_bytes += held_row['bytes']
                require(total_bytes <= 16*1024*1024, 'pkg-config metadata byte bound exceeded')
                require(str(requested_file) not in files, 'duplicate pkg-config input path')
                files[str(requested_file)] = {'requested_identity':identity(named_file),
                    'resolved_path':str(target),'held':held_row}
            require(identity(before) == identity(os.fstat(fd)) == identity(resolved.lstat()) and
                    identity(path.lstat()) == named_identity and path.resolve(strict=True) == resolved,
                    'pkg-config default directory changed during complete immediate snapshot')
            directories.append({'requested_path':str(path),'requested_identity':named_identity,
                'resolved_path':str(resolved),'held_identity':identity(before),'entries':sorted(names)})
        finally:
            os.close(fd)
    for row in absent:
        require(absent_pc_directory(row['requested_path']) == row,
                'pkg-config missing default entry changed during full namespace snapshot')
    require(files, 'actual pkg-config default directories contain no qualified metadata')
    return {'default_search_paths':paths,'default_directories':directories,
            'absent_default_directories':absent,'pc_files':files,
            'pc_file_count':total_files,'pc_bytes':total_bytes,'recursive_walk_performed':False,
            'native_headers_and_libraries_exhaustively_hashed':False}


def qualify_pkg_config(report, environment, tool_inputs):
    # First observation of this one fixed tool, never an old-tool hash claim.
    allowed = [Path('/usr/bin'),Path('/usr/lib'),Path('/lib')]
    row = pin_resolved(Path('/usr/bin/pkg-config'),allowed)
    tool_inputs.append(row)
    resolved = Path(row['resolved_path'])
    st = resolved.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and st.st_gid == 0 and
            stat.S_IMODE(st.st_mode)&0o111 and not stat.S_IMODE(st.st_mode)&0o6022,
            'fixed pkg-config tool is not a protected root-owned executable')
    fd = os.open(resolved,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        require(identity(os.fstat(fd)) == row['identity'] and os.read(fd,4) == b'\x7fELF',
                'fixed pkg-config executable is not the observed ELF')
    finally:
        os.close(fd)
    version = command(['/usr/bin/pkg-config','--version'],COPIED,environment,
                      'fixed-pkg-config-version',report['commands'],10)
    require(len(version) <= 128 and
            re.fullmatch(rb'[0-9]+\.[0-9]+(?:\.[0-9]+)?\n',version) is not None,
            'fixed pkg-config version is not a bounded numeric version')
    linked = command(['/usr/bin/ldd',str(resolved)],COPIED,environment,
                     'fixed-pkg-config-linked-libraries',report['commands'],10).decode()
    require(len(linked.encode()) <= 65536 and 'not found' not in linked,
            'pkg-config runtime library output missing or oversized')
    rows = [row]
    for line in linked.splitlines():
        match = re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
        if match:
            observed = pin_resolved(Path(match[1]),allowed)
            rows.append(observed)
            tool_inputs.append(observed)
    require(not any(name.startswith('PKG_CONFIG') for name in environment),
            'pkg-config path query was affected by a prior environment override')
    default_raw = command(['/usr/bin/pkg-config','--variable=pc_path','pkg-config'],
        COPIED,environment,'fixed-pkg-config-default-path',report['commands'],10)
    report['pkg_config_default_path_raw'] = write_new(OUT/'pkg-config-default-path.txt',default_raw)
    paths = pkg_config_path_list(default_raw)
    report['pkg_config_first_observation'] = {'tool':row,'version':version.decode(),
        'default_paths':paths,'prior_tool_hash_authority':False,
        'prior_PC_layout_authority':False,'default_path_query_count':1,
        'stable_absent_default_directories_are_not_providers':True,
        'required_native_dependencies_still_checked_by_original_build_scripts':True,
        'fallback_paths_or_system_metadata_created':False}
    snapshot = native_pc_snapshot(paths)
    report['native_pc_inputs_before'] = write_new(OUT/'native-pc-inputs-before.json',snapshot)
    require(not verify_resolved(rows), 'pkg-config tool closure changed during observation')
    # Freeze only the actual default search result; never invent a distro layout.
    environment.update({'PKG_CONFIG':'/usr/bin/pkg-config',
                        'PKG_CONFIG_LIBDIR':':'.join(paths),'PKG_CONFIG_PATH':''})
    return paths,snapshot

def qualified_vendor_inputs(registry, original_lock, cache, report):
    require(all(type(row.get('bytes')) is int and row['bytes'] > 0 and
                re.fullmatch(r'[0-9a-f]{64}',row.get('sha256','')) is not None
                for row in VENDOR_BINDING.values()),
            'future vendor preparation pins are not actually bound')
    raw_inputs, staged_inputs = {}, {}
    for name, limit in [('vendor-prep-result.json',4*1024*1024),
                        ('prepared-vendor-manifest.json',32*1024*1024),
                        ('prepared-vendor-config.toml',4096)]:
        raw,row = held(HERE/name,limit)
        expected = VENDOR_BINDING[name]
        require(row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'],
                'staged actual vendor input differs: '+name)
        raw_inputs[name],staged_inputs[name] = raw,row
    prior = json.loads(raw_inputs['vendor-prep-result.json'])
    manifest = json.loads(raw_inputs['prepared-vendor-manifest.json'])
    require(prior['state'] == 'PASS' and prior['collection_complete'] is True and
            prior['offline_vendor_prepared_qualified'] is True and
            prior['fixed_registry_packages'] == 193 and len(prior['packages']) == 193 and
            prior['shared_cache_writes'] == 0 and prior['workspace_or_lock_modified'] is False and
            prior['production_sources_modified'] is False and prior['Main_actions'] == 0 and
            prior['Cargo_executed'] is False and prior['crate_code_executed'] is False and
            prior['commands_executed'] == 0 and prior['metadata_or_compile_qualified'] is False and
            prior['production_ready'] is False and not prior['secondary_errors'] and
            not prior['observed_signals'] and prior['shared_cache_presence_unchanged'] is True and
            prior['own_children_before']['observed_empty'] is True and
            prior['own_children_after']['observed_empty'] is True and
            prior['owned_resource_gate']['pass'] is True and prior['owned_resource_fd_closed'] is True and
            not prior['explicit_owned_descriptor_journal']['remaining'] and
            not prior['explicit_owned_descriptor_journal']['close_errors'] and
            all(prior[name] == [] for name in ['authorities_changes','original_cached_archives_changes',
                  'original_45_sources_changes','private_archives_changes','vendor_sources_changes']),
            'actual preparation lacks a complete success and unchanged-input/cleanup/resource gate')
    require(all(item['complete'] is True and item['http_requests'] == 1 and
                item['automatic_retries'] == 0 and item['redirects_followed'] == 0 and
                item['response_closed'] is True and item['connection_closed'] is True
                for item in prior['downloads']), 'preparation retained an incomplete download')
    current_registry = {(row['name'],row['version']):row for row in registry['packages']}
    prior_rechecked = {(row['name'],row['version']):row for row in prior['original_45_requalification']}
    require(len(current_registry) == len(registry['packages']) == 45 and
            len(prior_rechecked) == len(prior['original_45_requalification']) == 45 and
            set(prior_rechecked) == set(current_registry) and
            all(prior_rechecked[key]['every_archive_file_matches_held_extracted_source'] is True and
                prior_rechecked[key]['archive']['sha256'] ==
                    current_registry[key]['expected_lock_checksum'] ==
                    current_registry[key]['comparison']['archive']['sha256']
                for key in current_registry),
            'prepared vendor lost the original45 archive/source authority')
    fixed_vendor, fixed_archives = PREP_OUT/'vendor', PREP_OUT/'archives'
    require(manifest['schema'] == 1 and
            manifest['source'] == 'exact-crates-io-original-workspace-lock' and
            manifest['original_lock'] == {'bytes':51836,'sha256':
                'c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62'} and
            manifest['vendor_root'] == str(fixed_vendor) and manifest['archive_root'] == str(fixed_archives) and
            manifest['registry_packages'] == 193 and manifest['metadata_or_compilation_executed'] is False,
            'actual prepared vendor uses a different root, phase or original lock')
    config = ('[source.crates-io]\nreplace-with = "pocket4-locked-vendor"\n\n'
              '[source.pocket4-locked-vendor]\ndirectory = '+json.dumps(str(fixed_vendor))+
              '\n\n[net]\noffline = true\n').encode()
    require(raw_inputs['prepared-vendor-config.toml'] == config and
            prior['source_config'] == manifest['source_config'],
            'explicit vendor source replacement differs')
    original_outputs = {}
    for input_name, field, path in [
        ('prepared-vendor-manifest.json','vendor_manifest',PREP_OUT/'vendor-manifest.json'),
        ('prepared-vendor-config.toml','source_config',PREP_OUT/'vendor-config.toml')]:
        before = prior[field]
        real_directory(path.parent)
        require(before['path'] == str(path) and before['bytes'] == VENDOR_BINDING[input_name]['bytes'] and
                before['sha256'] == VENDOR_BINDING[input_name]['sha256'] and
                hash_held(path,32*1024*1024) == before,
                'original prepared vendor metadata changed')
        original_outputs[str(path)] = before
    locked = {(row['name'],row['version']):row for row in original_lock['package'] if 'source' in row}
    records = manifest['packages']
    prepared = {(row['name'],row['version']):row for row in records}
    require(len(locked) == len(records) == len(prepared) == 193 and set(prepared) == set(locked),
            'prepared vendor does not contain exactly all locked registry packages')
    total_files,total_bytes,total_archives = 0,0,0
    for key in sorted(prepared):
        require(time.monotonic() < DEADLINE, 'complete vendor input qualification deadline exhausted')
        row,lock = prepared[key],locked[key]
        name,version = key
        require(re.fullmatch(r'[A-Za-z0-9_-]+',name) is not None and
                re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9_.+-]+)?',version) is not None and
                lock['source'] == 'registry+https://github.com/rust-lang/crates.io-index' and
                re.fullmatch(r'[0-9a-f]{64}',lock.get('checksum','')) is not None and
                row['package_checksum'] == lock['checksum'],
                'prepared package differs from original exact source/checksum')
        directory,archive = fixed_vendor/(name+'-'+version),fixed_archives/(name+'-'+version+'.crate')
        real_directory(directory)
        directory_st = directory.lstat()
        require(stat.S_ISDIR(directory_st.st_mode) and directory_st.st_uid == 1000 and
                directory_st.st_gid == 1000 and stat.S_IMODE(directory_st.st_mode) == 0o700 and
                row['directory'] == str(directory) and row['archive']['path'] == str(archive),
                'prepared package left its exact private root')
        archive_pin = hash_held(archive,32*1024*1024)
        require(archive_pin == row['archive'] and archive_pin['sha256'] == lock['checksum'],
                'prepared complete archive changed')
        inventory = regular_tree(directory,4096,64*1024*1024)
        require(inventory == row['files'] and '.cargo-checksum.json' in inventory and 'Cargo.toml' in inventory and
                len(inventory) == row['source_files']+1 and
                inventory['.cargo-checksum.json'] == row['checksum_metadata'] and
                all(value['path'] == str(directory/path) and
                    stat.S_IMODE(value['identity'][2]) in (0o444,0o555)
                    for path,value in inventory.items()),
                'complete archive-derived vendor file map changed')
        checksum_raw,checksum_pin = held(directory/'.cargo-checksum.json',1024*1024)
        expected_checksum = {'package':lock['checksum'],
            'files':{path:value['sha256'] for path,value in sorted(inventory.items())
                     if path != '.cargo-checksum.json'}}
        require(json.loads(checksum_raw) == expected_checksum and
                checksum_pin == row['checksum_metadata'],
                'Cargo source checksum metadata differs from every prepared original archive file')
        package_raw,package_pin = held(directory/'Cargo.toml',1024*1024)
        package = tomllib.loads(package_raw.decode('utf-8'))['package']
        require(package['name'] == name and package['version'] == version and
                package_pin == inventory['Cargo.toml'], 'prepared package manifest name/version differs')
        total_files += len(inventory)
        total_bytes += sum(value['bytes'] for value in inventory.values())
        total_archives += archive_pin['bytes']
        require(total_files <= 193*4096 and total_bytes <= 1024*1024*1024 and
                total_archives <= 512*1024*1024,
                'complete prepared registry exceeds original finite bounds')
        files = {str(archive):archive_pin,**{value['path']:value for value in inventory.values()}}
        cache[key] = {'checksum':lock['checksum'],'rows':inventory,'archive':archive_pin,'files':files,
                      'directory':str(directory),'source_inventory':prior['vendor_manifest']}
    require(total_files == prior['vendor_file_count'] and total_bytes == prior['vendor_source_bytes'] and
            total_archives == prior['archive_bytes'],
            'prepared full mapping totals differ')
    report['actual_vendor_preparation'] = {
        'result':staged_inputs['vendor-prep-result.json'],'original_manifest':prior['vendor_manifest'],
        'original_config':prior['source_config'],'registry_packages':193,
        'source_files':total_files,'source_bytes':total_bytes,'archive_bytes':total_archives,
        'all_current_archive_and_file_maps_equal_actual_preparation':True,
        'original45_authority_preserved':True,
        'source_copy_qualifies_no_Cargo_or_runtime_result':True}
    report['offline_vendor_input_gate_qualified'] = True
    collected = {value['path']:value for value in staged_inputs.values()}
    collected.update(original_outputs)
    for entry in cache.values():
        collected.update(entry['files'])
    return prepared,collected


def selected_dependencies(metadata, registry, original_lock, selected_lock, cache, prepared):
    require(metadata.get('target_directory') == str(OUT/'cargo-target') and
            type(metadata.get('packages')) is list and 0 < len(metadata['packages']) <= 256,
            'metadata target/package bound differs')
    entries = metadata['packages']
    by_id = {p['id']:p for p in entries}
    require(len(by_id) == len(entries), 'duplicate metadata package identity')
    nodes = {node['id']:node for node in metadata.get('resolve',{}).get('nodes',[])}
    require(len(nodes) == len(metadata.get('resolve',{}).get('nodes',[])) and
            0 < len(nodes) <= len(by_id) and set(nodes) <= set(by_id),
            'resolver package membership differs')
    require(metadata.get('workspace_root') == str(COPIED), 'Wayland workspace root differs')
    roots = [p for p in entries if p['source'] is None and p['name'] == 'droidloom-wayland' and
             p['manifest_path'] == str(COPIED/'graphics/droidloom-wayland/Cargo.toml')]
    require(len(roots) == 1 and roots[0]['id'] in metadata.get('workspace_members',[]),
            'real Wayland crate root is absent')
    selected_ids, pending = set(), [roots[0]['id']]
    while pending:
        item = pending.pop()
        if item in selected_ids:
            continue
        require(item in by_id and item in nodes and len(selected_ids) < 256,
                'Wayland resolver closure escaped bounded metadata')
        selected_ids.add(item)
        # --filter-platform selects this real host. This compile-only binary
        # uses normal/build edges, not unrelated dev-test dependencies.
        for edge in nodes[item]['deps']:
            require(edge['pkg'] in nodes and type(edge['dep_kinds']) is list and edge['dep_kinds'],
                    'metadata dependency edge is incomplete')
            require(all(k.get('kind') in (None,'build','dev') for k in edge['dep_kinds']),
                    'unknown dependency kind in locked metadata')
            if any(k['kind'] in (None,'build') for k in edge['dep_kinds']):
                pending.append(edge['pkg'])
    def lock_rows(value):
        result = {}
        for row in value['package']:
            key = (row['name'],row['version'])
            require(key not in result, 'ambiguous package version in immutable lock')
            result[key] = row
        return result
    old, new = lock_rows(original_lock), lock_rows(selected_lock)
    require(new == old, 'Wayland does not use exact original locked packages')
    authority = {(r['name'],r['version']):r for r in registry['packages']}
    require(len(authority) == len(registry['packages']) == 45,
            'original actual registry authority is incomplete')
    source_roots = {str(Path(r['source_directory']).parent) for r in registry['packages']}
    archive_roots = {str(Path(r['expected_archive_path']).parent) for r in registry['packages']}
    require(len(source_roots) == len(archive_roots) == 1, 'multiple registry namespaces rejected')
    source_root, archive_root = Path(next(iter(source_roots))), Path(next(iter(archive_roots)))
    require(source_root.parent == CARGO_HOME/'registry/src' and
            archive_root.parent == CARGO_HOME/'registry/cache' and
            source_root.name == archive_root.name and '..' not in source_root.parts,
            'actual registry roots are not paired fixed Cargo cache namespaces')
    descriptions, collected = [], {}
    for package_id in sorted(selected_ids):
        p = by_id[package_id]
        key = (p['name'],p['version'])
        require(re.fullmatch(r'[A-Za-z0-9_-]+',key[0]) is not None and
                re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9_.+-]+)?',key[1]) is not None,
                'noncanonical locked package component')
        require(key in new, 'selected package missing from held lock')
        locked = new[key]
        if p['source'] is None:
            require(locked.get('source') is None, 'path package acquired a registry source')
            require(key in old and old[key].get('source') is None, 'path package is not in original lock')
            manifest = Path(p['manifest_path'])
            require(manifest.is_relative_to(COPIED) and '..' not in manifest.parts and
                    str(manifest.relative_to(COPIED)) in SOURCE_MAP and
                    SOURCE_MAP[str(manifest.relative_to(COPIED))]['kind'] == 'file',
                    'path package manifest escaped exact copied source')
            require(hash_held(manifest)['sha256'] == SOURCE_MAP[str(manifest.relative_to(COPIED))]['sha256'],
                    'path package manifest changed before compilation')
            kind = 'pinned-source'
            descriptions.append({'id':p['id'],'name':p['name'],'version':p['version'],
                                 'kind':kind,'manifest':p['manifest_path']})
            continue
        require(key in old and p['source'] == locked.get('source') ==
                old[key].get('source') == 'registry+https://github.com/rust-lang/crates.io-index' and
                locked.get('checksum') == old[key].get('checksum') and
                re.fullmatch(r'[0-9a-f]{64}',locked.get('checksum','')) is not None,
                'resolver selected a registry package outside immutable original lock')
        observed = authority.get(key)
        require(key in prepared and key in cache, 'selected package was not completely prepared before metadata')
        saved = cache[key]
        directory = Path(saved['directory'])
        archive = Path(saved['archive']['path'])
        require(p['manifest_path'] == str(directory/'Cargo.toml') and
                directory == PREP_OUT/'vendor'/(key[0]+'-'+key[1]) and
                archive == PREP_OUT/'archives'/(key[0]+'-'+key[1]+'.crate'),
                'registry metadata escaped the exact prepared original-lock vendor')
        if observed is not None:
            require(observed['source_directory'] == str(source_root/(key[0]+'-'+key[1])) and
                    observed['expected_archive_path'] == str(archive_root/(key[0]+'-'+key[1]+'.crate')) and
                    observed['expected_lock_checksum'] == locked['checksum'] and
                    observed['comparison']['archive_matches_lock'] is True and
                    observed['comparison']['every_archive_file_matches_held_extracted_source'] is True,
                    'selected original45 package lost its prior actual archive/source authority')
        real_directory(directory)
        real_directory(archive.parent)
        require(saved['checksum'] == locked['checksum'] and hash_held(archive) == saved['archive'] and
                regular_tree(directory,4096,64*1024*1024) == saved['rows'],
                'prepared complete archive/source mapping changed between metadata phases')
        rows, archive_pin = saved['rows'],saved['archive']
        comparison = {'source_inventory':saved['source_inventory']}
        if observed is not None:
            require(archive_pin['sha256'] == observed['comparison']['archive']['sha256'],
                    'existing actual archive bytes changed')
        collected[str(archive)] = archive_pin
        for row in rows.values():
            require(len(collected) < 65536, 'selected source closure exceeds explicit file bound')
            collected[row['path']] = row
        manifest_raw, manifest_pin = held(directory/'Cargo.toml',1024*1024)
        package = tomllib.loads(manifest_raw.decode())['package']
        require(package['name'] == key[0] and package['version'] == key[1] and
                manifest_pin == rows['Cargo.toml'], 'cached package manifest differs')
        descriptions.append({'id':p['id'],'name':p['name'],'version':p['version'],
            'kind':'offline-registry','manifest':p['manifest_path'],'archive':archive_pin,
            'package_checksum':locked['checksum'],'archive_to_source':comparison['source_inventory'],
            'authority_kind':'prior-45-actual-and-complete-vendor-rechecked' if observed is not None else 'additional-original-lock-complete-vendor-rechecked',
            'prior_actual_archive_authority_present':observed is not None})
    return roots[0]['id'],descriptions,collected


def qualify_wayland_compile(raw, packages, dependency_rows, source_rows, root_id):
    qualified = {p['manifest']:p for p in packages}
    ids = {p['id'] for p in packages}
    observed, completions, wayland_artifacts = set(), [], []
    output_rows = {}
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        reason = item.get('reason')
        if reason == 'compiler-artifact':
            manifest = item.get('manifest_path')
            require(manifest in qualified and item['package_id'] == qualified[manifest]['id'],
                    'Cargo compiled an unqualified package')
            source = Path(item['target']['src_path'])
            row = dependency_rows.get(str(source))
            if row is None and source.is_relative_to(COPIED):
                row = source_rows.get(str(source.relative_to(COPIED)))
            require(row is not None and hash_held(source) == row,
                    'compiled target source was not prequalified')
            require(type(item['filenames']) is list and len(item['filenames']) <= 32 and
                    all(Path(name).is_relative_to(OUT/'cargo-target') and '..' not in Path(name).parts
                        for name in item['filenames']), 'compiled output escaped owned target')
            observed.add(item['package_id'])
            if item['package_id'] == root_id:
                require(item['target']['name'] == 'droidloom-wayland' and item['target']['kind'] == ['bin'] and
                        item['target']['src_path'] == str(COPIED/'graphics/droidloom-wayland/src/main.rs') and
                        item['profile']['test'] is False and item.get('executable') is None,
                        'Wayland check did not type-check the real complete binary target')
                wayland_artifacts.append(item)
                for name in item['filenames']:
                    path = Path(name)
                    require(str(path) not in output_rows, 'duplicate Wayland check output')
                    output_rows[str(path)] = hash_held(path,128*1024*1024)
        elif reason == 'build-script-executed':
            require(item['package_id'] in ids and Path(item['out_dir']).is_relative_to(OUT/'cargo-target') and
                    '..' not in Path(item['out_dir']).parts,
                    'unqualified build script or output directory')
        elif reason == 'build-finished':
            completions.append(item.get('success'))
        elif reason != 'compiler-message':
            raise RuntimeError('unexpected Cargo JSON record: '+str(reason))
    require(completions == [True] and observed and len(wayland_artifacts) == 1,
            'complete Wayland binary target type-check is absent or failed')
    return sorted(observed),wayland_artifacts[0],output_rows


def compact_preserved_command_logs(report):
    # Complete streams stay in their original commandNN files with their pins.
    # Keep a failed command's first error without inlining multi-megabyte text.
    for row in report['commands']:
        for stream in ['stdout','stderr']:
            value = row.get(stream)
            key = stream+'_pin'
            if isinstance(value,str) and key in row:
                row[stream] = row.pop(key)
                row[stream+'_raw_preserved_separately'] = True

def execute():
    global DEADLINE, CHILD_REAPER, SOURCE_MAP
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'ordinary operator UID1000 required')
    require(Path(__file__).absolute() == HERE/'check_wayland.py', 'exact staged controller required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(), 'create-only attempt already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    (OUT/'tmp').mkdir(mode=0o700)
    OWN_CARGO_HOME.mkdir(mode=0o700)
    DEADLINE = time.monotonic()+WORK_SECONDS
    report = {'schema':1,'state':'RUNNING','started_utc':utc(),'phase':'RESOURCE_ADMISSION',
              'scope':'complete exact Wayland binary crate cargo check with original workspace/lock',
              'Main_actions':0,'Main_identity_observed':False,'install_actions':0,
              'Android_Binder_provider_compile':False,'Android_or_Soong_executed':False,
              'installed_Main_source_provenance_qualified':False,'actual_Bili_failure_cause_proven':False,
              'production_ready':False,'commands':[],'focused_tests_executed':0,
              'host112_controls_repeated':False,'Wayland_runtime_GPU_qualified':False,
              'Wayland_complete_crate_typecheck_qualified':False,
              'network_downloads_permitted':False,'secondary_errors':[]}
    def interrupted(number, frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned controller interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    resource_fd, resource_before = -1, None
    original_rows, candidate_rows, dependency_rows, dependency_cache = {}, {}, {}, {}
    tool_rows, config_rows, config_paths = [], [], []
    pc_paths, pc_before, check_outputs = [], None, {}
    def secondary(stage, error):
        report['state'] = 'FAIL'
        report['secondary_errors'].append({'stage':stage,'error':repr(error)})
    try:
        resource_fd, resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        fresh_host_memory_admission(report)
        allowed = sorted(os.sched_getaffinity(0))
        require(len(allowed) >= 3, 'cannot leave two logical CPUs free')
        os.sched_setaffinity(0, [allowed[-1]])
        report['allowed_cpus_before'] = allowed
        report['selected_cpus'] = [allowed[-1]]
        CHILD_REAPER = OwnChildReaper()
        CHILD_REAPER.begin()
        env = {'PATH':'/usr/bin:/bin','CARGO_HOME':str(OWN_CARGO_HOME),
               'RUSTC':str(RUST_SYSROOT/'bin/rustc'),'RUSTDOC':str(RUST_SYSROOT/'bin/rustdoc'),
               'CARGO_NET_OFFLINE':'true','LC_ALL':'C','LANG':'C',
               'TMPDIR':str(OUT/'tmp'),'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
               'PYTHONDONTWRITEBYTECODE':'1'}
        python = pin_resolved(Path(sys.executable),[Path('/usr/bin')])
        require(Path(sys.executable) == Path('/usr/bin/python3'), 'admitted Python interpreter path differs')
        tool_rows.append(python)
        report['admitted_python_runtime_observation'] = python
        run_child_lifecycle_controls(report, OUT, env)
        report['phase'] = 'SOURCE_AND_TOOLCHAIN'
        parent_raw, parent_pin = pinned_packet('parent469-result.json',
            '3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5')
        parent = json.loads(parent_raw)
        require(parent_pin['bytes'] == 170316 and parent['state'] == 'PASS' and
                len(parent['commands']) == 65 and
                all(row['returncode'] == 0 and not row['timed_out'] for row in parent['commands']) and
                parent['focused_tests_passed'] == 27 and parent['updater_focused_tests_passed'] == 18 and
                parent['source_resume_tests_passed'] == 9 and
                parent['source_delta']['actual_source_file_count'] == 499 and
                parent['copied_manifest']['bytes'] == 99327 and
                parent['copied_manifest']['sha256'] == PARENT_MANIFEST_SHA and
                parent['builder_elf']['bytes'] == 34767856 and
                parent['builder_elf']['sha256'] == 'c758a1e12bbc1925cc36f8cde3b369ab8449ad1cf460a9854b42d627575627d8' and
                parent['owned_resource_gate']['pass'] is True and
                parent['copied_source_unchanged_after'] is True and
                parent['original_source_unchanged_after'] is True and
                parent['cargo_configs_unchanged_after'] is True and
                not parent['tool_changes'] and not parent['dependency_changes'] and
                not parent['cleanup']['errors'] and not parent['cleanup']['remaining'] and
                parent['cleanup']['forced_cleanup'] is False and
                parent['runtime_authorization_enabled'] is False,
                'actual builder469 source/tool qualification differs')
        report['actual_parent469_source_authority'] = parent_pin
        old_raw, _ = pinned_packet('parent469-manifest.json', PARENT_MANIFEST_SHA)
        candidate_raw, _ = pinned_packet('candidate-source-manifest.json', CANDIDATE_MANIFEST_SHA)
        expected = json.loads(old_raw)
        candidate_expected = json.loads(candidate_raw)
        SOURCE_MAP = candidate_expected
        original_rows, copied_before = exact_source_copy(expected)
        report['original_manifest'] = write_new(OUT/'original-source-manifest.json',old_raw)
        candidate_rows = apply_candidate_sources(expected,candidate_expected,copied_before)
        report['copied_manifest'] = write_new(OUT/'copied-source-manifest.json',candidate_raw)
        report['source_delta'] = {'changed_files':8,'new_files':1,'unchanged_files':491,
                                  'source_files':500,'Android_AIDL_adapter_source_changed':True,
                                  'Android_AIDL_adapter_engineering_ABI_compiled':False,
                                  'candidate_files':SOURCE_PINS}
        selected_tools, compiler_rows = toolchain(report, env)
        tool_rows.extend(compiler_rows)
        env.update({'PATH':str(selected_tools['cargo'].parent)+':/usr/bin:/bin',
                    'RUSTC':str(selected_tools['rustc']),'RUSTDOC':str(selected_tools['rustdoc']),
                    'RUSTDOCFLAGS':'','CARGO_ENCODED_RUSTDOCFLAGS':'',
                    'RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'',
                    'CARGO_TARGET_DIR':str(OUT/'cargo-target'),'CARGO_BUILD_JOBS':'1',
                    'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER':'/usr/bin/cc'})
        require('/home/alex/.cargo/bin' not in env['PATH'].split(':') and
                all(shutil.which(name,path=env['PATH']) == str(selected_tools[name])
                    for name in ['cargo','rustc','rustdoc']) and
                not any(name.startswith('RUSTUP') for name in env) and
                all(name not in env for name in ('LD_PRELOAD','LD_LIBRARY_PATH','RUSTC_BOOTSTRAP')),
                'fixed direct compiler tools were shadowed')
        config_paths = [CARGO_HOME/'config',CARGO_HOME/'config.toml',
                        OWN_CARGO_HOME/'config',OWN_CARGO_HOME/'config.toml']
        for directory in [COPIED]:
            for parent_directory in [directory,*directory.parents]:
                config_paths += [parent_directory/'.cargo/config',parent_directory/'.cargo/config.toml']
        config_rows = read_existing_config(config_paths)
        require(config_rows and all(row.get('absent') is True for row in config_rows),
                'unqualified Cargo configuration is present')
        report['cargo_config_inputs_before'] = config_rows
        report['build_environment'] = env
        original_lock_raw, original_lock_pin = held(COPIED/'Cargo.lock',1024*1024)
        require(original_lock_pin == candidate_rows['Cargo.lock'], 'immutable original Cargo.lock changed')
        report['original_lock'] = original_lock_pin
        registry_raw, registry_pin = pinned_packet('registry-result.json',
            'b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993')
        registry = json.loads(registry_raw)
        require(registry['state'] == 'PASS' and registry['collection_complete'] is True and
                registry['all_45_archive_and_source_matches'] is True and
                registry['authorities_unchanged_after'] is True and registry['owned_resource_gate']['pass'] is True,
                'actual existing registry qualification is incomplete')
        report['actual_registry_archive_authority'] = registry_pin
        report['phase'] = 'ACTUAL_COMPLETE_VENDOR_QUALIFICATION'
        prepared_vendor, vendor_rows = qualified_vendor_inputs(
            registry,tomllib.loads(original_lock_raw.decode()),dependency_cache,report)
        dependency_rows.update(vendor_rows)
        report['isolated_cargo_home'] = str(OWN_CARGO_HOME)
        report['shared_cargo_cache_writes'] = 0
        report['explicit_vendor_config'] = str(HERE/'prepared-vendor-config.toml')
        report['phase'] = 'LOCKED_METADATA_AND_DEPENDENCIES'
        metadata_raw = command([str(selected_tools['cargo']),'--config',str(HERE/'prepared-vendor-config.toml'),
                                'metadata','--offline','--locked',
                                '--format-version','1','--filter-platform','x86_64-unknown-linux-gnu'],
                               COPIED,env,'wayland-locked-metadata',report['commands'],60)
        held_lock_raw, held_lock_pin = held(COPIED/'Cargo.lock',1024*1024)
        require(held_lock_raw == original_lock_raw and held_lock_pin == original_lock_pin,
                'locked metadata changed the original workspace lock')
        root_id, packages, current_dependencies = selected_dependencies(
            json.loads(metadata_raw),registry,tomllib.loads(original_lock_raw.decode()),
            tomllib.loads(held_lock_raw.decode()),dependency_cache,prepared_vendor)
        dependency_rows.update(current_dependencies)
        report['dependency_inputs'] = write_new(OUT/'wayland-dependency-inputs-before.json',
                                                {'packages':packages,'files':dependency_rows})
        report['selected_dependency_package_count'] = len(packages)
        report['selected_registry_package_count'] = sum(p['kind'] == 'offline-registry' for p in packages)
        report['additional_locked_registry_first_observed_count'] = sum(
            p.get('authority_kind') == 'additional-original-lock-complete-vendor-rechecked' for p in packages)
        report['phase'] = 'NATIVE_PC_INPUTS'
        report['pkg_config_input_gate_qualified'] = False
        pc_paths, pc_before = qualify_pkg_config(report,env,tool_rows)
        report['pkg_config_input_gate_qualified'] = True
        report['tool_inputs'] = write_new(OUT/'tool-inputs-before.json',tool_rows)
        require(hash_held(COPIED/'Cargo.lock') == original_lock_pin,
                'original workspace lock changed before full crate check')
        report['phase'] = 'COMPLETE_WAYLAND_BINARY_CARGO_CHECK'
        argv = [str(selected_tools['cargo']),'--config',str(HERE/'prepared-vendor-config.toml'),
                'check','--offline','--locked','-j1',
                '-p','droidloom-wayland','--bin','droidloom-wayland',
                '--message-format=json-render-diagnostics']
        report['complete_wayland_check_argv'] = argv
        built = command(argv,COPIED,env,'complete-wayland-binary-check',report['commands'],780)
        compiled_ids, checked_target, check_outputs = qualify_wayland_compile(
            built,packages,dependency_rows,candidate_rows,root_id)
        report['actual_compiled_package_ids'] = compiled_ids
        report['actual_complete_wayland_binary_target'] = checked_target
        report['actual_check_outputs'] = check_outputs
        report['Wayland_complete_crate_typecheck_observed_success'] = True
        require(len(report['commands']) == 15 and
                all(row.get('returncode') == 0 and row['child_reaped'] and
                    row['owned_tree_cleanup_complete'] and row['pidfd_closed'] and row['output_fds_closed'] and
                    not row['timed_out'] and not row['descendants'] and
                    row.get('leader_alive_before_group_cleanup') is False and
                    row['first_error'] is None and not row['secondary_errors'] for row in report['commands']),
                'fixed 15-command sequence or strict driver cleanup differs')
        require(time.monotonic() < DEADLINE, 'Wayland check work qualification deadline exhausted')
        report['phase'] = 'FINAL_INPUT_AND_CLEANUP_GATES'
        report['state'] = 'PASS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
        report['error_detail'] = {'type':type(error).__name__,'message':str(error),
                                  'errno':getattr(error,'errno',None),'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['observed_signals'] = OBSERVED_SIGNALS
        try:
            require(CHILD_REAPER is not None and CHILD_REAPER.active, 'owned subreaper was not established')
            CHILD_REAPER.finish()
        except Exception as error:
            secondary('owned_reaper_final',error)
        report['owned_child_reaper'] = None if CHILD_REAPER is None else CHILD_REAPER.record
        for label, root, before in [
            ('original_source',BASE_SOURCE,original_rows),
            ('copied_source',COPIED,candidate_rows),
        ]:
            report[label+'_unchanged_after'] = None
            report[label+'_baseline_established'] = bool(before)
            try:
                if before:
                    unchanged = regular_tree(root) == before
                    report[label+'_unchanged_after'] = unchanged
                    require(unchanged,label+' qualified full source identity/content changed')
                if report['state'] == 'PASS':
                    require(report[label+'_unchanged_after'] is True,
                            'successful check lacks its complete source baseline')
            except Exception as error:
                secondary(label+'_after',error)
        # Recheck all successfully qualified packages even if a later package
        # made selected_dependencies fail before it could return its inventory.
        for saved in dependency_cache.values():
            dependency_rows.update(saved['files'])
        changes = []
        for path,row in dependency_rows.items():
            try:
                if hash_held(Path(path)) != row:
                    changes.append(path)
            except Exception as error:
                changes.append({'path':path,'error':repr(error)})
        try:
            for saved in dependency_cache.values():
                require(regular_tree(Path(saved['directory']),4096,64*1024*1024) == saved['rows'],
                        'prepared vendor namespace gained or lost a file')
        except Exception as error:
            changes.append({'stage':'complete_vendor_namespace_after','error':repr(error)})
        report['dependency_changes'] = changes
        if changes:
            secondary('dependency_after',RuntimeError('qualified dependency changed'))
        report['tool_changes'] = verify_resolved(tool_rows)
        if not tool_rows or report['tool_changes']:
            secondary('tool_after',RuntimeError('used tool closure missing or changed'))
        report['native_pc_inputs_unchanged_after'] = None
        try:
            if pc_before is not None:
                current = native_pc_snapshot(pc_paths)
                report['native_pc_inputs_after'] = write_new(OUT/'native-pc-inputs-after.json',current)
                report['native_pc_inputs_unchanged_after'] = current == pc_before
                require(report['native_pc_inputs_unchanged_after'],
                        'actual pkg-config default directories or metadata changed')
            if report['state'] == 'PASS':
                require(report['native_pc_inputs_unchanged_after'] is True,
                        'successful check lacks its native PC input baseline')
        except Exception as error:
            secondary('native_pc_after',error)
        try:
            report['cargo_configs_unchanged_after'] = bool(config_rows) and read_existing_config(config_paths) == config_rows
            require(report['cargo_configs_unchanged_after'], 'Cargo config set changed or was never qualified')
        except Exception as error:
            secondary('cargo_configs_after',error)
        try:
            report['check_outputs_unchanged_after'] = all(
                hash_held(Path(path),128*1024*1024) == row for path,row in check_outputs.items())
            require(report['check_outputs_unchanged_after'], 'qualified check outputs changed')
        except Exception as error:
            secondary('check_outputs_after',error)
        try:
            require(resource_fd >= 0 and resource_before is not None, 'owned resource admission not observed')
            report['owned_resource_gate'] = finish_resources(resource_fd,resource_before,report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass':False,'error':repr(error)}
            secondary('owned_resources_after',error)
        finally:
            if resource_fd >= 0:
                value, resource_fd = resource_fd, -1
                try:
                    os.close(value)
                    report['owned_resource_fd_closed'] = True
                except Exception as error:
                    report['owned_resource_fd_closed'] = False
                    secondary('owned_resource_fd_close',error)
        if time.monotonic() >= DEADLINE:
            secondary('final_work_deadline',TimeoutError('Wayland input/cleanup qualification exceeded 900 seconds'))
        compact_preserved_command_logs(report)
        report['Wayland_complete_crate_typecheck_qualified'] = (
            report['state'] == 'PASS' and report.get('Wayland_complete_crate_typecheck_observed_success') is True)
        report['finished_utc'] = utc()
        result = write_new(OUT/'result.json',report)
        resource_gate = report.get('owned_resource_gate',{})
        print(json.dumps({'state':report['state'],'phase':report['phase'],'result':result,
            'Main_actions':0,'Android_Binder_provider_compile':False,
            'ordinary_commands':len(report['commands']),'expected_ordinary_commands':15,
            'focused_tests_executed':0,'host112_controls_repeated':False,
            'lifecycle_controls':[{key:case[key] for key in ['name','passed']}
                                  for case in report.get('host_child_lifecycle_controls',[])],
            'Wayland_complete_crate_typecheck_qualified':report['Wayland_complete_crate_typecheck_qualified'],
            'Wayland_runtime_GPU_qualified':False,'native_headers_libraries_ABI_qualified':False,
            'resource_admission':report.get('resource_admission'),
            'resource_admission_qualified':report.get('resource_admission_qualified',False),
            'pkg_config_input_gate_qualified':report.get('pkg_config_input_gate_qualified',False),
            'selected_dependency_package_count':report.get('selected_dependency_package_count'),
            'additional_locked_registry_first_observed_count':report.get('additional_locked_registry_first_observed_count'),
            'owned_child_reaper':report.get('owned_child_reaper'),
            'owned_resource_fd_closed':report.get('owned_resource_fd_closed',False),
            'owned_resources':{name:resource_gate.get(name) for name in
                ['pass','memory_peak','memory_swap_peak','memory_events_delta','swap_max_observed_only']},
            'source_unchanged':{name:report.get(name) for name in
                ['original_source_unchanged_after','copied_source_unchanged_after',
                 'cargo_configs_unchanged_after','native_pc_inputs_unchanged_after']},
            'last_command':None if not report['commands'] else {name:report['commands'][-1].get(name) for name in
                ['label','argv','returncode','timed_out','first_error','stdout','stderr',
                 'stdout_complete','stderr_complete','child_reaped','owned_tree_cleanup_complete']},
            'error':report.get('error'),'secondary_errors':report['secondary_errors']}),flush=True)
    return 0 if report['state'] == 'PASS' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode':'PLAN','root':str(ROOT),'base_source':str(BASE_SOURCE),
            'requires_explicit_execute_once':True,'production_files_changed':8,'production_files_added':1,
            'source_files':500,'Main_actions':0,'Android_execution':False,
            'expected_focused_tests':0,'expected_ordinary_commands':15,'lifecycle_controls':3,
            'original_workspace_and_lock_unchanged':True,
            'actual_vendor_pins_bound':all(type(row['bytes']) is int for row in VENDOR_BINDING.values()),
            'isolated_cargo_home':str(OWN_CARGO_HOME),'network_downloads_permitted':False,
            'Wayland_full_binary_target_typecheck_required':True,
            'native_PC_layout':'only bounded actual fixed-tool default output; missing layout fails',
            'GPU_runtime_or_Android_Binder_ABI_qualification':False}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: check_wayland.py [--execute-once]')
