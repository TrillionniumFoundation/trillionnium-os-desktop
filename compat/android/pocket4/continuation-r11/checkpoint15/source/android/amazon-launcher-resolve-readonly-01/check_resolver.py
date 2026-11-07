#!/usr/bin/env python3
"""Local resolver/actual-receipt checks. Never call execute or Android."""
import copy
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
BASE=Path('/workspace/scratch/94990735b266')
def load(path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    return module

r=load(HERE/'resolve_amazon.py','owned_resolver_control')
originals=BASE/'root-recovery-20261104-02/evidence/amazon-qa-r1-install-state01-read01/originals'
observations=[]
def passed(name):observations.append({'name':name,'passed':True})
def rejects(name,call):
    try:call()
    except (RuntimeError,UnicodeError):passed(name)
    else:raise AssertionError(name+' unexpectedly accepted')

rows={}
for key,(_,size,digest) in r.PRIOR.items():
    raw=(originals/({'coordinator':'coordinator.json','stage':'stage.json','worker':'worker.json'}[key])).read_bytes()
    assert len(raw)==size and hashlib.sha256(raw).hexdigest()==digest
    rows[key]=json.loads(raw)
assert r.actual_install(rows)['installed']==r.INSTALLED
passed('actual_three_originals_full_pins_and_production_prior_chain')
for name,alter in (
    ('wrong_installed_uid',lambda x:x['worker'].__setitem__('owned_package_uid',10170)),
    ('state_connected_automation',lambda x:x['worker']['state']['helper'].__setitem__('ui_automation_connected',True)),
    ('coordinator_worker_pin',lambda x:x['coordinator']['worker_result'].__setitem__('sha256','0'*64)),
    ('retirement_incomplete',lambda x:x['worker'].__setitem__('held_binding_released',False)),
):
    wrong=copy.deepcopy(rows);alter(wrong)
    rejects(name,lambda:r.actual_install(wrong))

full=(r.PACKAGE+'/owned.fixture.Launcher\n').encode()
relative=(r.PACKAGE+'/.OwnedFixtureLauncher\n').encode()
assert r.component(full)['component']==full.decode().strip()
assert r.component(b'priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true\n'+relative)['component']==relative.decode().strip()
passed('synthetic_full_and_relative_component_with_original_brief_metadata')
for name,raw in (
    ('foreign_package',b'com.other.fixture/.Launcher\n'),
    ('ambiguous_components',full+relative),
    ('missing_component',b'No activity found\n'),
    ('output_byte_limit',b'x'*4096+b'\n'),
    ('embedded_NUL',b'\0'+full),
):
    rejects(name,lambda raw=raw:r.component(raw))

context_path=BASE/'android-amazon-qa-r1-install-state-01/amazon_context.py'
assert hashlib.sha256(context_path.read_bytes()).hexdigest()==r.CONTEXT_SHA
context=load(context_path,'actual_qualified_context_control')
plan=r.command_plan(context)
assert len(plan)==9 and all(m is False for _,_,m in plan)
assert plan[4]==(r.RESOLVE,15,False)
assert all('/system/bin/am' not in argv and 'install' not in argv and 'start' not in argv for argv,_,_ in plan)
passed('exact_nine_only_read_only_package_commands')

# These are transport I/O seams only. The production Context.android method
# itself decides whether the request can reach the transport and poisons it
# before any repeated Android command can be attempted.
def fixture():
    calls=[]
    def transport_factory(**kw):
        assert kw['package']==r.PACKAGE and kw['uid']==10129
        def call(argv,timeout):calls.append((argv,timeout));return b'owned synthetic response'
        return call
    transport=types.SimpleNamespace(BoundArun=transport_factory,FRAMEWORK_EPOCH_SHA256='owned-control-epoch')
    fake=types.SimpleNamespace(write_new=lambda *args:None)
    target=types.SimpleNamespace(verify=lambda:None,close=lambda:None)
    c=context.Context(fake,None,target,{},transport,lambda:None,HERE,plan,42,0)
    return c,calls
c,calls=fixture()
for argv,timeout,mutation in plan:c.android(argv,timeout,mutation=mutation)
assert c.next_command==9 and len(calls)==9
rejects('actual_Context_extra_command_denied',lambda:c.android(r.RESOLVE,15))
assert len(calls)==9 and c.poisoned
c,calls=fixture()
rejects('actual_Context_mutation_denied_before_transport',lambda:c.android(plan[0][0],15,mutation=True))
assert calls==[] and c.next_command==0 and c.poisoned

print(json.dumps({'schema':1,'state':'LOCAL_SOURCE_AND_RETAINED_INSTALL_CHECKS_PASS_ANDROID_UNRUN',
    'resolver_sha256':hashlib.sha256((HERE/'resolve_amazon.py').read_bytes()).hexdigest(),
    'passed':len(observations),'rows':observations,
    'actual_prior_receipts_verified':True,'actual_Context_android_called':True,
    'transport_and_guard_I_O_seams':True,'Android_or_Hepta_actions':0,
    'current_launcher_component_known':False,'whole_app_production_ready':False},sort_keys=True,indent=2))
