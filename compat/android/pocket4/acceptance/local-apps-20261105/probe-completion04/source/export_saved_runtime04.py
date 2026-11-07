#!/usr/bin/python3 -I
"""Bounded saved-only Probe04 evidence export; no live process or Android reads."""
from pathlib import Path
import gzip,hashlib,json,os,re,stat,time
ROOT=Path('/home/alex/work/pocket4-probe-completion-20261105-r12-04')
RUNTIME=ROOT/'runtime-private'
OUT=Path('/home/alex/work/pocket4-probe-completion-saved-export-20261105-r12-04')
RESULT_SHA='3e94b99a354719380674a7115d8b202c613beee4e2d90fccc6d443c3d7664327'
START=time.monotonic();TOTAL=0
def need(ok,why):
 if not ok:raise RuntimeError(why)
def sha(b):return hashlib.sha256(b).hexdigest()
def ident(st):return tuple(getattr(st,k) for k in ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_atime_ns','st_mtime_ns','st_ctime_ns'))
def read(p,maximum):
 global TOTAL
 need(time.monotonic()-START<60,'SAVED_READ_DEADLINE')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NOATIME)
 try:
  st=os.fstat(fd);need(stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_nlink==1 and st.st_size<=maximum,'OWNED_REGULAR_SAVED_FILE_REQUIRED')
  data=b''
  while len(data)<st.st_size:
   part=os.read(fd,min(65536,st.st_size-len(data)));need(part,'TRUNCATED_SAVED_FILE');data+=part
  need(ident(st)==ident(os.fstat(fd))==ident(os.stat(p,follow_symlinks=False)),'SAVED_FILE_OR_METADATA_CHANGED')
 finally:os.close(fd)
 TOTAL+=len(data);need(TOTAL<=64*1024*1024,'SAVED_TOTAL_LIMIT')
 return data
