"""Execute one original Clock scope on supplied current Main evidence.

This dedicated worker preserves the old business algorithms and independent
input/effect/task UNKNOWN states. It has no automatic replay or rollback path.
"""
from datetime import datetime,timezone
import os
from pathlib import Path
import signal
import time
import types


class CaseInterrupted(BaseException):pass
def stamp():return datetime.now(timezone.utc).isoformat()


def construct(session,components,result,monitor):
    trial=components['clock_delivery_trial.py'].Trial(session,session.root)
    session.trial=trial;session.helper.foreground=trial.helper_foreground
    model=components['clock_model.py'].model_for(session)
    if session.kind=='alarm04':
        reader=components['clock_alarm_reader.py'].make_reader(session.request['alarm_marker'])
        session.alarm_reader=reader
        raw,_=session.target.read_file(session.apk_paths['com.android.deskclock'],16777216)
        resources=reader.resource_contract(raw);result['actual_resource_contract']=resources
        flow=components['clock_alarm_flow.py'].AlarmFlow(trial,trial.base,model,reader,result,resources,session.root)
        flow.end=session.business_deadline
    else:
        timer=components['clock_timer_core.py'].make_timer_flow(session.limits['timer_duration_ms'])
        if session.kind=='expiry06':
            session.c.need(isinstance(monitor,components['clock_monitor_channel.py'].Client),
                'EXPIRY_REQUIRES_OWNED_CONTINUOUS_NOTIFY_SUPERVISOR')
            expiry=components['clock_expiry_flow.py'].make_flow(types.SimpleNamespace(Flow=timer),trial.base)
            delivery=components['clock_delivery.py'].Delivery(session,monitor,result)
            session.delivery=delivery
            cls=components['clock_delivery.py'].make_delivery_flow(expiry,delivery)
        else:
            session.c.need(monitor is None,'NO_FOREIGN_MONITOR_ON_ORIGINAL_TIMER_CORE')
            cls=timer
        flow=cls(trial,components['clock_selectors.py'],model,result,session.root,
            components['clock_model.py'].continuation_factory(session))
        flow.deadline=session.business_deadline
    session.flow=flow
    return flow,trial


def pending(session,flow):
    if flow is None:return {'input':None,'effect':None,'close':None}
    return {'input':flow.pending if session.kind=='alarm04' else flow.c.pending,
        'effect':flow.effect_pending,'close':flow.close_pending}


def final_original(session,flow,before,result):
    c=session.c;p=session.components['clock_preservation.py'];protection=session.protection
    state=pending(session,flow)
    if not any(value is not None for value in state.values()):flow.close()
    else:result['final_actions_blocked_by_unknown']={**state,'read_only':True}
    result['identity_after']=protection.identity();result['timer_final']=protection.timer_read()
    if session.kind=='alarm04':
        result['final_alarm_readback']=flow.reader.deleted()
        final=flow.evidence('final')
        c.need(final['commands']['scheduler']['clock_uid_current_pending_alarm_count']==0,
            'ORIGINAL_CLOCK_SCHEDULER_PENDING_AFTER_ALARM_CLEANUP')
        c.need(final['commands']['notifications']['alarm_record']['present'] is False,
            'ORIGINAL_ALARM_NOTIFICATION_REMAINS')
        roots,tasks=flow.topology('final-owned-alarm-tasks')
        c.need(tasks==flow.baseline and roots==flow.baseline_roots,'ORIGINAL_ALARM_TASK_SET_NOT_RESTORED')
        result.update(task_set_restored=True,empty_alarm_state_at_final_read=True,
            owned_alarm_cleanup_verified=not any(value is not None for value in pending(session,flow).values()))
    else:
        result['alarms_after']=protection.state();result['templates_sha_after']=protection.fingerprint()
        c.need(result['alarms_before']==result['alarms_after'] and result['templates_sha_before']==result['templates_sha_after'],
            'ORIGINAL_ALARMS_CHANGED_DURING_TIMER')
        if session.kind=='expiry06':roots,tasks=flow.topology('final-task-set')
        else:roots,tasks=session.trial.stacks('final-task-set')
        c.need(tasks==session.task_baseline and roots==session.task_baseline_roots,'ORIGINAL_CLOCK_TASKS_NOT_RESTORED')
        result['task_set_restored']=True
    if not any(value is not None for value in pending(session,flow).values()):
        after=protection.snapshot('after')
        result['protected_after']=c.regular(protection.journal_dir/'after.json',contents=False)
        c.need(p.preserved(before,after,include_preferences=False),'ORIGINAL_CLOCK_SOUND_PERMISSION_OR_DATA_CHANGED')
        result['protected_business_and_sound_state_preserved']=True
    session.held_artifacts.revalidate();result['guard_after']=session.guard()
    result['actual_final_caller']=session.caller_status({'timer15':'clock-timer-final-caller',
        'expiry06':'clock-expiry-final-caller','alarm04':'alarm-final-caller'}[session.kind])
    p.empty(result['timer_final'])


