#!/usr/bin/env python3
"""Project pinned saved Clock evidence into a text-only, privacy-limited bundle.

No device calls. Originals remain unchanged. This proposes one scoped identity
review; it does not edit the readiness registry or turn Alarm04 into a pass.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import copy
import hashlib
import json

HERE = Path(__file__).resolve().parent
CLOCK = HERE.parent
OUT = CLOCK / 'runtime04-public'
PREFIX = 'inputs/clock-runtime04'
SOURCES = {
    'saved_export': (HERE / 'saved-export04.json', 'd6131a5f9a4c3907717caa3d013cfa42afe26b78d808f5d5f5d0c36a5ec95706'),
    'runtime': (CLOCK / 'runtime04-label-corrected/actual-result04-original.json', 'ef32be14277156c79f653c942c9d55b32addc8b293ad6e886c3b2508173c5143'),
    'alarm': (HERE / 'alarm04-result-original.json', 'd67ee63b7762adb2a5f4ee66455d15dbd50ab1c41a46683f9172ec8b513b2cec'),
    'review': (HERE / 'INDEPENDENT_CLOCK_INVENTORY_REVIEW.json', '03758fd88f59ae6cf4252b8517c2337afbd2524e3ab79ef1dee7a70973ba3971'),
    'inventory': (HERE / 'ELF_INVENTORY04.json', 'c4f526bc60d577a0f047008654e810be7d7a994d5bc63008533f983e815d3f1e'),
    'install': (CLOCK / 'candidate/alarm-dispatch04/install04-result-original.json', 'efaf58417685c13d7abb6a2c1a9687ee0b70a998d5ded76cdb029376cef4e936'),
    'identity': (CLOCK / 'candidate/alarm-dispatch04/latest-installed-identity04-original.json', '1750f0c49dad70f0fb8178655ba82dcc5ef6e6b2a195c06c45e49571bca9c314'),
    'build': (CLOCK / 'candidate/alarm-dispatch04/build04-result-original.json', '4b4e23003f52b80f896cff316b930095ef4dd959e0fdbcb99b2ea0fc674b6881'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def put(name, value, raw=False):
    data = value if raw else encode(value)
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
    return {'path': name, 'bytes': len(data), 'sha256': sha(data)}


def main():
    originals = {}
    for name, (path, pin) in SOURCES.items():
        raw = path.read_bytes()
        assert sha(raw) == pin, name
        originals[name] = {'value': json.loads(raw), 'raw': raw, 'bytes': len(raw), 'sha256': pin}
    export, runtime, alarm, review, inventory, install, identity, build = [originals[n]['value']
        for n in ('saved_export', 'runtime', 'alarm', 'review', 'inventory', 'install', 'identity', 'build')]
    apk = identity['installed_apk_sha256']
    assert apk == '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d'
    assert runtime['APK']['sha256'] == apk == build['candidate_apk']['sha256']
    assert identity == install['installed_identity_observation']
    assert install['state'] == 'INSTALLED_VERIFIED' and install['install_response_verified'] is True
    assert identity['package_and_apk_readback_verified'] is True
    assert identity['uid'] == 10063 and identity['android_user'] == 0 and identity['version_code'] == 37
    assert runtime['sampler']['sample_count'] == 626 and runtime['sampler']['thread_joined'] is True
    assert runtime['runtime_identity_automatically_qualified'] is False
    assert runtime['sampler']['stable_complete_mapping_samples'] == 0
    assert alarm['state'] == 'FAILED' and alarm['business_success_verified'] is False
    assert alarm['actual_firing_verified'] is True and alarm['actual_alarm_notification_posted'] is True
    assert alarm['error'] == 'RuntimeError: ACTUAL_ALARM_ALERT_NOT_ONE_NEW_TASK'
    assert alarm['owned_alarm_cleanup_verified'] is True and alarm['task_set_restored'] is True
    assert all(alarm.get(k) is None for k in ('pending_effect', 'pending_database_effect', 'close_pending',
        'owned_task_remaining', 'final_guard_error', 'cleanup_error', 'outer_error'))
    assert review['all_scope_checks_passed'] is True and review['whole_hashed_ELF_union_count'] == 381
    assert sha(originals['inventory']['raw']) == review['ELF_inventory_sha256']
    assert runtime['guard_before'] == runtime['guard_after']
    assert identity['epoch_sha256'] == runtime['guard_before']['epoch_sha256'] == alarm['epoch_sha256']
    OUT.mkdir()
    files = []
    input_pins = {k: {'bytes': v['bytes'], 'sha256': v['sha256']} for k, v in originals.items()}
    input_pins['private_originals_retained_unmodified'] = True
    files.append(put('ORIGINAL_INPUT_PINS.json', input_pins))
    files.append(put('ELF_INVENTORY.json', originals['inventory']['raw'], raw=True))
    generations = sorted(review['stable_full_counts_by_generation'],
        key=lambda key: min(s['utc'] for s in review['selected_snapshots'] if s['generation'] == key))
    aliases = {key: 'generation-%d' % (i + 1) for i, key in enumerate(generations)}
    selected = []
    by_source = {s['source_name']: s for s in review['selected_snapshots']}
    for _, entry in sorted(export['runtime_selections'].items(), key=lambda item: item[1]['row']['utc']):
        row = entry['row']
        s = by_source[entry['source_name']]
        objects = row['mapped_code_objects']
        elf_paths = sorted(o['path'] for o in objects if o.get('elf') is True)
        assert len(elf_paths) == s['whole_hashed_ELF_count']
        selected.append({'generation': aliases[s['generation']], 'which': s['which'],
            'source_name': s['source_name'], 'source_bytes': entry['source_bytes'],
            'source_sha256': s['source_sha256'], 'observed_utc': s['utc'], 'phase': s['phase'],
            'android_uid': row['android_uid'], 'package': row['package'], 'process_name': row['process_name'],
            'host_identity_canonical_JSON_sha256': sha(encode(row['host_identity'])),
            'stable_process_identity': row['stable_process_identity'],
            'maps_before_after_equal': row['maps_before_after_equal'],
            'maps_sha256': row['maps_sha256'], 'maps_bytes': row['maps_bytes'],
            'executable': {'guest_path': row['host_identity']['exe'],
                'bytes': row['executable']['identity']['st_size'],
                **{k: row['executable'][k] for k in ('sha256', 'machine', 'bits', 'architecture', 'byte_order')}},
            'whole_hashed_ELF_paths': elf_paths, 'whole_hashed_ELF_count': len(elf_paths),
            'inventory_reference': 'ELF_INVENTORY.json',
            'header_only_non_ELF': [{'path': o['path'], 'content_read': o['content_read'],
                'whole_hash_available': False} for o in objects if o.get('elf') is not True],
            'unresolved_name_candidates': sorted({(m['path'], m['permissions']) for m in row['engine_mappings']
                if m['path'] in {x['path'] for x in row['unresolved_executable_objects']}}),
            'named_nonfilesystem_executable_mappings': [{'name': m['path'], 'permissions': m['permissions']}
                for m in entry['named_executable_mappings']],
            'process_memory_contents_read': False,
            'resource_observations': {'fd_count': s['fd_count'], **s['status']},
            'original_automatic_engine_qualification': False})
    files.append(put('SELECTED_CODE_OBSERVATIONS.json', {
        'schema': 'clock-runtime04-privacy-limited-code-observations/v1',
        'original_export': input_pins['saved_export'], 'selection': export['selection_rule'],
        'snapshots': selected,
        'omitted_fields': ['Raw maps and memory addresses', 'Raw proc stat and host process IDs',
            'Namespace and inode identifiers', 'Environment and document contents', 'Other sample rows'],
        'new_process_or_device_reads': 0}))
    public_review = copy.deepcopy(review)
    public_review['schema'] = 'clock-runtime04-privacy-limited-independent-review/v1'
    public_review['private_original_review'] = input_pins['review']
    public_review['selected_snapshots'] = [{k: v for k, v in s.items() if k not in ('executable',)}
                                          for s in review['selected_snapshots']]
    for s in public_review['selected_snapshots']:
        s['generation'] = aliases[s['generation']]
    for name in ('sample_rows_by_generation', 'stable_full_counts_by_generation'):
        public_review[name] = {aliases[k]: v for k, v in review[name].items()}
    public_review['selected_code_details'] = 'SELECTED_CODE_OBSERVATIONS.json'
    public_review['separate_scoped_identity_recommendation'] = 'Supported for these four actual snapshots of the exact current APK; root review remains separate.'
    files.append(put('INDEPENDENT_REVIEW_SELECTED.json', public_review))
    signature = [c for c in build['commands'] if c['label'] == 'candidate-signature-verify']
    assert len(signature) == 1 and signature[0]['rc'] == 0 and signature[0]['leader_joined'] is True
    assert signature[0]['timed_out'] is False
    assert build['candidate_apk']['certificate_sha256'] == identity['certificate_sha256']
    files.append(put('SIGNATURE_BINDING.json', {
        'schema': 'clock-runtime04-installed-signature-binding/v1', 'package': identity['package'],
        'uid': 10063, 'android_user': 0, 'version_code': 37, 'min_sdk': identity['min_sdk'],
        'target_sdk': identity['target_sdk'], 'framework_epoch_sha256': identity['epoch_sha256'],
        'apk': {'bytes': runtime['APK']['bytes'], 'sha256': apk,
            'certificate_sha256': identity['certificate_sha256'],
            'installed_files_count': len(identity['all_observed_apk_files'])},
        'source_build': input_pins['build'], 'source_install': input_pins['install'],
        'source_installed_identity': input_pins['identity'],
        'candidate_signature_verify': {k: v for k, v in signature[0].items() if k not in ('argv', 'command', 'cmd')},
        'basis': identity['certificate_basis'], 'actual_installed_observed_utc': identity['observed_utc'],
        'runtime_APK_read_before_after_matches': True, 'signature_verifier_rerun_for_publication': False,
        'business_review_from_prior_APK_inherited': False}))
    files.append(put('RUNTIME_TERMINAL_SELECTED.json', {
        'schema': 'clock-runtime04-original-terminal-selected/v1', 'original': input_pins['runtime'],
        **{k: runtime[k] for k in ('state', 'started_utc', 'finished_utc', 'Android_commands', 'UI_actions',
            'provider_mutations', 'service_or_Main_mutations', 'runtime_identity_automatically_qualified')},
        'whole_apk_sha256': apk, 'framework_epoch_sha256': identity['epoch_sha256'],
        'guard_before_after_identical': True, 'samples': 626, 'scan_error_count': 0,
        'thread_joined': True, 'elapsed_seconds': runtime['sampler']['elapsed_seconds'],
        'original_stable_complete_mapping_samples': 0, 'separate_UI_flow_result': runtime['separate_UI_flow_result'],
        'whole_app_production_ready': False}))
    alarm_keys = ('state', 'error', 'started_utc', 'finished_utc', 'business_success_verified',
        'actual_firing_verified', 'actual_alarm_notification_posted', 'UI_actions', 'acknowledged_input_count',
        'native_dispatch_attempts', 'native_launched_tasks', 'normally_closed_tasks',
        'owned_alarm_cleanup_verified', 'exact_owned_alarm_deleted', 'empty_alarm_state_at_final_read',
        'owned_task_remaining', 'pending_effect', 'pending_database_effect', 'close_pending',
        'task_set_restored', 'cleanup', 'desktop_popup_qualification', 'physical_audio_qualification',
        'global_volume_or_ringtone_changes', 'setting_changes', 'SQL_write_commands', 'provider_write_commands',
        'native_accessibility_policy_changes', 'dismiss_native_ACK', 'whole_app_production_ready')
    files.append(put('ALARM04_TERMINAL_SELECTED.json', {
        'schema': 'clock-alarm04-original-terminal-selected/v1', 'original': input_pins['alarm'],
        **{k: alarm.get(k) for k in alarm_keys}, 'actual_alarm_window_observed': alarm.get('actual_alarm_window_observed'),
        'whole_apk_sha256': apk, 'framework_epoch_sha256': identity['epoch_sha256'],
        'original_failure_not_rewritten': True,
        'scope': 'Actual scheduled firing and labelled notification were observed; no automatic Alert task or actual Dismiss was verified.'}))
    evidence = [dict(item, path=PREFIX + '/' + item['path']) for item in files
                if item['path'] in ('ELF_INVENTORY.json', 'SELECTED_CODE_OBSERVATIONS.json',
                    'INDEPENDENT_REVIEW_SELECTED.json', 'SIGNATURE_BINDING.json', 'RUNTIME_TERMINAL_SELECTED.json')]
    proposed = {'schema': 'clock-runtime04-scoped-identity-proposal/v1',
        'state': 'PROPOSED_FOR_ROOT_REVIEW_NOT_APPLIED', 'registry_edits': 0,
        'proposed_gate_review': {'id': 'clock_runtime04_current433ff_observed_identity',
            'package': identity['package'], 'uid': 10063, 'android_user': 0, 'version_code': 37,
            'apk_sha256': apk, 'framework_epoch_sha256': identity['epoch_sha256'], 'scope': 'scoped',
            'checks': {'identity': 'passed'}, 'reviewer': 'camera_runtime_review_independent_saved_inventory',
            'observed_at_utc': runtime['finished_utc'], 'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
            'evidence': evidence,
            'qualification_scope': 'Only the exact installed 433ff APK/signing identity, UID/user/version/epoch and four actual stable process/code snapshots from two generations.',
            'unresolved_findings': review['limits'] + [
                'Alarm04 remains FAILED. Firing and notification are partial observations, not a complete alarm gate.',
                'No prior APK timer, alarm, lifecycle, stability, audio or release-scope qualification is inherited.']},
        'whole_app_production_ready': False, 'business_gates_proposed': []}
    files.append(put('SCOPED_IDENTITY_PROPOSAL.json', proposed))
    files.append(put('source/review_inventory04_independent.py', (HERE / 'review_inventory04_independent.py').read_bytes(), raw=True))
    files.append(put('source/prepare_publication04.py', Path(__file__).read_bytes(), raw=True))
    files.append(put('README.md', (
        '# Clock runtime04 selected evidence on installed 433ff\n\n'
        'This bundle projects already saved evidence. It performs no new Android, UI, process or memory reads. '
        'The proposed readiness review is limited to identity of the exact installed APK and four selected stable '
        'process/code snapshots; it is not applied to the registry by this generator.\n\n'
        'Both process generations used the same whole-hashed x86_64 ELF inventory: 376 objects at the first '
        'selected snapshot and 381 at the last, with no hash, size or architecture drift. The complete union is '
        'included. The original collector completeness count remains zero. Two unresolved name candidates '
        'have actual read-only, non-executable mappings; their contents remain unread. One overlay APK has '
        'only a header observation. JIT/kernel mappings retain names and permissions, without memory contents.\n\n'
        'Alarm04 actually reached FIRED and posted its labelled notification. Its original overall result remains '
        'FAILED because a new Alert task was not observed. Dismiss and desktop-popup or physical-audio success '
        'are not granted. Its exact fixture and owned tasks were cleaned, with no pending action retained.\n\n'
        'Raw maps, host process identifiers, namespace/inode metadata, full notification dumps, original alarm '
        'contents and request payloads are omitted. ORIGINAL_INPUT_PINS and per-snapshot hashes bind the '
        'retained private originals. The ELF inventory and two review sources are copied byte for byte.\n'
    ).encode(), raw=True))
    omitted = []
    for name in ('saved_export', 'runtime', 'alarm', 'review', 'install', 'identity', 'build'):
        omitted.append({'source': name, **input_pins[name], 'omission':
            'Full original remains retained; only the explicitly selected scope is projected here.'})
    manifest = {'schema': 'clock-runtime04-public-selected-manifest/v1',
        'publication_prefix_suggestion': PREFIX, 'files': sorted(files, key=lambda item: item['path']),
        'selected_exact_copies': ['ELF_INVENTORY.json', 'source/review_inventory04_independent.py',
                                  'source/prepare_publication04.py'],
        'omitted_full_originals': omitted, 'originals_modified': False,
        'new_Android_or_UI_calls': 0, 'readiness_registry_modified': False,
        'overall_alarm04_result': 'FAILED', 'whole_app_production_ready': False}
    raw = encode(manifest)
    with (OUT / 'SOURCE_MANIFEST.json').open('xb') as stream:
        stream.write(raw)
    for name, (path, pin) in SOURCES.items():
        assert sha(path.read_bytes()) == pin, 'ORIGINAL_CHANGED_' + name
    print(json.dumps({'directory': str(OUT), 'files': len(files),
        'manifest_bytes': len(raw), 'manifest_sha256': sha(raw), 'device_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    if parser.parse_args().write:
        main()
    else:
        print(json.dumps({'state': 'PLAN_ONLY', 'device_calls': 0, 'writes': 0}))
