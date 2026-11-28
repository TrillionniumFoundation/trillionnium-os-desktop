"""Fresh source/build/pm-proof assembly before any Documents case execution.

Every copy is admitted against the externally pinned preparation before import.
A planned name or pinned receipt alone is never runtime or business evidence.
"""
import os
from pathlib import Path
import re
import secrets
import time
import types

SOURCE_FIELDS={'schema','baseline','qualification','target_identity','provider_identity','native_identity',
    'support_manifest','framework_epoch_sha256','run_id','case_root','source_preparation','task_source_manifest',
    'helper_files','helper_manifest','limits','original_gates','Android_UI_actions','whole_app_business_accepted','automatic_retry'}
REQUEST_FIELDS={'baseline','qualification','target_identity','provider_identity','native_identity'}
REQUIRED_SOURCE_NAMES={'app_runtime.py', 'documents_build.py', 'documents_case.py', 'documents_history.py', 'template_contract.json', 'documents_saf_ui.py', 'app_common.py', 'documents_profiles.py', 'original_dependencies.json', 'documents_entry.py', 'template_SafActivity.java', 'documents_policy.py', 'documents_transport_base.py', 'template_AndroidManifest.xml', 'documents_session.py', 'documents_artifact_inputs.py', 'documents_saf_core.py', 'documents_helper_source.py', 'template_ids.xml', 'documents_api.py', 'documents_plan.py', 'documents_names.py'}


def preparation(c,ref):
    value=c.parse(c.read_ref(ref,131072));files=value.get('files')
    c.need(value.get('schema')=='pocket4-final-documents-saf-case-preparation-v1'
        and value.get('code_entrypoints_complete') is True and value.get('Android_execution_authorized_by_publication') is False
        and type(files) is list and len(files)==len(REQUIRED_SOURCE_NAMES)
        and {Path(r['path']).name for r in files}==REQUIRED_SOURCE_NAMES and len({r['path'] for r in files})==len(files)
        and type(value.get('origins')) is list and 1<=len(value['origins'])<=100,
        'EXACT_COMPLETE_EXTERNALLY_PINNED_DOCUMENTS_SOURCE')
    for row in files+value['origins']:c.read_ref(row)
    return value


def named(c,packet,name):
    found=[r for r in packet['files'] if Path(r['path']).name==name]
    c.need(len(found)==1,'ONE_FROZEN_DOCUMENTS_MODULE:'+name)
    return c.module(found[0],'fresh_documents_'+Path(name).stem)


def source_packet(c,value,packet):
    c.need(type(value) is dict and ((set(value)==SOURCE_FIELDS and value['schema']=='pocket4-documents-saf-fresh-source-v1')
        or (set(value)==SOURCE_FIELDS|{'prebuilt_helper'} and value['schema']=='pocket4-documents-saf-prebuilt-source-v2')),
        'EXACT_NEW_DOCUMENTS_SOURCE_SCHEMA')
    root=Path(value['case_root'])
    c.need(root.parent==c.QUALIFICATION and re.fullmatch('business-documents-saf-case-[0-9a-f]{32}',root.name)
        and Path(value['task_source_manifest']['path'])==root/'task-source.json','NEW_CASE_SOURCE_PACKET_LOCATION')
    task=c.parse(c.read_ref(value['task_source_manifest']))
    expected=[{'path':str(root/'source'/Path(r['path']).name),'bytes':r['bytes'],'sha256':r['sha256']} for r in packet['files']]
    origins=[]
    for row in [value['source_preparation']]+packet['files']+packet['origins']:
        if row not in origins:origins.append(row)
    c.need(set(task)=={'schema','files','origins','original_runtime_authority_transferred'}
        and task['schema']=='pocket4-documents-saf-independent-source-packet-v1' and task['files']==expected
        and task['origins']==origins and task['original_runtime_authority_transferred'] is False,
        'NO_TASK_CODE_BEFORE_EXTERNAL_PREPARATION_ADMISSION')
    for row in task['files']+task['origins']:c.read_ref(row)
    return task


