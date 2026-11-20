"""Create one narrow Calendar core successor; never adopt CURRENT or a release."""
import copy
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
HOST=Path('/home/alex/work/p4-calendar-core-id-map-20261120-3b9d-r1')
CHANGES={
    'calendar_identity.py':[
        ('info = os.fstat(fd)', 'info, mapped_owner = session.c.mapped_file_info(session.flow.view, fd, uid)'),
        ('info.st_uid == info.st_gid == uid and info.st_ino',
         '(info.st_uid, info.st_gid) == mapped_owner and info.st_ino')],
    'calendar_base.py':[
        ('info = os.fstat(fd)', 'info, mapped_owner = self.s.c.mapped_file_info(self.s.flow.view, fd, 10017)'),
        ('info.st_uid == 10017', 'info.st_uid == mapped_owner[0]')],
}


def encode(x):return (json.dumps(x,sort_keys=True,indent=2)+'\n').encode()
def pin(p,r):return {'path':str(p),'bytes':len(r),'sha256':hashlib.sha256(r).hexdigest()}
def write(relative,body):
    raw=body if type(body)is bytes else encode(body)
    (HERE/relative).write_bytes(raw)
    return pin(HOST/relative,raw)


def build():
    previous=json.loads((HERE/'inputs/predecessor.json').read_bytes())
    old=(HERE/'inputs/preparation.json').read_bytes();assert pin(previous['path'],old)==previous
    prep=json.loads(old);original_files=copy.deepcopy(prep['files']);new=[]
    addition=(HERE/'mapped_owner_addition.py').read_bytes()
    assert len(addition)==5776 and hashlib.sha256(addition).hexdigest()=='235e1a4af17f40fc9149274e017572d66ae402fcb6e1280ccbc8e8c2517de32a'
    for ref in original_files:
        name=Path(ref['path']).name
        changed=name=='app_common.py' or name in CHANGES
        raw=(HERE/('inputs/originals' if changed else 'source')/name).read_bytes()
        assert pin(ref['path'],raw)==ref
        if name=='app_common.py':raw+=addition
        elif changed:
            text=raw.decode()
            for before,after in CHANGES[name]:
                assert text.count(before)==1,(name,before)
                text=text.replace(before,after)
            raw=text.encode()
        compile(raw,str(HERE/'source'/name),'exec')
        new.append(write('source/'+name,raw))
    prep['files']=new;prep['origins'].append(previous)
    prep['previous_source_rebind']=prep['source_rebind']
    prep['source_rebind']={'previous':previous,'state':'LIVE_HELD_MAIN_CALENDAR_ID_MAP_SOURCE_ONLY',
        'changed_files':['app_common.py','calendar_identity.py','calendar_base.py'],
        'original_PM_guest_UIDs_preserved':[10061,10017,10125],
        'same_original_business_permissions_database_queries_and_cleanup':True,
        'actual_Main_execution_pending':True,'runtime_qualified':False,'whole_app_business_accepted':False}
    prep_ref=write('preparation.json',prep)
    names=('selection-13.json','leaf_sources.json','APP-ROUTE-MAP.json')
    docs={n:json.loads((HERE/'inputs'/n).read_bytes()) for n in names}
    expected={'selection-13.json':(15320,'e45c67a8fcfeb4b636eb934d833face6a6253c9a33ed954d00bc0feeca5ec064'),
        'leaf_sources.json':(6876,'1f27c1bf85c070d627b1bca57f6ca4ac56637f0c399c96dbe8420d34030b4c27'),
        'APP-ROUTE-MAP.json':(102167,'90a6d0d23dbd438bdfe492691279d112fceb78f6b3db80dbd13d2ac39d71d602')}
    for n in names:
        raw=(HERE/'inputs'/n).read_bytes();assert (len(raw),hashlib.sha256(raw).hexdigest())==expected[n]
    selection,catalog,routes=(copy.deepcopy(docs[n]) for n in names)
    assert selection['selected_preparations'][0]==previous
    entry=next(r for r in new if Path(r['path']).name=='system_entry.py')
    selection['selected_preparations'][0]=prep_ref
    catalog[0]={'index':0,'preparation':prep_ref,'entry':entry}
    update={'state':'STAGED_CALENDAR_CORE_ID_MAP_SUCCESSOR_NOT_ADOPTED','changed_indexes':[0],
        'unchanged_indexes':list(range(1,13)),'CURRENT_writes':0,'Android_actions':0,
        'runtime_qualified':False,'production_ready':False}
    selection['previous_source_selection_update']=selection.get('source_selection_update')
    selection['source_selection_update']=update
    previous_root=Path('/home/alex/work/p4-uid-mapping-consumer-20261120-3b9d-r1/selection-integration')
    selection['previous_selection']=pin(previous_root/names[0],(HERE/'inputs'/names[0]).read_bytes())
    selection_ref=write('selection-integration/selection-13.json',selection)
    for row in routes['rows']:
        for leaf in row.get('existing_leaf_entries',[]):
            if leaf.get('selection_index')==0:
                leaf.update(preparation=prep_ref,entry_source=entry,actual_main_execution_pending=True,
                    source_only_prepared=True,whole_app_accepted=False)
    routes['previous_source_selection_update']=routes.get('source_selection_update')
    routes['source_selection_update']=update
    routes['inputs']['selected_preparations']=selection_ref
    routes['previous_route_map']=pin(previous_root/names[2],(HERE/'inputs'/names[2]).read_bytes())
    assert len(catalog)==len(selection['selected_preparations'])==13 and len(routes['rows'])==42
    assert all(x['accepted_gates']==0 for x in routes['rows'])
    assert selection['selected_preparations'][1:]==docs[names[0]]['selected_preparations'][1:]
    assert catalog[1:]==docs[names[1]][1:]
    result={'schema':'pocket4-calendar-core-live-id-map-source-successor-v1','preparation':prep_ref,
        'source_files':35,'byte_identical_original_files':32,'selector':selection_ref,
        'catalog':write('selection-integration/leaf_sources.json',catalog),
        'route_map':write('selection-integration/APP-ROUTE-MAP.json',routes),
        'CURRENT_writes':0,'Android_execution':False,'runtime_qualified':False,'production_ready':False}
    write('SOURCE-REPAIR-RESULT.json',result)
    return result


if __name__=='__main__':print(json.dumps(build(),sort_keys=True))
