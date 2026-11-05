#!/usr/bin/env python3
"""Review saved Gallery04 runtime identity without any new process or device read.

Preserve the collector's original zero complete-sample count. Explicitly classify
its two name-matched, non-executable property/resource mappings from saved maps.
This does not qualify stress, arbitrary anonymous code, or unobserved workloads.
"""
from pathlib import Path
import hashlib, json, re

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
ROOT=PARENT.parents[1]
def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(name,pin):
    raw=(PARENT/name).read_bytes()
    assert sha(raw)==pin,name
    return json.loads(raw),{'path':name,'bytes':len(raw),'sha256':pin}
export,export_pin=read('saved-export-original.json','d9aa8e8bf8da9c3cc9e1ff04ea9fdacc82fbb88c4dc6090ae08d4286b21db1af')
result,result_pin=read('result-original.json','550d1525bd28cd074d3317dd4e3c3c38c43e78924209612a751d01bbb7c787fb')
sources={}
for name,pin in [('export_saved04.py','3e308617265a939915a75de543a670a447d5129c8c912dba36a63835c548c757'),('runtime_evidence.py','670af6f9a2ecd16591babc3e40387dc6f25474d27f73fc93f42b881d3d60d5df')]:
    raw=(PARENT/name).read_bytes();assert sha(raw)==pin
    sources[name]={'bytes':len(raw),'sha256':pin}
assert export['original_result_sha256']==result_pin['sha256']
assert export['new_android_commands']==export['new_ui_inputs']==export['new_current_process_reads']==0
assert result['state']=='VIDEO_PLAY_PAUSE_RESUME_REOPEN_CLEANUP_VERIFIED'
assert result['guard_before']==result['guard_after']
assert result['gallery_before']==result['gallery_after']
app=result['gallery_after']
assert app['package']=='com.android.gallery3d' and app['uid']==10064 and app['version_code']==40030
assert app['apk_sha256']=='347c376f07a4365fa3828ddf9f011994fe527a53fd2f5bd059997ffd3904d46e'
assert app['epoch_sha256']==result['guard_after']['epoch_sha256']=='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
assert result['runtime_evidence']['stable_complete_mapping_samples']==0
unresolved_paths={'/dev/__properties__/u:object_r:qemu_sf_lcd_density_prop:s0',
 '/data/resource-cache/vendor@overlay@DroidloomFrameworkDisplayOverlay.apk@idmap'}
overlay='/vendor/overlay/DroidloomFrameworkDisplayOverlay.apk'
required_runtime={
 '/apex/com.android.art/lib64/libart.so':'3b53de051a3004be76078506f7a6924e50b467fd4b3277b867afc13328d082d0',
 '/apex/com.android.art/lib64/libartbase.so':'a2766974a16b431dcee611975c49b8a30b7d181e3237d213dbe4482d84f0e407',
 '/system/lib64/libandroid_runtime.so':'a2b1445b68a9bff4ab23687c66668579b57fbc5122df055d212a51a60049a64c',
 '/apex/com.android.art/lib64/libnativebridge.so':'800c7968a03e3d3c673771110aa1249c296c3a7963398c3a9856311db67252cc',
 '/system/lib64/libnativebridge_lazy.so':'5b1b02f4de4966ddd1dc817a1d36ac26f647bc201538e09ad8ab84f3faf0df7b'}
