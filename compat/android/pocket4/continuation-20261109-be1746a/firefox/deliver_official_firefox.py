import os,json,pathlib,hashlib,urllib.request,time,datetime,stat
ROOT=pathlib.Path('/home/alex/work/pocket4-android-final')
OUT=ROOT/'cohorts/qpr1-cp3a-16176746-20261108-8b88-r1/official-app-inputs-be1746a-r1'
SEL=ROOT/'qualification/apps-content-bound-20261108-8b88-r1/update_inputs/final-selected42-production-candidates.json'
CAND=ROOT/'qualification/apps-content-bound-20261108-8b88-r1/update_inputs/firefox_official/candidate.json'
url='https://ftp.mozilla.org/pub/fenix/releases/159.0.1/android/fenix-159.0.1-android-x86_64/fenix-159.0.1.multi.android-x86_64.apk'
api='https://product-details.mozilla.org/1.0/mobile_versions.json'
expected='dc4310b6193a5cadf3b7eff119e677aea006071c8484fa7a35874c2613fd18e1'
size=139231259
def ref(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
sraw=SEL.read_bytes(); assert hashlib.sha256(sraw).hexdigest()=='73b7578fe2376f700edd68184ed6e16182bf4b58d3b5c75554a5c597f5f3a603'
cr=ref(CAND);assert cr['sha256']=='54a737161cd552ca6e36a7687153aefbf1afc464ee5594d04d7ca513d45c7b54'
c=json.loads(CAND.read_text());assert c['apk_sha256']==expected and c['signature_verified'] is True
for p in [OUT.parent,ROOT]:
 st=p.lstat();assert stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and st.st_uid==0 and not st.st_mode&0o022
if OUT.exists():raise SystemExit('Existing delivery generation; reconcile its receipt, do not overwrite')
OUT.mkdir(mode=0o700)
result={'schema':'pocket4-official-app-binary-delivery-v1','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'selected_manifest':{'path':str(SEL),'bytes':len(sraw),'sha256':hashlib.sha256(sraw).hexdigest()},'prior_signature_receipt':cr,'source_url':url,'version_api':api,'installed':False,'Android_actions':0,'runtime_accepted':False,'production_ready':False}
def write(n,v):
 raw=(json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
 with (OUT/n).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 return {'path':str(OUT/n),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
write('intent.json',result)
part=OUT/'firefox-159.0.1-x86_64.apk.part'
try:
 with urllib.request.urlopen(api,timeout=20) as resp:
  meta=resp.read(65537);assert len(meta)<=65536 and resp.status==200
 latest=json.loads(meta);assert latest['version']=='159.0.1',latest.get('version')
 with (OUT/'mozilla-mobile-versions.json').open('xb') as f:f.write(meta);f.flush();os.fsync(f.fileno())
 h=hashlib.sha256();count=0;start=time.monotonic()
 with urllib.request.urlopen(url,timeout=20) as resp,part.open('xb') as f:
  assert resp.status==200
  effective=resp.geturl();assert effective.startswith('https://') and urllib.request.urlparse(effective).hostname in ['ftp.mozilla.org','archive.mozilla.org','download-installer.cdn.mozilla.net']
  while True:
   if time.monotonic()-start>180:raise TimeoutError('bounded APK delivery exceeded 180 seconds')
   b=resp.read(1024*1024)
   if not b:break
   count+=len(b)
   if count>size:raise ValueError('APK exceeds selected candidate size')
   h.update(b);f.write(b)
  f.flush();os.fsync(f.fileno())
 assert count==size and h.hexdigest()==expected,(count,h.hexdigest())
 target=OUT/'firefox-159.0.1-x86_64.apk';os.rename(part,target);os.chmod(target,0o600)
 result.update({'state':'EXACT_SELECTED_OFFICIAL_BINARY_DELIVERED','effective_url':effective,'current_official_stable_version':latest['version'],'artifact':{'path':str(target),'bytes':count,'sha256':h.hexdigest()},'exact_bytes_match_prior_verified_signature':True,'new_signature_verifier_execution':False,'selected_manifest_unchanged':SEL.read_bytes()==sraw,'elapsed_seconds':time.monotonic()-start})
 if not result['selected_manifest_unchanged']:raise RuntimeError('selector changed during delivery')
except Exception as e:
 result.update({'state':'DELIVERY_FAILED','error':type(e).__name__+': '+str(e)})
 if part.exists():part.unlink()
result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
receipt=write('result.json',result)
print(json.dumps({'receipt':receipt,'result':result},ensure_ascii=False))
raise SystemExit(0 if result['state']=='EXACT_SELECTED_OFFICIAL_BINARY_DELIVERED' else 1)

