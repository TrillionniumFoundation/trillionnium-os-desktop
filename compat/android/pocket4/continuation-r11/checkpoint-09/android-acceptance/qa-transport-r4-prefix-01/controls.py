#!/usr/bin/env python3
"""Execute actual old/new BoundArun; synthetic target/runner, real owned FDs.

No helper process, namespace entry, Android command, service or Main action.
The original -t rejection is retained as a negative baseline, not hidden.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import types

ROOT=Path(__file__).resolve().parent
OLD='ca3e30796961acc38737b6a9f22c3519abc9da1a7a6a384b732dd5a374a325d9'
NEW='7edecc741b8a61bea30d885ab9107666aab9407d6a6928bf799bd8efd4b4a23b'
INSTALL=['/system/bin/cmd','package','install','-R','-t','--user','0','--pkg',
         'org.droidloom.qa.bili.r1','/data/local/tmp/owned-fixture.apk']
READONLY=['/system/bin/cmd','package','list','packages','-U','--user','0','tv.danmaku.bili']


def module(path,expected,name):
    b=path.read_bytes();assert hashlib.sha256(b).hexdigest()==expected
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(b,str(path),'exec'),m.__dict__);return m


def control(m,name,args,edit=None,expected=None):
    fds=[os.open('/dev/null',os.O_RDONLY|os.O_CLOEXEC) for _ in range(7)]
    assert len(set(fds))==7 and all(fd>=3 for fd in fds)
    records=[];calls=[];guards=[];state={'entry_exits':0,'checks':0}
    class Target:
        expected={'pid':12345}
        helper_sha256=m.HELD_HELPER_SHA256
        helper_path='/owned-fixture/held-namespace-entry'
        def verify(self):
            state['checks']+=1
        @contextmanager
        def entry(self,command):
            prefix=[self.helper_path,'--parent-pid='+str(os.getpid()),'--root-fd='+str(fds[0])]
            prefix+=['--'+kind+'-fd='+str(fd) for kind,fd in zip(('mnt','pid','uts','ipc','net','cgroup'),fds[1:])]
            argv=prefix+['--']+command
            if edit is not None:argv=edit(argv,command)
            try:yield argv,tuple(fds)
            finally:state['entry_exits']+=1
    def runner(argv,**options):
        calls.append((list(argv),options))
        assert options['close_fds'] is True and options['pass_fds']==tuple(fds)
        return subprocess.CompletedProcess(argv,0,b'Success\n',b'')
    env={'PATH':'/system/bin','BOOTCLASSPATH':'/apex/owned-fixture.jar','DEX2OATBOOTCLASSPATH':'/apex/owned-fixture.jar',
         'ANDROID_ROOT':'/system','ANDROID_DATA':'/data','ANDROID_ART_ROOT':'/apex/com.android.art'}
    bound=m.BoundArun(target=Target(),environment=env,guard=lambda **kw:guards.append(kw),
        record=lambda kind,row:records.append((kind,row)),epoch_sha256=m.FRAMEWORK_EPOCH_SHA256,
        init_pid=12345,package=m.EXPECTED_PACKAGE,uid=m.EXPECTED_UID,interactive_production=True,runner=runner)
    failure=None
    try:
        try:
            value=bound(args,40)
            assert expected is None and value==b'Success\n'
        except m.TransportError as error:
            failure=str(error)
            assert expected==failure,(name,expected,failure)
        assert state['entry_exits']==1
        if expected is None:
            assert len(calls)==1 and len(guards)==2 and records[-1][0]=='verified-result'
            passed=calls[0][0]
            assert passed[-len(args):]==args and records[-1][1]['outcome_unknown'] is False
        else:
            assert len(calls)==0 and len(guards)==1 and records[-1][0]=='failure'
            assert records[-1][1]['action_attempted'] is False
            try:bound(args,40);raise AssertionError('poisoned transport replay accepted')
            except m.TransportError as error:assert str(error)=='TRANSPORT_CLOSED_AFTER_FAILURE'
        return {'name':name,'pass':True,'observed_error':failure,'runner_calls':len(calls),
                'entry_exits':state['entry_exits'],'guard_calls':len(guards),'record_kinds':[k for k,_ in records]}
    finally:
        for fd in fds:os.close(fd)
        for fd in fds:
            try:os.fstat(fd);raise AssertionError('owned fd retained')
            except OSError as e:assert e.errno==9


def insert_prefix(*parts):
    def edit(argv,command):
        n=argv.index('--');return argv[:n]+list(parts)+argv[n:]
    return edit


def replace_at(i,text):
    def edit(argv,command):
        value=list(argv);value[i]=text;return value
    return edit


def main():
    old=module(ROOT/'preimage/bound_android_transport.py',OLD,'r3_actual')
    new=module(ROOT/'source/bound_android_transport.py',NEW,'r4_actual')
    rows=[
        control(old,'old_R3_actual_install_t_rejected',INSTALL,expected='NUMERIC_PID_ENTRY_FORBIDDEN'),
        control(new,'new_R4_Android_install_t_unchanged',INSTALL),
        control(old,'old_R3_readonly_unchanged',READONLY),
        control(new,'new_R4_readonly_unchanged',READONLY),
        control(new,'new_R4_Android_literal_target_not_namespace',READONLY+['--target=owned-literal']),
        control(new,'prefix_short_t',INSTALL,insert_prefix('-t','12345'),'NUMERIC_PID_ENTRY_FORBIDDEN'),
        control(new,'prefix_long_target',INSTALL,insert_prefix('--target','12345'),'NUMERIC_PID_ENTRY_FORBIDDEN'),
        control(new,'prefix_target_equals',INSTALL,insert_prefix('--target=12345'),'NUMERIC_PID_ENTRY_FORBIDDEN'),
        control(new,'prefix_single_dash_target',INSTALL,insert_prefix('-target','12345'),'HELD_ENTRY_PREFIX_DIFFERS'),
        control(new,'prefix_attached_t',INSTALL,insert_prefix('-t12345'),'HELD_ENTRY_PREFIX_DIFFERS'),
        control(new,'prefix_wrong_parent',INSTALL,replace_at(1,'--parent-pid=1'),'HELD_ENTRY_PREFIX_DIFFERS'),
        control(new,'prefix_wrong_root_fd',INSTALL,replace_at(2,'--root-fd=987654'),'HELD_ENTRY_PREFIX_DIFFERS'),
        control(new,'separator_missing',INSTALL,lambda a,c:[x for x in a if x!='--'],'HELD_ENTRY_SEPARATOR_MISSING'),
        control(new,'separator_moved_before_authorities',INSTALL,lambda a,c:[a[0],'--']+a[1:],'HELD_ENTRY_COMMAND_SUFFIX_DIFFERS'),
        control(new,'Android_suffix_changed',INSTALL,lambda a,c:a+['unexpected'],'HELD_ENTRY_COMMAND_SUFFIX_DIFFERS'),
        control(new,'helper_path_changed',INSTALL,replace_at(0,'/usr/bin/nsenter'),'HELD_ENTRY_PREFIX_DIFFERS'),
        control(new,'duplicate_parent_option',INSTALL,insert_prefix('--parent-pid='+str(os.getpid())),'HELD_ENTRY_PREFIX_DIFFERS')
    ]
    result={'schema':1,'pass':True,'controls':rows,'original_source_sha256':OLD,'candidate_source_sha256':NEW,
        'scope':'Actual original/candidate BoundArun with synthetic target/runner callbacks and real seven owned FDs per control; no namespace/helper/device/UI executed',
        'actual_old_R3_regression_preserved':True,'all_created_FDs_closed':True,'production_or_Android_qualification':False}
    raw=(json.dumps(result,indent=2)+'\n').encode()
    fd=os.open(ROOT/'controls-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    print(json.dumps(result))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
