from pathlib import Path
import urllib.request,concurrent.futures,json,hashlib,base64,re
r=Path('/workspace/scratch/265e5bca485a/pocket4_eight_apps/framework_provider_repair/normal06'); dest=r/'reference/closure-providers'
locks=json.loads((r.parent/'normal05/source-r2/actual-provider-source-lock.json').read_text()); projects={p['path']:p for p in locks['projects']};projects['packages/apps/PersonalContext']={'name':'platform/packages/apps/PersonalContext','commit':'025cc78a5a242ab434161d462e8d67e327db64d3'}
paths=(r/'reference/normal05-actual-graph/Android.bp.list').read_text().splitlines(); deps=json.loads((r/'systemui-all-loaded-source-closure-r2.json').read_text())['external_dependencies_with_consumers']
selected=set()
for n in deps:
 if not n.startswith('androidx'):continue
 if '_' in n:group,artifact=n.split('_',1);group=group.replace('androidx-','androidx.')
 elif n.startswith('androidx.media3.'):group='androidx.media3';artifact=n[len('androidx.media3.'):]
 else:continue
 for suffix in ['', '-android','-jvm']:
  prefix='prebuilts/sdk/current/androidx/m2repository/'+group.replace('.','/')+'/'+artifact+suffix+'/'
  selected.update(p for p in paths if p.startswith(prefix) and len(p[len(prefix):].split('/'))==2)
items=[('prebuilts/sdk',p[len('prebuilts/sdk/'):]) for p in sorted(selected)]
items += [('prebuilts/sdk','current/androidx-legacy/Android.bp'),('prebuilts/sdk','current/Android.bp'),('platform_testing','libraries/screenshot/utils/compose/Android.bp'),('platform_testing','libraries/runner/Android.bp'),('packages/apps/PersonalContext','Android.bp'),('build/soong','android/prebuilt.go'),('external/hamcrest','hamcrest-library/Android.bp'),('external/junit','Android.bp'),('frameworks/base','test-base/Android.bp'),('frameworks/base','test-mock/Android.bp'),('frameworks/base','test-runner/Android.bp')]
assert len(items)<=90,len(items)
def one(item):
 project,path=item;lock=projects[project];local=dest/project/path;url=f"https://android.googlesource.com/{lock['name']}/+/{lock['commit']}/{path}?format=TEXT"
 try:
  if local.exists():
   meta=json.loads(local.with_suffix(local.suffix+'.source.json').read_text());assert hashlib.sha256(local.read_bytes()).hexdigest()==meta['decoded_sha256'];return {'reused':True,**meta}
  with urllib.request.urlopen(url,timeout=25) as f:raw=f.read(2097153);status=f.status
  assert len(raw)<=2097152;data=base64.b64decode(raw,validate=True);local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(data)
  meta={'path':project+'/'+path,'repository':lock['name'],'commit':lock['commit'],'url':url,'status':status,'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),'decoded_bytes':len(data),'decoded_sha256':hashlib.sha256(data).hexdigest(),'transport_TLS_verification':'urllib default verified'};local.with_suffix(local.suffix+'.source.json').write_text(json.dumps(meta,indent=2)+'\n');return meta
 except Exception as e:return {'path':project+'/'+path,'url':url,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:out=list(pool.map(one,items))
p=dest/'third-provider-capture-index.json';b=(json.dumps({'source_only':True,'host_actions':False,'selection':'direct names against exact actual BP paths plus known samecommit providers','files':out},indent=2)+'\n').encode();p.write_bytes(b)
print(json.dumps({'items':len(out),'successful':sum('decoded_sha256' in x for x in out),'index_bytes':len(b),'index_sha256':hashlib.sha256(b).hexdigest(),'failures':[x for x in out if 'error' in x]}))
