"""Verify literal-only rebinding without running the evidence reader."""
import ast
import difflib
import hashlib
import json
import re
from pathlib import Path

BASE = Path('/workspace/scratch/pocket4-lmkd-supervisor-r11-20261104-owned-01')
OLD = BASE / 'prefix-normal-readback-01'
NEW = BASE / 'prefix-normal-readback-02'
PLAN = BASE / 'prefix-normal-admission-02/normal-plan.json'
OUT = Path(__file__).resolve().parent

def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

old = (OLD / 'read-normal-evidence.py').read_text()
new = (NEW / 'read-normal-evidence.py').read_text()
assert hashlib.sha256(old.encode()).hexdigest() == 'c3d8476dddcc8edd86987469727685ffeb74cfde0c4756a04ca39e2b532e11c4'
assert hashlib.sha256(new.encode()).hexdigest() == 'bf4b311e5e33e3ff2fdb2c984858183c713f6001b4a04c97b84faa2989f49ea9'
manifest = pin(NEW / 'manifest.json')
rows = json.loads((NEW / 'manifest.json').read_bytes())['files']
assert len(rows) == 4
for row in rows:
    observed = pin(NEW / row['path'])
    assert all(observed[k] == row[k] for k in ('bytes', 'sha256'))
replacements = [
    ('/home/alex/work/pocket4-relay-prefix-r11-source-05-01', '/home/alex/work/pocket4-relay-prefix-r11-source-05-02', 1),
    ('5dcff218dbef5869c213de3c4bcf475ff76111794ac3bb302fac2d73d396f2be',
     'd5ac0c8b6b3250e8ab02a33f1d04fe9ea64f3a32667325dff1827499ba77336a', 1),
    ('p4-relay-prefix-5dcff218dbef5869c213de3c', 'p4-relay-prefix-d5ac0c8b6b3250e8ab02a33f', 2),
    ('dd9c420ae36678e3dc6fc4cbac4b08730a133a6b4b37ae11496c6f4b46babaef',
     'cc003f5e6bbb54e1c8a8cd86a78a50b65ee7598ac37992f64b5f89a32923a41f', 1),
    ('normal-plan-01.json', 'normal-plan-02.json', 1),
]
expected = old
for a, b, count in replacements:
    assert expected.count(a) == count
    expected = expected.replace(a, b)
assert new == expected
actual_diff = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                       fromfile='normal01/read-normal-evidence.py', tofile='normal02/read-normal-evidence.py'))
assert actual_diff.encode() == (NEW / 'normal01-to02-reader.diff').read_bytes()
constants = {}
for node in ast.parse(new).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in ('SOURCE_ROOT','BASE','LEAF','NAMESPACE','NONCE','PLAN_SHA','MEMBERS'):
            constants[node.targets[0].id] = ast.literal_eval(node.value)
plan_pin = pin(PLAN)
plan = json.loads(PLAN.read_bytes())
assert plan_pin['sha256'] == constants['PLAN_SHA'] == 'cc003f5e6bbb54e1c8a8cd86a78a50b65ee7598ac37992f64b5f89a32923a41f'
assert plan['nonce'] == constants['NONCE'] and re.fullmatch('[0-9a-f]{64}', constants['NONCE'])
assert plan['mode'] == 'normal' and plan['scope'] == 'OWNED_HOST_PREFIX_ONLY_NO_ANDROID' and plan['predecessor'] is None
assert constants['NAMESPACE'] == 'p4-relay-prefix-' + constants['NONCE'][:24]
assert constants['LEAF'] == constants['NAMESPACE'] + '-normal'
for label in ('actor', 'coordinator'):
    assert str(Path(plan['sources'][label]['path']).parent.parent) == constants['SOURCE_ROOT']
assert len(constants['MEMBERS']) == len(set(constants['MEMBERS'])) == 8
compile(new, str(NEW / 'read-normal-evidence.py'), 'exec')
prior = Path('/workspace/scratch/94990735b266/android-cp06/prefix-normal-reader-review-01/report.json')
assert pin(prior)['sha256'] == '71c8636cd18a49c5f0746c318d6e18cc25bdad2d9267fc01562ebb5e48846dd7'
result = {
    'schema': 1, 'scope': 'independent literal-only rebinding checks; no reader execution',
    'manifest': manifest, 'payloads_verified': len(rows), 'source': pin(NEW / 'read-normal-evidence.py'),
    'old_source': pin(OLD / 'read-normal-evidence.py'), 'prior_review': pin(prior), 'plan': plan_pin,
    'literal_replacements': [{'old': a, 'new': b, 'count': n} for a,b,n in replacements],
    'all_other_bytes_identical': True, 'stored_diff_exact': True, 'fixed_constants': constants,
    'nonce_length_and_namespace_leaf_consistent': True, 'exact_new_plan_binding_verified': True,
    'compile_only_pass': True, 'reader_executed': False, 'Hepta_calls': 0,
    'unit_or_namespace_actions': 0, 'Android_or_Main_actions': 0,
}
raw = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
with (OUT / 'binding-checks.json').open('xb') as stream:
    stream.write(raw)
print(json.dumps(pin(OUT / 'binding-checks.json')))
