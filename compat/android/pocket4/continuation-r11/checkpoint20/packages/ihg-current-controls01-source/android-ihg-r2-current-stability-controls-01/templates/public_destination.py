"""Explicit fresh Search then Destination; independent final read, no text input."""
import copy
import re
import math
import time

FORM_ROLES=('destination','dates','rooms_guests')
MAX_ANCESTORS=6

def public_form_nodes(qa,inspection):
    qa.inspect_record(inspection)
    result={role:[] for role in FORM_ROLES}
    for node in inspection['nodes']:
        if node.get('visible') is not True or node.get('password') is not False:
            continue
        for role in FORM_ROLES:
            fields=[]
            for field in ('text','content_desc'):
                value=node.get(field)
                if (isinstance(value,str) and node.get(field+'_truncated') is False and
                    ' '.join(value.split()).casefold() in PUBLIC_ROLES[role]):
                    need(node.get(field+'_sha256')==qa.sha(value.encode()),'PUBLIC_FORM_LABEL_DIGEST_REQUIRED')
                    fields.append(field)
            if fields:result[role].append(node)
    return result

def eligible(node):
    return (isinstance(node,dict) and node.get('visible') is True and node.get('enabled') is True and
        node.get('password') is False and node.get('class_truncated') is False and
        node.get('resource_id_truncated') is False and node.get('editable') is False)

def bounds(node):
    value=node.get('bounds')
    need(isinstance(value,list) and len(value)==4 and all(type(x) is int for x in value) and
         value[0]<value[2] and value[1]<value[3],'CURRENT_PUBLIC_FORM_GEOMETRY_REQUIRED')
    return value

def contains(outer,inner):
    return outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3]

def destination_selector(qa,inspection):
    """Choose only a fresh complete public form's unique finite clickable ancestor."""
    roles=public_form_nodes(qa,inspection)
    need(all(len(roles[role])==1 for role in FORM_ROLES),'UNIQUE_COMPLETE_PUBLIC_FORM_LABELS_REQUIRED')
    need(all(eligible(roles[role][0]) and roles[role][0].get('class')=='android.widget.TextView'
             and roles[role][0].get('clickable') is False for role in FORM_ROLES),
         'ELIGIBLE_NONCLICKABLE_PUBLIC_FORM_TEXT_LABELS_REQUIRED')
    label=roles['destination'][0];label_bounds=bounds(label)
    window_bounds=bounds(inspection['window'])
    nodes=inspection['nodes'];by_path={n['path']:n for n in nodes}
    path=label['path'];ancestors=[];candidates=[]
    for level in range(1,MAX_ANCESTORS+1):
        if '/' not in path:break
        path=path.rsplit('/',1)[0]
        need(path in by_path,'COMPLETE_PUBLIC_ANCESTOR_CHAIN_REQUIRED')
        parent=by_path[path]
        direct=[n for n in nodes if '/' in n['path'] and n['path'].rsplit('/',1)[0]==path]
        need(type(parent.get('child_count')) is int and parent['child_count']==len(direct)<=64,
             'COMPLETE_PUBLIC_ANCESTOR_CHILDREN_REQUIRED')
        need(contains(bounds(parent),label_bounds),'PUBLIC_ANCESTOR_MUST_CONTAIN_LABEL')
        ancestors.append((level,parent))
        if eligible(parent) and parent.get('clickable') is True:candidates.append((level,parent))
    need(len(candidates)==1,'UNIQUE_FINITE_CLICKABLE_DESTINATION_ANCESTOR_REQUIRED')
    level,node=candidates[0]
    need(node.get('class')=='android.view.ViewGroup' and contains(window_bounds,bounds(node)),
         'VISIBLE_CURRENT_DESTINATION_CONTAINER_GEOMETRY_REQUIRED')
    counts={role:sum(n['path']==node['path'] or n['path'].startswith(node['path']+'/')
                     for n in roles[role]) for role in FORM_ROLES}
    need(counts=={'destination':1,'dates':0,'rooms_guests':0},'DESTINATION_CONTAINER_MUST_EXCLUDE_OTHER_PUBLIC_FORM_ROLES')
    resource=node.get('resource_id')
    need(isinstance(resource,str) and re.fullmatch(re.escape(qa.PACKAGE)+r':id/[A-Za-z0-9_]+',resource)
         and 0<len(resource.encode())<=256 and node.get('resource_id_sha256')==qa.sha(resource.encode())
         and node.get('class_sha256')==qa.sha(node['class'].encode()),
         'COMPLETE_CURRENT_DESTINATION_RESOURCE_REQUIRED')
    selector={'class':node['class'],'resource_id':resource}
    selected=qa.select_unique_clickable(inspection,selector)
    need(selected=={'node_path':node['path'],'node_sha256':node['node_sha256']},
         'ORIGINAL_UNIQUE_CLICKABLE_DESTINATION_TARGET_REQUIRED')
    safe={'role':'destination','finite_ancestor_limit':MAX_ANCESTORS,
        'unique_eligible_clickable_ancestor_count':1,'chosen_distance_from_public_label':level,
        'examined_ancestor_count':len(ancestors),'bounds_contain_public_label':True,
        'container_inside_current_window':True,'complete_direct_children_verified':True,
        'public_form_label_counts':{role:len(roles[role]) for role in FORM_ROLES},
        'candidate_public_form_descendant_counts':counts,'target_resource_from_current_inspection':True,
        'unknown_resource_or_label_or_coordinates_exported':False,
        'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
        'node_count':len(nodes),'complete_tree_verified':True,
        'historical_node_or_task_used_as_authority':False,'implicit_search_click_allowed':False}
    return selector,selected,safe

