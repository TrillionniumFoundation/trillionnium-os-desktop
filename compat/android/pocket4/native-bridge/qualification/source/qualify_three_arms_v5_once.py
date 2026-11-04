"""Independent, read-only qualification of already completed private arms.
Writes one new receipt; never edits a runtime result or performs Android actions.
"""
from pathlib import Path
import hashlib,json,re,subprocess,os,datetime
ROOT=Path('/srv/pocket4-native-qualification')
MANIFEST_SHA='72d3151d28485f536b9f28b9575b248da92c6b289998e28066a82a8a2f776f67'
ENGINE={'r14':'a74cba50358ab473b4261e33daee98107fb45fcc78110f71599ad38b63822d2c','r15':'a770eda38e27d072f10568b7dee164a429f9eb05261667f7cb3c6f1c10e0d535','r16':'c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d'}
MAIN_LIMITS={'memory.high':'5368709120','memory.max':'6442450944','cpu.max':'200000 100000','memory.swap.max':'max','pids.max':'12288'}
DIRECTORIES={'r14':'r14-r4','r15':'r15-r2','r16':'r16-r2'}
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def package_set(raw):
 names=[]
 for line in raw.decode('utf-8','strict').splitlines():
  m=re.fullmatch(r'package:([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)',line);assert m,('bad package record',line);names.append(m[1])
 assert len(names)==len(set(names));return set(names)
def parse_uid_list(raw):
 records=[]
 for line in raw.decode('utf-8','strict').splitlines():
  m=re.fullmatch(r'package:([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*) uid:(\d+)',line);assert m,('bad UID record',line)
  records.append((m[1],int(m[2])))
 assert len(records)==len({n for n,u in records});return records
def log_payload(path,tag,nonce,pid,uid,earliest):
 output=[]
 for line in path.read_text().splitlines():
  if 'run_id='+nonce not in line:continue
  m=re.match(r'^\s*(\d+\.\d+)\s+([A-Za-z0-9_]+)\s+(\d+)\s+(\d+)\s+I\s+'+re.escape(tag)+r'\s*:\s*(.*)$',line)
  assert m and float(m[1])>=earliest and m[2] in (str(uid),'u0_a'+str(uid-10000)) and int(m[3])==pid
  output.append(m[5])
 assert output;return output
