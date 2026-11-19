#!/usr/bin/env python3
"""Materialize an isolated CP3A source adapter; never import a runtime runner.

Only fixed local JSON/source snapshots are read. Embedded host/APK/data paths
are evidence, never opened. The output is a source review candidate, not a
preparation accepted by an existing runtime bootstrap or an installation.
"""
import argparse
import ast
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

PINS = {
    'CURRENT-SOURCE-STATE.json': (157891, '4d25fc0aafd5668cc3f0c31be157bc617732902976aad821333a02de84ff9bf7'),
    'official-gsi-manifest.json': (12184, '8dff52f9abc8bd219266e1e85ba8cd3063677443aafc3efd90c4df9c8f04bfde'),
    'official-gallery-source-receipt.json': (326611, 'e0326b9a0f8acc599cf7ef1190cc03c967a5578e34efcdba55cc0f3f46f932ad'),
    'old-gallery-host-artifact-contract.json': (3978, 'c6fb3ad1c2ec673bab72ba3808418f140d0b73051627acdf6cccac34704beb2a'),
    'gallery_qpr1_artifacts.py': (14935, '0ed255b0f6668fcb6f3feae6c8ad2456e3540fbb184fa4522e2d8b58b0d961b8'),
    'old-gallery-method-observation.json': (2655, '86aa888d3a5e75977df7180977ef7284cccd93a0f9489ed2516fbd05f593e3d3'),
    'provider-metadata-observation.json': (1367, 'd3937ed9c58ab90ea3a52ed158461ced38448304900159e7e71ce98cfb6b3d29'),
    'preflight-r2-PLAN.json': (127403, '648559a6623a530d0c6ddf95662a2476c6fa50b90cebc7ed3d8ea99d93e48b43'),
    'preflight-r2-README.md': (12418, '916081e962299710c2dd8bed715323ad05127d5029c51359cf853f6a7bfc69ba'),
    'METADATA-CUSTODY.json': (3038, 'c5f49235efd85e01cb62cfea6d2d75f534d623a8801125b6e5d80a2b31997138'),
}
SOURCE_MANIFEST_PIN = (132175, 'dfe01692552abdb112575362e9ab80fb5b9782f1e7a878035b152198a2bec53d')
GSI_SHA = 'dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4'
CERT_PLATFORM = 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
CALENDAR = 'com.android.calendar'
CAMERA = 'com.android.camera2'
CONTACTS = 'com.android.contacts'
CLOCK = 'com.android.deskclock'
DOCUMENTS = 'com.android.documentsui'
GALLERY = 'com.android.gallery3d'
TARGETS = {
    CALENDAR: (2635213, 'c8a9d40dbfb3c975748e7c0520515316a5ef573414193e3128efa9ed400665e1',
               2520846, '726241395b485794badd1a1fdcef4298ebb284f67826d73a7e2648f2b7a5382e', 37, CERT_PLATFORM, 10061),
    CAMERA: (11892407, '0218041bc46f49c0c9622196e2a3610c641e0cc8f12386f23cdd88dc3a3ce18e',
             7709134, '24632b0e1a1c22741177583b0dfd4a3fa71ff9b1d1b72af60a3d7cf373c7e61f', 20002000, CERT_PLATFORM, 10062),
    CONTACTS: (11839391, '11f8be5fd46dd79ee4f7524d5d1334e21ce0f9e23892b2940a5b6091e2f349d0',
               11896473, 'f91e45e89b3a302198c9269a60bb07387150c0f40def95feb873b765520ae028', 10734,
               '28bbfe4a7b97e74681dc55c2fbb6ccb8d6c74963733f6af6ae74d8c3a6e879fd', 10055),
    CLOCK: (7597225, '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d',
            7665498, '9f24ea5fa57bca4a453556ab7cb44fbad1813cb3d15292a8e572cfb40fff7a77', 37, CERT_PLATFORM, 10063),
    DOCUMENTS: (None, '757feffc32440dd371eaab4fb91f45273a621ee45b848e2dc734b386ac6e2086',
                8923434, 'f7db1705178644333d5c9d291afd1170e71fcddfd1f73021381e1224be824899', 37,
                'c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8', 10022),
}
GALLERY_OFFICIAL = (7390425, '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439')
GALLERY_MODIFIED = (7493022, '6677d382076f10f0502c813c7614c32127ccf3cd8f02756b75a8c3574980e87e')
OFFICIAL_DEX = (1857660, '725ac7153e9ab4a9742672c238fc140bda311e6c940daf9e1d10a2b26c33e829')
MODIFIED_DEX = (1886696, '6a994fabd3494dcbf071d727922351f72ff8fdbee0d3d3c1a46b6ed30ca034ee')
B = 'business-system-cases-runtime-inputs-20261108-8b88-r2'
C = 'calendar-reminder-runtime-inputs-20261108-8b88-r2'
P = 'camera-app-photo-preparation-resume-20261107-r4'
K = 'clock-remaining-runtime-inputs-20261108-8b88-r2'
I = 'ihg-5.111.1-r1'
D = 'documents-saf11-runtime-inputs-20261108-8b88-r2'
S = 'documents-search-sort-runtime-inputs-20261108-8b88-r2'
G = 'gallery-new-runtime-preparation-20261107-r7'
R = 'gallery-rotation-current-preparation-20261107-r7'
V = 'gallery-album-current-preparation-20261107-r6'

