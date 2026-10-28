"""Host-only synthetic regressions against unchanged Desktop 745c0731."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path('/workspace/desktop-current-audit')

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

capture = load('capture', 'support/rootfs/capture.py')
compare = load('compare', 'compat/linux/compare.py')
results = {'scope': 'synthetic host-only; no ELF or kernel executed'}
results['empty_reports'] = compare.compare({}, {})
minimal = {'cases': {'threads': {'status': 'pass'}}}
results['missing_facts_and_exit'] = compare.compare(minimal, minimal)
reference = {'binaries': {'dynamic': {'sha256': 'a', 'interpreter': '/lib/ld.so'}},
             'cases': {'threads': {'status': 'pass', 'exit_code': 0,
                                   'facts': {'ok': True, 'count': 1}}}}
candidate = copy.deepcopy(reference)
candidate['cases']['threads']['facts'] = {'ok': 1, 'count': True}
results['wrong_fact_types'] = compare.compare(reference, candidate)
with tempfile.TemporaryDirectory(prefix='a04-duplicate-', dir=Path(__file__).parent) as tmp:
    base = Path(tmp)
    staged = base / 'staged'
    (staged / 'etc').mkdir(parents=True)
    payload = b'synthetic rootfs payload\n'
    (staged / 'etc/probe').write_bytes(payload)
    (staged / 'etc/probe').chmod(0o444)
    record = {'path': '/etc/probe', 'sha256': hashlib.sha256(payload).hexdigest(),
              'bytes': len(payload), 'mode': '0444'}
    manifest = base / 'manifest.json'
    manifest.write_text(json.dumps({'files': [record, dict(record)]}))
    archive = base / 'rootfs.tar'
    capture.create_tar(staged, archive)
    destination = base / 'extracted'
    try:
        capture.extract_verified_tar(archive, manifest, destination)
    except ValueError as exc:
        results['duplicate_manifest'] = {'error': str(exc),
            'destination_created_before_rejection': destination.exists(),
            'payload_written_before_rejection': (destination / 'etc/probe').read_bytes() == payload}
print(json.dumps(results, indent=2))
