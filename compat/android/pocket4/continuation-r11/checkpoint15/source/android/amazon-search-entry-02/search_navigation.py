"""One current Amazon search-entry click, without retained-node authority.

The public resource/class/role is the only selector. No retired node path,
account text, coordinates, raw tree or recommendation is present in this file.
The original Session and helper own every fresh inspection/action/after-state.
"""
import copy
import json
import time

PACKAGE='com.amazon.mShop.android.shopping'
ENTRY_ACTIVITY=PACKAGE+'/com.amazon.mShop.navigation.MainActivity'
SELECTOR={'resource_id':PACKAGE+':id/chrome_search_box',
          'class':'android.widget.ImageButton','content_desc':'Search'}
STABLE_READ_BUDGET_SECONDS=30


def need(value,reason):
    if not value:raise RuntimeError(reason)


def plans(spec):
    need(type(spec) is dict and set(spec)=={'schema','operation','stability','entry','post'} and
         spec['schema']==1 and spec['operation']=='search_entry' and
         type(spec['stability']) is list and len(spec['stability'])==5,
         'EXACT_BOUNDED_SEARCH_ENTRY_PLAN')
    rows=[*spec['stability'],spec['entry'],spec['post']]
    need(all(p['operation']=='inspect' for p in [*spec['stability'],spec['post']]) and
         spec['entry']['operation']=='click' and spec['entry']['selector']==SELECTOR,
         'ONLY_ONE_OBSERVED_PUBLIC_SEARCH_ENTRY_CLICK')
    return rows


def current_inspection(base,q,step,plan,sequence):
    need(sequence['installed_before']==sequence['installed_after']==q.installed,
         'EXACT_ACTUAL_INSTALLED_HELPER_DURING_READ')
    summary=base.assessment_summary(q,step,sequence,plan)
    raw=base.read(step/(plan['nonces']['inspect']+'.assessment.json'))
    value=json.loads(raw)
    need(summary['inspect']['assessment_sha256']==base.sha(raw) and
         value['wire_sha256']==sequence['inspection_wire_sha256'],
         'EXACT_CURRENT_ASSESSMENT_REQUIRED')
    return q.qa.inspect_record(value['helper']['inspection']),summary


def stable_entry(base,q,session,step,spec,result):
    previous=None;deadline=time.monotonic()+STABLE_READ_BUDGET_SECONDS
    result['stability_reads']=[]
    for index,plan in enumerate(spec['stability']):
        need(time.monotonic()<deadline,'SEARCH_ENTRY_STABILITY_READ_DEADLINE')
        sequence=session.sequence(copy.deepcopy(plan))
        inspection,summary=current_inspection(base,q,step,plan,sequence)
        scope=sequence['foreground_before']
        need(sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True and
             scope==sequence['foreground_after'] and scope['activity']==ENTRY_ACTIVITY,
             'EXACT_CURRENT_SEARCH_ENTRY_ACTIVITY')
        # This checks eligibility of each successful complete observation only.
        # The eventual action selects again inside its own original Session.
        q.qa.select_unique_clickable(inspection,SELECTOR)
        identity={'scope':scope,'tree_sha256':inspection['tree_sha256'],
                  'window_sha256':inspection['window_sha256']}
        result['stability_reads'].append({'index':index,'sequence':sequence,'assessments':summary,
            'public_entry_unique_and_eligible':True,'authorizes_future_node_action':False})
        need(time.monotonic()<deadline,'SEARCH_ENTRY_STABILITY_READ_DEADLINE')
        if previous==identity:
            result['stable_read_indices']=[index-1,index]
            return
        previous=identity
    raise RuntimeError('TWO_CONSECUTIVE_COMPLETE_SEARCH_ENTRY_OBSERVATIONS_REQUIRED')


class ActionBoundSearchContract:
    """Constrain the exact selection point of the unchanged Session.sequence."""
    def __init__(self,qa,session):self.original,self.session=qa,session
    def __getattr__(self,name):return getattr(self.original,name)
    def select_unique_clickable(self,inspection,selector):
        observed=self.session.sequence_observation
        need(selector==SELECTOR and observed['foreground_before']['activity']==ENTRY_ACTIVITY and
             observed['foreground_before']['package']==PACKAGE and
             inspection['window']['package']==PACKAGE,
             'ACTION_BOUND_CURRENT_SEARCH_ENTRY_SCOPE_REQUIRED')
        return self.original.select_unique_clickable(inspection,selector)


def run(base,q,session,step,spec,result):
    plans(spec)
    result['search_entry']={'ok':False,'error':None,'secondary_errors':[],
        'automatic_retry':False,'maximum_click_commands':1,'click_command_requested':False,
        'click_acknowledged':False,'post_inspection_attempted':False,'post_inspection_completed':False,
        'business_success_verified':False,'query_entered':False,'search_results_verified':False,
        'whole_app_production_ready':False,'raw_UI_tree_private_only':True}
    out=result['search_entry'];primary=None
    def remember(phase,error):
        nonlocal primary
        row={'phase':phase,'type':type(error).__name__,'message':str(error)}
        if primary is None:primary=error;out['error']=row
        else:out['secondary_errors'].append(row);primary.add_note(phase+': '+repr(error))
    try:
        stable_entry(base,q,session,step,spec,out)
        # No stale path/hash from stability reads is used for the action. The
        # unchanged Session reads a new complete tree then invokes this selector.
        original=session.qa
        session.qa=ActionBoundSearchContract(original,session)
        out['click_command_requested']=True
        try:
            out['entry_sequence']=session.sequence(copy.deepcopy(spec['entry']))
        finally:
            session.qa=original
        sequence=out['entry_sequence']
        need(sequence['click_acknowledged'] is True and sequence['restoration_qualified'] is True and
             sequence['after_state_completed'] is True and
             sequence['installed_before']==sequence['installed_after']==q.installed,
             'EXACT_ENTRY_CLICK_AND_RESTORATION_REQUIRED')
        out['entry_assessments']=base.assessment_summary(q,step,sequence,spec['entry'])
        out['click_acknowledged']=True
    except BaseException as error:
        if hasattr(session,'sequence_observation'):
            out['failed_sequence_observation']=copy.deepcopy(session.sequence_observation)
        remember('stable_search_entry_or_click',error)
    finally:
        # A failed read/action is never replayed. One independently named final
        # read is still attempted, with its own original after-state finally.
        out['post_inspection_attempted']=True
        try:
            sequence=session.sequence(copy.deepcopy(spec['post']))
            _,summary=current_inspection(base,q,step,spec['post'],sequence)
            need(sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True and
                 sequence['foreground_before']==sequence['foreground_after'],
                 'EXACT_POST_ENTRY_INSPECTION_AND_RESTORATION_REQUIRED')
            out['post_sequence']=sequence;out['post_assessments']=summary
            out['post_inspection_completed']=True
        except BaseException as error:
            if hasattr(session,'sequence_observation'):
                out['failed_post_sequence_observation']=copy.deepcopy(session.sequence_observation)
            remember('independent_post_entry_inspection',error)
    if primary is not None:raise primary
    need(out['click_acknowledged'] and out['post_inspection_completed'],
         'CURRENT_SEARCH_ENTRY_CLICK_AND_POST_READ_REQUIRED')
    out['ok']=True
    result['sequence']=out['post_sequence'];result['assessments']=out['post_assessments']
    result['inspection_completed']=True;result['search_entry_click_completed']=True
    return out
