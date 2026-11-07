#!/usr/bin/python3 -I
"""One new expiry after the already-passed current-binary core; no core replay."""
from pathlib import Path
from datetime import datetime, timezone
import argparse,hashlib,json,signal,time,types

HERE=Path(__file__).resolve().parent
ROOT=Path('/home/alex/work/pocket4-clock-expiry-delivery-20261105-r12-05')
INSTALLER=Path('/home/alex/work/pocket4-clock-expired-text-20261105-r12-02/transaction03/clock_install03.py')
INSTALLER_SHA='0f7d01f428d1b472e48327df66111d22dbd0551dc5a090faf8c4f5627aff1b48'
CURRENT='e4ff4b46a651ff3ac77397705b7b749c7fbaaeb94fe1d00818debb31dea34172'
PINS={'timer_expiry05.py': '0de3eb1792af737e0ade160a3d201db22ff4c9db15eb4084b1016d3acf099703', 'read_clock_expired_text02.py': '6f996dc4d8544d54520c76121308d7dba0cdbd58bbeda9a06fd84889dc3373b6'}
CORE_RESULT=Path('/home/alex/work/pocket4-clock-delivery-tools-20261105-r12-03/clock-timer03-result.json')
CORE_RESULT_SHA='ed01ff52b5dfee169a1218e23836ebe5eb6392cf8e589d3082fd172bc1223c6d'


def need(ok,why):
    if not ok:raise RuntimeError(why)


def stamp():return datetime.now(timezone.utc).isoformat()


def sha(raw):return hashlib.sha256(raw).hexdigest()


def load(path,pin):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'COMBINED_SOURCE_CHANGED')
    module=types.ModuleType('combined_'+Path(path).stem);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module


def deadline(*unused):raise TimeoutError('READ_ONLY_PROTECTED_SNAPSHOT_DEADLINE')


def phase_summary(module,code):
    raw=module.PUBLIC.read_bytes();value=json.loads(raw)
    fields=('state','business_success_verified','error','terminal_error','epoch_sha256',
        'identity_before','identity_after','ui_actions','pending_effect','owned_tasks','closed_tasks',
        'normal_closed_tasks','owned_task_remove_calls','owned_task_remaining','started_utc','finished_utc',
        'standard_title_body_to_host_Notify_observed','expired_desktop_state_removed','task_set_restored')
    out={k:value[k] for k in fields if k in value}
    out.update(return_code=code,result_path=str(module.PUBLIC),result_sha256=sha(raw),result_bytes=len(raw))
    if 'expiry_audio_evidence' in value:
        audio=value['expiry_audio_evidence']
        out['audio_evidence']={k:audio.get(k) for k in (
            'clock_UID_active_track_and_output_progress','nonzero_HAL_power_during_sole_Clock_active_output',
            'recorded_audio_bytes','microphone_access','physical_speaker_audibility_verified','audio_settings_changes')}
    if 'notify_watch_stop' in value:out['notify_watch_stop']=value['notify_watch_stop']
    if 'notify_watch_stop_error' in value:out['notify_watch_stop_error']=value['notify_watch_stop_error']
    for name in ('notify_watch_child_started','notify_monitor_closed_verified'):
        if name in value:out[name]=value[name]
    return out,value


