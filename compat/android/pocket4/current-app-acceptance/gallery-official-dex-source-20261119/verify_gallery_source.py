#!/usr/bin/env python3
"""Check actual official Gallery DEX source evidence without APK or runtime access."""
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

HERE = Path(__file__).resolve().parent
PREFIX = 'compat/android/pocket4/current-app-acceptance/'
DEPENDENCIES = {
    'source_receipt': (PREFIX + 'system-cp3a-source-adapter-20261119/inputs/official-gallery-source-receipt.json',
        326611, 'e0326b9a0f8acc599cf7ef1190cc03c967a5578e34efcdba55cc0f3f46f932ad'),
    'old_verifier_source': (PREFIX + 'system-cp3a-source-adapter-20261119/originals/gallery-new-runtime-preparation-20261107-r7/gallery_current_verify.py',
        16785, 'f7438c04a18e30333ffb6a5db081e304a127baf1deebdd2519be57045063033f'),
    'current_provider_cohort': (PREFIX + 'system-cp3a-provider-source-20261119/current/CURRENT-CP3A-PROVIDER-COHORT.json',
        71046, '487e747cec5d158052e9ad9e0e2c2beec3115a6f0d69594ad84941b438aed8ea'),
}
ACTUAL = {
    'actual/RESULT.json': (5644, 'e5682f9cd9fa8356755c4a21c0f09d1ec1fbb9d6816799932fb64f0301d19d17'),
    'actual/CLASS-DESCRIPTORS.json': (119880, '48784ff0a225c9319f685c86b44772d2240809a857686965aab3cdbe8b0d265e'),
    'actual/DEX-SOURCE-INVENTORY.json': (126819, '147509fe23c352a40a2db88fcc9e69b0e66eaf6018edf148150ea1849d087649'),
    'source/official_dex_inventory.py': (20841, '66fe0220ae81a8cf359acf7fc21cc1d2b66d740e41ee352ba6a52e9285278031'),
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(root, relative, expected=None):
    rel = PurePosixPath(relative)
    need(not rel.is_absolute() and str(rel) == relative and '..' not in rel.parts,
         'fixed relative metadata path')
    path = root / relative
    info = path.lstat()
    need(path.resolve() == path and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
         and info.st_size <= 1024 * 1024, 'bounded ordinary metadata')
    body = path.read_bytes()
    if expected:
        need((len(body), hashlib.sha256(body).hexdigest()) == expected, 'full metadata size/SHA mismatch')
    return body


def assignment(raw, name):
    matches = [node for node in ast.parse(raw).body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    need(len(matches) == 1, 'exact historical source assignment')
    return ast.literal_eval(matches[0].value)


def main():
    names = {}
    for line in read(HERE, 'FILES.sha256').decode('ascii').splitlines():
        sha, name = line.split('  ', 1)
        need(name not in names and re.fullmatch('[0-9a-f]{64}', sha), 'unique packet member')
        need(hashlib.sha256(read(HERE, name)).hexdigest() == sha, 'packet member hash')
        names[name] = sha
    actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file()}
    need(actual == set(names) | {'FILES.sha256'}, 'complete exact packet inventory')
    raw = {name: read(HERE, name, pin) for name, pin in ACTUAL.items()}
    deps = {key: read(HERE.parents[4], pin[0], pin[1:]) for key, pin in DEPENDENCIES.items()}
    result = json.loads(raw['actual/RESULT.json'])
    inventory = json.loads(raw['actual/DEX-SOURCE-INVENTORY.json'])
    descriptors = json.loads(raw['actual/CLASS-DESCRIPTORS.json'])
    source = json.loads(deps['source_receipt'])
    cohort = json.loads(deps['current_provider_cohort'])
    need(result['success'] is True and result['state'] == 'OFFICIAL_DEX_SOURCE_INVENTORIED_ART_AND_BUSINESS_PENDING',
         'actual successful static source inventory')
    need(result['APK'] == source['apk'] and result['full_GSI'] == source['source_image'] == cohort['full_GSI'],
         'same original Gallery APK and full CP3A image')
    need(result['source_worker']['sha256'] == ACTUAL['source/official_dex_inventory.py'][1] and
         result['original_source_receipt']['sha256'] == DEPENDENCIES['source_receipt'][2],
         'actual worker and source receipt binding')
    need(result['class_definition_count'] == inventory['class_definition_count'] ==
         len(descriptors) == len(set(descriptors)) == 2144 and
         descriptors == sorted(descriptors) == inventory['all_class_descriptors'], 'complete actual official class set')
    names_pin = assignment(deps['old_verifier_source'], 'NAMES_REF')
    need((names_pin['bytes'], names_pin['sha256']) == ACTUAL['actual/CLASS-DESCRIPTORS.json'] and
         assignment(deps['old_verifier_source'], 'DEX_SHA') ==
         '6a994fabd3494dcbf071d727922351f72ff8fdbee0d3d3c1a46b6ed30ca034ee',
         'only the identical class-name data can transfer from historical verifier')
    dex_members = [row for row in source['zip_members'] if row['name'] == 'classes.dex']
    need(len(dex_members) == 1 and dex_members[0]['bytes'] == inventory['dex']['bytes'] == 1857660 and
         dex_members[0]['sha256'] == inventory['dex']['sha256'] == result['DEX']['sha256'] ==
         '725ac7153e9ab4a9742672c238fc140bda311e6c940daf9e1d10a2b26c33e829', 'official DEX source identity')
    need(inventory['static_class_table_complete'] is True and result['selected_method_count'] == 2 and
         len(inventory['selected_methods']) == 2, 'actual selected methods and complete class table')
    for method in inventory['selected_methods']:
        need(method['access_flags'] == 1 and method['instruction_code_units'] * 2 == method['instruction_bytes'] and
             method['header_and_instruction_bytes'] == method['instruction_bytes'] + 16 and
             method['exceptions_debug_and_annotations_included_in_method_hash'] is False and
             method['instructions_disassembled_or_executed'] is False and
             method['ART_or_method_behavior_qualified'] is False, 'exact limited method hash scope')
    for value in (result, inventory):
        for flag in ('ART_qualified', 'method_behavior_qualified', 'installed',
                     'runtime_qualified', 'business_qualified', 'production_ready'):
            need(value[flag] is False, 'source cannot grant ' + flag)
    need(result['old_modified_APK_ART_or_method_credit_transferred'] is False and
         result['new_APK_or_DEX_copies_written'] == result['SDK_commands'] ==
         result['child_processes_spawned'] == result['Android_actions'] == result['user_data_reads'] == 0,
         'read-only source scope')
    need(len(result['input_bookends']) == 3 and all(row['F9_and_SHA_equal'] is True for row in result['input_bookends'])
         and len(result['actual_negative_controls']) == 5 and
         all(row['rejected'] is True for row in result['actual_negative_controls']), 'actual source controls and bookends')
    media = cohort['provider_cohort']['com.android.providers.media.module']
    need(media['source_identity_verified'] is True and media['current_APK']['sha256'] ==
         'aff897cc1f56583cd71c4cf48330eb4514fdefbd54f069e55223bd31e7af305b' and
         media['semantic_cleanup_qualified'] is False and media['actual_UID'] is None,
         'current MediaProvider source is known; semantics and actual UID remain pending')
    execution = json.loads(read(HERE, 'actual/execution.json'))
    retirement = json.loads(read(HERE, 'actual/retirement.json'))
    need(execution['status']['exit_code'] == retirement['status']['exit_code'] == 0 and
         execution['output_complete'] is retirement['output_complete'] is True, 'complete actual host observations')
    retired = json.loads(retirement['text'])
    need(retired['all_original_units_retired'] is True and len(retired['units']) == 2 and
         all(row['cgroup_exists'] is False and 'LoadState=not-found' in row['stdout'] and
             'ExecMainPID=0' in row['stdout'] for row in retired['units']), 'original host units retired')
    refusal = json.loads(read(HERE, 'history/affinity-refusal.json'))
    refusal_retirement = json.loads(read(HERE, 'history/affinity-refusal-retirement.json'))
    need(refusal['status']['exit_code'] == 1 and refusal['output_complete'] is True and
         'single CPU31 affinity required' in refusal['text'] and
         json.loads(refusal_retirement['text'])['work_exists'] is False, 'original pre-input refusal preserved')
    print(json.dumps({'state': 'PASS_OFFICIAL_GALLERY_STATIC_SOURCE_RUNTIME_BLOCKED',
        'packet_files': len(names), 'actual_official_class_count': 2144,
        'exact_old_class_name_list_reusable': True, 'actual_source_method_identities': 2,
        'recorded_actual_static_negative_controls': 5, 'source_inputs_reopened_here': 3,
        'APK_or_DEX_bodies_read_here': 0, 'SDK_commands_executed_here': 0, 'Android_actions': 0,
        'ART_qualified': False, 'method_behavior_qualified': False, 'installed': False,
        'runtime_qualified': False, 'business_qualified': False, 'production_ready': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
