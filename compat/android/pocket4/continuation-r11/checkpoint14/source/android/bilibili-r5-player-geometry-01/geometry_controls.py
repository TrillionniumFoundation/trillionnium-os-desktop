#!/usr/bin/env python3
"""Owned synthetic reproduction of the observed two-surface geometry.

No commercial tree, image, namespace, Android command, or device is read.
Only the unchanged outer inspect-record/scope parser is a seam; both original
and candidate production viewport predicates and same_scope run directly.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m);return m


def main():
    new=load(HERE/'viewport_observation.py','candidate_viewport')
    old=load(HERE.parent/'android-bili-r5-buffer-viewport-01/viewport_observation.py','original_viewport')
    contract=load(HERE.parent/'owned-bili-qa-r5-cache-build02/source/qa_contract.py','frozen_R5_canonical')
    def need(ok,reason):
        if not ok:raise RuntimeError(reason)
    digest=lambda b:hashlib.sha256(b).hexdigest()
    base=types.SimpleNamespace(require=need,sha=digest,BILI='tv.danmaku.bili')
    qa=types.SimpleNamespace(inspect_record=lambda x:x,scope=lambda x:x,canonical=contract.canonical)
    full=[320,45,1520,1498];crop=[320,45,1520,720];scope={'activity':new.DETAILS}
    def node(resource,kind,path,bounds,text=''):
        return {'resource_id':resource,'resource_id_truncated':False,'class':kind,'class_truncated':False,
                'path':path,'bounds':list(bounds),'visible':True,'enabled':True,'password':False,
                'text':text,'text_truncated':False,'text_sha256':digest(text.encode()),'clickable':False}
    def refresh(value):
        for n in value['nodes']:
            n.pop('node_sha256',None);n['node_sha256']=digest(contract.canonical(n))
        return value
    def fixture():
        values=[node('tv.danmaku.bili:id/title','android.widget.TextView','0/1',[320,760,1000,820],
                     'Very Basic Calculus 000: Course Introduction'),
                node('tv.danmaku.bili:id/author_name','android.widget.TextView','0/2',[320,830,1000,900],
                     'Ayumu爱讲数学'),
                node('tv.danmaku.bili:id/video_area','android.widget.FrameLayout','0/0',full),
                node('tv.danmaku.bili:id/video_container','android.widget.FrameLayout','0/0/0',full),
                node('tv.danmaku.bili:id/video_area_float_layer_container','android.widget.FrameLayout','0/0/1',crop),
                node('tv.danmaku.bili:id/collapsing_toolbar','android.widget.FrameLayout','0/0/2',crop),
                node('','android.widget.FrameLayout','0/0/0/0',full),
                node('','android.view.SurfaceView','0/0/0/0/0',full),
                node('','android.widget.FrameLayout','0/0/0/1',crop),
                node('','android.view.SurfaceView','0/0/0/1/0',crop)]
        return refresh({'nodes':values,'window':{'bounds':[320,0,1520,1520],'focused':True,
            'package':base.BILI,'display':0,'type':1},'window_sha256':'a'*64})
    def proof(value):return new.viewport(base,qa,value,scope)
    rows=[]
    def positive():
        value=fixture()
        try:old.viewport(base,qa,value,scope)
        except RuntimeError as e:assert str(e)=='UNIQUE_CURRENT_PLAYER_STRUCTURE_REQUIRED'
        else:raise AssertionError('original counterexample did not fail')
        out=proof(value)
        assert out['crop']==crop and out['surface_bounds']==crop and out['full_area_surface_bounds']==full
        assert out['renderer_content_identity_proven'] is False and out['video_only_pixels_proven'] is False
        assert len(out['render_structure']['surfaces'])==2
    positive();rows.append({'name':'observed_safe_geometry_original_red_candidate_unique_crop','passed':True})

    tests=[
      ('incomplete_single_surface',lambda x:x['nodes'].__delitem__(slice(8,10)),
       'EXACT_TWO_CURRENT_PLAYER_SURFACES_REQUIRED'),
      ('missing_area_surface',lambda x:x['nodes'].pop(7),'EXACT_TWO_CURRENT_PLAYER_SURFACES_REQUIRED'),
      ('third_surface',lambda x:x['nodes'].append(node('','android.view.SurfaceView','0/0/0/2',crop)),
       'EXACT_TWO_CURRENT_PLAYER_SURFACES_REQUIRED'),
      ('two_crop_sized_candidates',lambda x:(x['nodes'][6].update(bounds=crop),x['nodes'][7].update(bounds=crop)),
       'UNIQUE_AREA_AND_CROP_SURFACE_GEOMETRY_REQUIRED'),
      ('shifted_crop_candidate',lambda x:(x['nodes'][8].update(bounds=[321,45,1520,720]),
                                          x['nodes'][9].update(bounds=[321,45,1520,720])),
       'UNIQUE_AREA_AND_CROP_SURFACE_GEOMETRY_REQUIRED'),
      ('missing_immediate_parent',lambda x:x['nodes'].pop(8),'EXACT_SURFACE_PARENT_STRUCTURE_REQUIRED'),
      ('wrong_parent_class',lambda x:x['nodes'][8].update(**{'class':'android.widget.LinearLayout'}),
       'EXACT_SURFACE_PARENT_STRUCTURE_REQUIRED'),
      ('incomplete_parent_resource',lambda x:x['nodes'][8].update(resource_id_truncated=True),
       'EXACT_SURFACE_PARENT_STRUCTURE_REQUIRED'),
      ('TextureView_additional_candidate',lambda x:x['nodes'].append(node('','android.view.TextureView','0/9',crop)),
       'EXACT_TWO_CURRENT_PLAYER_SURFACES_REQUIRED'),
      ('crop_surface_outside_container',lambda x:x['nodes'][9].update(path='0/8/0'),
       'EXACT_TWO_CURRENT_PLAYER_SURFACES_REQUIRED'),
      ('incomplete_surface_class',lambda x:x['nodes'][9].update(class_truncated=True),
       'EXACT_TWO_CURRENT_PLAYER_SURFACES_REQUIRED')]
    for name,mutate,expected in tests:
        value=fixture();mutate(value);refresh(value)
        try:proof(value)
        except RuntimeError as e:assert str(e)==expected,(name,str(e))
        else:raise AssertionError('negative gate accepted '+name)
        rows.append({'name':name,'passed':True,'expected_error':expected})

    before=proof(fixture());reordered=fixture();reordered['nodes'].reverse();after=proof(reordered)
    assert new.same_scope(before,after) and before['render_structure_sha256']==after['render_structure_sha256']
    rows.append({'name':'traversal_order_not_a_selection_rule','passed':True})
    moved=fixture();moved['nodes'][8]['path']='0/0/0/3';moved['nodes'][9]['path']='0/0/0/3/0';refresh(moved)
    after=proof(moved);assert after['crop']==before['crop'] and not new.same_scope(before,after)
    rows.append({'name':'same_crop_changed_parent_path_rejected_before_publication','passed':True})
    changed=fixture();changed['nodes'][8]['clickable']=True;refresh(changed)
    after=proof(changed);assert after['crop']==before['crop'] and not new.same_scope(before,after)
    rows.append({'name':'same_crop_changed_parent_record_rejected_before_publication','passed':True})
    assert len(rows)==15
    report={'schema':1,'passed':15,'controls':rows,'actual_production_viewport_and_same_scope_called':True,
            'original_viewport_counterexample_executed':True,'scope_and_inspection_validation_seam':True,
            'geometry_from_safe_actual_report_SHA256':'4add570dcc3d680b469ca9b1133ffc6d76d9aa98cd4b21209943dea24dbc3143',
            'production_source_sha256':digest((HERE/'viewport_observation.py').read_bytes()),
            'synthetic_UI_nodes':True,'commercial_UI_or_images_read':False,
            'namespace_or_Android_calls':0,'playback_or_audio_qualification':False}
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
