#!/usr/bin/python3 -I
"""Isolated Calendar source/DEX build and same-certificate signing. No Android operations."""
from pathlib import Path
import argparse, datetime, gzip, hashlib, json, os, re, signal, subprocess, time, types, zipfile

HERE=Path(__file__).resolve().parent
OUT=Path('/home/alex/work/pocket4-calendar-repair-build-20261105-r12-11')
PREVIOUS=Path('/home/alex/work/pocket4-calendar-repair-build-20261105-r12-10')
PREVIOUS_APK_SHA='7872aa56b6aa35f4509a27a2c3c0ebb8743da7096136155e425f5b1e4499ae8e'
PREVIOUS_RESULT_SHA='03634674b17dba7960948ba7c92bd326e59f3ec48dc6c48ed94913af2381320a'
CAPTURE=Path('/home/alex/work/pocket4-calendar-code-readonly-20261105-r12-01/com.android.calendar')
PREIMAGE=Path('/home/alex/work/pocket4-calendar-repair-preimage-20261105-r12-03')
PREIMAGE_SHA='1b86909e5954f735ed16796d0ea044e374807dc37457cab0029186d9ab7f253e'
SOURCE_HELPER=Path('/home/alex/work/pocket4-calendar-source-inspection-tools-20261105-r12-02/inspect_source02.py')
SOURCE_HELPER_SHA='276d076bf82a9a8bbd616f9dc5b1c6386eeb88dccf5ac79ca98716d78c122a4c'
TOOLCHAIN=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12/toolchain11.json')
TOOLCHAIN_SHA='9f269253784471fb1cc0cc0f9f554032410ac25c1ca4b28071d21e4264128e4a'
APK_SHA='7522e88fe03f4997513b0e03591da215b8ebc67f6c933939a73addc3c75495a9'
DEX_SHA='ad94f4234e06c7b97ff5f4631fadd22ed7fc03f01187ded30f3c5c3125b194d8'
CERT='a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
SIGN_RECEIPT=Path('/home/alex/work/pocket4-camera-source-20261104/camera-hotplug-candidate-03/apk-release-07/result.json')
SIGN_RECEIPT_SHA='6da344e2624fcc728e046a13c92cdb9b4e999f3808ea4844fb948e821fecc90c'
LIMITS={'cpu.max':'100000 100000','memory.max':'805306368','memory.swap.max':'0','pids.max':'128'}

def require(value,reason):
    if not value: raise RuntimeError(reason)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()
