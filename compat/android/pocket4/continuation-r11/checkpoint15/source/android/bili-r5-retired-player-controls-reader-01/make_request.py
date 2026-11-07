#!/usr/bin/env python3
"""Create one exact retained-player metadata request; never dispatch."""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
READER_SHA = '49217861fcc838fc51983ca9fac7ab80dccacf93988c65f64977e94b663cf7f2'
READER_BYTES = 19820
KEY = 'pocket4-bilibili-r5-retired-player-controls-readback-01-20261105'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-once', action='store_true'); parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.write_once:
        print(json.dumps({'state': 'PLAN_ONLY', 'source_sha256': READER_SHA, 'bytes': READER_BYTES,
                          'stable_key': KEY, 'Android_or_process_actions': 0})); return 0
    raw = (HERE / 'read_controls.py').read_bytes()
    assert len(raw) == READER_BYTES and hashlib.sha256(raw).hexdigest() == READER_SHA and args.output is not None
    wrapper = ("import sys,hashlib;raw=sys.stdin.buffer.read(32769);assert len(raw)==19820 and "
        "hashlib.sha256(raw).hexdigest()==" + repr(READER_SHA) +
        ";scope={'__name__':'fixed_retired_player_reader','__file__':'<verified-retired-player-reader>'};"
        "exec(compile(raw,'read_controls.py','exec'),scope);raise SystemExit(scope['main'](['--collect-once']))")
    request = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-c', wrapper], 'cwd': '/home/alex/work',
        'env': {'PYTHONDONTWRITEBYTECODE': '1'}, 'stdin': raw.decode('utf-8'), 'idempotency_key': KEY,
        'timeout_seconds': 30, 'cpu_quota_percent': 100, 'memory_max_bytes': 134217728, 'nice': 10}
    data = (json.dumps(request, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(data):
            count = os.write(fd, data[offset:]); assert count > 0; offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps({'state': 'EXACT_REQUEST_NOT_SUBMITTED', 'path': str(args.output), 'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(), 'stdin_sha256': READER_SHA, 'stable_key': KEY}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