def public_search_nodes(qa,inspection):
    qa.inspect_record(inspection)
    rows=[]
    for node in inspection['nodes']:
        if node.get('visible') is not True or node.get('password') is not False:
            continue
        fields=[]
        for field in ('content_desc','text'):
            value=node.get(field)
            if (isinstance(value,str) and node.get(field+'_truncated') is False and
                ' '.join(value.split()).casefold()=='search'):
                need(node.get(field+'_sha256')==qa.sha(value.encode()),'PUBLIC_SEARCH_LABEL_DIGEST_REQUIRED')
                fields.append(field)
        if fields:
            rows.append((node,fields))
    return rows

def search_selector(qa,inspection):
    """A new complete inspection chooses one actual self-clickable public role."""
    counts=public_role_counts(qa,inspection)
    role=counts['fixed_public_role_queries']['search_tab']
    need(role['matching_visible_nonpassword_nodes']==role['eligible_matching_nodes']==2 and
         role['known_class_counts']=={'android.widget.FrameLayout':1,'android.widget.TextView':1} and
         role['eligible_clickable_self_count']==role['distinct_self_or_direct_parent_candidates']==1 and
         role['eligible_direct_clickable_parent_count']==role['editable_matching_nodes']==0,
         'UNIQUE_CURRENT_PUBLIC_SEARCH_ROLE_REQUIRED')
    rows=public_search_nodes(qa,inspection)
    need(len(rows)==2 and all(type(node.get('selected')) is bool for node,_ in rows),
         'CURRENT_PUBLIC_SEARCH_SELECTION_FLAGS_REQUIRED')
    need(all(node['selected'] is False for node,_ in rows),'PUBLIC_SEARCH_ALREADY_SELECTED_NO_CLICK_REQUIRED')
    candidates=[(n,fields) for n,fields in rows if n.get('clickable') is True and n.get('enabled') is True]
    need(len(candidates)==1,'UNIQUE_CURRENT_SEARCH_SELF_TARGET_REQUIRED')
    node,fields=candidates[0]
    need(node.get('package')==qa.PACKAGE and node.get('editable') is False and
         all(node.get(k+'_truncated') is False for k in ('class','resource_id','text','content_desc')),
         'COMPLETE_NONEDITABLE_PUBLIC_SEARCH_SELF_TARGET_REQUIRED')
    field=fields[0]
    selector={'class':node['class'],field:node[field]}
    selected=qa.select_unique_clickable(inspection,selector)
    need(selected=={'node_path':node['path'],'node_sha256':node['node_sha256']},
         'ORIGINAL_UNIQUE_CLICKABLE_PUBLIC_SEARCH_TARGET_REQUIRED')
    safe={'role':'search_tab','selected_before':False,'self_candidate_count':1,
        'matching_public_node_count':2,'parent_fallback_used':False,
        'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
        'node_count':len(inspection['nodes']),'complete_tree_verified':True,
        'historical_node_or_task_used_as_authority':False}
    return selector,selected,safe


