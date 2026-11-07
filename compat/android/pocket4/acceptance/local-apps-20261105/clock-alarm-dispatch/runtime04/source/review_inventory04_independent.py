#!/usr/bin/env python3
"""Independently summarize four already captured Clock process snapshots.

No device, process, memory, Android, or UI reads. Original completeness fields are
retained; this does not grant a whole-runtime or business qualification.
"""
from pathlib import Path
from collections import Counter
import hashlib,json,re

ROOT=Path(__file__).resolve().parent
INPUT=ROOT/'saved-export04.json'
# Exact original export pin, kept separate from every derived report.
INPUT_SHA='d6131a5f9a4c3907717caa3d013cfa42afe26b78d808f5d5f5d0c36a5ec95706'
RUNTIME=ROOT.parent/'runtime04-label-corrected/actual-result04-original.json'
RUNTIME_SHA='ef32be14277156c79f653c942c9d55b32addc8b293ad6e886c3b2508173c5143'
UI=ROOT/'alarm04-result-original.json'
UI_SHA='d67ee63b7762adb2a5f4ee66455d15dbd50ab1c41a46683f9172ec8b513b2cec'

def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def read(path,pin):
    raw=path.read_bytes();need(sha(raw)==pin,'ORIGINAL_INPUT_CHANGED');return json.loads(raw)

