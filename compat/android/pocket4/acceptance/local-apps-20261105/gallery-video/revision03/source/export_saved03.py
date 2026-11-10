#!/usr/bin/python3 -I
"""Export only completed Gallery03 owned observations. No Android/session/UI calls."""
from pathlib import Path
import base64,gzip,hashlib,json,os,re,stat,time
ROOT=Path('/home/alex/work/pocket4-gallery-video-flow-20261105-r12-03')
OUT=Path('/home/alex/work/pocket4-gallery-video-readback-20261105-r12-03')
RESULT_SHA='addc903b3b626c962b750571dfafb71fd064584e53cd2105bbeb346f28026a59'
START=time.monotonic()
TOTAL=0
def need(ok,why):
 if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def ident(st):return tuple(getattr(st,k) for k in ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns'))
def read(path,limit):
 global TOTAL
 need(time.monotonic()-START<35,'READ_DEADLINE')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink==1 and before.st_size<=limit,'EXACT_SAVED_FILE_SCOPE')
  raw=b''
  while len(raw)<before.st_size:
   b=os.read(fd,min(65536,before.st_size-len(raw)));need(b,'TRUNCATED');raw+=b
  need(ident(before)==ident(os.fstat(fd))==ident(os.stat(path,follow_symlinks=False)),'SAVED_FILE_CHANGED')
 finally:os.close(fd)
 TOTAL+=len(raw);need(TOTAL<=128*1024*1024,'TOTAL_READ_BOUND')
 return raw
def write(path,raw):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
 with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno());os.fchown(out.fileno(),0,1000);os.fchmod(out.fileno(),0o640)
def main():
 need(os.geteuid()==0 and ROOT.resolve(strict=True)==ROOT and not os.path.lexists(OUT),'EXACT_FRESH_ROOTS')
 raw=read(ROOT/'result.json',65536);need(sha(raw)==RESULT_SHA,'ORIGINAL_RESULT_PIN');old=json.loads(raw)
 need(old['error']=='RuntimeError:SHOW_CONTROLS_FRESH_DECISION_LIMIT' and old['owned_tasks']==old['normal_closed_tasks']==[960]
  and old['pending_effect'] is None and old['close_pending'] is None and old['cleanup']['errors']==[]
  and old['cleanup']['package_absent'] and old['cleanup']['video_deleted'] and old['owned_directory_removed'],'COMPLETED_CLEAN_SCOPE')
 dirs={name:os.lstat(ROOT/name) for name in ('ui','runtime-private')}
 need(all(stat.S_ISDIR(st.st_mode) and st.st_uid==0 for st in dirs.values()),'OWNED_PRIVATE_DIR_SCOPE')
 names=os.listdir(ROOT/'ui');need(len(names)<=300,'UI_JOURNAL_COUNT')
 selected=[n for n in names if re.fullmatch(r'\d{3}-(?:round-0-playing-(?:a|b|advance)|show-controls-[0-2]-(?:intent|explicit-no-effect)|pause-control-observation-[0-2])\.json',n)]
 need(len(selected)==12,'EXACT_UI_RECORD_COUNT')
 result={'schema':'gallery03-saved-observations-export/v1','original_result_sha256':RESULT_SHA,'ui_records':{},'frames':{},'runtime_selections':{},
  'new_android_commands':0,'new_ui_inputs':0,'new_current_process_reads':0,'original_files_modified':False,'whole_app_production_ready':False}
 for name in sorted(selected):
  data=read(ROOT/'ui'/name,262144);result['ui_records'][name]={'bytes':len(data),'sha256':sha(data),'value':json.loads(data)}
 for name in ('round-0-playing-a.png','round-0-playing-b.png'):
  data=read(ROOT/name,4*1024*1024);need(data.startswith(b'\x89PNG\r\n\x1a\n'),'EXACT_PNG');result['frames'][name]={'bytes':len(data),'sha256':sha(data),'base64':base64.b64encode(data).decode()}
 samples=sorted(n for n in os.listdir(ROOT/'runtime-private') if re.fullmatch(r'sample-\d{3}\.json',n))
 need(len(samples)==old['runtime_evidence']['sample_count']==47,'SAMPLER_COUNT_CHANGED')
 for name in samples:
  data=read(ROOT/'runtime-private'/name,8*1024*1024);sample=json.loads(data)
  phase=sample['phase']
  if phase in result['runtime_selections']:continue
  rows=[row for row in sample['rows'] if row.get('full_mapping_snapshot')]
  if not rows:continue
  need(len(rows)==1 and rows[0]['package']=='com.android.gallery3d' and rows[0]['android_uid']==10064,'EXACT_GALLERY_RUNTIME')
  row=rows[0]
  result['runtime_selections'][phase]={'source_name':name,'source_bytes':len(data),'source_sha256':sha(data),
   'row':{k:v for k,v in row.items() if k not in ('maps_rows','stat_raw')},
   'named_executable_mappings':[m for m in row['maps_rows'] if 'x' in m['permissions'] and not m['path'].startswith('/')]}
  if len(result['runtime_selections'])>=3:break
 encoded=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode();compressed=gzip.compress(encoded,compresslevel=9,mtime=0)
 os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
 write(OUT/'saved-export.json.gz',compressed)
 receipt={'state':'COMPLETED_SAVED_EXPORT','source_sha256':sha(Path(__file__).read_bytes()) if Path(__file__).is_file() else None,
  'original_result_sha256':RESULT_SHA,'json_bytes':len(encoded),'json_sha256':sha(encoded),'gzip_bytes':len(compressed),'gzip_sha256':sha(compressed),
  'gzip_path':str(OUT/'saved-export.json.gz'),'ui_record_count':len(selected),'runtime_phases':list(result['runtime_selections']),
  'total_saved_bytes_read':TOTAL,'new_android_commands':0,'new_ui_inputs':0,'new_current_process_reads':0}
 write(OUT/'receipt.json',(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode());print(json.dumps(receipt))
if __name__=='__main__':main()
