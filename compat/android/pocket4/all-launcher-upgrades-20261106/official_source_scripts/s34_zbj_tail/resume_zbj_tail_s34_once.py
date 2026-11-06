#!/usr/bin/env python3
"""One explicit s34 tail after settled s28: 41 sequential ranges, at most 1 MiB.

Only the original prefix and COMPLETE s28 segments 0..40 are reused.
The failed s28 partial is excluded. All reuse follows pinned origin receipts,
secure HTTP metadata, complete bytes/hash/stat, and exact source paths.
No Android, Main descriptor, namespace, permissions, or application actions."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import select
import signal
import stat
import subprocess
import threading
import time

ROOT=Path('/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s34')
CHUNK=1024*1024
OLD_CHUNK=2*1024*1024
OLD_PREFIX=38387712
TAIL_START=124370944
TOTAL_BYTES=166873622
TOTAL_SECONDS=1800
DEADLINE=None
CANDIDATES=[{'package': 'com.zhubajie.client', 'channel_version': '9.5.20', 'url': 'https://s.shouji.qihucdn.com/261009/9b8bc092373e8f09d56861322b8ce1c9/com.zhubajie.client_370.apk?en=curpage%3Dopenbox_wap_detail%26exp%3D1794571897%26from%3Dopenbox_mintf_getAppInfoByIds%26m2%3D%26ts%3D1793967097%26tok%3Db64e944d9e3de8d16861a770d758bee5%26v%3D%26f%3Dz.apk', 'total_bytes': 166873622, 'metadata_md5': None, 'prior_jobs': ['1a1b0c7a0fa-fc05-72dc', '1a1b0e62475-fc05-73cf', '1a1b0f20329-fc05-7444'], 'prefix_sources': [{'path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-s17/com.zhubajie.client.part', 'bytes': 38387712, 'sha256': '80c613a9897cf2ca5003ec48c2611c3ac25e692bd4db26fdb88a94c1b1465735'}], 'prior_header': {'path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-s17/com.zhubajie.client.headers', 'bytes': 424, 'sha256': '86b28ca76edde2297bdcf6a79dc79d2ccf34fb50617d47a4aa4e3cd76521c9da', 'status': 200}, 's24_result': {'path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-segments-s24/com.zhubajie.client-result.json', 'bytes': 27693, 'sha256': '7327e768a574d3aa7f0d904c80e2195057c1e75ccb873a47288d0cb949693d59', 'expected_complete_segments': 32, 'explicit_continuation_reason': 'Previous attempt terminal exit1. One failed range had curl6 DNS lookup failure with zero bytes; no HTTP rejection. Parent authorized one single-connection missing-range attempt.'}, 'previous_segment_result': {'path': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-missing-s28/com.zhubajie.client-result.json', 'bytes': 28307, 'sha256': 'd4bac41dee796ae163b4dabeccc87153d6f95c2191cde4a3eeac71fd9c2b3dde', 'expected_complete_segments': 41, 'expected_s24_reused': 32}}]
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
def remaining():
 require(DEADLINE is not None and time.monotonic()<DEADLINE,'TOTAL_TRANSFER_DEADLINE')
 return DEADLINE-time.monotonic()

def hashes(fd):
 os.lseek(fd,0,os.SEEK_SET);h=hashlib.sha256();m=hashlib.md5();n=0
 for block in iter(lambda:os.read(fd,1048576),b''):
  remaining();h.update(block);m.update(block);n+=len(block)
  require(n<=TOTAL_BYTES,'HASH_BYTE_BOUND')
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
 require(0<declaration['bytes']<=65536,'PRIOR_METADATA_BOUND')
 fd,before=opened(declaration['path'])
 try:
  require(before['st_size']==declaration['bytes'] and hashes(fd)[:2]==(declaration['bytes'],declaration['sha256']),'PRIOR_JSON_IDENTITY_CHANGED')
  raw=os.read(fd,declaration['bytes']+1);require(len(raw)==declaration['bytes'],'PRIOR_JSON_SIZE_CHANGED')
  require(identity(fd)==before,'PRIOR_JSON_CHANGED_DURING_READ');verify_path(declaration['path'],before)
  return json.loads(raw)
 finally:os.close(fd)

def pinned_metadata(declaration,expected_path):
 require(declaration['path']==expected_path and 0<=declaration['bytes']<=65536,'FIXED_METADATA_PATH_REQUIRED')
 fd,before=opened(expected_path)
 try:
  require(before['st_size']==declaration['bytes'] and hashes(fd)[:2]==(declaration['bytes'],declaration['sha256']),'CURL_METADATA_PIN_CHANGED')
  raw=os.read(fd,declaration['bytes']+1)
  require(len(raw)==declaration['bytes'] and identity(fd)==before,'CURL_METADATA_CHANGED')
  verify_path(expected_path,before);return raw
 finally:os.close(fd)

def header_etags(text):
 tags=re.findall(r'^ETag:\s*([^\r\n]+)',text,re.I|re.M)
 require(len(tags)<=1,'AMBIGUOUS_ENTITY_TAG')
 return tags

def validate_response(c,item,text):
 curl=item['curl'];start,end=item['start'],item['end']
 require(item.get('returncode')==0 and item.get('joined') is True and item.get('timed_out') is False,
         'ORIGIN_CURL_NOT_SUCCESSFULLY_JOINED')
 require(curl['http_code']==206 and curl['url_effective']==c['url'] and curl['num_redirects']==0 and
         curl['num_retries']==0 and curl['ssl_verify_result']==0 and curl['exitcode']==0,
         'EXACT_SECURE_RANGE_RESPONSE_REQUIRED')
 require(not re.search(r'^Retry-After\s*:',text,re.I|re.M),'RETRY_AFTER_REFUSAL_RESPECTED')
 require(re.findall(r'^HTTP/\S+\s+(\d+)',text,re.M)==['206'],'SINGLE_HTTP_206_REQUIRED')
 require(re.findall(r'^Content-Range:\s*([^\r\n]+)',text,re.I|re.M)==
         [f"bytes {start}-{end}/{c['total_bytes']}"],'EXACT_CONTENT_RANGE_REQUIRED')
 lengths=re.findall(r'^Content-Length:\s*([^\r\n]+)',text,re.I|re.M)
 require(lengths in ([],[str(end-start+1)]),'CONTENT_LENGTH_CONTRADICTS_COMPLETE_RANGE')
 require(curl['size_download']==end-start+1 and item['bytes']==end-start+1,'COMPLETE_RANGE_BODY_REQUIRED')
 return header_etags(text)

def validate_origin(c,item,folder,index):
 require(item['index']==index and item['status']=='COMPLETE' and item.get('request_attempts')==1 and
         item.get('automatic_retries')==0 and item['start']==OLD_PREFIX+index*OLD_CHUNK and
         item['end']==OLD_PREFIX+(index+1)*OLD_CHUNK-1,'EXACT_OLD_COMPLETE_RANGE_REQUIRED')
 stem=folder+f'/{index:04d}'
 require(item['path']==stem+'.part' and item['bytes']==OLD_CHUNK,'EXACT_OLD_DATA_PATH_REQUIRED')
 headers=pinned_metadata(item['headers'],stem+'.headers').decode('iso-8859-1')
 metrics=json.loads(pinned_metadata(item['metrics'],stem+'.curl.json'))
 require({key:metrics.get(key) for key in CURL_FIELDS}==item['curl'],'ORIGINAL_CURL_RECORD_DIFFERS')
 require(pinned_metadata(item['stderr'],stem+'.stderr')==b'','SUCCESSFUL_CURL_STDERR_NOT_EMPTY')
 require(validate_response(c,item,headers)==item.get('etag',[]),'RECORDED_ENTITY_TAG_DIFFERS')
 return item

def load_verified_prefix(c):
 source=c['previous_segment_result'];previous=read_pinned_json(source);prior24=read_pinned_json(c['s24_result'])
 for prior in (previous,prior24):
  require(prior['package']==c['package'] and prior['url']==c['url'] and
          prior['total_bytes']==c['total_bytes'],'EXACT_PREVIOUS_DOWNLOAD_SCOPE_REQUIRED')
 require(previous['status']=='SEGMENTED_TRANSFER_FAILED' and
         previous['segment_counts']=={'COMPLETE':41,'FAILED':1,'SKIPPED_AFTER_OTHER_RANGE_FAILURE':20},
         'ORIGINAL_FAILED_ATTEMPT_MUST_REMAIN_FAILED')
 rows=previous['segment_receipts'];require([row['index'] for row in rows]==list(range(62)),
         'COMPLETE_S28_DECLARATION_SET_REQUIRED')
 require([row['index'] for row in rows if row['status']=='COMPLETE']==list(range(41)) and
         rows[41]['status']=='FAILED' and all(row['status']=='SKIPPED_AFTER_OTHER_RANGE_FAILURE' for row in rows[42:]),
         'ONLY_41_CONTIGUOUS_COMPLETE_PREFIX_SEGMENTS')
 old24={row['index']:row for row in prior24['segment_receipts'] if row['status']=='COMPLETE'}
 require(len(old24)==len([row for row in prior24['segment_receipts'] if row['status']=='COMPLETE'])==32,
         'EXACT_S24_COMPLETE_COUNT_REQUIRED')
 folder24='/home/alex/work/pocket4-launcher-official-candidates-20261106-segments-s24/'+c['package']+'-segments'
 folder28='/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-missing-s28/'+c['package']+'-segments'
 complete=[];reused=0
 for declared in rows[:41]:
  remaining();index=declared['index']
  require(declared['receipt']['path']==folder28+f'/{index:04d}.json','EXACT_S28_RECEIPT_PATH_REQUIRED')
  item=read_pinned_json(declared['receipt'])
  require(item['index']==index and item['status']=='COMPLETE' and
          item['start']==OLD_PREFIX+index*OLD_CHUNK and item['end']==OLD_PREFIX+(index+1)*OLD_CHUNK-1,
          'S28_COMPLETE_RANGE_BOUNDS_REQUIRED')
  if item.get('origin')=='REUSED_VERIFIED_S24_SEGMENT':
   require(index in old24 and item['prior_receipt']==old24[index]['receipt'] and
           item['prior_receipt']['path']==folder24+f'/{index:04d}.json','EXACT_S24_PRIOR_RECEIPT_REQUIRED')
   origin=validate_origin(c,read_pinned_json(item['prior_receipt']),folder24,index)
   require(all(item[key]==origin[key] for key in ('path','bytes','sha256','stat','start','end')) and
           item.get('etag',[])==origin.get('etag',[]) and item.get('request_attempts')==0,
           'REUSED_RECORD_DIFFERS_FROM_VERIFIED_ORIGIN')
   reused+=1;chain=[declared['receipt'],item['prior_receipt']]
  else:
   require('origin' not in item and 'prior_receipt' not in item and index not in old24,
           'UNEXPECTED_OLD_RANGE_ORIGIN')
   origin=validate_origin(c,item,folder28,index);chain=[declared['receipt']]
  complete.append(dict(origin,receipt_chain=chain,prior_index=index))
 require(len(complete)==source['expected_complete_segments']==41 and
         reused==source['expected_s24_reused']==32,'EXACT_PREFIX_PROVENANCE_COUNTS_REQUIRED')
 return complete

def own_curl(argv,fd,metrics,errors,record,seconds):
 process=None;pidfd=None
 record.update(joined=False,pidfd_acquired=False,pidfd_closed=False,pidfd_exit_observed=False,
               owned_curl_signal_count=0,outcome_unknown=False,timed_out=False)
 try:
  with metrics.open('xb') as met,errors.open('xb') as err:
   try:
    process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=met,stderr=err,pass_fds=(fd,),close_fds=True)
    record.update(pid=process.pid,request_attempts=1)
    pidfd=os.pidfd_open(process.pid,0);record['pidfd_acquired']=True
    try:process.wait(timeout=min(seconds+5,max(.01,remaining()-10)))
    except subprocess.TimeoutExpired:
     record['timed_out']=True;raise RuntimeError('OWNED_CURL_DEADLINE')
   finally:
    if process is not None:
     if process.returncode is None and pidfd is not None:
      poll=select.poll();poll.register(pidfd,select.POLLIN)
      if not poll.poll(0):
       try:signal.pidfd_send_signal(pidfd,signal.SIGKILL,None,0);record['owned_curl_signal_count']+=1
       except ProcessLookupError:pass
       except BaseException as e:record['signal_error']=type(e).__name__
     try:process.wait(timeout=10);record.update(joined=True,returncode=process.returncode)
     except BaseException as e:record.update(outcome_unknown=True,join_error=type(e).__name__)
     if pidfd is not None:
      poll=select.poll();poll.register(pidfd,select.POLLIN);record['pidfd_exit_observed']=bool(poll.poll(0))
    met.flush();err.flush();os.fsync(met.fileno());os.fsync(err.fileno())
  require(record['joined'] and record['pidfd_exit_observed'] and not record['outcome_unknown'],'OWNED_CURL_RETIREMENT_UNPROVEN')
  return process.returncode
 finally:
  if pidfd is not None:os.close(pidfd);record['pidfd_closed']=True

def new_metadata(path):
 fd,before=opened(path)
 try:
  require(before['st_size']<=65536,'CURL_METADATA_BOUND')
  raw=os.read(fd,65537);require(len(raw)==before['st_size'],'CURL_METADATA_SIZE_CHANGED')
  require(identity(fd)==before,'CURL_METADATA_CHANGED');verify_path(path,before)
  return raw,{'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
 finally:os.close(fd)

def tail_plan(c):
 require(c['total_bytes']==TOTAL_BYTES,'EXACT_TOTAL_REQUIRED')
 ranges=[(i,start,min(start+CHUNK-1,TOTAL_BYTES-1))
         for i,start in enumerate(range(TAIL_START,TOTAL_BYTES,CHUNK))]
 require(len(ranges)==41 and sum(end-start+1 for _,start,end in ranges)==42502678,
         'FINITE_TAIL_PLAN_REQUIRED')
 return ranges

def one_segment(c,folder,index,start,end,abort):
 record={'index':index,'start':start,'end':end,'expected_bytes':end-start+1,'started_utc':now(),
         'request_attempts':0,'automatic_retries':0,'range_namespace':'S34_TAIL_1M_NO_CACHE'}
 part=folder/(f'{index:04d}.part');headers=folder/(f'{index:04d}.headers');metrics=folder/(f'{index:04d}.curl.json');errors=folder/(f'{index:04d}.stderr')
 fd=None
 try:
  if abort.is_set():record['status']='SKIPPED_AFTER_OTHER_RANGE_FAILURE';return record
  require(TAIL_START+index*CHUNK==start and end==min(start+CHUNK-1,c['total_bytes']-1) and
          0<end-start+1<=CHUNK,'EXACT_NEW_1M_RANGE_REQUIRED')
  require(remaining()>20,'INSUFFICIENT_TOTAL_BUDGET_FOR_NEW_REQUEST')
  time.sleep(2)
  seconds=min(180,int(remaining()-15));require(seconds>=1,'TOTAL_TRANSFER_DEADLINE')
  fd=os.open(part,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
  argv=['/usr/bin/curl','--disable','--fail','--proto','=https','--proto-redir','=https','--connect-timeout',
        str(min(25,seconds)),'--max-time',str(seconds),'--max-filesize',str(end-start+1),
        '--retry','0','--silent','--show-error','--user-agent','Mozilla/5.0',
        '--header','Accept-Encoding: identity','--range',str(start)+'-'+str(end),
        '--dump-header',str(headers),'--output','/proc/self/fd/'+str(fd),'--write-out','%{json}',c['url']]
  rc=own_curl(argv,fd,metrics,errors,record,seconds)
  metadata={}
  for name,path in [('headers',headers),('metrics',metrics),('stderr',errors)]:
   metadata[name],record[name]=new_metadata(path)
  curl=json.loads(metadata['metrics']);record['curl']={k:curl.get(k) for k in CURL_FIELDS}
  text=metadata['headers'].decode('iso-8859-1')
  retry_after=bool(re.search(r'^Retry-After\s*:',text,re.I|re.M))
  if curl.get('http_code') in (403,429) or retry_after:
   record['http_refusal_respected']=True
   record['retry_after']=re.findall(r'^Retry-After:\s*([^\r\n]*)',text,re.I|re.M)
   raise RuntimeError('HTTP_REFUSAL_NO_FURTHER_REQUESTS')
  require(rc==0 and record['owned_curl_signal_count']==0 and metadata['stderr']==b'','CURL_RANGE_FAILED')
  count,sha,md5=hashes(fd);before=identity(fd)
  require(count==end-start+1 and before['st_size']==count,'RANGE_SIZE_MISMATCH')
  record['bytes']=count
  tags=validate_response(c,record,text)
  require(tags==c['expected_etags'],'ENTITY_TAG_CHAIN_CHANGED')
  verify_path(part,before);os.fsync(fd)
  record.update(status='COMPLETE',sha256=sha,path=str(part),stat=before,etag=tags)
 except BaseException as error:
  abort.set();record.update(status='FAILED',error_type=type(error).__name__,error=str(error)[:512],partial_preserved=part.exists())
  if fd is not None:
   record['partial_size_snapshot']=os.fstat(fd).st_size
   if record.get('joined') and DEADLINE is not None and time.monotonic()<DEADLINE:
    try:
     count,sha,md5=hashes(fd);record.update(partial_bytes=count,partial_sha256=sha)
    except BaseException as e:record['partial_hash_status']='NOT_COMPUTED_'+type(e).__name__
   else:record['partial_hash_status']='NOT_COMPUTED_AFTER_DEADLINE_OR_UNJOINED_CURL'
 finally:
  if fd is not None:os.close(fd)
  record['finished_utc']=now()
  receipt=write_json(folder/(f'{index:04d}.json'),record);record['receipt']=receipt
  print(json.dumps({'package':c['package'],'segment':index,'status':record.get('status'),
                    'bytes':record.get('bytes',record.get('partial_bytes',0)),'receipt':receipt}),flush=True)
 return record

def run(c):
 row=dict(c,started_utc=now(),strategy='one explicit s34 tail; old prefix+41 complete 2MiB segments; 41 sequential <=1MiB requests; no retries',
          Android_reads=0,Main_lock_or_fds=0,installs=0,signature_verified=False,production_ready=False,total_deadline_seconds=TOTAL_SECONDS)
 held=[];part=ROOT/(c['package']+'.part');folder=ROOT/(c['package']+'-tail-1m');segments=[]
 try:
  folder.mkdir(mode=0o700)
  prefix_segments=load_verified_prefix(c);row['verified_old_complete_segments']=41
  row['failed_s28_partial_not_reused']=True
  d=c['prior_header'];fd,before=opened(d['path']);held.append((fd,before,d))
  require(before['st_size']==d['bytes'] and hashes(fd)[:2]==(d['bytes'],d['sha256']),'PRIOR_HEADER_CHANGED')
  text=os.read(fd,65537).decode('iso-8859-1')
  require(re.findall(r'^HTTP/\S+\s+(\d+)',text,re.M)==[str(d['status'])],'PRIOR_HTTP_STATUS_MISMATCH')
  require(not re.search(r'^Retry-After\s*:',text,re.I|re.M),'ORIGINAL_PREFIX_REFUSAL')
  c['expected_etags']=header_etags(text)
  require(all(s.get('etag',[])==c['expected_etags'] for s in prefix_segments),'PREFIX_ENTITY_TAG_CHAIN_CHANGED')
  row['etag_chain']={'values':c['expected_etags'],'all_observations_equal':True,
                    'server_supplied_validator':bool(c['expected_etags'])}
  source_prefix=c['prefix_sources'];require(len(source_prefix)==1 and source_prefix[0]['bytes']==OLD_PREFIX,'EXACT_ORIGINAL_PREFIX')
  sources=list(source_prefix)+[{'path':s['path'],'bytes':s['bytes'],'sha256':s['sha256'],'stat':s['stat'],
                                'receipt_chain':s['receipt_chain'],'prior_index':s['prior_index']} for s in prefix_segments]
  h=hashlib.sha256();m=hashlib.md5();count=0
  with part.open('xb') as out:
   for d in sources:
    remaining();fd,before=opened(d['path']);held.append((fd,before,d))
    require(before['st_size']==d['bytes'] and ('stat' not in d or before==d['stat']) and
            hashes(fd)[:2]==(d['bytes'],d['sha256']),'PRIOR_COMPLETE_SOURCE_IDENTITY_CHANGED')
    copied=0
    for block in iter(lambda:os.read(fd,1048576),b''):
     remaining()
     if count==0:require(block.startswith(b'PK\x03\x04'),'PREFIX_NOT_APK')
     out.write(block);h.update(block);m.update(block);count+=len(block);copied+=len(block)
    require(copied==d['bytes'] and identity(fd)==before,'PRIOR_COMPLETE_SOURCE_CHANGED_DURING_COPY')
    verify_path(d['path'],before)
   require(count==TAIL_START==OLD_PREFIX+41*OLD_CHUNK,'EXACT_NEW_TAIL_START_REQUIRED')
   row.update(prefix_bytes=count,prefix_sha256=h.hexdigest(),verified_prefix_sources=sources)
   out.flush();os.fsync(out.fileno())
   ranges=tail_plan(c)
   row['declared_ranges']=[{'index':i,'start':s,'end':e} for i,s,e in ranges]
   write_json(folder/'request-plan.json',{'package':c['package'],'url':c['url'],'ranges':row['declared_ranges'],
              'each_range_max_attempts':1,'concurrency':1,'request_spacing_seconds':2,
              'range_namespace':'S34_TAIL_1M_NO_CACHE','old_index_namespace':'S28_PREFIX_2M',
              'total_deadline_seconds':TOTAL_SECONDS})
   abort=threading.Event()
   for i,s,e in ranges:segments.append(one_segment(c,folder,i,s,e,abort))
   row['segment_receipts']=[{'index':s['index'],'status':s['status'],'receipt':s['receipt']} for s in segments]
   require(all(s['status']=='COMPLETE' for s in segments),'ONE_OR_MORE_RANGES_INCOMPLETE')
   require(all(s.get('etag',[])==c['expected_etags'] for s in segments),'TAIL_ENTITY_TAG_CHAIN_CHANGED')
   for s in segments:
    remaining();fd,before=opened(s['path'])
    try:
     require(before==s['stat'] and hashes(fd)[:2]==(s['bytes'],s['sha256']),'COMPLETED_SEGMENT_CHANGED')
     for block in iter(lambda:os.read(fd,1048576),b''):
      remaining();out.write(block);h.update(block);m.update(block);count+=len(block)
     require(identity(fd)==before,'SEGMENT_CHANGED_DURING_ASSEMBLY');verify_path(s['path'],before)
    finally:os.close(fd)
   require(count==c['total_bytes']==TOTAL_BYTES,'COMPLETE_APK_SIZE_MISMATCH')
   if c['metadata_md5'] is not None:require(m.hexdigest()==c['metadata_md5'],'OFFICIAL_STORE_CONTENT_MD5_MISMATCH')
   out.flush();os.fsync(out.fileno());written=os.fstat(out.fileno())
  fd,before=opened(part)
  try:
   require(before['st_dev']==written.st_dev and before['st_ino']==written.st_ino and
           hashes(fd)==(count,h.hexdigest(),m.hexdigest()) and identity(fd)==before,'COMPLETED_APK_CHANGED')
   verify_path(part,before)
  finally:os.close(fd)
  for fd,before,d in held:
   remaining();require(identity(fd)==before and hashes(fd)[:2]==(d['bytes'],d['sha256']) and identity(fd)==before,
                        'PRIOR_SOURCE_CHANGED');verify_path(d['path'],before)
  require(load_verified_prefix(c)==prefix_segments,'PRIOR_RECEIPT_CHAIN_CHANGED')
  final=ROOT/(c['package']+'.apk');require(not final.exists(),'FINAL_PATH_EXISTS');os.rename(part,final)
  directory=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
  try:os.fsync(directory)
  finally:os.close(directory)
  fd,final_stat=opened(final)
  try:
   require(final_stat['st_dev']==written.st_dev and final_stat['st_ino']==written.st_ino and
           hashes(fd)==(count,h.hexdigest(),m.hexdigest()) and identity(fd)==final_stat,'FINAL_PATH_IDENTITY_CHANGED')
   verify_path(final,final_stat)
  finally:os.close(fd)
  row.update(status='STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION',bytes=count,sha256=h.hexdigest(),
             actual_md5=m.hexdigest(),local_path=str(final),all_prior_sources_unchanged=True,
             verification_required={'package':'com.zhubajie.client','version_code':370,
                                    'greater_than_installed_code':369,'vendor_signature':True,'ABI':True})
 except BaseException as error:
  row.update(status='SEGMENTED_TRANSFER_FAILED',error_type=type(error).__name__,error=str(error)[:512],
             new_prefix_copy_preserved=part.exists(),final_candidate_path_preserved=(ROOT/(c['package']+'.apk')).exists())
 finally:
  close_errors=[]
  for fd,_,_ in held:
   try:os.close(fd)
   except OSError as e:close_errors.append(type(e).__name__)
  row['prior_file_descriptors']={'acquired':len(held),'closed':len(held)-len(close_errors),'errors':close_errors}
  if close_errors:row.update(status='SEGMENTED_TRANSFER_FAILED',descriptor_close_unproven=True)
 row['segment_counts']={label:sum(s['status']==label for s in segments) for label in ('COMPLETE','FAILED','SKIPPED_AFTER_OTHER_RANGE_FAILURE')}
 row['owned_curl_processes']={'started':sum(s.get('request_attempts',0) for s in segments),
     'joined':sum(s.get('joined') is True for s in segments),
     'outcome_unknown':any(s.get('outcome_unknown',False) for s in segments)}
 row['finished_utc']=now();receipt=write_json(ROOT/(c['package']+'-result.json'),row)
 print(json.dumps({'package':c['package'],'status':row['status'],'artifact':{k:row.get(k) for k in ('bytes','sha256','local_path')},
                   'segment_counts':row['segment_counts'],'error':row.get('error'),'receipt':receipt}),flush=True)
 return row

def main():
 global DEADLINE
 require(os.getuid()==1000 and os.geteuid()==1000,'EXACT_UNPRIVILEGED_AUTHORITY')
 require(shutil.disk_usage(ROOT.parent).free>=4*1024**3,'STAGING_SPACE_REQUIRED')
 os.umask(0o077);ROOT.mkdir(mode=0o700);DEADLINE=time.monotonic()+TOTAL_SECONDS
 rows=[run(c) for c in CANDIDATES]
 result={'candidates':rows,'Android_reads':0,'Main_lock_or_fds':0,'automatic_retries':0,'production_ready':False}
 receipt=write_json(ROOT/'results.json',result)
 print(json.dumps({'report':receipt,'staged':sum(x['status'].startswith('STAGED_') for x in rows),
                   'failed':sum(not x['status'].startswith('STAGED_') for x in rows)}),flush=True)
 return 0 if all(x['status'].startswith('STAGED_') for x in rows) else 1

if __name__=='__main__':raise SystemExit(main())
