"""One fixed host-only entry-control execution for the seven install sources.
38 original pure controls + four explicit manifest constructor seams + eight real
host-owned lease controls. No Main, Android, namespace entry, child or install.
"""
import base64
import hashlib
import json
import os
import re
import signal
import sys
import time
import types

KIND = 'pocket4-original-ndk-install-entry-controls01'
PACKET_SHA256 = '__PACKET_SHA256__'
PACKET_BYTES = __PACKET_BYTES__
PACKET_B64 = '__PACKET_B64__'
SOURCE_NAMES = {
    'fixture_contract.py','fixture_context.py','fixture_transport.py',
    'fixture_phases.py','current_discovery.py','install_lease.py','install_worker.py',
}
CONTROL_NAMES = {'check_fixture.py','check_external_manifest.py','check_install_lease.py'}
OUTPUT_LIMIT = 262144
WORK_SECONDS = 45.0


class Deadline(BaseException):
    pass


def need(value, code):
    if not value:
        raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def error_record(error):
    value={'type':type(error).__name__,'errno':getattr(error,'errno',None)}
    message=str(error)
    if re.fullmatch('[A-Z][A-Z0-9_: ]{0,159}',message):
        value['code']=message
    else:
        raw=message.encode('utf-8','replace')
        value.update(message_bytes=len(raw),message_sha256=digest(raw))
    return value


def member(row,maximum):
    need(type(row) is dict and set(row)=={'body','bytes','sha256'} and
         type(row['body']) is str and type(row['bytes']) is int and
         0<row['bytes']<=maximum and type(row['sha256']) is str and
         re.fullmatch('[0-9a-f]{64}',row['sha256']),'EXACT_PACKET_MEMBER_SHAPE')
    raw=row['body'].encode('utf-8')
    need(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'EXACT_PACKET_MEMBER_HASH')
    return raw


def module(raw,name):
    value=types.ModuleType(name)
    value.__file__='<frozen-entry-controls-'+name+'>'
    exec(compile(raw,value.__file__,'exec'),value.__dict__)
    return value