# Each tuple gives exact expected occurrences of the old hash and old byte size.
# Constant substitutions do not alter UIDs, selectors, paths, limits or control flow.
LITERAL_RECIPES = {
    B + '/system_profiles.py': [(CONTACTS, 1, 1), (CALENDAR, 1, 1)],
    B + '/contacts_model.py': [(CONTACTS, 1, 1)],
    B + '/contacts_trial.py': [(CONTACTS, 1, 1)],
    B + '/calendar_base.py': [(CALENDAR, 1, 0)],
    B + '/calendar_core.py': [(CALENDAR, 1, 0)],
    C + '/system_profiles.py': [(CALENDAR, 1, 1)],
    C + '/calendar_base.py': [(CALENDAR, 1, 0)],
    C + '/calendar_core.py': [(CALENDAR, 1, 0)],
    P + '/camera_profiles.py': [(CAMERA, 1, 1)],
    K + '/clock_profiles.py': [(CLOCK, 1, 1)],
    K + '/clock_protection.py': [(CLOCK, 1, 1)],
    I + '/app_profiles.py': [(CLOCK, 1, 1)],
    I + '/clock_guard.py': [(CLOCK, 0, 1)],
    I + '/clock_protection.py': [(CLOCK, 1, 1)],
    D + '/documents_profiles.py': [(DOCUMENTS, 1, 0)],
    D + '/documents_saf_core.py': [(DOCUMENTS, 1, 0)],
    S + '/documents_profiles.py': [(DOCUMENTS, 1, 0)],
    S + '/documents_package_fixture.py': [(DOCUMENTS, 1, 0)],
}
PROFILE_ASSIGNMENTS = {
    B + '/system_profiles.py': {'CONTACTS': CONTACTS, 'CALENDAR': CALENDAR},
    C + '/system_profiles.py': {'CALENDAR': CALENDAR},
    P + '/camera_profiles.py': {'CAMERA': CAMERA},
    K + '/clock_profiles.py': {'CLOCK': CLOCK},
    I + '/app_profiles.py': {'CLOCK': CLOCK},
    D + '/documents_profiles.py': {'DOCUMENTS': DOCUMENTS},
    S + '/documents_profiles.py': {'DOCUMENTS': DOCUMENTS},
}
GALLERY_GUARDS = {
    G + '/gallery_current_entry.py': ['main'],
    G + '/gallery_current_install.py': ['verify_art_receipt', 'execute'],
    G + '/gallery_current_verify.py': ['execute'],
    R + '/gallery_rotation_entry.py': ['main'],
    V + '/video_entry.py': ['main'],
}
GALLERY_REJECTION = 'CP3A_OFFICIAL_FULL_GSI_ONLY_OLD_MODIFIED_CANDIDATE_RUNTIME_ENTRY_RETIRED'
PROVIDER_DEPENDENCIES = {
    CALENDAR: ['com.android.providers.calendar'], CONTACTS: ['com.android.providers.contacts'],
    CAMERA: ['com.android.providers.media.module'], CLOCK: [],
    DOCUMENTS: ['com.android.externalstorage'], GALLERY: ['com.android.providers.media.module'],
}
RUNTIME_FIELDS = ('installed', 'runtime_qualified', 'business_qualified', 'production_ready',
                  'native_compatibility_qualified', 'execution_ready', 'execution_authorized',
                  'whole_app_business_accepted')
F9 = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


class AdmissionError(RuntimeError):
    pass


def need(value, reason):
    if not value:
        raise AdmissionError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def f9(value):
    return tuple(getattr(value, field) for field in F9)


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode()


def pairs_no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, 'DUPLICATE_JSON_KEY:' + key)
        value[key] = item
    return value


def parse(raw):
    def bad_constant(value):
        raise AdmissionError('NONFINITE_JSON:' + value)
    return json.loads(raw, object_pairs_hook=pairs_no_duplicates, parse_constant=bad_constant)


def read_fixed(root, relative, expected):
    """Read one bounded regular file with every local path component no-follow."""
    path = PurePosixPath(relative)
    need(not path.is_absolute() and str(path) == relative and '..' not in path.parts,
         'FIXED_RELATIVE_INPUT_REQUIRED')
    fds = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(directory)
        for part in path.parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            fds.append(directory)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        fds.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == expected[0]
             and 0 <= before.st_size <= 1024 * 1024, 'INPUT_TYPE_OR_LENGTH:' + relative)
        chunks = []; count = 0
        while count <= expected[0]:
            chunk = os.read(fd, min(65536, expected[0] + 1 - count))
            if not chunk:
                break
            chunks.append(chunk); count += len(chunk)
        raw = b''.join(chunks)
        need(count == expected[0] and sha(raw) == expected[1], 'INPUT_PIN:' + relative)
        named = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        need(f9(before) == f9(os.fstat(fd)) == f9(named), 'INPUT_BOOKEND:' + relative)
        return raw, f9(before)
    finally:
        for fd in reversed(fds):
            os.close(fd)


def load_bundle(root):
    metadata = {}; books = {}
    for name, expected in PINS.items():
        metadata[name], books['inputs/' + name] = read_fixed(root, 'inputs/' + name, expected)
    raw, books['ORIGINAL-SOURCE-MANIFEST.json'] = read_fixed(root, 'ORIGINAL-SOURCE-MANIFEST.json', SOURCE_MANIFEST_PIN)
    manifest = parse(raw)
    need(manifest['source_only'] is True and manifest['Android_calls'] == 0
         and len(manifest['source_files']) == 224 and len(manifest['preparation_bookends']) == 11,
         'EXACT_ORIGINAL_SNAPSHOT_SCOPE')
    sources = {}; references = {}
    for row in manifest['source_files']:
        local = row['local']
        need(local.startswith('originals/') and PurePosixPath(local).suffix in ('.py', '.java', '.xml', '.json'),
             'ORIGINAL_SOURCE_LOCATION')
        relative = local[len('originals/'):]
        need(relative not in sources, 'DUPLICATE_ORIGINAL_SOURCE')
        reference = row['origin']
        sources[relative], books[local] = read_fixed(root, local, (reference['bytes'], reference['sha256']))
        references[relative] = row
    need(len(sources) == 224, 'EXACT_224_ORIGINAL_SOURCES')
    return {'metadata_raw': metadata, 'docs': {name: parse(value) for name, value in metadata.items()
            if name.endswith('.json')}, 'sources': sources, 'source_references': references,
            'source_manifest': manifest, 'bookends': books}