def search_readiness_sample(qa,helper,scope,owned_task):
    """Safe identity of a current complete public Search observation, no node export."""
    inspection=qa.inspect_record(helper['inspection'])
    _,node,safe=search_selector(qa,inspection)
    counters=qa.tree_observations(helper['tree_observations'],'inspect',True)
    need(len(counters)==1 and counters[0]['complete'] is True and
         counters[0]['emitted_nodes']==len(inspection['nodes']),
         'COMPLETE_SEARCH_READINESS_CAPTURE_REQUIRED')
    capture=counters[0]
    need(type(capture['began_elapsed_ms']) is int and type(capture['last_elapsed_ms']) is int and
         0<=capture['began_elapsed_ms']<=capture['last_elapsed_ms'],
         'MONOTONIC_SEARCH_READINESS_CAPTURE_REQUIRED')
    current_scope=qa.scope(scope)
    identity={'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
              'node':node,'foreground':current_scope,'owned_task':owned_task}
    return {'identity_sha256':qa.sha(qa.canonical(identity)),
            'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
            'capture_began_elapsed_ms':capture['began_elapsed_ms'],
            'capture_last_elapsed_ms':capture['last_elapsed_ms'],
            'node_count':len(inspection['nodes']),'public_search_role':safe,
            'complete':True,'scope':copy.deepcopy(current_scope),'owned_task':copy.deepcopy(owned_task),
            'node_exported':False,'connection_scoped_window_id_compared_across_invocations':False}


