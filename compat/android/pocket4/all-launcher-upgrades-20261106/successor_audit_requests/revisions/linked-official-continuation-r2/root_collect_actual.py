#!/usr/bin/env python3
"""Local lossless settlement of one original-ledger batch; no remote calls."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
GATE_SHA = '0befe9f69aa46608a6cec8505c1fed41cd8fca1f9045693c43a83dbb4fa00d8e'
PLAN_SHA = 'e26ff7e5c1739d2e30eab340df9072ab34a433362b9e8c869b905e25c1af18b3'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save_exact(path, raw):
    if path.exists():
        assert path.read_bytes() == raw, str(path)
    else:
        with path.open('xb') as handle:
            handle.write(raw)


def main():
    assert len(sys.argv) == 3
    number = int(sys.argv[1]); assert 6 <= number <= 13
    status_name = sys.argv[2]
    assert Path(status_name).name == status_name
    folder = PROJECT / 'successor_audit_requests/actual/batches-final-r1' / f'batch-{number:02}'
    terminal_raw = (folder / status_name).read_bytes()
    terminal = json.loads(terminal_raw)
    submitted = json.loads((folder / 'submitted-job.json').read_bytes())
    assert terminal['job_id'] == submitted['job_id']
    assert terminal['state'] in ('succeeded', 'failed')
    assert terminal['output_complete'] and terminal['output_durable']
    size = terminal['log_bytes']['stdout']['stored']; assert 0 <= size <= 1048576
    assert terminal['log_bytes']['stderr'] == {'seen': 0, 'stored': 0}
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
    child = rows[1]['child_result']
    worker = child['worker_stdout_original'].encode()
    assert len(worker) == child['worker_stdout_bytes'] and sha(worker) == child['worker_stdout_sha256']
    save_exact(folder / 'worker.stdout.envelope.original.json', worker)
    gate_raw = (HERE / 'linked_audit_gate.py').read_bytes(); assert sha(gate_raw) == GATE_SHA
    gate = types.ModuleType('exact_linked_gate'); gate.__file__ = str(HERE / 'linked_audit_gate.py')
    exec(compile(gate_raw, gate.__file__, 'exec'), gate.__dict__)
    original = gate.original_gate()
    artifact, artifact_raw = original.decode_artifact(worker)
    save_exact(folder / 'artifact.original.json', artifact_raw)
    checked = subprocess.run([sys.executable, str(HERE / 'linked_audit_gate.py'), 'status',
                              '--plan', str(HERE / 'CONTINUATION_PLAN.json'), '--plan-sha256', PLAN_SHA],
                             capture_output=True, check=False)
    save_exact(folder / 'gate-status.stdout.original.json', checked.stdout)
    save_exact(folder / 'gate-status.stderr.original.txt', checked.stderr)
    decision = json.loads(checked.stdout)
    print(json.dumps({'batch': number, 'job': submitted['job_id'], 'terminal_state': terminal['state'],
          'terminal_exit': terminal['exit_code'], 'outer_stdout_bytes': len(body), 'outer_stdout_sha256': sha(body),
          'artifact_bytes': len(artifact_raw), 'artifact_sha256': sha(artifact_raw),
          'worker_status': artifact.get('status'), 'worker_errors': artifact.get('errors'),
          'commands': len(artifact.get('commands', [])), 'apps': len(artifact.get('apps', [])),
          'APKs': sum(len(a['apks']) for a in artifact.get('apps', [])),
          'gate_exit': checked.returncode, 'gate_state': decision['state'],
          'gate_reason': decision.get('reason'), 'next_batch': decision.get('next', {}).get('batch'),
          'production_ready': False}, ensure_ascii=False))
    return checked.returncode


if __name__ == '__main__':
    raise SystemExit(main())
