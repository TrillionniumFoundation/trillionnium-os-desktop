"""One observed public course-card click; unchanged Session/Java action path."""
import json
import time

TITLE_SHA='7ff99f77d6b59f394c4c6c0ca167aded470663d4cef66215fcce841ed549afba'
UPLOADER_SHA='3355707b07511199c7d280b9a77510b5e9b8698c7c7e4aedcf938805a3822d64'
DURATION_SHA='137ed61cdad38eb26c79124e18cb04925f8ac831f042169328a35d25520db3fa'
CARD_SELECTOR={'class':'android.view.ViewGroup'}
VIDEO_PLAN = {'schema': 1, 'operation': 'click', 'selector': {'class': 'android.view.ViewGroup'}, 'nonces': {'before': 'f32a8c1b150870ed8912c8e5347317a3', 'inspect': 'ca1375584c9a24568c1ededaa0fea3c9', 'action': '3d12bbf7d777dab524f9a2a866e37d09', 'after': '09dc7b6ceb72ca5fb97144ee6a073e94'}}
VIDEO_STABILITY_PLANS = [{'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'e39be981295e5cc680cdb034c202b252', 'inspect': '2046cdac099b5b81993d7a306c98d86d', 'after': '7c1dd6ef639ab87f6098d2401112a56e'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'a07e81be7bbd8afce9fcb8f96fae6b5a', 'inspect': 'b339ff3ac8252f368fb3720eab9dec0d', 'after': 'ac11aa7ecb93cce39bfd6fb8c0cc2f23'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '71f9fea2cda313827d1634aec056c05c', 'inspect': '9fc36e99796b08cf7c7f14394b635c61', 'after': '0412eb65a578d5e3cfb1493feba2eaf4'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '70875cc8898f56f8cb63248b379746f5', 'inspect': '9c86c1d8a9c4ba2a6ab7411c8f261b1f', 'after': '55e2e193f51d741f5b1316172d58dc6d'}}]
VIDEO_POST_PLANS = [{'schema': 1, 'operation': 'inspect', 'nonces': {'before': '9f895166a35e2b642a3001f23f69f505', 'inspect': '6bd040f028e1116eba42998b479b1115', 'after': 'a71086a0635d69534fb4161cb93f28b5'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '610700ee5a63a7e94d65b09c29d0ce06', 'inspect': 'c606b168892b6e25c543f2a76af98b06', 'after': '87f5c7c1f49caadea76543ee211eb993'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'dd2d11be149398a4760b2d343d23336c', 'inspect': '715b97bc50de868067a9dc5b60aca8fb', 'after': '1844f4f866cbf73a80615794125a0f42'}}]

CONTENT_READY_SECONDS=12
CONTENT_READY_PLANS=[{'schema': 1, 'operation': 'inspect', 'nonces': {'before': '818264c963ebda27cb8978d5900a4446', 'inspect': '10f0eda9bc807dc462bb73a481e6fa20', 'after': 'e60c13d6f88e680d41c979fcf63345d2'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'c0372b879d47bf96695d3ef2a4a8f42d', 'inspect': 'e05f9c76f24fa060bee63c758d0cffc0', 'after': 'f03c55b23afa9921c9516d1c8710a246'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'd24d23ef253c6814400630d84a80c169', 'inspect': '82cda757c998cbacb658dd09da08eaa9', 'after': '0b00d8d30915c665de5755f042ea954a'}}]


def validate(adapter,qa,base_nonces):
    plans=[VIDEO_PLAN,*VIDEO_STABILITY_PLANS,*VIDEO_POST_PLANS,*CONTENT_READY_PLANS]
    for plan in plans:adapter.validate_plan(plan,qa)
    values=[n for plan in plans for n in plan['nonces'].values()]
    qa.require(len(values)==len(set(values))==34 and not set(values)&set(base_nonces),
        'FRESH_DISTINCT_VIDEO_NONCES_REQUIRED')
    qa.require(VIDEO_PLAN['selector']==CARD_SELECTOR and VIDEO_PLAN['operation']=='click' and
        len(VIDEO_STABILITY_PLANS)==4 and len(VIDEO_POST_PLANS)==3 and len(CONTENT_READY_PLANS)==3 and
        all(p['operation']=='inspect' for p in [*VIDEO_STABILITY_PLANS,*VIDEO_POST_PLANS,*CONTENT_READY_PLANS]),
        'ONLY_ONE_OBSERVED_COURSE_CLICK_ALLOWED')


def select_course(base,qa,inspection,scope):
    """Select a current direct parent by three exact UTF-8 content digests.

    No historical path, node hash, rank or coordinate participates in selection.
    The class-only plan cannot authorize a click without this additional gate.
    """
    content=base.results_content_evidence(qa,inspection,scope)
    base.require(content['container_content_observed'],'CURRENT_RESULTS_CONTENT_REQUIRED_FOR_VIDEO')
    nodes=inspection['nodes'];by_path={n['path']:n for n in nodes}
    def matches(node,resource,digest):
        return (node.get('resource_id')==resource and node.get('resource_id_truncated') is False and
            node.get('class')=='android.widget.TextView' and node.get('class_truncated') is False and
            node.get('visible') is True and node.get('enabled') is True and node.get('password') is False and
            isinstance(node.get('text'),str) and node.get('text_truncated') is False and
            node.get('text_sha256')==digest and base.sha(node['text'].encode('utf-8'))==digest)
    titles=[n for n in nodes if matches(n,'tv.danmaku.bili:id/title',TITLE_SHA)]
    base.require(len(titles)==1,'EXACT_ORIGINAL_COURSE_TITLE_NOT_UNIQUE')
    title=titles[0];base.require('/' in title['path'],'DIRECT_COURSE_CARD_PARENT_REQUIRED')
    card=by_path.get(title['path'].rsplit('/',1)[0])
    base.require(isinstance(card,dict) and card.get('class')=='android.view.ViewGroup' and
        card.get('class_truncated') is False and card.get('resource_id')=='' and
        card.get('resource_id_truncated') is False and card.get('clickable') is True and
        card.get('visible') is True and card.get('enabled') is True and card.get('password') is False,
        'OBSERVED_ELIGIBLE_DIRECT_COURSE_CARD_REQUIRED')
    pagers=[n for n in nodes if n.get('resource_id')=='tv.danmaku.bili:id/pager' and n.get('visible') is True]
    base.require(len(pagers)==1 and card['path'].startswith(pagers[0]['path']+'/'),
        'COURSE_CARD_MUST_BELONG_TO_CURRENT_RESULT_PAGER')
    children=[n for n in nodes if n['path'].startswith(card['path']+'/')]
    users=[n for n in children if matches(n,'tv.danmaku.bili:id/upuser',UPLOADER_SHA)]
    durations=[n for n in children if matches(n,'tv.danmaku.bili:id/duration',DURATION_SHA)]
    base.require(len(users)==len(durations)==1,'EXACT_SAME_CARD_UPLOADER_AND_DURATION_REQUIRED')
    target={'node_path':card['path'],'node_sha256':card['node_sha256']}
    proof={'title_text_sha256':TITLE_SHA,'uploader_text_sha256':UPLOADER_SHA,'duration_text_sha256':DURATION_SHA,
        'title_resource_id':'tv.danmaku.bili:id/title','title_node_sha256':title['node_sha256'],
        'card_node_sha256':card['node_sha256'],'card_class':'android.view.ViewGroup','direct_parent_distance':1,
        'current_tree_sha256':inspection['tree_sha256'],'current_window_sha256':inspection['window_sha256'],
        'unique_title_and_same_card_identity':True,'historical_path_or_rank_used':False,
        'public_query_marker_verified':True,'raw_title_uploader_or_other_UI_text_exported':False}
    return target,proof


def inspected_course(base,qa,flow,sequence,summaries):
    scope=sequence['foreground_after']
    base.require(scope==sequence['foreground_before'],'VIDEO_READ_FOREGROUND_CHANGED')
    row=summaries['inspect']
    raw=base.read(flow.step/(row['nonce']+'.assessment.json'),1048576,row['assessment_sha256'],row['assessment_bytes'])
    value=json.loads(raw);helper=value['helper']
    base.require(value.get('actual_command_returncode')==0 and value.get('actual_instrumentation_finish_code')==-1 and
        helper.get('ok') is True and helper.get('error') is None and helper.get('secondary_errors')==[] and
        helper.get('protocol')==qa.PROTOCOL and helper['host_scope_attestation']==scope and
        helper['self_uid']==base.UID and helper['nonce']==row['nonce'] and helper['op']=='inspect' and
        value['wire_sha256']==row['wire_sha256']==base.sha(qa.canonical(helper)) and
        value['held_transport_returned_after_post_guard'] is True,'LIVE_COURSE_INSPECTION_RECEIPT_REQUIRED')
    return select_course(base,qa,helper['inspection'],scope)[1]


def stable_course(base,prior,qa,flow,session,installed,result):
    began=time.monotonic();previous=None
    record={'maximum_sequences':4,'deadline_seconds':12,'observations':[],'qualified':False,
        'failed_reads_retried':False,'click_retried':False}
    result['video_stability']=record
    for index,plan in enumerate(VIDEO_STABILITY_PLANS,1):
        base.require(time.monotonic()-began<=12,'COURSE_STABILITY_DEADLINE')
        sequence=session.sequence(json.loads(json.dumps(plan)))
        base.require(sequence['installed_before']==sequence['installed_after']==installed and
            sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True,
            'COURSE_READ_IDENTITY_AND_RESTORATION_REQUIRED')
        summaries=base.assessment_summary(prior,qa,flow.step,sequence,plan)
        proof=inspected_course(base,qa,flow,sequence,summaries)
        key={'tree_sha256':proof['current_tree_sha256'],'window_sha256':proof['current_window_sha256'],
            'foreground':sequence['foreground_after'],'accessibility_state':sequence['accessibility_restoration']['state_after']}
        record['observations'].append({'sequence':index,'elapsed_ms':int((time.monotonic()-began)*1000),
            'complete_key':key,'selection':proof,'assessments':summaries})
        base.require(time.monotonic()-began<=12,'COURSE_STABILITY_DEADLINE')
        if key==previous:
            record['qualified']=True;record['matching_sequences']=[index-1,index]
            return
        previous=key
    raise RuntimeError('COURSE_TREE_NOT_STABLE_IN_BOUNDED_READS')


def course_sequence(base,qa,session,result):
    base.require(session.qa is qa,'ORIGINAL_VIDEO_SESSION_CONTRACT_REQUIRED')
    class CourseContract:
        def __getattr__(self,name):return getattr(qa,name)
        def select_unique_clickable(self,inspection,selector):
            base.require(selector==CARD_SELECTOR,'ONLY_FIXED_COURSE_SELECTOR')
            scope=session.sequence_observation['foreground_before']
            target,proof=select_course(base,qa,inspection,scope)
            result['video_action_bound_selection']=proof
            return target
    original_foreground=session.foreground
    had_foreground='foreground' in session.__dict__
    old_foreground=session.__dict__.get('foreground')
    post_calls=0
    def post_foreground():
        nonlocal post_calls
        observed=session.sequence_observation
        if not (observed.get('click_acknowledged') is True and
                observed.get('after_state_completed') is True and
                observed.get('restoration_qualified') is True and
                observed.get('error') is None and observed.get('secondary_errors')==[]):
            return original_foreground()
        base.require(post_calls==0,'ONLY_ONE_ACKNOWLEDGED_POST_FOREGROUND_CALL')
        post_calls+=1
        return await_post_foreground(base,session,original_foreground,result)
    session.qa=CourseContract();session.foreground=post_foreground
    try:return session.sequence(json.loads(json.dumps(VIDEO_PLAN)))
    finally:
        session.qa=qa
        if had_foreground:session.foreground=old_foreground
        else:del session.foreground


def await_post_foreground(base,session,original_foreground,result):
    """Only a successful dump containing one exact null focus can be reread.

    This runs after this sequence's acknowledged click AND independent state
    restoration. It never retries an action, failed transport or unknown focus
    shape. The original Session.foreground/parser still authorize every result.
    Raw dumps remain private in memory and are discarded, as in the original.
    """
    flow=session.flow;began=time.monotonic();first_null=None
    record={'maximum_samples':6,'deadline_seconds':3,'samples':[],
        'qualified':False,'read_only':True,'action_replayed':False,
        'only_exact_single_null_may_wait':True,'raw_window_text_exported':False}
    result['video_post_foreground_transition']=record
    for index in range(1,7):
        remaining=3-(time.monotonic()-began)
        if remaining<=0:
            if first_null is not None:
                first_null.add_note('POST_FOREGROUND_READ_DEADLINE_EXHAUSTED');raise first_null
            raise RuntimeError('POST_FOREGROUND_READ_DEADLINE_EXHAUSTED')
        old_android=flow.android;had_android='android' in flow.__dict__
        old_android_attr=flow.__dict__.get('android');census=None;calls=0
        def capture(argv,timeout=30,**kwargs):
            nonlocal calls,census
            base.require(calls==0 and argv==['/system/bin/dumpsys','window','displays'] and
                timeout==15 and kwargs=={'mutation':False},'ONLY_ORIGINAL_READ_ONLY_FOREGROUND_COMMAND')
            calls+=1
            raw=old_android(argv,min(timeout,remaining),**kwargs)
            # Reaching here requires the original held transport's successful
            # return and post guard. No partial or failed command is sampled.
            base.require(isinstance(raw,bytes) and len(raw)<=262144,'POST_FOREGROUND_OUTPUT_BOUND')
            lines=[line.strip()for line in raw.decode('utf-8','strict').splitlines()if 'mCurrentFocus='in line]
            census={'raw_bytes':len(raw),'raw_sha256':base.sha(raw),'focus_line_count':len(lines),
                'exact_single_null':lines==['mCurrentFocus=null'],'successful_held_return':True}
            return raw
        flow.android=capture;value=None;error=None
        try:value=original_foreground()
        except BaseException as caught:error=caught
        finally:
            if had_android:flow.android=old_android_attr
            else:del flow.android
        elapsed=int((time.monotonic()-began)*1000)
        sample={'sample':index,'elapsed_ms':elapsed,'command_count':calls,'census':census,
            'error':None if error is None else {'type':type(error).__name__,'message':str(error)}}
        record['samples'].append(sample)
        if error is None:
            base.require(calls==1 and census is not None,'ONE_ORIGINAL_FOREGROUND_READ_REQUIRED')
            if time.monotonic()-began>3:
                raise RuntimeError('POST_FOREGROUND_SCOPE_OBSERVED_AFTER_DEADLINE')
            record['qualified']=True;record['scope']=value
            return value
        allowed=(type(error).__name__=='ControlError' and str(error)=='FOREGROUND_UNVERIFIED' and
            calls==1 and census is not None and census['exact_single_null'] is True)
        if not allowed:raise error
        if first_null is None:first_null=error
        if index==6 or time.monotonic()-began>=3:
            first_null.add_note('BOUNDED_NULL_FOREGROUND_OBSERVATION_EXHAUSTED');raise first_null


def waiting_structure(qa, inspection, host_scope):
    """Exact original non-metadata checks; authorizes no input or player proof."""
    inspect_record = qa.inspect_record
    scope = qa.scope
    require = qa.require
    PACKAGE = qa.PACKAGE
    REVEAL_ACTIVITY = qa.REVEAL_ACTIVITY
    reveal_rect = qa.reveal_rect
    sha = qa.sha
    canonical = qa.canonical
    require_hidden = True
    inspect_record(inspection)
    scope(host_scope)
    require(host_scope['activity'] == REVEAL_ACTIVITY, 'REVEAL_EXACT_COURSE_ACTIVITY')
    nodes = inspection['nodes']
    window = inspection['window']

    def eligible(n):
        return n.get('visible') is True and n.get('enabled') is True and (n.get('password') is False) and (n.get('class_truncated') is False) and (n.get('resource_id_truncated') is False)

    def one(resource, kind, text_hash=None):
        found = [n for n in nodes if n.get('resource_id') == resource and n.get('class') == kind and eligible(n) and (text_hash is None or (n.get('text_truncated') is False and isinstance(n.get('text'), str) and (n.get('text_sha256') == text_hash == sha(n['text'].encode()))))]
        require(len(found) == 1, 'REVEAL_UNIQUE_PLAYER_ROLE_REQUIRED')
        return found[0]

    def under(n, parent):
        return n['path'].startswith(parent['path'] + '/')

    def inside(a, b):
        reveal_rect(a)
        reveal_rect(b)
        return b[0] <= a[0] and a[2] <= b[2] and (b[1] <= a[1]) and (a[3] <= b[3])
    area = one(PACKAGE + ':id/video_area', 'android.widget.FrameLayout')
    container = one(PACKAGE + ':id/video_container', 'android.widget.FrameLayout')
    overlay = one(PACKAGE + ':id/video_area_float_layer_container', 'android.widget.FrameLayout')
    toolbar = one(PACKAGE + ':id/collapsing_toolbar', 'android.widget.FrameLayout')
    full = reveal_rect(area['bounds'])
    crop = reveal_rect(overlay['bounds'])
    require(full == container['bounds'] and crop == toolbar['bounds'] and (crop != full) and inside(crop, full) and inside(full, window['bounds']) and under(container, area) and under(overlay, area), 'REVEAL_ABSOLUTE_PLAYER_GEOMETRY')
    surfaces = [n for n in nodes if n.get('class') in ('android.view.SurfaceView', 'android.view.TextureView')]
    require(len(surfaces) == 2 and all((n['class'] == 'android.view.SurfaceView' and eligible(n) and (n['resource_id'] == '') and under(n, container) and (not under(n, overlay)) and (not under(n, toolbar)) for n in surfaces)), 'REVEAL_EXACT_TWO_SURFACE_ROLES')
    area_rows = [n for n in surfaces if n['bounds'] == full]
    crop_rows = [n for n in surfaces if n['bounds'] == crop]
    require(len(area_rows) == len(crop_rows) == 1, 'REVEAL_EXACT_TWO_SURFACE_ROLES')
    for n in nodes:
        if under(n, container) and n['visible'] is True:
            require(n['password'] is False, 'REVEAL_PLAYER_PASSWORD_DESCENDANT')
            text = n['text']
            require(isinstance(text, str) and (not text or n['text_truncated'] is False), 'REVEAL_PLAYER_TEXT_COMPLETENESS')
            require(not text.startswith('Buffering...'), 'REVEAL_BUFFERING_PLAYER_REJECTED')
    if require_hidden:
        controls = one(PACKAGE + ':id/control_container', 'android.widget.FrameLayout')
        require(under(controls, container) and type(controls['child_count']) is int and (controls['child_count'] == 0) and (controls['bounds'] == crop), 'REVEAL_CURRENT_HIDDEN_CONTROL_CONTAINER')
        require(all((n.get('clickable') is False and n['class'] != 'android.widget.SeekBar' for n in nodes if under(n, area) and n['visible'] is True and (n['enabled'] is True))), 'REVEAL_ALREADY_INTERACTIVE_PLAYER_REJECTED')
    by_path = {n['path']: n for n in nodes}
    parents = set()
    render = []
    for role, node in (('area-sized', area_rows[0]), ('crop-sized', crop_rows[0])):
        require('/' in node['path'], 'REVEAL_SURFACE_PARENT_PATH')
        parent_path = node['path'].rsplit('/', 1)[0]
        parent = by_path.get(parent_path)
        require(parent is not None and eligible(parent) and under(parent, container) and (parent['class'] == 'android.widget.FrameLayout') and (parent['resource_id'] == '') and (parent['bounds'] == node['bounds']) and (parent_path not in parents), 'REVEAL_EXACT_DISTINCT_SURFACE_PARENTS')
        parents.add(parent_path)
        render.append({'role': role, 'node_sha256': node['node_sha256'], 'parent_node_sha256': parent['node_sha256'], 'bounds': node['bounds']})
    return True


def content_status(qa,inspection,scope):
    """Original full proof, or the narrowly observed absent-metadata shape.

    A waitable shape authorizes only another independent no-action inspection.
    It never creates a player proof or substitutes for the reveal admission.
    """
    try:
        proof=qa.player_reveal_scope(inspection,scope,True)
    except qa.ProtocolError as error:
        if str(error)!='REVEAL_UNIQUE_PLAYER_ROLE_REQUIRED':raise
        nodes=inspection['nodes'];counts={};missing=[]
        qa.require(all(n.get('class_truncated') is False and n.get('resource_id_truncated') is False for n in nodes),
            'CONTENT_READY_ROLE_FIELDS_MUST_BE_COMPLETE')
        def eligible(n,kind):
            return (n.get('class')==kind and n.get('visible') is True and n.get('enabled') is True and
                n.get('password') is False and n.get('class_truncated') is False and
                n.get('resource_id_truncated') is False)
        def rows(resource):return [n for n in nodes if n.get('resource_id')==qa.PACKAGE+':id/'+resource]
        for resource,digest in (('title',qa.REVEAL_TITLE),('author_name',qa.REVEAL_AUTHOR)):
            found=rows(resource);counts[resource]=len(found)
            qa.require(len(found)<=1 and all(eligible(n,'android.widget.TextView') and
                n.get('text_truncated') is False and isinstance(n.get('text'),str) and
                n.get('text_sha256')==digest==qa.sha(n['text'].encode()) for n in found),
                'CONTENT_READY_PRESENT_METADATA_MUST_MATCH')
            if not found:missing.append(resource)
        qa.require(bool(missing),'CONTENT_READY_ONLY_ABSENT_METADATA_MAY_WAIT')
        for resource in ('video_area','video_container','video_area_float_layer_container',
                         'collapsing_toolbar','control_container'):
            found=rows(resource);counts[resource]=len(found)
            qa.require(len(found)==1 and eligible(found[0],'android.widget.FrameLayout'),
                'CONTENT_READY_FIXED_PLAYER_ROLE_CHANGED')
        waiting_structure(qa,inspection,scope)
        return {'ready':False,'wait_permitted':True,'missing_metadata_roles':missing,
            'fixed_resource_counts':counts,'surface_view_count':2,'texture_view_count':0,
            'original_nonmetadata_structure_qualified':True,
            'original_predicate_error':{'type':type(error).__name__,'message':str(error)}}
    return {'ready':True,'wait_permitted':False,'original_full_player_proof':proof}


def content_observation(base,qa,flow,installed,sequence,summaries,plan,anchor):
    scope=anchor['foreground_after']
    base.require(sequence.get('error') is None and sequence.get('secondary_errors')==[] and
        sequence['installed_before']==sequence['installed_after']==installed and
        sequence['owned_task']==anchor['owned_task'] and
        sequence['foreground_before']==sequence['foreground_after']==scope and
        sequence['after_state_completed'] is True and sequence['restoration_qualified'] is True and
        sequence['post_state_matches_before'] is True and
        sequence['accessibility_restoration']['state_after']==anchor['accessibility_restoration']['state_after'],
        'CONTENT_READY_CURRENT_OWNED_SCOPE_IDENTITY_AND_RESTORATION_REQUIRED')
    row=summaries['inspect']
    base.require(row['nonce']==plan['nonces']['inspect'] and
        row['wire_sha256']==sequence['inspection_wire_sha256'],'CONTENT_READY_EXACT_INSPECTION_NONCE_WIRE')
    helper,pin=reveal.assessment(base,qa,flow,row['nonce'],'inspect',scope,row['wire_sha256'])
    base.require(pin['assessment_bytes']==row['assessment_bytes'] and
        pin['assessment_sha256']==row['assessment_sha256'] and helper.get('action_attempted') is False and
        helper.get('outcome_unknown') is False and helper['restoration']['service_info_verified'] is True,
        'CONTENT_READY_NO_ACTION_EXACT_ASSESSMENT_REQUIRED')
    inspection=helper['inspection']
    return {'scope':scope,'owned_task':sequence['owned_task'],'assessments':summaries,
        'accessibility_restoration':sequence['accessibility_restoration'],
        'after_state_completed':True,'restoration_qualified':True,'action_attempted':False,
        'outcome_unknown':False,'node_count':len(inspection['nodes']),
        'tree_sha256':inspection['tree_sha256'],'window_sha256':inspection['window_sha256'],
        'status':content_status(qa,inspection,scope)}


def await_player_content(base,prior,qa,flow,session,installed,result,sequence,summaries):
    began=time.monotonic();anchor=result['video_click_sequence'];window=None
    record={'qualified':False,'maximum_additional_sequences':3,'deadline_seconds':CONTENT_READY_SECONDS,
        'deadline_kind':'readiness admission and qualification; original finally may complete',
        'original_worker_deadline_unchanged':True,'observations':[],
        'failed_reads_retried':False,'additional_input_actions':0,
        'future_reveal_requires_original_full_fresh_inspection':True}
    result['player_content_readiness']=record
    for index in range(4):
        base.require(time.monotonic()-began<CONTENT_READY_SECONDS,'PLAYER_CONTENT_READINESS_DEADLINE')
        plan=VIDEO_POST_PLANS[-1] if index==0 else CONTENT_READY_PLANS[index-1]
        if index:
            before=getattr(session,'sequence_observation',None)
            try:sequence=session.sequence(json.loads(json.dumps(plan)))
            except BaseException:
                current=getattr(session,'sequence_observation',None)
                if current is not None and current is not before:record['failed_sequence']=current
                raise
            summaries=base.assessment_summary(prior,qa,flow.step,sequence,plan)
        observed=content_observation(base,qa,flow,installed,sequence,summaries,plan,anchor)
        observed.update(index=index,source='existing_last_video_post' if index==0 else 'additional_no_action_read',
            elapsed_ms=int((time.monotonic()-began)*1000))
        record['observations'].append(observed)
        if window is None:window=observed['window_sha256']
        base.require(observed['window_sha256']==window,'CONTENT_READY_WINDOW_CHANGED')
        base.require(time.monotonic()-began<CONTENT_READY_SECONDS,'PLAYER_CONTENT_READINESS_DEADLINE')
        if observed['status']['ready']:
            record['qualified']=True;record['additional_sequences_used']=index
            result['player_content_readiness_completed']=True
            return
        base.require(observed['status']['wait_permitted'] is True,'CONTENT_READY_WAIT_NOT_AUTHORIZED')
    raise RuntimeError('PLAYER_CONTENT_METADATA_NOT_READY_IN_BOUNDED_READS')


def run(base,prior,qa,flow,session,installed,result):
    result['video_click_and_observations_completed']=False
    result['video_click_sequence_started']=False
    result['player_content_readiness_completed']=False
    try:
        base.require(result.get('query_submission_controls_completed') is True and
            result.get('results_container_content_observed') is True,'ACTUAL_CURRENT_QUERY_CONTENT_REQUIRED')
        stable_course(base,prior,qa,flow,session,installed,result)
        result['video_click_sequence_started']=True
        sequence=course_sequence(base,qa,session,result)
        result['video_click_sequence']=sequence
        base.require(sequence['installed_before']==sequence['installed_after']==installed and
            sequence.get('click_acknowledged') is True and sequence['restoration_qualified'] is True and
            sequence['after_state_completed'] is True and sequence['foreground_before']['activity']==base.SEARCH_ACTIVITY,
            'COURSE_CLICK_ACK_AND_RESTORATION_REQUIRED')
        result['video_click_assessments']=base.assessment_summary(prior,qa,flow.step,sequence,VIDEO_PLAN)
        selected=result['video_action_bound_selection'];inspected=result['video_click_assessments']['inspect']
        base.require(selected['current_tree_sha256']==inspected['tree_sha256'] and
            selected['current_window_sha256']==inspected['window_sha256'],'ACTION_BOUND_COURSE_INSPECTION_CHANGED')
        result['video_click_acknowledged']=True
    except BaseException as error:
        if hasattr(session,'sequence_observation'):result['failed_video_sequence']=session.sequence_observation
        prior.remember(result,'video_open',error)
    finally:
        # Read-only observations are separately fresh. A failed read stops this
        # list; the original Session still attempts its own independent state.
        result['video_post_observations']=[]
        post_plans=VIDEO_POST_PLANS if result['error'] is None else VIDEO_POST_PLANS[:1]
        for index,plan in enumerate(post_plans,1):
            try:
                sequence=session.sequence(json.loads(json.dumps(plan)))
                base.require(sequence['installed_before']==sequence['installed_after']==installed and
                    sequence['restoration_qualified'] is True and sequence['after_state_completed'] is True,
                    'POST_COURSE_READ_IDENTITY_AND_RESTORATION_REQUIRED')
                summaries=base.assessment_summary(prior,qa,flow.step,sequence,plan)
                result['video_post_observations'].append({'index':index,'foreground':sequence['foreground_after'],
                    'assessments':summaries,'restoration':sequence['accessibility_restoration'],
                    'restoration_qualified':True,'after_state_completed':True})
            except BaseException as error:
                if hasattr(session,'sequence_observation'):result['failed_video_post_sequence']=session.sequence_observation
                prior.remember(result,'independent_video_post_observation',error)
                break
    result['video_click_and_observations_completed']=(result.get('video_click_acknowledged') is True and
        len(result['video_post_observations'])==3 and result['error'] is None and result['secondary_errors']==[])
    result['video_effect_classification']='PENDING_PRIVATE_POST_CLICK_TREE_REVIEW'
    result['business_outcome_unknown']=True
    result['playback_or_audio_success_inferred']=False
    if result['video_click_and_observations_completed']:
        try:await_player_content(base,prior,qa,flow,session,installed,result,sequence,summaries)
        except BaseException as error:prior.remember(result,'player_content_readiness',error)
    if result['player_content_readiness_completed'] and result['error'] is None and result['secondary_errors']==[]:
        reveal.run(base,prior,qa,flow,session,installed,result)
