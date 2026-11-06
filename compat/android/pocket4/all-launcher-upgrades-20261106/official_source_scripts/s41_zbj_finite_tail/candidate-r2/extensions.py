"""S41 additions; assembled with the pinned S34 source, never run standalone."""


def directory_identity(fd):
 s=os.fstat(fd)
 return tuple(getattr(s,key) for key in ('st_dev','st_ino','st_mode','st_uid','st_gid'))


def remember_parent(fd,path):
 value=directory_identity(fd)
 require(stat.S_ISDIR(value[2]),'ACTUAL_PARENT_NOT_DIRECTORY')
 key=str(path)
 if key in PARENT_IDENTITIES:require(PARENT_IDENTITIES[key]==value,'SOURCE_PARENT_IDENTITY_CHANGED')
 else:PARENT_IDENTITIES[key]=value


def opened(path):
 """Keep S34 leaf contract and add S36-style nofollow parent traversal."""
 path=Path(path);require(path.is_absolute() and '..' not in path.parts,'EXACT_ABSOLUTE_SOURCE_PATH')
 parents=[];fd=None
 try:
  parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);parents.append(parent)
  current=Path('/');remember_parent(parent,current)
  for part in path.parts[1:-1]:
   parent=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
   parents.append(parent);current=current/part;remember_parent(parent,current)
  fd=os.open(path.name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
  before=identity(fd)
  require(stat.S_ISREG(before['st_mode']) and before['st_nlink']==1 and
          before['st_uid']==before['st_gid']==1000,'EXACT_OWNED_REGULAR_FILE_REQUIRED')
  pin=EXACT_RECENT_IDENTITIES.get(str(path))
  if pin is not None:
   require(before['st_size']==pin['bytes'] and stat.S_IMODE(before['st_mode'])==pin['mode'] and
           ':'.join(str(before[k]) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))==pin['version'],
           'ACTUAL_RECENT_FILE_INFO_IDENTITY_CHANGED')
  for item in parents:
   require(stat.S_ISDIR(os.fstat(item).st_mode),'OPENED_PARENT_CHANGED_KIND')
  return fd,before
 except BaseException:
  if fd is not None:os.close(fd)
  raise
 finally:
  for item in reversed(parents):os.close(item)


def settled_terminal(raw,expected_sha,job_id,state,exit_code,stdout_bytes):
 require(hashlib.sha256(raw.encode()).hexdigest()==expected_sha,'EMBEDDED_TERMINAL_PIN_CHANGED')
 value=json.loads(raw)
 require(value['job_id']==job_id and value['state']==state and value['exit_code']==exit_code and
         all(value[k] is True for k in ('output_complete','output_durable','terminal_publication_confirmed','audit_recorded')) and
         all(value[k] is False for k in ('automatic_retry','timed_out','cancelled')) and
         value['log_bytes']=={'stdout':{'seen':stdout_bytes,'stored':stdout_bytes},'stderr':{'seen':0,'stored':0}} and
         value['log_errors']=={'stdout':None,'stderr':None} and
         value['log_synced']=={'stdout':True,'stderr':True} and
         value['log_truncated']=={'stdout':False,'stderr':False},'DURABLE_EXACT_PRIOR_OUTCOME_REQUIRED')
 return value


def dns_observation_gate():
 terminal=settled_terminal(DNS_TERMINAL_RAW,DNS_TERMINAL_SHA256,
           '1a1b2983a9d-fc05-7ed3','succeeded',0,len(DNS_STDOUT_RAW.encode()))
 require(hashlib.sha256(DNS_STDOUT_RAW.encode()).hexdigest()==DNS_STDOUT_SHA256,'ACTUAL_DNS_STDOUT_PIN_CHANGED')
 lines=DNS_STDOUT_RAW.splitlines();require(len(lines)==2,'EXACT_TWO_DNS_RECORDS')
 started,value=map(json.loads,lines)
 require(started['event']=='DNS_RESOLUTION_STARTED' and started['hostname']=='s.shouji.qihucdn.com' and
         started['application_call_count']==1 and started['automatic_retries']==0,'EXACT_DNS_STARTED_MARKER')
 require(value['schema']=='pocket4-zbj-system-resolver-observation-v1' and value['ok'] is True and
         value['status']=='OS_DNS_RESOLVED_ONLY_NOT_HTTP_OR_DOWNLOAD_VERIFIED' and
         value['hostname']=='s.shouji.qihucdn.com' and value['service_port']==443 and
         value['application_getaddrinfo_calls']==1 and value['application_retries']==0 and
         value['resolution_completed'] is True and value['errors']==[] and
         0<value['elapsed_seconds']<20 and 0<len(value['address_records'])<=256 and
         all(value[k]==1000 for k in ('actual_uid','actual_euid','actual_gid','actual_egid')) and
         value['before_descriptor_identities']==value['after_descriptor_identities'] and
         value['original_descriptor_identities_restored'] is True and
         all(value[k]==0 for k in ('HTTP_requests','APK_downloads','TLS_handshakes_requested','explicit_subprocesses',
                                  'files_written_by_probe','Android_commands','Main_actions','Main_lock_or_fds','installs','permission_changes')) and
         all(value[k] is False for k in ('normal_resolver_configuration_changed','IP_override_or_custom_resolver',
                                        'authorizes_download_or_install')) and
         all(type(value[k]) is int and value[k]==0 for k in ('proxy_configuration_changes','TLS_configuration_changes')),
         'EXACT_ACTUAL_NARROW_DNS_SUCCESS_REQUIRED')
 return {'job_id':terminal['job_id'],'terminal_sha256':DNS_TERMINAL_SHA256,'stdout_sha256':DNS_STDOUT_SHA256,
         'observed_at_unix_ms':terminal['at_unix_ms'],'elapsed_seconds':value['elapsed_seconds'],
         'address_record_count':len(value['address_records']),'addresses_used_as_override':False,
         'scope':'past ordinary OS DNS observation only; normal curl resolution still required for every request'}


