"""One current-player reveal input, then one independent controls observation.

This module has no command transport or selector fallback. It uses the exact
R6 Session and its fresh complete-tree/player proof. Full assessments remain
private; its result contains only scoped hashes, counts and input lifecycle.
"""
import json

REVEAL_PLAN = {'schema': 1, 'operation': 'reveal_controls', 'nonces': {'before': 'cbbc4acce223bfd32bdefe3d2d559d21', 'inspect': '93596efb86bc6ac0b7b0ad06f33cf788', 'action': '5f04f79b9d0520e01cfe7c6044c63ee9', 'after': '88c15c65ab23830855262d4de75af632'}}
POST_PLAN = {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '8a35025f37131394c7622dedf22d7fbc', 'inspect': '234fec58dcab499091b31feb950ec438', 'after': '91942b636467e4167f6617aa566532c2'}}


def validate(adapter, qa, used):
    qa.require(qa.PROTOCOL == 'pocket4-owned-bili-qa-v6', 'EXACT_R6_REVEAL_PROTOCOL_REQUIRED')
    for plan in (REVEAL_PLAN, POST_PLAN):
        adapter.validate_plan(plan, qa)
    qa.require(REVEAL_PLAN['operation'] == 'reveal_controls' and POST_PLAN['operation'] == 'inspect',
               'ONE_REVEAL_AND_ONE_INDEPENDENT_READ_REQUIRED')
    nonces = [n for plan in (REVEAL_PLAN, POST_PLAN) for n in plan['nonces'].values()]
    qa.require(len(nonces) == len(set(nonces)) == 7 and not set(nonces) & set(used),
               'SEVEN_FRESH_DISTINCT_REVEAL_NONCES_REQUIRED')


def assessment(base, qa, flow, nonce, operation, scope, expected_wire=None):
    path = flow.step / (nonce + '.assessment.json')
    raw = base.read(path, 1048576)
    value = json.loads(raw)
    helper = value['helper']
    base.require(value['held_transport_returned_after_post_guard'] is True and
                 value['actual_command_returncode'] == 0 and
                 value['actual_instrumentation_finish_code'] == -1 and
                 helper['ok'] is True and helper['error'] is None and helper['secondary_errors'] == [] and
                 helper['self_uid'] == base.UID and helper['nonce'] == nonce and
                 helper['protocol'] == qa.PROTOCOL and helper['op'] == operation and
                 helper['host_scope_attestation'] == scope and
                 value['wire_sha256'] == base.sha(qa.canonical(helper)) and
                 (expected_wire is None or value['wire_sha256'] == expected_wire),
                 'EXACT_CURRENT_REVEAL_ASSESSMENT_REQUIRED')
    pin = {'nonce':nonce, 'operation':operation, 'assessment_bytes':len(raw),
           'assessment_sha256':base.sha(raw), 'wire_sha256':value['wire_sha256'],
           'recorder_command_result_sha256':value['recorder_command_result_sha256'],
           'actual_command_returncode':0, 'actual_instrumentation_finish_code':-1}
    return helper, pin


def controls_evidence(qa, inspection, scope):
    """Observe controls inside the complete, fixed public-course player only."""
    proof = qa.player_reveal_scope(inspection, scope, False)
    nodes = inspection['nodes']
    def eligible(n):
        return (n['visible'] is True and n['enabled'] is True and n['password'] is False and
                n['class_truncated'] is False and n['resource_id_truncated'] is False)
    def one(resource):
        rows = [n for n in nodes if n['resource_id'] == qa.PACKAGE + ':id/' + resource and
                n['class'] == 'android.widget.FrameLayout' and eligible(n)]
        qa.require(len(rows) == 1, 'UNIQUE_CURRENT_REVEAL_CONTROL_ROLE_REQUIRED')
        return rows[0]
    container = one('video_container')
    controls = one('control_container')
    qa.require(controls['path'].startswith(container['path'] + '/') and
               controls['bounds'] == proof['viewport_bounds'] and
               type(controls['child_count']) is int and controls['child_count'] >= 0,
               'CURRENT_CONTROLS_MUST_BELONG_TO_EXACT_PLAYER')
    descendants = [n for n in nodes if n['path'].startswith(controls['path'] + '/')]
    def inside_crop(n):
        bounds = n['bounds']; crop = proof['viewport_bounds']
        return (len(bounds) == 4 and all(type(v) is int for v in bounds) and
                crop[0] <= bounds[0] < bounds[2] <= crop[2] and
                crop[1] <= bounds[1] < bounds[3] <= crop[3])
    interactive = [n for n in descendants if eligible(n) and inside_crop(n) and n['clickable'] is True]
    seekbars = [n for n in descendants if eligible(n) and inside_crop(n) and n['class'] == 'android.widget.SeekBar']
    shown = controls['child_count'] > 0 and bool(interactive or seekbars)
    return {'proof':proof, 'complete':True, 'node_count':len(nodes),
            'control_container_path_sha256':qa.sha(controls['path'].encode()),
            'control_container_node_sha256':controls['node_sha256'],
            'control_container_child_count':controls['child_count'],
            'complete_control_descendant_count':len(descendants),
            'visible_enabled_clickable_count':len(interactive),
            'visible_enabled_seekbar_count':len(seekbars),
            'controls_revealed_observed':shown, 'node_text_or_description_published':False,
            'pause_seek_or_audio_qualified':False, 'raw_tree_private_only':True}


