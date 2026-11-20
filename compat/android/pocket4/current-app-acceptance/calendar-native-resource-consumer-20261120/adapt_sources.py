#!/usr/bin/env python3
"""Create the Calendar resource successor without changing business or cleanup."""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
HOST=Path('/home/alex/work/p4-calendar-resource-consumer-20261120-3b9d-r1')
GUARD_BYTES=29175
GUARD_SHA='77d8a3439f5d544c67de9aa4965e4007474d7a4737ac86df0329010319dd4114'


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def pin(path,target):
    body=path.read_bytes()
    return {'path':str(target),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}


def main():
    origins=json.loads((ROOT/'SOURCE-ORIGINS.json').read_bytes())
    original=(ROOT/'original-preparation.json').read_bytes()
    assert len(original)==origins['preparation']['bytes'] and hashlib.sha256(original).hexdigest()==origins['preparation']['sha256']
    prep=json.loads(original);output=ROOT/'source';output.mkdir(exist_ok=True)
    changed=[]
    for name,reference in origins['files'].items():
        raw=(ROOT/'originals'/name).read_bytes()
        assert len(raw)==reference['bytes'] and hashlib.sha256(raw).hexdigest()==reference['sha256']
        text=raw.decode()
        if name=='calendar_resources.py':
            assert text.count('def own_resources():')==1
            text=text.replace('def own_resources():','def _local_own_resources():')
            text+='\n\n'+(ROOT/'held_resource_binding.py').read_text()
        elif name=='system_entry.py':
            old="""        actual, outcome = components['system_case.py'].execute(c, request['base_plan'], components)
        print(json.dumps({'result': actual, 'state': outcome['state'],
            'case_business_success_verified': outcome['case_business_success_verified'],
            'whole_app_business_accepted': False}, sort_keys=True))
        return 0 if outcome['case_business_success_verified'] else 1"""
            new="""        native_release = components['native_calendar_release.py']
        # Discovering CURRENT is not admission: the lease independently opens
        # the original locks and validates the exact adopted native release.
        with native_release.bind_current(prep) as release:
            resource_scope = release.admit_owned_leaf_resources()
            c.need(type(resource_scope) is native_release.OwnedLeafResources,
                   'EXACT_LIVE_NATIVE_CALENDAR_RESOURCE_SCOPE_CLASS')
            components['calendar_resources.py'].bind_resource_scope(resource_scope)
            release.guard()
            actual, outcome = components['system_case.py'].execute(c, request['base_plan'], components)
            c.read_ref(request_ref); release.guard()
            print(json.dumps({'result': actual, 'state': outcome['state'],
                'case_business_success_verified': outcome['case_business_success_verified'],
                'whole_app_business_accepted': False}, sort_keys=True))
            return 0 if outcome['case_business_success_verified'] else 1"""
            assert text.count(old)==1;text=text.replace(old,new)
        if text.encode()!=raw:changed.append(name)
        compile(text,name,'exec');(output/name).write_text(text)
    assert changed==['calendar_resources.py','system_entry.py']
    guard=(ROOT/'native_calendar_release.py').read_bytes()
    assert len(guard)==GUARD_BYTES and hashlib.sha256(guard).hexdigest()==GUARD_SHA
    (output/'native_calendar_release.py').write_bytes(guard)
    # Only the two admission/observation modules change. The complete case,
    # planner, guards, UI, proof requirements and cleanup remain byte identical.
    for name in origins['files']:
        if name not in changed:assert (output/name).read_bytes()==(ROOT/'originals'/name).read_bytes()
    prep['files']=[pin(path,HOST/'source'/path.name)for path in sorted(output.glob('*.py'))]
    assert len(prep['files'])==34
    prep['origins'].append(origins['preparation'])
    prep['previous_source_rebind']=prep['source_rebind']
    prep['source_rebind']={
        'schema':'pocket4-calendar-native-resource-source-v1','source_only':True,
        'original_selected_preparation':origins['preparation'],
        'original_business_and_cleanup_files_byte_identical':31,
        'changed_source_modules':changed,'native_release_required_for_execute':True,
        'native_source_selection_index':1,'original_CPU_max_percent':50,
        'original_memory_max_bytes':536870912,'maximum_native_leaf_seconds':690,
        'runtime_qualified':False,'whole_app_business_accepted':False,'Android_actions':0}
    prep['source_graph_generation']='CP3A-calendar-held-resource-20261120-3b9d-r1'
    prep['actual_Main_execution_pending']=True
    (ROOT/'preparation.json').write_bytes(encoded(prep))
    handoff={'schema':'pocket4-calendar-native-resource-source-handoff-v1',
        'preparation':pin(ROOT/'preparation.json',HOST/'preparation.json'),
        'entry':pin(output/'system_entry.py',HOST/'source/system_entry.py'),
        'native_validator':pin(output/'native_calendar_release.py',HOST/'source/native_calendar_release.py'),
        'unchanged_source_files':31,'changed_existing_modules':changed,
        'request_fields':['base_plan'],'source_only':True,'runtime_qualified':False,
        'business_qualified':False,'production_ready':False,'Android_actions':0,'CURRENT_writes':0}
    (ROOT/'HANDOFF.json').write_bytes(encoded(handoff));print(json.dumps(handoff,sort_keys=True))


if __name__=='__main__':main()
