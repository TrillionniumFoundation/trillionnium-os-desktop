from pathlib import Path
import urllib.request,concurrent.futures,json,hashlib
r=Path('/workspace/scratch/265e5bca485a/pocket4_eight_apps/framework_provider_repair/normal06'); dest=r/'reference/upstream-tree'
items=[('platform/prebuilts/sdk','0f07e8d60ab0aba46129e427101f96ba459a95c1','current','sdk-current'),('platform/superproject','28f0bbddc24d56c8ec5a8df5342ac7a292184039','prebuilts','superproject-prebuilts'),('platform/platform_testing','6abefd291d50dee240ed2b22572d273175f070da','libraries/screenshot/utils','platform-testing-screenshot-utils'),('platform/packages/apps/PersonalContext','025cc78a5a242ab434161d462e8d67e327db64d3','','personalcontext-root'),('platform/frameworks/base','94b4c163b7dfe5ce3607f7bb8456f9573f7de57d','packages/SystemUI/compose/scene','systemui-scene')]
def one(item):
 repo,commit,path,label=item;url=f'https://android.googlesource.com/{repo}/+/{commit}/{path}/?format=JSON'
 try:
  with urllib.request.urlopen(url,timeout=25) as f: raw=f.read(1048577);status=f.status
  assert len(raw)<=1048576;data=json.loads(raw.split(b'\n',1)[1]);p=dest/(label+'.raw.json')
  if p.exists(): assert p.read_bytes()==raw
  else:p.write_bytes(raw)
  meta={'repository':repo,'commit':commit,'path':path,'url':url,'status':status,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'TLS':'urllib default verified'};p.with_suffix('.source.json').write_text(json.dumps(meta,indent=2)+'\n');return {**meta,'entries':data['entries']}
 except Exception as e:return {'path':path,'url':url,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for result in pool.map(one,items):print(json.dumps(result))
