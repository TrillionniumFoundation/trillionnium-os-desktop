"""Actual bounded_file against owned regular/hardlinked files; no Main reads."""
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types

HERE = Path(__file__).resolve().parent


def load(path, name):
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), mod.__dict__)
    return mod


old = load(HERE / 'preimage_source_contract.py', 'actual_r2_source_contract')
new = load(HERE / 'source_contract.py', 'actual_r3_source_contract_candidate')
old_ast = ast.parse((HERE / 'preimage_source_contract.py').read_text())
new_ast = ast.parse((HERE / 'source_contract.py').read_text())
old_fn = next(n for n in old_ast.body if isinstance(n, ast.FunctionDef) and n.name == 'bounded_file')
new_fn = next(n for n in new_ast.body if isinstance(n, ast.FunctionDef) and n.name == 'bounded_file')
assert ast.dump(old_fn.args, include_attributes=False) == ast.dump(new_fn.args, include_attributes=False)
old_require = old_fn.body[1].body[1]
new_require = new_fn.body[1].body[1]
assert ast.dump(old_require.value.args[0], include_attributes=False) == ast.dump(new_require.value.args[0], include_attributes=False)
assert old.bounded_file.__defaults__ == new.bounded_file.__defaults__ == (131072,)
assert ast.dump(next(n for n in old_ast.body if getattr(n, 'name', None) == 'verify_shared_helper'), include_attributes=False) == \
       ast.dump(next(n for n in new_ast.body if getattr(n, 'name', None) == 'verify_shared_helper'), include_attributes=False)

rows = []
with tempfile.TemporaryDirectory(prefix='owned-input-shape-', dir=HERE) as scratch:
    path = Path(scratch) / 'owned.bin'
    path.write_bytes(b'ABC')
    for label, module in [('old-over-bound', old), ('new-over-bound', new)]:
        try:
            module.bounded_file(path, 2)
        except RuntimeError as error:
            text = str(error)
        else:
            raise AssertionError('size gate unexpectedly accepted')
        row = {'case': label, 'error': text}
        if module is old:
            assert text == 'INPUT_SHAPE_OR_BOUND_CHANGED'
        else:
            context = json.loads(text.split(': ', 1)[1])
            assert context['path'] == str(path) and context['size_bytes'] == 3 and context['maximum_bytes'] == 2
            assert context['nlink'] == 1 and context['is_regular']
            row['actual_metadata_explained'] = True
        rows.append(row)
    assert new.bounded_file(path, 3) == b'ABC'
    rows.append({'case': 'unchanged-exact-bound-success', 'pass': True})
    os.link(path, Path(scratch) / 'alias.bin')
    try:
        new.bounded_file(path, 3)
    except RuntimeError as error:
        context = json.loads(str(error).split(': ', 1)[1])
        assert context['nlink'] == 2 and context['size_bytes'] == context['maximum_bytes'] == 3
        rows.append({'case': 'unchanged-hardlink-rejection', 'reported_nlink': context['nlink']})
    else:
        raise AssertionError('hardlink gate changed')
print(json.dumps({'schema': 1, 'success': True, 'source_sha256': hashlib.sha256((HERE/'source_contract.py').read_bytes()).hexdigest(),
    'condition_AST_unchanged': True, 'default_and_helper_call_bounds_unchanged': True,
    'rows': rows, 'Main_UI_audio': False, 'deployment_candidate_complete': False}, sort_keys=True))
