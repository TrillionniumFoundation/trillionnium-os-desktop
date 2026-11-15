"""Independent pre-normal originals; only actual owned v2 rows may restore inode/ctime."""
import hashlib,json,os,stat,time
from pathlib import Path
SCHEMA='native643-independent-before-normal-projection-originals-v1'
N=Path('/data/p4-production651-nbd-e6ac-r1/mount/source-production651');SOURCE=N/'work/aosp-source'
def need(v,m):
 if not v:raise RuntimeError(m)
def f9(s):return[s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def path_ok(value):
 need(type(value)is str,'original path must be a string');p=Path(value)
 need(p.is_absolute()and str(p)==value and p.is_relative_to(SOURCE)and p!=SOURCE and'..'not in p.parts and'.git'not in p.parts and p.name!='signing_key.pem','original path escapes fixed public source')
 return p
def parent(value):
 p=path_ok(value);fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  for part in p.parts[1:-1]:
   try:other=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
   except FileNotFoundError:os.close(fd);return None,p.name
   os.close(fd);fd=other
  return fd,p.name
 except BaseException:os.close(fd);raise
def physical(value):
 fd,name=parent(value);body=None
 if fd is None:return None
 try:
  try:st=os.stat(name,dir_fd=fd,follow_symlinks=False)
  except FileNotFoundError:return None
  need(stat.S_ISREG(st.st_mode)and st.st_uid==st.st_gid==1000 and st.st_nlink==1 and st.st_size<=16*1024**2,'bounded single-owned original regular file required: '+value)
  identity=f9(st);body=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=fd);need(f9(os.fstat(body))==identity,'original named/held identity differs');digest=hashlib.sha256();count=0
  while True:
   b=os.read(body,131072)
   if not b:break
   count+=len(b);need(count<=st.st_size,'original input grew');digest.update(b)
  need(count==st.st_size and f9(os.fstat(body))==identity==f9(os.stat(name,dir_fd=fd,follow_symlinks=False)),'whole original body or named identity changed')
  return{'path':value,'bytes':count,'sha256':digest.hexdigest(),'identity':identity}
 finally:
  if body is not None:os.close(body)
  os.close(fd)
def _unique_object(pairs):
 result={}
 for key,value in pairs:
  need(key not in result,'duplicate v2 JSON object key');result[key]=value
 return result
def parse_v2(raw):
 doc=json.loads(raw,object_pairs_hook=_unique_object);need(type(doc)is dict and set(doc)=={'schema_version','originals'}and type(doc['schema_version'])is int and doc['schema_version']==2 and type(doc['originals'])is list,'strict v2 originals required');out={}
 for row in doc['originals']:
  need(type(row)is dict and set(row)=={'path','bytes','modified','permissions_mode'},'exact v2 original fields required');path_ok(row['path']);need(row['path']not in out,'duplicate original path')
  if row['bytes']is None:
   need(row['modified']is row['permissions_mode']is None,'original absence must have all-null restoration fields');out[row['path']]=None
  else:
   need(type(row['bytes'])is list and len(row['bytes'])<=16*1024**2 and all(type(b)is int and 0<=b<=255 for b in row['bytes']),'bounded full original byte array required')
   mode=row['permissions_mode'];mtime=row['modified'];need(type(mode)is int and stat.S_ISREG(mode)and mode&~0o107777==0,'original regular mode required')
   need(type(mtime)is dict and set(mtime)=={'secs_since_epoch','nanos_since_epoch'}and all(type(v)is int for v in mtime.values())and mtime['secs_since_epoch']>=0 and 0<=mtime['nanos_since_epoch']<10**9,'exact original nsmtime required')
   body=bytes(row['bytes']);out[row['path']]={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'mode':mode,'mtime_ns':mtime['secs_since_epoch']*10**9+mtime['nanos_since_epoch']}
 return out
def original(row):return{'bytes':row['bytes'],'sha256':row['sha256'],'mode':row['identity'][2],'mtime_ns':row['identity'][7]}
def validate_baseline(baseline):
 need(baseline['schema']==SCHEMA and baseline['source']==str(SOURCE)and baseline['source_H']=='1a1d76d6d51-392-a9d'and baseline['normal_H']=='1a1d7487a36-392-a46','exact independent current-Cuttlefish-source/normala46 baseline required')
 known={r['path']:r for r in baseline['physical']};absent=set(baseline['absent']);need(len(known)==len(baseline['physical'])==146 and len(absent)==len(baseline['absent'])==15 and not(set(known)&absent)and set(baseline['paths'])==set(known)|absent and len(baseline['paths'])==161,'all161 original roles exactly once')
 for value in baseline['paths']:path_ok(value)
 return known,absent