def write(p,b):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),0,1000);os.fchmod(f.fileno(),0o640)
def entry(p,data):return {'source_name':p.name,'source_bytes':len(data),'source_sha256':sha(data)}
def execute():
 need(os.geteuid()==0 and not os.path.lexists(OUT),'CREATE_ONLY_EXPORT')
 os.sched_setaffinity(0,{20})
 for p in (ROOT,RUNTIME):
  st=os.lstat(p);need(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and p.resolve(strict=True)==p,'EXACT_OWNED_DIRECTORY')
 raw=read(ROOT/'result.json',65536);need(sha(raw)==RESULT_SHA,'EXACT_COMPLETED_RESULT')
 result=json.loads(raw);rt=result['runtime']
 need(result['state']=='THREE_OWNED_ROUNDS_AMBIGUITY_AND_BOUNDED_LIVE_VERIFIED_CLEAN'
  and rt['thread_joined'] and rt['sample_count']==255 and not rt['errors'] and rt['scan_error_count']==0,'COMPLETED_RUNTIME_SCOPE')
 expected={(str(x['host_pid']),str(x['start_ticks'])) for x in rt['bounded_process_resource_observations']}
 need(len(expected)==3,'THREE_ACTUAL_PROCESS_GENERATIONS')
 summary_raw=read(RUNTIME/'summary.json',16384);need(json.loads(summary_raw)==rt,'SAVED_RUNTIME_SUMMARY_MISMATCH')
 out={'schema':'probe04-saved-runtime-and-control-evidence/v1','result_sha256':RESULT_SHA,
  'runtime_summary':entry(RUNTIME/'summary.json',summary_raw),'sample_index':[],'runtime_selections':{},
  'selection_rule':'First and last stable full mapping row in each actual process generation; duplicate sources coalesced.',
  'control_evidence':[],'diagnostic_evidence':[],'new_Android_commands':0,'new_UI_inputs':0,'new_live_process_reads':0,'original_files_modified':False}
 samples=sorted(p for p in RUNTIME.iterdir() if re.fullmatch(r'sample-[0-9]{3}\.json',p.name))
 need([p.name for p in samples]==['sample-%03d.json'%i for i in range(255)],'EXACT_CONTIGUOUS_SAMPLE_SET')
 chosen={};stable={}
 for p in samples:
  data=read(p,4*1024*1024);sample=json.loads(data);compact=[]
  for row in sample['rows']:
   need(row['package']==row['process_name']=='local.pocket4.fixture' and row['android_uid']==10115,'EXACT_PROBE_SCOPE')
   key=(str(row['host_identity']['pid']),str(row['host_identity']['start']));need(key in expected,'UNEXPECTED_PROCESS_GENERATION')
   compact.append({'pid':key[0],'start':key[1],**{k:row[k] for k in ('phase','utc','fd_count','fd_enum_races','owned_fixture_fd_numbers','status','full_mapping_snapshot','stable_process_identity')},'maps_before_after_equal':row.get('maps_before_after_equal')})
   if not(row.get('full_mapping_snapshot') and row.get('stable_process_identity') and row.get('maps_before_after_equal')):continue
   stable[key]=stable.get(key,0)+1
   selected={**entry(p,data),'row':{k:v for k,v in row.items() if k not in ('maps_rows','stat_raw')},
    'all_executable_mappings':[m for m in row['maps_rows'] if 'x' in m['permissions']]}
   if key not in chosen:chosen[key]=[selected,selected]
   else:chosen[key][1]=selected
  out['sample_index'].append({**entry(p,data),'phase':sample['phase'],'elapsed_seconds':sample['elapsed_seconds'],'errors':sample['errors'],'rows':compact})
 need(set(chosen)==expected,'STABLE_CAPTURE_FOR_EVERY_GENERATION_REQUIRED')
 for key,pair in sorted(chosen.items()):
  for which,value in zip(('first','last'),pair):
   if which=='last' and value['source_name']==pair[0]['source_name']:continue
   out['runtime_selections'][':'.join(key)+':'+which]=value
 out['stable_full_counts_by_generation']={':'.join(k):v for k,v in stable.items()}
 need(3<=len(out['runtime_selections'])<=6,'BOUNDED_SELECTIONS')
 control=re.compile(r'[0-9]{3}-(?:effect-p[0-9]{2}[-a-z0-9]*|reply-p01-ambiguity|probe-launch-(?:receipt|readback)-[123]|probe-normal-close-(?:intent|readback)-(?:1008|1009|1010))\.json')
 diagnostic=re.compile(r'[0-9]{3}-probe-(?:diagnostic-baseline|diagnostic-[0-9]+|close-exit-(?:1008|1009|1010)-[0-9]+)\.json')
 top=list(ROOT.iterdir());need(len(top)<=1024,'OWNED_JOURNAL_ENTRY_LIMIT')
 for p in sorted(top):
  if control.fullmatch(p.name):
   data=read(p,262144);out['control_evidence'].append({**entry(p,data),'original_json':json.loads(data)})
  elif diagnostic.fullmatch(p.name):
   data=read(p,4*1024*1024);d=json.loads(data);need(set(d['packages'])=={'local.pocket4.fixture'},'EXACT_DIAGNOSTIC_PACKAGE')
   timed=[];unknown=0
   for line in d['events'].splitlines():
    m=re.match(r'^\s*(\d+\.\d+)\s+',line)
    if m:timed.append((float(m[1]),line))
    elif line.strip() and not line.startswith('--------- beginning of '):unknown+=1
   selected=[line for _,line in timed if re.search(r'\bam_(?:crash|anr)\s*:',line) and re.search(r'(?<![A-Za-z0-9_.:])local\.pocket4\.fixture(?![A-Za-z0-9_.:])',line)]
   out['diagnostic_evidence'].append({**entry(p,data),'guest_seconds':d['guest_seconds'],'packages':d['packages'],
    'events_projection':{'raw_utf8_sha256':sha(d['events'].encode()),'timestamped_line_count':len(timed),'unknown_line_count':unknown,
     'oldest_timestamp':min((t for t,_ in timed),default=None),'newest_timestamp':max((t for t,_ in timed),default=None),'exact_package_crash_anr_lines':selected,
     'other_packages_event_lines_returned':False}})
 need(20<=len(out['control_evidence'])<=32 and 20<=len(out['diagnostic_evidence'])<=72,'EXPECTED_BOUNDED_JOURNAL_SELECTION_COUNTS')
 need(sha(read(ROOT/'result.json',65536))==RESULT_SHA and read(RUNTIME/'summary.json',16384)==summary_raw,'ORIGINAL_RECEIPTS_CHANGED')
 encoded=(json.dumps(out,sort_keys=True,indent=2)+'\n').encode();need(len(encoded)<=8*1024*1024,'EXPORT_SIZE_LIMIT')
 packed=gzip.compress(encoded,compresslevel=9,mtime=0)
 os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
 write(OUT/'saved-export.json.gz',packed)
 receipt={'state':'COMPLETED_SAVED_PROBE04_EXPORT','result_sha256':RESULT_SHA,'json_bytes':len(encoded),'json_sha256':sha(encoded),
  'gzip_bytes':len(packed),'gzip_sha256':sha(packed),'gzip_path':str(OUT/'saved-export.json.gz'),'saved_samples_read':len(samples),
  'runtime_selections':list(out['runtime_selections']),'control_records':len(out['control_evidence']),'diagnostic_records':len(out['diagnostic_evidence']),
  'total_saved_bytes_read':TOTAL,'new_Android_commands':0,'new_UI_inputs':0,'new_live_process_reads':0,'other_packages_event_lines_returned':False}
 write(OUT/'receipt.json',(json.dumps(receipt,sort_keys=True,indent=2)+'\n').encode());print(json.dumps(receipt))
if __name__=='__main__':execute()
