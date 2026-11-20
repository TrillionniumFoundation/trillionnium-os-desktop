from pathlib import Path
import ast
import hashlib
import json

BASE = Path(__file__).resolve().parent
REMOTE = '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r21'

def sha(b):
    return hashlib.sha256(b).hexdigest()

old = (BASE / 'original_outer_r20.py').read_bytes()
if sha(old) != 'b5235de573194a674a1c0bf94cc19f834fcf7cf04c2396f9915162c9f18e8bfa' and old.endswith(b'\n\n') and sha(old[:-1]) == 'b5235de573194a674a1c0bf94cc19f834fcf7cf04c2396f9915162c9f18e8bfa':
    old = old[:-1]
    (BASE / 'original_outer_r20.py').write_bytes(old)
assert sha(old) == 'b5235de573194a674a1c0bf94cc19f834fcf7cf04c2396f9915162c9f18e8bfa'
bundle = json.loads((BASE / 'original_bundle_r20.json').read_bytes())
assert bundle['schema'] == 'pocket4-vendor-r20-launch-bundle-v1'
bundle['schema'] = 'pocket4-vendor-r21-launch-bundle-v1'
bundle['worker'] = {
    'path': REMOTE + '/source.py', 'bytes': 277931,
    'sha256': '71e439b91b5363ed9f295589ea7b29f6404de1556b9e61af0d85c6640e4768e9',
}
bundle['operational_contract'] = {
    'path': REMOTE + '/inputs/CONTRACT.json', 'bytes': 83652,
    'sha256': 'f88235f91532045e2037a42ce2a44623dc549075e93e041fb955c945d4876d3d',
}
bundle['preparation_scope'] = 'Exact existing R21 vendor-source worker; its fixed 2359-file vendor build cohort remains distinct from the 2360-file final runtime cohort.'
bundle['previous_outer_sha256'] = sha(old)
body = (json.dumps(bundle, sort_keys=True, indent=2) + '\n').encode()
outer = old.decode().replace('r20', 'r21').replace('R20', 'R21')
outer = outer.replace('417c25c35dd495cbfb20f3651848704b0e76ebd5014225da54a00193da37c942', sha(body))
ast.parse(outer)
restored = outer.replace('r21', 'r20').replace('R21', 'R20').replace(sha(body), '417c25c35dd495cbfb20f3651848704b0e76ebd5014225da54a00193da37c942')
assert restored.encode() == old, 'Only generation labels and bundle digest may differ'
for name, value in [('BUNDLE.json', body), ('outer.py', outer.encode())]:
    with (BASE / name).open('xb') as f:
        f.write(value)
result = {
    'schema': 'p4-r21-outer-exact-generation-preparation-v1',
    'source': bundle['worker'], 'contract': bundle['operational_contract'],
    'bundle': {'path': REMOTE + '/inputs/BUNDLE.json', 'bytes': len(body), 'sha256': sha(body)},
    'outer': {'path': REMOTE + '/outer.py', 'bytes': len(outer.encode()), 'sha256': sha(outer.encode())},
    'only_generation_labels_and_bundle_digest_changed': True,
    'budgets_locks_and_admission_conditions_unchanged': True,
    'runtime_qualified': False, 'production_ready': False, 'build_started': False,
}
with (BASE / 'PREPARATION.json').open('x') as f:
    json.dump(result, f, sort_keys=True, indent=2)
    f.write('\n')
print(json.dumps(result, sort_keys=True))
