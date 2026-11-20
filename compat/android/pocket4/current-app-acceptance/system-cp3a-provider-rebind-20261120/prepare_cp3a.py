#!/usr/bin/env python3
"""Join the published CP3A sources and prepare exact provider source postimages.

This entry never opens an embedded host/APK path, imports a runtime executor,
or changes a previous preparation. Runtime custody is a separate, mandatory
consumer: source verification cannot create a deployed-image receipt.
"""
import argparse
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import types

PREFIX = 'compat/android/pocket4/current-app-acceptance/'
OLD = PREFIX + 'system-cp3a-source-adapter-20261119/'
PROVIDERS = PREFIX + 'system-cp3a-provider-source-20261119/'
DEX = PREFIX + 'gallery-official-dex-source-20261119/'
OLD_CODE = (44608, '3d04239f428156b2a507a5cce6f50ca438eb66434f5df712d43ce86173173aea')
COHORT_PIN = (71046, '487e747cec5d158052e9ad9e0e2c2beec3115a6f0d69594ad84941b438aed8ea')
DEX_PIN = (126819, '147509fe23c352a40a2db88fcc9e69b0e66eaf6018edf148150ea1849d087649')
DEX_RESULT_PIN = (5644, 'e5682f9cd9fa8356755c4a21c0f09d1ec1fbb9d6816799932fb64f0301d19d17')
GSI = {'bytes': 2294853632, 'sha256': 'dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4'}
MEDIA_OLD = '/apex/com.android.mediaprovider/priv-app/MediaProvider@CP2A.260605.016/MediaProvider.apk'
MEDIA_NEW = '/apex/com.android.mediaprovider/priv-app/MediaProvider@CP3A.260905.010/MediaProvider.apk'
CAL = 'com.android.providers.calendar'
CON = 'com.android.providers.contacts'
EXT = 'com.android.externalstorage'
MED = 'com.android.providers.media.module'
PINS = {
    CAL: (340711, 'eebf12f81981f7d8c59a9b9ed465945818d2ab0208c121d858cbc4e6426f5fff', 336615,
          '1ae37944b4f5f24d8d7bc849c76bd80c678d19cc3f5647ccaebd1254d8508744',
          'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc', 10017,
          16169, 'dbbac2c144ad77a88c41f322452f26393c103dbcdfabc3d0f390f2a2ec967f4c'),
    CON: (872865, '9a8d8238565ff977a025ad6eb3f1496b5bd2ea9c819b3229278d62e29da0c313', 942497,
          '196cf184ca743601469dc235a4c7a163ac8ca9442cfdbd033bdaf109f5a9fd14',
          '28bbfe4a7b97e74681dc55c2fbb6ccb8d6c74963733f6af6ae74d8c3a6e879fd', 10015,
          14903, '40b35f49755c7ee3c08c439cff9cc124583e5119b1a756ec3487ec1c3a26c1df'),
    EXT: (None, '50d1e6f2be950e049cdc898dd812c8e609f421cc167013d4ee2c795dcdc0e5ea', 57567,
          '00cf8db78a3f8846e34fd3e6b7f1c811a9393b7c2e6227c083e27e5cdb0fa515',
          'c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8', 10024,
          14196, 'dada6f8c4377991b058a815e6c3c2ada685e09684c9220c8dd49b8f48fa4d8ed'),
    MED: (15447727, 'b98258475c14043fe1f7e0d5a61caa13aa22dea426ffc589e83012f0377ce0f4', 13826854,
          'aff897cc1f56583cd71c4cf48330eb4514fdefbd54f069e55223bd31e7af305b',
          '465983f7791f2abeb43ea2cbdc7f21a8260b72bc08a55c839fc1a43bc741a81e', None,
          379038, 'a4928bf3986ce13a766daa55a3c3ba7a7369b9ab73690642ee26e0da9efb1d4c'),
}
B = 'business-system-cases-runtime-inputs-20261108-8b88-r2'
C = 'calendar-reminder-runtime-inputs-20261108-8b88-r2'
P = 'camera-app-photo-preparation-resume-20261107-r4'
D = 'documents-saf11-runtime-inputs-20261108-8b88-r2'
S = 'documents-search-sort-runtime-inputs-20261108-8b88-r2'
R = 'gallery-rotation-current-preparation-20261107-r7'
# Counts apply to the exact source before this provider-only transformation.
RECIPES = {
    B + '/system_profiles.py': [(CAL, 1, 1), (CON, 1, 1)],
    B + '/calendar_core.py': [(CAL, 1, 0)],
    B + '/contacts_model.py': [(CON, 1, 1)],
    C + '/system_profiles.py': [(CAL, 1, 1)],
    C + '/calendar_core.py': [(CAL, 1, 0)],
    P + '/camera_profiles.py': [(MED, 1, 1)],
    D + '/documents_profiles.py': [(EXT, 1, 0)],
    D + '/documents_saf_core.py': [(EXT, 1, 0)],
    S + '/documents_profiles.py': [(EXT, 1, 0)],
    S + '/documents_package_fixture.py': [(EXT, 1, 0)],
    R + '/owned_media.py': [(MED, 1, 1)],
}
PROFILES = {
    B + '/system_profiles.py': {'CALENDAR_PROVIDER': CAL, 'CONTACTS_PROVIDER': CON},
    C + '/system_profiles.py': {'CALENDAR_PROVIDER': CAL},
    D + '/documents_profiles.py': {'PROVIDER': EXT},
    S + '/documents_profiles.py': {'PROVIDER': EXT},
}
RUNTIME_FALSE = ('installed', 'runtime_qualified', 'business_qualified', 'production_ready',
                 'execution_ready', 'execution_authorized', 'whole_app_business_accepted')


