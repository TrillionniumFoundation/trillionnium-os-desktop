"""Counts from complete current inspections, with a 30-second qualification deadline.

Only successful all-zero public catalogs permit a later independent read.
The original Session owns its after-state/finally path even beyond this
qualification deadline. No execution kill, UI input or network operation.
"""
import hashlib
import time

MAX_ROUNDS=3
QUALIFICATION_SECONDS=30.0
ROUND_OFFSETS_SECONDS=(0.0,10.0,20.0)
ERROR_ROLES=('retry','fixed_network_error')
SEMANTIC_RESOURCES=('android:id/search_src_text','com.bestbuy.android:id/search_button',
    'com.bestbuy.android:id/search','com.bestbuy.android:id/search_src_text',
    'com.bestbuy.android:id/country','com.bestbuy.android:id/country_selector',
    'com.bestbuy.android:id/continue_button','com.bestbuy.android:id/btn_continue',
    'com.bestbuy.android:id/skip','com.bestbuy.android:id/continue_as_guest')
PUBLIC_ROLES={'search_tab': ('search',), 'home_tab': ('home',), 'shop_tab': ('shop',), 'browse_tab': ('browse',), 'search_products': ('search products', 'search best buy', 'search bestbuy'), 'country_selector': ('country', 'select country', 'select your country', 'choose your country', 'country/region', 'select your country or region'), 'united_states': ('united states', 'united states of america', 'usa', 'u.s.', 'u.s.a.'), 'canada': ('canada',), 'continue': ('continue',), 'next': ('next',), 'skip': ('skip',), 'get_started': ('get started',), 'guest_continue': ('continue as guest', 'continue without signing in', 'browse as guest'), 'defer_signin': ('not now', 'maybe later'), 'sign_in': ('sign in', 'log in'), 'retry': ('retry', 'try again'), 'fixed_network_error': ('no internet connection', 'something went wrong')}
PUBLIC_RESOURCES=('android:id/button1', 'android:id/button2', 'android:id/button3', 'android:id/search_src_text', 'com.bestbuy.android:id/search_button', 'com.bestbuy.android:id/search', 'com.bestbuy.android:id/search_src_text', 'com.bestbuy.android:id/country', 'com.bestbuy.android:id/country_selector', 'com.bestbuy.android:id/continue_button', 'com.bestbuy.android:id/btn_continue', 'com.bestbuy.android:id/skip', 'com.bestbuy.android:id/continue_as_guest', 'com.bestbuy.android:id/bottom_navigation')
PUBLIC_CLASSES=('android.widget.TextView', 'android.widget.Button', 'android.widget.EditText', 'android.widget.ImageButton', 'android.widget.ImageView', 'android.widget.FrameLayout', 'android.widget.LinearLayout', 'android.view.ViewGroup', 'android.view.View', 'android.webkit.WebView')

def need(value, reason):
    if not value:raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def no_raw_ui(value):
    if isinstance(value,dict):
        need(not ({'nodes','text','content_desc','inspection','screenshot','pixels','raw_tree','raw_ui_tree'}&set(value)),
             'RAW_UI_EXPORT_FORBIDDEN')
        for item in value.values():no_raw_ui(item)
    elif isinstance(value,list):
        for item in value:no_raw_ui(item)

def validated_assessment(qa,assessed,nonce,wire,scope):
    helper=assessed['helper']
    need(assessed.get('held_transport_returned_after_post_guard') is True and
         assessed.get('actual_command_returncode')==0 and assessed.get('actual_instrumentation_finish_code')==-1 and
         helper.get('ok') is True and helper.get('error') is None and helper.get('secondary_errors')==[] and
         helper.get('protocol')==qa.PROTOCOL and helper.get('nonce')==nonce and helper.get('op')=='inspect' and
         helper.get('self_uid')==10155 and helper.get('action_attempted') is False and helper.get('outcome_unknown') is False and
         helper.get('claim_persistence_completed') is True and helper.get('helper_work_completed') is True and
         helper.get('automatic_retry') is False and helper.get('business_success_verified') is False,
         'ACTUAL_SUCCESSFUL_NO_ACTION_INSPECTION_REQUIRED')
    need(sha(qa.canonical(helper))==assessed.get('wire_sha256')==wire,'ACTUAL_CANONICAL_HELPER_WIRE_PIN_REQUIRED')
    expected_request={'protocol':qa.PROTOCOL,'nonce':nonce,'op':'inspect','scope':scope}
    raw_request=qa.validate_request(expected_request)
    need(helper.get('request_sha256')==sha(raw_request) and helper.get('host_scope_attestation')==scope and
         helper.get('target_uid_verified')==qa.UID,'EXACT_RETAINED_REQUEST_SCOPE_REQUIRED')
    restore=helper.get('restoration')
    need(isinstance(restore,dict) and restore.get('service_info_verified') is True and
         restore.get('service_info_captured') is True and restore.get('connection_flags')==1 and
         helper.get('requires_post_termination_state_check') is True,'ORIGINAL_OWN_SERVICE_RESTORATION_REQUIRED')
    inspection=qa.inspect_record(helper['inspection'])
    window=qa.window_observation(helper['window_observation'])
    counters=qa.tree_observations(helper['tree_observations'],'inspect',True)
    need(window['selected_window_id']==inspection['connection_scoped_window_id'] and
         counters[0]['emitted_nodes']==len(inspection['nodes']) and
         counters[0]['serialized_bytes']==len(qa.canonical(inspection)),
         'ORIGINAL_COMPLETE_INSPECTION_AND_WINDOW_COUNTERS_REQUIRED')
    return helper,inspection,window,counters

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

