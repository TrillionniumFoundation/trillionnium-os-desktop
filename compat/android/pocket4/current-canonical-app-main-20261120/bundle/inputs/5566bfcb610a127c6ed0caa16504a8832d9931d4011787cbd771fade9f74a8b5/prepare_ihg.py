"""Create an isolated IHG source preparation; never invoke Android or install.

The reviewed public business capsule supplies all 31 source files, including
the Clock readback fix. Only four IHG identity literals change. The original
preparation, selector, all runtime guards and their identities remain intact.
"""
from __future__ import annotations

import argparse
import ast
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types


PACKAGE = 'com.ihg.apps.android'
CURRENT = {'version_code': 50023808, 'version_name': '5.111.1',
           'bytes': 47680737,
           'sha256': '5357f9e3d483cad7b5bc09cb69d353da4b459a4df53860de3d96a0f062d1499a',
           'signer': '1448dc9480a27e52b06c886b3f6386f2b122b115b1df1f156b81b9aebcc73163'}
CHANGES = {
    'app_profiles.py': [('50023496', '50023808'), ('47668450', '47680737'),
        ('1b2c410b16e9f8e69fcc53d97138d7e8c3e7a1e500abb5372f3700d2a950af4f', CURRENT['sha256'])],
    'ihg_artifacts.py': [('VERSION = 50023496', 'VERSION = 50023808')],
}


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite JSON number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def f9(s):
    return tuple(getattr(s, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def read(ref, root=None, bookends=None):
    need(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'} and
         type(ref['bytes']) is int and 0 <= ref['bytes'] <= 2 * 1024 * 1024 and
         re.fullmatch('[0-9a-f]{64}', ref['sha256']), 'bounded explicit input pin required')
    path = Path(ref['path'])
    if root is not None:
        need(not path.is_absolute() and '..' not in path.parts, 'relative publication member required')
        path = root / path
        need(path.resolve(strict=True).is_relative_to(root), 'publication member escaped root')
    need(path.is_absolute() and path.resolve(strict=True) == path, 'canonical input required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             before.st_size == ref['bytes'], 'complete regular input required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(ref['bytes'] + 1)
        need(len(raw) == ref['bytes'] and sha(raw) == ref['sha256'] and
             f9(before) == f9(os.fstat(fd)) == f9(path.lstat()), 'input pin or F9 changed')
        if bookends is not None:
            previous = bookends.setdefault(str(path), f9(before))
            need(previous == f9(before), 'input F9 changed between bookends')
        return raw, {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}
    finally:
        os.close(fd)


def write(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True,
        indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def module(raw, path):
    result = types.ModuleType(Path(path).stem)
    result.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), result.__dict__)
    return result


def verify_current(candidate, receipt, badging):
    need(candidate['schema'] == 'pocket4-publisher-delivery-standalone-candidate-v1' and
         candidate['package'] == PACKAGE and candidate['version_name'] == CURRENT['version_name'] and
         candidate['version_code'] == CURRENT['version_code'] and candidate['version_code_major'] == 0 and
         candidate['signer_certificate_sha256'] == [CURRENT['signer']] and
         candidate['selected_abi'] == 'arm64-v8a', 'exact current signed candidate required')
    need(len(candidate['apks']) == 1 and candidate['apks'][0]['member'] == 'base.apk' and
         candidate['apks'][0]['split_name'] is None and candidate['apks'][0]['bytes'] == CURRENT['bytes'] and
         candidate['apks'][0]['sha256'] == CURRENT['sha256'], 'one exact current base APK required')
    need(receipt['schema'] == 'pocket4-verified-publisher-delivery-source-receipt-v1' and
         receipt['all_original_delivery_apks_verified'] is True and receipt['installed'] is False and
         receipt['runtime_qualified'] is False and receipt['production_ready'] is False and
         receipt['native_compatibility_qualified'] is False, 'source-only verified receipt required')
    need(len(receipt['identities']) == len(receipt['binary_metadata']) ==
         len(receipt['original_delivery_apks']) == len(receipt['complete_zip_integrity']) == 1,
         'exact complete single-APK receipt required')
    identity = receipt['identities'][0]
    need(identity['package'] == PACKAGE and identity['version_code'] == CURRENT['version_code'] and
         identity['version_name'] == CURRENT['version_name'] and identity['bytes'] == CURRENT['bytes'] and
         identity['sha256'] == CURRENT['sha256'] and identity['split_name'] is None and
         identity['signature_verified'] is True and identity['signer_certificate_sha256'] == [CURRENT['signer']] and
         identity['tool_exits'] == {'badging': 0, 'manifest': 0, 'signature': 0} and
         identity['verification_SDK_range'] == [37, 37], 'actual SDK37 identity required')
    need(receipt['split_closure']['manifest_dependency_closure_verified'] is True and
         receipt['split_closure']['standalone_dependency_absence_verified'] is True and
         receipt['split_closure']['base_count'] == 1 and receipt['split_closure']['split_count'] == 0 and
         receipt['complete_zip_integrity'][0]['all_member_crc_verified'] is True,
         'standalone closure and complete ZIP proof required')
    need(badging['returncode'] == 0 and badging['stderr'] == '' and
         badging['source_bookends_equal'] is True and badging['APK']['bytes'] == CURRENT['bytes'] and
         badging['APK']['sha256'] == CURRENT['sha256'] and
         sha(badging['stdout'].encode()) == badging['stdout_sha256'] == identity['tool_output_sha256']['badging'],
         'fresh actual launcher observation must reproduce the signed receipt')
    lines = badging['stdout'].splitlines()
    package = [line for line in lines if line.startswith('package:')]
    launcher = [line for line in lines if line.startswith('launchable-activity:')]
    need(len(package) == len(launcher) == 1 and
         "name='com.ihg.apps.android' versionCode='50023808' versionName='5.111.1'" in package[0] and
         "name='com.ihg.apps.android.activity.MainActivity'" in launcher[0], 'exact unchanged current launcher required')


def transform(raws):
    need(len(raws) == 31 and set(CHANGES).issubset(raws), 'complete 31-source packet required')
    output = {}
    for name, raw in raws.items():
        text = raw.decode('utf-8')
        for before, after in CHANGES.get(name, []):
            need(text.count(before) == 1 and after not in text, 'unique literal preimage required')
            text = text.replace(before, after, 1)
        inverse = text
        for before, after in reversed(CHANGES.get(name, [])):
            inverse = inverse.replace(after, before, 1)
        need(inverse.encode() == raw, 'undeclared source change')
        ast.parse(text, filename=name)
        output[name] = text.encode()
    need({name for name in raws if raws[name] != output[name]} == set(CHANGES), 'only two identity sources may change')
    return output


def prepare(spec_ref, publication_root, output):
    need(os.getuid() == os.geteuid() == 0, 'root required only for protected preparation input reads')
    root = Path(publication_root)
    need(root.is_absolute() and root.resolve(strict=True) == root, 'canonical publication root required')
    bookends = {}
    spec_raw, exact_spec = read(spec_ref, bookends=bookends)
    spec = parse(spec_raw)
    need(spec['schema'] == 'pocket4-ihg-preboot-source-rebind-spec-v1', 'exact source rebind spec required')
    held = [(spec_ref, None)]
    published = {}
    for name, ref in spec['publication_inputs'].items():
        raw, observed = read(ref, root, bookends)
        published[name] = (raw, observed)
        held.append((ref, root))
    base_manifest = parse(published['base_manifest'][0])
    raws = {}
    for row in base_manifest['sources']:
        need(row['path'].startswith('source/') and len(Path(row['path']).parts) == 2,
             'flat business source member required')
        ref = {**row, 'path': spec['business_directory'] + '/' + row['path']}
        raw, observed = read(ref, root, bookends)
        name = Path(row['path']).name
        need(name not in raws, 'duplicate source name')
        raws[name] = raw
        held.append((ref, root))
    successor = transform(raws)
    candidate = parse(published['candidate'][0])
    receipt = parse(published['receipt'][0])
    badging = parse(published['badging'][0])
    need(receipt['candidate']['bytes'] == len(published['candidate'][0]) and
         receipt['candidate']['sha256'] == sha(published['candidate'][0]), 'receipt candidate pin changed')
    verify_current(candidate, receipt, badging)
    old_raw, old_ref = read(spec['previous_preparation'], bookends=bookends)
    old = parse(old_raw)
    selector_raw, selector_ref = read(spec['previous_selection'], bookends=bookends)
    selector = parse(selector_raw)
    need(len(selector['selected_preparations']) == 13 and
         selector['selected_preparations'][5] == old_ref, 'exact existing thirteen-selector entry required')
    need(len(old['files']) == 31 and {Path(x['path']).name for x in old['files']} == set(raws),
         'full original preparation source required')
    for ref in old['files'] + old['origins'] + selector['selected_preparations']:
        raw, observed = read(ref, bookends=bookends)
        held.append((ref, None))
        if ref in old['files']:
            name = Path(ref['path']).name
            expected = raws[name]
            if name == 'timer_flow.py':
                text = expected.decode()
                for before, after in reversed(base_manifest['literal_changes']['timer_flow.py']):
                    need(text.count(after) == 1, 'reviewed Clock fix preimage changed')
                    text = text.replace(after, before, 1)
                expected = text.encode()
            need(raw == expected, 'original preparation differs from reviewed publication')
    held.extend([(spec['previous_preparation'], None), (spec['previous_selection'], None)])
    out = Path(output)
    need(out.is_absolute() and out.parent.resolve(strict=True) == out.parent and not out.exists(),
         'new isolated output root required')
    os.umask(0o077)
    out.mkdir(mode=0o700)
    (out / 'source').mkdir(mode=0o700)
    files = [write(out / 'source' / name, successor[name]) for name in sorted(successor)]
    updated = copy.deepcopy(old)
    updated['files'] = files
    updated['origins'] += [old_ref, exact_spec] + [ref for _, ref in published.values()]
    updated['source_graph_generation'] = '20261119-11ea-ihg-5.111.1-and-reviewed-clock-source-r1'
    updated['source_dependency_scope'] += (' Complete reviewed Clock readback successor retained; IHG exact '
        'official 5.111.1/50023808 source identity. Fresh Main, UID, destination custody and business evidence remain required.')
    preparation = write(out / 'preparation.json', updated)
    common = module(successor['app_common.py'], out / 'source/app_common.py')
    planner = module(successor['app_plan.py'], out / 'source/app_plan.py')
    planner.preparation(common, preparation)
    # Replay the existing 23 finite source controls with the current identity;
    # their synthetic values never become runtime or installed observations.
    manifest = copy.deepcopy(base_manifest)
    manifest['current_version_code'] = CURRENT['version_code']
    manifest['official_candidate'] = {'path': candidate['apks'][0]['delivery_path'],
        'bytes': CURRENT['bytes'], 'sha256': CURRENT['sha256']}
    manifest['sources'] = [{**row, 'path': 'source/' + Path(row['path']).name} for row in files]
    manifest['successor_preparation'] = preparation
    for name in CHANGES:
        for pair in manifest['literal_changes'][name]:
            for before, after in CHANGES[name]:
                if pair[1] == before:
                    pair[1] = after
    write(out / 'manifest.json', manifest)
    test = published['base_tests'][0].decode().replace('50023496', '50023808').replace('50023497', '50023809')
    write(out / 'test_source.py', test.encode())
    write(out / 'host-result.json', {'schema': 'pocket4-preboot-no-runtime-credit-v1',
        'runtime_qualified': False, 'production_ready': False, 'canonical_selection_changed': False,
        'runtime_accepted': 0, 'Android_actions': 0, 'apps_installed': 0})
    tested = subprocess.run([sys.executable, '-I', '-B', str(out / 'test_source.py')],
        capture_output=True, timeout=30, cwd=out)
    stdout = write(out / 'source-controls.stdout', tested.stdout)
    stderr = write(out / 'source-controls.stderr', tested.stderr)
    need(tested.returncode == 0 and re.search(rb'Ran 23 tests in .*\n\nOK\n', tested.stderr),
         'all original identity and Clock controls must pass')
    for ref, base in held:
        read(ref, base, bookends)
    result = write(out / 'RESULT.json', {'schema': 'pocket4-ihg-preboot-source-rebind-result-v1',
        'previous_preparation': old_ref, 'previous_selection': selector_ref,
        'new_preparation': preparation, 'specification': exact_spec,
        'source_files': 31, 'identity_changed_files': sorted(CHANGES), 'identity_literal_changes': 4,
        'byte_identical_to_reviewed_public_business_files': 29, 'reviewed_clock_fix_included': True,
        'actual_preparation_validator_passed': True, 'original_host_controls_passed': 23,
        'source_controls_stdout': stdout, 'source_controls_stderr': stderr,
        'original_input_bookends_equal': True, 'APK_path_is_source_location_only': True,
        'fresh_destination_custody_required': True, 'fresh_current_main_and_UID_observation_required': True,
        'historical_uid_is_requirement_not_new_runtime_observation': 10137,
        'official_metadata_observed_utc': candidate['source']['observed_utc'],
        'latest_check_must_be_refreshed_before_activation': True,
        'installed': False, 'runtime_qualified': False, 'native_compatibility_qualified': False,
        'whole_app_business_accepted': False, 'production_ready': False,
        'canonical_selection_changed': False, 'CURRENT_writes': 0, 'Android_actions': 0,
        'apps_installed': 0, 'runtime_accepted': 0,
        'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    new_selection = copy.deepcopy(selector)
    new_selection['selected_preparations'][5] = preparation
    new_selection.setdefault('identity_source_update_history', []).append(new_selection['identity_source_update'])
    new_selection['identity_source_update'] = {'schema': 'pocket4-selected-app-source-identity-update-v1',
        'old_preparation': old_ref, 'new_preparation': preparation, 'result': result,
        'changed_selection_entries': 1, 'selected_index': 5, 'unchanged_selection_entries': 12,
        'Android_actions': 0, 'runtime_qualified': False}
    new_selection['previous_selection'] = selector_ref
    new_selection['source_file_identity_scope'] += (' New selected entry 5 binds reviewed Clock readback '
        'and IHG 5.111.1/50023808; earlier IHG versions are historical. No runtime credit transferred.')
    need([row for i, row in enumerate(new_selection['selected_preparations']) if i != 5] ==
         [row for i, row in enumerate(selector['selected_preparations']) if i != 5], 'other twelve preparations changed')
    selected = write(out / 'selection-13.json', new_selection)
    delivery = write(out / 'DELIVERY.json', {'schema': 'pocket4-ihg-preboot-source-rebind-delivery-v1',
        'previous_selection': selector_ref, 'selection': selected, 'preparation': preparation,
        'result': result, 'changed_indices': [5], 'unchanged_entries': 12,
        'canonical_selection_changed': False, 'runtime_qualified': False, 'production_ready': False})
    print(json.dumps({'delivery': delivery, 'selection': selected, 'result': result,
        'runtime_qualified': False, 'production_ready': False}, sort_keys=True))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec', required=True, type=Path)
    p.add_argument('--expect-spec-sha256', required=True)
    p.add_argument('--publication-root', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    need(re.fullmatch('[0-9a-f]{64}', args.expect_spec_sha256), 'external specification SHA256 required')
    prepare({'path': str(args.spec), 'bytes': args.spec.stat().st_size,
        'sha256': args.expect_spec_sha256}, args.publication_root, args.output)


if __name__ == '__main__':
    main()
