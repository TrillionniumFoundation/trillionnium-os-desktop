"""Two fresh Settings launches and five actual read-only page observations.

Only settings.pages can be credited by this case. Setting round trips,
permission-management UI, and the six whole-app gates remain independent.
"""
import copy
from datetime import datetime,timezone
import os
from pathlib import Path
import signal


class Interrupted(BaseException):pass
def stamp():return datetime.now(timezone.utc).isoformat()


def execute(c,base_ref,modules,release,resources):
    c.need(os.getuid()==os.geteuid()==0,'ROOT_NEW_SETTINGS_CASE_REQUIRED')
    plan=modules['settings_plan.py'];runtime=modules['settings_runtime.py']
    host=modules['app_runtime.py'];identity=modules['settings_identity.py'];pages=modules['settings_pages.py']
    base=c.parse(c.read_ref(base_ref));_,support=c.support(base['support_manifest'])
    baseline=support['business_baseline.py'].BusinessBaseline(base['baseline'],base['qualification'])
    prepared,profile=plan.validate(c,base,baseline)
    release.guard();runtime.resource_report(c,resources)
    root=c.private_dir(base['case_root'])
    c.write_new(root/'execute-once.json',{'plan':base_ref,'operator':host.process(c,os.getpid()),
        'started_utc':stamp(),'automatic_retry':False},0o400)
    result={'schema':'pocket4-settings-pages-case-result-v1','state':'FAILED',
        'base_plan':base_ref,'started_utc':stamp(),'scope':'settings.pages','pages':[],
        'launches':[],'normal_closes':[],'case_business_success_verified':False,
        'whole_app_business_accepted':False,'automatic_retry':False,'secondary_errors':[],
        'setting_writes':0,'permission_writes':0,'account_writes':0,'package_writes':0,
        'remaining_gates':list(profile.REMAINING_GATES),'Android_runtime_qualification_inferred_from_source':False}
    session=flow=witness=None;first=None;signals=[];retiring=False;closed_flows=[];saved={}
    def remember(label,error):
        nonlocal first
        item={'phase':label,'type':type(error).__name__,'message':str(error)}
        if first is None:first=error;result['error']=item
        else:result['secondary_errors'].append(item)
    def interrupted(signum,frame):
        nonlocal retiring
        signals.append(signum)
        if not retiring:retiring=True;raise Interrupted('SETTINGS_CASE_CANCELLED')
    def close_host():
        nonlocal flow
        if flow is not None:
            ref=flow.scope_ref
            try:flow.close();closed_flows.append(ref)
            finally:flow=None
    try:
        for signum in (signal.SIGINT,signal.SIGTERM):saved[signum]=signal.signal(signum,interrupted)
        lease_ref=runtime.create_lease(c,host,base_ref,base)
        active_ref,scopes=plan.activate(c,base_ref,lease_ref);active=c.parse(c.read_ref(active_ref))
        lease=c.parse(c.read_ref(lease_ref));business_deadline=lease['business_deadline_monotonic_ns']/10**9
        session=runtime.Session(c,active_ref,active,profile,release,resources);session.bind_host(host)
        witness=c.EvidenceWitness([base_ref,active_ref,lease_ref,*scopes])
        result.update(active_plan=active_ref,lease=lease_ref,recorder_scopes=scopes,
                      resource_before=runtime.resource_report(c,resources),Main_before=baseline.guard())
        before_roots=before_tasks=None;before_identity=None
        for index,scope in enumerate(scopes):
            c.need(not retiring and first is None,'SETTINGS_CANCELLED_OR_FAILED_NO_FURTHER_LAUNCH')
            session.guard();witness.verify()
            flow=modules['app_flow.py'].Flow(c,scope,'launch','case-start',business_deadline,
                modules['settings_guard.py'],modules['settings_policy.py'].Policy,
                private_context={'session':session})
            _,roots,tasks=flow.stacks()
            if index==0:
                before_roots=copy.deepcopy(roots);before_tasks=set(tasks)
                before_identity=identity.snapshot(flow,profile)
                result['identity_before']=before_identity
                result['task_baseline']={'roots':before_roots,'task_ids':sorted(before_tasks)}
            else:
                c.need(roots==before_roots and tasks==before_tasks,'SETTINGS_FIRST_TASK_NOT_COMPLETELY_CLOSED')
            launched=flow.launch()
            claim,claim_ref=session.require_owned_task(flow)
            c.need(set(claim['prelaunch_task_ids'])==before_tasks,'SETTINGS_LAUNCH_BASELINE_CHANGED')
            session.task_claims.append(claim_ref);result['launches'].append(launched)
            flow.phase='inspect';flow._new_step('inspect-pages','phase',None,False);flow._bridge();flow.guard()
            home=pages.observe(flow,session,None)
            result['initial_home' if index==0 else 'reopened_home']=home
            if index==0:result['pages']=pages.execute_pages(flow,session)
            session.no_unknown()
            result['normal_closes'].append(session.normal_close(flow))
            _,roots,tasks=flow.stacks()
            c.need(roots==before_roots and tasks==before_tasks,'SETTINGS_COMPLETE_TASK_BASELINE_NOT_RESTORED')
            if index==1:
                after_identity=identity.snapshot(flow,profile)
                result['identity_after']=after_identity
                result['identity_permissions_directories_preserved']=identity.same(c,before_identity,after_identity)
                result['complete_task_baseline_restored']=True
            session.recorded_prefix(flow);close_host()
        result['all_five_pages_observed']=len(result['pages'])==len(profile.PAGES)==5
    except BaseException as error:
        remember('business_or_admission',error)
    finally:
        retiring=True
        # Known effects alone may use the original bounded normal-close path.
        # A route/UI/native outcome without a complete receipt is never replayed
        # or automatically removed. A previous close attempt is never retried.
        if flow is not None and session is not None and flow.scope_ref not in closed_flows:
            try:
                if flow.phase!='cleanup':
                    session.no_unknown();session.recorded_prefix(flow)
                    _,claim=flow.scope_module.load_owned_task(flow.bound)
                    c.need(claim in session.task_claims,'NO_UNCLAIMED_SETTINGS_CLEANUP')
                    result['failure_normal_close']=session.normal_close(flow)
                elif session.cleanup_admission is not None:
                    raise RuntimeError('SETTINGS_CLOSE_OUTCOME_UNKNOWN_NO_RETRY')
            except BaseException as error:
                result['unknown_retained_without_further_mutation']=True
                remember('known_owned_task_cleanup',error)
        try:close_host()
        except BaseException as error:remember('host_Main_or_artifact_FD_close',error)
        if witness is not None:
            try:witness.verify();witness.close();result['evidence_witness_closed']=True
            except BaseException as error:remember('evidence_witness_close',error)
        if session is not None:
            result.update(native_launch_count=len(session.task_claims),
                normally_closed_claims=session.closed_claims,page_route_count=session.page_route_count,
                observation_count=session.observation_count,
                pending_route=session.pending_route,pending_UI=session.current_ui_context,
                native_claims=session.task_claims)
            session.close()
        try:
            release.guard();result['resource_after']=runtime.resource_report(c,resources)
            result['Main_after']=baseline.guard();plan.validate(c,base,baseline)
            c.need(result.get('Main_before')==result['Main_after'],'SETTINGS_FINAL_MAIN_CHANGED')
            result['final_source_identity_chain_unchanged']=True
        except BaseException as error:remember('final_adopted_release_Main_or_source_chain',error)
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        pending=sorted(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
        if signals or pending:remember('cancelled_before_terminal_commit',Interrupted('SETTINGS_CANCELLED_NO_PASS'))
        result['cancellation_commit']={'observed_before_commit':signals,'pending_at_commit':pending,
                                       'decision_frozen_after_host_context_close':True}
        ok=(first is None and not result['secondary_errors'] and not signals and not pending
            and result.get('all_five_pages_observed') is True
            and result.get('identity_permissions_directories_preserved') is True
            and result.get('complete_task_baseline_restored') is True
            and result.get('final_source_identity_chain_unchanged') is True
            and result.get('evidence_witness_closed') is True
            and session is not None and session.task_claims==session.closed_claims
            and len(session.task_claims)==len(closed_flows)==2
            and session.page_route_count==5 and session.observation_count==7
            and session.pending_route is None and session.current_ui_context is None
            and session.cleanup_admission is None)
        result['case_business_success_verified']=bool(ok)
        result['accepted_gates']=['settings.pages'] if ok else []
        result['state']='SETTINGS_PAGES_VERIFIED_CLEAN' if ok else 'FAILED_OR_UNKNOWN_RETAINED'
        result.update(finished_utc=stamp(),whole_app_business_accepted=False,Binder_UID_cleanup_verified=False,
                      host_flow_contexts_closed=closed_flows)
        result_ref=c.write_new(root/'result.json',result)
    return result_ref,result
