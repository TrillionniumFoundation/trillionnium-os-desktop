"""Dedicated once-only current-Main entry for the preserved Features10 scope.

Publication is not execution authority. Success requires all original twelve
business predicates plus original search/sort and exact cleanup, actual final Main, and no cancellation
before the terminal commit. SAF11 and common soak stay separate; no whole-app acceptance is implied.
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
    ui=types.SimpleNamespace(Adapter=lambda *a:components['documents_features_ui.py'].DocumentsFeaturesUI(*a,scope=names))
    package=types.SimpleNamespace(PackageFixture=lambda *a:components['documents_package_fixture.py'].DocumentsPackageFixture(*a,scope=names,artifacts=artifacts))
    tree=types.SimpleNamespace(OwnedTree=lambda *a:components['documents_owned_tree.py'].DocumentsOwnedTree(*a,scope=names))
    flow=components['documents_features_core.py'].DocumentsFeaturesFlow(session,session.tx,ui,package,tree,
        components['documents_runtime_evidence.py'],components['documents_diagnostics.py'],scope=names,
        search_sort=components['documents_search_sort.py'])
    session.case=flow;return flow


def execute(c,plan_ref,prep_ref,components):
    c.need(os.getuid()==os.geteuid()==0,'ROOT_EXPLICIT_DOCUMENTS_CASE_EXECUTION')
    planner=components['documents_plan.py']
    plan,source,baseline,identities,packet,task,names,build=planner.validate_plan(c,plan_ref,prep_ref)
    # Even a direct call must admit the currently loaded implementation against
    # the external frozen packet; task self-reported hashes do not suffice.
    by_name={Path(r['path']).name:r for r in task['files']}
    c.need(set(components)=={n for n in by_name if n.endswith('.py')},'COMPLETE_CURRENT_DOCUMENTS_MODULE_SET')
    for name,module in components.items():
        c.need(c.regular(module.__file__,contents=False)==by_name[name],'LOADED_CODE_NOT_ADMITTED_CASE_COPY')
    root=c.private_dir(plan['case_root']);started=time.monotonic();business_deadline=started+750
    host=components['app_runtime.py'];c.write_new(root/'execute-once.json',{'schema':'pocket4-documents-once-execution-v1',
        'plan':plan_ref,'operator':host.process(c,os.getpid()),'started_utc':stamp(),'business_deadline_monotonic':business_deadline,
        'absolute_final_deadline_monotonic':business_deadline+150,'automatic_retry':False})
    c.private_dir(root/'ui',create=True)
    result={'schema':'pocket4-final-documents-original-case-result-v1','state':'FAILED_BEFORE_SESSION','plan':plan_ref,
        'source_preparation':prep_ref,'started_utc':stamp(),'case_business_success_verified':False,
        'whole_app_business_accepted':False,'automatic_retry':False,'secondary_errors':[]}
    session=flow=lock=witness=None;first=None;retiring=False;signals=[];saved={}
    def interrupted(signum,frame):
        nonlocal retiring
        signals.append(signum)
        if not retiring:
            retiring=True;raise CaseInterrupted('DOCUMENTS_CASE_CANCELLED')
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
        actual_names=components['documents_names.py'].FeaturesNames(names.RUN,root)
        cls=components['documents_session.py'].make_session_class(components['documents_transport_base.py'])
        session=cls(c,{**source,'pm_help':plan['pm_help']},root,components,lock,source_guard,business_deadline,
                    actual_names,artifacts,identities)
        flow=construct(session,components,actual_names,artifacts)
        flow.result.update(result);result=flow.result
        result['actual_business_phase']=session.phase_ref
        try:flow.business()
        except BaseException as error:remember('original_business',error);result['business_scope_completed']=False
        finally:
            retiring=True
            try:
                trigger=c.write_new(root/'cleanup-trigger.json',{'actual_business_error':result.get('error'),
                    'original_scope_completed':result.get('business_scope_completed') is True,'automatic_retry':False,'at_utc':stamp()})
                session.begin_cleanup(trigger);result['actual_cleanup_phase']=session.phase_ref
                result['cleanup']=flow.cleanup()
                try:
                    flow.final_checks();result['actual_final_caller']=session.caller_status('documents-features-final-caller')
                except BaseException as error:remember('original_final_evidence',error)
            except BaseException as error:remember('original_final_cleanup',error)
    except BaseException as error:remember('case_admission_or_construction',error)
    finally:
        retiring=True
        # Business cleanup may have stopped at any statement. Independently
        # retire local owned FDs without retrying it or deleting retained data.
        if flow is not None:
            for label,close in (('owned_tree_FDs',flow.tree.close),('helper_stage_FDs',flow.pkg.release_local_handles)):
                try:
                    close();result[label+'_closed']=True
                except BaseException as error:
                    remember(label+'_close',error)
        for obj,label in ((session,'actual_Main_and_APIs'),(lock,'whole_case_OFD'),(witness,'source_and_receipt_witness')):
            if obj is not None:
                try:obj.close();result[label+'_closed']=True
                except BaseException as error:remember(label+'_close',error)
        try:
            result['independent_Main_after']=baseline.guard()
            planner.validate_plan(c,plan_ref,prep_ref)
            result['final_source_and_identity_chain_unchanged']=True
            c.need(time.monotonic()<=business_deadline+150,'ORIGINAL_DOCUMENTS_ABSOLUTE_900_SECONDS')
        except BaseException as error:remember('independent_final_Main_and_source_chain',error)
        # This routine belongs only to the dedicated entry process. Preserve
        # the cancellation decision through result serialization and entry exit.
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        pending=sorted(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
        if signals or pending:remember('cancelled_before_terminal_commit',CaseInterrupted('DOCUMENTS_CANCELLED_BEFORE_TERMINAL_COMMIT'))
        result['cancellation_commit']={'observed_before_commit':list(signals),'pending_at_commit':pending,
            'decision_frozen_after_context_exit':True}
        if flow is not None:
            result.update(ui_actions=flow.ui.actions,native_launch_calls=flow.ui.launches,owned_remove_calls=flow.ui.removals,
                owned_task_ids_closed=flow.ui.closed,source_bound_adopted_tasks=flow.ui.adopted,owned_tasks=flow.ui.owned,
                ui_pending=flow.ui.pending,file_operation_pending=flow.operation_pending,helper_pending=flow.helper_pending,
                install_pending=flow.pkg.install_pending,uninstall_pending=flow.pkg.uninstall_pending,
                original_search_sort_state=flow.search_sort.state(),
                outcome_unknown=bool(flow.ui.pending or flow.operation_pending or flow.helper_pending or flow.pkg.install_pending
                    or flow.pkg.uninstall_pending or session.host_retirement_unknown),
                actual_task_claims=session.claimed_tasks,actual_launch_receipts=session.launch_receipts,
                retained_host_receipts=session.records,host_cancellation_observed=session.host_cancelled)
            clean=result.get('cleanup',{});file_clean=clean.get('file_cleanup') or {};package_clean=clean.get('package') or {}
            stage=clean.get('stage') or {};required=components['documents_profiles.py'].REQUIRED_GATES
            complete=bool(result.get('business_scope_completed') and set(result.get('gates',{}))==required
                and all(row.get('passed') is True for row in result.get('gates',{}).values()) and not clean.get('errors',[True])
                and package_clean.get('package_absent_verified') is True and package_clean.get('data_directories_absent') is True
                and file_clean.get('removed') is True and file_clean.get('fallback_files_unlinked')==0
                and stage.get('staged_apk_removed') is True and result.get('task_set_restored') is True
                and flow.ui.launches==3 and flow.ui.removals==len(flow.ui.closed)==3+len(flow.ui.adopted)
                and flow.ui.actions<=80 and not flow.ui.owned and not result['outcome_unknown']
                and result.get('final_guard')==result.get('initial_guard') and result.get('actual_final_caller')
                and not session.host_cancelled)
            result['case_business_success_verified']=bool(complete and first is None and not signals and not pending
                and not result['secondary_errors'])
        result['state']='ORIGINAL_FEATURES_SEARCH_SORT_VERIFIED_CLEAN' if result['case_business_success_verified'] else 'FAILED_OR_UNKNOWN_RETAINED'
        result.update(received_signals=signals,finished_utc=stamp(),elapsed_seconds=time.monotonic()-started,
            whole_app_business_accepted=False,Binder_UID_cleanup_verified=False,automatic_rollback=False,
            continuous_runtime_sampling_verified=False,soak_or_stress_verified=False,
            deferred_supported_features=[name for name,done in [('search',bool(flow and flow.search_sort.search_completed)),
                ('sort',bool(flow and flow.search_sort.sort_completed))] if not done],SAF11_scope_verified_by_this_result=False)
        ref=c.write_new(root/'result.json',result)
    return ref,result
