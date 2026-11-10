#!/usr/bin/python3 -I
"""Verify the isolated Calendar11 APK with installed ART; inert without --execute.

Reuses the already executed ART22 descriptor transport and dependency snapshot,
but runs an APK PCL[] context and requires every added/modified class Verified.
No installation, task, notification, provider, service restart, or UI operation.
"""
from pathlib import Path
import argparse,contextlib,datetime,gzip,hashlib,json,os,re,resource,stat,time,zipfile

STORAGE=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12')
OUT=Path('/home/alex/work/pocket4-calendar-art-verification-20261105-r12-11')
BUILD=Path('/home/alex/work/pocket4-calendar-repair-build-20261105-r12-11')
BUILD_SHA='ec9ce6f9c8e31d021992d59d86ce4319743496debff50e24ef7da8be544c96e9'
APK_SHA='00cb0b0a3e33a0bf79814a83c3c5900a3c10d9c41719d38e1e146a0ae134a85f'
INSTALLED_SHA='7872aa56b6aa35f4509a27a2c3c0ebb8743da7096136155e425f5b1e4499ae8e'
INSTALL=Path('/home/alex/work/pocket4-calendar-repair-install-20261105-r12-10/result.json')
INSTALL_SHA='253c98a9d27f1b5bb45e01cdda6042e0d43b2f268b3c0a228bf93a639b38f957'
TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ACTIVATION_SHA='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
ART_LIB_SHA='e5de57780be072ced10a5beba049fe89e89e381d6a66a974a8f298ef34cf2742'
DISCOVERY_LIB_SHA='605a30fe58ad9fb49bb62d85750a2d558686ea5730d000b3d703e88dde9e8aa5'
DISCOVERY_SHA='614f0c61ec4956a626edb06950bb6b7494ed856dc1dc2c45ac8bfd748421bab9'
MANIFEST_SHA='4745f217753636e077e65c7308123ab636dfec719ab0826f759bb14a547927dd'
UNIT='pocket4-calendar-art-verify11-r12.service'

def need(value,reason):
    if not value:raise RuntimeError(reason)
def sha(data):return hashlib.sha256(data).hexdigest()
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def load(path,pin,name):
    import types
    raw=path.read_bytes();need(sha(raw)==pin,'SOURCE_PIN:'+name)
    value=types.ModuleType(name);value.__file__=str(path);exec(compile(raw,str(path),'exec'),value.__dict__);return value

def limits_and_usage(require_limits=True):
    relative='/system.slice/'+UNIT
    need(Path('/proc/self/cgroup').read_text().strip()=='0::'+relative,'NOT_OWNED_ART_UNIT')
    cg=Path('/sys/fs/cgroup')/relative.lstrip('/')
    values={n:(cg/n).read_text().strip() for n in ('memory.max','memory.swap.max','cpu.max','pids.max')}
    if require_limits:
        quota,period=map(int,values['cpu.max'].split())
        need(values['memory.max']=='2147483648' and values['memory.swap.max']=='0'
             and quota==2*period and values['pids.max']=='64','RESOURCE_LIMITS_CHANGED')
        need(os.sched_getaffinity(0)=={20,21},'CPU_AFFINITY_CHANGED')
        need(resource.getrlimit(resource.RLIMIT_CORE)==(0,0),'CORE_NOT_DISABLED')
        need(resource.getrlimit(resource.RLIMIT_FSIZE)==(268435456,268435456),'OUTPUT_LIMIT_CHANGED')
    return {'limits':values,'memory_peak_bytes':int((cg/'memory.peak').read_text()),
        'memory_events':{k:int(v) for k,v in (x.split() for x in (cg/'memory.events').read_text().splitlines())},
        'cpu_stat':(cg/'cpu.stat').read_text()}

def prepare(tx,art,stack):
    directory=OUT/'candidate';directory.mkdir(mode=0o750);os.chown(directory,0,1000)
    raw=tx.read_regular(BUILD/'Calendar-pocket4-functional.apk',APK_SHA,maximum=8*1024*1024)
    art.own_file(directory/'candidate.apk',raw,stack,mode=0o444,uid=0)
    source=os.open(directory/'candidate.apk',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);stack.callback(os.close,source)
    marker=('calendar-art11:'+APK_SHA+'\n').encode()
    art.own_file(directory/'marker',marker,stack,mode=0o444,uid=0)
    markfd=os.open(directory/'marker',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);stack.callback(os.close,markfd)
    oat=art.own_file(directory/'candidate.odex',b'',stack)
    vdex=art.own_file(directory/'candidate.vdex',b'',stack)
    os.chmod(directory,0o555)
    dirfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);stack.callback(os.close,dirfd)
    need(art.pin_fd(source)['sha256']==APK_SHA,'OWNED_APK_COPY_CHANGED')
    return {'source':source,'oat':oat,'vdex':vdex,'directory':dirfd,'marker':markfd}

