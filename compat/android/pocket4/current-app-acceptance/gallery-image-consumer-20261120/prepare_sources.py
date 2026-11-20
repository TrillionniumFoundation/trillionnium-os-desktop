#!/usr/bin/env python3
"""Create five immutable source preparations; all live qualification stays false."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = Path('/home/alex/work/p4-gallery-image-consumer-20261120-3b9d-r1')


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)+'\n').encode()


def ref(path, target=None):
    body=path.read_bytes()
    return {'path': str(target or path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}


def constants(path):
    # Only literal assignments needed here; no source module is executed.
    tree=ast.parse(path.read_text()); out={}
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            try:out[node.targets[0].id]=ast.literal_eval(node.value)
            except (ValueError,TypeError):pass
    return out


def main():
    entry=constants(ROOT/'src/gallery_image_entry.py')
    groups={
        'rotation':'gallery-rotation-current-preparation-20261107-r7',
        'video':'gallery-video-current-preparation-20261107-r7',
        'seek':'gallery-seek-current-preparation-20261107-r6',
        'album':'gallery-album-current-preparation-20261107-r6'}
    export=json.loads((ROOT/'inputs/source-origin-pins.json').read_bytes())
    base={}
    for path in sorted((ROOT/'src').glob('*.py')):
        name='source/'+path.name; base[name]=ref(path,HOST/name)
    for path in sorted((ROOT/'generated/shared').glob('*.py')):
        name=path.relative_to(ROOT).as_posix();base[name]=ref(path,HOST/name)
    preparations={};destination=ROOT/'preparations';destination.mkdir(exist_ok=True)
    for case in ('identity',*groups):
        files=dict(base);external=[];prior=None;origins=[];runtime_consumers=[]
        if case!='identity':
            for role in sorted({'rotation',case}):
                for path in sorted((ROOT/'generated'/role).glob('*.py')):
                    name=path.relative_to(ROOT).as_posix();files[name]=ref(path,HOST/name)
                for key,value in sorted(export['files'].items()):
                    if key.startswith(groups[role]+'/'):
                        origins.append({'relative_source':key,'origin':value['origin'],
                            'bytes':value['bytes'],'sha256':value['sha256']})
            original_preparation=(ROOT/'inputs/original-preparations'/(groups[case]+'.json')).read_bytes()
            original_pin=export['preparations'][groups[case]]
            assert len(original_preparation)==original_pin['bytes'] and hashlib.sha256(original_preparation).hexdigest()==original_pin['sha256']
            old=json.loads(original_preparation)
            prior=old['prior_cleanup'];external.append(prior)
            api=constants(ROOT/'generated/rotation/gallery_rotation_api.py')
            runtime_consumers=[api['APP'],api['BACKEND']]
            # These are reviewed production candidates, still separate from
            # the live installed files. OriginalAPIs checks installed identity
            # at execution; source inspection must not accept the old live
            # consumer as the new candidate or pretend deployment occurred.
            external.extend({**row,'path':'/home/alex/work/pocket4-android-final/consumers/'+Path(row['path']).name}
                            for row in runtime_consumers)
            if case=='rotation':
                external.append({'path':'/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/fixtures/rotation/owned-media.apk',
                    'bytes':24780,'sha256':'d68bbcc45df268ab97866a9477d86e69cf01aa3efb5be6666c8fa607daeb5b6a'})
            else:
                external.extend(old['external_fixture_refs'][name] for name in
                    ('owned-media.apk','contract.json','fixture-build-result.json','task-option-proof.json'))
        prep={
            'schema':'pocket4-gallery-image-source-v1','case':case,
            'state':'CURRENT_IMAGE_CONSUMER_SOURCE_PREPARED_RUNTIME_PENDING',
            'files':files,'external_refs':external,'prior_cleanup':prior,'origins':origins,
            'required_installed_consumers':runtime_consumers,
            'producer_cli_path':entry['CLI_PATH'],'control_socket':entry['SOCKET'],
            'custody_protocol':entry['CUSTODY_PROTOCOL'],'native_release_required':True,
            'common':entry['COMMON'],'held':entry['HELD'],
            'entry':base['source/gallery_image_entry.py'],
            'request_schema':'pocket4-gallery-image-request-v1',
            'request_fields':['schema','baseline','qualification','output','native_release'],
            'imported_image_custody_accepted':False,'standalone_Gallery_installation_allowed':False,
            'execute_success_state':'CURRENT_IMAGE_OBSERVED_BUSINESS_PENDING' if case=='identity' else 'CURRENT_IMAGE_SCOPE_AND_CLEANUP_VERIFIED',
            'original_business_seconds':600,'original_cleanup_seconds':120,
            'each_current_image_capture_seconds':340,
            'runtime_qualified':False,'business_qualified':False,'data_continuity_qualified':False,
            'production_ready':False,'historical_runtime_authority_transferred':False,
            'actual_Main_execution_pending':True,'whole_app_business_accepted':False,
            'legacy_install_and_ART_receipts_consumed':False,
            'inspection_mode':'inspect-source','execution_mode':'execute'}
        path=destination/(case+'.json');path.write_bytes(encoded(prep))
        preparations[case]=ref(path,HOST/'preparations'/path.name)
    handoff={'schema':'pocket4-gallery-image-source-handoff-v1','preparations':preparations,
             'source_files':len(list((ROOT/'generated').rglob('*.py')))+len(list((ROOT/'src').glob('*.py'))),
             'entry':base['source/gallery_image_entry.py'],
             'changed_selection_indices':[8,9,10,11,12],'unchanged_selection_indices':list(range(8)),
             'runtime_qualified':False,'business_qualified':False,'production_ready':False,
             'actual_Main_execution_pending':True}
    (ROOT/'HANDOFF.json').write_bytes(encoded(handoff))
    print(json.dumps(handoff,sort_keys=True))


if __name__=='__main__':
    main()