def need(ok, why):
    if not ok:
        raise ValueError(why)


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def static_profile(old, raw, name):
    """Resolve only bounded literal assignments; never import the runtime file."""
    tree = ast.parse(raw)
    def resolve(node, stack):
        need(len(stack) <= 8, 'bounded acyclic profile constants')
        if isinstance(node, ast.Name):
            need(node.id not in stack, 'cyclic profile constant')
            return resolve(copy.deepcopy(old.assignment(tree, node.id)), stack + [node.id])
        for field, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                setattr(node, field, resolve(value, stack))
            elif isinstance(value, list):
                setattr(node, field, [resolve(v, stack) if isinstance(v, ast.AST) else v for v in value])
        if isinstance(node, ast.BinOp):
            need(isinstance(node.op, ast.Add) and isinstance(node.left, ast.Constant)
                 and isinstance(node.right, ast.Constant) and type(node.left.value) is str
                 and type(node.right.value) is str, 'only literal component string concatenation')
            return ast.Constant(node.left.value + node.right.value)
        return node
    return ast.literal_eval(resolve(copy.deepcopy(old.assignment(tree, name)), [name]))


def legacy(repo):
    # Import only the reviewed metadata transformer, never a runtime source.
    path = repo / OLD / 'adapt_cp3a.py'
    raw = path.read_bytes()
    need((len(raw), hashlib.sha256(raw).hexdigest()) == OLD_CODE, 'exact old metadata transformer')
    value = types.ModuleType('exact_cp3a_source_transformer')
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    value.read_fixed(repo, OLD + 'adapt_cp3a.py', OLD_CODE)
    return value


def load(repo):
    old = legacy(repo)
    bundle = old.load_bundle(repo / OLD)
    inputs = {
        PROVIDERS + 'current/CURRENT-CP3A-PROVIDER-COHORT.json': COHORT_PIN,
        DEX + 'actual/DEX-SOURCE-INVENTORY.json': DEX_PIN,
        DEX + 'actual/RESULT.json': DEX_RESULT_PIN,
    }
    inputs.update({PROVIDERS + 'actual/receipts/' + package + '.json': values[6:]
                   for package, values in PINS.items()})
    raw = {}; identities = {}
    for name, expected in inputs.items():
        raw[name], identities[name] = old.read_fixed(repo, name, expected)
    return old, bundle, inputs, raw, identities


