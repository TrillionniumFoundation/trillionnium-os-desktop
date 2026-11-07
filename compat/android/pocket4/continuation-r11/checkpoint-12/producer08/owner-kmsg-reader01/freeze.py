"""Create-only exact read request; does not dispatch it or open a kernel log."""
import ast
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path('/workspace/scratch/94990735b266')
WORK = Path(__file__).resolve().parent
OUT = WORK.with_name('owner08-kmsg-window01-freeze-01')
EVIDENCE = ROOT / 'root-recovery-20261104-02/evidence'
RUNTIME = EVIDENCE / 'owner08-normal01-runtime01/runtime-result.json'
PREPARED = EVIDENCE / 'owner08-normal01-prepare01/prepared.json'
PLAN = WORK.parent / 'owner08-normal01-freeze-01/plan.json'
PINS = {
    'runtime': (55292, '027848bec17ae20259e3ab2ddd8637bc820608b7f62e580c06b019f0e9ff8f16'),
    'prepared': (55138, '7972563f7c4e56c89e51424a06c01d3250f51fa1c7836ec6d67ab9a06057e0fa'),
    'plan': (66212, '9241286dcfbab3f1c45a2608c302cca7cde0c9b247db192dc6de1d89fad991ae'),
}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def read(name, path):
    body = path.read_bytes()
    assert (len(body), sha(body)) == PINS[name], name
    return json.loads(body)


def write(name, value):
    body = value if isinstance(value, bytes) else value.encode('utf-8')
    body.decode('utf-8', 'strict')
    with (OUT / name).open('xb') as stream:
        stream.write(body)


def dump(value):
    return json.dumps(value, sort_keys=True, indent=2) + '\n'