def capture(reader,origin):
 rows=parse_v2(reader.pinned(origin,128*1024**2,contents=True)[1]);need(len(rows)==161 and sum(v is None for v in rows.values())==15,'authenticated original8f7-161 path scope');files=[];absent=[]
 for path in sorted(rows):
  ref=physical(path)
  if ref is None:absent.append(path)
  else:files.append(ref)
 need(len(files)==146 and len(absent)==15,'current physical projection shape changed before normal')
 baseline={'schema':SCHEMA,'source':str(SOURCE),'source_H':'1a1d76d6d51-392-a9d','normal_H':'1a1d7487a36-392-a46','scope_original8f7_journal':origin,'paths':sorted(rows),'physical':files,'absent':absent,'captured_ns':time.time_ns(),'source_writes':0,'full_builds_started':0,'runtime_qualified':False};verify_restored(baseline,{})
 return baseline
def compare(raw,baseline,*,complete):
 known,absent=validate_baseline(baseline);rows=parse_v2(raw);need(set(rows)<=set(baseline['paths'])and(not complete or set(rows)==set(baseline['paths'])),'actual owned v2 projection scope differs')
 for path,row in rows.items():
  need((path in absent and row is None)or(path in known and row==original(known[path])),'actual v2 original differs from independent pre-normal bytes/mode/nsmtime/absence: '+path)
 return rows
def verify_restored(baseline,projected):
 known,absent=validate_baseline(baseline);need(set(projected)<=set(baseline['paths']),'unlisted restoration role');fresh=[];changed=[]
 for path,before in known.items():
  now=physical(path);need(now is not None and original(now)==original(before),'original bytes/mode/nsmtime were not restored: '+path)
  if now['identity']!=before['identity']:
   need(path in projected and projected[path]==original(before),'physical F9 changed without exact owned v2 original: '+path)
   need(all(now['identity'][k]==before['identity'][k]for k in(0,2,3,4,5,6,7)),'restore may change only original inode/ctime: '+path);changed.append({'path':path,'before':before['identity'],'after':now['identity']})
  fresh.append(now)
 for path in absent:need(physical(path)is None,'original absence was not restored: '+path)
 for row in fresh:need(physical(row['path'])==row,'complete161 boundary changed during verification')
 return{'actual_roles':161,'original_files':146,'original_absences':15,'actual_owned_v2_originals':len(projected),'whole_original_bytes_mode_nsmtime_absence_verified':True,'only_actual_projected_inode_ctime_may_change':True,'changed_F9':changed,'source_writes':0,'runtime_qualified':False}
