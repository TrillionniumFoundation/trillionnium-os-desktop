#!/usr/bin/python3
"""Reconcile exact historical Clock records; no device access or input."""
from pathlib import Path
import hashlib, json, re

HERE = Path(__file__).resolve().parent
CORE = HERE.parent / 'delivery03/clock-timer03-result.json'
OUT = HERE.parents[2] / 'publication-scheduler-checkpoint8'
# Keep the exact original result pin, not a reserialized copy.
CORE_SHA = 'ed01ff52b5dfee169a1218e23836ebe5eb6392cf8e589d3082fd172bc1223c6d'
AUDIT_SHA = 'ba1cdf550bc9bd3e80049ef0a6e8db7d3e86fc52eab3c6f8272adf896db5b78d'
APK = 'e4ff4b46a651ff3ac77397705b7b749c7fbaaeb94fe1d00818debb31dea34172'


def read(path, digest):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    return json.loads(raw)


def main():
    core = read(CORE, CORE_SHA)
    audit = read(HERE / 'selected-saved-audit.json', AUDIT_SHA)
    receipt = json.loads((HERE / 'receipt.json').read_text())
    status = receipt['status']
    assert status['state'] == 'succeeded' and status['exit_code'] == 0
    assert status['output_complete'] and status['output_durable'] and not status['timed_out']
    assert core['business_success_verified'] and core['pending_effect'] is None
    assert core['identity_before'] == core['identity_after'] and core['identity_after']['apk_sha256'] == APK
    assert core['timer_final']['ids'] == [] and core['owned_tasks'] == core['closed_tasks'] == [954, 955]
    assert audit['core_result_sha256'] == CORE_SHA and audit['Android_commands'] == audit['UI_actions'] == 0
    expected = {'before': 0, 'created-running': 1, 'paused': 0,
                'resumed': 1, 'paused-after-resume': 0, 'deleted': 0}
    selected, states = {}, []
    for phase, count in expected.items():
        observation = audit['scheduler'][phase]
        assert observation['raw_sha256'] == core['scheduler_observations'][phase]['sha256']
        rows = observation['clock_selected_context']
        active = [r for r in rows if re.fullmatch(
            r'    ELAPSED_WAKEUP #\d+: Alarm\{\w+ type 2 origWhen \d+ whenElapsed \d+ com\.android\.deskclock\}', r['line'])]
        assert len(active) == count
        counts = {x for r in rows for x in r['preceding_section_labels']
                  if x.startswith('  Pending alarms per uid: ')}
        assert len(counts) == 1
        match = re.search(r'\bu0a63:(\d+)\b', next(iter(counts)))
        uid_count = int(match[1]) if match else 0
        assert uid_count == count
        records = []
        for row in active:
            assert re.fullmatch(r'  \d+ pending alarms: ', row['preceding_section_labels'][-1])
            following = row['following_owned_record']
            assert following[0].strip() == 'tag=*walarm*:com.android.deskclock.action.TIMER_EXPIRED'
            operations = [x for x in following if 'operation=PendingIntent{' in x]
            assert len(operations) == 1 and 'com.android.deskclock startForegroundService' in operations[0]
            records.append({'line_number': row['line_number'], 'active_header': row['line'],
                'tag': following[0], 'operation': operations[0], 'section': 'current pending alarms'})
        historical_tags = [r for r in rows if 'TIMER_EXPIRED' in r['line']
                           and not r['following_owned_record']]
        assert historical_tags  # Actual negative control: strings also exist when no active alarm exists.
        selected[phase] = {'observed_utc': observation['observed_utc'],
            'original_raw_sha256': observation['raw_sha256'], 'original_raw_bytes': observation['raw_bytes'],
            'active_clock_pending_records': records, 'clock_uid_pending_count': uid_count,
            'historical_tag_lines_not_counted_as_active': len(historical_tags)}
        states.append({'phase': phase, 'active_clock_pending_count': count, 'clock_uid_pending_count': uid_count})
    summary = {'schema': 'clock-core03-scheduler-independent-review-v1',
        'state': 'HISTORICAL_CURRENT_APK_SCHEDULE_AND_CANCEL_VERIFIED',
        'package': 'com.android.deskclock', 'uid': 10063, 'android_user': 0,
        'apk_sha256': APK, 'epoch_sha256': core['epoch_sha256'],
        'original_core_result_sha256': CORE_SHA, 'original_core_result_modified': False,
        'original_core_started_utc': core['started_utc'], 'original_core_finished_utc': core['finished_utc'],
        'reader': {'job_id': receipt['start']['job_id'], 'state': status['state'], 'exit_code': 0,
            'output_complete': True, 'output_durable': True, 'timed_out': False,
            'compressed_artifact_sha256': receipt['manifest']['sha256'], 'compressed_artifact_bytes': receipt['manifest']['bytes'],
            'full_saved_export_sha256': AUDIT_SHA, 'full_saved_export_bytes': receipt['manifest']['uncompressed_bytes']},
        'phases': states, 'owned_timer_id': core['owned_timer_id'],
        'own_timer_deleted': True, 'owned_tasks_normally_closed': core['closed_tasks'],
        'new_device_commands_or_UI_actions_during_review': 0,
        'verified': ['creation registers one current foreground-service timer alarm',
            'pause removes the current timer alarm', 'resume registers one new current timer alarm',
            'second pause removes that current timer alarm', 'delete leaves no Clock pending alarm or timer object'],
        'limits': ['These are historical observations on the identified APK, not a current runtime probe.',
            'Historical Alarm Stats and App Alarm history are not current pending alarms.',
            'Expiry04, host Notify delivery, audio output, alarm workflow, and whole-app readiness remain unqualified.'],
        'timer_comprehensive_gate_passed': False, 'whole_app_production_ready': False}
    OUT.mkdir(exist_ok=False)
    for name, value in [('scheduler-independent-review.json', summary), ('clock-only-selected-records.json', selected)]:
        (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    (OUT / 'review_scheduler01.py').write_bytes(Path(__file__).read_bytes())
    (OUT / 'reader-manifest.json').write_text(json.dumps(receipt['manifest'], indent=2, sort_keys=True) + '\n')
    files = {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
             for p in sorted(OUT.iterdir())}
    (OUT / 'SOURCE_MANIFEST.json').write_text(json.dumps({'files': files, 'original_frozen_bundle_modified': False}, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'path': str(OUT), 'files': len(files), 'manifest_sha256': hashlib.sha256((OUT / 'SOURCE_MANIFEST.json').read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
