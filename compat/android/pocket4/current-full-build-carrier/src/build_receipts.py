"""Verify actual 9ecce normal receipts and artifacts without granting runtime credit.

The source specification is copied from exact whole-hashed current Rust modules.
Live effective input snapshots and restored originals are separate boundaries.
"""
import importlib.util
from pathlib import Path

_descriptor = importlib.util.spec_from_file_location('p4_carrier_checks', Path(__file__).with_name('carrier_checks.py'))
c = importlib.util.module_from_spec(_descriptor); _descriptor.loader.exec_module(c)
p = c.sibling('producer_contract')
need = c.need

NAMES = {
    'framework': 'droidloom-framework-asb-security',
    'wm': 'droidloom-wm-security',
    'avb': 'droidloom-avb-security',
    'libpng': 'droidloom-libpng-security',
}
COMMON_FALSE = ['QPR1_source_identity_claim', 'runtime_qualified']
RESULT_FALSE = ['QPR1_source_identity_claim', 'binary_semantic_fix_qualified', 'whole_security_bulletin_qualified', 'runtime_qualified', 'production_ready']


def lanes(phase):
    p.targets(phase)
    return ['avb', 'libpng'] if phase == 'vendor' else ['framework', 'wm', 'avb']


def false_fields(value, names):
    for name in names:
        need(value.get(name) is False, 'source/build evidence cannot grant ' + name)


def base_input(value, phase):
    need(value.get('requested_targets') == p.targets(phase), 'exact current requested targets differ')
    need(value.get('product') == p.PRODUCT and value.get('source_release') == 'cp2a' and value.get('build_variant') == 'user', 'strict original product/user/cp2a identity differs')
    need(value.get('strict_allow_missing_dependencies') == value.get('selinux_ignore_neverallows') == 'false', 'relaxed dependency or neverallow flag')
    need(value.get('source_profile') == ('exact-production651-source-user-vendor-image' if phase == 'vendor' else 'exact-production651-source-framework-asb-and-wm-targets'), 'exact current production source profile differs')
    if phase == 'wm':
        need(value.get('projection_scope_targets') == p.FRAMEWORK_TARGETS, 'framework projection targets differ')
    false_fields(value, COMMON_FALSE)


def lane_input(value, lane, phase, recipe, source, specification=None):
    """Validate input semantics; no success is inferred from a JSON declaration."""
    specification = specification or p.spec()
    item = specification['lanes'][lane]
    recipe, source = Path(recipe), Path(source)
    base_input(value, phase)
    need(value.get('schema') == NAMES[lane] + '-inputs-v1', 'input schema differs')
    lock = value.get('source_lock', {})
    need(lock.get('path') == str(recipe / 'android/manifest/production-full-source-lock.json') and lock.get('sha256') == p.LOCK_SHA, 'exact complete source lock differs')
    expected_effective = [{'path': str(source / item['project'] / name), 'bytes': size, 'sha256': sha} for name, size, sha in item['fixed'] + (item['providers'] if lane in ('framework', 'wm') else [])]
    if lane in ('framework', 'wm'):
        need(value.get('original_frameworks_base_pin') == item['project_pin'] and value.get('CVE_rows') == item['cves'], 'framework source/CVE scope differs')
        expected_patches = [{'path': str(recipe / name), 'bytes': size, 'sha256': sha, 'commit': commit, 'url': 'https://android.googlesource.com/platform/frameworks/base/+/' + commit} for name, size, sha, commit in item['patches']]
        need(value.get('official_complete_patches') == expected_patches, 'complete official framework patch identities/order differ')
        need(value.get('effective_upstream_files_and_providers') == expected_effective, 'exact effective files and providers differ')
        false_fields(value, ['artifact_identity_qualified', 'official_device_tests_executed', 'binary_semantic_fix_qualified', 'production_signing_qualified', 'whole_security_bulletin_qualified', 'production_ready'])
        if lane == 'framework':
            need(value.get('same_fix_aliases_not_replayed') == item['aliases'], 'framework alias scope differs')
            need(value.get('official_test_modules') == ['FrameworksServicesTests', 'UsbTests', 'AudioServiceTests', 'WmTests'], 'official framework test modules differ')
    else:
        need(value.get('original_project_pin') == item['project_pin'], 'original AVB/libpng project pin differs')
        expected_patches = [{'path': str(recipe / name), 'bytes': size, 'sha256': sha, 'official_commit': item['commits'][i]} for i, (name, size, sha) in enumerate(item['patches'])]
        need(value.get('official_patches_in_order') == expected_patches, 'complete official AVB/libpng patches/order differ')
        need(value.get('effective_upstream_files') == expected_effective and value.get('original_Android_bp_sha256') == item['providers'][0][2], 'effective AVB/libpng files or provider differs')
        false_fields(value, ['regression_executed', 'whole_security_bulletin_qualified'])
        if lane == 'avb':
            need(value.get('CVE') == 'CVE-2026-58956' and value.get('upstream_bug') == 'A-461507723' and value.get('alternate_commit_not_replayed') == '119d66ea37241def63e715658ac02c414bd3d0e5' and value.get('original_file_equals_official_patch_preimage') is True, 'AVB official source evidence differs')
            false_fields(value, ['artifact_identity_qualified', 'binary_semantic_fix_qualified', 'production_ready'])
        else:
            need(value.get('CVE') == 'CVE-2026-58936' and value.get('first_official_fix_parent') == '7d98050ef8d9d17d495eb178b8217548437cedf1' and value.get('original_project_pin_is_first_fix_parent') is False and value.get('all_five_original_files_equal_official_patch_preimages') is True, 'libpng official source evidence differs')
            false_fields(value, ['vendor_artifact_identity_qualified'])
    projection = value.get('effective_projection', {}).get('files')
    need(type(projection) is dict and projection, 'actual complete projection file map required')
    # Changed fixed files must occur in the original normal projection journal.
    for name, _, sha in item['fixed']:
        need(projection.get(item['project'] + '/' + name) == sha, 'fixed source absent from effective projection')
    return {'patches': expected_patches, 'effective': expected_effective}