def success_predicates(session,flow,result):
    common=bool(result.get('business_scope_completed') is True and result.get('task_set_restored') is True
        and result.get('protected_business_and_sound_state_preserved') is True
        and result.get('identity_before')==result.get('identity_after')
        and result.get('guard_before')==result.get('guard_after')
        and result.get('actual_final_caller') and session.trial.owned is None
        and not any(value is not None for value in pending(session,flow).values())
        and not session.host_cancelled and not session.host_retirement_unknown
        and session.native_launches==session.trial.launches==2)
    if session.kind=='alarm04':
        required=('actual_firing_verified','actual_alarm_notification_posted','actual_alarm_window_observed',
            'actual_dismiss_effect_verified','normal_close_reopen_time_and_timezone_preserved',
            'exact_owned_alarm_deleted','owned_alarm_cleanup_verified')
        return bool(common and all(result.get(key) is True for key in required)
            and len(flow.native_tasks)==len(set(flow.native_tasks))==2
            and all(task in flow.normal_closed for task in flow.native_tasks)
            and flow.alert_task in flow.normal_closed+flow.self_finished
            and flow.actions<=24 and flow.create_ack and flow.label_ack and flow.dismiss_ack and flow.delete_ack)
    timer=bool(common and flow.owned==flow.closed and len(set(flow.owned))==2
        and session.trial.removals==2 and flow.c.actions<=session.limits['maximum_UI_actions'])
    if session.kind=='timer15':return timer
    required=('actual_expiry_verified','actual_expired_notification_posted','notify_monitor_closed_verified')
    # Exact host Notify and audio observations remain separate recorded facts,
    # matching original expiry05. Their absence is not silently turned into a
    # whole-app pass, desktop popup proof or physical speaker proof.
    deleted=[result.get('notifications',{}).get(label) for label in
        ('deleted','deleted-readback-0','deleted-readback-1')]
    deleted=[value for value in deleted if value is not None]
    return bool(timer and all(result.get(key) is True for key in required)
        and result.get('stop_reconciliation',{}).get('same_id_reset_verified') is True
        and deleted and deleted[-1].get('records')==[])


