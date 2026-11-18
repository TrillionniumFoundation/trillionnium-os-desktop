"""Build a separate, deliberately unadmitted source candidate using ordinary files.

This performs no remote action and never reads CURRENT, root proofs or images.
It consumes the already observed full CURRENT reference; the missing owner/CAS
ROOT reference stays null. No old source file is modified.
"""
import argparse
import hashlib
import json
import pathlib
import secrets
import sys

from owner_acquisition_v2 import (CURRENT_BYTES, CURRENT_PATH, CURRENT_SHA256,
    FROZEN_R8_NONCE, GENERATION, validate_owner_record_v2, validate_acquisition_current_reference)

BASELINE_MANIFEST = '91772330fc4f500a6ed0961bf3b0ab5efcab3381a35de647c4470f0919f8fa11'
REVISION = 'r8-r36-v2-r1'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode()


def replace_exact(text, old, new, count=1):
    require(text.count(old) == count, 'exact frozen source occurrence: ' + old)
    return text.replace(old, new)


def verified_current_reference(observation):
    require(type(observation) is dict and observation.get('opened_no_follow') is True and
            observation.get('fd_and_path_bookends_equal') is True,
            'actual original no-follow CURRENT read with unchanged fd/path bookends')
    require(all(key in observation for key in ('path', 'bytes', 'sha256', 'identity')),
            'complete actually observed CURRENT reference')
    reference = {key: observation[key] for key in ('path', 'bytes', 'sha256', 'identity')}
    return validate_acquisition_current_reference(reference)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=pathlib.Path, required=True)
    parser.add_argument('--projection', type=pathlib.Path, required=True)
    parser.add_argument('--origin', type=pathlib.Path, required=True)
    parser.add_argument('--current-f9', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest_raw = (args.baseline / 'SOURCE-MANIFEST.json').read_bytes()
    require(hashlib.sha256(manifest_raw).hexdigest() == BASELINE_MANIFEST, 'exact frozen R8 source manifest')
    manifest = json.loads(manifest_raw)
    bodies = {name: (args.baseline / name).read_bytes() for name in manifest['files']}
    require(all(len(bodies[name]) == ref['bytes'] and hashlib.sha256(bodies[name]).hexdigest() == ref['sha256']
                for name, ref in manifest['files'].items()), 'all frozen R8 source bytes')
    projection = json.loads(args.projection.read_bytes())
    origin = json.loads(args.origin.read_bytes())
    current_reference = verified_current_reference(json.loads(args.current_f9.read_bytes()))
    require(origin['path'] == CURRENT_PATH and origin['size'] == CURRENT_BYTES and
            origin['sha256'] == CURRENT_SHA256 and origin['projection_read_complete'] is True,
            'ordinary observed source for the exact owner projection')
    owner, record = projection['foreground_owner'], projection['foreground_owner_acquisition_current']
    record_result = validate_owner_record_v2(owner, record)
    old = json.loads(bodies['contract.json'])
    require(record['superseded_acquisition_record'] == old['owner_acquisition']['record'] and
            record['superseded_owner'] == dict(old['owner_acquisition']['owner'], generation='20261117-e6ac-r35'),
            'full native-integer R34 history retained exactly')
    contract = json.loads(bodies['contract.json'])
    nonce = secrets.token_hex(32)
    require(nonce not in (FROZEN_R8_NONCE, old['immediate_predecessor']['nonce'], old['offline_ancestor']['nonce']),
            'fresh generation nonce')
    contract['generation'] = GENERATION
    contract['nonce'] = nonce
    contract['owner_acquisition_id'] = owner['acquisition_id']
    contract['owner_acquisition'] = {'owner': owner, 'record': record,
                                     'current': current_reference, 'root_acceptance': None}
    contract['superseded_foreground_owner'] = record['superseded_owner']
    active_paths = ('p4_source', 'desktop_source', 'p4_root', 'desktop_root', 'mount_target',
                    'full_source_dir', 'import_source_dir', 'incoming_admission_path', 'export_name')
    for key in active_paths:
        require('-r8' in contract[key], 'old active source token: ' + key)
        contract[key] = contract[key].replace('-r8', '-' + REVISION)
    for key in ('rotation_inputs_paths', 'incoming_rotation_paths', 'role_units'):
        for name, value in contract[key].items():
            require('-r8' in value, 'old active mapping token: ' + key + '.' + name)
            contract[key][name] = value.replace('-r8', '-' + REVISION)
    for role in ('server', 'controller', 'client', 'ssh', 'finalize'):
        contract[role + '_unit'] = contract[role + '_unit'].replace('-r8.', '-' + REVISION + '.')
        contract[role + '_description'] = contract[role + '_description'].replace(' r8 ', ' ' + REVISION + ' ').replace(old['nonce'], nonce)
    bodies['contract.json'] = encoded(contract)
    rotation = bodies['rotation_support.py'].decode()
    rotation = replace_exact(rotation, "'successor_storage_authority.py'):", "'successor_storage_authority.py', 'owner_acquisition_v2.py'):")
    rotation = replace_exact(rotation, '    IMMEDIATE_PREDECESSOR, OFFLINE_ANCESTOR)\n',
        '    IMMEDIATE_PREDECESSOR, OFFLINE_ANCESTOR)\nfrom owner_acquisition_v2 import validate_storage_owner_v2, FROZEN_R8_NONCE\n')
    rotation = replace_exact(rotation, "contract['generation'] == 'e6ac-storage-r8'", "contract['generation'] == " + repr(GENERATION))
    begin = rotation.index("    acquisition = contract['owner_acquisition']\n")
    end = rotation.index("    return {'total_seconds':", begin)
    rotation = rotation[:begin] + '    validate_storage_owner_v2(contract)\n' + rotation[end:]
    rotation = replace_exact(rotation, "contract['nonce'] not in (contract['immediate_predecessor']['nonce'], contract['offline_ancestor']['nonce'])",
        "contract['nonce'] not in (contract['immediate_predecessor']['nonce'], contract['offline_ancestor']['nonce'], FROZEN_R8_NONCE)")
    rotation = replace_exact(rotation, 'Finite r8 storage', 'Finite independent R36-source storage')
    rotation = replace_exact(rotation, 'new finite r8 storage;', 'new finite R36-source storage;')
    rotation = replace_exact(rotation, "'p4-r8-preserved-image-lineage-v2'", "'p4-r36-source-preserved-image-lineage-v2'")
    bodies['rotation_support.py'] = rotation.encode()
    prepare = bodies['prepare.py'].decode()
    for old_token, new_token, count in (
        ('e6ac-r8.tar.xz', 'e6ac-' + REVISION + '.tar.xz', 2),
        ('production400-storage-source-r8', 'production400-storage-source-' + REVISION, 1),
        ('p4-production651-nbd-storage-source-e6ac-r8', 'p4-production651-nbd-storage-source-e6ac-' + REVISION, 1),
        ("'e6ac-storage-r8'", repr(GENERATION), 1),
        ('p4-storage-r8-', 'p4-storage-' + REVISION + '-', 3),
    ):
        prepare = replace_exact(prepare, old_token, new_token, count)
    prepare = replace_exact(prepare, "contract = json.loads(entries['contract.json'])\n",
        "contract = json.loads(entries['contract.json'])\nowner_validator = {'__name__': 'sealed_pure_owner_acquisition_v2'}\n"
        "exec(compile(entries['owner_acquisition_v2.py'], 'owner_acquisition_v2.py', 'exec'), owner_validator)\n"
        "owner_validator['validate_storage_owner_v2'](contract)  # Before any target/proof writes.\n")
    bodies['prepare.py'] = prepare.encode()
    bodies['owner_acquisition_v2.py'] = pathlib.Path(__file__).with_name('owner_acquisition_v2.py').read_bytes()
    for name, body in bodies.items():
        require(len(body) < 65536, 'unchanged seal member limit: ' + name)
        if name.endswith('.py'):
            compile(body, name, 'exec')
    new_manifest = dict(manifest, files={name: {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
                                       for name, body in sorted(bodies.items())})
    new_manifest_raw = encoded(new_manifest)
    bodies['SOURCE-MANIFEST.json'] = new_manifest_raw
    status = {'schema': 'p4-r36-owner-source-candidate-status-v1',
              'baseline_manifest_sha256': BASELINE_MANIFEST,
              'candidate_manifest_sha256': hashlib.sha256(new_manifest_raw).hexdigest(),
              'generation': GENERATION, 'nonce': nonce,
              'owner_record_consistency': record_result,
              'unresolved_required_slots': ['owner_acquisition.root_acceptance'],
              'acquisition_current_reference_actual_read_verified': True,
              'owner_cas_root_reference_verified': False,
              'retirement_reference_read': False, 'candidate_can_seal_or_admit': False,
              'source_files': len(new_manifest['files']), 'contract_bytes': len(bodies['contract.json']),
              'new_storage_starts': 0, 'Full_B_starts': 0, 'Android_starts': 0, 'production_ready': False}
    args.output.mkdir()  # Create-only; never overwrite an old or competing source generation.
    source = args.output / 'source'
    source.mkdir()
    for name, body in sorted(bodies.items()):
        with (source / name).open('xb') as stream:
            stream.write(body)
    with (args.output / 'CANDIDATE-STATUS.json').open('xb') as stream:
        stream.write(encoded(status))
    print(json.dumps(status, sort_keys=True))


if __name__ == '__main__':
    main()