stable_phases=('paused','resumed','round-0-playback','round-1-launch','round-1-playback')
evidence=[];inventory=None;identities=set()
for phase in stable_phases:
    entry=export['runtime_selections'][phase];row=entry['row'];identity=row['host_identity']
    assert row['package']==row['process_name']=='com.android.gallery3d' and row['android_uid']==10064
    assert row['stable_process_identity'] and row['maps_before_after_equal']
    assert identity['uid']==['10064']*4 and identity['ns']['pid']=='pid:[4026533288]'
    assert identity['exe']=='/system/bin/app_process64'
    assert row['executable']['sha256']=='456322c6cc424d228d153623717e8a6b1ac7d0b3aa48f0f1948380412f54ac73'
    assert row['executable']['architecture']=='x86_64' and row['executable']['machine']==62
    identities.add((identity['pid'],identity['start']))
    unresolved=row['unresolved_executable_objects']
    assert len(unresolved)==2 and {x['path'] for x in unresolved}==unresolved_paths
    classified=[]
    for path in sorted(unresolved_paths|{overlay}):
        mappings=[m for m in row['engine_mappings'] if m['path']==path]
        assert mappings and all(m['permissions']=='r--s' for m in mappings)
        classified.append({'path':path,'mapping_count':len(mappings),'permissions':sorted({m['permissions'] for m in mappings}),
           'classification':'non-executable, read-only shared mapping; selected by broad name heuristic',
           'bytes_read_for_this_review':0,'mapped_code_identity_claimed':False})
    objects=row['mapped_code_objects']
    assert len(objects)==382 and len({o['path'] for o in objects})==382
    elf=[o for o in objects if o['elf']]
    nonelf=[o for o in objects if not o['elf']]
    assert len(elf)==381 and len(nonelf)==1 and nonelf[0]['path']==overlay
    assert all(o['architecture']=='x86_64' and o['machine']==62 and o['bits']==64 and re.fullmatch('[0-9a-f]{64}',o['sha256']) for o in elf)
    by_path={o['path']:o for o in elf}
    assert all(by_path[path]['sha256']==pin for path,pin in required_runtime.items())
    current={path:{'sha256':o['sha256'],'bytes':o['identity']['st_size'],'machine':o['machine'],'architecture':o['architecture']} for path,o in sorted(by_path.items())}
    if inventory is None:inventory=current
    else:assert current==inventory
    named=entry['named_executable_mappings']
    assert len(named)==4 and {m['path'] for m in named}=={'[anon_shmem:dalvik-zygote-jit-code-cache]','[anon_shmem:dalvik-jit-code-cache]','[vdso]','[vsyscall]'}
    assert all('x' in m['permissions'] and 'w' not in m['permissions'] for m in named)
    assert {m['path'] for m in row['anonymous_executable_mappings']}=={'[vdso]','[vsyscall]'}
    evidence.append({'phase':phase,'observed_at_utc':row['utc'],'source':{k:entry[k] for k in ('source_name','source_bytes','source_sha256')},
      'host_pid':identity['pid'],'start_ticks':identity['start'],'android_pid':int(identity['nspid'][-1]),
      'android_uid':10064,'process_name':row['process_name'],'pid_namespace':identity['ns']['pid'],
      'maps_sha256':row['maps_sha256'],'maps_bytes':row['maps_bytes'],'stable_identity':True,'maps_before_after_equal':True,
      'file_backed_ELF_objects_hashed':len(elf),'classified_read_only_name_matches':classified,
      'named_non_path_executable_mappings':[{'path':m['path'],'permissions':m['permissions']} for m in named],
      'anonymous_or_JIT_code_bytes_verified':False})
assert identities=={(2585031,'92480054'),(2587281,'92483758')}
assert export['runtime_selections']['round-0-launch']['row']['maps_before_after_equal'] is False
out={'schema':'gallery04-saved-runtime-identity-review/v1','state':'OBSERVED_RUNTIME_IDENTITIES_BOUND_PENDING_INDEPENDENT_REVIEW',
 'inputs':[export_pin,result_pin],'collector_and_exporter_sources':sources,
 'app':{k:app[k] for k in ('package','uid','version_code','apk_sha256','apk_bytes','epoch_sha256')},'android_user':0,
 'required_runtime_artifacts':required_runtime,'all_hashed_ELF_objects':inventory,'stable_observations':evidence,
 'excluded_unstable_phase':'round-0-launch','original_stable_complete_mapping_samples':0,
 'original_collector_result_modified':False,'new_device_or_process_reads':0,'device_actions':0,
 'identity_gate_granted':False,'whole_app_production_ready':False,
 'interpretation':'The exact process executable, ART, framework runtime and native-bridge/lazy bridge files were observed and hashed in five stable snapshots across two actual Gallery process generations. Two unresolved name candidates and one non-ELF name candidate are explicitly read-only non-executable mappings. Their contents are neither inspected nor qualified. This is an observed runtime identity binding, not a claim that the entire process address space or all future translation behavior is verified.',
 'limits':['Original full-sampler completeness stays zero; no collection guards or raw receipts are changed.',
 'JIT caches, vDSO and vsyscall mapping names/permissions are retained, without process-memory hashing.',
 'The one unstable first-launch maps snapshot receives no stable identity coverage credit.',
 'No all-workload native translation exclusion, arbitrary anonymous-code validation, stress, leak, audio, rotation, business or release gate is granted.']}
with (HERE/'IDENTITY_REVIEW.json').open('x') as stream:stream.write(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps({'file':str(HERE/'IDENTITY_REVIEW.json'),'sha256':sha((HERE/'IDENTITY_REVIEW.json').read_bytes()),'stable_observations':len(evidence),'process_generations':len(identities),'ELF_objects':len(inventory),'identity_gate_granted':False}))
