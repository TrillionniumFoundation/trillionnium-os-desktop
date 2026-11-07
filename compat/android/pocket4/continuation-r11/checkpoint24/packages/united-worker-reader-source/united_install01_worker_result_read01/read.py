"""Collect only the exact pinned owned United successful worker result; no runtime actions."""
import base64,hashlib,json,os,re,signal,stat,sys,time
FILES={"worker_result":{"bytes":16495,"path":"/home/alex/work/pocket4-owned-united-qa-r1-install-state-01/worker/result.json","sha256":"4b00d7f66902fbcd933599ca5e7d85fa6369833e2feb0b594f9ab395eee6e858"}}
AUTHORITY_RAW={"coordinator":"{\n  \"App_launches\": 0,\n  \"Bili_Flow_instantiated\": false,\n  \"Main_after\": {\n    \"Main_epoch_sha256\": \"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\n    \"authenticated_owner_chain_matches\": true,\n    \"config_sha256\": \"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\",\n    \"current_baseline_qualification_sha256\": \"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\",\n    \"current_baseline_sha256\": \"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\",\n    \"current_executable_and_root_backing_match\": true,\n    \"current_user_namespaces_match\": true,\n    \"framework_exit_cause_resolved\": false,\n    \"historical_activation_sha256\": \"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615\",\n    \"historical_verified_sha256\": \"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387\",\n    \"old_helpers_and_tasks_reauthorized\": false,\n    \"previous_current_baseline_sha256\": \"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\n    \"production_ready\": false,\n    \"resource_limits_match\": true,\n    \"schema\": \"pocket4-current-main-guard-v2\",\n    \"seven_processes_match\": true,\n    \"three_host_processes_match\": true\n  },\n  \"Main_before\": {\n    \"Main_epoch_sha256\": \"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\n    \"authenticated_owner_chain_matches\": true,\n    \"config_sha256\": \"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\",\n    \"current_baseline_qualification_sha256\": \"ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e\",\n    \"current_baseline_sha256\": \"633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364\",\n    \"current_executable_and_root_backing_match\": true,\n    \"current_user_namespaces_match\": true,\n    \"framework_exit_cause_resolved\": false,\n    \"historical_activation_sha256\": \"7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615\",\n    \"historical_verified_sha256\": \"2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387\",\n    \"old_helpers_and_tasks_reauthorized\": false,\n    \"previous_current_baseline_sha256\": \"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\n    \"production_ready\": false,\n    \"resource_limits_match\": true,\n    \"schema\": \"pocket4-current-main-guard-v2\",\n    \"seven_processes_match\": true,\n    \"three_host_processes_match\": true\n  },\n  \"UI_actions\": 0,\n  \"audio_actions\": 0,\n  \"automatic_retry\": false,\n  \"error\": null,\n  \"install_state_worker_requested\": true,\n  \"nonce\": \"3d4d2496058c6c7cb4e520d15505b38d\",\n  \"ok\": true,\n  \"old_v2_helper_called\": false,\n  \"owned_after\": {\n    \"cpu.max\": \"100000 100000\",\n    \"device\": 30,\n    \"inode\": 35963113,\n    \"memory.current\": \"390144000\",\n    \"memory.events\": \"low 0\\nhigh 0\\nmax 0\\noom 0\\noom_kill 0\\noom_group_kill 0\\nsock_throttled 0\",\n    \"memory.max\": \"536870912\",\n    \"memory.peak\": \"465670144\",\n    \"memory.swap.current\": \"0\",\n    \"memory.swap.max\": \"0\",\n    \"memory.swap.peak\": \"0\",\n    \"path\": \"/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-1a1b31ad6e2-fc05-80a1.service\",\n    \"pids.max\": \"128\"\n  },\n  \"owned_before\": {\n    \"cpu.max\": \"100000 100000\",\n    \"device\": 30,\n    \"inode\": 35963113,\n    \"memory.current\": \"32509952\",\n    \"memory.events\": \"low 0\\nhigh 0\\nmax 0\\noom 0\\noom_kill 0\\noom_group_kill 0\\nsock_throttled 0\",\n    \"memory.max\": \"536870912\",\n    \"memory.peak\": \"33038336\",\n    \"memory.swap.current\": \"0\",\n    \"memory.swap.max\": \"0\",\n    \"memory.swap.peak\": \"0\",\n    \"path\": \"/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-1a1b31ad6e2-fc05-80a1.service\",\n    \"pids.max\": \"128\"\n  },\n  \"owned_package_retained_for_separate_UI_admission\": true,\n  \"owned_package_uid\": 10163,\n  \"package\": \"org.droidloom.qa.united.r1\",\n  \"schema\": 1,\n  \"secondary_errors\": [],\n  \"source_and_artifact_unchanged\": true,\n  \"source_manifest_sha256\": \"9d4a034ad49e1412e2554f179100771eb4508b1b703e339fe2f2d00cbadfaef6\",\n  \"state_wire_sha256\": \"549e6763e53fd26acab04fedd3fede890d9e4981e91e759a316c827419896b71\",\n  \"target_package\": \"com.united.mobile.android\",\n  \"whole_app_production_ready\": false,\n  \"worker_result\": {\n    \"bytes\": 16495,\n    \"path\": \"/home/alex/work/pocket4-owned-united-qa-r1-install-state-01/worker/result.json\",\n    \"sha256\": \"4b00d7f66902fbcd933599ca5e7d85fa6369833e2feb0b594f9ab395eee6e858\"\n  },\n  \"worker_root\": \"/home/alex/work/pocket4-owned-united-qa-r1-install-state-01/worker\"\n}\n","terminal":"{\n  \"at_unix_ms\": 1794006247490,\n  \"audit_recorded\": true,\n  \"automatic_retry\": false,\n  \"cancelled\": false,\n  \"exit_code\": 0,\n  \"job_id\": \"1a1b31ad6e2-fc05-80a1\",\n  \"launch_nonce\": \"ba3b9caf983eec069113b7f47d57c69a\",\n  \"log_bytes\": {\n    \"stderr\": {\n      \"seen\": 0,\n      \"stored\": 0\n    },\n    \"stdout\": {\n      \"seen\": 682,\n      \"stored\": 682\n    }\n  },\n  \"log_errors\": {\n    \"stderr\": null,\n    \"stdout\": null\n  },\n  \"log_synced\": {\n    \"stderr\": true,\n    \"stdout\": true\n  },\n  \"log_truncated\": {\n    \"stderr\": false,\n    \"stdout\": false\n  },\n  \"output_complete\": true,\n  \"output_durable\": true,\n  \"state\": \"succeeded\",\n  \"terminal_publication_confirmed\": true,\n  \"terminal_publication_protocol\": 1,\n  \"timed_out\": false\n}"}
AUTHORITY_PINS={"coordinator":{"bytes":4469,"sha256":"341ee027b4c9767fa3b0dab127444d526be6291f4f2fd38da89d98ab3a1fca0f"},"terminal":{"bytes":729,"sha256":"0b02dcce3efd992d951b3733035978660cf03cbce0575df2639fb60dbfec67d2"}}
JOB='1a1b31ad6e2-fc05-80a1'
def need(ok,code):
    if not ok:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()

