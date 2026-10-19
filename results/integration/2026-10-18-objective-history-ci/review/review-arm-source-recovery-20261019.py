# Recovery execution copy generated on 2026-10-19.
# Original logic retained; only new API-observation and temporary-output paths adapted.
# This reconstructs a new review; it does not reproduce the lost 2026-10-18 final receipt bytes.
import collections,hashlib,importlib,json,os,pathlib,re,stat,struct,subprocess,sys,tempfile,tomllib,zipfile,zlib
from datetime import datetime,timezone
sys.dont_write_bytecode=True
B=pathlib.Path('/workspace/scratch/499c7902de8e')
D=B/'r9-integration'; O=B/'r9-hepta-owner'
DESKTOP='46dcb2d691827f7aa3ad7903dae09d39fd338126'
DTREE='8d5de807c41090e3d987764daec9c235ebd022a1'
OWNER='2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5'
OTREE='f4ef891d43baf90d6eebd29921a5ed03222ef3ab'
CONTRACT_SHA='f0fc1110233dc38542097c6f9f7ef2e3f6ca5eb215fa2b4447e556cd7ac46981'
ZIP_SHA='2717d25e42c9a1329e07bce92459db89a3109f72313ebac3e6010ddc8f1accd4'
OUT=pathlib.Path('/tmp/r10-arm-history-review'); OUT.mkdir(exist_ok=True)
def need(v,m):
 if not v: raise RuntimeError(m)
