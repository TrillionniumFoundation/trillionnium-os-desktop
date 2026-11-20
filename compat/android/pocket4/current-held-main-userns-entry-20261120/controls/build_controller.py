#!/usr/bin/python3
"""Small isolated build and pure tests; never enter an Android namespace."""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import resource
import signal
import stat
import sys
import time
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
RUSTC = Path('/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/rustc')
SOURCE_SHA = '5367f5c9786b9d3795b14c51af6c6bd488782a624b9066ce84e64af7feacf792'


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def f9(s):
    return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,
            s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def read(path, limit=32*1024**2):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=f9(os.fstat(fd))
        need(stat.S_ISREG(before[2]) and before[5]==1 and before[6]<=limit,'bounded regular input')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
        need(len(raw)==before[6] and before==f9(os.fstat(fd))==f9(path.lstat()),'actual input bookend')
        return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'identity':before},raw
    finally:
        os.close(fd)


def save(path,value):
    raw=(json.dumps(value,indent=2)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
    return read(path)[0]


def main():
    need(os.getuid()==1000 and ROOT.name=='p4-guest-entry-source-20261120-runtimeaudit-r1', 'isolated exact build root')
    available=sorted(os.sched_getaffinity(0));need(20 in available and len(available)>=3,'one selected CPU with at least two reserved')
    os.sched_setaffinity(0,{20})
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    need(ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0,'owned child subreaper')
    owner_ref,owner_raw=read(ROOT/'owned_process.py')
    owner=types.ModuleType('pinned_owned_process');exec(compile(owner_raw,str(ROOT/'owned_process.py'),'exec'),owner.__dict__)
    for signum in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(signum,owner.interrupted)
    source_ref,source=read(ROOT/'held_namespace_entry.rs')
    need(source_ref['sha256']==SOURCE_SHA,'exact reviewed new source')
    compiler_ref,_=read(RUSTC)
    env={'PATH':str(RUSTC.parent)+':/usr/bin:/bin','HOME':'/home/alex','LANG':'C.UTF-8',
         'TMPDIR':str(ROOT/'tmp'),'RUST_BACKTRACE':'0'}
    (ROOT/'tmp').mkdir(mode=0o700)
    commands=[];started=time.time_ns();deadline=time.monotonic()+150
    def run(name,argv,seconds,code=0):
        need(time.monotonic()+seconds<deadline,'bounded original command start')
        output,errors=ROOT/(name+'.stdout'),ROOT/(name+'.stderr')
        before=time.time_ns()
        with output.open('xb') as out,errors.open('xb') as err:
            actual=owner.execute_child(argv,ROOT,env,out,err,seconds)
        actual.update(name=name,argv=argv,started_ns=before,finished_ns=time.time_ns(),stdout=read(output)[0],stderr=read(errors)[0])
        commands.append(actual)
        need(actual['actual_child_reaped'] is True and actual['original_pidfd_held_until_reaped'] is True
             and type(actual['exit_code']) is int and actual['exit_code']==code
             and actual['owned_descendants_remaining']==0 and actual['cleanup_errors']==[] and actual['error'] is None
             and all(not row.get('forced',False) for row in actual['retired_descendants']),
             'actual command outcome and full retirement: '+name)
        return read(output)[1],read(errors)[1]
    report={'schema':'p4-held-main-userns-entry-build-controls-v1','started_ns':started,
            'source':source_ref,'compiler':compiler_ref,'owned_process':owner_ref,
            'selected_affinity':[20],'reserved_cpus':[v for v in available if v!=20],
            'passed':False,'runtime_qualified':False,'production_ready':False,
            'Android_namespace_entries':0,'Android_commands_executed':0}
    try:
        version,stderr=run('compiler-version',[str(RUSTC),'-Vv'],5)
        need(b'release: 1.93.0\n' in version and stderr==b'','actual fixed compiler version')
        common=[str(RUSTC),'--edition=2021','-Dwarnings','-C','opt-level=2','-C','debuginfo=0']
        binary=ROOT/'held-namespace-entry'
        _,stderr=run('normal-build',common+[str(ROOT/'held_namespace_entry.rs'),'-o',str(binary)],45)
        need(stderr==b'','normal compile warnings/errors absent')
        tests=ROOT/'held-namespace-entry-tests'
        _,stderr=run('test-build',common+['--test',str(ROOT/'held_namespace_entry.rs'),'-o',str(tests)],45)
        need(stderr==b'','test compile warnings/errors absent')
        result,stderr=run('pure-tests',[str(tests),'--test-threads=1','--nocapture'],10)
        need(b'4 passed; 0 failed; 0 ignored;' in result and stderr==b'','four actual pure tests')
        _,stderr=run('real-missing-contract',[str(binary),'--','/system/bin/true'],5,125)
        need(b'exact seven FDs and complete Main comparisons required' in stderr,'real binary rejects before namespace entry')
        need(read(ROOT/'held_namespace_entry.rs')[0]==source_ref and read(RUSTC)[0]==compiler_ref
             and read(ROOT/'owned_process.py')[0]==owner_ref,'all actual build input bookends')
        report.update(passed=True,binary=read(binary)[0],test_binary=read(tests)[0],pure_tests_passed=4,
                      real_pre_namespace_rejection_controls=1,compiler_version=version.decode())
    except BaseException as failure:
        report['error']={'type':type(failure).__name__,'message':str(failure)}
    finally:
        report['final_descendant_retirement']=owner.reap_descendants()
        report['all_owned_children_retired']=owner.owned_children()==set()
        report.update(commands=commands,finished_ns=time.time_ns())
        report['passed']=report['passed'] and report['all_owned_children_retired'] and not any(x.get('forced',False) for x in report['final_descendant_retirement'])
        reference=save(ROOT/'BUILD-CONTROLS.json',report)
        print(json.dumps({'passed':report['passed'],'report':reference,'commands':len(commands),'error':report.get('error')}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
