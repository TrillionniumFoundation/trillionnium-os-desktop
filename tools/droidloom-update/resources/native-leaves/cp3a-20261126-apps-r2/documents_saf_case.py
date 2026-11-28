"""Dedicated fresh-Main SAF11 execution, preserving the original scoped gates.

Only real original business readback, all owned task/package/file cleanup and
the new complete source/Main chain can produce scoped success. Publication and
host controls grant no Android permission or whole-application credit.
"""
from datetime import datetime,timezone
import os
from pathlib import Path
import signal
import time
import types

class CaseInterrupted(BaseException):pass
def stamp():return datetime.now(timezone.utc).isoformat()

def construct(session,components,names,artifacts):
    adapter=types.SimpleNamespace(Adapter=lambda *a:components['documents_saf_ui.py'].SAF11UI(*a,scope=names))
    history=components['documents_history.py'].HistoricalFacts(session.c)
    flow=components['documents_saf_core.py'].SAF11Flow(session,session.tx,adapter,scope=names,artifacts=artifacts,history=history)
    session.case=flow
    return flow

def execute(c,plan_ref,prep_ref,components):
    c.need(os.getuid()==os.geteuid()==0,'ROOT_EXPLICIT_SAF11_CASE_EXECUTION')
    planner=components['documents_plan.py']
    plan,source,baseline,identities,packet,task,names,build=planner.validate_plan(c,plan_ref,prep_ref)
    by_name={Path(r['path']).name:r for r in task['files']}
    c.need(set(components)=={n for n in by_name if n.endswith('.py')},'COMPLETE_EXTERNALLY_ADMITTED_SAF11_MODULE_SET')
    for name,module in components.items():
        c.need(c.regular(module.__file__,contents=False)==by_name[name],'LOADED_SAF_CODE_NOT_ADMITTED_CASE_COPY')
    root=c.private_dir(plan['case_root']);business_seconds,cleanup_seconds=c.support(c.SUPPORT_REF)[1]['business_commands.py'].native_channel_module().fixture_phase_budget(600,120);started=time.monotonic();business_deadline=started+business_seconds
    host=components['app_runtime.py']
    c.write_new(root/'execute-once.json',{'schema':'pocket4-documents-saf-once-execution-v1','plan':plan_ref,
        'operator':host.process(c,os.getpid()),'started_utc':stamp(),'business_deadline_monotonic':business_deadline,
        'absolute_final_deadline_monotonic':business_deadline+cleanup_seconds,'automatic_retry':False})
    c.private_dir(root/'ui',create=True)
    result={'schema':'pocket4-final-documents-saf-original-case-result-v1','state':'FAILED_BEFORE_SESSION','plan':plan_ref,
        'source_preparation':prep_ref,'started_utc':stamp(),'case_business_success_verified':False,
        'whole_app_business_accepted':False,'automatic_retry':False,'secondary_errors':[]}
    session=flow=lock=witness=None;first=None;retiring=False;signals=[];saved={}
    def interrupted(signum,frame):
        nonlocal retiring
        signals.append(signum)
        if not retiring:
            retiring=True
            raise CaseInterrupted('SAF11_CASE_CANCELLED')
    def remember(label,error):
        nonlocal first
        item={'phase':label,'type':type(error).__name__,'message':str(error)}
        if first is None:first=error;result['error']=item
        else:result['secondary_errors'].append(item)
    try:
        for sig in (signal.SIGINT,signal.SIGTERM):saved[sig]=signal.signal(sig,interrupted)
        lock=components['documents_transport_base.py'].ActionLock(c,root)
        witness=c.EvidenceWitness([plan_ref,source,source['task_source_manifest'],prep_ref,*task['files'],*task['origins']])
        artifacts=components['documents_artifact_inputs.py'].HelperArtifactInputs(
            Path(build['apk']['path']),build['apk']['bytes'],build['apk']['sha256'],build['signer_certificate_sha256'],
            Path(plan['build']['path']),plan['build']['sha256'],Path(plan['pm_help']['path']),plan['pm_help']['sha256'])
        def source_guard():
            witness.verify();c.read_ref(plan_ref);c.read_ref(c.GATES)
        actual_names=components['documents_names.py'].SAFNames(names.RUN,root)
        cls=components['documents_session.py'].make_session_class(components['documents_transport_base.py'])
        session=cls(c,{**source,'pm_help':plan['pm_help']},root,components,lock,source_guard,business_deadline,
            actual_names,artifacts,identities)
        flow=construct(session,components,actual_names,artifacts)
        flow.result.update(result);result=flow.result
        result['initial_guard']=session.guard();result['actual_business_phase']=session.phase_ref
        try:flow.business()
        except BaseException as error:
            remember('original_business',error);result['business_flow_completed']=False
        finally:
            retiring=True
            try:
                trigger=c.write_new(root/'cleanup-trigger.json',{'actual_business_error':result.get('error'),
                    'original_scope_completed':result.get('business_flow_completed') is True,
                    'automatic_retry':False,'at_utc':stamp()})
                session.begin_cleanup(trigger);result['actual_cleanup_phase']=session.phase_ref
                result['cleanup']=flow.cleanup()
                flow.ui.check_tasks('final-exact-owned-task-set-restored')
                c.need(not flow.ui.owned and session.last_stacks is not None and session.last_stacks[1]==flow.ui.baseline,
                    'ALL_SAF_OWNED_TASKS_ABSENT_OTHER_TASKS_UNCHANGED')
                result['task_set_restored']=True
                result['actual_final_caller']=session.caller_status('documents-final-caller')
                result['final_guard']=session.guard()
            except BaseException as error:remember('original_final_cleanup_or_evidence',error)
    except BaseException as error:remember('case_admission_or_construction',error)
    finally:
        retiring=True
        if flow is not None:
            try:flow.release_local_handles();result['all_original_local_FDs_closed']=True
            except BaseException as error:remember('original_local_FD_close',error)
        for obj,label in ((session,'actual_Main_and_APIs'),(lock,'whole_case_OFD'),(witness,'source_and_receipt_witness')):
            if obj is not None:
                try:obj.close();result[label+'_closed']=True
                except BaseException as error:remember(label+'_close',error)
        try:
            result['independent_Main_after']=baseline.guard()
            planner.validate_plan(c,plan_ref,prep_ref)
            result['final_source_and_identity_chain_unchanged']=True
            c.need(time.monotonic()<=business_deadline+cleanup_seconds,'FIXED_SAF11_ABSOLUTE_CASE_DEADLINE')
        except BaseException as error:remember('independent_final_Main_and_source_chain',error)
        # Dedicated entry immediately prints and exits. Cancellation is frozen
        # only after context/FD retirement and actual final source/Main checks.
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        pending=sorted(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
        if signals or pending:remember('cancelled_before_terminal_commit',CaseInterrupted('SAF11_CANCELLED_BEFORE_COMMIT'))
        result['cancellation_commit']={'observed_before_commit':list(signals),'pending_at_commit':pending,
            'decision_frozen_after_context_exit':True}
        if flow is not None:
            result.update(ui_actions=flow.ui.actions,native_launch_calls=flow.ui.launches,owned_remove_calls=flow.ui.removals,
                owned_task_ids_closed=flow.ui.closed,source_bound_adopted_tasks=flow.ui.adopted,owned_tasks=flow.ui.owned,
                pending_effects=flow.ui.pending,install_pending=flow.install_pending,uninstall_pending=flow.uninstall_pending,
                outcome_unknown=bool(flow.ui.pending or flow.install_pending or flow.uninstall_pending or session.host_retirement_unknown),
                actual_task_claims=session.claimed_tasks,actual_launch_receipts=session.launch_receipts,
                retained_host_receipts=session.records,host_cancellation_observed=session.host_cancelled)
            clean=result.get('cleanup',{});files=clean.get('file_cleanup') or {}
            required=components['documents_profiles.py'].REQUIRED_GATES
            complete=bool(result.get('business_flow_completed') is True and set(result.get('gates',{}))==required
                and all(row.get('passed') is True for row in result.get('gates',{}).values())
                and clean.get('errors')==[] and clean.get('package_uninstalled_verified') is True
                and clean.get('package_absent_verified') is True and clean.get('guest_staging_used') is False and clean.get('staged_apk_created') is False and clean.get('staged_apk_removed') is False
                and files.get('directory_removed_verified') is True and files.get('fallback_file_unlink') is False
                and flow.ui.launches==2 and flow.ui.removals==len(flow.ui.closed)==2+len(flow.ui.adopted)
                and len(flow.ui.closed)==len(set(flow.ui.closed)) and flow.ui.actions<=36
                and not flow.ui.owned and not result['outcome_unknown'] and result.get('task_set_restored') is True
                and result.get('final_guard')==result.get('initial_guard') and result.get('actual_final_caller')
                and not session.host_cancelled and result.get('all_original_local_FDs_closed') is True)
            result['case_business_success_verified']=bool(complete and first is None and not signals and not pending
                and result['secondary_errors']==[])
        result['state']='ORIGINAL_SAF11_VERIFIED_CLEAN' if result['case_business_success_verified'] else 'FAILED_OR_UNKNOWN_RETAINED'
        result.update(received_signals=signals,finished_utc=stamp(),elapsed_seconds=time.monotonic()-started,
            whole_app_business_accepted=False,Binder_UID_cleanup_verified=False,automatic_rollback=False,
            continuous_runtime_sampling_verified=False,soak_or_stress_verified=False,
            Features10_scope_verified_by_this_result=False,deferred_supported_features=['search','sort'])
        ref=c.write_new(root/'result.json',result)
    return ref,result
