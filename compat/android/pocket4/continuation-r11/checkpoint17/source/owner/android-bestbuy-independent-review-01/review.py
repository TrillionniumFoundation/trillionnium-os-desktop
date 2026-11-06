#!/usr/bin/env python3
"""Independent local source and retained-actual review. No runtime access."""
import ast
import hashlib
import json
from pathlib import Path
import types

B=Path(__file__).resolve().parent.parent
OUT=Path(__file__).resolve().parent
E=B/'root-recovery-20261104-02/evidence'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(path):
    raw=path.read_bytes();return {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}
def checked(path,size,digest):
    raw=path.read_bytes();assert len(raw)==size and sha(raw)==digest,str(path);return raw
def frozen(path):
    manifest=json.loads((path/'FROZEN_FILES.json').read_bytes())
    for name,row in manifest['files'].items():checked(path/name,row['bytes'],row['sha256'])
    return {'manifest':pin(path/'FROZEN_FILES.json'),'payloads_verified':len(manifest['files'])}
def module(path):
    value=types.ModuleType('independent_'+path.stem);value.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),value.__dict__);return value
def assignment(source,name,value):
    nodes=[n for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
    assert len(nodes)==1,name;n=nodes[0];lines=source.splitlines(True)
    lines[n.lineno-1:n.end_lineno]=[name+'='+repr(value)+'\n'];return ''.join(lines)

install=B/'android-bestbuy-qa-r1-install-state-01';launch=B/'android-bestbuy-launch-inspect-01'
install_frozen=frozen(install);launch_frozen=frozen(launch)
mapping=json.loads((install/'literal-substitutions.json').read_bytes())
names={'install_state.py':'install_state.py','ihg_context.py':'bestbuy_context.py',
       'ihg_transport.py':'bestbuy_transport.py','stage_execute.py':'stage_execute.py','make_request.py':'make_request.py'}
for old,new in names.items():
    source=(B/'android-ihg-qa-r1-install-state-01'/old).read_text()
    for before,after in mapping['replacements']:source=source.replace(before,after)
    for before,after in mapping['semantic_changes'].get(new,[]):
        assert before in source;source=source.replace(before,after)
    assert source==(install/new).read_text(),new
assert (install/'references/readonly_r3_coordinator.py').read_bytes()==(B/'android-ihg-qa-r1-install-state-01/references/readonly_r3_coordinator.py').read_bytes()
assert (install/'references/read_bestbuy.py').read_bytes()==(B/'android-bestbuy-artifact-launcher-readonly-01/read_bestbuy.py').read_bytes()
stage=module(install/'stage_execute.py')
install_request=json.loads((install/'exact-request.json').read_bytes())
stage.checked_packet(install_request['stdin'].encode())

entry=module(launch/'owned_inspect.py')
actual_install={}
for key,(relative,size,digest) in entry.PRIOR.items():
    actual_install[key]=json.loads(checked(E/'bestbuy-r1-install-read01'/(key+'.json'),size,digest))
actual_metadata={}
for key,(relative,size,digest) in entry.RESOLVER_RECORDS.items():
    actual_metadata[key]=json.loads(checked(E/'bestbuy-artifact-launcher-readonly01'/(key+'.reconstructed-from-actual-stdout.json'),size,digest))
entry.actual_install(actual_install);entry.actual_resolver(actual_metadata,entry.INSTALLED)

# Re-derive the actual launch source from IHG using exact current assignments.
old=B/'android-ihg-launch-inspect-01'
def names_for_launch(source):
    return (source.replace('com.ihg.apps.android','com.bestbuy.android')
        .replace('ihg','bestbuy').replace('IHG','BESTBUY').replace('amazon','bestbuy')
        .replace('Amazon','BestBuy').replace('AMAZON','BESTBUY')
        .replace('UID=10137','UID=10130').replace('10196','10198')
        .replace('399444a5b72d53139b880a4afefdb31a',entry.NONCE))
source=names_for_launch((old/'owned_inspect.py').read_text())
bindings=['PLAN','INSTALL_SOURCE_SHA','UTIL_SHA','UTIL_BYTES','CONTEXT_SHA','TRANSPORT_SHA','STATE_NONCE',
          'STATE_WIRE','INSTALLED','PRIOR','RESOLVER_SHA','RESOLVER_BYTES','RESOLVER_NONCE','RESOLVER_RECORDS']
for name in bindings:source=assignment(source,name,getattr(entry,name))
changes=[("COMPONENT=PACKAGE+'/.activity.MainActivity'","COMPONENT=PACKAGE+'/.activity.SplashActivity'"),
    ('RUNTIME_FILES=','EXPECTED_TARGET_ARTIFACTS='+repr(actual_metadata['worker']['artifacts'])+'\nRUNTIME_FILES='),
    ("'version_code':50023219","'version_code':2012312321"),
    ("len(worker['artifacts'])==1 and worker['total_apk_bytes']==44999052 and\n         worker['artifacts'][0]['sha256']=='c12bb3bae3514c94caaca0a4ef6e8f1ad4491cbce57fd2a15be48b83b4c85b90'",
     "worker['artifacts']==EXPECTED_TARGET_ARTIFACTS and len(worker['artifacts'])==3 and\n         worker['total_apk_bytes']==245511693"),
    ("['held_APK_FDs_closed']==1","['held_APK_FDs_closed']==3"),
    ('len(artifacts.records)==1','len(artifacts.records)==3'),
    ('The original Ticket observation preceded this helper install','The original BestBuy observation preceded this helper install')]
for before,after in changes:
    assert before in source;source=source.replace(before,after)
assert source==(launch/'owned_inspect.py').read_text()
assert names_for_launch((old/'ihg_task_context.py').read_text())==(launch/'bestbuy_task_context.py').read_text()
assert names_for_launch((old/'stage_execute.py').read_text())==(launch/'stage_execute.py').read_text()
maker=names_for_launch((old/'make_request.py').read_text())
for name,value in [('MANIFEST_SHA',sha((launch/'SOURCE_PINS.json').read_bytes())),
                   ('STAGE_SHA',sha((launch/'stage_execute.py').read_bytes())),('STAGE_BYTES',(launch/'stage_execute.py').stat().st_size)]:
    maker=assignment(maker,name,value)
assert maker==(launch/'make_request.py').read_text()
request=json.loads((launch/'exact-request.json').read_bytes());old_request=json.loads((old/'exact-request.json').read_bytes())
assert {k:v for k,v in request.items() if k not in ('args','stdin','idempotency_key')}=={k:v for k,v in old_request.items() if k not in ('args','stdin','idempotency_key')}
packet=json.loads(request['stdin']);manifest=json.loads((launch/'SOURCE_PINS.json').read_bytes())
assert set(packet['files'])==set(manifest['files'])|{'SOURCE_PINS.json'} and packet['nonce']==entry.NONCE
for name,body in packet['files'].items():assert body.encode()==(launch/name).read_bytes()

roles=module(B/'android-bestbuy-launch01-public-roles-reader-01/read_roles.py')
paths={'coordinator':roles.ROOT/'result.json','stage':roles.ROOT/'stage-result.json',
       'launch':roles.FLOW/'steps/launch-01/result.json','inspect':roles.STEP/'result.json',
       'cleanup':roles.FLOW/'steps/cleanup-01/result.json'}
rows={};actual_pins={}
for name,path in paths.items():
    size,digest=roles.PINS[path];local=E/'bestbuy-launch-five-results-read01'/(name+'.json')
    rows[name]=json.loads(checked(local,size,digest));actual_pins[name]=pin(local)
scope,metadata,before=roles.validate_retained(*(rows[n] for n in ('coordinator','stage','launch','inspect','cleanup')))
main=rows['coordinator']['Main_before']
assert main['Main_epoch_sha256']=='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
assert main['three_host_processes_match'] is True and main['resource_limits_match'] is True
assert rows['stage']['coordinator_returncode']==0
expected_counts={'launch':{'target_uid':2,'target_path':2,'helper_uid':2,'helper_path':2,'resolve':1,'stacks':2},
    'inspect':{'target_uid':2,'target_path':2,'helper_uid':4,'helper_path':4,'stacks':2,'instrument':3,'foreground':3},
    'cleanup':{'target_uid':2,'target_path':2,'helper_uid':2,'helper_path':2,'stacks':2}}
for name,count in [('launch',12),('inspect',17),('cleanup',11)]:
    assert rows[name]['command_counts']==expected_counts[name] and rows[name]['durable_command_count']==count
    assert rows[name]['helper_before']==entry.INSTALLED and rows[name]['helper_after']==entry.INSTALLED
    assert rows[name]['target_before']['artifacts']==entry.EXPECTED_TARGET_ARTIFACTS
    assert rows[name]['target_before']['signer_independently_verified'] is False
    assert rows[name]['shared_helper']['whole_process_tree_cleanup_qualified'] is False
assert 'action_lock_released' not in rows['cleanup']
assert rows['cleanup']['action_lock_owner']=='original Flow.cleanup for exact retirement'
role_raw=checked(E/'bestbuy-launch01-public-roles-read01/stdout.log',12446,'ad7febadb3ea1a3216bdabd024041e685c327d0333919f6d752165b9ca1ef62d')
role_actual=json.loads(role_raw);roles.no_raw_ui(role_actual)
assert role_actual['tree_sha256']==metadata['tree_sha256'] and role_actual['window_sha256']==metadata['window_sha256']
assert role_actual['assessment_nonce']==metadata['nonce'] and role_actual['canonical_helper_wire_sha256']==metadata['wire_sha256']
counts=role_actual['public_role_counts']
assert len(counts['fixed_public_role_queries'])==17 and len(counts['fixed_public_resource_queries'])==14
assert all(row['matching_visible_nonpassword_nodes']==0 for row in counts['fixed_public_role_queries'].values())
assert all(row['matching_nodes']==0 for row in counts['fixed_public_resource_queries'].values())
assert counts['fixed_known_class_counts']==dict.fromkeys(roles.PUBLIC_CLASSES,0)|{
    'android.widget.FrameLayout':7,'android.widget.LinearLayout':4,'android.view.ViewGroup':1}

review={'schema':1,'state':'INDEPENDENT_SOURCE_AND_RETAINED_ACTUAL_REVIEW_COMPLETE',
    'install_source':install_frozen,'launch_source':launch_frozen,
    'install_exact_literal_rederivation_files':list(names.values()),
    'install_only_semantic_residuals':mapping['semantic_changes'],
    'launch_exact_rederived_files':['owned_inspect.py','bestbuy_task_context.py','stage_execute.py','make_request.py'],
    'original_envelope_resources_and_deadlines_preserved':True,
    'actual_install_and_metadata_full_original_qualifiers_passed':True,'five_actual_pins':actual_pins,
    'Main_maps_identical_to_original_epoch':13,'phase_durable_command_counts':{'launch':12,'inspect':17,'cleanup':11},
    'task_retired':1012,'baseline_task_ids_preserved':[851],
    'three_APKs_and_exact_helper_10198_unchanged':True,'original_post_termination_state_restored':True,
    'flow_and_held_bindings_closed_all_phases':True,
    'cleanup_action_lock_scope':'original Flow.cleanup owns and releases; no outer action_lock_released field invented',
    'actual_current_foreground':scope,'launcher':'com.bestbuy.android/.activity.SplashActivity',
    'public_roles_actual':pin(E/'bestbuy-launch01-public-roles-read01/stdout.log'),
    'public_query_matches':0,'public_query_count':31,'complete_nodes':12,
    'capture_duration_ms':role_actual['capture_last_elapsed_ms']-role_actual['capture_began_elapsed_ms'],
    'historical_page_type_or_persistent_failure_inferred':False,'future_action_authority':False,
    'shared_helper_whole_process_tree_cleanup_qualified':False,'target_signer_independently_verified':False,
    'whole_app_production_ready':False,'shopping_login_or_purchase_verified':False,'Hepta_or_UI_calls':0}
raw=(json.dumps(review,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
with (OUT/'review.json').open('xb') as f:f.write(raw)
print(json.dumps({'review':pin(OUT/'review.json'),'source_rederivation_complete':True,'actual_five_and_roles_checked':True}))
