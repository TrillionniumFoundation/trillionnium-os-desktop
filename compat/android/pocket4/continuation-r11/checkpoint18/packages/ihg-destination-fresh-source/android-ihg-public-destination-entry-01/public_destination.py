"""One fresh public Destination ancestor click. No standalone action or text input."""
import copy
import re

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

def make_session(adapter,flow,recorder,qa,proof,helper_uid,click_plan,post_plan):
    """Keep the original Session.sequence/finally and full helper action guards."""
    class PublicDestinationSession(adapter.Session):
        def __init__(self):
            super().__init__(flow,recorder,qa,proof,helper_uid)
            self.public_destination_proof=None
            self._action_binding=None
            self.post_inspection=None
            self.action_request_admitted=False

        def instrument(self,request):
            if request['op']=='click':
                need(self._action_binding is not None and not self.action_request_admitted,
                     'ONE_FRESH_PUBLIC_DESTINATION_REQUEST_REQUIRED')
                need(request==self._action_binding,'EXACT_FRESH_PUBLIC_DESTINATION_NODE_REQUEST_REQUIRED')
                self.action_request_admitted=True
            assessed=super().instrument(request)
            if request['nonce']==click_plan['nonces']['inspect']:
                need(request['op']=='inspect' and self.public_destination_proof is None,
                     'ONE_CURRENT_PUBLIC_DESTINATION_INSPECTION_REQUIRED')
                selector,node,safe=destination_selector(qa,assessed['helper']['inspection'])
                click_plan['selector']=selector
                adapter.validate_plan(click_plan,qa)
                self._action_binding={'protocol':qa.PROTOCOL,'nonce':click_plan['nonces']['action'],
                    'op':'click','scope':copy.deepcopy(request['scope']),
                    'inspection_nonce':request['nonce'],'inspection_sha256':assessed['wire_sha256'],**node}
                self.public_destination_proof={**safe,'inspection_nonce':request['nonce'],
                    'inspection_wire_sha256':assessed['wire_sha256']}
            elif request['nonce']==post_plan['nonces']['inspect']:
                need(request['op']=='inspect' and self.post_inspection is None,
                     'ONE_INDEPENDENT_POST_INSPECTION_REQUIRED')
                self.post_inspection=assessed['helper']['inspection']
            return assessed
    return PublicDestinationSession()

def run_sequences(qa,session,installed,click_plan,post_plan,result,summary,remember):
    """One Destination action; always retain an independent post inspection."""
    result['click_sequence_started']=True
    try:
        if hasattr(session,'sequence_observation'):del session.sequence_observation
        seq=session.sequence(click_plan)
        result['sequence']=seq
        need(seq['installed_before']==seq['installed_after']==installed and
             seq.get('click_acknowledged') is True and seq['after_state_completed'] is True and
             seq['restoration_qualified'] is True,'ORIGINAL_DESTINATION_CLICK_AND_RESTORATION_REQUIRED')
        result['assessments']=summary(seq,click_plan)
        result['public_destination_action_binding']=session.public_destination_proof
        result['click_acknowledged']=True
    except BaseException as error:
        if hasattr(session,'sequence_observation'):result['failed_click_sequence']=session.sequence_observation
        remember('public_destination_click',error)
    finally:
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
        need(result.get('click_acknowledged') is True and result.get('post_inspection_completed') is True and
             result['sequence']['owned_task']==result['post_sequence']['owned_task'],
             'ACK_AND_INDEPENDENT_SAME_OWNED_TASK_READ_REQUIRED')
        result['public_destination_observation']=destination_readback(qa,session.post_inspection,session.public_destination_proof)
        result['inspection_completed']=True
        result['destination_click_and_observation_completed']=True
    except BaseException as error:remember('public_destination_post_readback',error)

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
