"""Create one independent Clock case from actual new Main and APK receipts.

Preparation and source publication do not authorize Android actions. A copied
task module is admitted against the external frozen packet before any import.
"""
import os
from pathlib import Path
import re
import secrets

REQUIRED_SOURCE_NAMES={'app_common.py','app_runtime.py','clock_alarm_flow.py','clock_alarm_reader.py',
    'clock_api.py','clock_audio_observe.py','clock_case.py','clock_continuation.py','clock_delivery.py',
    'clock_delivery_trial.py','clock_entry.py','clock_expiry_flow.py','clock_model.py','clock_monitor_channel.py','clock_notify_binding.py',
    'clock_notify_proof.py','clock_notify_supervisor.py','clock_plan.py','clock_policy.py','clock_preservation.py',
    'clock_profiles.py','clock_protection.py','clock_selectors.py','clock_session.py','clock_timer_core.py',
    'clock_transport_base.py','runtime_dependencies.json'}
REQUEST_FIELDS={'kind','baseline','qualification','target_identity','native_identity'}
SOURCE_FIELDS=REQUEST_FIELDS|{'schema','support_manifest','framework_epoch_sha256','case_root','run_id','alarm_marker',
    'source_preparation','task_source_manifest','limits','original_gates','Android_UI_actions',
    'whole_app_business_accepted','automatic_retry'}


def preparation(c,ref):
    value=c.parse(c.read_ref(ref,131072));files=value.get('files')
    c.need(value.get('schema')=='pocket4-final-clock-original-case-preparation-v1'
        and value.get('code_entrypoints_complete') is True and value.get('Android_execution_authorized_by_publication') is False
        and type(files) is list and len(files)==len(REQUIRED_SOURCE_NAMES)
        and {Path(row['path']).name for row in files}==REQUIRED_SOURCE_NAMES and len({row['path'] for row in files})==len(files)
        and type(value.get('origins')) is list and 1<=len(value['origins'])<=100,
        'COMPLETE_EXTERNALLY_PINNED_NEW_CLOCK_SOURCE')
    for row in files+value['origins']:c.read_ref(row)
    return value


def named(c,packet,name):
    rows=[row for row in packet['files'] if Path(row['path']).name==name]
    c.need(len(rows)==1,'ONE_EXTERNAL_CLOCK_MODULE:'+name)
    return c.module(rows[0],'new_clock_'+Path(name).stem)


def source_packet(c,value,packet):
    c.need(type(value) is dict and set(value)==SOURCE_FIELDS and value['schema']=='pocket4-clock-fresh-source-v1',
        'EXACT_NEW_CLOCK_SOURCE_SCHEMA')
    root=Path(value['case_root'])
    c.need(root.parent==c.QUALIFICATION and re.fullmatch('business-clock-case-[0-9a-f]{32}',root.name)
        and Path(value['task_source_manifest']['path'])==root/'task-source.json','NEW_PRIVATE_CLOCK_SOURCE_LOCATION')
    task=c.parse(c.read_ref(value['task_source_manifest']))
    expected=[{'path':str(root/'source'/Path(row['path']).name),'bytes':row['bytes'],'sha256':row['sha256']} for row in packet['files']]
    origins=[]
    for row in [value['source_preparation']]+packet['files']+packet['origins']:
        if row not in origins:origins.append(row)
    c.need(set(task)=={'schema','files','origins','original_runtime_authority_transferred'}
        and task['schema']=='pocket4-clock-independent-source-packet-v1' and task['files']==expected
        and task['origins']==origins and task['original_runtime_authority_transferred'] is False,
        'NO_CLOCK_TASK_MODULE_IMPORT_BEFORE_FROZEN_SOURCE_ADMISSION')
    for row in task['files']+task['origins']:c.read_ref(row)
    return task


def inputs(c,request,packet):
    c.need(set(request)==REQUEST_FIELDS,'ACTUAL_NEW_CLOCK_MAIN_AND_TWO_PACKAGE_IDENTITIES')
    p=named(c,packet,'clock_profiles.py');c.need(request['kind'] in p.LIMITS,'ONLY_ORIGINAL_CLOCK_SCOPES')
    _,support=c.support(c.CLOCK_SUPPORT_REF)
    baseline=support['business_baseline.py'].BusinessBaseline(request['baseline'],request['qualification'])
    c.need(baseline.qualification['source_manifest']==c.CLOCK_SUPPORT_REF,'ACTUAL_R8_RETAINED_PREIMAGE_CLOCK_BASELINE')
    identities=[]
    for key,profile in (('target_identity',p.CLOCK),('native_identity',p.NATIVE_HELPER)):
        value=c.parse(c.read_ref(request[key]));c.validate_identity(value,profile,request['baseline'],request['qualification'])
        identities.append(value)
    c.need(baseline.value['data_continuity']['package_uids'][p.PACKAGE]==p.CLOCK['uid'],
        'PREDEPLOYMENT_CLOCK_DATA_UID_CONTINUITY')
    c.read_ref(c.GATES);baseline.guard();return baseline,identities,p


