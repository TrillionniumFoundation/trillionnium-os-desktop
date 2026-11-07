#!/usr/bin/env python3
"""Review fixed safe historical role counts locally; no raw UI or device access."""
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
WORK=HERE.parent
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(path):
    raw=path.read_bytes();return {'bytes':len(raw),'sha256':sha(raw)}

def main():
    source=WORK/'android-ihg-launch01-public-roles-reader-01/read_roles.py'
    raw=source.read_bytes()
    assert len(raw)==19209 and sha(raw)=='e6413134cb585885c45ad36a644f04170193bb948216612d2c8559c6c0233aa9'
    module=types.ModuleType('fixed_historical_reader');module.__file__=str(source)
    exec(compile(raw,str(source),'exec'),module.__dict__)
    path=WORK/'root-recovery-20261104-02/evidence/ihg-launch01-public-roles-read01/stdout.log'
    raw=path.read_bytes()
    assert len(raw)==12714 and sha(raw)=='ba438fee676cfdfad2bb8bfbf8e630fccc1d0d6ffc8dca13399b7538e19d02cc'
    value=json.loads(raw)
    assert value['state']=='RETAINED_IHG_PUBLIC_ROLE_COUNTS_ONLY'
    assert value['source_manifest_sha256']==module.SOURCE_SHA and value['flow_nonce']==module.NONCE
    assert value['assessment_nonce']==module.INSPECT_NONCE and value['canonical_helper_wire_sha256']==module.INSPECT_WIRE
    assert value['input_file_pins']==[{'path':str(p),'bytes':size,'sha256':digest} for p,(size,digest) in module.PINS.items()]
    assert value['node_count']==63 and value['complete_tree_verified'] is True and value['window_ready'] is True
    assert value['owned_task_retired']==1002 and value['old_task_ids_preserved']==[851]
    assert value['all_observations_from_retired_task'] is True
    assert value['Android_or_process_actions']==0
    for name in ('raw_commercial_tree_or_user_text_or_pixels_exported','runtime_qualification_asserted',
                 'current_runtime_or_future_action_authority','hotel_search_login_or_booking_verified',
                 'whole_app_production_ready'):
        assert value[name] is False,name
    counts=value['public_role_counts'];roles=counts['fixed_public_role_queries']
    assert set(roles)==set(module.PUBLIC_ROLES)
    assert all(roles[k]['fixed_public_variants']==list(v) for k,v in module.PUBLIC_ROLES.items())
    expected={'search_tab':(2,2,1,0,1,1,1,{'android.widget.FrameLayout':1,'android.widget.TextView':1}),
              'home_tab':(1,1,0,0,0,1,0,{'android.widget.TextView':1})}
    for role,row in roles.items():
        assert row['current_or_future_action_authority'] is False
        fields=('matching_visible_nonpassword_nodes','eligible_matching_nodes','eligible_clickable_self_count',
                'eligible_direct_clickable_parent_count','distinct_self_or_direct_parent_candidates',
                'via_complete_public_text_count','via_complete_public_description_count','known_class_counts')
        assert tuple(row[f] for f in fields)==expected.get(role,(0,0,0,0,0,0,0,{})),role
        assert row['editable_matching_nodes']==0
    assert set(counts['fixed_public_resource_queries'])==set(module.PUBLIC_RESOURCES)
    assert all(all(x==0 for x in row.values()) for row in counts['fixed_public_resource_queries'].values())
    assert sum(counts['fixed_known_class_counts'].values())+counts['other_class_count']==63
    assert counts['unknown_labels_identifiers_paths_or_coordinates_exported'] is False
    assert counts['action_selection_performed'] is False and counts['query_catalog_not_asserted_observed'] is True
    result={'schema':1,'state':'HISTORICAL_PUBLIC_SEARCH_ROLE_COUNT_REVIEW_PASS',
        'actual_stdout':{'path':str(path),**pin(path)},'reader_source':{'path':str(source),**pin(source)},
        'all_six_fixed_input_pins_match_source':True,'retired_task':1002,'preexisting_task_preserved':[851],
        'complete_tree_node_count':63,'search_role':roles['search_tab'],'home_role':roles['home_tab'],
        'all_other_fixed_role_and_resource_queries_zero':True,
        'cross_field_class_label_clickability_association_available':False,
        'literal_label_case_or_node_path_available':False,
        'next_source_scope':'New owned task, fresh complete inspection, one unique self-clickable public Search role, original R1 fresh click checks, independent post inspection and exact task cleanup',
        'no_historical_node_task_or_wire_reuse_as_action_authority':True,
        'hotel_search_login_booking_whole_app_qualified':False,'Hepta_Android_or_input_actions':0}
    output=HERE/'review.json';data=(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()
    if output.exists():assert output.read_bytes()==data
    else:output.open('xb').write(data)
    print(json.dumps({'review':str(output),**pin(output)},indent=2))

if __name__=='__main__':main()
