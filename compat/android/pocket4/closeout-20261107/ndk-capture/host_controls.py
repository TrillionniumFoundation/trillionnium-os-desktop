#!/usr/bin/env python3
"""Host-only regression of the exact NDK command seam; no namespace entry."""
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
import types

ROOT=Path(__file__).resolve().parent
ORIGINAL=ROOT/'original'
CANDIDATE=ROOT/'candidate'
LIMIT=262144

def load(path,name):
    raw=path.read_bytes()
    scope=types.ModuleType(name);scope.__file__=str(path)
    exec(compile(raw,str(path),'exec'),scope.__dict__)
    return scope

recorder=load(ORIGINAL/'R6-recorder.py','actual_R6_readonly_command_source')
assert hashlib.sha256((ORIGINAL/'R6-recorder.py').read_bytes()).hexdigest()=='c63cbdca615a609ebb41bcb25db6b770f43c4488c46a8f7b1dbee4bc462b4e64'
old=load(ORIGINAL/'fixture_context.py','original_ndk_context_controls')
new=load(CANDIDATE/'fixture_context.py','fixed_ndk_context_controls')
cases=[]
owned_fds=[]
libc=ctypes.CDLL(None,use_errno=True)
prior=ctypes.c_int()
assert libc.prctl(37,ctypes.byref(prior),0,0,0)==0
assert libc.prctl(36,1,0,0,0)==0
original_limit=resource.getrlimit(resource.RLIMIT_FSIZE)

def check(condition,message):
    if not condition:raise AssertionError(message)

def context(path):
    state={'guards':0,'poisoned':False}
    def guard(*args,**kwargs):state['guards']+=1
    def poison():state['poisoned']=True
    ctx=types.SimpleNamespace(recorder=recorder,step=path,command_index=0,
        _android_mutation=True,action_attempted=False,guard=guard,
        binding=types.SimpleNamespace(target=types.SimpleNamespace(poison_unjoined_command=poison)))
    return ctx,state

def run(name,code,timeout=2,module=new,prepare=None,assertion=None,executable=None):
    with tempfile.TemporaryDirectory(prefix='ndk-capture-control-',dir=ROOT/'host-tmp') as td:
        path=Path(td)
        ctx,state=context(path)
        if prepare:prepare(path)
        args=[sys.executable,'-I','-B','-c',code,str(path)] if executable is None else [executable]
        options={'close_fds':True,'stdout':new.subprocess.PIPE,'stderr':new.subprocess.PIPE,
                 'pass_fds':tuple(owned_fds),'timeout':timeout,
                 'env':{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}}
        before=set(os.listdir('/proc/self/fd'));limit=resource.getrlimit(resource.RLIMIT_FSIZE)
        started=time.monotonic()
        got=module.command_with_bound(ctx,args,options)
        elapsed=time.monotonic()-started
        after=set(os.listdir('/proc/self/fd'))
        check(before==after,name+': descriptor leak')
        check(resource.getrlimit(resource.RLIMIT_FSIZE)==limit,name+': parent file limit changed')
        check(got.recorder_joined and not state['poisoned'],name+': owned child unjoined')
        check(len(got.stdout)<=LIMIT and len(got.stderr)<=LIMIT,name+': returned output overflow')
        for suffix in ('stdout','stderr'):
            file=path/('command-001.'+suffix)
            if file.exists():check(file.stat().st_size<=LIMIT,name+': on-disk output overflow')
        receipt=json.loads((path/'command-001.result.json').read_bytes())
        if module is new:
            check(receipt['capture']['pipes_closed'] and receipt['capture']['files_closed'] and
                  receipt['capture']['selector_closed'],name+': capture cleanup incomplete')
            check(receipt['capture']['RLIMIT_FSIZE_before']==list(limit)==
                  receipt['capture']['RLIMIT_FSIZE_after'],name+': file limit evidence mismatch')
        check(elapsed<timeout+2,name+': cleanup exceeded host control bound')
        if assertion:assertion(got,receipt,path,state)
        row={'name':name,'passed':True,'returncode':got.returncode,
             'stdout_bytes':len(got.stdout),'stderr_bytes':len(got.stderr),
             'owned_command_joined':got.recorder_joined,'parent_RLIMIT_FSIZE_unchanged':True,
             'capture_FDs_closed':True,'seconds':elapsed}
        if module is new:row['capture']=receipt['capture']
        cases.append(row)
        return got,receipt

