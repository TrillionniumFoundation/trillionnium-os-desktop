"""One-shot fresh Settings controller; source or partial pages cannot grant app acceptance."""
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import time

class CaseInterrupted(BaseException):
    pass

def stamp():
    return datetime.now(timezone.utc).isoformat()

def diagnostics(session, label):
    raw = session.android(['/system/bin/date', '+%s'],8).decode('utf-8','strict').strip()
    session.c.need(raw.isdecimal() and abs(time.time()-int(raw)) <= 3, 'ACTUAL_GUEST_DIAGNOSTIC_CLOCK')
    value = {'guest_seconds':int(raw)}
    for name, argv in [('exits',['/system/bin/dumpsys','activity','exit-info','com.android.settings']),
            ('events',['/system/bin/logcat','-b','events','-d','-v','epoch','-t','2048'])]:
        output = session.android(argv,15)
        session.c.need(len(output) <= 4*1024*1024,'BOUNDED_SETTINGS_DIAGNOSTIC')
        value[name] = output.decode('utf-8','strict')
    session.components['settings_diagnostics.py'].exit_events(value['exits'])
    value['evidence'] = session.record(label, value)
    return value

def permissions(session, label):
    raw = session.android(['/system/bin/dumpsys','package','com.android.settings'],20).decode('utf-8','strict')
    rows = session.model.permission_rows(raw)
    session.record(label,{'raw':raw,'permission_rows':rows,'shared_UID_does_not_identify_foreign_processes':True})
    session.flow.artifacts.revalidate()
    return rows

