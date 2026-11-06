#!/usr/bin/env python3
"""One explicit missing-range continuation after settled s24 DNS failure.

Prior successful ranges are hashed and reused, never downloaded again.
Every missing 2 MiB range is requested at most once. A failed range aborts
unstarted ranges for that package; all bytes and failed receipts are retained.
No Android, Main descriptor, namespace, permissions, or application actions.
"""
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import threading
import time

ROOT=Path('/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-missing-s28')
CHUNK=2*1024*1024
CANDIDATES=[{'package': 'com.zhubajie.client', 'channel_version': '9.5.20', 'url': 'https://s.shouji.qihucdn.com/261009/9b8bc092373e8f09d56861322b8ce1c9/com.zhubajie.client_370.apk?en=curpage%3Dopenbox_wap_detail%26exp%3D1794571897%26from%3Dopenbox_mintf_getAppInfoByIds%26m2%3D%26ts%3D1793967097%26tok%3Db64e944d9e3de8d16861a770d758bee5%26v%3D%26f%3Dz.apk', 'total_bytes': 166873622, 'metadata_md5': None, 'prior_jobs': ['1a1b0c7a0fa-fc05-72dc', '1a1b0e62475-fc05-73cf'], 'prefix_sources': [{'path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-s17/com.zhubajie.client.part', 'bytes': 38387712, 'sha256': '80c613a9897cf2ca5003ec48c2611c3ac25e692bd4db26fdb88a94c1b1465735'}], 'prior_header': {'path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-s17/com.zhubajie.client.headers', 'bytes': 424, 'sha256': '86b28ca76edde2297bdcf6a79dc79d2ccf34fb50617d47a4aa4e3cd76521c9da', 'status': 200}, 'previous_segment_result': {'path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-segments-s24/com.zhubajie.client-result.json', 'bytes': 27693, 'sha256': '7327e768a574d3aa7f0d904c80e2195057c1e75ccb873a47288d0cb949693d59', 'expected_complete_segments': 32, 'explicit_continuation_reason': 'Previous attempt terminal exit1. One failed range had curl6 DNS lookup failure with zero bytes; no HTTP rejection. Parent authorized one single-connection missing-range attempt.'}}]
STAT=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
CURL_FIELDS=('http_code','url_effective','content_type','size_download','time_total','speed_download','num_redirects','num_retries','ssl_verify_result','errormsg','exitcode')

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def require(value,reason):
 if not value:raise RuntimeError(reason)
def identity(fd):
 s=os.fstat(fd);return {k:getattr(s,k) for k in STAT}
def opened(path):
 fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK);before=identity(fd)
 if not(stat.S_ISREG(before['st_mode']) and before['st_nlink']==1 and before['st_uid']==1000):
  os.close(fd);raise RuntimeError('EXACT_OWNED_REGULAR_FILE_REQUIRED')
 return fd,before
def hashes(fd):
 os.lseek(fd,0,os.SEEK_SET);h=hashlib.sha256();m=hashlib.md5();n=0
 for block in iter(lambda:os.read(fd,1048576),b''):h.update(block);m.update(block);n+=len(block)
 os.lseek(fd,0,os.SEEK_SET);return n,h.hexdigest(),m.hexdigest()
def write_json(path,value):
 raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
 with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def verify_path(path,before):
 fd,current=opened(path)
 try:require(current==before,'DECLARED_PATH_REPLACED')
 finally:os.close(fd)

def read_pinned_json(declaration):
 fd,before=opened(declaration['path'])
 try:
  require(hashes(fd)[:2]==(declaration['bytes'],declaration['sha256']),'PRIOR_JSON_IDENTITY_CHANGED')
  raw=os.read(fd,declaration['bytes']+1);require(len(raw)==declaration['bytes'],'PRIOR_JSON_SIZE_CHANGED')
  require(identity(fd)==before,'PRIOR_JSON_CHANGED_DURING_READ');verify_path(declaration['path'],before)
  return json.loads(raw)
 finally:os.close(fd)

