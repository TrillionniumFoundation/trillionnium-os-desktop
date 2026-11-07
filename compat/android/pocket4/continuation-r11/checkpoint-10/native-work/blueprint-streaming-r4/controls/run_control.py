#!/usr/bin/env python3
"""Owned, offline, complete-package old/fixed Blueprint writer controls."""
import ctypes
import datetime
import difflib
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

SOURCE = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
ROOT = Path('/home/alex/work/pocket4-blueprint-streaming-controls-04-20261105')
HERE = ROOT / 'source'
OUT = ROOT / 'attempt01'
GOROOT = SOURCE / 'prebuilts/go/linux-x86'
GO = GOROOT / 'bin/go'
PREIMAGE = 'e2b7bf50848ba9f9ac7078dae87c6b2e13ce7019ba997c71f90a04e602f1a9d4'
CANDIDATE = '1559969a55db1b682401c01264dd8ba96fa224781c3af277f0996a5050f7c9fa'
PATCH_SHA = '9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307'
TEST_SHA = '6e07b46d2fec835897fdc2bb444571d09ef41d01148d8c3940398e716d8594ef'
SOURCE_PINS = {
    'build/blueprint/context.go': PREIMAGE,
    'build/blueprint/ninja_writer.go': '6b4b26e0d998ec64477634e0afdccb1d636fc852a4546d090748fe3e96654c0e',
    'build/blueprint/bootstrap/command.go': 'bb681356afa58932692866c41086e122509dc65d36edabc22c7bb154be5c8f38',
    'build/blueprint/context_test.go': 'cd013c8f248e93d5502a749d68abaa0a52f9d304936ceb4ccc486a0c0bb50eb9',
    'build/blueprint/module_ctx.go': 'e20bd048d8f78a7149c37a8a9e2d519d0189b6e9629783c72b2dd8554bec7f8f',
    'build/blueprint/ninja_defs.go': '858de97881c570cdb184135857eb95908feca09f8e3194ae5defa51de8acc1c2',
    'build/blueprint/go.mod': 'c940e025c622a4628e79b45719357e37825acd6b39db338adedd52072f907ba1',
    'build/soong/cmd/soong_build/main.go': 'fa57972b284800393e78b9b452604c28576350e63ce0d8f3dd1fd93b66fb9faf',
}
OLD = '\t\t\t\terr = c.writeIncrementalModules(batchModules, writer)\n'
NEW = ('\t\t\t\tif c.GetIncrementalEnabled() {\n'
       '\t\t\t\t\terr = c.writeIncrementalModules(batchModules, writer)\n'
       '\t\t\t\t} else {\n'
       '\t\t\t\t\t// Uncached modules can be streamed without retaining whole-module buffers.\n'
       '\t\t\t\t\terr = c.writeModuleAction(batchModules, writer)\n'
       '\t\t\t\t}\n')
DEADLINE = None
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

# Exact fixture links observed without following them in source-layout-read01.
# Production .go files and every unlisted symlink remain rejected.
SOURCE_TEST_LINKS = {'pathtools/testdata/dangling/a/a/f': '../../f', 'pathtools/testdata/dangling/b': 'a', 'pathtools/testdata/dangling/c': 'a/a', 'pathtools/testdata/dangling/d': 'c', 'pathtools/testdata/dangling/dangling': 'missing', 'pathtools/testdata/dangling/e': 'a/a/a', 'pathtools/testdata/symlinks/b': 'a', 'pathtools/testdata/symlinks/c': 'a/a', 'pathtools/testdata/symlinks/d': 'c', 'pathtools/testdata/symlinks/e': 'a/a/a'}

def held_link(path, expected_target):
    before = path.lstat()
    require(stat.S_ISLNK(before.st_mode), 'expected test fixture link missing: '+str(path))
    target = os.readlink(path)
    require(target == expected_target, 'test fixture link target changed: '+str(path))
    require(identity(before) == identity(path.lstat()), 'test fixture link changed during read: '+str(path))
    raw = target.encode('utf-8')
    return {'path':str(path), 'bytes':len(raw), 'sha256':sha(raw), 'identity':identity(before),
            'kind':'symlink', 'target':target}

def copied_link(path, row):
    observed = held_link(path, row['target'])
    require(observed['sha256'] == row['sha256'], 'copied test fixture link differs: '+str(path))
    return observed

