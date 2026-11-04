from pathlib import Path, PurePosixPath
import hashlib, io, json, os, stat, tarfile, types, datetime
def need(v,m):
 if not v: raise RuntimeError(m)
def sha(b): return hashlib.sha256(b).hexdigest()
def read(p,limit):
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno()); need(stat.S_ISREG(a.st_mode) and a.st_size<=limit,'bounded regular file')
  raw=f.read(limit+1); b=os.fstat(f.fileno())
  need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)==(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns) and len(raw)==a.st_size,'read changed')
  return raw
profiles=[
 ('pressure','04','13e2357c590b540d42bb6a745cfe9bb9429cdb0d68269ffd6a99bf54be9adb00','184b0db208fd06cda07c1b2ae9a73fee31f5c12c058050266f9536cf6b4d790a','cf081ede4d6d757b522bd35b6280bda03a27e5517e0119e9dabb219cbd13e98a',46),
 ('stale','05','64c887b51f18b7b04275b0715d990aab422ec51be3e05357692b90d96b0354af','99644b1eda1606096319950141665c6430496f28096286a6bd399cb2b62eb0e9','f028dd348031341f3ef8ed1f8f26b8e1ff87d8e560e919ddb5a807b07e9cc663',32)]

def module(path,pin,name):
 raw=read(path,131072);need(sha(raw)==pin,'verification source pin')
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
q=module(Path('/home/alex/work/pocket4-lmkd-host-pressure-r11-source-09/owned-relay/qualify_pressure.py'),
 '271d0d95f5532fface42fbe25f55787e455291c23a23a26ed74b23a4e08b88d5','pinned_qualifier09')
c=module(Path('/home/alex/work/pocket4-lmkd-pressure-r11-coordinator-source-10/parent/once.py'),
 'c699848a1a6315a6daf398f2962c4d5c27a705e47900987da2835926133744e2','pinned_coordinator09')
