#!/usr/bin/env python3
"""Independent review of actual saved Probe04 mappings, resources and diagnostics."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import hashlib,json,re,os
P=Path(__file__).resolve().parent
EXPORT_SHA='c061b63f1fe43d115dfc3ab5ef7c085c1a7f5d54dee9460caf2e24c2f0420e0d'
RESULT_SHA='3e94b99a354719380674a7115d8b202c613beee4e2d90fccc6d443c3d7664327'
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p,h):
 b=p.read_bytes();assert sha(b)==h,p.name;return json.loads(b)
def put(name,v):
 b=(json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
 with (P/name).open('xb') as f:f.write(b)
 print(json.dumps({'path':name,'bytes':len(b),'sha256':sha(b)}));return sha(b)
def timestamp(x):return datetime.fromisoformat(x).timestamp()
data=read(P/'saved-runtime-export04.json',EXPORT_SHA);result=read(P/'result04-original.json',RESULT_SHA)
assert data['result_sha256']==RESULT_SHA and all(data[k]==0 for k in ('new_Android_commands','new_UI_inputs','new_live_process_reads'))
index=data['sample_index'];assert len(index)==255 and [e['source_name'] for e in index]==['sample-%03d.json'%i for i in range(255)]
assert all(not s['errors'] for s in index)
indexed={e['source_name']:e for e in index};inventory={};snapshots=[];generations={};unresolved=[]
assert len(data['runtime_selections'])==6
for name,entry in sorted(data['runtime_selections'].items()):
 row=entry['row'];host=row['host_identity'];pid,start,which=name.split(':')
 assert [pid,start]==[str(host['pid']),str(host['start'])] and which in ('first','last')
 assert row['package']==row['process_name']=='local.pocket4.fixture' and row['android_uid']==10115
 assert host['uid']==['10115']*4 and host['exe']=='/system/bin/app_process64' and host['nspid'][0]==pid and len(host['nspid'])==2
 assert host['ns']['pid']=='pid:[4026533288]' and host['ns']['net']=='net:[4026533041]'
 assert host['cgroup']=='0::/system.slice/droidloomd.service/apps/uid_10115/pid_'+host['nspid'][1]+'\n'
 assert row['full_mapping_snapshot'] and row['stable_process_identity'] and row['maps_before_after_equal']
 saved=indexed[entry['source_name']];assert (saved['source_bytes'],saved['source_sha256'])==(entry['source_bytes'],entry['source_sha256'])
 assert len([r for r in saved['rows'] if (r['pid'],r['start'],r['utc'])==(pid,start,row['utc'])])==1
 objs=row['mapped_code_objects'];assert len({o['path'] for o in objs})==len(objs)
 elf={o['path']:o for o in objs if o.get('elf')};assert len(elf)==381
 for path,o in elf.items():
  assert (o['machine'],o['bits'],o['byte_order'],o['architecture'])==(62,64,'little','x86_64')
  assert re.fullmatch('[0-9a-f]{64}',o['sha256']) and o['identity']['st_size']>0
  item={'path':path,'bytes':o['identity']['st_size'],'sha256':o['sha256'],'machine':o['machine'],'bits':o['bits'],'architecture':o['architecture']}
  assert path not in inventory or inventory[path]==item
  inventory[path]=item
 nonelf=[o for o in objs if not o.get('elf')]
 assert len(nonelf)==1 and nonelf[0]['path']=='/vendor/overlay/DroidloomFrameworkDisplayOverlay.apk' and nonelf[0]['content_read']=='first_64_code_bytes_only'
 assert row['executable']['sha256']=='456322c6cc424d228d153623717e8a6b1ac7d0b3aa48f0f1948380412f54ac73'
 assert row['executable']['architecture']=='x86_64' and row['executable']['machine']==62
 unresolved_paths={o['path'] for o in row['unresolved_executable_objects']}
 assert unresolved_paths=={'/dev/__properties__/u:object_r:qemu_sf_lcd_density_prop:s0','/data/resource-cache/vendor@overlay@DroidloomFrameworkDisplayOverlay.apk@idmap'}
 unresolved_maps=[m for m in row['engine_mappings'] if m['path'] in unresolved_paths]
 assert {m['path'] for m in unresolved_maps}==unresolved_paths and all(m['permissions']=='r--s' for m in unresolved_maps)
 unresolved.extend(unresolved_maps)
 named=[m for m in entry['all_executable_mappings'] if not m['path'].startswith('/')]
 assert {m['path'] for m in named}=={'[anon_shmem:dalvik-zygote-jit-code-cache]','[anon_shmem:dalvik-jit-code-cache]','[vdso]','[vsyscall]'}
 filesystem=[m for m in entry['all_executable_mappings'] if m['path'].startswith('/')]
 for m in filesystem:
  assert m['path'] in elf and 'x' in m['permissions']
  o=elf[m['path']]['identity'];assert m['inode']==o['st_ino'] and (m['device_major'],m['device_minor'])==(os.major(o['st_dev']),os.minor(o['st_dev']))
 assert not row['non_filesystem_mapping_contents_read'] and row['actual_engine_exclusion_automatically_qualified'] is False
 key=pid+':'+start;generations.setdefault(key,{})[which]=set(elf)
 snapshots.append({'generation':key,'guest_pid':host['nspid'][1],'which':which,'source_name':entry['source_name'],'source_sha256':entry['source_sha256'],'utc':row['utc'],'phase':row['phase'],'whole_hashed_x86_64_ELF_objects':381,'filesystem_executable_mapping_count':len(filesystem),'unresolved_nonexecutable_name_candidates':2,'named_JIT_and_kernel_mapping_count':len(named),'stable_process_and_maps':True})
assert len(generations)==3 and len(inventory)==381 and all(set(pair)=={'first','last'} and pair['first']==pair['last'] for pair in generations.values())
assert len({frozenset(pair['last']) for pair in generations.values()})==1
assert inventory['/apex/com.android.art/lib64/libart.so']['sha256']=='3b53de051a3004be76078506f7a6924e50b467fd4b3277b867afc13328d082d0'
assert inventory['/apex/com.android.runtime/bin/linker64']['sha256']=='b49ddfc69f7ad2558fef7145524c353391d42bce8004ff5f09e022066c9a1173'
budget=result['reviewed_resource_budget'];rounds=[]
for i in (1,2,3):
 rows=[r for s in index if s['phase']=='probe-round-%d'%i for r in s['rows']]
 assert len(rows)>=budget['minimum_samples_each_round'] and all(r['stable_process_identity'] for r in rows)
 assert len({(r['pid'],r['start']) for r in rows})==1
 times=[timestamp(r['utc']) for r in rows];span=times[-1]-times[0];gaps=[b-a for a,b in zip(times,times[1:])]
 assert span>=budget['minimum_sample_span_seconds'] and all(0<=g<=budget['maximum_adjacent_sample_gap_seconds'] for g in gaps)
 rss=[int(r['status']['VmRSS'].split()[0]) for r in rows];fds=[r['fd_count'] for r in rows];threads=[int(r['status']['Threads']) for r in rows]
 assert max(rss)<=budget['maximum_rss_kib'] and max(fds)<=budget['maximum_fds'] and max(threads)<=budget['maximum_threads']
 late=[j for j,t in enumerate(times) if t-times[0]>=10];assert len(late)>=5
 growth={'rss_kib':rss[-1]-rss[late[0]],'fds':fds[-1]-fds[late[0]],'threads':threads[-1]-threads[late[0]]}
 assert growth['rss_kib']<=budget['maximum_late_rss_growth_kib'] and growth['fds']<=budget['maximum_late_fd_growth'] and growth['threads']<=budget['maximum_late_thread_growth']
 stable=sum(bool(r['full_mapping_snapshot'] and r['maps_before_after_equal']) for r in rows);assert stable>=1
 rounds.append({'round':i,'samples':len(rows),'span_seconds':span,'maximum_sample_gap_seconds':max(gaps),'process_generation_count':1,'maximum_rss_kib':max(rss),'maximum_fds':max(fds),'maximum_threads':max(threads),'late_growth':growth,'stable_full_mapping_samples':stable})
assert rounds==result['runtime_resource_review']['rounds']
controls=data['control_evidence'];assert len(controls)==23
positive=[e for e in controls if re.search(r'-effect-p(?:0[2-9]|10)-',e['source_name'])];assert len(positive)==9
for e in positive:
 v=e['original_json'];assert v['action_replayed'] is False and v['intent']['native_acknowledged'] is True and v['intent']['automatic_retry'] is False
 assert [v['actual_state'][k] for k in ('editor','other_editor','result')]==v['intent']['expected']
 ambiguity=next(e['original_json'] for e in controls if '-effect-p01-ambiguity' in e['source_name'])
 assert ambiguity==result['ambiguity_rejection'] and ambiguity['successful_input_credit']==0
for task in (1008,1009,1010):
 readback=next(e['original_json'] for e in controls if '-probe-normal-close-readback-'+str(task) in e['source_name']);assert readback['task_ids']==[851]
def exit_rows(text):
 assert text.startswith('ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)')
 out={}
 for block in re.split(r'(?=^\s*ApplicationExitInfo #\d+:)',text,flags=re.M)[1:]:
  def one(pattern):
   values=re.findall(pattern,block);assert len(values)==1;return values[0].strip()
  key=(one(r'\btimestamp=([^\n]+)'),one(r'\bpid=(\d+)'),one(r'\brealUid=(\d+)'),one(r'\breason=(\d+)\s*\('),one(r'\bprocess=([^\s]+)'))
  assert key[2]=='10115' and key[4]=='local.pocket4.fixture' and key not in out
  out[key]={'subreason':one(r'\bsubreason=(\d+)\s*\('),'status':one(r'\bstatus=(-?\d+)'),'description':one(r'\bdescription=([^\n]+)')}
 return out
def timed(text):
 rows=[]
 for line in text.splitlines():
  match=re.match(r'^\s*(\d+\.\d+)\s+',line)
  if match:rows.append((float(match[1]),line))
  else:assert not line.strip() or line.startswith('--------- beginning of ')
 return rows
diags=data['diagnostic_evidence'];segments=result['diagnostic_segments_completed'];assert len(diags)==21 and len(segments)==20
previous=diags[0];old=exit_rows(previous['packages']['local.pocket4.fixture']['exits']);normal_exits=[];reviewed=[]
for n,after in enumerate(diags[1:]):
 segment=segments[n];assert (previous['guest_seconds'],after['guest_seconds'])==(segment['from_guest_seconds'],segment['to_guest_seconds'])
 p=after['events_projection'];assert p['unknown_line_count']==0 and (p['timestamped_line_count']<2048 or p['oldest_timestamp']<=previous['guest_seconds'])
 assert not timed('\n'.join(p['exact_package_crash_anr_lines']))
 current=after['packages']['local.pocket4.fixture'];crash=timed(current['crash']);assert (len(crash)<512 or min(t for t,_ in crash)<=previous['guest_seconds']) and not [line for t,line in crash if t>=previous['guest_seconds']]
 new=exit_rows(current['exits']);assert set(old)<=set(new);added=set(new)-set(old)
 assert sorted([list(k) for k in added])==segment['new_exit_tuples']
 if added:
  expected=segment['expected_normal_close'];assert expected and expected['normal_remove_completed'] and len(added)==1
  for key in added:
   detail=new[key];assert key[1]==str(expected['guest_pid']) and key[3]=='10' and detail['subreason']=='22' and detail['status']=='0' and 'remove task' in detail['description'].lower()
   normal_exits.append({'task':expected['task'],'exit_tuple':list(key),'detail':detail})
 reviewed.append({'source_name':after['source_name'],'source_sha256':after['source_sha256'],'from':previous['guest_seconds'],'through':after['guest_seconds'],'new_exits':len(added),'fresh_crash_ANR_events':0,'retained_buffer_coverage':True})
 previous=after;old=new
assert [e['task'] for e in normal_exits]==[1008,1009,1010]
assert result['runtime']['stable_complete_mapping_samples']==0
inv_hash=put('INDEPENDENT_ELF_INVENTORY04.json',{'schema':'probe04-actual-mapped-ELF-inventory/v1','saved_export_sha256':EXPORT_SHA,'objects':[inventory[k] for k in sorted(inventory)],'whole_hashed_ELF_objects':381,'all_observed_ELF_headers_x86_64':True,'same_six_snapshots':True,'process_memory_or_JIT_contents_read':False})
put('ROOT_RUNTIME_DIAGNOSTICS_REVIEW04.json',{'schema':'probe04-root-actual-runtime-and-diagnostics-review/v1','original_result_sha256':RESULT_SHA,'saved_export_sha256':EXPORT_SHA,'inventory_sha256':inv_hash,'all_checks_passed':True,'observed_process_engine':'Exact three local.pocket4.fixture UID10115 process generations run x86_64 app_process64 with mapped Android ART/libart.so and linker64; all381 observed filesystem ELF objects are fully hashed and x86_64.','snapshots':snapshots,'sample_count':255,'stable_full_counts_by_generation':data['stable_full_counts_by_generation'],'resources':{'frozen_budget':budget,'independent_rounds':rounds,'budget_passed':True,'measured_live_seconds':result['live_observation_seconds']},'positive_controls_independently_matched':9,'negative_ambiguity_outcome_independently_matched':True,'normal_task_exits':normal_exits,'diagnostic_intervals':reviewed,'unexplained_process_replacement_or_exit':False,'original_automatic_complete_mapping_counter':0,'original_automatic_engine_qualification':False,'whole_App_qualification_requires_separate_complete_feature_and_release_review':True,'new_device_or_UI_operations':0,'limits':['Runtime identity describes the actual sampled UID process generations, not an Asterinas or system-wide engine qualification.','The two unresolved name candidates are actual read-only non-executable property/idmap mappings; no property/idmap contents were read.','One overlay APK had only a non-ELF header classification in this collector, not a whole-file integrity claim.','Dalvik JIT and kernel vdso/vsyscall mappings were identified by saved names, permissions and boundaries; no process-memory contents were read.','Nativebridge support libraries are present. Their names alone do not prove that a translator was active or that all emulation is absent.','Stability credit is limited to the predeclared three-round bounded QA-fixture budget; no long-duration leak or stress claim.','Crash/ANR review covers consecutive retained-buffer intervals. Original external-log-clear and older-history limitations remain.']})
