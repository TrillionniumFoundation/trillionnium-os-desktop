#!/usr/bin/env python3
"""Write the exact fixed read-only diagnostic request; never submit it."""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_BYTES = 11243
SOURCE_SHA = 'c1f3aa39711ec69d905cdae1e0eee01d89289bd9a6575d39b6f5b7324e57b780'
KEY = 'pocket4-main-resource-limits-diagnostic-01-20261105'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-once', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.write_once:
        print(json.dumps(dict(state='PLAN_ONLY', source_sha256=SOURCE_SHA,
                              stable_key=KEY, submitted=False)))
        return 0
    raw = (HERE / 'read_main_limits.py').read_bytes()
    assert len(raw) == SOURCE_BYTES and hashlib.sha256(raw).hexdigest() == SOURCE_SHA
    assert args.output is not None
    wrapper = ("import hashlib,sys;raw=sys.stdin.buffer.read(16385);assert len(raw)==" + str(SOURCE_BYTES) +
               " and hashlib.sha256(raw).hexdigest()==" + repr(SOURCE_SHA) +
               ";scope={'__name__':'fixed_main_limits_reader','__file__':'<verified-fixed-main-limits-reader>'};" +
               "exec(compile(raw,'read_main_limits.py','exec'),scope);raise SystemExit(scope['main'](['--collect-once']))")
    request = dict(host='pocket4', executable='/usr/bin/sudo',
                   args=['-n', '/usr/bin/python3', '-I', '-B', '-c', wrapper],
                   cwd='/home/alex/work', env={'PYTHONDONTWRITEBYTECODE': '1'},
                   stdin=raw.decode('utf-8'), idempotency_key=KEY,
                   timeout_seconds=30, cpu_quota_percent=100,
                   memory_max_bytes=134217728, nice=10)
    data = (json.dumps(request, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(data):
            count = os.write(fd, data[offset:])
            assert count > 0
            offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps(dict(state='EXACT_REQUEST_NOT_SUBMITTED', path=str(args.output),
                          bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                          stdin_bytes=len(raw), stdin_sha256=SOURCE_SHA, stable_key=KEY)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
