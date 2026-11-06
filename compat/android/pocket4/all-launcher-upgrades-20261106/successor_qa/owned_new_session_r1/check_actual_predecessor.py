#!/usr/bin/env python3
"""Check this candidate against actual cleanup bytes; never call Main entries."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    base_path = HERE.parent / 'owned_cleanup_r1/cleanup_owned_task_once.py'
    raw = base_path.read_bytes()
    assert len(raw) == 22233 and hashlib.sha256(raw).hexdigest() == '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'
    base = load(base_path, 'actual_cleanup_definitions_only')
    worker = load(HERE / 'new_session_once.py', 'new_session_definitions_only')
    stdout = (HERE / 'cleanup.stdout.original.jsonl').read_bytes()
    terminal = (HERE / 'cleanup.terminal.original.json').read_bytes()
    proof = worker.cleanup_gate(stdout, terminal, base)
    assert proof['cleanup']['task_ids_after'] == [875, 877]
    cases = [{'name': 'actual_durable_cleanup_bytes_and_owned_exit', 'accepted': True}]
    changed = json.loads(terminal); changed['exit_code'] = 1
    broken = [(stdout, json.dumps(changed).encode(), 'different_terminal_rejected'),
              (stdout[:-1], terminal, 'incomplete_original_output_rejected')]
    for out, status, name in broken:
        try:
            worker.cleanup_gate(out, status, base)
        except RuntimeError as error:
            assert str(error) == 'ACTUAL_CLEANUP_ORIGINAL_BYTES_REQUIRED'
            cases.append({'name': name, 'accepted': False, 'reason': str(error)})
        else:
            raise AssertionError(name)
    print(json.dumps({'schema': 'pocket4-new-session-actual-predecessor-local-check-v1', 'ok': True,
        'worker_sha256': hashlib.sha256((HERE / 'new_session_once.py').read_bytes()).hexdigest(),
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'cases': cases,
        'Main_operations': 0, 'remote_operations': 0, 'init_or_launch_executed': False,
        'existing_real_pidfd_controls_reused': '../owned_cleanup_r1/local-controls.stdout.original.jsonl'},
        sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