def inputs(c,request,packet):
    c.need(set(request) in (REQUEST_FIELDS,REQUEST_FIELDS|{'prebuilt_helper'}),'ACTUAL_MAIN_AND_THREE_ORIGINAL_PACKAGE_IDENTITIES')
    _,support=c.support(c.SUPPORT_REF)
    baseline=support['business_baseline.py'].BusinessBaseline(request['baseline'],request['qualification'])
    c.need(c.current_qualification_support(request['baseline'], request['qualification'])==c.SUPPORT_REF,'ACTUAL_R5_FINAL_MAIN_FOR_DOCUMENTS')
    p=named(c,packet,'documents_profiles.py');identities=[]
    for key,profile in [('target_identity',p.DOCUMENTS),('provider_identity',p.PROVIDER),('native_identity',p.NATIVE_HELPER)]:
        value=c.parse(c.read_ref(request[key]));c.validate_identity(value,profile,request['baseline'],request['qualification'])
        identities.append(value)
    # The original predeployment continuity receipt covers the canonical 45
    # applications. ExternalStorage is an independently verified provider,
    # outside that target set; its real UID/APK remain checked above and held
    # again by the session, as required by the original feature contract.
    c.need(baseline.value['data_continuity']['package_uids'][p.DOCUMENTS['package']]==p.DOCUMENTS['uid'],
        'ORIGINAL_DOCUMENTS_TARGET_DATA_UID')
    named(c,packet,'documents_history.py').validate(c)
    c.read_ref(c.GATES);baseline.guard();return baseline,identities,p


def templates(c,packet):
    return {name:c.read_ref(next(r for r in packet['files'] if Path(r['path']).name=='template_'+name))
        for name in ('AndroidManifest.xml','SafActivity.java','ids.xml','contract.json')}


def create_source(c,request,output,prep_ref):
    c.need(os.getuid()==os.geteuid()==0,'ROOT_FRESH_SOURCE_ASSEMBLY')
    packet=preparation(c,prep_ref);baseline,_,profiles=inputs(c,request,packet)
    root=Path(output);c.need(root.parent==c.QUALIFICATION
        and re.fullmatch('business-documents-saf-case-[0-9a-f]{32}',root.name),'NEW_PRIVATE_DOCUMENTS_CASE_ROOT')
    normal=named(c,packet,'documents_build.py').read_prebuilt(c,request['prebuilt_helper']) if 'prebuilt_helper' in request else None
    names_module=named(c,packet,'documents_names.py');names=names_module.SAFNames(normal['contract']['run_id'] if normal else secrets.token_hex(8),root)
    render=named(c,packet,'documents_helper_source.py');rendered,manifest=render.render(names,templates(c,packet))
    root=c.private_dir(root,create=True);src=c.private_dir(root/'source',create=True)
    copied=[c.write_new(src/Path(r['path']).name,c.read_ref(r),0o400) for r in packet['files']]
    origins=[]
    for row in [prep_ref]+packet['files']+packet['origins']:
        if row not in origins:origins.append(row)
    task=c.write_new(root/'task-source.json',{'schema':'pocket4-documents-saf-independent-source-packet-v1',
        'files':copied,'origins':origins,'original_runtime_authority_transferred':False},0o400)
    helper=c.private_dir(root/'helper-source',create=True);helper_files={}
    for rel,raw in sorted(rendered.items()):
        path=helper/rel;parents=[];p=path.parent
        while p!=helper:parents.append(p);p=p.parent
        for parent in parents[::-1]:
            if not parent.exists():c.private_dir(parent,create=True)
        helper_files[rel]=c.write_new(path,raw,0o400)
    value={'schema':'pocket4-documents-saf-prebuilt-source-v2' if normal else 'pocket4-documents-saf-fresh-source-v1',**request,'support_manifest':c.SUPPORT_REF,
        'framework_epoch_sha256':baseline.value['framework_epoch']['sha256'],'run_id':names.RUN,'case_root':str(root),
        'source_preparation':prep_ref,'task_source_manifest':task,'helper_files':helper_files,'helper_manifest':manifest,
        'limits':profiles.LIMITS,'original_gates':c.GATES,'Android_UI_actions':0,
        'whole_app_business_accepted':False,'automatic_retry':False}
    source_packet(c,value,packet)
    if normal:named(c,packet,'documents_build.py').require_prebuilt_render(c,value,names,rendered)
    baseline.guard();return c.write_new(root/'helper-source.json',value,0o400)


