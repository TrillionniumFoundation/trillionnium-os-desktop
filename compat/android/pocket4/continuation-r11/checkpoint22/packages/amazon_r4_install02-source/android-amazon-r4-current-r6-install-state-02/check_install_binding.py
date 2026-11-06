"""Current-host, per-App Context and owned temporary-source controls; no Android actions."""
import copy
import types
import json

CONTROL_COUNT = 68

def run_controls(entry, actual_host, manifest, context, transport, baseline, ref, files, source_manifest_sha256):
    rows = []
    def yes(name):
        rows.append({'name':name,'passed':True})
    def rejected(name, call):
        try:
            call()
        except (RuntimeError,KeyError):
            pass
        else:
            raise RuntimeError('CURRENT_CONTEXT_NEGATIVE_ACCEPTED:'+name)
        yes(name)
    entry.qualify_host_stage(actual_host,manifest)
    yes('complete_actual_host_stage_accepted')
    def host_no(name,change):
        value=copy.deepcopy(actual_host);change(value)
        rejected(name,lambda:entry.qualify_host_stage(value,manifest))
    host_no('host_stage_error',lambda v:v.update(ok=False))
    host_no('old_host_manifest',lambda v:v.update(source_manifest_sha256='52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'))
    host_no('missing_final_Main',lambda v:v.pop('Main_final'))
    host_no('wrong_final_epoch',lambda v:v['Main_final'].update(Main_epoch_sha256='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'))
    host_no('FD_close_incomplete',lambda v:v['source_fds'].update(closed=v['source_fds']['closed']-1))
    host_no('partial_source',lambda v:v.update(all_staged_sources_unchanged=False))
    host_no('controls_count_changed',lambda v:v['controls'].update(count=37))
    host_no('production_claim',lambda v:v.update(whole_app_production_ready=True))
    def host_no_exact(name,change,code):
        value=copy.deepcopy(actual_host);change(value)
        try:entry.qualify_host_stage(value,manifest)
        except RuntimeError as error:entry.require(str(error)==code,'R6_HOST_CONTROL_WRONG_FIRST_ERROR')
        else:raise RuntimeError('R6_HOST_NEGATIVE_ACCEPTED:'+name)
        yes(name)
    host_no_exact('previous_host_stage_schema_rejected',lambda v:v.update(schema='pocket4-current-host-source-stage-result-v1'),
                  'ACTUAL_COMPLETE_R6_HOST_SOURCE_STAGE_REQUIRED')
    host_no_exact('publication_FD_close_incomplete',lambda v:v['publication_fds'].update(closed=v['publication_fds']['closed']-1),
                  'ACTUAL_CURRENT_HOST_SOURCE_FDS_NOT_RETIRED')
    host_no_exact('published_source_leaf_drift',lambda v:v['source_pins']['recorder.py'].update(sha256='0'*64),
                  'ACTUAL_R6_PUBLISHED_SOURCE_PINS_REQUIRED')
    host_no_exact('unauthenticated_owner_chain',lambda v:v['Main_before'].update(authenticated_owner_chain_matches=False),
                  'CURRENT_HOST_STAGE_MAIN_FENCES_CHANGED')
    host_no_exact('current_user_namespace_mismatch',lambda v:v['Main_final'].update(current_user_namespaces_match=False),
                  'CURRENT_HOST_STAGE_MAIN_FENCES_CHANGED')
    host_no_exact('durable_host_stage_pin_drift',lambda v:v['stage_result'].update(sha256='0'*64),
                  'ACTUAL_R6_DURABLE_STAGE_PIN_REQUIRED')
    host_no_exact('compiled_source_name_changed',lambda v:v['controls']['compiled_sources'].__setitem__(0,'foreign.py'),
                  'ACTUAL_38_CURRENT_HOST_CONTROLS_REQUIRED')
    entry.require(entry.uid_from(('package:'+entry.SELF+' uid:99999\n').encode())==99999,
                  'SYNTHETIC_UID_PARSER_POSITIVE')
    yes('synthetic_uid_positive_not_actual_identity')
    rejected('previous_actual_helper_uid_rejected',lambda:entry.uid_from(
        ('package:'+entry.SELF+' uid:'+str(entry.PREVIOUS_HELPER_UID)+'\n').encode()))
    scope=context.baseline_scope(ref,baseline)
    entry.require(scope==context.current_scope() and scope['package']==context.PACKAGE and
                  scope['uid']==context.UID,'ACTUAL_CURRENT_SCOPE_CONSTRUCTION')
    yes('actual_baseline_projects_own_target_scope')
    def base_no(name,change):
        value=copy.deepcopy(baseline);change(value)
        rejected(name,lambda:context.baseline_scope(ref,value))
    base_no('old_baseline_schema',lambda v:v.update(schema='legacy-activation'))
    base_no('forged_deployment_flag',lambda v:v.update(main_deployed=True))
    base_no('old_framework_epoch',lambda v:v['framework_epoch'].update(sha256='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'))
    base_no('wrong_target_uid',lambda v:v['packages'].update({context.PACKAGE:10117}))
    base_no('bool_target_uid',lambda v:v['packages'].update({context.PACKAGE:True}))
    base_no('missing_current_target_directory',lambda v:v['app_directories'].pop('user_de/0/'+context.PACKAGE))
    base_no('foreign_current_target_directory_owner',lambda v:v['app_directories']['user/0/'+context.PACKAGE].update(uid=10117))
    base_no('baseline_production_claim',lambda v:v.update(whole_app_production_ready=True))
    base_no('previous_current_baseline_schema_rejected',lambda v:v.update(schema='pocket4-main-current-baseline-v1'))
    base_no('previous_current_baseline_kind_rejected',lambda v:v.update(kind='current-framework-generation'))
    for field in ('BASELINE_SHA','QUALIFICATION_SHA'):
        wrong=types.SimpleNamespace(EPOCH=ref.EPOCH,BASELINE_SHA=ref.BASELINE_SHA,
                                    QUALIFICATION_SHA=ref.QUALIFICATION_SHA)
        setattr(wrong,field,'0'*64)
        rejected('wrong_reference_'+field.lower(),lambda wrong=wrong:context.baseline_scope(wrong,baseline))
    calls={'Main':0,'target':0,'command':0}
    def forbidden_command(*args,**kwargs):
        calls['command']+=1
        raise RuntimeError('PURE_CONTEXT_CONTROL_COMMAND_FORBIDDEN')
    def fake_guard():
        calls['Main']+=1
    def fake_verify():
        calls['target']+=1
    target=types.SimpleNamespace(expected={'pid':baseline['framework_epoch']['binding']['processes']['init']['host_pid']},
        helper_sha256=transport.HELD_HELPER_SHA256,verify=fake_verify,close=lambda:None)
    recorder=types.SimpleNamespace(Flow=types.SimpleNamespace(command=forbidden_command),
                                  write_new=forbidden_command)
    environment={'PATH':'/system/bin','BOOTCLASSPATH':'/synthetic/boot.jar',
                 'DEX2OATBOOTCLASSPATH':'/synthetic/boot.jar','ANDROID_ROOT':'/system',
                 'ANDROID_DATA':'/data','ANDROID_ART_ROOT':'/apex/com.android.art'}
    def create(value,manifest_sha=context.SHARED_MANIFEST):
        contract=types.SimpleNamespace(sha256=manifest_sha)
        return context.Context(recorder,contract,target,environment,transport,fake_guard,
                               None,[],target.expected['pid'],1,copy.deepcopy(value))
    ctx=create(scope)
    entry.require(ctx.scope==scope and ctx.command_index==ctx.next_command==0 and
                  ctx.action_attempted is False,'PURE_OWN_TARGET_CONTEXT_CONSTRUCTOR')
    yes('production_context_constructor_own_target')
    rejected('constructor_old_R4_manifest',lambda:create(scope,'52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'))
    rejected('constructor_previous_R5_manifest',lambda:create(scope,'6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'))
    def scope_no(name,change):
        value=copy.deepcopy(scope);change(value)
        rejected(name,lambda:create(value))
    scope_no('constructor_old_scope_schema',lambda v:v.update(schema='legacy-scope'))
    scope_no('constructor_Bili_scope',lambda v:v.update(package='tv.danmaku.bili',uid=10117))
    scope_no('constructor_old_epoch',lambda v:v.update(epoch_sha256='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'))
    scope_no('constructor_wrong_baseline',lambda v:v.update(current_baseline_sha256='0'*64))
    scope_no('constructor_wrong_qualification',lambda v:v.update(current_baseline_qualification_sha256='0'*64))
    scope_no('constructor_bool_user',lambda v:v.update(user=False))
    scope_no('constructor_extra_old_activation',lambda v:v.update(activation_sha256='0'*64))
    scope_no('constructor_missing_baseline',lambda v:v.pop('current_baseline_schema'))
    ctx.scope['package']='tv.danmaku.bili'
    rejected('guard_rejects_tampered_target_before_callbacks',lambda:ctx.guard())
    entry.require(calls=={'Main':0,'target':0,'command':0},'PURE_CONTROL_CALLBACK_OR_COMMAND_ATTEMPTED')
    qa_manifest=json.loads(entry.read(entry.QA_ROOT/'SOURCE_PINS.json',131072,entry.QA_MANIFEST))
    qa=entry.module(entry.QA_ROOT/'qa_contract.py',qa_manifest['files']['qa_contract.py']['sha256'],'amazon_r4_install_plan_contract')
    entry.require(qa.SELF==entry.SELF=='org.droidloom.qa.amazon.r4' and
                  qa.PROTOCOL=='pocket4-owned-amazon-qa-v4','EXACT_R4_PLAN_CONTRACT')
    actual_plan=context.ordered_commands(qa,entry.SELF,entry.GUEST_APK,entry.STATE_NONCE)
    state_request={'protocol':qa.PROTOCOL,'nonce':entry.STATE_NONCE,'op':'state'}
    qa.validate_request(state_request)
    entry.require(len(actual_plan)==13 and actual_plan[0]==(context.LIST,15,False) and
                  actual_plan[1]==(context.PATHS,15,False) and actual_plan[3]==(entry.INSTALL,40,True) and
                  actual_plan[7]==(qa.instrumentation_argv(state_request),20,False) and
                  sum(item[2] is True for item in actual_plan)==1,'ACTUAL_R4_ORDERED_INSTALL_STATE_PLAN')
    yes('production_ordered_commands_actual_R4_contract_positive')
    rejected('production_ordered_commands_previous_R3_package_rejected',lambda:context.ordered_commands(
        qa,'org.droidloom.qa.amazon.r3',entry.GUEST_APK,entry.STATE_NONCE))
    rows.extend(run_source_controls(entry,files,source_manifest_sha256))
    discovery_controls = types.ModuleType('production_current_discovery_controls')
    exec(compile(files['check_current_discovery.py'],'<current-discovery-controls>','exec'),discovery_controls.__dict__)
    legacy_source = entry.read(entry.BASE_HOST_ROOT/'references/android_app.py',131072,
                               discovery_controls.LEGACY_SHA)
    rows.extend(discovery_controls.run_discovery_controls(files['current_discovery.py'],baseline,legacy_source))
    rows.extend(discovery_controls.run_context_route_controls(context,files,baseline,legacy_source,source_manifest_sha256))
    entry.require(len(rows)==CONTROL_COUNT and len({x['name'] for x in rows})==CONTROL_COUNT,
                  'EXACT_CURRENT_CONTEXT_CONTROL_COUNT')
    return {'schema':'pocket4-current-app-install-context-controls-v1','all_passed':True,
            'count':CONTROL_COUNT,'cases':rows,'target_package':context.PACKAGE,
            'target_uid':context.UID,'synthetic_context_is_not_runtime_observation':True,
            'production_Context_and_BoundArun_constructors_used':True,
            'actual_qualified_baseline_only_in_memory':True,
            'Bili_Flow_or_MainBinding_instantiated':False,'private_baseline_exported':False,
            'Android_commands':0,'UI_actions':0,'children':0,
            'owned_temporary_source_directories':True,'temporary_directories_removed':True,
            'actual_R6_reference_read_only':True,'production_verify_source_calls':5,
            'new_owner_discovery_controls':18,'production_discovery_and_Context_route_used':True,
            'legacy_discover_failure_reproduced_in_memory':True}


