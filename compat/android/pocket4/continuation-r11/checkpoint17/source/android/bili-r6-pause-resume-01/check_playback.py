#!/usr/bin/env python3
"""Production Session/selector/round logic; synthetic tree and explicit I/O seams."""
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
    current_label = '暂停'; inspect_count = 0; seeded = False
    first = RuntimeError('CONTROL_FIRST_INPUT_ERROR')
    state = {'accessibility_enabled':False, 'touch_exploration_enabled':False,
             'enabled_service_count':0, 'enabled_services_sha256':qa.sha(b'')}
    with tempfile.TemporaryDirectory(prefix='owned-bili-toggle-control-') as temp:
        flow = types.SimpleNamespace(step=Path(temp))
        session = object.__new__(adapter.Session); session.qa = qa
        session.installed = lambda: copy.deepcopy(installed)
        session.task = lambda: copy.deepcopy(owned)
        def foreground():
            value = fixture.scope()
            if seeded and mode == 'changed_foreground':value['window_token'] = 'ab13'
            return value
        session.foreground = foreground
        def instrument(request):
            nonlocal current_label, inspect_count
            calls.append((request['op'], request['nonce']))
            op = request['op']
            helper = {'protocol':qa.PROTOCOL, 'op':op, 'nonce':request['nonce'],
                'self_uid':10184, 'ok':True, 'error':None, 'secondary_errors':[],
                'restoration':{'service_info_verified':True},
                'ui_automation_connected':False if op == 'state' else True}
            if op == 'state':helper['state'] = copy.deepcopy(state)
            else:
                helper.update(host_scope_attestation=request['scope'],
                              accessibility_state_before_connection=copy.deepcopy(state))
                if op == 'inspect':
                    inspect_count += 1
                    if mode == 'first_and_post_errors' and seeded and inspect_count == 3:
                        raise RuntimeError('CONTROL_SECONDARY_POST_READ_ERROR')
                    value = tree(current_label)
                    if seeded and inspect_count == 2:
                        if mode == 'wrong_fresh_label':
                            value['nodes'][-1].update(content_desc='继续', content_desc_sha256=qa.sha('继续'.encode()))
                        elif mode == 'translated_fresh_frame':
                            for node in value['nodes']:
                                node['bounds'][0] += 32; node['bounds'][2] += 32
                            value['window']['bounds'][0] += 32; value['window']['bounds'][2] += 32
                        elif mode == 'duplicate_resource':
                            twin = copy.deepcopy(value['nodes'][-1]);twin['path'] = '0/0/0/2/0/1'
                            value['nodes'].append(twin)
                        elif mode == 'wrong_parent':
                            value['nodes'][-2]['class'] = 'android.widget.FrameLayout'
                    helper['inspection'] = fixture.refresh(value)
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
            (flow.step/(request['nonce']+'.assessment.json')).write_text(json.dumps(value, ensure_ascii=False))
            return value
        session.instrument = instrument
        seed = {'schema':1, 'operation':'inspect', 'nonces':dict(before='1'*32, inspect='2'*32, after='3'*32)}
        initial = session.sequence(seed); seeded = True
        def read(path, maximum=1048576, *args):
            raw = Path(path).read_bytes();assert len(raw) <= maximum;return raw
        # This is an explicit summary-metadata I/O seam. The production selector,
        # Session, independent read, assessment consumer and failure control flow run.
        def summaries(prior, contract, step, sequence, plan):
            values = {}
            for phase, nonce in plan['nonces'].items():
                item = json.loads((step/(nonce+'.assessment.json')).read_text())
                values[phase] = {'wire_sha256':item['wire_sha256']}
                if phase == 'inspect':
                    values[phase].update({k:item['helper']['inspection'][k] for k in ('tree_sha256','window_sha256')})
            return values
        def remember(result, phase, error):
            errors.append(error);record = {'phase':phase, 'type':type(error).__name__, 'message':str(error)}
            if result['error'] is None:result['error'] = record
            else:result['secondary_errors'].append(record)
        base = types.SimpleNamespace(require=qa.require, sha=qa.sha, read=read, UID=10184,
                                     assessment_summary=summaries)
        prior = types.SimpleNamespace(remember=remember)
        result = {'error':None, 'secondary_errors':[], 'controls_reveal_and_observation_completed':True,
            'controls_reveal_observation':{'independent_sequence':initial,
                'independent_observation':reveal.controls_evidence(qa,tree(),fixture.scope())}}
        toggle.run(base, prior, qa, reveal, flow, session, installed, result)
        assert session.qa is qa
        assert len({nonce for _,nonce in calls}) == len(calls), 'no sequence/action replay'
        phases = result['playback_button_observation']['transitions']
        clicks = sum(op == 'click' for op,_ in calls)
        if mode == 'success':
            assert result['playback_button_transitions_completed'] is True and clicks == 2 and len(phases) == 2
            assert [p['independent_observation']['observed_public_label'] for p in phases] == ['播放','暂停']
            assert all(p['sequence']['restoration_qualified'] and p['independent_sequence']['restoration_qualified'] for p in phases)
        else:
            assert result['playback_button_transitions_completed'] is False and len(phases) == 1
            assert phases[0]['independent_read_attempted'] is True
            assert sum(op == 'state' for op,_ in calls) == 6  # seed + action + independent read: each before/after.
            assert clicks == (1 if mode in ('first_error','first_and_post_errors','ack_without_label_transition') else 0)
            if mode in ('first_error','first_and_post_errors'):
                assert errors[0] is first and result['error']['message'] == str(first)
                assert result['secondary_errors'] and phases[0]['failed_sequence']['after_state_completed'] is True
        assert result['business_outcome_unknown'] is True and result['playback_or_audio_success_inferred'] is False
        return {'case':mode, 'passed':True, 'actual_click_IO_calls':clicks,
                'new_action_or_read_nonce_count':len(calls)-3, 'transitions_attempted':len(phases),
                'primary_error':result['error'], 'secondary_error_count':len(result['secondary_errors'])}


def main():
    toggle.validate(adapter, qa, ['0'*32])
    rows = [exercise(mode) for mode in ('success','wrong_fresh_label','changed_foreground',
        'translated_fresh_frame','duplicate_resource','wrong_parent','ack_without_label_transition',
        'first_error','first_and_post_errors')]
    print(json.dumps({'schema':1,'passed':len(rows),'controls':rows,
        'production_Session_and_selector_and_round_logic':True,
        'synthetic_complete_public_course_trees':True,'explicit_instrumentation_and_summary_IO_seams':True,
        'Android_or_namespace_or_UI_execution':False,'helper_Java_not_executed':True,
        'source_pins':{n:hashlib.sha256((HERE/n).read_bytes()).hexdigest()
                       for n in ('playback_controls.py','controls_reveal.py')}},ensure_ascii=False,indent=2))
    return 0


if __name__ == '__main__':raise SystemExit(main())