def read_exact_file(path,limit,pin=None,expected_identity=None):
    path=str(path)
    need(path.startswith('/') and not path.startswith('//') and '\0' not in path and
         all(x not in ('','.','..') for x in path[1:].split('/')),'EXACT_FILE_PATH_GRAMMAR')
    fds=[]
    first=None
    errors=[]
    deadline=time.monotonic()+10
    try:
        directory=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
        fds.append(directory)
        parts=path[1:].split('/')
        for component in parts[:-1]:
            need(time.monotonic()<deadline,'FIXED_FILE_DEADLINE')
            directory=os.open(component,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                              dir_fd=directory)
            fds.append(directory)
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
        fds.append(fd)
        before=os.fstat(fd)
        keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
             0<=before.st_size<=limit,'FIXED_REGULAR_FILE_BOUND')
        if expected_identity is not None:
            actual={k:getattr(before,v) for k,v in {
                'device':'st_dev','inode':'st_ino','mode':'st_mode','uid':'st_uid',
                'gid':'st_gid','nlink':'st_nlink','bytes':'st_size',
                'mtime_ns':'st_mtime_ns','ctime_ns':'st_ctime_ns'}.items()}
            need(type(expected_identity) is dict and actual==expected_identity,
                 'FIXED_ACTUAL_INPUT_IDENTITY_CHANGED')
        chunks=[]
        count=0
        while True:
            need(time.monotonic()<deadline,'FIXED_FILE_DEADLINE')
            part=os.read(fd,min(65536,limit+1-count))
            if not part:
                break
            count+=len(part)
            need(count<=limit,'FIXED_FILE_GREW')
            chunks.append(part)
        raw=b''.join(chunks)
        after=os.fstat(fd)
        named=os.stat(parts[-1],dir_fd=directory,follow_symlinks=False)
        need(len(raw)==before.st_size and
             all(getattr(x,k)==getattr(before,k) for x in (after,named) for k in keys),
             'FIXED_HELD_NAMED_FILE_CHANGED')
        if pin is not None:
            need(set(pin)=={'bytes','sha256'} and len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],
                 'FIXED_WHOLE_FILE_PIN_CHANGED')
        return raw
    except BaseException as error:
        first=error
        raise
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except BaseException as close_error:
                errors.append(type(close_error).__name__)
        if errors:
            if first is None:
                raise RuntimeError('FIXED_FILE_FD_CLOSE_FAILED')
            first.add_note('FIXED_FILE_FD_CLOSE_FAILED')