def bookend(root, bundle):
    expected = {'inputs/' + name: value for name, value in PINS.items()}
    expected['ORIGINAL-SOURCE-MANIFEST.json'] = SOURCE_MANIFEST_PIN
    expected.update({'originals/' + name: (len(raw), sha(raw)) for name, raw in bundle['sources'].items()})
    for name, value in expected.items():
        _, actual = read_fixed(root, name, value)
        need(actual == bundle['bookends'][name], 'SOURCE_CHANGED_DURING_GENERATION:' + name)


def assignment(tree, name):
    found = [node.value for node in tree.body if isinstance(node, ast.Assign)
             and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name]
    need(len(found) == 1, 'ONE_STATIC_ASSIGNMENT:' + name)
    return found[0]


def dictionary_value(node, key):
    need(isinstance(node, ast.Dict), 'STATIC_PROFILE_DICT_REQUIRED')
    values = [value for field, value in zip(node.keys, node.values)
              if isinstance(field, ast.Constant) and field.value == key]
    need(len(values) == 1, 'ONE_STATIC_PROFILE_FIELD:' + key)
    return values[0]


def metadata_contract(bundle):
    docs = bundle['docs']; state = docs['CURRENT-SOURCE-STATE.json']; gsi = docs['official-gsi-manifest.json']
    rows = {row['package']: row for row in state['applications']}
    need(len(rows) == len(state['applications']) == 39 and state['required_count'] == 39,
         'EXACT_REQUIRED39_SOURCE_STATE')
    need(state['individual_system_APK_installation_allowed'] is False and state['installed'] is False
         and state['runtime_qualified'] is False and state['production_ready'] is False,
         'SOURCE_STATE_CANNOT_ADMIT_INSTALL_OR_RUNTIME')
    image = state['full_GSI_dependency']
    need((image['bytes'], image['sha256']) == (2294853632, GSI_SHA), 'CURRENT_FULL_GSI_IDENTITY')
    profile = gsi['profile']; build = profile['build_identity']
    need(gsi['binary_inputs_verified'] is True and gsi['runtime_qualified'] is False
         and gsi['production_ready'] is False and build['id'] == 'CP3A.260905.010'
         and build['incremental'] == '16176746' and build['sdk'] == 37
         and build['security_patch'] == '2026-09-05', 'EXACT_CP3A_BINARY_METADATA')
    members = {row['name']: row for row in profile['archive_members']}
    need((members['system.img']['bytes'], members['system.img']['sha256']) == (image['bytes'], image['sha256'])
         and members['build.prop']['sha256'] == '810fc1db84f7ae7574598a02496610e0b808c9f495fed61fe4b180662f549fac',
         'STATE_GSI_MANIFEST_CHAIN')
    selected = {}
    for package, target in TARGETS.items():
        row = rows[package]; source = row['unchanged_original_system_record']
        need(row['kind'] == 'system' and row['source_identity_verified'] is True
             and source['source_identity_verified'] is True and source['package'] == package,
             'QUALIFIED_CURRENT_SYSTEM_SOURCE:' + package)
        need(all(row.get(key) is False for key in ('installed', 'runtime_qualified', 'business_qualified', 'production_ready'))
             and row['individual_APK_install_authorized'] is False
             and row['install_mode'] == 'coherent_full_GSI_with_framework_and_native_dependencies',
             'SYSTEM_SOURCE_ONLY:' + package)
        need((source['apk']['bytes'], source['apk']['sha256'], source['version_code']) == (target[2], target[3], target[4])
             and source['signer_certificate_sha256'] == [target[5]], 'CURRENT_TARGET_PIN_OR_SIGNER:' + package)
        need(source['image_path'].startswith('/system/') and source['source_receipt']['sha256'],
             'IMAGE_BOUND_TARGET_SOURCE:' + package)
        selected[package] = source
    gallery_row = rows[GALLERY]; gallery = gallery_row['unchanged_original_system_record']
    need(gallery_row['individual_APK_install_authorized'] is False and gallery_row['source_identity_verified'] is True
         and all(gallery_row[key] is False for key in ('installed', 'runtime_qualified', 'business_qualified', 'production_ready')),
         'GALLERY_SOURCE_ONLY_REQUIRED')
    receipt = docs['official-gallery-source-receipt.json']; old = docs['old-gallery-host-artifact-contract.json']
    need((gallery['apk']['bytes'], gallery['apk']['sha256']) == GALLERY_OFFICIAL
         and receipt['apk'] == gallery['apk'] and receipt['source_image'] == image
         and receipt['original_image_path'] == gallery['image_path'] == '/system/product/app/Gallery2/Gallery2.apk'
         and receipt['source_identity_verified'] is True and receipt['independent_APK_crc_and_all_member_hashes_verified'] is True
         and receipt['signature_verified_for_api'] == 37 and receipt['package'] == GALLERY
         and receipt['signer_certificate_sha256'] == gallery['signer_certificate_sha256'] == [CERT_PLATFORM]
         and all(receipt[key] is False for key in ('installed', 'runtime_qualified', 'production_ready', 'native_execution_qualified')),
         'OFFICIAL_GALLERY_SOURCE_RECEIPT_CHAIN')
    need((gallery['source_receipt']['bytes'], gallery['source_receipt']['sha256']) == PINS['official-gallery-source-receipt.json'],
         'GALLERY_RECEIPT_PIN_LINK')
    dex = [row for row in receipt['zip_members'] if row['name'] == 'classes.dex']
    need(len(dex) == 1 and (dex[0]['bytes'], dex[0]['sha256']) == OFFICIAL_DEX
         and dex[0]['complete_eof_crc_verified'] is True, 'OFFICIAL_GALLERY_DEX_METADATA')
    need((old['current_candidate']['bytes'], old['current_candidate']['sha256']) == GALLERY_MODIFIED
         and old['official_APK_sha256'] == gallery['apk']['sha256'] and old['official_image_sha256'] == GSI_SHA,
         'OLD_GALLERY_CANDIDATE_IS_NOT_OFFICIAL_BASELINE')
    old_code = ast.parse(bundle['metadata_raw']['gallery_qpr1_artifacts.py'])
    need(ast.literal_eval(assignment(old_code, 'MODIFIED_METHODS')) == [
        ['com/android/gallery3d/exif/ExifInterface.smali', 'public rewriteExif(Ljava/lang/String;Ljava/util/Collection;)Z'],
        ['com/android/gallery3d/ui/MenuExecutor$MediaOperation.smali', 'public run(Lcom/android/gallery3d/util/ThreadPool$JobContext;)Ljava/lang/Void;']],
        'EXACT_HISTORICAL_MODIFIED_METHOD_NAMES')
    methods = docs['old-gallery-method-observation.json']
    need((methods['bytes'], methods['sha256']) == (old['documents']['build']['bytes'], old['documents']['build']['sha256'])
         and (methods['new_DEX_bytes'], methods['new_DEX_sha256']) == MODIFIED_DEX
         and [[r['class'], r['replaced_method']] for r in methods['method_port']] == ast.literal_eval(assignment(old_code, 'MODIFIED_METHODS')),
         'OLD_GALLERY_METHOD_METADATA_CHAIN')
    need(OFFICIAL_DEX != MODIFIED_DEX and GALLERY_OFFICIAL != GALLERY_MODIFIED, 'GALLERY_MISMATCH_MUST_REMAIN_EXPLICIT')
    selected[GALLERY] = gallery
    providers = docs['provider-metadata-observation.json']
    need(providers['provider_APK_source_receipts_qualified_here'] == 0 and providers['all_current_provider_APK_pins'] is None,
         'NO_INFERRED_PROVIDER_APK_IDENTITY')
    old_plan = docs['preflight-r2-PLAN.json']
    need(old_plan['required_before_installation'] == state['required_before_installation']
         and old_plan['counts']['finite_prepared_case_packages'] == 7
         and old_plan['counts']['packages_without_selected_business_executor'] == 32
         and old_plan['counts']['target_identity_rebinds'] == 5, 'PRESERVE_REQUIRED39_PRIOR_GATES')
    return selected, image, profile


