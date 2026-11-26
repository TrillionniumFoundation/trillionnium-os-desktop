"""Full current Main/source/identity lease guards for the Settings page case."""
import atexit
import hashlib
import json
import os
from pathlib import Path
import stat
import types

_ENTRIES={}


def prepare(*, runtime):
    c=runtime.c
    c.need(type(runtime.private_context) is dict and set(runtime.private_context)=={'session'},
           'SETTINGS_LIVE_SAME_PROCESS_SESSION_REQUIRED')
    runtime.session=runtime.private_context['session']
    runtime.settings_runtime=c.packet_module(runtime.scope,'settings_runtime.py')
    runtime.host_runtime=c.packet_module(runtime.scope,'app_runtime.py')
    planner=c.packet_module(runtime.scope,'settings_plan.py')
    planner.validate(c,runtime.plan,runtime.view.baseline,runtime.scope)
    c.need(runtime.session.active_ref==runtime.scope['phase_plan']
           and runtime.session.active==runtime.plan,
           'SETTINGS_SESSION_IS_NOT_THIS_FRESH_ACTIVE_PLAN')
    runtime.session.guard(runtime)
    runtime.receipt_witness=c.EvidenceWitness([runtime.scope['phase_plan'],
        runtime.scope['actual_resolution_receipt'],*runtime.scope['installed_helper_receipts'],runtime.plan['lease']])
    runtime.bound.commands=runtime.host_runtime.PhaseCommands(runtime.bound.commands,runtime)


def full_guard(*, attempted=False, runtime):
    c=runtime.c
    c.need(type(attempted) is bool and runtime.receipt_witness is not None,
           'SETTINGS_COMPLETE_PREPARED_GUARD_REQUIRED')
    runtime.receipt_witness.verify(); runtime.artifacts.verify()
    runtime.session.guard(runtime)
    c.need(runtime.phase in ('launch','inspect','cleanup'), 'SETTINGS_UNKNOWN_PHASE')
    if runtime.phase!='launch': runtime.scope_module.load_owned_task(runtime.bound)
    return {'same_fresh_Main':True,'same_actual_packages':True,'lease':runtime.plan['lease'],
            'native_resource_scope_held':True,'whole_app_business_accepted':False}


def _read(ref):
    path=Path(ref['path'])
    if not path.is_absolute() or path.resolve()!=path:
        raise RuntimeError('SETTINGS_GUARD_CANONICAL_SOURCE_REQUIRED')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        first=os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or first.st_nlink!=1 or not 0<first.st_size<=2*1024*1024:
            raise RuntimeError('SETTINGS_GUARD_SOURCE_BOUND')
        with os.fdopen(os.dup(fd),'rb') as stream: raw=stream.read(2*1024*1024+1)
        fields=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        last=os.fstat(fd); named=path.lstat()
        if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256'] or not all(
            getattr(first,k)==getattr(last,k)==getattr(named,k) for k in fields):
            raise RuntimeError('SETTINGS_GUARD_SOURCE_CHANGED')
        return raw
    finally: os.close(fd)


def _entry(context):
    key=context['step']
    if key in _ENTRIES:
        row=_ENTRIES[key]; row.c.need(row.context==context,'SETTINGS_UI_CONTEXT_CHANGED');return row
    scope=context['scope'];packet=json.loads(_read(scope['task_source_manifest']))
    matches=[r for r in packet['files'] if Path(r['path']).name=='app_common.py']
    if len(matches)!=1:raise RuntimeError('ONE_SETTINGS_COMMON_SOURCE_REQUIRED')
    common=types.ModuleType('settings_child_guard_common');common.__file__=matches[0]['path']
    exec(compile(_read(matches[0]),matches[0]['path'],'exec'),common.__dict__)
    common.read_ref(scope['task_source_manifest'])
    plan=common.parse(common.read_ref(scope['phase_plan']))
    host=common.packet_module(scope,'app_runtime.py');runtime=common.packet_module(scope,'settings_runtime.py')
    planner=common.packet_module(scope,'settings_plan.py')
    intent=common.parse(common.regular(Path(key)/'intent.json')[0])
    ctx=intent['case_context']
    common.need(type(ctx) is dict and set(ctx)=={'schema','scope','lease','owned_claim',
                    'observation_number','page','automatic_retry'}
        and ctx['schema']=='pocket4-settings-pages-ui-context-v1'
        and ctx['scope']==context['scope_ref'] and ctx['lease']==plan['lease']
        and type(ctx['observation_number']) is int and 1<=ctx['observation_number']<=9
        and ctx['automatic_retry'] is False
        and intent['request']=={'op':'observe','accessibility_mode':'none'}
        and intent['mutation'] is False,'SETTINGS_READONLY_UI_CONTEXT_REQUIRED')
    runtime.validate_lease(common,host,ctx['lease'],plan,child=True)
    def no_commands(*args):raise RuntimeError('SETTINGS_GUARD_VIEW_CANNOT_EXECUTE')
    view=common.MainView(scope['business_baseline'],scope['business_qualification'],
                        common.private_dir(Path(key)),no_commands,support_ref=scope['support_manifest'])
    artifacts=None;witness=None
    try:
        _,profile=planner.validate(common,plan,view.baseline,scope)
        common.need(ctx['page'] is None or ctx['page'] in profile.PAGES,'SETTINGS_UNDECLARED_PAGE')
        identities=[common.parse(common.read_ref(scope['actual_resolution_receipt']))]+[
            common.parse(common.read_ref(r)) for r in scope['installed_helper_receipts']]
        artifacts=common.HeldArtifacts(view.target,identities)
        witness=common.EvidenceWitness([scope['phase_plan'],scope['actual_resolution_receipt'],
            *scope['installed_helper_receipts'],plan['lease'],ctx['owned_claim']])
        module,modules=common.support(scope['support_manifest'])
        binding=types.SimpleNamespace(scope=scope,scope_ref=context['scope_ref'],
            root=Path(scope['flow_root']),baseline=view.baseline,commands=modules['business_commands.py'])
        claim,ref=module.load_owned_task(binding)
        common.need(ref==ctx['owned_claim'] and claim['package']==profile.PACKAGE,
                    'SETTINGS_CHILD_UI_OWNED_CLAIM_CHANGED')
        row=types.SimpleNamespace(c=common,context=context,plan=plan,scope=scope,
            runtime=runtime,host=host,view=view,artifacts=artifacts,witness=witness,ui_context=ctx)
        def close():
            errors=[]
            for obj in (witness,artifacts,view):
                try:obj.close()
                except BaseException as e:errors.append(e)
            if errors:raise errors[0]
        atexit.register(close);_ENTRIES[key]=row;return row
    except BaseException:
        for obj in (witness,artifacts,view):
            if obj is not None:obj.close()
        raise


def existing_ui_guard(*, attempted=False, entry_context):
    row=_entry(entry_context);c=row.c
    c.need(attempted is False and entry_context['operation']=='observe'
           and entry_context['mutation'] is False,
           'SETTINGS_UI_ENTRY_NEVER_AUTHORIZES_INPUT')
    row.view.guard();row.witness.verify();row.artifacts.verify()
    row.runtime.validate_lease(c,row.host,row.plan['lease'],row.plan,child=True)
    return {'same_fresh_Main':True,'actual_settings_APK_held':True,
            'readonly_page_observation':True,'whole_app_business_accepted':False}