def decision(counts):
    """No target is selected; generic buttons and error labels never grant readiness."""
    roles=counts['fixed_public_role_queries']
    resources=counts['fixed_public_resource_queries']
    need(set(roles)==set(PUBLIC_ROLES) and set(resources)==set(PUBLIC_RESOURCES),
         'EXACT_PUBLIC_CATALOG_COUNTS_REQUIRED')
    all_zero=all(row['matching_visible_nonpassword_nodes']==0 for row in roles.values()) and all(
        row['matching_nodes']==0 for row in resources.values())
    errors=any(roles[name]['matching_visible_nonpassword_nodes']>0 for name in ERROR_ROLES)
    actionable_roles=[name for name in PUBLIC_ROLES if name not in ERROR_ROLES and
        roles[name]['distinct_self_or_direct_parent_candidates']>0]
    # An editable flag alone is not used as proof of an actionable public entry.
    actionable_resources=[name for name in SEMANTIC_RESOURCES if resources[name]['eligible_clickable_nodes']>0]
    candidate=bool(not errors and (actionable_roles or actionable_resources))
    reason=('ACTIONABLE_PUBLIC_ENTRY_OR_ONBOARDING' if candidate else
        'PUBLIC_ERROR_OR_RETRY_PRESENT' if errors else
        'COMPLETE_PUBLIC_CATALOG_ALL_ZERO' if all_zero else
        'PUBLIC_CATALOG_NONZERO_WITHOUT_ACTIONABLE_ENTRY')
    return {'catalog_all_zero':all_zero,'public_error_or_retry_present':errors,
        'public_entry_candidate_present':candidate,'reason':reason,
        'actionable_fixed_public_roles':actionable_roles,
        'actionable_fixed_public_resources':actionable_resources,
        'target_selected':False,'input_action_authority':False,
        'business_success_verified':False,'whole_app_production_ready':False}


def qualify_current(qa,assessed,sequence,plan,metadata,owned_task,installed):
    """Rebind the retained current assessment to its just-completed original Session."""
    need(sequence.get('owned_task')==owned_task and
         sequence.get('installed_before')==sequence.get('installed_after')==installed and
         sequence.get('error') is None and sequence.get('secondary_errors')==[] and
         sequence.get('foreground_before')==sequence.get('foreground_after') and
         sequence.get('after_state_completed') is True and sequence.get('restoration_qualified') is True and
         sequence.get('post_state_matches_before') is True and
         sequence['post_termination_state']['nonce']==plan['nonces']['after'] and
         sequence['post_termination_state']['helper_uid']==10155 and
         sequence['post_termination_state']['ui_automation_connected'] is False,
         'CURRENT_COMPLETE_ORIGINAL_SESSION_SAME_TASK_REQUIRED')
    need(set(metadata)=={'before','inspect','after'} and all(
         metadata[name]['nonce']==plan['nonces'][name] for name in metadata),
         'CURRENT_ROUND_ASSESSMENT_NONCES_REQUIRED')
    wire=sequence['inspection_wire_sha256']
    helper,inspection,window,counters=validated_assessment(qa,assessed,
        plan['nonces']['inspect'],wire,sequence['foreground_after'])
    summary=metadata['inspect']
    restore=sequence['accessibility_restoration']
    need(helper['accessibility_state_before_connection']==restore['state_before']==restore['state_after']==
         sequence['post_termination_state']['state'] and
         restore['wire_sha256']==[metadata[name]['wire_sha256'] for name in ('before','inspect','after')] and
         inspection['tree_sha256']==summary['tree_sha256'] and
         inspection['window_sha256']==summary['window_sha256'] and
         len(inspection['nodes'])==summary['node_count'] and
         window==summary['window_observation'] and counters==summary['tree_observations'] and
         assessed['recorder_command_result_sha256']==summary['recorder_command_result_sha256'],
         'CURRENT_ASSESSMENT_TREE_WIRE_STATE_AND_COMMAND_BINDING_REQUIRED')
    counts=public_role_counts(qa,inspection)
    public=decision(counts)
    row={'sequence':sequence,'assessments':metadata,'public_role_counts':counts,
         'public_decision':public,'complete_current_assessment_verified':True,
         'raw_UI_tree_private_only':True,'business_success_verified':False,
         'whole_app_production_ready':False}
    no_raw_ui(row)
    return row


