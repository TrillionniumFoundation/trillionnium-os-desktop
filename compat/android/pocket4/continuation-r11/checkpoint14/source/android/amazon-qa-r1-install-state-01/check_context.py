#!/usr/bin/env python3
"""Local admission/FD controls only. Never execute a transport or Android call."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import types

HERE=Path(__file__).resolve().parent
BASE=Path('/workspace/scratch/94990735b266')
def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__)
    return m
c=load(HERE/'amazon_context.py','actual_amazon_context')
w=load(HERE/'install_state.py','actual_amazon_install')
q=load(BASE/'owned-amazon-qa-r1-build01/source/qa_contract.py','actual_amazon_qa')
reader=load(HERE/'references/read_amazon.py','actual_amazon_metadata')
rows=[]
def passed(name,**details):rows.append({'name':name,'passed':True,**details})
def reject(call,contains):
    try:call()
    except RuntimeError as error:
        assert contains in str(error),repr(error)
        return error
    raise AssertionError('expected rejection: '+contains)

plan=c.ordered_commands(q,w.SELF,w.GUEST_APK,w.STATE_NONCE)
assert len(plan)==13 and sum(x[2] for x in plan)==1
assert plan[3]==(w.INSTALL,40,True) and plan[7]==(q.instrumentation_argv(
    {'protocol':q.PROTOCOL,'nonce':w.STATE_NONCE,'op':'state'}),20,False)
assert all('/system/bin/am' not in row[0] or row==plan[7] for row in plan)
passed('production_plan_has_exact13_one_explicit_no_replace_install_one_state',transport_executed=False)

class FakeBound:
    def __init__(self,**kw):self.calls=[];self.failure=None
    def __call__(self,argv,timeout):
        self.calls.append((list(argv),timeout))
        if self.failure:raise self.failure
        return b''
def context():
    target=types.SimpleNamespace(verify=lambda:None,close=lambda:None)
    return c.Context(types.SimpleNamespace(),types.SimpleNamespace(),target,{},
        types.SimpleNamespace(BoundArun=FakeBound,FRAMEWORK_EPOCH_SHA256=q.MAIN_EPOCH),
        lambda:None,Path('/not-used'),plan,123,time.monotonic()+60)
def wrong_at(index,argv,timeout,mutation):
    x=context();x.next_command=index
    reject(lambda:x.android(argv,timeout,mutation=mutation),'ONLY_ORDERED')
    assert x.transport.calls==[] and x.poisoned and x.next_command==index and not x._android_mutation
    reject(lambda:x.android(*plan[index][:2],mutation=plan[index][2]),'CLOSED_OR_PRIVATE')
    assert x.transport.calls==[]

bad=list(w.INSTALL);bad[3]='-r';wrong_at(3,bad,40,True)
bad=list(w.INSTALL);bad.insert(4,'-g');wrong_at(3,bad,40,True)
bad=list(w.INSTALL);bad[8]='org.droidloom.qa.bili.r5';wrong_at(3,bad,40,True)
wrong_at(3,w.INSTALL,40,False)
wrong_at(0,c.PATHS,15,False)
wrong_at(7,q.instrumentation_argv({'protocol':q.PROTOCOL,'nonce':'0'*32,'op':'state'}),20,False)
passed('replace_grant_old_package_wrong_mutation_order_or_nonce_rejected_before_transport',negative_cases=6,
       original_after_rejection_cannot_retry=True,transport_executed=False)

x=context();x.next_command=3;first=OSError(9,'owned seam failure');x.transport.failure=first
try:x.android(w.INSTALL,40,mutation=True)
except OSError as error:assert error is first
else:raise AssertionError('first failure lost')
assert x.next_command==4 and x.poisoned and not x._android_mutation and len(x.transport.calls)==1
reject(lambda:x.android(*plan[4][:2],mutation=plan[4][2]),'CLOSED_OR_PRIVATE')
assert len(x.transport.calls)==1
passed('first_transport_exception_preserved_and_no_following_command',transport_is_explicit_seam=True)

x=context()
for argv,timeout,mutation in plan:x.android(argv,timeout,mutation=mutation)
reject(lambda:x.android(*plan[0][:2],mutation=False),'PLAN_EXHAUSTED')
assert len(x.transport.calls)==13 and x.next_command==13 and x.poisoned
passed('exact_plan_has_no_fourteenth_command',transport_is_explicit_seam=True)

target_failure=OSError(9,'close failure')
def failclose():raise target_failure
x=context();x.target.close=failclose
try:x.close()
except OSError as error:assert error is target_failure
else:raise AssertionError('close failure swallowed')
assert x.closed
reject(lambda:x.android(*plan[0][:2],mutation=False),'CLOSED_OR_PRIVATE')
assert x.transport.calls==[]
passed('held_target_release_failure_does_not_reopen_command_admission',target_is_explicit_seam=True)

actual_target=json.loads((HERE/'target-artifact-reference.json').read_text())
paths=[row['path'] for row in actual_target['artifacts']]
assert os.geteuid()==0,'local fixed-file fixture expects observed local root'
actual_identity=c.identity
def owner_projection(fd):
    value=actual_identity(fd)
    value['uid']=value['gid']=1000
    return value
with tempfile.TemporaryDirectory(prefix='amazon-install-context-owned-',dir=str(HERE)) as temp:
    folder=Path(temp);mapped={};expected=copy.deepcopy(actual_target)
    for index,row in enumerate(expected['artifacts']):
        p=folder/('apk-'+str(index));p.write_bytes(('owned fixture '+str(index)).encode())
        os.chmod(p,0o444);mapped[row['path']]=p
        fd=os.open(p,os.O_RDONLY)
        try:row['held_file']=owner_projection(fd)
        finally:os.close(fd)
        row['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    class Target:
        def __init__(self):self.failure_path=None
        def open_root(self,path,flags):
            if path==self.failure_path:raise FileNotFoundError(path)
            return os.open(mapped[path],flags|os.O_CLOEXEC)
    class LocalContext:
        def __init__(self):self.target=Target();self.artifacts=None;self.calls=[];self.deadline=time.monotonic()+60
        def android(self,args,timeout):
            self.calls.append(list(args))
            if args==c.LIST:return ('package:'+c.PACKAGE+' versionCode:'+str(c.VERSION)+' uid:'+str(c.UID)+'\n').encode()
            assert args==c.PATHS
            return ''.join('package:'+p+'\n' for p in paths).encode()
    ctx=LocalContext();raw_owner=copy.deepcopy(expected)
    fd=os.open(mapped[paths[0]],os.O_RDONLY)
    try:raw_owner['artifacts'][0]['held_file']=actual_identity(fd)
    finally:os.close(fd)
    a=c.ArtifactSet(ctx,raw_owner,reader)
    reject(a.before,'IDENTITY_CHANGED');a.close()
    passed('actual_local_root_owner_rejected_by_unchanged_production_uid1000_gate',real_file_io=True)
    # Local filesystem cannot map chown(1000): explicit UID/GID-only test seam.
    # All device/inode/size/mode/link/timestamps, hash reads and close are real.
    c.identity=owner_projection
    ctx=LocalContext();a=c.ArtifactSet(ctx,expected,reader)
    before=a.before();after=a.after()
    assert before==after and len(a.opened)==3
    held=list(a.opened);closed=a.close();assert closed['held_APK_FDs_closed']==3
    for fd in held:
        try:os.fstat(fd)
        except OSError as error:assert error.errno==9
        else:raise AssertionError('held fixture fd leaked')
    passed('actual_streaming_hash_and_named_path_revalidation_of_three_owned_files',
           target_open_root_and_package_output_are_explicit_seams=True,real_file_io=True)

    ctx=LocalContext();bad=copy.deepcopy(expected);bad['artifacts'][0]['sha256']='0'*64
    a=c.ArtifactSet(ctx,bad,reader)
    reject(a.before,'CONTENT_CHANGED');fds=list(a.opened)
    assert len(fds)==1
    assert a.close()['held_APK_FDs_closed']==1
    for fd in fds:
        try:os.fstat(fd)
        except OSError as error:assert error.errno==9
        else:raise AssertionError('hash rejection fd leaked')
    passed('wrong_actual_content_pin_rejects_and_partial_held_fd_closes',real_file_io=True)

    ctx=LocalContext();ctx.deadline=time.monotonic()-1
    a=c.ArtifactSet(ctx,expected,reader)
    reject(a.before,'STREAM_HASH_DEADLINE')
    assert len(a.opened)==1 and a.close()['held_APK_FDs_closed']==1
    passed('whole_worker_deadline_cannot_be_extended_by_a_new_hash_pass',real_file_io=True,
           elapsed_deadline_is_explicit_fixture=True)

    ctx=LocalContext();ctx.target.failure_path=paths[1];a=c.ArtifactSet(ctx,expected,reader)
    try:a.before()
    except FileNotFoundError:pass
    else:raise AssertionError('second open did not fail')
    fds=list(a.opened);assert len(fds)==1 and len(a.records)==1
    assert a.close()['held_APK_FDs_closed']==1
    for fd in fds:
        try:os.fstat(fd)
        except OSError as error:assert error.errno==9
        else:raise AssertionError('open failure fd leaked')
    passed('later_apk_open_failure_retains_owned_first_fd_for_exact_finally_close',real_file_io=True)

    ctx=LocalContext();a=c.ArtifactSet(ctx,expected,reader);a.before()
    fd=a.opened[0]
    # Keep the held inode unchanged while the target's namespace resolver now
    # returns another actual owned inode for that exact pathname.
    different=folder/'different';different.write_bytes(mapped[paths[0]].read_bytes())
    os.chmod(different,0o444)
    previous=mapped[paths[0]];mapped[paths[0]]=different
    reject(a.revalidate_files,'NAMED_PATH_CHANGED')
    assert c.identity(fd)==expected['artifacts'][0]['held_file'];a.close();mapped[paths[0]]=previous
    passed('same_content_different_named_inode_rejected',real_file_io=True,namespace_resolver_is_explicit_seam=True)

original=(BASE/'android-qa-r5-install-state-03/install_state.py').read_text()
new=(HERE/'install_state.py').read_text()
def functions(text):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a,b=functions(original),functions(new)
unchanged=['require','digest','read','module','error_record','remember','command','acquire_action_lock',
           'owned_resources','prepare_owned_limits','resources_qualified']
assert all(a[name]==b[name] for name in unchanged)
assert a['OwnedApk']==functions(new.replace('owned-amazon-qa.apk','owned-bili-qa.apk'))['OwnedApk']
t=(HERE/'amazon_transport.py').read_text().replace('EXPECTED_PACKAGE = "com.amazon.mShop.android.shopping"',
    'EXPECTED_PACKAGE = "tv.danmaku.bili"').replace('EXPECTED_UID = 10129','EXPECTED_UID = 10117')
assert t==(BASE/'android-qa-r5-install-state-03/r4/bound_android_transport.py').read_text()
passed('eleven_original_functions_and_owned_apk_body_preserved_two_transport_literals_only',
       original_real_flock_controls_not_rerun=True)

print(json.dumps({'schema':1,'scope':'local production-function admission and held-file controls',
    'state':'LOCAL_CONTROLS_PASS_ANDROID_UNRUN','passed':len(rows),'rows':rows,
    'actual_Android_commands':0,'namespace_or_Main_operations':0,
    'file_identity_uid_gid_projection_only':True,'real_UID1000_file_ownership_qualified':False,
    'original_chown_failure_preserved':'controls-first-owner-mapping-failure.json',
    'device_install_state_qualified':False,'whole_app_production_ready':False},sort_keys=True,indent=2))