def qualify_search_readiness(qa,session,installed,plans,result,summary,clock=None):
    """Finite complete reads; time span qualifies samples, never a future action."""
    need(len(plans)==8 and all(p['operation']=='inspect' for p in plans),
         'EIGHT_FIXED_NO_ACTION_SEARCH_READINESS_PLANS_REQUIRED')
    if clock is None:clock=time.monotonic
    began=clock();previous_clock=began
    need(type(began) in (int,float) and math.isfinite(began),'FINITE_SEARCH_READINESS_CLOCK_REQUIRED')
    deadline=began+20
    result['search_readiness_observations']=[]
    first_task=first_scope=last_key=None
    run_count=0;run_began=None;previous_capture_last=None
    for index,plan in enumerate(plans):
        now=clock()
        need(type(now) in (int,float) and math.isfinite(now) and previous_clock<=now<deadline,
             'SEARCH_READINESS_QUALIFICATION_DEADLINE')
        previous_clock=now
        if hasattr(session,'sequence_observation'):del session.sequence_observation
        seq=session.sequence(plan)
        need(seq['installed_before']==seq['installed_after']==installed and
             seq.get('after_state_completed') is True and seq.get('restoration_qualified') is True and
             seq.get('post_state_matches_before') is True and
             seq['foreground_before']==seq['foreground_after'] and
             seq['post_termination_state']['ui_automation_connected'] is False,
             'ORIGINAL_SEARCH_READINESS_STATE_RESTORATION_REQUIRED')
        current=session.search_readiness_samples[plan['nonces']['inspect']]
        need(current['owned_task']==seq['owned_task'] and current['scope']==seq['foreground_before'],
             'SEARCH_READINESS_CURRENT_TASK_AND_SCOPE_REQUIRED')
        if first_task is None:
            first_task=copy.deepcopy(seq['owned_task']);first_scope=copy.deepcopy(seq['foreground_before'])
        need(seq['owned_task']==first_task and seq['foreground_before']==first_scope,
             'SEARCH_READINESS_OWNED_TASK_OR_FOREGROUND_CHANGED')
        need(previous_capture_last is None or current['capture_began_elapsed_ms']>=previous_capture_last,
             'SEARCH_READINESS_CAPTURE_TIME_MOVED_BACKWARD')
        previous_capture_last=current['capture_last_elapsed_ms']
        now=clock()
        need(type(now) in (int,float) and math.isfinite(now) and previous_clock<=now<=deadline,
             'SEARCH_READINESS_QUALIFICATION_DEADLINE')
        previous_clock=now
        if current['identity_sha256']==last_key:
            run_count+=1
        else:
            last_key=current['identity_sha256'];run_count=1
            run_began=current['capture_began_elapsed_ms']
        span=current['capture_last_elapsed_ms']-run_began
        assessments=summary(seq,plan)
        need(assessments['inspect']['wire_sha256']==seq['inspection_wire_sha256'] and
             assessments['inspect']['tree_sha256']==current['tree_sha256'] and
             assessments['inspect']['window_sha256']==current['window_sha256'],
             'SEARCH_READINESS_SAFE_ASSESSMENT_BINDING_REQUIRED')
        result['search_readiness_observations'].append({'index':index+1,'sequence':seq,
            'assessments':assessments,'observation':current,'consecutive_equal':run_count,
            'capture_span_ms':span,'qualified':run_count>=3 and span>=4000})
        if run_count>=3 and span>=4000:
            session.search_readiness_qualified=True
            session.search_readiness_identity=last_key
            session.search_readiness_owned_task=first_task
            result['search_readiness_qualified']=True
            result['search_readiness_count']=index+1
            result['search_readiness_capture_span_ms']=span
            result['search_readiness_future_stability_proven']=False
            return
    raise RuntimeError('SEARCH_READINESS_NOT_STABLE_WITHIN_EIGHT_COMPLETE_READS')

