#!/usr/bin/python3 -I
"""Verify Clock alarm candidate04 with installed ART and observed shared-library FDs.

Default inert; no installation, application code, tasks or provider writes.
The declared CLC does not claim a running Java class-loader heap capture.
"""
from pathlib import Path
import argparse,contextlib,datetime,gzip,hashlib,json,os,re,resource,stat,struct,time,zipfile

STORAGE=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12')
OUT=Path('/home/alex/work/pocket4-clock-alarm-art-20261105-r12-04')
BUILD=Path('/home/alex/work/pocket4-clock-alarm-dispatch-20261105-r12-04/build')
BUILD_SHA='4b4e23003f52b80f896cff316b930095ef4dd959e0fdbcb99b2ea0fc674b6881'
APK_SHA='433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d'
DEX_SHA='deff3873f215d97ab47908c7f60cb6ab62d4a6e4f6274dc3f3130023f0630c98'
INSTALLED_SHA='e4ff4b46a651ff3ac77397705b7b749c7fbaaeb94fe1d00818debb31dea34172'
TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ACTIVATION_SHA='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
ART_LIB_SHA='e5de57780be072ced10a5beba049fe89e89e381d6a66a974a8f298ef34cf2742'
DISCOVERY_LIB_SHA='605a30fe58ad9fb49bb62d85750a2d558686ea5730d000b3d703e88dde9e8aa5'
DISCOVERY_SHA='614f0c61ec4956a626edb06950bb6b7494ed856dc1dc2c45ac8bfd748421bab9'
CONTEXT_SOURCE=Path('/home/alex/work/pocket4-clock-art-context-tools-20261105-r12-05/read_context05.py')
CONTEXT_SOURCE_SHA='ad93287b86624ea8444ebf37300c8b51ed899ac5511d904b81bc2283adcaf398'
CONTEXT_RESULT=Path('/home/alex/work/pocket4-clock-art-context-20261105-r12-05/result.json')
CONTEXT_RESULT_SHA='512380a0cca62cba61eb727edff500e23cf8cb365d6f189a01d1bb0aac5813af'
UNIT='p4-clock-alarm-art-20261105-r12-04.service'
TARGETS=['Lcom/android/deskclock/alarms/'+n+';' for n in (
 'AlarmService','AlarmStateManager','AlarmStateManager$Companion',
 'AlarmStateManager$AlarmManagerStateChangeScheduler')]

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

