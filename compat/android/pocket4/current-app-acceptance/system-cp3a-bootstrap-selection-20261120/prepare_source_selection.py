#!/usr/bin/env python3
"""Prepare a complete source-only successor for the existing 13-leaf selector.

This command creates files only under the isolated task directory. The separate
commit operation must use the original locks and the complete exact CURRENT CAS.
"""
import ast
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import time
import types

ROOT = Path('/home/alex/work/p4-cp3a-bootstrap-20261120-runtimeaudit-r1')
OUT = ROOT / 'selection-integration'
CANONICAL = Path('/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json')
CURRENT_SHA = 'b29be8cb340b4744c73df67046be421faf33ad00ea04bff84c4516e6def1d3bc'
CURRENT_F9 = [66306, 41717958, 33152, 1000, 1000, 1, 1579957, 1795169179610735957, 1795169179617736102]
HELPER_SHA = '5981eda642b2cc35a18979fddb2fd98e7a7ae0ba038a92f5f37370e2a808b401'
HANDOFF_SHA = 'cd65abd448cb936bff6aecd5f17311882537add6356ba62542fb5b5ec39d2a07'
GROUPS = (
    'business-system-cases-runtime-inputs-20261108-8b88-r2',
    'calendar-reminder-runtime-inputs-20261108-8b88-r2',
    'camera-app-photo-preparation-resume-20261107-r4',
    'camera-display',
    'clock-remaining-runtime-inputs-20261108-8b88-r2',
    'ihg-5.111.1-r1',
    'documents-saf11-runtime-inputs-20261108-8b88-r2',
    'documents-search-sort-runtime-inputs-20261108-8b88-r2',
)
ALLOWED_KEYS = {
    'application_qualification_preparations',
    'application_qualification_preparations_previous',
    'application_qualification_preparation_selection_scope',
    'application_current_route_audit',
    'application_current_IHG_identity',
}


def pin(value):
    return {k: value[k] for k in ('path', 'bytes', 'sha256')}


def read_ref(value, maximum=16 * 1024 * 1024):
    return h.read(value['path'], pin(value), maximum=maximum)


def json_ref(value):
    return json.loads(read_ref(value)[0])