def s34_result_gate(c,prior):
 settled_terminal(S28_TERMINAL_RAW,S28_TERMINAL_SHA256,'1a1b0f20329-fc05-7444','failed',1,21169)
 settled_terminal(S34_TERMINAL_RAW,S34_TERMINAL_SHA256,'1a1b19cedcf-fc05-79de','failed',1,14495)
 require(prior['package']==c['package'] and prior['url']==c['url'] and prior['total_bytes']==TOTAL_BYTES and
         prior['channel_version']=='9.5.20' and prior['metadata_md5'] is None and
         all(prior[k]==c[k] for k in ('prefix_sources','prior_header','s24_result','previous_segment_result')),
         'EXACT_S34_SOURCE_LINEAGE_REQUIRED')
 require(prior['status']=='SEGMENTED_TRANSFER_FAILED' and prior['error']=='ONE_OR_MORE_RANGES_INCOMPLETE' and
         prior['segment_counts']=={'COMPLETE':3,'FAILED':1,'SKIPPED_AFTER_OTHER_RANGE_FAILURE':37} and
         prior['prefix_bytes']==OLD_TAIL_START and prior['prefix_sha256']==S34_PREFIX_SHA256 and
         prior['verified_old_complete_segments']==41 and prior['failed_s28_partial_not_reused'] is True and
         prior['owned_curl_processes']=={'started':4,'joined':4,'outcome_unknown':False} and
         prior['prior_file_descriptors']=={'acquired':43,'closed':43,'errors':[]} and
         prior['etag_chain']=={'values':[],'all_observations_equal':True,'server_supplied_validator':False},
         'EXACT_SETTLED_S34_FAILURE_AND_CLOSURE_REQUIRED')
 rows=prior['segment_receipts']
 require(len(rows)==41 and [r['index'] for r in rows]==list(range(41)) and
         all(rows[i]['status']=='COMPLETE' and rows[i]['receipt']==S34_COMPLETE_RECEIPTS[i] for i in range(3)) and
         rows[3]['status']=='FAILED' and rows[3]['receipt']==S34_FAILURE_PIN and
         all(r['status']=='SKIPPED_AFTER_OTHER_RANGE_FAILURE' for r in rows[4:]),
         'ONLY_THREE_S34_COMPLETE_RANGES_MAY_BE_REUSED')
 require(prior['declared_ranges']==[{'index':i,'start':s,'end':min(s+CHUNK-1,TOTAL_BYTES-1)}
                                 for i,s in enumerate(range(OLD_TAIL_START,TOTAL_BYTES,CHUNK))],
         'EXACT_S34_ORIGINAL_RANGE_DECLARATIONS')


def s34_failure_gate(failure):
 require(failure['index']==3 and failure['status']=='FAILED' and failure['start']==TAIL_START and
         failure['end']==TAIL_START+CHUNK-1 and failure['expected_bytes']==CHUNK and
         failure['returncode']==6 and failure['request_attempts']==1 and failure['automatic_retries']==0 and
         failure['partial_bytes']==0 and failure['partial_size_snapshot']==0 and
         failure['partial_sha256']==hashlib.sha256(b'').hexdigest() and
         failure['curl']['http_code']==0 and failure['curl']['size_download']==0 and
         failure['curl']['errormsg']=='Could not resolve host: s.shouji.qihucdn.com' and
         failure['joined'] is True and failure['pidfd_acquired'] is True and
         failure['pidfd_closed'] is True and failure['pidfd_exit_observed'] is True and
         failure['outcome_unknown'] is False and failure['timed_out'] is False and
         failure['owned_curl_signal_count']==0,'ACTUAL_SETTLED_S34_DNS_FAILURE_REQUIRED')


