"""Independent local source/pin checks. Never imports or executes the controller."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266/native-new-env-01')
OLD = BASE / 'factory-diagnostic03-runtime02-freeze-01'
NEW = BASE / 'factory-capdrop03-runtime03-freeze-01'
OUT = Path(__file__).resolve().parent

def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def write_new(name, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
    return pin(OUT / name)

manifest = pin(NEW / 'SOURCE_PINS.json')
assert manifest['sha256'] == '3e880d69c5520d2cac259ea5e0d0d8de76c2f2eff48d3787c2c50c05158eb9b1'
files = json.loads((NEW / 'SOURCE_PINS.json').read_bytes())['files']
assert len(files) == 5
for item in files:
    observed = pin(NEW / item['path'])
    assert all(observed[k] == item[k] for k in ('bytes', 'sha256'))
old = (OLD / 'controller.py').read_bytes()
new = (NEW / 'controller.py').read_bytes()
assert hashlib.sha256(old).hexdigest() == '2db9c643b177a61989d5fd3c860caba8a40b4abc7b8009db408b08d93caf99f2'
assert hashlib.sha256(new).hexdigest() == 'e76e35332951ba72e68bc59e7d4849ec05c06233c5db95d8d50d74ecfefe0628'
assert (BASE / 'factory-client-capdrop-runtime03-work01/controller.py').read_bytes() == new
actual_diff = ''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                       fromfile='runtime02/controller.py', tofile='runtime03/controller.py'))
assert actual_diff.encode() == (NEW / 'runtime02-to-capdrop03.patch').read_bytes()

tree = ast.parse(new)
added = {'CapabilityHeader', 'CapabilityData', 'clear_dropped_client_capabilities'}
removed_classes_functions = []
removed_bindings = []
kept = []
for node in tree.body:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in added:
        removed_classes_functions.append(node.name)
        continue
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = ast.unparse(node.targets[0])
        if target in ('libc.capget.argtypes', 'libc.capget.restype', 'libc.capset.argtypes', 'libc.capset.restype'):
            removed_bindings.append(target)
            continue
    kept.append(node)
tree.body = kept
assert set(removed_classes_functions) == added and len(removed_classes_functions) == 3
assert len(removed_bindings) == 4
entry = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'child_exec')
execute = entry.body[0]
drop = execute.body[0]
assert isinstance(drop, ast.If)
calls = [ast.unparse(n) for n in drop.body]
assert calls == ['os.setgroups([])', 'os.setresgid(uid, uid, uid)', 'os.setresuid(uid, uid, uid)',
                 'clear_dropped_client_capabilities(uid)', 'arm_parent(parent_fd)']
drop.body.pop(3)
assert ast.dump(tree, include_attributes=False) == ast.dump(ast.parse(old), include_attributes=False)
compile(new, str(NEW / 'controller.py'), 'exec')

old_stage = (OLD / 'stage_runtime.py').read_text()
stage = (NEW / 'stage_runtime.py').read_text()
expected_stage = old_stage.replace(hashlib.sha256(old).hexdigest(), hashlib.sha256(new).hexdigest())
expected_stage = expected_stage.replace('pocket4-factory-v2-host-runtime-source-02/', 'pocket4-factory-v2-host-runtime-source-03/')
expected_stage = expected_stage.replace('pocket4-factory-v2-host-runtime-02', 'pocket4-factory-v2-host-runtime-03')
assert stage == expected_stage
compile(stage, str(NEW / 'stage_runtime.py'), 'exec')
old_request = json.loads((OLD / 'exact-process-start-request.json').read_bytes())
request = json.loads((NEW / 'exact-process-start-request.json').read_bytes())
expected = copy.deepcopy(old_request)
expected['idempotency_key'] = 'pocket4-factory-v2-capdrop03-host-runtime-03-20261104'
expected['stdin'] = new.decode()
expected['args'][4] = stage
expected['args'][-1] = '/home/alex/work/pocket4-factory-v2-host-runtime-03'
assert request == expected
assert request['args'][:4] == ['-n', '/usr/bin/python3', '-I', '-c']
assert request['cpu_quota_percent'] == 100 and request['memory_max_bytes'] == 536870912
assert request['timeout_seconds'] == 180 and request['nice'] == 10
checks = {
    'schema': 1, 'scope': 'local exact-byte, AST and request binding only',
    'new_manifest': manifest, 'old_controller': pin(OLD / 'controller.py'),
    'new_controller': pin(NEW / 'controller.py'), 'payloads_verified': len(files),
    'frozen_diff_exact': True, 'all_other_controller_ast_unchanged': True,
    'child_call_order': calls, 'stage_only_pin_and_fresh_paths_changed': True,
    'exact_request_stdin_and_stage_bound': True, 'resource_values_unchanged': True,
    'controller_and_stage_compile_only': True, 'controller_imported_or_executed': False,
    'capset_or_credentials_changed': False, 'remote_requests': 0,
    'namespace_or_service_actions': 0, 'Main_or_Android_actions': 0,
}
print(json.dumps(write_new('binding-checks.json', checks)))
