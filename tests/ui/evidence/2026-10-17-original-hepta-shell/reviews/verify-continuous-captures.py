#!/usr/bin/env python3
"""Read-only verification of completed R6 receipts, with separately observed pixels.

This does not launch Hepta, Session, Shell, a display, or a product test. The
visual facts below were transcribed by the independent reviewer after opening
each original PNG with view_image; JSON alone does not establish pixel truth.
All output is confined to this review directory.
"""
import datetime
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path('/workspace/scratch/98f315e377b2')
TOOLS = ROOT / 'next-tools'
OUT = TOOLS / 'r6-review'
PHASES = ['starting', 'running', 'draining', 'old_spawn_stale', 'recovered_running', 'stopped_stale']
AGENT = '22222222-2222-4222-8222-222222222222'
EXPECTED_ORIGINAL = {'commit': 'f8c9419df6ddeb36ff8b522a50219981fb8d9345',
    'tree': '15c9d6ea07bf3832de82825a6cc1e8c958dd3d45',
    'cargo_lock_sha256': '8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389',
    'clean_checkout': True}
# sample, spawn, current, PID, lifecycle, ready, promotion, next/latest cursor
VISUAL = {
 '02': [(1792277794233,1,1,615532,'starting',False,True,3),
        (1792277797242,1,2,615532,'running',True,True,4),
        (1792277800252,1,3,615532,'draining',False,False,6),
        (1792277801255,1,3,615532,'draining',False,False,6),
        (1792277809180,5,6,615755,'running',True,True,4),
        (1792277809180,5,6,615755,'running',True,True,4)],
 '03': [(1792277987357,1,1,616327,'starting',False,True,3),
        (1792277990368,1,2,616327,'running',True,True,4),
        (1792277993377,1,3,616327,'draining',False,False,6),
        (1792277993377,1,3,616327,'draining',False,False,6),
        (1792278000290,5,6,616535,'running',True,True,4),
        (1792278002303,5,7,616535,'draining',False,False,5)]}
WORKTREES = {'02': ROOT/'next-r6-runtime-old-03', '03': ROOT/'next-r6-runtime-new-03'}
PRODUCTION = {'02': '35f379101c0863027e971ccb91faf8da71cf929c', '03': '84f0070b6e7e01238a8dac6044748b15101c9497'}
HASH_CACHE = {}

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while data := stream.read(1024 * 1024):
            h.update(data)
    return h.hexdigest()

def load(path):
    return json.loads(Path(path).read_text())

def file_info(path):
    return {'path': str(path), 'bytes': Path(path).stat().st_size, 'sha256': digest(path)}

def verify_file(path, record):
    actual = file_info(path)
    assert actual['sha256'] == record['sha256'], str(path)
    if 'bytes' in record:
        assert actual['bytes'] == record['bytes'], str(path)
    return actual

def git(worktree, *args):
    return subprocess.check_output(['git', '-C', str(worktree), *args]).decode().strip()

def git_bytes(worktree, spec):
    return subprocess.check_output(['git', '-C', str(worktree), 'show', spec])

def verify_elf(record):
    path = record['path']
    if path not in HASH_CACHE:
        actual = file_info(path)
        with open(path, 'rb') as stream:
            header = stream.read(64)
        assert header[:6] == b'\x7fELF\x02\x01', path
        assert struct.unpack('<H', header[18:20])[0] == 62, path
        actual.update(elf_class=64, elf_machine=62, execution_by_reviewer=False)
        HASH_CACHE[path] = actual
    actual = HASH_CACHE[path]
    assert actual['sha256'] == record['sha256'] and actual['bytes'] == record['bytes'], path
    return actual

def one(records, event):
    result = [r for r in records if r.get('event') == event]
    assert len(result) == 1, event
    return result[0]

def write(name, value):
    path = OUT/name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return file_info(path)

