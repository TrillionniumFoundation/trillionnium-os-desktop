"""Read three fixed public Android libc++ configuration inputs; no execution."""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import time

AOSP = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
INPUTS = (
    ('sdk_stl_selection', 'build/soong/cc/stl.go', 32768),
    ('target_header_selection', 'prebuilts/clang/host/linux-x86/soong/clangprebuilts.go', 65536),
    ('arm64_ndk_config', 'prebuilts/clang/host/linux-x86/clang-r584948b/android_libc++/ndk/aarch64/include/c++/v1/__config_site', 8192),
)
SOURCE_TOTAL_MAX = 98304
OUTPUT_MAX = 262144
START = time.monotonic()
DEADLINE = START + 8.0
EVENTS = []
CLOSE_ERRORS = []
LIVE = {}
CODES = {
    'ORDINARY_OPERATOR_REQUIRED', 'FIXED_SOURCE_PATH', 'INPUT_FD_BOUND',
    'REGULAR_SINGLE_LINK_SOURCE_REQUIRED', 'SOURCE_BYTES_BOUND',
    'SOURCE_CHANGED', 'SOURCE_TOTAL_BOUND', 'SOURCE_SECOND_READ_DIFFERS',
    'SOURCE_NAMED_IDENTITY_DIFFERS', 'OUTPUT_BOUND',
}
class BudgetExpired(BaseException):
    pass
def need(value, code):
    if not value:
        raise RuntimeError(code)
def tick():
    if time.monotonic() >= DEADLINE:
        raise BudgetExpired()
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def encode(value):
    return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()
def failure(error, stage):
    code = str(error) if type(error) is RuntimeError and str(error) in CODES else 'FIXED_SOURCE_OPERATION_FAILED'
    if isinstance(error,BudgetExpired):
        code = 'READ_BUDGET_EXHAUSTED'
    row = {'stage':stage,'type':type(error).__name__,'code':code}
    number = getattr(error,'errno',None)
    if type(number) is int:
        row['errno'] = number
    return row
def metadata(st):
    return {'device':st.st_dev,'inode':st.st_ino,'mode':st.st_mode,
            'uid':st.st_uid,'gid':st.st_gid,'nlink':st.st_nlink,
            'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'ctime_ns':st.st_ctime_ns}
def take(fd,role):
    row = {'fd':fd,'role':role,'close_attempted':False,'closed':False}
    EVENTS.append(row)
    LIVE[fd] = row
    need(len(EVENTS)<=256,'INPUT_FD_BOUND')
    return fd
def drop(fd):
    row = LIVE.pop(fd)
    row['close_attempted'] = True
    try:
        os.close(fd)
        row['closed'] = True
    except BaseException as error:
        CLOSE_ERRORS.append(failure(error,'owned_FD_close'))
        raise
def open_source(path,role):
    need(path.is_absolute() and path in tuple(AOSP/relative for _,relative,_ in INPUTS) and
         all(part not in ('','.','..') for part in path.parts[1:]),'FIXED_SOURCE_PATH')
    acquired = []
    first = None
    try:
        tick()
        current = take(os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC),role+':parent')
        acquired.append(current)
        for part in path.parts[1:-1]:
            tick()
            following = take(os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current),role+':parent')
            acquired.append(following)
            acquired.remove(current)
            drop(current)
            current = following
        tick()
        leaf = take(os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current),role+':leaf')
        acquired.append(leaf)
        acquired.remove(current)
        drop(current)
        acquired.remove(leaf)
        return leaf
    except BaseException as error:
        first = error
        raise
    finally:
        for fd in reversed(acquired):
            try:
                drop(fd)
            except BaseException:
                if first is not None:
                    first.add_note('owned acquisition close failure')
                else:
                    raise
def read_source(fd,maximum,observations):
    tick()
    before = os.fstat(fd)
    observed = {'before':metadata(before)}
    observations.append(observed)
    need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'REGULAR_SINGLE_LINK_SOURCE_REQUIRED')
    need(0<before.st_size<=maximum,'SOURCE_BYTES_BOUND')
    os.lseek(fd,0,os.SEEK_SET)
    chunks = []
    used = 0
    while True:
        tick()
        chunk = os.read(fd,min(16384,maximum+1-used))
        if not chunk:
            break
        chunks.append(chunk)
        used += len(chunk)
        need(used<=maximum,'SOURCE_BYTES_BOUND')
    raw = b''.join(chunks)
    after = os.fstat(fd)
    observed['after'] = metadata(after)
    need(metadata(before)==metadata(after) and len(raw)==after.st_size,'SOURCE_CHANGED')
    text = raw.decode('utf-8','strict')
    return raw,text,metadata(after)
