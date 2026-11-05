#!/usr/bin/env python3
"""Local source controls only: no Android, namespace, process or UI calls."""
import contextlib
import copy
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import types

HERE=Path(__file__).resolve().parent
BASE=Path('/workspace/scratch/94990735b266')


def module(path,name):
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),value.__dict__)
    return value


def require(value,reason):
    if not value:raise RuntimeError(reason)


@contextlib.contextmanager
def patched(value,name,replacement):
    previous=getattr(value,name);setattr(value,name,replacement)
    try:yield
    finally:setattr(value,name,previous)


def main():
    candidate=module(HERE/'viewport_observation.py','actual_candidate')
    qa_path=BASE/'owned-bili-qa-r3-search-01/source/qa_contract.py'
    adapter_path=BASE/'owned-bili-qa-r3-search-01/source/qa_adapter.py'
    backend_path=BASE/'android-bili-r3-video-foreground-reference-01/android_backend.py'
    private_path=BASE/'root-recovery-20261104-02/private/qa-r3-video-transition01-trees/private-trees.json'
    expected={qa_path:'6789ec1fef825d9738a6f59a14611dc2d60adc994b093f1ee4cfa9eb75ef9470',
        adapter_path:'f58ee613069a6e8e4d6f1aa7c6532f2faeb5790a70564d294591444fa7de1767',
        backend_path:'088be6d783e80006645a05b8c5b90cd100d3e38b6f3d4634dd499ab1de7898ae',
        private_path:'66d9d408177eb7ff3ddfc3c62745e137e80fef218f49a5a3a540575e0568549a'}
    for path,pin in expected.items():assert hashlib.sha256(path.read_bytes()).hexdigest()==pin
    qa=module(qa_path,'actual_r3_contract');adapter=module(adapter_path,'actual_r3_adapter')
    backend=module(backend_path,'actual_backend_codec');private=json.loads(private_path.read_bytes())
    base=types.SimpleNamespace(require=require,sha=lambda raw:hashlib.sha256(raw).hexdigest(),BILI='tv.danmaku.bili',UID=10166)
    records=[]
    def case(name,body):
        body();records.append({'name':name,'passed':True})
    proofs=[]
    def actual_geometry():
        for row in private['observations'][1:]:
            proof=candidate.viewport(base,qa,row['inspection'],row['scope'])
            assert proof['crop']==[320,45,1520,720] and proof['buffering_label_present'] is True
            proofs.append(proof)
    case('actual_two_complete_private_trees_match_current_course_overlay_buffering',actual_geometry)
    def incomplete_course():
        row=private['observations'][0]
        try:candidate.viewport(base,qa,row['inspection'],row['scope'])
        except RuntimeError as exc:assert str(exc)=='EXACT_CURRENT_VIEWPORT_NODE_REQUIRED:tv.danmaku.bili:id/title'
        else:raise AssertionError('early metadata absence admitted')
    case('actual_first_tree_without_course_metadata_rejected',incomplete_course)
    case('all_45_fixed_read_nonces_pass_actual_adapter_contract',lambda:candidate.validate(adapter,qa,[]))
    def collision():
        try:candidate.validate(adapter,qa,[candidate.NONCES[0][0]])
        except qa.ProtocolError:pass
        else:raise AssertionError('nonce collision accepted')
    case('nonce_collision_rejected_before_any_command',collision)

    image=backend.Image.new('RGB',(1840,1520),(20,30,40))
    image.paste((80,90,100),(320,45,1520,720));wire=io.BytesIO();image.save(wire,format='PNG');png=wire.getvalue();image.close()
    proof=proofs[-1]
    def capture_case(mode):
        with tempfile.TemporaryDirectory(prefix='owned-viewport-control-')as td:
            calls=[];flow=types.SimpleNamespace(step=Path(td),_private_backend_transport=False,
                contract=types.SimpleNamespace(load=lambda path,name:backend))
            def android(argv,timeout,**kwargs):
                calls.append('capture');assert flow._private_backend_transport is True
                assert argv==['/system/bin/screencap','-p'] and timeout==20 and kwargs=={'mutation':False}
                if mode=='timeout_after_failure':raise subprocess.TimeoutExpired('owned-test',20)
                return b'not PNG'if mode=='bad_png'else png
            flow.android=android
            def post(*args):
                calls.append('after')
                if mode in ('timeout_after_failure','post_failure'):raise RuntimeError('OWNED_POST_READ_FAILURE')
                value=copy.deepcopy(proof)
                if mode=='changed_scope':value['scope']['window_token']='deadbeef'
                return value,{'owned_synthetic_post_read':True}
            initial_fds=len(os.listdir('/proc/self/fd'))
            with patched(candidate,'inspect',post):
                original_write=candidate.os.write
                def no_space(fd,data):raise OSError(errno.ENOSPC,'owned injected write failure')
                with patched(candidate.os,'write',no_space if mode=='write_failure'else original_write):
                    try:
                        after,result=candidate.capture(base,None,qa,flow,None,None,proof,candidate.PLANS[12],1)
                    except BaseException as exc:
                        assert mode!='success'
                        if mode=='timeout_after_failure':
                            assert isinstance(exc,subprocess.TimeoutExpired) and any('OWNED_POST_READ_FAILURE'in n for n in exc.__notes__)
                        elif mode=='bad_png':assert str(exc)=='BOUNDED_ORIGINAL_SCREENSHOT_REQUIRED'
                        elif mode=='post_failure':assert str(exc)=='OWNED_POST_READ_FAILURE'
                        elif mode=='changed_scope':assert str(exc)=='VIEWPORT_SCOPE_CHANGED_DURING_CAPTURE'
                        elif mode=='write_failure':assert exc.errno==errno.ENOSPC
                        assert exc.viewport_observation['private_crop_published'] is False
                        if mode!='write_failure':assert list(Path(td).iterdir())==[]
                    else:
                        assert mode=='success' and result['private_crop_published'] is True
                        saved=Path(result['private_crop']['path']);raw=saved.read_bytes()
                        assert stat.S_IMODE(saved.stat().st_mode)==0o600
                        assert result['private_crop']['sha256']==base.sha(raw)
                        parsed=backend.png_image(raw)
                        try:assert parsed.size==(1200,675) and parsed.getpixel((0,0))==(80,90,100)
                        finally:parsed.close()
                        assert raw!=png and result['atomic_frame_attribution'] is False
                        assert result['video_only_pixels_proven'] is False and result['playback_verified'] is False
            assert calls==['capture','after'] and flow._private_backend_transport is False
            assert len(os.listdir('/proc/self/fd'))==initial_fds
    for mode in ('success','timeout_after_failure','bad_png','post_failure','changed_scope','write_failure'):
        case('actual_capture_'+mode,lambda mode=mode:capture_case(mode))

    def remember(result,phase,exc):
        row={'phase':phase,'type':type(exc).__name__,'message':str(exc)}
        if result['error']is None:result['error']=row
        else:result['secondary_errors'].append(row)
    prior=types.SimpleNamespace(remember=remember)
    def run_case(mode):
        reads=[];captures=[];session=types.SimpleNamespace(sequence_observation={'owned_synthetic_marker':True})
        def read(*args):
            reads.append(args[-1]);value=copy.deepcopy(proof)
            if mode=='failed_second_read'and len(reads)==2:raise RuntimeError('OWNED_READ_FIRST_FAILURE')
            value['buffering_label_present']=mode in ('persistent','failed_second_read')or len(reads)<2
            return value,{'owned_synthetic_read':len(reads)}
        def capture(*args):
            captures.append(args[-1]);value=copy.deepcopy(args[-3])
            if mode=='reappeared':value['buffering_label_present']=True
            return value,{'owned_synthetic_crop':args[-1]}
        result={'error':None,'secondary_errors':[],'video_click_and_observations_completed':True}
        with patched(candidate,'inspect',read),patched(candidate,'capture',capture):
            candidate.run(base,prior,qa,None,session,None,result)
        if mode=='persistent':
            assert len(reads)==12 and captures==[1] and result['error']['message']=='BUFFERING_REMAINED_IN_BOUNDED_READS'
        elif mode=='ready':
            assert len(reads)==2 and captures==[1,2,3] and result['error']is None
            assert result['buffer_viewport_observation']['final_scope']==proof['scope']
        elif mode=='failed_second_read':assert len(reads)==2 and captures==[] and result['error']['message']=='OWNED_READ_FIRST_FAILURE'
        elif mode=='reappeared':assert len(reads)==2 and captures==[1] and result['error']['message']=='BUFFERING_REAPPEARED_DURING_VIEWPORT_OBSERVATION'
        assert result['buffer_viewport_observation_completed']is(mode=='ready')
        assert result['playback_or_audio_success_inferred']is False
        assert result['buffer_viewport_observation']['action_replayed']is False
    for mode in ('persistent','ready','failed_second_read','reappeared'):
        case('actual_run_'+mode,lambda mode=mode:run_case(mode))
    print(json.dumps({'schema':1,'passed':True,'controls':records,'count':len(records),
        'remote_actions':0,'commercial_UI_or_audio_actions':0,'raw_private_UI_exported':False,
        'actual_candidate_source_sha256':base.sha((HERE/'viewport_observation.py').read_bytes()),
        'actual_external_inputs':{str(path):pin for path,pin in expected.items()},
        'seams':['held Android command returns owned synthetic PNG or error','independent Session inspection IO in capture controls',
                 'inspection and capture IO in bounded-loop controls'],
        'not_qualified':['actual screencap/default-display mapping','live player effects','audio','whole App']},indent=2,sort_keys=True))


if __name__=='__main__':main()
