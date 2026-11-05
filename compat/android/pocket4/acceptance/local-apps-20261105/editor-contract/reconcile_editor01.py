#!/usr/bin/python3 -I
"""Collect the completed Editor01 evidence and remove only its exact owned nonce."""
from pathlib import Path
import argparse, hashlib, json, os, re, types

EDITOR = Path('/home/alex/work/pocket4-editor-ui-tools-20261105-r12-01/editor_ui01.py')
EDITOR_SHA = '62f088841a1f35d40b15b40f917b6e3eea9a86071584e96888430feff67b5a3d'
ORIGINAL = Path('/home/alex/work/pocket4-editor-ui-20261105-r12-01')
RESULT_SHA = '15332e7f5124637f7fbea4597bf6d34d8f2f0cb5b31f37aba1f9044cbde31f17'
OUT = Path('/home/alex/work/pocket4-editor-reconcile-20261105-r12-01')

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reconcile-and-clean-exact-owned', action='store_true')
    if not ap.parse_args().reconcile_and_clean_exact_owned:
        print('INERT'); return 0
    raw = EDITOR.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EDITOR_SHA
    editor = types.ModuleType('frozen_editor01'); editor.__file__ = str(EDITOR)
    exec(compile(raw, str(EDITOR), 'exec'), editor.__dict__)
    before_raw = (ORIGINAL / 'result.json').read_bytes()
    assert hashlib.sha256(before_raw).hexdigest() == RESULT_SHA
    original = json.loads(before_raw)
    assert original['state'] == 'FAILED' and original['error'] == 'ControlError: STALE_FRAME'
    assert original['owned_tasks'] == original['closed_tasks'] == [922]
    assert original['pending_effect'] is None and original['ui_actions'] == 1
    assert original['native_launch_calls'] == original['nonce_intent_calls'] == 1
    assert original['owned_nonces_requiring_reconciliation'] == ['p4r12_editor_c749a031_0']
    assert os.geteuid() == 0 and not os.path.lexists(OUT)
    OUT.mkdir(mode=0o750); os.chown(OUT, 0, 1000); os.chmod(OUT, 0o750)
    base = editor.load(editor.CONTACT / 'ui_preflight04.py', editor.PINS[str(editor.CONTACT / 'ui_preflight04.py')])
    base.PACKAGE, base.COMPONENT, base.ROOT = editor.PACKAGE, editor.COMPONENT, OUT
    tx = base.load_session()
    result = {'schema': 'pocket4-editor01-exact-owned-reconciliation-v1',
        'original_result_sha256': RESULT_SHA, 'original_failure_preserved': True,
        'ui_actions': 0, 'launches': 0, 'input_replay': False, 'state': 'FAILED',
        'selected_observations': {}, 'owned_record_removed': False}
    selected = {'before-enter-0', 'after-unicode-0', 'fresh-enter-one-0',
        'nonce-launch-result-0', 'native-ack-unicode-0', 'response-unicode-0'}
    for path in sorted(ORIGINAL.glob('*.json')):
        match = re.fullmatch(r'\d+-(.+)\.json', path.name)
        if not match or match[1] not in selected:
            continue
        raw = path.read_bytes(); value = json.loads(raw)
        assert len(raw) <= 262144
        result['selected_observations'][match[1]] = {'source_file': path.name,
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'value': value}
    assert {'before-enter-0', 'after-unicode-0', 'fresh-enter-one-0'} <= set(result['selected_observations'])
    with tx.CameraSession(OUT / 'commands') as session:
        result['guard_before'] = session.guard()
        result['identity_before'] = editor.identity(session)
        assert result['identity_before'] == original['identity_before']
        roots, tasks = base.parse_stacks(session.android(['/system/bin/cmd', 'activity', 'stack', 'list']).decode())
        assert 922 not in tasks and 922 not in roots
        result['original_task_absence_verified'] = True
        trial = base.Trial(session, tx)
        evidence = editor.Evidence(trial, 'p4r12_editor_c749a031_0')
        result['closed_app_record'] = evidence.read('closed-owned-record')
        editor.Evidence(trial, 'p4r12_editor_c749a031_1').absent()
        evidence.cleanup()
        result['owned_record_removed'] = evidence.cleaned
        result['identity_after'] = editor.identity(session)
        assert result['identity_after'] == result['identity_before']
        result['guard_after'] = session.guard()
        result['state'] = 'ORIGINAL_EVIDENCE_COLLECTED_EXACT_NONCE_FILES_REMOVED'
    tx.write_new(OUT / 'result.json', result, alex_readable=True)
    print(json.dumps({'state': result['state'], 'ui_actions': 0, 'launches': 0,
        'owned_record_removed': result['owned_record_removed'], 'output': str(OUT / 'result.json')}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
