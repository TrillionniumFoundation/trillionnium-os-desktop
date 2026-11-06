"""Read only ownership metadata for the nine observed host Python/Java PIDs.

No argv, environment, file contents outside procfs, signals or runtime changes.
The private output is evidence for review, never a stop/kill authorization.
"""
import json
import os
from pathlib import Path

PIDS = (3190677, 3213141, 1698757, 1713125, 1613458, 1640298, 1640311, 2332057, 993255)


def identity(pid):
    raw = (Path('/proc') / str(pid) / 'stat').read_bytes()
    right = raw.rindex(b')')
    fields = raw[right + 2:].split()
    return {'pid': pid, 'comm': raw[raw.index(b'(') + 1:right].decode('utf-8', 'replace'),
            'ppid': int(fields[1]), 'start_time_ticks': fields[19].decode('ascii')}


def main():
    assert os.getuid() == os.geteuid() == 1000
    before_fds = len(os.listdir('/proc/self/fd'))
    rows = []
    for pid in PIDS:
        row = {'pid': pid, 'signals': 0}
        try:
            before = identity(pid)
            path = Path('/proc') / str(pid)
            row['proc_uid'] = path.stat().st_uid
            assert row['proc_uid'] == 1000
            row['identity_before'] = before
            for field in ('exe', 'cwd'):
                try:
                    row[field] = os.readlink(path / field)
                except OSError as error:
                    row[field] = {'unavailable': type(error).__name__}
            with (path / 'cgroup').open('rb') as handle:
                raw = handle.read(8193)
            assert len(raw) <= 8192
            row['cgroup'] = raw.decode('utf-8', 'strict')
            row['identity_after'] = identity(pid)
            row['same_process_identity'] = row['identity_after'] == before
        except (OSError, ValueError, AssertionError) as error:
            row['observation_incomplete'] = type(error).__name__
        rows.append(row)
    assert len(os.listdir('/proc/self/fd')) == before_fds
    print(json.dumps({'schema': 'pocket4-fixed-host-process-ownership-observation-v1',
                      'actual_uid': os.getuid(), 'rows': rows, 'arguments_read': False,
                      'environment_read': False, 'signals': 0, 'stop_authority': False,
                      'Main_actions': 0, 'automatic_retry': False,
                      'FDs_before': before_fds, 'FDs_after': before_fds}, sort_keys=True))


if __name__ == '__main__':
    main()