def run(base, prior, qa, flow, session, installed, result):
    record = {'input_sequence_started':False, 'input_acknowledged':False,
              'independent_read_attempted':False, 'independent_read_completed':False,
              'controls_revealed_observed':False, 'automatic_retry':False,
              'pause_seek_or_audio_qualified':False, 'business_success_verified':False,
              'atomic_input_target_attribution':False}
    result['controls_reveal_observation'] = record
    result['controls_reveal_and_observation_completed'] = False
    input_proof = None
    input_observation_before = None
    try:
        base.require(result.get('video_click_and_observations_completed') is True and
                     result['error'] is None and result['secondary_errors'] == [],
                     'ORIGINAL_COURSE_OPEN_MUST_COMPLETE_BEFORE_REVEAL')
        record['input_sequence_started'] = True
        input_observation_before = getattr(session, 'sequence_observation', None)
        sequence = session.sequence(json.loads(json.dumps(REVEAL_PLAN)))
        record['input_sequence'] = sequence
        base.require(sequence['installed_before'] == sequence['installed_after'] == installed and
                     sequence.get('reveal_input_acknowledged') is True and
                     sequence.get('controls_revealed') is None and sequence['restoration_qualified'] is True and
                     sequence['after_state_completed'] is True and
                     sequence['foreground_before'] == sequence['foreground_after'],
                     'REVEAL_INPUT_ACK_SCOPE_IDENTITY_AND_RESTORATION_REQUIRED')
        scope = sequence['foreground_after']
        helper, pin = assessment(base, qa, flow, REVEAL_PLAN['nonces']['action'], 'reveal_controls', scope)
        qa.touch_observation(helper['touch'], True)
        input_proof = helper['player_scope']
        base.require(helper['inspection_nonce'] == REVEAL_PLAN['nonces']['inspect'] and
                     helper['inspection_sha256'] == sequence['inspection_wire_sha256'] and
                     input_proof['scope'] == scope and
                     helper['player_scope_sha256'] == qa.sha(qa.canonical(input_proof)),
                     'REVEAL_ACK_MUST_BIND_THIS_SEQUENCE_CURRENT_INSPECTION')
        immediate = controls_evidence(qa, helper['post_inspection'], scope)
        base.require(qa.same_reveal_frame(input_proof, immediate['proof']) and
                     helper['post_player_scope'] == immediate['proof'] and
                     qa.sha(qa.canonical(helper['post_inspection'])) == sequence['post_input_inspection_sha256'] and
                     helper['scope_unchanged_after_input'] is True,
                     'REVEAL_COMPLETE_IMMEDIATE_POST_SCOPE_REQUIRED')
        record.update(input_acknowledged=True, input_assessment=pin,
                      input_lifecycle=helper['touch'], immediate_post_observation=immediate)
    except BaseException as error:
        current = getattr(session, 'sequence_observation', None)
        if record['input_sequence_started'] and current is not None and current is not input_observation_before:
            record['failed_input_sequence'] = current
        prior.remember(result, 'controls_reveal_input', error)
    finally:
        # Independently observe after any attempted sequence, without repeating
        # the input. A failed read stays a failure and cannot replace the first.
        if record['input_sequence_started']:
            record['independent_read_attempted'] = True
            post_observation_before = getattr(session, 'sequence_observation', None)
            try:
                sequence = session.sequence(json.loads(json.dumps(POST_PLAN)))
                record['independent_sequence'] = sequence
                base.require(sequence['installed_before'] == sequence['installed_after'] == installed and
                             sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True and
                             sequence['foreground_before'] == sequence['foreground_after'],
                             'INDEPENDENT_REVEAL_READ_SCOPE_AND_RESTORATION_REQUIRED')
                helper, pin = assessment(base, qa, flow, POST_PLAN['nonces']['inspect'], 'inspect',
                                         sequence['foreground_after'], sequence['inspection_wire_sha256'])
                observed = controls_evidence(qa, helper['inspection'], sequence['foreground_after'])
                record.update(independent_read_completed=True, independent_assessment=pin,
                              independent_observation=observed, final_scope=observed['proof']['scope'])
                if input_proof is not None:
                    base.require(qa.same_reveal_frame(input_proof, observed['proof']),
                                 'ABSOLUTE_PLAYER_SCOPE_CHANGED_AFTER_REVEAL')
                record['controls_revealed_observed'] = observed['controls_revealed_observed']
                base.require(observed['controls_revealed_observed'] is True,
                             'INDEPENDENT_CURRENT_PLAYER_CONTROLS_NOT_OBSERVED')
            except BaseException as error:
                current = getattr(session, 'sequence_observation', None)
                if current is not None and current is not post_observation_before:
                    record['failed_independent_sequence'] = current
                prior.remember(result, 'independent_controls_readback', error)
    result['controls_reveal_and_observation_completed'] = (
        record['input_acknowledged'] and record['independent_read_completed'] and
        record['controls_revealed_observed'] and result['error'] is None and result['secondary_errors'] == [])
    result['business_outcome_unknown'] = True
    result['playback_or_audio_success_inferred'] = False
