#!/usr/bin/env python3
"""Stage frozen recovery sources and run only the read-only preflight.

Coordinator reviewed every listed durable terminal and all three agent drains.
This program has no restart or App mutation invocation. Its fresh drain is for
this preflight only; a later lifecycle operation needs another reviewed drain.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import zlib

ROOT = Path('/home/alex/work/pocket4-cell-recovery-preflight-20261106-r1')
MANIFEST_SHA = 'b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f'
CLI_SOURCE = Path('/home/alex/work/droidloom-m579-app-lifecycle-20261014/runtime/droidloom-supervisor/src/bin/droidloomctl.rs')
CLI_SOURCE_SHA = '19a9e75d0deb0836fb9d125850600004a4a15be1b1ce8519fb8ca40e2165708d'
OLD_FLOW = '/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1'
STAGING = '/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o400)
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode() + b'\n'


def main():
    assert os.geteuid() == 0
    os.umask(0o077)
    encoded = sys.stdin.buffer.read(900001)
    assert len(encoded) <= 900000
    packet = json.loads(encoded)
    assert set(packet) == {'files', 'source_names', 'evidence_names', 'plan'}
    assert len(packet['files']) <= 32
    for parent in reversed(ROOT.parents):
        assert stat.S_ISDIR(parent.lstat().st_mode)
    ROOT.mkdir(mode=0o700)
    sources = ROOT / 'source'
    sources.mkdir(mode=0o700)
    receipts = []
    for name, item in packet['files'].items():
        assert name and '/' not in name and name not in ('.', '..')
        raw = item['text'].encode()
        assert len(raw) == item['bytes'] and digest(raw) == item['sha256']
        target = sources / name if name in packet['source_names'] else ROOT / name
        pin = write_new(target, raw)
        if name in packet['evidence_names']:
            value = json.loads(raw)
            assert value['state'] in ('succeeded', 'failed') and value['terminal_publication_confirmed'] is True
            assert value['output_durable'] is True and value['output_complete'] is True
            receipts.append(pin)
    assert digest((sources / 'SOURCE_PINS.json').read_bytes()) == MANIFEST_SHA
    manifest = json.loads((sources / 'SOURCE_PINS.json').read_bytes())
    assert set(packet['source_names']) == set(manifest['files']) | {'SOURCE_PINS.json'}
    for name, pin in manifest['files'].items():
        raw = (sources / name).read_bytes()
        assert len(raw) == pin['bytes'] and digest(raw) == pin['sha256']
    unknown = packet['plan']['unknown_evidence']
    for pin in unknown:
        raw = Path(pin['path']).read_bytes()
        assert len(raw) == pin['bytes'] and digest(raw) == pin['sha256']
        receipts.append(pin)
    locks = []
    for directory in (OLD_FLOW, STAGING + '/com.lianjia.beike-bound-install-r1',
                      STAGING + '/com.lianjia.beike-bound-install-r2'):
        path = directory + '/flow.lock'
        value = os.stat(path, follow_symlinks=False)
        assert stat.S_ISREG(value.st_mode) and value.st_uid == 0 and value.st_nlink == 1
        locks.append({'path': path, 'identity': {'st_dev': value.st_dev, 'st_ino': value.st_ino}})
    drain = {'schema': 'pocket4-owned-worker-drain-v1',
             'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'reviewed_monotonic_ns': time.monotonic_ns(),
             'unresolved_start_attempts': [], 'workers': [], 'flow_locks': locks,
             'source_receipts': receipts,
             'review_scope': 'all-known-pocket4-UI-install-observer-restart-jobs'}
    plan = packet['plan']
    plan['targets'] = {'path': str(ROOT / 'targets.json'), 'sha256': digest((ROOT / 'targets.json').read_bytes())}
    plan['drain'] = write_new(ROOT / 'drain.json', dump(drain))
    plan['output_root'] = '/home/alex/work/pocket4-cell-successor-20261106-r1'
    plan_pin = write_new(ROOT / 'plan.json', dump(plan))
    # Read exact deployed-source candidate and CLI help without issuing a lifecycle request.
    raw = CLI_SOURCE.read_bytes()
    assert len(raw) == 20413 and digest(raw) == CLI_SOURCE_SHA
    source_pin = write_new(ROOT / 'actual-m579-droidloomctl.rs', raw)
    help_rows = []
    for tail in (['--help'], ['restart', '--help']):
        argv = ['/usr/bin/sudo', '-n', '-u', '#1000', '--', '/usr/bin/env',
                'XDG_RUNTIME_DIR=/run/user/1000', 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
                '/usr/bin/droidloomctl', *tail]
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
        assert len(done.stdout) + len(done.stderr) <= 32768
        help_rows.append({'argv': argv, 'returncode': done.returncode,
                          'stdout': done.stdout.decode(), 'stderr': done.stderr.decode()})
    source_readback = {'source': source_pin, 'content': raw.decode(), 'help': help_rows}
    body = dump(source_readback)
    write_new(ROOT / 'actual-cli-source-and-help.json', body)
    print(json.dumps({'kind': 'actual_cli_source_and_help', 'bytes': len(body),
                      'sha256': digest(body), 'zlib_base64': base64.b64encode(zlib.compress(body)).decode()}), flush=True)
    argv = [sys.executable, '-B', '-I', str(sources / 'successor_runtime.py'), 'preflight',
            '--plan', str(ROOT / 'plan.json'), '--plan-sha256', plan_pin['sha256'],
            '--source-manifest-sha256', MANIFEST_SHA]
    done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
    assert len(done.stdout) + len(done.stderr) <= 262144
    write_new(ROOT / 'preflight.stdout', done.stdout)
    write_new(ROOT / 'preflight.stderr', done.stderr)
    print(json.dumps({'kind': 'readonly_preflight', 'returncode': done.returncode,
                      'plan': plan_pin, 'stdout': done.stdout.decode(), 'stderr': done.stderr.decode(),
                      'restarts': 0, 'installs': 0, 'UI_actions': 0}), flush=True)
    return done.returncode


if __name__ == '__main__':
    raise SystemExit(main())
