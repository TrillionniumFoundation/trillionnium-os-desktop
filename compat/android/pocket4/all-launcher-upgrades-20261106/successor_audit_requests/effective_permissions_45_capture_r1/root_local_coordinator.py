#!/usr/bin/env python3
"""Root's local claim/receipt collector. No remote, Android or UI calls."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
GATE_SHA = 'dc4fffb3f11e8428db732b96cd1925f0bdce239cdce81ff64ab369dc14c751f4'
PLAN_SHA = '802c9616b99c0c753c7a31188ab7b594e5baba39d6940d963c2c1b9bd2cdb749'
LEDGER = PROJECT / 'successor_audit_requests/actual/permissions-fixed45-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save_exact(path, raw):
    if path.exists():
        assert path.read_bytes() == raw, str(path)
    else:
        with path.open('xb') as handle:
            handle.write(raw)


def gate_source():
    raw = (HERE / 'permission_capture_gate.py').read_bytes()
    assert sha(raw) == GATE_SHA
    assert sha((HERE / 'CAPTURE_PLAN.json').read_bytes()) == PLAN_SHA
    module = types.ModuleType('exact_reviewed_permission_gate')
    module.__file__ = str(HERE / 'permission_capture_gate.py')
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def claim(number):
    gate_source()
    plan = json.loads((HERE / 'CAPTURE_PLAN.json').read_bytes())
    row = plan['batches'][number - 1]
    assert row['batch'] == number
    folder = LEDGER / f'batch-{number:02}'
    assert not folder.exists(), 'Reconcile existing submission; never replace it.'
    raw = (HERE / row['process_request']['file']).read_bytes()
    assert len(raw) == row['process_request']['bytes'] and sha(raw) == row['process_request']['sha256']
    result = subprocess.run([sys.executable, '-B', str(HERE / 'permission_capture_gate.py'), 'claim-next'],
                            capture_output=True, check=False)
    save_exact(HERE / f'root-claim-b{number:02}.stdout.original.json', result.stdout)
    save_exact(HERE / f'root-claim-b{number:02}.stderr.original.txt', result.stderr)
    decision = json.loads(result.stdout)
    assert result.returncode == 0 and not result.stderr
    assert decision['state'] == 'CLAIMED_NOT_SUBMITTED' and decision['batch'] == number
    assert Path(decision['folder']) == folder and Path(decision['process_request_file']) == HERE / row['process_request']['file']
    sys.stdout.buffer.write(raw)


def settle(number, status_name):
    assert Path(status_name).name == status_name
    folder = LEDGER / f'batch-{number:02}'
    terminal_raw = (folder / status_name).read_bytes()
    terminal = json.loads(terminal_raw)
    submitted = json.loads((folder / 'submitted-job.json').read_bytes())
    assert terminal['job_id'] == submitted['job_id'] and terminal['state'] in ('succeeded', 'failed')
    assert terminal['output_complete'] and terminal['output_durable']
    size = terminal['log_bytes']['stdout']['stored']
    assert 0 < size <= 1048576 and terminal['log_bytes']['stderr'] == {'seen': 0, 'stored': 0}
    body = bytearray()
    for offset in range(0, size, 16384):
        read = json.loads((folder / f'read-{offset}.original.txt').read_bytes())
        stream = read['stdout']; chunk = bytes.fromhex(stream['bytes_hex'])
        assert read['job_id'] == submitted['job_id'] and stream['size'] == size
        assert stream['offset'] == offset == len(body) and stream['next_offset'] == offset + len(chunk)
        assert not bytes.fromhex(read['stderr']['bytes_hex']) and read['stderr']['eof']
        body.extend(chunk)
    assert stream['eof'] and len(body) == size == terminal['log_bytes']['stdout']['seen']
    save_exact(folder / 'terminal.original.json', terminal_raw)
    save_exact(folder / 'stdout.original.jsonl', bytes(body))
    rows = [json.loads(line) for line in body.splitlines()]
    assert len(rows) == 2
    child = rows[1]['child_result']; worker = child['worker_stdout_original'].encode('utf-8')
    assert len(worker) == child['worker_stdout_bytes'] and sha(worker) == child['worker_stdout_sha256']
    save_exact(folder / 'worker.stdout.envelope.original.json', worker)
    gate = gate_source(); primitives = gate.primitives()
    artifact, artifact_raw = primitives.decode_artifact(worker)
    save_exact(folder / 'artifact.original.json', artifact_raw)
    checked = subprocess.run([sys.executable, '-B', str(HERE / 'permission_capture_gate.py'), 'status'],
                             capture_output=True, check=False)
    save_exact(folder / 'gate-status.stdout.original.json', checked.stdout)
    save_exact(folder / 'gate-status.stderr.original.txt', checked.stderr)
    decision = json.loads(checked.stdout)
    print(json.dumps({'batch': number, 'job': submitted['job_id'], 'terminal': terminal['state'],
        'exit_code': terminal['exit_code'], 'stdout_bytes': len(body), 'stdout_sha256': sha(body),
        'artifact_bytes': len(artifact_raw), 'artifact_sha256': sha(artifact_raw),
        'worker_status': artifact.get('status'), 'worker_errors': artifact.get('errors'),
        'Android_commands': len(artifact.get('android_commands', [])), 'targets': artifact.get('target_packages'),
        'gate_state': decision['state'], 'gate_error': decision.get('error'), 'gate_exit': checked.returncode,
        'next_batch': decision.get('next', {}).get('batch'), 'production_ready': False}))
    return checked.returncode


if __name__ == '__main__':
    assert len(sys.argv) in (3, 4)
    operation, number = sys.argv[1], int(sys.argv[2]); assert 1 <= number <= 13
    if operation == 'claim':
        assert len(sys.argv) == 3
        claim(number)
    else:
        assert operation == 'settle' and len(sys.argv) == 4
        raise SystemExit(settle(number, sys.argv[3]))