def write_link(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(row['target'], path)
    copied_link(path, row)

def copy_source_tree(source, destination):
    real_directory(source)
    key = str(source.relative_to(SOURCE))
    require(key in ['build/blueprint','external/pogreb'], 'unexpected source tree: '+str(source))
    expected_links = SOURCE_TEST_LINKS if key == 'build/blueprint' else {}
    observed_links = set()
    rows = []
    total = 0
    destination.mkdir(parents=True)
    def take_link(path):
        relative = str(path.relative_to(source))
        require(relative in expected_links, 'unlisted source symlink rejected: '+str(path))
        row = held_link(path, expected_links[relative])
        require(len(rows) < 4096, 'fixed source-tree inventory bound exceeded')
        row['relative'] = relative
        write_link(destination/relative, row)
        rows.append(row)
        observed_links.add(relative)
    for directory, dirs, files in os.walk(source, followlinks=False):
        descend = []
        for name in sorted(d for d in dirs if d != '.git'):
            path = Path(directory)/name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                take_link(path)
            else:
                require(stat.S_ISDIR(mode), 'source directory changed type: '+str(path))
                descend.append(name)
        dirs[:] = descend
        for name in sorted(files):
            if name == '.git':
                continue
            path = Path(directory)/name
            relative = str(path.relative_to(source))
            if stat.S_ISLNK(path.lstat().st_mode):
                take_link(path)
                continue
            require(relative not in expected_links, 'expected test fixture link became regular: '+str(path))
            data, row = held(path)
            total += len(data)
            require(len(rows) < 4096 and total <= 64*1024*1024, 'fixed source-tree inventory bound exceeded')
            write_new(destination/relative, data)
            row['relative'] = relative
            rows.append(row)
    require(rows and observed_links == set(expected_links), 'source test fixture link set differs: '+str(source))
    return rows

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

def dependency_files(raw):
    decoder = json.JSONDecoder()
    text = raw.decode()
    index = 0
    paths = set()
    package_count = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index == len(text):
            break
        item, index = decoder.raw_decode(text, index)
        package_count += 1
        require(not item.get('Error') and not item.get('DepsErrors') and not item.get('Incomplete'), 'incomplete Go dependency graph')
        directory = Path(item['Dir']) if item.get('Dir') else None
        for field in ['GoFiles','CgoFiles','CFiles','CXXFiles','MFiles','HFiles','FFiles','SFiles','SwigFiles','SwigCXXFiles','SysoFiles','EmbedFiles','TestGoFiles','XTestGoFiles','TestEmbedFiles','XTestEmbedFiles']:
            for name in item.get(field, []):
                path = Path(name)
                if not path.is_absolute():
                    require(directory is not None, 'relative dependency has no directory')
                    path = directory/path
                require(path.is_relative_to(OUT) or path.is_relative_to(GOROOT), 'dependency escaped owned source and fixed GoRoot: '+str(path))
                paths.add(path)
    require(0 < package_count <= 1024 and len(paths) <= 8192, 'dependency inventory bound exceeded')
    return sorted(paths), package_count

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


def execute():
    global DEADLINE
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'ordinary operator UID 1000 required')
    require(Path(__file__).absolute() == HERE/'run_control.py', 'exact staged controller path required')
    real_directory(HERE)
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'owned cleanup requires pidfd APIs')
    require(not OUT.exists() and not OUT.is_symlink(), 'create-only attempt already exists')
    fixture, fixture_pin = held(HERE/'owned_streaming_test.go')
    patch, patch_pin = held(HERE/'0009-blueprint-stream-uncached-module-actions.patch')
    require(sha(fixture) == TEST_SHA and sha(patch) == PATCH_SHA, 'staged source pin mismatch')
    authority_rows = []
    for relative, wanted in SOURCE_PINS.items():
        data, row = held(SOURCE/relative)
        require(sha(data) == wanted, 'actual source pin mismatch: '+relative)
        authority_rows.append(row)
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    DEADLINE = time.monotonic()+550
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(36, 1, 0, 0, 0) == 0, 'cannot establish owned child subreaper')
    require(not children(), 'unexpected initial children')
    allowed_cpus = sorted(os.sched_getaffinity(0))
    require(len(allowed_cpus) >= 3, 'cannot reserve two logical CPUs for this compiler control')
    selected_cpus = [allowed_cpus[-1]]
    os.sched_setaffinity(0, selected_cpus)
    report = {'schema': 1, 'scope': 'complete Blueprint production package with only the new owned test file',
              'started_utc': utc(), 'state': 'RUNNING', 'Main_actions': 0,
              'Main_identity_observed': False, 'full_engine_build': False,
              'fixture': fixture_pin, 'patch': patch_pin, 'commands': [],
              'allowed_cpus_before': allowed_cpus, 'selected_cpus': selected_cpus}
    def interrupted(number, frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned controller interrupted by signal %d' % number)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    input_rows = []
    tool_rows = []
    resource_fd = -1
    resource_before = None
    try:
        resource_fd, resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        version, version_pin = held(GOROOT/'VERSION', 1024)
        require(version.startswith(b'go1.25.4\n'), 'observed GoRoot version changed')
        tool_rows.append(version_pin)
        for relative in ['bin/go', 'pkg/tool/linux_amd64/compile', 'pkg/tool/linux_amd64/link', 'pkg/tool/linux_amd64/asm']:
            _, row = held(GOROOT/relative, 64*1024*1024)
            tool_rows.append(row)
        pre = OUT/'preimage/gopath/src/github.com/google/blueprint'
        cand = OUT/'candidate/gopath/src/github.com/google/blueprint'
        dep = OUT/'dependencies/gopath/src/github.com/akrylysov/pogreb'
        blueprint_rows = copy_source_tree(SOURCE/'build/blueprint', pre)
        pogreb_rows = copy_source_tree(SOURCE/'external/pogreb', dep)
        input_rows = blueprint_rows+pogreb_rows
        for row in authority_rows:
            _, current = held(Path(row['path']))
            require(current == row, 'authority source changed before compilation')
        for row in blueprint_rows:
            if row.get('kind') == 'symlink':
                copied_link(pre/row['relative'], row)
                write_link(cand/row['relative'], row)
            else:
                data, _ = held(pre/row['relative'])
                require(sha(data) == row['sha256'], 'copied preimage changed: '+row['relative'])
                write_new(cand/row['relative'], data)
        original_tests = []
        for path in sorted(pre.glob('*_test.go')):
            data, row = held(path)
            original_tests.append({'name':path.name, 'bytes':len(data), 'sha256':row['sha256']})
            for arm, directory in [('preimage',pre), ('candidate',cand)]:
                destination = OUT/'original-package-tests'/arm/path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                require(not destination.exists(), 'test reference already exists')
                (directory/path.name).rename(destination)
        report['original_tests_preserved_outside_compiled_package'] = original_tests
        report['upstream_test_suite_executed'] = False
        original, _ = held(pre/'context.go')
        require(sha(original) == PREIMAGE and original.decode().count(OLD) == 1, 'unexpected writer preimage')
        fixed = original.decode().replace(OLD, NEW).encode()
        require(sha(fixed) == CANDIDATE, 'candidate bytes do not match frozen source')
        actual_patch = ''.join(difflib.unified_diff(original.decode().splitlines(True), fixed.decode().splitlines(True), fromfile='a/context.go', tofile='b/context.go')).encode()
        require(actual_patch == patch, 'candidate delta differs from frozen patch')
        (cand/'context.go').write_bytes(fixed)
        for directory in [pre, cand]:
            write_new(directory/'owned_streaming_test.go', fixture)
        report['source_inventory'] = write_new(OUT/'copied-source-manifest.json', {'files': input_rows, 'blueprint_count':len(blueprint_rows), 'pogreb_count':len(pogreb_rows)})
        (OUT/'go-cache').mkdir()
        (OUT/'go-tmp').mkdir()
        results = {}
        for arm, directory in [('preimage', pre), ('candidate', cand)]:
            armroot = OUT/arm
            artifacts = armroot/'artifacts'
            artifacts.mkdir()
            env = {'PATH': str(GOROOT/'bin')+':/usr/bin:/bin', 'GOROOT':str(GOROOT),
                   'GOPATH':str(armroot/'gopath')+':'+str(OUT/'dependencies/gopath'),
                   'GO111MODULE':'off', 'GOWORK':'off', 'GOPROXY':'off', 'GOSUMDB':'off',
                   'GOTOOLCHAIN':'local', 'GOENV':'off', 'CGO_ENABLED':'0', 'GOCACHE':str(OUT/'go-cache'),
                   'GOTMPDIR':str(OUT/'go-tmp'), 'TMPDIR':str(OUT/'go-tmp'),
                   'POCKET4_WRITER_ARTIFACTS':str(artifacts), 'LC_ALL':'C', 'LANG':'C'}
            raw = command([str(GO),'list','-p=1','-deps','-test','-json','github.com/google/blueprint'], directory, env, arm+'-dependencies', report['commands'])
            paths, count = dependency_files(raw)
            before = [held(p)[1] for p in paths]
            binary = armroot/'writer-controls.test'
            command([str(GO),'test','-vet=off','-p=1','-c','-o',str(binary),'github.com/google/blueprint'], directory, env, arm+'-compile', report['commands'], 240)
            after = [held(p)[1] for p in paths]
            require(before == after, 'actual compiler source/dependency closure changed during build')
            closure = write_new(armroot/'dependency-closure.json', {'package_count':count, 'files':before})
            _, elf = held(binary, 64*1024*1024)
            stdout = command([str(binary),'-test.run','^TestPocket4Streaming','-test.timeout','90s','-test.v'], directory, env, arm+'-runtime', report['commands'], 100)
            expected_tests = {'TestPocket4Streaming'+name for name in ['WholeShardOutput','RealSerializerEquivalence','WriterErrors','ShardOpenError','AllocationControl','WholePathAllocation']}
            observed_tests = set(re.findall(r'^--- PASS: (TestPocket4Streaming[A-Za-z]+) \(', stdout.decode(), re.MULTILINE))
            require(observed_tests == expected_tests, 'required actual test functions did not all finish successfully')
            _, elf_after = held(binary, 64*1024*1024)
            require(elf == elf_after, 'test binary changed while executing')
            artifacts_rows = {}
            for file in sorted(artifacts.iterdir()):
                data, row = held(file, 16*1024*1024)
                artifacts_rows[file.name] = {'bytes':len(data), 'sha256':row['sha256']}
            require('metrics-full.json' in artifacts_rows, 'full-path measurement missing')
            for case in ['zero','one','nine','ten','eleven','mixed37','large','enabled13']:
                require(case+'.main.ninja' in artifacts_rows and case+'.shards.json' in artifacts_rows, 'required whole-output case did not run: '+case)
            metrics = json.loads((artifacts/'metrics-full.json').read_text())
            results[arm] = {'binary':elf, 'dependency_closure':closure, 'artifacts':artifacts_rows, 'metrics':metrics}
        old_files = {k:v for k,v in results['preimage']['artifacts'].items() if k != 'metrics-full.json'}
        new_files = {k:v for k,v in results['candidate']['artifacts'].items() if k != 'metrics-full.json'}
        require(old_files and old_files == new_files, 'old/fixed whole output set or bytes differ')
        old_metrics, new_metrics = results['preimage']['metrics'], results['candidate']['metrics']
        require(old_metrics['output_bytes'] == new_metrics['output_bytes'], 'full-path measurement outputs differ')
        require(old_metrics['total_alloc_delta']-new_metrics['total_alloc_delta'] >= old_metrics['output_bytes'], 'whole production path did not eliminate at least one output-sized allocation')
        report['arms'] = results
        report['whole_output_files_equal'] = len(old_files)
        report['whole_path_total_alloc_saved'] = old_metrics['total_alloc_delta']-new_metrics['total_alloc_delta']
        report['state'] = 'PASS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        report['observed_signals'] = OBSERVED_SIGNALS
        report['cleanup'] = cleanup_children()
        for group_name, rows in [('source',input_rows), ('tools',tool_rows), ('authority',authority_rows)]:
            changed = []
            for row in rows:
                try:
                    if row.get('kind') == 'symlink':
                        after = held_link(Path(row['path']), row['target'])
                        before = {k:row[k] for k in ['path','bytes','sha256','identity','kind','target']}
                    else:
                        _, after = held(Path(row['path']), 64*1024*1024)
                        before = {k:row[k] for k in ['path','bytes','sha256','identity']}
                    if after != before:
                        changed.append(row['path'])
                except Exception as error:
                    changed.append({'path':row['path'], 'error':repr(error)})
            report[group_name+'_unchanged_after'] = not changed
            report[group_name+'_changes'] = changed
            if changed:
                report['state'] = 'FAIL'
        cleanup = report['cleanup']
        if cleanup['forced_cleanup'] or cleanup['remaining'] or cleanup['errors']:
            report['state'] = 'FAIL'
        try:
            require(resource_fd >= 0 and resource_before is not None, 'owned resource admission was not observed')
            report['owned_resource_gate'] = finish_resources(resource_fd,resource_before,report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass':False,'error':repr(error)}
            report['state'] = 'FAIL'
        finally:
            if resource_fd >= 0:
                os.close(resource_fd)
        report['finished_utc'] = utc()
        result = write_new(OUT/'result.json', report)
        print(json.dumps({'state':report['state'], 'result':result, 'Main_actions':0, 'full_engine_build':False}), flush=True)
    return 0 if report['state'] == 'PASS' else 1

if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode':'PLAN', 'root':str(ROOT), 'actual_source':str(SOURCE), 'source_changes':0,
                          'requires_explicit_execute_once':True, 'whole_engine_qualification':False}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: run_control.py [--execute-once]')
