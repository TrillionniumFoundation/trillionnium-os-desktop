#!/usr/bin/python3 -I
"""Read only completed Contacts fixture journals; no Android or live process calls."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,stat,time
UI=Path('/home/alex/work/pocket4-contacts-search-flow-20261105-r12-01')
RUNTIME=Path('/home/alex/work/pocket4-contacts-runtime-evidence-20261105-r12-02')
OUT=Path('/home/alex/work/pocket4-contacts-saved-readback-20261105-r12-01')
UI_SHA='0184620e924ae7dddb564b5e1e4399f90fc2fcc66e68bdbab173c33d98f26df4'
RT_SHA='612e91ac38c9d07d1d27a16ada46c5b1215c7901ca56ee65900833605653405a'
START=time.monotonic();TOTAL=0
def need(ok,why):
 if not ok:raise RuntimeError(why)
def sha(b):return hashlib.sha256(b).hexdigest()
def ident(st):return tuple(getattr(st,k) for k in ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_atime_ns','st_mtime_ns','st_ctime_ns'))
def read(p,maximum):
 global TOTAL
 need(time.monotonic()-START<45,'SAVED_READ_DEADLINE')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NOATIME)
 try:
  st=os.fstat(fd);need(stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_nlink==1 and st.st_size<=maximum,'OWNED_SAVED_REGULAR_FILE_REQUIRED')
  data=b''
  while len(data)<st.st_size:
   part=os.read(fd,min(65536,st.st_size-len(data)));need(part,'TRUNCATED_SAVED_FILE');data+=part
  need(ident(st)==ident(os.fstat(fd))==ident(os.stat(p,follow_symlinks=False)),'SAVED_FILE_OR_METADATA_CHANGED')
 finally:os.close(fd)
 TOTAL+=len(data);need(TOTAL<=128*1024*1024,'SAVED_READ_TOTAL_LIMIT')
 return data
def write(p,b):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),0,1000);os.fchmod(f.fileno(),0o640)
def execute():
 need(os.geteuid()==0 and not os.path.lexists(OUT),'CREATE_ONLY_EXPORT')
 for p in (UI,RUNTIME,RUNTIME/'samples'):
  st=os.lstat(p);need(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and p.resolve(strict=True)==p,'EXACT_OWNED_DIRECTORY')
 uiraw=read(UI/'result.json',32768);rtraw=read(RUNTIME/'result.json',16384)
 need(sha(uiraw)==UI_SHA and sha(rtraw)==RT_SHA,'ACTUAL_TERMINAL_RECEIPT_PINS')
 ui=json.loads(uiraw);rt=json.loads(rtraw)
 need(ui['state']=='FAILED' and ui['cleanup_verified'] and ui['native_launched_tasks']==ui['normally_closed_tasks']==[980,981]
  and ui['pending_input'] is ui['pending_close'] is ui['pending_database_effect'] is None and ui['owned_task_remaining'] is None
  and ui['deleted_final_proof']['database_returned_to_empty'] and ui['deleted_final_proof']['owned_tombstone_count']==0
  and not any(ui.get(k) for k in ('final_error','outer_error','fixture_cleanup_error')),'COMPLETED_CLEAN_UI_SCOPE')
 need(rt['state']=='BOUNDED_CONTACTS_RUNTIME_OBSERVATIONS_CAPTURED_REVIEW_REQUIRED' and rt['sampler']['thread_joined']
  and rt['separate_UI_flow_result']['sha256']==UI_SHA and rt['sampler']['sample_count']==104,'COMPLETED_RUNTIME_SCOPE')
 out={'schema':'contacts-saved-observations-export/v1','UI_result_sha256':UI_SHA,'runtime_result_sha256':RT_SHA,
  'ui_records':{},'frames':{},'runtime_selections':{},'sample_index':[],
  'new_android_commands':0,'new_ui_inputs':0,'new_current_process_reads':0,'original_files_modified':False}
 files=sorted(UI.glob('*.json'));need(len(files)<=250,'UI_FILE_COUNT')
 for p in files:
  need(re.fullmatch(r'(?:\d{3}-[a-z0-9-]+|owned-contact-claim|result)\.json',p.name),'OWNED_UI_FILENAME')
  data=read(p,2*1024*1024);out['ui_records'][p.name]={'bytes':len(data),'sha256':sha(data),'value':json.loads(data)}
 frames=sorted(p for p in UI.glob('*.png') if 'open-search' in p.name);need(len(frames)<=2,'SEARCH_FRAME_COUNT')
 for p in frames:
  data=read(p,4*1024*1024);need(data.startswith(b'\x89PNG\r\n\x1a\n'),'SAVED_PNG')
  out['frames'][p.name]={'bytes':len(data),'sha256':sha(data),'base64':base64.b64encode(data).decode()}
 samples=sorted(p for p in (RUNTIME/'samples').iterdir() if re.fullmatch(r'sample-\d{3}\.json',p.name))
 need(len(samples)==104,'EXACT_SAVED_SAMPLE_COUNT')
 for p in samples:
  data=read(p,8*1024*1024);sample=json.loads(data)
  out['sample_index'].append({'name':p.name,'bytes':len(data),'sha256':sha(data),'phase':sample['phase'],'errors':sample['errors']})
  rows=[r for r in sample['rows'] if r.get('full_mapping_snapshot') and r.get('stable_process_identity') and r.get('maps_before_after_equal')]
  for row in rows:
   need(row['package']=='com.android.contacts' and row['android_uid']==10055 and row['process_name']=='com.android.contacts','EXACT_CONTACTS_RUNTIME_ROW')
   key=sample['phase']+':'+str(row['host_identity']['pid'])+':'+str(row['host_identity']['start'])
   if key in out['runtime_selections']:continue
   need(len(out['runtime_selections'])<8,'BOUNDED_RUNTIME_SELECTIONS')
   out['runtime_selections'][key]={'source_name':p.name,'source_bytes':len(data),'source_sha256':sha(data),
    'row':{k:v for k,v in row.items() if k not in ('maps_rows','stat_raw')},
    'named_executable_mappings':[m for m in row['maps_rows'] if 'x' in m['permissions'] and not m['path'].startswith('/')]}
 need(sha(read(UI/'result.json',32768))==UI_SHA and sha(read(RUNTIME/'result.json',16384))==RT_SHA,'TERMINAL_RECEIPTS_CHANGED')
 encoded=(json.dumps(out,sort_keys=True,indent=2)+'\n').encode();packed=gzip.compress(encoded,compresslevel=9,mtime=0)
 os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
 write(OUT/'saved-export.json.gz',packed)
 receipt={'state':'COMPLETED_SAVED_EXPORT','UI_result_sha256':UI_SHA,'runtime_result_sha256':RT_SHA,
  'json_bytes':len(encoded),'json_sha256':sha(encoded),'gzip_bytes':len(packed),'gzip_sha256':sha(packed),
  'gzip_path':str(OUT/'saved-export.json.gz'),'ui_records':len(out['ui_records']),'frames':list(out['frames']),
  'runtime_selections':list(out['runtime_selections']),'saved_samples_read':len(samples),'total_saved_bytes_read':TOTAL,
  'new_android_commands':0,'new_ui_inputs':0,'new_current_process_reads':0}
 write(OUT/'receipt.json',(json.dumps(receipt,sort_keys=True,indent=2)+'\n').encode());print(json.dumps(receipt))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args()
 if args.execute:execute()
 else:print('INERT: completed owned Contacts journals only; no live Android calls')
