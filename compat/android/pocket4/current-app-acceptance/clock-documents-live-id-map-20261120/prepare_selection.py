"""Stage the four new source graphs over the reviewed Gallery/Calendar proposal.

This never reads or writes CONTINUATION_CURRENT and never adopts a release.
"""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = Path('/home/alex/work/p4-uid-mapping-consumer-20261120-3b9d-r1')
BASE_HOST = Path('/home/alex/work/p4-calendar-resource-consumer-20261120-3b9d-r1/selection-integration')
BASE_PINS = {
    'selection-13.json': (12745, '9db3ea2a573326af39676f6366e49b9dbad28efde3ea5486223b15f2bc17d295'),
    'leaf_sources.json': (5909, '4773fb83a547171c7682e9bc43457148bdd842aa63a5439f6de1c9d578e52d7a'),
    'APP-ROUTE-MAP.json': (83620, '6d5d20e97c2de399988951d45a41481e71191fe128553a37e0b4ba5c8668d30f'),
}


def reference(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write(name, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()
    (HERE / 'selection-integration' / name).write_bytes(raw)
    return reference(HOST / 'selection-integration' / name, raw)


def build():
    documents = {}
    for name, pin in BASE_PINS.items():
        raw = (HERE / 'inputs/prior-selection' / name).read_bytes()
        assert (len(raw), hashlib.sha256(raw).hexdigest()) == pin
        documents[name] = json.loads(raw)
    selection = copy.deepcopy(documents['selection-13.json'])
    catalog = copy.deepcopy(documents['leaf_sources.json'])
    routes = copy.deepcopy(documents['APP-ROUTE-MAP.json'])
    changed = json.loads((HERE / 'PREPARATIONS.json').read_bytes())
    for item in changed:
        index, ref = item['index'], item['preparation']
        raw = (HERE / 'preparations' / Path(ref['path']).name).read_bytes()
        assert reference(ref['path'], raw) == ref
        prep = json.loads(raw)
        entry_name = Path(catalog[index]['entry']['path']).name
        entry = next(row for row in prep['files'] if Path(row['path']).name == entry_name)
        selection['selected_preparations'][index] = ref
        catalog[index] = {'index': index, 'preparation': ref, 'entry': entry}
        for row in routes['rows']:
            for leaf in row.get('existing_leaf_entries', []):
                if leaf.get('selection_index') == index:
                    leaf['preparation'], leaf['entry_source'] = ref, entry
                    leaf['actual_main_execution_pending'] = True
                    leaf['source_only_prepared'] = True
                    leaf['whole_app_accepted'] = False
    assert len(selection['selected_preparations']) == len(catalog) == 13
    assert [i for i in range(13) if selection['selected_preparations'][i] !=
            documents['selection-13.json']['selected_preparations'][i]] == [4, 5, 6, 7]
    assert len(routes['rows']) == 42 and all(row['accepted_gates'] == 0 for row in routes['rows'])
    update = {'state': 'STAGED_FOUR_LIVE_ID_MAP_SOURCE_SUCCESSORS_NOT_ADOPTED',
              'changed_indexes': [4, 5, 6, 7], 'unchanged_indexes': [0, 1, 2, 3, 8, 9, 10, 11, 12],
              'CURRENT_writes': 0, 'native_release_adopted': False, 'Android_actions': 0,
              'runtime_qualified': False, 'production_ready': False}
    selection['previous_source_selection_update'] = selection.get('source_selection_update')
    selection['source_selection_update'] = update
    selection['previous_selection'] = {'path': str(BASE_HOST / 'selection-13.json'),
                                      'bytes': BASE_PINS['selection-13.json'][0],
                                      'sha256': BASE_PINS['selection-13.json'][1]}
    selection['CURRENT_writes'] = 0
    selection['selection_only'] = selection['source_only'] = True
    (HERE / 'selection-integration').mkdir(exist_ok=True)
    selection_ref = write('selection-13.json', selection)
    catalog_ref = write('leaf_sources.json', catalog)
    routes['previous_source_selection_update'] = routes.get('source_selection_update')
    routes['source_selection_update'] = update
    routes['inputs']['selected_preparations'] = selection_ref
    routes['previous_route_map'] = {'path': str(BASE_HOST / 'APP-ROUTE-MAP.json'),
                                  'bytes': BASE_PINS['APP-ROUTE-MAP.json'][0],
                                  'sha256': BASE_PINS['APP-ROUTE-MAP.json'][1]}
    route_ref = write('APP-ROUTE-MAP.json', routes)
    return {'selection': selection_ref, 'compiled_catalog_candidate': catalog_ref, 'route_map': route_ref,
            'CURRENT_writes': 0, 'runtime_qualified': False, 'production_ready': False}


if __name__ == '__main__':
    print(json.dumps(build(), sort_keys=True))
