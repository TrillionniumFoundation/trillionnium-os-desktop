import os, json, hashlib, stat, subprocess, select, signal, time, traceback, re, shutil, tarfile
from pathlib import Path

R = Path('/data/pocket4-runtime-d6-init-metadata-20261113-e2a3-r2')
ARCHIVE = Path('/home/qian-qi/work/p4-runtime-d6-source430-transfer-e2a3-r1.tar.gz')
OLD = Path('/data/pocket4-intentresolver-security-normal-20261113-e2a3-r3')
repo = R / 'source'
Q = R / 'completion-r1'
HEAD = '7d86a66b8d95477781519cec99e53fd0e76b6f36'
TREE = '224fdc48b1083044cdce30a09ee4ec995a48c12d'
BASE = 'b08cdd2c70c05463c3b4c892012f7426691c502b'
UNIT = 'p4-runtime-d6-init-metadata-completion-e2a3-r1.service'
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
assert (cgp / 'memory.max').read_text().strip() == '2147483648'
assert (cgp / 'memory.swap.max').read_text().strip() == '0'
assert (cgp / 'cpu.max').read_text().split() == ['200000', '100000']
assert R.is_dir() and not Q.exists()
Q.mkdir(); (Q / 'tmp').mkdir()
report = {'schema': 'runtime-d6-existing-release-copy-completion-v1', 'state': 'RUNNING',
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
    raw, prior_ref = pinned(R / 'qualification-normal-r1/RESULT.json', {'bytes': 32860, 'sha256': '4e1d303664c757bd2b06cc847e0da4b408d59640e6e55c23e9ba95853640700e'})
    prior = json.loads(raw)
    assert prior['state'] == 'FAILED' and prior['head'] == HEAD and prior['tree'] == TREE
    assert len(prior['commands']) == 21 and all(x['exit_code'] == 0 and x['original_pidfd_retired'] and not x['timed_out'] for x in prior['commands'])
    assert prior['all430_source_F9_Gitblobs_modes_preserved'] is True
    assert len(prior['errors']) == 1 and prior['errors'][0]['type'] == 'AssertionError'
    assert 'body, sr = pinned(source)' in prior['errors'][0]['traceback']
    prior_commands = {row['name']: row for row in prior['commands']}
    for row in prior['commands']:
        for side in ['stdout', 'stderr']:
            _, now_ref = pinned(row[side]['path'], row[side])
            assert now_ref == row[side]
    b, retire_ref = pinned(R / 'NORMAL-r1-RETIREMENT.json', {'bytes': 315, 'sha256': 'ae770d948a07b34daa9e3f3f8719533af6a6d70607d02f3c5e0f6f62b14c417b'})
    retired = json.loads(b)
    assert retired['exit_code'] == 1 and retired['original_pidfd_retired'] and retired['cgroup_absent']
    pids = {x['pid'] for x in prior['commands']} | {prior['reader_pid'], retired['systemd_run_pid'], 3576377}
    for pid in pids:
        try: fd = os.pidfd_open(pid)
        except ProcessLookupError: continue
        else: os.close(fd); raise AssertionError(('old candidate PID remains', pid))
    assert not Path(prior['cgroup']).exists()
    assert not [p for p in Path('/sys/fs/cgroup').rglob('*') if p.is_dir() and ('1a1d722f93f-392-a00' in p.name or p.name == 'p4-runtime-d6-init-metadata-normal-e2a3-r2.service')]
    report['original21_commands_and_tree_retired'] = True
    report['original_PIDs_fresh_ESRCH'] = sorted(pids)
    report['original_failed_result'] = prior_ref
    report['original_owned_unit_retirement'] = retire_ref
    body, manifest_ref = pinned(R / 'D6-SOURCE-MANIFEST-r1.json')
    assert manifest_ref['sha256'] == '5cf0a064f604d9ddb5b22a1f2551477f3eebe87a9eb2451b52a8ce5f3f8517f2'
    manifest = json.loads(body)
    before_source = snapshot(manifest)
    assert before_source == json.loads(pinned(prior['source_before']['path'], prior['source_before'])[0])
    report['source_before'] = write_json(Q / 'SOURCE-BEFORE.json', before_source)
    assert git('current-head', 'rev-parse', 'HEAD').strip() == HEAD
    assert git('current-tree', 'rev-parse', 'HEAD^{tree}').strip() == TREE
    assert not git('current-status', 'status', '--porcelain')
    test_log = pinned(prior_commands['nine-runtime-input-controls']['stdout']['path'])[0].decode()
    actual_tests = re.findall(r'^test (\S+) \.\.\. ok$', test_log, re.M)
    assert len(actual_tests) == 9 and set(actual_tests) == TESTS == set(prior['actual_tests_passed'])
    assert len(re.findall(r'^test result: ok\. 9 passed; 0 failed; 0 ignored; 0 measured; \d+ filtered out; finished in [0-9.]+s$', test_log, re.M)) == 1
    release_command = prior_commands['two-fresh-release-binaries']
    release_log = pinned(release_command['stdout']['path'])[0].decode()
    messages = [json.loads(line) for line in release_log.splitlines() if line]
    assert messages[-1]['reason'] == 'build-finished' and messages[-1]['success'] is True
    bins = [x for x in messages if x.get('reason') == 'compiler-artifact' and x['target']['name'] in {'droidloom-supervisor', 'droidloomd'} and not x['profile']['test'] and x.get('executable')]
    assert len(bins) == 2 and {x['target']['name'] for x in bins} == {'droidloom-supervisor', 'droidloomd'}
    assert (R / 'bin').is_dir() and not list((R / 'bin').iterdir())
    report['release_binaries'] = {}
    report['original_Cargo_aliases'] = {}
    for row in bins:
        name = row['target']['name']; source = Path(row['executable'])
        assert row['fresh'] is False and source == R / 'target/release' / name
        assert Path(row['target']['src_path']).is_relative_to(repo / 'runtime/droidloom-supervisor/src')
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            original = os.fstat(fd)
            assert stat.S_ISREG(original.st_mode) and original.st_nlink == 2 and original.st_uid == original.st_gid == 1000
            assert original.st_mode & 0o111 and not original.st_mode & 0o6022
            assert 64 <= original.st_size <= 128 * 1024 * 1024
            assert release_command['started_ns'] <= original.st_mtime_ns <= release_command['ended_ns']
            assert release_command['started_ns'] <= original.st_ctime_ns <= release_command['ended_ns']
            aliases = []
            for p in (R / 'target/release').rglob('*'):
                s = p.lstat()
                if stat.S_ISREG(s.st_mode) and (s.st_dev, s.st_ino) == (original.st_dev, original.st_ino):
                    assert f9(s) == f9(original)
                    aliases.append(p)
            assert len(aliases) == 2 and source in aliases
            assert next(p for p in aliases if p != source).parent == R / 'target/release/deps'
            with os.fdopen(os.dup(fd), 'rb') as stream: body = stream.read()
            assert body[:4] == b'\x7fELF' and len(body) == original.st_size
            assert f9(os.fstat(fd)) == f9(original) and all(f9(p.lstat()) == f9(original) for p in aliases)
            destination = R / 'bin' / name
            with destination.open('xb') as stream:
                stream.write(body); stream.flush(); os.fsync(stream.fileno())
            destination.chmod(0o555)
            dr = ref(destination)
            assert dr['identity'][5] == 1 and dr['identity'][1] != original.st_ino
            assert dr['sha256'] == hashlib.sha256(body).hexdigest() and dr['bytes'] == len(body)
            assert f9(os.fstat(fd)) == f9(original) and all(f9(p.lstat()) == f9(original) for p in aliases)
            report['release_binaries'][name] = dr
            report['original_Cargo_aliases'][name] = {'paths': [str(p) for p in aliases], 'identity': f9(original), 'sha256': dr['sha256'], 'all_links_inside_private_target': True}
        finally: os.close(fd)
    run('normal-supervisor-help', [str(R / 'bin/droidloom-supervisor'), '--help'])
    assert {name: ref(R / 'bin' / name) for name in report['release_binaries']} == report['release_binaries']
    assert snapshot(manifest) == before_source
    assert not git('final-status', 'status', '--porcelain')
    report['actual_original_tests_passed'] = sorted(actual_tests)
    report['source_before_and_after_unchanged'] = True
    report['Cargo_or_tests_repeated'] = False
    report['original_failed_report_unchanged'] = ref(R / 'qualification-normal-r1/RESULT.json') == prior_ref
    report['state'] = 'COMPOSITE_NINE_ACTUAL_TESTS_AND_TWO_FRESH_RELEASE_BINARIES_QUALIFIED'
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
    print(json.dumps({'state': report['state'], 'result': result, 'actual_original_tests_passed': len(report.get('actual_original_tests_passed', [])), 'errors': report['errors']}), flush=True)
raise SystemExit(0 if report['state'] == 'COMPOSITE_NINE_ACTUAL_TESTS_AND_TWO_FRESH_RELEASE_BINARIES_QUALIFIED' else 1)
