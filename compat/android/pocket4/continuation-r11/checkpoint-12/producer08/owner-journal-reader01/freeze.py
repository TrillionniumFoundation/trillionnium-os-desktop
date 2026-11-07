"""Create-only fixed journal request. Never dispatches or invokes journalctl."""
import ast
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
OUT = WORK.with_name('owner08-journal-window01-freeze-01')
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
        'idempotency_key': 'p4-owner08-normal01-journal-window01-' + sha(source.encode())[:16]}
    OUT.mkdir()
    for name in ('collect-template.py', 'controls.py', 'freeze.py'):
        write(name, (WORK / name).read_bytes())
    write('collect.py', source)
    write('request.json', dump(request))
    write('input-binding.json', dump({'schema': 1, 'source_ast_only_cfg_changed': True,
        'six_original_evidence_helpers_ast_unchanged': True, 'request_stdin_exact': True,
        'original_kmsg_source_sha256': sha(original), 'actual_kmsg_report_bytes': len(raw),
        'actual_kmsg_report_sha256': sha(raw), 'actual_kmsg_report_included': False,
        'original_window_not_retained_in_ring': True, 'config': cfg,
        'runtime_executed': False, 'journal_read_executed': False}))
    write('local-controls.json', dump({'schema': 1, 'actual_execution': True, 'test_count': 6,
        'tool_exec_chunk_id': '4cd927', 'exit_code': 0, 'elapsed_wall_seconds': 0.310249386,
        'scope': 'PURE_RECORDS_AND_THREE_OWNED_LOCAL_PYTHON_CHILDREN_ONLY',
        'template_sha256': sha(template.encode()), 'controls_sha256': sha((WORK / 'controls.py').read_bytes()),
        'journalctl_executed': False, 'kernel_log_opened': False, 'device_executed': False,
        'cases': ['boot/transport/time rejection', 'named or PID candidate selection',
            'binary message exact raw JSON preservation', 'normal owned child exact reap',
            'timeout retains partial and reaps exact child', 'parse primary error retained through cleanup']}))
    write('README.md', '''# Owner08 persistent kernel journal: fixed retired-attempt read

The earlier exact `/dev/kmsg` read completed, but the ring no longer retained the original Owner08 interval. That absence does not establish that init emitted no error. The original runtime remains failed and the SIGHUP cause remains unknown.

This request holds and hashes the protected, root-owned, no-file-capability `/usr/bin/journalctl`, invokes only that diagnostic child through the held executable FD, and checks the same executable afterward. It requests `_TRANSPORT=kernel` and the exact original boot ID. A 40-second realtime query envelope is derived from the already observed, hash-bound original runtime file mtime. Export filtering then requires the exact original monotonic microsecond interval and a named init/reboot or recorded PID-number candidate. Realtime envelope derivation is a bounded search aid, not an independent clock calibration or proof that every relevant journal record exists.

The original runtime SHA, prepared SHA, Invocation, actor PID, state directory, boot and mtime must still match before and after. The only child is journalctl; it is reaped under a 10-second read bound, including failure. Its stdout is capped at 8 MiB, stderr at 64 KiB, and selected records at 256 KiB/256 records. Partial selected evidence and the primary failure survive timeout or malformed output. The child is never a runtime, namespace helper or Main process. No journal flush/rotation/clear, file write, chmod, runtime replay or deployment is requested.

All raw journal output belongs in Root's private evidence directory and must not be published to Git. This source packet contains no raw journal records. Six actual local controls used synthetic records and three private Python children; all passed and all children were reaped. No local journal or device operation was performed. `persistent_journal_completeness_proved` and every qualification flag remain false even if collection succeeds. Exact records may support a later causal diagnosis; a text/PID-number/time match alone does not.
''')
    files = []
    for path in sorted(OUT.iterdir()):
        body = path.read_bytes()
        files.append({'path': path.name, 'bytes': len(body), 'sha256': sha(body)})
    write('manifest.json', dump({'schema': 1, 'kind': 'owner08-fixed-journal-window-read01',
        'payload': files, 'raw_journal_included': False, 'qualification': False}))
    print(dump({'output': str(OUT), 'payload_count': len(files),
        'manifest_sha256': sha((OUT / 'manifest.json').read_bytes()),
        'request_bytes': len((OUT / 'request.json').read_bytes()),
        'request_sha256': sha((OUT / 'request.json').read_bytes()),
        'source_bytes': len(source.encode()), 'source_sha256': sha(source.encode()),
        'idempotency_key': request['idempotency_key']}))


if __name__ == '__main__':
    main()