def validate_source(c,ref,prep_ref):
    value=c.parse(c.read_ref(ref,131072));packet=preparation(c,prep_ref)
    c.need(value.get('source_preparation')==prep_ref,'SOURCE_NOT_FROM_THIS_EXTERNAL_PREPARATION')
    task=source_packet(c,value,packet)
    baseline,identities,profiles=inputs(c,{k:value[k] for k in REQUEST_FIELDS},packet)
    c.need(value['support_manifest']==c.SUPPORT_REF and value['framework_epoch_sha256']==baseline.value['framework_epoch']['sha256']
        and value['limits']==profiles.LIMITS and value['original_gates']==c.GATES and value['Android_UI_actions']==0
        and value['whole_app_business_accepted'] is False and value['automatic_retry'] is False
        and Path(ref['path'])==Path(value['case_root'])/'helper-source.json','EXACT_ORIGINAL_DOCUMENTS_INPUT_CONTRACT')
    names=named(c,packet,'documents_names.py').SAFNames(value['run_id'],Path(value['case_root']))
    rendered,manifest=named(c,packet,'documents_helper_source.py').render(names,templates(c,packet))
    c.need(value['helper_manifest']==manifest and set(value['helper_files'])==set(rendered),
        'EXACT_FRESH_NAME_DERIVATION_FROM_ORIGINAL_HELPER')
    for name,raw in rendered.items():
        row=value['helper_files'][name]
        c.need(Path(row['path'])==Path(value['case_root'])/'helper-source'/name and c.read_ref(row)==raw,
            'GENERATED_HELPER_BYTES_OR_PATH_CHANGED')
    if 'prebuilt_helper' in value:named(c,packet,'documents_build.py').require_prebuilt_render(c,value,names,rendered)
    baseline.guard();return value,baseline,identities,packet,task,names


def observe_pm_help(c,source_ref,output,prep_ref):
    source,baseline,_,packet,_,_=validate_source(c,source_ref,prep_ref)
    root=Path(output);c.need(root.parent==c.QUALIFICATION
        and re.fullmatch('business-documents-saf-pm-help-[0-9a-f]{32}',root.name),'NEW_READONLY_PM_PROOF_ROOT')
    root=c.private_dir(root,create=True);journal=c.private_dir(root/'commands',create=True)
    view=None;calls=0;result={'schema':'pocket4-documents-saf-current-pm-no-replace-v1','state':'FAILED','source':source_ref,
        'source_preparation':prep_ref,'baseline':source['baseline'],'qualification':source['qualification'],
        'ui_actions':0,'package_mutations':0,'automatic_retry':False,'held_binding_closed':False}
    def admission(argv,timeout,root_read,private):
        nonlocal calls
        c.need(calls==0 and argv==['/system/bin/pm','help'] and timeout==15 and not root_read and not private,'ONE_ACTUAL_PM_HELP_READ')
        calls+=1
    try:
        view=c.MainView(source['baseline'],source['qualification'],journal,admission,support_ref=c.SUPPORT_REF)
        runtime=named(c,packet,'app_runtime.py');view.commands=runtime.PhaseCommands(view.commands,types.SimpleNamespace(c=c,deadline=time.monotonic()+60))
        result['guard_before']=view.guard();raw,row=view.command(['/system/bin/pm','help'],15)
        row['result']=c.regular(row.pop('path'),contents=False);row.pop('command_observation');result['observation']=row
        lines=[line for line in raw.decode('utf-8','strict').splitlines() if re.match(r'^\s*-R:',line)]
        c.need([line.strip() for line in lines]==['-R: disallow replacement of existing application'],'ACTUAL_PM_NO_REPLACE_SEMANTICS')
        result.update(no_replace_flag='-R',actual_flag_lines=lines,guard_after=view.guard())
        c.need(result['guard_before']==result['guard_after'],'PM_HELP_MAIN_CHANGED')
        c.read_ref(source_ref);result['state']='ACTUAL_NO_REPLACE_FLAG_VERIFIED'
    except BaseException as exc:
        result['error']={'type':type(exc).__name__,'message':str(exc)};raise
    finally:
        if view is not None:
            try:view.close();result['held_binding_closed']=True
            except BaseException as exc:result['state']='UNKNOWN';result['close_error']=type(exc).__name__
        c.write_new(root/'result.json',result)
    c.need(result['state']=='ACTUAL_NO_REPLACE_FLAG_VERIFIED' and result['held_binding_closed'],'PM_PROOF_NOT_COMPLETE')
    return c.regular(root/'result.json',contents=False)


