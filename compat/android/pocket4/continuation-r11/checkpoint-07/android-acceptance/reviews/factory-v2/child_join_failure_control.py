#!/usr/bin/env python3
"""Actual controller.Child with one own bounded child; no namespace/service."""
import importlib.util
import json
import os
from pathlib import Path
import hashlib
import signal

source = Path('/workspace/scratch/94990735b266/native-new-env-01/factory-host-fixture-01/controller.py')
spec = importlib.util.spec_from_file_location('factory_controller_review_only', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

def snapshot_fds():
    # os.listdir closes its own enumerating descriptor before it returns.
    return {int(name) for name in os.listdir('/proc/self/fd')
            if (Path('/proc/self/fd') / name).exists()}

def child_body(parent_fd):
    remaining = b'Q' * 65537
    while remaining:
        written = os.write(1, remaining)
        if written <= 0:
            raise RuntimeError('owned bounded write failed')
        remaining = remaining[written:]
    return 0

before = snapshot_fds()
child = module.spawn('owned-review-output-overflow', child_body)
first_error = retirement = None
try:
    try:
        child.join(3)
    except BaseException as error:
        first_error = {'type': type(error).__name__, 'message': str(error)}
    try:
        retirement = child.retire()
    except BaseException as error:
        retirement = {'error': type(error).__name__, 'message': str(error)}
finally:
    if child.returncode is None:
        if module.alive(child.pidfd):
            signal.pidfd_send_signal(child.pidfd, signal.SIGKILL)
        waited, status = os.waitpid(child.pid, 0)
        assert waited == child.pid
        child.returncode = os.waitstatus_to_exitcode(status)
    for fd in (child.stdout, child.stderr, child.pidfd):
        try:
            os.close(fd)
        except OSError:
            pass
after = snapshot_fds()
retained = retirement.get('stdout', '') if isinstance(retirement, dict) else ''
report = {
    'source_sha256': source_hash,
    'scope': 'actual spawn/Child; one own child writes 65,537 bytes; no namespace/service/Main',
    'first_error': first_error,
    'retirement': retirement,
    'bytes_originally_written': 65537,
    'bytes_retained_after_retire': len(retained.encode()),
    'original_output_lost': bool(first_error and len(retained.encode()) < 65536),
    'child_reaped': child.returncode is not None,
    'fd_table_restored': before == after,
}
print(json.dumps(report, sort_keys=True))
raise SystemExit(0 if report['original_output_lost'] and report['child_reaped'] and report['fd_table_restored'] else 1)