def run_source_controls(entry, files, expected):
    """Run the production source gate in private temporary source directories."""
    import tempfile
    from pathlib import Path
    rows=[]
    entry.require(set(files)==entry.EXPECTED_SOURCE_FILES|{'SOURCE_PINS.json'},
                  'TEMP_SOURCE_FIXTURE_EXACT_SET')
    manifest=json.loads(files['host/source-manifest.json'])
    coordinator=manifest['files']['current_coordinator.py']
    host_manifest=entry.read(entry.BASE_HOST_ROOT/'source-manifest.json',131072,entry.RECORDER_MANIFEST)
    host_source=entry.read(entry.BASE_HOST_ROOT/'current_coordinator.py',131072,
                           entry.REFERENCE_SHA,coordinator['bytes'])
    with tempfile.TemporaryDirectory(prefix='pocket4-current-source-control-') as temporary:
        root=Path(temporary);source=root/'source';source.mkdir(mode=0o700)
        for name,raw in files.items():
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            path.write_bytes(raw);path.chmod(0o600)
        isolated=types.ModuleType('pure_production_source_gate');isolated.__file__=str(source/'install_state.py')
        exec(compile(files['install_state.py'],isolated.__file__,'exec'),isolated.__dict__)
        actual=isolated.verify_source(expected)
        entry.require(actual['files']==json.loads(files['SOURCE_PINS.json'])['files'],
                      'ACTUAL_COMPLETE_PRODUCTION_SOURCE_GATE')
        rows.append({'name':'production_verify_source_actual_R6_reference_positive','passed':True})
        host=root/'host';host.mkdir(mode=0o700)
        (host/'source-manifest.json').write_bytes(host_manifest)
        (host/'current_coordinator.py').write_bytes(host_source)
        isolated.BASE_HOST_ROOT=host
        isolated.verify_source(expected)
        rows.append({'name':'production_verify_source_private_reference_fixture_positive','passed':True})
        def rejected(name):
            try:
                isolated.verify_source(expected)
            except (RuntimeError,FileNotFoundError):
                pass
            else:
                raise RuntimeError('SOURCE_REFERENCE_NEGATIVE_ACCEPTED:'+name)
            rows.append({'name':name,'passed':True})
        (host/'current_coordinator.py').unlink()
        rejected('production_verify_source_missing_R6_coordinator_rejected')
        (host/'current_coordinator.py').write_bytes(host_source+b'\n')
        rejected('production_verify_source_wrong_R6_coordinator_hash_rejected')
        (host/'current_coordinator.py').write_bytes(host_source)
        original=(source/'README.md').read_bytes()
        (source/'README.md').write_bytes(original+b'\n')
        rejected('production_verify_source_payload_hash_changed_rejected')
    entry.require(len(rows)==5,'EXACT_FIVE_SOURCE_CLOSURE_CONTROLS')
    return rows
