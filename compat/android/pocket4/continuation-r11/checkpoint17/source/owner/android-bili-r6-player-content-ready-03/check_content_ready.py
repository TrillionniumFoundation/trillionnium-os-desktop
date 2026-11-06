#!/usr/bin/env python3
"""Production readiness and Session, synthetic public trees, explicit local I/O seams."""
import ast,copy,hashlib,json,tempfile,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

fixture=load(ROOT/'owned-bili-qa-r6-reveal-01/controls/check_reveal.py','existing_public_fixture')
qa,adapter=fixture.qa,fixture.adapter
video=load(HERE/'video_navigation.py','actual_content_ready')
video.reveal=load(HERE/'controls_reveal.py','actual_reveal')
base_source=load(HERE/'owned_navigation.py','actual_navigation_source')


def shape(mode):
    v=fixture.fixture()
    if mode in ('missing','title_only','missing_container','different_present_title','duplicate_author','truncated_resource'):
        v['nodes']=[n for n in v['nodes'] if n['resource_id'] not in
            ([qa.PACKAGE+':id/author_name'] if mode=='title_only' else [qa.PACKAGE+':id/title',qa.PACKAGE+':id/author_name'])]
    if mode=='truncated_resource':v['nodes'][0]['resource_id_truncated']=True
    if mode=='wrong_title':v['nodes'][0].update(text='Another public course',text_sha256=qa.sha(b'Another public course'))
    if mode=='missing_container':v['nodes']=[n for n in v['nodes'] if n['resource_id']!=qa.PACKAGE+':id/video_container']
    if mode=='different_present_title':
        v['nodes'].append(fixture.node(qa.PACKAGE+':id/title','android.widget.TextView','0/1',[320,760,1000,820],'Another public course'))
    if mode=='duplicate_author':
        for path in ('0/2','0/3'):v['nodes'].append(fixture.node(qa.PACKAGE+':id/author_name','android.widget.TextView',path,[320,830,1000,900],'Ayumu爱讲数学'))
    if mode=='partial':v['complete']=False
    if mode=='changed_window':v['window']['bounds'][3]+=1
    if mode=='bad_geometry':v['nodes'][3]['bounds'][2]-=1
    return fixture.refresh(v)


