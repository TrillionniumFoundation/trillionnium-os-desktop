"""Original bounded private IHG assessment summarizer with explicit actual dependencies."""
import json
import types

def assessment_summary(common, qa, helper_uid, step, sequence, plan):
    """No raw UI text, node list, screenshots or recommendations in the result."""
    need, sha = common.need, common.sha
    read = lambda path: common.regular(path)[0]
    q = types.SimpleNamespace(qa=qa)
    HELPER_UID = helper_uid
    result={}
    for phase,nonce in plan['nonces'].items():
        path=step/(nonce+'.assessment.json');raw=read(path);value=json.loads(raw);helper=value['helper']
        need(helper['nonce']==nonce and helper['self_uid']==HELPER_UID and
             helper['op']==(plan['operation'] if phase=='action' else 'inspect' if phase=='inspect' else 'state') and
             value['actual_command_returncode']==0 and value['actual_instrumentation_finish_code']==-1 and
             value['held_transport_returned_after_post_guard'] is True and helper['ok'] is True and
             helper['error'] is None and helper['secondary_errors']==[] and
             value['wire_sha256']==sha(q.qa.canonical(helper)), 'ACTUAL_CURRENT_ASSESSMENT_REQUIRED')
        row={'nonce':nonce,'operation':helper['op'],'assessment_bytes':len(raw),'assessment_sha256':sha(raw),
            'wire_sha256':value['wire_sha256'],'recorder_command_result_sha256':value['recorder_command_result_sha256'],
            'actual_command_returncode':0,'actual_instrumentation_finish_code':-1}
        if phase=='inspect':
            inspection=q.qa.inspect_record(helper['inspection'])
            need(value['wire_sha256']==sequence['inspection_wire_sha256'],'INSPECTION_WIRE_CHANGED')
            row.update(tree_sha256=inspection['tree_sha256'],window_sha256=inspection['window_sha256'],
                node_count=len(inspection['nodes']),window={k:inspection['window'][k] for k in ('package','display','type','focused')},
                window_observation=q.qa.window_observation(helper['window_observation']),
                connection_scoped_window_id=inspection['connection_scoped_window_id'],
                tree_observations=q.qa.tree_observations(helper['tree_observations'],'inspect',True),
                complete=True,raw_tree_private_only=True)
        elif phase=='action':
            need(helper['node_action']==('ACTION_SET_TEXT' if plan['operation']=='set_text' else 'ACTION_CLICK') and
                 helper['node_action_returned'] is True and
                 helper['action_attempted'] is True and helper['outcome_unknown'] is True and
                 helper['inspection_nonce']==plan['nonces']['inspect'] and
                 helper['inspection_sha256']==sequence['inspection_wire_sha256'],'ACTUAL_CURRENT_SEARCH_CLICK_ACK_REQUIRED')
            row.update(node_action=helper['node_action'],node_action_returned=True,action_attempted=True,outcome_unknown=True,
                target_node_sha256=helper['target_node_sha256'],inspection_nonce=helper['inspection_nonce'],
                inspection_sha256=helper['inspection_sha256'],
                action_window={k:helper['action_window'][k] for k in ('package','display','type','focused')},
                window_observation=q.qa.window_observation(helper['window_observation']),
                tree_observations=q.qa.tree_observations(helper['tree_observations'],plan['operation'],True))
            if plan['operation']=='set_text':
                need(helper.get('target_resource_id')==plan['selector']['resource_id'] and
                     helper.get('requested_value_sha256')==helper.get('observed_value_sha256')==sha(b'London') and
                     helper.get('value_readback_verified') is True,'ACTUAL_PUBLIC_LONDON_INPUT_READBACK')
                row.update(fixed_public_value='London',requested_value_sha256=sha(b'London'),
                    observed_value_sha256=helper['observed_value_sha256'],value_readback_verified=True,
                    target_resource_sha256=sha(helper['target_resource_id'].encode()))
        result[phase]=row
    return result
