#!/usr/bin/env python3
"""Run the actual old/new control methods at unknown-effect boundaries; no device."""
from pathlib import Path
import copy, hashlib, importlib.util, json, time, types

ROOT=Path(__file__).resolve().parent

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def main():
    old=load(ROOT.parent/'candidate/expired-text/delivery03/timer03.py','timer_old')
    new=load(ROOT/'timer_core04.py','timer_new');rows=[]
    def base(module):
        f=module.Flow.__new__(module.Flow);calls=[]
        f.r={'phases':{}};f.timer_id=7;f.owned=[999];f.closed=[];f.number=0
        f.deadline=time.monotonic()+30;f.effect_pending=None;f.close_pending=None
        f.c=types.SimpleNamespace(pending=None,actions=0,nodes=[],latest='actual-before')
        f.t=types.SimpleNamespace(owned=(999,{851}),removals=0,result={},s=object(),
            record=lambda label,value:calls.append(('record',label,copy.deepcopy(value))))
        def close():
            calls.append(('close',));f.t.owned=None;f.t.removals+=1;f.t.result['other_tasks_preserved']=True
        f.t.close=close
        return f,calls
    # Old production close really sends a remove despite unresolved native input.
    f,calls=base(old);f.c.pending='unresolved-input';f.close()
    assert sum(c[0]=='close' for c in calls)==1
    rows.append({'case':'old_close_negative_control_dispatches_with_native_unknown','passed':True})
    for field,value in (('native','unresolved-input'),('effect',{'operation':'create'}),
                        ('close',{'task':999})):
        f,calls=base(new)
        if field=='native':f.c.pending=value
        elif field=='effect':f.effect_pending=value
        else:f.close_pending=value
        try:f.close()
        except RuntimeError as exc:assert str(exc)=='UNKNOWN_TIMER_INPUT_EFFECT_OR_CLOSE_RETAINED'
        else:raise AssertionError(field)
        assert not any(c[0]=='close' for c in calls)
        rows.append({'case':'new_'+field+'_pending_blocks_actual_close','passed':True})
    f,calls=base(new)
    def unknown_close():f.t.owned=None;calls.append(('close',));raise RuntimeError('REMOVE_OUTCOME_UNKNOWN')
    f.t.close=unknown_close
    try:f.close()
    except RuntimeError as exc:assert str(exc)=='REMOVE_OUTCOME_UNKNOWN'
    assert f.close_pending=={'task':999,'automatic_retry':False} and f.t.owned is None
    try:f.close()
    except RuntimeError as exc:assert str(exc)=='UNKNOWN_TIMER_INPUT_EFFECT_OR_CLOSE_RETAINED'
    assert sum(c[0]=='close' for c in calls)==1
    rows.append({'case':'actual_unknown_remove_keeps_fence_after_Trial_loses_owned_field','passed':True})
    for scenario in ('ack_without_prefs_readback','unknown_native','preinput_rejected'):
        f,calls=base(new)
        node={'resource-id':new.PACKAGE+':id/fab','class':'android.widget.Button',
              'text':'Pause','clickable':True}
        f.c.nodes=[node];f.settle_notice=lambda:None;f.timer_tab=lambda:{'selected':True}
        f.loop=types.SimpleNamespace(candidates=lambda *args:[node])
        f.m=types.SimpleNamespace(read=lambda *args:{'state':1},owned=lambda *args:{'state':1})
        def step(request):
            assert f.effect_pending['operation']=='pause' and f.effect_pending['timer_id']==7
            assert any(c[0]=='record' and c[1].startswith('timer-effect-intent-') for c in calls)
            if scenario=='preinput_rejected':raise RuntimeError('KNOWN_PREINPUT_REJECTION')
            f.c.actions+=1
            if scenario=='unknown_native':f.c.pending=request['id'];raise RuntimeError('INPUT_UNKNOWN')
        f.c.step=step
        try:f.act('pause',node,1)
        except RuntimeError as exc:
            assert str(exc) in ('INPUT_UNKNOWN','KNOWN_PREINPUT_REJECTION')
            assert scenario!='ack_without_prefs_readback'
        else:assert scenario=='ack_without_prefs_readback'
        assert (f.effect_pending is None)==(scenario=='preinput_rejected')
        if f.effect_pending is not None:
            saved=copy.deepcopy(f.effect_pending);f.cleanup(time.monotonic()+35)
            assert f.effect_pending==saved and not any(c[0]=='close' for c in calls)
        rows.append({'case':scenario+'_effect_precedes_dispatch_and_no_implicit_cleanup','passed':True})
    f,calls=base(new);f.effect_pending={'operation':'delete','native_request_id':'t01-delete','timer_id':7}
    values=[{'ids':[7],'timers':[{'id':7}]},{'ids':[],'timers':[]}]
    def read(*args):assert f.timer_id==7;return values.pop(0)
    f.m=types.SimpleNamespace(read=read,empty=lambda v:None,
        owned=lambda v,i,d:v['timers'][0] if v['ids']==[i] else (_ for _ in ()).throw(RuntimeError('FOREIGN')))
    f.observe_scheduler=lambda label:None
    new.time=types.SimpleNamespace(monotonic=time.monotonic,sleep=lambda seconds:None)
    f.deleted('deleted')
    assert f.timer_id is None and f.effect_pending is None and not values
    rows.append({'case':'delete_retains_owned_ID_until_exact_empty_readback','passed':True})
    bound=new.CANDIDATE_BINDING_READY;new.CANDIDATE_BINDING_READY=False
    try:new.execute()
    except RuntimeError as exc:assert str(exc)=='NEW_CLOCK_INSTALL_IDENTITY_NOT_BOUND'
    else:raise AssertionError('draft executed')
    new.CANDIDATE_BINDING_READY=bound
    rows.append({'case':'unbound_candidate_execute_is_inert','passed':True})
    result={'schema':'timer04-pending-boundary-review-v1','passed':len(rows),'failed':0,'cases':rows,
        'source_sha256':hashlib.sha256((ROOT/'timer_core04.py').read_bytes()).hexdigest(),
        'scope':'Actual old/new close, act, cleanup and delete control methods with explicit Trial/native/prefs reader boundary doubles. No native input, timer creation or device business proof.',
        'device_commands':0,'UI_actions':0,'candidate_identity_bound':bound}
    raw=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode();(ROOT/'PENDING_BOUNDARIES_BOUND04.json').write_bytes(raw)
    print(json.dumps({'passed':len(rows),'failed':0,'sha256':hashlib.sha256(raw).hexdigest()}))

if __name__=='__main__':main()