def exercise(modes,fail=None,expire=False,changed_task=False):
    calls=[];clock=[0.0];installed={'synthetic_fixed_installed_identity':True}
    owned={'task':12345,'package':qa.PACKAGE,'synthetic':True};state={'accessibility_enabled':False,
        'touch_exploration_enabled':False,'enabled_service_count':0,'enabled_services_sha256':qa.sha(b'')}
    failure=RuntimeError('SYNTHETIC_'+str(fail));counter=[0];task_changed=[False]
    with tempfile.TemporaryDirectory(prefix='bili-content-ready-pure-') as temporary:
        flow=types.SimpleNamespace(step=Path(temporary));session=object.__new__(adapter.Session);session.qa=qa
        session.installed=lambda:copy.deepcopy(installed)
        session.task=lambda:dict(owned,task=12346) if task_changed[0] else copy.deepcopy(owned)
        session.foreground=fixture.scope
        def instrument(request):
            op,nonce=request['op'],request['nonce'];calls.append((op,nonce));clock[0]+=0.01
            assert op in ('state','inspect'),'readiness attempted an input'
            is_extra=nonce in {n for p in video.CONTENT_READY_PLANS for n in p['nonces'].values()}
            if is_extra and fail=='inspect' and op=='inspect':raise failure
            if is_extra and fail=='after_state' and nonce==video.CONTENT_READY_PLANS[0]['nonces']['after']:raise failure
            helper={'protocol':qa.PROTOCOL,'op':op,'nonce':nonce,'self_uid':10184,'ok':True,'error':None,
                'secondary_errors':[],'restoration':{'service_info_verified':True},'action_attempted':False,
                'outcome_unknown':False,'ui_automation_connected':op!='state'}
            if op=='state':helper['state']=copy.deepcopy(state)
            else:
                index=min(counter[0],len(modes)-1)
                helper.update(host_scope_attestation=copy.deepcopy(request['scope']),
                    accessibility_state_before_connection=copy.deepcopy(state),inspection=shape(modes[index]))
                counter[0]+=1
            assessed={'helper':helper,'held_transport_returned_after_post_guard':True,
                'actual_command_returncode':0,'actual_instrumentation_finish_code':-1,
                'wire_sha256':qa.sha(qa.canonical(helper)),'recorder_command_result_sha256':'a'*64}
            (flow.step/(nonce+'.assessment.json')).write_text(json.dumps(assessed,sort_keys=True))
            if is_extra and expire and nonce==video.CONTENT_READY_PLANS[0]['nonces']['after']:clock[0]+=13
            return assessed
        session.instrument=instrument
        def summary(prior,contract,step,sequence,plan):
            result={}
            for phase,nonce in plan['nonces'].items():
                raw=(step/(nonce+'.assessment.json')).read_bytes();v=json.loads(raw)
                result[phase]={'nonce':nonce,'operation':v['helper']['op'],'assessment_bytes':len(raw),
                    'assessment_sha256':qa.sha(raw),'wire_sha256':v['wire_sha256'],
                    'recorder_command_result_sha256':v['recorder_command_result_sha256'],
                    'actual_command_returncode':0,'actual_instrumentation_finish_code':-1}
            return result
        base=types.SimpleNamespace(require=qa.require,read=base_source.read,sha=qa.sha,UID=10184,
                                  assessment_summary=summary)
        initial=session.sequence(copy.deepcopy(video.VIDEO_POST_PLANS[-1]));summaries=summary(None,qa,flow.step,initial,video.VIDEO_POST_PLANS[-1])
        anchor=copy.deepcopy(initial)
        if changed_task:task_changed[0]=True
        result={'video_click_sequence':anchor,'player_content_readiness_completed':False}
        original_time=video.time;video.time=types.SimpleNamespace(monotonic=lambda:clock[0])
        error=None
        try:video.await_player_content(base,None,qa,flow,session,installed,result,initial,summaries)
        except BaseException as caught:error=caught
        finally:video.time=original_time
        return result,error,calls,session.sequence_observation,failure