def live_inputs(out, recipe, source, phase):
    """Called inside the retained normal-driver PIDFD/lock observation boundary."""
    out, recipe, source = Path(out), Path(recipe), Path(source)
    refs = {}; effective_refs = {}; patch_refs = {}
    lock = c.read_file(recipe / 'android/manifest/production-full-source-lock.json', 1024**2)
    need(lock['bytes'] == 400363 and lock['sha256'] == p.LOCK_SHA, 'actual complete source lock differs')
    specification = p.spec()
    for lane in lanes(phase):
        value, ref = c.read_json(out / (NAMES[lane] + '-inputs.json'))
        expected = lane_input(value, lane, phase, recipe, source, specification)
        for row in expected['patches']:
            patch_refs[row['path']] = c.exact_file(row, row['path'])
        for row in expected['effective']:
            effective_refs[row['path']] = c.exact_file(row, row['path'], 64 * 1024**2)
        # AVB/libpng Android.bp are preserved providers, not patched source.
        for name, size, sha in specification['lanes'][lane]['providers']:
            path = source / specification['lanes'][lane]['project'] / name
            effective_refs[str(path)] = c.exact_file({'path': str(path), 'bytes': size, 'sha256': sha}, path, 64 * 1024**2)
        refs[lane] = ref
    for row in list(refs.values()) + list(effective_refs.values()) + list(patch_refs.values()) + [lock]:
        c.exact_file(row, row['path'], identity=True)
    return {'inputs': refs, 'effective_files_and_providers': effective_refs, 'official_patches': patch_refs, 'source_lock': lock,
            'runtime_qualified': False, 'production_ready': False}


def verify_restored(recipe, source, lane, specification):
    item = specification['lanes'][lane]; refs = {}
    originals = {name: (size, sha) for name, size, sha in item['originals']}
    for name, size, sha in item['providers']:
        need(name not in originals or originals[name] == (size, sha), 'conflicting original provider identity')
        originals[name] = (size, sha)
    for name, (size, sha) in originals.items():
        path = Path(source) / item['project'] / name
        refs[str(path)] = c.exact_file({'path': str(path), 'bytes': size, 'sha256': sha}, path, 64 * 1024**2)
    for row in item['patches']:
        name, size, sha = row[:3]; path = Path(recipe) / name
        refs[str(path)] = c.exact_file({'path': str(path), 'bytes': size, 'sha256': sha}, path)
    return refs


