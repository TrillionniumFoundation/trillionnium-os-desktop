import os, json, hashlib, stat, re, time, traceback
from pathlib import Path

R = Path('/data/pocket4-runtime-d6-init-metadata-20261113-e2a3-r2')
Q = R / 'independent-retirement-r1'
REPO = R / 'source'
BOOT = '14f92beb-43c6-4786-839e-b57307ae8048'
HEAD = '7d86a66b8d95477781519cec99e53fd0e76b6f36'
TREE = '224fdc48b1083044cdce30a09ee4ec995a48c12d'
BASE = 'b08cdd2c70c05463c3b4c892012f7426691c502b'
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
report = {'schema': 'runtime-d6-independent-composite-retirement-v1', 'state': 'RUNNING',
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
        {'bytes': 32860, 'sha256': '4e1d303664c757bd2b06cc847e0da4b408d59640e6e55c23e9ba95853640700e'})
    completion, completion_ref = get_json('completion/RESULT.json', R / 'completion-r1/RESULT.json',
        {'bytes': 12219, 'sha256': 'da7c0274f376273d06c0767e42e924e4cc8b210d1cd856f692ca331793603082'})
    assert normal['state'] == 'FAILED' and len(normal['errors']) == 1
    assert normal['errors'][0]['type'] == 'AssertionError' and 'body, sr = pinned(source)' in normal['errors'][0]['traceback']
    assert completion['state'] == 'COMPOSITE_NINE_ACTUAL_TESTS_AND_TWO_FRESH_RELEASE_BINARIES_QUALIFIED' and not completion['errors']
    assert completion['Cargo_or_tests_repeated'] is False
    assert completion['original_failed_result'] == normal_ref
    commands = normal['commands'] + completion['commands']
    assert len(normal['commands']) == 21 and len(completion['commands']) == 5
    for group, doc in [('normal', normal), ('completion', completion)]:
        assert doc['head'] == HEAD and doc['tree'] == TREE and doc['base'] == BASE
        assert doc['all430_source_F9_Gitblobs_modes_preserved'] is True
        assert doc['Android_starts'] == doc['original_data_body_reads'] == doc['host_policy_writes'] == 0
        assert all(doc[k] is False for k in ('actual_SELinux_transition_qualified', 'ExecutionAdmission_constructible', 'runtime_qualified', 'production_ready'))
        assert all(int(line.split()[1]) == 0 for line in doc['memory_events'].splitlines())
        for cmd in doc['commands']:
            assert cmd['exit_code'] == 0 and cmd['original_pidfd_retired'] is True and cmd['timed_out'] is False
            for side in ('stdout', 'stderr'):
                include(group + '/' + cmd['name'] + '.' + side, cmd[side]['path'], cmd[side])
    before, before_ref = get_json('normal/SOURCE-BEFORE.json', normal['source_before']['path'], normal['source_before'])
    c_before, c_before_ref = get_json('completion/SOURCE-BEFORE.json', completion['source_before']['path'], completion['source_before'])
    assert before == c_before and len(before) == 430
    manifest, manifest_ref = get_json('D6-SOURCE-MANIFEST-r1.json', R / 'D6-SOURCE-MANIFEST-r1.json',
        {'sha256': '5cf0a064f604d9ddb5b22a1f2551477f3eebe87a9eb2451b52a8ce5f3f8517f2'})
    actual = set()
    for path in REPO.rglob('*'):
        relative = path.relative_to(REPO)
        if '.git' in relative.parts:
            continue
        assert not path.is_symlink() and (path.is_file() or path.is_dir())
        if path.is_file():
            actual.add(relative.as_posix())
    assert actual == set(manifest['files']) == set(before)
    source_after = {}
    for relative, wanted in manifest['files'].items():
        raw, row = pinned(REPO / relative, before[relative])
        assert row['bytes'] == wanted['bytes'] and row['sha256'] == wanted['sha256']
        assert stat.S_IMODE(row['identity'][2]) == int(wanted['git_mode'], 8) & 0o777
        assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == wanted['git_blob']
        source_after[relative] = row
    assert source_after == before
    source_after_ref = save(Q / 'SOURCE-AFTER.json', source_after)
    include('independent/SOURCE-AFTER.json', Q / 'SOURCE-AFTER.json', source_after_ref)
    test_command = next(x for x in normal['commands'] if x['name'] == 'nine-runtime-input-controls')
    test_text = pinned(test_command['stdout']['path'], test_command['stdout'])[0].decode()
    test_names = re.findall(r'^test (\S+) \.\.\. ok$', test_text, re.M)
    assert len(test_names) == len(set(test_names)) == 9
    assert set(test_names) == set(normal['actual_tests_passed']) == set(completion['actual_original_tests_passed'])
    assert len(re.findall(r'^test result: ok\. 9 passed; 0 failed; 0 ignored; 0 measured; \d+ filtered out; finished in [0-9.]+s$', test_text, re.M)) == 1
    build_command = next(x for x in normal['commands'] if x['name'] == 'two-fresh-release-binaries')
    build_messages = [json.loads(line) for line in pinned(build_command['stdout']['path'], build_command['stdout'])[0].decode().splitlines() if line]
    assert build_messages[-1] == {'reason': 'build-finished', 'success': True}
    artifacts = [m for m in build_messages if m.get('reason') == 'compiler-artifact' and m.get('executable') and m['target']['name'] in {'droidloom-supervisor', 'droidloomd'}]
    assert len(artifacts) == 2 and all(a['fresh'] is False and a['profile']['test'] is False for a in artifacts)
    assert {a['target']['name'] for a in artifacts} == set(completion['release_binaries']) == {'droidloom-supervisor', 'droidloomd'}
    for name, wanted in completion['release_binaries'].items():
        raw, row = pinned(wanted['path'], wanted)
        assert Path(wanted['path']) == R / 'bin' / name and stat.S_IMODE(row['identity'][2]) == 0o555 and raw.startswith(b'\x7fELF')
        old = completion['original_Cargo_aliases'][name]
        assert old['all_links_inside_private_target'] is True and len(old['paths']) == 2
        assert all(Path(path).is_relative_to(R / 'target/release') for path in old['paths'])
        for path in old['paths']:
            old_raw, old_ref = pinned(path, {'identity': old['identity'], 'sha256': old['sha256']}, links=2)
            assert old_raw == raw and old_ref['identity'][1] != row['identity'][1]
    retirements = []
    for label, filename, expected_sha, exit_code in [
        ('normal', 'NORMAL-r1-RETIREMENT.json', 'ae770d948a07b34daa9e3f3f8719533af6a6d70607d02f3c5e0f6f62b14c417b', 1),
        ('completion', 'COMPLETION-r1-RETIREMENT.json', '70a80ad1c37e023cc009d02e92faae34920b843069b53660f8384c57a567da85', 0)]:
        doc, row = get_json(label + '/OWNED-UNIT-RETIREMENT.json', R / filename, {'bytes': 315, 'sha256': expected_sha})
        assert doc['exit_code'] == exit_code and doc['original_pidfd_retired'] is True and doc['cgroup_absent'] is True
        assert set(doc['unit_show'].splitlines()) == {'MainPID=0', 'ControlGroup=', 'LoadState=not-found', 'ActiveState=inactive'}
        retirements.append(doc)
    pids = {x['pid'] for x in commands} | {normal['reader_pid'], completion['reader_pid']} | {x['systemd_run_pid'] for x in retirements}
    groups = {normal['cgroup'], completion['cgroup']}
    h_proofs = {}
    for label, jid, digest, nonce, code, at, outbytes, errbytes in [
        ('normal', '1a1d722f93f-392-a00', 'cd7b1a9b335be93e6b7e64fa1c73c02158b352bcdcbf497fcb57f79a01073308', '0b851510596cc2303a02a41e18ffbc82', 1, 1794610868759, 2733, 305),
        ('completion', '1a1d72a3008-392-a0b', '0d87d8cf796c8412e41e20ab65332652d5da0f2dc02893a723904f83726138cb', '5d3edd5edd4fb2944af583de1d1e0cf9', 0, 1794611232307, 1090, 295)]:
        directory = Path('/home/qian-qi/.local/state/hepta-runtime-mac-worker/jobs') / jid
        docs = {}
        h_proofs[label] = {}
        for name in ('request', 'started', 'exit'):
            docs[name], h_proofs[label][name] = get_json('durable/' + label + '-' + name + '.json', directory / (name + '.json'))
            assert docs[name]['job_id'] == jid and docs[name]['launch_nonce'] == nonce
        request, started, terminal = (docs[x] for x in ('request', 'started', 'exit'))
        assert request['request_digest'] == request['request_fingerprint'] == digest
        assert request['terminal_publication_protocol'] == terminal['terminal_publication_protocol'] == 1
        assert started['supervisor_uid'] == 1000 and started['supervisor_identity']['kind'] == 'proc_start_ticks'
        assert started['supervisor_identity']['value'].startswith(BOOT + ':')
        assert terminal['exit_code'] == code and terminal['at_unix_ms'] == at
        assert terminal['cancelled'] is False and terminal['timed_out'] is False
        assert terminal['output_complete'] is True and terminal['output_durable'] is True
        for side, count in [('stdout', outbytes), ('stderr', errbytes)]:
            assert terminal['log_bytes'][side] == {'seen': count, 'stored': count}
            assert terminal['log_errors'][side] is None and terminal['log_synced'][side] is True and terminal['log_truncated'][side] is False
        pids.add(started['supervisor_pid'])
        for prefix in ('user.slice/user-1000.slice/user@1000.service/app.slice', 'system.slice'):
            groups.add(str(Path('/sys/fs/cgroup') / prefix / ('hepta-runtime-job-' + jid + '.service')))
    for pid in sorted(pids):
        no_pid(pid)
    assert all(not os.path.lexists(group) for group in groups)
    old = Path('/data/pocket4-runtime-d6-init-metadata-20261113-e2a3-r1')
    old_failure, _ = get_json('preflight-failure/RESULT.json', old / 'qualification-normal-r1/RESULT.json',
        {'bytes': 20564, 'sha256': '8cca934c88ec47fa29ecea34194a50225e531e44c80ec1837ee3ed4e1fad3bca'})
    assert old_failure['state'] == 'FAILED' and len(old_failure['commands']) == 14
    get_json('preflight-failure/INDEPENDENT-RETIREMENT.json', old / 'INDEPENDENT-RETIREMENT-r1.json',
        {'bytes': 672, 'sha256': 'edf1eb88b530de6d12ba3a961a9f5a4337ac5916b99d769413162f414e564e9e'})
    for cmd in old_failure['commands']:
        for side in ('stdout', 'stderr'):
            include('preflight-failure/' + cmd['name'] + '.' + side, cmd[side]['path'], cmd[side])
    for label, script in [('normal-worker-r2.py', '/home/qian-qi/work/p4-runtime-d6-normal-worker-e2a3-r2.py'),
                          ('normal-launch-r2.py', '/home/qian-qi/work/p4-runtime-d6-normal-launch-e2a3-r2.py'),
                          ('completion-worker-r1.py', '/home/qian-qi/work/p4-runtime-d6-completion-worker-e2a3-r1.py'),
                          ('completion-launch-r1.py', '/home/qian-qi/work/p4-runtime-d6-completion-launch-e2a3-r1.py'),
                          ('independent-retirement-r1.py', __file__)]:
        include('controllers/' + label, script)
    for path, wanted in refs.items():
        pinned(path, wanted)
    for relative, wanted in source_after.items():
        pinned(REPO / relative, wanted)
    for wanted in completion['release_binaries'].values():
        pinned(wanted['path'], wanted)
    report.update({'state': 'NINE_ACTUAL_TESTS_TWO_FRESH_RELEASES_AND_430_SOURCE_FILES_INDEPENDENTLY_RETIRED',
                   'actual_commands': 26, 'actual_distinct_tests_passed': 9,
                   'actual_test_names': sorted(test_names), 'original_PIDs_fresh_ESRCH': sorted(pids),
                   'cgroups_absent': sorted(groups), 'all430_F9_Gitblobs_modes_unchanged': True,
                   'all52_command_log_F9_and_whole_SHA256_verified': True,
                   'fresh_single_link_0555_release_binaries': completion['release_binaries'],
                   'durable_H_envelopes': h_proofs, 'original_failed_normal_result_preserved': normal_ref,
                   'completion_result': completion_ref, 'source_after': source_after_ref,
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
        manifest_ref = save(Q / 'PUBLIC-PACKET-MANIFEST.json', {'schema': 'runtime-d6-original-public-evidence-packet-v1', 'members': packet})
    else:
        manifest_ref = None
    print(json.dumps({'state': report['state'], 'result': result, 'packet_manifest': manifest_ref, 'errors': report['errors']}), flush=True)
raise SystemExit(1 if report['state'] == 'FAILED' else 0)
