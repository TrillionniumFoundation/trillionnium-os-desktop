"""Current-host, per-App Context and owned temporary-source controls; no Android actions."""
import copy
import types
import json

CONTROL_COUNT = 75

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
    rejected('actual_parent_helper_uid_rejected',lambda:entry.uid_from(
        ('package:'+entry.SELF+' uid:'+str(entry.PARENT_HELPER_UID)+'\n').encode()))
    authority=context.qualify_target_metadata(json.loads(files['actual-target-metadata.json']),
        json.loads(files['target-artifact-reference.json']))
    scope=context.baseline_scope(ref,baseline,authority)
    entry.require(scope==context.current_scope() and scope['package']==context.PACKAGE and
                  scope['uid']==context.UID,'ACTUAL_CURRENT_SCOPE_CONSTRUCTION')
    yes('actual_metadata_projects_separate_target_scope_without_changing_baseline')
    def base_no(name,change):
        value=copy.deepcopy(baseline);change(value)
        rejected(name,lambda:context.baseline_scope(ref,value,authority))
    base_no('old_baseline_schema',lambda v:v.update(schema='legacy-activation'))
    base_no('forged_deployment_flag',lambda v:v.update(main_deployed=True))
    base_no('old_framework_epoch',lambda v:v['framework_epoch'].update(sha256='48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'))
    def authority_no(name,change):
        value=copy.deepcopy(authority);change(value)
        rejected(name,lambda:context.baseline_scope(ref,baseline,value))
    def both_metadata(value,uid):
        for key in ('metadata_before','metadata_after'):value[key]['uid']=uid
    def both_directories(value,change):
        for key in ('data_directories_before','data_directories_after'):change(value[key])
    authority_no('wrong_target_uid',lambda v:both_metadata(v,10117))
    authority_no('bool_target_uid',lambda v:both_metadata(v,True))
    authority_no('missing_current_target_directory',lambda v:both_directories(v,lambda rows:rows.pop()))
    authority_no('foreign_current_target_directory_owner',lambda v:both_directories(v,lambda rows:rows[0].update(uid=10117)))
    base_no('baseline_production_claim',lambda v:v.update(whole_app_production_ready=True))
    base_no('previous_current_baseline_schema_rejected',lambda v:v.update(schema='pocket4-main-current-baseline-v1'))
    base_no('previous_current_baseline_kind_rejected',lambda v:v.update(kind='current-framework-generation'))
    for field in ('BASELINE_SHA','QUALIFICATION_SHA'):
        wrong=types.SimpleNamespace(EPOCH=ref.EPOCH,BASELINE_SHA=ref.BASELINE_SHA,
                                    QUALIFICATION_SHA=ref.QUALIFICATION_SHA)
        setattr(wrong,field,'0'*64)
        rejected('wrong_reference_'+field.lower(),lambda wrong=wrong:context.baseline_scope(wrong,baseline,authority))
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
    qa=entry.module(entry.QA_ROOT/'qa_contract.py',qa_manifest['files']['qa_contract.py']['sha256'],'ticket12306_r1_install_plan_contract')
    entry.require(qa.SELF==entry.SELF=='org.droidloom.qa.ticket12306.r1' and
                  qa.PROTOCOL=='pocket4-owned-ticket12306-qa-v1','EXACT_INDEPENDENT_R1_PLAN_CONTRACT')
    actual_plan=context.ordered_commands(qa,entry.SELF,entry.GUEST_APK,entry.STATE_NONCE)
    state_request={'protocol':qa.PROTOCOL,'nonce':entry.STATE_NONCE,'op':'state'}
    qa.validate_request(state_request)
    entry.require(len(actual_plan)==13 and actual_plan[0]==(context.LIST,15,False) and
                  actual_plan[1]==(context.PATHS,15,False) and actual_plan[3]==(entry.INSTALL,40,True) and
                  actual_plan[7]==(qa.instrumentation_argv(state_request),20,False) and
                  sum(item[2] is True for item in actual_plan)==1,'ACTUAL_INDEPENDENT_R1_ORDERED_INSTALL_STATE_PLAN')
    yes('production_ordered_commands_actual_independent_R1_contract_positive')
    rejected('production_ordered_commands_parent_helper_package_rejected',lambda:context.ordered_commands(
        qa,'org.droidloom.qa.bestbuy.r4',entry.GUEST_APK,entry.STATE_NONCE))
    rows.extend(run_source_controls(entry,files,source_manifest_sha256))
    discovery_controls = types.ModuleType('production_current_discovery_controls')
    exec(compile(files['check_current_discovery.py'],'<current-discovery-controls>','exec'),discovery_controls.__dict__)
    legacy_source = entry.read(entry.BASE_HOST_ROOT/'references/android_app.py',131072,
                               discovery_controls.LEGACY_SHA)
    rows.extend(discovery_controls.run_discovery_controls(files['current_discovery.py'],baseline,legacy_source))
    rows.extend(discovery_controls.run_context_route_controls(context,files,baseline,legacy_source,source_manifest_sha256))
    rows.extend(run_independent_target_controls(entry,context,transport,baseline,ref,files,
        source_manifest_sha256,discovery_controls,legacy_source,manifest))
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
            'legacy_discover_failure_reproduced_in_memory':True,
            'independent_target_authority_and_held_route_controls':7,
            'immutable_baseline_packages_modified':False,
            'new_target_held_IO_is_explicit_synthetic_seam':True}


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

