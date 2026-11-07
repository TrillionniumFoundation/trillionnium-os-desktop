"""Read exactly one failed fixture result and command002's three original files.
No Android command, Main read, namespace entry, file write, directory scan or child.
The original read_exact_file function is copied byte-for-byte from the exact phase.
Actual command bodies are an input to Root's private diagnostic review, not public UI.
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

KIND='pocket4-original-ndk-install01-failure-read01'
ROOT='/home/alex/work/pocket4-original-ndk-fixture-APK03-install-01'
RESULT=ROOT+'/result.json'
COMMAND=ROOT+'/steps/install-01/command-002'
RESULT_PIN={'bytes':8994,'sha256':'0c3669215137fc4b8fce1603c586a6e8d8451777a359c926a29e9b43200cf202'}
SOURCE_PIN={'bytes':1054,'sha256':'50dce3c5572a40562c1928264219173a61d92fb9f39a96be9feb956695ba8c2e'}
NONCE='e4b5a1bdac8be04ff2ea3188a6d946d6'
FILE_LIMITS={'result':1048576,'command_result':65536,'stdout':262144,'stderr':262144}
FILE_PATHS={'result':RESULT,'command_result':COMMAND+'.result.json',
            'stdout':COMMAND+'.stdout','stderr':COMMAND+'.stderr'}
OUTPUT_LIMIT=2097152
WORK_SECONDS=20.0
SUMMARY_RAW="{\"automatic_retry\":false,\"error\":{\"code\":\"ANDROID_COMMAND_FAILED\",\"errno\":null,\"stage\":\"install\",\"type\":\"TransportError\"},\"install_attempted\":true,\"installed_UID\":null,\"kind\":\"pocket4-original-ndk-install-worker-summary01\",\"ok\":false,\"original_NdkTests_runtime_qualified\":false,\"outcome_unknown\":true,\"result\":{\"bytes\":8994,\"path\":\"/home/alex/work/pocket4-original-ndk-fixture-APK03-install-01/result.json\",\"result_file_and_parent_FDs_closed\":true,\"sha256\":\"0c3669215137fc4b8fce1603c586a6e8d8451777a359c926a29e9b43200cf202\"},\"schema\":1}\n"
TERMINAL_RAW="{\n  \"at_unix_ms\": 1793995160219,\n  \"audit_recorded\": true,\n  \"automatic_retry\": false,\n  \"cancelled\": false,\n  \"exit_code\": 1,\n  \"job_id\": \"1a1b271b3a6-fc05-7e09\",\n  \"launch_nonce\": \"36287f927d3ae15b6ebafae935170b46\",\n  \"log_bytes\": {\n    \"stderr\": {\n      \"seen\": 0,\n      \"stored\": 0\n    },\n    \"stdout\": {\n      \"seen\": 537,\n      \"stored\": 537\n    }\n  },\n  \"log_errors\": {\n    \"stderr\": null,\n    \"stdout\": null\n  },\n  \"log_synced\": {\n    \"stderr\": true,\n    \"stdout\": true\n  },\n  \"log_truncated\": {\n    \"stderr\": false,\n    \"stdout\": false\n  },\n  \"output_complete\": true,\n  \"output_durable\": true,\n  \"state\": \"failed\",\n  \"terminal_publication_confirmed\": true,\n  \"terminal_publication_protocol\": 1,\n  \"timed_out\": false\n}"
SUMMARY_PIN={"bytes":537,"sha256":"0f2ad089141dd8cda896c133cd3bd3bd9e0d4b886da970e1d7412996077e7d98"}
TERMINAL_PIN={"bytes":726,"sha256":"4d69cd6cbd841e547a41c1b2f7b9cfbc7fc95f4df16a4f3bdccf09e17ae2a710"}


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
    start=time.monotonic()
    deadline=start+WORK_SECONDS
    output={'schema':1,'kind':KIND,'collection_complete':False,'errors':[],
        'first_error':None,'files':{},'read_events':[],
        'all_requested_reads_returned_after_FD_close':False,
        'all_second_reads_identical':False,'command_stream_hashes_match_record':False,
        'body_encoding':'base64-original-bytes','original_installed_UID':None,
        'install_outcome_qualified_by_reader':False,'automatic_retry':False,
        'runtime_qualified':False,'Main_reads':0,'Android_commands':0,
        'namespace_entries':0,'children':0,'explicit_file_writes':0,
        'directories_scanned':0,'standard_library_import_IO_included_in_counters':False,
        'original_failed_job':'1a1b271b3a6-fc05-7e09',
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
                 'ACTUAL_FAILED_JOB_AUTHORITY_PIN')
        summary=json.loads(SUMMARY_RAW)
        terminal=json.loads(TERMINAL_RAW)
        need(terminal.get('job_id')==output['original_failed_job'] and
             terminal.get('state')=='failed' and terminal.get('exit_code')==1 and
             all(terminal.get(k) is True for k in (
                 'output_complete','output_durable','terminal_publication_confirmed')) and
             all(terminal.get(k) is False for k in ('timed_out','cancelled','automatic_retry')) and
             terminal.get('log_bytes')=={'stdout':{'seen':537,'stored':537},
                                        'stderr':{'seen':0,'stored':0}} and
             all(terminal['log_synced'][k] is True and terminal['log_truncated'][k] is False and
                 terminal['log_errors'][k] is None for k in ('stdout','stderr')),
             'EXACT_FAILED_COMPLETE_TERMINAL')
        need(summary.get('kind')=='pocket4-original-ndk-install-worker-summary01' and
             summary.get('ok') is False and summary.get('automatic_retry') is False and
             summary.get('install_attempted') is True and summary.get('outcome_unknown') is True and
             summary.get('installed_UID') is None and
             summary.get('result')=={'path':RESULT,**RESULT_PIN,'result_file_and_parent_FDs_closed':True},
             'EXACT_FAILED_INSTALL_SUMMARY')
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
        need(report.get('kind')=='pocket4-original-ndk-fixture-install-v1' and
             report.get('entry_kind')=='pocket4-original-ndk-install-worker01' and
             report.get('source_manifest')==SOURCE_PIN and
             report.get('scope',{}).get('package')=='com.example.ndk_tests' and
             report.get('scope',{}).get('phase')=='install' and
             report.get('scope',{}).get('attempt_nonce')==NONCE and
             report.get('ok') is False and report.get('install_attempted') is True and
             report.get('outcome_unknown') is True,
             'EXACT_OWN_FAILED_INSTALL_PARENT_REQUIRED')
        # Three literal command002 files only. A missing file remains an error;
        # there is no fallback to command001, a directory enumeration, or pm retry.
        for label in ('command_result','stdout','stderr'):
            stage=label
            try:
                need(time.monotonic()<deadline,'FIXED_READ_DEADLINE')
                raw=read_exact_file(FILE_PATHS[label],FILE_LIMITS[label])
                values[label]=raw
                output['files'][label]={'path':FILE_PATHS[label],**member(raw)}
                output['read_events'].append({'file':label,'pass':1,'returned_after_close':True})
            except BaseException as error:
                fail(label,error)
        if all(label in values for label in ('command_result','stdout','stderr')):
            stage='command_stream_binding'
            record=json.loads(values['command_result'])
            need(type(record) is dict and
                 record.get('stdout_sha256')==sha(values['stdout']) and
                 record.get('stderr_sha256')==sha(values['stderr']),
                 'COMMAND002_STDIO_WHOLE_HASHES_DIFFER_FROM_OWN_RECORD')
            # A nonzero rc, timeout/error or partial output is not changed to success.
            output['command_stream_hashes_match_record']=True
        # Repeat only the same known files with exact first-read whole pins.
        for label in ('result','command_result','stdout','stderr'):
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
        complete=set(values)==set(FILE_PATHS) and len(output['read_events'])==8
        output['all_requested_reads_returned_after_FD_close']=complete
        output['all_second_reads_identical']=complete
        output['collection_complete']=bool(complete and not output['errors'] and
            output['command_stream_hashes_match_record'])
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