def execute():
    installer=load(INSTALLER,INSTALLER_SHA)
    phases={name:load(HERE/name,pin) for name,pin in PINS.items()}
    model=phases['read_clock_expired_text02.py'];tx=model.load_session()
    timers=installer.load(installer.CLOCK/'read_timer.py',installer.TIMER_SHA)
    expiry=phases['timer_expiry05.py']
    result={'state':'FAILED','started_utc':stamp(),'whole_app_production_ready':False,
        'expected_apk_sha256':CURRENT,'automatic_retry':False,'audio_bytes_recorded':0,
        'microphone_access':False,'global_sound_changes':0,'notification_settings_changes':0,
        'desktop_popup_visual_qualification':False,'physical_speaker_audibility_qualification':False,
        'maximum_work_seconds':360,'source_pins':PINS}
    ROOT.mkdir(mode=0o700);before=None;end=time.monotonic()+360
    prior=signal.signal(signal.SIGALRM,deadline)
    try:
        signal.setitimer(signal.ITIMER_REAL,30)
        with tx.ui_lock(),tx.CameraSession(ROOT/'before-commands') as session:
            before=installer.snapshot(session,tx,model,timers,'before')
            need(before['apk']['sha256']==CURRENT,'CURRENT_INSTALLED_APK_REQUIRED')
            result['before_snapshot_sha256']=sha((session.journal_dir/'before.json').read_bytes())
        signal.setitimer(signal.ITIMER_REAL,0)
        # This exact current-binary core result is an admitted prerequisite,
        # not another UI phase and never re-executed by this controller.
        raw=CORE_RESULT.read_bytes();need(sha(raw)==CORE_RESULT_SHA,'CORE_RESULT_CHANGED')
        core_raw=json.loads(raw)
        need(core_raw['business_success_verified'] is True and core_raw['pending_effect'] is None
            and core_raw['identity_before']['apk_sha256']==CURRENT
            and core_raw['identity_after']['apk_sha256']==CURRENT
            and core_raw['owned_tasks']==core_raw['closed_tasks'] and len(core_raw['closed_tasks'])==2,
            'CURRENT_CORE_PREREQUISITE_UNVERIFIED')
        timers.empty(core_raw['timer_final'])
        result['existing_current_binary_core']={'result_sha256':CORE_RESULT_SHA,
            'started_utc':core_raw['started_utc'],'finished_utc':core_raw['finished_utc'],
            'ui_actions':core_raw['ui_actions'],'owned_task_remove_calls':core_raw['owned_task_remove_calls'],
            'replayed':False}
        need(time.monotonic()+315<end,'INSUFFICIENT_EXPIRY_AND_FINAL_READ_BUDGET')
        code=expiry.execute();result['expiry'],expired_raw=phase_summary(expiry,code)
        watch=expired_raw.get('notify_watch_stop',{})
        result['notify_monitor_cleanup_verified']=expired_raw.get('notify_monitor_closed_verified') is True
        result['own_notify_monitor_joined']=bool(expired_raw.get('notify_watch_child_started') is True
            and result['notify_monitor_cleanup_verified']
            and watch.get('all_owned_monitor_writers_closed') is True
            and watch.get('child_joined') is True and watch.get('reader_joined') is True
            and watch.get('pipe_eof')=={'stdout':True,'stderr':True}
            and watch.get('cleanup_error') is None and not watch.get('errors'))
        need(code==0 and expired_raw['business_success_verified'] is True
            and expired_raw['pending_effect'] is None,'CURRENT_EXPIRY_NOT_COMPLETE')
        timers.empty(expired_raw['timer_final'])
        result['new_expiry_UI_scope_verified']=True
        result['standard_title_body_forwarded_to_host_Notify']=expired_raw.get('standard_title_body_to_host_Notify_observed') is True
        result['expired_host_notification_state_removed']=expired_raw.get('expired_desktop_state_removed') is True
        audio=expired_raw.get('expiry_audio_evidence',{})
        result['UID_track_output_frames_and_nonzero_HAL_power_verified']=bool(
            audio.get('clock_UID_active_track_and_output_progress') is True
            and audio.get('nonzero_HAL_power_during_sole_Clock_active_output') is True)
        result['state']='EXPIRY_UI_COMPLETE_DELIVERY_EVIDENCE_REVIEW_PENDING'
    except BaseException as error:result['error']=type(error).__name__+': '+str(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL,max(.001,min(30,end-time.monotonic())))
        try:
            with tx.ui_lock(),tx.CameraSession(ROOT/'after-commands') as session:
                after=installer.snapshot(session,tx,model,timers,'after')
                result['after_snapshot_sha256']=sha((session.journal_dir/'after.json').read_bytes())
                result['protected_state_preserved']=bool(before is not None and installer.preserved(before,after,include_preferences=False))
                result['final_installed_apk']=after['apk'];result['final_epoch_sha256']=after['epoch_sha256']
                result['timer_and_stopwatch_final_empty']=after['timer_and_stopwatch_empty']
                result['timer_allocation_metadata_excluded_from_byte_identity_claim']=True
                need(after['apk']['sha256']==CURRENT and result['protected_state_preserved'],'PROTECTED_CLOCK_STATE_CHANGED')
                session.caller_status('combined-final-caller');session.guard()
        except BaseException as error:result['final_guard_error']=type(error).__name__+': '+str(error)
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,prior)
        if (result.get('new_expiry_UI_scope_verified') and result.get('own_notify_monitor_joined')
            and result.get('standard_title_body_forwarded_to_host_Notify')
            and result.get('expired_host_notification_state_removed')
            and result.get('UID_track_output_frames_and_nonzero_HAL_power_verified')
            and result.get('protected_state_preserved') and not result.get('final_guard_error')):
            result['state']='CURRENT_EXPIRY_NOTIFY_AND_HAL_OUTPUT_SCOPES_VERIFIED'
        result['finished_utc']=stamp()
        tx.write_new(ROOT/'result.json',result,alex_readable=True)
        tx.write_new(HERE/'clock-expiry-delivery05-result.json',result,alex_readable=True)
        print(json.dumps(result,sort_keys=True))
    return 0 if result['state']=='CURRENT_EXPIRY_NOTIFY_AND_HAL_OUTPUT_SCOPES_VERIFIED' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    if parser.parse_args().execute:raise SystemExit(execute())
    print(json.dumps({'state':'PLAN_ONLY','UI_actions':0,'expected_apk_sha256':CURRENT,'source_pins':PINS}))
