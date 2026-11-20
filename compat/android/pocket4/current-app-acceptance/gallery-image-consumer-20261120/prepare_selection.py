#!/usr/bin/env python3
"""Create a complete source-only selector/catalog without changing CURRENT."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = Path('/home/alex/work/p4-gallery-image-consumer-20261120-3b9d-r1')
PREVIOUS_ROOT = Path('/home/alex/work/p4-cp3a-bootstrap-20261120-runtimeaudit-r1/selection-integration')
CASES = ('identity', 'rotation', 'video', 'seek', 'album')
PREVIOUS = {
    'selection-13.json': (14276, '24629e7533bf3d63c3f08ee6aa09aaffd76f4ef6673783c36c4c5290b2e294d0'),
    'APP-ROUTE-MAP.json': (99043, '880ffd517f97a141944b363394debea843514dd7d6d3ae0b15e717d37aed0eb6'),
}


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)+'\n').encode()


def reference(path, host_path):
    body = path.read_bytes()
    return {'path':str(host_path), 'bytes':len(body), 'sha256':hashlib.sha256(body).hexdigest()}


def write(name, value):
    path = ROOT/'selection-integration'/name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(encoded(value))
    return reference(path, HOST/'selection-integration'/name)


def main():
    original = {}; previous_refs = {}
    for name, (size, sha) in PREVIOUS.items():
        path = ROOT/'inputs/previous-selection'/name
        ref = reference(path, PREVIOUS_ROOT/name)
        assert (ref['bytes'], ref['sha256']) == (size, sha), name
        original[name] = json.loads(path.read_bytes()); previous_refs[name] = ref
    selection = original['selection-13.json']; routes = original['APP-ROUTE-MAP.json']
    assert len(selection['selected_preparations']) == 13 and selection['selection_only'] is True
    assert len(routes['rows']) == 42 and routes['inputs']['selected_preparations'] == previous_refs['selection-13.json']
    handoff = json.loads((ROOT/'HANDOFF.json').read_bytes())
    inspection_path = ROOT/'SOURCE-INSPECTION.json'
    inspection = json.loads(inspection_path.read_bytes())
    assert inspection['state'] == 'SOURCE_BOOTSTRAP_VERIFIED_RUNTIME_PENDING'
    assert inspection['runtime_qualified'] is False and inspection['production_ready'] is False
    assert len(inspection['positive']) == 5 and inspection['negative']
    assert all(row['returncode'] == 0 for row in inspection['positive'])
    assert all(row['refused'] is True for row in inspection['negative'])
    by_case = {row['case']:row['preparation'] for row in inspection['positive']}
    assert by_case == handoff['preparations']
    source_inspection = reference(inspection_path, HOST/'SOURCE-INSPECTION.json')
    handoff_ref = reference(ROOT/'HANDOFF.json', HOST/'HANDOFF.json')
    all_refs = selection['selected_preparations'][:8]+[handoff['preparations'][case] for case in CASES]
    catalog = []
    for index, prep_ref in enumerate(all_refs):
        if index < 8:
            candidates = [leaf['entry_source'] for row in routes['rows'] for leaf in row['existing_leaf_entries']
                          if leaf['selection_index'] == index]
            assert candidates and all(pin == candidates[0] for pin in candidates)
            entry = candidates[0]
        else:
            prep_path = ROOT/'preparations'/(CASES[index-8]+'.json')
            assert reference(prep_path, prep_ref['path']) == prep_ref
            prep = json.loads(prep_path.read_bytes()); entry = prep['entry']
            assert prep['native_release_required'] is True and prep['actual_Main_execution_pending'] is True
        catalog.append({'index':index, 'preparation':prep_ref, 'entry':entry})
    catalog_ref = write('leaf_sources.json', catalog)
    successor = copy.deepcopy(selection)
    successor['previous_selection'] = previous_refs['selection-13.json']
    successor['previous_source_closure_summary'] = successor['source_closure_summary']
    successor['source_closure_summary'] = source_inspection
    successor['selected_preparations'] = all_refs
    successor['unchanged_preparations'] = 8
    successor['source_file_identity_scope'] = (
        'Five Gallery source consumers now use the original image custody producer and the current native release lease. '
        'The first eight CP3A/IHG source selections are unchanged. Actual native release adoption, coherent current Main, '
        'finite business execution, cleanup and whole-app acceptance remain pending.')
    successor['source_selection_update'] = {
        'changed_indices':list(range(8,13)), 'unchanged_indices':list(range(8)),
        'validation':source_inspection, 'source_handoff':handoff_ref, 'catalog':catalog_ref,
        'runtime_enabled':False, 'current_Main_required':True, 'native_release_adoption_required':True,
        'current_inventory':routes['inputs']['current_42_inventory']}
    successor.update(source_only=True, runtime_qualified=False, production_ready=False)
    selection_ref = write('selection-13.json', successor)
    updated = copy.deepcopy(routes)
    updated['previous_route_map'] = previous_refs['APP-ROUTE-MAP.json']
    updated['inputs']['selected_preparations'] = selection_ref
    updated['inputs']['source_selection_validation'] = source_inspection
    updated['source_selection_update'] = {
        'changed_indices':list(range(8,13)), 'unchanged_indices':list(range(8)),
        'source_only':True, 'runtime_enabled':False, 'source_checks':source_inspection,
        'native_release_adoption_required':True}
    count = 0
    for row in updated['rows']:
        for leaf in row['existing_leaf_entries']:
            index = leaf['selection_index']
            assert leaf['preparation'] == selection['selected_preparations'][index]
            if index < 8:
                continue
            assert row['package'] == 'com.android.gallery3d'
            case = CASES[index-8]
            leaf['preparation'] = all_refs[index]
            leaf['entry_source'] = catalog[index]['entry']
            leaf['request_schema'] = 'pocket4-gallery-image-request-v1'
            leaf['request_fields'] = ['schema','baseline','qualification','output','native_release']
            leaf['result_schema'] = 'pocket4-gallery-image-scope-v1'
            leaf['execute_success_state'] = ('CURRENT_IMAGE_OBSERVED_BUSINESS_PENDING' if case == 'identity'
                else 'CURRENT_IMAGE_SCOPE_AND_CLEANUP_VERIFIED')
            leaf['stdout_result_is_FilePin'] = True
            leaf['maximum_native_leaf_seconds'] = 1530
            leaf['native_binding_protocol'] = 'droidloom-gallery-image-custody-v1'
            leaf['native_release_adoption_required'] = True
            leaf['actual_main_execution_pending'] = True
            leaf['whole_app_accepted'] = False
            count += 1
    assert count == 5
    assert updated['common_gates'] == routes['common_gates'] and updated['profiles'] == routes['profiles']
    for old, new in zip(routes['rows'], updated['rows']):
        assert old['package'] == new['package']
        assert new['accepted_gates'] == 0 and new['runtime_qualified'] is False and new['production_ready'] is False
        if old['package'] != 'com.android.gallery3d':
            assert old == new
    route_ref = write('APP-ROUTE-MAP.json', updated)
    report = {'schema':'pocket4-gallery-source-selection-v1', 'selection':selection_ref, 'route_map':route_ref,
        'catalog':catalog_ref, 'previous_selection':previous_refs['selection-13.json'],
        'previous_route_map':previous_refs['APP-ROUTE-MAP.json'], 'source_inspection':source_inspection,
        'changed_indices':list(range(8,13)), 'unchanged_indices':list(range(8)),
        'changed_package_rows':1, 'unchanged_package_rows':41,
        'CURRENT_writes':0, 'runtime_qualified':False, 'production_ready':False,
        'native_release_adoption_required':True}
    write('PREPARED.json', report)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
