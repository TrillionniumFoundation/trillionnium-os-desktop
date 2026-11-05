#!/usr/bin/env python3
"""Create only candidate07 from candidate06 plus four include edits and one private UAPI header."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

HERE = Path('/home/alex/work/pocket4-candidate07-host-uapi-composition-source-01-20261105')
OWNER = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01')
PARENT = OWNER / 'overlay-reconstruction-10/candidate-06'
PARENT_MANIFEST = PARENT.parent / 'candidate-06-source-manifest.json'
PARENT_SHA = '3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376'
PARENT_COMPOSITION_SHA = 'f49173e0527e336f5d5ff5af489a2dfa97ceaba247f0fc3657c9a68ca242922a'
ROOT = OWNER / 'overlay-reconstruction-11'
DESTINATION = ROOT / 'candidate-07'
MANIFEST_SHA = 'e10024548a5b2b5a391ecc9ddb3ea2f19b95a6fea3437f40207a0f4721745a93'
BASE_CONTRACT_SHA = 'b42ee9229dfac7b62bb04472e39568867fc53d695389b2214c8bbfd9e0f83619'
GATE_ROOT = Path('/home/alex/work/pocket4-native-host-glibc-uapi-tu-control-01-20261105')
GATE_REPORT = GATE_ROOT / 'attempt01/result.json'
GATE_SHA = '5a09aa094c960a2bcc2d357fa732aac0cdb95203d25d3b690ced62497bb1c1d1'
GATE_CONTROLLER_SHA = 'dc1c91c1c0b84cdd8ca9e487fa7b043da66c0c0c5ce49c4706c55c71c17f48e3'
FAILED_INPUTS_SHA = '8206e05341acd16dccf6d5b0e8e3ad63d83ebc095842f5efbfea1dfdb7105b4d'
ANCESTRY = 'Host glibc2.17 UAPI declarations; exact five-TU compiler control separately pinned by candidate07 composition'
DELTA = {'engine/kernel_api/include/berberis/kernel_api/proc_maps_linux_compat.h': (None, '131d1eef8d9f789876c965fa2d827b21a59fc64ab7886fa1f78d95623114370c', 2072), 'engine/kernel_api/proc_maps_fd_owner.cc': ('b9ab891c0a09a04661bf4c9306978502094b08606c33d8ea2742f5eba3d29c5e', '35a4b8cb00d40f85e4173a74939222f189f21ee842df00d0bb21c2f441ac3d8a', 20989), 'engine/kernel_api/proc_maps_path.cc': ('48b0c85bdd0fb1b08b7e9478d7642ffe199d321c6bf80304eaba9c42f62b9765', 'fc2083c33c14b95b97d84f17c277bf077b005f72036f81f8ca399a03b21aaff7', 7082), 'engine/kernel_api/proc_maps_provenance.cc': ('f4e6685f5b689d3b408dc6aa7723e36b2174e6e2545e743fbb5c5896f6142137', 'a5954f296ac863d641f90973e231840cc8aba9ad88f60ae1631e1096e263df21', 32628), 'engine/kernel_api/proc_maps_raw_metadata_owner.cc': ('4400b1db44f3d7c46dd25136dba8599bc934f2ef28963c289cde1953960536a6', 'b8b8a2d4989082d244fd76287b03abc32e945535bc0676d63f1ea22787163427', 25457)}

def need(value, why):
    if not value:
        raise RuntimeError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, expected, bound):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= bound, 'regular source/bound mismatch')
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, min(32768, bound + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            need(size <= bound, 'source grew beyond bound')
        raw = b''.join(chunks)
        after = os.fstat(fd)
        named = Path(path).lstat()
        key = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        need(key(before) == key(after) == key(named) and size == before.st_size and sha(raw) == expected,
             'held source bytes/identity changed: ' + str(path))
        return raw
    finally:
        os.close(fd)


def load_source(name, expected):
    path = HERE / name
    raw = pinned(path, expected, 65536)
    scope = {'__name__': 'frozen_source_contract_only', '__file__': str(path)}
    exec(compile(raw, str(path), 'exec'), scope, scope)
    return scope


def proof_contract():
    # The old Android/host 26-case proof is validated by the exact unchanged
    # candidate06 source contract. It does not become a new runtime test here.
    raw = pinned(GATE_REPORT, GATE_SHA, 1048576)
    gate = json.loads(raw)
    pinned(GATE_ROOT / 'source/compile_tus.py', GATE_CONTROLLER_SHA, 65536)
    need(gate['state'] == 'PASS' and gate['baseline_reproduced'] is True and
         gate['full_engine_built'] is False and gate['objects_executed'] is False and
         gate['installed'] is False and gate['Main_actions'] == 0 and
         gate['sources_modified_outside_owned_root'] is False and
         gate['kernel_ABI_compatibility_runtime_not_claimed_by_compilation'] is True and
         not gate['input_changes'] and not gate['observed_signals'] and
         gate['owned_resource_gate']['pass'] is True,
         'actual complete TU proof or resource qualification differs')
    cleanup = gate['cleanup']
    need(not cleanup['forced_cleanup'] and not cleanup['remaining'] and not cleanup['errors'],
         'actual TU control cleanup incomplete')
    tus = ['proc_maps_provenance', 'proc_maps_raw_metadata_owner', 'proc_maps_fd_owner',
           'proc_maps_path', 'proc_maps_factory_wire']
    need([row['name'] for row in gate['compiled_TUs']] == tus and
         all(row['original_warning_target_and_sysroot_flags_preserved'] is True
             for row in gate['compiled_TUs']), 'complete original-flags TU set differs')
    labels = ['compiler-version', 'host-macros', 'preimage-provenance']
    for name in tus:
        labels += [name + '-dependencies', name + '-compile']
    commands = gate['commands']
    need([row['label'] for row in commands] == labels and
         all(not row['timed_out'] for row in commands), 'actual TU command set differs')
    need(commands[2]['returncode'] != 0 and commands[2]['expected_failure'] is True and
         all(row['returncode'] == 0 for i, row in enumerate(commands) if i != 2),
         'original missing-header negative or candidate compiles differ')
    dependencies = gate['actual_system_and_generated_dependencies']
    for name, (before, after, size) in DELTA.items():
        path = str(GATE_ROOT / 'source/candidate' / name[len('engine/'):])
        need(dependencies[path]['sha256'] == after and dependencies[path]['bytes'] == size,
             'new composition input was not an actual compiled input: ' + name)
        pinned(Path(path), after, size)
    return gate


def derive(parent):
    need(set(parent) == {'schema', 'files', 'ancestry'} and parent['schema'] == 1 and
         len(parent['files']) == len(parent['ancestry']) == 948, 'parent manifest schema differs')
    value = json.loads(json.dumps(parent))
    for name, (before, after, size) in DELTA.items():
        if before is None:
            need(name not in value['files'] and name not in value['ancestry'],
                 'new private header already exists in parent')
            value['ancestry'][name] = []
        else:
            need(value['files'][name] == before and value['ancestry'][name][-1]['sha256'] == before,
                 'delta preimage/ancestry differs')
        value['files'][name] = after
        value['ancestry'][name].append({'source': ANCESTRY, 'prior_sha256': before, 'sha256': after})
    raw = (json.dumps(value, indent=2) + '\n').encode()
    need(sha(raw) == MANIFEST_SHA and len(value['files']) == 949 and
         sum(name.startswith('engine/') for name in value['files']) == 926,
         'derived candidate07 manifest differs')
    return value, raw


def execute():
    need(os.getuid() == 1000 and os.geteuid() == 1000 and Path(__file__).absolute() == HERE / 'compose.py',
         'explicit operator/staged source required')
    os.umask(0o077)
    base = load_source('references/base-source-contract.py', BASE_CONTRACT_SHA)
    base['no_alias'](HERE)
    base['no_alias'](ROOT)
    need(not ROOT.exists(), 'candidate07 root exists; reconcile, never overwrite or retry')
    # This unchanged full-build contract validates candidate06's full inventory,
    # exact NOFILE host/Android proof, six signal files and matching builder450.
    parent_files = base['source_contract']()[0]
    parent_raw = pinned(PARENT_MANIFEST, PARENT_SHA, 524288)
    parent = json.loads(parent_raw)
    need(parent['files'] == parent_files, 'parent manifest/source contract differs')
    manifest, manifest_raw = derive(parent)
    gate = proof_contract()
    overrides = {}
    for name, (before, after, size) in DELTA.items():
        value = pinned(HERE / 'delta' / name[len('engine/'):], after, size)
        need(len(value) == size, 'delta size differs')
        overrides[name] = value
    ROOT.mkdir(mode=0o700)
    base['save'](ROOT / 'claim.json', {'schema': 1, 'state': 'COMPOSING_CANDIDATE07',
                 'parent_manifest_sha256': PARENT_SHA, 'expected_manifest_sha256': MANIFEST_SHA,
                 'changes': sorted(DELTA), 'started_utc': base['utc'](), 'automatic_retry': False})
    try:
        DESTINATION.mkdir(mode=0o700)
        for name, expected in manifest['files'].items():
            base['relative'](name)
            destination = DESTINATION / name
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if name in overrides:
                raw = overrides[name]
            else:
                raw = pinned(PARENT / name, expected, 8388608)
            need(sha(raw) == expected, 'source-copy input differs')
            with destination.open('xb') as stream:
                need(stream.write(raw) == len(raw), 'short new source write')
                stream.flush()
                os.fsync(stream.fileno())
            destination.chmod(0o444)
        need(base['hashes'](DESTINATION) == manifest['files'], 'candidate07 exact full inventory differs')
        need(base['source_contract']()[0] == parent_files and
             pinned(PARENT_MANIFEST, PARENT_SHA, 524288) == parent_raw,
             'original candidate06 or source authority changed during copying')
        proof_contract()
        for name, (before, after, size) in DELTA.items():
            pinned(HERE / 'delta' / name[len('engine/'):], after, size)
        with (ROOT / 'candidate-07-source-manifest.json').open('xb') as stream:
            need(stream.write(manifest_raw) == len(manifest_raw), 'short manifest write')
            stream.flush()
            os.fsync(stream.fileno())
        (ROOT / 'candidate-07-source-manifest.json').chmod(0o444)
        result = {'schema': 1, 'state': 'CANDIDATE07_COMPOSED_SOURCE_NOT_BUILT',
                  'finished_utc': base['utc'](), 'candidate': str(DESTINATION),
                  'manifest': str(ROOT / 'candidate-07-source-manifest.json'),
                  'manifest_sha256': MANIFEST_SHA, 'parent_manifest_sha256': PARENT_SHA,
                  'source_files': 949, 'engine_files': 926,
                  'changed_files': sorted(name for name, row in DELTA.items() if row[0] is not None),
                  'added_files': sorted(name for name, row in DELTA.items() if row[0] is None),
                  'unchanged_total_files': 944, 'unchanged_engine_files': 921,
                  'parent_and_authority_unchanged_after': True,
                  'parent_composition_sha256': PARENT_COMPOSITION_SHA,
                  'parent_NOFILE_host_and_Android_proof_revalidated': True,
                  'actual_complete_TU_gate_sha256': GATE_SHA,
                  'actual_original_missing_header_failure_reproduced': True,
                  'actual_complete_candidate_TUs': len(gate['compiled_TUs']),
                  'original_host_warning_target_and_sysroot_flags_preserved': True,
                  'all_five_composition_inputs_in_actual_compiled_dependencies': True,
                  'source_proof_files_root': str(HERE),
                  'original_candidate05_matched_gate_sha256': base['MATCHED_GATE_SHA'],
                  'matched_candidate05_gates_rerun_for07': False,
                  'NOFILE_Android_runtime_rerun_after_header_delta': False,
                  'feature_default_enabled': False, 'full_engine_built': False,
                  'ART_built': False, 'factory_built': False, 'installed': False,
                  'Main_actions': 0, 'Android_actions': 0, 'services_started': False, 'production_ready': False}
        base['save'](ROOT / 'candidate-07-composition-report.json', result)
        print(json.dumps({'state': result['state'], 'manifest_sha256': MANIFEST_SHA,
                          'report': str(ROOT / 'candidate-07-composition-report.json'),
                          'report_sha256': base['digest'](ROOT / 'candidate-07-composition-report.json')}), flush=True)
        return 0
    except BaseException as error:
        base['save'](ROOT / 'failure.json', {'state': 'COMPOSITION_FAILED', 'error': repr(error),
                     'source_copy_only': True, 'full_engine_built': False, 'Main_actions': 0})
        raise


if __name__ == '__main__':
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps({'state': 'PLAN_ONLY', 'root': str(ROOT), 'parent_manifest_sha256': PARENT_SHA,
                          'expected_manifest_sha256': MANIFEST_SHA, 'changes': sorted(DELTA),
                          'source_files': 949, 'engine_files': 926, 'actual_TU_gate_sha256': GATE_SHA,
                          'full_build_started': False, 'Main_actions': 0, 'remote_actions': 0}))
    else:
        raise SystemExit(execute())
