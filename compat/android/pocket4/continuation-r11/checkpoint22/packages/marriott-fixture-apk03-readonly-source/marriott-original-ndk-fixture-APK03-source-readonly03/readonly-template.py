"""Only qualify the exact completed APK03 public report and run 38 pure fixture controls.
No installation, Android command, namespace entry, process child, or Main read.
The source modules retain all unbound runtime barriers.
"""
import base64
import hashlib
import json
import os
import re
import signal
import stat
import time
import types

PACKET_B64 = None  # Exact UTF8-byte packet binding, not a runtime authority.
PACKET_SHA256 = None
PACKET_BYTES = None
REPORT = '/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-03-20261106/build-result.json'
REPORT_PIN = {'bytes':9811525,'sha256':'02b979004666268ae73814c809ffeba54de261e4c826a130af267fe717f3f46f'}
SOURCE_NAMES = {'fixture_contract.py','fixture_context.py','fixture_transport.py',
                'fixture_phases.py','current_discovery.py'}
MEMBER_NAMES = SOURCE_NAMES | {'check_fixture.py','SOURCE_PINS.json',
    'actual-static-build.json','build-terminal.original.json','build-stdout.original.json'}

class ControlDeadline(BaseException):
    pass

def need(value,code):
    if not value:
        raise RuntimeError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def whole(raw):
    return {'bytes':len(raw),'sha256':sha(raw)}

def identity(path):
    s=os.stat(path,follow_symlinks=False)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,
            'gid':s.st_gid,'nlink':s.st_nlink,'bytes':s.st_size,
            'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}

def public_error(error):
    value=str(error)
    row={'type':type(error).__name__,'errno':getattr(error,'errno',None),
         'message_utf8_bytes':len(value.encode('utf-8','replace')),
         'message_sha256':sha(value.encode('utf-8','replace'))}
    if re.fullmatch('[A-Z][A-Z0-9_: ]{0,159}',value):
        row['code']=value
    return row