def main():
    cases=[]
    def passed(name):cases.append({'case':name,'passed':True})
    baseplans=[base_source.PLAN,base_source.POST_PLAN,base_source.SET_TEXT_PLAN,base_source.SUBMIT_PLAN,
        base_source.RESULTS_PLAN,*base_source.STABILITY_PLANS,*base_source.QUERY_STABILITY_PLANS,
        *base_source.SUBMIT_STABILITY_PLANS,*base_source.RESULT_OBSERVATION_PLANS]
    used=[base_source.NONCE,*(n for p in baseplans for n in p['nonces'].values())]
    video.validate(adapter,qa,used)
    plans=[*baseplans,video.VIDEO_PLAN,*video.VIDEO_STABILITY_PLANS,*video.VIDEO_POST_PLANS,*video.CONTENT_READY_PLANS]
    video.reveal.validate(adapter,qa,[base_source.NONCE,*(n for p in plans for n in p['nonces'].values())])
    playback=load(HERE/'playback_controls.py','unchanged_player_controls')
    plans.extend((video.reveal.REVEAL_PLAN,video.reveal.POST_PLAN))
    playback.validate(adapter,qa,[base_source.NONCE,*(n for p in plans for n in p['nonces'].values())])
    passed('all_fresh_plan_groups_disjoint_original_validators')
    for modes,extra in ((['ready'],0),(['missing','ready'],1),(['missing','title_only','ready'],2)):
        result,error,calls,seq,_=exercise(modes)
        assert error is None and result['player_content_readiness_completed'] is True
        record=result['player_content_readiness'];assert record['qualified'] and record['additional_sequences_used']==extra
        assert len(calls)==3*(extra+1) and all(op in ('state','inspect') for op,_ in calls)
        assert seq['after_state_completed'] and seq['restoration_qualified']
        assert record['observations'][-1]['status']['original_full_player_proof']['title_text_sha256']==qa.REVEAL_TITLE
        passed('original_full_proof_after_'+str(extra)+'_additional_reads')
    result,error,calls,seq,_=exercise(['missing'])
    assert str(error)=='PLAYER_CONTENT_METADATA_NOT_READY_IN_BOUNDED_READS' and len(calls)==12
    assert not result['player_content_readiness_completed'] and not result['player_content_readiness']['qualified']
    assert len(result['player_content_readiness']['observations'])==4 and seq['restoration_qualified']
    passed('absent_metadata_exhausts_exact_three_reads_without_input')
    for mode,reason in (
        ('wrong_title','CONTENT_READY_PRESENT_METADATA_MUST_MATCH'),
        ('different_present_title','CONTENT_READY_PRESENT_METADATA_MUST_MATCH'),
        ('duplicate_author','CONTENT_READY_PRESENT_METADATA_MUST_MATCH'),
        ('missing_container','CONTENT_READY_FIXED_PLAYER_ROLE_CHANGED'),
        ('partial','COMPLETE_INSPECTION_REQUIRED'),
        ('truncated_resource','CONTENT_READY_ROLE_FIELDS_MUST_BE_COMPLETE'),
        ('bad_geometry','REVEAL_ABSOLUTE_PLAYER_GEOMETRY')):
        result,error,calls,seq,_=exercise([mode])
        assert str(error)==reason,(mode,str(error));assert len(calls)==3 and seq['restoration_qualified']
        assert not result['player_content_readiness_completed'];passed(mode+'_never_authorizes_extra_read')
    result,error,calls,seq,_=exercise(['missing','changed_window'])
    assert str(error)=='CONTENT_READY_WINDOW_CHANGED' and len(calls)==6 and not result['player_content_readiness_completed']
    passed('changed_window_rejected_after_complete_restored_read')
    result,error,calls,seq,_=exercise(['missing','ready'],changed_task=True)
    assert str(error)=='CONTENT_READY_CURRENT_OWNED_SCOPE_IDENTITY_AND_RESTORATION_REQUIRED'
    assert not result['player_content_readiness_completed'];passed('changed_owned_task_rejected')
    for failure in ('inspect','after_state'):
        result,error,calls,seq,first=exercise(['missing','ready'],fail=failure)
        assert error is first and len(calls)==6 and not result['player_content_readiness_completed']
        assert result['player_content_readiness']['failed_sequence'] is seq and seq['after_state_attempted']
        assert seq['after_state_completed'] is (failure=='inspect')
        assert calls[-1][1]==video.CONTENT_READY_PLANS[0]['nonces']['after']
        passed('original_Session_'+failure+'_failure_finally_retained_no_retry')
    result,error,calls,seq,_=exercise(['missing','ready'],expire=True)
    assert str(error)=='PLAYER_CONTENT_READINESS_DEADLINE' and len(calls)==6 and seq['restoration_qualified']
    assert not result['player_content_readiness_completed'] and not result['player_content_readiness']['qualified']
    passed('late_ready_observation_does_not_qualify_original_finally_completes')
    source=ROOT/'owned-bili-qa-r6-reveal-01/source'
    expected={'qa_contract.py':'871c784812063739a6ab976784fb38243af52266b0d9a95aa1244779ccd2c005',
              'qa_adapter.py':'1e939fb27aa4eaa9bb2fd79d7022ff4f48011fdf8824b0e7645bbc6f3308e1c8'}
    for name,h in expected.items():assert hashlib.sha256((source/name).read_bytes()).hexdigest()==h
    passed('original_R6_contract_and_Session_bytes_unchanged')
    report={'schema':1,'ok':True,'count':len(cases),'cases':cases,'Android_Hepta_or_process_actions':0,
        'synthetic_public_trees_only':True,'production_Session_sequence_and_full_predicate_executed':True,
        'instrument_installed_task_foreground_IO_are_explicit_synthetic_seams':True,
        'real_assessment_pins_and_canonical_helper_wire_checked':True}
    print(json.dumps(report,sort_keys=True,indent=2))
if __name__=='__main__':main()
