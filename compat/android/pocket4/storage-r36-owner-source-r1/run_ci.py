"""Replay the pinned owner-format source and run its 35 ordinary Python cases.

No storage entry point is executed. The sole candidate helper is copied from
this packet into a temporary source tree, which is removed after the tests.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import shutil
import stat
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
BASELINE_SHA256 = '91772330fc4f500a6ed0961bf3b0ab5efcab3381a35de647c4470f0919f8fa11'
CANDIDATE_SHA256 = 'f3ad987024396fe19d33a51be57af57d1b2c6e3b7d97c4e249a49d422f5592fc'
POSTIMAGES = {'admit.py', 'contract.json', 'prepare.py', 'rotation_support.py'}
EXPECTED_TESTS = 35


def require(ok, detail):
    if not ok:
        raise RuntimeError(detail)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_relative(value):
    require(type(value) is str and '\0' not in value and
            not value.startswith('/') and pathlib.PurePosixPath(value).as_posix() == value and
            all(part not in ('', '.', '..') for part in value.split('/')), 'canonical packet member path')
    return value


def regular_bytes(path, limit=65536):
    metadata = path.lstat()
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and
            0 < metadata.st_size <= limit, 'bounded single-link regular packet member: ' + str(path))
    raw = path.read_bytes()
    require(len(raw) == metadata.st_size, 'complete packet member: ' + str(path))
    return raw


def verify_packet(expected):
    require(type(expected) is str and len(expected) == 64 and
            all(char in '0123456789abcdef' for char in expected), 'externally reviewed inventory SHA256')
    raw = regular_bytes(ROOT / 'FILES.json')
    require(digest(raw) == expected, 'exact reviewed packet inventory')
    inventory = json.loads(raw)
    require(type(inventory) is dict and set(inventory) == {'schema', 'files'} and
            inventory['schema'] == 'p4-storage-owner-source-packet-v1' and
            type(inventory['files']) is dict and len(inventory['files']) == 41,
            'complete finite source packet')
    members = {}
    for name, reference in inventory['files'].items():
        safe_relative(name)
        require(type(reference) is dict and set(reference) == {'bytes', 'sha256'} and
                type(reference['bytes']) is int, 'exact source member reference')
        body = regular_bytes(ROOT / name)
        require(len(body) == reference['bytes'] and digest(body) == reference['sha256'],
                'source member bytes differ: ' + name)
        members[name] = body
    actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob('*') if path.is_file()}
    require(actual == set(members) | {'FILES.json'}, 'no omitted or undeclared packet files')
    return members


def checked_source_manifest(members, directory, expected, count):
    raw = members[directory + '/SOURCE-MANIFEST.json']
    require(digest(raw) == expected, 'exact source-generation manifest: ' + directory)
    manifest = json.loads(raw)
    require(type(manifest['files']) is dict and len(manifest['files']) == count,
            'complete source-generation member count')
    for name in manifest['files']:
        require(safe_relative(name) == pathlib.PurePosixPath(name).name, 'flat source member name')
    return raw, manifest


def replay_candidate(members, destination):
    _, baseline = checked_source_manifest(members, 'baseline-r8', BASELINE_SHA256, 29)
    candidate_raw, candidate = checked_source_manifest(members, 'postimages', CANDIDATE_SHA256, 30)
    require(set(candidate['files']) == set(baseline['files']) | {'owner_acquisition_v2.py'},
            'one new owner helper and the complete original source set')
    destination.mkdir()
    source = destination / 'source'
    source.mkdir()
    for name, reference in candidate['files'].items():
        if name == 'owner_acquisition_v2.py':
            body = members[name]  # The packet contains exactly one authoritative helper.
        elif name in POSTIMAGES:
            body = members['postimages/' + name]
        else:
            body = members['baseline-r8/' + name]
            require(reference == baseline['files'][name], 'unchanged original source reference: ' + name)
        require(len(body) == reference['bytes'] and digest(body) == reference['sha256'],
                'exact candidate source postimage: ' + name)
        (source / name).write_bytes(body)
    (source / 'SOURCE-MANIFEST.json').write_bytes(candidate_raw)
    (destination / 'CANDIDATE-STATUS.json').write_bytes(members['CANDIDATE-STATUS.json'])
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--out', type=pathlib.Path)
    args = parser.parse_args()
    members = verify_packet(args.inventory_sha256)
    # -I intentionally omits the script directory. Add only this verified packet.
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location('pocket4_storage_owner_v2_controls', ROOT / 'test_owner_v2.py')
    controls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controls)
    with tempfile.TemporaryDirectory(prefix='p4-owner-v2-source-') as temporary:
        temporary_path = pathlib.Path(temporary)
        controls.BASELINE = ROOT / 'baseline-r8'
        controls.CANDIDATE = replay_candidate(members, temporary_path / 'candidate-r36-v2-r2')
        suite = unittest.defaultTestLoader.loadTestsFromModule(controls)
        require(suite.countTestCases() == EXPECTED_TESTS, 'all 35 source cases discovered')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        require(result.testsRun == EXPECTED_TESTS and result.wasSuccessful() and not result.skipped and
                not result.expectedFailures and not result.unexpectedSuccesses,
                'all 35 source cases executed without failure, skip or expected-failure credit')
    require(not temporary_path.exists(), 'temporary candidate source tree removed')
    report = {
        'schema': 'p4-r36-owner-source-ci-v1',
        'scope': 'ordinary_source_replay_and_owner_format_tests',
        'packet_inventory_sha256': args.inventory_sha256,
        'baseline_source_manifest_sha256': BASELINE_SHA256,
        'candidate_source_manifest_sha256': CANDIDATE_SHA256,
        'source_members_replayed': 30, 'tests_run': result.testsRun, 'tests_skipped': 0,
        'ordinary_source_checks_passed': True, 'temporary_source_removed': True,
        'unresolved_required_slots': ['owner_acquisition.root_acceptance'],
        'unresolved_acceptance_semantics': ['original_lock_custody', 'source_review'],
        'owner_cas_publication_revalidated': False,
        'original_operation_bodies_in_packet': False,
        'original_lock_verified': False, 'source_review_verified': False,
        'owner_acquisition_acceptance_verified': False,
        'device_evidence_revalidated': False, 'owner_cas_root_verified': False,
        'new_storage_admitted': False, 'fresh_full_B_admitted': False,
        'Android_starts': 0, 'production_ready': False,
    }
    rendered = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered)
    print(rendered, end='')


if __name__ == '__main__':
    main()