def security_completion(out, recipe, source, phase, observed):
    """Require the same live-observed inputs, successful results and actual restoration."""
    need(type(observed) is dict and set(observed['inputs']) == set(lanes(phase)), 'actual retained-driver security input observation missing')
    out = Path(out); specification = p.spec(); results = {}; originals = {}
    for lane in lanes(phase):
        input_path = out / (NAMES[lane] + '-inputs.json')
        inputs, input_ref = c.read_json(input_path)
        need(input_ref == observed['inputs'][lane], 'live-observed input receipt F9/SHA changed')
        lane_input(inputs, lane, phase, recipe, source, specification)
        value, ref = c.read_json(out / (NAMES[lane] + '-normal-result.json'))
        need(value.get('schema') == NAMES[lane] + '-normal-result-v1' and value.get('inputs') == {'path': str(input_path), 'sha256': input_ref['sha256']}, 'normal result is not bound to the exact observed input bytes')
        need(value.get('requested_targets') == p.targets(phase) and value.get('normal_command_returned_success') is True and value.get('product') == p.PRODUCT and value.get('source_release') == 'cp2a' and value.get('build_variant') == 'user', 'normal result scope or success differs')
        false_fields(value, RESULT_FALSE)
        if lane in ('framework', 'wm'):
            need(value.get('original_source_files_and_providers_restored') is True and value.get('strict_allow_missing_dependencies') == value.get('selinux_ignore_neverallows') == 'false' and value.get('CVE_rows') == specification['lanes'][lane]['cves'], 'strict framework result/restoration differs')
            false_fields(value, ['artifact_identity_qualified', 'official_device_tests_executed', 'production_signing_qualified'])
            if lane == 'framework':
                need(value.get('same_fix_aliases_not_replayed') == specification['lanes'][lane]['aliases'], 'result alias scope differs')
        else:
            restoration = 'original_source_restored' if lane == 'avb' else 'all_five_original_source_files_restored'
            need(value.get(restoration) is True and value.get('original_Android_bp_preserved') is True and value.get('CVE') == ('CVE-2026-58956' if lane == 'avb' else 'CVE-2026-58936'), 'AVB/libpng result/restoration differs')
            false_fields(value, ['regression_executed', 'artifact_identity_qualified' if lane == 'avb' else 'vendor_artifact_identity_qualified'])
        originals.update(verify_restored(recipe, source, lane, specification))
        results[lane] = {'reference': ref, 'value': value}
    for row in list(originals.values()) + [r['reference'] for r in results.values()]:
        c.exact_file(row, row['path'], identity=True)
    return {'receipts': {k: v['reference'] for k, v in results.items()}, 'values': {k: v['value'] for k, v in results.items()}, 'restored_originals': originals,
            'runtime_qualified': False, 'production_ready': False}


def output_identity(row, out, expected_path):
    path = Path(expected_path); out = Path(out)
    need(path.is_absolute() and path != out and path.is_relative_to(out) and '..' not in path.parts, 'artifact escaped exact output root')
    ref = c.exact_file(row, path)
    need(ref['bytes'] > 0, 'empty compiled artifact')
    identity = ref['identity']
    actual = {'device': identity[0], 'inode': identity[1], 'mode': identity[2], 'uid': identity[3], 'gid': identity[4], 'nlink': identity[5],
              'mtime_seconds': identity[7] // 10**9, 'mtime_nanoseconds': identity[7] % 10**9,
              'ctime_seconds': identity[8] // 10**9, 'ctime_nanoseconds': identity[8] % 10**9}
    need(all(type(row.get(k)) is int and row[k] == v for k, v in actual.items()), 'complete original artifact identity differs')
    return ref


def framework_artifacts(out, value):
    out = Path(out); product = out / 'target/product' / p.PRODUCT
    rows = value.get('actual_output_files')
    need(type(rows) is list and len(rows) >= 6, 'complete framework artifacts missing')
    services = product / 'system/framework/services.jar'
    need(type(rows[0]) is dict and rows[0].get('path') == str(services), 'normal services.jar output missing')
    files = [output_identity(rows[0], out, services)]
    need(type(rows[-1]) is dict and set(rows[-1]) == {'module_info'}, 'actual module-info output missing')
    info_path = product / 'module-info.json'
    info_ref = output_identity(rows[-1]['module_info'], out, info_path)
    info, read_ref = c.read_json(info_path, 128 * 1024**2)
    need(read_ref == info_ref, 'module-info changed before complete parse')
    expected = []
    for module, provider in p.TEST_PROVIDERS.items():
        row = info.get(module)
        need(type(row) is dict and type(row.get('path')) is list and all(type(x) is str for x in row['path']) and provider in row['path'], 'official test provider differs: ' + module)
        installed = row.get('installed')
        need(type(installed) is list and all(type(x) is str for x in installed), 'invalid installed test artifact metadata')
        apks = [Path(x) for x in installed if Path(x).suffix == '.apk']
        need(apks and len({str(x) for x in apks}) == len(apks), 'missing or duplicate actual test APK')
        for path in apks:
            need(path.is_absolute() and path.is_relative_to(product) and '..' not in path.parts, 'test APK not in this exact absolute product output')
            expected.append((module, provider, path))
    need(len(rows[1:-1]) == len(expected), 'incomplete or extra declared test artifact')
    need(len({str(x[2]) for x in expected}) == len(expected), 'same APK reused across different official test modules')
    for row, (module, provider, path) in zip(rows[1:-1], expected):
        need(set(row) == {'module', 'provider', 'artifact'} and row['module'] == module and row['provider'] == provider, 'actual test artifact provider/order differs')
        files.append(output_identity(row['artifact'], out, path))
    files.append(info_ref)
    for row in files:
        c.exact_file(row, row['path'], identity=True)
    return files


def framework_completion(out, recipe, source, observed):
    receipts = security_completion(out, recipe, source, 'wm', observed)
    files = framework_artifacts(out, receipts['values']['framework'])
    receipts.pop('values')
    return {'normal_security_receipts': receipts, 'nonempty_whole_hashed_outputs': files,
            'official_device_tests_executed': False, 'binary_semantic_fix_qualified': False,
            'CP3A_framework_replacement_authorized': False, 'production_signing_qualified': False,
            'runtime_qualified': False, 'production_ready': False}