def apply_edits(raw, edits):
    edits = sorted(edits, key=lambda row: (row['start'], row['end']))
    last = -1
    for edit in edits:
        need(edit['start'] >= last and raw[edit['start']:edit['end']] == edit['before'].encode(),
             'NONOVERLAPPING_EXACT_SOURCE_EDIT')
        last = edit['end']
    for edit in reversed(edits):
        raw = raw[:edit['start']] + edit['after'].encode() + raw[edit['end']:]
    return raw


def span(raw, node):
    lines = raw.splitlines(keepends=True)
    return (sum(map(len, lines[:node.lineno - 1])) + node.col_offset,
            sum(map(len, lines[:node.end_lineno - 1])) + node.end_col_offset)


def change_targets(relative, raw):
    tree = ast.parse(raw); edits = []
    def replace(node, value, purpose):
        start, end = span(raw, node)
        edits.append({'start': start, 'end': end, 'line': node.lineno, 'before': raw[start:end].decode(),
                      'after': repr(value), 'purpose': purpose})
        node.value = value
    for package, hash_count, size_count in LITERAL_RECIPES[relative]:
        old_size, old_sha, new_size, new_sha, _, _, _ = TARGETS[package]
        for before, after, count, field in ((old_sha, new_sha, hash_count, 'sha256'), (old_size, new_size, size_count, 'bytes')):
            if before is None:
                need(count == 0, 'NO_INVENTED_OLD_SIZE'); continue
            matches = [node for node in ast.walk(tree) if isinstance(node, ast.Constant)
                       and type(node.value) is type(before) and node.value == before]
            need(len(matches) == count, 'EXACT_LITERAL_OCCURRENCES:' + relative + ':' + field)
            for node in matches:
                replace(node, after, package + ':' + field)
    for name, package in PROFILE_ASSIGNMENTS.get(relative, {}).items():
        profile = assignment(tree, name)
        certificate = dictionary_value(profile, 'certificate_sha256')
        need(isinstance(certificate, ast.Constant) and certificate.value in (None, TARGETS[package][5]),
             'NO_SIGNER_CONSTRAINT_LOSS:' + package)
        if certificate.value is None:
            replace(certificate, TARGETS[package][5], package + ':add_exact_current_signer')
        # Documents' previous reader checked only hash. Add the exact known size,
        # retaining its signer/version/UID and every original validation call.
        if package == DOCUMENTS:
            apks = dictionary_value(profile, 'apks')
            need(isinstance(apks, ast.List) and len(apks.elts) == 1, 'ONE_DOCUMENTS_APK')
            artifact = apks.elts[0]
            need(isinstance(artifact, ast.Dict) and len(artifact.keys) == 1, 'HASH_ONLY_OLD_DOCUMENTS_PROFILE')
            start, _ = span(raw, artifact); start += 1
            edits.append({'start': start, 'end': start, 'line': artifact.lineno, 'before': '',
                          'after': "'bytes': " + str(TARGETS[package][2]) + ', ', 'purpose': package + ':add_exact_size'})
            artifact.keys.insert(0, ast.Constant('bytes')); artifact.values.insert(0, ast.Constant(TARGETS[package][2]))
    result = apply_edits(raw, edits)
    need(ast.dump(ast.parse(result), include_attributes=False) == ast.dump(tree, include_attributes=False),
         'AST_CHANGED_OUTSIDE_EXPLICIT_LITERAL_OR_STRICTER_IDENTITY_FIELDS:' + relative)
    return result, edits


