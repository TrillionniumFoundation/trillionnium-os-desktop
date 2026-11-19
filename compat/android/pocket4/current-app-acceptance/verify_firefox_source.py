#!/usr/bin/env python3
"""Verify the frozen Firefox source candidate against the required39 inputs.

This reads repository source/metadata only. Embedded historical host paths are
never followed, and no original transport, APK, controller or runner is loaded.
"""
import ast
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

HERE = Path(__file__).resolve().parent
PACKET = 'firefox-public-executor-20261119'
PREFLIGHT = 'required39-business-preflight-20261119-r2'
FIXED = {
    'FILES.sha256': (3171, '02563e9828de2c8790189540570b640d40306609d4e856ae7e2d4144288e5918'),
    'MANIFEST.json': (7905, '22ec962410837130f5c34569aefdbacd7fcf18feaacfc4d4ad655020f7447a5f'),
    'CURRENT-SOURCE-SUCCESSOR.json': (4619, 'b707d115a06d7fb962926dde9cb570135fc274a69339de3c6c6a26bdc90e7445'),
}
METADATA = {
    'business_plan_r2': 'PLAN.json',
    'registry': 'inputs/current-source-inputs.json',
    'release_scope': 'inputs/release-scope.json',
    'source_state': 'inputs/CURRENT-SOURCE-STATE.json',
}
F9 = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, message):
    if not value:
        raise ValueError(message)


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(relative, expected=None):
    name = PurePosixPath(relative)
    need(not name.is_absolute() and '..' not in name.parts and str(name) == relative, 'fixed relative source path')
    path = HERE / relative
    need(path.resolve() == path, 'no source symlink components')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= 1024 * 1024,
             'bounded single-link source file')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(before.st_size + 1)
        f9 = lambda value: tuple(getattr(value, key) for key in F9)
        need(len(raw) == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()),
             'source changed during read')
    finally:
        os.close(fd)
    if expected is not None:
        need(pin(raw) == {key: expected[key] for key in ('bytes', 'sha256')}, 'complete source size/hash: ' + relative)
    return raw


def constant(tree, name):
    rows = [node.value for node in tree.body if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name]
    need(len(rows) == 1, 'one source constant: ' + name)
    return ast.literal_eval(rows[0])


def main():
    fixed = {}
    for name, (size, digest) in FIXED.items():
        fixed[name] = read(PACKET + '/' + name, {'bytes': size, 'sha256': digest})
    manifest = json.loads(fixed['MANIFEST.json'])
    current = json.loads(fixed['CURRENT-SOURCE-SUCCESSOR.json'])
    inventory = {}
    for line in fixed['FILES.sha256'].decode('ascii').splitlines():
        digest, name = line.split('  ', 1)
        need(name not in inventory and len(digest) == 64, 'unique exact inventory member')
        inventory[name] = digest
    need(len(inventory) == 33 and set(inventory) == {row['path'] for row in manifest['files']} | {'MANIFEST.json'},
         'complete original 34-file packet')
    bodies = {}
    expected = {row['path']: row for row in manifest['files']}
    for name, digest in inventory.items():
        bodies[name] = read(PACKET + '/' + name, expected.get(name))
        need(pin(bodies[name])['sha256'] == digest, 'inventory full-content digest')
    binding = json.loads(bodies['SOURCE-BINDING.json'])
    metadata = {key: json.loads(read(PREFLIGHT + '/' + local, binding[key])) for key, local in METADATA.items()}
    package = 'org.mozilla.firefox'
    source = next(row for row in metadata['source_state']['applications'] if row['package'] == package)
    registry = next(row for row in metadata['registry']['applications'] if row['package'] == package)
    plan = next(row for row in metadata['business_plan_r2']['packages'] if row['package'] == package)
    need(source == binding['selected_source'] and registry == source['unchanged_current_registry_record'],
         'exact selected Firefox source and registry record')
    need(plan['actual_runtime_bindings'] == binding['previous_actual_runtime_bindings']
         and all(value is None for value in plan['actual_runtime_bindings'].values())
         and plan['additive_checklist'] == binding['previous_additive_checklist'], 'unchanged historical plan and unresolved runtime')
    need(binding['exemptions'] == metadata['release_scope']['exemptions']
         and len(metadata['release_scope']['selected_packages']) == binding['selected_count'] == 42
         and len(metadata['source_state']['applications']) == binding['required_count'] == 39, 'unchanged 42/39/3 scope')
    custody = ast.parse(bodies['firefox_custody.py'])
    values = {name: constant(custody, name) for name in ('PACKAGE', 'VERSION_NAME', 'VERSION_CODE', 'APK_BYTES', 'APK_SHA256')}
    need(values == {'PACKAGE': package, 'VERSION_NAME': registry['version_name'], 'VERSION_CODE': registry['version_code'],
                   'APK_BYTES': registry['input']['bytes'], 'APK_SHA256': registry['input']['sha256']}, 'exact selected source constants')
    protocol = ast.parse(bodies['firefox_protocol.py'])
    checklist = binding['previous_additive_checklist']
    need(constant(protocol, 'PAGES') == checklist['pages']
         and constant(protocol, 'STEPS') == tuple(row['id'] for row in checklist['steps']), 'same finite public checklist')
    adapter = ast.parse(bodies['firefox_adapter.py'])
    flow = read('system-cp3a-source-adapter-20261119/originals/ihg-5.111.1-r1/app_flow.py')
    need(pin(flow)['sha256'] == constant(adapter, 'FLOW_SHA')
         and pin(bodies['originals/business_baseline.py'])['sha256'] == constant(adapter, 'BASELINE_SHA')
         and pin(bodies['originals/business_ui_entry.py'])['sha256'] == constant(adapter, 'UI_ENTRY_SHA'), 'complete original transport source bodies')
    origins = json.loads(bodies['ORIGINS.json'])
    need(origins['current_source_cohort_compatibility_qualified'] is False
         and all(row['matches_old_typed_entry'] is False and row['repinned_or_replaced'] is False
                 and row['observed_sha256'] != row['old_typed_entry_expected_sha256'] for row in origins['current_host_clients']),
         'host CLI cohort mismatch remains explicit')
    need(gzip.decompress(bodies['originals/native-actions-source-export.json.gz'])
         == bodies['originals/native-actions-source-export.json'], 'exact existing helper source export')
    need(current['state'] == 'EXECUTOR_SOURCE_PREPARED_PRODUCTION_ENTRY_HELD'
         and current['production_entry_held'] is True and current['production_hold_has_no_configuration_override'] is True
         and all(current[key] is False for key in ('installed', 'execution_ready', 'runtime_qualified', 'business_qualified',
             'whole_app_business_accepted', 'production_ready', 'finite_public_case_passed', 'all39_runtime_accepted', 'all39_latest_qualified')),
         'source publication cannot qualify execution')
    print(json.dumps({'state': 'PASS_FIREFOX_FROZEN_SOURCE_ONLY', 'packet_files': 34, 'external_metadata_files': 4,
        'production_entry_held': True, 'historical_controls': 32, 'current_host_controls': 35,
        'Android_calls': 0, 'runtime_qualified': False, 'production_ready': False}, sort_keys=True))


if __name__ == '__main__':
    main()