class ReadDeadline(BaseException):
    pass
def public_error(error):
    row={'type':type(error).__name__,'errno':getattr(error,'errno',None)}
    message=str(error)
    if re.fullmatch('[A-Z][A-Z0-9_]{0,159}',message):
        row['code']=message
    else:
        raw=message.encode('utf-8','replace')
        row.update(message_bytes=len(raw),message_sha256=sha(raw))
    return row

def main():
    start=time.monotonic()
    result={'schema':1,'kind':'pocket4-owned-united-install01-fixed-worker-result-read01',
        'original_job':JOB,'collection_complete':False,'first_error':None,'errors':[],
        'files':{},'read_events':[],'body_encoding':'base64-original-bytes',
        'Main_reads':0,'Android_commands':0,'namespace_entries':0,'children':0,
        'explicit_file_writes':0,'directory_scans':0,'automatic_retry':False,
        'installation_outcome_qualified':False,'runtime_qualified':False,
        'ambient_FD_equality_asserted':False,'whole_invocation_resource_observed':False,
        'standard_library_import_IO_included_in_counters':False,
        'all_requested_reads_returned_after_FD_close':False,
        'all_second_reads_identical':False,'signal_handler_restored':False}
    old_handler=None
    installed=False
    changed=False
    stage='authority'
    def fail(error):
        row={'stage':stage,**public_error(error)}
        result['errors'].append(row)
        if result['first_error'] is None:result['first_error']=row
    def check():
        need(time.monotonic()-start<20,'FIXED_COLLECTION_DEADLINE')
    try:
        need(sys.flags.isolated and sys.dont_write_bytecode,'ISOLATED_NO_BYTECODE_READER')
        need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,'ROOT_ONLY_FIXED_READ')
        for name,text in AUTHORITY_RAW.items():
            raw=text.encode('utf-8')
            need(len(raw)==AUTHORITY_PINS[name]['bytes'] and sha(raw)==AUTHORITY_PINS[name]['sha256'],
                 'FULL_ORIGINAL_AUTHORITY_PIN')
        t=json.loads(AUTHORITY_RAW['terminal'])
        need(t['job_id']==JOB and t['state']=='succeeded' and t['exit_code']==0 and
             t['output_complete'] is True and t['output_durable'] is True and
             t['terminal_publication_confirmed'] is True and
             t['timed_out'] is False and t['cancelled'] is False and t['automatic_retry'] is False and
             t['log_bytes']=={'stdout':{'seen':682,'stored':682},'stderr':{'seen':0,'stored':0}} and
             all(t['log_synced'][k] is True and t['log_truncated'][k] is False and
                 t['log_errors'][k] is None for k in ('stdout','stderr')),
             'EXACT_COMPLETE_SUCCESSFUL_TERMINAL')
        parent=json.loads(AUTHORITY_RAW['coordinator'])
        need(parent['ok'] is True and parent['error'] is None and
             parent['secondary_errors']==[] and parent['source_and_artifact_unchanged'] is True and
             parent['package']=='org.droidloom.qa.united.r1' and
             parent['target_package']=='com.united.mobile.android' and
             parent['worker_result']==FILES['worker_result'] and
             parent['worker_root']=='/home/alex/work/pocket4-owned-united-qa-r1-install-state-01/worker' and
             parent['owned_package_uid']==10163 and
             parent['owned_package_retained_for_separate_UI_admission'] is True and
             parent['install_state_worker_requested'] is True,
             'EXACT_SUCCESSFUL_WORKER_AUTHORITY')
        need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0) and
             signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'NO_AMBIENT_READER_ALARM')
        old_handler=signal.getsignal(signal.SIGALRM)
        def alarm(_number,_frame):raise ReadDeadline('FIXED_COLLECTION_DEADLINE')
        signal.signal(signal.SIGALRM,alarm)
        changed=True
        signal.setitimer(signal.ITIMER_REAL,20)
        installed=True
        first={}
        for name,spec in FILES.items():
            stage='first_'+name
            check()
            pin={'bytes':spec['bytes'],'sha256':spec['sha256']}
            raw=read_exact_file(spec['path'],spec['bytes'],pin)
            need(type(json.loads(raw)) is dict,'EXACT_JSON_REPORT_OBJECT')
            first[name]=raw
            result['files'][name]={**spec,'body_base64':base64.b64encode(raw).decode('ascii')}
            result['read_events'].append({'file':name,'pass':1,'returned_after_close':True})
        for name,spec in FILES.items():
            stage='second_'+name
            check()
            raw=read_exact_file(spec['path'],spec['bytes'],{'bytes':spec['bytes'],'sha256':spec['sha256']})
            need(raw==first[name],'SECOND_ORIGINAL_REPORT_CHANGED')
            result['read_events'].append({'file':name,'pass':2,'returned_after_close':True})
        need(len(result['read_events'])==2,'EXACT_TWO_COMPLETE_READS')
        result['all_requested_reads_returned_after_FD_close']=True
        result['all_second_reads_identical']=True
        result['collection_complete']=True
    except BaseException as error:
        fail(error)
    finally:
        if installed:
            try:signal.setitimer(signal.ITIMER_REAL,0)
            except BaseException as error:
                stage='disable_alarm'
                fail(error)
        if changed:
            try:
                signal.signal(signal.SIGALRM,old_handler)
                result['signal_handler_restored']=True
            except BaseException as error:
                stage='restore_handler'
                fail(error)
    result['elapsed_seconds']=time.monotonic()-start
    result['collection_complete']=bool(result['collection_complete'] and not result['errors'] and
        result['signal_handler_restored'] and result['elapsed_seconds']<20)
    raw=(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
    need(len(raw)<=131072,'FIXED_READER_OUTPUT_BOUND')
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0 if result['collection_complete'] else 1
raise SystemExit(main())