def pin(path):
    path=Path(path).resolve(strict=True); before=path.stat(); value=digest(path); after=path.stat()
    require(0<before.st_size<=268435456 and (before.st_ino,before.st_dev,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
        (after.st_ino,after.st_dev,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'INPUT_CHANGED')
    return {'path':str(path),'bytes':after.st_size,'sha256':value}
def write(path,value):
    raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
    with os.fdopen(fd,'wb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),0,1000);os.fchmod(f.fileno(),0o640)
    return {'bytes':len(raw),'sha256':sha(raw)}
def module(path,expected,name):
    raw=path.read_bytes();require(sha(raw)==expected,'MODULE_PIN:'+str(path))
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def signature_entry(name):
    return name.upper()=='META-INF/MANIFEST.MF' or re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC)',name,re.I) is not None

def main(source_sha):
    require(os.geteuid()==0 and not os.path.lexists(OUT),'FRESH_ROOT_REQUIRED')
    raw=(HERE/'SOURCE_PINS.json').read_bytes();require(sha(raw)==source_sha,'SOURCE_MANIFEST_CHANGED')
    sources=json.loads(raw)['files']
    for name,row in sources.items():
        data=(HERE/name).read_bytes();require(sha(data)==row['sha256'] and len(data)==row['bytes'],'SOURCE_CHANGED:'+name)
    os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
    tmp=OUT/'tmp';tmp.mkdir(mode=0o700)
    result={'schema':'calendar-functional-repair-build-v1','state':'FAILED','commands':[],
            'source_manifest_sha256':source_sha,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'android_commands':0,'ui_inputs':0,'package_mutations':0,'provider_mutations':0,
            'installed':False,'art_runtime_verified':False,'whole_app_production_ready':False}
    deadline=time.monotonic()+200;cg=None;deps={};toolpins={};previous_inputs={}
    def run(label,argv,timeout=65):
        budget=min(timeout,deadline-time.monotonic());require(budget>0,'BUILD_DEADLINE')
        row={'label':label,'argv':argv,'rc':None,'joined':False,'timed_out':False};result['commands'].append(row)
        process=None;start=time.monotonic()
        with (OUT/(label+'.stdout')).open('xb') as stdout,(OUT/(label+'.stderr')).open('xb') as stderr:
            try:
                process=subprocess.Popen(argv,cwd=OUT,stdout=stdout,stderr=stderr,start_new_session=True,
                    close_fds=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TMPDIR':str(tmp)})
                row['rc']=process.wait(timeout=budget);row['joined']=True
            except BaseException as exc:
                row['timed_out']=isinstance(exc,subprocess.TimeoutExpired)
                if process is not None:
                    if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
                    row['rc']=process.wait(timeout=5);row['joined']=True
                raise
            finally:
                stdout.flush();stderr.flush();os.fsync(stdout.fileno());os.fsync(stderr.fileno())
                row['elapsed_seconds']=time.monotonic()-start
        for ext in ('stdout','stderr'):
            p=OUT/(label+'.'+ext);require(p.stat().st_size<=2*1024*1024,'LOG_BOUND')
            row[ext]={'bytes':p.stat().st_size,'sha256':digest(p)}
        if row['rc']!=0:
            result['failed_command_stderr']=(OUT/(label+'.stderr')).read_text(errors='replace')[-32768:]
        require(row['rc']==0,'COMMAND_FAILED:'+label)
        return (OUT/(label+'.stdout')).read_text(errors='strict')
    try:
        rows=[s[3:] for s in Path('/proc/self/cgroup').read_text().splitlines() if s.startswith('0::')]
        require(len(rows)==1,'CGROUP_V2');cg=Path('/sys/fs/cgroup')/rows[0].lstrip('/')
        result['limits']={n:(cg/n).read_text().strip() for n in LIMITS}
        require(result['limits']==LIMITS and sorted(os.sched_getaffinity(0))==[20],'RESOURCE_LIMITS')
        for path,d in [(CAPTURE/'base.apk',APK_SHA),(CAPTURE/'classes.dex',DEX_SHA),
                       (PREIMAGE/'result.json',PREIMAGE_SHA),(TOOLCHAIN,TOOLCHAIN_SHA),(SIGN_RECEIPT,SIGN_RECEIPT_SHA)]:
            require(digest(path)==d,'FIXED_INPUT_CHANGED:'+str(path))
        helper=module(SOURCE_HELPER,SOURCE_HELPER_SHA,'calendar_build_source_helper')
        patch=module(HERE/'patch_original.py',sources['patch_original.py']['sha256'],'calendar_build_patch')
        ir=module(HERE/'smali_equivalence.py',sources['smali_equivalence.py']['sha256'],'calendar_build_ir')
        require(digest(PREVIOUS/'result.json')==PREVIOUS_RESULT_SHA,'PREVIOUS_BUILD_RECEIPT_CHANGED')
        previous=json.loads((PREVIOUS/'result.json').read_text())
        require(previous['state']=='BUILT_SIGNED_NOT_INSTALLED' and previous['signed_apk']['sha256']==PREVIOUS_APK_SHA,
            'PREVIOUS_BUILD_NOT_VERIFIED')
        for name,expected_pin in [('result.json',PREVIOUS_RESULT_SHA),('Calendar-pocket4-functional.apk',PREVIOUS_APK_SHA),
            ('class-ir-proof.json',previous['semantic_proof']['proof']['sha256'])]:
            previous_inputs[name]=pin(PREVIOUS/name)
            require(previous_inputs[name]['sha256']==expected_pin,'PREVIOUS_ARTIFACT_CHANGED:'+name)
        previous_ir={x['class']:x['candidate_ir_sha256'] for x in json.loads((PREVIOUS/'class-ir-proof.json').read_text())}
        result['previous10_inputs_before']=previous_inputs
        expected=json.loads((HERE/'dependencies.json').read_text())
        for name,row in expected.items():
            deps[name]=pin(row['declared_path']);require(deps[name]['sha256']==row['sha256'],'SDK_TOOL_CHANGED:'+name)
        toolchain=json.loads(TOOLCHAIN.read_text())
        for group in ('jars','jre'):
            for name,row in toolchain[group].items():
                toolpins[group+'/'+name]=pin(row['canonical'])
                require(toolpins[group+'/'+name]['sha256']==row['sha256'],'SMALI_TOOL_CHANGED:'+name)
        result['dependencies_before']=deps;result['smali_tools_before']=toolpins
        patch_result=patch.patch_tree(PREIMAGE/'original-smali',OUT/'candidate-smali',PREIMAGE/'result.json')
        write(OUT/'patch-result.json',patch_result);result['patch']=patch_result
        classes=OUT/'classes';classes.mkdir();testclasses=OUT/'test-classes';testclasses.mkdir()
        java=deps['java']['path'];javac=deps['javac']['path'];sdk=deps['android_jar']['path']
        vm=['-Xmx256m','-XX:ActiveProcessorCount=1','-XX:-UsePerfData','-Djava.io.tmpdir='+str(tmp),'-Duser.home='+str(tmp)]
        javacvm=['-J'+v for v in vm]
        run('javac',[javac,*javacvm,'-encoding','UTF-8','-g','-source','8','-target','8','-bootclasspath',deps['core_lambda_stubs']['path']+':'+sdk,
            '-d',str(classes),*[str(p) for p in sorted((HERE/'src').rglob('*.java'))]])
        run('test-javac',[javac,*javacvm,'-source','8','-target','8','-bootclasspath',deps['core_lambda_stubs']['path']+':'+sdk,'-cp',str(classes),'-d',str(testclasses),
            *[str(p) for p in sorted((HERE/'tests').glob('*.java'))]])
        result['host_tests']={}
        for test in ('EventDraftTest','ProviderReceiptTest','EventReferenceTest','SnoozeStateTest','AlertIdentityTest'):
            result['host_tests'][test]=run(test.lower(),[java,*vm,'-cp',str(classes)+':'+str(testclasses),test])
        jar=OUT/'new-program.jar'
        with zipfile.ZipFile(jar,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for p in sorted(classes.rglob('*.class')):
                info=zipfile.ZipInfo(p.relative_to(classes).as_posix(),(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(info,p.read_bytes())
        dexdir=OUT/'new-dex';dexdir.mkdir()
        run('d8',[java,*vm,'-cp',deps['r8']['path'],'com.android.tools.r8.D8','--release','--min-api','37',
            '--lib',sdk,'--output',str(dexdir),str(jar)])
        require([p.name for p in dexdir.iterdir()]==['classes.dex'],'ONE_NEW_DEX_REQUIRED')
        j25=toolchain['jre']['bin/java']['canonical']
        cpnames=['antlr3-runtime','dexlib2','guava','jcommander','smali-util']
        def cp(extra):return ':'.join(toolchain['jars'][n]['canonical'] for n in [*cpnames,extra])
        # Compare the actual prior/new restored DEX, not merely Java file hashes.
        with zipfile.ZipFile(PREVIOUS/'Calendar-pocket4-functional.apk') as prior:
            write(OUT/'previous-classes2.dex',prior.read('classes2.dex'))
        for label,source,target in [('previous-restored',OUT/'previous-classes2.dex',OUT/'previous-restored-smali'),
                                    ('candidate-restored',dexdir/'classes.dex',OUT/'candidate-restored-smali')]:
            run(label,[j25,*vm,'-cp',cp('baksmali'),'org.jf.baksmali.Main','disassemble','--api','35','--jobs','1',
                '--output',str(target),str(source)])
        older={p.relative_to(OUT/'previous-restored-smali').as_posix():p for p in (OUT/'previous-restored-smali').rglob('*.smali')}
        newer={p.relative_to(OUT/'candidate-restored-smali').as_posix():p for p in (OUT/'candidate-restored-smali').rglob('*.smali')}
        require(set(older)==set(newer) and len(older)==60,'RESTORED_CLASS_SET_CHANGED')
        changes_expected={
            'com/android/calendar/event/ProviderReceipt.smali':{
                'changed':set(),'added':{'calendarId(Ljava/lang/String;Ljava/lang/String;)J'}},
            'com/android/calendar/event/EventEditorStore.smali':{
                'changed':{'createLocalCalendar(Ljava/lang/String;)J'},'added':set()}}
        restored_rows=[];actual_changes={}
        for name in sorted(older):
            former=ir.class_ir(older[name].read_text());candidate=ir.class_ir(newer[name].read_text())
            if name not in changes_expected:
                require(former==candidate,'UNRELATED_RESTORED_CLASS_CHANGED:'+name)
            else:
                require(former['header']==candidate['header'],'RECEIPT_CLASS_HEADER_CHANGED:'+name)
                require(set(former['methods'])<=set(candidate['methods']),'RESTORED_METHOD_REMOVED:'+name)
                added={m.split()[-1] for m in set(candidate['methods'])-set(former['methods'])}
                changed={m.split()[-1] for m in former['methods'] if former['methods'][m]!=candidate['methods'][m]}
                require(added==changes_expected[name]['added'] and changed==changes_expected[name]['changed'],
                    'CALENDAR_RECEIPT_METHOD_DELTA:'+name)
                actual_changes[name]={'changed_methods':sorted(changed),'added_methods':sorted(added)}
            restored_rows.append({'class':name,'previous_ir_sha256':ir.ir_sha256(former),'candidate_ir_sha256':ir.ir_sha256(candidate),
                'equal':former==candidate})
        require(sum(x['equal'] for x in restored_rows)==58,'EXACT_TWO_RESTORED_CLASSES_CHANGED')
        write(OUT/'restored-class-ir-proof.json',restored_rows)
        result['restored_code_proof']={'classes_compared':len(older),'unchanged_classes':58,
            'changed_classes':sorted(actual_changes),'actual_method_changes':actual_changes,
            'original_generic_receipt_validator_IR_unchanged':True,
            'proof':pin(OUT/'restored-class-ir-proof.json')}
        run('assemble',[j25,*vm,'-cp',cp('smali'),'org.jf.smali.Main','assemble','--api','35','--jobs','1',
            '--output',str(OUT/'patched.dex'),str(OUT/'candidate-smali')])
        run('roundtrip',[j25,*vm,'-cp',cp('baksmali'),'org.jf.baksmali.Main','disassemble','--api','35','--jobs','1',
            '--output',str(OUT/'roundtrip'),str(OUT/'patched.dex')])
        rows=json.loads((PREIMAGE/'result.json').read_text())['class_manifest'];semantic=[]
        expected_methods={(x['class'],x['method']) for x in patch_result['changes'] if 'method' in x}
        observed_methods=set();method_count=0;changes_from10=[]
        for row in rows:
            name=row['path'];old=ir.class_ir((PREIMAGE/'original-smali'/name).read_text())
            candidate=ir.class_ir((OUT/'candidate-smali'/name).read_text());roundtrip=ir.class_ir((OUT/'roundtrip'/name).read_text())
            require(candidate==roundtrip,'ROUNDTRIP_IR_DIFF:'+name)
            former=ir.class_ir((PREVIOUS/'candidate-smali'/name).read_text())
            require(ir.ir_sha256(former)==previous_ir[name],'PREVIOUS_SMALI_DIFFERS_FROM_VERIFIED_IR:'+name)
            require(former['header']==candidate['header'] and set(former['methods'])==set(candidate['methods']),
                'CLASS_STRUCTURE_CHANGED_FROM10:'+name)
            for signature,body in former['methods'].items():
                if body!=candidate['methods'][signature]:changes_from10.append([name,signature.split()[-1]])
            require(set(old['methods'])==set(candidate['methods']),'ORIGINAL_METHOD_SET_CHANGED:'+name)
            expected_header=[x.replace('.super Landroid/app/Activity;','.super Lcom/android/calendar/event/EditEventActivity;')
                if name=='com/android/calendar/EventInfoActivity.smali' else x for x in old['header']]
            require(candidate['header']==expected_header,'CLASS_METADATA_CHANGED:'+name)
            for signature,before in old['methods'].items():
                method_count+=1
                if before!=candidate['methods'][signature]: observed_methods.add((name,signature.split()[-1]))
            semantic.append({'class':name,'original_ir_sha256':ir.ir_sha256(old),
                'candidate_ir_sha256':ir.ir_sha256(candidate),'roundtrip_equal':True})
        require(observed_methods==expected_methods,'TARGET_METHOD_DIFF_SET')
        require(changes_from10==[],'NO_ORIGINAL_CLASS_METHOD_MAY_DIFFER_FROM10')
        write(OUT/'class-ir-proof.json',semantic)
        result['semantic_proof']={'classes':445,'methods':method_count,'only_expected_methods_changed':True,
            'changed_methods':len(observed_methods),'roundtrip_equal_all_classes':True,
            'proof':pin(OUT/'class-ir-proof.json')}
        old_defs={x['descriptor'] for x in helper.all_definitions((CAPTURE/'classes.dex').read_bytes())}
        patched_defs={x['descriptor'] for x in helper.all_definitions((OUT/'patched.dex').read_bytes())}
        new_defs={x['descriptor'] for x in helper.all_definitions((dexdir/'classes.dex').read_bytes())}
        require(old_defs==patched_defs and not old_defs.intersection(new_defs),'DEX_CLASS_IDENTITY_COLLISION')
        require({'Lcom/android/calendar/event/EditEventActivity;','Lcom/android/calendar/alerts/SnoozeAlarmsService;'}<=new_defs,'MISSING_COMPONENT_NOT_RESTORED')
        result['new_class_definitions']=sorted(new_defs)
        unsigned=OUT/'Calendar-unsigned.apk'
        payload=[]
        with zipfile.ZipFile(CAPTURE/'base.apk') as original,zipfile.ZipFile(unsigned,'x') as target:
            require(len(original.namelist())==len(set(original.namelist())) and original.testzip() is None,'PARENT_ZIP_INVALID')
            require('classes2.dex' not in original.namelist(),'UNEXPECTED_PARENT_MULTIDEX')
            for info in original.infolist():
                if signature_entry(info.filename):continue
                raw=original.read(info.filename)
                target.writestr(info,(OUT/'patched.dex').read_bytes() if info.filename=='classes.dex' else raw)
                payload.append({'name':info.filename,'bytes':len(raw),'sha256':sha(raw)})
            info=zipfile.ZipInfo('classes2.dex',(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            target.writestr(info,(dexdir/'classes.dex').read_bytes())
        aligned=OUT/'Calendar-aligned.apk';signed=OUT/'Calendar-pocket4-functional.apk'
        run('zipalign',[deps['zipalign']['path'],'-f','-P','16','4',str(unsigned),str(aligned)])
        signing=json.loads(SIGN_RECEIPT.read_text());oldsign=next(x['argv'] for x in signing['commands'] if x['label']=='sign')
        require(oldsign[:2]==['/usr/bin/apksigner','sign'] and '--ks-pass' not in oldsign and '--key-pass' not in oldsign,'SIGN_SHAPE')
        require(oldsign[oldsign.index('--min-sdk-version')+1]=='37','SIGN_API')
        signargs=oldsign[1:];signargs[signargs.index('--out')+1]=str(signed);signargs[-1]=str(aligned)
        run('sign',[java,*vm,'-jar',deps['apksigner_jar']['path'],*signargs])
        signature=run('signature-verify',[java,*vm,'-jar',deps['apksigner_jar']['path'],'verify','--verbose','--print-certs',str(signed)])
        require('Signer #1 certificate SHA-256 digest: '+CERT in signature and
            'Verified using v3 scheme (APK Signature Scheme v3): true' in signature,'SIGNATURE_IDENTITY')
        run('alignment-verify',[deps['zipalign']['path'],'-c','-P','16','4',str(signed)])
        with zipfile.ZipFile(signed) as built:
            names=set(built.namelist());require(len(names)==len(built.namelist()) and built.testzip() is None,'SIGNED_ZIP_INVALID')
            original_names={x['name'] for x in payload}
            require({n for n in names if not signature_entry(n)}==original_names|{'classes2.dex'},'PAYLOAD_SET_CHANGED')
            for row in payload:
                if row['name']=='classes.dex':continue
                raw=built.read(row['name']);require(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'NON_TARGET_ZIP_PAYLOAD_CHANGED:'+row['name'])
            require(built.read('classes.dex')==(OUT/'patched.dex').read_bytes() and built.read('classes2.dex')==(dexdir/'classes.dex').read_bytes(),'DEX_PAYLOAD_CHANGED')
            with zipfile.ZipFile(PREVIOUS/'Calendar-pocket4-functional.apk') as former:
                previous_names={n for n in former.namelist() if not signature_entry(n)}
                require(previous_names=={n for n in names if not signature_entry(n)},'PAYLOAD_SET_CHANGED_FROM10')
                for name in sorted(previous_names-{'classes2.dex'}):
                    require(built.read(name)==former.read(name),'NON_TARGET_PAYLOAD_CHANGED_FROM10:'+name)
                result['against_previous10']={'apk_sha256':PREVIOUS_APK_SHA,'changed_methods':changes_from10,
                    'classes_compared':len(previous_ir),'methods_compared':method_count,
                    'all_other_methods_IR_equal':True,'classes2_dex_byte_equal':built.read('classes2.dex')==former.read('classes2.dex'),
                    'classes_dex_byte_equal':True,'classes2_preserved_except_reviewed_receipt_path':True,
                    'all_other_non_signature_payloads_byte_equal':True,'compared_non_signature_payloads':len(previous_names)}
        result['payload_proof']={'original_payloads':len(payload),'all_non_dex_payloads_byte_equal':True,
            'manifest_resources_permissions_unchanged':True,'only_replaced_payload':'classes.dex','only_added_payload':'classes2.dex'}
        write(OUT/'original-payload-manifest.json',payload)
        result['signed_apk']=pin(signed);result['certificate_sha256']=CERT
        result['signature_v3_verified']=True;result['alignment_16k_verified']=True
        os.chown(signed,0,1000);os.chmod(signed,0o640)
        result['state']='BUILT_SIGNED_NOT_INSTALLED'
    except BaseException as exc:
        result['error']=type(exc).__name__+':'+str(exc)
    finally:
        try:
            after={name:pin(row['path']) for name,row in deps.items()}
            tafter={name:pin(row['path']) for name,row in toolpins.items()}
            require(after==deps and tafter==toolpins,'TOOLS_CHANGED_AFTER_BUILD')
            for name,row in sources.items():require(digest(HERE/name)==row['sha256'],'SOURCE_CHANGED_AFTER:'+name)
            require(digest(CAPTURE/'base.apk')==APK_SHA and digest(CAPTURE/'classes.dex')==DEX_SHA,'PARENT_CHANGED_AFTER')
            require({name:pin(PREVIOUS/name) for name in previous_inputs}==previous_inputs,'PREVIOUS10_INPUT_CHANGED_AFTER')
            result['input_postcheck_passed']=True
        except BaseException as exc:
            result['state']='FAILED';result['postcheck_error']=type(exc).__name__+':'+str(exc)
        if cg is not None:result['resource_usage']={n:(cg/n).read_text().strip() for n in ('memory.peak','memory.events','cpu.stat')}
        result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        raw=(json.dumps(result,sort_keys=True,indent=2)+'\n').encode();write(OUT/'result.json',raw)
        compressed=write(OUT/'result.json.gz',gzip.compress(raw,mtime=0))
    print(json.dumps({'state':result['state'],'error':result.get('error'),'signed_apk':result.get('signed_apk'),
        'result_gzip':compressed,'android_commands':0,'installed':False}))
    return 0 if result['state']=='BUILT_SIGNED_NOT_INSTALLED' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--source-sha')
    args=parser.parse_args()
    if not args.execute:print('INERT: host build only, no Android operations');raise SystemExit(0)
    raise SystemExit(main(args.source_sha))
