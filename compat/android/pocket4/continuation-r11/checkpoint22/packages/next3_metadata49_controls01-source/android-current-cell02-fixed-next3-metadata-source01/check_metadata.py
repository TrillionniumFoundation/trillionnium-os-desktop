#!/usr/bin/env python3
"""Thirteen bounded local parser/first-error controls; no namespace or Android."""
import ast
import copy
import hashlib
import os
import stat
import json
from pathlib import Path
import subprocess
import types

CLOSED_TARGETS={'ticket12306':('com.MobileTicket','12306',275),'hilton':('com.hilton.android.hhonors','Hilton',1004),'united':('com.united.mobile.android','United',3617)}


def base_controls(source,key,exact_row):
    raw=source.encode()
    package,app,version=CLOSED_TARGETS[key]
    assert exact_row=={'package':package,'app':app,'installed_version_code':version,
        'production_ready':False,'status':'CURRENT_EPOCH_BUSINESS_ACCEPTANCE_PENDING',
        'scope':'installed_launcher_inventory_only'}
    m=types.ModuleType('fixed_'+key+'_metadata_controls');m.__file__='/pure-control/'+key+'/read_target.py'
    exec(compile(raw,m.__file__,'exec'),m.__dict__)
    assert m.NONCE=='__FRESH_METADATA_NONCE__' and m.PACKAGE==package and m.HISTORICAL_VERSION==version
    m.NONCE='f'*32  # Synthetic control-only value; never runtime issuance.
    rows=[]
    def record(name,run):
        run();rows.append({'name':name,'passed':True})
    def rejected(call,reason):
        try:call()
        except RuntimeError as e:assert str(e)==reason
        else:raise AssertionError('unexpected acceptance')
    def parse_good():
        result=m.metadata(('package:'+m.PACKAGE+' versionCode:275 uid:14000\n').encode())
        assert result=={'package':m.PACKAGE,'user':0,'uid':14000,'version_code':275}
    record('one_exact_synthetic_package_UID_version',parse_good)
    record('another_package_or_multiple_rows_rejected',lambda:rejected(
        lambda:m.metadata(b'package:unrelated.app versionCode:1 uid:14000\n'),
        'ONE_EXACT_TICKET12306_USER0_METADATA_ROW_REQUIRED'))
    base='/data/app/~~owned-token/'+m.PACKAGE+'-owned-token/base.apk'
    def paths_good():assert m.apk_paths(('package:'+base+'\n').encode())==[base]
    record('one_synthetic_12306_base_path',paths_good)
    record('path_outside_12306_install_directory_rejected',lambda:rejected(
        lambda:m.apk_paths(b'package:/data/app/~~token/other.app-token/base.apk\n'),
        'ONLY_EXACT_TICKET12306_INSTALL_DIRECTORY_APKS_MAY_BE_READ'))
    record('duplicate_APK_path_rejected',lambda:rejected(
        lambda:m.apk_paths((('package:'+base+'\n')*2).encode()),'DUPLICATE_APK_PATH'))

    def lifetime(kind):
        calls={'command':0,'release':0,'guard':0,'verify':0}
        authority=tuple(range(30,37))  # Protocol-only seam; no real FD or exec.
        class Entry:
            def __enter__(self):
                prefix=['/qualified/held-entry','--parent-pid='+str(m.os.getpid()),'--root-fd=30']
                prefix += ['--'+name+'-fd='+str(fd) for name,fd in
                    zip(('mnt','pid','uts','ipc','net','cgroup'),authority[1:])]
                if kind=='bad_prefix':prefix[1]='--target=1'
                return prefix+['--',*self.command],authority
            def __exit__(self,*unused):
                calls['release']+=1
                if kind in ('timeout_release','success_release'):raise OSError(9,'owned lease release seam')
        class Target:
            helper_path='/qualified/held-entry'
            def verify(self):calls['verify']+=1
            def entry(self,command):e=Entry();e.command=command;return e
        class Flow:
            @staticmethod
            def command(context,*args,**kwargs):
                calls['command']+=1;context.command_index+=1
                if kind=='timeout_release':raise subprocess.TimeoutExpired('owned command seam',15)
                r=subprocess.CompletedProcess([],0,b'owned-metadata',b'')
                r.recorder_spawned=True;r.recorder_joined=True;r.host_timed_out=False;r.recorder_errors=[]
                return r
        def guard():calls['guard']+=1
        c=m.Context(types.SimpleNamespace(Flow=Flow),object(),Target(),guard,{})
        try:c.command(list(m.LIST),{'PATH':'/system/bin'})
        except BaseException as e:
            if kind=='timeout_release':
                assert isinstance(e,subprocess.TimeoutExpired)
                assert any('entry_release' in n and 'OSError' in n for n in e.__notes__)
            elif kind=='success_release':assert isinstance(e,OSError) and e.errno==9
            else:assert str(e)=='EXACT_R4_HELD_PREFIX_AND_COMMAND_REQUIRED'
        else:raise AssertionError('expected closure rejection')
        assert calls['guard']==2 and calls['release']==1 and len(c.observations)==1
        assert calls['command']==(0 if kind=='bad_prefix' else 1)
        assert c.observations[0]['Android_UI_action'] is False
        if kind=='success_release':
            assert c.observations[0]['returncode']==0 and c.observations[0]['stdout_bytes']==14
        if kind=='timeout_release':assert len(c.observations[0]['secondary_errors'])==1
    for kind in ('bad_prefix','timeout_release','success_release'):
        record(kind+'_actual_Context_first_error_and_postguard',lambda k=kind:lifetime(k))
    def matrix_package_only():
        value={'exact_row':exact_row,'uid_or_APK_paths_guessed':False,'current_identity_inferred':False}
        assert value['exact_row']==exact_row
        assert value['uid_or_APK_paths_guessed'] is False and value['current_identity_inferred'] is False
        assert m.PACKAGE==value['exact_row']['package'] and len(m.NONCE)==32
    record('historical_45_matrix_binds_package_only_not_current_UID_or_APKs',matrix_package_only)
    def newer_version_observed():
        result=m.metadata(('package:'+m.PACKAGE+' versionCode:'+str(version+1)+' uid:14001\n').encode())
        assert result['version_code']==version+1 and result['uid']==14001 and m.HISTORICAL_VERSION==version
    record('current_version_and_UID_come_from_actual_row_not_historical_number',newer_version_observed)
    def variable_splits():
        split=base.rsplit('/',1)[0]+'/split_xxhdpi.apk'
        assert m.apk_paths(('package:'+split+'\npackage:'+base+'\n').encode())==sorted([base,split])
        assert len(m.apk_paths(('package:'+base+'\n').encode()))==1
    record('one_base_or_multiple_APKs_no_Amazon_three_file_assumption',variable_splits)
    def exact_launcher():
        row=m.component((m.PACKAGE+'/.OwnedSyntheticLauncher\n').encode())
        assert row['component']==m.PACKAGE+'/.OwnedSyntheticLauncher' and row['launch_performed'] is False
        assert row['fallback_used'] is False and row['later_launch_requires_new_current_binding'] is True
        rejected(lambda:m.component(b'other.package/.Main\n'),'LAUNCHER_MUST_BELONG_TO_EXACT_TICKET12306_PACKAGE')
        rejected(lambda:m.component((m.PACKAGE+'/.A\n'+m.PACKAGE+'/.B\n').encode()),'ONE_CURRENT_LAUNCHER_COMPONENT_REQUIRED')
        rejected(lambda:m.component(b'No activity found\n'),'ONE_CURRENT_LAUNCHER_COMPONENT_REQUIRED')
    record('one_exact_launcher_or_fail_without_fallback',exact_launcher)
    def ordered_five_reads():
        seen=[]
        authority=tuple(range(50,57))  # Protocol-only seam, no actual FD authority.
        class Entry:
            def __init__(self,command):self.command=command
            def __enter__(self):
                prefix=['/qualified/held-entry','--parent-pid='+str(m.os.getpid()),'--root-fd=50']
                prefix += ['--'+name+'-fd='+str(fd) for name,fd in zip(('mnt','pid','uts','ipc','net','cgroup'),authority[1:])]
                return prefix+['--',*self.command],authority
            def __exit__(self,*unused):pass
        class Target:
            helper_path='/qualified/held-entry'
            def verify(self):pass
            def entry(self,command):return Entry(command)
        class Flow:
            @staticmethod
            def command(context,argv,timeout,**kwargs):
                assert timeout==15 and kwargs['mutation'] is False and len(kwargs['pass_fds'])==7
                seen.append(argv);context.command_index+=1
                r=subprocess.CompletedProcess(argv,0,b'owned-metadata',b'')
                r.recorder_spawned=True;r.recorder_joined=True;r.host_timed_out=False;r.recorder_errors=[]
                return r
        context=m.Context(types.SimpleNamespace(Flow=Flow),object(),Target(),lambda:None,{})
        assert m.COMMANDS==[m.LIST,m.PATHS,m.RESOLVE,m.PATHS,m.LIST]
        for command in m.COMMANDS:assert context.command(command,{'PATH':'/system/bin'})==b'owned-metadata'
        assert context.command_index==5 and len(seen)==len(context.observations)==5 and context.action_attempted is False
        rejected(lambda:context.command(m.RESOLVE,{'PATH':'/system/bin'}),'ONLY_FIVE_ORDERED_FIXED_READ_ONLY_COMMANDS_ALLOWED')
        assert len(seen)==5
    record('five_ordered_current_identity_paths_launcher_reads_then_closed',ordered_five_reads)
    assert len(rows)==13 and len({r['name'] for r in rows})==13
    return m,[{'name':key+':'+r['name'],'passed':r['passed']} for r in rows]


