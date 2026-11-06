from pathlib import Path
import urllib.request,concurrent.futures,json,hashlib,base64
r=Path('/workspace/scratch/265e5bca485a/pocket4_eight_apps/framework_provider_repair/normal06'); dest=r/'reference/closure-providers'
locks=json.loads((r.parent/'normal05/source-r2/actual-provider-source-lock.json').read_text());projects={p['path']:p for p in locks['projects']}
root=json.loads((r/'reference/upstream-tree/superproject-root.raw.json').read_bytes().split(b'\n',1)[1]);gl={p['name']:p['id'] for p in root['entries'] if p['type']=='commit'};projects['development']={'name':'platform/development','commit':gl['development']}
ext=json.loads((r/'reference/upstream-tree/superproject-external.raw.json').read_bytes().split(b'\n',1)[1]);ext={p['name']:p['id'] for p in ext['entries'] if p['type']=='commit'}
for n in ['dexmaker','perfetto','nullaway']:
 if n in ext:projects['external/'+n]={'name':'platform/external/'+n,'commit':ext[n]}
pre=json.loads((r/'reference/upstream-tree/superproject-prebuilts.raw.json').read_bytes().split(b'\n',1)[1]);pre={p['name']:p['id'] for p in pre['entries'] if p['type']=='commit'};projects['prebuilts/r8']={'name':'platform/prebuilts/r8','commit':pre['r8']}
items=[('prebuilts/misc','common/androidx-test/Android.bp'),('prebuilts/misc','common/androidx-media3/Android.bp'),('prebuilts/sdk','current/extras/constraint-layout-x/Android.bp'),('prebuilts/sdk','current/extras/material-design-x/Android.bp'),('platform_testing','libraries/flag-helpers/junit/Android.bp'),('platform_testing','libraries/junit-rules/Android.bp'),('platform_testing','libraries/uiautomator-helpers/Android.bp'),('platform_testing','libraries/compatibility-common-util/Android.bp'),('tools/lint_checks','Android.bp'),('frameworks/base','packages/Android.bp'),('frameworks/base','ravenwood/Android.bp'),('frameworks/base','core/proto/Android.bp'),('frameworks/proto_logging','stats/stats_log_api_gen/Android.bp'),('packages/apps/Settings','Android.bp'),('development','samples/SceneTransitionLayoutDemo/Android.bp'),('external/dexmaker','Android.bp'),('external/perfetto','Android.bp'),('external/nullaway','Android.bp'),('prebuilts/r8','Android.bp')]
actual=(r/'reference/normal05-actual-graph/Android.bp.list').read_text().splitlines()
for p in actual:
 if p.startswith('frameworks/base/packages/SettingsLib/') and any('/'+d+'/' in p for d in ['CollapsingToolbarBaseActivity','Preference','Service','SettingsTheme']) and p.count('/')<=7:items.append(('frameworks/base',p[len('frameworks/base/'):]))
 if p in ['frameworks/base/services/accessibility/Android.bp','frameworks/base/services/core/java/com/android/server/am/Android.bp','frameworks/base/core/java/android/hardware/devicestate/Android.bp','frameworks/base/core/java/android/app/notification/flags/Android.bp','frameworks/base/services/core/java/com/android/server/notification/Android.bp']:items.append(('frameworks/base',p[len('frameworks/base/'):]))
items=list(dict.fromkeys(items))
def one(item):
 project,path=item;lock=projects[project];local=dest/project/path;url=f"https://android.googlesource.com/{lock['name']}/+/{lock['commit']}/{path}?format=TEXT"
 try:
  if local.exists():
   meta=json.loads(local.with_suffix(local.suffix+'.source.json').read_text());assert hashlib.sha256(local.read_bytes()).hexdigest()==meta['decoded_sha256'];return {'reused':True,**meta}
  with urllib.request.urlopen(url,timeout=25) as f:raw=f.read(3145729);status=f.status
  assert len(raw)<=3145728;data=base64.b64decode(raw,validate=True);local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(data);local.with_suffix(local.suffix+'.wire-base64.txt').write_bytes(raw)
  meta={'path':project+'/'+path,'repository':lock['name'],'commit':lock['commit'],'url':url,'status':status,'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),'decoded_bytes':len(data),'decoded_sha256':hashlib.sha256(data).hexdigest(),'transport_TLS_verification':'urllib default verified'};local.with_suffix(local.suffix+'.source.json').write_text(json.dumps(meta,indent=2)+'\n');return meta
 except Exception as e:return {'path':project+'/'+path,'url':url,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:out=list(pool.map(one,items))
p=dest/'fourth-provider-capture-index.json';b=(json.dumps({'source_only':True,'host_actions':False,'files':out},indent=2)+'\n').encode();p.write_bytes(b)
print(json.dumps({'items':len(out),'successful':sum('decoded_sha256' in x for x in out),'index_bytes':len(b),'index_sha256':hashlib.sha256(b).hexdigest(),'failures':[x for x in out if 'error' in x]}))
