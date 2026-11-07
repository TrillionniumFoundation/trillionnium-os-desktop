"""Offline review of pinned expiry05 dumps. Never invokes Android or edits originals."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import re

HERE = Path(__file__).resolve().parent
PINS = {
    'expiry05-result-original.json': '6c6d7e4c073e956c089ff3a7a63c1173771d76d4cea7c1e7c1936620f39752cf',
    'combined05-result-original.json': '2c552c341e0c69400cc0f9a6a5b725f59eeb386b7b992830b8bfbcd8bfa0d9ec',
    'audio_observe.py': '5c6a49c7ee119c457d60072fbd25ea5ff1b23a577ad2504ba5fcbfc3fe01fdac',
    'saved-audio/expired-0-audio-flinger-private.txt': '85d9a17072e1471da374cd37b30bef4a0fa73881fee0e772667369a0b2e2796e',
    'saved-audio/expired-1-audio-flinger-private.txt': '5e51e05c5150283d0fbf015dea72c5d19015e171203913b67db9513b7283fe9e',
    'saved-audio/expired-2-audio-flinger-private.txt': '633fae133ce449600a0876dab93315f763bab433060d110c0f70df57336e5ff8',
    'saved-audio/expired-0.json': 'd1a0144a0cbb9d9d9eb0035c11cf10b7e511d202f424bd4bd95d054cdc855156',
    'saved-audio/expired-1.json': 'e08e31d365909b2c2d7d572e83ab2a9f57daf9ece937704d73ccca201f778d65',
    'saved-audio/expired-2.json': '8b0cb17ebffe3d450157090a9657b3e047ffee49b81da7eec35b77f2cdaa8ea5',
}
NUMBER = r'-?(?:\d+(?:\.\d+)?|inf)'
LINE = re.compile(r'^\s*(\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}):\s+(.*)$')
VALUES = re.compile(r'(' + NUMBER + r'(?:\s+' + NUMBER + r')*)(?:\s*\]\s+sum\(' + NUMBER + r'\))?')


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def pinned(relative):
    data = (HERE / relative).read_bytes()
    need(hashlib.sha256(data).hexdigest() == PINS[relative], 'INPUT_HASH:' + relative)
    return data


def power_rows(body, year):
    """Only explicit timestamped samples under the HAL history headings.

    A start '[' may lack a closing '] sum(...)' while the burst is ongoing.
    Continuations require that open burst in this same resolution section.
    The following ASCII graph and untimestamped numeric labels are excluded.
    """
    parts = body.split('Hal stream dump:', 1)
    need(len(parts) == 2, 'HAL_DUMP_REQUIRED')
    parts = re.split(r'^\s*Signal power history \(resolution: (1000\.0|50\.0) ms\):\s*$', parts[1], flags=re.M)
    need(parts[1::2] == ['1000.0', '50.0'], 'HAL_RESOLUTION_HEADINGS')
    rows = []
    for resolution, section in zip(parts[1::2], parts[2::2]):
        open_burst = False
        for line in section.splitlines():
            match = LINE.fullmatch(line)
            if match is None:
                continue
            timestamp, payload = match.groups()
            starts = payload.startswith('[')
            if starts:
                need(not open_burst, 'NESTED_POWER_BURST')
                payload = payload[1:].strip()
            else:
                need(open_burst, 'POWER_CONTINUATION_WITHOUT_START')
            values = VALUES.fullmatch(payload)
            need(values is not None, 'POWER_ROW_GRAMMAR')
            closed = '] sum(' in payload
            open_burst = not closed
            levels = values[1].split()
            stamp = datetime.strptime(str(year) + '-' + timestamp, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
            rows.append({'resolution_ms': float(resolution), 'timestamp_UTC': stamp.isoformat(),
                         'levels_db': levels, 'row_form': ('closed' if closed else 'open') if starts else 'continuation',
                         'source_line_sha256': hashlib.sha256(line.encode()).hexdigest()})
    return rows


def review_one(raw, sample, parse_flinger, due, year):
    parsed = parse_flinger(raw)
    active = [(out, track) for out in parsed for track in out['tracks'] if track['active']]
    need(len(active) == 1 and active[0][1]['uid'] == 10063, 'SOLE_CLOCK_ACTIVE_TRACK_REQUIRED')
    output, track = active[0]
    need(not output['master_muted'], 'MASTER_MUTED')
    need(parsed == sample['outputs'], 'ORIGINAL_LIVE_TABLE_READBACK_CHANGED')
    blocks = re.split(r'(?=^Output thread )', raw.decode('utf-8', 'strict'), flags=re.M)[1:]
    matches = [block.split('  Local log:', 1)[0] for block in blocks if block.splitlines()[0] == output['name']]
    need(len(matches) == 1, 'BOUND_OUTPUT_AMBIGUOUS')
    rows = power_rows(matches[0], year)
    observed = datetime.fromisoformat(sample['observed_utc'])
    # Exact recorded wall/uptime mapping; do not admit pre-due UI clicks.
    fresh = [row for row in rows if due <= datetime.fromisoformat(row['timestamp_UTC']) <= observed
             and any(math.isfinite(float(value)) and float(value) > -80 for value in row['levels_db'])]
    old_fresh = [row for row in output['power_1s']
                 if due <= datetime.strptime(str(year) + '-' + row['timestamp'], '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc) <= observed
                 and any(math.isfinite(float(value)) and float(value) > -80 for value in row['levels_db'])]
    return {'observed_utc': sample['observed_utc'], 'raw_sha256': hashlib.sha256(raw).hexdigest(),
            'output_name': output['name'], 'active_track': {key: track[key] for key in ('uid','pid','id','session','active')},
            'master_muted': output['master_muted'], 'frames_written': output['frames_written'],
            'total_writes': output['total_writes'], 'fresh_nonzero_power_rows': fresh,
            'old_completed_1s_parser_fresh_count': len(old_fresh),
            'matched_main_namespace_host_stream_count': len(sample['host_streams']),
            'host_stream_query': sample['host_stream_query']}


def main():
    data = {name: pinned(name) for name in PINS}
    inner = json.loads(data['expiry05-result-original.json'])
    outer = json.loads(data['combined05-result-original.json'])
    audio = inner['expiry_audio_evidence']
    need(audio['nonzero_HAL_power_during_sole_Clock_active_output'] is False, 'ORIGINAL_AUDIO_RESULT_CHANGED')
    need(outer['UID_track_output_frames_and_nonzero_HAL_power_verified'] is False, 'ORIGINAL_OUTER_RESULT_CHANGED')
    basis = datetime.fromisoformat(audio['basis_UTC'])
    due = basis + timedelta(milliseconds=audio['owned_expiry_due_ms'] - audio['basis_device_uptime_ms'])
    spec = importlib.util.spec_from_file_location('original_audio05', HERE / 'audio_observe.py')
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    samples, raw_samples, parsed_samples = [], [], []
    for index in range(3):
        raw = data[f'saved-audio/expired-{index}-audio-flinger-private.txt']
        sample = json.loads(data[f'saved-audio/expired-{index}.json'])
        need(sample['flinger_sha256'] == hashlib.sha256(raw).hexdigest(), 'SAMPLE_RAW_PIN')
        need(sample['host_stream_query'] == {'guard_after': True, 'joined': True, 'rc': 0, 'timed_out': False}, 'HOST_QUERY_UNKNOWN')
        samples.append(review_one(raw, sample, original.parse_flinger, due, basis.year))
        raw_samples.append(raw)
        parsed_samples.append(sample)
    track = samples[0]['active_track']
    need(all(sample['active_track'] == track for sample in samples), 'TRACK_IDENTITY_CHANGED')
    need(all(a['output_name'] == b['output_name'] and a['frames_written'] < b['frames_written']
             and a['total_writes'] < b['total_writes'] for a,b in zip(samples, samples[1:])), 'OUTPUT_NOT_PROGRESSING')
    need(all(sample['fresh_nonzero_power_rows'] and sample['old_completed_1s_parser_fresh_count'] == 0 for sample in samples), 'EXPECTED_PARSER_DIFFERENCE_NOT_FOUND')
    controls = []
    # The actual closed histories/UI clicks alone must not become current power.
    for index, (raw, sample) in enumerate(zip(raw_samples, parsed_samples)):
        stripped = b'\n'.join(line for line in raw.split(b'\n') if not re.match(rb'\s*11-05 16:17:', line))
        result = review_one(stripped, sample, original.parse_flinger, due, basis.year)
        need(result['fresh_nonzero_power_rows'] == [], 'OLD_HISTORY_OR_GRAPH_FALSE_POSITIVE')
        controls.append({'case': f'sample{index}_remove_current_rows_keep_completed_history_and_graph', 'passed': True})
    # A different UID in the live table must fail before considering power.
    changed = raw_samples[0].replace(b'735449/  10063', b'735449/  10064')
    try:
        review_one(changed, parsed_samples[0], original.parse_flinger, due, basis.year)
    except RuntimeError as error:
        need(str(error) == 'SOLE_CLOCK_ACTIVE_TRACK_REQUIRED', 'WRONG_NEGATIVE_CONTROL_REJECTION')
    else:
        raise RuntimeError('FOREIGN_UID_ACCEPTED')
    controls.append({'case': 'active_uid_changed_to_foreign_uid', 'passed': True})
    result = {
        'schema': 'clock-expiry05-saved-audio-review/v1', 'review_type': 'offline_reconciliation_of_unchanged_originals',
        'input_pins': {name: {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()} for name,blob in data.items()},
        'original_outer_state': outer['state'], 'original_job_exit_code': 1,
        'original_HAL_boolean_preserved': False, 'original_results_modified': False,
        'due_utc_from_recorded_basis': due.isoformat(), 'timer_due_uptime_ms': audio['owned_expiry_due_ms'],
        'finding': 'The executed parser only accepted completed 1000ms rows ending in ] sum(...). The saved HAL dumps contain ongoing open 1000ms and open/multiline 50ms rows after this timer due time; those rows were omitted.',
        'samples': samples,
        'independent_conclusions': {
            'same_Clock_UID_track_and_output_frames_writes_progress': True,
            'nonzero_HAL_power_contemporaneous_with_sole_Clock_active_track_snapshots': True,
            'matched_Main_namespace_Pulse_stream_observed': False,
            'physical_speaker_audibility_verified': False,
            'desktop_popup_visual_verified': False,
            'whole_app_production_ready': False,
        },
        'scope': 'Output-level HAL signal-power telemetry contemporaneous with the sole active Clock track in these three snapshots. This does not prove physical speaker output, host sink delivery, every intervening instant, or audio-engine qualification.',
        'controls': controls, 'controls_passed': len(controls),
        'remote_commands': 0, 'UI_actions': 0, 'settings_changes': 0, 'audio_bytes_recorded': 0, 'microphone_access': False,
    }
    target = HERE / 'audio-saved-reconciliation05.json'
    encoded = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    if target.exists():
        need(target.read_bytes() == encoded, 'OUTPUT_ALREADY_EXISTS_WITH_OTHER_CONTENT')
    else:
        target.write_bytes(encoded)
    print(json.dumps({'path': str(target), 'bytes': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest(),
                      'samples': len(samples), 'controls_passed': len(controls), 'original_exit_code_preserved': 1}))


if __name__ == '__main__':
    main()
