#!/usr/bin/env python3
"""Offline integrity check; no compiler, QEMU, GDB, network or source mutation."""
from pathlib import Path
import gzip,hashlib,io,json,os,stat,sys,tarfile
root=Path(sys.argv[1]).resolve()
def require(ok,reason):
 if not ok:raise SystemExit(reason)
def body(path):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  a=os.fstat(fd);require(stat.S_ISREG(a.st_mode),'not regular: '+str(path)); chunks=[]
  while b:=os.read(fd,1024*1024):chunks.append(b)
  z=os.fstat(fd); require((a.st_dev,a.st_ino,a.st_mode,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_mode,z.st_size,z.st_mtime_ns,z.st_ctime_ns),'unstable: '+str(path))
  return b''.join(chunks)
 finally:os.close(fd)
def sha(b):return hashlib.sha256(b).hexdigest()
sums={}
for line in body(root/'SHA256SUMS').decode().splitlines():
 digest,name=line.split('  ',1);require(name not in sums and not Path(name).is_absolute() and '..' not in Path(name).parts,'invalid sums path');sums[name]=digest
files={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
require(files==set(sums),'checksum file set differs')
for name,digest in sums.items():
 b=body(root/name);require(len(b)<=2097152,'file >2MiB: '+name);require(sha(b)==digest,'checksum differs: '+name)
archive=json.loads(body(root/'raw/manifest.json'));packed=bytearray()
for part in archive['ordered_parts']:
 b=body(root/'raw'/part['path']);require(len(b)==part['bytes'] and sha(b)==part['sha256'],'raw chunk differs');packed.extend(b)
require(len(packed)==archive['gzip_bytes'] and sha(packed)==archive['gzip_sha256'],'raw gzip differs')
seen=set();raw_contents={}
with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz') as tar:
 for member in tar:
  require(member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts,'unsafe raw member')
  require(member.name not in seen,'duplicate member');seen.add(member.name);b=tar.extractfile(member).read();expected=archive['members'][member.name]
  require(len(b)==expected['bytes'] and sha(b)==expected['sha256'],'raw member differs: '+member.name)
  if member.name.endswith(('qemu.json','/result.json','commands.json')):raw_contents[member.name]=b
require(seen==set(archive['members']),'raw member set differs')
inputs=json.loads(body(root/'artifacts/manifest.json'));count_parts=0
for key,entry in inputs['unique_artifacts'].items():
 require(key==entry['raw_sha256'],'raw key differs');packed=bytearray()
 for part in entry['ordered_parts']:
  relative=Path(part['path']);require(not relative.is_absolute() and '..' not in relative.parts,'unsafe artifact part')
  b=body(root/'artifacts/storage'/relative);require(len(b)==part['bytes'] and sha(b)==part['sha256'],'artifact part differs');packed.extend(b);count_parts+=1
 require(len(packed)==entry['gzip_bytes'] and sha(packed)==entry['gzip_sha256'],'artifact gzip differs')
 h=hashlib.sha256();n=0
 with gzip.GzipFile(fileobj=io.BytesIO(packed),mode='rb') as stream:
  while b:=stream.read(1024*1024):n+=len(b);require(n<=entry['raw_bytes'],'artifact too large');h.update(b)
 require(n==entry['raw_bytes'] and h.hexdigest()==key,'artifact raw differs')
report=json.loads(body(root/'report.json'));phase=report['phase'];mappings=inputs['mappings']
require(len(mappings)==23,'mapping denominator differs')
if phase=='final':
 result=json.loads(raw_contents['final-matrix/result.json']);require((result['passed'],result['failed'],result['blocked'],result['selected_cases'])==(22,0,0,22),'final cases differ')
 guests=[g for case in result['cases'] for g in case.get('guests',[])];require(len(guests)==11,'final guest count differs')
 for g in guests:
  require((g['raw_exit_code'],g['wrapper_exit_code'],g['serial_valid'])==(33,33,True),'final guest exit differs')
  q=json.loads(raw_contents['final-matrix/'+g['record']]);require(q['snapshot_verification']['before_qemu'] is True and q['snapshot_verification']['after_qemu'] is True,'snapshot check failed')
 for m in mappings:require(m['passed'] and m['storage_key'] in inputs['unique_artifacts'],'final mapping missing')
 require(len(inputs['unique_artifacts'])==13,'final dedup count differs')
 commands=json.loads(raw_contents['controller-final-matrix/commands.json']);require(len(commands)==6 and all(c['returncode']==0 for c in commands),'final controller differs')
else:
 require(inputs['known_unavailable_count']==1 and inputs['retained_mapping_count']==22 and not inputs['historical_input_bytes_complete'],'before gap differs')
 missing=[m for m in mappings if not m.get('retained')];require(len(missing)==1 and missing[0]['original_artifact']['sha256'].startswith('04bd3249'),'historical missing identity differs')
 require(not inputs['unexpected_errors'] and len(inputs['unique_artifacts'])==12,'unexpected before error')
 result=json.loads(raw_contents['integration-retry/result.json']);require((result['passed'],result['failed'],result['blocked'])==(20,2,0),'initial matrix differs')
 result=json.loads(raw_contents['ktest-retry/result.json']);require(result['passed'],'correct-root ktest failed')
 totals=[g for c in result['crates'] for g in c['guests']];require(sum(g['passed'] for g in totals)==362 and sum(g['soft_skipped'] for g in totals)==3 and all(g['raw_qemu_exit']==33 for g in totals),'ktest denominator differs')
 result=json.loads(raw_contents['coverage-retry2/result.json']);require((result['passed'],result['failed'],result['selected_cases'])==(1,0,1),'coverage2 differs')
source=json.loads(body(root/'consumed-source-manifest.json'));archive_body=body(root/'consumed-source.tar.gz');require(len(archive_body)==source['archive_bytes'] and sha(archive_body)==source['archive_sha256'],'consumed source archive differs')
source_seen=set()
with tarfile.open(fileobj=io.BytesIO(archive_body),mode='r:gz') as tar:
 for member in tar:
  require(member.isfile() and member.name in source['members'] and member.name not in source_seen,'consumed source member differs');source_seen.add(member.name);b=tar.extractfile(member).read();identity=source['members'][member.name];require(len(b)==identity['bytes'] and sha(b)==identity['sha256'],'consumed source bytes differ')
require(source_seen==set(source['members']),'consumed source set differs')
require(source['runtime_source_sha']==report['source_binding']['runtime_source_sha'],'consumed source runtime differs')
binding=json.loads(body(root/'source-binding.json'));require(binding==report['source_binding'],'embedded source binding differs')
require(len(binding['source_export_paths'])==len(set(binding['source_export_paths'])),'duplicate static source path')
validations={v['path']:v for v in binding['source_export_path_validation']};require(set(validations)==set(binding['source_export_paths']),'source export validation set differs')
for path,validation in validations.items():
 require(validation['runtime_commit']==binding['runtime_source_sha'] and validation['git_object_type']=='blob' and validation['ls_tree_exit']==0,'invalid exact source validation')
 require(validation['present_in_frozen_source_exports'],'missing source export payload')
 for location in validation['present_in_frozen_source_exports']:
  original=archive['members'][location['member']] if location['archive']=='raw' else source['members'][location['member']]
  require(original['sha256']==validation['sha256'] and original['bytes']==validation['bytes'],'source export binding differs')
print(json.dumps({'passed':True,'phase':phase,'outer_files':len(sums)+1,'raw_members':len(seen),'input_mappings':len(mappings),'unique_artifacts':len(inputs['unique_artifacts']),'artifact_parts':count_parts,'known_historical_input_gap':phase=='before','checksums_sha256':sha(body(root/'SHA256SUMS'))},sort_keys=True))