def main():
    started=time.monotonic()
    result={'schema':1,'kind':'pocket4-original-ndk-fixture-APK03-readonly-controls01',
        'ok':False,'errors':[],'complete_static_APK_report_qualified':False,
        'source_pins':{},'controls':None,'actual_installed_UID':None,
        'fixture_attempt_nonces':None,'Main_reads':0,'Android_commands':0,
        'namespace_entries':0,'child_processes':0,'explicit_fixture_files_written':0,
        'standard_library_import_IO_included_in_counters':False,
        'global_ambient_FD_equality_asserted':False,
        'runtime_source_barriers_retained':False,'runtime_dispatch_authorized':False,
        'configured_envelope':{'memory_max_bytes':268435456,'cpu_quota_percent':100,
                               'nice':15,'outer_timeout_seconds':60},
        'whole_invocation_resource_observed':False,
        'report_two_full_reads_completed':False,
        'report_read_functions_returned_after_close':False}
    previous_handler=None
    timer_set=False
    def expired(signum,frame):
        raise ControlDeadline('READONLY_CONTROL_DEADLINE')
    def tick():
        need(time.monotonic()-started<35,'READONLY_CONTROL_DEADLINE')
    try:
        need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,
             'FIXED_ORDINARY_UID1000_REQUIRED')
        need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'EXISTING_TIMER_NOT_ADOPTED')
        previous_handler=signal.signal(signal.SIGALRM,expired)
        signal.setitimer(signal.ITIMER_REAL,35)
        timer_set=True
        need(type(PACKET_B64) is str and type(PACKET_BYTES) is int and
             0<PACKET_BYTES<=262144 and type(PACKET_SHA256) is str,
             'FIXED_SOURCE_PACKET_REQUIRED')
        packet_raw=base64.b64decode(PACKET_B64,validate=True)
        need(whole(packet_raw)=={'bytes':PACKET_BYTES,'sha256':PACKET_SHA256},
             'EXACT_UTF8_SOURCE_PACKET_REQUIRED')
        packet=json.loads(packet_raw)
        need(packet.get('schema')==1 and
             packet.get('kind')=='pocket4-original-ndk-fixture-APK03-readonly-controls' and
             set(packet.get('members',{}))==MEMBER_NAMES,'EXACT_TEN_MEMBER_PACKET_REQUIRED')
        data={}
        for name,row in packet['members'].items():
            need(type(row) is dict and set(row)=={'bytes','sha256','body'} and
                 type(row['body']) is str,'EXACT_SOURCE_MEMBER_FIELDS')
            body=row['body'].encode('utf-8')
            need(whole(body)=={k:row[k] for k in ('bytes','sha256')} and
                 0<len(body)<=131072,'EXACT_SOURCE_MEMBER_PIN')
            data[name]=body
            result['source_pins'][name]=whole(body)
        manifest=json.loads(data['SOURCE_PINS.json'])
        need(manifest.get('schema')=='pocket4-original-ndk-fixture-source-v1' and
             set(manifest.get('files',{}))==SOURCE_NAMES and
             all(manifest['files'][name]==whole(data[name]) for name in SOURCE_NAMES),
             'EXACT_FIVE_SOURCE_MANIFEST_REQUIRED')
        modules={}
        for name in sorted(SOURCE_NAMES|{'check_fixture.py'}):
            code=compile(data[name],'<fixed-owned-fixture-'+name+'>','exec')
            if name in ('fixture_contract.py','fixture_phases.py','check_fixture.py'):
                module=types.ModuleType('source_only_'+name.removesuffix('.py'))
                module.__file__='<fixed-owned-fixture-'+name+'>'
                exec(code,module.__dict__)
                modules[name]=module
        fixture=modules['fixture_contract.py']
        phases=modules['fixture_phases.py']
        need(fixture.PENDING_ACTUALS is None and phases.PENDING_SOURCE_ROOT is None and
             phases.PENDING_SOURCE_MANIFEST is None,'RUNTIME_BARRIERS_MUST_REMAIN_UNBOUND')
        result['runtime_source_barriers_retained']=True
        binding=json.loads(data['actual-static-build.json'])
        need(binding.get('kind')=='pocket4-original-ndk-fixture-actual-APK03-static-binding' and
             binding['build_result']['path']==REPORT and
             {k:binding['build_result'][k] for k in ('bytes','sha256')}==REPORT_PIN and
             binding['source_manifest']==whole(data['SOURCE_PINS.json']) and
             binding['installed_UID'] is None and binding['install_run_retire_nonces'] is None and
             binding['runtime_request_generated'] is False and
             binding['Main_or_Android_action_authorized_by_this_binding'] is False,
             'EXACT_ACTUAL_STATIC_BINDING_WITHOUT_RUNTIME_AUTHORITY')
        tick()
        before=identity(REPORT)
        result['report_identity_before']=before
        need(stat.S_ISREG(before['mode']) and stat.S_IMODE(before['mode'])==0o400 and
             before['uid']==before['gid']==1000 and before['nlink']==1 and
             before['bytes']==REPORT_PIN['bytes'],'FIXED_PUBLIC_BUILD_REPORT_SHAPE')
        first=phases.read_exact_file(REPORT,REPORT_PIN['bytes'],REPORT_PIN)
        tick()
        second=phases.read_exact_file(REPORT,REPORT_PIN['bytes'],REPORT_PIN)
        after=identity(REPORT)
        result['report_identity_after']=after
        need(first==second and before==after,'REPORT_TWO_COMPLETE_READS_AND_IDENTITY_CHANGED')
        del second
        result['report_two_full_reads_completed']=True
        result['report_read_functions_returned_after_close']=True
        result['report_pin']=whole(first)
        build=fixture.actual_build(first,REPORT_PIN)
        terminal_pin={k:binding['terminal'][k] for k in ('bytes','sha256')}
        stdout_pin={k:binding['stdout'][k] for k in ('bytes','sha256')}
        fixture.terminal(data['build-terminal.original.json'],terminal_pin,
                         binding['terminal']['job_id'],stdout_pin['bytes'])
        stdout=fixture.exact_bytes(data['build-stdout.original.json'],stdout_pin,32768)
        need(stdout=={'success':True,'path':REPORT,**REPORT_PIN,'first_error':None} and
             build['APK']==binding['APK'] and
             build['signer_sha256']==binding['signature_certificate_sha256'] and
             build['native_members']==binding['native_members'] and
             fixture.REGISTRY==binding['original_registry23'] and
             fixture.FOCUS==binding['exact_focus12'],
             'ACTUAL_BUILD_AND_ORIGINAL_REGISTRY_BINDING_CHANGED')
        result['complete_static_APK_report_qualified']=True
        result['qualified_static_build']=build
        del first
        tick()
        payload={}
        for key,name in (('contract','fixture_contract.py'),('context','fixture_context.py'),
                         ('phases','fixture_phases.py')):
            payload[key+'_source']=data[name].decode('utf-8','strict')
            payload[key+'_pin']=whole(data[name])
        controls=modules['check_fixture.py'].run_controls(payload)
        need(controls.get('ok') is True and controls.get('count')==38 and
             len(controls.get('cases',[]))==38 and
             all(row.get('passed') is True for row in controls['cases']) and
             controls.get('runtime_qualified') is False and
             controls.get('actual_APK_or_UID_bound') is False,
             'EXACT_THIRTY_BASE_AND_EIGHT_CONSTRUCTOR_CONTROLS')
        result['controls']=controls
        tick()
        result['ok']=True
    except BaseException as error:
        result['errors'].append(public_error(error))
    finally:
        if timer_set:
            try:
                signal.setitimer(signal.ITIMER_REAL,0)
            except BaseException as error:
                result['errors'].append(public_error(error))
        if previous_handler is not None:
            try:
                signal.signal(signal.SIGALRM,previous_handler)
            except BaseException as error:
                result['errors'].append(public_error(error))
    result['ok']=bool(result['ok'] and not result['errors'])
    result['elapsed_seconds']=time.monotonic()-started
    encoded=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(encoded)<=65536,'READONLY_SAFE_RESULT_BOUND')
    print(encoded.decode('utf-8'),end='',flush=True)
    return 0 if result['ok'] else 1

if __name__=='__main__':
    raise SystemExit(main())
