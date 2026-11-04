#!/usr/bin/env python3
"""Local own-directory control only; never invokes fixed-root execute_once."""
import ast
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'index_selected_roots.py'


def empty():
    return {'roots': [], 'candidates': [], 'primary_error': None, 'secondary_errors': []}


def main():
    raw = SOURCE.read_bytes()
    calls = {n.func.attr for n in ast.walk(ast.parse(raw))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {'read', 'read_bytes', 'read_text', 'readlink', 'walk', 'rglob', 'glob'}
    scope = {'__name__': 'own_stage2_control'}
    exec(compile(raw, str(SOURCE), 'exec'), scope, scope)
    with tempfile.TemporaryDirectory(prefix='owned-stage2-', dir=HERE) as directory:
        root = Path(directory)
        for name in ('actions-v2', 'data', 'objects', 'business-flows', 'marriott-diagnostics'):
            (root / name).mkdir()
        for name in ('ActionRunner.java', 'AndroidManifest.xml', 'build-actions-v2.py',
                     'source-manifest.json', 'sources.tar.gz', 'actions-v2.apk', 'plain.log'):
            (root / name).write_text('owned metadata-only sentinel\n')
        (root / 'actions-v2' / 'nested-sentinel').write_text('must not enumerate nested content\n')
        (root / 'ActionRunner-link.java').symlink_to(root / 'ActionRunner.java')
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            result = empty()
            scope['index_root'](fd, str(root), result, time.monotonic() + 5)
        finally:
            os.close(fd)
        assert result['primary_error'] is None and not result['secondary_errors']
        assert result['roots'][0]['completed'] is True
        expected = {'actions-v2', 'ActionRunner.java', 'AndroidManifest.xml',
                    'build-actions-v2.py', 'source-manifest.json', 'sources.tar.gz', 'actions-v2.apk'}
        assert {Path(row['path']).name for row in result['candidates']} == expected
        assert result['roots'][0]['skipped_directories'] == 4
        assert result['roots'][0]['skipped_symlink_or_special'] == 1
        assert result['roots'][0]['skipped_nondirectory_nonmatch'] == 1
        scope['MAX_ENTRIES_PER_ROOT'] = 1
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            limited = empty()
            scope['index_root'](fd, str(root), limited, time.monotonic() + 5)
        finally:
            os.close(fd)
        assert limited['primary_error']['message'].startswith('fixed-root entry bound reached;')
        assert limited['roots'][0]['completed'] is False
    plan = subprocess.run(['python3', '-I', str(SOURCE)], capture_output=True, timeout=5)
    assert plan.returncode == 0 and not plan.stderr and json.loads(plan.stdout)['state'] == 'PLAN_ONLY'
    print(json.dumps({'schema': 1, 'actual_local_fixture': True,
                      'exact_7_selected_rows': True, 'excluded_data_objects_commercial_flow_directories': True,
                      'symlink_and_unmatched_file_skipped': True, 'no_nested_entry': True,
                      'entry_cap_negative': True, 'source_has_no_file_body_or_recursive_read_API': True,
                      'default_PLAN_returncode': 0, 'fixture_removed': not root.exists(),
                      'fixed_remote_roots_or_Android_accessed': False}))


if __name__ == '__main__':
    main()