def retire_gallery_entries(relative, raw):
    tree = ast.parse(raw); edits = []
    for name in GALLERY_GUARDS[relative]:
        matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
        need(len(matches) == 1, 'EXACT_RETIRED_GALLERY_ENTRY:' + name)
        function = matches[0]; position = 0
        if (isinstance(function.body[0], ast.Expr) and isinstance(function.body[0].value, ast.Constant)
                and isinstance(function.body[0].value.value, str)):
            position = 1
        first = function.body[position]
        lines = raw.splitlines(keepends=True); start = sum(map(len, lines[:first.lineno - 1]))
        insertion = ' ' * first.col_offset + 'raise RuntimeError(' + repr(GALLERY_REJECTION) + ')\n'
        edits.append({'start': start, 'end': start, 'line': first.lineno, 'before': '', 'after': insertion,
                      'purpose': 'retire_old_modified_candidate_entry:' + name})
        function.body.insert(position, ast.parse('raise RuntimeError(' + repr(GALLERY_REJECTION) + ')').body[0])
    result = apply_edits(raw, edits)
    need(ast.dump(ast.parse(result), include_attributes=False) == ast.dump(tree, include_attributes=False),
         'GALLERY_CHANGE_OUTSIDE_UNCONDITIONAL_RETIREMENT_GUARD')
    return result, edits


def build_postimages(bundle):
    postimages = {}; records = []
    need(not set(LITERAL_RECIPES) & set(GALLERY_GUARDS), 'DISJOINT_SOURCE_EDITS')
    for relative in sorted(set(LITERAL_RECIPES) | set(GALLERY_GUARDS)):
        original = bundle['sources'][relative]
        updated, edits = change_targets(relative, original) if relative in LITERAL_RECIPES else retire_gallery_entries(relative, original)
        need(updated != original, 'REAL_SOURCE_CHANGE_REQUIRED')
        postimages[relative] = updated
        records.append({'relative': relative, 'original': bundle['source_references'][relative],
                        'postimage': pin(updated), 'edits': edits,
                        'change_kind': 'exact_target_metadata' if relative in LITERAL_RECIPES else 'retire_modified_gallery_entry'})
    for relative, original in bundle['sources'].items():
        for target in TARGETS.values():
            if target[1].encode() in original:
                need(relative in LITERAL_RECIPES and target[1].encode() not in postimages[relative],
                     'UNADAPTED_STATIC_TARGET_HASH:' + relative)
    return postimages, records