def main():
    result = {'schema':1,'kind':'marriott-arm64-ndk-libcxx-fixed-config-read01',
        'collection_complete':False,'first_error':None,'secondary_errors':[],
        'authority':{
            'aosp_root':str(AOSP),
            'canonical_job':'1a1b1019282-fc05-74d4',
            'canonical_stdout_sha256':'be381038a62eeb2995aac02d48ad473f37b9f92a6d2aa34ffd9ae6c7b7d2402b',
            'compile02_job':'1a1b0f08513-fc05-7433',
            'compile02_result_sha256':'6f0241de61c3dd47839268494eefdf38dc72f08a982bf441c683fae526a5cc10',
            'actual_apk_bp_bytes':2027,
            'actual_apk_bp_sha256':'e7b5ca968da9969df0e8fa3d60d225342e7a7adb58f44abb57ab87254a4b1295',
        },
        'sources':[],'all_source_pins_first_observed':True,
        'fixed_file_count':3,'source_total_bytes':0,'source_total_max':SOURCE_TOTAL_MAX,
        'source_body_reads':0,'input_path_fallbacks':0,'directory_enumerations':0,
        'child_processes':0,'Main_access':False,'Android_actions':0,'files_written':0,
        'new_dependency_root_authorized':False,'build_retry_created':False,
        'tool_executed':False,'Android_ABI_qualified':False,'observation_budget_seconds':8}
    held = []
    completed = False
    stage = 'operator'
    try:
        need(os.getuid()==os.geteuid()==1000,'ORDINARY_OPERATOR_REQUIRED')
        for role,relative,maximum in INPUTS:
            stage = role+':open'
            path = AOSP/relative
            fd = open_source(path,role)
            row = {'role':role,'path':str(path),'maximum_bytes':maximum,
                   'second_read_equal':False,'held_named_unchanged':False,'read_metadata':[]}
            result['sources'].append(row)
            stage = role+':first_full_read'
            raw,text,before = read_source(fd,maximum,row['read_metadata'])
            result['source_body_reads'] += 1
            result['source_total_bytes'] += len(raw)
            need(result['source_total_bytes']<=SOURCE_TOTAL_MAX,'SOURCE_TOTAL_BOUND')
            row.update({'bytes':len(raw),'sha256':sha(raw),'metadata_before':before,'text_utf8':text})
            held.append((fd,path,maximum,raw,before,row))
        for fd,path,maximum,original,before,row in held:
            stage = row['role']+':second_full_read'
            raw,text,after = read_source(fd,maximum,row['read_metadata'])
            result['source_body_reads'] += 1
            row['metadata_after'] = after
            need(raw==original and after==before,'SOURCE_SECOND_READ_DIFFERS')
            row['second_read_equal'] = True
        for fd,path,maximum,original,before,row in held:
            stage = row['role']+':named_final'
            named = open_source(path,row['role']+':named_final')
            try:
                tick()
                held_final = metadata(os.fstat(fd))
                named_final = metadata(os.fstat(named))
                row['held_metadata_final'] = held_final
                row['named_metadata_final'] = named_final
                need(before==held_final==named_final,'SOURCE_NAMED_IDENTITY_DIFFERS')
                row['held_named_unchanged'] = True
            finally:
                drop(named)
        tick()
        completed = True
    except BaseException as error:
        result['first_error'] = failure(error,stage)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        for fd in list(LIVE):
            try:
                drop(fd)
            except BaseException as error:
                record = failure(error,'final_owned_FD_close')
                if result['first_error'] is None:
                    result['first_error'] = record
                else:
                    result['secondary_errors'].append(record)
    result['FD_events'] = EVENTS
    result['FD_close_errors'] = CLOSE_ERRORS
    result['all_owned_FDs_closed'] = not LIVE and not CLOSE_ERRORS and all(x['closed'] for x in EVENTS)
    result['collection_complete'] = bool(completed and result['first_error'] is None and
        not result['secondary_errors'] and result['all_owned_FDs_closed'])
    result['elapsed_seconds'] = time.monotonic()-START
    raw = encode(result)
    if len(raw)>OUTPUT_MAX:
        result['collection_complete'] = False
        error = {'stage':'output','type':'RuntimeError','code':'OUTPUT_BOUND'}
        if result['first_error'] is None:
            result['first_error'] = error
        else:
            result['secondary_errors'].append(error)
        for row in result['sources']:
            row.pop('text_utf8',None)
        result['source_texts_omitted_for_output_failure'] = True
        raw = encode(result)
    need(len(raw)<=OUTPUT_MAX,'OUTPUT_BOUND')
    print(raw.decode(),end='',flush=True)
    return 0 if result['collection_complete'] else 1
def alarm_handler(signum,frame):
    raise BudgetExpired()
if __name__=='__main__':
    previous = signal.signal(signal.SIGALRM,alarm_handler)
    signal.setitimer(signal.ITIMER_REAL,8.0)
    try:
        code = main()
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)
    raise SystemExit(code)