def provider_sources(old, bundle, raw):
    cohort = old.parse(raw[PROVIDERS + 'current/CURRENT-CP3A-PROVIDER-COHORT.json'])
    selected, image, profile = old.metadata_contract(bundle)
    need(cohort['schema'] == 'pocket4-current-cp3a-provider-source-cohort-v1'
         and cohort['full_GSI'] == image and {k: image[k] for k in GSI} == GSI
         and cohort['build_identity'] == profile['build_identity']
         and set(cohort['targets']) == set(selected)
         and set(cohort['provider_cohort']) == set(PINS), 'same six targets and four CP3A providers')
    need(cohort['source_only'] is True and cohort['provider_source_verified_count'] == 4
         and cohort['provider_runtime_qualified_count'] == cohort['provider_semantic_cleanup_qualified_count'] == 0
         and all(cohort[k] is False for k in RUNTIME_FALSE), 'source cohort cannot grant runtime')
    for package, source in selected.items():
        need(cohort['targets'][package]['source_record'] == source
             and cohort['targets'][package]['provider_dependencies'] == old.PROVIDER_DEPENDENCIES[package]
             and all(cohort['targets'][package][k] is False for k in RUNTIME_FALSE), 'target source/dependency drift')
    receipts = {}
    for package, values in PINS.items():
        row = cohort['provider_cohort'][package]
        receipt = old.parse(raw[PROVIDERS + 'actual/receipts/' + package + '.json'])
        need(row['source_identity_verified'] is True and row['actual_UID'] is None
             and row['historical_expected_profile_is_current_authority'] is False
             and row['current_APK'] == receipt['apk'] and row['required_full_GSI'] == image
             and (row['current_APK']['bytes'], row['current_APK']['sha256']) == values[2:4]
             and row['current_signer'] == receipt['signer_certificate_sha256'] == [values[4]],
             'exact provider APK and independent signer: ' + package)
        need(receipt['package'] == package and receipt['full_system_image'] == image
             and receipt['version_code'] == 37 and receipt['signature_verified_for_api'] == 37
             and receipt['source_identity_verified'] is True and receipt['full_CRC_and_SHA_verified'] is True
             and receipt['actual_UID'] is None and receipt['framework_epoch'] is None
             and receipt['individual_APK_install_authorized'] is False
             and all(receipt[k] is False for k in ('installed', 'runtime_qualified', 'business_qualified',
                                                  'production_ready', 'semantic_cleanup_qualified'))
             and all(row[k] is False for k in ('runtime_qualified', 'business_qualified',
                                              'production_ready', 'semantic_cleanup_qualified')),
             'provider source cannot replace actual UID/semantic/runtime evidence: ' + package)
        if package == MED:
            need(receipt['original_image_path'] == MEDIA_NEW and receipt['container_chain'],
                 'current inner MediaProvider APK; CAPEX is not an APK')
        receipts[package] = receipt
    dex = old.parse(raw[DEX + 'actual/DEX-SOURCE-INVENTORY.json'])
    result = old.parse(raw[DEX + 'actual/RESULT.json'])
    gallery = selected[old.GALLERY]
    need(result['success'] is True and result['APK'] == gallery['apk'] and result['full_GSI'] == image
         and dex['schema'] == 'pocket4-official-gallery-static-dex-inventory-v1'
         and (dex['dex']['bytes'], dex['dex']['sha256']) == old.OFFICIAL_DEX
         and result['DEX']['sha256'] == old.OFFICIAL_DEX[1]
         and dex['class_definition_count'] == len(dex['all_class_descriptors']) == 2144
         and len(set(dex['all_class_descriptors'])) == 2144
         and dex['static_class_table_complete'] is True
         and all(dex[k] is False for k in ('ART_qualified', 'method_behavior_qualified', 'installed',
                                          'runtime_qualified', 'business_qualified', 'production_ready')),
         'official Gallery source never transfers modified-APK ART or business credit')
    return cohort, receipts, dex


