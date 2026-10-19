"""Verify retained bytes, without regenerating missing historical evidence."""
import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent
r7 = json.loads((root / 'recovery-manifest.json').read_bytes())
a06 = json.loads((root / 'a06-recovery-manifest.json').read_bytes())

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

with zipfile.ZipFile(root / 'retained-r7-text.zip') as bundle:
    assert bundle.testzip() is None
    members = r7['files']
    assert len(bundle.namelist()) == len(members) == r7['retained_text_files'] == 864
    for entry in members:
        raw = bundle.read(entry['path'])
        assert len(raw) == entry['bytes'], entry['path']
        assert sha256(raw) == entry['sha256'], entry['path']
    assert all(x['path'] not in bundle.namelist() for x in r7['missing_binary_paths'])

archive = a06['archive']
raw = (root / archive['path']).read_bytes()
assert len(raw) == archive['bytes'] and sha256(raw) == archive['sha256']
with zipfile.ZipFile(root / archive['path']) as bundle:
    assert bundle.testzip() is None
    assert set(bundle.namelist()) == {x['path'] for x in a06['exact_retained_files']}
    for entry in a06['exact_retained_files']:
        raw = bundle.read(entry['path'])
        assert len(raw) == entry['bytes'] and sha256(raw) == entry['sha256']

serial = a06['guest_serial']
raw = (root / serial['path']).read_bytes()
assert len(raw) == serial['bytes'] and sha256(raw) == serial['sha256']
missing = r7['missing_binary_paths'] + a06['missing_binary_paths']
assert len({x['path'] for x in missing}) == a06['combined_missing_binary_path_count'] == 48
assert len({x['sha'] for x in missing}) == a06['combined_missing_binary_unique_blob_count'] == 43
assert r7['complete_original_tree_recovered'] is False
assert a06['exact_original_commit_tree_recovered'] is False
print(json.dumps({'retained_r7_text_files_verified': 864, 'a06_exact_json_files_verified': 6,
                  'missing_binary_paths': 48, 'missing_binary_blobs': 43,
                  'historical_product_execution_rerun': False}, sort_keys=True))
