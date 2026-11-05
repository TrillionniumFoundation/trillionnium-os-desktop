"""Build a selected public delta from fixed existing expiry05 evidence; no device access."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
INPUT = Path(__file__).resolve().parent
OUT = ROOT / 'publication-expiry05-checkpoint8'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(name, expected=None):
    data = (INPUT / name).read_bytes()
    if expected:
        assert sha(data) == expected, name
    return data


def write(name, data):
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(data, bytes):
        data = (json.dumps(data, indent=2, sort_keys=True) + '\n').encode()
    if target.exists():
        assert target.read_bytes() == data, name
    else:
        target.write_bytes(data)


def main():
    inner_raw = read('expiry05-result-original.json', '6c6d7e4c073e956c089ff3a7a63c1173771d76d4cea7c1e7c1936620f39752cf')
    outer_raw = read('combined05-result-original.json', '2c552c341e0c69400cc0f9a6a5b725f59eeb386b7b992830b8bfbcd8bfa0d9ec')
    audio_raw = read('audio-saved-reconciliation05.json', 'a78992a712d0b0f7976a13fd16e17e4cc9fa98be0640f7100695405022d06e36')
    inner, outer, audio = map(json.loads, (inner_raw, outer_raw, audio_raw))
    assert inner['business_success_verified'] and inner['pending_effect'] is None
    assert inner['normal_closed_tasks'] == [958,959] and inner['task_set_restored']
    assert outer['UID_track_output_frames_and_nonzero_HAL_power_verified'] is False
    assert audio['independent_conclusions']['nonzero_HAL_power_contemporaneous_with_sole_Clock_active_track_snapshots']
    OUT.mkdir(exist_ok=True)
    write('metadata/combined05-result-original.json', outer_raw)
    write('metadata/expiry05-job-status-selected.json', read('expiry05-job-status-selected.json'))
    write('metadata/saved-audio-export-job-status-selected.json', read('saved-audio-export-job-status-selected.json'))
    write('metadata/audio-saved-reconciliation05.json', audio_raw)
    write('metadata/execution-source-manifest.json', read('SOURCE_MANIFEST.json'))
    write('metadata/execution-local-validation.json', read('LOCAL_VALIDATION.json'))
    write('latest-installed-identity.json', (ROOT / 'publication-expired-text-checkpoint8/latest-installed-identity.json').read_bytes())
    selection_keys = ('state','started_utc','finished_utc','epoch_sha256','business_success_verified',
        'whole_app_production_ready','identity_before','identity_after','owned_timer_id','timer_duration_ms',
        'ui_actions','owned_task_remove_calls','owned_tasks','normal_closed_tasks','owned_task_remaining',
        'pending_effect','task_set_restored','stop_reconciliation','timer_final','alarms_before','alarms_after',
        'templates_sha_before','templates_sha_after','appop_before','appop_after','automatic_retry',
        'global_volume_or_ringtone_actions','notification_permission_actions','standard_title_body_to_host_Notify_observed',
        'notification_posted_verified','expired_desktop_state_removed','notify_monitor_closed_verified',
        'notify_watch_child_started','notify_watch_stop','source_pins','installed_dex_sha256')
    selected = {key: inner[key] for key in selection_keys}
    selected['selection_of_unchanged_private_original'] = {'bytes':len(inner_raw),'sha256':sha(inner_raw)}
    selected['expiry_timing'] = {key:value for key,value in inner['expiry_timing'].items() if key != 'samples'}
    selected['expiry_timing']['observations_count'] = len(inner['expiry_timing']['samples'])
    selected['owned_timer_states'] = {phase: {key:state[key] for key in ('ids','stopwatch','timers')}
                                    for phase,state in inner['phases'].items()}
    write('metadata/expiry05-selected.json', selected)
    proof = dict(inner['Notify_scope'])
    proof['expiry_timing'] = selected['expiry_timing']
    proof['host_record_states'] = {name:{key:inner[name]['own_state'][key] for key in ('utc','key','record','owner','bus_id')}
                                 for name in ('host_notify_running','host_notify_expired','host_notify_after_delete')}
    proof['raw_private_NMS_or_DBus_payload_included'] = False
    proof['independent_peer_review'] = {
        'reviewer': 'review_android_acceptance', 'source_sha256':sha(inner_raw),
        'conclusion':'Exact expired key/UID and title-body pair, post due+243ms, cookie41 complete line starting at running offset30323, and host absent->709/new version->absent agree. This is not running-only evidence.',
        'scope':'Notify transport association only; sender timestamp, desktop popup and physical audio are unqualified.'}
    write('metadata/notify-association-selected.json', proof)
    runtime = {}
    for phase, observation in inner['runtime_observations'].items():
        commands = observation['commands']
        runtime[phase] = {'observed_utc':observation['observed_utc'],'uptime_ms':observation['uptime_ms'],
            'events_source_sha256':commands['events']['sha256'],
            'Clock_events': [line for line in commands['events']['clock_lines'] if any(token in line for token in
                (' am_kill ', ' am_proc_died:', ' am_proc_start:', ' am_foreground_service_start:', 'Background started FGS:'))],
            'services_source_sha256':commands['services']['sha256'],
            'service_app_process_pids':commands['services']['service_app_process_pids'],
            'service_state_lines':commands['services']['service_state_lines']}
        assert all('com.android.deskclock' in line for line in runtime[phase]['Clock_events'])
    write('metadata/cold-start-selected.json', runtime)
    write('metadata/source-and-profile-bindings.json', {
        'stage_request': {'bytes':len(read('stage-execute-request.json')),'sha256':sha(read('stage-execute-request.json')),
                          'idempotency_key':'clock-expiry-delivery-r12-05','job_id':'1a1ac7f0da5-fc05-54c5'},
        'profile':{'transaction_sha256':'e65a47bea8b3800d0b1a89247bd8c356dd291523c2d248d401d05d1d3b55fb83',
                   'activation_sha256':'91c7a4a911a7bcf908726750f55f3fda66f40263ddf3fac457473e0a6c780435',
                   'actual_pids_max':6144,'profile_creation_result_sha256':'fac5e023b695432003549e7f4132ceb53482215af16870b77ba5350b4b6a8bdb',
                   'Main_resource_writes':0,'guard_logic_changed':False},
        'delivery04':{'executed':False,'staged':False,'source_preserved':True},
        'existing_binary_core03_replayed':False,
        'previous_bundle_manifest_sha256':'dfec1b20299ab6dc2965bf5dc7cdb35de0cbf6bf7362f90a5b202768dca59b5b',
        'previous_bundle_modified':False,
        'raw_pins':{'expiry05':{'bytes':len(inner_raw),'sha256':sha(inner_raw)},'outer05':{'bytes':len(outer_raw),'sha256':sha(outer_raw)},
                    'saved_audio_export':{'compressed_bytes':20175,'compressed_sha256':'8e5a621b936afd41028878f77eec72f1db82fe6967a46a5355b973e004cd1092',
                                          'full_bytes':146194,'full_sha256':'02ef3a539ef4bf05caf35b5e1910bb6c9f6410ef785061836c36938605cf6bba'}}})
    source_files = ['run_expiry05.py','timer_expiry05.py','read_clock_expired_text02.py','notify_watch03.py',
                    'notify_proof.py','audio_observe.py','review_saved_audio05.py','prepare_publication05.py',
                    'run_expiry05.py.patch','timer_expiry05.py.patch','read_clock_expired_text02.py.patch']
    for name in source_files:
        write('source/'+name, read(name))
    write('CURRENT_STATUS.json', {
        'package':'com.android.deskclock','uid':10063,'installed_apk_sha256':outer['expected_apk_sha256'],
        'original_job':{'id':'1a1ac7f0da5-fc05-54c5','state':'failed','exit_code':1,'complete':True,'durable':True,'timed_out':False},
        'original_outer_state':outer['state'],'original_HAL_boolean':False,'original_result_overwritten':False,
        'current_binary_scoped_passes':[
            'Prior core03: one owned timer start/pause/reopen/resume/reset/delete, scheduler arm/cancel sequence; no replay here.',
            'Expiry05: 60-second sole-owned timer after normal task removal and process death, actual cold FGS start and EXPIRED.',
            'Expiry05: exact standard title/body Time\'s up traversed Clock Notify to host owner and owned state; state removed after cleanup.',
            'Expiry05: actual Stop reset the same timer; Delete removed it; two normal task removals and no pending effects.',
            'Saved-only independent review: HAL open power rows show nonzero output contemporaneous with sole active Clock UID/track snapshots and advancing frame/write counters.'],
        'independently_reconciled_audio_review_sha256':sha(audio_raw),
        'unqualified':['desktop popup/heads-up visual delivery','physical speaker audibility','matched host Pulse output stream',
                       'owned alarm create/fire/snooze/dismiss','multi-timer scenarios','whole-app production readiness','engine qualification'],
        'original_two_disabled_alarms_preserved':True,'notification_permission_still_true':True,
        'volume_or_ringtone_changes':0,'microphone_access':False,'recorded_audio_bytes':0,
        'owned_tasks_remaining':None,'pending_effect':None,'monitor_writers_and_reader_joined':True,
        'raw_private_audio_NMS_DBus_or_preferences_included':False,'whole_app_production_ready':False})
    readme = '''# Clock expiry05: current-binary evidence delta

The original worker finished with exit 1 at 2026-11-05 16:18:17 UTC. Its inner timer flow passed; the outer result retained an unproved audio-power flag. Both original outcomes remain intact.

On the installed e4ff4b46 APK, the sole 60-second timer survived normal task removal and process death. AlarmManager cold-started TimerService, the exact timer became EXPIRED, and its standard title and body reached the fixed host Notify consumer. Stop reset that same timer and Delete removed it. Tasks 958 and 959 closed normally; pending effects were empty, protected state was preserved, and the owned monitor was joined with both pipes at EOF.

## Saved audio reconciliation

The executed observer only parsed completed 1000 ms power rows ending in `] sum(...)`. The pinned raw dumps contain an ongoing burst with open 1000 ms and multiline 50 ms records after this timer's due time. A separate offline review admits those actual timestamped rows, excludes old UI-click history and graph coordinates, and rechecks the sole active Clock UID/track plus increasing output frames/writes. Four negative controls pass.

This establishes nonzero HAL signal-power telemetry contemporaneous with the sole active Clock track in three snapshots. It does not establish physical speaker audibility, a matched host Pulse stream, desktop popup display, or whole-app readiness. No PCM was recorded and no sound setting changed. The original `HAL=false` and exit 1 were not rewritten as success.

## Reproducibility and scope

`metadata/combined05-result-original.json` is byte-for-byte original. The 63,508-byte inner result, three full AudioFlinger dumps, and full NMS/DBus payloads stay private; their hashes and selected Clock-only fields are included. `review_saved_audio05.py` reruns against those pinned private inputs in their original delivery05 directory. The execution sources are frozen copies. delivery04 was never staged or executed. The earlier dfec1b20 bundle remains unchanged.

The new resource profile validates the actual 6144 PID limit with the existing guard logic. This flow made no Main resource/configuration writes. Existing core03 evidence is bound to this same APK; it was not replayed here.
'''
    write('README.md', readme.encode())
    files = {str(path.relative_to(OUT)):{'bytes':path.stat().st_size,'sha256':sha(path.read_bytes())}
             for path in sorted(OUT.rglob('*')) if path.is_file() and path.name != 'SOURCE_MANIFEST.json'}
    write('SOURCE_MANIFEST.json', {'files':files,'original_frozen_bundle_modified':False,'private_payloads_included':False})
    manifest = (OUT/'SOURCE_MANIFEST.json').read_bytes()
    print(json.dumps({'directory':str(OUT),'files':len(files),'bytes':sum(x['bytes'] for x in files.values()),
                      'manifest_bytes':len(manifest),'manifest_sha256':sha(manifest)}))


if __name__ == '__main__':
    main()
