#!/usr/bin/env python3
"""Bounded operator-only reads of eleven fixed memory files. No state changes."""
import datetime
import json
import os
import signal
import time

LIMIT = 32768
FILES = (
    '/proc/meminfo',
    '/proc/pressure/memory',
    '/sys/fs/cgroup/memory.current',
    '/sys/fs/cgroup/memory.stat',
    '/sys/fs/cgroup/memory.swap.current',
    '/sys/fs/cgroup/system.slice/droidloomd.service/memory.current',
    '/sys/fs/cgroup/system.slice/droidloomd.service/memory.stat',
    '/sys/fs/cgroup/system.slice/droidloomd.service/memory.swap.current',
    '/sys/fs/cgroup/system.slice/droidloomd.service/memory.events',
    '/sys/fs/cgroup/system.slice/droidloomd.service/memory.max',
    '/sys/fs/cgroup/system.slice/droidloomd.service/memory.high',
)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def expired(signum, frame):
    raise TimeoutError('fixed readonly memory collection exceeded 20 seconds')


def main():
    if os.geteuid() == 0:
        raise RuntimeError('ordinary operator required; no sudo fallback')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(20)
    report = {'schema': 1, 'scope': 'fixed readonly memory admission diagnostic',
              'started_utc': now(), 'started_monotonic': time.monotonic(),
              'uid': os.getuid(), 'euid': os.geteuid(), 'files': [],
              'per_file_read_limit': LIMIT, 'state_changes': False,
              'process_scan': False, 'sudo_used': False}
    try:
        for path in FILES:
            row = {'path': path, 'started_utc': now()}
            descriptor = None
            data = bytearray()
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
                eof = False
                while len(data) < LIMIT:
                    part = os.read(descriptor, LIMIT - len(data))
                    if not part:
                        eof = True
                        break
                    data.extend(part)
                row.update(bytes=len(data), text=data.decode('utf-8'), complete=eof,
                           limit_reached=len(data) == LIMIT)
            except Exception as error:
                row.update(error_type=type(error).__name__, error=str(error), errno=getattr(error, 'errno', None),
                           bytes_before_error=len(data), partial_text=data.decode('utf-8', errors='replace'))
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                row['finished_utc'] = now()
                report['files'].append(row)
    finally:
        signal.alarm(0)
        report['finished_utc'] = now()
        report['elapsed_seconds'] = time.monotonic() - report['started_monotonic']
        print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