def run_independent_target_controls(entry, context, transport, baseline, ref, files,
                                    expected_manifest, discovery_controls, legacy_source, host_manifest):
    """Real authority/open_context functions; filesystem/held-target I/O is explicit synthetic input."""
    import hashlib
    import os
    import time
    from pathlib import PurePosixPath
    rows = []
    authority = json.loads(files['actual-target-metadata.json'])
    artifact = json.loads(files['target-artifact-reference.json'])
    manifest = json.loads(files['SOURCE_PINS.json'])
    root = PurePosixPath('/pure-owned-source')
    original_baseline = copy.deepcopy(baseline)
    def add(name): rows.append({'name':name,'passed':True})
    def reject(name, code, call):
        try:call()
        except RuntimeError as error:
            entry.require(str(error) == code, 'INDEPENDENT_TARGET_CONTROL_WRONG_FIRST_ERROR:'+name)
        else:raise RuntimeError('INDEPENDENT_TARGET_NEGATIVE_ACCEPTED:'+name)
        add(name)
    reads = []
    def memory_read(path, maximum=1048576, expected=None, size=None):
        name = str(path.relative_to(root))
        data = files[name]
        entry.require(type(data) is bytes and len(data) <= maximum and
                      (expected is None or hashlib.sha256(data).hexdigest() == expected) and
                      (size is None or len(data) == size), 'EXACT_MEMORY_SOURCE_READ_REQUIRED')
        reads.append(name)
        return data
    util = types.SimpleNamespace(read=memory_read)
    observed = context.load_target_metadata(util,manifest,root)
    entry.require(observed == authority and reads == ['actual-target-metadata.json','target-artifact-reference.json'] and
                  context.baseline_scope(ref,baseline,observed) == context.current_scope() and
                  baseline == original_baseline, 'PINNED_INDEPENDENT_TARGET_AUTHORITY_POSITIVE')
    add('actual_metadata_loader_and_scope_preserve_original_baseline')
    wrong = copy.deepcopy(manifest);wrong['files']['actual-target-metadata.json']['sha256'] = '0'*64
    reads.clear()
    reject('metadata_source_pin_rejected_before_read','INDEPENDENT_TARGET_AUTHORITY_SOURCE_PINS_REQUIRED',
           lambda:context.load_target_metadata(util,wrong,root))
    entry.require(reads == [], 'UNPINNED_AUTHORITY_READ_ATTEMPTED')
    binding_row = host_manifest['files']['main_binding.py']
    real_binding = entry.module(entry.BASE_HOST_ROOT/'main_binding.py',binding_row['sha256'],
                                'independent_target_real_package_parser')
    def io_fixture(directory_drift=False):
        state = {'opened':[],'closed':[],'target_verify':0,'held_created':0,'held_closed':0,
                 'Main':0,'writes':[],'commands':0}
        records = {}; next_fd = [2000000000]
        def allocate(row):
            next_fd[0] += 1
            fd = next_fd[0];records[fd] = row;state['opened'].append(fd)
            return fd
        def close(fd):
            entry.require(fd in records and fd not in state['closed'], 'ONE_SYNTHETIC_FD_CLOSE')
            state['closed'].append(fd)
        def fstat(fd):
            entry.require(fd in records and fd not in state['closed'], 'LIVE_SYNTHETIC_DIRECTORY_FD')
            row = records[fd]
            return types.SimpleNamespace(st_dev=row['device'],st_ino=row['inode'],
                st_mode=row['mode'],st_uid=row['uid'],st_gid=row['gid'])
        fake_os = types.SimpleNamespace(**{k:v for k,v in vars(os).items()
                                          if k not in ('open','close','fstat')})
        fake_os.close=close;fake_os.fstat=fstat
        known = {r['path']:r for r in authority['data_directories_before']}
        class Target:
            def __init__(self, actual=None, helper_path=None, helper_sha=None):
                state['held_created'] += 1
                self.expected={'pid':baseline['framework_epoch']['binding']['processes']['init']['host_pid']}
                self.helper_sha256=transport.HELD_HELPER_SHA256
                self.record={'synthetic_held_target':True}
            def verify(self):state['target_verify'] += 1
            def read_file(self,path,maximum):
                entry.require(path == '/data/system/packages.list' and maximum == 1024*1024,
                              'ONE_PRIVATE_PACKAGE_LIST_IN_MEMORY')
                return (context.PACKAGE+' '+str(context.UID)+'\n').encode(),{}
            def open_root(self,path,flags):
                entry.require(path in known and flags == os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW,
                              'EXACT_TWO_TARGET_DIRECTORY_PATHS')
                row=copy.deepcopy(known[path])
                if directory_drift:row['inode'] += 1
                return allocate(row)
            def close(self):state['held_closed'] += 1
        namespace=dict(context.__dict__)
        namespace['os']=fake_os
        verify=types.FunctionType(context.verify_target_data.__code__,namespace)
        return state,records,allocate,fake_os,Target,namespace,verify
    state,records,allocate,fake_os,Target,namespace,verify=io_fixture()
    verify(Target(),authority,real_binding)
    entry.require(len(state['opened']) == 2 and state['closed'] == state['opened'] and
                  state['target_verify'] == 2, 'LIVE_FIXED_DIRECTORIES_AND_FD_CLOSURE')
    add('production_target_directory_revalidation_uses_real_package_parser')
    state,records,allocate,fake_os,Target,namespace,verify=io_fixture(True)
    reject('changed_live_target_directory_rejected_and_closed','CURRENT_TARGET_DATA_DIRECTORY_IDENTITY_CHANGED',
           lambda:verify(Target(),authority,real_binding))
    entry.require(len(state['opened']) == 1 and state['closed'] == state['opened'],
                  'REJECTED_DIRECTORY_DESCRIPTOR_NOT_CLOSED')
    def open_fixture(wrong_init=False, wrong_Main=False):
        f=discovery_controls.Fixture(baseline,files['current_discovery.py'],legacy_source)
        state,records,allocate,fake_os,Target,namespace,verify=io_fixture()
        expected=baseline['framework_epoch']['binding']['processes']['init']
        actual={'pid':expected['host_pid'],'start':str(expected['start_ticks']),
            'uid':[str(x) for x in expected['uids']],'ppid':expected['parent_host_pid'],
            'nspid':[str(x) for x in expected['namespace_pids']],
            'exe':expected['executable'],'cgroup':'\n'.join(expected['cgroup']),
            'ns':copy.deepcopy(expected['namespaces'])}
        def open_proc(path,flags):
            entry.require(path == '/proc/'+str(expected['host_pid']) and
                flags == os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                'ONLY_FIXED_CURRENT_INIT_PROC_OPEN')
            return allocate({'synthetic_proc':True})
        fake_os.open=open_proc
        def proc_identity_at(fd,pid,deadline):
            entry.require(fd in records and pid == expected['host_pid'], 'FIXED_INIT_HELD_IDENTITY_INPUT')
            return copy.deepcopy(actual)
        def forbidden(*args,**kwargs):
            state['commands'] += 1
            raise RuntimeError('INDEPENDENT_CONTEXT_ROUTE_CONTROL_COMMAND_FORBIDDEN')
        recorder=types.SimpleNamespace(APP='/pure/original/android_app.py',APP_SHA='a'*64,
            Flow=types.SimpleNamespace(command=forbidden),
            write_new=lambda path,value:state['writes'].append((path,value)))
        held=types.SimpleNamespace(proc_identity_at=proc_identity_at,HeldTarget=Target)
        def main_classpaths(held_module,target,epoch_record,epoch_module,guard):
            entry.require(held_module is held and epoch_record is baseline['framework_epoch'],
                          'ORIGINAL_TWO_ROOT_CLASSPATH_BOUNDARY')
            guard()
            return dict(f.environment),{'synthetic_classpaths':True}
        binding=types.SimpleNamespace(package_uids=real_binding.package_uids,
            same_epoch_identity=real_binding.same_epoch_identity,main_classpaths=main_classpaths)
        def contract_load(name,label):
            return {'recorder.py':recorder,'references/held_runtime_r5.py':held,'main_binding.py':binding}[name]
        contract=types.SimpleNamespace(sha256=context.SHARED_MANIFEST,load=contract_load,verify=lambda:None)
        source=types.SimpleNamespace(HELPER_PATH=PurePosixPath('/pure/held-helper'),
            HELPER_SHA=transport.HELD_HELPER_SHA256,HELPER_BYTES=7,
            verify_shared_helper=lambda:{'synthetic_qualification':True})
        def contract_constructor(path,expected_sha):
            entry.require(path == context.INSTALLED_SHARED/'source-manifest.json' and
                          expected_sha == context.SHARED_MANIFEST, 'ORIGINAL_R6_SOURCE_CONSTRUCTOR_ROUTE')
            return contract
        source.SourceContract=contract_constructor
        def source_verify(expected_sha):
            entry.require(expected_sha == expected_manifest, 'ORIGINAL_INSTALL_SOURCE_PIN_ROUTE')
            return manifest
        def module(path, expected_sha, name):
            if path == context.INSTALLED_SHARED/'source_contract.py':
                entry.require(expected_sha == context.CONTRACT_SHA, 'ORIGINAL_R6_CONTRACT_PIN_ROUTE')
                return source
            if path == context.Path(recorder.APP):
                entry.require(expected_sha == recorder.APP_SHA, 'ORIGINAL_ANDROID_APP_PIN_ROUTE')
                return f.app
            entry.require(path == root/'current_discovery.py' and
                          expected_sha == hashlib.sha256(files['current_discovery.py']).hexdigest(),
                          'ORIGINAL_CURRENT_DISCOVERY_PIN_ROUTE')
            if wrong_init:
                current=types.SimpleNamespace(**vars(f.current))
                original=f.current.discover_current
                def discover(*args):
                    init,env,status=original(*args)
                    return init+1,env,status
                current.discover_current=discover
                return current
            return f.current
        def read(path, maximum=1048576, expected=None, size=None):
            if path == source.HELPER_PATH:
                entry.require(maximum == size == source.HELPER_BYTES and expected == source.HELPER_SHA,
                              'ORIGINAL_SHARED_HELPER_PIN_ROUTE')
                return b'seam-io'
            return memory_read(path,maximum,expected,size)
        util=types.SimpleNamespace(module=module,read=read)
        def guard(baseline_value,epoch_value):
            entry.require(baseline_value is baseline and epoch_value is f.epoch,
                          'ORIGINAL_MAIN_GUARD_ARGUMENT_ROUTE')
            state['Main'] += 1
            value=copy.deepcopy(authority['Main_before'])
            if wrong_Main:value['seven_processes_match']=False
            return value
        ref_view=types.SimpleNamespace(EPOCH=context.CURRENT_EPOCH,BASELINE_SHA=context.BASELINE_SHA,
            QUALIFICATION_SHA=context.QUALIFICATION_SHA,current_baseline=lambda:baseline,
            EPOCH_SOURCE='/pure/original/framework_epoch.py',EPOCH_SOURCE_SHA='b'*64,
            read=lambda path,expected:b'pure-epoch',module=lambda raw,path,name:f.epoch,
            main_guard=guard,write_new=lambda path,value:state['writes'].append((path,value)))
        namespace['verify_target_data']=verify
        opened=types.FunctionType(context.open_context.__code__,namespace)
        result={};step=PurePosixPath('/pure-owned-step')
        def invoke():
            return opened(ref_view,util,expected_manifest,source_verify,root,step,
                          transport,[],result,time.monotonic()+1000)
        return f,state,result,invoke
    f,state,result,invoke=open_fixture()
    ctx,recorder,guard=invoke()
    entry.require(ctx.scope == context.current_scope() and state['held_created'] == 1 and
                  state['held_closed'] == 0 and f.status_calls == 1 and
                  len(f.identity_calls) == 8 and state['Main'] >= 4 and
                  len(state['writes']) == 1 and
                  state['writes'][0][1]['target_package'] == context.PACKAGE and
                  state['writes'][0][1]['target_uid'] == context.UID and
                  state['writes'][0][1]['independent_target_metadata_sha256'] == context.METADATA_RESULT_SHA and
                  state['commands'] == 0 and state['opened'] == state['closed'],
                  'PRODUCTION_INDEPENDENT_OPEN_CONTEXT_MUST_REACH_HELD_RECORD')
    ctx.close()
    entry.require(state['held_closed'] == 1, 'SUCCESSFUL_SYNTHETIC_HELD_TARGET_CLOSE')
    add('production_open_context_reaches_current_discovery_and_independent_held_record')
    f,state,result,invoke=open_fixture(wrong_init=True)
    reject('production_open_rejects_foreign_discovered_init_and_closes_held',
           'FIXED_MAIN_DISCOVERY_CHANGED',invoke)
    entry.require(state['held_created'] == state['held_closed'] == 1 and
                  state['opened'] == state['closed'] and state['commands'] == 0 and
                  state['writes'] == [], 'WRONG_DISCOVERED_INIT_CLOSURE_REQUIRED')
    f,state,result,invoke=open_fixture(wrong_Main=True)
    reject('production_open_rejects_current_Main_mismatch_before_held',
           'INDEPENDENT_METADATA_AND_CURRENT_MAIN_DIFFER',invoke)
    entry.require(state['held_created'] == 0 and state['opened'] == [] and
                  state['commands'] == 0 and state['writes'] == [] and baseline == original_baseline,
                  'MISMATCHED_MAIN_MUST_NOT_ENTER_OR_MUTATE_BASELINE')
    entry.require(len(rows) == 7,'EXACT_SEVEN_INDEPENDENT_TARGET_CONTROLS')
    return rows