def execute(c,plan_ref,prep_ref,components,monitor=None):
    c.need(os.getuid()==os.geteuid()==0,'ROOT_EXPLICIT_NEW_CLOCK_CASE')
    planner=components['clock_plan.py']
    plan,source,baseline,identities,packet,task=planner.validate_plan(c,plan_ref,prep_ref)
    by_name={Path(row['path']).name:row for row in task['files']}
    c.need(set(components)=={name for name in by_name if name.endswith('.py')},'COMPLETE_CURRENT_CLOCK_MODULE_SET')
    for name,module in components.items():
        c.need(c.regular(module.__file__,contents=False)==by_name[name],'CLOCK_CODE_NOT_CURRENT_ADMITTED_COPY')
    if plan['kind']=='expiry06':
        c.need(isinstance(monitor,components['clock_monitor_channel.py'].Client),'ONLY_EXPLICIT_PARENT_OWNED_EXPIRY_WORKER')
        monitor.verify()
    else:c.need(monitor is None,'NO_UNREQUESTED_CLOCK_MONITOR')
    root=c.private_dir(plan['case_root']);started=time.monotonic();limits=source['limits']
    runtime=components['app_runtime.py']
    c.write_new(root/'execute-once.json',{'schema':'pocket4-clock-current-once-execution-v1','plan':plan_ref,
        'operator':runtime.process(c,os.getpid()),'kind':plan['kind'],'started_utc':stamp(),
        'started_monotonic':started,'business_deadline_monotonic':started+limits['business_seconds'],
        'lease_deadline_monotonic':started+limits['lease_seconds'],
        'absolute_final_deadline_monotonic':started+limits['lease_seconds']+limits['cleanup_seconds'],
        'automatic_retry':False})
    result={'schema':'pocket4-current-clock-original-case-result-v1','state':'FAILED_BEFORE_SESSION','kind':plan['kind'],
        'plan':plan_ref,'source_preparation':prep_ref,'support_manifest':source['support_manifest'],
        'framework_epoch_sha256':source['framework_epoch_sha256'],'started_utc':stamp(),
        'case_business_success_verified':False,'whole_app_business_accepted':False,'phases':{},'secondary_errors':[],
        'old_binary_or_epoch_business_credit_inherited':False,'automatic_retry':False,
        'SQL_write_commands':0,'provider_write_commands':0,'settings_writes':0,'permission_writes':0,
        'global_volume_or_ringtone_changes':0,'physical_audio_qualification':False,'desktop_popup_qualification':False,
        'scheduler_cancellation_verified':False,'scheduler_requires_saved_review':True,'limits':limits}
    session=flow=trial=lock=witness=None;before=None;first=None;retiring=False;signals=[]
    def interrupted(number,frame):
        nonlocal retiring
        signals.append(number)
        if not retiring:retiring=True;raise CaseInterrupted('CLOCK_CASE_CANCELLED_NO_REPLAY')
    def remember(label,error):
        nonlocal first
        row={'phase':label,'type':type(error).__name__,'message':str(error),'details':getattr(error,'details',None)}
        if first is None:first=error;result['error']=row
        else:result['secondary_errors'].append(row)
    try:
        for number in (signal.SIGINT,signal.SIGTERM):signal.signal(number,interrupted)
        lock=components['clock_transport_base.py'].ActionLock(c,root)
        witness=c.EvidenceWitness([plan_ref,plan['source'],source['task_source_manifest'],prep_ref,
            source['target_identity'],source['native_identity'],*task['files'],*task['origins']])
        def source_guard():witness.verify();c.read_ref(plan_ref);c.read_ref(c.GATES)
        cls=components['clock_session.py'].make_session_class(components['clock_transport_base.py'])
        session=cls(c,source,root,components,lock,source_guard,started,identities)
        session.protection=components['clock_protection.py'].Protection(session)
        result['guard_before']=session.guard();before=session.protection.snapshot('before')
        result.update(protected_before=c.regular(session.protection.journal_dir/'before.json',contents=False),
            identity_before=before['identity'],alarms_before=before['alarm_state'],
            templates_sha_before=before['alarm_content_sha256'],actual_business_phase=session.phase_ref)
        flow,trial=construct(session,components,result,monitor)
        try:flow.run();result['business_scope_completed']=True
        except BaseException as error:remember('original_business',error);result['business_scope_completed']=False
        finally:
            retiring=True
            try:
                trigger=c.write_new(root/'cleanup-trigger.json',{'business_completed':result.get('business_scope_completed') is True,
                    'first_error':result.get('error'),'pending':pending(session,flow),'automatic_retry':False})
                session.begin_cleanup(trigger);result['actual_cleanup_phase']=session.phase_ref
                if not result.get('business_scope_completed'):
                    try:flow.cleanup(session.deadline)
                    except BaseException as error:remember('original_failure_cleanup',error)
                final_original(session,flow,before,result)
            except BaseException as error:remember('original_final_cleanup_and_evidence',error)
    except BaseException as error:remember('case_admission_or_construction',error)
    finally:
        retiring=True
        if session is not None and session.delivery is not None:
            try:
                stop=session.delivery.stop();result['notify_watch_stop']=stop
                result['notify_monitor_closed_verified']=components['clock_notify_proof.py'].monitor_closed(
                    stop,session.delivery.started)
                c.need(result['notify_monitor_closed_verified'],'ORIGINAL_MONITOR_CHILD_READER_AND_BOTH_EOF_REQUIRED')
            except BaseException as error:remember('continuous_notify_retirement',error)
        if monitor is not None:
            try:monitor.close();result['monitor_control_FD_closed']=True
            except BaseException as error:remember('monitor_control_close',error)
        for obj,label in ((session,'actual_Main_and_APIs'),(lock,'whole_case_OFD'),(witness,'source_and_receipt_witness')):
            if obj is not None:
                try:obj.close();result[label+'_closed']=True
                except BaseException as error:remember(label+'_close',error)
        try:
            result['independent_Main_after']=baseline.guard();planner.validate_plan(c,plan_ref,prep_ref)
            c.need(time.monotonic()<=started+limits['lease_seconds']+limits['cleanup_seconds'],
                'ORIGINAL_CLOCK_ABSOLUTE_CASE_BUDGET')
            result['final_source_and_identity_chain_unchanged']=True
        except BaseException as error:remember('independent_final_Main_and_source',error)
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        waiting=sorted(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
        if signals or waiting:remember('cancelled_before_terminal_commit',CaseInterrupted('CLOCK_CANCELLED_BEFORE_TERMINAL_COMMIT'))
        result['cancellation_commit']={'observed_before_commit':list(signals),'pending_at_commit':waiting,
            'decision_frozen_after_context_exit':True}
        if flow is not None:
            state=pending(session,flow)
            result.update(pending=state,owned_task_remaining=trial.owned,native_launch_calls=trial.launches,
                normal_remove_calls=trial.removals,actual_task_claims=session.claimed_tasks,
                actual_launch_receipts=session.launch_receipts,retained_host_receipts=session.records,
                ui_actions=flow.actions if session.kind=='alarm04' else flow.c.actions,
                outcome_unknown=any(value is not None for value in state.values()) or session.host_retirement_unknown,
                host_cancellation_observed=session.host_cancelled,
                case_business_success_verified=bool(first is None and not signals and not waiting
                    and not result['secondary_errors'] and success_predicates(session,flow,result)))
            if session.kind=='alarm04':
                result.update(native_launched_tasks=flow.native_tasks,normally_closed_tasks=flow.normal_closed,
                    alert_self_finished_tasks=flow.self_finished,owned_alarm_id=flow.reader.alarm_id,
                    creation_native_ACK=flow.create_ack,label_native_ACK=flow.label_ack,
                    dismiss_native_ACK=flow.dismiss_ack,delete_native_ACK=flow.delete_ack)
            else:result.update(owned_tasks=flow.owned,closed_tasks=flow.closed,
                alert_self_finished_tasks=getattr(flow,'alert_self_finished',[]))
        result.update(state='ORIGINAL_CLOCK_SCOPE_VERIFIED_CLEAN' if result['case_business_success_verified'] else 'FAILED_OR_UNKNOWN_RETAINED',
            received_signals=signals,finished_utc=stamp(),elapsed_seconds=time.monotonic()-started,
            whole_app_business_accepted=False,Binder_UID_cleanup_verified=False,automatic_rollback=False,
            continuous_runtime_sampling_verified=False,soak_or_stress_verified=False)
        result_ref=c.write_new(root/'result.json',result)
    return result_ref,result
