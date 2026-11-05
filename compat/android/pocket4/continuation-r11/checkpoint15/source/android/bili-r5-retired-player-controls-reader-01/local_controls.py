#!/usr/bin/env python3
"""Local pure metadata/privacy controls; no collect, remote data or Android."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('fixed_controls_reader', HERE / 'read_controls.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/bili-r5-player-fresh-before01-read01/originals')
QA = Path('/workspace/scratch/94990735b266/owned-bili-qa-r5-cache-build02/source/qa_contract.py')
raw = QA.read_bytes()
assert len(raw) == 27891 and m.sha(raw) == m.QA_SHA
qa = {}; exec(compile(raw, str(QA), 'exec'), qa)
rows = []


def run(name, function):
    function(); rows.append({'name': name, 'passed': True})


def rejects(function, message):
    try:
        function()
    except RuntimeError as error:
        assert str(error) == message, str(error)
    else:
        raise AssertionError('expected rejection: ' + message)


def node(path, resource='', kind='android.widget.FrameLayout', label='', description='', **kwargs):
    value = {'path': path, 'package': 'tv.danmaku.bili', 'enabled': True, 'clickable': False,
             'visible': True, 'focused': False, 'selected': False, 'checked': False,
             'password': False, 'child_count': 0, 'editable': False, 'supports_set_text': False,
             'bounds': [0, 0, 100, 100]}
    for key, text in (('resource_id', resource), ('class', kind), ('text', label), ('content_desc', description)):
        value[key] = text; value[key + '_sha256'] = m.sha(text.encode()); value[key + '_truncated'] = False
    value.update(kwargs)
    if value['password'] or not value['visible']:
        value['content_redacted'] = True
        for key in ('text', 'content_desc'):
            for suffix in ('', '_sha256', '_truncated'):
                value.pop(key + suffix)
    value['node_sha256'] = m.sha(qa['canonical'](value))
    return value


def fixture(extra):
    values = [node('0'), node('0/1', m.ROLE_IDS['area']),
              node('0/1/0', m.ROLE_IDS['container']), node('0/1/1', m.ROLE_IDS['overlay']),
              node('0/1/2', m.ROLE_IDS['toolbar'])] + extra
    window = {'package': 'tv.danmaku.bili', 'display': 0, 'type': 1, 'focused': True}
    result = {'nodes': values, 'complete': True, 'traversal': 'visible-non-password-subtrees',
              'window': window, 'window_sha256': m.sha(qa['canonical'](window)),
              'tree_sha256': m.sha(qa['canonical'](values)), 'observed_elapsed_ms': 1,
              'connection_scoped_window_id': 1}
    qa['inspect_record'](result)
    return result, {'crop': [0, 0, 100, 100]}


def actual_pin_and_admission():
    values = {}
    for name, filename in (('coordinator', 'coordinator.json'), ('stage', 'stage.json'),
                           ('navigation', 'navigation.json'), ('cleanup', 'cleanup.json')):
        raw = (EVIDENCE / filename).read_bytes()
        _, size, digest, _ = m.INPUTS[name]
        assert len(raw) == size and m.sha(raw) == digest
        values[name] = json.loads(raw)
    sample = m.validate_retained(*(values[key] for key in ('coordinator', 'stage', 'navigation', 'cleanup')))
    for _, key, nonce, digest, wire in m.CASES:
        row = sample[key]['assessments']['inspect']
        assert row['nonce'] == nonce and row['assessment_sha256'] == digest and row['wire_sha256'] == wire
    assert len(m.INPUTS) == 11
    return values


def actual_unknown_preserved():
    values = actual_pin_and_admission()
    values['navigation']['outcome_unknown'] = False
    rejects(lambda: m.validate_retained(*(values[key] for key in ('coordinator', 'stage', 'navigation', 'cleanup'))),
            'BUSINESS_UNKNOWN_MUST_REMAIN_RECORDED')


def unknown_content_stays_hash_only():
    sentinel = 'private-comment-email-account-title-DO-NOT-EXPORT'
    inspection, proof = fixture([node('0/1/0/0', kind='android.widget.TextView', label=sentinel, description=sentinel)])
    result = m.controls_metadata(inspection, proof); m.no_raw_ui(result)
    encoded = json.dumps(result)
    assert sentinel not in encoded and m.sha(sentinel.encode()) in encoded
    row = result['rows'][-1]
    assert row['public_text_label'] is None and row['public_description_label'] is None


def exact_public_label_only():
    inspection, proof = fixture([node('0/1/0/0', kind='android.widget.ImageButton', description='Pause', clickable=True),
                                 node('0/1/0/1', kind='android.widget.TextView', label='Pause my private title')])
    result = m.controls_metadata(inspection, proof)
    assert result['rows'][-2]['public_description_label'] == 'Pause'
    assert result['rows'][-1]['public_text_label'] is None
    assert 'Pause my private title' not in json.dumps(result)


def exact_path_boundary():
    inspection, proof = fixture([node('0/10', resource='tv.danmaku.bili:id/outside', label='secretoutside', clickable=True)])
    result = m.controls_metadata(inspection, proof)
    assert result['row_count'] == 4 and result['outside_player_nodes_omitted'] == 2
    assert 'outside' not in json.dumps(result['rows']) and 'secretoutside' not in json.dumps(result)


def invisible_password_not_touched():
    inspection, proof = fixture([node('0/1/0/0', password=True), node('0/1/0/1', visible=False)])
    result = m.controls_metadata(inspection, proof)
    assert result['invisible_or_password_nodes_omitted'] == 2 and result['row_count'] == 4


def unsafe_identity_hash_only():
    unsafe = 'tv.danmaku.bili:id/private user title'
    inspection, proof = fixture([node('0/1/0/0', resource=unsafe, kind='Private User Class')])
    result = m.controls_metadata(inspection, proof)
    row = result['rows'][-1]
    assert row['resource_id'] is None and row['class_name'] is None
    assert unsafe not in json.dumps(result) and 'Private User Class' not in json.dumps(result)


def row_bound_refuses_partial():
    # Path components respect the actual helper grammar; siblings need not be real
    # Android nodes because this control is explicitly for the pure row cap.
    extra = [node('0/1/0/%d/%d' % (index // 64, index % 64)) for index in range(125)]
    inspection, proof = fixture(extra)
    rejects(lambda: m.controls_metadata(inspection, proof), 'PLAYER_CONTROL_METADATA_ROW_BOUND')


def no_invented_progress_capability():
    inspection, proof = fixture([node('0/1/0/0', kind='android.widget.SeekBar', clickable=True)])
    result = m.controls_metadata(inspection, proof)
    assert result['seekbar_class_count'] == 1 and result['accessibility_range_or_set_progress_support_observed'] is False
    assert result['control_presence_does_not_authorize_action'] is True


def raw_key_tripwire():
    rejects(lambda: m.no_raw_ui({'safe': [{'text': 'forbidden'}]}), 'RAW_UI_EXPORT_FORBIDDEN')


for name, function in (
    ('actual_four_safe_receipts_exact_pins_and_admission', actual_pin_and_admission),
    ('actual_business_unknown_must_not_be_promoted', actual_unknown_preserved),
    ('unknown_text_and_description_are_hash_only', unknown_content_stays_hash_only),
    ('only_exact_fixed_public_control_labels_emitted', exact_public_label_only),
    ('actual_helper_slash_path_boundary_no_prefix_collision', exact_path_boundary),
    ('password_and_invisible_metadata_skipped_without_content_access', invisible_password_not_touched),
    ('unsafe_resource_and_class_strings_are_hash_only', unsafe_identity_hash_only),
    ('row_limit_failure_never_returns_partial_success', row_bound_refuses_partial),
    ('SeekBar_class_does_not_prove_set_progress_support', no_invented_progress_capability),
    ('raw_UI_key_export_tripwire', raw_key_tripwire),
):
    run(name, function)
print(json.dumps({'schema': 1, 'state': 'LOCAL_METADATA_CONTROLS_PASS', 'passed': len(rows), 'controls': rows,
    'production_source_sha256': m.sha((HERE / 'read_controls.py').read_bytes()),
    'actual_safe_receipts_read': True, 'raw_commercial_assessment_read': False,
    'synthetic_player_rows': True, 'collect_executed': False, 'Android_or_process_actions': 0},
    sort_keys=True, indent=2))
