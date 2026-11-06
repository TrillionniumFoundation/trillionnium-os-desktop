"""Fresh public Search role gate for one owned IHG entry click. No standalone action."""
import copy


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


def make_session(adapter,flow,recorder,qa,proof,helper_uid,click_plan,post_plan):
    """Keep original Session.sequence/finally and helper full-freshness checks."""
    class PublicSearchSession(adapter.Session):
        def __init__(self):
            super().__init__(flow,recorder,qa,proof,helper_uid)
            self.public_search_proof=None
            self._action_binding=None
            self.post_inspection=None
            self.action_request_admitted=False

        def instrument(self,request):
            if request['op']=='click':
                need(self._action_binding is not None and not self.action_request_admitted,
                     'ONE_FRESH_PUBLIC_SEARCH_REQUEST_REQUIRED')
                need(request==self._action_binding,'EXACT_FRESH_PUBLIC_SEARCH_NODE_REQUEST_REQUIRED')
                self.action_request_admitted=True
            assessed=super().instrument(request)
            if request['nonce']==click_plan['nonces']['inspect']:
                need(request['op']=='inspect' and self.public_search_proof is None,
                     'ONE_CURRENT_PUBLIC_SEARCH_INSPECTION_REQUIRED')
                selector,node,safe=search_selector(qa,assessed['helper']['inspection'])
                click_plan['selector']=selector
                adapter.validate_plan(click_plan,qa)
                self._action_binding={'protocol':qa.PROTOCOL,'nonce':click_plan['nonces']['action'],
                    'op':'click','scope':copy.deepcopy(request['scope']),
                    'inspection_nonce':request['nonce'],'inspection_sha256':assessed['wire_sha256'],**node}
                self.public_search_proof={**safe,'inspection_nonce':request['nonce'],
                    'inspection_wire_sha256':assessed['wire_sha256']}
            elif request['nonce']==post_plan['nonces']['inspect']:
                need(request['op']=='inspect' and self.post_inspection is None,
                     'ONE_INDEPENDENT_POST_INSPECTION_REQUIRED')
                self.post_inspection=assessed['helper']['inspection']
            return assessed
    return PublicSearchSession()


def run_sequences(qa,session,installed,click_plan,post_plan,result,summary,remember):
    """One original click sequence and an independent read even after failure."""
    result['click_sequence_started']=True
    try:
        if hasattr(session,'sequence_observation'):del session.sequence_observation
        seq=session.sequence(click_plan)
        result['sequence']=seq
        need(seq['installed_before']==seq['installed_after']==installed and
             seq.get('click_acknowledged') is True and seq['after_state_completed'] is True and
             seq['restoration_qualified'] is True,'ORIGINAL_SEARCH_CLICK_AND_RESTORATION_REQUIRED')
        result['assessments']=summary(seq,click_plan)
        result['public_search_action_binding']=session.public_search_proof
        result['click_acknowledged']=True
    except BaseException as error:
        if hasattr(session,'sequence_observation'):result['failed_click_sequence']=session.sequence_observation
        remember('public_search_click',error)
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
            remember('independent_search_post_inspection',error)
    if result['error'] is not None:return
    try:
        need(result.get('click_acknowledged') is True and result.get('post_inspection_completed') is True and
             result['sequence']['owned_task']==result['post_sequence']['owned_task'],
             'ACK_AND_INDEPENDENT_SAME_OWNED_TASK_READ_REQUIRED')
        result['public_search_entry']=entry_readback(qa,session.post_inspection,session.public_search_proof)
        result['inspection_completed']=True
        result['public_search_entry_completed']=True
    except BaseException as error:remember('public_search_entry_readback',error)


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