def verify_run(suffix):
    capture_dir = TOOLS/f'r6-original-shell-{suffix}'
    runtime_dir = TOOLS/'r6-original-runtime'/f'runtime-{suffix}'
    capture = load(capture_dir/'capture-receipt.json')
    runtime = load(runtime_dir/'receipt.json')
    namespace = load(capture_dir/'namespace.json')
    assert capture['capture_passed'] is True and namespace['returncode'] == 0
    assert capture['visual_review_required'] is True and capture['visual_review_completed_by_capture'] is False
    assert runtime['status'] == runtime['live_agentd_acceptance'] == runtime['persistent_session_acceptance'] == 'passed'
    assert runtime['private_state_cleanup_complete'] is True
    assert not Path(runtime['private_original_state_root']).exists()
    assert runtime['desktop'] == runtime['desktop_after']
    assert runtime['original_build'] == runtime['original_after']
    assert runtime['original_build']['original'] == EXPECTED_ORIGINAL
    assert runtime['binaries_before'] == runtime['binaries_after']
    assert runtime['helper_sha256'] == runtime['helper_sha256_after']
    assert set(runtime['binaries_before']) == {'agentd','probe','observer','session','ctl'}
    for name, expected in runtime['helper_sha256'].items():
        assert digest(TOOLS/'r6-original-runtime'/'helper-v3'/name) == expected
    raw_files = [verify_file(runtime_dir/name, info) for name, info in runtime['raw_artifacts'].items()]
    records = [json.loads(line) for line in (runtime_dir/'original-session-process.log').read_text().splitlines() if line.startswith('{')]
    assert records == runtime['runtime_records'] == load(runtime_dir/'runtime-records.json')
    orig_accept = one(records, 'acceptance_pass')
    session_accept = one(records, 'session_acceptance_pass')
    assert orig_accept['checks'] == ['original_starting','original_running','bounded_capabilities_events','missing_run_read','same_process_draining','original_restart','old_spawn_rejected','controlled_stop']
    assert session_accept['checks'] == ['persistent_session_starting','persistent_session_running','persistent_session_draining','same_worker_same_instance','old_spawn_stale_ipc_responsive','explicit_session_replacement','replacement_running','stopped_stale_ipc_responsive']
    assert session_accept['shell_capture_qualified_by_this_record'] is False
    for accepted in (orig_accept, session_accept):
        assert all(accepted[k] is False for k in ('objective_submission','model_turn','device_effect'))
    assert len(runtime['steps']) == 1
    step = runtime['steps'][0]
    assert step['exit_code'] == 0 and step['child_guard_armed_after_completion'] is False
    verify_file(step['log']['path'], step['log'])
    source = capture['source_provenance']
    worktree = WORKTREES[suffix]
    assert git(worktree, 'rev-parse', 'HEAD') == runtime['desktop']['commit'] == source['harness_commit']
    assert git(worktree, 'rev-parse', 'HEAD^{tree}') == runtime['desktop']['tree'] == source['harness_tree']
    assert git(worktree, 'status', '--porcelain') == ''
    assert source['production_ui_commit'] == PRODUCTION[suffix]
    assert git(worktree, 'rev-parse', PRODUCTION[suffix]+'^{tree}') == source['production_source_tree']
    assert git(worktree, 'rev-parse', 'HEAD:ui') == git(worktree, 'rev-parse', PRODUCTION[suffix]+':ui') == source['unchanged_ui_subtree']
    copies = {'harness':'capture-source.py','pixels':'x11-capture-source.py','guard':'child-guard-source.py'}
    for key, info in source['tracked_sources'].items():
        actual = verify_file(capture_dir/copies[key], info)
        assert git(worktree, 'rev-parse', 'HEAD:'+info['path']) == info['git_blob']
        assert hashlib.sha256(git_bytes(worktree, 'HEAD:'+info['path'])).hexdigest() == actual['sha256']
    for name, expected in runtime['desktop']['inputs'].items():
        assert digest(worktree/name) == expected
    for name, info in runtime['consumer_source_reuse']['linked_source_inputs'].items():
        built = git(worktree, 'rev-parse', runtime['consumer_source_reuse']['compiled_source_commit']+':'+name)
        current = git(worktree, 'rev-parse', 'HEAD:'+name)
        assert built == current == info['built_git_object'] == info['current_git_object'] and info['identical'] is True
    assert runtime['consumer_source_reuse']['recompiled_for_runtime_source'] is False
    for name, info in runtime['ui_build']['linked_source_inputs'].items():
        built = git(worktree, 'rev-parse', PRODUCTION[suffix]+':'+name)
        current = git(worktree, 'rev-parse', 'HEAD:'+name)
        assert built == current == info['built_git_object'] == info['current_git_object'] and info['identical'] is True
    verify_file(runtime['consumer_build_receipt']['path'], runtime['consumer_build_receipt'])
    verify_file(runtime['ui_build']['build_receipt_path'], {'sha256':runtime['ui_build']['build_receipt_sha256']})
    assert digest(capture_dir/'rust-build-receipt.json') == runtime['ui_build']['build_receipt_sha256']
    for previous in runtime['previous_runtime_receipts']:
        verify_file(previous['path'], previous)
        assert load(previous['path'])['status'] == previous['status']
    elf_checks = {name:verify_elf(info) for name, info in runtime['binaries_before'].items()}
    for label, name in [('trill-session','session'), ('trill-ctl','ctl')]:
        assert source['binaries'][label]['sha256'] == elf_checks[name]['sha256']
    elf_checks['shell'] = verify_elf(source['binaries']['trill-shell'])
    assert capture['shell_processes_started'] == 1
    assert capture['same_shell_pid_all_phases'] is True and capture['same_shell_window_all_phases'] is True
    assert capture['shared_pid_namespace'] is True and capture['isolated_network_mounts_ipc_uts'] is True
    assert capture['private_display_rejects_no_cookie'] is True
    for key in ('synthetic_agentd_fixture_used','renderer_memory_injected','objective_submitted','model_called','device_effect_tested','physical_display_tested','keyboard_input_tested'):
        assert capture[key] is False
    assert len(capture['phases']) == 6
    images, identities = [], []
    acknowledged = [r for r in records if r.get('event') == 'session_phase_acknowledged']
    assert len(acknowledged) == 6
    for i, (phase, recorded, visible) in enumerate(zip(PHASES, capture['phases'], VISUAL[suffix]), 1):
        sample, spawn, generation, pid, lifecycle, ready, promotion, cursor = visible
        assert recorded['sequence'] == i and recorded['phase'] == phase
        png = capture_dir/recorded['screenshot']['file']
        screenshot = verify_file(png, recorded['screenshot'])
        with png.open('rb') as stream:
            header = stream.read(24)
        assert header[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II', header[16:24]) == (1440,1000)
        held_path = runtime_dir/'phases'/f'phase-{i}.json'
        assert digest(held_path) == recorded['phase_sha256'] == digest(capture_dir/recorded['phase_file'])
        held = load(held_path)
        assert held in records and held['capture_ack_is_coordination_only'] is True
        assert held['sequence'] == i and held['phase'] == phase
        ack = load(runtime_dir/'phases'/f'ack-{i}.json')
        assert ack == held['ack'] == acknowledged[i-1]['ack']
        assert acknowledged[i-1]['capture_ack_is_coordination_only'] is True
        sid = (held['session_pid'], held['session_instance'], held['worker_tid'])
        identities.append(sid)
        assert recorded['session_pid'] == sid[0] and recorded['session_instance'] == sid[1]
        assert recorded['shell_pid'] == capture['shell_pid'] and recorded['shell_window_xid'] == capture['shell_window']['xid']
        snapshots = []
        for key in ('before','after'):
            info = recorded[key]
            verify_file(capture_dir/info['file'], info)
            snap = load(capture_dir/info['file'])
            assert snap['hepta'] == info['hepta'] and snap['tasks'] == [] and snap['session_instance'] == sid[1]
            assert info['peer_pid'] == sid[0] and info['peer_uid'] == 0 and info['peer_gid'] == 0
            snapshots.append(snap['hepta'])
        before, after = snapshots
        assert recorded['before']['finished_unix_ms'] <= recorded['capture_started_unix_ms'] <= recorded['capture_finished_unix_ms'] <= recorded['after']['finished_unix_ms'] <= recorded['acknowledged_unix_ms']
        ob, oa = before['last_observation'], after['last_observation']
        assert ob['sampled_unix_ms'] <= sample <= oa['sampled_unix_ms']
        expected_health = {'process_id':pid,'lifecycle':lifecycle,'ready':ready,'promotion_ready':promotion,'fenced':False}
        assert oa['health'] == expected_health
        assert oa['agent_id'] == AGENT and oa['spawn_generation'] == spawn and oa['current_generation'] == generation
        assert oa['next_cursor'] == oa['latest_cursor'] == cursor
        is_stale = i in (4,6)
        status = 'stale' if is_stale else 'observed'
        error = 'protocol_mismatch' if i == 4 else 'unavailable' if i == 6 else None
        assert before['connection'] == after['connection'] == status
        assert before['error_code'] == after['error_code'] == error
        stale_review = None
        if is_stale:
            proof = held['stale_verification']
            first = proof['first_stale_snapshot']['hepta']
            previous = proof['preceding_live_observation']
            final = held['snapshot']['hepta']
            assert first['connection'] == final['connection'] == 'stale'
            assert first['error_code'] == final['error_code'] == error
            assert first['last_observation'] == final['last_observation'] == ob == oa
            assert sample == oa['sampled_unix_ms'] < first['last_attempt_unix_ms'] < final['last_attempt_unix_ms'] <= before['last_attempt_unix_ms'] < after['last_attempt_unix_ms']
            assert previous['sampled_unix_ms'] <= sample
            for key in ('agent_id','spawn_generation'):
                assert previous[key] == oa[key]
            assert previous['health']['process_id'] == pid
            assert previous['events'] == oa['events'][:len(previous['events'])]
            assert previous['current_generation'] <= generation and previous['next_cursor'] <= cursor
            stale_review = {'first_failure_unix_ms':first['last_attempt_unix_ms'], 'held_later_failure_unix_ms':final['last_attempt_unix_ms'], 'before_failure_unix_ms':before['last_attempt_unix_ms'], 'after_failure_unix_ms':after['last_attempt_unix_ms'], 'preceding_live_sample_unix_ms':previous['sampled_unix_ms'], 'entire_last_observation_preserved':True}
        else:
            assert recorded['capture_finished_unix_ms'] - sample <= 7000
        images.append({'sequence':i,'phase':phase,'screenshot':screenshot,'manual_visual_review':'passed',
            'visible_main_and_inspector_status':'STALE · CURRENT STATE UNKNOWN' if is_stale else 'OBSERVED · READ ONLY',
            'visible_diagnostic':error,'visible_historical_warning':is_stale,'visible_sample_unix_ms':sample,
            'visible_agent_id':AGENT,'visible_spawn_generation':spawn,'visible_current_generation':generation,
            'visible_health':expected_health,'visible_next_and_latest_cursor':cursor,
            'before_observation_sample_unix_ms':ob['sampled_unix_ms'],'after_observation_sample_unix_ms':oa['sampled_unix_ms'],
            'visible_sample_within_actual_before_after_range':True,'session_pid':sid[0],'session_instance':sid[1],'worker_tid':sid[2],
            'actual_peer_pid_uid_matched_both_sides':True,'stale_retention_verification':stale_review,
            'owner_phase_sha256':recorded['phase_sha256'],'ack_sha256':digest(runtime_dir/'phases'/f'ack-{i}.json')})
    assert len(set(identities[:4])) == len(set(identities[4:])) == 1 and identities[0] != identities[4]
    stopped = [r for r in records if r.get('event') == 'session_stopped']
    assert len(stopped) == 2
    assert [(r['session_pid'],r['session_instance'],r['worker_tid']) for r in stopped] == [identities[0],identities[4]]
    assert all(r['signal'] == 9 for r in stopped)
    assert {r['label'] for r in capture['cleanup']} == {'rust-shell','xvfb'}
    assert all(isinstance(r['observed_returncode'],int) for r in capture['cleanup'])
    absent = sorted({step['pid'], *[i[0] for i in identities], *[i[2] for i in identities], *[x['pid'] for x in capture['children']], *[v[3] for v in VISUAL[suffix]]})
    assert all(not Path('/proc',str(pid)).exists() for pid in absent)
    return {'reviewer':'/root/r6_review_ci','reviewed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status':'passed','independent_from_implementation':True,'product_processes_or_tests_started_by_reviewer':False,
        'method':'Each original PNG opened individually with view_image; manually transcribed visible facts then compared to raw before/after Session snapshots, owner phase/ACK/process logs, source Git objects and actual executable bytes.',
        'capture_receipt':file_info(capture_dir/'capture-receipt.json'),'runtime_receipt':file_info(runtime_dir/'receipt.json'),
        'namespace_receipt':file_info(capture_dir/'namespace.json'),'source_provenance':source,
        'original':EXPECTED_ORIGINAL,'original_acceptance_record':orig_accept,'session_acceptance_record':session_accept,
        'actual_executables_rehashed_after_both_runs':elf_checks,'runtime_five_ELF_pre_post_match':True,
        'source_helper_and_component_closure_verified':True,'raw_runtime_artifacts_verified':raw_files,
        'shell_pid':capture['shell_pid'],'shell_window':capture['shell_window'],'one_shell_all_six_phases':True,
        'first_session':dict(zip(('pid','instance','worker_tid'),identities[0])),
        'replacement_session':dict(zip(('pid','instance','worker_tid'),identities[4])),
        'cleanup':{'recorded_session_stops':stopped,'recorded_shell_display_stops':capture['cleanup'],'probe_exit_code':step['exit_code'],
            'probe_guard_disarmed':True,'private_state_removed':runtime['private_original_state_root'],'actual_process_ids_absent_at_review':absent},
        'images':images,'limitations':['Linux x86_64 host process integration with private Xvfb framebuffer; no physical display or input tested.',
            'ACK is coordination only; visual acceptance is this separate reviewer observation.',
            'Only first phase has TRILL_HEPTA_LAYOUT_V1 marker; all six pixel judgments used actual images.',
            'No synthetic Agentd fixture or renderer-memory injection in these runs.',
            'No objective submission, model invocation, device effect, HOS2 kernel, Android/iOS qualification or arbitrary-descendant cleanup claim.',
            'Original build03 resumed the previously admitted target; the stock fresh 8GiB gate was not rerun.']}

def main():
    original = ROOT/'next-hepta-source'
    assert git(original, 'rev-parse', 'HEAD') == EXPECTED_ORIGINAL['commit']
    assert git(original, 'rev-parse', 'HEAD^{tree}') == EXPECTED_ORIGINAL['tree']
    assert git(original, 'status', '--porcelain') == ''
    assert digest(original/'codex-rs/Cargo.lock') == EXPECTED_ORIGINAL['cargo_lock_sha256']
    results = []
    for suffix in ('02','03'):
        result = verify_run(suffix)
        results.append(write(f'shell-{suffix}-independent-review.json', result))
    failed_capture = TOOLS/'r6-original-shell-01/capture-receipt.json'
    failed_runtime = TOOLS/'r6-original-runtime/runtime-01/receipt.json'
    failure = load(failed_capture)
    owner = load(failed_runtime)
    assert failure['capture_passed'] is False and failure['error'] == 'live runtime metadata changed: health'
    assert owner['status'] == 'failed' and owner['steps'][0]['exit_code'] == 1
    assert not Path(owner['private_original_state_root']).exists()
    assert not list((failed_runtime.parent/'phases').glob('ack-*.json'))
    failed_pids = [612928,612929,612960,612962,613064,613072]
    assert all(not Path('/proc',str(pid)).exists() for pid in failed_pids)
    combined = {'reviewer':'/root/r6_review_ci','reviewed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status':'passed','accepted_actual_pixel_images':12,'accepted_runs':results,
        'preserved_initial_failed_run':{'capture':file_info(failed_capture),'runtime':file_info(failed_runtime),
            'independent_failure_review':file_info(OUT/'shell-01-starting-independent-review.json'),
            'cause':'Initial oracle incorrectly required entire live health equality across legitimate Starting app_server_ready progress.',
            'no_ack_written':True,'private_state_absent_at_review':True,'actual_process_ids_absent_at_review':failed_pids,
            'owner_v2_receipt_has_explicit_cleanup_boolean':False,
            'recorded_shell_display_stops':failure['cleanup'],'probe_exit_code':1,'counts_as_completed_integration_pass':False},
        'stopped_stale_difference':{'old_R5_run02':'Retained Running/current6/PID615755/sample1792277809180/cursor4.',
            'new_GREEN03_run03':'Retained Draining/current7/PID616535/sample1792278002303/cursor5.',
            'interpretation':'Both are actual legal stop races; each first stale and later failure preserve its own complete last successful observation.'},
        'scope':'Real immutable original Hepta → continuous Session observer/IPC → one actual native Rust Shell across six phases, twice; no control-side effect or mobile readiness promoted.'}
    results.append(write('continuous-shell-independent-review.json', combined))
    print(json.dumps({'status':'passed','outputs':results},indent=2))

if __name__ == '__main__':
    main()