def execute(c, base_ref, components):
    c.need(os.getuid() == os.geteuid() == 0,'ROOT_EXPLICIT_FRESH_SETTINGS_EXECUTION')
    base = c.parse(c.read_ref(base_ref)); plan = components['settings_plan.py']; runtime = components['settings_runtime.py']
    host = components['app_runtime.py']; _, support = c.support(base['support_manifest'])
    baseline = support['business_baseline.py'].BusinessBaseline(base['baseline'],base['qualification'])
    plan.validate(c,base,baseline); root = c.private_dir(base['case_root'])
    c.write_new(root/'execute-once.json',{'plan':base_ref,'operator':host.process(c,os.getpid()),
        'started_utc':stamp(),'automatic_retry':False})
    evidence = c.private_dir(root/'evidence',create=True)
    result = {'schema':'pocket4-final-settings-case-result-v1','state':'FAILED','kind':base['kind'],
        'plan':base_ref,'started_utc':stamp(),'case_business_success_verified':False,
        'original_gates':dict(base['original_business_checks']), 'satisfied_original_gates':[],
        'whole_app_business_accepted':False,'automatic_retry':False,'secondary_errors':[],
        'permission_writes':0,'account_operations':0,'package_mutations':0,'network_configuration_writes':0,
        'direct_setting_writes':0,'shared_UID_is_package_identity':False,
        'continuous_sampling_or_soak_credit':False,'original_full_app_gates_unchanged':True}
    session = driver = lock = witness = None; first = None; retiring = False; signals = []
    def interrupted(signum, frame):
        nonlocal retiring
        signals.append(signum)
        if not retiring:
            retiring = True
            raise CaseInterrupted('SETTINGS_CANCELLED_NO_REPLAY')
    def remember(phase, error):
        nonlocal first
        item = {'phase':phase,'type':type(error).__name__,'message':str(error)}
        if first is None: first=error; result['error']=item
        else: result['secondary_errors'].append(item)
    try:
        for signum in (signal.SIGINT,signal.SIGTERM): signal.signal(signum,interrupted)
        lock=runtime.ActionLock(c,host,root); lease=runtime.create_lease(c,host,base_ref,base)
        active_ref,scopes=plan.activate(c,base_ref,lease,lock.ref); active=c.parse(c.read_ref(active_ref))
        phase=runtime.phase(c,host,active_ref,active,'business')
        witness=c.EvidenceWitness([base_ref,active_ref,lease,lock.ref,*scopes])
        session=components['settings_session.py'].Session(c,active_ref,active,scopes,phase,lock,components,evidence)
        driver=components['settings_driver.py'].Driver(session,result)
        result.update(active_plan=active_ref,recorder_scopes=scopes,actual_business_phase=phase)
        try:
            permission_before=permissions(session,'before-permissions'); before=diagnostics(session,'before-diagnostics')
            driver.run()
            after=diagnostics(session,'after-diagnostics')
            result['diagnostics']=components['settings_diagnostics.py'].compare(before,after)
            c.need(result['diagnostics']['clear'],'FRESH_SETTINGS_PROCESS_CRASH_ANR_OR_EXIT')
            c.need(permissions(session,'after-permissions')==permission_before,'ACTUAL_SETTINGS_PERMISSIONS_CHANGED')
            result['actual_permissions_unchanged']=True
        except BaseException as error:
            remember('actual_settings_case',error)
        finally:
            retiring=True
            try:
                trigger=c.write_new(root/'cleanup-trigger.json',{'error':result.get('error'),
                    'case_scope_completed':result.get('case_scope_completed') is True,'started_utc':stamp(),
                    'automatic_retry':False})
                result['actual_cleanup_phase']=session.begin_cleanup(trigger); driver.cleanup()
                roots,tasks,ref=session.stacks('final-task-set')
                c.need(tasks==session.baseline_tasks and roots==session.baseline_roots,'ALL_PREEXISTING_TASKS_PRESERVED')
                result['final_tasks']=ref;result['guard_after']=session.guard()
                if base['kind']=='settings_roundtrip' and driver.preimage is not None:
                    final=driver.read_rotation('final-restored-rotation')
                    c.need(driver.rotation_values(final)==driver.rotation_values(driver.preimage),'ORIGINAL_ROTATION_DRIFTED_AFTER_TASK_RETIREMENT')
                    result['final_rotation_preimage_verified']=True
            except BaseException as error:
                remember('bounded_settings_restore_and_owned_cleanup',error)
    except BaseException as error:
        remember('case_admission_or_construction',error)
    finally:
        retiring=True
        for obj,label in ((session,'actual_Main_and_UI'),(lock,'whole_case_OFD'),(witness,'evidence_witness')):
            if obj is not None:
                try:obj.close();result[label+'_closed']=True
                except BaseException as error:remember(label+'_close',error)
        try:
            result['independent_Main_after']=baseline.guard();plan.validate(c,base,baseline)
            result['final_source_and_identity_chain_unchanged']=True
        except BaseException as error:
            remember('independent_final_Main_or_source_chain',error)
        # Explicit one-shot process boundary. The entry exits after durable
        # publication; this function must not be embedded in a long-lived host.
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        pending=sorted(signal.sigpending() & {signal.SIGINT,signal.SIGTERM})
        if signals or pending:remember('cancelled_before_terminal_commit',CaseInterrupted('SETTINGS_CANCELLED_BEFORE_COMMIT'))
        result['cancellation_commit']={'observed_before_commit':list(signals),'pending_at_commit':pending,
            'decision_frozen_after_context_exit':True,'one_shot_process_exit_required':True}
        if driver is not None:
            result.update(UI_actions=driver.actions,page_route_calls=driver.routes,pending_input=driver.pending,
                native_launch_calls=session.native_launches,native_tasks=session.native_tasks,
                closed_native_tasks=session.closed_native_tasks,known_owned_remove_calls=session.remove_calls,
                owned_task_remaining=session.primary_task,rotation_delta_remaining=driver.dirty,
                rotation_preimage=driver.preimage,rotation_restored=driver.restored,
                unknown_input_not_resolved_by_cleanup=driver.pending is not None)
            clean=bool(result.get('case_scope_completed') and result.get('actual_permissions_unchanged')
                and result.get('guard_after') and driver.pending is None and not driver.dirty
                and session.native_tasks==session.closed_native_tasks and len(set(session.native_tasks))==2
                and session.primary_task is None and first is None and not result['secondary_errors'] and not signals and not pending)
            gate={'settings_pages':'settings.pages','settings_permissions':'settings.permissions',
                'settings_roundtrip':'settings.roundtrip'}[base['kind']]
            observed=(base['kind']=='settings_pages' or base['kind']=='settings_permissions'
                and result.get('actual_permission_error_branch_observed') is True or base['kind']=='settings_roundtrip'
                and result.get('reopened_rotation_persistence_verified') is True and driver.restored
                and result.get('final_rotation_preimage_verified') is True)
            result['case_business_success_verified']=bool(clean and observed)
            if result['case_business_success_verified']:result['satisfied_original_gates']=[gate]
            elif clean and base['kind']=='settings_permissions':result['pending_original_gates']=['settings.permissions:error handling']
        result['state']='ACTUAL_SETTINGS_CASE_VERIFIED_CLEAN' if result['case_business_success_verified'] else 'FAILED_OR_INCOMPLETE_RETAINED'
        result.update(finished_utc=stamp(),received_signals=signals,whole_app_business_accepted=False,
            Binder_UID_cleanup_verified=False,automated_rollback=False)
        ref=c.write_new(root/'result.json',result)
    return ref,result
