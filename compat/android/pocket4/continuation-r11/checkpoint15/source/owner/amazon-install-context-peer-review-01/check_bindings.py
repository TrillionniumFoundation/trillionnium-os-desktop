#!/usr/bin/env python3
"""Read-only pins/AST/retained-result checks; no production import or execution."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path('/workspace/scratch/94990735b266')
SOURCE = ROOT / 'android-amazon-qa-r1-install-state-01'
EVIDENCE = ROOT / 'root-recovery-20261104-02/evidence/amazon-qa-r1-install-state01-read01'
OUT = Path(__file__).resolve().parent


def pin(path):
    raw = path.read_bytes()
    raw.decode('utf-8')
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    expected = {
        'amazon_context.py': (13619, '59e4aac802aba1ac90800929e38dafd6455425d7fc97425b7ca640658d7934c1'),
        'amazon_transport.py': (15619, '7fd7cce15b902aa41f9abd32e5a64f2d0d26799e86afbe2c80984bdeccf22ed2'),
        'install_state.py': (32646, '8036635bac509beac9f510534565721ab82f3e3b3f9574e47c5074558afde672'),
        'SOURCE_PINS.json': (1506, '9179d58761fbf41c04c1a32c4398c9d7a7a7b36add5bf75f8ec89e189a4ed7cf'),
    }
    pins = {}
    for name, (size, digest) in expected.items():
        row = pin(SOURCE / name)
        assert row['bytes'] == size and row['sha256'] == digest
        pins[name] = row
    manifest = json.loads((SOURCE / 'SOURCE_PINS.json').read_bytes())
    for name, row in manifest['files'].items():
        actual = pin(SOURCE / name)
        assert (actual['bytes'], actual['sha256']) == (row['bytes'], row['sha256'])
    assert len(manifest['files']) == 10

    prior = ROOT / 'android-qa-install-state-02/r4/bound_android_transport.py'
    old = prior.read_text()
    new = (SOURCE / 'amazon_transport.py').read_text()
    assert old.count('EXPECTED_PACKAGE = "tv.danmaku.bili"') == 1
    assert old.count('EXPECTED_UID = 10117') == 1
    assert new == old.replace('EXPECTED_PACKAGE = "tv.danmaku.bili"',
                              'EXPECTED_PACKAGE = "com.amazon.mShop.android.shopping"').replace(
                                  'EXPECTED_UID = 10117', 'EXPECTED_UID = 10129')
    for name in expected:
        if name.endswith('.py'):
            ast.parse((SOURCE / name).read_text())
    recorder = ROOT / 'android-qa-install-state-01/review-inputs/recorder.py'
    assert pin(recorder)['sha256'] == '5f25f22db55ba94e6ac895c2ce274b6959a274b64c9aa82bbc30d8c3c860f511'

    report_path = EVIDENCE / 'reader-report.json'
    report_pin = pin(report_path)
    assert (report_pin['bytes'], report_pin['sha256']) == (
        39519, 'efd4d5e4abb6d8d1085d7a8360097e89d6d495950518baea1e61eb915db619d3')
    reader = json.loads(report_path.read_bytes())
    assert len(reader['files']) == 11
    actual_pins = {}
    for name, row in reader['files'].items():
        raw = (EVIDENCE / 'originals' / name).read_bytes()
        assert raw == row['text'].encode('utf-8')
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        actual_pins[name] = {'bytes': len(raw), 'sha256': row['sha256']}
    worker = json.loads((EVIDENCE / 'originals/worker.json').read_bytes())
    coordinator = json.loads((EVIDENCE / 'originals/coordinator.json').read_bytes())
    assert worker['source_manifest_sha256'] == expected['SOURCE_PINS.json'][1]
    assert coordinator['source_manifest_sha256'] == worker['source_manifest_sha256']
    assert worker['ok'] and coordinator['ok'] and worker['error'] is None
    assert worker['secondary_errors'] == coordinator['secondary_errors'] == []
    assert coordinator['worker_result']['sha256'] == actual_pins['worker.json']['sha256']
    assert coordinator['worker_result']['bytes'] == actual_pins['worker.json']['bytes']
    assert worker['install_attempted'] is worker['install_success_observed'] is worker['state_attempted'] is True
    assert worker['exact_command_count'] == 13 and worker['owned_package_uid'] == 10175
    assert worker['target_before'] == worker['target_after']
    assert worker['Main_before_lock'] == worker['Main_before'] == worker['Main_after']
    assert worker['target_FD_cleanup'] == {'held_APK_FDs_closed': 3, 'commercial_files_changed': False}
    assert worker['held_binding_released'] and worker['action_lock_released'] and worker['final_Main_guard_passed']
    assert worker['state']['helper']['ui_automation_connected'] is False
    assert worker['state']['helper']['op'] == 'state'
    for row in (worker, coordinator):
        assert all(row[k] == 0 for k in ('UI_actions', 'audio_actions', 'App_launches'))
        assert row['whole_app_production_ready'] is False
    result = {
        'schema': 1,
        'scope': 'Local source pins/AST/two-literal transport equality and retained public install/state receipt binding only.',
        'success': True,
        'pins': pins,
        'all_ten_manifest_members_exact': True,
        'transport_preimage': pin(prior),
        'only_two_transport_identity_literals_changed': True,
        'original_Flow_command_source': pin(recorder),
        'retained_reader': report_pin,
        'retained_originals': actual_pins,
        'retained_scope': {
            'reported_install_and_state_success': True,
            'target_package': 'com.amazon.mShop.android.shopping',
            'target_uid': 10129,
            'helper_package': 'org.droidloom.qa.amazon.r1',
            'actual_helper_uid': 10175,
            'reported_ordered_command_count': 13,
            'reported_closed_target_FDs': 3,
            'reported_no_UI_automation': True,
            'reported_Main_and_target_unchanged': True,
        },
        'production_module_imported': False,
        'production_controls_executed': False,
        'device_or_Hepta_executed': False,
        'whole_installation_runtime_independently_requalified': False,
        'whole_Amazon_production_qualified': False,
    }
    raw = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
    with (OUT / 'checks.json').open('xb') as stream:
        stream.write(raw)
    print(json.dumps(pin(OUT / 'checks.json')))


if __name__ == '__main__':
    main()
