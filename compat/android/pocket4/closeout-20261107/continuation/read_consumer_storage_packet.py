import os,stat,json,hashlib,gzip,base64
from pathlib import Path
F=Path('/home/alex/work/pocket4-android-final')
targets=['/usr/local/bin/android-app','/usr/local/bin/android-app-digitalis','/usr/local/bin/android-app-digitalis-validation','/usr/local/libexec/android-digitalis-observe-helper','/usr/local/libexec/android-digitalis-helper','/usr/local/libexec/android-digitalis-validation-helper']
manifest=json.loads((F/'deployment/manifest.json').read_text())
bytarget={x['install_target']:x for x in manifest['payload']}
files=[]
for target in targets:
 for version,p,expected in [('installed',Path(target),None),('candidate',Path(bytarget[target]['path']),bytarget[target])]:
  s=p.lstat();assert stat.S_ISREG(s.st_mode)and s.st_size<=1048576,str(p)
  data=p.read_bytes();h=hashlib.sha256(data).hexdigest()
  if expected:assert h==expected['sha256']and len(data)==expected['bytes']
  files.append({'path':str(p),'target':target,'version':version,'bytes':len(data),'sha256':h,'text':data.decode('utf-8')})
B=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12')
for rel in ['frozen13/build_runtime13.py','frozen13/smali_equivalence.py','frozen13/StorageSessionController.smali','frozen15/align_runtime15.py']:
 p=B/rel;s=p.lstat();assert stat.S_ISREG(s.st_mode)and s.st_size<=2097152,str(p)
 data=p.read_bytes()
 files.append({'path':str(p),'version':'current_storage_transform_source','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'text':data.decode('utf-8')})
raw=json.dumps({'schema':'pocket4-task-source-readonly-packet-v1','files':files,'deployment_manifest_sha256':hashlib.sha256((F/'deployment/manifest.json').read_bytes()).hexdigest()},sort_keys=True,separators=(',',':')).encode()
blob=gzip.compress(raw,compresslevel=9,mtime=0)
print(json.dumps({'encoding':'gzip+base64','raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),'compressed_bytes':len(blob),'files':len(files),'data':base64.b64encode(blob).decode()},separators=(',',':')))