def validate_native_pm_help(c,v,ref,source_ref,source,baseline):
    # The actual Rust producer retains PackageHelpObservation through Ready ACK.
    # This checks its full comparison; it cannot reconstruct that opaque value.
    c.need(set(v)=={'schema','source','source_preparation','baseline','qualification','stdout','stderr',
        'observation','actual_returncode','no_replace_flag','actual_flag_lines','ui_actions','package_mutations',
        'automatic_retry','application_gate_credit'} and v['schema']=='droidloom.documents-package-help.v2'
        and source['schema']=="pocket4-documents-saf-prebuilt-source-v2"
        and v['source']==source_ref and v['source_preparation']==source['source_preparation']
        and v['baseline']==source['baseline'] and v['qualification']==source['qualification']
        and v['actual_returncode']==0 and v['no_replace_flag']=='-R'
        and v['ui_actions']==v['package_mutations']==0 and v['automatic_retry'] is False
        and v['application_gate_credit'] is False,'EXACT_NATIVE_PM_HELP_COMPARISON')
    root=Path(ref['path']).parent
    c.need(Path(ref['path']).name=='result.json' and root.parent==c.QUALIFICATION
        and re.fullmatch("business-documents-saf-pm-help-[0-9a-f]{32}",root.name)
        and Path(v['stdout']['path'])==root/'stdout' and Path(v['stderr']['path'])==root/'stderr'
        and Path(v['observation']['path'])==root/'OBSERVATION.json','FIXED_NATIVE_PM_HELP_OUTPUTS')
    raw=c.read_ref(v['stdout'],65536);err=c.read_ref(v['stderr'],65536);o=c.parse(c.read_ref(v['observation'],1048576))
    c.need(set(o)=={'schema','logical_argv','actual_factory_argv','request','before_main','after_main',
        'stdout','stderr','stderr_bytes','stderr_sha256','receipt'}
        and o['schema']=='droidloom.package-help-reply.v1'
        and o['logical_argv']==['/system/bin/pm','help']
        and o['actual_factory_argv']==['/system/bin/cmd','package','help']
        and o['request']['schema']=='droidloom.package-help-request.v1'
        and o['request']['main']==o['before_main']==o['after_main']==baseline.value['native_owner']['main']
        and o['request']['application']==baseline.value['native_owner']['application']
        and bytes(o['stdout'])==raw and bytes(o['stderr'])==err==b''
        and o['stderr_bytes']==0 and o['stderr_sha256']==c.sha(b''),'ACTUAL_MAIN_AND_COMPLETE_QUERY_OUTPUT')
    r=o['receipt'];life=r['lifecycle'];execution=r['exec']
    c.need(r['schema']==2 and r['query_waitid_code']==1 and r['query_waitid_status']==0
        and r['cgroup_removed'] is True and r['output_bytes']==len(raw) and r['output_sha256']==c.sha(raw)
        and life['owner']=='instance_factory' and life['release_acknowledged'] is True
        and life['stdio_creator']['waitid_code']==1 and life['stdio_creator']['waitid_status']==0
        and execution['process_selinux']=='u:r:droidloom_query:s0'
        and execution['process_apparmor']=='droidloom-production-android (enforce)'
        and execution['uid']==execution['gid']==2002000 and execution['no_new_privileges'] is True
        and execution['seccomp_filter_mode']==2 and execution['waitid_code']==4
        and execution['waitid_status']==(5|(4<<8)) and execution['event_previous_tid']==r['query_pid'],
        'ACTUAL_QUERY_TRACEEXEC_AND_COMPLETED_RETIREMENT')
    lines=[line for line in raw.decode('utf-8','strict').splitlines() if re.match(r'^\s*-R:',line)]
    c.need(lines==v['actual_flag_lines']
        and [line.strip() for line in lines]==['-R: disallow replacement of existing application'],
        'ACTUAL_PM_NO_REPLACE_SEMANTICS')
    baseline.guard();return v


