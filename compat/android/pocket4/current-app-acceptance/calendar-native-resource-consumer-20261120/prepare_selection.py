#!/usr/bin/env python3
"""Stage the complete Calendar/Gallery source selector; do not change CURRENT."""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
GALLERY=ROOT.parent/'p4_gallery_image_consumer'
if not GALLERY.is_dir():GALLERY=ROOT.parent/'gallery-image-consumer-20261120'
HOST=Path('/home/alex/work/p4-calendar-resource-consumer-20261120-3b9d-r1')
GALLERY_HOST=Path('/home/alex/work/p4-gallery-image-consumer-20261120-3b9d-r1')
CHANGED=[1,8,9,10,11,12]
UNCHANGED=[0,2,3,4,5,6,7]


def encode(value):return(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def ref(path,target):
    data=path.read_bytes();return{'path':str(target),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def read(path,sha):
    data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==sha,str(path);return json.loads(data)
def write(name,value):
    path=ROOT/'selection-integration'/name;path.parent.mkdir(exist_ok=True);path.write_bytes(encode(value))
    return ref(path,HOST/'selection-integration'/name)


def main():
    base=read(GALLERY/'inputs/previous-selection/selection-13.json','24629e7533bf3d63c3f08ee6aa09aaffd76f4ef6673783c36c4c5290b2e294d0')
    base_routes=read(GALLERY/'inputs/previous-selection/APP-ROUTE-MAP.json','880ffd517f97a141944b363394debea843514dd7d6d3ae0b15e717d37aed0eb6')
    gallery=read(GALLERY/'selection-integration/selection-13.json','9735e7ff77263f989d42e0507d6ab70ad4b128ab5432f9afa59732d09de92b64')
    routes=read(GALLERY/'selection-integration/APP-ROUTE-MAP.json','00fb994df02de4862113eb93dfc19b628f15c0c7cbefc7dc5944470e6e1d1233')
    catalog=read(GALLERY/'selection-integration/leaf_sources.json','7e34a955419df777e3d637afe0802beb28d9ff8e6ab2cb8e5466828d58120a20')
    h=json.loads((ROOT/'HANDOFF.json').read_bytes())
    calendar_check=read(ROOT/'SOURCE-INSPECTION.json','46d4e39398db24a2239fb1da86e8bed87bee4fad36c96a45eb15b2408bca7636')
    gallery_check=read(GALLERY/'SOURCE-INSPECTION.json','3a3068e3330c0d5763fef8356cdcbea7088a2bec16b28cbcb332b0de927c15b7')
    for report,count in ((calendar_check,1),(gallery_check,5)):
        assert report['state']=='SOURCE_BOOTSTRAP_VERIFIED_RUNTIME_PENDING' and len(report['positive'])==count
        assert all(row['returncode']==0 for row in report['positive'])and all(row['refused']for row in report['negative'])
        assert report['runtime_qualified']is False and report['production_ready']is False
    assert calendar_check['positive'][0]['preparation']==h['preparation']
    assert len(catalog)==len(gallery['selected_preparations'])==13
    assert gallery['selected_preparations'][:8]==base['selected_preparations'][:8]
    catalog[1]={'index':1,'preparation':h['preparation'],'entry':h['entry']}
    catalog_ref=write('leaf_sources.json',catalog)
    calendar_inspection=ref(ROOT/'SOURCE-INSPECTION.json',HOST/'SOURCE-INSPECTION.json')
    gallery_inspection=ref(GALLERY/'SOURCE-INSPECTION.json',GALLERY_HOST/'SOURCE-INSPECTION.json')
    validation=write('SOURCE-VALIDATION.json',{
        'schema':'pocket4-calendar-gallery-source-integration-v1',
        'calendar_preparation':h['preparation'],'calendar_source_inspection':calendar_inspection,
        'gallery_source_inspection':gallery_inspection,'positive_source_inspections':6,'negative_refusals':3,
        'calendar_original_business_and_cleanup_files_byte_identical':31,
        'changed_indices':CHANGED,'unchanged_indices':UNCHANGED,'runtime_qualified':False,
        'business_qualified':False,'production_ready':False,'native_release_adoption_required':True,
        'Android_actions':0,'Main_actions':0,'CURRENT_writes':0})
    selection=copy.deepcopy(gallery)
    selection['selected_preparations']=[row['preparation']for row in catalog]
    selection['source_closure_summary']=validation
    selection['unchanged_preparations']=7
    selection['source_file_identity_scope']=(
        'Calendar reminder uses its original 50-percent CPU and 512-MiB memory predicates through a live native resource lease; '
        'the five Gallery source consumers bind the official image producer. Seven other CP3A/IHG sources are unchanged. '
        'Native release adoption and every original runtime, business and whole-app gate remain pending.')
    selection['source_selection_update']={
        'changed_indices':CHANGED,'unchanged_indices':UNCHANGED,'validation':validation,
        'catalog':catalog_ref,'current_inventory':base_routes['inputs']['current_42_inventory'],
        'calendar_source_handoff':ref(ROOT/'HANDOFF.json',HOST/'HANDOFF.json'),
        'gallery_source_handoff':ref(GALLERY/'HANDOFF.json',GALLERY_HOST/'HANDOFF.json'),
        'runtime_enabled':False,'current_Main_required':True,'native_release_adoption_required':True}
    selection_ref=write('selection-13.json',selection)
    updated=copy.deepcopy(routes)
    updated['inputs']['selected_preparations']=selection_ref
    updated['inputs']['source_selection_validation']=validation
    updated['source_selection_update']={
        'changed_indices':CHANGED,'unchanged_indices':UNCHANGED,'source_only':True,
        'runtime_enabled':False,'source_checks':validation,'native_release_adoption_required':True}
    count=0
    for row in updated['rows']:
        for leaf in row['existing_leaf_entries']:
            if leaf['selection_index']!=1:continue
            assert row['package']=='com.android.calendar'
            leaf.update(preparation=h['preparation'],entry_source=h['entry'],
                request_fields=['base_plan'],maximum_native_leaf_seconds=690,
                native_release_adoption_required=True,
                native_resource_scope='held_actual_native_parent_CPU_le_50_percent_memory_512MiB',
                actual_main_execution_pending=True,whole_app_accepted=False)
            count+=1
    assert count==1
    for index in UNCHANGED:assert selection['selected_preparations'][index]==base['selected_preparations'][index]
    assert updated['common_gates']==base_routes['common_gates']and updated['profiles']==base_routes['profiles']
    changed_rows=[]
    for old,new in zip(base_routes['rows'],updated['rows']):
        assert old['package']==new['package']and new['accepted_gates']==0 and new['runtime_qualified']is False and new['production_ready']is False
        if old!=new:changed_rows.append(new['package'])
    assert set(changed_rows)=={'com.android.calendar','com.android.gallery3d'}
    routes_ref=write('APP-ROUTE-MAP.json',updated)
    report={'schema':'pocket4-calendar-gallery-source-selection-v1','selection':selection_ref,'catalog':catalog_ref,
        'route_map':routes_ref,'source_validation':validation,'changed_indices':CHANGED,'unchanged_indices':UNCHANGED,
        'changed_package_rows':2,'unchanged_package_rows':40,'CURRENT_writes':0,
        'runtime_qualified':False,'production_ready':False,'native_release_adoption_required':True}
    write('PREPARED.json',report);print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()