def expected_argv(contract):return contract['full_context']['normal_argv']
def actual_projection(reader,contract):
 ctx=contract['full_context'];result=Path(ctx['result']);normal_path=result/'commands/normal-full-native-engine-ART-pair.json';baseline=reader.document(contract['projection_baseline']);projected={};evidence=[]
 if not normal_path.exists():return projected,evidence
 normal=reader.document(reader.file_ref(normal_path));life=normal['lifecycle'];need(normal['argv']==expected_argv(contract)and normal['driver']['argv']==normal['argv']and normal['driver']['exe']==normal['argv'][0]and normal['driver']['cgroup']=='0::/system.slice/'+ctx['unit']+'\n','actual normal full command binding required')
 need(normal['owned_retirement_complete']is life['child_reaped']is life['pidfd_closed']is life['owned_tree_cleanup_complete']is True and life['remaining_owned_children']==[],'actual normal full must retire before restoration proof')
 outer=reader.document(reader.file_ref(Path(ctx['control'])/'outer-execution.json'));need(outer['full_unit']==ctx['unit']and outer['started_ns']<=normal['started_ns']<=normal['finished_ns'],'actual original outer/normal lineage differs')
 effective=result/'effective-inputs/result.json'
 if effective.exists():
  record=reader.document(reader.file_ref(effective));need(record['state']=='OBSERVED_NOT_COMPILED_QUALIFIED'and record['actual_command_argv']==normal['argv']and record['driver_initial_observation']==normal['driver']and record['outer_admission']==reader.file_ref(Path(ctx['control'])/'outer-execution.json')and normal['started_ns']<=record['begun_ns']<=record['finished_ns']<=normal['finished_ns'],'exact actual owned Soong observation required')
  ref=record['source_projection_copy'];need(ref['path']==str(result/'effective-inputs/source-projection.original.json'),'exact current effective journal copy required');projected.update(compare(reader.pinned(ref,128*1024**2,contents=True)[1],baseline,complete=True));evidence.append(reader.file_ref(effective))
 for proof_path in(result/'interrupted-projection-before-recovery.json',Path(ctx['control'])/'interrupted-projection-before-fallback.json'):
  if not proof_path.exists():continue
  record=reader.document(reader.file_ref(proof_path));need(record['schema']=='native643-owned-retired-command-interrupted-v2-copy-v1'and record['normal_command']==reader.file_ref(normal_path)and record['outer_admission']==reader.file_ref(Path(ctx['control'])/'outer-execution.json')and record['copy']['path']==str(proof_path.with_suffix('.raw.json'))and record['live_journal']['path']==str(N/'work/source-projection.json')and type(record['captured_ns'])is int and record['captured_ns']>=normal['finished_ns'],'exact normal interrupted journal lineage');rows=compare(reader.pinned(record['copy'],128*1024**2,contents=True)[1],baseline,complete=False)
  for path,row in rows.items():need(path not in projected or projected[path]==row,'owned journal original changed between witnesses');projected[path]=row
  evidence.append(reader.file_ref(proof_path))
 return projected,evidence
def capture_interrupted(s,contract,destination):
 result=Path(contract['full_context']['result']);normal_path=result/'commands/normal-full-native-engine-ART-pair.json';normal,normal_ref=s.read_json(normal_path);life=normal['lifecycle'];need(normal['argv']==expected_argv(contract)and normal['owned_retirement_complete']is life['child_reaped']is life['pidfd_closed']is life['owned_tree_cleanup_complete']is True and life['remaining_owned_children']==[],'only exact retired normal journal can be recovered')
 baseline=json.loads(s.pinned(contract['projection_baseline'],contents=True)[1]);target=Path(destination).with_suffix('.raw.json');live=s.file_ref(N/'work/source-projection.json',128*1024**2,copy_to=target);copy=s.file_ref(target,128*1024**2);rows=compare(s.pinned(copy,128*1024**2,contents=True)[1],baseline,complete=False);need(s.file_ref(N/'work/source-projection.json',128*1024**2)==live,'interrupted journal changed before recovery')
 return s.create(destination,{'schema':'native643-owned-retired-command-interrupted-v2-copy-v1','normal_command':normal_ref,'outer_admission':s.file_ref(Path(contract['full_context']['control'])/'outer-execution.json'),'live_journal':live,'copy':copy,'actual_originals':len(rows),'captured_ns':time.time_ns(),'source_writes':0})
def boundary(reader,contract,*,initial,physical_helper):
 baseline=reader.document(contract['projection_baseline']);projected,evidence=({},[])if initial else actual_projection(reader,contract);proof=verify_restored(baseline,projected);index=reader.document(contract['cuttlefish_source']['physical_index']);observed=[]
 need(index['file_count']==30955 and len(index['files'])==30955,'all30955 original source roles required')
 for row in index['files']:
  allowed=not initial and row['path']in projected
  if allowed:need(projected[row['path']]==original(row),'projected physical original differs from Cuttlefish source epoch')
  ident=physical_helper.physical(reader,row,require_original_f9=not allowed);need(ident[7]==row['identity'][7],'all30955 original physical nsmtime must restore');observed.append((row,ident))
 for row,identity in observed:
  fd=reader.open_absolute(Path(row['path']).parent,os.O_RDONLY|os.O_DIRECTORY)
  try:need(f9(os.stat(Path(row['path']).name,dir_fd=fd,follow_symlinks=False))==identity,'30955 boundary changed during complete held-read audit')
  finally:os.close(fd)
 for row in index['auxiliary_refs']:reader.pinned(row,1024**2)
 proof.update(initial=initial,source_originals=30955,actual_projection_evidence=evidence,unchanged_F9_required_outside_actual_projection=True,all_source_original_nsmtime_verified=True);return proof
