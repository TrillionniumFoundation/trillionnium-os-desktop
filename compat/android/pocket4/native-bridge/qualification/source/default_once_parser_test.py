"""Synthetic attribution unit tests; these are not Android execution evidence."""
from pathlib import Path
import copy,json,hashlib,re,os
C=Path(__file__).resolve().parent
base={};exec(compile((C/'assess-v2.py').read_bytes(),'base-assessor','exec'),base)
once={};exec(compile((C/'assess-default-once.py').read_bytes(),'once-assessor','exec'),once)
nonce='0123456789abcdef0123456789abcdef';uid=10114;pkg='local.pocket4.nativeoraclev8'
prefix='run_id='+nonce+' mode=default-alarm pid=5557 uid=10114 start_ticks=100 '
am1='2000.001 1000 822 859 I am_proc_start: [0,5557,10114,'+pkg+',top-activity,{'+pkg+'/'+pkg+'.MainActivity}]'
am2='2000.051 1000 822 859 I am_proc_start: [0,5583,10114,'+pkg+',top-activity,{'+pkg+'/'+pkg+'.MainActivity}]'
launch='2000.000 1000 822 859 I ActivityTaskManager: START u0 {cmp='+pkg+'/.MainActivity (has extras)} with LAUNCH_MULTIPLE from uid 2000 (com.android.shell)'
def log(pid,at,message):return str(at)+' 10114 '+str(pid)+' '+str(pid)+' I NativeOracleV8: '+message
native=[
 log(5557,2000.01,prefix+'phase=claim-acquired owner_pid=5557 owner_uid=10114 owner_start_ticks=100'),
 log(5557,2000.02,prefix+'phase=before-load'),
 log(5557,2000.03,prefix+'phase=loaded initial_alarm=0'),
 log(5557,2000.04,prefix+'phase=before-native case=5')]
refusal=log(5583,2000.06,'run_id='+nonce+' mode=default-alarm pid=5583 uid=10114 start_ticks=101 phase=relaunch-refused owner_pid=5557 owner_uid=10114 owner_start_ticks=100')
lines=[launch,am1,*native,am2,refusal]
def evaluate(lines):
 c=once['collect'](('\n'.join(lines)+'\n').encode(),nonce,uid,1999.0,pkg)
 return once['assess'](c,nonce,uid,'r15',base['assess'])
expected=evaluate(lines)
assert expected['native_executor_pids']==[5557] and expected['all_nonce_pids']==[5557,5583] and expected['relaunch_refused'][0]['pid']==5583
cases={
 'duplicate_claim':lines+[native[0]],
 'nonowner_load':lines+[log(5583,2000.07,'run_id='+nonce+' mode=default-alarm pid=5583 uid=10114 start_ticks=101 phase=before-load')],
 'wrong_refusal_owner':lines[:-1]+[refusal.replace('owner_start_ticks=100','owner_start_ticks=102')],
 'owner_start_changed':[x.replace('phase=loaded initial_alarm=0','phase=loaded initial_alarm=0').replace('start_ticks=100 phase=loaded','start_ticks=102 phase=loaded') for x in lines],
 'exception':lines+[log(5583,2000.07,'run_id='+nonce+' mode=default-alarm pid=5583 uid=10114 start_ticks=101 phase=exception type=java.lang.Error')],
 'two_host_launches':lines+[launch],
 'wrong_header_uid':[x.replace('2000.03 10114','2000.03 10115') for x in lines],
 'ignored_alarm_on_r15':[x.replace('initial_alarm=0','initial_alarm=1') for x in lines],
 'returned_after_default':[x for x in lines]+[log(5557,2000.07,prefix+'phase=result case=5 returned=0')],
 'missing_refuser_AM':[x for x in lines if x!=am2],
}
results=[]
for name,variant in cases.items():
 try:evaluate(variant)
 except (AssertionError,KeyError,ValueError):results.append({'case':name,'rejected':True})
 else:raise AssertionError('negative accepted: '+name)
pending=lines+['2000.071 1000 822 859 I am_proc_start: [0,5599,10114,'+pkg+',top-activity,{'+pkg+'/'+pkg+'.MainActivity}]']
assert evaluate(pending) is None
assert evaluate([launch,am1]) is None
record={'schema':'pocket4-default-once-parser-unit-v1','fixture_kind':'SYNTHETIC_NOT_ANDROID_EXECUTION','positive_attribution':expected,'negative_cases':results,'unattributed_started_PID_returns_incomplete':True,'missing_claim_returns_incomplete':True,'source_sha256':{name:hashlib.sha256((C/name).read_bytes()).hexdigest() for name in ('assess-default-once.py','assess-v2.py')},'state':'PASS_1_SYNTHETIC_POSITIVE_10_REJECTIONS_2_INCOMPLETE_CONTROLS'}
path=C/'default-once-parser-unit-result.json';fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o444)
with os.fdopen(fd,'w') as f:json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
print(json.dumps({'state':record['state'],'actual_android_test':False,'negative_count':len(results),'receipt':str(path)}))
