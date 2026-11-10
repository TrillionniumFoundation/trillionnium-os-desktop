#!/usr/bin/python3
"""Independent local review of saved Contacts runtime02; no device operations."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,pin):
 raw=(ROOT/path).read_bytes();assert sha(raw)==pin,path
 return json.loads(raw),{'path':path,'bytes':len(raw),'sha256':pin}
export,ep=load('contacts-search08/readback01/saved-export.json','302854134d6398abe331f94c9505d41cfd14389b9737addb4e4615ffe84eaa1c')
result,rp=load('contacts-search08/runtime02/actual-result.json','612e91ac38c9d07d1d27a16ada46c5b1215c7901ca56ee65900833605653405a')
audit,ap=load('app-identity08/public-metadata/installed-app-identities.json','a070c1f6f33b73942e2948540654d2106d997daa7f11bb45af098df8b311a821')
sources={}
for path,pin in [
 ('contacts-search08/runtime02/runtime_evidence.py','8018acc97132f3e417cbcb47a23071a45849f7e52f197a6aa250ccab7cce9422'),
 ('contacts-search08/runtime02/capture_runtime02.py','8504a777aea04d997a80aa08d8ca6e6bc749da42327c49c164465609855cecce'),
 ('contacts-search08/readback01/export_saved01.py','3e0c54326af8c958c7202791328664fddb6995558578d3c0af3cfbc89b583e6f')]:
 raw=(ROOT/path).read_bytes();assert sha(raw)==pin;sources[path]={'bytes':len(raw),'sha256':pin}
assert export['runtime_result_sha256']==rp['sha256']
assert export['UI_result_sha256']==result['separate_UI_flow_result']['sha256']=='0184620e924ae7dddb564b5e1e4399f90fc2fcc66e68bdbab173c33d98f26df4'
assert export['new_android_commands']==export['new_ui_inputs']==export['new_current_process_reads']==0 and export['original_files_modified'] is False
assert result['state']=='BOUNDED_CONTACTS_RUNTIME_OBSERVATIONS_CAPTURED_REVIEW_REQUIRED'
assert result['guard_before']==result['guard_after'] and result['guard_after']['epoch_sha256']=='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
assert result['sampler']['sample_count']==104 and result['sampler']['thread_joined'] and not result['sampler']['errors'] and result['sampler']['scan_error_count']==0
assert result['sampler']['stable_complete_mapping_samples']==0
assert result['separate_UI_flow_result']['state']=='FAILED' and result['separate_UI_flow_result']['UI_flow_business_success'] is False
apps=[x for x in audit['apps'] if x['package']=='com.android.contacts'];assert len(apps)==1
app=apps[0];assert app['android_user']==0 and app['uid']==10055 and app['version_code']==10734 and len(app['apks'])==1
apk=app['apks'][0];assert apk['sha256']==result['APK']['sha256']=='11f8be5fd46dd79ee4f7524d5d1334e21ce0f9e23892b2940a5b6091e2f349d0'
assert apk['bytes']==result['APK']['bytes']==11839391
assert apk['signature']['verified'] and apk['signature']['tool_exit_code']==0 and apk['signature']['verified_schemes']['v3']
assert apk['signature']['signer_certificate_sha256']==['28bbfe4a7b97e74681dc55c2fbb6ccb8d6c74963733f6af6ae74d8c3a6e879fd']
index={s['name']:s for s in export['sample_index']};assert len(index)==104 and all(not s['errors'] for s in index.values())
assert len(export['runtime_selections'])==5
unresolved_paths={'/dev/__properties__/u:object_r:qemu_sf_lcd_density_prop:s0',
 '/data/resource-cache/vendor@overlay@DroidloomFrameworkDisplayOverlay.apk@idmap'}
overlay='/vendor/overlay/DroidloomFrameworkDisplayOverlay.apk'
named_paths={'[anon_shmem:dalvik-zygote-jit-code-cache]','[anon_shmem:dalvik-jit-code-cache]','[vdso]','[vsyscall]'}
runtime_paths=['/apex/com.android.art/lib64/libart.so','/apex/com.android.art/lib64/libartbase.so',
 '/system/lib64/libandroid_runtime.so','/apex/com.android.art/lib64/libnativebridge.so','/system/lib64/libnativebridge_lazy.so']
inventory=None;observations=[];generations=set();phases=set();exe_sha=None
for selection,entry in export['runtime_selections'].items():
 source=index[entry['source_name']];assert entry['source_sha256']==source['sha256'] and entry['source_bytes']==source['bytes']
 row=entry['row'];identity=row['host_identity'];assert row['phase']==source['phase']
 assert row['package']==row['process_name']=='com.android.contacts' and row['android_uid']==10055
 assert row['full_mapping_snapshot'] and row['stable_process_identity'] and row['maps_before_after_equal']
 assert identity['uid']==['10055']*4 and identity['ns']['pid']=='pid:[4026533288]' and identity['ppid']==3588887
 assert len(identity['nspid'])==2 and identity['nspid'][0]==str(identity['pid']) and identity['exe']=='/system/bin/app_process64'
 assert row['cgroup_after']==identity['cgroup'] and ('/uid_10055/pid_'+identity['nspid'][-1]) in identity['cgroup']
 executable=row['executable'];assert executable['elf'] and executable['machine']==62 and executable['bits']==64 and executable['architecture']=='x86_64'
 assert executable['sha256']=='456322c6cc424d228d153623717e8a6b1ac7d0b3aa48f0f1948380412f54ac73'
 if exe_sha is None:exe_sha=executable['sha256']
 else:assert exe_sha==executable['sha256']
 generations.add((identity['pid'],identity['start'],identity['nspid'][-1]));phases.add(row['phase'])
 unresolved=row['unresolved_executable_objects'];assert len(unresolved)==2 and {r['path'] for r in unresolved}==unresolved_paths
 classifications=[]
 for path in sorted(unresolved_paths|{overlay}):
  mappings=[m for m in row['engine_mappings'] if m['path']==path]
  assert mappings and all(m['permissions']=='r--s' for m in mappings)
  classifications.append({'path':path,'permissions':['r--s'],'mapping_count':len(mappings),
   'classification':'Read-only shared non-executable name candidate; not a mapped executable engine claim.'})
 objects=row['mapped_code_objects'];assert len(objects)==len({o['path'] for o in objects})==382
 elf=[o for o in objects if o['elf']];nonelf=[o for o in objects if not o['elf']]
 assert len(elf)==381 and len(nonelf)==1 and nonelf[0]['path']==overlay
 assert nonelf[0]['content_read']=='first_64_code_bytes_only'
 assert all(o['machine']==62 and o['bits']==64 and o['architecture']=='x86_64' and o['byte_order']=='little'
     and re.fullmatch('[0-9a-f]{64}',o['sha256']) and o['identity']['st_size']>0 and 'hash_limit' not in o for o in elf)
 current={o['path']:{'sha256':o['sha256'],'bytes':o['identity']['st_size'],'machine':o['machine'],'bits':o['bits'],'architecture':o['architecture']} for o in sorted(elf,key=lambda x:x['path'])}
 if inventory is None:inventory=current
 else:assert current==inventory
 assert all(p in current for p in runtime_paths)
 named=entry['named_executable_mappings'];assert len(named)==4 and {m['path'] for m in named}==named_paths
 assert all('x' in m['permissions'] and 'w' not in m['permissions'] for m in named)
 assert row['non_filesystem_executable_mappings']==named
 assert {m['path'] for m in row['anonymous_executable_mappings']}=={'[vdso]','[vsyscall]'}
 assert row['non_filesystem_mapping_contents_read'] is False
 observations.append({'selection':selection,'phase':row['phase'],'utc':row['utc'],
  'source_sample':{k:entry[k] for k in ('source_name','source_bytes','source_sha256')},
  'host_pid':identity['pid'],'start_ticks':identity['start'],'android_pid':int(identity['nspid'][-1]),
  'android_uid':10055,'pid_namespace':identity['ns']['pid'],'stable_process_identity':True,'stable_maps':True,
  'maps_bytes':row['maps_bytes'],'maps_sha256':row['maps_sha256'],'ELF_objects_hashed':len(elf),
  'non_executable_name_candidates':classifications,
  'named_executable_maps':[{'path':m['path'],'permissions':m['permissions']} for m in named],
  'JIT_or_anonymous_bytes_read_or_verified':False})
assert generations=={(2919793,'93469953','866709'),(2924489,'93475876','869932')}
assert phases=={'before-ui','interval-00','interval-01','interval-02'}
inventory_bytes=(json.dumps(inventory,indent=2,sort_keys=True)+'\n').encode()
with (HERE/'ELF_INVENTORY.json').open('xb') as f:f.write(inventory_bytes)
report={'schema':'contacts-runtime02-independent-saved-evidence-peer-v1',
 'recommendation':'ACCEPT_OBSERVED_RUNTIME_IDENTITY_ONLY_FOR_THIS_APK_AND_CAPTURE',
 'identity_gate_granted_by_this_script':False,'whole_app_production_ready':False,
 'input_pins':[ep,rp,ap],'collector_and_exporter_pins':sources,
 'package':{'package':app['package'],'android_user':0,'uid':10055,'version_code':10734,'version_name':app['version_name'],
  'apk_sha256':apk['sha256'],'apk_bytes':apk['bytes'],'signer_certificate_sha256':apk['signature']['signer_certificate_sha256'],
  'signature_source':'Earlier real signature verification of these exact unchanged APK bytes; no signature rerun in this peer'},
 'guard':result['guard_after'],'sample_index_entries':104,'stable_snapshots_reviewed':5,'distinct_phase_labels':sorted(phases),
 'process_generations':[{'host_pid':p,'start_ticks':s,'android_pid':int(a)} for p,s,a in sorted(generations)],
 'process_executable':{'guest_path':'/system/bin/app_process64','sha256':exe_sha,'machine':62,'architecture':'x86_64'},
 'runtime_artifact_hashes':{p:inventory[p]['sha256'] for p in runtime_paths},
 'all_ELF_inventory':{'path':'ELF_INVENTORY.json','objects':381,'bytes':len(inventory_bytes),'sha256':sha(inventory_bytes)},
 'inventory_identical_across_all_five_saved_snapshots':True,'observations':observations,
 'original_stable_complete_mapping_samples':0,'original_collector_or_receipts_modified':False,
 'review_device_calls':0,'review_current_process_reads':0,'review_UI_or_provider_or_package_mutations':0,
 'separate_UI_business_result_preserved':result['separate_UI_flow_result'],
 'limits':['The original aggregate completeness count remains zero; this is a separate classification and identity review.',
  'Five selected stable snapshots bind this Contacts run. The other 99 index entries are not claimed as full mapping snapshots.',
  'Four distinct phase labels contain five snapshots because interval-01 contains both process generations.',
  'JIT caches, vDSO and vsyscall names and permissions are observed; their memory bytes are neither read nor hashed.',
  'No claim covers arbitrary anonymous code, every future load, all-workload ARM translation exclusion, stress or leak qualification.',
  'The failed search business flow remains failed. No business, visual, lifecycle, crash or whole-App gate is granted here.',
  'Raw maps and full proc stat are absent from the public selected export; exact original sample hashes and the pinned selection source bind the preserved fields.']}
with (HERE/'REVIEW.json').open('x') as f:f.write(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({'review_path':str(HERE/'REVIEW.json'),'review_bytes':len((HERE/'REVIEW.json').read_bytes()),
 'review_sha256':sha((HERE/'REVIEW.json').read_bytes()),'inventory_sha256':sha(inventory_bytes),
 'stable_snapshots':5,'distinct_phase_labels':4,'process_generations':2,'ELF_objects':381,'new_device_calls':0}))
