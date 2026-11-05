#!/usr/bin/env python3
"""Actual capture/run functions with owned PNG and explicit inspection I/O seams.

No commercial UI/image is read, no device command or namespace is entered.
"""
import ast
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import types

HERE=Path(__file__).resolve().parent
BASE=Path('/workspace/scratch/94990735b266')
def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__)
    return m
def require(ok,message):
    if not ok:raise RuntimeError(message)
@contextlib.contextmanager
def patched(module,name,value):
    original=getattr(module,name);setattr(module,name,value)
    try:yield
    finally:setattr(module,name,original)

new=load(HERE/'viewport_observation.py','actual_fresh_capture')
old=load(BASE/'android-bili-r5-player-geometry-01/viewport_observation.py','actual_retained_capture')
qa=load(BASE/'owned-bili-qa-r5-cache-build02/source/qa_contract.py','actual_r5_contract')
adapter=load(BASE/'owned-bili-qa-r5-cache-build02/source/qa_adapter.py','actual_r5_adapter')
backend_path=BASE/'android-bili-r3-video-foreground-reference-01/android_backend.py'
assert hashlib.sha256(backend_path.read_bytes()).hexdigest()=='088be6d783e80006645a05b8c5b90cd100d3e38b6f3d4634dd499ab1de7898ae'
backend=load(backend_path,'actual_existing_png_codec')
base=types.SimpleNamespace(require=require,sha=lambda b:hashlib.sha256(b).hexdigest())
def remember(result,phase,error):
    row={'phase':phase,'type':type(error).__name__,'message':str(error)}
    if result['error'] is None:result['error']=row
    else:result['secondary_errors'].append(row)
prior=types.SimpleNamespace(remember=remember)

def proof(x,buffering=False):
    window={'id':42,'type':1,'display':0,'package':'tv.danmaku.bili',
        'focused':True,'active':True,'bounds':[x,0,x+1200,1520]}
    return {'scope':{'package':'tv.danmaku.bili','uid':10117,'user':0,'display':0,
        'activity':new.DETAILS,'window_token':'f00dcafe','main_epoch_sha256':qa.MAIN_EPOCH},
        'window':window,'window_sha256':base.sha(qa.canonical(window)),
        'crop':[x,45,x+1200,720],'surface_bounds':[x,45,x+1200,720],
        'full_area_surface_bounds':[x,45,x+1200,1498],
        'render_structure_sha256':base.sha(qa.canonical({'synthetic':True,'x':x})),
        'title_text_sha256':new.TITLE,'author_text_sha256':new.AUTHOR,
        'buffering_label_present':buffering}

im=backend.Image.new('RGB',(1840,1520),(20,30,40))
im.paste((80,90,100),(0,45,1840,720))
wire=io.BytesIO();im.save(wire,format='PNG');png=wire.getvalue();im.close()
rows=[]
def passed(name,**extra):rows.append({'name':name,'passed':True,**extra})

def transaction(mode,baseline=False):
    with tempfile.TemporaryDirectory(prefix='owned-fresh-viewport-',dir=HERE) as td:
        events=[];published=[]
        flow=types.SimpleNamespace(step=Path(td),_private_backend_transport=False,
            contract=types.SimpleNamespace(load=lambda path,name:backend))
        def android(argv,timeout,**kwargs):
            events.append('capture')
            assert flow._private_backend_transport and argv==['/system/bin/screencap','-p']
            assert timeout==20 and kwargs=={'mutation':False}
            if mode=='timeout_and_after_error':raise subprocess.TimeoutExpired('owned synthetic command',20)
            return png
        flow.android=android
        def inspect(*args):
            if baseline:
                events.append('after');return proof(0),{'owned_synthetic_io':True}
            phase='before' if args[-1] is new.PLANS[12] else 'after'
            assert args[-1] is new.PLANS[12 if phase=='before' else 13]
            events.append(phase)
            if mode=='before_error' and phase=='before':raise RuntimeError('OWNED_FRESH_BEFORE_FAILURE')
            if mode in ('after_error','timeout_and_after_error') and phase=='after':
                raise RuntimeError('OWNED_INDEPENDENT_AFTER_FAILURE')
            value=proof(320 if mode=='inside_move' and phase=='before' else 0,
                        buffering=mode=='before_rebuffer' and phase=='before')
            return value,{'owned_synthetic_io':True,'proof':value}
        target=old if baseline else new
        with patched(target,'inspect',inspect):
            try:
                if baseline:after,record=old.capture(base,prior,qa,flow,None,None,proof(320),old.PLANS[12],1)
                else:after,record=new.capture(base,prior,qa,flow,None,None,new.PLANS[12],new.PLANS[13],1)
            except BaseException as error:
                assert baseline or mode!='stable_new_authority',repr(error)
                if baseline or mode=='inside_move':assert str(error)=='VIEWPORT_SCOPE_CHANGED_DURING_CAPTURE'
                elif mode=='before_error':assert str(error)=='OWNED_FRESH_BEFORE_FAILURE'
                elif mode=='before_rebuffer':assert str(error)=='BUFFERING_REAPPEARED_BEFORE_CAPTURE'
                elif mode=='after_error':assert str(error)=='OWNED_INDEPENDENT_AFTER_FAILURE'
                elif mode=='timeout_and_after_error':
                    assert isinstance(error,subprocess.TimeoutExpired)
                    assert any('OWNED_INDEPENDENT_AFTER_FAILURE' in x for x in error.__notes__)
                assert error.viewport_observation['private_crop_published'] is False
                assert not list(Path(td).iterdir())
            else:
                assert mode=='stable_new_authority' and record['fresh_before_read_completed'] is True
                assert record['scope_checked_before_and_after'] is True and record['private_crop_published'] is True
                assert record['before_observation']['proof']==after==proof(0)
                assert record['private_crop']['bounds']==[0,45,1200,720]
                saved=Path(record['private_crop']['path']);assert saved.exists()
                image=backend.png_image(saved.read_bytes())
                try:assert image.size==(1200,675) and image.getpixel((0,0))==(80,90,100)
                finally:image.close()
                assert record['atomic_frame_attribution'] is False and record['playback_verified'] is False
        expected_events=['capture','after'] if baseline else (['before'] if mode in ('before_error','before_rebuffer')
            else ['before','capture','after'])
        assert events==expected_events and flow._private_backend_transport is False
        return events

