#!/usr/bin/env python3
"""Freeze reviewed R7 sources, actual failure basis, controls, and build-only request."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

HERE=Path(__file__).resolve().parent;SOURCE=HERE/'source'
BASE=HERE.parent;OLD=BASE/'owned-bili-qa-r6-reveal-01/source'
E=BASE/'root-recovery-20261104-02/evidence/bili-r6-first-search-foreground05-failure-read01'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(path):
    raw=path.read_bytes();return {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}
def encoded(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def put(name,value):
    path=HERE/name;path.parent.mkdir(parents=True,exist_ok=True)
    raw=value.encode() if isinstance(value,str) else value
    with path.open('xb') as f:f.write(raw)
    return pin(path)
def read_checked(path,size,digest):
    raw=path.read_bytes();assert len(raw)==size and sha(raw)==digest,str(path);return raw
def module(path):
    result=types.ModuleType('local_'+path.stem);result.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),result.__dict__);return result
def ast_functions(source):
    return {n.name:n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
mapping=json.loads((HERE/'literal-rebindings.json').read_bytes())
def normalize(value):
    for a,b in mapping:value=value.replace(a,b)
    return value

manifest_raw=(SOURCE/'SOURCE_PINS.json').read_bytes();manifest=json.loads(manifest_raw)
assert len(manifest['files'])==11
for name,row in manifest['files'].items():read_checked(SOURCE/name,row['bytes'],row['sha256'])
old_manifest=read_checked(OLD/'SOURCE_PINS.json',1478,'6c75b4a976990d4815de58f504912d3f9a7181c0d5a9094c6319180a1279c419')
for name,row in json.loads(old_manifest)['files'].items():read_checked(OLD/name,row['bytes'],row['sha256'])
original_java=normalize((OLD/'src/org/droidloom/qa/bili/r6/ActionRunner.java').read_text())
new_java=(SOURCE/'src/org/droidloom/qa/bili/r7/ActionRunner.java').read_text()
inverse=new_java.replace((HERE/'player_java_block.txt').read_text(),'')
inverse=inverse.replace('            else if (op.equals("player_button")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "transition", "player_frame_sha256");\n','')
inverse=inverse.replace('                else if (op.equals("player_button")) playerButton(request, result);\n','')
inverse=inverse.replace(' || error instanceof PlayerButtonTransaction.Fault','')
assert inverse==original_java,'ORIGINAL_JAVA_GUARDS_CHANGED'
assert (SOURCE/'src/org/droidloom/qa/bili/r7/TouchTransaction.java').read_text()==normalize((OLD/'src/org/droidloom/qa/bili/r6/TouchTransaction.java').read_text())
assert (SOURCE/'src/org/droidloom/qa/bili/r7/PlayerButtonTransaction.java').read_bytes()==(HERE/'PlayerButtonTransaction.java').read_bytes()
builder_new=(SOURCE/'build_candidate.py').read_text()
builder_inverse=builder_new.replace(", 'src/org/droidloom/qa/bili/r7/PlayerButtonTransaction.java'",'').replace(",str(source_java.with_name('PlayerButtonTransaction.java'))",'')
assert builder_inverse==normalize((OLD/'build_candidate.py').read_text())
assert (SOURCE/'stage_build.py').read_text()==normalize((OLD/'stage_build.py').read_text())
old_adapter=ast_functions(normalize((OLD/'qa_adapter.py').read_text()))['Session']
new_adapter=ast_functions((SOURCE/'qa_adapter.py').read_text())['Session']
old_methods={n.name:n for n in old_adapter.body if isinstance(n,ast.FunctionDef)}
new_methods={n.name:n for n in new_adapter.body if isinstance(n,ast.FunctionDef)}
class RemoveNewPlayerBranch(ast.NodeTransformer):
    def visit_If(self,node):
        if isinstance(node.test,ast.Compare) and any(isinstance(n,ast.Constant) and n.value=='player_button' for n in node.test.comparators):return None
        return self.generic_visit(node)
    def visit_Tuple(self,node):
        node=self.generic_visit(node);node.elts=[n for n in node.elts if not isinstance(n,ast.Constant) or n.value!='player_button'];return node
for name in old_methods:
    old=ast.dump(old_methods[name],include_attributes=False)
    if name=='__init__':
        body=ast.unparse(new_methods[name]).replace(', 10184)',' )')
        revised=ast.parse(body).body[0]
    elif name in ('sequence','instrument'):
        revised=RemoveNewPlayerBranch().visit(new_methods[name])
    else:revised=new_methods[name]
    assert ast.dump(revised,include_attributes=False)==old,name

actual={};pins={}
for name,size,digest in [
    ('coordinator',7407,'9b1246c7bd0e7c27baab6f489d644597e5a5d0dbe69d42fefee37e1330efb3de'),
    ('stage',1773,'6d656e3abdf5294cd01f25fb9c09c34df1d60c05650ea05f762745b17daee705'),
    ('launch',5118,'757d1b30cf903e45a970101f35ca1cf82042e91e9dc47d9b8d4df90873904601'),
    ('navigation',243380,'41b4a676ac8ab866c682d4e787f8a2e2b10fd87f9cc481468ec47d94928c8517'),
    ('cleanup',447,'619fafcc87d90c095afc0589265d39c5c69b7b3dbfdeccaa8ddd25eb486fc1b8')]:
    path=E/(name+'.json');actual[name]=json.loads(read_checked(path,size,digest));pins[name]=pin(path)
c,s,l,n,cleanup=(actual[k] for k in ('coordinator','stage','launch','navigation','cleanup'))
assert c['nonce']==s['nonce']==l['nonce']==n['nonce']=='c54a6b039b42371f84903662e8e3762f'
assert c['source_manifest_sha256']==s['source_manifest_sha256']==l['source_manifest_sha256']==n['source_manifest_sha256']=='1219f775585458f7905b7fcf544c0f5c5d2ae15bdb5c30fc09e65daf23362b67'
assert c['Main_before']==c['Main_after']==s['Main_before']==s['Main_after']
assert c['Main_before']['Main_epoch_sha256']=='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
for phase in (l,n):assert all(phase[k] is True for k in ('final_Main_guard_passed','held_binding_released','action_lock_released'))
assert cleanup['ok'] is True and cleanup['outcome_unknown'] is False and cleanup['new_leaf_removed_and_verified'] is True and cleanup['other_tasks_preserved'] is True and cleanup['task_ids_after']==[851]
assert c['owned_task']['task']==1014 and c['owned_task']['prelaunch_task_ids']==[851] and c['owned_task_absent_after_cleanup'] is True
transition=n['playback_button_observation']['transitions'][0];assert len(n['playback_button_observation']['transitions'])==1
assert transition['phase']=='pause' and transition['click_acknowledged'] is False and transition['transition_observed'] is False
failure=n['error']['details']['previous_details']['owned_helper_failure']['helper_rejection']
assert failure['error']=='INSPECTED_TREE_OR_WINDOW_CHANGED' and failure['action_attempted'] is False and failure['outcome_unknown'] is False
capture=failure['tree_observations'][0]
assert len(failure['tree_observations'])==1 and capture['complete'] is True and capture['emitted_nodes']==173 and capture['last_elapsed_ms']-capture['began_elapsed_ms']==97
failed=transition['failed_sequence'];after=transition['independent_sequence']
assert failed['restoration_qualified'] is False and after['restoration_qualified'] is True
for sequence in (failed,after):
    assert sequence['after_state_completed'] is True and sequence['post_state_matches_before'] is True and sequence['post_termination_state']['ui_automation_connected'] is False
    assert sequence['owned_task']==c['owned_task'] and sequence['installed_before']==sequence['installed_after']
assert failed['foreground_before']==failed['foreground_after']==after['foreground_before']==after['foreground_after']
assert n['outcome_unknown'] is True and n['whole_app_production_ready'] is False and n['business_success_verified'] is False
reveal=n['controls_reveal_observation'];gap=failure['started_elapsed_ms']-reveal['input_lifecycle']['finished_time_ms']
assert gap==2038 and reveal['input_acknowledged'] is True and reveal['independent_observation']['node_count']==173
first=n['click_sequence']['first_search_post_ack_foreground']
assert first['first_sample_classification']=='expected_search_focus' and len(first['observations'])==1 and first['observations'][0]['elapsed_ms']==167 and first['waiting_authorized_by_first_explicit_zero'] is False
assert n['player_content_readiness']['qualified'] is True and n['player_content_readiness']['additional_sequences_used']==0
basis=put('bili05-actual-basis.json',encoded({'schema':1,'actual_pins':pins,
    'failed_attempt_preserved':True,'new_task_retired':1014,'preexisting_tasks_preserved':[851],
    'Main_parent_chain_and_child_final_fences_passed':True,'child_held_and_action_locks_released':True,
    'pause_first_error':failure['error'],'pause_action_attempted':False,'pause_outcome_unknown':False,
    'overall_navigation_outcome_unknown':True,'pause_click_acknowledged':False,'automatic_resume_not_performed':True,
    'pause_fresh_inspection_complete_nodes':173,'pause_action_target_complete_nodes':173,'pause_action_target_capture_ms':97,
    'reveal_input_finished_elapsed_ms':reveal['input_lifecycle']['finished_time_ms'],
    'pause_helper_started_elapsed_ms':failure['started_elapsed_ms'],'reveal_finish_to_pause_helper_start_ms':gap,
    'first_failure_before_target_refresh_final_capture_or_click':True,
    'changed_tree_or_window_field_not_retained_and_not_inferred':True,'auto_hide_or_network_cause_inferred':False,
    'pause_failed_sequence_restoration_qualified':False,'pause_after_state_completed_disconnected_and_matches_before':True,
    'subsequent_independent_read_restoration_qualified':True,
    'subsequent_public_role_failure':n['secondary_errors'],
    'first_search_focus_classification':'expected_search_focus','first_search_samples':1,'first_search_elapsed_ms':167,
    'first_search_zero_wait_branch_exercised':False,'content_readiness_additional_wait_branch_exercised':False,
    'business_success_verified':False,'whole_app_production_ready':False}))

player=json.loads((HERE/'python-controls-01/player.stdout.json').read_bytes());assert player['passed']==35
reveal_tests=json.loads((HERE/'python-controls-01/reveal.stdout.json').read_bytes());assert reveal_tests['passed']==21
for name in ('player','reveal'):assert (HERE/('python-controls-01/'+name+'.stderr.log')).read_bytes()==b''
java_controls=json.loads((HERE/'java-controls-01/run.json').read_bytes());assert len(java_controls['commands'])==2 and all(x['returncode']==0 and x['stderr_bytes']==0 for x in java_controls['commands'])
assert json.loads((HERE/'java-controls-01/run.stdout.log').read_text().splitlines()[-1])['passed']==18
class_pins=[pin(path) for path in sorted((HERE/'java-controls-01/classes').rglob('*.class'))]
put('java-controls-01/class-pins.json',encoded({'schema':1,'local_actual_compiled_classes':class_pins,'not_Android_APK_artifacts':True}))
builder=module(SOURCE/'build_candidate.py');old_builder=module(OLD/'build_candidate.py')
assert builder.TOOLS==old_builder.TOOLS and builder.R21_INPUT_RECEIPT_SHA==old_builder.R21_INPUT_RECEIPT_SHA
builder.manifest_contract()
done=subprocess.run([sys.executable,'-I','-B',str(SOURCE/'make_build_request.py'),
    '--source-manifest-sha256',sha(manifest_raw),'--output-dir',str(HERE/'request')],capture_output=True,timeout=10,check=True)
assert not done.stderr;put('request-generation.stdout.json',done.stdout);put('request-generation.stderr.log',done.stderr)
request=json.loads((HERE/'request/exact-request.json').read_bytes());packet=json.loads(request['stdin'])
stage=module(SOURCE/'stage_build.py');raw_files=stage.validate_packet(packet)
assert len(raw_files)==12 and all(raw==(SOURCE/name).read_bytes() for name,raw in raw_files.items())
assert request['executable']=='/usr/bin/python3' and request['args'][:2]==['-I','-c'] and request['timeout_seconds']==300
assert request['memory_max_bytes']==536870912 and request['cpu_quota_percent']==100 and request['nice']==10
assert len(request['stdin'].encode())<=524288
compile(request['args'][-1],'<fixed-build-wrapper>','exec')
put('PACKET_AND_SOURCE_VALIDATION.json',encoded({'schema':1,'source_manifest':pin(SOURCE/'SOURCE_PINS.json'),
    'packet_payload_count':12,'source_file_count':11,'all_packet_files_byte_exact':True,
    'stdin_bytes':len(request['stdin'].encode()),'stdin_sha256':sha(request['stdin'].encode()),
    'envelope_unchanged_resources_timeout_and_operator':True,'seven_tool_table_values_exact_original':True,
    'old_Java_method_bodies_unchanged_after_protocol_namespace_except_explicit_new_dispatch':True,
    'old_Session_methods_AST_unchanged_after_new_op_and_UID_gate_removed':True,
    'build_new_Java_source_required_and_compiled_explicitly':True,'remote_actions':0}))
review=put('source-review.json',encoded({'schema':1,'state':'R7_STATIC_BUILD_CANDIDATE_FROZEN_NOT_SUBMITTED',
    'baseline_source_manifest':pin(OLD/'SOURCE_PINS.json'),'source_manifest':pin(SOURCE/'SOURCE_PINS.json'),
    'actual_failure_basis':basis,'new_package':'org.droidloom.qa.bili.r7','new_protocol':'pocket4-owned-bili-qa-v7',
    'R7_helper_UID':None,'R7_APK_and_signer':None,'R6_source_and_installed_helper_unchanged':True,
    'new_operation_only':'player_button with pause/resume intent, fixed public course and fixed current player role',
    'prior_successful_inspection_role':'context provenance, exact stable public player frame, same host scope, original ten-second maximum age; never old node/action authority',
    'current_authority':'new complete selection capture inside this invocation followed by two complete equal tree/window captures',
    'full_tree_fields_ignored':[],'current_selection_max_age_ms':1000,'maximum_clicks_per_invocation':1,
    'automatic_retry':False,'Android_atomicity_claimed':False,'caller_coordinates_or_arbitrary_selector':False,
    'original_target_refresh_nodehash_eligibility_final_window_and_full_tree_checks_preserved':True,
    'original_helper_restoration_and_after_termination_host_state_guards_preserved':True,
    'failure_or_unknown_does_not_authorize_resume':True,'host_fresh_flow_still_requires_separate_actual_install_binding':True,
    'pure_protocol_predicate_and_Session_controls':{'passed':35,'stdout':pin(HERE/'python-controls-01/player.stdout.json')},
    'original_reveal_regression_controls':{'passed':21,'stdout':pin(HERE/'python-controls-01/reveal.stdout.json')},
    'real_local_Java_production_transaction_controls':{'passed':18,'stdout':pin(HERE/'java-controls-01/run.stdout.log')},
    'full_Android_API_APK_build_performed_locally':False,'full_Android_API_APK_build_requested_for_Root':True,
    'seven_pinned_tools_unchanged':True,'build_command_count':11,'build_memory_bytes':536870912,'build_timeout_seconds':300,
    'UI_business_media_or_audio_success_asserted':False,'whole_app_production_ready':False,'Hepta_or_Android_actions':0,
    'build_request':pin(HERE/'request/exact-request.json')}))
put('README.md','R7 is a separate helper and protocol candidate. Review source/README.md, normalized-semantic-residual.patch, guard-correspondence.json, PACKET_AND_SOURCE_VALIDATION.json and source-review.json. The exact build-only request is request/exact-request.json. Python protocol/Session controls and real local JVM compilation/execution of the production transaction passed; a full Android API/APK build, install and fresh UI execution have not run. The original R6 source and all failed actual attempts remain unchanged. Locally compiled control .class files are reproducible intermediate artifacts and separately pinned in java-controls-01/class-pins.json; the frozen text manifest excludes those binary intermediates.\n')
files={}
for path in sorted(HERE.rglob('*')):
    if not path.is_file() or path.suffix=='.class' or '__pycache__' in path.parts:continue
    raw=path.read_bytes();raw.decode('utf-8','strict')
    files[str(path.relative_to(HERE))]={'bytes':len(raw),'sha256':sha(raw)}
frozen=put('FROZEN_FILES.json',encoded({'schema':1,'files':files,'payload_count':len(files),'remote_actions':0,
    'excluded_reproducible_binary_intermediates':'java-controls-01/classes/**/*.class, separately pinned'}))
print(json.dumps({'state':'FROZEN_BUILD_ONLY_NOT_SUBMITTED','source_manifest':pin(SOURCE/'SOURCE_PINS.json'),
    'request':pin(HERE/'request/exact-request.json'),'request_pins':pin(HERE/'request/REQUEST_PINS.json'),
    'source_review':review,'frozen':frozen,'payload_count':len(files),'key':request['idempotency_key']},sort_keys=True))