def main():
    data=read(INPUT,INPUT_SHA);runtime=read(RUNTIME,RUNTIME_SHA);ui=read(UI,UI_SHA)
    need(data['UI_result_sha256']==UI_SHA and data['runtime_result_sha256']==RUNTIME_SHA,
         'EXPORT_NOT_BOUND_TO_TWO_ORIGINALS')
    need(runtime['sampler']['thread_joined'] is True and runtime['sampler']['sample_count']==626
         and runtime['sampler']['scan_error_count']==0,'ACTUAL_CAPTURE_TERMINAL_CHANGED')
    need(ui['state']=='FAILED' and ui['actual_firing_verified'] is True
         and ui['actual_alarm_notification_posted'] is True
         and ui['owned_alarm_cleanup_verified'] is True,'ORIGINAL_UI_SCOPE_CHANGED')
    index=data['sample_index'];need(len(index)==626,'SAMPLE_INDEX_COUNT')
    indexed={s['name']:s for s in index};need(len(indexed)==626,'DUPLICATE_SAMPLE')
    need(all(not s['errors'] for s in index),'ACTUAL_INDEX_HAS_ERRORS')
    selected=data['runtime_selections'];need(len(selected)==4,'EXACT_FOUR_SELECTED_SNAPSHOTS')
    inventory={};snapshots=[];generations={};all_unresolved=[]
    for name,entry in sorted(selected.items()):
        row=entry['row'];host=row['host_identity'];parts=name.split(':')
        need(len(parts)==3 and parts[2] in ('first','last')
             and parts[:2]==[str(host['pid']),str(host['start'])],'GENERATION_LABEL_MISMATCH')
        need(row['android_uid']==10063 and row['package']==row['process_name']=='com.android.deskclock'
             and host['uid']==['10063']*4 and host['exe']=='/system/bin/app_process64'
             and host['nspid'][0]==str(host['pid']) and len(host['nspid'])==2,'EXACT_CLOCK_PROCESS_SCOPE')
        need(row['full_mapping_snapshot'] is True and row['stable_process_identity'] is True
             and row['maps_before_after_equal'] is True,'SELECTED_SNAPSHOT_NOT_STABLE')
        saved=indexed[entry['source_name']]
        need(saved['bytes']==entry['source_bytes'] and saved['sha256']==entry['source_sha256'],
             'SELECTED_FILE_INDEX_NOT_BOUND')
        matches=[x for x in saved['rows'] if x['pid']==str(host['pid']) and x['start']==str(host['start'])]
        need(len(matches)==1 and matches[0]['utc']==row['utc'],'SELECTED_ROW_INDEX_NOT_BOUND')
        objects=row['mapped_code_objects'];need(len({o['path'] for o in objects})==len(objects),'DUPLICATE_OBJECT_PATH')
        elf={o['path']:o for o in objects if o.get('elf') is True}
        need(len(elf)==(376 if parts[2]=='first' else 381),'ACTUAL_ELF_COUNT_CHANGED')
        for path,obj in elf.items():
            need((obj['machine'],obj['architecture'],obj['bits'],obj['byte_order'])==(62,'x86_64',64,'little')
                 and re.fullmatch('[0-9a-f]{64}',obj['sha256']) and obj['identity']['st_size']>0,
                 'ELF_HEADER_OR_WHOLE_HASH_INCOMPLETE')
            selected_obj={'path':path,'sha256':obj['sha256'],'bytes':obj['identity']['st_size'],
                'machine':obj['machine'],'architecture':obj['architecture'],'bits':obj['bits']}
            need(path not in inventory or inventory[path]==selected_obj,'ELF_HASH_SIZE_OR_MACHINE_DRIFT')
            inventory[path]=selected_obj
        nonelf=[o for o in objects if o.get('elf') is not True]
        need(len(nonelf)==1 and nonelf[0]['path']=='/vendor/overlay/DroidloomFrameworkDisplayOverlay.apk'
             and nonelf[0]['content_read']=='first_64_code_bytes_only' and 'sha256' not in nonelf[0],
             'NON_ELF_HEADER_ONLY_OBJECT_CHANGED')
        unresolved=row['unresolved_executable_objects'];unresolved_paths={o['path'] for o in unresolved}
        need(len(unresolved)==2,'EXPECTED_UNRESOLVED_LABEL_COUNT')
        unresolved_maps=[m for m in row['engine_mappings'] if m['path'] in unresolved_paths]
        need(unresolved_paths=={m['path'] for m in unresolved_maps}
             and all(m['permissions']=='r--s' for m in unresolved_maps),'UNRESOLVED_ENTRY_PERMISSIONS_CHANGED')
        all_unresolved.extend(unresolved)
        need(row['non_filesystem_mapping_contents_read'] is False,'PROCESS_MEMORY_READ_SCOPE_CHANGED')
        need({m['path'] for m in entry['named_executable_mappings']}=={
             '[anon_shmem:dalvik-zygote-jit-code-cache]','[anon_shmem:dalvik-jit-code-cache]','[vdso]','[vsyscall]'},
             'NAMED_NON_FILESYSTEM_EXECUTABLE_SET_CHANGED')
        key=':'.join(parts[:2]);generations.setdefault(key,{})[parts[2]]=set(elf)
        snapshots.append({'generation':key,'which':parts[2],'source_name':entry['source_name'],
            'source_sha256':entry['source_sha256'],'utc':row['utc'],'phase':row['phase'],
            'whole_hashed_ELF_count':len(elf),'header_only_non_ELF_count':len(nonelf),
            'fd_count':row['fd_count'],'status':row['status'],'executable':row['executable'],
            'stable_process_identity':True,'maps_before_after_equal':True,
            'original_automatic_engine_qualification':row['actual_engine_exclusion_automatically_qualified']})
    expected_added={'/vendor/lib64/dri/radeonsi_dri.so','/vendor/lib64/hw/mapper.minigbm.so',
        '/vendor/lib64/libdmabufheap.so','/vendor/lib64/libgbm_mesa.so','/vendor/lib64/libminigbm_gralloc.so'}
    need(len(generations)==2 and len(inventory)==381,'TWO_GENERATION_ELF_UNION_CHANGED')
    for pair in generations.values():
        need(set(pair)=={'first','last'} and pair['first']<=pair['last']
             and pair['last']-pair['first']==expected_added,'OBSERVED_MAP_DELTA_CHANGED')
    need(len({frozenset(p['last']) for p in generations.values()})==1,'GENERATIONS_HAVE_DIFFERENT_ELF_UNIONS')
    counts=Counter((r['pid'],r['start']) for s in index for r in s['rows'])
    inv={'schema':'clock-runtime04-reviewed-ELF-inventory-v1','input_sha256':INPUT_SHA,
         'objects':[inventory[k] for k in sorted(inventory)],'whole_ELF_objects':381,
         'process_memory_or_JIT_contents_included':False}
    invraw=encode(inv)
    report={'schema':'clock-runtime04-independent-saved-review-v1','inputs':{
        'saved_export':INPUT_SHA,'runtime_original':RUNTIME_SHA,'UI_original':UI_SHA},
        'new_device_or_UI_calls':0,'original_files_modified':False,'index_count':626,
        'index_error_count':0,'sample_rows_by_generation':{':'.join(k):v for k,v in counts.items()},
        'selected_snapshots':snapshots,'stable_full_counts_by_generation':data['stable_full_counts_by_generation'],
        'all_observed_ELF_headers_x86_64':True,'whole_hashed_ELF_union_count':381,
        'ELF_hash_or_size_drift':False,'later_added_paths':sorted(expected_added),
        'ELF_inventory_sha256':sha(invraw),'original_stable_complete_mapping_samples':runtime['sampler']['stable_complete_mapping_samples'],
        'original_automatic_runtime_qualification':runtime['runtime_identity_automatically_qualified'],
        'original_UI_business_success':ui['business_success_verified'],
        'limits':['Only first and last selected stable full snapshots of each of two actual process generations were independently inventoried.',
            'The original complete-mapping counter and automatic engine qualification remain unchanged.',
            'One overlay APK was identified from its first 64 bytes only; its whole bytes are not qualified by this collector.',
            'The two unresolved labels correspond to read-only, non-executable property/idmap mappings in the captured engine-name candidate rows. Their contents were not read.',
            'Both Dalvik JIT mappings and the kernel vdso/vsyscall mappings have names and boundaries only; no process-memory contents were read.',
            'Library names containing engine or nativebridge are heuristic candidates, not independent proof of an emulator or of its absence.',
            'These bounded process observations do not prove long-duration memory stability, UI delivery, Dismiss, audio output, or an entire App production-ready.'],
        'all_scope_checks_passed':True,'business_or_engine_gate_automatically_granted':False}
    for name,value in [('ELF_INVENTORY04.json',invraw),('INDEPENDENT_CLOCK_INVENTORY_REVIEW.json',encode(report))]:
        path=ROOT/name
        with path.open('xb') as stream:stream.write(value)
        print(name,len(value),sha(value))

if __name__=='__main__':main()