reports=[]
for phase,suffix,ap,mp,rp,count in profiles:
 root=Path('/home/alex/work/pocket4-lmkd-pressure-r11-export-'+suffix)
 raw=read(root/'owned-evidence.tar.gz',1048576);need(sha(raw)==ap,'archive pin')
 payload={}
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as t:
  members=t.getmembers();need(len(members)==count+1,'member count')
  for m in members:
   p=PurePosixPath(m.name);need(m.isfile() and not p.is_absolute() and '..' not in p.parts and m.name not in payload and m.size<=1048576,'canonical unique regular member')
   payload[m.name]=t.extractfile(m).read()
 need(sum(map(len,payload.values()))<8*1048576,'total bound')
 manifest_raw=payload.pop('export-manifest.json');need(sha(manifest_raw)==mp,'manifest pin')
 manifest=json.loads(manifest_raw);need(set(manifest['files'])==set(payload),'exact member set')
 for name,entry in manifest['files'].items():
  b=payload[name];need(len(b)==entry['bytes'] and sha(b)==entry['sha256'],'payload pin '+name)
 result_raw=payload['coordinator/02-'+phase+'-once/result.json'];need(sha(result_raw)==rp,'original result pin')
 need(read(root/'coordinator-result.json',1048576)==result_raw,'exact original result')
 r=json.loads(result_raw)
 need(r['phase']==phase and r['source_manifest_sha256']==c.SOURCE and r['matching_build_receipt_sha256']==c.BUILD,'source/build scope')
 need(sha(payload['source/source-manifest.json'])==c.SOURCE and sha(payload['source/matching-build-result.json'])==c.BUILD,'source/build bytes')
 for name,entry in r['retained_files'].items():
  b=payload['evidence/'+name];need(sha(b)==entry['sha256'] and len(b)==entry['bytes'],'retained byte pin')
 need(r['exact_owned_cleanup_verified'] is True and r['main_epoch_unchanged_after_cleanup'] is True and
  r['outcome_unknown'] is False and not r.get('cleanup_error') and r['owned_cgroup_after_stop']=='absent' and
  r['post_stop_status']['LoadState']=='not-found','actual cleanup/Main closure')
 detail={'phase':phase,'archive':str(root/'owned-evidence.tar.gz'),'archive_sha256':ap,'manifest_sha256':mp,
  'coordinator_result_sha256':rp,'payload_files_verified':len(payload),'invocation_id':r['invocation_id'],
  'terminal':r['terminal_status'],'exact_cleanup':True,'main_epoch_unchanged':True,'phase_pass':r['ok']}
 if phase=='pressure':
  qmraw=payload['evidence/qualification-inputs.json'];need(sha(qmraw)==r['qualification']['evidence_manifest_sha256'],'external qualification manifest')
  qm=q.decode(qmraw);qd={}
  need(len(qm['files'])==len(q.required_names(phase)),'exact evidence row count')
  for row in qm['files']:
   name=row['name'];need(name in q.required_names(phase) and name not in qd,'unique required evidence')
   b=payload['evidence/'+name];need(len(b)==row['bytes'] and sha(b)==row['sha256'],'qualification row pin');qd[name]=q.decode(b)
  need(set(qd)==q.required_names(phase),'exact evidence set')
  got=q.qualified(qm,qd,phase)
  need(all(r['qualification'].get(k)==v for k,v in got.items()),'retained qualification differs')
  identity=c.bind_terminal(r['terminal_status'],r['resources_first_observed'],qd['outer-final.json'],got,r['unit'],r['invocation_id'])
  need(r['ok'] is True and r['pressure_qualified'] is True and r['partial_medium_only'] is False and
   r['external_unit_binding_verified'] is True and identity==r['outer_identity_bound'] and
   r['terminal_status']['Result']=='success' and r['terminal_status']['ExecMainStatus']=='0','actual complete positive')
  detail.update(qualification_recomputed=got,external_unit_identity_rebound=identity,
   outer_final=qd['outer-final.json'],target_cleanup=qd['target-cleanup.json'],
   broker_pressure_audit=qd['broker-pressure-audit.json'])
 else:
  failure=json.loads(payload['evidence/phase-failure.json']);before=json.loads(payload['evidence/pressure-before.json'])
  log=payload['unit/unit.stderr'].decode()
  need(r['ok'] is False and r['stale_qualified'] is False and r['stale_critical_qualified'] is False and
   r.get('qualification') is None and r['terminal_status']['ExecMainStatus']=='1' and
   'stale interval has new pressure stalls' in log,'preserved actual stale failure')
  detail.update(failed_check='stale interval has new pressure stalls',failure_phase='strict aging before resume',
   failure_sample=failure,pressure_before=before,pressure_elapsed_ms=failure['monotonic_ms']-before['monotonic_ms'],
   phase_failure_sha256=sha(payload['evidence/phase-failure.json']),owned_stderr=log,
   joined_retirement_audit_present='evidence/broker-pressure-audit.json' in payload,
   final_outer_counters_present='evidence/outer-final.json' in payload,native_stale_drop_observed=False)
 reports.append(detail)
summary={'schema':1,'actual_read_only_archive_audit':True,'audited_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'source_manifest_sha256':c.SOURCE,'matching_build_receipt_sha256':c.BUILD,'profiles':reports,
 'any_runtime_reexecuted':False,'installed_files_changed':False,'all_apps_production_ready':False}
out=Path('/home/alex/work/pocket4-lmkd-pressure-r11-revision09-audit-01');out.mkdir(mode=0o700)
data=(json.dumps(summary,indent=2,sort_keys=True)+'\n').encode()
fd=os.open(out/'report.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
print(json.dumps({'ok':True,'report':str(out/'report.json'),'sha256':sha(data),'bytes':len(data),
 'payload_counts':[x['payload_files_verified'] for x in reports],'positive_pass':reports[0]['phase_pass'],
 'stale_pass':reports[1]['phase_pass'],'stale_failed_check':reports[1]['failed_check'],'exact_cleanup_both':True,
 'main_epoch_unchanged_both':True,'runtime_reexecuted':False}),flush=True)