def run_controls(payload):
    assert set(payload)=={'schema','sources','source_pins','historical_rows','main_binding_source','main_binding_pin'}
    assert payload['schema']==1 and set(payload['sources'])==set(CLOSED_TARGETS)
    rows=[];modules={}
    for key in CLOSED_TARGETS:
        raw=payload['sources'][key].encode()
        assert payload['source_pins'][key]=={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        compile(raw,'<'+key+'-source>','exec')
        module,cases=base_controls(raw.decode(),key,payload['historical_rows'][key])
        modules[key]=module;rows.extend(cases)
    # The new public scope/discovery/directory method bodies are identical
    # across the three independent fixed packages; test these common bodies once.
    bodies=[]
    for key in CLOSED_TARGETS:
        tree=ast.parse(payload['sources'][key])
        nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and
               n.name in ('current_baseline_scope','discover_main','directory_identity','DataDirectories')]
        assert len(nodes)==4
        bodies.append(ast.dump(ast.Module(body=nodes,type_ignores=[]),include_attributes=False))
    assert len(set(bodies))==1
    m=modules['ticket12306']
    def record(name):
        rows.append({'name':name,'passed':True})
    def rejected(call,message):
        try:call()
        except RuntimeError as error:assert str(error)==message,(str(error),message)
        else:raise AssertionError('unexpected acceptance')
    baseline={'schema':'pocket4-main-current-baseline-v2','kind':'current-cell-generation',
        'deployment_performed':False,'framework_exit_cause_resolved':False,'whole_app_production_ready':False,
        'framework_epoch':{'sha256':m.CURRENT_EPOCH},'packages':{'tv.danmaku.bili':10117}}
    ref=types.SimpleNamespace(EPOCH=m.CURRENT_EPOCH,BASELINE_SHA=m.BASELINE_SHA,QUALIFICATION_SHA=m.QUALIFICATION_SHA)
    before=copy.deepcopy(baseline);scope=m.current_baseline_scope(ref,baseline)
    assert baseline==before and m.PACKAGE not in baseline['packages'] and scope['package']==m.PACKAGE
    assert scope['business_action_authority'] is False and scope['Bili_scope_reused'] is False
    record('new_target_metadata_scope_does_not_mutate_or_reuse_baseline_package_authority')
    for field,value,name in [('schema','pocket4-main-current-baseline-v1','previous_baseline_schema'),
                              ('kind','deployment','wrong_generation_kind')]:
        changed=copy.deepcopy(baseline);changed[field]=value
        rejected(lambda:m.current_baseline_scope(ref,changed),'EXACT_CURRENT_CELL02_BASELINE_REQUIRED')
        record(name+'_rejected_by_real_scope_constructor')
    original_load=m.load
    for bad in (False,True):
        calls=[];app=object();epoch=object();guard=object()
        def discover(app_arg,baseline_arg,epoch_arg,guard_arg):
            assert app_arg is app and baseline_arg is baseline and epoch_arg is epoch and guard_arg is guard
            calls.append('discover_current');return (12345,{'synthetic':'only'},{'host_pid':12000})
        def loader(path,pin,name,size):
            assert path==m.SOURCE_PATH.parent/'current_discovery.py' and pin==m.DISCOVERY_SHA and size==8332
            calls.append('load')
            return types.SimpleNamespace(BASELINE_SHA=('0'*64 if bad else m.BASELINE_SHA),
                QUALIFICATION_SHA=m.QUALIFICATION_SHA,MAIN_EPOCH=m.CURRENT_EPOCH,discover_current=discover)
        m.load=loader
        try:
            if bad:
                rejected(lambda:m.discover_main(app,baseline,epoch,guard),'EXACT_CURRENT_DISCOVERY_AUTHORITY')
                assert calls==['load']
            else:
                assert m.discover_main(app,baseline,epoch,guard)[0]==12345
                assert calls==['load','discover_current']
        finally:m.load=original_load
        record('real_discovery_call_'+('rejects_previous_source_authority' if bad else 'forwards_exact_current_baseline_and_guard'))

    binding_raw=payload['main_binding_source'].encode()
    assert payload['main_binding_pin']=={'bytes':len(binding_raw),'sha256':hashlib.sha256(binding_raw).hexdigest()}
    tree=ast.parse(binding_raw)
    f=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='package_uids']
    assert len(f)==1
    binding=types.ModuleType('actual_r6_package_uid_parser');binding.require=m.need
    exec(compile(ast.Module(body=f,type_ignores=[]),'<actual-R6-package-uids>','exec'),binding.__dict__)
    def directories_case(mode):
        active={};closed=[];named=[];reads=[];counter=[100];replacement=[False];uid_changed=[False]
        real_os=m.os;real_time=m.time
        root_paths=['/data/user/0/'+m.PACKAGE,'/data/user_de/0/'+m.PACKAGE]
        identities={path:{'st_dev':5,'st_ino':500+i,'st_mode':stat.S_IFDIR|0o700,'st_uid':14000,'st_gid':14000}
                    for i,path in enumerate(root_paths)}
        class Target:
            def verify(self):pass
            def open_root(self,path,flags):
                assert path in root_paths and flags==os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW
                named.append(path)
                if mode=='second_open_failed' and len(named)==2:raise OSError(2,'synthetic missing second directory')
                value=dict(identities[path])
                if mode=='wrong_uid' and len(named)==1:value['st_uid']=14001
                if replacement[0]:value['st_ino']+=1000
                counter[0]+=1;fd=counter[0];active[fd]=types.SimpleNamespace(**value)
                return fd
            def read_file(self,path,maximum,deadline):
                assert path=='/data/system/packages.list' and maximum==1024*1024 and deadline==5
                reads.append(path)
                raw=(m.PACKAGE+' '+str(14001 if uid_changed[0] else 14000)+' ignored\nunrelated.package 14002 ignored\n').encode()
                return raw,{'synthetic':True}
        def close(fd):
            assert fd in active
            del active[fd];closed.append(fd)
        m.os=types.SimpleNamespace(O_PATH=os.O_PATH,O_DIRECTORY=os.O_DIRECTORY,O_NOFOLLOW=os.O_NOFOLLOW,
            fstat=lambda fd:active[fd],close=close)
        m.time=types.SimpleNamespace(monotonic=lambda:0)
        obj=None
        try:
            try:obj=m.DataDirectories(Target(),14000,binding,30)
            except BaseException as error:
                if mode=='wrong_uid':assert str(error)=='CURRENT_TARGET_DATA_DIRECTORY_OWNER_REQUIRED'
                elif mode=='second_open_failed':assert isinstance(error,OSError) and error.errno==2
                else:raise
                assert not active and len(closed)==1
                return
            assert mode not in ('wrong_uid','second_open_failed')
            if mode=='changed_package_uid':
                uid_changed[0]=True
                rejected(obj.record,'FIXED_BILIBILI_OR_ACTION_RUNNER_UID_CHANGED')
            elif mode=='named_directory_changed':
                replacement[0]=True
                rejected(obj.record,'NAMED_TARGET_DATA_DIRECTORY_CHANGED')
            else:
                a=obj.record();b=obj.record()
                assert a==b and [x['path'] for x in a]==root_paths and all(x['uid']==14000 for x in a)
                assert len(active)==2 and all(p=='/data/system/packages.list' for p in reads)
            result=obj.close()
            assert result=={'held_data_directory_FDs_closed':2,'contents_read':False} and not active
        finally:
            if obj is not None and not obj.closed:obj.close()
            m.os=real_os;m.time=real_time
    for mode in ('positive','wrong_uid','second_open_failed','changed_package_uid','named_directory_changed'):
        directories_case(mode);record('production_two_directory_lifetime_'+mode)
    assert len(rows)==49 and len({r['name'] for r in rows})==49
    return {'schema':1,'ok':True,'count':49,'cases':rows,'fixed_targets':list(CLOSED_TARGETS),
        'source_pins':payload['source_pins'],'original_parser_and_Context_cases_per_target':13,
        'current_scope_discovery_and_directory_cases':10,'synthetic_IO_only':True,
        'actual_UID_or_version_or_APK_observed':False,'private_directory_contents_read':False,
        'filesystem_writes':0,'child_processes':0,'Android_commands':0,'App_launches':0,'UI_actions':0,
        'new_target_runtime_scope_authorized':False,'whole_app_production_ready':False}