def sha(v): return hashlib.sha256(v).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def git(repo,*args): return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.PIPE,timeout=30)
def blob(repo,rev,path):return git(repo,'show',rev+':'+path)
def file_rec(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
started=now()
P=B/'r9-evidence/ci/r9-history-arm-evidence-39115155092.zip'
raw=P.read_bytes(); need(len(raw)==852554 and sha(raw)==ZIP_SHA,'zip identity')
z=zipfile.ZipFile(P)
infos=z.infolist();need(len(infos)==99,'entry count')
names=[i.filename for i in infos]
need(len(names)==len(set(names))==len({n.casefold() for n in names}),'zip duplicate or case alias')
need(z.testzip() is None,'zip CRC')
need(z.comment==b'','unexpected zip comment')
eocd=raw.rfind(b'PK\x05\x06')
fields=struct.unpack_from('<4s4H2LH',raw,eocd)
need(fields[1]==fields[2]==0 and fields[3]==fields[4]==99,'zip multidisk/count')
need(eocd+22+fields[7]==len(raw) and fields[7]==0,'zip tail/comment')
need(fields[6]==z.start_dir and fields[5]+fields[6]==eocd,'zip central directory')
manifest=[]; contents={}; ranges=[]
for i in infos:
 pp=pathlib.PurePosixPath(i.filename)
 need(not pp.is_absolute() and '\\' not in i.filename and '\x00' not in i.filename
      and all(x not in ('.','..','') for x in i.filename.split('/'))
      and ':' not in i.filename and not i.is_dir(),'unsafe zip name')
 mode=i.external_attr>>16; ftype=stat.S_IFMT(mode)
 need(ftype in (0,stat.S_IFREG) and not stat.S_ISLNK(mode),'nonregular zip member')
 need(not i.flag_bits&1 and i.compress_type==zipfile.ZIP_DEFLATED,'encrypted or unsupported zip member')
 need(i.file_size<4*1024*1024,'member bound')
 h=struct.unpack_from('<4s5H3L2H',raw,i.header_offset)
 need(h[0]==b'PK\x03\x04' and h[2]==i.flag_bits and h[3]==i.compress_type,'local header mismatch')
 local_name=raw[i.header_offset+30:i.header_offset+30+h[-2]].decode('utf-8' if i.flag_bits&0x800 else 'cp437')
 need(local_name==i.filename,'local filename differs')
 start=i.header_offset; payload=start+30+h[-2]+h[-1]; end=payload+i.compress_size
 need(0<=start<payload<=end<=z.start_dir,'member range')
 ranges.append((start,end,i.filename))
 value=z.read(i)
 need(len(value)==i.file_size and (zlib.crc32(value)&0xffffffff)==i.CRC,'CRC/size mismatch')
 contents[i.filename]=value
 manifest.append({'path':i.filename,'bytes':i.file_size,'compressed_bytes':i.compress_size,
                  'sha256':sha(value),'crc32':f'{i.CRC:08x}','mode_octal':oct(mode),
                  'local_header_offset':i.header_offset,'crc_and_size_verified':True})
for a,b in zip(sorted(ranges),sorted(ranges)[1:]):need(a[1]<=b[0],'overlapping zip ranges')
need(sum(i.file_size for i in infos)==8622417,'total bytes')
need(not any(any(x in pathlib.PurePosixPath(n).parts for x in ['fleet','home','target','targets','.git','cargo-home','rustup-home']) for n in names),'unapproved tree uploaded')
def J(n):return json.loads(contents[n])
report=J('work/report.json'); before=J('identity/desktop-before.json'); after=J('identity/final-checkouts.json')
builds=J('identity/builds.json'); upstream=J('identity/hepta-before.json'); alloc=J('identity/allocation.json'); contract=J('locks/OBJECTIVE_HISTORY_CONTRACT.json')
need(report['status']=='passed' and report['runtime_executed'] is True and contents['runtime-exit-code.txt']==b'0\n','runtime success')
need(contents['work/report.json']==contents['logs/history-gate.log'],'gate log differs report')
need(git(D,'rev-parse',DESKTOP+'^{tree}').decode().strip()==DTREE,'desktop raw tree')
need(git(O,'rev-parse',OWNER+'^{tree}').decode().strip()==OTREE,'owner raw tree')
need(before['commit']==DESKTOP and before['tree']==DTREE and before['consumer_tree']==git(D,'rev-parse',DESKTOP+':services/hepta-os').decode().strip(),'before identity')
need(after['unchanged'] is True and before['source_sha256']==after['source_sha256'],'desktop map drift')
source_path='services/hepta-os/OBJECTIVE_HISTORY_CONTRACT.json'
need(contents['locks/OBJECTIVE_HISTORY_CONTRACT.json']==blob(D,DESKTOP,source_path),'contract raw blob')
need(sha(contents['locks/OBJECTIVE_HISTORY_CONTRACT.json'])==CONTRACT_SHA,'contract sha')
need(contract['schema_version']==1 and contract['repository'].rstrip('/').removesuffix('.git')=='https://github.com/TrillionniumFoundation/hepta-private-ci'
     and contract['base_commit']=='f8c9419df6ddeb36ff8b522a50219981fb8d9345' and contract['commit']==OWNER
     and contract['control_schema_version']==2 and contract['profile']=='linux-local-known-objective-history'
     and contract['read_method_allowlist']==['ObjectiveAdmission'] and contract['max_control_frame_bytes_including_newline']==65536,'contract fields')
subprocess.run(['git','-C',str(O),'merge-base','--is-ancestor',contract['base_commit'],OWNER],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=30)
contract_fields=contract['files']; paths=[v['path'] for v in contract_fields]
need(len(paths)==len(set(paths))==36 and all(p.startswith('codex-rs/') and '..' not in pathlib.PurePosixPath(p).parts for p in paths),'reviewed paths')
owner_map={}
for entry in contract_fields:
 h=sha(blob(O,OWNER,entry['path']));need(h==entry['sha256'],'owner file '+entry['path']);owner_map[entry['path']]=h
probe_names=['objective_history_probe.rs','objective_history_client.rs','original_objective_owner.rs','original_objective_fixture.rs','original_objective_profile.json','run_objective_history.py','run_original_objective.py','run_original_agentd.py']
fixed_inputs={n:sha(blob(D,DESKTOP,'tests/integration/hepta/'+n)) for n in probe_names}
desktop_paths=set(git(D,'ls-tree','-r','--name-only',DESKTOP,'--','services/hepta-os').decode().splitlines())
desktop_paths.update('tests/integration/hepta/'+n for n in probe_names); desktop_paths.add('.github/workflows/hepta-objective-history.yml')
need(len(desktop_paths)==len(before['source_sha256'])==35 and desktop_paths==set(before['source_sha256']),'desktop scope')
desktop_map={}
for p,wanted in before['source_sha256'].items():
 h=sha(blob(D,DESKTOP,p));need(h==wanted,'desktop hash '+p);desktop_map[p]=h
archived_sources={}
for dst,src in [('work/probe/src/main.rs','objective_history_probe.rs'),('work/probe/src/objective_history_client.rs','objective_history_client.rs'),
('work/probe/src/original_objective_fixture.rs','original_objective_fixture.rs'),('work/probe/src/original_objective_owner.rs','original_objective_owner.rs'),
('work/probe/src/original_objective_profile.json','original_objective_profile.json'),
('work/probe/src/original_objective_session.rs','original_objective_session.rs'),('work/probe/src/original_session_probe.rs','original_session_probe.rs')]:
 need(contents[dst]==blob(D,DESKTOP,'tests/integration/hepta/'+src),'archived probe source '+dst);archived_sources[dst]={'git_path':'tests/integration/hepta/'+src,'sha256':sha(contents[dst])}
expected_upstream={'commit':OWNER,'tree':OTREE,'cargo_lock_sha256':contract['cargo_lock_sha256'],'clean_checkout':True,'reviewed_files':36}
need(upstream==expected_upstream==report['upstream']==builds['upstream_before']==builds['upstream_after'],'owner source provenance')
need(before['contract']==report['contract']==builds['contract'] and report['contract']['sha256']==CONTRACT_SHA and report['contract']['desktop_commit']==DESKTOP and before['expected_hepta_commit']==OWNER,'contract provenance')
binding={'commit':OWNER,'tree':OTREE,'cargo_lock_sha256':contract['cargo_lock_sha256'],'contract_sha256':CONTRACT_SHA,'probe_inputs':fixed_inputs}
need(report['source_sha256']==fixed_inputs and report['compiled_source_binding']==binding==J('work/probe/src/objective_history_source_binding.json'),'8 source binding')
for n in probe_names:
 need(sha((D/'tests/integration/hepta'/n).read_bytes())==fixed_inputs[n],'local verifier source must equal pinned blob')
sys.path.insert(0,str(D/'tests/integration/hepta'))
history=importlib.import_module('run_objective_history')
need(history.SOURCES==probe_names,'fixed helper sources')
for archive,path,repo,rev in [('locks/hepta-Cargo.lock','codex-rs/Cargo.lock',O,OWNER),('locks/hepta-Cargo.toml','codex-rs/Cargo.toml',O,OWNER),
('locks/hepta-rust-toolchain.toml','codex-rs/rust-toolchain.toml',O,OWNER),('locks/desktop-Cargo.lock','services/hepta-os/Cargo.lock',D,DESKTOP)]:
 need(contents[archive]==blob(repo,rev,path),'lock/manifest raw blob '+archive)
need(sha(contents['locks/hepta-Cargo.lock'])==contract['cargo_lock_sha256'],'owner lock hash')
need(sha(contents['work/probe/Cargo.lock'])==report['resolved_lock_sha256'],'probe lock hash')
with tempfile.TemporaryDirectory(prefix='r9-arm-lock-audit-',dir='/tmp') as td:
 t=pathlib.Path(td);s=t/'source';r=t/'probe';(s/'codex-rs').mkdir(parents=True);r.mkdir()
 (s/'codex-rs/Cargo.lock').write_bytes(contents['locks/hepta-Cargo.lock'])
 (s/'codex-rs/Cargo.toml').write_bytes(contents['locks/hepta-Cargo.toml'])
 (r/'Cargo.lock').write_bytes(contents['work/probe/Cargo.lock'])
 verified_lock=history.original.verify_runner_lock(s,r)
need(verified_lock==report['lock_validation'] and verified_lock['shared_package_identities_checked']==735,'shared dependency identities')
need(report['patch_omission']==verified_lock['omitted_patch'],'patch omission')
metas={}
for n in ['work/resolution.log','work/locked-metadata.log']:
 lines=contents[n].splitlines(); objs=[(i+1,v) for i,v in enumerate(lines) if v.startswith(b'{')]
 need(len(objs)==1,'metadata object count')
 metas[n]={'line':objs[0][0],'json_sha256':sha(objs[0][1]),'object':json.loads(objs[0][1])}
need(metas['work/resolution.log']['object']==metas['work/locked-metadata.log']['object'],'unlocked/locked metadata differs')
metadata=metas['work/locked-metadata.log']['object']
need(metadata['target_directory']==report['target'] and metadata['workspace_root']==report['runner'],'metadata paths')
probe_manifest=tomllib.loads(contents['work/probe/Cargo.toml'].decode())
need(probe_manifest['package']['name']=='hepta-original-observer-probe' and probe_manifest['bin']==[{'name':'hepta-objective-history-probe','path':'src/main.rs'}],'manifest actual bin')
need(probe_manifest['dependencies']['codex-hepta-supervisor']['default-features'] is False and 'io-util' in probe_manifest['dependencies']['tokio']['features'],'probe feature graph')
remote_root='/home/runner/work/_temp/hepta-history-native-39115155092-1'
for name,val in probe_manifest['dependencies'].items():
 if isinstance(val,dict) and 'path' in val:
  need(val['path'].startswith(remote_root+'/hepta-source/codex-rs/'),'manifest source path '+name)
need(metadata['resolve'] is not None,'resolved metadata absent')
root_id=metadata['resolve']['root']; root_pkg=next(p for p in metadata['packages'] if p['id']==root_id)
need(root_pkg['name']==probe_manifest['package']['name'] and root_pkg['manifest_path']==report['runner']+'/Cargo.toml','metadata root source')
targets=[t for t in root_pkg['targets'] if t['name']=='hepta-objective-history-probe']
need(len(targets)==1 and targets[0]['src_path']==report['runner']+'/src/main.rs' and targets[0]['kind']==['bin'],'metadata target')
all_ids={(p['name'],p['version'],p.get('source')) for p in metadata['packages']}
lock_packages=tomllib.loads(contents['work/probe/Cargo.lock'].decode())['package']
need(all_ids=={(p['name'],p['version'],p.get('source')) for p in lock_packages},'metadata/lock packages')
for p in metadata['packages']:
 if p['name'].startswith('codex-') and p['source'] is None:
  need(p['manifest_path'].startswith(remote_root+'/hepta-source/codex-rs/'),'resolved original package outside fixed source')
need([v['label'] for v in report['steps']]==['resolution','locked-metadata','build'] and report.get('prebuilt_probe_requires_caller_build_binding') is not True,'prebuilt probe')
need(builds['status']=='passed' and builds['desktop_commit']==DESKTOP and len(builds['steps'])==2 and all(s['exit_code']==0 for s in builds['steps']),'native build receipt')
expected_builds=[
 ['rustup','run','1.95.0','cargo','build','--locked','--profile','dev-small','--no-default-features','-p','codex-hepta-agentd','--bin','codex-hepta-agentd','-j1'],
 ['rustup','run','1.88.0','cargo','build','--locked','--manifest-path','services/hepta-os/Cargo.toml','--features','objective-history','--bins','-j1']]
need([v['command'] for v in builds['steps']]==expected_builds,'native build commands')
need(builds['steps'][0]['cwd']==remote_root+'/hepta-source/codex-rs' and builds['steps'][0]['target']==remote_root+'/hepta-target'
     and builds['steps'][1]['target']==remote_root+'/desktop-target','native build paths')
expected_bins={'probe':remote_root+'/hepta-target/dev-small/hepta-objective-history-probe','agentd':remote_root+'/hepta-target/dev-small/codex-hepta-agentd',
'observer':remote_root+'/desktop-target/debug/hepta-observe','submitter':remote_root+'/desktop-target/debug/hepta-submit','history':remote_root+'/desktop-target/debug/hepta-history'}
need(set(report['binaries'])==set(expected_bins) and all(report['binaries'][n]['path']==p for n,p in expected_bins.items()),'five binary paths')
need(report['runtime_command'][:5]==[expected_bins[n] for n in ['probe','agentd','observer','submitter','history']] and report['runtime_command'][5].startswith('/tmp/hh-'),'runtime explicit binary paths')
log_ends={}
for n,profile in [('logs/original-agentd-build.log','dev-small'),('logs/desktop-clis-build.log','dev'),('work/build.log','dev-small')]:
 lines=contents[n].decode().splitlines();need('Finished '+chr(96)+profile+chr(96)+' profile' in lines[-1] and not any(l.startswith('error:') for l in lines),'actual build log finish '+n);log_ends[n]=lines[-1]
native_log=contents['logs/native-setup.log'].decode()
need('rustc 1.95.0 (59807616e 2026-04-14)' in native_log and 'rustc 1.88.0 (6b00bc388 2025-06-23)' in native_log and native_log.count('host: aarch64-unknown-linux-gnu')>=2,'native compiler host')
need(alloc['expected_desktop_commit']==DESKTOP and alloc['runner_arch']=='ARM64' and alloc['machine']=='aarch64' and alloc['run_attempt']=='1','allocation')
for label,c,t in [('desktop',DESKTOP,DTREE),('hepta',OWNER,OTREE)]:
 state=after['checkouts'][label]
 need(state['identity']=={'exit_code':0,'stdout':c+'\n'+t+'\n','stderr':''} and state['status']=={'exit_code':0,'stdout':'','stderr':''},'final checkout '+label)
need(set(after['steps'])=={'checkout','contract','owner_source','toolchains','builds','runtime'}
     and all(v['outcome']==v['conclusion']=='success' for v in after['steps'].values()),'final local step receipt')
meta_path=B/'r9-evidence/ci/arm-history-recovery-github-metadata-20261019.json'
jobs_path=B/'r9-evidence/ci/arm-history-recovery-jobs-20261019.json'
api_meta=json.loads(meta_path.read_text());api_jobs=json.loads(jobs_path.read_text())
obs={o['key']:o for o in api_meta['observations']}
run=obs['history_run']['data'];artifacts=obs['history_artifacts']['data']['artifacts']
jobobs=next(o for o in api_jobs['observations'] if o['key']=='desktop_history_jobs')
job=next(j for j in jobobs['response_json']['jobs'] if j['id']==117655596136)
need(run['id']==39115155092 and run['run_attempt']==1 and run['head_sha']==DESKTOP and run['status']=='completed' and run['conclusion']=='success','official run')
need(job['head_sha']==DESKTOP and job['run_id']==run['id'] and job['run_attempt']==1 and job['status']=='completed' and job['conclusion']=='success','official job')
need(len(job['steps'])==14 and all(v['status']=='completed' and v['conclusion']=='success' for v in job['steps']),'14 steps success')
evidence_artifact=next(a for a in artifacts if a['id']==12134664375)
need(evidence_artifact['size_in_bytes']==len(raw) and evidence_artifact['digest']=='sha256:'+ZIP_SHA and evidence_artifact['workflow_run']['head_sha']==DESKTOP and evidence_artifact['workflow_run']['id']==run['id'] and evidence_artifact['expired'] is False,'official artifact')
runtime_step=next(s for s in job['steps'] if 'source-bound probe and execute' in s['name'])
need(runtime_step['started_at']=='2026-10-18T11:23:24Z' and runtime_step['completed_at']=='2026-10-18T11:28:16Z','runtime step times')
need(sha(P.read_bytes())==ZIP_SHA,'zip changed while auditing')
out={'schema_version':1,'review_part':'zip_source_locks_builds_api','started_at_utc':started,'completed_at_utc':now(),
'zip':{'path':str(P),'bytes':len(raw),'sha256':ZIP_SHA,'entry_count':99,'total_uncompressed_bytes':sum(i.file_size for i in infos),'central_directory_offset':z.start_dir,
       'crc_all_passed':True,'safe_relative_unique_regular_member_names':True,'encrypted_members':False,'multidisk':False,'appended_bytes':0,'overlapping_member_ranges':False,
       'allowlisted_logs_identity_locks_public_fixture_sources_only':True,'manifest':manifest},
'source_binding':{'desktop_commit':DESKTOP,'desktop_tree':DTREE,'consumer_tree':before['consumer_tree'],'owner':expected_upstream,'contract_sha256':CONTRACT_SHA,
                 'contract_fields_valid':True,'base_is_ancestor':True,'desktop_before_after_raw_git_sha256':desktop_map,
                 'owner_contract_raw_git_sha256':owner_map,'compiled_source_binding':binding,'archived_probe_sources':archived_sources,
                 'copied_original_session_modules_note':'Inherited preparation copies match pinned desktop blobs; their presence does not prove session probe execution.'},
'locks':{'original_sha256':sha(contents['locks/hepta-Cargo.lock']),'desktop_sha256':sha(contents['locks/desktop-Cargo.lock']),'probe_sha256':sha(contents['work/probe/Cargo.lock']),
         'fixed_python_verify_runner_lock':verified_lock,'metadata_resolution_equals_locked':True,'metadata_package_count':len(all_ids),
         'metadata_json_sha256':metas['work/locked-metadata.log']['json_sha256'],'shared_identity_and_metadata_provenance_verified':True,
         'manifest_bin':'hepta-objective-history-probe','manifest_package':'hepta-original-observer-probe','prebuilt_probe_used':False},
'builds':builds,'build_log_finishes':log_ends,'allocation':alloc,'reported_binary_identities':report['binaries'],
'elf_byte_review_scope':'This review cross-binds reported identities and exact build/runtime paths. Root independently streams the separate ELF ZIP and compares actual AArch64 bytes; no ELF execution here.',
'final_checkouts':after,
'official_api':{'metadata_input':file_rec(meta_path),'jobs_input':file_rec(jobs_path),'run_observed_at_utc':obs['history_run']['observed_at_utc'],'job_observed_at_utc':jobobs['observed_at_utc'],
                'run':{k:run[k] for k in ['id','run_attempt','head_sha','status','conclusion','created_at','updated_at','html_url']},
                'job':{k:job[k] for k in ['id','run_id','run_attempt','head_sha','status','conclusion','started_at','completed_at','runner_name','labels','steps']},
                'artifact':evidence_artifact},
'actual_time_bounds':{'native_job_started_at':job['started_at'],'native_job_completed_at':job['completed_at'],'runtime_build_and_execution_step_started_at':runtime_step['started_at'],
'runtime_build_and_execution_step_completed_at':runtime_step['completed_at'],'report_initialized_at':report['recorded_at_utc'],'final_checkout_recorded_at':after['recorded_at_utc'],
'note':'The report timestamp marks initialization before the probe build. The enclosing runtime step includes metadata resolution and a 4m21s probe build, not 4m52s of runtime scenarios.'}}
(OUT/'source.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'passed_source_zip_lock_build_api','entries':len(infos),'desktop_sources':len(desktop_map),'owner_sources':len(owner_map),'probe_inputs':len(fixed_inputs),'shared_lock_identities':verified_lock['shared_package_identities_checked'],'metadata_packages':len(all_ids),'official_steps':len(job['steps']),'report_sha256':sha(contents['work/report.json']),'runtime_sha256':sha(contents['work/runtime.log']),'temporary_section':str(OUT/'source.json')},ensure_ascii=False))