def make_cohort(bundle, records):
    selected, image, profile = metadata_contract(bundle)
    providers = {}
    for name, source_file, assignment_name in [
        ('com.android.providers.calendar', B + '/system_profiles.py', 'CALENDAR_PROVIDER'),
        ('com.android.providers.contacts', B + '/system_profiles.py', 'CONTACTS_PROVIDER'),
        ('com.android.externalstorage', D + '/documents_profiles.py', 'PROVIDER')]:
        historical = ast.literal_eval(assignment(ast.parse(bundle['sources'][source_file]), assignment_name))
        providers[name] = {'status': 'PENDING_CURRENT_GSI_PROVIDER_SOURCE_AND_SEMANTIC_QUALIFICATION',
                           'current_APK': None, 'current_signer': None, 'actual_UID': None,
                           'historical_expected_profile': historical,
                           'historical_profile_source': bundle['source_references'][source_file]['origin'],
                           'historical_expected_profile_is_current_authority': False,
                           'required_full_GSI': copy.deepcopy(image)}
    media_tree = ast.parse(bundle['sources'][P + '/camera_profiles.py'])
    providers['com.android.providers.media.module'] = {
        'status': 'PENDING_CURRENT_GSI_INNER_MEDIAPROVIDER_APK_AND_SEMANTIC_QUALIFICATION',
        'current_APK': None, 'current_signer': None, 'actual_UID': None,
        'historical_expected_APK': {key: ast.literal_eval(assignment(media_tree, name)) for key, name in
             [('path', 'MEDIA_PROVIDER_APK'), ('bytes', 'MEDIA_PROVIDER_BYTES'), ('sha256', 'MEDIA_PROVIDER_SHA')]},
        'historical_profile_source': bundle['source_references'][P + '/camera_profiles.py']['origin'],
        'historical_expected_profile_is_current_authority': False,
        'current_CAPEX_container_metadata_only': copy.deepcopy(bundle['docs']['provider-metadata-observation.json']['capex_reference_is_not_inner_APK_identity']),
        'CAPEX_hash_is_not_an_APK_identity': True, 'required_full_GSI': copy.deepcopy(image),
    }
    targets = {}
    for package, source in selected.items():
        targets[package] = {
            'source_record': copy.deepcopy(source), 'install_mode': 'coherent_full_GSI_only',
            'individual_APK_install_authorized': False, 'source_APK_body_read_by_this_adapter': False,
            'provider_dependencies': PROVIDER_DEPENDENCIES[package],
            'historical_UID_constraint': TARGETS[package][6] if package in TARGETS else None,
            'historical_UID_is_actual_observation': False,
            'actual_runtime_bindings': {name: None for name in ('Main', 'UID', 'framework_epoch', 'installed_APK_identity', 'UI_selectors', 'helper_custody')},
            'static_target_literal_adaptation_prepared': package in TARGETS,
            'current_runtime_profile_qualified': False,
            'required_future_gates': ['fresh current Main/qualification/UID and same data continuity',
                                      'new preparation source pins and host boundary qualification',
                                      'all original finite business, cleanup and stability gates'],
            **{key: False for key in RUNTIME_FIELDS},
        }
    targets[CALENDAR]['required_future_gates'] += [
        'explicit coherent-GSI custody successor for the old repaired Calendar install receipt; do not relabel a standalone install as image custody',
        'review official Calendar source/UI semantics and current CalendarProvider atomic empty-delete contract',
        'preserve historical CE/DE inode/UID/gid and firstInstallTime continuity gates; no new data receipt is fabricated']
    old = bundle['docs']['old-gallery-host-artifact-contract.json']; method = bundle['docs']['old-gallery-method-observation.json']
    gallery_delta = {
        'baseline_matches_current_official_APK': True,
        'historical_baseline_APK': {'bytes': GALLERY_OFFICIAL[0], 'sha256': GALLERY_OFFICIAL[1]},
        'current_official_source_record': copy.deepcopy(selected[GALLERY]),
        'current_official_DEX_metadata': {'bytes': OFFICIAL_DEX[0], 'sha256': OFFICIAL_DEX[1], 'name': 'classes.dex'},
        'historical_modified_candidate': copy.deepcopy(old['current_candidate']),
        'historical_modified_DEX': {'bytes': MODIFIED_DEX[0], 'sha256': MODIFIED_DEX[1]},
        'historical_modified_method_metadata': copy.deepcopy(method['method_port']),
        'method_hash_scope': 'These are complete class preimage, patched-source and patched-IR hashes associated with the named replaced method; they are not a newly measured method-body hash.',
        'historical_build_receipt': copy.deepcopy(old['documents']['build']),
        'historical_artifact_contract': {'path': next(row['path'] for row in bundle['docs']['METADATA-CUSTODY.json']['files']
            if row['name'] == 'old-gallery-host-artifact-contract.json'), **pin(bundle['metadata_raw']['old-gallery-host-artifact-contract.json'])},
        'modified_candidate_matches_current_official_APK': False,
        'modified_DEX_matches_current_official_DEX': False,
        'old_ART_or_modified_method_credit_transferred': False,
        'old_pm_install_entry_retired': True,
        'current_official_ART_qualified': False, 'current_official_rotation_or_edit_semantics_qualified': False,
        'required_future_gates': ['fresh official-DEX ART and complete class-set proof',
                                  'review and execute supported official-APK edit/rotation behavior on owned fixtures',
                                  'fresh image generation and installed APK custody bound to the same Main/UID',
                                  'current MediaProvider source and owned cleanup semantics'],
    }
    targets[GALLERY]['required_future_gates'] += gallery_delta['required_future_gates']
    cohort = {
        'schema': 'pocket4-current-cp3a-system-source-adapter-v1',
        'state': 'SOURCE_ADAPTER_PREPARED_RUNTIME_BLOCKED', 'source_only': True,
        'required39_source_state': {'path': 'inputs/CURRENT-SOURCE-STATE.json', **pin(bundle['metadata_raw']['CURRENT-SOURCE-STATE.json'])},
        'full_GSI': copy.deepcopy(image), 'build_identity': copy.deepcopy(profile['build_identity']),
        'current_required_system_count': 10, 'adapted_target_profile_mismatch_count': 5,
        'separate_Gallery_modified_candidate_mismatch_count': 1,
        'historical_finite_source_package_count': 7, 'current_business_runtime_compatible_packages_qualified': 0,
        'source_files_validated': len(bundle['sources']), 'source_postimages': records,
        'targets': targets, 'provider_cohort': providers, 'gallery_candidate_mismatch': gallery_delta,
        'required_before_installation': copy.deepcopy(bundle['docs']['CURRENT-SOURCE-STATE.json']['required_before_installation']),
        'APK_bodies_read': 0, 'Android_actions': 0, 'SDK_commands': 0, 'user_data_reads': 0,
        'host_product_mutations': 0, 'old_sources_or_receipts_modified': False,
        'runtime_bootstrap_preparation_admission_claimed': False,
        **{key: False for key in RUNTIME_FIELDS},
    }
    validate_cohort(cohort, selected)
    return cohort


def validate_cohort(cohort, selected):
    need(cohort['source_only'] is True and cohort['state'] == 'SOURCE_ADAPTER_PREPARED_RUNTIME_BLOCKED'
         and all(cohort[key] is False for key in RUNTIME_FIELDS), 'COHORT_CANNOT_PROMOTE_EXECUTION')
    need(set(cohort['targets']) == set(TARGETS) | {GALLERY}
         and len(cohort['provider_cohort']) == 4, 'EXACT_SOURCE_ADAPTER_SCOPE')
    for package, row in cohort['targets'].items():
        need(row['source_record'] == selected[package] and all(row[key] is False for key in RUNTIME_FIELDS)
             and all(value is None for value in row['actual_runtime_bindings'].values())
             and row['provider_dependencies'] == PROVIDER_DEPENDENCIES[package]
             and row['individual_APK_install_authorized'] is False
             and row['current_runtime_profile_qualified'] is False, 'NO_RUNTIME_BINDING_OR_SOURCE_PROMOTION:' + package)
    for provider in cohort['provider_cohort'].values():
        need(provider['current_APK'] is None and provider['current_signer'] is None
             and provider['actual_UID'] is None and provider['historical_expected_profile_is_current_authority'] is False,
             'PROVIDER_SOURCE_STILL_PENDING')
    gallery = cohort['gallery_candidate_mismatch']
    need(gallery['baseline_matches_current_official_APK'] is True and gallery['modified_candidate_matches_current_official_APK'] is False
         and gallery['modified_DEX_matches_current_official_DEX'] is False and gallery['old_ART_or_modified_method_credit_transferred'] is False
         and gallery['current_official_ART_qualified'] is False and gallery['old_pm_install_entry_retired'] is True,
         'NO_GALLERY_CANDIDATE_OR_ART_CREDIT_TRANSFER')