def qualify_arm(arm,parser,once,contract):
 directory=ROOT/DIRECTORIES[arm];p=json.loads((directory/'prepared.json').read_text());r=json.loads((directory/'runtime-result.json').read_text())
 assert p['arm']==r['arm']==arm and p['engine_sha256']==ENGINE[arm]
 assert p['runner_contract_sha256']==MANIFEST_SHA
 assert p['apks']['v8']['sha256']==contract['v8_apk_sha256']=='dc1777871e32681a823253c36dba0a553ef596a464a3c4d7a282d3f9a6bafa67'
 assert sha(Path(p['apks']['v8']['path']))==p['apks']['v8']['sha256']
 assert json.loads((directory/'v8-install.json').read_text())['APK_SHA256']==p['apks']['v8']['sha256']
 assert sha(Path(p['stage'])/'payload/39/libberberis_arm64.so')==ENGINE[arm]
 assert r.get('run_returned') is True and not r.get('error') and not r['cleanup']['errors']
 for key in ('all_native_contracts_observed','all_owned_contracts_complete','own_packages_removed','main_preserved','owned_memory_events_zero','source_contract_preserved'):assert r.get(key) is True,(arm,key)
 assert r['boot']=={'completed':'1','android':'17','sdk':'37','system_server_start_count':'1','adbd':'stopped','engine_sha256':ENGINE[arm]}
 assert r['adbd_before_cleanup']=='stopped'
 assert r['main_after']==p['main_before'] and p['main_before']['framework_sha256']=='d820db4ea51514fdc7f2258e490a7b7453e03aefd666aab0939ad5a87915842d'
 assert r['main_resources_before']==r['main_resources_after']==MAIN_LIMITS
 expected={'manifest_sha256':MANIFEST_SHA,'files':contract['files'],'inventory_sha256':contract['inventory_sha256']}
 assert r['source_contract_before']==r['source_contract_after']==expected
 bootstrap=json.loads((directory/'bootstrap-ready.json').read_text());assert bootstrap['complete'] is True and bootstrap['observations']
 last=bootstrap['observations'][-1]
 assert last['home_setup_state']==last['ime_setup_state']=='stopped'
 for pkg,expected_hash in [('com.android.droidloom.home','4580d4ba3db94de30204f2a654dbeefae8d52684cdd3d93ba31cb943324b8484'),('com.android.droidloom.ime','1345fb142061e5d8cb3979d1fce3f3a5d125cc9dab2e9287a3ac7db904a8058a')]:
  b=last['packages'][pkg];assert b['installed'] is True and b['sha256']==b['marker_sha256']==expected_hash and b['versionCode']==1 and b['marker_returncode']==0
 before=package_set((directory/'packages-before.txt').read_bytes());after=package_set((directory/'packages-after.txt').read_bytes())
 third_before=package_set((directory/'packages-before-third-party.txt').read_bytes());third_after=package_set((directory/'packages-after-third-party.txt').read_bytes())
 assert before==after and third_before==third_after
 assert {'com.android.droidloom.home','com.android.droidloom.ime'}.issubset(third_before)
 uid_records=parse_uid_list((directory/'package-uids-after.txt').read_bytes())
 assert {n for n,u in uid_records}==after,'independent full UID-list completeness check'
 owned={v['package'] for v in p['apks'].values()}
 owned_uids={json.loads((directory/(key+'-install.json')).read_text())['uid'] for key in ('v4','v5','v6','v8')}
 assert len(owned_uids)==4 and not after&owned and not any(n in owned or u in owned_uids for n,u in uid_records)
 data=json.loads((directory/'owned-code-data-cleanup.json').read_text())
 assert data['remaining']==[] and data['owned_uids_absent_from_package_registry'] is True
 assert len(data['actual_namespace_checks'])==len(data['checked_paths'])==16
 assert {v['path'] for v in data['actual_namespace_checks']}==set(data['checked_paths'])
 for row in data['actual_namespace_checks']:
  assert row['returncode']==1 and not row['stdout'] and row['path'] in row['stderr'] and 'no such file or directory' in row['stderr'].lower()
 for key in ('v4','v5','v6','v8'):
  row=json.loads((directory/(key+'-uninstall.json')).read_text());assert row['returncode']==0 and row['stdout'].strip()=='Success'
 earliest=datetime.datetime.fromisoformat(r['started_utc']).timestamp();controls={}
 for key in ('v8','v4','v5','v6'):
  version=int(key[1:]);record=r[key];pid=record['guest_identity']['pid'];uid=record['guest_identity']['uid'];host=record['host_identity']
  assert host['namespace_pids'][-1]==pid and host['uids']==[uid]*4 and host['start_ticks']==int(record['guest_identity']['start'])
  loaded=record['engine_loaded'];assert loaded['engine_sha256']==ENGINE[arm] and len(loaded['actual_host_maps'])>=3 and any('r-xp' in line for line in loaded['actual_host_maps'])
  nonce=p['nonces'][key if key!='v8' else 'v8-controls']
  observations=[]
  for second in (0,2,10):
   payload=log_payload(directory/(key+'-log-'+str(second)+'.txt'),'NativeOracleV'+str(version),nonce,pid,uid,earliest)
   assessed=parser['assess'](version,payload,nonce,pid,uid,arm,expected_cpu_count=24);observations.append(assessed)
  assert all(o==observations[0] for o in observations)
  controls[key]=observations[0]
 alarm=r['v8_default']
 command=json.loads((directory/'v8-default-single-launch-command.json').read_text())
 assert command['host_launch_count']==1 and command['APK_SHA256']==contract['v8_apk_sha256'] and command['engine_sha256']==ENGINE[arm]
 since=command['earliest_epoch'];nonce=p['nonces']['v8-default-alarm'];uid=command['uid']
 assert command['nonce']==nonce and since>=earliest
 collected=once['collect']((directory/'v8-default-log.txt').read_bytes(),nonce,uid,since,p['apks']['v8']['package'])
 parsed=once['assess'](collected,nonce,uid,arm,parser['assess'])
 assert parsed and parsed==alarm['at_most_once'] and alarm['observed_stable_seconds']>=2
 assert alarm['assessment']==parsed['assessment']
 pid=parsed['owner_pid']
 expected_claim=('v=1 run_id='+nonce+' mode=default-alarm pid='+str(pid)+' uid='+str(uid)+' start_ticks='+str(parsed['owner_start_ticks'])+'\n').encode()
 claim=json.loads((directory/'v8-default-claim.json').read_text())
 final_claim=json.loads((directory/'v8-default-final-claim.json').read_text())
 assert claim==final_claim==alarm['durable_claim']
 assert claim['mode']=='0o600' and claim['uid']==uid and claim['nlink']==1 and claim['bytes']==len(expected_claim) and claim['sha256']==hashlib.sha256(expected_claim).hexdigest()
 assert claim['owner_pid']==pid and claim['owner_start_ticks']==parsed['owner_start_ticks']
 assert (directory/'v8-default-claim.raw').read_bytes()==(directory/'v8-default-final-claim.raw').read_bytes()==expected_claim
 if arm=='r14':
  assert alarm['ignored_alarm_returned_and_survived'] is True and alarm['engine_loaded']['engine_sha256']==ENGINE[arm]
  assert alarm['guest_identity']['pid']==pid and alarm['guest_identity']['uid']==uid
  assert int(alarm['guest_identity']['start'])==alarm['host_identity']['start_ticks']==parsed['owner_start_ticks']
 else:
  assert alarm['actual_default_termination'] is True and alarm['exit_reason']==2 and alarm['exit_status']==14
  assert alarm['logged_guest_pid']==pid and alarm['uid']==uid
  assert alarm['owner_start_ticks_from_durable_claim']==parsed['owner_start_ticks']
  assert alarm['owner_start_ticks_not_independently_sampled_due_to_immediate_death'] is True
  assert alarm['owner_engine_mapping_from_prior_same_arm_live_controls'] is True
  text=(directory/'v8-default-exit-info.txt').read_text();blocks=re.split(r'ApplicationExitInfo #\d+:',text)
  matched=[b for b in blocks if re.search(r'\bpid='+str(pid)+r'\b',b) and re.search(r'\bprocess=local\.pocket4\.nativeoraclev8\b',b)]
  assert len(matched)==1 and re.search(r'\brealUid='+str(uid)+r'\b',matched[0]) and re.search(r'\bpackageUid='+str(uid)+r'\b',matched[0]) and re.search(r'\breason=2\s+\(SIGNALED\)',matched[0]) and re.search(r'\bstatus=14\b',matched[0])
  ts=re.search(r'timestamp=(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})',matched[0]);assert ts and ts[1]==alarm['exit_timestamp']
  z=command['guest_timezone_offset'];assert re.fullmatch(r'[+-]\d{4}',z)
  zone=datetime.timezone(datetime.timedelta(minutes=(1 if z[0]=='+' else -1)*(int(z[1:3])*60+int(z[3:]))))
  stop=json.loads((directory/'v8-default-owned-stop-boundary.json').read_text())
  assert since<=datetime.datetime.strptime(ts[1],'%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=zone).timestamp()<datetime.datetime.fromisoformat(stop['utc']).timestamp()
  for record in alarm['refusing_live_processes']:
   gp=record['guest_identity']['pid'];hp=record['host_identity']
   match=[x for x in parsed['relaunch_refused'] if x['pid']==gp];assert len(match)==1
   assert int(record['guest_identity']['start'])==hp['start_ticks']==match[0]['start_ticks']
   assert hp['uids']==[uid]*4 and record['native_probe_not_mapped'] is True
   maps=[x for x in directory.glob('v8-default-observation-*.refused-pid-'+str(gp)+'.maps') if sha(x)==record['maps_sha256']]
   assert maps and all(b'libnativeoraclev8.so' not in x.read_bytes() for x in maps)
 final_collected=once['collect']((directory/'v8-default-after-owned-stop.log').read_bytes(),nonce,uid,since,p['apks']['v8']['package'])
 assert once['assess'](final_collected,nonce,uid,arm,parser['assess'])==parsed
 resources=json.loads((directory/'resources-before-cleanup.json').read_text());assert len(resources)==5
 peaks={}
 for row in resources:
  assert 'error' not in row
  events=dict((k,int(v)) for k,v in (line.split() for line in row['memory.events'].splitlines()))
  assert all(events.get(k)==0 for k in ('oom','oom_kill','oom_group_kill'))
  if 'properties' in row:
   props=dict(line.split('=',1) for line in row['properties'].splitlines() if '=' in line)
   assert props['MemorySwapMax']=='0' and int(props['MemoryPeak'])<=int(props['MemoryMax'])
   peaks[row['unit']]=int(props['MemoryPeak'])
  else:
   assert row['memory.max']=='268435456' and row['memory.swap.max']=='0' and row['cpu.max']=='10000 100000'
   peaks[row['unit']]=int(row['memory.peak'])
 units=[]
 for row in r['cleanup']['units']:
  q=subprocess.run(['/usr/bin/systemctl','show',row['unit'],'-p','LoadState','-p','ActiveState','-p','MainPID'],capture_output=True,text=True,timeout=15)
  props=dict(line.split('=',1) for line in q.stdout.splitlines() if '=' in line)
  assert props.get('MainPID','0')=='0' and props.get('ActiveState') not in ('active','activating','deactivating')
  procs=Path('/sys/fs/cgroup'+row['group']+'/cgroup.procs');assert not procs.exists() or not procs.read_text().strip()
  units.append({'unit':row['unit'],'live_final_state':props})
 receipt_files=['v8-default-single-launch-command.json','v8-default-claim.raw','v8-default-claim.json','v8-default-final-claim.raw','v8-default-final-claim.json','v8-default-owned-stop-boundary.json','v8-default-after-owned-stop.log','v8-default-after-owned-stop-exit-info.txt','prepared.json','runtime-result.json','bootstrap-ready.json','private-framework-epoch.json','cpu-inventory-observed.json','resources-before-cleanup.json','packages-before.txt','packages-after.txt','packages-before-third-party.txt','packages-after-third-party.txt','package-uids-after.txt','package-set-comparison.json','owned-code-data-cleanup.json','v8-default-log.txt']
 if arm!='r14':receipt_files.append('v8-default-exit-info.txt')
 return {'arm':arm,'directory':str(directory),'engine_sha256':ENGINE[arm],'full_v5_contract':'PASS_WITH_EXPECTED_BASELINE_NEGATIVES' if arm!='r16' else 'PASS_OWNED_NATIVE_SEMANTICS','controls':controls,'default_alarm':'SIG_IGN_returned_and_survived' if arm=='r14' else 'SIGNALED_14','main_epoch_sha256':p['main_before']['framework_sha256'],'main_limits':MAIN_LIMITS,'adbd':'stopped','all_owned_oom_events_zero':True,'all_owned_units_empty':True,'owned_package_uid_list_complete':True,'owned_code_data_absent_in_actual_namespace':True,'source_contract':expected,'units':units,'memory_peaks_bytes':peaks,'started_utc':r['started_utc'],'finished_utc':r['finished_utc'],'receipts_sha256':{n:sha(directory/n) for n in receipt_files},'default_alarm_new_process_maps_observed':arm=='r14','at_most_once':parsed,'v8_APK_sha256':p['apks']['v8']['sha256']}
def main():
 assert os.geteuid()==0
 assert sha(ROOT/'runner-v5-once-manifest.json')==MANIFEST_SHA
 contract=json.loads((ROOT/'runner-v5-once-manifest.json').read_text())
 assert all(sha(ROOT/n)==h for n,h in contract['files'].items())
 parser={};exec(compile((ROOT/'assess-v2.py').read_bytes(),'frozen-assessor-v2','exec'),parser)
 once={};exec(compile((ROOT/'assess-default-once.py').read_bytes(),'frozen-default-once-assessor','exec'),once)
 arms=[qualify_arm(a,parser,once,contract) for a in ('r14','r15','r16')]
 build=json.loads((ROOT/'v8-once-source-r2/build-attempt-1/build-result.json').read_text())
 assert build['state']=='BUILT_STATIC_AND_REAL_HOST_CONTROLS_PASS_ANDROID_UNRUN' and build['APK']['sha256']==contract['v8_apk_sha256'] and build['ELF']['sha256']==contract['v8_native_elf_sha256_unchanged']
 import sys
 old_argv=sys.argv[:];sys.argv=[str(ROOT/'run_arm-v5-once.py'),'r16-r2']
 frozen={'__name__':'read_only_qualification_definitions','__file__':str(ROOT/'run_arm-v5-once.py')}
 try:exec(compile((ROOT/'run_arm-v5-once.py').read_bytes(),str(ROOT/'run_arm-v5-once.py'),'exec'),frozen)
 finally:sys.argv=old_argv
 current_main=frozen['main_snapshot']();current_limits=frozen['main_resources']()
 assert current_main==json.loads((ROOT/'r16-r2/prepared.json').read_text())['main_before'] and current_limits==MAIN_LIMITS
 report={'schema':'pocket4-native-three-arm-qualification-v2','state':'PASS_THREE_ARM_OWNED_NATIVE_SEMANTICS','arms':arms,'fixed_presenter_sha256':'47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24','owned_v8_apk_sha256':contract['v8_apk_sha256'],'actual_current_main':current_main,'actual_current_main_limits':current_limits,'qualifier_sha256':sha(Path(__file__)),'main_deployment_performed':False,'publisher_application_qualification':False,'limitations':['Native engine and owned probes only; no Marriott or other publisher app compatibility inference.','R15/R16 default-termination process start ticks are recorded by the app before load into a durable claim, but were not independently sampled by the host before death. All nonce PID/UID/claim events and ApplicationExitInfo establish SIG14; engine maps were independently observed in each preceding live owned control process.','Bootstrap loop has a 120-second entry deadline plus bounded final-command timeouts; it is not a strict total wallclock budget.','Original R14 CPU8/package-bootstrap failures, v3 R15 lifecycle attribution failure, the diagnostic-only repeated-Activity run, failed first once-APK compile, and non-root launcher preflight failure remain unmodified. Only r14-r4/r15-r2/r16-r2 use the same complete v5 once contract.'],'additional_independent_checks':['UID registry package names equal full after package inventory; rejects empty or truncated UID list.','Every actual namespace absence result is rc1, empty stdout, exact checked path, and ENOENT text.']}
 path=ROOT/'three-arm-qualification-v5-once.json'
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o444)
 with os.fdopen(fd,'w') as out:json.dump(report,out,indent=2,sort_keys=True);out.write('\n');out.flush();os.fsync(out.fileno())
 print(json.dumps({'state':report['state'],'receipt':str(path),'sha256':sha(path),'arms':[{'arm':a['arm'],'outcome':a['full_v5_contract'],'default_alarm':a['default_alarm']} for a in arms]}),flush=True)
if __name__=='__main__':main()
