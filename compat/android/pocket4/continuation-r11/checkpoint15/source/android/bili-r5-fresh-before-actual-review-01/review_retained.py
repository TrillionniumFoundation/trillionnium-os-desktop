#!/usr/bin/env python3
"""Local, read-only review of already collected safe receipts; no Android calls."""
import ast
import hashlib
import json
from pathlib import Path
import types

ROOT=Path('/workspace/scratch/94990735b266')
EVIDENCE=ROOT/'root-recovery-20261104-02/evidence/bili-r5-player-fresh-before01-read01'
SOURCE=ROOT/'android-bili-r5-player-fresh-before-01'
MANIFEST='f151b6737f72c53e9f776076ed81fecce4a68b327b59d2bf2f971fe838372283'
NONCE='c1eaefa79cbafc86cb32f638900443bf'
MAIN='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
EXPECTED={
    'coordinator.json':(249889,'ff2c8e0f8a09f194c7dea3ae1358e425a1c1376d5b68fe273e779cd7b5f75ec3'),
    'stage.json':(1651,'780d97c06491bcfd51ff9da0d97552b08cda25406f839ff160dc8e989e1b567a'),
    'navigation.json':(268643,'b1cc104486632c7ec6c42d609c8c0d23c97a72ca3e2823c5ff48abc93bba7483'),
    'cleanup.json':(446,'14ad1897af7ee9c0b8d220de63213f07a121aea640f363dd87d43d38b64e0eda'),
    'launch.json':(5090,'c4364e176563f8eadf92af218cd55b9ca5cc9c79b4b9295a60625a0fee17fe4f'),
    'launch-command-result.json':(1163,'3cb2d1309c242bf01238d3f8fba0fdb4b007bff8d3e2b68d9a59478602dd76ee'),
    'navigation-command-result.json':(1169,'f00ab6fb3487ccd307b1746c0499b0eba7e2aacf131d8942b6df8838b1ee138a'),
    'cleanup-command-result.json':(1287,'b92f4117e5b892dc17addaa90ebc399d0f2d929cefe74acfda2b87c5138472e5'),
}

def sha(data):return hashlib.sha256(data).hexdigest()
def check(value, label):
    if not value:raise AssertionError(label)
def read(path,size,digest):
    raw=path.read_bytes()
    check(len(raw)==size and sha(raw)==digest,'exact input '+str(path))
    return raw
def pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}