def all_target_statuses(text,expected):
    pattern=re.compile(r'^\d+: (L[^;]+;) \(offset=0x[0-9a-f]+\) \(type_idx=\d+\) \(([^)]+)\) \(([^)]+)\)$',re.M)
    rows={}
    for match in pattern.finditer(text):
        descriptor,status,kind=match.groups();need(descriptor not in rows,'DUPLICATE_CLASS_STATUS:'+descriptor)
        rows[descriptor]={'status':status,'compilation_kind':kind,'header':match[0]}
    need(rows,'ACTUAL_CLASS_STATUS_GRAMMAR_REQUIRED')
    missing=sorted(set(expected)-set(rows));unverified={n:rows[n] for n in expected if n in rows and rows[n]['status']!='Verified'}
    result={'expected_target_classes':len(expected),'parsed_class_headers':len(rows),
        'target_statuses':{n:rows[n] for n in expected if n in rows},'missing':missing,'unverified':unverified,
        'other_nonverified_statuses':{n:row for n,row in rows.items() if n not in expected and row['status']!='Verified'}}
    return result

def verify(s,tx,art,discovery_lib,discovery,build,installed,result):
    with contextlib.ExitStack() as stack:
        identity=s.activation['framework_epoch']['binding']['processes']['system_server']
        need(identity==discovery['system_server_identity'],'SYSTEMSERVER_GENERATION_CHANGED')
        peer=s.held.HeldZygoteRoot(identity,art.DEADLINE);stack.callback(peer.close)
        before=art.snapshot(s,peer,discovery_lib,discovery)
        current_apk=art.pin_guest(s,peer,installed['after']['apk_path'])
        need(current_apk['sha256']==INSTALLED_SHA,'INSTALLED_CALENDAR10_CHANGED')
        tx.write_new(OUT/'before.json',before,alex_readable=False)
        cache_before=art.cache_inventory(s);tx.write_new(OUT/'cache-before.json',cache_before,alex_readable=False)
        bcp=[]
        for path in before['values']['BOOTCLASSPATH'].split(':'):
            fd=s.target.open_root(path,os.O_RDONLY);stack.callback(os.close,fd)
            old=next(x for x in before['classpath_files'] if x['path']==path);observed=art.pin_fd(fd)
            need(all(observed[k]==old[k] for k in ('device','inode','bytes','sha256')),'HELD_BCP_CHANGED')
            bcp.append(fd)
        need(len(bcp)==52,'EXPECTED_ACTUAL_52_BOOT_FILES')
        own=prepare(tx,art,stack)
        extras=tuple([*bcp,own['source'],own['oat'],own['vdex'],own['directory'],own['marker']])
        read_only=set(extras)-{own['oat'],own['vdex']}
        result['fd_proof']=art.prove_fds(s,'calendar11',extras,read_only,{own['oat'],own['vdex']},own['marker'],own['directory'])
        source_before=art.pin_fd(own['source'])
        timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%m-%d %H:%M:%S.000')
        args=[art.DEX2OAT,f"--zip-fd={own['source']}",'--zip-location='+installed['after']['apk_path'],
            f"--oat-fd={own['oat']}",f"--output-vdex-fd={own['vdex']}",
            f"--oat-location=/proc/self/fd/{own['directory']}/candidate.odex",
            '--instruction-set=x86_64','--boot-image=/system/framework/boot.art',
            '--runtime-arg','-Xbootclasspath:'+before['values']['BOOTCLASSPATH'],
            '--runtime-arg','-Xbootclasspathfds:'+':'.join(map(str,bcp)),
            '--class-loader-context=PCL[]','--compiler-filter=verify',
            '--abort-on-hard-verifier-error','--abort-on-soft-verifier-error',
            '--copy-dex-files=always','--runtime-arg','-Xms32m','--runtime-arg','-Xmx768m','-j2']
        result['compiler_argv']=args
        expected=sorted(set(build['new_class_definitions'])|{'L'+p[:-6]+';' for p in build['patch']['changed_classes']})
        need(len(build['new_class_definitions'])==60 and len(build['patch']['changed_classes'])==6 and len(expected)==66,'EXPECTED_TARGET_CLASS_SET_CHANGED')
        result['expected_targets']=expected
        try:
            result['compiler_attempted']=True
            reply=art.command(s,'calendar11-compiler',args,extras,85)
            result['compiler']=art.record_command(tx,'calendar11-compiler',reply)
            need(reply['rc']==0,'ACTUAL_COMPILER_VERIFICATION_FAILED')
            need(os.pread(own['oat'],4,0)==b'\x7fELF' and os.pread(own['vdex'],4,0)==b'vdex','ART_OUTPUT_HEADERS')
            dump=[art.OATDUMP,f"--oat-file=/proc/self/fd/{own['directory']}/candidate.odex",
                f"--dex-file=/proc/self/fd/{own['directory']}/candidate.apk",
                '--class-filter=com.android.calendar','--no-disassemble','--no-dump:vmap']
            result['oatdump_argv']=dump
            reply=art.command(s,'calendar11-all-targets',dump,extras,20)
            result['oatdump']=art.record_command(tx,'calendar11-all-targets',reply)
            need(reply['rc']==0,'ACTUAL_OATDUMP_FAILED')
            proof=all_target_statuses(reply['stdout'].decode('utf-8','strict'),expected)
            result['target_status_proof']=proof
            tx.write_new(OUT/'target-statuses.json',proof,alex_readable=True)
            need(not proof['missing'] and not proof['unverified'],'ALL_66_NEW_AND_MODIFIED_CLASSES_MUST_BE_VERIFIED')
            result['all_66_target_classes_stored_status_verified']=True
        finally:
            errors=[]
            for name,action in [
                ('input',lambda:need(art.pin_fd(own['source'])==source_before,'OWNED_APK_CHANGED')),
                ('outputs',lambda:result.update(outputs={n:art.pin_fd(own[n]) for n in ('oat','vdex')})),
            ]:
                try:action()
                except BaseException as exc:errors.append(name+':'+type(exc).__name__+':'+str(exc))
            try:
                reply=art.command(s,'calendar11-art-log',['/system/bin/logcat','-d','-b','all','--uid=2000',
                    '-v','threadtime','-T',timestamp,'dex2oat:V','dex2oat64:V','oatdump:V','art:V','*:S'],(),10)
                result['android_compiler_log']=art.record_command(tx,'calendar11-art-log',reply)
                need(reply['rc']==0,'COMPILER_LOG_UNAVAILABLE')
            except BaseException as exc:errors.append('log:'+type(exc).__name__+':'+str(exc))
            try:
                after=art.snapshot(s,peer,discovery_lib,discovery);tx.write_new(OUT/'after.json',after,alex_readable=False)
                result['input_boot_apex_classpaths_unchanged']=after==before
                need(after==before,'ART_DEPENDENCY_CLOSURE_CHANGED')
                need(art.pin_guest(s,peer,installed['after']['apk_path'])==current_apk,'INSTALLED_CALENDAR_CHANGED')
                result['installed_calendar10_unchanged']=True
                cache_after=art.cache_inventory(s);tx.write_new(OUT/'cache-after.json',cache_after,alex_readable=False)
                complete=cache_before['complete'] and cache_after['complete']
                result['cache_observation']={'complete':complete,'persistent_delta_observed':cache_before!=cache_after if complete else None,
                    'interpretation':'Only metadata of two fixed cache roots. Does not capture transient writes; concurrent App changes are not attributed to this compiler.'}
                result['guard_after']=s.guard()
            except BaseException as exc:errors.append('postcheck:'+type(exc).__name__+':'+str(exc))
            if errors:result['final_errors']=errors;raise RuntimeError('ART_FINAL_COLLECTION_INCOMPLETE:'+repr(errors))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'state':'INERT','apk_sha256':APK_SHA,'installed':False,'UI_actions':0}));return 0
    need(os.geteuid()==0 and not os.path.lexists(OUT),'NEW_OWNED_OUTPUT_REQUIRED')
    tx=load(TX,TX_SHA,'calendar_art_tx');need(tx.ACTIVATION_SHA==ACTIVATION_SHA,'APPROVED_ACTIVATION_REQUIRED')
    art=tx.load_module(STORAGE/'verify_candidate22.py',ART_LIB_SHA,'calendar_art_descriptor_library')
    discovery_lib=tx.load_module(STORAGE/'collect_art16.py',DISCOVERY_LIB_SHA,'calendar_art_discovery_library')
    art.OUT=OUT;art.DEADLINE=time.monotonic()+225
    art.INPUTS={'candidate':(BUILD/'Calendar-pocket4-functional.apk',APK_SHA)}
    discovery=json.loads(tx.read_regular(STORAGE/'art-discovery16/result.json',DISCOVERY_SHA,maximum=1048576))
    build=json.loads(tx.read_regular(BUILD/'result.json',BUILD_SHA,maximum=131072))
    need(build['state']=='BUILT_SIGNED_NOT_INSTALLED' and build['signed_apk']['sha256']==APK_SHA and
        build['against_previous10']['apk_sha256']==INSTALLED_SHA and
        build['against_previous10']['classes_compared']==445 and
        build['against_previous10']['methods_compared']==2327 and
        build['against_previous10']['changed_methods']==[] and
        build['against_previous10']['classes_dex_byte_equal'] and
        build['against_previous10']['classes2_preserved_except_reviewed_receipt_path'] and
        build['against_previous10']['all_other_methods_IR_equal'] and
        build['against_previous10']['all_other_non_signature_payloads_byte_equal'] and
        build['restored_code_proof']['classes_compared']==60 and
        build['restored_code_proof']['unchanged_classes']==58 and
        build['restored_code_proof']['original_generic_receipt_validator_IR_unchanged'] and
        build['restored_code_proof']['changed_classes']==[
            'com/android/calendar/event/EventEditorStore.smali',
            'com/android/calendar/event/ProviderReceipt.smali'] and
        build['restored_code_proof']['actual_method_changes']=={
            'com/android/calendar/event/EventEditorStore.smali':{
                'changed_methods':['createLocalCalendar(Ljava/lang/String;)J'],'added_methods':[]},
            'com/android/calendar/event/ProviderReceipt.smali':{
                'changed_methods':[],'added_methods':['calendarId(Ljava/lang/String;Ljava/lang/String;)J']}},
        'ACTUAL_BUILD11_REQUIRED')
    installed=json.loads(tx.read_regular(INSTALL,INSTALL_SHA,maximum=65536))
    need(installed['state']=='INSTALLED_VERIFIED_NOT_BUSINESS_QUALIFIED' and installed['after']['apk_sha256']==INSTALLED_SHA,'EXACT_INSTALL10_REQUIRED')
    with zipfile.ZipFile(BUILD/'Calendar-pocket4-functional.apk') as apk:
        need(sha(apk.read('AndroidManifest.xml'))==MANIFEST_SHA,'APP_MANIFEST_CHANGED')
    os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
    result={'schema':'calendar11-installed-art-isolated-verification-v1','state':'FAILED','started_utc':stamp(),
        'apk_sha256':APK_SHA,'build_result_sha256':BUILD_SHA,'transport_sha256':TX_SHA,
        'activation_sha256':ACTIVATION_SHA,'reused_art_transport_sha256':ART_LIB_SHA,
        'runner_sha256':sha(Path(__file__).read_bytes()),'installed':False,'UI_actions':0,'provider_mutations':0,
        'installed_runtime_mutations_requested':False,'all_runtime_writes_observed':False,
        'runtime_business_success':False,'whole_app_production_ready':False,'automatic_retry':False,
        'class_loader_context':'PCL[]','context_basis':'Pinned unchanged APK manifest has no uses-library/uses-static-library entries; all original and restored application DEX are in this same ZIP. This is an isolated artifact gate, not a running process class-loader capture.',
        'compiler_attempted':False,'all_66_target_classes_stored_status_verified':False}
    rc=2
    try:
        result['resource_admission']=limits_and_usage()
        with tx.CameraSession(OUT/'journal') as s:
            result['guard_before']=s.guard();verify(s,tx,art,discovery_lib,discovery,build,installed,result)
        result['state']='ALL_66_NEW_AND_MODIFIED_CALENDAR_CLASSES_ART_VERIFIED_NOT_INSTALLED';rc=0
    except BaseException as exc:result['error']=type(exc).__name__+':'+str(exc)
    try:result['resource_usage']=limits_and_usage(False)
    except BaseException as exc:result['state']='FAILED';result['resource_error']=type(exc).__name__+':'+str(exc);rc=2
    result['finished_utc']=stamp();tx.write_new(OUT/'result.json',result,alex_readable=True)
    raw=(OUT/'result.json').read_bytes();compressed=gzip.compress(raw,mtime=0);tx.write_new(OUT/'result.json.gz',compressed,alex_readable=True)
    print(json.dumps({'state':result['state'],'error':result.get('error'),'result_path':str(OUT/'result.json'),
        'result_bytes':len(raw),'result_sha256':sha(raw),'gzip_bytes':len(compressed),'gzip_sha256':sha(compressed),'installed':False}))
    return rc
if __name__=='__main__':raise SystemExit(main())