def main():
    runtime = read('runtime', RUNTIME)
    prepared = read('prepared', PREPARED)
    plan = read('plan', PLAN)
    assert runtime['attempt_nonce'] == prepared['attempt_nonce'] == plan['attempt_nonce']
    assert runtime['prepared_sha256'] == PINS['prepared'][1]
    assert runtime['exact_unit_cleanup'] == {
        'cgroup_absent': True, 'invocation': '68550c01a9fd402687a3d36d3e69c2c8',
        'original_actor_dead': True, 'unit': 'p4-owner08-normal-20261105-01.service',
        'unit_not_found': True,
    }
    lifecycle = runtime['actor_result']['latest_status']['relay_lifecycle']
    records = lifecycle['records']
    kinds = [item['detail']['event'] for item in records]
    assert len(kinds) == 15 and 'broker_active' not in kinds
    assert kinds[2:8] == ['init_hello', 'broker_ready', 'init_project_sent',
                         'init_projected_accepted', 'init_commit_sent', 'init_done_accepted']
    pids = [runtime['actor_result']['actor_pid'], lifecycle['producer']['process']['pid'],
            records[1]['detail']['process']['pid'], records[2]['detail']['init']['process']['pid'],
            records[3]['detail']['process']['pid']]
    assert pids == [1204471, 1204535, 1204577, 1204580, 1205183]
    cfg = {
        'runtime_bytes': PINS['runtime'][0], 'runtime_sha256': PINS['runtime'][1],
        'attempt_nonce': runtime['attempt_nonce'], 'prepared_sha256': PINS['prepared'][1],
        'invocation': runtime['first_unit']['InvocationID'], 'actor_pid': pids[0],
        'unit': runtime['exact_unit_cleanup']['unit'],
        'start_ns': runtime['started_monotonic_ns'], 'end_ns': runtime['finished_monotonic_ns'],
        'window_start_us': runtime['started_monotonic_ns'] // 1000,
        'window_end_us': (runtime['finished_monotonic_ns'] + 999) // 1000,
        'boot_id': plan['main']['framework_binding']['boot_id'],
        'state_leaf': 'p4-owner08-normal-20261105-01-state',
        'state_identity': [prepared['state_identity']['device'], prepared['state_identity']['inode']],
        'owned_pids': pids,
    }
    assert cfg['window_start_us'] == 878272853218 and cfg['window_end_us'] == 878276364280
    assert cfg['state_identity'] == [66306, 44179349]
    template = (WORK / 'collect-template.py').read_text()
    needle = 'CFG = None  # Filled once from the externally pinned actual runtime/preparation.'
    assert template.count(needle) == 1
    source = template.replace(needle, 'CFG = ' + repr(cfg))
    parsed = ast.parse(source)
    template_parsed = ast.parse(template)
    for tree in (parsed, template_parsed):
        matches = [x for x in tree.body if isinstance(x, ast.Assign)
                   and len(x.targets) == 1 and isinstance(x.targets[0], ast.Name) and x.targets[0].id == 'CFG']
        assert len(matches) == 1
        if tree is parsed:
            assert ast.literal_eval(matches[0].value) == cfg
        matches[0].value = ast.Constant(None)
    assert ast.dump(parsed) == ast.dump(template_parsed)
    request = {
        'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-'], 'cwd': '/',
        'stdin': source, 'cpu_quota_percent': 100, 'memory_max_bytes': 134217728,
        'nice': 10, 'timeout_seconds': 30,
        'idempotency_key': 'p4-owner08-normal01-kmsg-window01-' + sha(source.encode())[:16],
    }
    OUT.mkdir()
    for name in ('collect-template.py', 'controls.py', 'freeze.py'):
        write(name, (WORK / name).read_bytes())
    write('collect.py', source)
    write('request.json', dump(request))
    write('input-binding.json', dump({'schema': 1, 'input_pins': PINS, 'config': cfg,
        'all_inputs_exact': True, 'only_cfg_ast_changed': True,
        'request_stdin_exact': request['stdin'].encode() == source.encode(),
        'runtime_dispatched': False, 'kernel_read_executed': False}))
    write('local-controls.json', dump({'schema': 1, 'scope': 'PURE_IN_MEMORY_KERNEL_RECORD_FIXTURES',
        'actual_execution': True, 'test_count': 8, 'exit_code': 0,
        'tool_exec_chunk_id': 'd3716a', 'elapsed_wall_seconds': 0.045267748,
        'collector_sha256': sha(template.encode()), 'controls_sha256': sha((WORK / 'controls.py').read_bytes()),
        'kernel_log_opened': False, 'device_executed': False, 'runtime_qualification': False,
        'cases': ['exact window excludes outside messages', 'PID or named candidate filter',
                  'malformed and duplicate caller rejection', 'partial retention after I/O error',
                  'overrun and sequence loss incomplete', 'missing old window incomplete',
                  'non-UTF8 raw bytes preserved', 'selection bound retains earlier evidence']}))
    write('README.md', '''# Owner08 exact retired-attempt kernel-window diagnostic

This request only reads the retained kernel ring and the already existing, externally pinned runtime result. It does not create a child process, start a runtime, clear/seek/write the ring, change permissions, or retry the retired generation. The original Owner08 overall failure remains unchanged.

The original runtime SHA, prepared SHA, Invocation ID, actor PID, protected state directory identity, boot ID and exact 3.511-second monotonic interval are fixed in the request. The collector exports only records whose kernel timestamp lies in this interval and whose text names init/ueventd/apexd/reboot or whose optional caller field matches a recorded owned PID. These are diagnostic candidates. A PID number without a retained birth association, a textual match, or timestamp proximity does not establish causation. Kernel timestamp bounds are reported separately; no independent kernel/userspace clock calibration or exact-kernel source binding is claimed.

Reading is limited to 16 MiB, 65536 records and 10 seconds; exported records to 256 KiB/256 records. Every selected raw record is preserved with its SHA and base64. If the ring was overwritten, has a sequence gap, lacks the original interval, or a bound/error interrupts the scan, the corresponding completeness field remains false and already collected evidence is retained. Successful collection alone is never an Owner, LMKD, Android, or application qualification. All qualification fields remain false.

Eight actual local controls exercised in-memory records only. They did not open `/dev/kmsg`, run the collector main function, or access Pocket4. The request has not been dispatched by this agent. Root owns the one remote dispatch and any reconciliation under the same stable key.
''')
    members = []
    for path in sorted(OUT.iterdir()):
        body = path.read_bytes()
        members.append({'path': path.name, 'bytes': len(body), 'sha256': sha(body)})
    write('manifest.json', dump({'schema': 1, 'kind': 'owner08-fixed-kernel-window-read01',
                                 'payload': members, 'qualification': False}))
    print(dump({'output': str(OUT), 'payload_count': len(members),
        'manifest_sha256': sha((OUT / 'manifest.json').read_bytes()),
        'request_bytes': len((OUT / 'request.json').read_bytes()),
        'request_sha256': sha((OUT / 'request.json').read_bytes()),
        'source_bytes': len(source.encode()), 'source_sha256': sha(source.encode()),
        'idempotency_key': request['idempotency_key']}))


if __name__ == '__main__':
    main()