def change_provider(old, relative, raw):
    tree = ast.parse(raw); edits = []
    def replace(node, value, why):
        start, end = old.span(raw, node)
        edits.append({'start': start, 'end': end, 'line': node.lineno,
                      'before': raw[start:end].decode(), 'after': repr(value), 'purpose': why})
        node.value = value
    for package, hashes, sizes in RECIPES[relative]:
        before_size, before_sha, after_size, after_sha = PINS[package][:4]
        for before, after, count, kind in ((before_sha, after_sha, hashes, 'sha256'),
                                           (before_size, after_size, sizes, 'bytes')):
            if before is None:
                need(count == 0, 'no invented historical provider size'); continue
            found = [node for node in ast.walk(tree) if isinstance(node, ast.Constant)
                     and type(node.value) is type(before) and node.value == before]
            need(len(found) == count, 'exact provider literal occurrence: ' + relative + ':' + kind)
            for node in found:
                replace(node, after, package + ':' + kind)
        if package == MED:
            found = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and node.value == MEDIA_OLD]
            need(len(found) == 1, 'exact old APEX member path')
            replace(found[0], MEDIA_NEW, package + ':exact_current_APEX_member')
    for name, package in PROFILES.get(relative, {}).items():
        profile = old.assignment(tree, name)
        cert = old.dictionary_value(profile, 'certificate_sha256')
        need(isinstance(cert, ast.Constant) and cert.value is None, 'original unset provider signer')
        replace(cert, PINS[package][4], package + ':add_exact_source_signer')
        if package == EXT:
            artifact = old.dictionary_value(profile, 'apks').elts[0]
            need(isinstance(artifact, ast.Dict) and len(artifact.keys) == 1, 'one hash-only original ExternalStorage APK')
            start, _ = old.span(raw, artifact); start += 1
            edits.append({'start': start, 'end': start, 'line': artifact.lineno, 'before': '',
                          'after': "'bytes': " + str(PINS[package][2]) + ', ',
                          'purpose': package + ':add_exact_source_size'})
            artifact.keys.insert(0, ast.Constant('bytes')); artifact.values.insert(0, ast.Constant(PINS[package][2]))
    updated = old.apply_edits(raw, edits)
    need(ast.dump(ast.parse(updated), include_attributes=False) == ast.dump(tree, include_attributes=False),
         'provider edit escaped exact literals/stronger signer/size constraints')
    return updated, edits