def context_bytes(raw):
    need(len(raw)==33536 and hashlib.sha256(raw).hexdigest()==
        'f9bd1ff8feda33004e2052369f64fac534efb461b389831b68ced3b5e262fea6',
        'FIXED_INSTALLED_OAT_BYTES_REQUIRED')
    need(raw[:6]==b'\x7fELF\x02\x01','ELF64_LITTLE_ENDIAN_REQUIRED')
    shoff=struct.unpack_from('<Q',raw,40)[0]
    shentsize,shnum,shstr=struct.unpack_from('<HHH',raw,58)
    need(shentsize==64 and 0<shnum<=32 and shstr<shnum
        and shoff+shentsize*shnum<=len(raw),'ELF_SECTION_TABLE_BOUNDS')
    rows=[struct.unpack_from('<IIQQQQIIQQ',raw,shoff+i*shentsize) for i in range(shnum)]
    table=rows[shstr];need(table[4]+table[5]<=len(raw),'SECTION_NAMES_BOUNDS')
    names=raw[table[4]:table[4]+table[5]]
    selected=[]
    for row in rows:
        need(row[0]<len(names) and names.find(b'\0',row[0])>=0,'SECTION_NAME_BOUNDS')
        name=names[row[0]:names.find(b'\0',row[0])]
        if name==b'.rodata':selected.append(row)
    need(len(selected)==1,'UNIQUE_RODATA_REQUIRED')
    start,size=selected[0][4:6]
    need(start+size<=len(raw) and size>=72 and raw[start:start+8]==b'oat\n275\0',
        'OBSERVED_OAT275_RODATA_REQUIRED')
    count=struct.unpack_from('<I',raw,start+68)[0]
    begin,end=start+72,start+72+count
    need(0<count<=16384 and end<=start+size,'OBSERVED_OAT_KEY_VALUE_BOUNDS')
    data=raw[begin:end];need(data.endswith(b'\0'),'NUL_TERMINATED_KEY_TABLE_REQUIRED')
    parts=data[:-1].split(b'\0');need(len(parts)%2==0,'KEY_VALUE_PAIRS_REQUIRED')
    pairs={};empty_pairs=0
    for key,value in zip(parts[::2],parts[1::2]):
        if key==value==b'':empty_pairs+=1;continue
        need(re.fullmatch(rb'[a-z0-9-]+',key) is not None and key not in pairs,
            'DUPLICATE_OR_INVALID_NONEMPTY_KEY')
        pairs[key]=value
    need(len(pairs)==13 and empty_pairs==944,'OBSERVED_KEY_TABLE_SHAPE_CHANGED')
    stored=pairs[b'classpath'].decode('ascii','strict')
    normalized=re.sub(r'\*\d+(?=\])','',stored)
    expected='PCL[]{PCL[/system_ext/framework/androidx.window.extensions.jar]#PCL[/system_ext/framework/androidx.window.sidecar.jar]}'
    need(normalized==expected,'INSTALLED_OAT_CLASSLOADER_HIERARCHY_CHANGED')
    command=pairs[b'dex2oat-cmdline'].decode('ascii','strict').split()
    need(command.count('--class-loader-context='+expected)==1,'STORED_COMMAND_CONTEXT_DIFFERS')
    return {'input_bytes':len(raw),'input_sha256':hashlib.sha256(raw).hexdigest(),
        'section_file_offset':start,'section_bytes':size,'observed_oat_magic_version':'oat\\n275\\0',
        'observed_header_bytes':72,'observed_key_value_size_word_offset':68,
        'key_value_file_offset':begin,'key_value_bytes':count,
        'key_value_table_sha256':hashlib.sha256(data).hexdigest(),
        'nonempty_unique_keys':[k.decode() for k in pairs],'empty_key_and_empty_value_pairs':empty_pairs,
        'stored_classpath':stored,'stored_clc_without_checksums':normalized,
        'stored_cmdline_same_classloader_context':True,'shared_libraries_after_app_in_stored_context':False,
        'running_classloader_heap_capture':False,'candidate_ART_verified':False,
        'scope':'Exact retained OAT275 bytes only. Empty/empty pairs are explicitly counted; no inference about why they exist, OAT runtime acceptance, or previous oatdump rc1.'}

def context_gate(context,lib):
    need(context['state']=='DECLARED_CONTEXT_METADATA_COLLECTED_NOT_ART_VERIFIED'
        and context['closure_unchanged'] and context['apk_before']['sha256']==INSTALLED_SHA
        and context['package_before']==context['package_after']
        and context['transport_sha256']==TX_SHA and context['activation_sha256']==ACTIVATION_SHA,
        'ACTUAL_CONTEXT_CLOSURE_REQUIRED')
    need(context['package_before']['usesOptionalLibraries']==lib.LIBRARIES
        and context['package_before']['usesLibraryFiles']==lib.LIBRARY_FILES
        and not any(context['declared_dependencies'].values()),'DECLARED_LIBRARY_SET_OR_DEPENDENCIES')
    value='PCL[]{'+'#'.join('PCL['+p+']' for p in lib.LIBRARY_FILES)+'}'
    need(context['declared_candidate_context']==value,'CONTEXT_STRING_CHANGED')
    observed=context['flatten_observation']
    receipt=context['artifact_commands']
    need(len(receipt)==1 and receipt[0]['joined'] and not receipt[0]['timed_out']
        and receipt[0]['rc']==observed.get('rc')==50
        and receipt[0]['stdout']['sha256']=='8be66f6d14b29e6bf9449bcb722617ca60ca664c62a2b8a362e9639f546a9f79'
        and receipt[0]['stderr']['bytes']==0,'ACTUAL_FLATTEN_RECEIPT_CHANGED')
    need(observed['stdout']=='/system_ext/framework/androidx.window.sidecar.jar:/system_ext/framework/androidx.window.extensions.jar',
        'ACTUAL_FLATTENED_PATH_ORDER_CHANGED')
    paths=observed['stdout'].strip().split(':')
    need(len(paths)==2 and set(paths)==set(lib.LIBRARY_FILES),'FLATTENED_CONTEXT_PATHS_DIFFER')
    return value,paths