def make_session(adapter,flow,recorder,qa,proof,helper_uid,search_plan,click_plan,post_plan,readiness_plans):
    """Two explicit fresh roles; original Session.sequence and helper guards remain."""
    class PublicSearchDestinationSession(adapter.Session):
        def __init__(self):
            super().__init__(flow,recorder,qa,proof,helper_uid)
            self.readiness_inspection_nonces={plan['nonces']['inspect'] for plan in readiness_plans}
            need(len(readiness_plans)==len(self.readiness_inspection_nonces)==8,
                 'EIGHT_DISTINCT_READINESS_INSPECTIONS_REQUIRED')
            self.search_readiness_samples={}
            self.search_readiness_qualified=False
            self.search_readiness_identity=None
            self.search_readiness_owned_task=None
            self.public_search_proof=None
            self.public_search_entry=None
            self.public_destination_proof=None
            self.search_sequence_qualified=False
            self.search_owned_task=None
            self._action_bindings={}
            self.post_inspection=None
            self.action_requests_admitted=set()

        def instrument(self,request):
            if request['op']=='click':
                role=('search' if request['nonce']==search_plan['nonces']['action'] else
                      'destination' if request['nonce']==click_plan['nonces']['action'] else None)
                need(role is not None and role in self._action_bindings and
                     role not in self.action_requests_admitted,
                     'ONE_EXPLICIT_FRESH_REQUEST_PER_PUBLIC_ROLE_REQUIRED')
                need(request==self._action_bindings[role],
                     'EXACT_FRESH_PUBLIC_ROLE_NODE_REQUEST_REQUIRED')
                if role=='destination':
                    need(self.search_sequence_qualified is True and self.public_search_entry is not None and
                         self.public_search_entry.get('public_search_entry_selection_verified') is True and
                         getattr(self,'sequence_observation',{}).get('owned_task')==self.search_owned_task,
                         'QUALIFIED_SEARCH_AND_SAME_OWNED_TASK_BEFORE_DESTINATION_REQUIRED')
                self.action_requests_admitted.add(role)
            assessed=super().instrument(request)
            if request['nonce'] in self.readiness_inspection_nonces:
                need(request['op']=='inspect' and request['nonce'] not in self.search_readiness_samples and
                     self.search_readiness_qualified is False and not self.action_requests_admitted,
                     'ONE_FRESH_NO_ACTION_SEARCH_READINESS_OBSERVATION_REQUIRED')
                self.search_readiness_samples[request['nonce']]=search_readiness_sample(qa,assessed['helper'],
                    request['scope'],self.sequence_observation['owned_task'])
            elif request['nonce']==search_plan['nonces']['inspect']:
                need(request['op']=='inspect' and self.public_search_proof is None and
                     not self.action_requests_admitted,
                     'ONE_CURRENT_EXPLICIT_SEARCH_INSPECTION_REQUIRED')
                need(self.search_readiness_qualified is True and
                     self.sequence_observation['owned_task']==self.search_readiness_owned_task,
                     'QUALIFIED_CURRENT_SEARCH_READINESS_REQUIRED')
                current=search_readiness_sample(qa,assessed['helper'],request['scope'],
                    self.sequence_observation['owned_task'])
                need(current['identity_sha256']==self.search_readiness_identity,
                     'SEARCH_CHANGED_AFTER_READINESS_NO_ACTION')
                selector,node,safe=search_selector(qa,assessed['helper']['inspection'])
                search_plan['selector']=selector
                adapter.validate_plan(search_plan,qa)
                self._action_bindings['search']={'protocol':qa.PROTOCOL,
                    'nonce':search_plan['nonces']['action'],'op':'click','scope':copy.deepcopy(request['scope']),
                    'inspection_nonce':request['nonce'],'inspection_sha256':assessed['wire_sha256'],**node}
                self.public_search_proof={**safe,'inspection_nonce':request['nonce'],
                    'inspection_wire_sha256':assessed['wire_sha256']}
            elif request['nonce']==click_plan['nonces']['inspect']:
                need(request['op']=='inspect' and self.public_destination_proof is None and
                     self.search_sequence_qualified is True and self.action_requests_admitted=={'search'} and
                     getattr(self,'sequence_observation',{}).get('owned_task')==self.search_owned_task,
                     'QUALIFIED_SEARCH_AND_FRESH_SAME_TASK_DESTINATION_INSPECTION_REQUIRED')
                # This is a new complete observation after the first sequence's
                # original after-state/installation/task checks, never its ACK.
                inspection=assessed['helper']['inspection']
                self.public_search_entry=entry_readback(qa,inspection,self.public_search_proof)
                selector,node,safe=destination_selector(qa,inspection)
                click_plan['selector']=selector
                adapter.validate_plan(click_plan,qa)
                self._action_bindings['destination']={'protocol':qa.PROTOCOL,
                    'nonce':click_plan['nonces']['action'],'op':'click','scope':copy.deepcopy(request['scope']),
                    'inspection_nonce':request['nonce'],'inspection_sha256':assessed['wire_sha256'],**node}
                self.public_destination_proof={**safe,'inspection_nonce':request['nonce'],
                    'inspection_wire_sha256':assessed['wire_sha256'],
                    'preceding_explicit_search_sequence_qualified':True,
                    'fresh_search_selection_verified':True}
            elif request['nonce']==post_plan['nonces']['inspect']:
                need(request['op']=='inspect' and self.post_inspection is None,
                     'ONE_INDEPENDENT_POST_INSPECTION_REQUIRED')
                self.post_inspection=assessed['helper']['inspection']
            return assessed
    return PublicSearchDestinationSession()

