#!/usr/bin/python3 -I
"""One data-preserving Calendar update. Default inert; no UI or provider mutation."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, io, json, os, re, signal, stat, types, zipfile

ROOT=Path('/home/alex/work/pocket4-calendar-repair-install-20261105-r12-06')
BUILD=Path('/home/alex/work/pocket4-calendar-repair-build-20261105-r12-06')
BUILD_SHA='a5100a2d71d90ef3f20701a87239d5631b3c163afdd72706fdcdb846d03ba320'
OLD_SHA='7522e88fe03f4997513b0e03591da215b8ebc67f6c933939a73addc3c75495a9'
NEW_SHA='cf06143a7f90aa28607dd32e85a41b897ef4634fc602c50da47a9a1352e095f7'
OLD_BYTES,NEW_BYTES=2532558,2622925
PACKAGE='com.android.calendar'
PROVIDER='com.android.providers.calendar'
PROVIDER_SHA='eebf12f81981f7d8c59a9b9ed465945818d2ab0208c121d858cbc4e6426f5fff'
CERT='a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
FLOW=Path('/home/alex/work/pocket4-calendar-flow-tools-20261105-r12-01/run_calendar01.py')
FLOW_SHA='d307f4ceda9fc80e216f280cb1a9558fbe4e27b43cd659ecc83a1c6edab9c8fa'
CLEANUP=Path('/home/alex/work/pocket4-calendar-cleanup-20261105-r12-02/result.json')
CLEANUP_SHA='185ce605ff4f1caefbcb7fc37773658899b90b82078b9def2e8391a80b874019'
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
        require(len(a)==663 and b==a|{'classes2.dex'} and 'classes2.dex' not in a,'PAYLOAD_SET_CHANGED')
        require([n for n in sorted(a) if old.read(n)!=new.read(n)]==['classes.dex'],'NON_TARGET_PAYLOAD_CHANGED')
        require(sha(old.read('classes.dex'))=='ad94f4234e06c7b97ff5f4631fadd22ed7fc03f01187ded30f3c5c3125b194d8',
                'ORIGINAL_DEX_CHANGED')

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
    m=load(FLOW,FLOW_SHA)
    tx,base,doc,diag=[m.load(Path(path),pin,'calendar_install_dependency_'+str(i))
                     for i,(path,pin) in enumerate(m.PINS.items())]
    require(m.PINS[str(m.TX)]=='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470',
            'ORIGINAL_HELD_GUARD_REQUIRED')
    base.PACKAGE=base.DOCS=m.CALENDAR;base.CLIENT=m.MAIN;base.FILES=m.INFO;diag.PACKAGE=PACKAGE
    m.ROOT=ROOT;m.TABLES=(*m.TABLES,'CalendarAlerts')
    result={'schema':'calendar-data-preserving-install-v1','state':'NOT_DISPATCHED',
        'source_sha256':sha(Path(__file__).read_bytes()),'started_utc':stamp(),
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
            prior=json.loads(tx.read_regular(CLEANUP,CLEANUP_SHA,32768))
            require(prior['state']=='FAILED_BUSINESS_FLOW_EXACT_FIXTURE_CLEANUP_VERIFIED' and
                prior['helper_package_and_data_absent'] is True and prior['calendar_removed'] is True and
                not prior['delete_pending'] and not prior['uninstall_pending'],'PRIOR_FIXTURE_NOT_CLEAN')
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
                require({k:v for k,v in before.items() if k!='first_install_time'}==prior['calendar_after'],
                        'CALENDAR_PREIMAGE_CHANGED_SINCE_CLEANUP')
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
