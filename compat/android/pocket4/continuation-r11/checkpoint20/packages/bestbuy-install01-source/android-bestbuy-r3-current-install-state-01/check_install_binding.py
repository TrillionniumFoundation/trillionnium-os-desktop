"""Pure current-host and per-App Context construction controls; no device authority."""
import copy
import types

CONTROL_COUNT = 33

def run_controls(entry, actual_host, manifest, context, transport, baseline, ref):
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
    host_no('FD_close_incomplete',lambda v:v['owned_fds'].update(closed=v['owned_fds']['closed']-1))
    host_no('partial_source',lambda v:v.update(source_published=False))
    host_no('controls_count_changed',lambda v:v['controls'].update(count=25))
    host_no('production_claim',lambda v:v.update(whole_app_production_ready=True))
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
    entry.require(len(rows)==CONTROL_COUNT and len({x['name'] for x in rows})==CONTROL_COUNT,
                  'EXACT_CURRENT_CONTEXT_CONTROL_COUNT')
    return {'schema':'pocket4-current-app-install-context-controls-v1','all_passed':True,
            'count':CONTROL_COUNT,'cases':rows,'target_package':context.PACKAGE,
            'target_uid':context.UID,'synthetic_context_is_not_runtime_observation':True,
            'production_Context_and_BoundArun_constructors_used':True,
            'actual_qualified_baseline_only_in_memory':True,
            'Bili_Flow_or_MainBinding_instantiated':False,'private_baseline_exported':False,
            'Android_commands':0,'UI_actions':0,'children':0,'filesystem_operations':0}
