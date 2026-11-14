import os, json, hashlib, stat, subprocess, select, signal, time, traceback, re, shutil, tarfile
from pathlib import Path

R = Path('/data/pocket4-runtime-d7-unified538-20261113-e2a3-r1')
ARCHIVE = Path('/home/qian-qi/work/p4-runtime-d7-unified1595-transfer-e2a3-r1.tar.gz')
OLD = Path('/data/pocket4-runtime-d6-init-metadata-20261113-e2a3-r2')
PARENT = Path('/data/pocket4-audio538-security-normal-20261113-e2a3-r1')
repo = R / 'source'
Q = R / 'qualification-normal-r1'
HEAD = '273d1a2b554923b7b53e645560ddbe5999cbde9b'
TREE = 'cde7467f68d2de89f688431cafd494fed147e247'
BASE = 'fbb235628023f5fb5d9e47064a6d2884d23534bc'
UNIT = 'p4-runtime-d7-unified538-normal-e2a3-r1.service'
PREFIX = 'production_mounts::runtime_assets::tests::'
TESTS = {PREFIX + x for x in [
    'runtime_inputs_reject_other_base_or_original_system',
    'runtime_manifest_rejects_paths_aliases_and_lineage_substitution',
    'runtime_schema_rejects_boolean_integer_and_unknown_authority_fields',
    'held_init_rejects_foreign_architecture_and_overflowing_segments',
    'runtime_init_xattr_requires_complete_exact_bytes',
    'runtime_init_xattr_follows_held_descriptor_after_path_replacement',
    'runtime_init_capability_absence_rejects_present_empty_and_binary_values',
    'runtime_init_xattr_read_errors_do_not_establish_absence',
    'runtime_init_metadata_cannot_be_supplied_by_user_attributes',
]}
os.umask(0o077)
assert os.getuid() == 1000 and os.sched_getaffinity(0) == {8, 9}
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == '14f92beb-43c6-4786-839e-b57307ae8048'
cg = next(x.split(':', 2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
cgp = Path('/sys/fs/cgroup') / cg.lstrip('/')
assert cg.endswith('/' + UNIT)
assert (cgp / 'memory.max').read_text().strip() == '4294967296'
assert (cgp / 'memory.swap.max').read_text().strip() == '0'
assert (cgp / 'cpu.max').read_text().split() == ['200000', '100000']
assert not R.exists()
R.mkdir(); Q.mkdir(); (Q / 'tmp').mkdir()
report = {'schema': 'runtime-d7-unified538-actual-normal-v1', 'state': 'RUNNING',
          'head': HEAD, 'tree': TREE, 'base': BASE, 'commands': [], 'errors': [],
          'cgroup': str(cgp), 'invocation_id': os.environ.get('INVOCATION_ID'),
          'reader_pid': os.getpid(), 'started_ns': time.time_ns(),
          'Android_starts': 0, 'original_data_body_reads': 0, 'host_policy_writes': 0,
          'actual_SELinux_transition_qualified': False, 'ExecutionAdmission_constructible': False,
          'runtime_qualified': False, 'production_ready': False}

def f9(s):
    return [getattr(s, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid',
                                   'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]

def pinned(path, expected=None):
    path = Path(path)
    assert path.resolve() == path
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd); assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1
        with os.fdopen(os.dup(fd), 'rb') as f: raw = f.read()
        assert len(raw) == s.st_size and f9(s) == f9(os.fstat(fd)) == f9(path.lstat())
        result = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'identity': f9(s)}
        if expected:
            assert all(result[k] == expected[k] for k in ('bytes', 'sha256', 'identity') if k in expected), str(path)
        return raw, result
    finally: os.close(fd)

def ref(p): return pinned(p)[1]

def write_json(p, value):
    with p.open('x') as f:
        json.dump(value, f, sort_keys=True, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    return ref(p)

env = dict(os.environ, PATH='/home/qian-qi/.cargo/bin:/usr/local/bin:/usr/bin:/bin',
           CARGO_HOME=str(R / 'cargo-home'), CARGO_TARGET_DIR=str(R / 'target'),
           CARGO_BUILD_JOBS='2', CARGO_TERM_COLOR='never', TMPDIR=str(Q / 'tmp'),
           GIT_TERMINAL_PROMPT='0', GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', LC_ALL='C')

def run(name, args, limit=120, stdin=None, extra_env=None):
    op, ep = Q / (name + '.stdout'), Q / (name + '.stderr')
    begun = time.time_ns(); timed_out = False
    with op.open('xb') as out, ep.open('xb') as err:
        child = subprocess.Popen(args, cwd=repo, env=env if not extra_env else dict(env, **extra_env),
                                 stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                 stdout=out, stderr=err, start_new_session=True)
        fd = os.pidfd_open(child.pid)
        try:
            start_ticks = int(Path(f'/proc/{child.pid}/stat').read_text().rsplit(')', 1)[1].split()[19])
            try: child.communicate(input=stdin, timeout=limit)
            except subprocess.TimeoutExpired:
                timed_out = True; os.killpg(child.pid, signal.SIGTERM)
                try: child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.communicate(timeout=5)
            poll = select.poll(); poll.register(fd, select.POLLIN)
            retired = bool(poll.poll(0)); assert retired
        finally: os.close(fd)
    row = {'name': name, 'argv': args, 'pid': child.pid, 'start_ticks': start_ticks,
           'exit_code': child.returncode, 'timed_out': timed_out, 'original_pidfd_retired': retired,
           'started_ns': begun, 'ended_ns': time.time_ns(), 'stdout': ref(op), 'stderr': ref(ep)}
    report['commands'].append(row)
    print(json.dumps({'event': 'command_complete', 'name': name, 'exit_code': child.returncode}), flush=True)
    assert child.returncode == 0 and not timed_out, (name, child.returncode, timed_out)
    return op.read_text()

def git(name, *args, **kw): return run(name, ['/usr/bin/git', *args], **kw)

def snapshot(manifest):
    actual = {p.relative_to(repo).as_posix() for p in repo.rglob('*') if p.is_file() and '.git' not in p.relative_to(repo).parts}
    assert actual == set(manifest['files']) and len(actual) == 1595
    rows = {}
    for relative, wanted in manifest['files'].items():
        b, row = pinned(repo / relative, wanted)
        assert stat.S_IMODE(row['identity'][2]) == int(wanted['git_mode'], 8) & 0o777
        assert hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest() == wanted['git_blob']
        rows[relative] = row
    return rows

before_source = None
try:
    archive_raw, archive_ref = pinned(ARCHIVE, {'bytes': 962202, 'sha256': 'a429026ebf3b4dc10f7f8f70a2dd65ba756191d3884babf2f35080a22b8b51f8'})
    report['archive'] = archive_ref
    with tarfile.open(ARCHIVE, 'r:gz') as tar:
        members = tar.getmembers(); assert len(members) == 70
        seen = set()
        for member in members:
            rel = Path(member.name)
            assert member.isfile() and not rel.is_absolute() and '..' not in rel.parts and '.git' not in rel.parts
            assert str(rel) not in seen and member.mode in (0o644, 0o755)
            seen.add(str(rel)); path = R / 'inputs' / rel; path.parent.mkdir(parents=True, exist_ok=True)
            body = tar.extractfile(member).read(); assert len(body) == member.size
            with path.open('xb') as stream: stream.write(body); stream.flush(); os.fsync(stream.fileno())
            path.chmod(member.mode)
    assert ref(ARCHIVE) == archive_ref
    manifest = json.loads(pinned(R / 'inputs/CANDIDATE-MANIFEST-r1.json', {'sha256': '2f9cf9529f025cea2cbc8f1ee6fa512c8f169f9d93fbb43a5df071dbd2f88fe0'})[0])
    assert manifest['head'] == HEAD and manifest['tree'] == TREE and manifest['parent'] == BASE
    assert len(manifest['files']) == 1595 and len(manifest['changed_paths']) == 13 and len(manifest['new_paths']) == 38
    parent_manifest = json.loads(pinned(R / 'inputs/AUDIO538-PARENT-FILES.json')[0])
    d6_manifest = json.loads(pinned(R / 'inputs/D6-PARENT-FILES.json')[0])
    assert len(parent_manifest) == 1557 and len(d6_manifest) == 430
    parent_before_raw, parent_before_ref = pinned(PARENT / 'qualification-normal-r1/SOURCE-BEFORE.json', {'bytes': 993572, 'sha256': '61eb63b6ffef5bda3220edfa471e754b2da8bb33113e091c836c80b56963e02a'})
    parent_before = json.loads(parent_before_raw); assert len(parent_before) == 1557
    assert {row['relative'] for row in parent_before} == set(parent_manifest)
    parent_rows = {}
    repo.mkdir()
    for old in parent_before:
        relative = old['relative']; wanted = parent_manifest[relative]
        path = PARENT / 'recipe' / relative
        assert path == Path(old['path'])
        raw, current = pinned(path, old)
        assert current == {k: old[k] for k in current}
        assert all(current[k] == wanted[k] for k in ('bytes', 'sha256'))
        assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == wanted['git_blob'] == old['git_blob']
        assert stat.S_IMODE(current['identity'][2]) == int(wanted['git_mode'], 8) & 0o777
        dest = repo / relative; dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream: stream.write(raw); stream.flush()
        dest.chmod(stat.S_IMODE(current['identity'][2])); parent_rows[relative] = current
    git('git-init', 'init', '--initial-branch=repair/runtime-d7-unified538')
    git('parent-add', 'add', '--force', '--', '.')
    assert git('parent-tree', 'write-tree').strip() == '23c1a126efd8975156d219af22a2d858a4dd3b2b'
    assert git('parent-raw-commit', 'hash-object', '-w', '-t', 'commit', str(R / 'inputs/parent.commit')).strip() == BASE
    for relative in manifest['changed_paths'] + manifest['new_paths']:
        raw, post = pinned(R / 'inputs/post' / relative, manifest['files'][relative])
        path = repo / relative
        if relative in manifest['changed_paths']:
            assert path.read_bytes() == pinned(R / 'inputs/pre' / relative, parent_manifest[relative])[0]
        else:
            assert not path.exists() and relative not in parent_manifest
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('wb' if path.exists() else 'xb') as stream: stream.write(raw); stream.flush()
        path.chmod(int(manifest['files'][relative]['git_mode'], 8) & 0o777)
    git('candidate-add', 'add', '--force', '--', '.')
    assert git('candidate-tree', 'write-tree').strip() == TREE
    assert git('candidate-raw-commit', 'hash-object', '-w', '-t', 'commit', str(R / 'inputs/candidate.commit')).strip() == HEAD
    git('set-branch', 'update-ref', 'refs/heads/repair/runtime-d7-unified538', HEAD)
    assert git('full-parent', 'rev-parse', 'HEAD^').strip() == BASE
    assert not git('initial-status', 'status', '--porcelain')
    git('diff-check', 'diff', BASE, HEAD, '--check')
    before_source = snapshot(manifest)
    assert all(before_source[p]['sha256'] == d6_manifest[p]['sha256'] for p in manifest['selected_D6_paths'])
    assert all(before_source[p]['sha256'] == wanted['sha256'] for p, wanted in parent_manifest.items() if p not in manifest['changed_paths'])
    report['source_before'] = write_json(Q / 'SOURCE-BEFORE.json', before_source)
    report['parent_source_before'] = write_json(Q / 'PARENT-SOURCE-BEFORE.json', parent_rows)
    report['all1595_expected_composite_Git_blobs_verified'] = True
    report['unchanged_Android_tool_source_files'] = 1544
    report['selected_exact_D6_files'] = len(manifest['selected_D6_paths'])
    available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))) * 1024
    assert available >= 12 * 1024**3 and shutil.disk_usage(R).free >= 6 * 1024**3
    cache_raw, cache_ref = pinned(OLD / 'CACHE-COPY-RESULT.json', {'bytes': 247607, 'sha256': '2113b8197e2206c9ad2c3d9e1da9316f0c88db026369fe025879b13cfc946460'})
    previous = json.loads(cache_raw); assert len(previous['copied']) == 240 and previous['credential_files_read_or_copied'] == 0
    destination = R / 'cargo-home'; destination.mkdir(); copied = []
    for old in previous['copied']:
        row = old['destination']; source = Path(row['path']); relative = source.relative_to(OLD / 'cargo-home')
        assert relative.parts[0] == 'registry' and '..' not in relative.parts and not any('credential' in x.lower() for x in relative.parts)
        raw, sr = pinned(source, row); assert sr == row
        dest = destination / relative; dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream: stream.write(raw); stream.flush()
        dest.chmod(0o400); copied.append({'source': sr, 'destination': ref(dest)})
    assert all(ref(row['source']['path']) == row['source'] for row in copied)
    report['public_registry_cache_copy'] = write_json(R / 'CACHE-COPY-RESULT.json', {'source_manifest': cache_ref, 'copied': copied, 'credential_files_read_or_copied': 0, 'shared_cache_writes': 0})
    cargo = '/home/qian-qi/.cargo/bin/cargo'
    report['cargo_version'] = run('cargo-version', [cargo, '--version']).strip()
    report['rustc_version'] = run('rustc-version', ['/home/qian-qi/.cargo/bin/rustc', '--version', '--verbose'])
    assert not (R / 'target').exists()
    built = run('compile-supervisor-library', [cargo, 'test', '--locked', '--offline', '-j', '2', '-p', 'droidloom-supervisor', '--lib', '--no-run', '--message-format=json'], 1200)
    messages = [json.loads(line) for line in built.splitlines() if line]
    assert messages[-1]['reason'] == 'build-finished' and messages[-1]['success'] is True
    artifacts = [x for x in messages if x.get('reason') == 'compiler-artifact' and x['target']['name'] == 'droidloom_supervisor' and x['profile']['test'] and x.get('executable')]
    assert len(artifacts) == 1 and artifacts[0]['fresh'] is False
    binary = Path(artifacts[0]['executable']); assert binary.parent == R / 'target/debug/deps'
    report['actual_test_harness'] = ref(binary)
    catalog = run('supervisor-test-catalog', [str(binary), '--list', '--format=terse'])
    all_names = {line[:-6] for line in catalog.splitlines() if line.endswith(': test')}
    assert len(all_names) == len(catalog.splitlines()) == 310 and TESTS.issubset(all_names)
    ignored_catalog = run('supervisor-ignored-catalog', [str(binary), '--ignored', '--list', '--format=terse'])
    ignored_names = {line[:-6] for line in ignored_catalog.splitlines() if line.endswith(': test')}
    assert len(ignored_names) == len(ignored_catalog.splitlines()) and ignored_names < all_names and not TESTS.intersection(ignored_names)
    ordinary_names = all_names - ignored_names
    report['all_registered_supervisor_tests'] = sorted(all_names)
    report['privileged_ignored_tests_not_qualified'] = sorted(ignored_names)
    output = run('all-ordinary-supervisor-tests', [str(binary), '--test-threads=1', '--color', 'never'], 1200)
    passed = re.findall(r'^test (\S+) \.\.\. ok$', output, re.M)
    ignored = re.findall(r'^test (\S+) \.\.\. ignored(?:, .*)?$', output, re.M)
    assert len(passed) == len(ordinary_names) and set(passed) == ordinary_names
    assert len(ignored) == len(ignored_names) and set(ignored) == ignored_names
    terminal = f'test result: ok. {len(ordinary_names)} passed; 0 failed; {len(ignored_names)} ignored; 0 measured; 0 filtered out;'
    assert output.strip().splitlines()[-1].startswith(terminal)
    report['actual_tests_passed'] = sorted(passed)
    report['actual_ordinary_tests_passed'] = len(passed)
    report['actual_D6_runtime_input_tests_passed'] = sorted(TESTS)
    release = run('four-fresh-release-binaries', [cargo, 'build', '--locked', '--offline', '--release', '-j', '2', '-p', 'droidloom-supervisor', '-p', 'droidloom-source', '-p', 'droidloom-update', '--bins', '--message-format=json'], 1500)
    release_command = report['commands'][-1]
    rows = [json.loads(line) for line in release.splitlines() if line]
    assert rows[-1]['reason'] == 'build-finished' and rows[-1]['success'] is True
    wanted = {'droidloom-supervisor', 'droidloomd', 'droidloom-source', 'droidloom-update'}
    bins = [x for x in rows if x.get('reason') == 'compiler-artifact' and x['target']['name'] in wanted and not x['profile']['test'] and x.get('executable')]
    assert len(bins) == 4 and {x['target']['name'] for x in bins} == wanted
    (R / 'bin').mkdir(); report['release_binaries'] = {}; report['original_Cargo_aliases'] = {}
    for row in bins:
        name = row['target']['name']; source = Path(row['executable'])
        assert row['fresh'] is False and source == R / 'target/release' / name
        assert Path(row['target']['src_path']).is_relative_to(repo)
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            original = os.fstat(fd)
            assert stat.S_ISREG(original.st_mode) and original.st_nlink in (1, 2) and original.st_uid == original.st_gid == 1000
            assert original.st_mode & 0o111 and not original.st_mode & 0o6022 and 64 <= original.st_size <= 128 * 1024 * 1024
            assert release_command['started_ns'] <= original.st_mtime_ns <= release_command['ended_ns']
            assert release_command['started_ns'] <= original.st_ctime_ns <= release_command['ended_ns']
            aliases = []
            for path in (R / 'target/release').rglob('*'):
                s = path.lstat()
                if stat.S_ISREG(s.st_mode) and (s.st_dev, s.st_ino) == (original.st_dev, original.st_ino):
                    assert f9(s) == f9(original); aliases.append(path)
            assert len(aliases) == original.st_nlink and source in aliases
            assert all(p == source or p.parent == R / 'target/release/deps' for p in aliases)
            with os.fdopen(os.dup(fd), 'rb') as stream: body = stream.read()
            assert body[:6] == b'\x7fELF\x02\x01' and int.from_bytes(body[18:20], 'little') == 62 and len(body) == original.st_size
            assert f9(os.fstat(fd)) == f9(original) and all(f9(p.lstat()) == f9(original) for p in aliases)
            dest = R / 'bin' / name
            with dest.open('xb') as stream: stream.write(body); stream.flush(); os.fsync(stream.fileno())
            dest.chmod(0o555); dr = ref(dest)
            assert dr['identity'][5] == 1 and dr['identity'][1] != original.st_ino and dr['sha256'] == hashlib.sha256(body).hexdigest()
            assert f9(os.fstat(fd)) == f9(original) and all(f9(p.lstat()) == f9(original) for p in aliases)
            report['release_binaries'][name] = dr
            report['original_Cargo_aliases'][name] = {'paths': [str(p) for p in aliases], 'identity': f9(original), 'sha256': dr['sha256'], 'all_links_inside_private_target': True}
        finally: os.close(fd)
    for name in sorted(wanted):
        run('normal-help-' + name, [str(R / 'bin' / name), '--help'])
    assert snapshot(manifest) == before_source
    for relative, expected in parent_rows.items():
        assert ref(PARENT / 'recipe' / relative) == expected
    assert ref(PARENT / 'qualification-normal-r1/SOURCE-BEFORE.json') == parent_before_ref
    assert not git('final-status', 'status', '--porcelain')
    report['all1557_parent_F9_unchanged'] = True
    report['all1595_source_F9_Gitblobs_modes_preserved'] = True
    report['state'] = 'ALL_ORDINARY_RUNTIME_TESTS_AND_FOUR_FRESH_UNIFIED_RELEASE_BINARIES_PASSED'
except BaseException as error:
    report['state'] = 'FAILED'
    report['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
finally:
    if before_source is not None:
        try: report['all1595_source_F9_Gitblobs_modes_preserved'] = snapshot(manifest) == before_source
        except BaseException as error: report['source_after_error'] = str(error)
    report['finished_ns'] = time.time_ns()
    report['memory_events'] = (cgp / 'memory.events').read_text()
    report['memory_peak_bytes'] = int((cgp / 'memory.peak').read_text())
    result = write_json(Q / 'RESULT.json', report)
    print(json.dumps({'state': report['state'], 'result': result, 'actual_tests_passed': len(report.get('actual_tests_passed', [])), 'errors': report['errors']}), flush=True)
raise SystemExit(0 if report['state'] == 'ALL_ORDINARY_RUNTIME_TESTS_AND_FOUR_FRESH_UNIFIED_RELEASE_BINARIES_PASSED' else 1)
