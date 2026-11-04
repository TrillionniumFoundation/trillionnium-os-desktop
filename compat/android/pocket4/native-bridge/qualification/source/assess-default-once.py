"""Strict attribution for an owned default-alarm nonce with one durable native executor.

Every matching raw line is retained and classified. A framework-created process may
only report relaunch-refused; it may never load or invoke the native probe.
"""
import re

def tokens(line):
 pairs=[s.split('=',1) for s in line.split()]
 assert pairs and all(len(p)==2 for p in pairs)
 row=dict(pairs);assert len(row)==len(pairs)
 return row

def collect(raw,nonce,uid,since,package):
 records=[];starts=[];launches=[]
 for line in raw.decode('utf-8','strict').splitlines():
  if 'run_id='+nonce in line:
   m=re.fullmatch(r'\s*(\d+\.\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+I\s+NativeOracleV8\s*:\s*(.*)',line)
   assert m,'default nonce log header malformed'
   assert float(m[1])>=since and m[2] in (str(uid),'u0_a'+str(uid-10000))
   row=tokens(m[5])
   assert row['run_id']==nonce and row['mode']=='default-alarm'
   assert int(row['pid'])==int(m[3]) and int(row['uid'])==uid and int(row['start_ticks'])>0
   assert row.get('phase')!='exception','owned default probe exception'
   records.append({'epoch':float(m[1]),'pid':int(m[3]),'uid':uid,'start_ticks':int(row['start_ticks']),'payload':m[5],'fields':row,'raw':line})
  if package not in line:continue
  head=re.match(r'^\s*(\d+\.\d+)\s+',line)
  if not head or float(head[1])<since:continue
  m=re.search(r'\bam_proc_start:\s*\[0,(\d+),(\d+),'+re.escape(package)+r',([^,]+),',line)
  if m:
   assert int(m[2])==uid
   starts.append({'epoch':float(head[1]),'pid':int(m[1]),'reason':m[3],'raw':line})
  if 'ActivityTaskManager: START ' in line and 'cmp='+package+'/.MainActivity' in line:
   assert 'from uid 2000 ' in line
   launches.append(line)
 assert len(starts)==len(set(x['pid'] for x in starts)),'duplicate actual process start record'
 assert len(launches)<=1,'more than one host activity launch'
 return {'records':records,'process_starts':starts,'host_launches':launches}

def assess(collected,nonce,uid,arm,base_assess):
 rows=collected['records'];claims=[r for r in rows if r['fields']['phase']=='claim-acquired']
 assert len(claims)<=1,'more than one durable execution claim'
 if not claims:return None
 owner=claims[0];pid=owner['pid'];start=owner['start_ticks']
 claim=owner['fields']
 assert int(claim['owner_pid'])==pid and int(claim['owner_uid'])==uid and int(claim['owner_start_ticks'])==start
 expected=['claim-acquired','before-load','loaded','before-native']+(['result','complete'] if arm=='r14' else [])
 own=[r for r in rows if r['pid']==pid]
 assert own[0] is owner and all(r['start_ticks']==start for r in own),'owner process identity changed'
 own_phases=[r['fields']['phase'] for r in own]
 assert own_phases==expected[:len(own_phases)] and len(own_phases)<=len(expected),'unexpected owner phase or repeated native execution'
 refused=[r for r in rows if r['pid']!=pid]
 assert len(refused)==len(set(r['pid'] for r in refused)),'repeated lifecycle event in one refusing process'
 for row in refused:
  r=row['fields']
  assert r['phase']=='relaunch-refused','non-owner loaded or executed native probe'
  assert int(r['owner_pid'])==pid and int(r['owner_uid'])==uid and int(r['owner_start_ticks'])==start
  assert row['epoch']>=owner['epoch'] and row['start_ticks']>=start
 assert arm!='r14' or not refused,'R14 ignored default signal unexpectedly caused lifecycle replay'
 observed={r['pid'] for r in rows};started={r['pid'] for r in collected['process_starts']}
 assert observed.issubset(started),'nonce process lacks an actual ActivityManager start'
 if len(own_phases)!=len(expected) or started!=observed or len(collected['host_launches'])!=1:return None
 native=[r['payload'] for r in own[1:]]
 assessment=base_assess(8,native,nonce,pid,uid,arm,'default-alarm')
 return {'assessment':assessment,'owner_pid':pid,'owner_uid':uid,'owner_start_ticks':start,'native_executor_pids':[pid],'all_nonce_pids':sorted(observed),'all_activity_manager_pids':sorted(started),'relaunch_refused':[{'pid':r['pid'],'uid':uid,'start_ticks':r['start_ticks'],'owner_pid':pid,'owner_uid':uid,'owner_start_ticks':start} for r in refused],'nonce_payloads':[r['payload'] for r in rows],'one_host_launch_only':True}
