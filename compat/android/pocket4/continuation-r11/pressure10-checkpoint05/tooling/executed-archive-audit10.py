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
profiles=[["pressure","06","33a95d6a65fa6b647fcf9175935f603750c2ef21de1bab8bba6c4e9cd0c579f5","0a155907521f48d6c52af7fb71a0705b3c1ac00f5bf677da98d5a3f8efc47002","158ec28a6c0cd05c36314f30a14feec6a93d7a793e34790fe5b957d3b9f5c67e",46],["stale","07","0bf2773de22aeb32b8ae45c38739cb1d8cee42f60a2f4441f507a15802836b54","8d9af25ca53b577a0afc40166bc45531fc7de13e065eb6203664a5b3d51b1fdc","8e1099ca1f0491ce4a59c04cef93bb460ee8ad8612d2d8084748899e6b089893",45]]

def module(path,pin,name):
 raw=read(path,131072);need(sha(raw)==pin,'verification source pin')
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
q=module(Path('/home/alex/work/pocket4-lmkd-host-pressure-r11-source-10/owned-relay/qualify_pressure.py'),
 '73a7405d3b663138e5a321257197ae073a01302631a9c21044076cb211651c31','pinned_qualifier10')
c=module(Path('/home/alex/work/pocket4-lmkd-pressure-r11-coordinator-source-10/once.py'),
 '01d153c4b9c363754a10adbcaa109025cdbb28dbeac2a31629096ee3cf51559a','pinned_coordinator10')
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
 need(r['phase']==phase and r['source_manifest_sha256']==c.SOURCE and r['matching_build_receipt_sha256']==c.BUILD and r['binaries_sha256']==c.BINS,'source/build/binary scope')
 need(sha(payload['source/source-manifest.json'])==c.SOURCE and sha(payload['source/matching-build-result.json'])==c.BUILD,'source/build bytes')
 for name,entry in r['retained_files'].items():
  b=payload['evidence/'+name];need(sha(b)==entry['sha256'] and len(b)==entry['bytes'],'retained byte pin')
 need(r['exact_owned_cleanup_verified'] is True and r['main_epoch_unchanged_after_cleanup'] is True and
  r['outcome_unknown'] is False and r['forced_teardown'] is False and not r.get('cleanup_error') and
  r['owned_cgroup_after_stop']=='absent' and r['post_stop_status']['LoadState']=='not-found','actual cleanup/Main closure')
 qmraw=payload['evidence/qualification-inputs.json'];need(sha(qmraw)==r['qualification']['evidence_manifest_sha256'],'external qualification manifest')
 qm=q.decode(qmraw);qd={}
 need(len(qm['files'])==len(q.required_names(phase)),'exact evidence row count')
 for row in qm['files']:
  name=row['name'];need(name in q.required_names(phase) and name not in qd,'unique required evidence')
  b=payload['evidence/'+name];need(len(b)==row['bytes'] and sha(b)==row['sha256'],'qualification row pin');qd[name]=q.decode(b)
 need(set(qd)==q.required_names(phase),'exact evidence set')
 got=q.qualified(qm,qd,phase)
 need(all(r['qualification'].get(k)==v for k,v in got.items()),'retained qualification differs')
 c.require_phase_qualification(phase,r['qualification_returncode'],got)
 identity=c.bind_terminal(r['terminal_status'],r['resources_first_observed'],qd['outer-final.json'],got,r['unit'],r['invocation_id'])
 need(r['ok'] is True and r['partial_medium_only'] is False and r['external_unit_binding_verified'] is True and identity==r['outer_identity_bound'] and
  r['terminal_status']['Result']=='success' and r['terminal_status']['ExecMainStatus']=='0','actual complete invocation')
 flags=c.phase_result_flags(phase,True,r['qualification_returncode'])
 need(all(r.get(k)==v for k,v in flags.items()),'outer narrow scope flags')
 need(r['stale_qualified'] is False and r['stale_critical_qualified'] is False and r['native_stale_drop_observed'] is False and
  r['above_high_stale_zero_kill_verified'] is False,'no independent native expiry/above-high gate')
 detail={'phase':phase,'archive':str(root/'owned-evidence.tar.gz'),'archive_sha256':ap,'manifest_sha256':mp,
  'coordinator_result_sha256':rp,'payload_files_verified':len(payload),'invocation_id':r['invocation_id'],
  'terminal':r['terminal_status'],'exact_cleanup':True,'main_epoch_unchanged':True,'phase_pass':r['ok'],
  'qualification_recomputed':got,'scope_flags_recomputed':flags,'external_unit_identity_rebound':identity,
  'outer_final':qd['outer-final.json'],'target_cleanup':qd['target-cleanup.json'],
  'broker_pressure_audit':qd['broker-pressure-audit.json'],'pressure_workload':qd['pressure-workload.json']}
 if phase=='pressure':
  need(r['pressure_qualified'] is True and got['critical_event_observed_in_phase'] is True and
   got['native_critical_kill_decision_observed'] is True and got['fresh_critical_event_correlated_with_cached_exit'] is True,'actual complete critical positive')
 else:
  need(r['stale_relief_critical_qualified'] is True and r['stale_test_scope']=='relieved-domain-aged-critical-queue' and
   got['critical_event_observed_in_phase'] is True and got['stale_after_allocator_relief_zero_kill_verified'] is True,'actual relief critical stale scope')
  detail.update(pressure_relief=qd['pressure-relief.json'],stale_aging=qd['stale-aging.json'])
 reports.append(detail)
summary={'schema':1,'actual_read_only_archive_audit':True,'audited_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'source_manifest_sha256':c.SOURCE,'matching_build_receipt_sha256':c.BUILD,'profiles':reports,
 'any_runtime_reexecuted':False,'installed_files_changed':False,'all_apps_production_ready':False,
 'native_stale_drop_observed':False,'above_high_stale_zero_kill_verified':False,
 'installed_supervisor_recovery_qualified':False,'production_cgroup_kill_qualified':False}
out=Path('/home/alex/work/pocket4-lmkd-pressure-r11-revision10-audit-01');out.mkdir(mode=0o700)
data=(json.dumps(summary,indent=2,sort_keys=True)+'\n').encode()
fd=os.open(out/'report.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
print(json.dumps({'ok':True,'report':str(out/'report.json'),'sha256':sha(data),'bytes':len(data),
 'payload_counts':[x['payload_files_verified'] for x in reports],'positive_critical_pass':reports[0]['phase_pass'],
 'stale_relief_critical_pass':reports[1]['phase_pass'],'legacy_stale_critical_qualified':False,
 'native_stale_drop_observed':False,'above_high_stale_zero_kill_verified':False,
 'exact_cleanup_both':True,'main_epoch_unchanged_both':True,'runtime_reexecuted':False}),flush=True)
