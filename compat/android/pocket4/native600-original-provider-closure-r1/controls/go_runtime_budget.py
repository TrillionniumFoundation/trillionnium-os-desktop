"""Validate actual Blueprint entry/exit runtime metrics from normal build logs."""
import re

PREFIX = b'DROIDLOOM_GO_BUDGET '
MARKER = re.compile(rb'DROIDLOOM_GO_BUDGET phase=(enter|leave) pid=([1-9][0-9]*) '
                    rb'gomaxprocs=([0-9]+) gomemlimit_bytes=([0-9]+) gogc_percent=([0-9]+)')


def qualify_runtime_budget(streams, observed_soong_pids):
    if (type(observed_soong_pids) is not set or not observed_soong_pids
            or any(type(pid) is not int or pid <= 0 for pid in observed_soong_pids)):
        raise ValueError('actual observed Soong PIDs are required')
    records = []
    active = {}
    complete = []
    for stream_name, lines in streams:
        for line_number, raw in enumerate(lines, 1):
            if type(raw) is not bytes or len(raw) > 1024**2:
                raise ValueError('bounded raw log line required')
            if PREFIX not in raw:
                continue
            # Ninja can forward the child's stderr into the driver's stdout.
            # Each marker must still be a complete line emitted by that child.
            match = MARKER.fullmatch(raw.rstrip(b'\r\n'))
            if match is None:
                raise ValueError('malformed actual Go runtime marker')
            phase, pid, procs, memory, gc = match.groups()
            row = {'stream': stream_name, 'line': line_number, 'phase': phase.decode(),
                   'pid': int(pid), 'gomaxprocs': int(procs),
                   'gomemlimit_bytes': int(memory), 'gogc_percent': int(gc)}
            if (row['gomaxprocs'], row['gomemlimit_bytes'], row['gogc_percent']) != (2, 5 * 1024**3, 50):
                raise ValueError('actual Go runtime budget differs from 2 / 5 GiB / 50')
            if row['phase'] == 'enter':
                if row['pid'] in active:
                    raise ValueError('duplicate unmatched Go entry marker')
                active[row['pid']] = row
            else:
                if row['pid'] not in active:
                    raise ValueError('Go exit has no preceding entry marker')
                complete.append({'enter': active.pop(row['pid']), 'leave': row})
            records.append(row)
    if not complete or active:
        raise ValueError('actual complete entry/exit budget evidence is missing')
    matched = sorted({row['enter']['pid'] for row in complete} & observed_soong_pids)
    if not matched:
        raise ValueError('runtime metrics do not belong to an observed Soong process')
    return {'schema': 'go-runtime-entry-exit-budget-v1', 'state': 'ACTUAL_ENTRY_EXIT_BUDGET_VERIFIED',
            'expected': {'gomaxprocs': 2, 'gomemlimit_bytes': 5 * 1024**3, 'gogc_percent': 50},
            'records': records, 'complete_pairs': complete, 'observed_soong_pids': sorted(observed_soong_pids),
            'matching_observed_pids': matched, 'continuous_runtime_sampling': False,
            'environment_alone_accepted': False}
