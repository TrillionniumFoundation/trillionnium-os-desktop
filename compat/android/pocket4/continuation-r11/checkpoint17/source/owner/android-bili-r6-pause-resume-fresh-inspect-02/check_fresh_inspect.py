#!/usr/bin/env python3
"""Unmodified production Session; synthetic complete trees and explicit I/O seams."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load(name, path):
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


fixture = load('existing_reveal_fixture', ROOT/'owned-bili-qa-r6-reveal-01/controls/check_reveal.py')
qa, adapter = fixture.qa, fixture.adapter
toggle = load('actual_playback_controls', HERE/'playback_controls.py')
reveal = load('actual_reveal_controls', HERE/'controls_reveal.py')


def tree(label='暂停'):
    value = fixture.fixture(); crop = value['nodes'][10]['bounds']
    value['nodes'][10]['child_count'] = 1
    parent = fixture.node('', 'android.view.ViewGroup', '0/0/0/2/0', crop)
    parent['child_count'] = 1
    control = fixture.node(toggle.RESOURCE, 'android.widget.ImageView', '0/0/0/2/0/0',
                           [crop[0], crop[3]-60, crop[0]+60, crop[3]])
    control.update(clickable=True, content_desc=label, content_desc_sha256=qa.sha(label.encode()))
    value['nodes'] += [parent, control]
    return fixture.refresh(value)


def exercise(mode):
    calls = []; errors = []; installed = {'synthetic_signed_identity':True}
    owned = {'task':12345, 'package':qa.PACKAGE, 'synthetic':True}
    current_label = '暂停'; playback_started = False; revealed = False
    first = RuntimeError('CONTROL_FIRST_INPUT_ERROR')
    state = {'accessibility_enabled':False, 'touch_exploration_enabled':False,
             'enabled_service_count':0, 'enabled_services_sha256':qa.sha(b'')}
    pause = toggle.PAIRS[0]; resume = toggle.PAIRS[1]
    with tempfile.TemporaryDirectory(prefix='owned-bili-fresh-inspect-control-') as temp:
        flow = types.SimpleNamespace(step=Path(temp))
        session = object.__new__(adapter.Session); session.qa = qa
        session.installed = lambda: copy.deepcopy(installed)
        session.task = lambda: copy.deepcopy(owned)
        def foreground():
            value = fixture.scope()
            if playback_started and mode == 'changed_foreground':value['window_token'] = 'ab13'
            return value
        session.foreground = foreground
        def instrument(request):
            nonlocal current_label, revealed
            op, nonce = request['op'], request['nonce']; calls.append((op, nonce))
            if mode == 'after_state_failure' and nonce == pause['action']['nonces']['after']:
                raise RuntimeError('CONTROL_PAUSE_AFTER_STATE_ERROR')
            if mode == 'reveal_after_state_failure' and nonce == reveal.REVEAL_PLAN['nonces']['after']:
                raise first
            helper = {'protocol':qa.PROTOCOL, 'op':op, 'nonce':nonce,
                'self_uid':10184, 'ok':True, 'error':None, 'secondary_errors':[],
                'restoration':{'service_info_verified':True},
                'action_attempted':op in ('click','reveal_controls'),
                'outcome_unknown':op in ('click','reveal_controls'),
                'ui_automation_connected':False if op == 'state' else True}
            if op == 'state':helper['state'] = copy.deepcopy(state)
            else:
                helper.update(host_scope_attestation=request['scope'],
                              accessibility_state_before_connection=copy.deepcopy(state))
                if op == 'inspect':
                    if mode == 'first_and_post_errors' and nonce == pause['post']['nonces']['inspect']:
                        raise RuntimeError('CONTROL_SECONDARY_POST_READ_ERROR')
                    value = tree(current_label) if revealed else fixture.fixture()
                    if nonce == pause['action']['nonces']['inspect']:
                        if mode == 'wrong_fresh_label':
                            value['nodes'][-1].update(content_desc='继续', content_desc_sha256=qa.sha('继续'.encode()))
                        elif mode == 'translated_fresh_frame':
                            for node in value['nodes']:
                                node['bounds'][0] += 32; node['bounds'][2] += 32
                            value['window']['bounds'][0] += 32; value['window']['bounds'][2] += 32
                        elif mode == 'duplicate_resource':
                            twin = copy.deepcopy(value['nodes'][-1]);twin['path'] = '0/0/0/2/0/1'
                            value['nodes'].append(twin)
                        elif mode == 'wrong_parent':value['nodes'][-2]['class'] = 'android.widget.FrameLayout'
                        elif mode == 'ack_only_hidden_controls':value = fixture.fixture()
                    helper['inspection'] = fixture.refresh(value)
                elif op == 'reveal_controls':
                    if mode == 'reveal_failure':raise first
                    hidden = fixture.fixture(); proof = qa.player_reveal_scope(hidden, request['scope'])
                    helper.update(inspection_nonce=request['inspection_nonce'],
                        inspection_sha256=request['inspection_sha256'], action_window=hidden['window'],
                        player_scope=proof, player_scope_sha256=qa.sha(qa.canonical(proof)),
                        post_inspection=hidden, post_player_scope=qa.player_reveal_scope(hidden,request['scope'],False),
                        scope_unchanged_after_input=True, touch=fixture.touch())
                    revealed = True
                elif op == 'click':
                    if mode in ('first_error','first_and_post_errors'):raise first
                    value = tree(current_label)
                    helper.update(inspection_nonce=request['inspection_nonce'],
                        inspection_sha256=request['inspection_sha256'], target_node_path=request['node_path'],
                        target_node_sha256=request['node_sha256'], action_window=value['window'])
                    if mode != 'ack_without_label_transition':current_label = '播放' if current_label == '暂停' else '暂停'
                else:raise AssertionError('unexpected I/O operation')
            value = {'helper':helper, 'wire_sha256':qa.sha(qa.canonical(helper)),
                'actual_command_returncode':0, 'actual_instrumentation_finish_code':-1,
                'held_transport_returned_after_post_guard':True, 'recorder_command_result_sha256':'c'*64}
            persisted = copy.deepcopy(value)
            is_pause_inspect = nonce == pause['action']['nonces']['inspect']
            if is_pause_inspect:
                if mode == 'wrong_assessment_wire':persisted['wire_sha256'] = 'd'*64
                elif mode == 'wrong_assessment_nonce':persisted['helper']['nonce'] = 'e'*32
                elif mode == 'wrong_assessment_scope':persisted['helper']['host_scope_attestation']['window_token'] = 'ab14'
                elif mode == 'assessment_action_attempted':persisted['helper']['action_attempted'] = True
                elif mode == 'assessment_restore_failed':persisted['helper']['restoration']['service_info_verified'] = False
                if mode in ('assessment_action_attempted','assessment_restore_failed'):
                    persisted['wire_sha256'] = qa.sha(qa.canonical(persisted['helper'])); value = copy.deepcopy(persisted)
            if not (is_pause_inspect and mode == 'missing_assessment'):
                (flow.step/(nonce+'.assessment.json')).write_text(json.dumps(persisted, ensure_ascii=False))
            if is_pause_inspect and mode == 'assessment_inspection_mismatch':
                value['helper']['inspection'] = fixture.fixture()
            return value
        session.instrument = instrument
        def read(path, maximum=1048576, *args):
            raw = Path(path).read_bytes();assert len(raw) <= maximum;return raw
        def summaries(prior, contract, step, sequence, plan):
            values = {}
            for phase, nonce in plan['nonces'].items():
                item = json.loads((step/(nonce+'.assessment.json')).read_text())
                values[phase] = {'wire_sha256':item['wire_sha256']}
                if phase == 'inspect':
                    values[phase].update({k:item['helper']['inspection'][k] for k in ('tree_sha256','window_sha256')})
            return values
        def remember(result, phase, error):
            errors.append(error); row = {'phase':phase, 'type':type(error).__name__, 'message':str(error)}
            if result['error'] is None:result['error'] = row
            else:result['secondary_errors'].append(row)
        base = types.SimpleNamespace(require=qa.require, sha=qa.sha, read=read, UID=10184,
                                     assessment_summary=summaries)
        prior = types.SimpleNamespace(remember=remember)
        result = {'error':None, 'secondary_errors':[], 'video_click_and_observations_completed':True}
        reveal.run(base, prior, qa, flow, session, installed, result)
        ready = result['controls_reveal_observation']
        if mode in ('reveal_failure','reveal_after_state_failure'):
            assert errors[0] is first and result['error']['message'] == str(first)
            assert ready['independent_read_attempted'] is True
            assert [op for op,_ in calls] == ['state','inspect','reveal_controls','state','state','inspect','state']
            assert result['controls_reveal_and_observation_completed'] is False
            phases = []; clicks = 0
        else:
            assert ready['input_acknowledged'] is True and ready['input_sequence']['restoration_qualified'] is True
            assert ready['immediate_post_observation']['controls_revealed_observed'] is False
            assert ready['independent_read_completed'] is False and ready['independent_read_attempted'] is False
            assert result['controls_reveal_and_observation_completed'] is False
            assert [op for op,_ in calls] == ['state','inspect','reveal_controls','state']
            playback_started = True
            toggle.run(base, prior, qa, reveal, flow, session, installed, result)
            phases = result['playback_button_observation']['transitions']
            clicks = sum(op == 'click' for op,_ in calls)
            assert not set(reveal.POST_PLAN['nonces'].values()) & {nonce for _,nonce in calls}
            if mode == 'success':
                assert result['playback_button_transitions_completed'] is True and clicks == 2 and len(phases) == 2
                assert result['controls_reveal_and_observation_completed'] is True
                assert ready['independent_sequence_restoration_qualified'] is True
                assert ready['independent_assessment']['nonce'] == pause['action']['nonces']['inspect']
                assert ready['independent_assessment']['wire_sha256'] == phases[0]['sequence']['inspection_wire_sha256']
                assert [p['independent_observation']['observed_public_label'] for p in phases] == ['播放','暂停']
                assert all(p['sequence']['restoration_qualified'] and p['independent_sequence']['restoration_qualified'] for p in phases)
                assert len(calls) == 18
            else:
                assert result['playback_button_transitions_completed'] is False and len(phases) == 1
                assert phases[0]['independent_read_attempted'] is True
                assert not {n for plan in (resume['action'],resume['post']) for n in plan['nonces'].values()} & {n for _,n in calls}
                assert clicks == (1 if mode in ('first_error','first_and_post_errors','ack_without_label_transition','after_state_failure') else 0)
                assert pause['action']['nonces']['after'] in {nonce for _,nonce in calls}
                assert pause['post']['nonces']['after'] in {nonce for _,nonce in calls}
                if mode in ('first_error','first_and_post_errors'):
                    assert errors[0] is first and result['error']['message'] == str(first)
                    assert result['secondary_errors'] and phases[0]['failed_sequence']['after_state_completed'] is True
                if mode == 'after_state_failure':
                    assert ready['independent_sequence_restoration_qualified'] is False
                    assert result['controls_reveal_and_observation_completed'] is False
        assert session.qa is qa
        assert len({nonce for _,nonce in calls}) == len(calls), 'no sequence/action replay'
        assert result['business_outcome_unknown'] is True and result['playback_or_audio_success_inferred'] is False
        error = copy.deepcopy(result['error'])
        if error and error['type'] == 'FileNotFoundError':error['message'] = 'missing exact current assessment'
        return {'case':mode, 'passed':True, 'actual_click_IO_calls':clicks,
                'instrumentation_IO_calls':len(calls), 'transitions_attempted':len(phases),
                'primary_error':error, 'secondary_error_count':len(result['secondary_errors'])}


def main():
    reveal.validate(adapter, qa, ['0'*32]); toggle.validate(adapter, qa,
        [n for p in (reveal.REVEAL_PLAN,reveal.POST_PLAN) for n in p['nonces'].values()])
    modes = ('success','wrong_fresh_label','changed_foreground','translated_fresh_frame',
        'duplicate_resource','wrong_parent','ack_without_label_transition','first_error','first_and_post_errors',
        'after_state_failure','ack_only_hidden_controls','missing_assessment','wrong_assessment_wire',
        'wrong_assessment_nonce','wrong_assessment_scope','assessment_action_attempted',
        'assessment_restore_failed','assessment_inspection_mismatch','reveal_failure','reveal_after_state_failure')
    rows = [exercise(mode) for mode in modes]
    print(json.dumps({'schema':1,'passed':len(rows),'controls':rows,
        'production_Session_and_selector_and_reveal_and_round_logic':True,
        'synthetic_complete_public_course_trees':True,'explicit_instrumentation_and_summary_IO_seams':True,
        'Android_or_namespace_or_UI_execution':False,'helper_Java_not_executed':True,
        'source_pins':{n:hashlib.sha256((HERE/n).read_bytes()).hexdigest()
                       for n in ('playback_controls.py','controls_reveal.py')},
        'unmodified_Session_source_sha256':hashlib.sha256((ROOT/'owned-bili-qa-r6-reveal-01/source/qa_adapter.py').read_bytes()).hexdigest()},
        ensure_ascii=False,indent=2))
    return 0


if __name__ == '__main__':raise SystemExit(main())
