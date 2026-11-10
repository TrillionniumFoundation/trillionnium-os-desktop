#!/usr/bin/python3 -I
"""Read existing Clock due-window logs through the fixed Main session; no UI or mutations."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,gzip,hashlib,json,os,re,types

MODEL=Path('/home/alex/work/pocket4-clock-alarm-tools-20261105-r12-03/read_clock_expired_text02.py')
MODEL_SHA='93a25eacc015e5e87a12a0cd55a9b97c8a7fd7068dd6c691a56b9c77b2a1af6f'
ROOT=Path('/home/alex/work/pocket4-clock-alarm-due-logs-20261105-r12-01')
CLEAN=Path('/home/alex/work/pocket4-clock-alarm-cleanup-20261105-r12-03/result.json')
CLEAN_SHA='320f661f8e471ede5f9dcd46364d36837d8f7d2cb4ec41ad2b1e7317c0b439fc'
PACKAGE='com.android.deskclock'
WINDOW=re.compile(r'^11-05 (?:18:(?:49|5[0-9])|19:0[0-3]):')
OWN=re.compile(r'com\.android\.deskclock|\bu0a63\b|\b10063\b|content://com\.android\.deskclock/instances/1')

def need(ok,why):
    if not ok:raise RuntimeError(why)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def read(session,tx,label,argv,kind):
    raw=session.android(argv,20);need(len(raw)<=4*1024*1024,'LOG_RESPONSE_BOUND')
    tx.write_new(ROOT/(label+'-private.txt'),raw)
    text=raw.decode('utf-8','strict');lines=text.splitlines()
    item={'argv':argv,'bytes':len(raw),'sha256':sha(raw),'private_path':str(ROOT/(label+'-private.txt'))}
    if kind=='small':
        need(len(raw)<=16384,'SMALL_METADATA_BOUND');item['text']=text
    else:
        selected=[line for line in lines if WINDOW.search(line) and (kind=='uid' or OWN.search(line))]
        stamps=[line[:18] for line in lines if re.match(r'^\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}',line)]
        item.update(selected_lines=selected[:240],selected_count=len(selected),
            selected_truncated=len(selected)>240,first_timestamp=stamps[0] if stamps else None,
            last_timestamp=stamps[-1] if stamps else None,
            historical_window='2026-11-05 18:49:00 through 19:03:59 GMT',
            absence_does_not_prove_no_dispatch=True)
    return item

def execute():
    need(os.geteuid()==0,'ROOT_READER_REQUIRED')
    raw=MODEL.read_bytes();need(sha(raw)==MODEL_SHA,'FIXED_MODEL_CHANGED')
    model=types.ModuleType('alarm_due_model');model.__file__=str(MODEL)
    exec(compile(raw,str(MODEL),'exec'),model.__dict__);tx=model.load_session()
    need(model.SOURCE_SHA=='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
        and tx.ACTIVATION_SHA=='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615',
        'ORIGINAL_STRICT_RESOURCE_PROFILE_REQUIRED')
    cleaned=json.loads(tx.read_regular(CLEAN,CLEAN_SHA,maximum=256*1024))
    need(cleaned['cleanup_verified'] is True and cleaned['state']=='EXACT_ALARM03_FIXTURE_REMOVED'
        and all(cleaned[k] is None for k in ('pending','close_pending','effect_pending')),'SAVED_CLEANUP_NOT_COMPLETE')
    os.sched_setaffinity(0,{20});os.umask(0o077);ROOT.mkdir(mode=0o750);os.chown(ROOT,0,1000);os.chmod(ROOT,0o750)
    result={'state':'CLOCK_ALARM_DUE_READ_ONLY','started_utc':datetime.now(timezone.utc).isoformat(),
        'cleanup_source_sha256':CLEAN_SHA,'UI_actions':0,'SQL_writes':0,'provider_writes':0,
        'permission_changes':0,'service_restarts':0,'time_changes':0,'commands':{},'automatic_retry':False}
    with tx.CameraSession(ROOT/'commands') as session:
        result['guard_before']=session.guard();result['identity_before']=model.identity(session)
        need(result['identity_before']==cleaned['identity_before'],'CURRENT_CLOCK_IDENTITY_CHANGED')
        initial=model.state(session);model.verify_before(initial);need(model.baseline_ids(initial)=={1,2},'ORIGINAL_ALARM_SET_CHANGED')
        result['alarm_state_before']=initial
        specs=[('clock-uid-log',['/system/bin/logcat','-b','main','-b','system','-b','crash','-d','-v','threadtime','--uid=10063','-t','4000'],'uid'),
            ('service-system-log',['/system/bin/logcat','-b','system','-b','main','-d','-v','threadtime','-t','5000','-s','AlarmManager:V','AlarmManagerService:V','ActivityManager:I','AppOps:I','AndroidRuntime:E'],'own'),
            ('clock-events',['/system/bin/logcat','-b','events','-d','-v','threadtime','-t','5000'],'own')]
        for operation in ('SCHEDULE_EXACT_ALARM','RUN_IN_BACKGROUND','RUN_ANY_IN_BACKGROUND'):
            specs.append(('appop-'+operation.lower(),['/system/bin/cmd','appops','get','--user','0',PACKAGE,operation],'small'))
        for label,argv,kind in specs:
            try:result['commands'][label]=read(session,tx,label,argv,kind)
            except Exception as error:result['commands'][label]={'error':type(error).__name__+': '+str(error),'automatic_retry':False}
        result['identity_after']=model.identity(session);need(result['identity_after']==result['identity_before'],'CLOCK_IDENTITY_CHANGED_DURING_READ')
        result['alarm_state_after']=model.state(session);need(result['alarm_state_after']==initial,'ALARM_STATE_CHANGED_DURING_READ')
        session.caller_status('alarm-due-read-final-caller');result['guard_after']=session.guard()
        result['finished_utc']=datetime.now(timezone.utc).isoformat()
        published=tx.write_new(ROOT/'result.json',result,alex_readable=True)
        final=tx.read_regular(ROOT/'result.json',published['sha256'],maximum=512*1024)
        packed=gzip.compress(final,mtime=0);need(len(packed)<=64*1024,'SELECTED_LOG_BUNDLE_BOUND')
        archive=tx.write_new(ROOT/'result.json.gz',packed,alex_readable=True)
    print(json.dumps({'state':result['state'],'result':published,'gzip':archive,
        'selected_counts':{k:v.get('selected_count') for k,v in result['commands'].items()},
        'command_errors':{k:v['error'] for k,v in result['commands'].items() if 'error' in v},
        'UI_actions':0,'provider_writes':0},sort_keys=True))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collect',action='store_true')
    if p.parse_args().collect:execute()
    else:print('{"state":"INERT","UI_actions":0,"provider_writes":0}')
