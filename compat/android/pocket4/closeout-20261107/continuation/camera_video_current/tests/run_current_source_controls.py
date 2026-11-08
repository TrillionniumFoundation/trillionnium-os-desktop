#!/usr/bin/env python3
"""Run bounded source-only canonical Camera controls; no runtime admission."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_SHA256 = '28e61371c50638a3ac33d4e28b0466754bc2b81c9f5d015f262d43e60243dd00'
SUITES = (
    ('preparation', 'test_preparation_entry.py', 11),
    ('display_contract', 'test_video_display_contract.py', 18),
    ('state_public_api', 'camera_video_state_test.py', 9),
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def snapshot():
    inventory_raw = (ROOT / 'reviewed-source-inventory.json').read_bytes()
    require(digest(inventory_raw) == INVENTORY_SHA256, 'EXACT_CURRENT_INVENTORY_REQUIRED')
    inventory = json.loads(inventory_raw)
    require(inventory['source_count'] == len(inventory['files']) == 29,
            'EXACT_29_PRODUCTION_SOURCES')
    names = {r['name'] for r in inventory['files']}
    require(len(names) == 29 and names == {p.name for p in (ROOT / 'source').iterdir()},
            'EXACT_SOURCE_DIRECTORY_MEMBERS')
    for row in inventory['files']:
        path = ROOT / 'source' / row['name']
        require(path.is_file() and not path.is_symlink(), 'REGULAR_PRODUCTION_SOURCE')
        raw = path.read_bytes()
        require((len(raw), digest(raw)) == (row['bytes'], row['sha256']),
                'CURRENT_SOURCE_CHANGED:' + row['name'])
    relative = ['source/' + name for name in sorted(names)]
    relative += ['reviewed-source-inventory.json', 'tools/prepare_camera_video.py',
                 'display/video_display_wrapper.py', 'display/display_holder.py',
                 'display/display_lease.py', 'provenance/photo_display_wrapper.py',
                 'provenance/display_holder.py', 'tests/run_current_source_controls.py',
                 'tests/fixtures/owner_camera_video_state_fixture.py']
    relative += ['tests/' + filename for _, filename, _ in SUITES]
    rows = []
    for name in sorted(relative):
        path = ROOT / name
        require(path.is_file() and not path.is_symlink(), 'REGULAR_CONTROL_INPUT')
        raw = path.read_bytes()
        rows.append({'relative': name, 'bytes': len(raw), 'sha256': digest(raw)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    require(not args.report.exists() and not args.report.is_symlink(), 'CREATE_ONLY_CONTROL_REPORT')
    require(args.report.parent.is_dir(), 'EXISTING_REPORT_PARENT')
    before = snapshot()
    results = []
    for family, filename, expected in SUITES:
        path = ROOT / 'tests' / filename
        module = types.ModuleType('current_camera_' + family)
        module.__file__ = str(path)
        exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        require(suite.countTestCases() == expected, 'COMPLETE_EXPECTED_SUITE:' + family)
        result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
        results.append({'family': family, 'expected': expected, 'tests_run': result.testsRun,
                        'failures': len(result.failures), 'errors': len(result.errors),
                        'skipped': len(result.skipped)})
    after = snapshot()
    passed = before == after and all(r['tests_run'] == r['expected']
        and r['failures'] == r['errors'] == r['skipped'] == 0 for r in results)
    report = {'schema': 'pocket4-camera-current-source-controls-v1',
              'inventory_sha256': INVENTORY_SHA256, 'suites': results,
              'tests_run': sum(r['tests_run'] for r in results),
              'expected_tests': 38, 'source_and_control_inputs_before': before,
              'source_and_control_inputs_after': after, 'source_bytes_unchanged': before == after,
              'passed': passed, 'uid': os.getuid(), 'euid': os.geteuid(),
              'interpreter': sys.executable, 'python_version': sys.version.split()[0],
              'prior_host_qualification_transferred': False,
              'real_UID_1000_decoder_qualified': False, 'real_display_lease_qualified': False,
              'Main_actions': 0, 'Android_UI_actions': 0, 'physical_audio_stream_actions': 0,
              'runtime_qualified': False, 'whole_app_business_accepted': False,
              'scope': 'Real temporary source files, formal entry rejection and synthetic receipt/state contracts; no owned runtime or device acceptance.'}
    with args.report.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, sort_keys=True, indent=2)
        handle.write('\n')
    print(json.dumps({k: report[k] for k in ('schema', 'tests_run', 'expected_tests', 'passed',
                                           'source_bytes_unchanged', 'runtime_qualified')}, sort_keys=True))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