def main():
    reader_raw=read(EVIDENCE/'reader-report.json',571202,'df77c0232486b52e50c4c4d2aeb0570f3aa78730e2d9486995d79d85c516cb70')
    reader=json.loads(reader_raw)
    check(set(reader['files'])==set(EXPECTED) and reader['missing']==[], 'eight exact collected files')
    values={};pins={}
    for name,(size,digest) in EXPECTED.items():
        raw=read(EVIDENCE/'originals'/name,size,digest);record=reader['files'][name]
        check(record['bytes']==size and record['sha256']==digest and record['text'].encode()==raw,'reader original '+name)
        values[name]=json.loads(raw);pins[name]=pin(raw)
    c,n,s,cl,l=(values[x] for x in ('coordinator.json','navigation.json','stage.json','cleanup.json','launch.json'))
    for name,v in [('coordinator',c),('navigation',n),('stage',s),('cleanup',cl),('launch',l)]:
        check(v['ok'] is True and v.get('error') is None and v.get('secondary_errors',[])==[] and v['automatic_retry'] is False,'actual success '+name)
    for v in (c,n,s,l):
        check(v['nonce']==NONCE and v['source_manifest_sha256']==MANIFEST and v['whole_app_production_ready'] is False,'fixed flow')
    for parent,key,name in ((s,'coordinator_result','coordinator.json'),(c,'navigation_result','navigation.json'),(c,'launch_result','launch.json'),(c,'cleanup_result','cleanup.json')):
        check({k:parent[key][k] for k in ('bytes','sha256')}==pins[name],'durable chain '+name)
    # The coordinator intentionally embeds a selected summary, not the complete
    # worker record. The full worker is independently bound by navigation_result.
    common=set(c['navigation'])&set(n)
    check(all(c['navigation'][k]==n[k] for k in common),'coordinator embedded common fields')
    check(c['Main_before']==c['Main_after']==s['Main_before']==s['Main_after'],'Main full equality')
    check(c['Main_before']['Main_epoch_sha256']==MAIN and s['source_unchanged'] is True,'Main/source gates')
    for name in ('launch-command-result.json','navigation-command-result.json','cleanup-command-result.json'):
        v=values[name]
        check(v['returncode']==0 and v['joined'] is True and v['timed_out'] is False and v['secondary_errors']==[],'command complete '+name)
        check(v['Main_before'] is True and v['Main_after']==c['Main_after'],'command Main '+name)
    check(all(n[k] is True for k in ('final_Main_guard_passed','held_binding_released','action_lock_released','query_submission_controls_completed','results_container_content_observed','video_click_and_observations_completed','buffer_viewport_observation_completed')),'worker complete gates')
    check(n['live_installed_before']==n['actual_install']['installed_identity']==l['live_installed_before'],'actual helper identity')
    check(n['helper_uid']==10170 and n['uid']==10117 and n['package']=='tv.danmaku.bili','exact app pair')
    check(n['outcome_unknown'] is True and n['business_outcome_unknown'] is True and c['business_outcome_unknown'] is True,'unknown business retained')
    check(all(v['business_success_verified'] is False for v in (c,n,s,l,cl)),'no business escalation')
    manifest_raw=(SOURCE/'SOURCE_PINS.json').read_bytes();check(sha(manifest_raw)==MANIFEST,'source manifest')
    manifest=json.loads(manifest_raw)
    source_pins={}
    for name in ('owned_navigation.py','viewport_observation.py'):
        row=manifest['files'][name];raw=read(SOURCE/name,row['bytes'],row['sha256']);source_pins[name]=pin(raw)
    mod=types.ModuleType('review_viewport')
    exec(compile((SOURCE/'viewport_observation.py').read_bytes(),str(SOURCE/'viewport_observation.py'),'exec'),mod.__dict__)
    code=(SOURCE/'owned_navigation.py').read_text();tree=ast.parse(code)
    worker=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='worker')
    assignments=[x for x in ast.walk(worker) if isinstance(x,ast.Assign) and any(isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name) and t.value.id=='result' and isinstance(t.slice,ast.Constant) and t.slice.value=='outcome_unknown' for t in x.targets)]
    check(any(ast.unparse(x.value)=="result['action_attempted'] and (phase == 'navigate' or not result['ok'])" for x in assignments),'source unknown semantics')
    b=n['buffer_viewport_observation'];samples=b['viewport_samples']
    check(len(samples)==3 and b['fresh_before_read_per_capture'] is True and b['maximum_capture_transactions']==3,'three fresh capture transactions')
    check(len(b['reads'])==1 and b['buffering_label_absent_observed'] is True,'actual buffer observation')
    check(b['action_replayed'] is False and b['failed_read_retried'] is False and b['audio_captured'] is False and b['playback_verified'] is False and b['whole_app_ready'] is False,'scope limits')
    sample_summary=[];seen=[];proofs=[]
    for i,row in enumerate(samples):
        check(row['index']==i+1 and row['capture_attempted'] is True and row['private_crop_published'] is True and row['fresh_before_read_completed'] is True and row['scope_checked_before_and_after'] is True,'sample complete')
        check(row['atomic_frame_attribution'] is False and row['audio_captured'] is False and row['playback_verified'] is False and row['video_only_pixels_proven'] is False,'sample limits')
        obs=[]
        for side,offset in (('before',12+2*i),('after',13+2*i)):
            o=row[side+'_observation'];proof=o['proof'];proofs.append(proof)
            check(o['after_state_completed'] is True and o['restoration_qualified'] is True and proof['buffering_label_present'] is False,'restored ready observation')
            check(proof['scope']['main_epoch_sha256']==MAIN and proof['scope']['uid']==10117 and proof['scope']['package']=='tv.danmaku.bili' and proof['window']['focused'] is True and proof['window']['display']==0,'scope identity')
            assessments=o['assessments']
            for phase in ('before','inspect','after'):
                a=assessments[phase];seen.append(a['nonce'])
                check(a['nonce']==mod.PLANS[offset]['nonces'][phase] and a['actual_command_returncode']==0 and a['actual_instrumentation_finish_code']==-1,'bound assessment '+side+' '+phase)
            a=assessments['inspect']
            check(a['complete'] is True and a['node_count']==153 and a['window_sha256']==proof['window_sha256'],'complete actual inspection')
            w=a['window_observation'];check(w['ready'] is True and w['cache_last_result'] is True and w['cache_clears']==w['cache_attempts'] and w['cache_last_exception'] is None and w['cache_runtime_sdk']==37,'actual own cache gate')
            obs.append({'side':side,'plan_index':offset,'nonces':{k:assessments[k]['nonce'] for k in ('before','inspect','after')},'inspection_pin':{k:a[k] for k in ('assessment_bytes','assessment_sha256','wire_sha256','tree_sha256','window_sha256','node_count')},'restoration_qualified':True,'ready_samples':w['samples'],'cache_clears':w['cache_clears']})
        before,after=(row[x+'_observation']['proof'] for x in ('before','after'))
        check(mod.same_scope(before,after),'actual frozen absolute same_scope')
        check(before['crop']==after['crop']==[320,45,1520,720] and before['window']['bounds']==after['window']['bounds']==[320,0,1520,1520],'exact absolute viewport')
        crop=row['private_crop']
        check(crop['bounds']==before['crop'] and crop['width']==1200 and crop['height']==675 and crop['must_not_enter_Git'] is True,'private crop contract')
        sample_summary.append({'index':i+1,'capture_ms':row['capture_ms'],'absolute_before_after_scope_equal':True,'window_bounds':before['window']['bounds'],'crop_bounds':before['crop'],'render_structure_sha256':before['render_structure_sha256'],'private_crop_pin':crop,'observations':obs})
    check(len(seen)==len(set(seen))==18,'18 actual unique capture-phase nonces')
    check(len({x['private_crop']['sha256'] for x in samples})==3,'distinct PNG bytes only')
    check(all(mod.same_scope(proofs[0],p) for p in proofs),'this run no observed inter-transaction scope move')
    check(c['owned_task']['task']==936 and c['owned_task']['prelaunch_task_ids']==[851] and c['owned_task']['prelaunch_absent'] is True,'owned task admission')
    check(cl['task_ids_after']==[851] and cl['new_leaf_removed_and_verified'] is True and cl['other_tasks_preserved'] is True and cl['outcome_unknown'] is False and c['owned_task_absent_after_cleanup'] is True,'exact task cleanup')
    rb,ra=c['owned_before'],c['owned_after']
    for key in ('path','device','inode','cpu.max','memory.max','memory.swap.max','pids.max'):check(rb[key]==ra[key],'resource binding '+key)
    check(ra['cpu.max']=='100000 100000' and ra['memory.max']=='536870912' and ra['memory.swap.max']=='0' and ra['pids.max']=='128','resource limits')
    events=dict(line.split() for line in ra['memory.events'].splitlines())
    check(all(events[k]=='0' for k in ('max','oom','oom_kill','oom_group_kill')) and ra['memory.swap.peak']=='0','zero actual OOM/swap')
    report={'schema':1,'scope':'independent local retained-safe-record review of one actual fresh-before Bilibili flow','actual_job':'1a1ab5c780b-fc05-4cfe','terminal_source':'Root supplied authoritative exit0 complete/durable; this review does not issue device RPCs','reader_pin':pin(reader_raw),'original_pins':pins,'source_manifest_sha256':MANIFEST,'reviewed_source_pins':source_pins,'actual_scope_result':'THREE_FRESH_BEFORE_AFTER_CAPTURE_TRANSACTIONS_AND_EXACT_TASK_CLEANUP_VERIFIED','flow_nonce':NONCE,'main_epoch_sha256':MAIN,'Main_before_after_equal':True,'source_unchanged':True,'actual_helper_uid':10170,'commercial_uid':10117,'samples':sample_summary,'capture_phase_unique_nonces':18,'all_observed_absolute_scopes_equal_this_run':True,'movement_branch_actually_exercised_this_run':False,'cleanup':{'owned_task':936,'preexisting_tasks':[851],'remaining_tasks':cl['task_ids_after'],'new_leaf_removed_and_verified':True,'other_tasks_preserved':True,'observations':cl['observations'],'outcome_unknown':False},'resources':{'cgroup_device':ra['device'],'cgroup_inode':ra['inode'],'cpu_max':ra['cpu.max'],'memory_max':int(ra['memory.max']),'memory_peak':int(ra['memory.peak']),'swap_peak':int(ra['memory.swap.peak']),'pids_max':int(ra['pids.max']),'events':events},'outcome_semantics':{'navigation_ok':True,'navigation_action_attempted':n['action_attempted'],'navigation_outcome_unknown':True,'coordinator_business_outcome_unknown':True,'source_rule':"action_attempted and (phase == 'navigate' or not ok)",'interpretation':'The frozen producer intentionally retains unknown business outcome for navigate even when acknowledged actions and bounded observations pass; no command timeout or unacknowledged attempt was inferred from this field. The durable phase gate itself requires this true value.','business_success_verified':False,'whole_app_production_ready':False},'not_verified':['pause and resume behavior','seek position/time advancement','reopen/resume and cold-start continuity','app-attributed actual audio output','continuous playback or producer attribution','atomic screenshot/window ownership','content of these three PNGs: this reviewer has not read image pixels','inter-transaction move branch on the actual device in this run'],'privacy':{'raw_UI_tree_read':False,'pixels_read':False,'raw_journal_read':False,'private_images_in_Git':False},'actions_by_reviewer':{'device':0,'Android':0,'UI':0,'retry':0},'original_geometry_failure_preserved':True}
    print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True))

if __name__=='__main__':main()
