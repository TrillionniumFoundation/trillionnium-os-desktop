#!/usr/bin/env python3
"""Independent local verification of five exact IHG safe result originals."""
from pathlib import Path
import base64,hashlib,json,types,zlib
W=Path('/workspace/scratch/94990735b266');E=W/'root-recovery-20261104-02/evidence/ihg-launch-five-results-read01';HERE=Path(__file__).resolve().parent

def sha(raw):return hashlib.sha256(raw).hexdigest()
def exact(path,size,pin):
    raw=path.read_bytes();assert len(raw)==size and sha(raw)==pin,str(path);return raw

def load(path,size,pin,name):
    raw=exact(path,size,pin);m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m

def main():
    decoding=json.loads(exact(E/'decode-verification.json',1671,'b6fbaa7da1b04f2468465fff42176626078e63bb1ce5c7300450dbb7f3a4052b'))
    carrier=exact(E/'stdout.log',10210,'be4c69c94b79fda33548a7894d45586b6db5a8bb68c9fb861fc58e09006bd625')
    env=json.loads(carrier);compressed=base64.b64decode(env['data'],validate=True)
    assert len(compressed)==env['compressed_bytes'] and sha(compressed)==env['compressed_sha256']
    decoder=zlib.decompressobj(31);raw=decoder.decompress(compressed,3145729)
    assert decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and len(raw)<=3145728
    assert len(raw)==env['uncompressed_bytes'] and sha(raw)==env['uncompressed_sha256'];bundle=json.loads(raw)
    assert set(bundle['files'])=={'coordinator.json','stage.json','launch.json','inspect.json','cleanup.json'}
    reader=load(W/'android-ihg-launch-inspect01-results-reader-01/read_summary.py',7536,'99abe052f06846f2d81ceb3a3b1350df14140a0fcf42236ca2496e69c8f84393','reviewed_reader')
    entry=load(W/'android-ihg-launch-inspect-01/owned_inspect.py',34373,'456f62258aa4a27e4a5663ab20ef9ddcf7284f0220c7e0a7cfaa8af0bebe2d3b','reviewed_launch')
    values={};originals={};pins={}
    for name,member in bundle['files'].items():
        pin={k:member[k] for k in ('path','bytes','sha256')};assert pin==decoding['members'][name]
        raw=exact(E/name,pin['bytes'],pin['sha256']);assert raw==member['text'].encode() and pin['path']==str(reader.FILES[name])
        values[name]=json.loads(raw);reader.no_raw_ui(values[name]);originals[pin['path']]=raw;pins[name]=pin
    c,s,l,i,k=(values[n+'.json'] for n in ('coordinator','stage','launch','inspect','cleanup'))
    assert pins['coordinator.json']['sha256']=='6a354bc4cfe0066263b8f6041be90d674fce05700cd57b21dcf5880122312211'
    assert pins['stage.json']['sha256']=='bb34503b97e7702a8b10c6da10cb4bb6e3a95043168ff59859a15cbdf56d7bf1'
    assert s['coordinator_result']==pins['coordinator.json'] and s['coordinator_returncode']==0
    entry.read=lambda path,*args:originals[str(path)]
    main_guard=c['Main_before'];guards=[]
    for name,v in values.items():
        assert v['ok'] is True and v['error'] is None and v['secondary_errors']==[]
        assert v['source_manifest_sha256']==reader.SOURCE_SHA and v['nonce']==reader.NONCE
        assert v['package']=='com.ihg.apps.android' and not v['business_success_verified'] and not v['whole_app_production_ready']
        for key,value in v.items():
            if key in ('Main_before','Main_after','Main_before_lock'):assert value==main_guard;guards.append(name+':'+key)
        assert all(v[x]==0 for x in ('click_actions','text_actions','audio_actions','screenshots'))
    assert len(guards)==13 and main_guard['resource_limits_match'] and main_guard['three_host_processes_match']
    assert main_guard['Main_epoch_sha256']=='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
    installed=json.loads(exact(W/'android-ihg-r1-install-actual-review-01/review.json',2750,'cdcf8d661a906e7f577233ea28151ef26db4bcbd9f709bdc701dbe86b0e5ae76'))['installed_identity']
    for phase,field,v in (('launch','launch_result',l),('inspect','inspection_result',i),('cleanup','cleanup_result',k)):
        observed,pin=entry.durable(v,phase,reader.SOURCE_SHA);assert observed==v and pin==pins[phase+'.json']==c[field]==c['retained_phase_results'][phase]
        assert v['helper_before']==v['helper_after']==installed
        assert v['actual_install']==c['actual_install'] and v['actual_resolution']==c['actual_resolution']
        assert v['target_before']==v['target_after']==l['target_before'] and v['target_before']['signer_independently_verified'] is False
        assert v['shared_helper']['whole_process_tree_cleanup_qualified'] is False
        assert v['outcome_unknown'] is False and v['action_attempted'] is (phase!='inspect')
        assert v['target_FD_cleanup']=={'commercial_files_changed':False,'held_APK_FDs_closed':1}
        assert v['flow_lock_admission']['acquired'] and v['flow_lock_admission']['same_inode_confirmed']
        assert v['flow_lock_released'] and v['held_binding_released'] and v['final_Main_guard_passed']
        if phase!='cleanup':
            assert v['action_lock_released'] and v['action_lock_admission']['acquired'] and v['action_lock_admission']['same_inode_confirmed']
            assert v['action_lock_admission']['opened_identity']['device']==28 and v['action_lock_admission']['opened_identity']['inode']==8312
    assert [v['durable_command_count'] for v in (l,i,k)]==[12,17,11]
    assert l['current_launcher']['component']==c['component']=='com.ihg.apps.android/.activity.MainActivity'
    assert l['resolve_command']['stdout_sha256']==l['current_launcher']['resolve_stdout_sha256']==c['actual_resolution']['actual_resolve_stdout_sha256']
    task=c['owned_task'];assert task==l['owned_task']==i['sequence']['owned_task']==k['owned_task']
    assert task['task']==1002 and task['prelaunch_task_ids']==[851] and task['prelaunch_absent'] and task['cleanup_allowed']
    assert k['owned_task_absent'] and c['owned_task_absent_after_cleanup'] and k['task_ids_after']==c['task_ids_after']==[851]
    assert k['cleanup']['new_leaf_removed_and_verified'] and k['cleanup']['other_tasks_preserved']
    seq=i['sequence'];rest=seq['accessibility_restoration'];ass=i['assessments'];plan=entry.PLAN['nonces']
    assert ass==c['assessments'] and seq['foreground_before']==seq['foreground_after']==c['foreground']
    assert seq['installed_before']==seq['installed_after']==installed and seq['error'] is None and seq['secondary_errors']==[]
    assert seq['after_state_attempted'] and seq['after_state_completed'] and seq['restoration_qualified'] and seq['post_state_matches_before']
    assert rest==c['restoration'] and rest['state_before']==rest['state_after']==seq['post_termination_state']['state']
    assert seq['post_termination_state']['ui_automation_connected'] is False and seq['post_termination_state']['helper_uid']==10196
    for phase in ('before','inspect','after'):
        assert ass[phase]['nonce']==plan[phase] and ass[phase]['actual_command_returncode']==0 and ass[phase]['actual_instrumentation_finish_code']==-1
        assert ass[phase]['operation']==('inspect' if phase=='inspect' else 'state')
    assert rest['wire_sha256']==[ass[n]['wire_sha256'] for n in ('before','inspect','after')]
    assert seq['inspection_wire_sha256']==ass['inspect']['wire_sha256'] and seq['post_termination_state']['wire_sha256']==ass['after']['wire_sha256']
    assert ass['inspect']['complete'] and ass['inspect']['node_count']==63 and ass['inspect']['window']['focused'] and ass['inspect']['window']['display']==0
    source=exact(W/'android-qa-r5-install-state-03/r4/source-manifest.json',7565,'52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1')
    recorder_pin=json.loads(source)['files']['recorder.py'];recorder=exact(W/'android-qa-install-state-01/review-inputs/recorder.py',recorder_pin['bytes'],recorder_pin['sha256']).decode()
    assert "        finally:\n            os.close(lock)" in recorder and k['action_lock_owner']=='original Flow.cleanup for exact retirement'
    for name in ('owned_before','owned_after'):
        row=c[name];assert row['cpu.max']=='100000 100000' and row['memory.max']=='536870912' and row['memory.swap.max']=='0' and row['pids.max']=='128'
        assert all(line.split()[1]=='0' for line in row['memory.events'].splitlines())
    assert c['owned_after']['memory.peak']=='161103872'
    result={'schema':1,'state':'ACTUAL_OWNED_LAUNCH_READ_ONLY_INSPECTION_AND_EXACT_TASK_RETIREMENT_VERIFIED','job':'1a1add98701-fc05-5b20','collector_job':'1a1adf28a24-fc05-5c02','five_original_pins':pins,'original_durable_function_passed_for_all_phases':True,'Main_exact_matching_observations':len(guards),'command_counts':{'launch':12,'inspect':17,'cleanup':11},'native_launches':1,'owned_task_removed':1002,'preexisting_task_ids_preserved':[851],'helper_uid':10196,'target_uid':10137,'state_restore_and_independent_no_automation_after_state_verified':True,'installed_helper_and_target_APKs_equal_across_phases':True,'flow_and_action_locks':{'launch_inspect_explicit_release':True,'all_three_flow_locks_explicit_release':True,'cleanup_global_lock_release_basis':'successful original Flow.cleanup return after its pinned finally os.close; no new FD sweep','recorder_source':recorder_pin},'held_APK_FDs_closed_per_phase':1,'held_context_released_all_phases':True,'phase_action_attempted':{'launch':True,'inspect':False,'cleanup':True},'phase_outcome_unknown_all_false':True,'read_only_inspection':ass['inspect'],'owned_peak_bytes':161103872,'owned_memory_events_all_zero':True,'target_signer_independently_verified':False,'shared_helper_whole_process_tree_cleanup_qualified':False,'host_foreground_display_independently_verified':False,'business_success_verified':False,'hotel_search_login_or_booking_verified':False,'whole_app_production_ready':False,'Hepta_Android_or_new_runtime_actions':0,'raw_UI_tree_exported':False}
    target=HERE/'review.json';assert not target.exists();target.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(json.dumps({'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())}))
if __name__=='__main__':main()
