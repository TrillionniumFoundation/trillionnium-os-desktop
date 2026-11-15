"""Run public regressions from a clean checkout without private evidence."""
from pathlib import Path
import hashlib
import importlib.util
import json
import platform
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CASES = 44


def main():
    if sys.version_info < (3, 10):
        raise SystemExit('Public core tests require Python 3.10 or newer.')
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise SystemExit('Public ELF/FIFO core tests require Linux x86_64.')
    if shutil.which('cc') is None:
        raise SystemExit('Public ELF tests require an actual C compiler available as cc.')
    manifest = json.loads((ROOT / 'SOURCE-MANIFEST.json').read_bytes())
    if manifest['schema'] != 'p4-full-carrier-public-source-v1' or manifest['execution_authorized'] is not False:
        raise SystemExit('Expected the source-only public carrier manifest.')
    actual = {'src/' + path.name for path in (ROOT / 'src').iterdir() if path.is_file()}
    if actual != set(manifest['files']):
        raise SystemExit('The complete public source member set differs from the manifest.')
    for name, expected in manifest['files'].items():
        path = ROOT / name
        if path.is_symlink():
            raise SystemExit('The public source member is a symlink: ' + name)
        raw = path.read_bytes()
        if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise SystemExit('The exact public source member differs: ' + name)
    descriptor = importlib.util.spec_from_file_location('full_carrier_public_core', ROOT / 'tests/test_core.py')
    module = importlib.util.module_from_spec(descriptor)
    descriptor.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    if suite.countTestCases() != EXPECTED_CASES:
        raise SystemExit('The reviewed public core test count changed.')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {'suite': 'public_core', 'tests': result.testsRun, 'failures': len(result.failures),
               'errors': len(result.errors), 'skipped': len(result.skipped),
               'private_qualification_evidence_loaded': False, 'Android_builds': 0,
               'VM_starts': 0, 'runtime_qualified': False, 'production_ready': False}
    print(json.dumps(summary, sort_keys=True))
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
