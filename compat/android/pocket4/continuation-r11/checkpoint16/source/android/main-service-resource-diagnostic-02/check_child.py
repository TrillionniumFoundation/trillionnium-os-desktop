#!/usr/bin/env python3
"""Local owned-child checks only; executable/argv/deadline are explicit seams."""
import contextlib
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shlex
import signal
import subprocess
import time
import types

HERE = Path(__file__).resolve().parent
SOURCE_SHA = '2a23f28c9cb76f5029f4d4a86402946894c3c909dccc8070008220513d2eb0ce'
raw = (HERE / 'read_main_service.py').read_bytes()
assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA
module = runpy.run_path(str(HERE / 'read_main_service.py'), run_name='local_readonly_diagnostic_check')
call = module['systemctl_read']
scope = call.__globals__
fixture = {'Id': 'droidloomd.service', 'ActiveState': 'active', 'SubState': 'running',
           'MainPID': '3588022', 'InvocationID': '67cdc2375f394012ad9d7f39b0d77426',
           'ControlGroup': '/system.slice/droidloomd.service', 'TasksMax': '6144', 'TasksCurrent': '1',
           'FragmentPath': '/fixture/not-read.service', 'DropInPaths': '', 'UnitFileState': 'enabled',
           'NRestarts': '0'}
text = ''.join(key + '=' + fixture[key] + '\n' for key in scope['PROPERTIES'])
cases = [('complete-owned-child', "printf '%s' " + shlex.quote(text), 1.0, None, False),
         ('stdout-bound', 'exec /usr/bin/head -c 17000 /dev/zero', 1.0, 'SYSTEMCTL_STREAM_BOUND:stdout', False),
         ('owned-child-timeout', 'exec /usr/bin/sleep 2', 0.1, 'SYSTEMCTL_COMMAND_DEADLINE', False),
         ('signal-error-still-waits', 'exec /usr/bin/sleep 2', 0.1, 'SYSTEMCTL_COMMAND_DEADLINE', True)]
rows = []
for name, code, seconds, reason, inject_signal_error in cases:
    scope['SYSTEMCTL'] = '/usr/bin/dash'
    scope['COMMAND_SECONDS'] = seconds
    actual_argv = ['/usr/bin/dash', '-c', code]

    def routed(argv, **kwargs):
        assert argv[1:4] == ['--system', 'show', '--no-pager'] and argv[-1] == 'droidloomd.service'
        return subprocess.Popen(actual_argv, **kwargs)

    def kill_then_error(fd, number):
        signal.pidfd_send_signal(fd, number)
        raise ProcessLookupError(errno.ESRCH, 'explicit post-signal error seam')

    scope['subprocess'] = types.SimpleNamespace(Popen=routed, DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE)
    scope['signal'] = types.SimpleNamespace(SIGKILL=signal.SIGKILL,
        pidfd_send_signal=kill_then_error if inject_signal_error else signal.pidfd_send_signal)
    before = set(os.listdir('/proc/self/fd'))
    record = {}
    started = time.monotonic()
    ok = call(record, started + 5)
    elapsed = time.monotonic() - started
    after = set(os.listdir('/proc/self/fd'))
    row = dict(case=name, actual_local_child_argv=actual_argv, result=record,
               elapsed_seconds=elapsed, all_owned_local_fds_restored=before == after)
    rows.append(row)
    (HERE / 'final-control-progress.json').write_text(json.dumps(rows, sort_keys=True, indent=2) + '\n')
    assert before == after
    assert record['child_reaped'] and record['child_pidfd_exit_observed'] and record['tool_unchanged']
    if reason is None:
        assert ok and record['properties'] == fixture and record['output_complete']
    else:
        assert not ok and record['error']['message'] == reason
    if inject_signal_error:
        assert not record['cleanup_complete']
        assert len(record['secondary_errors']) == 1
        assert record['secondary_errors'][0]['phase'] == 'signal_exact_systemctl_child'
        assert record['secondary_errors'][0]['errno'] == errno.ESRCH
    else:
        assert record['cleanup_complete'] and not record['secondary_errors']
    row['ok_as_expected'] = True
module = runpy.run_path(str(HERE / 'read_main_service.py'), run_name='source_default_plan')
output = io.StringIO()
with contextlib.redirect_stdout(output):
    assert module['main']([]) == 0
(HERE / 'default-plan.stdout.json').write_text(output.getvalue())
result = dict(schema=1, source_bytes=len(raw), source_sha256=SOURCE_SHA, cases=rows,
              scope='Actual production systemctl_read body; explicit local executable/argv/deadline/signal-error seams; actual pipes/pidfd/signal/wait. Synthetic properties are not Main observations.',
              Main_or_Pocket4_read=False, collector_collect_invoked=False, commands_submitted_to_Hepta=0)
encoded = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
with (HERE / 'local-child-controls.json').open('xb') as stream:
    stream.write(encoded)
print(json.dumps(dict(cases_passed=len(rows), bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest(),
                      source_sha256=SOURCE_SHA, Main_or_Hepta_calls=0)))
