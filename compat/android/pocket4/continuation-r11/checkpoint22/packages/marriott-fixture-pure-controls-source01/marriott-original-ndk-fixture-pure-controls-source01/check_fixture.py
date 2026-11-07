"""Pure regression checks for the frozen, still-unbound original NDK fixture.
No file, process, Android, namespace, or Main operation. Explicit synthetic
observations exercise production parsers and plans; they are not runtime proof.
"""
import copy
import hashlib
import json
import types

def need(value, message):
    if not value:
        raise AssertionError(message)

def run_controls(payload):
    need(type(payload) is dict and set(payload)=={'contract_source','contract_pin',
         'context_source','context_pin','phases_source','phases_pin'},'fixed payload shape')
    modules={}
    for key in ('contract','context','phases'):
        body=payload[key+'_source'].encode('utf-8')
        need(payload[key+'_pin']=={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()},
             key+' source pin')
        module=types.ModuleType('source_only_fixture_'+key)
        module.__file__='<fixed-source-only-'+key+'>'
        exec(compile(body,module.__file__,'exec'),module.__dict__)
        modules[key]=module
    f=modules['contract'];c=modules['context'];p=modules['phases']
    need(f.PENDING_ACTUALS is None and p.PENDING_SOURCE_ROOT is None and
         p.PENDING_SOURCE_MANIFEST is None,'must test unbound source, not an executable fixture')
    cases=[]
    def case(name, check):
        check()
        cases.append({'name':name,'passed':True})
    def reject(callback, code):
        try:
            callback()
        except RuntimeError as error:
            need(str(error)==code,('wrong failure',str(error),code))
        else:
            raise AssertionError('unexpected acceptance: '+code)
    pin={'bytes':123,'sha256':'b'*64}
    install=f.scope('install','1'*32,pin)
    # This normalized shape exists only inside this pure fixture. No real
    # installed identity, UID, build result, or phase authority is supplied.
    synthetic_install={'package':f.PACKAGE,'uid':14000,'user':0,
        'owned_install_qualified':True,'Main_epoch':f.MAIN_EPOCH,'build_result':pin}
    run=f.scope('run','2'*32,pin,synthetic_install)
    retire=f.scope('retire','3'*32,pin,synthetic_install)

    def independent_scope():
        need(f.validate_scope(install)==install and f.validate_scope(run)==run and
             f.validate_scope(retire)==retire,'actual scope validators')
        need(install['uid'] is None and run['uid']==retire['uid']==14000 and
             len({x['attempt_nonce'] for x in (install,run,retire)})==3 and
             not any(x['commercial_App_scope_inherited'] or x['automatic_retry']
                     for x in (install,run,retire)),'separate unallocated/actual UID scope')
    case('three_separate_fixed_fixture_scopes',independent_scope)
    for name,key,value in (
        ('commercial_package','package','tv.danmaku.bili'),
        ('old_epoch','Main_epoch','0'*64),
        ('old_baseline','baseline_sha256','0'*64),
        ('inherited_scope','commercial_App_scope_inherited',True),
        ('automatic_retry','automatic_retry',True)):
        def check(k=key,v=value):
            bad=copy.deepcopy(run);bad[k]=v
            reject(lambda:f.validate_scope(bad),'FIXED_CURRENT_NDK_SCOPE_REQUIRED')
        case('scope_rejects_'+name,check)
    case('install_rejects_adopted_old_UID',lambda:reject(
        lambda:f.scope('install','4'*32,pin,synthetic_install),'INSTALL_CANNOT_ADOPT_OLD_UID_OR_SCOPE'))

    def nonempty_registry():
        argv=f.instrumentation_argv()
        need(len(f.REGISTRY)==len(set(f.REGISTRY))==23 and len(f.FOCUS)==12,'complete list')
        index=argv.index('atf-gtest-list')
        need(argv[index-1]=='-e' and argv[index+1].split(':')==f.REGISTRY and
             argv[argv.index('atf-gtest-filter')+1]=='ProcSelfMaps.*' and
             argv[argv.index('class')+1]==f.JAVA_TEST and argv[-1]==f.RUNNER,
             'actual original Java/JNI arguments')
    case('actual_instrumentation_supplies_complete23_and_exact12_filter',nonempty_registry)
    def empty_list():
        old=f.REGISTRY
        try:
            f.REGISTRY=[]
            reject(f.instrumentation_argv,'FIXED_COMPLETE_ORIGINAL_REGISTRY_REQUIRED')
        finally:
            f.REGISTRY=old
    case('empty_VerifyTestList_cannot_be_admitted',empty_list)

    def bounded_plans():
        guest='/data/local/tmp/p4-ndk-'+install['attempt_nonce']+'/owned-ndk-fixture.apk'
        ip=f.installation_plan(install,guest);rp=f.run_plan(run);ep=f.retirement_plan(retire)
        need((len(ip),len(rp),len(ep))==(8,5,8),'exact phase command counts')
        need(ip[1]==(['/system/bin/cmd','package','install','-R','-t','--user','0',
                    '--pkg',f.PACKAGE,guest],40,True),'original install policy exact')
        forbidden={'--bypass-low-target-sdk-block','-g','-r'}
        need(not forbidden.intersection(ip[1][0]),'no grant, replace, or SDK bypass')
        need(sum(x[0]==f.FORCE_STOP for x in ep)==1 and
             all(x[0]!=f.FORCE_STOP for x in ip+rp),'one retirement-only force stop')
        need(rp[-1]==(f.instrumentation_argv(),60,True) and
             sum(x[2] for x in ip)==sum(x[2] for x in rp)==sum(x[2] for x in ep)==1,
             'one separately bounded mutation per phase')
    case('actual_phase_plans_keep_install_run_retirement_separate',bounded_plans)
    case('run_scope_cannot_invoke_retirement_plan',lambda:reject(
        lambda:f.retirement_plan(run),'RETIREMENT_REQUIRES_NEW_SCOPE'))
    case('install_must_start_from_all_user_absence',lambda:reject(
        lambda:f.package_absent(b'package:com.example.ndk_tests uid:14000\n'),
        'PREEXISTING_NDK_PACKAGE_MUST_NOT_BE_REPLACED'))

    def actual_metadata():
        raw=('package:'+f.PACKAGE+' versionCode:1 uid:14000\n').encode()
        need(f.package_metadata(raw,{10117,10155})==
             {'package':f.PACKAGE,'user':0,'uid':14000,'version_code':1},
             'new UID is actual row, not historical commercial UID')
        reject(lambda:f.package_metadata(raw,{14000}),'NEW_UID_CANNOT_ALIAS_BASELINE_PACKAGES')
    case('package_parser_uses_new_UID_and_rejects_protected_UID',actual_metadata)
    def numeric_process_projection():
        raw=('UID PID NAME\n1000 123 unrelated-private-process\n14000 456 '+f.PACKAGE+'\n').encode()
        result=f.own_processes(raw,14000)
        need(result['own_processes']==[{'uid':14000,'namespace_pid':456,'name':f.PACKAGE}] and
             'unrelated-private-process' not in json.dumps(result) and
             result['kernel_process_identity_or_pidfd_qualification'] is False,
             'only fixed UID body is projected')
        reject(lambda:f.own_processes(raw+b'1000 123 other\n',14000),
               'DUPLICATE_PROCESS_TABLE_PID')
    case('numeric_process_parser_projects_only_fixed_UID',numeric_process_projection)

    success='\n'.join([
        'INSTRUMENTATION_STATUS: class='+f.PACKAGE+'.NdkTests',
        'INSTRUMENTATION_STATUS: test=testMain','INSTRUMENTATION_STATUS_CODE: 1',
        'INSTRUMENTATION_STATUS: class='+f.PACKAGE+'.NdkTests',
        'INSTRUMENTATION_STATUS: test=testMain','INSTRUMENTATION_STATUS_CODE: 0',
        'INSTRUMENTATION_CODE: -1','']).encode()
    case('actual_instrumentation_parser_requires_one_original_testMain',lambda:need(
        f.instrumentation_result(success)['native_XML_still_required'] is True,'XML remains required'))
    case('failed_instrumentation_status_cannot_pass',lambda:reject(
        lambda:f.instrumentation_result(success.replace(b'STATUS_CODE: 0',b'STATUS_CODE: -2')),
        'ONE_ORIGINAL_JAVA_TEST_MUST_COMPLETE_SUCCESSFULLY'))

    def xml_fixture():
        root=f.ET.Element('testsuites',{'tests':'12','failures':'0','disabled':'0',
            'errors':'0','time':'0.1','timestamp':'2000-01-01T00:00:00','name':'AllTests'})
        suite=f.ET.SubElement(root,'testsuite',{'name':'ProcSelfMaps','tests':'12','failures':'0',
            'disabled':'0','skipped':'0','errors':'0','time':'0.1','timestamp':'2000-01-01T00:00:00'})
        for name in f.FOCUS:
            f.ET.SubElement(suite,'testcase',{'name':name.split('.',1)[1],
                'file':'synthetic/proc_self_maps_test.cc','line':'1','status':'run',
                'result':'completed','time':'0.01','timestamp':'2000-01-01T00:00:00',
                'classname':'ProcSelfMaps'})
        return root
    def encode(root):
        return f.ET.tostring(root,encoding='utf-8')
    def exact_xml():
        result=f.native_xml(encode(xml_fixture()))
        need(result['tests']==12 and set(result['native_test_names'])==set(f.FOCUS) and
             result['freshness_and_same_owned_UID_binding_still_required'] is True and
             result['raw_XML_or_failure_body_exported'] is False,'XML parser scope')
    case('actual_XML_parser_requires_exact12_without_runtime_inference',exact_xml)
    for field in ('failures','disabled','skipped','errors'):
        def check(k=field):
            root=xml_fixture();root[0].set(k,'1')
            reject(lambda:f.native_xml(encode(root)),
                   'NO_FAILED_ERRORED_DISABLED_OR_SKIPPED_TEST_ALLOWED')
        case('XML_rejects_'+field,check)
    def duplicate_xml():
        root=xml_fixture();root[0][1].set('name',root[0][0].get('name'))
        reject(lambda:f.native_xml(encode(root)),'UNEXPECTED_OR_DUPLICATE_TESTCASE')
    case('XML_rejects_duplicate_test_body',duplicate_xml)
    def missing_xml():
        root=xml_fixture();root[0].remove(root[0][-1])
        reject(lambda:f.native_xml(encode(root)),'EXACT_TWELVE_TESTCASE_SET_REQUIRED')
    case('XML_rejects_missing_test_body',missing_xml)
    def fake_completed_xml():
        root=xml_fixture();root[0][0].set('status','notrun')
        reject(lambda:f.native_xml(encode(root)),'EXACT_COMPLETED_TESTCASE_REQUIRED')
    case('XML_rejects_unexecuted_test_body',fake_completed_xml)
    case('XML_entity_definitions_are_rejected',lambda:reject(
        lambda:f.native_xml(b'<!DOCTYPE testsuites [<!ENTITY secret "not read">]><testsuites/>'),
        'BOUNDED_ENTITY_FREE_OWN_XML_REQUIRED'))

    class Forbidden:
        def __getattr__(self,name):
            raise AssertionError('unexpected runtime operation in source-only gate: '+name)
    blocked=Forbidden()
    for phase in ('install','run','retire'):
        def check(name=phase):
            if name=='install':
                callback=lambda:p.install_once(blocked,f,blocked,blocked,blocked,blocked,
                                               blocked,blocked)
            elif name=='run':
                callback=lambda:p.run_original_once(blocked,f,blocked,blocked,blocked,blocked,
                                                    blocked,blocked)
            else:
                callback=lambda:p.retire_once(blocked,f,blocked,blocked,blocked,blocked,
                                              blocked,blocked,blocked)
            # Match each actual signature. The first production operation is
            # the pending gate; every other object rejects any IO access.
            reject(callback,'SOURCE_ONLY_ACTUAL_APK_INSTALL_UID_NONCES_UNBOUND')
        case('source_only_'+phase+'_stops_before_any_IO',check)
    case('source_only_context_stops_before_any_IO',lambda:reject(
        lambda:c.open_context(blocked,f,blocked,blocked,blocked,blocked,blocked),
        'SOURCE_ONLY_ACTUAL_APK_INSTALL_UID_NONCES_UNBOUND'))
    case('source_only_source_loader_stops_before_any_IO',lambda:reject(
        p.FixedSources,'SOURCE_ONLY_OWN_ROOT_AND_MANIFEST_UNBOUND'))
    need(len(cases)==30 and len({x['name'] for x in cases})==30,'fixed control count')
    return {'schema':1,'ok':True,'count':len(cases),'cases':cases,
        'pure_production_parsers_and_plans_called':True,'synthetic_IO_only':True,
        'filesystem_reads':0,'filesystem_writes':0,'child_processes':0,'Android_commands':0,
        'Main_namespace_reads':0,'actual_APK_or_UID_bound':False,'runtime_qualified':False,
        'XML_fixture_not_an_actual_test_result':True,'original_source_only_barrier_retained':True}