def source_route(cohort, package, purpose):
    """An executable metadata-only route: no caller can request an install/run."""
    need(package in cohort['targets'], 'EXACT_SOURCE_TARGET_REQUIRED')
    need(purpose == 'describe_source', 'SOURCE_ADAPTER_HAS_NO_INSTALL_VERIFY_RUNTIME_OR_EXECUTE_MODE')
    need(cohort['source_only'] is True and all(cohort[key] is False for key in RUNTIME_FIELDS)
         and all(cohort['targets'][package][key] is False for key in RUNTIME_FIELDS),
         'SOURCE_ROUTE_CANNOT_PROMOTE_RUNTIME')
    return copy.deepcopy(cohort['targets'][package])


def require_provider_cohort(cohort, package):
    """Future consumers can fail before runtime on the specific missing cohort."""
    need(package in cohort['targets'], 'EXACT_SOURCE_TARGET_REQUIRED')
    dependencies = cohort['targets'][package]['provider_dependencies']
    need(dependencies == PROVIDER_DEPENDENCIES[package], 'PROVIDER_DEPENDENCY_REMOVAL_FORBIDDEN')
    need(all(cohort['provider_cohort'][name]['current_APK'] is None for name in dependencies),
         'UNREVIEWED_PROVIDER_RECORD_NOT_ACCEPTED')
    pending = [name for name in dependencies if cohort['provider_cohort'][name]['current_APK'] is None]
    need(not pending, 'CURRENT_PROVIDER_SOURCE_PENDING:' + ','.join(pending))
    return copy.deepcopy(dependencies)  # An empty list does not qualify runtime.


def corrected_preflight(bundle, cohort):
    old = bundle['docs']['preflight-r2-PLAN.json']; plan = copy.deepcopy(old); corrections = []
    def change(node, field, value, pointer):
        before = copy.deepcopy(node[field]) if field in node else {'field_absent': True}
        node[field] = value
        corrections.append({'json_pointer': pointer + '/' + field, 'before': before, 'after': copy.deepcopy(value)})
    change(plan, 'schema', 'pocket4-required39-business-plan-cp3a-source-adapter-successor-v1', '')
    change(plan, 'state', 'SOURCE_ADAPTER_PLAN_PREPARED_RUNTIME_BLOCKED', '')
    change(plan, 'prior_preflight_plan', {'path': 'inputs/preflight-r2-PLAN.json', **pin(bundle['metadata_raw']['preflight-r2-PLAN.json'])}, '')
    change(plan['counts'], 'historical_finite_source_package_count', 7, '/counts')
    change(plan['counts'], 'current_business_runtime_compatible_packages_qualified', 0, '/counts')
    change(plan['counts'], 'Gallery_modified_candidate_mismatches', 1, '/counts')
    change(plan, 'finite_prepared_case_source_count_semantics', 'The original seven-package count records historical finite source only; it is not seven current-compatible runtimes.', '')
    for index, row in enumerate(plan['packages']):
        package = row['package']; pointer = '/packages/' + str(index)
        if row['finite_prepared_case_source_exists']:
            change(row, 'finite_source_qualification_scope', 'HISTORICAL_SOURCE_ONLY_CURRENT_RUNTIME_NOT_QUALIFIED', pointer)
        if package in TARGETS:
            change(row, 'source_adapter_candidate', {'state': 'STATIC_TARGET_LITERALS_ADAPTED_REVIEW_AND_REQUALIFICATION_PENDING',
                'old_mismatch_definition_preserved': True, 'current_source_record': copy.deepcopy(cohort['targets'][package]['source_record']),
                'runtime_qualified': False, 'adopted_by_original_preparation': False}, pointer)
        if package == GALLERY:
            change(row, 'gallery_candidate_mismatch', copy.deepcopy(cohort['gallery_candidate_mismatch']), pointer)
            change(row, 'prepared_case_scopes', [
                'historical modified-candidate ART/source verifier; no current official-APK ART credit',
                'historical modified-candidate eight image-rotation gates',
                'historical modified-candidate silent video, midpoint seek and owned-album scopes'], pointer)
            change(row, 'required_adapter', 'Official APK source admission is implemented in the isolated source adapter. Old modified-candidate install/verify/case entrypoints are retired in postimages. Fresh image custody, official-DEX ART and official edit/rotation semantics remain unqualified.', pointer)
            change(row, 'pending_work', [
                'Review and adopt the source-only coherent-GSI adapter and new preparation pins',
                'Do not transfer old modified-candidate DEX, ART class-set or two-method repair credit',
                'Fresh image-installed custody, Main/UID/framework and MediaProvider cohort',
                'Actual official-APK rotation/edit/video/seek/album and all common gates',
                'Continuous stability and whole-App review'], pointer)
    need(plan['required_before_installation'] == old['required_before_installation'], 'INSTALLATION_PREREQUISITES_LOST')
    need(plan['counts']['target_identity_rebinds'] == 5 and plan['counts']['finite_prepared_case_packages'] == 7
         and plan['counts']['packages_without_selected_business_executor'] == 32, 'HISTORICAL_COUNTS_REDEFINED')
    need(all(plan[key] is False for key in ('installed', 'runtime_qualified', 'business_qualified', 'production_ready', 'execution_authorized'))
         and all(all(row[key] is False for key in RUNTIME_FIELDS) for row in plan['packages'])
         and all(all(v is None for v in row['actual_runtime_bindings'].values()) for row in plan['packages']),
         'CORRECTED_PLAN_CANNOT_PROMOTE_RUNTIME')
    text = bundle['metadata_raw']['preflight-r2-README.md'].decode()
    old_line = "- Gallery's official target hash matches, but its historical entry permits standalone APK installation. The selected source-state prohibits that path; an image-installed custody/verification adapter still needs review. Camera also retains an old CP2A MediaProvider binding. Calendar/Contacts/ExternalStorage/MediaProvider bindings must be checked against the current coherent GSI."
    new_line = "- Gallery's historical official baseline APK matches the selected current official APK (835fe119…), but the actual old runtime candidate (6677d382…) and its DEX (6a994fab…) are different from the current official APK/DEX (725ac715…). This is a separate Gallery candidate mismatch in addition to the five target-profile mismatches. No old ART, class-set or two-modified-method repair credit transfers. The isolated CP3A adapter provides source admission and retires old standalone install/modified-candidate entrypoints in postimages; fresh image custody, official-DEX ART and supported official edit/rotation semantics remain pending. Calendar/Contacts/ExternalStorage/MediaProvider source and semantic qualification remain pending; a CAPEX container hash does not identify its inner APK."
    old_count = '- Thirteen preparation references cover limited source workflows for **seven packages**, six system apps and IHG. **32 packages still lack a selected business executor.** This is a bounded conclusion about the inspected current selector, not a whole-host search claim.'
    new_count = '- Thirteen preparation references cover historical finite source workflows for **seven packages**, six system apps and IHG. They do not establish seven current-compatible runtimes. **32 packages still lack a selected business executor.** This is a bounded conclusion about the inspected selector, not a whole-host search claim.'
    for before, after in [(old_line, new_line), (old_count, new_count)]:
        need(text.count(before) == 1, 'EXACT_PRIOR_README_SENTENCE_REQUIRED')
        corrections.append({'document': 'preflight-r2-README.md', 'before': before, 'after': after})
        text = text.replace(before, after)
    return plan, text.encode(), corrections


