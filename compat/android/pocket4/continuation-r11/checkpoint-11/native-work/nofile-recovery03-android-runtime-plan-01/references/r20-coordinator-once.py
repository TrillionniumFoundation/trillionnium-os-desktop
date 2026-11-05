from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys
RUNNER=Path('/home/alex/work/pocket4-owned-held-ns-runner-r4-01/run-r4.py')
APK=Path('/home/alex/work/pocket4-owned-fd-capability-r20-apk-01/fd-owner-probe-r20-source/build-attempt-1/fdownerprobe.apk')
AUDIT=Path('/home/alex/work/pocket4-owned-fd-capability-r20-audit-01/audit-receipt.json')
ENTRY=Path('/home/alex/work/pocket4-owned-held-ns-runner-r4-export-01/qualification.json')
MANUAL=Path('/home/alex/work/pocket4-owned-fd-capability-r20-root-review-01/root-manual-review.json')
ROOT=Path('/home/alex/work/pocket4-owned-fd-capability-r20-android-01')
RUNNER_SHA='c16015f7a51f857d114d92691dbf4ac4d0ccf758c2f99c7c541653ce1957ea62'
APK_SHA='c056d2c116abc0bca4ec6606defb6810ba53d960fd6164a0595cac9cc8ed06f0'
AUDIT_SHA='4db3d1736597844dfeccf09646591db92201dece70b2231d769ac8f2b08cee33'
ENTRY_SHA='3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3'
MANUAL_SHA='b174dd5085b7f591e2bec7a377f4c3d4404e13f0dc4fa190073a405aa6c8866a'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,value):
 b=value if isinstance(value,bytes) else (json.dumps(value,indent=2)+'\n').encode()
 with (ROOT/name).open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
assert os.geteuid()==0
for p,h in [(RUNNER,RUNNER_SHA),(APK,APK_SHA),(AUDIT,AUDIT_SHA),(ENTRY,ENTRY_SHA),(MANUAL,MANUAL_SHA)]:
 assert sha(p)==h
audit=json.loads(AUDIT.read_bytes());entry=json.loads(ENTRY.read_bytes());manual=json.loads(MANUAL.read_bytes())
assert audit['state']=='ACTUAL_ANDROID_ELF_AUDIT_PASSED_UNRUN' and audit['APK']['sha256']==APK_SHA
assert audit['apk_embedded_elf_exact_match'] is True and audit['errors']==[]
worker_path=AUDIT.parent/'worker-audit.json'
assert sha(worker_path)=='74256faa7106d0ad05d750aa16ceb7012e6d78ea5a6c0afcb36e1d6fa7d9eecc'
worker=json.loads(worker_path.read_bytes())
assert worker['qualified_worker_closure'] is True and worker['elf_sha256']==audit['ELF']['sha256'] and worker['errors']==[]
assert sha(AUDIT.parent/'relevant-disassembly.txt')==audit['relevant_disassembly_sha256']
build_root=APK.parent.parent
old_root=Path('/home/alex/work/pocket4-owned-fd-capability-r19-apk-01/fd-owner-probe-r19-source')
assert len(audit['source_files'])==15
for name,h in audit['source_files'].items():
 assert sha(build_root/name)==h,('source changed',name)
unchanged=[n for n in audit['source_files'] if n.startswith('actual/') and n!='actual/proc_maps_raw_metadata_owner.cc']+['AndroidManifest.xml','src/local/pocket4/fdownerprobe/ProbeInstrumentation.java','audit_worker_binary.py','metadata_raw_cases.cc']
assert len(unchanged)==11
for name in unchanged:assert (old_root/name).read_bytes()==(build_root/name).read_bytes(),('unexpected delta',name)
assert sha(AUDIT.parent/'start-trampoline-exact.txt')=='f8bc000748d1f25fd43e31275fb4f4f934d699acfe485424dbcb312f105acec3'
assert sha(AUDIT.parent/'read-publication-exact.txt')=='74289dbfb77c1f8439b7c2baeaa194c8a768b775bd9f8a975441f8315d01e2cd'
assert sha(AUDIT.parent/'entry-read-slices.json')=='f9048a7947ca224beb02dc8ca9170e9475c886325dd4a12bb6c507f34d75cb74'
assert audit['source_pins_sha256']=='6e6c806a9560b34435a937ae8d9dab241f3139f63106f93da108b06dc0584cbb'
assert audit['source_files']['actual/proc_maps_raw_metadata_owner.cc']=='8a5812793ec5b569ef03d7a159871d74e27baccaf17d3e8fe6c9998e348e28a8'
assert sha(Path('/home/alex/work/pocket4-owned-fd-capability-r20-root-review-01/actual-source-and-elf-read.json'))=='ec56180d572df6db5247e6dc794f56a3108b23d4f5639bb407bbc07e315d966a'
assert entry['qualified_for_owned_namespace_entry'] is True and entry['owned_runner_sha256']==RUNNER_SHA
assert entry['helper_binary_sha256']=='21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689'
assert entry['qualified_for_whole_process_tree_cleanup'] is False
assert manual['owned_android_probe_admissible'] is True and manual['entry_qualification_sha256']==ENTRY_SHA and manual['apk_sha256']==APK_SHA
assert not ROOT.exists() and not ROOT.is_symlink()
os.umask(0o077);ROOT.mkdir(mode=0o700)
save('coordinator-claim.json',{'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'apk_sha256':APK_SHA,'runner_sha256':RUNNER_SHA,'actual_elf_audit_sha256':AUDIT_SHA,'entry_qualification_sha256':ENTRY_SHA,'root_manual_review_sha256':MANUAL_SHA,'no_automatic_retry':True,'scope':'Owned app UID; R20 clears only Bionic ST_VALID before successful publication; original 12 observations include known NOFILE0 red'})
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
  phase('run','02-run',['--nonce','p4r11_real_metadata_bionic_fixed_r20_20261104_a1'])
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