def prepare(tx,art,stack):
    directory=OUT/'candidate';directory.mkdir(mode=0o750);os.chown(directory,0,1000)
    raw=tx.read_regular(BUILD/'DeskClock-pocket4-alarm-dispatch.apk',APK_SHA,maximum=12*1024*1024)
    art.own_file(directory/'candidate.apk',raw,stack,mode=0o444,uid=0)
    source=os.open(directory/'candidate.apk',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);stack.callback(os.close,source)
    art.own_file(directory/'marker',('clock-alarm-art04:'+APK_SHA+'\n').encode(),stack,mode=0o444,uid=0)
    markfd=os.open(directory/'marker',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);stack.callback(os.close,markfd)
    oat=art.own_file(directory/'candidate.odex',b'',stack)
    vdex=art.own_file(directory/'candidate.vdex',b'',stack)
    os.chmod(directory,0o555)
    dirfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);stack.callback(os.close,dirfd)
    need(art.pin_fd(source)['sha256']==APK_SHA,'OWNED_APK_COPY_CHANGED')
    return {'source':source,'oat':oat,'vdex':vdex,'directory':dirfd,'marker':markfd}

def shared_snapshot(s,tx,art,peer,lib,context,label):
    package=lib.package(s,tx,label)
    need(package==context['package_before'],'CURRENT_CLOCK_PACKAGE_CONTEXT_CHANGED')
    apk=art.pin_guest(s,peer,lib.APK)
    need(apk==context['apk_before'],'CURRENT_CLOCK_APK_CHANGED')
    config=lib.xml_config(s,art,peer)
    need(config==context['library_config_before'],'LIBRARY_CONFIGURATION_CHANGED')
    jars={p:art.pin_guest(s,peer,p) for p in lib.LIBRARY_FILES}
    need(jars==context['library_files_before'],'LIBRARY_JAR_IDENTITY_CHANGED')
    oat=context['existing_oat']
    need(oat['present'] and art.pin_guest(s,peer,oat['path'])==oat['pin'],'INSTALLED_OAT_CHANGED')
    raw,_=s.target.read_file(oat['path'],65536)
    parsed=context_bytes(raw)
    need(parsed['stored_clc_without_checksums']==context['declared_candidate_context'],'CURRENT_OAT_CONTEXT_DIFFERS')
    return {'package':package,'apk':apk,'xml_config':config,'jar_files':jars,'stored_OAT_context':parsed}