def build(old, bundle, raw):
    cohort, receipts, dex = provider_sources(old, bundle, raw)
    outputs, previous = old.build_postimages(bundle)
    rows = []
    for name in sorted(RECIPES):
        before = outputs.get(name, bundle['sources'][name])
        after, edits = change_provider(old, name, before)
        outputs[name] = after
        rows.append({'relative': name, 'before': pin(before), 'after': pin(after), 'edits': edits})
    # Coverage is over all 224 actual originals, including files outside the recipes.
    for name, original in bundle['sources'].items():
        after = outputs.get(name, original)
        for values in PINS.values():
            if values[1].encode() in original:
                need(name in RECIPES and values[1].encode() not in after, 'unadapted provider hash: ' + name)
        if MEDIA_OLD.encode() in original:
            need(name in RECIPES and MEDIA_OLD.encode() not in after, 'unadapted MediaProvider path: ' + name)
    bindings = {}
    profile_names = {old.CALENDAR: (B + '/system_profiles.py', 'CALENDAR'),
        old.CONTACTS: (B + '/system_profiles.py', 'CONTACTS'),
        old.CAMERA: (P + '/camera_profiles.py', 'CAMERA'),
        old.CLOCK: (old.K + '/clock_profiles.py', 'CLOCK'),
        old.DOCUMENTS: (D + '/documents_profiles.py', 'DOCUMENTS')}
    for package, target in cohort['targets'].items():
        source = target['source_record']
        if package in profile_names:
            name, assignment = profile_names[package]
            expected = static_profile(old, outputs[name], assignment)
        else:
            expected = {'package': package, 'uid': 10064, 'version_code': source['version_code'],
                        'component': None, 'apks': [{k: source['apk'][k] for k in ('bytes', 'sha256')}],
                        'certificate_sha256': source['signer_certificate_sha256'][0], 'require_v3': False}
        bindings[package] = {'profile': expected, 'source_image_member': source['image_path'],
            'source_receipt': source['source_receipt'], 'provider_dependencies': old.PROVIDER_DEPENDENCIES[package],
            'UID_constraint_is_live_observation': False, 'runtime_qualified': False}
    for package, receipt in receipts.items():
        values = PINS[package]
        bindings[package] = {'profile': {'package': package, 'uid': values[5], 'version_code': 37,
            'component': None, 'apks': [{'bytes': values[2], 'sha256': values[3]}],
            'certificate_sha256': values[4], 'require_v3': False},
            'source_image_member': receipt['original_image_path'],
            'source_receipt': cohort['provider_cohort'][package]['current_source_receipt'],
            'provider_dependencies': [], 'UID_constraint_is_live_observation': False, 'runtime_qualified': False}
    contract = {
        'schema': 'pocket4-cp3a-image-custody-source-contract-v1',
        'state': 'SOURCE_REBINDING_PREPARED_ACTUAL_IMAGE_CUSTODY_AND_BUSINESS_PENDING',
        'source_only': True, 'source_basis': {'provider_cohort': {'path': PROVIDERS + 'current/CURRENT-CP3A-PROVIDER-COHORT.json', **dict(zip(('bytes','sha256'),COHORT_PIN))},
            'official_DEX': {'path': DEX + 'actual/DEX-SOURCE-INVENTORY.json', **dict(zip(('bytes','sha256'),DEX_PIN))}},
        'full_GSI': GSI, 'build_identity': cohort['build_identity'], 'bindings': bindings,
        'install_mode': 'coherent_full_GSI_only', 'individual_APK_install_authorized': False,
        'old_modified_Gallery_entries_retired': True, 'old_modified_ART_credit_transferred': False,
        'official_Gallery_DEX': {k: dex['dex'][k] for k in ('bytes','sha256')},
        'official_Gallery_class_count': 2144, 'official_Gallery_classes': dex['sorted_class_list_json'],
        'official_Gallery_selected_methods': dex['selected_methods'],
        'provider_semantics_transferred': False, 'runtime_bootstrap_preparation_admission_claimed': False,
        'live_custody_producer_qualified': False, 'actual_Main': None, 'actual_image_custody': None,
        'remaining_gates': ['reviewed whole-GSI deployment and current mounted-image custody producer',
            'actual committed cell, current Main/UID/epoch and retained user-data identity',
            'complete adopted preparation/source closures and host-boundary qualification',
            'fresh official-DEX ART, edit/rotation semantics and current provider cleanup semantics',
            'original finite business, cleanup and stability acceptance'],
        **{key: False for key in RUNTIME_FALSE}, 'Android_actions': 0, 'user_data_reads': 0,
    }
    return outputs, {'schema': 'pocket4-cp3a-provider-source-transform-v1', 'old_target_and_retirement_edits': previous,
                     'provider_edits': rows, 'original_files_covered': len(bundle['sources']),
                     'combined_postimages': len(outputs), 'provider_transform_control_flow_UID_limits_unchanged': True}, contract


def materialize(repo, output):
    old, bundle, inputs, raw, identities = load(repo)
    outputs, transform, contract = build(old, bundle, raw)
    need(not output.exists(), 'new output only; preserve old preparation and failure evidence')
    output.mkdir(parents=False, mode=0o700)
    for name, body in outputs.items():
        path = output / 'postimages' / name; path.parent.mkdir(parents=True, exist_ok=True)
        old.create_exclusive_file(path, body)
    for name, value in [('TRANSFORM.json', transform), ('SOURCE-CONTRACT.json', contract)]:
        old.create_exclusive_file(output / name, old.json_bytes(value))
    patch = ''.join(''.join(difflib.unified_diff(bundle['sources'][name].decode().splitlines(True),
        body.decode().splitlines(True), fromfile='originals/' + name, tofile='postimages/' + name))
        for name, body in sorted(outputs.items()))
    old.create_exclusive_file(output / 'SOURCE.patch', patch.encode())
    old.bookend(repo / OLD, bundle)
    for name, expected in inputs.items():
        _, after = old.read_fixed(repo, name, expected)
        need(after == identities[name], 'source evidence changed during preparation')
    return {'state': contract['state'], 'original_sources': len(bundle['sources']),
            'combined_postimages': len(outputs), 'provider_changed_files': len(RECIPES),
            'contract': pin(old.json_bytes(contract)), 'Android_actions': 0,
            **{key: False for key in RUNTIME_FALSE}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(materialize(args.repo_root.resolve(), args.output.resolve()), sort_keys=True))


if __name__ == '__main__':
    main()
