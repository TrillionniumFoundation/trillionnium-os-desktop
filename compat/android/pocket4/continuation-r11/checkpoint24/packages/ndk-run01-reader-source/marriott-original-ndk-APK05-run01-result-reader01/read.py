"""Read only one actually bound terminal NDK run or retirement result, twice.
The unbound template has no executable request and rejects before any file read.
No Android command, Main read, namespace entry, file write, directory scan or child.
read_exact_file is unchanged from the actually qualified install02 result reader.
Collection preserves original bytes and failures; it never qualifies test runtime.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

KIND='pocket4-original-ndk-APK05-runtime-result-read01'
BINDING=json.loads("{\"schema\":1,\"phase\":\"run\",\"job\":\"1a1b31bedf5-fc05-80a3\",\"nonce\":\"def3ce316193da8b2d46ebea64db1380\",\"result\":{\"bytes\":10868,\"sha256\":\"6164de7cd4d97420ce2058846e413b93e0770fd16d9fdcc3b7b21759ef504c98\"},\"summary_raw\":\"{\\\"automatic_retry\\\":false,\\\"error\\\":{\\\"code\\\":\\\"ANDROID_COMMAND_FAILED\\\",\\\"errno\\\":null,\\\"stage\\\":\\\"original_instrumentation\\\",\\\"type\\\":\\\"TransportError\\\"},\\\"independent_retirement_completed\\\":false,\\\"installed_UID\\\":10162,\\\"instrumentation_attempted\\\":true,\\\"kind\\\":\\\"pocket4-original-ndk-runtime-worker-summary01\\\",\\\"ok\\\":false,\\\"original_NdkTests_runtime_qualified\\\":false,\\\"outcome_unknown\\\":true,\\\"phase\\\":\\\"run\\\",\\\"result\\\":{\\\"bytes\\\":10868,\\\"path\\\":\\\"/home/alex/work/pocket4-original-ndk-fixture-APK05-run-01/result.json\\\",\\\"result_file_and_parent_FDs_closed\\\":true,\\\"sha256\\\":\\\"6164de7cd4d97420ce2058846e413b93e0770fd16d9fdcc3b7b21759ef504c98\\\"},\\\"schema\\\":1}\\n\",\"summary_pin\":{\"bytes\":615,\"sha256\":\"500273f04924c42fc47a6cd7ce05c156b9ecfc878fdc73d63f31f44fee5be1e1\"},\"terminal_raw\":\"{\\n  \\\"at_unix_ms\\\": 1794006316870,\\n  \\\"audit_recorded\\\": true,\\n  \\\"automatic_retry\\\": false,\\n  \\\"cancelled\\\": false,\\n  \\\"exit_code\\\": 1,\\n  \\\"job_id\\\": \\\"1a1b31bedf5-fc05-80a3\\\",\\n  \\\"launch_nonce\\\": \\\"0c9e690cba0b374545880053ca9ca361\\\",\\n  \\\"log_bytes\\\": {\\n    \\\"stderr\\\": {\\n      \\\"seen\\\": 0,\\n      \\\"stored\\\": 0\\n    },\\n    \\\"stdout\\\": {\\n      \\\"seen\\\": 615,\\n      \\\"stored\\\": 615\\n    }\\n  },\\n  \\\"log_errors\\\": {\\n    \\\"stderr\\\": null,\\n    \\\"stdout\\\": null\\n  },\\n  \\\"log_synced\\\": {\\n    \\\"stderr\\\": true,\\n    \\\"stdout\\\": true\\n  },\\n  \\\"log_truncated\\\": {\\n    \\\"stderr\\\": false,\\n    \\\"stdout\\\": false\\n  },\\n  \\\"output_complete\\\": true,\\n  \\\"output_durable\\\": true,\\n  \\\"state\\\": \\\"failed\\\",\\n  \\\"terminal_publication_confirmed\\\": true,\\n  \\\"terminal_publication_protocol\\\": 1,\\n  \\\"timed_out\\\": false\\n}\",\"terminal_pin\":{\"bytes\":726,\"sha256\":\"405a1a61ef1aad65241dc797be40a11a89e85b562358efbc19e5e29f93fd7b52\"}}")
SOURCE_PIN={'bytes':1050,'sha256':'7ea8d117de4a6c4cbeceebc4d5d4cf56fd7f075f3cb068b8f3610be4283df582'}
PHASE_ROOTS={
    'run':'/home/alex/work/pocket4-original-ndk-fixture-APK05-run-01',
    'retire':'/home/alex/work/pocket4-original-ndk-fixture-APK05-retire-01'}
FILE_LIMITS={'result':1048576}
OUTPUT_LIMIT=2097152
WORK_SECONDS=20.0


def need(ok,code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


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
    text=str(error)
    row={'type':type(error).__name__,'errno':getattr(error,'errno',None)}
    if re.fullmatch('[A-Z][A-Z0-9_: ]{0,159}',text):
        row['code']=text
    else:
        raw=text.encode('utf-8','replace')
        row.update(message_bytes=len(raw),message_sha256=sha(raw))
    return row


def member(raw):
    return {'bytes':len(raw),'sha256':sha(raw),
            'body_base64':base64.b64encode(raw).decode('ascii')}


def main():
    need(type(BINDING) is dict and set(BINDING)=={
        'schema','phase','job','nonce','result','summary_raw','summary_pin','terminal_raw','terminal_pin'} and
        BINDING['schema']==1 and BINDING['phase'] in PHASE_ROOTS,
        'ACTUAL_RUNTIME_RESULT_BINDING_PENDING_OR_INVALID')
    phase=BINDING['phase']
    RESULT=PHASE_ROOTS[phase]+'/result.json'
    RESULT_PIN=BINDING['result']
    SUMMARY_RAW=BINDING['summary_raw']
    SUMMARY_PIN=BINDING['summary_pin']
    TERMINAL_RAW=BINDING['terminal_raw']
    TERMINAL_PIN=BINDING['terminal_pin']
    NONCE=BINDING['nonce']
    FILE_PATHS={'result':RESULT}
    need(type(RESULT_PIN) is dict and set(RESULT_PIN)=={'bytes','sha256'} and
         type(RESULT_PIN['bytes']) is int and 0<RESULT_PIN['bytes']<=FILE_LIMITS['result'] and
         type(RESULT_PIN['sha256']) is str and re.fullmatch('[0-9a-f]{64}',RESULT_PIN['sha256']) and
         type(BINDING['job']) is str and re.fullmatch('[0-9a-f]+-[0-9a-f]+-[0-9a-f]+',BINDING['job']) and
         type(NONCE) is str and re.fullmatch('[0-9a-f]{32}',NONCE) and NONCE!='0'*32 and
         type(SUMMARY_RAW) is type(TERMINAL_RAW) is str and
         0<len(SUMMARY_RAW.encode('utf-8'))<=8192 and
         0<len(TERMINAL_RAW.encode('utf-8'))<=32768,
         'EXACT_BOUNDED_RUNTIME_RESULT_AUTHORITY_REQUIRED')
    start=time.monotonic()
    deadline=start+WORK_SECONDS
    output={'schema':1,'kind':KIND,'collection_complete':False,'errors':[],
        'first_error':None,'files':{},'read_events':[],
        'all_requested_reads_returned_after_FD_close':False,
        'all_second_reads_identical':False,
        'body_encoding':'base64-original-bytes','advertised_installed_UID':10162,'phase':phase,
        'installed_UID_qualified_by_reader':False,
        'runtime_outcome_qualified_by_reader':False,'automatic_retry':False,
        'runtime_qualified':False,'Main_reads':0,'Android_commands':0,
        'namespace_entries':0,'children':0,'explicit_file_writes':0,
        'directories_scanned':0,'standard_library_import_IO_included_in_counters':False,
        'original_job':BINDING['job'],
        'requested_memory_max_bytes':134217728,'work_seconds':WORK_SECONDS,'outer_seconds':30,
        'whole_invocation_resource_observed':False,
        'ambient_FD_equality_asserted':False,'signal_handler_restored':False}
    values={}
    original_handler=None
    changed=False
    installed=False
    stage='authority'
    def fail(where,error):
        row={'stage':where,**public_error(error)}
        output['errors'].append(row)
        if output['first_error'] is None:
            output['first_error']=row
    try:
        need(sys.flags.isolated and sys.dont_write_bytecode,'ISOLATED_NO_BYTECODE_READER')
        need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,'ROOT_ONLY_FIXED_READ')
        for text,pinned in ((SUMMARY_RAW,SUMMARY_PIN),(TERMINAL_RAW,TERMINAL_PIN)):
            raw=text.encode('utf-8')
            need(len(raw)==pinned['bytes'] and sha(raw)==pinned['sha256'],
                 'ACTUAL_COMPLETE_JOB_AUTHORITY_PIN')
        summary=json.loads(SUMMARY_RAW)
        terminal=json.loads(TERMINAL_RAW)
        need(terminal.get('job_id')==output['original_job'] and
             ((terminal.get('state'),terminal.get('exit_code')) in (('succeeded',0),('failed',1))) and
             all(terminal.get(k) is True for k in (
                 'output_complete','output_durable','terminal_publication_confirmed')) and
             all(terminal.get(k) is False for k in ('timed_out','cancelled','automatic_retry')) and
             terminal.get('log_bytes')=={'stdout':{'seen':SUMMARY_PIN['bytes'],'stored':SUMMARY_PIN['bytes']},
                                        'stderr':{'seen':0,'stored':0}} and
             all(terminal['log_synced'][k] is True and terminal['log_truncated'][k] is False and
                 terminal['log_errors'][k] is None for k in ('stdout','stderr')),
             'EXACT_COMPLETE_RUNTIME_TERMINAL')
        need(summary.get('schema')==1 and
             summary.get('kind')=='pocket4-original-ndk-runtime-worker-summary01' and
             summary.get('phase')==phase and type(summary.get('ok')) is bool and
             summary.get('ok')==(terminal['exit_code']==0) and
             summary.get('automatic_retry') is False and
             type(summary.get('outcome_unknown')) is bool and
             type(summary.get('original_NdkTests_runtime_qualified')) is bool and
             summary.get('installed_UID')==output['advertised_installed_UID'] and
             summary.get('result')=={'path':RESULT,**RESULT_PIN,'result_file_and_parent_FDs_closed':True},
             'EXACT_RUNTIME_PHASE_SUMMARY')
        output['producer_ok']=summary['ok']
        output['producer_outcome_unknown']=summary['outcome_unknown']
        output['producer_runtime_claim_qualified_by_reader']=False
        need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0) and
             signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),
             'NO_AMBIENT_OR_BLOCKED_READER_ALARM')
        original_handler=signal.getsignal(signal.SIGALRM)
        def alarm(_number,_frame):
            raise ReadDeadline('FIXED_READ_DEADLINE')
        signal.signal(signal.SIGALRM,alarm)
        changed=True
        signal.setitimer(signal.ITIMER_REAL,WORK_SECONDS)
        installed=True
        stage='result'
        need(time.monotonic()<deadline,'FIXED_READ_DEADLINE')
        raw=read_exact_file(RESULT,FILE_LIMITS['result'],RESULT_PIN)
        values['result']=raw
        output['files']['result']={'path':RESULT,**member(raw)}
        output['read_events'].append({'file':'result','pass':1,'returned_after_close':True})
        report=json.loads(raw)
        need(report.get('schema')==1 and
             report.get('kind')=='pocket4-original-ndk-fixture-'+phase+'-v1' and
             report.get('entry_kind')=='pocket4-original-ndk-runtime-worker01' and
             report.get('source_manifest')==SOURCE_PIN and
             report.get('scope',{}).get('package')=='com.example.ndk_tests' and
             report.get('scope',{}).get('phase')==phase and
             report.get('scope',{}).get('attempt_nonce')==NONCE and
             report.get('scope',{}).get('uid')==output['advertised_installed_UID'] and
             report.get('ok')==summary['ok'] and report.get('error')==summary.get('error') and
             report.get('outcome_unknown')==summary['outcome_unknown'] and
             report.get('original_NdkTests_runtime_qualified')==
                 summary['original_NdkTests_runtime_qualified'] and
             report.get('automatic_retry') is False,
             'EXACT_OWN_RUNTIME_PHASE_PARENT_REQUIRED')
        # Repeat only the same known files with exact first-read whole pins.
        for label in ('result',):
            if label not in values:
                continue
            stage='second_'+label
            try:
                need(time.monotonic()<deadline,'FIXED_READ_DEADLINE')
                raw=values[label]
                second=read_exact_file(FILE_PATHS[label],FILE_LIMITS[label],
                                      {'bytes':len(raw),'sha256':sha(raw)})
                need(second==raw,'EXACT_SECOND_FILE_READ_CHANGED')
                output['read_events'].append({'file':label,'pass':2,'returned_after_close':True})
            except BaseException as error:
                fail(stage,error)
        complete=set(values)==set(FILE_PATHS) and len(output['read_events'])==2
        output['all_requested_reads_returned_after_FD_close']=complete
        output['all_second_reads_identical']=complete
        output['collection_complete']=bool(complete and not output['errors'])
    except BaseException as error:
        fail(stage,error)
    finally:
        if installed:
            try:
                signal.setitimer(signal.ITIMER_REAL,0)
            except BaseException as error:
                fail('disable_own_alarm',error)
        if changed:
            try:
                signal.signal(signal.SIGALRM,original_handler)
                output['signal_handler_restored']=True
            except BaseException as error:
                fail('restore_original_handler',error)
    output['elapsed_seconds']=time.monotonic()-start
    output['collection_complete']=bool(output['collection_complete'] and
        not output['errors'] and output['signal_handler_restored'])
    raw=(json.dumps(output,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    need(len(raw)<=OUTPUT_LIMIT,'FIXED_READER_OUTPUT_BOUND')
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0 if output['collection_complete'] else 1


if __name__=='__main__':
    raise SystemExit(main())