try:
    (ROOT/'host-tmp').mkdir(mode=0o700,exist_ok=True)
    for _ in range(7):owned_fds.append(os.open('/dev/null',os.O_RDONLY|os.O_CLOEXEC))
    run('binary_stdout_and_stderr', "import os;os.write(1,b'hello\\x00world');os.write(2,b'error\\xff')",
        assertion=lambda r,j,p,s:check(r.returncode==0 and r.stdout==b'hello\x00world' and
            r.stderr==b'error\xff' and not r.recorder_errors and j['capture']['complete'],'binary preservation'))
    run('exact_independent_output_bounds',
        "import os;os.write(1,b'a'*262144);os.write(2,b'b'*262144)",
        assertion=lambda r,j,p,s:check(r.returncode==0 and r.stdout==b'a'*LIMIT and
            r.stderr==b'b'*LIMIT and not r.recorder_errors and j['capture']['complete'],'exact bounds'))
    for stream,fd in [('stdout',1),('stderr',2)]:
        run('one_byte_'+stream+'_overflow',
            "import os;os.write("+str(fd)+",b'x'*262145)",
            assertion=lambda r,j,p,s,stream=stream:check(
                j['capture']['overflow_streams']==[stream] and
                j['capture']['retained_bytes'][stream]==LIMIT and r.recorder_errors and
                not j['capture']['complete'],'overflow must fail closed'))
    run('unbounded_output_stopped_and_joined',
        "import os\nwhile True:os.write(1,b'x'*8192)",
        assertion=lambda r,j,p,s:check(r.returncode<0 and j['capture']['owned_group_stopped'] and
            j['capture']['overflow_streams']==['stdout'],'continuous output stop'))
    # A private subject file is larger than the entire output budget. The old
    # seam changes the child limit; this fork/wait wrapper uses the real helper's
    # exit-vs-signal mapping without entering any Android namespace.
    writes="""import os,signal,sys,resource
child=os.fork()
if child==0:
 signal.signal(signal.SIGXFSZ,signal.SIG_DFL)
 with open(sys.argv[1]+'/subject.data','wb',buffering=0) as stream:
  data=b'z'*524289
  while data:
   count=stream.write(data)
   data=data[count:]
 os._exit(0)
_,status=os.waitpid(child,0)
sig=status&0x7f
os._exit(((status>>8)&255) if sig==0 else 128+sig)
"""
    run('original_seam_host_fixture_reproduces153',writes,module=old,
        assertion=lambda r,j,p,s:check(r.returncode==153 and not r.stdout and not r.stderr and
            (p/'subject.data').stat().st_size==LIMIT,'original inherited FSIZE fixture'))
    run('subject_regular_file_exceeds_output_budget',writes,
        assertion=lambda r,j,p,s:check(r.returncode==0 and not r.recorder_errors and
            (p/'subject.data').stat().st_size==524289,'subject file must not inherit output cap'))
    run('child_inherits_original_file_limit',
        "import resource,json;print(json.dumps(resource.getrlimit(resource.RLIMIT_FSIZE)))",
        assertion=lambda r,j,p,s:check(json.loads(r.stdout)==list(original_limit),'child ambient limit'))
    run('silent_command_timeout',
        "import time;time.sleep(30)",timeout=0.12,
        assertion=lambda r,j,p,s:check(r.host_timed_out and r.returncode==-signal.SIGKILL and
            j['capture']['owned_group_stopped'],'silent timeout cleanup'))
    run('closed_pipes_running_child_timeout',
        "import os,time;os.close(1);os.close(2);time.sleep(30)",timeout=0.12,
        assertion=lambda r,j,p,s:check(r.host_timed_out and r.returncode==-signal.SIGKILL and
            all(j['capture']['pipe_eof'].values()),'post-EOF timeout cleanup'))
    def descendant_check(r,j,p,state):
        child=int(r.stdout.strip());end=time.monotonic()+1
        while time.monotonic()<end:
            waited,status=os.waitpid(child,os.WNOHANG)
            if waited:
                check(os.WIFSIGNALED(status) and os.WTERMSIG(status)==signal.SIGKILL,
                      'descendant did not terminate from owned group stop')
                break
            time.sleep(0.01)
        else:
            os.kill(child,signal.SIGKILL);os.waitpid(child,0)
            raise AssertionError('owned descendant leaked')
        check(r.host_timed_out and j['capture']['owned_group_stopped'],'retained-pipe timeout cleanup')
    run('exited_leader_descendant_pipe_timeout',
        "import os,time\npid=os.fork()\nif pid==0:time.sleep(30);os._exit(0)\nos.write(1,str(pid).encode());os._exit(0)",
        timeout=0.15,assertion=descendant_check)
    run('spawn_failure_closes_all_outputs',"",executable='/definitely-not-an-ndk-capture-program',
        assertion=lambda r,j,p,s:check(not r.recorder_spawned and r.returncode is None and
            r.recorder_errors[0]['phase']=='command_spawn','spawn failure evidence'))
    run('partial_output_open_does_not_spawn',"raise RuntimeError('must not execute')",
        prepare=lambda p:(p/'command-001.stderr').write_bytes(b'owned-existing'),
        assertion=lambda r,j,p,s:check(not r.recorder_spawned and not s['poisoned'] and
            (p/'command-001.stderr').read_bytes()==b'owned-existing' and
            r.recorder_errors[0]['phase']=='command_output_open','output-open failure evidence'))
    selector_factory=new.selectors.DefaultSelector
    def interrupted_selector():
        sel=selector_factory()
        def interrupted(*args,**kwargs):raise KeyboardInterrupt('fixed owned host control')
        sel.select=interrupted
        return sel
    new.selectors.DefaultSelector=interrupted_selector
    try:
        run('capture_interruption_stops_and_joins',"import time;time.sleep(30)",
            assertion=lambda r,j,p,s:check(r.returncode==-signal.SIGKILL and
                r.recorder_errors[0]['exception_type']=='KeyboardInterrupt' and
                j['capture']['owned_group_stopped'],'interruption cleanup'))
    finally:
        new.selectors.DefaultSelector=selector_factory
    check(len(cases)==14,'exact control count')
    report={'schema':1,'kind':'pocket4-ndk-pipe-capture-host-controls-r2',
        'state':'PASS','passed':len(cases),'cases':cases,'errors':[],
        'subject_file_limit_changed':False,
        'original_153_cause_reclassified':False,
        'original_signal_cause_remains_unknown':True,
        'Main_reads':0,'Android_commands':0,'namespace_entries':0,
        'original_R6_shared_source_changed':False,'runtime_qualified':False}
finally:
    for fd in owned_fds:os.close(fd)
    check(resource.getrlimit(resource.RLIMIT_FSIZE)==original_limit,'final parent file limit')
    assert libc.prctl(36,prior.value,0,0,0)==0
raw=(json.dumps(report,indent=2)+'\n').encode()
fd=os.open(ROOT/'host-controls-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps({'state':'PASS','passed':report['passed'],'result':str(ROOT/'host-controls-result.json'),
    'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'Main_reads':0,'Android_commands':0}),flush=True)
