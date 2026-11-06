from pathlib import Path
import urllib.request,concurrent.futures,json,hashlib,base64
r=Path('/workspace/scratch/265e5bca485a/pocket4_eight_apps/framework_provider_repair/normal06'); dest=r/'reference/closure-providers'
locks=json.loads((r.parent/'normal05/source-r2/actual-provider-source-lock.json').read_text());projects={p['path']:p for p in locks['projects']}
root=json.loads((r/'reference/upstream-tree/superproject-root.raw.json').read_bytes().split(b'\n',1)[1]);gl={p['name']:p['id'] for p in root['entries'] if p['type']=='commit'};projects['development']={'name':'platform/development','commit':gl['development']}
ext=json.loads((r/'reference/upstream-tree/superproject-external.raw.json').read_bytes().split(b'\n',1)[1]);ext={p['name']:p['id'] for p in ext['entries'] if p['type']=='commit'}
for n in ['dexmaker','perfetto','nullaway']:
 if n in ext:projects['external/'+n]={'name':'platform/external/'+n,'commit':ext[n]}
pre=json.loads((r/'reference/upstream-tree/superproject-prebuilts.raw.json').read_bytes().split(b'\n',1)[1]);pre={p['name']:p['id'] for p in pre['entries'] if p['type']=='commit'};projects['prebuilts/r8']={'name':'platform/prebuilts/r8','commit':pre['r8']}
for n in ['ksp','escapevelocity']:
 assert n in ext;projects['external/'+n]={'name':'platform/external/'+n,'commit':ext[n]}
items=[["external/auto","factory/Android.bp"],["external/jspecify","Android.bp"],["external/kotlin.metadata","Android.bp"],["external/kotlinx.metadata","Android.bp"],["external/ksp","Android.bp"],["external/escapevelocity","Android.bp"],["external/objenesis","Android.bp"],["external/okio","Android.bp"],["packages/apps/Launcher3","aconfig/Android.bp"],["platform_testing","libraries/health/utils/Android.bp"],["platform_testing","libraries/metrics-helper/Android.bp"],["platform_testing","libraries/notes-role-test-helper/Android.bp"],["platform_testing","libraries/uinput-device-test-helper/Android.bp"]]
def one(item):
 project,path=item;lock=projects[project];local=dest/project/path;url=f"https://android.googlesource.com/{lock['name']}/+/{lock['commit']}/{path}?format=TEXT"
 try:
  if local.exists():
   meta=json.loads(local.with_suffix(local.suffix+'.source.json').read_text());assert hashlib.sha256(local.read_bytes()).hexdigest()==meta['decoded_sha256'];return {'reused':True,**meta}
  with urllib.request.urlopen(url,timeout=25) as f:raw=f.read(3145729);status=f.status
  assert len(raw)<=3145728;data=base64.b64decode(raw,validate=True);local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(data);local.with_suffix(local.suffix+'.wire-base64.txt').write_bytes(raw)
  meta={'path':project+'/'+path,'repository':lock['name'],'commit':lock['commit'],'url':url,'status':status,'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),'decoded_bytes':len(data),'decoded_sha256':hashlib.sha256(data).hexdigest(),'transport_TLS_verification':'urllib default verified'};local.with_suffix(local.suffix+'.source.json').write_text(json.dumps(meta,indent=2)+'\n');return meta
 except Exception as e:return {'path':project+'/'+path,'url':url,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(one,items))
p=dest/'eleventh-provider-capture-index.json';b=(json.dumps({'source_only':True,'host_actions':False,'files':out},indent=2)+'\n').encode();p.write_bytes(b)
print(json.dumps({'items':len(out),'successful':sum('decoded_sha256' in x for x in out),'index_bytes':len(b),'index_sha256':hashlib.sha256(b).hexdigest(),'failures':[x for x in out if 'error' in x]}))
