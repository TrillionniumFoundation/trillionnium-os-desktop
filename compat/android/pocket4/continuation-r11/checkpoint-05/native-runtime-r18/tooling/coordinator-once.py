from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys
RUNNER=Path('/home/alex/work/pocket4-owned-held-ns-runner-r4-01/run-r4.py')
APK=Path('/home/alex/work/pocket4-owned-fd-capability-r18-apk-01/fd-owner-probe-r18-source/build-attempt-1/fdownerprobe.apk')
AUDIT=Path('/home/alex/work/pocket4-owned-fd-capability-r18-audit-01/receipt.json')
ENTRY=Path('/home/alex/work/pocket4-owned-held-ns-runner-r4-export-01/qualification.json')
MANUAL=Path('/home/alex/work/pocket4-owned-held-ns-runner-r4-export-01/native-r18-root-manual-review.json')
ROOT=Path('/home/alex/work/pocket4-owned-fd-capability-r18-android-01')
RUNNER_SHA='c16015f7a51f857d114d92691dbf4ac4d0ccf758c2f99c7c541653ce1957ea62'
APK_SHA='a0be875bdba992e5f4b96c4657916b7760ce28c62bc130331cdce7dc5eb3fe65'
AUDIT_SHA='2f082862debae528f401e161226f0187cac15168e61419540a1b2bcb7c696f9c'
ENTRY_SHA='3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3'
MANUAL_SHA='dcfed44d778a97bf46718a6bbc6be0b07de0c9b04a6c659b7658571dddfeb1d4'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,value):
 b=value if isinstance(value,bytes) else (json.dumps(value,indent=2)+'\n').encode()
 with (ROOT/name).open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
assert os.geteuid()==0
for p,h in [(RUNNER,RUNNER_SHA),(APK,APK_SHA),(AUDIT,AUDIT_SHA),(ENTRY,ENTRY_SHA),(MANUAL,MANUAL_SHA)]:
 assert sha(p)==h
audit=json.loads(AUDIT.read_bytes());entry=json.loads(ENTRY.read_bytes());manual=json.loads(MANUAL.read_bytes())
assert audit['qualified_for_owned_runtime_probe'] is True and audit['apk_sha256']==APK_SHA
assert audit['artifact_hashes_unchanged'] is True and audit['worker_closure']['qualified_worker_closure'] is True
assert entry['qualified_for_owned_namespace_entry'] is True and entry['owned_runner_sha256']==RUNNER_SHA
assert entry['helper_binary_sha256']=='21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689'
assert entry['qualified_for_whole_process_tree_cleanup'] is False
assert manual['owned_android_probe_admissible'] is True and manual['entry_qualification_sha256']==ENTRY_SHA and manual['apk_sha256']==APK_SHA
assert not ROOT.exists() and not ROOT.is_symlink()
os.umask(0o077);ROOT.mkdir(mode=0o700)
save('coordinator-claim.json',{'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'apk_sha256':APK_SHA,'runner_sha256':RUNNER_SHA,'actual_elf_audit_sha256':AUDIT_SHA,'entry_qualification_sha256':ENTRY_SHA,'root_manual_review_sha256':MANUAL_SHA,'no_automatic_retry':True,'scope':'Owned app UID; R7 real metadata wrappers and explicit raw owner; 12 expected observations include known NOFILE0 red'})
steps=[];errors=[]
def phase(name,step,extra):
 argv=['/usr/bin/python3','-I',str(RUNNER),name,'--kind','owner','--root',str(ROOT),'--step',step]+extra
 item={'phase':name,'argv':argv}
 try:
  p=subprocess.run(argv,capture_output=True,timeout=95)
  save(step+'-coordinator.stdout',p.stdout);save(step+'-coordinator.stderr',p.stderr)
  item['returncode']=p.returncode
  path=ROOT/step/'result.json'
  item['report']=json.loads(path.read_bytes()) if path.is_file() else {'ok':False,'missing_result':True,'outcome_unknown':True}
 except Exception as e:
  item.update(error=repr(e),report={'ok':False,'outcome_unknown':True});errors.append({'phase':name,'error':repr(e)})
  if isinstance(e,subprocess.TimeoutExpired):
   save(step+'-coordinator-timeout.stdout',e.stdout or b'');save(step+'-coordinator-timeout.stderr',e.stderr or b'')
 steps.append(item);r=item['report']
 print(json.dumps({'phase':name,'returncode':item.get('returncode'),'ok':r.get('ok'),'outcome_unknown':r.get('outcome_unknown'),'identity':r.get('installed_identity'),'cleanup':r.get('only_exact_owned_package_removed'),'error':item.get('error',r.get('error'))}),flush=True)
 return r.get('ok') is True
try:
 if phase('install','01-install',['--apk',str(APK),'--apk-sha256',APK_SHA]):
  phase('run','02-run',['--nonce','p4r11_real_metadata_actual_r18_20261104_a1'])
finally:
 if (ROOT/'install-verified.json').is_file():phase('remove','03-remove',[])
 else:errors.append({'phase':'remove','reason':'No verified owned identity; no blind removal.'})
 removed=any(s['phase']=='remove' and s['report'].get('only_exact_owned_package_removed') is True for s in steps)
 result={'schema':1,'steps':steps,'errors':errors,'owned_cycle_complete':len(steps)==3 and removed,
         'exact_owned_package_removed':removed,'native_pass_not_implied_by_dispatch_success':True}
 save('coordinator-result.json',result)
 run=next((s['report'] for s in steps if s['phase']=='run'),{})
 print(json.dumps({'instrumentation_output':run.get('instrumentation_output'),'owned_cycle_complete':result['owned_cycle_complete']}),flush=True)
raise SystemExit(0 if result['owned_cycle_complete'] else 1)
