"""Fixed compiler dependency canonical metadata; only pinned .d bytes are read."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import time

DEPENDENCIES = Path('/home/alex/work/pocket4-marriott-proc-readlink-outer-tu-02-20261106/proc_self_maps_test.cc.preflight.d')
DEP_BYTES = 134340
DEP_SHA = '32c3ccb0b85e0263d3e90626864512eb606f00fe708eaf29163687d9b5d5c4c7'
EXPECTED_TARGET = 'proc_self_maps_test.cc'
EXPECTED_COUNT = 793
AOSP = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
ROOTS = (
    Path('/home/alex/work/pocket4-marriott-proc-readlink-outer-tu-02-20261106/source'),
    AOSP/'prebuilts/clang/host/linux-x86/clang-r584948b/include/c++/v1',
    AOSP/'prebuilts/clang/host/linux-x86/clang-r584948b/lib/clang/22/include',
    AOSP/'bionic/libc/include',
    AOSP/'bionic/libc/kernel',
    AOSP/'external/googletest/googletest/include',
    AOSP/'libnativehelper/include_jni',
)
START = time.monotonic()
DEADLINE = START + 8.0
EVENTS = []
CLOSE_ERRORS = []
LIVE = {}
FIRST_CODES = {
    'ORDINARY_OPERATOR_REQUIRED','READ_BUDGET_EXHAUSTED','FIXED_PATH',
    'INPUT_FD_BOUND','DEPENDENCY_INPUT_SHAPE','DEPENDENCY_INPUT_PIN',
    'DEPENDENCY_INPUT_CHANGED','DEPENDENCY_TARGET','DEPENDENCY_COUNT',
    'DEPENDENCY_NAME_BOUND','DEPENDENCY_NAMED_ROOT','ROOT_DIRECTORY',
    'CANONICAL_METADATA_CHANGED','NAMED_DEPENDENCY_CHANGED',
    'FD_CLOSE_FAILURE','OUTPUT_BOUND',
}
class BudgetExpired(BaseException):
    pass
def need(value, code):
    if not value:
        raise RuntimeError(code)
def tick():
    if time.monotonic() >= DEADLINE:
        raise BudgetExpired()
def digest(raw):
    return hashlib.sha256(raw).hexdigest()
def canon(value):
    return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()
def error_record(error, stage):
    code = str(error) if type(error) is RuntimeError and str(error) in FIRST_CODES else 'METADATA_OPERATION_FAILED'
    if isinstance(error,BudgetExpired):
        code = 'READ_BUDGET_EXHAUSTED'
    result = {'stage':stage,'type':type(error).__name__,'code':code}
    number = getattr(error,'errno',None)
    if type(number) is int:
        result['errno'] = number
    return result
def take(fd, role):
    row = {'fd':fd,'role':role,'close_attempted':False,'closed':False}
    EVENTS.append(row)
    LIVE[fd] = row
    need(len(EVENTS) <= 128, 'INPUT_FD_BOUND')
    return fd
def drop(fd):
    row = LIVE.pop(fd)
    row['close_attempted'] = True
    try:
        os.close(fd)
        row['closed'] = True
    except BaseException as error:
        CLOSE_ERRORS.append(error_record(error,'owned_FD_close'))
        raise
def open_fixed():
    """Open only the already observed .d, no symlink components or new paths."""
    need(DEPENDENCIES.is_absolute() and all(p not in ('.','..','') for p in DEPENDENCIES.parts[1:]), 'FIXED_PATH')
    acquired = []
    first = None
    answer = None
    try:
        tick()
        current = take(os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC),'fixed_parent')
        acquired.append(current)
        for part in DEPENDENCIES.parts[1:-1]:
            tick()
            following = take(os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current),'fixed_parent')
            acquired.append(following)
            acquired.remove(current)
            drop(current)
            current = following
        tick()
        answer = take(os.open(DEPENDENCIES.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current),'pinned_dependency_file')
        acquired.append(answer)
        acquired.remove(current)
        drop(current)
        acquired.remove(answer)
        return answer
    except BaseException as error:
        first = error
        raise
    finally:
        for fd in reversed(acquired):
            try:
                drop(fd)
            except BaseException as close_error:
                if first is not None:
                    first.add_note('owned acquisition close failure')
                else:
                    raise
def metadata(st):
    return {'device':st.st_dev,'inode':st.st_ino,'mode':st.st_mode,
            'uid':st.st_uid,'gid':st.st_gid,'nlink':st.st_nlink,
            'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'ctime_ns':st.st_ctime_ns}
def shape(st):
    if stat.S_ISREG(st.st_mode):
        return 'regular'
    if stat.S_ISDIR(st.st_mode):
        return 'directory'
    if stat.S_ISLNK(st.st_mode):
        return 'symlink'
    return 'other'
def read_dep(fd):
    tick()
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==DEP_BYTES,'DEPENDENCY_INPUT_SHAPE')
    os.lseek(fd,0,os.SEEK_SET)
    pieces = []
    used = 0
    while True:
        tick()
        piece = os.read(fd,min(16384,DEP_BYTES+1-used))
        if not piece:
            break
        pieces.append(piece)
        used += len(piece)
        need(used<=DEP_BYTES,'DEPENDENCY_INPUT_SHAPE')
    raw = b''.join(pieces)
    after = os.fstat(fd)
    need(metadata(before)==metadata(after),'DEPENDENCY_INPUT_CHANGED')
    need(len(raw)==DEP_BYTES and digest(raw)==DEP_SHA,'DEPENDENCY_INPUT_PIN')
    return raw, metadata(after)
def within(path, roots):
    return any(path==root or path.is_relative_to(root) for root in roots)
def canonical_metadata(name):
    """Path resolution/stat only; this function never opens or reads a leaf."""
    path = Path(name)
    need(path.is_absolute() and len(str(path).encode())<=4096,'DEPENDENCY_NAME_BOUND')
    tick()
    named_before = path.lstat()
    tick()
    resolved = path.resolve(strict=True)
    need(len(str(resolved).encode())<=4096,'DEPENDENCY_NAME_BOUND')
    tick()
    target_before = resolved.lstat()
    tick()
    named_after = path.lstat()
    resolved_after = path.resolve(strict=True)
    tick()
    target_after = resolved.lstat()
    need(metadata(named_before)==metadata(named_after) and resolved==resolved_after and
         metadata(target_before)==metadata(target_after),'CANONICAL_METADATA_CHANGED')
    return {'named':str(path),'resolved':str(resolved),
            'named_type':shape(named_after),'resolved_type':shape(target_after),
            'named_metadata':metadata(named_after),'resolved_metadata':metadata(target_after)}
def parse_names(raw):
    text = raw.decode('utf-8','strict').replace('\\\n',' ')
    need(': ' in text,'DEPENDENCY_TARGET')
    target,payload = text.split(': ',1)
    need(target.strip()==EXPECTED_TARGET,'DEPENDENCY_TARGET')
    names = shlex.split(payload)
    need(len(names)==EXPECTED_COUNT and len(names)==len(set(names)) and len(names)<=2048,'DEPENDENCY_COUNT')
    for name in names:
        need(Path(name).is_absolute() and len(name.encode())<=4096,'DEPENDENCY_NAME_BOUND')
        need(within(Path(name),ROOTS),'DEPENDENCY_NAMED_ROOT')
    return names
def main():
    result = {'schema':1,'kind':'marriott-fixed-dependency-canonical-metadata01',
        'collection_complete':False,'first_error':None,'secondary_errors':[],
        'authority':{'path':str(DEPENDENCIES),'bytes':DEP_BYTES,'sha256':DEP_SHA,
                     'build_job':'1a1b0f08513-fc05-7433',
                     'build_result_sha256':'6f0241de61c3dd47839268494eefdf38dc72f08a982bf441c683fae526a5cc10'},
        'root_count':7,'expected_dependency_count':EXPECTED_COUNT,'roots':[],
        'dependencies_checked':0,'first_rejection':None,
        'no_rejection_is_not_original_failure_disproof':True,
        'metadata_rechecked':False,'pinned_d_two_full_reads':False,
        'leaf_body_reads':0,'only_file_body_read':'exact pinned .preflight.d twice',
        'directory_enumerations':0,'child_processes':0,'Main_access':False,
        'Android_actions':0,'files_written':0,'tool_executed':False,
        'new_dependency_root_authorized':False,'build_retry_created':False,
        'observation_budget_seconds':8}
    fd = None
    proof = []
    completed = False
    stage = 'operator'
    try:
        need(os.getuid()==os.geteuid()==1000,'ORDINARY_OPERATOR_REQUIRED')
        stage = 'pinned_dependency_open'
        fd = open_fixed()
        stage = 'pinned_dependency_read'
        raw,input_before = read_dep(fd)
        result['dependency_file_before'] = input_before
        stage = 'dependency_names'
        names = parse_names(raw)
        result['dependency_names_sha256'] = digest(canon(names))
        stage = 'canonical_roots'
        for root in ROOTS:
            row = canonical_metadata(root)
            need(row['resolved_type']=='directory','ROOT_DIRECTORY')
            result['roots'].append(row)
        canonical_roots = tuple(Path(row['resolved']) for row in result['roots'])
        stage = 'canonical_dependency_prefix'
        for index,name in enumerate(names):
            row = canonical_metadata(name)
            row['index'] = index
            row['allowed_by_original_textual_roots'] = within(Path(row['resolved']),ROOTS)
            row['within_canonical_roots_diagnostic_only'] = within(Path(row['resolved']),canonical_roots)
            proof.append(row)
            result['dependencies_checked'] = len(proof)
            if not row['allowed_by_original_textual_roots']:
                result['first_rejection'] = {'reason':'fixed source/dependency root escaped',**row}
                break
        result['checked_prefix_metadata_sha256'] = digest(canon(proof))
        stage = 'canonical_metadata_after'
        for old in result['roots']:
            need(canonical_metadata(old['named'])==old,'CANONICAL_METADATA_CHANGED')
        for old in proof:
            current = canonical_metadata(old['named'])
            wanted = {k:v for k,v in old.items() if k not in
                      ('index','allowed_by_original_textual_roots','within_canonical_roots_diagnostic_only')}
            need(current==wanted,'CANONICAL_METADATA_CHANGED')
        result['metadata_rechecked'] = True
        stage = 'pinned_dependency_second_read'
        second,input_after = read_dep(fd)
        need(second==raw and input_after==input_before,'DEPENDENCY_INPUT_CHANGED')
        result['dependency_file_after'] = input_after
        result['pinned_d_two_full_reads'] = True
        stage = 'named_dependency_final'
        named_fd = open_fixed()
        try:
            tick()
            need(metadata(os.fstat(named_fd))==input_before,'NAMED_DEPENDENCY_CHANGED')
        finally:
            drop(named_fd)
        tick()
        completed = True
    except BaseException as error:
        result['first_error'] = error_record(error,stage)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        for owned_fd in list(LIVE):
            try:
                drop(owned_fd)
            except BaseException as error:
                record = error_record(error,'final_owned_FD_close')
                if result['first_error'] is None:
                    result['first_error'] = record
                else:
                    result['secondary_errors'].append(record)
    result['FD_events'] = EVENTS
    result['FD_close_errors'] = CLOSE_ERRORS
    result['all_owned_FDs_closed'] = not LIVE and not CLOSE_ERRORS and all(row['closed'] for row in EVENTS)
    result['collection_complete'] = bool(completed and result['first_error'] is None and
        not result['secondary_errors'] and result['all_owned_FDs_closed'])
    result['elapsed_seconds'] = time.monotonic()-START
    encoded = canon(result)
    need(len(encoded)<=65536,'OUTPUT_BOUND')
    print(encoded.decode(),end='',flush=True)
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
