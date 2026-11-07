#!/usr/bin/env python3
"""Local fixed-role diagnostic controls; no retained UI or device reads."""
import importlib.util
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent

def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
    d=load(HERE/'read_structure.py','structure_reader')
    original=load(HERE.parent/'android-bili-r5-buffer-viewport-01/viewport_observation.py','actual_frozen_viewport')
    # Only scope/hash validation is a seam here; the original production viewport
    # predicate and the new diagnostic itself run unchanged on synthetic nodes.
    qa=types.SimpleNamespace(inspect_record=lambda x:x,scope=lambda x:x)
    base=types.SimpleNamespace(require=d.need,sha=d.sha,BILI='tv.danmaku.bili')
    def node(resource,kind,path,bounds,text=''):
        value={'resource_id':resource,'class':kind,'path':path,'bounds':bounds,
                'resource_id_truncated':False,'class_truncated':False,'visible':True,
                'enabled':True,'password':False,'text':text,'text_truncated':False,'text_sha256':d.sha(text.encode())}
        value['node_sha256']=d.sha(json.dumps(value,sort_keys=True).encode())
        return value
    title='Very Basic Calculus 000: Course Introduction';author='Ayumu爱讲数学'
    def fixture():
        nodes=[node('tv.danmaku.bili:id/title','android.widget.TextView','0/1',[0,100,50,120],title),
               node('tv.danmaku.bili:id/author_name','android.widget.TextView','0/2',[0,120,50,140],author),
               node('tv.danmaku.bili:id/video_area','android.widget.FrameLayout','0/0',[0,0,100,100]),
               node('tv.danmaku.bili:id/video_container','android.widget.FrameLayout','0/0/0',[0,0,100,100]),
               node('tv.danmaku.bili:id/video_area_float_layer_container','android.widget.FrameLayout','0/0/1',[0,0,100,100]),
               node('tv.danmaku.bili:id/collapsing_toolbar','android.widget.FrameLayout','0/0/2',[0,0,100,100]),
               node('','android.view.SurfaceView','0/0/0/0',[0,0,100,100])]
        return {'nodes':nodes,'window':{'bounds':[0,0,100,200],'focused':True,'package':base.BILI,'display':0,'type':1},
                'window_sha256':'a'*64}
    controls=[]
    for name,mutate,failed_term in [
        ('all_three_terms_true',lambda x:None,None),
        ('surface_outside_container',lambda x:x['nodes'][6].update(path='0/8'),'one_eligible_SurfaceView_under_container'),
        ('container_outside_area',lambda x:(x['nodes'][3].update(path='0/3'),x['nodes'][6].update(path='0/3/0')),'container_is_descendant_of_area'),
        ('overlay_outside_area',lambda x:x['nodes'][4].update(path='0/4'),'overlay_is_descendant_of_area'),
        ('duplicate_surface',lambda x:x['nodes'].append({**x['nodes'][6],'path':'0/0/0/1'}),'one_eligible_SurfaceView_under_container')]:
        value=fixture();mutate(value);error=None
        try:original.viewport(base,qa,value,{'activity':original.DETAILS})
        except RuntimeError as e:error=str(e)
        got=d.fixed_roles(value)
        assert (error is None)==(failed_term is None)
        if failed_term:
            assert error=='UNIQUE_CURRENT_PLAYER_STRUCTURE_REQUIRED' and got['original_three_terms'][failed_term] is False
        else:assert got['all_original_three_terms_true'] is True
        d.no_raw_ui(got)
        assert title not in json.dumps(got) and author not in json.dumps(got)
        controls.append({'name':name,'passed':True,'original_predicate_error':error})
    try:d.no_raw_ui({'outer':{'nodes':[]}})
    except RuntimeError:controls.append({'name':'raw_node_export_rejected','passed':True})
    else:raise AssertionError('raw nodes were not rejected')
    pair=fixture();pair['nodes'].append({**pair['nodes'][6],'path':'0/0/0/1'})
    got=d.fixed_roles(pair)
    assert got['original_three_terms']['one_eligible_SurfaceView_under_container'] is False
    geometry=got['geometry'];assert geometry['unique_surface_bounds_count']==1
    assert geometry['all_eligible_surfaces_cover_crop'] is True
    assert len(geometry['eligible_surfaces'])==2 and geometry['surface_selection_performed'] is False
    assert all(x['parent_path_sha256']==d.sha(b'0/0/0') for x in geometry['eligible_surfaces'])
    controls.append({'name':'two_coextensive_surfaces_reported_without_selection_or_old_gate_relaxation','passed':True})
    pair['nodes'][-1]['bounds']=[10,10,90,90]
    geometry=d.fixed_roles(pair)['geometry']
    assert geometry['unique_surface_bounds_count']==2 and geometry['all_eligible_surfaces_cover_crop'] is False
    assert [x['crop_is_inside_surface'] for x in geometry['eligible_surfaces']]==[True,False]
    d.no_raw_ui(geometry);assert title not in json.dumps(geometry) and author not in json.dumps(geometry)
    controls.append({'name':'different_surface_geometry_and_insufficient_cover_visible_as_observation','passed':True})
    print(json.dumps({'schema':1,'scope':'new structural diagnostic only','passed':len(controls),'controls':controls,
        'synthetic_node_data':True,'scope_and_hash_validation_seam':True,'original_viewport_predicate_executed':True,
        'retained_commercial_UI_read':False,'Android_or_Hepta_actions':0,'qualification_asserted':False},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
