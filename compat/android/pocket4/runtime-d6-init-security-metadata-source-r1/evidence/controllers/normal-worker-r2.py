import os, json, hashlib, stat, subprocess, select, signal, time, traceback, re, shutil, tarfile
from pathlib import Path

R = Path('/data/pocket4-runtime-d6-init-metadata-20261113-e2a3-r2')
ARCHIVE = Path('/home/qian-qi/work/p4-runtime-d6-source430-transfer-e2a3-r1.tar.gz')
OLD = Path('/data/pocket4-intentresolver-security-normal-20261113-e2a3-r3')
repo = R / 'source'
Q = R / 'qualification-normal-r1'
HEAD = '7d86a66b8d95477781519cec99e53fd0e76b6f36'
TREE = '224fdc48b1083044cdce30a09ee4ec995a48c12d'
BASE = 'b08cdd2c70c05463c3b4c892012f7426691c502b'
UNIT = 'p4-runtime-d6-init-metadata-normal-e2a3-r2.service'
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
report = {'schema': 'runtime-d6-init-metadata-actual-normal-v1', 'state': 'RUNNING',
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
            assert all(result[k] == expected[k] for k in ['bytes', 'sha256']), str(path)
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
    assert actual == set(manifest['files']) and len(actual) == 430
    rows = {}
    for relative, wanted in manifest['files'].items():
        b, row = pinned(repo / relative, wanted)
        assert stat.S_IMODE(row['identity'][2]) == int(wanted['git_mode'], 8) & 0o777
        assert hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest() == wanted['git_blob']
        rows[relative] = row
    return rows

before_source = None
try:
    raw, archive_ref = pinned(ARCHIVE, {'bytes': 3065470, 'sha256': '8b1f7854284b61a96f3c196d48dbbb1cbfdfc651b09a1f9495ec255b40b356b0'})
    report['archive'] = archive_ref
    with tarfile.open(ARCHIVE, 'r:gz') as tar:
        members = tar.getmembers(); assert len(members) == 438
        seen = set()
        for member in members:
            rel = Path(member.name)
            assert member.isfile() and not rel.is_absolute() and '..' not in rel.parts and '.git' not in rel.parts
            assert rel.parts and str(rel) not in seen and member.mode in (0o644, 0o755)
            seen.add(str(rel)); p = R / rel; p.parent.mkdir(parents=True, exist_ok=True)
            body = tar.extractfile(member).read(); assert len(body) == member.size
            with p.open('xb') as f: f.write(body); f.flush(); os.fsync(f.fileno())
            p.chmod(member.mode)
    assert ref(ARCHIVE) == archive_ref
    body, source_manifest_ref = pinned(R / 'D6-SOURCE-MANIFEST-r1.json')
    assert source_manifest_ref['sha256'] == '5cf0a064f604d9ddb5b22a1f2551477f3eebe87a9eb2451b52a8ce5f3f8517f2'
    manifest = json.loads(body); assert manifest['head'] == HEAD and manifest['tree'] == TREE
    original = json.loads((R / 'SOURCE-430.json').read_bytes())['sources']
    assert hashlib.sha256((R / 'D5-MANIFEST.json').read_bytes()).hexdigest() == manifest['original_D5_manifest_sha256']
    sealed = json.loads((R / 'D5-MANIFEST.json').read_bytes())['sealed']
    changed = set(manifest['changed_files'])
    assert changed == {'docs/contracts/runtime-layout-v1.md', 'runtime/droidloom-supervisor/src/production_runtime_assets.rs'}
    for relative, wanted in manifest['files'].items():
        key = 'source/' + relative
        assert original[key]['sha256'] == sealed[key]['sha256']
        p = R / 'preimages' / relative if relative in changed else repo / relative
        pinned(p, original[key])
    git('git-init', 'init', '--initial-branch=repair/runtime-d6-init-metadata')
    git('git-add', 'add', '--force', '--', '.')
    assert git('git-tree', 'write-tree').strip() == TREE
    base_entries = []
    for i, (relative, wanted) in enumerate(sorted(manifest['files'].items())):
        blob = wanted['git_blob']
        if relative in changed:
            blob = git('original-blob-' + str(i), 'hash-object', '-w', str(R / 'preimages' / relative)).strip()
        base_entries.append(wanted['git_mode'] + ' ' + blob + '\t' + relative + '\n')
    index_env = {'GIT_INDEX_FILE': str(R / 'import-index')}
    git('base-empty-index', 'read-tree', '--empty', extra_env=index_env)
    git('base-index', 'update-index', '--index-info', stdin=''.join(base_entries).encode(), extra_env=index_env)
    assert git('base-tree', 'write-tree', extra_env=index_env).strip() == manifest['import_tree']
    assert git('base-commit-object', 'hash-object', '-w', '-t', 'commit', str(R / 'IMPORT-COMMIT.raw')).strip() == BASE
    assert git('candidate-commit-object', 'hash-object', '-w', '-t', 'commit', str(R / 'CANDIDATE-COMMIT.raw')).strip() == HEAD
    git('set-branch', 'update-ref', 'refs/heads/repair/runtime-d6-init-metadata', HEAD)
    assert git('full-parent', 'rev-parse', 'HEAD^').strip() == BASE
    assert not git('initial-status', 'status', '--porcelain')
    git('diff-check', 'diff', BASE, HEAD, '--check')
    before_source = snapshot(manifest)
    report['source_before'] = write_json(Q / 'SOURCE-BEFORE.json', before_source)
    available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))) * 1024
    assert available >= 12 * 1024**3 and shutil.disk_usage(R).free >= 6 * 1024**3
    cache_raw, cache_ref = pinned(OLD / 'CACHE-COPY-RESULT.json', {'bytes': 109276, 'sha256': 'e23be42c69b0664b9134a44ad14b656abf6dd0ba8ef92a828aa380d190b30ae8'})
    previous = json.loads(cache_raw); assert len(previous['copied']) == 242 and previous['credential_files_read_or_copied'] == 0
    destination = R / 'cargo-home'; destination.mkdir(); copied = []
    skipped_metadata = []
    for row in previous['copied']:
        src = Path(row['destination']); relative = src.relative_to(OLD / 'cargo-home')
        if relative.parts[0] != 'registry':
            expected_metadata = {'INTENT.json': (78353, '62b188b2d9d95875a3a56547b51fc0fa7c6b7ed08baeebeaf66a834f94f7959e'), 'READY.json': (324808, '86901bb22ba20b73fc086be5ef07d1beb973291aea20c56b92a44ac0fef293ff')}
            assert str(relative) in expected_metadata and (row['bytes'], row['sha256']) == expected_metadata[str(relative)]
            skipped_metadata.append(str(relative))
            continue
        assert '..' not in relative.parts
        assert not any('credential' in x.lower() for x in relative.parts)
        data, sr = pinned(src, row); target = destination / relative; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as f: f.write(data); f.flush()
        target.chmod(0o400); copied.append({'source': sr, 'destination': ref(target)})
    assert len(copied) == 240 and set(skipped_metadata) == {'INTENT.json', 'READY.json'}
    assert all(ref(row['source']['path']) == row['source'] for row in copied)
    report['public_registry_cache_copy'] = write_json(R / 'CACHE-COPY-RESULT.json', {'source_manifest': cache_ref, 'copied': copied, 'credential_files_read_or_copied': 0, 'shared_cache_writes': 0, 'unneeded_historical_metadata_not_copied': skipped_metadata})
    cargo = '/home/qian-qi/.cargo/bin/cargo'
    report['cargo_version'] = run('cargo-version', [cargo, '--version']).strip()
    report['rustc_version'] = run('rustc-version', ['/home/qian-qi/.cargo/bin/rustc', '--version', '--verbose'])
    run('rustfmt-check', ['/home/qian-qi/.cargo/bin/rustfmt', '--edition', '2024', '--check', str(repo / 'runtime/droidloom-supervisor/src/production_runtime_assets.rs')])
    assert not (R / 'target').exists()
    built = run('compile-library-harness', [cargo, 'test', '--locked', '--offline', '-j', '2', '-p', 'droidloom-supervisor', '--lib', '--no-run', '--message-format=json'], 1200)
    messages = [json.loads(line) for line in built.splitlines() if line]
    assert messages[-1]['reason'] == 'build-finished' and messages[-1]['success'] is True
    artifacts = [x for x in messages if x.get('reason') == 'compiler-artifact' and x['target']['name'] == 'droidloom_supervisor' and x['profile']['test'] and x.get('executable')]
    assert len(artifacts) == 1
    binary = Path(artifacts[0]['executable']); assert binary.parent == R / 'target/debug/deps'
    report['actual_test_harness'] = ref(binary)
    catalog = run('focused-test-catalog', [str(binary), PREFIX, '--list', '--format=terse'])
    assert set(catalog.splitlines()) == {name + ': test' for name in TESTS} and len(catalog.splitlines()) == 9
    output = run('nine-runtime-input-controls', [str(binary), PREFIX, '--test-threads=1', '--color', 'never'])
    observed = re.findall(r'^test (\S+) \.\.\. ok$', output, re.M)
    assert len(observed) == 9 and set(observed) == TESTS
    terminal = re.findall(r'^test result: ok\. 9 passed; 0 failed; 0 ignored; 0 measured; (\d+) filtered out; finished in [0-9.]+s$', output, re.M)
    assert len(terminal) == 1 and output.strip().splitlines()[-1].startswith('test result: ok. 9 passed;')
    report['actual_tests_passed'] = sorted(observed); report['other_tests_not_run'] = int(terminal[0])
    release = run('two-fresh-release-binaries', [cargo, 'build', '--locked', '--offline', '--release', '-j', '2', '-p', 'droidloom-supervisor', '--bins', '--message-format=json'], 1200)
    rows = [json.loads(line) for line in release.splitlines() if line]
    assert rows[-1]['reason'] == 'build-finished' and rows[-1]['success'] is True
    wanted = {'droidloom-supervisor', 'droidloomd'}
    built_bins = [x for x in rows if x.get('reason') == 'compiler-artifact' and x['target']['name'] in wanted and not x['profile']['test'] and x.get('executable')]
    assert len(built_bins) == 2 and {x['target']['name'] for x in built_bins} == wanted
    (R / 'bin').mkdir(); report['release_binaries'] = {}
    for row in built_bins:
        source = Path(row['executable']); assert source.parent == R / 'target/release'
        body, sr = pinned(source); assert body[:4] == b'\x7fELF'
        dest = R / 'bin' / row['target']['name']
        with dest.open('xb') as f: f.write(body); f.flush(); os.fsync(f.fileno())
        dest.chmod(0o555); dr = ref(dest); assert sr['identity'][1] != dr['identity'][1]
        report['release_binaries'][row['target']['name']] = dr
    run('normal-supervisor-help', [str(R / 'bin/droidloom-supervisor'), '--help'])
    assert snapshot(manifest) == before_source
    assert not git('final-status', 'status', '--porcelain')
    report['all430_source_F9_Gitblobs_modes_preserved'] = True
    report['state'] = 'NINE_ACTUAL_RUNTIME_INPUT_CONTROLS_AND_TWO_FRESH_RELEASE_BINARIES_PASSED'
except BaseException as error:
    report['state'] = 'FAILED'
    report['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
finally:
    if before_source is not None:
        try: report['all430_source_F9_Gitblobs_modes_preserved'] = snapshot(manifest) == before_source
        except BaseException as error: report['source_after_error'] = str(error)
    report['finished_ns'] = time.time_ns()
    report['memory_events'] = (cgp / 'memory.events').read_text()
    report['memory_peak_bytes'] = int((cgp / 'memory.peak').read_text())
    result = write_json(Q / 'RESULT.json', report)
    print(json.dumps({'state': report['state'], 'result': result, 'actual_tests_passed': len(report.get('actual_tests_passed', [])), 'errors': report['errors']}), flush=True)
raise SystemExit(0 if report['state'] == 'NINE_ACTUAL_RUNTIME_INPUT_CONTROLS_AND_TWO_FRESH_RELEASE_BINARIES_PASSED' else 1)
