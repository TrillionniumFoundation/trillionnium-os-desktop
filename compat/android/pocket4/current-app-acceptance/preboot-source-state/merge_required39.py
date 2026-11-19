"""Join existing source receipts without installing, executing or re-verifying APKs.

This source-state successor is deliberately not an Android activation manifest.
It exposes all six newly closed inputs to the same 29-input registry consumer,
and binds the ten original GSI APKs to their coherent full-image dependency.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat


EXEMPT = {'com.enflick.android.TextNow', 'com.pinger.textfree', 'com.ubercab'}
SYSTEM = {'com.android.' + name for name in ('calendar', 'camera2', 'contacts',
    'deskclock', 'dialer', 'documentsui', 'gallery3d', 'messaging', 'quicksearchbox', 'settings')}
RETAINED = {'com.bestbuy.android', 'com.ehi.national.mobile', 'com.hertz.android.digital'}
MEITUAN = 'com.sankuai.meituan.takeoutnew'
SIX = RETAINED | {MEITUAN, 'com.ss.android.ugc.aweme', 'com.xunmeng.pinduoduo'}
COMPANION = 'com.android.vending'
NO_CREDIT = ('installed', 'runtime_qualified', 'native_compatibility_qualified',
             'business_qualified', 'production_ready')
GSI_SHA = 'dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4'


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite JSON number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def f9(metadata):
    return tuple(getattr(metadata, key) for key in ('st_dev', 'st_ino', 'st_mode',
        'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def pin(ref):
    return {key: ref[key] for key in ('path', 'bytes', 'sha256')}


def read(ref, root=None, held=None):
    need(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'} and
         type(ref['bytes']) is int and 0 <= ref['bytes'] <= 2 * 1024 * 1024 and
         type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}', ref['sha256']),
         'complete bounded metadata pin required')
    path = Path(ref['path'])
    if root is not None:
        need(not path.is_absolute() and '..' not in path.parts, 'relative member required')
        path = root / path
        need(path.resolve(strict=True).is_relative_to(root), 'member escaped publication')
    need(path.is_absolute() and path.resolve(strict=True) == path, 'canonical input required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             before.st_size == ref['bytes'], 'complete single-link regular file required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(ref['bytes'] + 1)
        need(len(raw) == ref['bytes'] and digest(raw) == ref['sha256'] and
             f9(before) == f9(os.fstat(fd)) == f9(path.lstat()), 'metadata bytes or F9 changed')
        if held is not None:
            need(held.setdefault(str(path), f9(before)) == f9(before), 'metadata bookend changed')
        return raw, {**ref, 'path': str(path)}
    finally:
        os.close(fd)


def check_backing(ref, held):
    """Read inode metadata only; never claim another whole-image/APK body hash."""
    path = Path(ref['path'])
    need(path.is_absolute() and path.resolve(strict=True) == path, 'canonical backing required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        value = os.fstat(fd)
        expected = tuple(int(x) for x in ref['identity'])
        need(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and
             value.st_size == ref['bytes'] and f9(value) == expected == f9(path.lstat()),
             'retained backing differs from the original freeze')
        need(held.setdefault(str(path), expected) == expected, 'backing bookend changed')
    finally:
        os.close(fd)


def no_credit(record, required=('installed', 'runtime_qualified', 'production_ready')):
    for key in required:
        need(record.get(key) is False, 'source-only record required: ' + key)
    for key in NO_CREDIT + ('device_profile_match_qualified', 'abi_compatibility_verified',
                            'native_execution_qualified', 'dispatch_runtime_observed'):
        if key in record:
            need(record[key] is False, 'unexpected execution credit: ' + key)


def indexed(rows, count):
    need(type(rows) is list and len(rows) == count, 'exact row count required')
    out = {row['package']: row for row in rows}
    need(len(out) == count, 'duplicate or omitted package')
    return out


def validate_indices(scope, registry, freshness, system, summary, freeze, result, previous):
    selected = scope['selected_packages']
    need(len(selected) == len(set(selected)) == 42 and
         len(scope['exemptions']) == 3 and {x['package'] for x in scope['exemptions']} == EXEMPT,
         'original 42 selection and exact three exemptions required')
    required = set(selected) - EXEMPT
    need(len(required) == 39 and SYSTEM <= required and COMPANION not in required,
         'required39 partition changed')
    apps = indexed(registry['applications'], 30)
    need(set(apps) == (required - SYSTEM) | {COMPANION}, '29 third-party inputs plus companion required')
    for package, app in apps.items():
        no_credit(app, NO_CREDIT)
        need(app['source_identity_verified'] is True and app['signature_verified'] is True and
             app['required39_member'] is (package != COMPANION) and
             app['retained_dependency_outside_required39'] is (package == COMPANION),
             'source identity or required39 membership changed')
    rs = registry['scope']
    no_credit(rs, NO_CREDIT)
    need(rs['selected_application_count'] == 42 and rs['required_application_count'] == 39 and
         rs['required_system_count'] == 10 and rs['required_third_party_count'] == 29 and
         rs['current_verified_third_party_source_input_count'] == 29 and
         rs['remaining_current_compatible_third_party_input_count'] == 0 and
         rs['extra_dependency_count'] == 1 and set(rs['excluded_packages']) == EXEMPT,
         'registry counts or exemptions changed')
    fr = indexed(freshness['rows'], 29)
    need(set(fr) == required - SYSTEM and set(freshness['excluded_packages']) == EXEMPT and
         freshness['selected_current_source_input_count'] == 29 and
         freshness['remaining_current_source_input_count'] == 0, 'freshness coverage changed')
    for package, row in fr.items():
        no_credit(row)
        need(row['source_input_selected'] is True and
             row['selected_input_version'] == apps[package]['version_name'], 'freshness identity changed')
        if 'selected_input_version_code' in row:
            need(row['selected_input_version_code'] == apps[package]['version_code'],
                 'freshness version code changed')
    systems = indexed(system['new_system_inputs'], 10)
    need(set(systems) == SYSTEM and summary['apps'] == system['new_system_inputs'],
         'exact original system10 state and summary required')
    no_credit(system)
    for item in (summary, freeze, result):
        no_credit(item, ('runtime_qualified', 'production_ready'))
    need(system['original_GSI_APKs_remain_bound_to_full_image_and_its_external_framework_and_native_dependencies'] is True and
         system['source_identity_does_not_establish_latest_check_for_all_33_on_index_date'] is True and
         system['previous23_evidence_ages_preserved'] is True and
         system['previous23_APK_bodies_reverified_in_this_step'] is False and
         set(system['original_three_exemptions']) == EXEMPT and
         set(system['remaining_required_source_inputs']) == SIX,
         'original system image, historical age or missing-input boundary changed')
    need(summary['source_only'] is True and summary['source_pass_count'] == 10 and
         summary['actual_SDK_commands'] == 30 and summary['actual_image_commands'] == 20 and
         freeze['all_original_body_F9_SHA_bookends_equal'] is True and
         result['success'] is True and result['source_pass_count'] == 10 and
         result['actual_verifier_scopes_retired'] is True, 'original actual system source closure required')
    image = summary['original_system_image']
    need(image['bytes'] == 2294853632 and image['sha256'] == GSI_SHA,
         'system10 must remain bound to the reviewed complete GSI')
    retained = {x['path']: x for x in freeze['retained_current_APK_pins']}
    need(len(retained) == 10, 'ten unique retained system APKs required')
    for row in systems.values():
        no_credit(row)
        need(row['source_identity_verified'] is True and retained.get(row['apk']['path']) == row['apk'],
             'system APK differs from the retained original source')
    prior = indexed(previous['rows'], 39)
    need(set(prior) == required and previous['all_production_ready'] is False and
         previous['source_pass_does_not_qualify_Android_device_profile_native_runtime_or_business'] is True and
         set(previous['remaining_current_compatible_inputs']) == SIX, 'previous source history changed')
    old23 = {p: x for p, x in prior.items() if x.get('source_verified_at_recorded_time') is True}
    need(len(old23) == 23 and set(old23) == required - SYSTEM - SIX, 'exact previous23 required')
    for package, row in old23.items():
        need(row['version_code'] == apps[package]['version_code'] and
             row['version_name'] == apps[package]['version_name'] and
             row['runtime_acceptance_granted_by_this_artifact'] is False and
             row['production_ready'] is False, 'previous23 source identity or no-credit changed')
        if 'expected_input' in row:
            need(row['expected_input'] == apps[package]['expected_input'], 'previous23 APK contract changed')
        else:
            need(row['input'] == apps[package]['input'] and
                 row['archive']['name'] == apps[package]['archive'] and
                 row['archive'] in registry['archives'], 'previous23 archive member or whole archive changed')
    need(apps[MEITUAN]['signer_migration_qualified'] is False, 'Meituan migration remains a separate gate')
    return apps, systems, old23


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.tzinfo is not None, 'timezone required')
    return parsed


def validate_six(app, candidate, receipt, native):
    package = app['package']
    need(package in SIX and candidate['package'] == package and
         candidate['version_code'] == app['version_code'] and
         candidate['version_name'] == app['version_name'], 'six-input candidate identity changed')
    no_credit(receipt)
    no_credit(native)
    need(native['application'] == {'package': package, 'expected_input': app['expected_input']},
         'complete existing native input contract required')
    expected = app['expected_input']
    need(expected['version_code'] == app['version_code'], 'input code differs')
    pins = {(a['name'], a['bytes'], a['sha256']) for a in expected['apks']}
    need(len(pins) == len(expected['apks']) and len({x[0] for x in pins}) == len(pins) and
         len({x[2] for x in pins}) == len(pins), 'unique complete APK set required')
    identities = receipt.get('identities', [receipt.get('identity')])
    standalone = 'identity' in receipt
    need(not standalone or (len(pins) == 1 and expected['apks'][0]['name'] == 'base.apk'),
         'standalone input uses exactly one canonical base member')
    need(len(identities) == len(pins) and
         len({x['sha256'] for x in identities}) == len(identities) and
         {(('base.apk' if standalone else x['filename']), x['bytes'], x['sha256'])
          for x in identities} == pins,
         'actual identities must cover every expected split exactly once')
    base = [x for x in identities if x['split_name'] is None]
    need(len(base) == 1 and base[0]['version_name'] == app['version_name'], 'one current base version required')
    for identity in identities:
        need(identity['package'] == package and identity['version_code'] == app['version_code'] and
             identity['version_name'] in ('', app['version_name']) and
             identity['signer_certificate_sha256'] == candidate['signer_certificate_sha256'] and
             identity['signature_verified'] is True and identity['executed'] is False and
             identity['verification_SDK_range'] == [37, 37] and
             identity['tool_exits'] == {'signature': 0, 'badging': 0, 'manifest': 0},
             'actual signed SDK37 identity required')
    if package in RETAINED:
        current = receipt['current_source_validation']
        observed = timestamp(current['latest_release_identity_observed_utc'])
        verified = timestamp(receipt['verified_utc'])
        due = timestamp(current['metadata_revalidation_due_utc'])
        need(current['current_metadata_restriction'] == 'UNAVAILABLE_COUNTRY' and
             current['current_metadata_release_identity_matches'] is True and
             current['current_delivery_obtained'] is False and app['current_delivery_obtained'] is False and
             receipt['current_delivery_obtained'] is False and native['current_delivery_obtained'] is False and
             due == observed + dt.timedelta(hours=24) and observed <= verified <= due and
             timestamp(app['metadata_revalidation_due_utc']) == due,
             'retain historical country restriction and exact 24h metadata deadline')
        closure = receipt['split_closure']
        need(closure['manifest_dependency_closure_verified'] is True and
             len(receipt['complete_zip_integrity']) == len(pins) and
             all(x['all_member_crc_verified'] is True for x in receipt['complete_zip_integrity']),
             'retained complete split and ZIP closure required')
    if package == MEITUAN:
        need(native['signer_migration_qualified'] is False and app['signer_migration_qualified'] is False,
             'Meituan signer migration is not source qualification')


def validate_system_receipt(row, receipt, image):
    no_credit(receipt)
    need(receipt['native_execution_qualified'] is False and
         receipt['source_identity_verified'] is True and
         receipt['signature_verified_for_api'] == 37 and
         receipt['independent_APK_crc_and_all_member_hashes_verified'] is True and
         receipt['package'] == row['package'] and receipt['apk'] == row['apk'] and
         receipt['source_image'] == image and receipt['original_image_path'] == row['image_path'] and
         receipt['version_code'] == row['version_code'] and receipt['version_code_major'] == 0 and
         receipt['version_name_sdk_resolved'] == row['version_name'] and
         receipt['signer_certificate_sha256'] == row['signer_certificate_sha256'] and
         receipt['selected_signing_scheme']['certificate_sha256'] == row['signer_certificate_sha256'],
         'system receipt identity must bind exact original APK and coherent full image')
    manifest = receipt['manifest']
    need(manifest['package'] == row['package'] and manifest['version_code'] == row['version_code'] and
         manifest['split_name'] is None and manifest['uses_split'] is None and
         manifest['required_split_types'] == [] and manifest['is_split_required'] is False,
         'system source manifest dependency fields changed')
    need(len(receipt['commands']) == 5 and all(x['exit'] == 0 and x['actual_child_reaped'] is True and
         x['original_pidfd_held_until_reaped'] is True for x in receipt['commands']),
         'original two image and three SDK command exits required')


def write(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2,
        sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def merge(spec_ref, root, output):
    root, output = Path(root), Path(output)
    need(root.is_absolute() and root.resolve(strict=True) == root, 'canonical publication root required')
    need(output.is_absolute() and output.parent.resolve(strict=True) == output.parent and
         not output.exists() and not output.is_symlink(), 'new isolated output required')
    held, reread, published = {}, [], {}
    spec_raw, exact_spec = read(spec_ref, held=held)
    reread.append((spec_ref, None))
    spec = parse(spec_raw)
    need(spec['schema'] == 'pocket4-required39-source-merge-spec-v1' and
         len(spec['new_six_packages']) == 6 and set(spec['new_six_packages']) == SIX,
         'explicit reviewed merge spec required')
    originals, inputs, raws = {}, {}, {}
    for name, ref in spec['inputs'].items():
        base = None if Path(ref['path']).is_absolute() else root
        raw, observed = read(ref, base, held)
        originals[name], inputs[name], raws[name] = observed, parse(raw), raw
        reread.append((ref, base))
    apps, systems, old23 = validate_indices(**{name: inputs[name] for name in
        ('scope', 'registry', 'freshness')}, system=inputs['system_state'],
        summary=inputs['system_summary'], freeze=inputs['system_freeze'],
        result=inputs['system_result'], previous=inputs['previous23_state'])
    system, summary, freeze, result = (inputs[x] for x in
        ('system_state', 'system_summary', 'system_freeze', 'system_result'))
    need(pin(system['previous23_state']) == originals['previous23_state'] and
         result['current_state'] == freeze['current_state'] == originals['system_state'] and
         result['summary'] == freeze['summary'] == originals['system_summary'] and
         result['source_freeze'] == originals['system_freeze'], 'original owner source chain changed')
    refs = spec['publication_proofs']
    need(len({ref['path'] for ref in refs}) == len(refs), 'duplicate proof member')
    expected_proofs = {r['path']: r for p in SIX for r in apps[p]['proofs'].values()}
    need({r['path']: r for r in refs} == expected_proofs, 'complete six-input proof closure required')
    for ref in refs:
        raw, observed = read(ref, root, held)
        published[ref['path']] = (raw, observed)
        reread.append((ref, root))
    for package in sorted(SIX):
        app = apps[package]
        def proof(name):
            return parse(published[app['proofs'][name]['path']][0])
        candidate, receipt, native = (proof(x) for x in
            ('candidate.json', 'source-receipt.json', 'native-input.json'))
        need(pin(receipt['candidate'])['bytes'] == app['proofs']['candidate.json']['bytes'] and
             receipt['candidate']['sha256'] == app['proofs']['candidate.json']['sha256'] and
             native['candidate']['sha256'] == app['proofs']['candidate.json']['sha256'] and
             native['candidate']['bytes'] == app['proofs']['candidate.json']['bytes'] and
             pin(app['expected_input']['source_receipt'])['bytes'] == app['proofs']['source-receipt.json']['bytes'] and
             app['expected_input']['source_receipt']['sha256'] == app['proofs']['source-receipt.json']['sha256'],
             'six-input original candidate/receipt content binding changed')
        validate_six(app, candidate, receipt, native)
    image = summary['original_system_image']
    check_backing(image, held)
    freeze_pins = {x['path']: pin(x) for x in freeze['input_pins']}
    receipt_observations = []
    for package, row in sorted(systems.items()):
        need(freeze_pins.get(row['source_receipt']['path']) == row['source_receipt'],
             'system receipt missing from original source freeze')
        raw, observed = read(row['source_receipt'], held=held)
        reread.append((row['source_receipt'], None))
        validate_system_receipt(row, parse(raw), image)
        check_backing(row['apk'], held)
        receipt_observations.append({'package': package, 'receipt': observed,
            'receipt_full_bytes_and_F9_verified': True, 'APK_F9_matches_original_freeze': True})
    for ref, base in reread:
        read(ref, base, held)
    check_backing(image, held)
    for row in systems.values():
        check_backing(row['apk'], held)
    output.mkdir(mode=0o700)
    files = []
    actual_registry = write(output / 'current-source-inputs.json', raws['registry'])
    actual_freshness = write(output / 'current-source-freshness.json', raws['freshness'])
    files += [actual_registry, actual_freshness]
    proof_map = {}
    (output / 'proofs').mkdir(mode=0o700)
    for index, (original, (raw, observed)) in enumerate(sorted(published.items())):
        target = output / 'proofs' / ('%02d-' % index + Path(original).name)
        copied = write(target, raw)
        files.append(copied)
        proof_map[original] = copied
    six_inputs = []
    for package in sorted(SIX):
        app = apps[package]
        six_inputs.append({'package': package, 'version_code': app['version_code'],
            'version_name': app['version_name'], 'original_host': app['storage']['host'],
            'original_input': app['input'], 'expected_input': app['expected_input'],
            'proofs': {name: proof_map[ref['path']] for name, ref in app['proofs'].items()},
            'fresh_destination_custody_required_before_installation': True,
            'signer_migration_qualified': False if package == MEITUAN else None,
            **{key: False for key in NO_CREDIT}})
    consumer = write(output / 'six-new-source-inputs.json', {
        'schema': 'pocket4-six-source-input-consumer-manifest-v1',
        'applications': six_inputs, 'current29_registry': actual_registry,
        'copied_proof_bytes_identical_to_published_sources': True,
        'transport_or_installation_performed': False, **{key: False for key in NO_CREDIT}})
    files.append(consumer)
    applications = []
    for package in sorted(set(apps) - {COMPANION}):
        applications.append({'package': package, 'kind': 'third_party',
            'unchanged_current_registry_record': apps[package],
            'source_identity_verified': True, 'latest_qualified_at_merge_time': False,
            **{key: False for key in NO_CREDIT}})
    for package in sorted(systems):
        applications.append({'package': package, 'kind': 'system',
            'unchanged_original_system_record': systems[package],
            'install_mode': 'coherent_full_GSI_with_framework_and_native_dependencies',
            'individual_APK_install_authorized': False, 'source_identity_verified': True,
            'latest_qualified_at_merge_time': False, **{key: False for key in NO_CREDIT}})
    state = {
        'schema': 'pocket4-required39-source-state-successor-v1',
        'scope_id': spec['scope_id'], 'base_commit': spec['base_commit'],
        'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'source_evidence_count': 39, 'third_party_source_evidence_count': 29,
        'system_source_evidence_count': 10, 'selected_count': 42, 'required_count': 39,
        'remaining_missing_source_inputs': [], 'exemptions': inputs['scope']['exemptions'],
        'applications': sorted(applications, key=lambda x: x['package']),
        'retained_dependency_outside_required39': apps[COMPANION],
        'current29_registry': actual_registry, 'current29_freshness': actual_freshness,
        'six_new_source_inputs': consumer, 'source_inputs': originals,
        'full_GSI_dependency': image, 'individual_system_APK_installation_allowed': False,
        'all_39_latest_qualified': False, 'all_39_runtime_accepted': False,
        'existing_23_registry_records_unchanged': True, 'owner_history_ages_preserved': True,
        'owner_history_raw_private_URLs_embedded': False,
        'original_system10_receipts_rechecked': receipt_observations,
        'required_before_installation': {
            'final_coherent_Android_GSI_framework_vendor_native_cohort': 'PENDING',
            'fresh_destination_custody_for_every_selected_APK_and_split': 'PENDING',
            'final_actual_UID_package_identity_and_runtime_gate_manifest': 'PENDING',
            'Meituan_official_signer_and_existing_userdata_migration': 'PENDING',
            'Beike_current_publisher_refresh_and_qualification': 'PENDING',
            'fresh_official_metadata_for_retained_Play_inputs': {
                p: {'historical_expiry': apps[p]['metadata_revalidation_due_utc'],
                    'activation_metadata_revalidated': False,
                    'restriction': 'UNAVAILABLE_COUNTRY', 'new_delivery_obtained': False}
                for p in sorted(RETAINED)},
            'latest_release_recheck_for_every_required_application': 'PENDING',
            'actual_business_and_common_gates_for_all_required39': 'PENDING',
            'any_required_user_login_or_SMS': 'EXTERNAL_GATE_IF_ENCOUNTERED'},
        'new_SDK_commands': 0, 'new_downloads': 0, 'APK_or_image_bodies_read': 0,
        'Android_actions': 0, 'owner_CURRENT_changed': False,
        **{key: False for key in NO_CREDIT}}
    state_ref = write(output / 'CURRENT-SOURCE-STATE.json', state)
    files.append(state_ref)
    # Re-read original inputs after publication; no success receipt if custody changed.
    for ref, base in reread:
        read(ref, base, held)
    check_backing(image, held)
    for row in systems.values():
        check_backing(row['apk'], held)
    answer = {'schema': 'pocket4-required39-source-merge-result-v1', 'success': True,
        'spec': exact_spec, 'current_state': state_ref, 'files': files,
        'source_evidence_count': 39, 'required_runtime_acceptances': 39,
        'runtime_acceptance_count': 0, 'original_input_bookends_equal': True,
        'new_SDK_commands': 0, 'APK_or_image_bodies_read': 0, 'Android_actions': 0,
        'latest_release_qualification_granted': False, **{key: False for key in NO_CREDIT}}
    result_ref = write(output / 'RESULT.json', answer)
    delivery = write(output / 'DELIVERY.json', {'schema': 'pocket4-source-merge-delivery-v1',
        'result': result_ref, 'current_state': state_ref, 'current29_registry': actual_registry,
        'six_new_source_inputs': consumer, **{key: False for key in NO_CREDIT}})
    return {'result': result_ref, 'delivery': delivery, 'current_state': state_ref}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--expect-spec-sha256', required=True)
    parser.add_argument('--publication-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    ref = {'path': str(Path(args.spec)), 'bytes': Path(args.spec).stat().st_size,
           'sha256': args.expect_spec_sha256}
    print(json.dumps(merge(ref, args.publication_root, args.output), sort_keys=True))