def main():
    result={'schema':1,'kind':KIND,'ok':False,'errors':[],
        'counts':{'fixture':0,'manifest':0,'lease':0},'cases':[],
        'source_manifest':None,'sources':{},'controls':{},'groups':{},
        'all_owned_control_FDs_closed':False,'all_owned_control_files_removed':False,
        'Main_reads':0,'Android_commands':0,'children':0,
        'namespace_entry':False,'actual_install_nonce_consumed':False,
        'installed_UID':None,'runtime_qualified':False,'automatic_retry':False,
        'original_source_only_barriers_retained':True,
        'standard_library_import_IO_included_in_counters':False,
        'ambient_FD_equality_asserted':False,'whole_invocation_resource_observed':False,
        'work_deadline_seconds':WORK_SECONDS,'outer_timeout_seconds':60,
        'signal_handler_restored':False,'umask_restored':False}
    start=time.monotonic()
    original_handler=None
    original_umask=None
    timer_installed=False
    handler_changed=False
    stage='packet'
    try:
        need(sys.dont_write_bytecode and sys.flags.isolated,
             'ISOLATED_NO_BYTECODE_PYTHON_REQUIRED')
        need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,
             'EXACT_ROOT_HOST_CONTROL_CONTEXT')
        need(type(PACKET_BYTES) is int and 0<PACKET_BYTES<=524288 and
             len(PACKET_B64)<=699052,'FIXED_PACKET_BOUND')
        raw=base64.b64decode(PACKET_B64,validate=True)
        need(len(raw)==PACKET_BYTES and digest(raw)==PACKET_SHA256,'EXACT_PACKET_WHOLE_HASH')
        packet=json.loads(raw)
        need(type(packet) is dict and set(packet)=={'schema','kind','sources','manifest','controls'} and
             packet['schema']==1 and packet['kind']==KIND and
             set(packet['sources'])==SOURCE_NAMES and set(packet['controls'])==CONTROL_NAMES,
             'EXACT_ENTRY_CONTROL_PACKET')
        sources={name:member(row,131072) for name,row in packet['sources'].items()}
        controls={name:member(row,32768) for name,row in packet['controls'].items()}
        manifest_raw=member(packet['manifest'],65536)
        manifest=json.loads(manifest_raw)
        need(type(manifest) is dict and set(manifest)=={'schema','files'} and
             manifest['schema']=='pocket4-original-ndk-fixture-source-v1' and
             set(manifest['files'])==SOURCE_NAMES and
             all(manifest['files'][name]=={'bytes':len(body),'sha256':digest(body)}
                 for name,body in sources.items()),'EXACT_SEVEN_PRODUCTION_SOURCE_MANIFEST')
        result['source_manifest']={'bytes':len(manifest_raw),'sha256':digest(manifest_raw)}
        result['sources']=manifest['files']
        result['controls']={name:{'bytes':len(body),'sha256':digest(body)}
                            for name,body in controls.items()}
        need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),
             'NO_AMBIENT_ALARM_MAY_BE_REPLACED')
        need(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),
             'HOST_CONTROL_ALARM_MUST_NOT_BE_BLOCKED')
        original_handler=signal.getsignal(signal.SIGALRM)
        def alarm(_signum,_frame):
            raise Deadline('HOST_ENTRY_CONTROLS_DEADLINE')
        signal.signal(signal.SIGALRM,alarm)
        handler_changed=True
        signal.setitimer(signal.ITIMER_REAL,WORK_SECONDS)
        timer_installed=True
        original_umask=os.umask(0o077)
        stage='original_fixture38'
        fixture=module(controls['check_fixture.py'],'original_fixture38')
        payload={}
        for label,name in (('contract','fixture_contract.py'),('context','fixture_context.py'),
                           ('phases','fixture_phases.py')):
            payload[label+'_source']=sources[name].decode('utf-8','strict')
            payload[label+'_pin']=manifest['files'][name]
        first=fixture.run_controls(payload)
        result['groups']['fixture']=first
        need(first.get('ok') is True and first.get('count')==38 and
             first.get('runtime_qualified') is False and first.get('child_processes')==0 and
             first.get('Main_namespace_reads')==first.get('Android_commands')==0 and
             first.get('explicit_fixture_filesystem_reads')==0 and
             first.get('explicit_fixture_filesystem_writes')==0,
             'ORIGINAL_38_PRODUCTION_CONTROLS_REQUIRED')
        result['counts']['fixture']=38
        result['cases'].extend(first['cases'])
        stage='external_manifest4'
        manifest_test=module(controls['check_external_manifest.py'],'external_manifest4')
        second=manifest_test.run_controls(sources['fixture_phases.py'].decode('utf-8','strict'),
                                         manifest['files']['fixture_phases.py'])
        result['groups']['manifest']=second
        need(second.get('ok') is True and second.get('count')==4 and
             second.get('source_barriers_restored') is True and
             second.get('actual_files_read')==second.get('children')==second.get('Main_or_Android')==0 and
             second.get('runtime_qualified') is False,
             'FOUR_EXTERNAL_MANIFEST_CONSTRUCTOR_CONTROLS_REQUIRED')
        result['counts']['manifest']=4
        result['cases'].extend(second['cases'])
        stage='real_owned_lease8'
        lease_test=module(controls['check_install_lease.py'],'real_owned_lease8')
        third=lease_test.run_controls(sources,manifest_raw)
        result['groups']['lease']=third
        need(third.get('ok') is True and third.get('count')==8 and
             third.get('all_owned_control_FDs_closed') is True and
             third.get('all_owned_control_files_removed') is True and
             third.get('seams_restored') is True and
             third.get('expected_unlock_failure_preserved') is True and
             third.get('Main_reads')==third.get('Android_commands')==third.get('children')==0 and
             third.get('actual_install_nonce_consumed') is False and
             third.get('runtime_qualified') is False,
             'EIGHT_REAL_OWNED_LEASE_CONTROLS_AND_CLOSURE_REQUIRED')
        result['counts']['lease']=8
        result['cases'].extend(third['cases'])
        need(result['counts']=={'fixture':38,'manifest':4,'lease':8} and
             len(result['cases'])==len({x['name'] for x in result['cases']})==50 and
             all(x.get('passed') is True for x in result['cases']),
             'EXACT_FIFTY_UNIQUE_PASSED_CASES_REQUIRED')
        result['all_owned_control_FDs_closed']=True
        result['all_owned_control_files_removed']=True
        need(time.monotonic()-start<WORK_SECONDS,'HOST_ENTRY_CONTROLS_DEADLINE')
        result['ok']=True
    except BaseException as error:
        result['errors'].append({'stage':stage,**error_record(error)})
    finally:
        if timer_installed:
            try:
                signal.setitimer(signal.ITIMER_REAL,0)
            except BaseException as error:
                result['errors'].append({'stage':'disable_own_timer',**error_record(error)})
        if handler_changed:
            try:
                signal.signal(signal.SIGALRM,original_handler)
                result['signal_handler_restored']=True
            except BaseException as error:
                result['errors'].append({'stage':'restore_handler',**error_record(error)})
        if original_umask is not None:
            try:
                os.umask(original_umask)
                result['umask_restored']=True
            except BaseException as error:
                result['errors'].append({'stage':'restore_umask',**error_record(error)})
    result['elapsed_seconds']=time.monotonic()-start
    result['ok']=bool(result['ok'] and not result['errors'] and
        result['signal_handler_restored'] and result['umask_restored'])
    raw=(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    need(len(raw)<=OUTPUT_LIMIT,'ENTRY_CONTROL_REPORT_BOUND')
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
