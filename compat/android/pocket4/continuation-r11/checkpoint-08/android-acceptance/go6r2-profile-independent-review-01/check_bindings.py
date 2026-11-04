#!/usr/bin/env python3
"""Read-only exact-input/delta checks; never submit or run the builder."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266/native-new-env-01')
SOURCE = BASE / 'combined05-go6r2-profile-02'
OUT = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, expected):
    raw = path.read_bytes()
    assert sha(raw) == expected, str(path)
    return raw


def delta(a, b, before, after):
    return ''.join(difflib.unified_diff(a.decode().splitlines(True), b.decode().splitlines(True),
                                       fromfile=before, tofile=after)).encode()


def functions(raw):
    source = raw.decode()
    return {n.name: ast.get_source_segment(source, n).encode() for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def main():
    manifest_raw = pinned(SOURCE/'SOURCE_PINS.json', '4918f3634e328caa0c359a38a6a8291f8d2686ce28459ad56e4c01b927f06490')
    manifest = json.loads(manifest_raw)
    assert len(manifest['files']) == manifest['source_files'] == 18
    records = {}
    for rel, wanted in manifest['files'].items():
        assert not Path(rel).is_absolute() and '..' not in Path(rel).parts
        path = SOURCE/rel
        assert not path.is_symlink() and path.is_file()
        raw = pinned(path, wanted['sha256'])
        assert len(raw) == wanted['bytes']
        raw.decode('utf-8')
        records[rel] = wanted
    assert set(str(p.relative_to(SOURCE)) for p in SOURCE.rglob('*') if p.is_file()) == set(records)|{'SOURCE_PINS.json'}
    old = pinned(BASE/'fullbuild05-prepare-01/combined_build05.py', 'e56f06abdbda5aa95fe42e4ecf14d7f79f53e53821a8d5b1d43d0dce0776c655')
    new = (SOURCE/'combined_build_go6r2.py').read_bytes()
    assert delta(old, new, 'a/combined_build05.py', 'b/combined_build_go6r2.py') == (SOURCE/'controller-original-go6-to-go6r2.patch').read_bytes()
    old_fence = (BASE/'combined05-go4-profile-01/fenced_build_go4.template.py').read_bytes()
    new_fence = (SOURCE/'fenced_build_go6r2.template.py').read_bytes()
    assert delta(old_fence, new_fence, 'a/fenced_build_go4.template.py', 'b/fenced_build_go6r2.template.py') == (SOURCE/'fence-go4-to-go6r2.patch').read_bytes()
    old_gen = (BASE/'combined05-go4-profile-01/make_requests.py').read_bytes()
    new_gen = (SOURCE/'make_requests.py').read_bytes()
    assert delta(old_gen, new_gen, 'a/go4/make_requests.py', 'b/go6r2/make_requests.py') == (SOURCE/'request-generator-go4-to-go6r2.patch').read_bytes()
    old_funcs, new_funcs = functions(old), functions(new)
    changed = sorted(name for name in old_funcs if old_funcs[name] != new_funcs[name])
    added = sorted(set(new_funcs)-set(old_funcs))
    assert changed == ['artifact_gate', 'build', 'plan', 'source_contract']
    assert added == ['go_projection_contract', 'memory_admission', 'owned_resource_gate']
    preserved = json.loads((SOURCE/'preserved-protocols.json').read_bytes())
    for row in preserved['unchanged_functions']:
        assert old_funcs[row['function']] == new_funcs[row['function']]
        assert sha(old_funcs[row['function']]) == row['sha256']
        assert len(old_funcs[row['function']]) == row['bytes']
    snapshot = pinned(SOURCE/'main_snapshot.py', 'f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb')
    assert snapshot == (BASE/'combined05-go4-profile-01/main_snapshot.py').read_bytes()
    builder = pinned(SOURCE/'expected-copied-builder-source-manifest.json', 'e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017')
    assert builder == (BASE/'go5-actual-preparation-01/base-builder-source-manifest.reconstructed-exact.json').read_bytes()
    assert len(json.loads(builder)) == 449
    scope = {'__name__': 'review_only', '__file__': str(SOURCE/'make_requests.py')}
    exec(compile(new_gen, str(SOURCE/'make_requests.py'), 'exec'), scope, scope)
    request_raw = (SOURCE/'prepare-request-01/exact-request.json').read_bytes()
    assert scope['encoded'](scope['make_prepare']()) == request_raw
    request = json.loads(request_raw)
    assert request['stdin'].encode() == new and request['args'][-1] == '--prepare'
    assert request['timeout_seconds'] == 300 and request['cpu_quota_percent'] == 100
    assert request['memory_max_bytes'] == 1073741824 and request['nice'] == 10
    assert request['idempotency_key'] == 'pocket4-native-combined05-go6-full-source-preparation-02-20261104'
    record = {'schema': 1, 'pass': True, 'manifest_sha256': sha(manifest_raw),
              'payloads_verified': records, 'all_three_patches_recomputed_equal': True,
              'changed_existing_functions': changed, 'added_functions': added,
              'preserved_functions_rechecked': len(preserved['unchanged_functions']),
              'original_builder_manifest_449_rows_byte_identical': True,
              'Main_snapshot_byte_identical': True,
              'prepare_request_exact_generator_bytes': True,
              'prepare_request_sha256': sha(request_raw),
              'remote_calls': 0, 'prepare_build_or_main_execution': False}
    raw = (json.dumps(record, indent=2)+'\n').encode()
    (OUT/'binding-checks.json').open('xb').write(raw)
    print(json.dumps({'pass': True, 'bytes': len(raw), 'sha256': sha(raw)}))


if __name__ == '__main__':
    main()