def verify(s,tx,art,discovery_lib,discovery,context_lib,context,result):
    with contextlib.ExitStack() as stack:
        identity=s.activation['framework_epoch']['binding']['processes']['system_server']
        need(identity==discovery['system_server_identity'],'SYSTEMSERVER_GENERATION_CHANGED')
        peer=s.held.HeldZygoteRoot(identity,art.DEADLINE);stack.callback(peer.close)
        before=art.snapshot(s,peer,discovery_lib,discovery)
        shared=shared_snapshot(s,tx,art,peer,context_lib,context,'current-before')
        tx.write_new(OUT/'before.json',before,alex_readable=False)
        tx.write_new(OUT/'shared-before.json',shared,alex_readable=True)
        cache_before=art.cache_inventory(s);tx.write_new(OUT/'cache-before.json',cache_before,alex_readable=False)
        bcp=[]
        for path in before['values']['BOOTCLASSPATH'].split(':'):
            fd=s.target.open_root(path,os.O_RDONLY);stack.callback(os.close,fd)
            old=next(x for x in before['classpath_files'] if x['path']==path);observed=art.pin_fd(fd)
            need(all(observed[k]==old[k] for k in ('device','inode','bytes','sha256')),'HELD_BCP_CHANGED')
            bcp.append(fd)
        need(len(bcp)==52,'EXPECTED_ACTUAL_52_BOOT_FILES')
        clc,ordered_paths=context_gate(context,context_lib)
        context_fds=[]
        for path in ordered_paths:
            fd=s.target.open_root(path,os.O_RDONLY);stack.callback(os.close,fd)
            need(art.pin_fd(fd)==shared['jar_files'][path],'HELD_SHARED_LIBRARY_CHANGED')
            context_fds.append(fd)
        result['shared_library_FD_order']=[{'path':p,'fd':fd,'pin':shared['jar_files'][p]}
            for p,fd in zip(ordered_paths,context_fds)]
        own=prepare(tx,art,stack)
        extras=tuple([*bcp,*context_fds,own['source'],own['oat'],own['vdex'],own['directory'],own['marker']])
        read_only=set(extras)-{own['oat'],own['vdex']}
        result['fd_proof']=art.prove_fds(s,'clock04',extras,read_only,{own['oat'],own['vdex']},own['marker'],own['directory'])
        source_before=art.pin_fd(own['source'])
        timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%m-%d %H:%M:%S.000')
        args=[art.DEX2OAT,f"--zip-fd={own['source']}",'--zip-location='+context_lib.APK,
            f"--oat-fd={own['oat']}",f"--output-vdex-fd={own['vdex']}",
            f"--oat-location=/proc/self/fd/{own['directory']}/candidate.odex",
            '--instruction-set=x86_64','--boot-image=/system/framework/boot.art',
            '--runtime-arg','-Xbootclasspath:'+before['values']['BOOTCLASSPATH'],
            '--runtime-arg','-Xbootclasspathfds:'+':'.join(map(str,bcp)),
            '--class-loader-context='+clc,'--class-loader-context-fds='+':'.join(map(str,context_fds)),
            '--compiler-filter=verify','--abort-on-hard-verifier-error','--abort-on-soft-verifier-error',
            '--copy-dex-files=always','--runtime-arg','-Xtarget-sdk-version:30',
            '--runtime-arg','-Xhidden-api-policy:enabled',
            '--runtime-arg','-Xms32m','--runtime-arg','-Xmx768m','-j2']
        result['compiler_argv']=args;result['expected_targets']=sorted(TARGETS)
        try:
            result['compiler_attempted']=True
            reply=art.command(s,'clock04-compiler',args,extras,85)
            result['compiler']=art.record_command(tx,'clock04-compiler',reply)
            need(reply['rc']==0,'ACTUAL_COMPILER_VERIFICATION_FAILED')
            need(os.pread(own['oat'],4,0)==b'\x7fELF' and os.pread(own['vdex'],4,0)==b'vdex','ART_OUTPUT_HEADERS')
            dump=[art.OATDUMP,f"--oat-file=/proc/self/fd/{own['directory']}/candidate.odex",
                f"--dex-file=/proc/self/fd/{own['directory']}/candidate.apk",
                '--class-filter=com.android.deskclock.alarms','--no-disassemble','--no-dump:vmap']
            result['oatdump_argv']=dump
            reply=art.command(s,'clock04-all-targets',dump,extras,20)
            result['oatdump']=art.record_command(tx,'clock04-all-targets',reply)
            need(reply['rc']==0,'ACTUAL_OATDUMP_FAILED')
            proof=all_target_statuses(reply['stdout'].decode('utf-8','strict'),sorted(TARGETS))
            result['target_status_proof']=proof
            tx.write_new(OUT/'target-statuses.json',proof,alex_readable=True)
            need(not proof['missing'] and not proof['unverified'],'ALL_FOUR_MODIFIED_CLASSES_MUST_BE_VERIFIED')
            result['all_four_target_classes_stored_status_verified']=True
        finally:
            errors=[]
            for name,action in [
                ('input',lambda:need(art.pin_fd(own['source'])==source_before,'OWNED_APK_CHANGED')),
                ('outputs',lambda:result.update(outputs={n:art.pin_fd(own[n]) for n in ('oat','vdex')})),
                ('held-shared-libraries',lambda:need(
                    [art.pin_fd(fd) for fd in context_fds]==[shared['jar_files'][p] for p in ordered_paths],
                    'HELD_SHARED_LIBRARY_CHANGED')),
            ]:
                try:action()
                except BaseException as exc:errors.append(name+':'+type(exc).__name__+':'+str(exc))
            try:
                reply=art.command(s,'clock04-art-log',['/system/bin/logcat','-d','-b','all','--uid=2000',
                    '-v','threadtime','-T',timestamp,'dex2oat:V','dex2oat64:V','oatdump:V','art:V','*:S'],(),10)
                result['android_compiler_log']=art.record_command(tx,'clock04-art-log',reply)
                need(reply['rc']==0,'COMPILER_LOG_UNAVAILABLE')
            except BaseException as exc:errors.append('log:'+type(exc).__name__+':'+str(exc))
            try:
                after=art.snapshot(s,peer,discovery_lib,discovery);tx.write_new(OUT/'after.json',after,alex_readable=False)
                result['input_boot_apex_classpaths_unchanged']=after==before
                need(after==before,'ART_DEPENDENCY_CLOSURE_CHANGED')
                shared_after=shared_snapshot(s,tx,art,peer,context_lib,context,'current-after')
                tx.write_new(OUT/'shared-after.json',shared_after,alex_readable=True)
                need(shared_after==shared,'CURRENT_APP_AND_SHARED_LIBRARY_CLOSURE_CHANGED')
                result['installed_clock_and_shared_libraries_unchanged']=True
                cache_after=art.cache_inventory(s);tx.write_new(OUT/'cache-after.json',cache_after,alex_readable=False)
                complete=cache_before['complete'] and cache_after['complete']
                result['cache_observation']={'complete':complete,
                    'persistent_delta_observed':cache_before!=cache_after if complete else None,
                    'interpretation':'Only metadata of two fixed cache roots. No transient-write proof or attribution of concurrent App changes.'}
                result['guard_after']=s.guard()
            except BaseException as exc:errors.append('postcheck:'+type(exc).__name__+':'+str(exc))
            if errors:result['final_errors']=errors;raise RuntimeError('ART_FINAL_COLLECTION_INCOMPLETE:'+repr(errors))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'state':'INERT','apk_sha256':APK_SHA,'installed':False,'UI_actions':0}));return 0
    need(re.fullmatch('[0-9a-f]{64}',CONTEXT_RESULT_SHA) is not None,'CONTEXT_NOT_REVIEWED')
    need(os.geteuid()==0 and not os.path.lexists(OUT),'NEW_OWNED_OUTPUT_REQUIRED')
    tx=load(TX,TX_SHA,'clock_art_tx');need(tx.ACTIVATION_SHA==ACTIVATION_SHA,'APPROVED_ACTIVATION_REQUIRED')
    art=tx.load_module(STORAGE/'verify_candidate22.py',ART_LIB_SHA,'clock_art_descriptor_library')
    discovery_lib=tx.load_module(STORAGE/'collect_art16.py',DISCOVERY_LIB_SHA,'clock_art_discovery_library')
    context_lib=load(CONTEXT_SOURCE,CONTEXT_SOURCE_SHA,'clock_declared_context_library');context_lib.ROOT=OUT
    art.OUT=OUT;art.DEADLINE=time.monotonic()+225
    art.INPUTS={'candidate':(BUILD/'DeskClock-pocket4-alarm-dispatch.apk',APK_SHA)}
    discovery=json.loads(tx.read_regular(STORAGE/'art-discovery16/result.json',DISCOVERY_SHA,maximum=1048576))
    build=json.loads(tx.read_regular(BUILD/'result.json',BUILD_SHA,maximum=65536))
    need(build['state']=='SIGNED_OFFLINE_CANDIDATE_VERIFIED' and not build['installed']
        and build['candidate_apk']['sha256']==APK_SHA and build['candidate_dex']['sha256']==DEX_SHA
        and build['semantic_verification']['all_2941_class_IR_compared']
        and build['semantic_verification']['non_target_semantic_changes']==0
        and len(build['semantic_verification']['differences'])==5
        and len(build['semantic_verification']['added_methods'])==6
        and build['payload_verification']['only_changed_payload']=='classes.dex'
        and build['payload_verification']['same_certificate_verified'],'ACTUAL_CLOCK_BUILD04_REQUIRED')
    targets={'Lcom/android/deskclock/alarms/'+p[:-6]+';' for p in build['reviewed_targets']}
    need(targets==set(TARGETS) and len(targets)==4,'EXPECTED_REVIEWED_TARGET_SET')
    context=json.loads(tx.read_regular(CONTEXT_RESULT,CONTEXT_RESULT_SHA,maximum=256*1024))
    clc,paths=context_gate(context,context_lib)
    with zipfile.ZipFile(BUILD/'DeskClock-pocket4-alarm-dispatch.apk') as apk:
        need(sha(apk.read('AndroidManifest.xml'))==context['manifest_sha256'],'APP_MANIFEST_CHANGED')
        need(sha(apk.read('classes.dex'))==DEX_SHA,'CANDIDATE_DEX_CHANGED')
    os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
    result={'schema':'clock-alarm04-installed-art-isolated-verification-v1','state':'FAILED','started_utc':stamp(),
        'apk_sha256':APK_SHA,'build_result_sha256':BUILD_SHA,'transport_sha256':TX_SHA,
        'activation_sha256':ACTIVATION_SHA,'reused_art_transport_sha256':ART_LIB_SHA,
        'runner_sha256':sha(Path(__file__).read_bytes()),'installed':False,'UI_actions':0,'provider_mutations':0,
        'installed_runtime_mutations_requested':False,'all_runtime_writes_observed':False,
        'runtime_business_success':False,'whole_app_production_ready':False,'automatic_retry':False,
        'class_loader_context':clc,'shared_library_paths_in_actual_flattened_order':paths,
        'context_result_sha256':CONTEXT_RESULT_SHA,
        'context_basis':'Exact PM declaration/XML and held whole JAR hashes, current installed OAT275 stored CLC/command-line, actual installed analyzer flattened path order. Isolated artifact verification; not a running Java ClassLoader heap capture.',
        'running_class_loader_heap_capture':False,'compiler_attempted':False,
        'all_four_target_classes_stored_status_verified':False}
    rc=2
    try:
        result['resource_admission']=limits_and_usage()
        with tx.CameraSession(OUT/'journal') as s:
            result['guard_before']=s.guard();verify(s,tx,art,discovery_lib,discovery,context_lib,context,result)
        result['state']='ALL_FOUR_MODIFIED_CLOCK_CLASSES_ART_VERIFIED_NOT_INSTALLED';rc=0
    except BaseException as exc:
        result['state']='FAILED';result['error']=type(exc).__name__+':'+str(exc);rc=2
    try:
        result['resource_usage']=limits_and_usage()
        events=result['resource_usage']['memory_events']
        need(events.get('max',0)==events.get('oom',0)==events.get('oom_kill',0)==0,'ART_MEMORY_LIMIT_HIT')
    except BaseException as exc:
        result['state']='FAILED';result['resource_error']=type(exc).__name__+':'+str(exc);rc=2
    result['finished_utc']=stamp();tx.write_new(OUT/'result.json',result,alex_readable=True)
    raw=(OUT/'result.json').read_bytes();compressed=gzip.compress(raw,mtime=0)
    tx.write_new(OUT/'result.json.gz',compressed,alex_readable=True)
    print(json.dumps({'state':result['state'],'error':result.get('error'),'result_path':str(OUT/'result.json'),
        'result_bytes':len(raw),'result_sha256':sha(raw),'gzip_bytes':len(compressed),
        'gzip_sha256':sha(compressed),'installed':False}))
    return rc
if __name__=='__main__':raise SystemExit(main())

