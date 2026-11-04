#!/usr/bin/env python3
"""Only local owned-directory controls; never calls execute_once or remote tools."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'index_task_directories.py'


def report():
    return {'direct_entries_seen': 0, 'matching_nondirectory_entries_skipped': 0,
            'directories': [], 'primary_error': None, 'secondary_errors': []}


def main():
    tree = ast.parse(SOURCE.read_bytes())
    forbidden = {'walk', 'rglob', 'glob', 'read', 'read_bytes', 'read_text', 'readlink'}
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls & forbidden
    spec = importlib.util.spec_from_file_location('owned_index_fixture', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='owned-direct-index-', dir=HERE) as directory:
        base = Path(directory)
        (base / 'pocket4-one').mkdir()
        (base / 'droidloom-two').mkdir()
        (base / 'unselected').mkdir()
        (base / 'pocket4-one' / 'ActionRunner.java').write_text('owned nested sentinel\n')
        (base / 'pocket4-file').write_text('owned file sentinel\n')
        (base / 'pocket4-link').symlink_to(base / 'unselected', target_is_directory=True)
        descriptor = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        module.ROOT = str(base)
        try:
            actual = report()
            module.scan_directories(descriptor, actual, time.monotonic() + 5)
            assert actual['primary_error'] is None and not actual['secondary_errors']
            assert {Path(row['path']).name for row in actual['directories']} == {'pocket4-one', 'droidloom-two'}
            assert actual['matching_nondirectory_entries_skipped'] == 2
            assert actual['direct_entries_seen'] == 5
            assert all(row['children_enumerated'] is False and row['file_body_read'] is False
                       for row in actual['directories'])
            module.MAX_ENTRIES = 1
            limited = report()
            limited_descriptor = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                module.scan_directories(limited_descriptor, limited, time.monotonic() + 5)
            finally:
                os.close(limited_descriptor)
            assert limited['primary_error']['message'].startswith('direct-entry limit reached;')
        finally:
            os.close(descriptor)
    result = subprocess.run(['python3', '-I', str(SOURCE)], capture_output=True, timeout=5)
    assert result.returncode == 0 and not result.stderr
    assert json.loads(result.stdout)['state'] == 'PLAN_ONLY'
    print(json.dumps({'schema': 1, 'actual_local_owned_fixture': True,
                      'selected_exact_two_task_directories': True,
                      'regular_file_and_symlink_skipped': True,
                      'nested_sentinel_not_indexed': True,
                      'entry_cap_actual_rejection': True,
                      'no_file_body_or_recursive_API_in_source': True,
                      'default_PLAN_returncode': result.returncode,
                      'fixture_removed': not base.exists(),
                      'remote_or_fixed_host_root_index_run': False}))


if __name__ == '__main__':
    main()
