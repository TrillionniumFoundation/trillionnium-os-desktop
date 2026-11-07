#!/usr/bin/python3 -I
"""One data-preserving Calendar update. Default inert; no UI or provider mutation."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, io, json, os, re, signal, stat, types, zipfile

PROFILE_TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
PROFILE_TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PROFILE_ACTIVATION_SHA='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'

ROOT=Path('/home/alex/work/pocket4-calendar-repair-install-20261105-r12-11')
BUILD=Path('/home/alex/work/pocket4-calendar-repair-build-20261105-r12-11')
BUILD_SHA='ec9ce6f9c8e31d021992d59d86ce4319743496debff50e24ef7da8be544c96e9'
OLD_SHA='7872aa56b6aa35f4509a27a2c3c0ebb8743da7096136155e425f5b1e4499ae8e'
NEW_SHA='00cb0b0a3e33a0bf79814a83c3c5900a3c10d9c41719d38e1e146a0ae134a85f'
OLD_BYTES,NEW_BYTES=2631117,2635213
PACKAGE='com.android.calendar'
PROVIDER='com.android.providers.calendar'
PROVIDER_SHA='eebf12f81981f7d8c59a9b9ed465945818d2ab0208c121d858cbc4e6426f5fff'
CERT='a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
FLOW=Path('/home/alex/work/pocket4-calendar-flow-tools-20261105-r12-01/run_calendar01.py')
FLOW_SHA='d307f4ceda9fc80e216f280cb1a9558fbe4e27b43cd659ecc83a1c6edab9c8fa'
PRIOR=Path('/home/alex/work/pocket4-calendar-repair-install-20261105-r12-10/result.json')
PRIOR_SHA='253c98a9d27f1b5bb45e01cdda6042e0d43b2f268b3c0a228bf93a639b38f957'
ART=Path('/home/alex/work/pocket4-calendar-art-verification-20261105-r12-11/result.json')
ART_SHA='85c0a4746e04f07e22e7a7550b5d1048ef3f418635365497dba045baeb796065'
CLEANUP=Path('/home/alex/work/pocket4-calendar-core11-empty-cleanup-20261105-r12-01/result.json')
CLEANUP_SHA='8baa04ffaec51cfa11cb4e7ad2de8976e0fe5a38adfa6a7ed88d465b2783ce87'
JAVA_CLOSURE=('java','java_security','jdk_modules','jdk_release','jvm_cfg','libjava',
              'libjimage','libjli','libjvm','apksigner_jar','signer_companion_apksig-0.9.jar')

def require(value,reason):
    if not value: raise RuntimeError(reason)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def stamp(): return datetime.now(timezone.utc).isoformat()

def load(path,pin):
    raw=path.read_bytes();require(sha(raw)==pin,'SOURCE_CHANGED:'+path.name)
    module=types.ModuleType('calendar_install_'+path.stem);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module

def signature_entry(name):
    return name.upper()=='META-INF/MANIFEST.MF' or re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC)',name,re.I) is not None

def verify_payload(original,candidate):
    with zipfile.ZipFile(io.BytesIO(original)) as old,zipfile.ZipFile(io.BytesIO(candidate)) as new:
        for archive in (old,new):
            require(len(archive.namelist())==len(set(archive.namelist())) and archive.testzip() is None,'APK_ZIP_INVALID')
        a={n for n in old.namelist() if not signature_entry(n)}
        b={n for n in new.namelist() if not signature_entry(n)}
        require(len(a)==664 and b==a and 'classes2.dex' in a,'PAYLOAD_SET_CHANGED')
        require([n for n in sorted(a) if old.read(n)!=new.read(n)]==['classes2.dex'],
                'ONLY_REVIEWED_RESTORED_DEX_MAY_CHANGE')

def pin_tools(deps):
    result={}
    for name in JAVA_CLOSURE:
        row=deps[name];path=Path(row['path']);before=path.stat()
        with path.open('rb') as stream: value=hashlib.file_digest(stream,'sha256').hexdigest()
        after=path.stat()
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
        require(all(getattr(before,k)==getattr(after,k) for k in fields) and
                value==row['sha256'] and after.st_size==row['bytes'],'SIGNER_CLOSURE_CHANGED:'+name)
        result[name]={'bytes':after.st_size,'sha256':value}
    return result

def verify_signature(s,tx,path,deps,label):
    args=[deps['java']['path'],'-Xmx128m','-XX:ActiveProcessorCount=1','-XX:-UsePerfData',
          '-Djava.io.tmpdir='+str(ROOT/'tmp'),'-Duser.home='+str(ROOT/'tmp'),
          '-jar',deps['apksigner_jar']['path'],'verify','--verbose','--print-certs',str(path)]
    value=s.run_host(label,args,25)
    require(value['rc']==0 and value['joined'] and not value['timed_out'],'SIGNATURE_COMMAND_FAILED')
    text=value['stdout'].decode('utf-8','strict')
    require(re.findall(r'^Signer #\d+ certificate SHA-256 digest: (\w+)$',text,re.M)==[CERT]
        and 'Verified using v3 scheme (APK Signature Scheme v3): true' in text,'SIGNATURE_IDENTITY')

def identity(s,m,doc):
    paths=s.android(['/system/bin/pm','path','--user','0',PACKAGE],12).decode().splitlines()
    require(len(paths)==1 and paths[0].startswith('package:/') and paths[0].endswith('.apk'),'ONE_CALENDAR_APK')
    apk,_=s.target.read_file(paths[0][8:],8*1024*1024,single_link=True)
    observed=sha(apk);require(observed in (OLD_SHA,NEW_SHA),'UNREVIEWED_CALENDAR_APK')
    value=doc.identity(s,PACKAGE,observed,10061,37)
    raw=s.android(['/system/bin/dumpsys','package',PACKAGE],15).decode()
    value['permissions']=m.permission_rows(raw,PACKAGE)
    active=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',raw,re.M|re.S)
    require(len(active)==1,'ACTIVE_PACKAGE_SECTION')
    require(re.findall(r'^    versionCode=(\d+) minSdk=(\d+) targetSdk=(\d+)$',active[0],re.M)
            ==[('37','37','34')],'CALENDAR_SDK_CHANGED')
    first=re.findall(r'^      firstInstallTime=(.*)$',active[0],re.M)
    require(len(first)==1,'FIRST_INSTALL_TIME_AMBIGUOUS')
    value['first_install_time']=first[0]
    require(all(m.permission_granted(value['permissions'],p) for p in
                ('android.permission.READ_CALENDAR','android.permission.WRITE_CALENDAR',
                 'android.permission.POST_NOTIFICATIONS')),'EXISTING_CALENDAR_GRANTS_CHANGED')
    return value

def data_projection(value):
    return {key:item for key,item in value.items() if key not in ('apk_path','apk_sha256','apk_bytes')}

def execute():
    require(os.geteuid()==0 and not os.path.lexists(ROOT),'NEW_ROOT_REQUIRED')
    require(re.fullmatch(r'[0-9a-f]{64}',ART_SHA) is not None,'ACTUAL_ART_PIN_NOT_FROZEN')
    require(re.fullmatch(r'[0-9a-f]{64}',CLEANUP_SHA) is not None,'ACTUAL_EMPTY_CLEANUP_PIN_NOT_FROZEN')
    m=load(FLOW,FLOW_SHA)
    # Bind the original strictly revalidated 12288 profile; original helper and guard sources remain intact.
    previous_tx=str(m.TX)
    require(m.PINS[previous_tx]=='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470','ORIGINAL_TRANSPORT_PREIMAGE_CHANGED')
    m.PINS={str(PROFILE_TX) if path==previous_tx else path: PROFILE_TX_SHA if path==previous_tx else pin
            for path,pin in m.PINS.items()}
    m.TX=PROFILE_TX
    tx,base,doc,diag=[m.load(Path(path),pin,'calendar_install_dependency_'+str(i))
                     for i,(path,pin) in enumerate(m.PINS.items())]
    require(m.PINS[str(m.TX)]==PROFILE_TX_SHA and tx.ACTIVATION_SHA==PROFILE_ACTIVATION_SHA,
            'REVIEWED_PROFILE_AND_UNCHANGED_GUARD_REQUIRED')
    base.PACKAGE=base.DOCS=m.CALENDAR;base.CLIENT=m.MAIN;base.FILES=m.INFO;diag.PACKAGE=PACKAGE
    m.ROOT=ROOT;m.TABLES=(*m.TABLES,'CalendarAlerts','EventsRawTimes','ExtendedProperties')
    result={'schema':'calendar-data-preserving-install-v1','state':'NOT_DISPATCHED',
        'source_sha256':sha(Path(__file__).read_bytes()),'started_utc':stamp(),
        'transport_sha256':PROFILE_TX_SHA,'activation_sha256':PROFILE_ACTIVATION_SHA,
        'package':PACKAGE,'old_sha256':OLD_SHA,'new_sha256':NEW_SHA,'build_result_sha256':BUILD_SHA,
        'install_calls':0,'install_pending':False,'automatic_retry':False,'rollback_calls':0,
        'ui_inputs':0,'provider_write_commands':0,'permission_changes':0,'data_clear_calls':0,
        'whole_app_production_ready':False,'reminder_delivery_verified':False}
    old_signal=signal.signal(signal.SIGALRM,m.expired)
    try:
        with tx.ui_lock():
            os.umask(0o077);ROOT.mkdir(mode=0o750);os.chown(ROOT,0,1000);os.chmod(ROOT,0o750)
            for name in ('ui','diagnostics','tmp'):(ROOT/name).mkdir(mode=0o700)
            tx.write_new(ROOT/'claim.json',result);signal.setitimer(signal.ITIMER_REAL,180)
            build=json.loads(tx.read_regular(BUILD/'result.json',BUILD_SHA,65536))
            require(build['state']=='BUILT_SIGNED_NOT_INSTALLED' and
                build['signed_apk']['sha256']==NEW_SHA and build['signed_apk']['bytes']==NEW_BYTES and
                build['certificate_sha256']==CERT and build['signature_v3_verified'] is True and
                build['alignment_16k_verified'] is True and build['input_postcheck_passed'] is True and
                build['semantic_proof']['only_expected_methods_changed'] is True and
                build['payload_proof']['all_non_dex_payloads_byte_equal'] is True,'BUILD_PROVENANCE')
            change=build['against_previous10'];restored=build['restored_code_proof']
            require(change['apk_sha256']==OLD_SHA and change['all_other_methods_IR_equal'] and
                change['changed_methods']==[] and change['classes_dex_byte_equal'] and
                change['classes2_preserved_except_reviewed_receipt_path'] and
                restored['classes_compared']==60 and restored['unchanged_classes']==58 and
                restored['original_generic_receipt_validator_IR_unchanged'] and
                restored['changed_classes']==[
                    'com/android/calendar/event/EventEditorStore.smali',
                    'com/android/calendar/event/ProviderReceipt.smali'] and
                restored['actual_method_changes']=={
                    'com/android/calendar/event/EventEditorStore.smali':{
                        'changed_methods':['createLocalCalendar(Ljava/lang/String;)J'],'added_methods':[]},
                    'com/android/calendar/event/ProviderReceipt.smali':{
                        'changed_methods':[],'added_methods':['calendarId(Ljava/lang/String;Ljava/lang/String;)J']}},
                'ACTUAL_NARROW_CALENDAR_RECEIPT_BUILD_PROOF_REQUIRED')
            prior=json.loads(tx.read_regular(PRIOR,PRIOR_SHA,32768))
            require(prior['state']=='INSTALLED_VERIFIED_NOT_BUSINESS_QUALIFIED' and
                prior['after']['apk_sha256']==OLD_SHA and not prior['install_pending'],'EXACT_PRIOR_INSTALL_REQUIRED')
            cleanup=json.loads(tx.read_regular(CLEANUP,CLEANUP_SHA,65536))
            require(cleanup['state']=='EXACT_CORE11_EMPTY_CALENDAR_REMOVED_BASELINE_RESTORED' and
                cleanup['delete_calls']==1 and not cleanup['delete_pending'] and
                cleanup['delete_outcome_verified_by_physical_empty_read'] and
                cleanup['counts_after']==dict.fromkeys(m.TABLES,0) and
                cleanup['calendar_after']==prior['after'] and
                cleanup['guard_before']==cleanup['guard_after']==prior['guard_after'],
                'ACTUAL_RETAINED_FIXTURE_CLEANUP_REQUIRED')
            result['prior_core11_cleanup_receipt_sha256']=CLEANUP_SHA
            art=json.loads(tx.read_regular(ART,ART_SHA,131072))
            require(art['state']=='ALL_66_NEW_AND_MODIFIED_CALENDAR_CLASSES_ART_VERIFIED_NOT_INSTALLED'
                and art['apk_sha256']==NEW_SHA and art['build_result_sha256']==BUILD_SHA
                and art['all_66_target_classes_stored_status_verified'] is True
                and art['input_boot_apex_classpaths_unchanged'] is True
                and art['installed_calendar10_unchanged'] is True
                and art['compiler']['rc']==0 and art['oatdump']['rc']==0,'ACTUAL_ART_VERIFICATION_REQUIRED')
            proof=art['target_status_proof']
            expected=set(build['new_class_definitions'])|{'L'+p[:-6]+';' for p in build['patch']['changed_classes']}
            require(proof['expected_target_classes']==len(expected) and set(proof['target_statuses'])==expected
                and not proof['missing'] and not proof['unverified']
                and all(x['status']=='Verified' for x in proof['target_statuses'].values()),'ALL_TARGET_ART_STATUSES_REQUIRED')
            require(art['resource_usage']['limits']==art['resource_admission']['limits']
                and art['resource_usage']['memory_events']['oom']==0
                and art['resource_usage']['memory_events']['oom_kill']==0,'ACTUAL_ART_FINAL_RESOURCES_REQUIRED')
            result['art_verification_receipt_sha256']=ART_SHA
            deps=build['dependencies_before'];result['signer_before']=pin_tools(deps)
            with tx.CameraSession(ROOT/'commands') as s:
                flow=m.Flow(s,tx,base,doc,diag)
                result['guard_before']=s.guard()
                require(result['guard_before']==prior['guard_after'],'MAIN_EPOCH_CHANGED')
                roots,tasks=flow.ui.stacks('install-initial-tasks')
                require(not any(child['component'].split('/')[0] in (PACKAGE,m.PACKAGE)
                    for root in roots.values() for child in root['children']),'TARGET_ACTIVITY_PRESENT')
                flow.ui.baseline=set(tasks);result['tasks_before']=sorted(tasks)
                before=identity(s,m,doc);result['before']=before
                require(before['apk_sha256']==OLD_SHA and before['apk_bytes']==OLD_BYTES,'ORIGINAL_APK_REQUIRED')
                require(before==prior['after'],'CALENDAR_PREIMAGE_CHANGED_SINCE_VERIFIED_INSTALL10')
                result['provider_before']=doc.identity(s,PROVIDER,PROVIDER_SHA,10017,37)
                result['counts_before']=flow.counts('install-before')
                empty=dict.fromkeys(m.TABLES,0);require(result['counts_before']==empty,'ZERO_CALENDAR_BASELINE_REQUIRED')
                original,_=s.target.read_file(before['apk_path'],8*1024*1024,single_link=True)
                require(sha(original)==OLD_SHA,'ORIGINAL_CHANGED_BEFORE_BACKUP')
                candidate=tx.read_regular(BUILD/'Calendar-pocket4-functional.apk',NEW_SHA,8*1024*1024)
                require(len(candidate)==NEW_BYTES,'CANDIDATE_LENGTH_CHANGED');verify_payload(original,candidate)
                backup=ROOT/'Calendar-original-before.apk';staged=ROOT/'Calendar-reviewed-candidate.apk'
                tx.write_new(backup,original,alex_readable=True);tx.write_new(staged,candidate,alex_readable=True)
                verify_signature(s,tx,backup,deps,'calendar-original-signature')
                verify_signature(s,tx,staged,deps,'calendar-candidate-signature')
                flow.ui.check_tasks('install-before-dispatch')
                require(identity(s,m,doc)==before and flow.counts('install-just-before')==empty,'STATE_CHANGED_BEFORE_DISPATCH')
                tx.write_new(ROOT/'before.json',result)
                result['state']='INSTALL_DISPATCHED';result['install_pending']=True;result['install_calls']=1
                call=tx.install_once(s,staged,NEW_SHA,'calendar-install')
                result['install_response_verified']=tx.verified_response(call)
                try:
                    result['after']=identity(s,m,doc)
                    result['provider_after']=doc.identity(s,PROVIDER,PROVIDER_SHA,10017,37)
                    result['counts_after']=flow.counts('install-after')
                    _,tasks=flow.ui.check_tasks('install-after-tasks');result['tasks_after']=sorted(tasks)
                    result['task_set_preserved']=result['tasks_after']==result['tasks_before']
                    result['data_identity_preserved']=data_projection(result['after'])==data_projection(before)
                    result['zero_provider_baseline_preserved']=result['counts_after']==empty
                except Exception as exc:
                    result['post_read_error']=type(exc).__name__+':'+str(exc)
                require(result['install_response_verified'],'INSTALL_OUTCOME_UNKNOWN_NO_REPLAY')
                require('after' in result and not result.get('post_read_error'),'POST_INSTALL_READBACK_FAILED')
                require(result['after']['apk_sha256']==NEW_SHA and result['after']['apk_bytes']==NEW_BYTES,'POST_INSTALL_APK_DIFFERS')
                require(result['provider_after']==result['provider_before'] and result['zero_provider_baseline_preserved'],
                        'PROVIDER_IDENTITY_OR_COUNTS_CHANGED')
                require(result['data_identity_preserved'] and result['task_set_preserved'],'APP_IDENTITY_OR_TASKS_CHANGED')
                result['signer_after']=pin_tools(deps);require(result['signer_after']==result['signer_before'],'SIGNER_CHANGED_AFTER')
                require(sha(tx.read_regular(BUILD/'result.json',BUILD_SHA,65536))==BUILD_SHA,'BUILD_CHANGED_AFTER')
                s.caller_status('calendar-install-final');result['guard_after']=s.guard()
                require(result['guard_after']==result['guard_before'],'MAIN_CHANGED_AFTER')
                result['install_pending']=False;result['state']='INSTALLED_VERIFIED_NOT_BUSINESS_QUALIFIED'
    except BaseException as exc:
        result['error']=type(exc).__name__+':'+str(exc)
        result['state']='INSTALL_OUTCOME_UNRESOLVED' if result['install_pending'] else 'FAILED'
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_signal)
        result['finished_utc']=stamp()
        if ROOT.is_dir():tx.write_new(ROOT/'result.json',result,alex_readable=True)
    print(json.dumps({key:result.get(key) for key in
        ('state','install_calls','install_pending','data_identity_preserved','zero_provider_baseline_preserved','task_set_preserved','error')}))
    return 0 if result['state']=='INSTALLED_VERIFIED_NOT_BUSINESS_QUALIFIED' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        print('INERT: one reviewed update only; Main guard unchanged; no UI or provider write');raise SystemExit(0)
    raise SystemExit(execute())