def load_s34_complete(c,prefix_segments):
 prior=read_pinned_json(S34_RESULT_PIN);s34_result_gate(c,prior)
 s34_failure_gate(read_pinned_json(S34_FAILURE_PIN))
 expected_prior=list(c['prefix_sources'])+[{'path':s['path'],'bytes':s['bytes'],'sha256':s['sha256'],'stat':s['stat'],
       'receipt_chain':s['receipt_chain'],'prior_index':s['prior_index']} for s in prefix_segments]
 require(prior['verified_prefix_sources']==expected_prior,'S34_PREFIX_CHAIN_DIFFERS_FROM_VERIFIED_S28')
 result=[]
 for index,declaration in enumerate(S34_COMPLETE_RECEIPTS):
  remaining();item=read_pinned_json(declaration);stem=S34_FOLDER+f'/{index:04d}'
  require(item['index']==index and item['status']=='COMPLETE' and item['start']==OLD_TAIL_START+index*CHUNK and
          item['end']==OLD_TAIL_START+(index+1)*CHUNK-1 and item['bytes']==CHUNK and
          item['request_attempts']==1 and item['automatic_retries']==0 and
          item['path']==stem+'.part' and item['pidfd_acquired'] is True and item['pidfd_closed'] is True and
          item['pidfd_exit_observed'] is True and item['owned_curl_signal_count']==0 and item['outcome_unknown'] is False,
          'EXACT_S34_COMPLETED_RANGE_AND_RETIREMENT')
  expected=S34_BODY_PINS[index]
  require(item['path']==expected['path'] and item['bytes']==expected['bytes'] and
          item['sha256']==expected['sha256'] and item['stat']==expected['stat'],'ACTUAL_READBACK_BODY_BINDING_CHANGED')
  headers=pinned_metadata(item['headers'],stem+'.headers').decode('iso-8859-1')
  metrics=json.loads(pinned_metadata(item['metrics'],stem+'.curl.json'))
  require({key:metrics.get(key) for key in CURL_FIELDS}==item['curl'],'S34_CURL_METRICS_CHANGED')
  require(pinned_metadata(item['stderr'],stem+'.stderr')==b'','S34_SUCCESSFUL_STDERR_NOT_EMPTY')
  require(validate_response(c,item,headers)==item['etag']==[],'S34_NO_SERVER_ETAG_EXPECTED')
  result.append(dict(item,receipt_chain=[S34_RESULT_PIN,declaration],prior_s34_index=index))
 return result


def main():
 global DEADLINE
 require(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000 and
         sys.argv[1:]==['--continue-zbj-38-ranges-once'],'EXACT_UNPRIVILEGED_EXPLICIT_ENTRY')
 before=census();created=False;rows=[]
 result={'schema':'pocket4-zbj-explicit-s41-tail-v1','ok':False,'candidates':rows,'errors':[],
         'Android_reads':0,'Main_lock_or_fds':0,'automatic_retries':0,'installs':0,'permission_changes':0,
         'production_ready':False,'cleanup_eligible':False,'old_files_modified_or_deleted':False,
         'signature_or_manifest_verified':False,'prior_failures_preserved':True}
 try:
  require(ROOT.parent.resolve()==ROOT.parent and shutil.disk_usage(ROOT.parent).free>=4*1024**3,
          'FIXED_STAGING_PARENT_AND_SPACE_REQUIRED')
  result['dns_observation_basis']=dns_observation_gate()
  os.umask(0o077);ROOT.mkdir(mode=0o700);created=True;DEADLINE=time.monotonic()+TOTAL_SECONDS
  rows.extend(run(c) for c in CANDIDATES)
  result['ok']=len(rows)==1 and all(row['status']=='STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION' and
       row.get('all_prior_sources_unchanged') is True and row['prior_file_descriptors']['errors']==[] and
       row['owned_curl_processes']['started']==row['owned_curl_processes']['joined']==38 and
       row['owned_curl_processes']['outcome_unknown'] is False for row in rows)
 except BaseException as error:
  result['errors'].append({'type':type(error).__name__,'reason':str(error)[:1024]})
 after=census();result['before_descriptor_identities']=before;result['after_descriptor_identities']=after
 result['original_descriptor_identities_restored']=before==after
 result['ok']=bool(result['ok'] and before==after and not result['errors'])
 result['state']='STAGED_PENDING_FULL_APK_VERIFICATION' if result['ok'] else 'FINITE_CONTINUATION_FAILED_NO_RETRY'
 result['staged']=sum(row['status']=='STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION' for row in rows)
 result['failed']=sum(row['status']!='STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION' for row in rows)
 result['partial_or_complete_candidate_installable']=False
 if created:result['report']=write_json(ROOT/'results.json',result)
 print(json.dumps(result,ensure_ascii=False),flush=True)
 return 0 if result['ok'] else 1
