"""Prepare an isolated Settings source candidate, with native admission pending."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
HOST=Path('/home/alex/work/p4-settings-pages-consumer-20261120-3b9d-r1')
def ref(path,raw):return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def build():
    files=[]
    for p in sorted((ROOT/'source').glob('*.py')):
        raw=p.read_bytes();compile(raw,str(p),'exec');files.append(ref(HOST/'source'/p.name,raw))
    original_root=Path('/home/alex/work/p4-calendar-core-id-map-20261120-3b9d-r1/source')
    origins=[ref(original_root/name,(ROOT/'source'/name).read_bytes())
             for name in ('app_common.py','app_flow.py','app_runtime.py')]
    origins += [ref(HOST/name,(ROOT/name).read_bytes())
                for name in ('manifest-observation.json','resource-observation.json')]
    packet={'schema':'pocket4-settings-pages-preparation-v1','files':files,'origins':origins,
        'route':'settings_supported_pages','native_profile':'settings-pages',
        'business_consumer_entrypoints_present':True,'code_entrypoints_complete':False,
        'native_release_binding':'PENDING_DEDICATED_NATIVE_SETTINGS_PROFILE_AND_ROOT_ADOPTION',
        'required_native_module':'native_settings_release.py',
        'source_publication_authorizes_runtime':False,'Android_execution_authorized_by_publication':False,
        'actual_Main_execution_pending':True,'whole_app_business_accepted':False,'runtime_qualified':False,
        'credit_scope':'settings.pages only after actual page, image, permission, identity and cleanup verification',
        'remaining_original_gates':['settings.roundtrip','settings.permissions','identity','lifecycle','stability',
                                    'data_permissions','release_scope','ui_observation'],
        'canonical_migration_pending':True}
    raw=(json.dumps(packet,sort_keys=True,indent=2)+'\n').encode();(ROOT/'preparation.json').write_bytes(raw)
    return ref(HOST/'preparation.json',raw)

if __name__=='__main__':print(json.dumps(build(),sort_keys=True))