transaction('stable_new_authority',baseline=True)
passed('retained_baseline_stale_previous_scope_rejects_same_owned_moved_fixture')
transaction('stable_new_authority')
passed('fresh_current_before_and_after_agree_after_inter_transaction_move')
for mode in ['inside_move','before_error','before_rebuffer','after_error','timeout_and_after_error']:
    events=transaction(mode)
    passed(mode+'_fails_without_crop_and_without_retry',events=events)

def run_case(mode):
    with tempfile.TemporaryDirectory(prefix='owned-fresh-loop-',dir=HERE) as td:
        calls=[];raws=[]
        flow=types.SimpleNamespace(step=Path(td),_private_backend_transport=False,
            contract=types.SimpleNamespace(load=lambda path,name:backend))
        def android(argv,timeout,**kwargs):raws.append(1);return png
        flow.android=android
        def inspect(*args):
            plan=args[-1];index=next(i for i,x in enumerate(new.PLANS) if x is plan)
            calls.append(index)
            if mode=='failed_buffer' and index==1:raise RuntimeError('OWNED_SECOND_BUFFER_FAILURE')
            if index<12:return proof(320,mode in ('persistent_buffer','failed_buffer')),{'index':index}
            pair=(index-12)//2
            x=[320,0,640][pair]
            if mode=='within_second' and index==15:x=320
            return proof(x,mode=='persistent_buffer'),{'index':index,'proof':proof(x,mode=='persistent_buffer')}
        result={'error':None,'secondary_errors':[],'video_click_and_observations_completed':True}
        session=types.SimpleNamespace(sequence_observation={'owned_synthetic_marker':True})
        with patched(new,'inspect',inspect):new.run(base,prior,qa,flow,session,None,result)
        published=sorted(p.name for p in Path(td).iterdir())
        if mode=='new_each_time':
            assert calls==[0,12,13,14,15,16,17] and len(raws)==3 and len(published)==3
            assert result['error'] is None and result['buffer_viewport_observation_completed'] is True
            assert [x['before_observation']['index'] for x in result['buffer_viewport_observation']['viewport_samples']]==[12,14,16]
        elif mode=='within_second':
            assert calls==[0,12,13,14,15] and len(raws)==2 and published==['player-viewport-01.png']
            assert result['error']['message']=='VIEWPORT_SCOPE_CHANGED_DURING_CAPTURE'
            assert result['buffer_viewport_observation']['failed_capture']['private_crop_published'] is False
        elif mode=='persistent_buffer':
            assert calls==list(range(14)) and len(raws)==1 and len(published)==1
            assert result['error']['message']=='BUFFERING_REMAINED_IN_BOUNDED_READS'
        elif mode=='failed_buffer':
            assert calls==[0,1] and not raws and not published
            assert result['error']['message']=='OWNED_SECOND_BUFFER_FAILURE'
        assert result['playback_or_audio_success_inferred'] is False
        return calls
for mode in ['new_each_time','within_second','persistent_buffer','failed_buffer']:
    passed('actual_run_'+mode,inspection_plan_indexes=run_case(mode))

registry=json.loads((HERE/'new-nonces.json').read_text())
current=[n for row in new.NONCES for n in row]
assert len(current)==54 and len(set(registry.values()))==len(registry)==158
new.validate(adapter,qa,set(registry.values())-set(current))
passed('actual_r5_contract_validates54_capture_read_nonces_in_fresh158_nonce_set')
def funcs(path):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body
            if isinstance(n,ast.FunctionDef)}
a,b=funcs(BASE/'android-bili-r5-player-geometry-01/viewport_observation.py'),funcs(HERE/'viewport_observation.py')
assert [n for n in a if a[n]!=b[n]]==['validate','capture','run']
passed('geometry_inspect_scope_comparator_and_private_writer_ast_unchanged')
print(json.dumps({'schema':1,'state':'LOCAL_FRESH_CAPTURE_TRANSACTION_CONTROLS_PASS_ANDROID_UNRUN',
    'passed':len(rows),'rows':rows,'candidate_sha256':base.sha((HERE/'viewport_observation.py').read_bytes()),
    'actual_prior_source_called':True,'actual_candidate_capture_and_run_called':True,
    'actual_original_PNG_codec_used_on_owned_synthetic_image':True,
    'explicit_seams':['independent Session inspection I/O returns owned proof','held screenshot command returns owned PNG'],
    'commercial_UI_images_or_trees_read':False,'Android_or_Hepta_actions':0,
    'live_capture_mapping_and_playback_or_audio_qualified':False,'whole_app_production_ready':False},
    sort_keys=True,indent=2))