def observation_record():
    return {'maximum_rounds':MAX_ROUNDS,'qualification_window_seconds':QUALIFICATION_SECONDS,
        'round_offsets_seconds':list(ROUND_OFFSETS_SECONDS),'rounds':[],
        'rounds_started':0,'completed_rounds':0,'public_entry_candidate_present':False,
        'qualification_deadline_is_not_execution_kill':True,
        'original_after_state_and_finally_retained':True,
        'continuation_requires_successful_complete_all_31_public_queries_zero':True,
        'new_read_after_failure':False,'automatic_retry':False,
        'business_success_verified':False,'whole_app_production_ready':False}


def observe(plans,collect,guard,result,*,clock=time.monotonic,sleep=time.sleep):
    """At most three distinct original Sessions; exceptions leave all prior rows intact."""
    need(isinstance(plans,list) and len(plans)==MAX_ROUNDS and
         all(p.get('operation')=='inspect' and set(p['nonces'])=={'before','inspect','after'} for p in plans),
         'THREE_FIXED_INSPECT_PLANS_REQUIRED')
    nonces=[n for p in plans for n in p['nonces'].values()]
    need(len(nonces)==len(set(nonces))==9,'NINE_DISTINCT_INSPECTION_NONCES_REQUIRED')
    need(result==observation_record(),'FRESH_READINESS_OBSERVATION_REQUIRED')
    started=clock();deadline=started+QUALIFICATION_SECONDS
    result['qualification_started_monotonic']=started
    result['qualification_deadline_monotonic']=deadline
    try:
        for index,plan in enumerate(plans):
            if index:
                need(result['rounds'][-1]['public_decision']['catalog_all_zero'] is True,
                     'ONLY_SUCCESSFUL_ALL_ZERO_READ_CAN_CONTINUE')
                delay=min(started+ROUND_OFFSETS_SECONDS[index],deadline)-clock()
                if delay>0:
                    guard();sleep(delay);guard()
            if clock()>=deadline:
                result['stop_reason']='QUALIFICATION_DEADLINE_REACHED';break
            guard()
            if clock()>=deadline:
                result['stop_reason']='QUALIFICATION_DEADLINE_REACHED';break
            result['rounds_started']=index+1
            began=clock()
            # No retry or catch/re-enter around an original Session call.
            row=collect(plan,index)
            need(row.get('complete_current_assessment_verified') is True,
                 'COMPLETE_CURRENT_ROUND_REQUIRED')
            no_raw_ui(row)
            ended=clock()
            row['round']=index+1
            row['began_seconds_after_qualification_start']=began-started
            row['completed_seconds_after_qualification_start']=ended-started
            row['completed_within_qualification_window']=ended<=deadline
            result['rounds'].append(row);result['completed_rounds']=len(result['rounds'])
            if ended>deadline:
                result['stop_reason']='COMPLETED_AFTER_QUALIFICATION_DEADLINE';break
            if row['public_decision']['public_entry_candidate_present'] is True:
                result['public_entry_candidate_present']=True
                result['stop_reason']='ACTIONABLE_PUBLIC_ENTRY_OBSERVED';break
            if row['public_decision']['catalog_all_zero'] is not True:
                result['stop_reason']=row['public_decision']['reason'];break
        else:
            result['stop_reason']='THREE_COMPLETE_PUBLIC_CATALOGS_ALL_ZERO'
        need(result['completed_rounds']>0,'NO_COMPLETE_READINESS_OBSERVATION')
        return result
    except BaseException as error:
        result['stop_reason']='READ_OR_QUALIFICATION_FAILED_NO_RETRY'
        result['public_entry_candidate_present']=False
        result['error']={'type':type(error).__name__,'message':str(error)}
        raise
    finally:
        result['elapsed_seconds']=clock()-started