def validate_pm_help(c,ref,source_ref,source,baseline):
    v=c.parse(c.read_ref(ref,1048576));root=Path(ref['path']).parent
    if source['schema']=="pocket4-documents-saf-prebuilt-source-v2":
        c.need(v.get('schema')=='droidloom.documents-package-help.v2','PREBUILT_SOURCE_REQUIRES_ACTUAL_NATIVE_PM_HELP')
        return validate_native_pm_help(c,v,ref,source_ref,source,baseline)
    c.need(v.get('schema')!='droidloom.documents-package-help.v2','V1_SOURCE_CANNOT_BORROW_V2_QUERY')
    c.need(Path(ref['path']).name=='result.json' and root.parent==c.QUALIFICATION
        and re.fullmatch('business-documents-saf-pm-help-[0-9a-f]{32}',root.name)
        and v.get('schema')=='pocket4-documents-saf-current-pm-no-replace-v1' and v['state']=='ACTUAL_NO_REPLACE_FLAG_VERIFIED'
        and v['source']==source_ref and v['source_preparation']==source['source_preparation']
        and v['baseline']==source['baseline'] and v['qualification']==source['qualification']
        and v['ui_actions']==v['package_mutations']==0 and v['held_binding_closed'] is True
        and v['no_replace_flag']=='-R' and v['automatic_retry'] is False,'COMPLETED_CURRENT_MAIN_PM_HELP_PROOF')
    row=v['observation'];c.need(row['logical']['argv']==['/system/bin/pm','help'] and row['logical']['Android_mutation'] is False,
        'ACTUAL_READONLY_PM_HELP_COMMAND')
    command=c.parse(c.read_ref(row['result']));transport=c.parse(c.read_ref(row['transport']))
    c.need(command['returncode']==0 and command['host_retirement_proved'] is True and command['evidence_complete'] is True
        and command['timed_out'] is False and command['errors']==[] and command.get('first_error') is None
        and transport['lease_entered'] is transport['lease_released'] is transport['host_retirement_proved'] is True
        and transport['error_type'] is None and transport['logical']==row['logical'],
        'REAL_PM_HELP_COMMAND_AND_LEASE_COMPLETION')
    raw=c.read_ref(command['stdout']);c.need(c.read_ref(command['stderr'])==b'','UNEXPECTED_PM_HELP_DIAGNOSTIC')
    lines=[line for line in raw.decode('utf-8','strict').splitlines() if re.match(r'^\s*-R:',line)]
    guard=baseline.guard()
    c.need(lines==v['actual_flag_lines'] and [line.strip() for line in lines]==['-R: disallow replacement of existing application']
        and v['guard_before']==v['guard_after']==transport['post_guard']==guard,'SAME_ACTUAL_PM_FLAG_AND_MAIN')
    return v


def bind(c,request,prep_ref):
    c.need(set(request)=={'source','build','pm_help'},'ACTUAL_SOURCE_BUILD_AND_PM_FLAG_REFERENCES')
    source,baseline,identities,packet,task,names=validate_source(c,request['source'],prep_ref)
    build=named(c,packet,'documents_build.py').verify_build(c,request['build'],prep_ref)
    c.need(build['source']==request['source'],'BUILD_DID_NOT_USE_THIS_FRESH_HELPER_SOURCE')
    validate_pm_help(c,request['pm_help'],request['source'],source,baseline)
    value={'schema':'pocket4-documents-saf-prebuilt-execution-plan-v2' if 'prebuilt_helper' in source else 'pocket4-documents-saf-current-execution-plan-v1',**request,'source_preparation':prep_ref,
        'baseline':source['baseline'],'qualification':source['qualification'],'case_root':source['case_root'],
        'framework_epoch_sha256':baseline.value['framework_epoch']['sha256'],'run_id':names.RUN,
        'task_source_manifest':source['task_source_manifest'],'original_gates':c.GATES,
        'whole_app_business_accepted':False,'automatic_retry':False}
    return c.write_new(Path(source['case_root'])/'execution-plan.json',value,0o400)


def validate_plan(c,ref,prep_ref):
    value=c.parse(c.read_ref(ref,131072))
    c.need(set(value)=={'schema','source','build','pm_help','source_preparation','baseline','qualification','case_root',
        'framework_epoch_sha256','run_id','task_source_manifest','original_gates','whole_app_business_accepted','automatic_retry'}
        and value['schema'] in ('pocket4-documents-saf-current-execution-plan-v1','pocket4-documents-saf-prebuilt-execution-plan-v2') and value['source_preparation']==prep_ref,
        'EXACT_NEW_DOCUMENTS_EXECUTION_PLAN')
    source,baseline,identities,packet,task,names=validate_source(c,value['source'],prep_ref)
    c.need(value['schema']==('pocket4-documents-saf-prebuilt-execution-plan-v2' if 'prebuilt_helper' in source else 'pocket4-documents-saf-current-execution-plan-v1'),
        'SOURCE_AND_EXECUTION_PLAN_VERSION_MUST_MATCH')
    for key in ('baseline','qualification','case_root','framework_epoch_sha256','run_id','task_source_manifest','original_gates'):
        c.need(value[key]==source[key],'EXECUTION_PLAN_SOURCE_BINDING_CHANGED:'+key)
    c.need(Path(ref['path'])==Path(source['case_root'])/'execution-plan.json' and value['whole_app_business_accepted'] is False
        and value['automatic_retry'] is False,'ONCE_NEW_CASE_PLAN_LOCATION_AND_NO_CREDIT')
    build=named(c,packet,'documents_build.py').verify_build(c,value['build'],prep_ref)
    c.need(build['source']==value['source'],'ACTUAL_BUILD_SOURCE_NOT_THIS_CASE')
    validate_pm_help(c,value['pm_help'],value['source'],source,baseline)
    return value,source,baseline,identities,packet,task,names,build
