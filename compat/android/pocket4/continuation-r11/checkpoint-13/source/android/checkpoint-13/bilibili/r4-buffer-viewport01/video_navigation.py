"""One observed public course-card click; unchanged Session/Java action path."""
import json
import time

TITLE_SHA='7ff99f77d6b59f394c4c6c0ca167aded470663d4cef66215fcce841ed549afba'
UPLOADER_SHA='3355707b07511199c7d280b9a77510b5e9b8698c7c7e4aedcf938805a3822d64'
DURATION_SHA='137ed61cdad38eb26c79124e18cb04925f8ac831f042169328a35d25520db3fa'
CARD_SELECTOR={'class':'android.view.ViewGroup'}
VIDEO_PLAN = {'schema': 1, 'operation': 'click', 'selector': {'class': 'android.view.ViewGroup'}, 'nonces': {'before': '04707df07da98d4a837d7dd101f3e4ba', 'inspect': '7cc89c86837b49256edd6aa74213ef43', 'action': '6093a4691f3b219d9599286e202555d1', 'after': '993d1f31e4ab4f74c417ca22b49dca6d'}}
VIDEO_STABILITY_PLANS = [{'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'bca88735e103cbde92a430636a7efcdd', 'inspect': 'c24f0055d2ae44776da177ef75537b6a', 'after': '713ba42b4898821c7bf7f306a75ef892'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '0b5a245d8927c9798811fc482e07203b', 'inspect': '20f2d8cfe369866480a6f7ef5ffaca1a', 'after': '1ef29a1ea9b64f0d04f4876948b06f71'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'b2c9c0389d9099bd3ab69e2dd905afce', 'inspect': '796ae693bb98e2bf34436c7905ea1306', 'after': 'a60b4698d0296ca9823810d1b5874072'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': 'f467cd752993968b9b0688c76e6ffc17', 'inspect': '34c88dfd5685fb468f601fa47c06772a', 'after': 'd063aa066d705d18b0cfd23f4c64b058'}}]
VIDEO_POST_PLANS = [{'schema': 1, 'operation': 'inspect', 'nonces': {'before': '1c6701cc81d7edb484203c2f690d3dc3', 'inspect': '555348bd29aae99ee85b8150cf8b7d05', 'after': '7e98cb89e496ca10a2a9b3399cee7243'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '4e6dd04c076e56de943c65564a2a361f', 'inspect': '9f2caa3b9e47e8246acd217cb22bed12', 'after': '8a3b6189f76ee0008b9c3f8d4bff0356'}}, {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '75b0769140fa9dca9699da149bfd2f65', 'inspect': '4eb70f855d733211fe406f8e4d893e02', 'after': '57da4709ca6ebff88d0081942814434b'}}]


def validate(adapter,qa,base_nonces):
    plans=[VIDEO_PLAN,*VIDEO_STABILITY_PLANS,*VIDEO_POST_PLANS]
    for plan in plans:adapter.validate_plan(plan,qa)
    values=[n for plan in plans for n in plan['nonces'].values()]
    qa.require(len(values)==len(set(values))==25 and not set(values)&set(base_nonces),
        'FRESH_DISTINCT_VIDEO_NONCES_REQUIRED')
    qa.require(VIDEO_PLAN['selector']==CARD_SELECTOR and VIDEO_PLAN['operation']=='click' and
        len(VIDEO_STABILITY_PLANS)==4 and len(VIDEO_POST_PLANS)==3 and
        all(p['operation']=='inspect' for p in [*VIDEO_STABILITY_PLANS,*VIDEO_POST_PLANS]),
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


def run(base,prior,qa,flow,session,installed,result):
    result['video_click_and_observations_completed']=False
    result['video_click_sequence_started']=False
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
        viewport.run(base,prior,qa,flow,session,installed,result)
