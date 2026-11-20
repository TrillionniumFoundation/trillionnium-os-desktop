"""Reproduce four source-only successors from exact published predecessor bytes."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = Path('/home/alex/work/p4-uid-mapping-consumer-20261120-3b9d-r1')
CHANGES = {
    'clock-remaining-runtime-inputs-20261108-8b88-r2': {
        'clock_protection.py': [
            ('info = os.fstat(fd)', 'info, mapped_owner = self.c.mapped_file_info(self.s.view, fd, UID)'),
            ('info.st_uid == info.st_gid == UID and info.st_ino',
             '(info.st_uid, info.st_gid) == mapped_owner and info.st_ino'),
        ],
        'clock_alarm_reader.py': [
            ('value = os.fstat(fd)', 'value, mapped_owner = session.c.mapped_file_info(session.view, fd, UID)'),
            ('value.st_uid == value.st_gid == UID,', '(value.st_uid, value.st_gid) == mapped_owner,'),
        ],
    },
    'ihg-5.111.1-r1': {
        'clock_protection.py': [
            ('info = os.fstat(fd)', 'info, mapped_owner = self.c.mapped_file_info(self.view, fd, UID)'),
            ('info.st_uid == info.st_gid == UID and info.st_ino',
             '(info.st_uid, info.st_gid) == mapped_owner and info.st_ino'),
        ],
    },
    'documents-saf11-runtime-inputs-20261108-8b88-r2': {
        'documents_saf_core.py': [
            ('info = os.fstat(fd)', 'info, mapped_owner = session.c.mapped_file_info(session.view, fd, uid)'),
            ('info.st_uid == info.st_gid == uid and info.st_ino',
             '(info.st_uid, info.st_gid) == mapped_owner and info.st_ino'),
        ],
    },
    'documents-search-sort-runtime-inputs-20261108-8b88-r2': {
        'documents_package_fixture.py': [
            ('info = os.fstat(fd)', 'info, mapped_owner = session.c.mapped_file_info(session.view, fd, uid)'),
            ('info.st_uid == info.st_gid == uid and info.st_ino',
             '(info.st_uid, info.st_gid) == mapped_owner and info.st_ino'),
        ],
    },
}


def pin(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def build(destination):
    predecessors = json.loads((HERE / 'inputs/predecessors.json').read_bytes())
    addition = (HERE / 'mapped_owner_addition.py').read_bytes()
    manifest = []
    for group, meta in predecessors.items():
        old_raw = (HERE / 'inputs/preparations' / (group + '.json')).read_bytes()
        assert pin(meta['predecessor']['path'], old_raw) == meta['predecessor']
        preparation = json.loads(old_raw)
        files = []
        for ref in meta['files']:
            name = Path(ref['path']).name
            changed = name == 'app_common.py' or name in CHANGES[group]
            source = HERE / ('inputs/changed-originals' if changed else 'source') / group / name
            raw = source.read_bytes()
            assert pin(ref['path'], raw) == ref, 'Predecessor changed: ' + str(source)
            if name == 'app_common.py':
                raw += addition
            elif changed:
                text = raw.decode()
                for before, after in CHANGES[group][name]:
                    assert text.count(before) == 1, (group, name, before)
                    text = text.replace(before, after)
                raw = text.encode()
            target = destination / 'source' / group / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            files.append(pin(HOST / 'source' / group / name, raw))
        preparation['files'] = files
        preparation['origins'] = preparation['origins'] + [meta['predecessor']]
        preparation['source_rebind'] = {
            'previous': meta['predecessor'],
            'state': 'LIVE_HELD_MAIN_UID_GID_TRANSLATION_SOURCE_ONLY',
            'changed_files': sorted(['app_common.py', *CHANGES[group]]),
            'guest_PM_UIDs_preserved': True,
            'same_original_permission_business_and_cleanup_gates': True,
            'runtime_qualified': False,
            'whole_app_business_accepted': False,
        }
        target = destination / 'preparations' / (group + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = encode(preparation)
        target.write_bytes(raw)
        manifest.append({'index': meta['index'], 'preparation': pin(HOST / 'preparations' / target.name, raw)})
    (destination / 'PREPARATIONS.json').write_bytes(encode(sorted(manifest, key=lambda x: x['index'])))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=HERE)
    args = parser.parse_args()
    print(json.dumps(build(args.output), sort_keys=True))
