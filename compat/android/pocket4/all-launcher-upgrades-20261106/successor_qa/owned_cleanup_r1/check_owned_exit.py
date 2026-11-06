#!/usr/bin/env python3
"""Two real local child exits; no simulated Android identity or cleanup claim."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent / 'ffi_bootstrap_probe_r1/probe_ffi_bootstrap.py'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    assert hashlib.sha256(PROBE.read_bytes()).hexdigest() == 'c7fc2c4a9397d861e27f257e3e0788cd76f7867f006d1b873b2916303b35ce82'
    probe = load(PROBE, 'original_local_owned_child_control')
    worker = load(HERE / 'cleanup_owned_task_once.py', 'new_cleanup_definitions_only')
    before = probe.census()
    cases = []
    for code in (0, 1):
        body = 'import sys\nassert sys.stdin.buffer.read(1)==b"R"\nprint("LOCAL_OWNED_CHILD")\nsys.exit(%d)\n' % code
        life, stdout, stderr = probe.run_owned_child([sys.executable, '-I', '-B', '-c', body], seconds=5)
        assert stdout == b'LOCAL_OWNED_CHILD\n' and stderr == b'' and life['returncode'] == code
        try:
            worker.require_owned_exit(life, stderr)
            accepted = True
        except RuntimeError as failure:
            assert str(failure) == 'NORMAL_ORIGINAL_CHILD_LIFETIME_REQUIRED'
            accepted = False
        assert accepted is (code == 0)
        assert life['pidfd_acquired'] and life['pidfd_exit_observed'] and life['pidfd_closed']
        assert life['parent_descriptors_restored'] and life['owned_child_sigkill_count'] == 0
        assert probe.same_descriptors(before, probe.census())
        cases.append({'name': 'normal_zero_exit' if code == 0 else 'nonzero_exit_rejected',
                      'accepted': accepted, 'actual_owned_child_lifecycle': life})
    print(json.dumps({'schema': 'pocket4-original-cleanup-local-owned-exit-controls-v1', 'ok': True,
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'cases': cases,
        'whole_process_descriptor_identities_unchanged': probe.same_descriptors(before, probe.census()),
        'Main_operations': 0, 'remote_operations': 0, 'Android_cleanup_executed': False,
        'worker_sha256': hashlib.sha256((HERE / 'cleanup_owned_task_once.py').read_bytes()).hexdigest()},
        sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
