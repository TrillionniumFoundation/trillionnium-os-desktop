#!/usr/bin/env python3
"""Owned local Git-fixture subreaper reproduction; no Rust or device execution."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def own_children():
    return [int(value) for value in Path('/proc/self/task/%d/children' % os.getpid()).read_text().split()]


def snapshot(pid):
    raw = Path('/proc/%d/stat' % pid).read_text()
    fields = raw[raw.rindex(')')+2:].split()
    return {'pid':pid, 'comm':raw[raw.index('(')+1:raw.rindex(')')],
            'state':fields[0], 'parent':int(fields[1]), 'starttime':int(fields[19])}


def worker(git_path, fix, root):
    root = Path(root)
    environment = {'PATH':'/usr/bin:/bin','LC_ALL':'C','GIT_CONFIG_NOSYSTEM':'1',
        'GIT_CONFIG_GLOBAL':'/dev/null','GIT_TRACE2_EVENT':str(root/'trace.jsonl')}
    extra = ['-c','maintenance.auto=false','-c','gc.auto=0'] if fix else []
    def run(label, cwd, args, expected=0):
        argv = [git_path, *extra, '-C', str(cwd), *args]
        result = subprocess.run(argv,env=environment,capture_output=True,timeout=5)
        require = result.returncode == expected
        print(json.dumps({'label':label,'argv':argv,'returncode':result.returncode,
            'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),
            'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()}),flush=True)
        assert sys.stdin.readline() == 'continue\n'
        assert require, (label,result.stderr.decode())
        return result.stdout
    origin=root/'fixture-origin';origin.mkdir()
    run('fixture-origin-init',origin,['init','--quiet','--initial-branch=main'])
    (origin/'marker').write_bytes(b'locked bytes\n')
    run('fixture-origin-add',origin,['add','marker'])
    run('fixture-origin-commit',origin,['-c','user.name=Owned source test','-c',
        'user.email=owned-source-test@droidloom.invalid','commit','--quiet','-m','fixture'])
    commit=run('fixture-origin-HEAD',origin,['rev-parse','HEAD']).decode().strip()
    checkout=root/'checkout';checkout.mkdir()
    run('fixture-checkout-init',checkout,['init','--quiet','--initial-branch=droidloom'])
    run('fixture-local-fetch',checkout,['-c','protocol.allow=never','-c','protocol.file.allow=always',
        'fetch','--quiet','--depth=1','file://'+str(origin),commit])
    run('fixture-origin-configure',checkout,['remote','add','origin',
        'https://android.googlesource.com/platform/owned-resume-control'])
    run('fixture-detached-checkout',checkout,['checkout','--quiet','--detach',commit])
    run('completed-readonly-status',checkout,['--no-optional-locks','status','--porcelain=v1','--untracked-files=all'])
    run('legacy-final-verifier-status',checkout,['status','--porcelain'])


def one(git_path, fix, root):
    assert own_children() == []
    trace_dir=root/((Path(git_path).parent.parent.name or 'root')+('-fixed' if fix else '-original'))
    trace_dir.mkdir()
    process=subprocess.Popen([sys.executable,'-I','-B',__file__,'--worker',git_path,
        'fixed' if fix else 'original',str(trace_dir)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,start_new_session=True)
    rows=[]
    try:
        while True:
            line=process.stdout.readline()
            if not line:break
            row=json.loads(line)
            observed=[pid for pid in own_children() if pid!=process.pid]
            row['subreaper_adopted_children']=[snapshot(pid) for pid in observed]
            reaped=[];deadline=time.monotonic()+5
            while any(pid in own_children() for pid in observed) and time.monotonic()<deadline:
                for pid in observed:
                    if pid not in own_children():continue
                    got,status=os.waitpid(pid,os.WNOHANG)
                    if got:reaped.append({'pid':got,'wait_status':status})
                if any(pid in own_children() for pid in observed):time.sleep(0.005)
            assert not any(pid in own_children() for pid in observed), 'owned fixture child did not retire'
            row['reaped']=reaped;rows.append(row)
            process.stdin.write('continue\n');process.stdin.flush()
        code=process.wait(timeout=5);stderr=process.stderr.read()
        assert code==0 and not stderr,(code,stderr)
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        leftovers=own_children()
        for pid in leftovers:
            got,status=os.waitpid(pid,os.WNOHANG)
            if not got:
                fd=os.pidfd_open(pid,0)
                try:signal.pidfd_send_signal(fd,signal.SIGKILL)
                finally:os.close(fd)
                os.waitpid(pid,0)
        assert not own_children()
    trace_raw=(trace_dir/'trace.jsonl').read_bytes()
    trace=[json.loads(line) for line in trace_raw.splitlines()]
    maintenance=[{key:row.get(key) for key in ('event','sid','child_id','pid','argv','name','code')}
        for row in trace if (row.get('event')=='child_start' and
            any('maintenance'==arg or 'gc'==arg for arg in row.get('argv',[]))) or
            (row.get('event')=='cmd_name' and row.get('name') in ('maintenance','gc'))]
    return {'git':git_path,'fixed':fix,'commands':rows,'maintenance_trace_events':maintenance,
        'trace':{'path':str(trace_dir/'trace.jsonl'),'bytes':len(trace_raw),'sha256':hashlib.sha256(trace_raw).hexdigest()},
        'adopted_child_count':sum(len(row['subreaper_adopted_children']) for row in rows),
        'all_own_children_reaped':not own_children(),'network_calls':0}


def main():
    assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
    assert not own_children()
    root=Path(__file__).parent/'subreaper-git-control01-actual'
    root.mkdir(mode=0o700)
    results=[]
    for git_path in ['/usr/bin/git','/usr/local/bin/git']:
        raw=Path(git_path).read_bytes()
        version=subprocess.run([git_path,'--version'],capture_output=True,text=True,check=True).stdout.strip()
        original=one(git_path,False,root)
        fixed=one(git_path,True,root)
        assert fixed['adopted_child_count']==0 and not fixed['maintenance_trace_events']
        results.append({'git_version':version,'git_sha256':hashlib.sha256(raw).hexdigest(),
                        'original':original,'fixed':fixed})
    report={'schema':1,'state':'LOCAL_OWNED_GIT_SUBREAPER_COMPARISON','uid':os.getuid(),
        'results':results,'local_controls_only':True,'Rust_compiled_or_executed':False,
        'Pocket4_execution':False,'actual_target_PID_command_identities_proven':False,
        'original_compile02_FAIL_preserved':True,'Main_actions':0}
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    if sys.argv[1:2]==['--worker']:
        worker(sys.argv[2],sys.argv[3]=='fixed',sys.argv[4])
    else:
        main()