def load_verified_cache(c):
 source=c['previous_segment_result'];previous=read_pinned_json(source)
 require(previous['package']==c['package'] and previous['url']==c['url'] and previous['total_bytes']==c['total_bytes'],'EXACT_PREVIOUS_DOWNLOAD_SCOPE_REQUIRED')
 cache={}
 for declared in previous['segment_receipts']:
  if declared['status']!='COMPLETE':continue
  item=read_pinned_json(declared['receipt']);index=declared['index']
  require(item['index']==index and item['status']=='COMPLETE' and item['curl']['http_code']==206 and item['curl']['num_retries']==0 and item['curl']['ssl_verify_result']==0,'PREVIOUS_RANGE_NOT_VERIFIED')
  require(item['curl']['url_effective']==c['url'],'PREVIOUS_RANGE_SOURCE_MISMATCH')
  expected='/home/alex/work/pocket4-launcher-official-candidates-20261106-segments-s24/'+c['package']+'-segments/'+f'{index:04d}.part'
  require(item['path']==expected and item['bytes']==item['end']-item['start']+1,'PREVIOUS_RANGE_PATH_OR_SIZE_MISMATCH')
  cache[index]=dict(item,prior_receipt=declared['receipt'])
 require(len(cache)==source['expected_complete_segments'],'PREVIOUS_COMPLETED_RANGE_COUNT_MISMATCH')
 return cache