def literal_profile(path, name):
    raw, _, _ = h.read(path)
    values = {}
    def literal(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = literal(node.left), literal(node.right)
            h.need(type(left) is type(right) is str, 'PROFILE_CONCATENATION_IS_STRINGS_ONLY')
            return left + right
        if isinstance(node, ast.Dict):
            return {literal(k): literal(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.List):
            return [literal(v) for v in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(literal(v) for v in node.elts)
        raise RuntimeError('NONLITERAL_PROFILE_EXPRESSION:' + name)
    matches = 0
    for node in ast.parse(raw).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            try:
                values[key] = literal(node.value)
            except RuntimeError:
                if key == name:
                    raise
                continue
            if key == name:
                matches += 1
    h.need(matches == 1, 'ONE_LITERAL_PROFILE:' + name)
    return values[name]


def check_profile(profile, row, artifacts):
    h.need(profile['package'] == row['package'] and profile['version_code'] == row['version_code'],
           'CURRENT_PACKAGE_VERSION_MISMATCH')
    expected = sorted((a['bytes'], a['sha256']) for a in artifacts)
    actual = sorted((a['bytes'], a['sha256']) for a in profile['apks'])
    h.need(actual == expected, 'CURRENT_COMPLETE_APK_SET_MISMATCH')


def source_status(obj):
    for key in ('production_ready', 'runtime_qualified'):
        h.need(obj.get(key) is False, 'SOURCE_MUST_NOT_CLAIM_RUNTIME:' + key)


def main():
    os.umask(0o077)
    h.need(not OUT.exists(), 'CREATE_ONLY_SOURCE_SELECTION_DIRECTORY')
    raw, current_ref, current_f9 = h.read(CANONICAL, maximum=2 * 1024 * 1024)
    h.need(current_ref['sha256'] == CURRENT_SHA and current_f9 == CURRENT_F9, 'EXACT_CURRENT_PREFLIGHT')
    current = json.loads(raw)
    h.need(raw == (json.dumps(current, sort_keys=True, separators=(',', ':')) + '\n').encode(),
           'ORIGINAL_COMPACT_CURRENT_REPRESENTATION')
    source_status(current)
    h.need(current['all_blockers_closed'] is False, 'KEEP_OPEN_RUNTIME_BLOCKERS')
    handoff_raw, handoff_ref, _ = h.read(ROOT / 'HANDOFF.json')
    h.need(handoff_ref['sha256'] == HANDOFF_SHA, 'PINNED_SOURCE_HANDOFF')
    handoff = json.loads(handoff_raw)
    for name in ('bootstrap_verification',):
        report = json_ref(handoff[name])
        h.need(report['verified'] is True and report['positive_count'] == 7
               and report['negative_count'] == 6 and report['original_input_bookends_unchanged'] is True,
               'COMPLETE_ORIGINAL_BOOTSTRAP_VERIFICATION')
        source_status(report)
    camera_report = json_ref(handoff['camera_display']['verification'])
    h.need(camera_report['positive']['returncode'] == 0 and len(camera_report['negative']) == 3
           and camera_report['all_other_AST_unchanged'] is True
           and camera_report['supervisor_methods_byte_identical'] == 20,
           'ORIGINAL_DISPLAY_WRAPPER_VERIFICATION')
    source_status(camera_report)
    candidate = json_ref(handoff['candidate_manifest'])
    h.bookend(candidate['original_input_bookends'])
    for source in candidate['source_files'].values():
        read_ref(source)
    old_selection_ref = pin(current['application_qualification_preparations'])
    selection = json_ref(old_selection_ref)
    old_route_ref = pin(current['application_current_route_audit']['map'])
    routes = json_ref(old_route_ref)
    inventory_ref = pin(current['final_selected_application_acceptance']['latest_artifact_inventory'])
    inventory = json_ref(inventory_ref)
    h.need(selection['schema'] == 'current-application-preparation-selection-v1'
           and len(selection['selected_preparations']) == 13 and selection['selection_only'] is True,
           'EXISTING_FORMAL_THIRTEEN_LEAF_SELECTOR')
    h.need(routes['schema'] == 'pocket4-current-42-app-executable-route-map-v1'
           and routes['inputs']['selected_preparations'] == old_selection_ref,
           'EXISTING_ROUTE_MAP_SELECTOR_RELATION')
    source_status(routes); source_status(inventory)
    h.need(inventory['selected_count'] == 42 and inventory['required_count'] == 39
           and inventory['runtime_accepted_count'] == 0 and len(inventory['applications']) == 39,
           'CURRENT_REQUIRED_THIRTY_NINE_SOURCE_SCOPE')
    required = {r['package']: r for r in inventory['applications']}
    exemptions = {r['package'] for r in inventory['exemptions']}
    h.need(exemptions == {'com.enflick.android.TextNow', 'com.pinger.textfree', 'com.ubercab'}
           and set(required) | exemptions == {r['package'] for r in routes['rows']},
           'EXACT_UNCHANGED_FORTY_TWO_PACKAGE_SET')
    by_group = {r['group']: r for r in handoff['preparations']}
    by_group['camera-display'] = {'preparation': handoff['camera_display']['preparation'],
                                  'entry': handoff['camera_display']['source']}
    new_refs = [by_group[group]['preparation'] for group in GROUPS]
    entries = [by_group[group]['entry'] for group in GROUPS]
    checks = []
    all_refs = new_refs + selection['selected_preparations'][8:]
    for i, prep_ref in enumerate(all_refs):
        packet = json_ref(prep_ref)
        if i < 8:
            h.need(packet.get('Android_execution_authorized_by_publication') is False,
                   'PREPARATION_PUBLICATION_CANNOT_AUTHORIZE_ANDROID')
        else:
            # The five retained Gallery packets have their original distinct schemas.
            # Preserve their exact existing refs; do not invent a new runtime admission.
            for flag in ('Android_execution_authorized_by_publication', 'Main_admission_authorized',
                         'whole_app_business_accepted', 'runtime_qualified', 'production_ready'):
                if flag in packet:
                    h.need(packet[flag] is False, 'RETAINED_GALLERY_MUST_NOT_CLAIM_RUNTIME')
        if i < 8:
            entry = entries[i]
        else:
            candidates = [leaf['entry_source'] for r in routes['rows'] for leaf in r['existing_leaf_entries']
                          if leaf['selection_index'] == i]
            h.need(len(candidates) == 1, 'ONE_RETAINED_GALLERY_ENTRY')
            entry = candidates[0]
        read_ref(entry)
        checks.append({'index': i, 'preparation': prep_ref, 'entry': entry,
                       'source_rebound': i < 8, 'runtime_qualified': False})
    # Compare immutable current payload identities with the actual selected source constants.
    profile_specs = (
        (0, 'system_profiles.py', 'CONTACTS', 'com.android.contacts'),
        (0, 'system_profiles.py', 'CALENDAR', 'com.android.calendar'),
        (1, 'system_profiles.py', 'CALENDAR', 'com.android.calendar'),
        (2, 'camera_profiles.py', 'CAMERA', 'com.android.camera2'),
        (4, 'clock_profiles.py', 'CLOCK', 'com.android.deskclock'),
        (5, 'app_profiles.py', 'CLOCK', 'com.android.deskclock'),
        (5, 'app_profiles.py', 'IHG', 'com.ihg.apps.android'),
        (6, 'documents_profiles.py', 'DOCUMENTS', 'com.android.documentsui'),
        (7, 'documents_profiles.py', 'DOCUMENTS', 'com.android.documentsui'),
    )
    profile_checks = []
    payload_bookends = []
    contract = json_ref(h.ref(ROOT / 'candidate/metadata/SOURCE-CONTRACT.json',
                              (ROOT / 'candidate/metadata/SOURCE-CONTRACT.json').read_bytes()))
    h.need({k: inventory['full_GSI_dependency'][k] for k in ('bytes', 'sha256')} == contract['full_GSI'],
           'SAME_CURRENT_FULL_GSI_SOURCE_IDENTITY')
    seen_payloads = set()
    for index, filename, name, package in profile_specs:
        profile = literal_profile(Path(entries[index]['path']).parent / filename, name)
        row = required[package]
        h.need(row['source_identity_verified'] is True and row['signature_verified'] is True
               and row['current_source_custody_verified'] is True, 'CURRENT_SOURCE_CUSTODY_REQUIRED')
        receipt = pin(row['source_custody_receipt']); read_ref(receipt)
        if row['kind'] == 'system':
            artifacts = [row['current_system_source_record']['apk']]
            h.need(profile == contract['bindings'][package]['profile'], 'REVIEWED_CP3A_PROFILE_CHANGED')
        else:
            artifacts = row['current_registry_record']['prepared_apks']
        check_profile(profile, row, artifacts)
        for artifact in artifacts:
            if artifact['path'] in seen_payloads:
                continue
            _, payload_ref, f9 = read_ref(artifact, maximum=128 * 1024 * 1024)
            payload_bookends.append({'ref': payload_ref, 'f9': f9})
            seen_payloads.add(artifact['path'])
        profile_checks.append({'index': index, 'package': package, 'profile': name,
            'version_code': row['version_code'], 'version_name': row['version_name'],
            'source_custody_receipt': receipt, 'exact_complete_APK_set_matches': True})
    negative = []
    sample = required['com.ihg.apps.android']; sample_artifacts = sample['current_registry_record']['prepared_apks']
    sample_profile = literal_profile(Path(entries[5]['path']).parent / 'app_profiles.py', 'IHG')
    for label, invalid in (('wrong-current-version', {**sample_profile, 'version_code': 0}),
                           ('wrong-current-apk-set', {**sample_profile, 'apks': []})):
        try:
            check_profile(invalid, sample, sample_artifacts)
        except RuntimeError as error:
            negative.append({'name': label, 'refused': True, 'error': str(error)})
        else:
            raise RuntimeError('CURRENT_IDENTITY_NEGATIVE_ACCEPTED')
    h.mkdir(OUT)
    before_ref = h.write(OUT / 'BEFORE-CURRENT.json', raw)
    validation = {'schema': 'pocket4-source-selector-full-closure-verification-v1',
        'current_preimage': {**current_ref, 'f9': current_f9}, 'current_inventory': inventory_ref,
        'previous_selection': old_selection_ref, 'previous_route_map': old_route_ref,
        'entries': checks, 'source_preparations_checked': 13, 'primary_entries_checked': 13,
        'changed_indices': list(range(8)), 'unchanged_indices': list(range(8, 13)),
        'profile_checks': profile_checks, 'current_payload_bookends': payload_bookends,
        'negative_controls': negative, 'bootstrap_verification': handoff['bootstrap_verification'],
        'display_verification': handoff['camera_display']['verification'],
        'source_only': True, 'Android_actions': 0, 'runtime_qualified': False, 'production_ready': False,
        'all_other_package_business_gates_unchanged': True}
    validation_ref = h.write(OUT / 'SOURCE-SELECTION-VALIDATION.json', h.encoded(validation))
    successor = copy.deepcopy(selection)
    successor['previous_selection'] = old_selection_ref
    successor['selected_preparations'] = all_refs
    successor['previous_identity_source_update'] = successor.pop('identity_source_update')
    successor['previous_source_closure_summary'] = successor['source_closure_summary']
    successor['source_closure_summary'] = validation_ref
    successor['unchanged_preparations'] = 5
    successor['source_file_identity_scope'] = 'Eight current source preparations rebound to reviewed official CP3A target/provider identities and IHG 5.111.1. Five Gallery source references are preserved as historical pending routes. No runtime or business credit is transferred.'
    successor.update({'source_only': True, 'runtime_qualified': False, 'production_ready': False,
        'source_selection_update': {'changed_indices': list(range(8)), 'unchanged_indices': list(range(8, 13)),
            'validation': validation_ref, 'current_inventory': inventory_ref,
            'runtime_enabled': False, 'current_Main_required': True}})
    selection_ref = h.write(OUT / 'selection-13.json', h.encoded(successor))
    updated_routes = copy.deepcopy(routes)
    updated_routes['created_ns'] = time.time_ns()
    updated_routes['inputs']['selected_preparations'] = selection_ref
    updated_routes['inputs']['previous_42_inventory'] = routes['inputs']['current_42_inventory']
    updated_routes['inputs']['current_42_inventory'] = inventory_ref
    updated_routes['inputs']['source_selection_validation'] = validation_ref
    updated_routes['previous_route_map'] = old_route_ref
    updated_routes['source_selection_update'] = {'changed_indices': list(range(8)), 'unchanged_indices': list(range(8, 13)),
        'source_only': True, 'runtime_enabled': False, 'source_checks': validation_ref}
    changed_leaves = 0
    for row in updated_routes['rows']:
        for leaf in row['existing_leaf_entries']:
            index = leaf['selection_index']
            h.need(leaf['preparation'] == selection['selected_preparations'][index], 'ORIGINAL_ROUTE_LEAF_BINDING')
            if index < 8:
                leaf['preparation'] = new_refs[index]
                leaf['entry_source'] = entries[index]
                changed_leaves += 1
        if row['package'] == 'com.android.deskclock':
            row['previous_identity_blocker'] = row.pop('identity_blocker')
            row['identity_blocker'] = 'Source now pins the official CP3A DeskClock in both selected leaves. Coherent full-GSI deployment, actual current Main/UID custody and all original Clock runtime gates remain pending.'
    h.need(changed_leaves == 10, 'EXACT_TEN_LEAF_OCCURRENCES_FOR_EIGHT_PREPARATIONS')
    h.need(updated_routes['common_gates'] == routes['common_gates']
           and updated_routes['profiles'] == routes['profiles'], 'ORIGINAL_BUSINESS_GATES_PRESERVED')
    for old, new in zip(routes['rows'], updated_routes['rows']):
        h.need(old['package'] == new['package'] and new['runtime_qualified'] is False
               and new['production_ready'] is False and new['accepted_gates'] == 0,
               'NO_ROUTE_RUNTIME_CREDIT')
        if all(i >= 8 for i in old['leaf_selection_indexes']):
            h.need(old == new, 'UNRELATED_PACKAGE_ROW_CHANGED')
    route_ref = h.write(OUT / 'APP-ROUTE-MAP.json', h.encoded(updated_routes))
    readme = ('# Current source selector integration\n\n'
        'The existing 13-entry selector now points indices 0 through 7 to the verified CP3A/IHG source preparations. '
        'Indices 8 through 12 are unchanged. The full 42-package route map retains all business gates and zero accepted gates.\n\n'
        'Source inspection succeeded for seven original application bootstraps and the Camera display wrapper. '
        'Nine original bootstrap/display negative controls and two current-identity mismatch controls refused invalid inputs. '
        'Nine profile occurrences match six freshly rehashed current APK identities and the current source custody receipts.\n\n'
        'This selection enables no Android runtime, installs no APK, and grants no business acceptance. '
        'The unchanged Gallery references still require a current official-image consumer. '
        'Calendar historical receipt checks and every original runtime admission remain mandatory.\n')
    readme_ref = h.write(OUT / 'README.md', readme.encode())
    replacements = {
        'application_qualification_preparations': selection_ref,
        'application_qualification_preparations_previous': old_selection_ref,
        'application_qualification_preparation_selection_scope': {
            'previous_scope': current['application_qualification_preparation_selection_scope'],
            'state': 'EIGHT_CURRENT_SOURCE_PREPARATIONS_SELECTED_RUNTIME_PENDING',
            'selected_preparations': 13, 'replaced': 8, 'unchanged': 5,
            'actual_source_validation': validation_ref, 'source_closure_summary': handoff['candidate_manifest'],
            'original_bootstrap_inspections_passed': 8, 'negative_controls_passed': 11,
            'historical_runtime_credit_transferred': False, 'Android_runtime_actions': 0,
            'runtime_passes': 0, 'runtime_qualified': False, 'production_ready': False},
        'application_current_route_audit': {**current['application_current_route_audit'],
            'map': route_ref, 'readme': readme_ref,
            'state': 'CURRENT_EIGHT_SOURCE_LEAVES_REBOUND_ALL_ORIGINAL_BUSINESS_GATES_PENDING',
            'source_selection_validation': validation_ref},
        'application_current_IHG_identity': {
            'previous_identity_source': current['application_current_IHG_identity'],
            'state': 'OFFICIAL_5_111_1_SOURCE_SELECTED_RUNTIME_PENDING', 'preparation': new_refs[5],
            'selection': selection_ref, 'previous_selection': old_selection_ref,
            'current_inventory': inventory_ref, 'source_custody_receipt': sample['source_custody_receipt'],
            'source_validation': validation_ref, 'public_commit': handoff['reviewed_commit'],
            'version_code': 50023808, 'version_name': '5.111.1', 'source_files': 31,
            'APK_installs': 0, 'runtime_acceptances': 0, 'runtime_qualified': False, 'production_ready': False},
    }
    h.need(set(replacements) == ALLOWED_KEYS, 'EXACT_SOURCE_POINTER_FIELDS_ONLY')
    draft = copy.deepcopy(current); draft.update(replacements)
    h.need({k: v for k, v in draft.items() if k not in ALLOWED_KEYS}
           == {k: v for k, v in current.items() if k not in ALLOWED_KEYS}, 'NO_UNRELATED_CURRENT_CHANGES')
    draft_raw = (json.dumps(draft, sort_keys=True, separators=(',', ':')) + '\n').encode()
    h.need(len(draft_raw) < 2 * 1024 * 1024, 'ORIGINAL_CURRENT_READER_LIMIT')
    draft_ref = h.write(OUT / 'AFTER-CURRENT.reviewed.json', draft_raw)
    h.bookend(candidate['original_input_bookends'])
    for row in payload_bookends:
        _, _, f9 = read_ref(row['ref'], maximum=128 * 1024 * 1024)
        h.need(f9 == row['f9'], 'CURRENT_PAYLOAD_METADATA_CHANGED')
    final_raw, _, final_f9 = h.read(CANONICAL, current_ref, maximum=2 * 1024 * 1024)
    h.need(final_raw == raw and final_f9 == current_f9, 'CURRENT_CHANGED_DURING_SOURCE_PREPARATION')
    plan = {'schema': 'pocket4-exact-source-selection-cas-plan-v1',
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'current_preimage': {**current_ref, 'f9': current_f9}, 'before_copy': before_ref,
        'reviewed_draft': draft_ref, 'changed_keys': sorted(ALLOWED_KEYS),
        'expected_before_values': {k: current[k] for k in sorted(ALLOWED_KEYS)},
        'replacement_values': replacements, 'source_selection': selection_ref,
        'route_map': route_ref, 'validation': validation_ref,
        'evidence': [handoff_ref, handoff['candidate_manifest'], handoff['bootstrap_verification'],
                     handoff['camera_display']['verification'], selection_ref, route_ref, readme_ref, validation_ref, inventory_ref],
        'original_owner': current['foreground_owner'], 'source_only': True,
        'Android_actions': 0, 'runtime_qualified': False, 'production_ready': False}
    plan_ref = h.write(OUT / 'CAS-PLAN.json', h.encoded(plan))
    print(json.dumps({'plan': plan_ref, 'selection': selection_ref, 'route_map': route_ref,
        'validation': validation_ref, 'reviewed_draft': draft_ref, 'current_unchanged': True,
        'source_only': True, 'profile_checks': len(profile_checks), 'unique_APKs_rehashed': len(payload_bookends)}, sort_keys=True))


if __name__ == '__main__':
    code = (ROOT / 'prepare_bootstrap.py').read_bytes()
    if hashlib.sha256(code).hexdigest() != HELPER_SHA:
        raise RuntimeError('SOURCE_HELPER_PIN_REQUIRED')
    h = types.ModuleType('source_helper'); h.__file__ = str(ROOT / 'prepare_bootstrap.py')
    exec(compile(code, h.__file__, 'exec'), h.__dict__)
    main()
