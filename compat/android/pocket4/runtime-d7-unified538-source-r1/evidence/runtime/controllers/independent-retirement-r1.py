import os, json, hashlib, stat, re, time, traceback
from pathlib import Path

R = Path('/data/pocket4-runtime-d7-unified538-20261113-e2a3-r1')
Q = R / 'independent-retirement-r1'
PARENT = Path('/data/pocket4-audio538-security-normal-20261113-e2a3-r1')
REPO = R / 'source'
BOOT = '14f92beb-43c6-4786-839e-b57307ae8048'
HEAD = '273d1a2b554923b7b53e645560ddbe5999cbde9b'
TREE = 'cde7467f68d2de89f688431cafd494fed147e247'
BASE = 'fbb235628023f5fb5d9e47064a6d2884d23534bc'
os.umask(0o077)
assert os.getuid() == os.getgid() == 1000
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
assert {8, 9}.issubset(os.sched_getaffinity(0))
os.sched_setaffinity(0, {8, 9})
assert not Q.exists()
Q.mkdir()
CG = Path('/sys/fs/cgroup') / next(x.split(':', 2)[2].lstrip('/') for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
assert CG.name.startswith('hepta-runtime-job-')
assert (CG / 'memory.max').read_text().strip() == '268435456'
assert (CG / 'cpu.max').read_text().split() == ['100000', '100000']
report = {'schema': 'runtime-d7-independent-composite-retirement-v1', 'state': 'RUNNING',
          'boot_id': BOOT, 'reader_pid': os.getpid(), 'reader_cgroup': str(CG),
          'head': HEAD, 'tree': TREE, 'base': BASE, 'started_ns': time.time_ns(),
          'Android_starts': 0, 'Cargo_or_tests_repeated': False, 'original_data_body_reads': 0,
          'host_policy_writes': 0, 'actual_SELinux_transition_qualified': False,
          'ExecutionAdmission_constructible': False, 'runtime_qualified': False,
          'production_ready': False, 'errors': []}
packet = {}
refs = {}

def f9(s):
    return [getattr(s, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]

def pinned(path, expected=None, links=1):
    path = Path(path)
    assert path.is_absolute() and path.resolve() == path
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        assert stat.S_ISREG(s.st_mode) and s.st_nlink == links and s.st_size <= 32 * 1024 * 1024
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read()
        assert len(raw) == s.st_size and f9(s) == f9(os.fstat(fd)) == f9(path.lstat())
        row = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'identity': f9(s)}
        if expected:
            assert all(row[k] == v for k, v in expected.items()), ('mismatch', str(path))
        return raw, row
    finally:
        os.close(fd)

def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    return pinned(path)[1]

def include(name, path, expected=None):
    assert name not in packet and not name.startswith('/') and '..' not in Path(name).parts
    raw, row = pinned(path, expected)
    packet[name] = row
    refs[str(path)] = row
    return raw, row

def get_json(name, path, expected=None):
    raw, row = include(name, path, expected)
    return json.loads(raw), row

def no_pid(pid):
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    else:
        os.close(fd)
        raise AssertionError(('PID still exists', pid))

try:
    normal, normal_ref = get_json('normal/RESULT.json', R / 'qualification-normal-r1/RESULT.json',
        {'bytes': 97958, 'sha256': 'b7a18e0f8b37d855f95885ee53cf78b0a8c02446cb2713187e459dfd2a1318c3'})
    assert normal['state'] == 'ALL_ORDINARY_RUNTIME_TESTS_AND_FOUR_FRESH_UNIFIED_RELEASE_BINARIES_PASSED' and not normal['errors']
    assert normal['head'] == HEAD and normal['tree'] == TREE and normal['base'] == BASE
    assert normal['all1557_parent_F9_unchanged'] is True and normal['all1595_source_F9_Gitblobs_modes_preserved'] is True
    assert normal['Android_starts'] == normal['host_policy_writes'] == normal['original_data_body_reads'] == 0
    assert all(normal[key] is False for key in ('actual_SELinux_transition_qualified', 'ExecutionAdmission_constructible', 'runtime_qualified', 'production_ready'))
    assert all(int(line.split()[1]) == 0 for line in normal['memory_events'].splitlines())
    assert len(normal['commands']) == 23
    for cmd in normal['commands']:
        assert cmd['exit_code'] == 0 and cmd['timed_out'] is False and cmd['original_pidfd_retired'] is True
        for side in ('stdout', 'stderr'):
            include('normal/' + cmd['name'] + '.' + side, cmd[side]['path'], cmd[side])
    manifest, manifest_ref = get_json('CANDIDATE-MANIFEST-r1.json', R / 'inputs/CANDIDATE-MANIFEST-r1.json',
        {'sha256': '2f9cf9529f025cea2cbc8f1ee6fa512c8f169f9d93fbb43a5df071dbd2f88fe0'})
    parent_manifest, _ = get_json('AUDIO538-PARENT-FILES.json', R / 'inputs/AUDIO538-PARENT-FILES.json')
    d6_manifest, _ = get_json('D6-PARENT-FILES.json', R / 'inputs/D6-PARENT-FILES.json')
    before, source_ref = get_json('normal/SOURCE-BEFORE.json', normal['source_before']['path'], normal['source_before'])
    parent_before, parent_source_ref = get_json('normal/PARENT-SOURCE-BEFORE.json', normal['parent_source_before']['path'], normal['parent_source_before'])
    assert len(before) == len(manifest['files']) == 1595 and len(parent_before) == len(parent_manifest) == 1557 and len(d6_manifest) == 430
    actual = set()
    for path in REPO.rglob('*'):
        relative = path.relative_to(REPO)
        if '.git' in relative.parts: continue
        assert not path.is_symlink() and (path.is_dir() or path.is_file())
        if path.is_file(): actual.add(relative.as_posix())
    assert actual == set(before) == set(manifest['files'])
    for relative, wanted in manifest['files'].items():
        raw, row = pinned(REPO / relative, before[relative])
        assert row['bytes'] == wanted['bytes'] and row['sha256'] == wanted['sha256']
        assert stat.S_IMODE(row['identity'][2]) == int(wanted['git_mode'], 8) & 0o777
        assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == wanted['git_blob']
    assert len(manifest['selected_D6_paths']) == 66 and len(manifest['changed_paths']) == 13 and len(manifest['new_paths']) == 38
    expected = dict(parent_manifest)
    for name in manifest['selected_D6_paths']: expected[name] = d6_manifest[name]
    assert expected == manifest['files']
    for relative, wanted in parent_manifest.items():
        raw, row = pinned(PARENT / 'recipe' / relative, parent_before[relative])
        assert row['bytes'] == wanted['bytes'] and row['sha256'] == wanted['sha256']
        assert stat.S_IMODE(row['identity'][2]) == int(wanted['git_mode'], 8) & 0o777
        assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == wanted['git_blob']
    names = set(normal['all_registered_supervisor_tests']); ignored = set(normal['privileged_ignored_tests_not_qualified']); passed = set(normal['actual_tests_passed'])
    assert len(names) == 310 and len(ignored) == 21 and len(passed) == normal['actual_ordinary_tests_passed'] == 289
    assert not ignored.intersection(passed) and names == ignored | passed
    assert len(normal['actual_D6_runtime_input_tests_passed']) == 9 and set(normal['actual_D6_runtime_input_tests_passed']).issubset(passed)
    cmd = next(x for x in normal['commands'] if x['name'] == 'all-ordinary-supervisor-tests')
    test_text = pinned(cmd['stdout']['path'], cmd['stdout'])[0].decode()
    observed = re.findall(r'^test (\S+) \.\.\. ok$', test_text, re.M)
    observed_ignored = re.findall(r'^test (\S+) \.\.\. ignored(?:, .*)?$', test_text, re.M)
    assert len(observed) == 289 and set(observed) == passed and len(observed_ignored) == 21 and set(observed_ignored) == ignored
    assert test_text.strip().splitlines()[-1].startswith('test result: ok. 289 passed; 0 failed; 21 ignored; 0 measured; 0 filtered out;')
    cmd = next(x for x in normal['commands'] if x['name'] == 'four-fresh-release-binaries')
    messages = [json.loads(line) for line in pinned(cmd['stdout']['path'], cmd['stdout'])[0].decode().splitlines() if line]
    assert messages[-1] == {'reason': 'build-finished', 'success': True}
    wanted_names = {'droidloom-supervisor', 'droidloomd', 'droidloom-source', 'droidloom-update'}
    artifacts = [row for row in messages if row.get('reason') == 'compiler-artifact' and row.get('executable') and row['target']['name'] in wanted_names]
    assert len(artifacts) == 4 and {row['target']['name'] for row in artifacts} == wanted_names == set(normal['release_binaries'])
    assert all(row['fresh'] is False and row['profile']['test'] is False for row in artifacts)
    for name, wanted in normal['release_binaries'].items():
        raw, row = pinned(wanted['path'], wanted)
        assert Path(wanted['path']) == R / 'bin' / name and stat.S_IMODE(row['identity'][2]) == 0o555
        assert raw[:6] == b'\x7fELF\x02\x01' and int.from_bytes(raw[18:20], 'little') == 62
        old = normal['original_Cargo_aliases'][name]; assert old['all_links_inside_private_target'] is True
        assert len(old['paths']) == old['identity'][5] and old['identity'][5] in (1, 2)
        for path in old['paths']:
            assert Path(path).is_relative_to(R / 'target/release')
            old_raw, old_ref = pinned(path, {'identity': old['identity'], 'sha256': old['sha256']}, links=old['identity'][5])
            assert old_raw == raw and old_ref['identity'][1] != row['identity'][1]
    owned, owned_ref = get_json('normal/OWNED-UNIT-RETIREMENT.json', R / 'NORMAL-r1-RETIREMENT.json')
    assert owned['exit_code'] == 0 and owned['original_pidfd_retired'] is True and owned['cgroup_absent'] is True
    assert set(owned['unit_show'].splitlines()) == {'MainPID=0', 'ControlGroup=', 'LoadState=not-found', 'ActiveState=inactive'}
    directory = Path('/home/qian-qi/.local/state/hepta-runtime-mac-worker/jobs/1a1d74074e7-392-a34')
    docs = {}; h_refs = {}
    for name in ('request', 'started', 'exit'):
        docs[name], h_refs[name] = get_json('durable/normal-' + name + '.json', directory / (name + '.json'))
        assert docs[name]['job_id'] == '1a1d74074e7-392-a34' and docs[name]['launch_nonce'] == '150356723c7c3a41313cd4c440b13b1e'
    assert docs['request']['request_digest'] == 'e76baf64d95593b5d255d1f1a414ec46ef8b702fc2dfe7dc8e7bc44c8456d2fe'
    terminal = docs['exit']
    assert terminal['exit_code'] == 0 and terminal['at_unix_ms'] == 1794612833463
    assert terminal['output_complete'] is True and terminal['output_durable'] is True and terminal['timed_out'] is False and terminal['cancelled'] is False
    for side, size in [('stdout', 2484), ('stderr', 299)]:
        assert terminal['log_bytes'][side] == {'seen': size, 'stored': size}
        assert terminal['log_errors'][side] is None and terminal['log_synced'][side] is True and terminal['log_truncated'][side] is False
    pids = {row['pid'] for row in normal['commands']} | {normal['reader_pid'], owned['systemd_run_pid'], docs['started']['supervisor_pid']}
    assert len(pids) == 26
    for pid in pids: no_pid(pid)
    groups = [normal['cgroup']]
    for prefix in ('user.slice/user-1000.slice/user@1000.service/app.slice', 'system.slice'):
        groups.append(str(Path('/sys/fs/cgroup') / prefix / 'hepta-runtime-job-1a1d74074e7-392-a34.service'))
    assert all(not os.path.lexists(group) for group in groups)
    for label, path in [('normal-worker-r1.py', '/home/qian-qi/work/p4-runtime-d7-normal-worker-e2a3-r1.py'),
                        ('normal-launch-r1.py', '/home/qian-qi/work/p4-runtime-d7-normal-launch-e2a3-r1.py'),
                        ('independent-retirement-r1.py', __file__)]:
        include('controllers/' + label, path)
    for name in ('candidate.commit', 'parent.commit', 'CANDIDATE-r1.patch'):
        include('source/' + name, R / 'inputs' / name)
    for name, expected in refs.items(): pinned(name, expected)
    for relative, expected in before.items(): pinned(REPO / relative, expected)
    for relative, expected in parent_before.items(): pinned(PARENT / 'recipe' / relative, expected)
    for expected in normal['release_binaries'].values(): pinned(expected['path'], expected)
    report.update({'state': 'ALL289_ACTUAL_ORDINARY_TESTS_FOUR_FRESH_RELEASES_AND_ALL3152_SOURCE_FILES_INDEPENDENTLY_RETIRED',
                   'actual_commands': 23, 'actual_ordinary_tests_passed': 289, 'registered_tests': 310,
                   'actual_D6_input_tests_passed': 9, 'ignored_privileged_tests_not_qualified': sorted(ignored),
                   'original_PIDs_fresh_ESRCH': sorted(pids), 'cgroups_absent': groups,
                   'all1595_candidate_F9_Gitblobs_modes_preserved': True,
                   'all1557_parent_F9_Gitblobs_modes_preserved': True,
                   'complete_composition_proven': True, 'all46_command_logs_whole_SHA_and_F9_verified': True,
                   'independent_single_link_0555_release_binaries': normal['release_binaries'],
                   'durable_H_envelopes': h_refs, 'normal_result': normal_ref,
                   'public_packet_member_count_before_report': len(packet)})
except BaseException as error:
    report['state'] = 'FAILED'
    report['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
finally:
    report['finished_ns'] = time.time_ns()
    report['memory_peak_bytes'] = int((CG / 'memory.peak').read_text())
    report['memory_events'] = (CG / 'memory.events').read_text()
    result = save(Q / 'RESULT.json', report)
    if report['state'] != 'FAILED':
        packet['independent/RESULT.json'] = result
        manifest_ref = save(Q / 'PUBLIC-PACKET-MANIFEST.json', {'schema': 'runtime-d7-original-public-evidence-packet-v1', 'members': packet})
    else:
        manifest_ref = None
    print(json.dumps({'state': report['state'], 'result': result, 'packet_manifest': manifest_ref, 'errors': report['errors']}), flush=True)
raise SystemExit(1 if report['state'] == 'FAILED' else 0)