def run_sequences(qa,session,installed,search_plan,click_plan,post_plan,readiness_plans,result,summary,remember):
    """First Search must finish before fresh Destination; post-read always runs."""
    result['search_readiness_started']=True
    current_phase='search_readiness'
    try:
        qualify_search_readiness(qa,session,installed,readiness_plans,result,summary)
        result['search_sequence_started']=True
        current_phase='explicit_public_search_click'
        if hasattr(session,'sequence_observation'):del session.sequence_observation
        seq=session.sequence(search_plan)
        result['search_sequence']=seq
        need(seq['installed_before']==seq['installed_after']==installed and
             seq.get('click_acknowledged') is True and seq['after_state_completed'] is True and
             seq['restoration_qualified'] is True,'ORIGINAL_SEARCH_CLICK_AND_RESTORATION_REQUIRED')
        result['search_assessments']=summary(seq,search_plan)
        result['public_search_action_binding']=session.public_search_proof
        result['search_click_acknowledged']=True
        session.search_owned_task=copy.deepcopy(seq['owned_task'])
        session.search_sequence_qualified=True
        result['search_sequence_qualified']=True
        result['click_sequence_started']=True
        try:
            if hasattr(session,'sequence_observation'):del session.sequence_observation
            seq=session.sequence(click_plan)
            result['sequence']=seq
            need(seq['installed_before']==seq['installed_after']==installed and
                 seq.get('click_acknowledged') is True and seq['after_state_completed'] is True and
                 seq['restoration_qualified'] is True and seq['owned_task']==session.search_owned_task,
                 'ORIGINAL_DESTINATION_CLICK_AND_RESTORATION_REQUIRED')
            result['assessments']=summary(seq,click_plan)
            result['public_destination_action_binding']=session.public_destination_proof
            result['click_acknowledged']=True
        except BaseException as error:
            if hasattr(session,'sequence_observation'):result['failed_click_sequence']=session.sequence_observation
            remember('public_destination_click',error)
    except BaseException as error:
        if hasattr(session,'sequence_observation'):
            result['failed_search_readiness_sequence' if current_phase=='search_readiness' else
                   'failed_search_sequence']=session.sequence_observation
        remember(current_phase,error)
    finally:
        # Even a failed or ambiguous first click never causes a second input.
        # Preserve a verified semantic observation without turning a later
        # Destination failure into whole-sequence success.
        if session.public_search_entry is not None:
            result['public_search_entry']=session.public_search_entry
        result['post_inspection_attempted']=True
        try:
            if hasattr(session,'sequence_observation'):del session.sequence_observation
            seq=session.sequence(post_plan)
            result['post_sequence']=seq
            need(seq['installed_before']==seq['installed_after']==installed and
                 seq['after_state_completed'] is True and seq['restoration_qualified'] is True and
                 seq['foreground_before']==seq['foreground_after'],'ORIGINAL_POST_READ_AND_RESTORATION_REQUIRED')
            result['post_assessments']=summary(seq,post_plan)
            result['post_public_roles']=public_role_counts(qa,session.post_inspection)
            result['post_inspection_completed']=True
        except BaseException as error:
            if hasattr(session,'sequence_observation'):result['failed_post_sequence']=session.sequence_observation
            remember('independent_destination_post_inspection',error)
    if result['error'] is not None:return
    try:
        need(result.get('search_sequence_qualified') is True and result.get('search_click_acknowledged') is True and
             result.get('click_acknowledged') is True and result.get('post_inspection_completed') is True and
             result['search_sequence']['owned_task']==result['sequence']['owned_task']==result['post_sequence']['owned_task'] and
             session.action_requests_admitted=={'search','destination'} and
             result.get('public_search_entry',{}).get('public_search_entry_selection_verified') is True,
             'TWO_EXPLICIT_ACKS_AND_INDEPENDENT_SAME_OWNED_TASK_READ_REQUIRED')
        result['public_destination_observation']=destination_readback(qa,session.post_inspection,session.public_destination_proof)
        result['inspection_completed']=True
        result['destination_click_and_observation_completed']=True
        result['explicit_search_then_destination_completed']=True
    except BaseException as error:remember('public_destination_post_readback',error)