def create_exclusive_file(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(fd, view); need(written > 0, 'OUTPUT_WRITE_FAILED'); view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def materialize(root, output):
    need(not os.path.lexists(output), 'EXCLUSIVE_NEW_OUTPUT_REQUIRED')
    bundle = load_bundle(root)
    metadata_contract(bundle)
    postimages, records = build_postimages(bundle)
    cohort = make_cohort(bundle, records)
    plan, readme, corrections = corrected_preflight(bundle, cohort)
    patch_parts = []
    for name, raw in postimages.items():
        patch_parts.extend(difflib.unified_diff(bundle['sources'][name].decode().splitlines(keepends=True),
            raw.decode().splitlines(keepends=True), fromfile='originals/' + name, tofile='postimages/' + name))
    files = {'CURRENT-CP3A-COHORT.json': json_bytes(cohort), 'PLAN.json': json_bytes(plan),
             'preflight-r2-corrected-README.md': readme,
             'PREFLIGHT-CORRECTIONS.json': json_bytes({'schema': 'p4-required39-cp3a-source-corrections-v1',
                  'prior_plan': pin(bundle['metadata_raw']['preflight-r2-PLAN.json']), 'changes': corrections,
                  'original_r2_files_modified': False}),
             'changes.patch': ''.join(patch_parts).encode()}
    files.update({'postimages/' + name: raw for name, raw in postimages.items()})
    bookend(root, bundle)
    output.mkdir(mode=0o700)
    for relative, raw in files.items():
        create_exclusive_file(output / relative, raw)
    bookend(root, bundle)
    manifest = {
        'schema': 'p4-system-cp3a-source-adapter-output-v1', 'state': 'SOURCE_ADAPTER_PREPARED_RUNTIME_BLOCKED',
        'source_only': True, 'source_files_full_SHA_checked': 224, 'original_preparation_metadata_count': 11,
        'exact_target_metadata_postimage_files': len(LITERAL_RECIPES), 'Gallery_entry_retirement_postimage_files': len(GALLERY_GUARDS),
        'Gallery_entry_retirement_functions': sum(map(len, GALLERY_GUARDS.values())),
        'input_pins': {name: {'bytes': value[0], 'sha256': value[1]} for name, value in PINS.items()},
        'source_manifest_pin': {'bytes': SOURCE_MANIFEST_PIN[0], 'sha256': SOURCE_MANIFEST_PIN[1]},
        'original_source_F9_and_full_SHA_unchanged': True,
        'outputs': {name: pin(raw) for name, raw in sorted(files.items())},
        'Android_actions': 0, 'SDK_commands': 0, 'APK_bodies_read': 0, 'user_data_reads': 0,
        'product_host_mutations': 0, 'originals_imported_or_executed': False,
        'preparation_or_runtime_qualification_claimed': False,
        **{key: False for key in RUNTIME_FIELDS},
    }
    create_exclusive_file(output / 'MANIFEST.json', json_bytes(manifest))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).parent)
    sub = parser.add_subparsers(dest='mode', required=True)
    build = sub.add_parser('materialize'); build.add_argument('--out', required=True, type=Path)
    describe = sub.add_parser('describe_source'); describe.add_argument('--package', required=True, choices=sorted(set(TARGETS) | {GALLERY}))
    args = parser.parse_args(argv)
    try:
        if args.mode == 'materialize':
            manifest = materialize(args.root, args.out)
            print(json.dumps({'state': manifest['state'], 'output_files': len(manifest['outputs']) + 1,
                 'target_postimages': manifest['exact_target_metadata_postimage_files'],
                 'retired_Gallery_entries': manifest['Gallery_entry_retirement_functions'],
                 'Android_actions': 0, 'runtime_qualified': False}, sort_keys=True))
        else:
            bundle = load_bundle(args.root); _, records = build_postimages(bundle)
            cohort = make_cohort(bundle, records); value = source_route(cohort, args.package, 'describe_source')
            bookend(args.root, bundle); print(json.dumps(value, sort_keys=True, indent=2))
        return 0
    except (AdmissionError, OSError, ValueError, KeyError) as error:
        print(type(error).__name__ + ':' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
