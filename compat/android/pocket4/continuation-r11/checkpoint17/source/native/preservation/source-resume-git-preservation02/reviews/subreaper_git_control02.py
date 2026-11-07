#!/usr/bin/env python3
"""Local owned-zombie comparison via waitid; target /proc gate is unchanged."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import time


def exited_owned(exclude=None):
    rows=[]
    while True:
        try:
            child=os.waitid(os.P_ALL,0,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        except ChildProcessError:
            break
        if child is None:
            break
        assert child.si_pid != exclude, 'fixture worker exited before its expected acknowledgment'
        row={'pid':child.si_pid,'waitid_code':child.si_code,'waitid_status':child.si_status}
        try:
            raw=Path('/proc/%d/stat' % child.si_pid).read_text()
            fields=raw[raw.rindex(')')+2:].split()
            row.update({'comm':raw[raw.index('(')+1:raw.rindex(')')],
                'state':fields[0],'parent':int(fields[1]),'starttime':int(fields[19])})
        except OSError as error:
            row['own_child_stat_error']={'errno':error.errno,'type':type(error).__name__}
        got,status=os.waitpid(child.si_pid,0)
        assert got==child.si_pid
        row['reaped_wait_status']=status
        rows.append(row)
    return rows


def no_children_left():
    try:
        child=os.waitid(os.P_ALL,0,os.WEXITED|os.WNOHANG|os.WNOWAIT)
    except ChildProcessError:
        return True
    return False


def one(git_path,fix,root):
    assert no_children_left()
    name=Path(git_path).parent.parent.name+('-fixed' if fix else '-original')
    trace_dir=root/name;trace_dir.mkdir()
    process=subprocess.Popen([sys.executable,'-I','-B',__file__,'--worker',git_path,
        'fixed' if fix else 'original',str(trace_dir)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,start_new_session=True)
    rows=[];late=[]
    try:
        while True:
            line=process.stdout.readline()
            if not line:break
            row=json.loads(line);owned=[]
            deadline=time.monotonic()+0.05
            while time.monotonic()<deadline:
                owned.extend(exited_owned(exclude=process.pid))
                time.sleep(0.005)
            row['subreaper_adopted_exited_children']=owned;rows.append(row)
            process.stdin.write('continue\n');process.stdin.flush()
        code=process.wait(timeout=5);stderr=process.stderr.read()
        assert code==0 and not stderr,(code,stderr)
        deadline=time.monotonic()+5
        while not no_children_left() and time.monotonic()<deadline:
            late.extend(exited_owned());time.sleep(0.005)
        assert no_children_left(),'an owned child is still live after the fixed local fixture bound'
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        late.extend(exited_owned())
    raw=(trace_dir/'trace.jsonl').read_bytes()
    trace=[json.loads(line) for line in raw.splitlines()]
    maintenance=[{key:row.get(key) for key in ('event','sid','child_id','pid','argv','name','code')}
        for row in trace if (row.get('event')=='child_start' and
            any(arg in ('maintenance','gc') for arg in row.get('argv',[]))) or
            (row.get('event')=='cmd_name' and row.get('name') in ('maintenance','gc'))]
    return {'git':git_path,'fixed':fix,'commands':rows,'late_reaped':late,
        'maintenance_trace_events':maintenance,
        'trace':{'path':str(trace_dir/'trace.jsonl'),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},
        'adopted_exited_child_count':sum(len(row['subreaper_adopted_exited_children']) for row in rows)+len(late),
        'all_own_children_reaped':no_children_left(),'network_calls':0}


def main():
    assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
    assert no_children_left()
    root=Path(__file__).parent/'subreaper-git-control02-actual';root.mkdir(mode=0o700)
    results=[]
    for git_path in ['/usr/bin/git','/usr/local/bin/git']:
        raw=Path(git_path).read_bytes()
        version=subprocess.run([git_path,'--version'],capture_output=True,text=True,check=True).stdout.strip()
        original=one(git_path,False,root);fixed=one(git_path,True,root)
        assert fixed['adopted_exited_child_count']==0 and not fixed['maintenance_trace_events']
        results.append({'git_version':version,'git_sha256':hashlib.sha256(raw).hexdigest(),
            'original':original,'fixed':fixed})
    print(json.dumps({'schema':1,'state':'LOCAL_GIT_SUBREAPER_WAITID_COMPARISON_COMPLETE',
        'uid':os.getuid(),'results':results,'local_children_proc_file_unavailable':True,
        'observer':'waitid P_ALL WEXITED WNOHANG WNOWAIT, then exact own-child waitpid',
        'worker_source':{'file':str(Path(__file__).with_name('subreaper_git_control01.py')),
            'sha256':hashlib.sha256(Path(__file__).with_name('subreaper_git_control01.py').read_bytes()).hexdigest()},
        'Rust_compiled_or_executed':False,'Pocket4_execution':False,
        'actual_target_PID_command_identities_proven':False,'original_compile02_FAIL_preserved':True,
        'Main_actions':0},indent=2))


if __name__=='__main__':
    if sys.argv[1:2]==['--worker']:
        original=runpy.run_path(str(Path(__file__).with_name('subreaper_git_control01.py')),
            run_name='original_fixture_worker_only')
        original['worker'](sys.argv[2],sys.argv[3]=='fixed',sys.argv[4])
    else:
        main()
