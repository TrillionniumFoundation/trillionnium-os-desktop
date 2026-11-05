#!/usr/bin/env python3
"""Actual new controls_evidence predicate with the frozen public-course fixture.

All nodes are synthetic. No Android, namespace, filesystem evidence collection,
UI input, or original R6 control suite is executed by this file.
"""
import copy
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parent/'owned-bili-qa-r6-reveal-01'


def load(name, path):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
    return value


def main():
    fixture = load('fixed_public_synthetic_reveal_fixture', FROZEN/'controls/check_reveal.py')
    module = load('actual_controls_readback', HERE/'controls_reveal.py')
    qa = fixture.qa
    checks = []
    def observe(name, tree, shown):
        value = module.controls_evidence(qa, fixture.refresh(tree), fixture.scope())
        assert value['controls_revealed_observed'] is shown
        assert value['pause_seek_or_audio_qualified'] is False
        assert value['node_text_or_description_published'] is False
        checks.append({'case':name, 'passed':True, 'controls_revealed_observed':shown})
    def rejected(name, tree):
        try:
            module.controls_evidence(qa, fixture.refresh(tree), fixture.scope())
        except qa.ProtocolError as error:
            checks.append({'case':name, 'passed':True, 'rejected':str(error)})
        else:
            raise AssertionError(name+' was accepted')
    hidden = fixture.fixture()
    observe('complete_hidden_player_is_not_revealed', hidden, False)
    shown = fixture.fixture(); shown['nodes'][10]['child_count'] = 1
    n = fixture.node(qa.PACKAGE+':id/owned_synthetic_control', 'android.widget.Button',
                     '0/0/0/2/0', [900,360,940,400])
    n['clickable'] = True; shown['nodes'].append(n)
    observe('complete_in_scope_interactive_control_observed', shown, True)
    outside = copy.deepcopy(shown); outside['nodes'][-1]['bounds'] = [900,730,940,770]
    observe('descendant_outside_absolute_player_crop_not_revealed', outside, False)
    sibling = copy.deepcopy(shown); sibling['nodes'][-1]['path'] = '0/0/0/20/0'
    observe('path_prefix_sibling_not_control_descendant', sibling, False)
    disabled = copy.deepcopy(shown); disabled['nodes'][-1]['enabled'] = False
    observe('disabled_control_does_not_establish_reveal', disabled, False)
    duplicate = copy.deepcopy(shown); duplicate['nodes'].append(copy.deepcopy(duplicate['nodes'][10]))
    duplicate['nodes'][-1]['path'] = '0/0/0/3'
    rejected('duplicate_control_container_rejected', duplicate)
    partial = copy.deepcopy(shown); partial['complete'] = False
    rejected('partial_tree_not_readback_success', partial)
    foreign = copy.deepcopy(shown); foreign['window']['package'] = 'org.example.other'
    rejected('foreign_window_not_readback_success', foreign)
    # New orchestration must observe after a failed input sequence without
    # replaying it, preserving the original error if that observation fails.
    prior = load('actual_prior_error_recorder', HERE.parent/'android-qa-r5-install-state-03/install_state.py')
    base = types.SimpleNamespace(require=qa.require)
    class FailedSession:
        def __init__(self):
            self.calls = []
            self.sequence_observation = {'owned_synthetic_sequence':True}
        def sequence(self, plan):
            self.calls.append(plan['operation'])
            if len(self.calls) == 1:
                raise RuntimeError('OWNED_FIRST_INPUT_FAILURE')
            raise RuntimeError('OWNED_INDEPENDENT_READ_FAILURE')
    session = FailedSession()
    result = {'error':None, 'secondary_errors':[], 'video_click_and_observations_completed':True}
    module.run(base, prior, qa, None, session, None, result)
    assert session.calls == ['reveal_controls','inspect']
    assert result['error']['message'] == 'OWNED_FIRST_INPUT_FAILURE'
    assert [v['message'] for v in result['secondary_errors']] == ['OWNED_INDEPENDENT_READ_FAILURE']
    assert result['controls_reveal_and_observation_completed'] is False
    checks.append({'case':'actual_run_failed_input_keeps_first_error_and_independent_read_no_replay',
                   'passed':True, 'Session_IO_is_explicit_seam':True})
    session = FailedSession()
    result = {'error':None, 'secondary_errors':[], 'video_click_and_observations_completed':False}
    module.run(base, prior, qa, None, session, None, result)
    assert session.calls == [] and result['controls_reveal_and_observation_completed'] is False
    assert result['controls_reveal_observation']['independent_read_attempted'] is False
    checks.append({'case':'unqualified_course_open_cannot_start_reveal_or_followup', 'passed':True})
    # The frozen Session first evaluates installed_before, before it replaces
    # sequence_observation. A failed first step must not relabel its old object.
    preimage = load('prior_reveal_diagnostic_preimage', HERE/'controls_reveal-preimage-01.py')
    old_session = FailedSession(); old_observation = old_session.sequence_observation
    old_result = {'error':None, 'secondary_errors':[], 'video_click_and_observations_completed':True}
    preimage.run(base, prior, qa, None, old_session, None, old_result)
    assert old_result['controls_reveal_observation']['failed_input_sequence'] is old_observation
    assert old_result['controls_reveal_observation']['failed_independent_sequence'] is old_observation
    new_session = FailedSession()
    new_result = {'error':None, 'secondary_errors':[], 'video_click_and_observations_completed':True}
    module.run(base, prior, qa, None, new_session, None, new_result)
    assert 'failed_input_sequence' not in new_result['controls_reveal_observation']
    assert 'failed_independent_sequence' not in new_result['controls_reveal_observation']
    assert new_result['error'] == old_result['error'] and new_result['secondary_errors'] == old_result['secondary_errors']
    assert new_session.calls == old_session.calls == ['reveal_controls','inspect']
    checks.append({'case':'old_sequence_object_not_relabelled_after_first_step_failure',
                   'passed':True, 'preimage_diagnostic_counterexample_observed':True,
                   'first_and_secondary_errors_unchanged':True, 'Session_IO_is_explicit_seam':True})
    report = {'schema':1, 'passed':len(checks), 'controls':checks,
              'actual_production_functions':['controls_evidence','run'], 'synthetic_tree_fixture':True,
              'Session_IO_explicit_seam_for_two_orchestration_controls':True,
              'Android_actions':0, 'actual_controls_revealed':False,
              'input_lifecycle_or_whole_app_qualification':False,
              'production_sha256':hashlib.sha256((HERE/'controls_reveal.py').read_bytes()).hexdigest(),
              'frozen_fixture_sha256':hashlib.sha256((FROZEN/'controls/check_reveal.py').read_bytes()).hexdigest()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