def entry_readback(qa,inspection,before_proof):
    """Qualify only the public Search selection, never hotel results or booking."""
    counts=public_role_counts(qa,inspection)
    rows=public_search_nodes(qa,inspection)
    need(before_proof is not None and before_proof['selected_before'] is False,
         'ACTUAL_PRE_CLICK_PUBLIC_ROLE_PROOF_REQUIRED')
    need(rows and all(type(node.get('selected')) is bool for node,_ in rows),
         'POST_SEARCH_SELECTION_FLAGS_REQUIRED')
    selected=[node for node,_ in rows if node['selected'] is True and node.get('enabled') is True and
              node.get('class_truncated') is False and node.get('resource_id_truncated') is False]
    need(1<=len(selected)<=2,'PUBLIC_SEARCH_SELECTION_NOT_OBSERVED')
    need(inspection['tree_sha256']!=before_proof['tree_sha256'],'POST_SEARCH_SELECTION_TREE_UNCHANGED')
    return {'public_search_entry_selection_verified':True,'selected_public_role_nodes':len(selected),
        'independent_after_click_inspection':True,'tree_sha256':inspection['tree_sha256'],
        'window_sha256':inspection['window_sha256'],'node_count':len(inspection['nodes']),
        'public_role_counts':counts,'hotel_search_results_verified':False,
        'login_or_booking_verified':False,'business_success_verified':False,'whole_app_production_ready':False}

def destination_readback(qa,inspection,before_proof):
    """Keep the observed result separate from an unverified destination page."""
    counts=public_role_counts(qa,inspection)
    need(before_proof is not None and before_proof.get('role')=='destination' and
         before_proof.get('complete_tree_verified') is True and
         before_proof.get('unique_eligible_clickable_ancestor_count')==1,
         'ACTUAL_PRE_CLICK_DESTINATION_PROOF_REQUIRED')
    return {'current_public_destination_click_and_independent_read_verified':True,
        'independent_after_click_inspection':True,'tree_sha256':inspection['tree_sha256'],
        'window_sha256':inspection['window_sha256'],'node_count':len(inspection['nodes']),
        'tree_changed_after_click':inspection['tree_sha256']!=before_proof['tree_sha256'],
        'public_role_counts':counts,'destination_input_semantics_verified':False,
        'hotel_search_results_verified':False,'login_or_booking_verified':False,
        'business_success_verified':False,'whole_app_production_ready':False}

PUBLIC_ROLES={
 'find_hotel':('find a hotel','find hotels','search hotels','search for hotels','book a hotel','find and book','find & book'),
 'search_tab':('search',),'hotels_tab':('hotels',),'book_tab':('book',),'home_tab':('home',),
 'guest_continue':('continue as guest','continue without signing in','browse as guest'),
 'defer_signin':('not now','maybe later','skip'),
 'onboarding_continue':('get started','next','continue'),
 'destination':('destination','where are you going?','city, airport or hotel','search destinations'),
 'dates':('dates','check-in','check out','check-out','check in'),
 'rooms_guests':('rooms','guests','rooms and guests','rooms & guests'),
 'sign_in':('sign in','log in'),'join':('join','join now','create account','create an account'),
 'retry':('retry','try again'),'fixed_network_error':('no internet connection','something went wrong'),
 'find_hotel_zh':('查找酒店','搜索酒店','酒店搜索','预订酒店'),
 'guest_continue_zh':('以游客身份继续','游客访问','暂不登录','跳过'),
 'destination_zh':('目的地','城市、机场或酒店'),
}