def create_source(c,request,output,prep_ref):
    c.need(os.getuid()==os.geteuid()==0,'ROOT_EXPLICIT_FRESH_CLOCK_SOURCE_FACTORY')
    packet=preparation(c,prep_ref);baseline,_,profiles=inputs(c,request,packet)
    root=Path(output)
    c.need(root.parent==c.QUALIFICATION and re.fullmatch('business-clock-case-[0-9a-f]{32}',root.name),
        'EXPLICIT_NEW_CLOCK_CASE_ROOT')
    root=c.private_dir(root,create=True);src=c.private_dir(root/'source',create=True)
    files=[c.write_new(src/Path(row['path']).name,c.read_ref(row),0o400) for row in packet['files']]
    origins=[]
    for row in [prep_ref]+packet['files']+packet['origins']:
        if row not in origins:origins.append(row)
    task=c.write_new(root/'task-source.json',{'schema':'pocket4-clock-independent-source-packet-v1',
        'files':files,'origins':origins,'original_runtime_authority_transferred':False},0o400)
    run=secrets.token_hex(16)
    value={'schema':'pocket4-clock-fresh-source-v1',**request,'support_manifest':c.CLOCK_SUPPORT_REF,
        'framework_epoch_sha256':baseline.value['framework_epoch']['sha256'],'case_root':str(root),'run_id':run,
        'alarm_marker':'Pocket4 QA alarm '+run if request['kind']=='alarm04' else None,
        'source_preparation':prep_ref,'task_source_manifest':task,'limits':profiles.LIMITS[request['kind']],
        'original_gates':c.GATES,'Android_UI_actions':0,'whole_app_business_accepted':False,'automatic_retry':False}
    source_packet(c,value,packet);baseline.guard();return c.write_new(root/'case-source.json',value,0o400)


def validate_source(c,ref,prep_ref):
    value=c.parse(c.read_ref(ref,131072));packet=preparation(c,prep_ref)
    c.need(value.get('source_preparation')==prep_ref,'CLOCK_SOURCE_NOT_FROM_EXTERNAL_PREPARATION')
    task=source_packet(c,value,packet)
    baseline,identities,profiles=inputs(c,{k:value[k] for k in REQUEST_FIELDS},packet)
    c.need(value['support_manifest']==c.CLOCK_SUPPORT_REF
        and value['framework_epoch_sha256']==baseline.value['framework_epoch']['sha256']
        and re.fullmatch('[0-9a-f]{32}',value['run_id']) and value['alarm_marker']==
            ('Pocket4 QA alarm '+value['run_id'] if value['kind']=='alarm04' else None)
        and value['limits']==profiles.LIMITS[value['kind']] and value['original_gates']==c.GATES
        and value['Android_UI_actions']==0 and value['whole_app_business_accepted'] is False
        and value['automatic_retry'] is False and Path(ref['path'])==Path(value['case_root'])/'case-source.json',
        'EXACT_ORIGINAL_CLOCK_SCOPE_AND_FRESH_INPUTS')
    baseline.guard();return value,baseline,identities,packet,task


def bind(c,request,prep_ref):
    c.need(set(request)=={'source'},'ONE_NEW_CLOCK_SOURCE_FOR_EXECUTION_PLAN')
    source,baseline,identities,packet,task=validate_source(c,request['source'],prep_ref)
    plan={'schema':'pocket4-clock-current-execution-plan-v1',**request,'source_preparation':prep_ref,
        **{k:source[k] for k in ('kind','baseline','qualification','case_root','run_id','alarm_marker',
            'support_manifest','framework_epoch_sha256','task_source_manifest','limits','original_gates')},
        'whole_app_business_accepted':False,'automatic_retry':False}
    return c.write_new(Path(source['case_root'])/'execution-plan.json',plan,0o400)


def validate_plan(c,ref,prep_ref):
    plan=c.parse(c.read_ref(ref,131072))
    keys={'schema','source','source_preparation','kind','baseline','qualification','case_root','run_id','alarm_marker',
        'support_manifest','framework_epoch_sha256','task_source_manifest','limits','original_gates',
        'whole_app_business_accepted','automatic_retry'}
    c.need(set(plan)==keys and plan['schema']=='pocket4-clock-current-execution-plan-v1'
        and plan['source_preparation']==prep_ref,'EXACT_CURRENT_CLOCK_PLAN')
    source,baseline,identities,packet,task=validate_source(c,plan['source'],prep_ref)
    for key in keys-{'schema','source'}:c.need(plan[key]==source[key],'CLOCK_EXECUTION_PLAN_CHANGED:'+key)
    c.need(Path(ref['path'])==Path(source['case_root'])/'execution-plan.json','ONCE_CLOCK_EXECUTION_PLAN_LOCATION')
    return plan,source,baseline,identities,packet,task
