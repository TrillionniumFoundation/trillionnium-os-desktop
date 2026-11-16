"""Run the complete original WebView business or media body in a fresh scope."""
from datetime import datetime,timezone
import os
from pathlib import Path
import signal
import time

class CaseInterrupted(BaseException):pass
def stamp():return datetime.now(timezone.utc).isoformat()

def execute(c,base_ref,components,prep_ref,client):
    c.need(os.getuid()==os.geteuid()==0,'ROOT_NEW_WEBVIEW_WORKER')
    base=c.parse(c.read_ref(base_ref));plan=components['webview_plan.py'];runtime=components['webview_runtime.py']
    host=components['app_runtime.py'];_,support=c.support(base['support_manifest'])
    baseline=support['business_baseline.py'].BusinessBaseline(base['baseline'],base['qualification'])
    plan.validate(c,base,baseline);root=c.private_dir(base['case_root'])
    trial_module=components['webview_trial10.py' if base['kind']=='webview_business10' else 'webview_trial11.py']
    resources_before=trial_module.limits()
    c.write_new(root/'execute-once.json',{'plan':base_ref,'operator':host.process(c,os.getpid()),
        'started_utc':stamp(),'automatic_retry':False})
    evidence=c.private_dir(root/'evidence',create=True)
    result={'schema':'pocket4-current-webview-original-case-result-v1','state':'FAILED','kind':base['kind'],
        'plan':base_ref,'source_preparation':prep_ref,'started_utc':stamp(),'case_business_success_verified':False,
        'whole_app_business_accepted':False,'automatic_retry':False,'secondary_errors':[],
        'resources_before':resources_before,'original_full_app_gates_unchanged':True,
        'diagnostic_scope':'original synchronous UID/exit/crash checkpoints for media11 only',
        'continuous_sampling_or_soak_credit':False,'audio_playback_qualified':False,
        'Binder_UID_cleanup_verified':False,'automatic_rollback':False}
    session=trial=lock=witness=None;first=None;retiring=False;signals=[]
    def interrupted(number,frame):
        nonlocal retiring
        signals.append(number)
        if not retiring:
            retiring=True;raise CaseInterrupted('WEBVIEW_CANCELLED_NO_ACTION_REPLAY')
    def begin_retirement():
        nonlocal retiring
        retiring=True
    def remember(label,error):
        nonlocal first
        row={'phase':label,'type':type(error).__name__,'message':str(error)}
        if first is None:first=error;result['error']=row
        else:result['secondary_errors'].append(row)
    try:
        for number in (signal.SIGINT,signal.SIGTERM):signal.signal(number,interrupted)
        lock=runtime.ActionLock(c,host,root)
        lease=runtime.create_lease(c,host,base_ref,base)
        active_ref,scopes=plan.activate(c,base_ref,lease,lock.ref)
        active=c.parse(c.read_ref(active_ref));phase=runtime.phase(c,host,active_ref,active,'business')
        witness=c.EvidenceWitness([base_ref,active_ref,lease,lock.ref,*scopes])
        session=components['webview_session.py'].Session(c,active_ref,active,scopes,phase,lock,components,evidence,
            client,begin_retirement)
        client.attach(session)
        session.home_identity=components['webview_protection.py'].home_only(session)
        result.update(active_plan=active_ref,recorder_scopes=scopes,actual_business_phase=phase,
            fresh_default_HOME_before=session.home_identity)
        client.start()
        trial=trial_module.make_trial(session,session.tx,client,components['webview_protection.py'],
            session.protection,components['webview_diagnostics.py'],evidence,session.main_identity)
        session.bind_trial(trial)
        result['original_business_result']=trial.run()
        result['actual_cleanup_phase']=session.phase_ref
        session.caller_status('webview10-final-caller' if base['kind']=='webview_business10' else 'webview11-final-caller')
        after=components['webview_protection.py'].home_only(session)
        c.need(after==session.home_identity,'ORIGINAL_HOME_TASK_AND_COMPONENT_RESTORED_WITHOUT_RECREATION')
        result['fresh_default_HOME_after']=after;result['guard_after']=session.guard()
    except BaseException as error:remember('original_case_or_admission',error)
    finally:
        retiring=True
        # The server is a host-only owned sibling. EOF/retirement does not
        # authorize replaying a pending WebView action or deleting a storage key.
        if session is not None:
            if client.session is None:
                try:client.attach(session)
                except BaseException as error:remember('attach_owned_fixture_cleanup',error)
            if client.session is not None:
                try:result['fixture_stop']=client.stop()
                except BaseException as error:remember('fixture_owned_retirement',error)
        for obj,label in ((session,'actual_Main_and_original_APIs'),(lock,'whole_case_OFD'),(witness,'evidence_witness'),(client,'fixture_control')):
            if obj is not None:
                try:obj.close();result[label+'_closed']=True
                except BaseException as error:remember(label+'_close',error)
        try:
            result['independent_Main_after']=baseline.guard();plan.validate(c,base,baseline)
            result['final_source_and_identity_chain_unchanged']=True
            result['resources_after']=trial_module.limits()
        except BaseException as error:remember('independent_final_Main_source_resources',error)
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        pending=sorted(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
        if signals or pending:remember('cancel_before_terminal_commit',CaseInterrupted('WEBVIEW_CANCELLED_BEFORE_COMMIT'))
        result['cancellation_commit']={'observed_before_commit':list(signals),'pending_at_commit':pending,
            'decision_frozen_after_context_exit':True}
        if trial is not None:
            result['original_business_result']=trial.result
            result.update(UI_actions=trial.actions,native_launch_calls=trial.launches,normal_remove_calls=trial.removals,
                pending_effects=sorted(trial.pending),remaining_owned_task=trial.owned,
                outcome_unknown=bool(trial.pending),original_identity_checks=trial.identity_checks)
            completed=bool(trial.result.get('business_flow_completed') is True and trial.launches==trial.removals==2
                and trial.identity_checks==2 and not trial.pending and trial.owned is None
                and result.get('guard_after') and result.get('fresh_default_HOME_after')==result.get('fresh_default_HOME_before')
                and result.get('fixture_stop',{}).get('own_child_reaped') is True
                and result.get('fixture_stop',{}).get('socket_closed') is True
                and result.get('fixture_control_closed') is True)
            if base['kind']=='webview_business10':
                completed=completed and trial.result.get('owned_storage_key_removal_verified') is True
                result['owned_storage_state']=trial.result.get('owned_storage_state')
            result['case_business_success_verified']=bool(completed and first is None and not signals and not pending
                and not result['secondary_errors'])
        result['state']='ORIGINAL_WEBVIEW_CASE_VERIFIED_CLEAN' if result['case_business_success_verified'] else 'FAILED_OR_UNKNOWN_RETAINED'
        result.update(received_signals=signals,finished_utc=stamp(),whole_app_business_accepted=False)
        ref=c.write_new(root/'result.json',result)
    return ref,result