PUBLIC_RESOURCES=(
 'android:id/button1','android:id/button2','android:id/button3','android:id/search_src_text',
 'com.ihg.apps.android:id/search_button','com.ihg.apps.android:id/btn_search',
 'com.ihg.apps.android:id/search','com.ihg.apps.android:id/destination',
 'com.ihg.apps.android:id/book','com.ihg.apps.android:id/skip',
 'com.ihg.apps.android:id/continue_as_guest','com.ihg.apps.android:id/bottom_navigation',
)

PUBLIC_CLASSES=('android.widget.TextView','android.widget.Button','android.widget.EditText',
 'android.widget.ImageButton','android.widget.ImageView','android.widget.FrameLayout',
 'android.widget.LinearLayout','android.view.ViewGroup','android.view.View','android.webkit.WebView')

def need(value, reason):
    if not value:raise RuntimeError(reason)

def public_role_counts(qa,inspection):
    qa.inspect_record(inspection)
    nodes=inspection['nodes'];by_path={n['path']:n for n in nodes}
    def eligible(n):
        return (isinstance(n,dict) and n.get('visible') is True and n.get('enabled') is True and
            n.get('password') is False and n.get('class_truncated') is False and n.get('resource_id_truncated') is False)
    def normalized(value):return ' '.join(value.split()).casefold()
    result={}
    for role,variants in PUBLIC_ROLES.items():
        matches=[];via_text=via_description=0;self_targets=set();parent_targets=set();classes={}
        for node in nodes:
            if node.get('visible') is not True or node.get('password') is not False:continue
            fields=[]
            for field in ('text','content_desc'):
                value=node.get(field)
                if isinstance(value,str) and node.get(field+'_truncated') is False and normalized(value) in variants:
                    need(node.get(field+'_sha256')==qa.sha(value.encode()),'PUBLIC_LABEL_DIGEST_MISMATCH')
                    fields.append(field)
            if not fields:continue
            matches.append(node);via_text+='text' in fields;via_description+='content_desc' in fields
            kind=node.get('class');kind=kind if kind in PUBLIC_CLASSES else 'other'
            classes[kind]=classes.get(kind,0)+1
            if eligible(node):
                if node.get('clickable') is True:self_targets.add(node['path'])
                if '/' in node['path']:
                    parent=by_path.get(node['path'].rsplit('/',1)[0])
                    if eligible(parent) and parent.get('clickable') is True:parent_targets.add(parent['path'])
        result[role]={'fixed_public_variants':list(variants),'matching_visible_nonpassword_nodes':len(matches),
            'via_complete_public_text_count':via_text,'via_complete_public_description_count':via_description,
            'eligible_matching_nodes':sum(eligible(n) for n in matches),
            'eligible_clickable_self_count':len(self_targets),
            'eligible_direct_clickable_parent_count':len(parent_targets),
            'distinct_self_or_direct_parent_candidates':len(self_targets|parent_targets),
            'editable_matching_nodes':sum(eligible(n) and n.get('editable') is True for n in matches),
            'known_class_counts':classes,'current_or_future_action_authority':False}
    resources={}
    for resource in PUBLIC_RESOURCES:
        rows=[n for n in nodes if n.get('resource_id')==resource]
        resources[resource]={'matching_nodes':len(rows),'eligible_nodes':sum(eligible(n) for n in rows),
            'eligible_clickable_nodes':sum(eligible(n) and n.get('clickable') is True for n in rows),
            'eligible_editable_nodes':sum(eligible(n) and n.get('editable') is True for n in rows)}
    return {'fixed_public_role_queries':result,'fixed_public_resource_queries':resources,
        'fixed_known_class_counts':{kind:sum(n.get('class')==kind for n in nodes) for kind in PUBLIC_CLASSES},
        'other_class_count':sum(n.get('class') not in PUBLIC_CLASSES for n in nodes),
        'unknown_labels_identifiers_paths_or_coordinates_exported':False,
        'query_catalog_not_asserted_observed':True,'action_selection_performed':False}
