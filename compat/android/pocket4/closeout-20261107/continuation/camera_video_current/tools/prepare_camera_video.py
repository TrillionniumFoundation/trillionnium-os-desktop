#!/usr/bin/python3 -I
"""Create one exact Camera video source preparation; never admit runtime work.

The 29 reviewed modules are copied byte for byte. The existing entry and planner
validate the completed packet. Historical locations are documentary provenance;
every live source/origin reference is inside this newly created preparation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types

INVENTORY_SHA256 = '12c7591d2491d346cda679cd1f314cba375f54e6bab7809e6ab7352c4ec18181'
TESTED_ARCHIVE_SHA256 = '318bddb268df84955a2e4ce79b8c363066813d22e01a068f4ece7deb7299a434'
R4_MANIFEST_SHA256 = '963b8724906da54e70147b3a3268dd29640a85b45b947274fda7d5e61a55c5c4'
R4_PUBLICATION_SHA256 = '81083b43e21cdf0cf09167ba3ee3038af5e23b847579c73200aa685f05187a68'
KEYS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('ascii')


def identity(value):
    return {key: getattr(value, key) for key in KEYS}


def parse(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: need(False, 'NONFINITE_JSON'))


class Inputs:
    def __init__(self):
        self.rows = []

    def read(self, path, maximum=262144):
        path = Path(path)
        need(path.is_absolute() and path.resolve() == path, 'CANONICAL_INPUT_REQUIRED')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                 0 < before.st_size <= maximum, 'BOUNDED_SINGLE_LINK_INPUT')
            raw = bytearray()
            while len(raw) < before.st_size:
                block = os.read(fd, min(65536, before.st_size - len(raw)))
                need(bool(block), 'SHORT_INPUT_READ')
                raw.extend(block)
            need(os.read(fd, 1) == b'' and identity(before) == identity(os.fstat(fd))
                 == identity(path.lstat()), 'HELD_INPUT_CHANGED')
            self.rows.append((fd, path, identity(before)))
            return bytes(raw)
        except BaseException:
            os.close(fd)
            raise

    def verify(self):
        for fd, path, wanted in self.rows:
            need(identity(os.fstat(fd)) == identity(path.lstat()) == wanted,
                 'SOURCE_CHANGED_DURING_PREPARATION:' + str(path))

    def close(self):
        errors = []
        for fd, _, _ in reversed(self.rows):
            try:
                os.close(fd)
            except OSError as error:
                errors.append(error)
        self.rows.clear()
        need(not errors, 'PREPARATION_INPUT_CLOSE_FAILED')


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def load(raw, path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def inspect(preparation, entry):
    entry_raw = Path(entry).read_bytes()
    module = load(entry_raw, entry, 'camera_video_preparation_entry')
    args = argparse.Namespace(preparation=preparation['path'],
                              expect_preparation_sha256=preparation['sha256'])
    common, packet, ref, _ = module.bootstrap(args)
    witness = common.EvidenceWitness([ref])
    try:
        witness.verify()
        paths = sorted(row[1] for row in witness.rows)
        root = Path(preparation['path']).parent
        need(all(Path(path).is_relative_to(root) for path in paths),
             'SOURCE_PREPARATION_MUST_NOT_DEPEND_ON_OLD_DRAFTS')
        return {'schema': 'pocket4-camera-video-preparation-source-inspection-v1',
                'source_preparation': ref, 'source_files': len(packet['files']),
                'held_evidence_files': len(paths), 'live_dependency_paths': paths,
                'all_live_dependencies_under_preparation_root': True,
                'formal_entry_bootstrap_passed': True,
                'Main_actions': 0, 'Android_UI_actions': 0, 'actual_audio_stream_actions': 0,
                'runtime_qualified': False, 'whole_app_business_accepted': False}
    finally:
        witness.close()


def prepare(source, inventory, expected_sha256, output):
    source, inventory, output = map(Path, (source, inventory, output))
    need(expected_sha256 == INVENTORY_SHA256, 'EXACT_REVIEWED_29_MODULE_INVENTORY_REQUIRED')
    need(source.is_absolute() and source.resolve() == source and source.is_dir(),
         'CANONICAL_SOURCE_DIRECTORY_REQUIRED')
    need(output.is_absolute() and output.parent.resolve(strict=True) == output.parent,
         'CANONICAL_EXISTING_OUTPUT_PARENT_REQUIRED')
    need(not output.exists() and not output.is_symlink(), 'CREATE_ONLY_PREPARATION_REQUIRED')
    held = Inputs()
    try:
        inventory_raw = held.read(inventory, 131072)
        need(sha(inventory_raw) == expected_sha256, 'REVIEWED_SOURCE_INVENTORY_CHANGED')
        model = parse(inventory_raw)
        need(model['schema'] == 'pocket4-reviewed-camera-video-source-inventory-v1'
             and model['source_count'] == len(model['files']) == 29
             and model['Android_execution_authorized_by_publication'] is False
             and model['whole_app_business_accepted'] is False, 'EXACT_SOURCE_INVENTORY_CONTRACT')
        wanted = {row['name']: row for row in model['files']}
        need(len(wanted) == 29 and {p.name for p in source.iterdir()} == set(wanted),
             'EXACT_29_SOURCE_DIRECTORY_MEMBERS_REQUIRED')
        files = {}
        for name, row in sorted(wanted.items()):
            need(set(row) == {'name', 'bytes', 'sha256'} and Path(name).name == name
                 and re.fullmatch('[a-z_]+[.]py', name) and type(row['bytes']) is int
                 and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'EXACT_SOURCE_INVENTORY_ROW')
            raw = held.read(source / name)
            need((len(raw), sha(raw)) == (row['bytes'], row['sha256']),
                 'REVIEWED_SOURCE_BYTES_CHANGED:' + name)
            files[name] = raw
        entry = load(files['camera_entry.py'], source / 'camera_entry.py', 'reviewed_camera_video_entry')
        need(set(files) == entry.SOURCE_NAMES, 'FORMAL_ENTRY_REQUIRES_THESE_EXACT_29_MODULES')
        held.verify()
        output.mkdir(mode=0o700)
        (output / 'source').mkdir(mode=0o700)
        references = [write_new(output / 'source' / name, raw) for name, raw in sorted(files.items())]
        inventory_ref = write_new(output / 'reviewed-source-inventory.json', inventory_raw)
        provenance = {'schema': 'pocket4-camera-video-prepared-source-provenance-v1',
            'source_inventory_sha256': expected_sha256, 'module_count': 29,
            'r4_manifest_sha256': R4_MANIFEST_SHA256, 'r4_publication_sha256': R4_PUBLICATION_SHA256,
            'previously_tested_archive_sha256': TESTED_ARCHIVE_SHA256,
            'exact_source_bytes_match_previously_tested_candidate': False,
            'source_merge_parents': {
                'canonical_source_commit': 'f9c506431b389c941fbb05f5875166fcd8a7b763',
                'r4_source_controls_commit': 'a355e81a753cdc1aed198424d87d0a8b6e4b2ebc'},
            'previous_canonical_inventory_sha256':
                '2444a7f3dcbeace9a3a9c5b86d2fc815a59ae965b626ddb80ba99b6f4d13520f',
            'previous_combined_inventory_sha256':
                '28e61371c50638a3ac33d4e28b0466754bc2b81c9f5d015f262d43e60243dd00',
            'prior_host_qualification_transferred': False,
            'current_host_qualification': 'pending_for_exact_merged_source_bytes',
            'historical_locations_are_documentary_only': True, 'old_runtime_authority_transferred': False,
            'inputs': [{'original_path': str(path), 'identity': ident} for _, path, ident in held.rows],
            'runtime_qualified': False, 'whole_app_business_accepted': False}
        provenance_ref = write_new(output / 'source-provenance.json', canonical(provenance))
        held.verify()
        packet = {'schema': 'pocket4-current-camera-video-preparation-v1',
            'code_entrypoints_complete': True, 'files': references,
            'origins': [inventory_ref, provenance_ref],
            'source_inventory_sha256': expected_sha256,
            'Android_execution_authorized_by_publication': False,
            'Main_admission_authorized': False, 'whole_app_business_accepted': False,
            'runtime_qualified': False, 'camera_recovery_qualified': False,
            'camera_recovery_preparation_pending': True, 'display_lease_outer_pending': True,
            'pending': ['reviewed recovery source scope and outer display integration',
                        'fresh deployed Main epoch and exact installed Camera/Player/helper identities',
                        'real locked display lease and independent normal release evidence',
                        'current acoustic capture, full decode and same owned URI playback',
                        'whole Camera business qualification and visual review'],
            'Main_actions': 0, 'Android_UI_actions': 0, 'actual_audio_stream_actions': 0}
        preparation = write_new(output / 'preparation.json', canonical(packet))
        inspection = inspect(preparation, output / 'source/camera_entry.py')
        held.verify()
        inspection_ref = write_new(output / 'source-inspection.json', canonical(inspection))
        return {'preparation': preparation, 'inspection': inspection_ref,
                'source_files': 29, 'runtime_qualified': False,
                'whole_app_business_accepted': False}
    finally:
        held.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--expect-inventory-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.source, args.inventory, args.expect_inventory_sha256, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