def one_segment(c,folder,index,start,end,abort):
 record={'index':index,'start':start,'end':end,'expected_bytes':end-start+1,'started_utc':now(),'request_attempts':0,'automatic_retries':0}
 part=folder/(f'{index:04d}.part');headers=folder/(f'{index:04d}.headers');metrics=folder/(f'{index:04d}.curl.json');errors=folder/(f'{index:04d}.stderr')
 fd=None
 try:
  if index in c['verified_cache']:
   prior=c['verified_cache'][index]
   require(prior['start']==start and prior['end']==end,'CACHED_RANGE_BOUNDS_MISMATCH')
   fd,before=opened(prior['path'])
   require(before==prior['stat'] and hashes(fd)[:2]==(prior['bytes'],prior['sha256']) and identity(fd)==before,'CACHED_RANGE_IDENTITY_CHANGED')
   verify_path(prior['path'],before)
   record.update(status='COMPLETE',bytes=prior['bytes'],sha256=prior['sha256'],path=prior['path'],stat=before,etag=prior.get('etag',[]),origin='REUSED_VERIFIED_S24_SEGMENT',prior_receipt=prior['prior_receipt'])
   return record
  if abort.is_set():
   record['status']='SKIPPED_AFTER_OTHER_RANGE_FAILURE';return record
  time.sleep(2)  # bounded request spacing; no retry and no DNS/TLS override
  fd=os.open(part,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
  source='/proc/self/fd/'+str(fd)
  argv=['/usr/bin/curl','--fail','--proto','=https','--proto-redir','=https','--connect-timeout','25','--max-time','180','--max-filesize',str(end-start+1),'--silent','--show-error','--user-agent','Mozilla/5.0','--header','Accept-Encoding: identity','--range',str(start)+'-'+str(end),'--dump-header',str(headers),'--output',source,'--write-out','%{json}',c['url']]
  with metrics.open('xb') as met,errors.open('xb') as err:
   process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=met,stderr=err,pass_fds=(fd,));record.update(pid=process.pid,request_attempts=1)
   try:rc=process.wait(timeout=200)
   except subprocess.TimeoutExpired:
    process.kill();rc=process.wait(timeout=20);record.update(returncode=rc,joined=True,timed_out=True);raise RuntimeError('OWNED_CURL_DEADLINE')
  record.update(returncode=rc,joined=True,timed_out=False)
  for name,path in [('headers',headers),('metrics',metrics),('stderr',errors)]:
   raw=path.read_bytes();require(len(raw)<=65536,'CURL_METADATA_BOUND');record[name]={'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
  curl=json.loads(metrics.read_bytes());record['curl']={k:curl.get(k) for k in CURL_FIELDS}
  if curl.get('http_code') in (403,429):
   record['http_refusal_respected']=True;record['retry_after']=re.findall(r'^Retry-After:\s*([^\r\n]+)',headers.read_text(),re.I|re.M)
  require(rc==0,'CURL_RANGE_FAILED')
  require(curl['http_code']==206 and curl['url_effective']==c['url'] and curl['num_redirects']==0 and curl['num_retries']==0 and curl['ssl_verify_result']==0,'EXACT_SECURE_RANGE_RESPONSE_REQUIRED')
  text=headers.read_text();ranges=re.findall(r'^Content-Range:\s*([^\r\n]+)',text,re.I|re.M)
  require(ranges==[f"bytes {start}-{end}/{c['total_bytes']}"],'EXACT_CONTENT_RANGE_REQUIRED')
  count,sha,md5=hashes(fd);before=identity(fd)
  require(count==end-start+1 and before['st_size']==count,'RANGE_SIZE_MISMATCH');verify_path(part,before)
  record.update(status='COMPLETE',bytes=count,sha256=sha,path=str(part),stat=before,etag=re.findall(r'^ETag:\s*([^\r\n]+)',text,re.I|re.M))
 except BaseException as error:
  abort.set();record.update(status='FAILED',error_type=type(error).__name__,error=str(error)[:512],partial_preserved=part.exists())
  if fd is not None:
   count,sha,md5=hashes(fd);record.update(partial_bytes=count,partial_sha256=sha)
 finally:
  if fd is not None:os.close(fd)
  record['finished_utc']=now()
  receipt=write_json(folder/(f'{index:04d}.json'),record)
  record['receipt']=receipt
  print(json.dumps({'package':c['package'],'segment':index,'status':record.get('status'),'bytes':record.get('bytes',record.get('partial_bytes',0)),'receipt':receipt}),flush=True)
 return record

def run(c):
 row=dict(c,started_utc=now(),strategy='one explicit missing-range continuation; reuse32 verified old segments; single connection; 2s bounded spacing; no automatic retries',Android_reads=0,Main_lock_or_fds=0,installs=0,signature_verified=False,production_ready=False)
 held=[];part=ROOT/(c['package']+'.part');folder=ROOT/(c['package']+'-segments');segments=[]
 try:
  folder.mkdir(mode=0o700)
  c['verified_cache']=load_verified_cache(c);row['verified_old_segment_count']=len(c['verified_cache'])
  d=c['prior_header'];fd,before=opened(d['path']);held.append((fd,before,d))
  require(hashes(fd)[:2]==(d['bytes'],d['sha256']),'PRIOR_HEADER_CHANGED')
  text=os.read(fd,65537).decode('iso-8859-1')
  require(re.findall(r'^HTTP/\S+\s+(\d+)',text,re.M)==[str(d['status'])],'PRIOR_HTTP_STATUS_MISMATCH')
  if 'content_range' in d:require(re.findall(r'^Content-Range:\s*([^\r\n]+)',text,re.I|re.M)==[d['content_range']],'PRIOR_CONTENT_RANGE_MISMATCH')
  h=hashlib.sha256();m=hashlib.md5();count=0
  with part.open('xb') as out:
   for d in c['prefix_sources']:
    fd,before=opened(d['path']);held.append((fd,before,d));require(hashes(fd)[:2]==(d['bytes'],d['sha256']),'PRIOR_PARTIAL_BYTES_CHANGED')
    copied=0
    for block in iter(lambda:os.read(fd,1048576),b''):
     if count==0:require(block.startswith(b'PK\x03\x04'),'PREFIX_NOT_APK')
     out.write(block);h.update(block);m.update(block);count+=len(block);copied+=len(block)
    require(copied==d['bytes'] and identity(fd)==before,'PRIOR_PARTIAL_CHANGED_DURING_COPY')
   row.update(prefix_bytes=count,prefix_sha256=h.hexdigest());out.flush();os.fsync(out.fileno())
   require(0<count<c['total_bytes'],'VALID_PARTIAL_PREFIX_REQUIRED')
   ranges=[(i,start,min(start+CHUNK-1,c['total_bytes']-1)) for i,start in enumerate(range(count,c['total_bytes'],CHUNK))]
   row['declared_ranges']=[{'index':i,'start':s,'end':e} for i,s,e in ranges];write_json(folder/'request-plan.json',{'package':c['package'],'url':c['url'],'ranges':row['declared_ranges'],'each_range_max_attempts':1,'concurrency':1,'existing_segment_indexes_reused':sorted(c['verified_cache']),'request_spacing_seconds':2})
   abort=threading.Event()
   with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    futures=[pool.submit(one_segment,c,folder,i,s,e,abort) for i,s,e in ranges]
    segments=[future.result() for future in futures]
   row['segment_receipts']=[{'index':s['index'],'status':s['status'],'receipt':s['receipt']} for s in segments]
   require(all(s['status']=='COMPLETE' for s in segments),'ONE_OR_MORE_RANGES_INCOMPLETE')
   etags={v for s in segments for v in s.get('etag',[])};require(len(etags)<=1,'RANGE_ENTITY_TAG_CHANGED')
   for s in segments:
    fd,before=opened(s['path'])
    try:
     require(before==s['stat'] and hashes(fd)[:2]==(s['bytes'],s['sha256']),'COMPLETED_SEGMENT_CHANGED')
     for block in iter(lambda:os.read(fd,1048576),b''):out.write(block);h.update(block);m.update(block);count+=len(block)
     require(identity(fd)==before,'SEGMENT_CHANGED_DURING_ASSEMBLY');verify_path(s['path'],before)
    finally:os.close(fd)
   require(count==c['total_bytes'],'COMPLETE_APK_SIZE_MISMATCH')
   if c['metadata_md5'] is not None:require(m.hexdigest()==c['metadata_md5'],'OFFICIAL_STORE_CONTENT_MD5_MISMATCH')
   out.flush();os.fsync(out.fileno());written=os.fstat(out.fileno())
  fd,before=opened(part)
  try:
   require(before['st_dev']==written.st_dev and before['st_ino']==written.st_ino and hashes(fd)==(count,h.hexdigest(),m.hexdigest()) and identity(fd)==before,'COMPLETED_APK_CHANGED');verify_path(part,before)
  finally:os.close(fd)
  for fd,before,d in held:
   require(identity(fd)==before and hashes(fd)[:2]==(d['bytes'],d['sha256']) and identity(fd)==before,'PRIOR_SOURCE_CHANGED');verify_path(d['path'],before)
  final=ROOT/(c['package']+'.apk');require(not final.exists(),'FINAL_PATH_EXISTS');os.rename(part,final)
  row.update(status='STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION',bytes=count,sha256=h.hexdigest(),actual_md5=m.hexdigest(),local_path=str(final),all_prior_sources_unchanged=True)
 except BaseException as error:row.update(status='SEGMENTED_TRANSFER_FAILED',error_type=type(error).__name__,error=str(error)[:512],new_prefix_copy_preserved=part.exists())
 finally:
  for fd,_,_ in held:os.close(fd)
 row['segment_counts']={label:sum(s['status']==label for s in segments) for label in ('COMPLETE','FAILED','SKIPPED_AFTER_OTHER_RANGE_FAILURE')}
 row['finished_utc']=now();receipt=write_json(ROOT/(c['package']+'-result.json'),row)
 print(json.dumps({'package':c['package'],'status':row['status'],'artifact':{k:row.get(k) for k in ('bytes','sha256','local_path')},'segment_counts':row['segment_counts'],'error':row.get('error'),'receipt':receipt}),flush=True)
 return row

def main():
 require(os.getuid()==1000 and os.geteuid()==1000,'EXACT_UNPRIVILEGED_AUTHORITY')
 require(shutil.disk_usage(ROOT.parent).free>=4*1024**3,'STAGING_SPACE_REQUIRED')
 os.umask(0o077);ROOT.mkdir(mode=0o700)
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:rows=list(pool.map(run,CANDIDATES))
 result={'candidates':rows,'Android_reads':0,'Main_lock_or_fds':0,'automatic_retries':0,'production_ready':False}
 receipt=write_json(ROOT/'results.json',result)
 print(json.dumps({'report':receipt,'staged':sum(x['status'].startswith('STAGED_') for x in rows),'failed':sum(not x['status'].startswith('STAGED_') for x in rows)}),flush=True)
 return 0 if all(x['status'].startswith('STAGED_') for x in rows) else 1

if __name__=='__main__':raise SystemExit(main())
