"""Create-only fixed journal request. Never dispatches or invokes journalctl."""
import ast
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
OUT = WORK.with_name('owner08-journal-window02-freeze-01')
OLD = WORK.with_name('owner08-kmsg-window01-freeze-01')
ACTUAL = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/private/owner08-kmsg-window01/reader-report.json')


def sha(body):
    return hashlib.sha256(body).hexdigest()


def dump(value):
    return json.dumps(value, sort_keys=True, indent=2) + '\n'


def write(name, body):
    if not isinstance(body, bytes):
        body = body.encode()
    body.decode('utf-8', 'strict')
    with (OUT / name).open('xb') as stream:
        stream.write(body)


def main():
    original = (OLD / 'collect.py').read_bytes()
    assert sha(original) == '1e43346512f28a02d15c2132dd1263035fafb99357091f04b70ce0ff106d4819'
    old_tree = ast.parse(original)
    cfg = ast.literal_eval(next(n.value for n in old_tree.body if isinstance(n, ast.Assign)
        and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'CFG'))
    raw = ACTUAL.read_bytes()
    assert len(raw) == 1767 and sha(raw) == '403d412dcf852efa0e6d48f93244dbc3488e5760a5eb103be05b923728133d09'
    actual = json.loads(raw)
    assert actual['config'] == cfg and actual['collection_complete'] is True
    assert actual['qualification'] is False and actual['scan']['selected_records'] == []
    assert actual['scan']['window_evidence_complete'] is False
    assert actual['runtime_before'] == actual['runtime_after']
    mtime = actual['runtime_after']['identity'][8]
    assert mtime == 1793852567075924112
    cfg.update({'runtime_mtime_ns': mtime, 'query_since_realtime_seconds': mtime // 1_000_000_000 - 35,
                'query_until_realtime_seconds': mtime // 1_000_000_000 + 5})
    template = (WORK / 'collect-template.py').read_text()
    marker = 'CFG = None  # Fixed only from already verified original evidence.'
    assert template.count(marker) == 1
    source = template.replace(marker, 'CFG = ' + repr(cfg))
    a, b = ast.parse(template), ast.parse(source)
    for tree in (a, b):
        item = next(n for n in tree.body if isinstance(n, ast.Assign)
            and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'CFG')
        if tree is b:
            assert ast.literal_eval(item.value) == cfg
        item.value = ast.Constant(None)
    assert ast.dump(a) == ast.dump(b)
    helpers = ('need', 'sha', 'stamp', 'directory', 'read_runtime', 'boot_id')
    old_helpers = {n.name: ast.dump(n) for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name in helpers}
    new_helpers = {n.name: ast.dump(n) for n in b.body if isinstance(n, ast.FunctionDef) and n.name in helpers}
    assert old_helpers == new_helpers
    request = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-'], 'cwd': '/', 'stdin': source,
        'cpu_quota_percent': 100, 'memory_max_bytes': 134217728, 'nice': 10, 'timeout_seconds': 30,
        'idempotency_key': 'p4-owner08-normal01-journal-window02-' + sha(source.encode())[:16]}
    prior_path = ACTUAL.parent.parent / 'owner08-journal-window01/reader-report.json'
    prior_raw = prior_path.read_bytes()
    assert len(prior_raw) == 339003 and sha(prior_raw) == 'd48c9463dae071b4337e3189b1d6a8d626e4caab5e46f4935bbc6d813dac4b89'
    prior = json.loads(prior_raw)
    assert prior['collection_complete'] is False and prior['journal']['child_reaped'] is True
    assert len(prior['journal']['selected_records']) == 256
    assert prior['journal']['first_error'] == "RuntimeError('selected journal evidence bound reached')"
    OUT.mkdir()
    for name in ('collect-template.py', 'collect-template-attempt01.py', 'controls.py', 'freeze.py', 'local-controls-attempt01.json'):
        write(name, (WORK / name).read_bytes())
    write('collect.py', source)
    write('request.json', dump(request))
    write('input-binding.json', dump({'schema': 1, 'source_ast_only_cfg_changed': True,
        'six_original_evidence_helpers_ast_unchanged': True, 'request_stdin_exact': True,
        'original_kmsg_source_sha256': sha(original), 'actual_kmsg_report_bytes': len(raw),
        'actual_kmsg_report_sha256': sha(raw), 'actual_kmsg_report_included': False,
        'original_window_not_retained_in_ring': True, 'prior_journal_report_bytes': len(prior_raw),
        'prior_journal_report_sha256': sha(prior_raw), 'prior_actual_export_bound_failure_preserved': True,
        'prior_raw_journal_included': False, 'config': cfg,
        'runtime_executed': False, 'journal_read_executed': False}))
    write('local-controls.json', dump({'schema': 1, 'actual_execution': True, 'test_count': 8,
        'tool_exec_chunk_id': 'e4e045', 'exit_code': 0, 'elapsed_wall_seconds': 0.330525855,
        'scope': 'PURE_RECORDS_AND_THREE_OWNED_LOCAL_PYTHON_CHILDREN_ONLY',
        'template_sha256': sha(template.encode()), 'controls_sha256': sha((WORK / 'controls.py').read_bytes()),
        'journalctl_executed': False, 'kernel_log_opened': False, 'device_executed': False,
        'cases': ['boot/transport/time rejection', 'named or PID candidate selection',
            'binary message exact raw JSON preservation', 'normal owned child exact reap',
            'timeout retains partial and reaps exact child', 'parse primary error retained through cleanup',
            'Main control/routine parse traffic excluded', 'source and journal receipt clocks stay separate']}))
    import difflib
    old_template = WORK.with_name('owner08-journal-window01-freeze-01').joinpath('collect-template.py').read_text()
    write('source.diff', ''.join(difflib.unified_diff(old_template.splitlines(True), template.splitlines(True), fromfile='journal01/collect-template.py', tofile='journal02/collect-template.py')))
    write('README.md', """# Owner08 journal diagnostic 02: narrow error context, unchanged bounds

The original journal01 attempt is retained as FAILED at the 256-record export limit, with its partial evidence and exact child reap. This new read excludes routine init parsing and unrelated control messages. It keeps only the original received-monotonic time interval plus recorded-PID-number or named init/processgroup/APEX startup, cgroup error and reboot context. The realtime query envelope, held original runtime/boot/state binding, journalctl executable checks, all I/O limits and child cleanup are unchanged.

Journal receipt time and source/kernel monotonic/boottime fields are recorded separately. The observed roughly 29.1-second difference has not been calibrated. No timestamp or SYSLOG_IDENTIFIER/PID-number match establishes init birth or generation ownership. The candidate bootstrap failure must not be reported as an attributed Owner08 cause without independent evidence.

All original limits remain: 40-second realtime search aid, exact original 3.511-second receive-monotonic export interval, 10-second child limit, 8-MiB stdout, 64-KiB stderr, 256 selected records/256 KiB, CPU1/128MiB outer request. Persistent journal completeness and every qualification flag remain false. No runtime, namespace, deployment or Main mutation is requested.

Eight actual local controls passed, including three private Python children with normal, timeout and malformed-output cleanup. A first local control correctly exposed a missing `could not` error token; the original candidate source and failed control receipt are preserved, then only that token was added and the full eight controls passed. No local journal or device operation was performed. The raw original or newly collected journal belongs only in Root's private evidence; this packet contains none.
""")
    files = []
    for path in sorted(OUT.iterdir()):
        body = path.read_bytes()
        files.append({'path': path.name, 'bytes': len(body), 'sha256': sha(body)})
    write('manifest.json', dump({'schema': 1, 'kind': 'owner08-fixed-journal-window-read02',
        'payload': files, 'raw_journal_included': False, 'qualification': False}))
    print(dump({'output': str(OUT), 'payload_count': len(files),
        'manifest_sha256': sha((OUT / 'manifest.json').read_bytes()),
        'request_bytes': len((OUT / 'request.json').read_bytes()),
        'request_sha256': sha((OUT / 'request.json').read_bytes()),
        'source_bytes': len(source.encode()), 'source_sha256': sha(source.encode()),
        'idempotency_key': request['idempotency_key']}))


if __name__ == '__main__':
    main()
