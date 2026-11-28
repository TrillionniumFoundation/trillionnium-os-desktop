"""Compile the original fresh-name helper once under the qualified host reaper.

All compiler/signing children are UID 1000; the root observer's journal remains
private. Source assembly and actual current Main are independently revalidated.
No install, service, Android command or UI entry exists in this producer.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
import types
import zipfile

DEPENDENCIES_SHA='35d868142deecbcc8ac603db3ff7f4bc454f8c6b44155ec11da38cbd7383928c'
COMMAND_NAMES=['aapt-package','javac','d8','align','create-owned-key','sign','signature','alignment','badging','permissions','manifest']
LIMITS={'cpu.max':'100000 100000','memory.max':'536870912','memory.swap.max':'0','pids.max':'128'}


def planner(c,prep_ref):
    packet=c.parse(c.read_ref(prep_ref,131072));rows=[r for r in packet['files'] if Path(r['path']).name=='documents_plan.py']
    c.need(len(rows)==1,'ONE_EXTERNAL_FROZEN_DOCUMENTS_PLANNER')
    p=c.module(rows[0],'actual_documents_producer_plan');p.preparation(c,prep_ref);return p


def pin(c,declared,maximum=268435456):
    declared=Path(declared);path=declared.resolve(strict=True)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd);h=hashlib.sha256();count=0
        c.need(stat.S_ISREG(before.st_mode) and 0<before.st_size<=maximum,'BOUNDED_ORIGINAL_TOOL_INPUT')
        while True:
            raw=os.read(fd,65536)
            if not raw:break
            count+=len(raw);c.need(count<=maximum,'TOOL_INPUT_GREW');h.update(raw)
        c.need(count==before.st_size and c.metadata(before)==c.metadata(os.fstat(fd))
            and declared.resolve(strict=True)==path and c.metadata(path.stat())==c.metadata(before),
            'TOOL_CHANGED_DURING_READ')
        return {'declared_path':str(declared),'resolved_path':str(path),'bytes':count,'sha256':h.hexdigest()}
    finally:os.close(fd)


def dependencies(c,packet):
    rows=[r for r in packet['files'] if Path(r['path']).name=='original_dependencies.json']
    c.need(len(rows)==1 and rows[0]['sha256']==DEPENDENCIES_SHA,'EXACT_ORIGINAL_BUILD_DEPENDENCY_CONTRACT')
    expected=c.parse(c.read_ref(rows[0],16384));actual={n:pin(c,row['declared_path']) for n,row in expected.items()}
    c.need(all(actual[n]['sha256']==row['sha256'] for n,row in expected.items()),'ORIGINAL_BUILD_DEPENDENCY_CHANGED')
    pending=[Path(actual['apksigner_jar']['resolved_path'])];seen=set()
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path);c.need(len(seen)<=8,'ORIGINAL_SIGNER_CLASSPATH_BOUND')
        with zipfile.ZipFile(path) as z:manifest=z.read('META-INF/MANIFEST.MF').decode('utf-8')
        manifest=re.sub(r'\r?\n ','',manifest)
        lines=[line[len('Class-Path: '):] for line in manifest.splitlines() if line.startswith('Class-Path: ')]
        c.need(len(lines)<=1,'SIGNER_CLASSPATH_AMBIGUOUS')
        for name in (lines[0].split() if lines else []):
            c.need(':' not in name and not name.startswith('//'),'NON_FILE_SIGNER_DEPENDENCY')
            declared=Path(name) if name.startswith('/') else path.parent/name;resolved=declared.resolve(strict=True)
            c.need(resolved.parent==Path('/usr/share/java') and resolved.suffix=='.jar','ORIGINAL_SYSTEM_SIGNER_JAR_SCOPE')
            actual['signer_companion_'+resolved.name]=pin(c,declared,67108864);pending.append(resolved)
    return actual


def resources(c):
    lines=Path('/proc/self/cgroup').read_text().splitlines()
    c.need(len(lines)==1 and lines[0].startswith('0::/') and 'hepta-runtime-job-' in lines[0]
        and lines[0].endswith('.service'),'ISOLATED_HOST_BUILD_JOB_REQUIRED')
    path=Path('/sys/fs/cgroup')/lines[0][3:].lstrip('/')
    c.need(str(os.getpid()) in (path/'cgroup.procs').read_text().split(),'ACTUAL_OWN_HOST_CGROUP')
    values={name:(path/name).read_text().strip() for name in (*LIMITS,'memory.current','memory.peak','memory.events','cpu.stat')}
    values['path']=str(path);values['affinity']=sorted(os.sched_getaffinity(0))
    c.need(all(values[k]==v for k,v in LIMITS.items()) and len(values['affinity'])==1 and os.getpriority(os.PRIO_PROCESS,0)>=10,
        'ORIGINAL_ONE_CPU_512M_SWAP0_PIDS128_NICE10_REQUIRED')
    return values


def class_paths(root,package):
    prefix=package.replace('.','/')+'/'
    names={'SafActivity.class','SafActivity$Checked.class','R.class','R$attr.class','R$id.class'}
    names|={'SafActivity$'+str(i)+'.class' for i in range(1,11)}
    return [root/'classes'/name for name in sorted(prefix+n for n in names)]


def command_plan(root,names,tools):
    dep={n:row['resolved_path'] for n,row in tools.items()};java=[dep['java'],'-XX:ActiveProcessorCount=1','-XX:+UseSerialGC','-Xmx256m']
    signer=java+['-jar',dep['apksigner_jar']];source=root/'source';apk=root/'owned-saf.apk'
    password=root/'private-signing/password.txt';key=root/'private-signing/owned.p12'
    java_source=source/'src'/names.PACKAGE.replace('.','/')/'SafActivity.java'
    generated=root/'generated'/names.PACKAGE.replace('.','/')/'R.java'
    return [
      [dep['aapt'],'package','-f','-m','-M',str(source/'AndroidManifest.xml'),'-S',str(source/'res'),'-I',dep['android_jar'],
       '-J',str(root/'generated'),'-F',str(root/'unsigned.apk')],
      [dep['javac'],'-J-XX:ActiveProcessorCount=1','-J-XX:+UseSerialGC','-J-Xmx192m','-proc:none','-encoding','UTF-8','-source','8',
       '-target','8','-bootclasspath',dep['android_jar'],'-d',str(root/'classes'),str(java_source),str(generated)],
      java+['-cp',dep['r8'],'com.android.tools.r8.D8','--lib',dep['android_jar'],'--min-api','31','--output',str(root/'dex'),
            *[str(p) for p in class_paths(root,names.PACKAGE)]],
      [dep['zipalign'],'-f','4',str(root/'unsigned.apk'),str(root/'aligned.apk')],
      java+['-m','java.base/sun.security.tools.keytool.Main','-genkeypair','-noprompt','-storetype','PKCS12','-keystore',str(key),
            '-storepass:file',str(password),'-alias','owned-saf-r12','-keyalg','RSA','-keysize','3072','-validity','3650',
            '-dname','CN=Pocket4 Owned SAF '+names.RUN[:8]+',O=Owned Test,C=US'],
      signer+['sign','--ks',str(key),'--ks-pass','file:'+str(password),'--ks-key-alias','owned-saf-r12','--min-sdk-version','31',
              '--v1-signing-enabled','false','--v2-signing-enabled','true','--v3-signing-enabled','true','--out',str(apk),str(root/'aligned.apk')],
      signer+['verify','--verbose','--print-certs','--min-sdk-version','31',str(apk)],
      [dep['zipalign'],'-c','4',str(apk)],
      [dep['aapt'],'dump','badging',str(apk)],
      [dep['aapt'],'dump','permissions',str(apk)],
      [dep['aapt'],'dump','xmltree',str(apk),'AndroidManifest.xml']]


def validate_artifact_outputs(c,names,root,outputs):
    signature=outputs['signature'];certs=re.findall(rb'^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})\r?$',signature,re.M)
    c.need(len(certs)==1 and b'Number of signers: 1' in signature
        and b'Verified using v3 scheme (APK Signature Scheme v3): true' in signature,'ONE_ACTUAL_V3_OWNED_SIGNER')
    badge=outputs['badging'];permissions=outputs['permissions'];xml=outputs['manifest']
    c.need(("package: name='"+names.PACKAGE+"' versionCode='1'").encode() in badge
        and b"sdkVersion:'31'" in badge and b"targetSdkVersion:'33'" in badge,'ACTUAL_ORIGINAL_HELPER_IDENTITY')
    c.need(b'uses-permission' not in permissions and b'uses-permission' not in xml
        and b'application-debuggable' not in badge and b'launchable-activity' not in badge,'ORIGINAL_HELPER_PRIVILEGE_CONTRACT')
    c.need(len(re.findall(rb'E: activity\s',xml))==1 and all(n not in xml for n in
        (b'E: service ',b'E: receiver ',b'E: provider ',b'E: instrumentation ',b'E: activity-alias ')),
        'ORIGINAL_SINGLE_ACTIVITY_COMPONENT_SET')
    with zipfile.ZipFile(io.BytesIO(c.regular(root/'owned-saf.apk',1048576)[0])) as z:
        entries=z.namelist();c.need(len(entries)==len(set(entries)) and set(entries)=={'AndroidManifest.xml','classes.dex','resources.arsc'},
            'ORIGINAL_EXACT_APK_MEMBERSHIP')
        c.need(z.read('classes.dex')==c.regular(root/'dex/classes.dex',1048576)[0],'SIGNED_APK_NOT_THIS_COMPILED_DEX')
    return certs[0].decode()


def build(c,source_ref,output,prep_ref):
    c.need(os.getuid()==os.geteuid()==0,'ROOT_OBSERVER_FOR_UNPRIVILEGED_COMPILER')
    p=planner(c,prep_ref);source,baseline,_,packet,_,names=p.validate_source(c,source_ref,prep_ref)
    root=Path(output);c.need(root.parent==c.QUALIFICATION and root.parent.resolve()==root.parent
        and re.fullmatch('business-documents-saf-helper-build-[0-9a-f]{32}',root.name),'NEW_HELPER_BUILD_ROOT')
    resource_before=resources(c);c.need(int(resource_before['memory.current'])<134217728,'HOST_BUILD_HEADROOM')
    tools=dependencies(c,packet);plan=command_plan(root,names,tools)
    os.umask(0o077);root.mkdir(mode=0o700);os.chown(root,1000,1000)
    observer=c.private_dir(root/'observer',create=True)
    c.write_new(observer/'once.claim.json',{'source':source_ref,'source_preparation':prep_ref,'automatic_retry':False})
    deadline=time.monotonic()+240
    runtime=p.named(c,packet,'app_runtime.py');commands=runtime.PhaseCommands(c.support(c.SUPPORT_REF)[1]['business_commands.py'],types.SimpleNamespace(c=c,deadline=deadline))
    environment={'PATH':str(Path(tools['java']['resolved_path']).parent)+':/usr/bin:/bin',
        'JAVA_HOME':str(Path(tools['java']['resolved_path']).parent.parent),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
    result={'schema':'pocket4-documents-saf-actual-helper-build-v1','state':'BUILD_FAILED','source':source_ref,'source_preparation':prep_ref,
        'package':names.PACKAGE,'run_id':names.RUN,'commands':[],'tools_before':tools,'error':None,
        'Android_UI_actions':0,'Main_mutations':0,'installed':False,'whole_app_business_accepted':False,'automatic_retry':False,
        'compiler_and_signing_UID':1000,'own_resources_before':resource_before,'system_native_shared_libraries_fully_frozen':False}
    def guard(*,action_attempted=False):
        c.need(time.monotonic()<deadline,'ORIGINAL_HELPER_BUILD_240_SECONDS')
        c.read_ref(source_ref);c.read_ref(prep_ref)
        for row in source['helper_files'].values():c.read_ref(row)
        resources(c);return baseline.guard()
    def directory(path):
        path.mkdir(mode=0o700);os.chown(path,1000,1000)
    def owned_file(path,raw):
        ref=c.write_new(path,raw);os.chown(path,1000,1000);return ref
    def command(index):
        name=COMMAND_NAMES[index];argv=plan[index]
        c.need(index==len(result['commands']),'ORIGINAL_COMPILER_COMMAND_ORDER')
        actual=['/usr/bin/sudo','-n','-u','#1000','--','/usr/bin/env','-i']+[k+'='+environment[k] for k in sorted(environment)]+argv
        value=commands.run_recorded(name,actual,90,observer,guard,protected_pids=baseline.protected_pids,host_env=c.HOST_ENV)
        result['commands'].append({'name':name,'logical_argv':argv,'result':c.regular(observer/(name+'.result.json'),contents=False)})
        return value.stdout
    try:
        result['Main_before']=guard()
        for n in ('source','generated','classes','dex','private-signing'):directory(root/n)
        for rel,row in source['helper_files'].items():
            path=root/'source'/rel;parents=[];parent=path.parent
            while parent!=root/'source':parents.append(parent);parent=parent.parent
            for parent in parents[::-1]:
                if not parent.exists():directory(parent)
            owned_file(path,c.read_ref(row))
        command(0)
        generated=sorted((root/'generated').rglob('R.java'))
        c.need(generated==[root/'generated'/names.PACKAGE.replace('.','/')/'R.java'],'ONE_ACTUAL_GENERATED_R_SOURCE')
        command(1);classes=sorted((root/'classes').rglob('*.class'));c.need(classes==class_paths(root,names.PACKAGE),'EXACT_ORIGINAL_15_COMPILED_CLASSES')
        result['classes']={x.relative_to(root/'classes').as_posix():pin(c,x,262144) for x in classes}
        command(2);c.need(sorted(x.name for x in (root/'dex').iterdir())==['classes.dex'],'SINGLE_COMPILED_DEX')
        dex=c.regular(root/'dex/classes.dex',1048576)[0]
        with zipfile.ZipFile(root/'unsigned.apk','a',compression=zipfile.ZIP_DEFLATED) as z:
            c.need('classes.dex' not in z.namelist(),'NO_PREEXISTING_DEX');z.writestr('classes.dex',dex)
        command(3);owned_file(root/'private-signing/password.txt',(secrets.token_hex(32)+'\n').encode())
        command(4);command(5);outputs={COMMAND_NAMES[i]:command(i) for i in range(6,len(COMMAND_NAMES))}
        cert=validate_artifact_outputs(c,names,root,outputs)
        for rel,row in source['helper_files'].items():c.need(c.regular(root/'source'/rel,1048576)[0]==c.read_ref(row),'COMPILER_SOURCE_COPY_CHANGED')
        result['tools_after']=dependencies(c,packet);c.need(result['tools_after']==tools,'BUILD_DEPENDENCY_DRIFT')
        result['Main_after']=guard();c.need(result['Main_before']==result['Main_after'],'MAIN_CHANGED_DURING_HELPER_BUILD')
        result.update(state='BUILT_SIGNED_VERIFIED_UNINSTALLED',apk=c.regular(root/'owned-saf.apk',1048576,contents=False),
            signer_certificate_sha256=cert,permissions=[],launcher=False,source_and_dependencies_unchanged=True,
            private_signer_publicly_exported=False)
    except BaseException as exc:
        result['state']='UNKNOWN' if getattr(exc,'command_observation',{}).get('host_retirement_proved') is False else 'BUILD_FAILED'
        result['error']={'type':type(exc).__name__,'message':str(exc),'notes':getattr(exc,'__notes__',[])};raise
    finally:
        try:result['own_resources_after']=resources(c)
        except BaseException as exc:
            result['state']='BUILD_FAILED';result['resource_error']=type(exc).__name__+':'+str(exc)
        c.write_new(root/'build-result.json',result)
    c.need(result['state']=='BUILT_SIGNED_VERIFIED_UNINSTALLED','BUILD_NOT_COMPLETE')
    return c.regular(root/'build-result.json',contents=False)


# v2 publishes only the real normal-build public outputs. This is a fixed
# source/byte comparison, never an installation or a current-Main factory.
PREBUILT_MANIFEST={"path":"/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1/saf/MANIFEST.json","bytes":16781,"sha256":"5b965fdab8fd49af9686854fb65f7ce0442e83f716752802ede2f646cc429dbb"}
PREBUILT_ROOT="/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1/saf"
PREBUILT_KIND="saf"
PREBUILT_MEMBERS={"SOURCE.json":{"bytes":2281,"sha256":"a6ac2ec4a91930e573bca80b712738a7db647036a9ba86b3d2f169cd55b7123a"},"STATE-SOURCE.json":{"bytes":15851,"sha256":"d11880a5c19c7783b5d7b130f081740887e559891aee0fc3ebda0cb3f339cb2b"},"helper.apk":{"bytes":24838,"sha256":"eb7bac9ede6b729829fbecb031db4ae7b7224634619154abe2f01b2b3be875d6"},"signer.der":{"bytes":1083,"sha256":"b5ed86bf8873ade11e2304965288d19f0ee0dc84da5a5f3e4411d4535b015ea7"},"source/AndroidManifest.xml":{"bytes":1137,"sha256":"a3adcf3764edcda1fb89526ea93669637e3513342788d4d681581695b77451b9"},"source/SOURCE_PINS.json":{"bytes":2281,"sha256":"a6ac2ec4a91930e573bca80b712738a7db647036a9ba86b3d2f169cd55b7123a"},"source/contract.json":{"bytes":1105,"sha256":"146bba638a8875dd7b3eedc0d1fbbcd28e636975afd4a65cb145927abc7ac6cf"},"source/res/values/ids.xml":{"bytes":273,"sha256":"96b43d2d226700a9d1b99a9575b6ab73f5ca245776165d1a05ef783579e9c1f7"},"source/src/org/droidloom/qa/saf/r12/na7f1de49e707c7a9/SafActivity.java":{"bytes":16590,"sha256":"b0e977a68c02d1e2d9be5509d2e705f4068480ab85bd7409e3fe9a625f0dd7fd"},"state/FixedStateProvider.java":{"bytes":11630,"sha256":"f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545"}}
PREBUILT_SOURCE_SCHEMA="pocket4-documents-saf-prebuilt-source-v2"


def read_prebuilt(c,ref):
    c.need(ref==PREBUILT_MANIFEST,'FIXED_NORMAL_DOCUMENTS_BUNDLE_ONLY')
    value=c.parse(c.read_ref(PREBUILT_MANIFEST,65536))
    c.need(value['schema']=='droidloom.prebuilt-state-helper-bundle.v1'
        and value['kind']==PREBUILT_KIND and value['members']==PREBUILT_MEMBERS
        and value['normal_static_build_verified'] is True and value['installed'] is False
        and value['private_signing_key_published'] is False and value['actual_main_embedded_in_apk'] is False
        and value['runtime_authority_created'] is False and value['whole_app_business_accepted'] is False
        and value['original_sources_recompiled'] is False
        and value['original_manifest_semantics_preserved'] is True
        and value['original_business_dex_resources_assets_preserved'] is True
        and value['contract']['state_caller_uid']==2000 and len(value['commands'])==12 and all(v['returncode']==0 for v in value['commands']),
        'ACTUAL_NORMAL_STATIC_BUILD_SCOPE')
    for name,pin in PREBUILT_MEMBERS.items():
        c.read_ref({'path':PREBUILT_ROOT+'/'+name,**pin},1048576)
    return value


def require_prebuilt_render(c,source,names,rendered):
    value=read_prebuilt(c,source['prebuilt_helper'])
    c.need(source['schema']==PREBUILT_SOURCE_SCHEMA and names.RUN==value['contract']['run_id']
        and names.PACKAGE==value['contract']['package']
        and set(rendered)=={name[len('source/'):] for name in PREBUILT_MEMBERS if name.startswith('source/')},
        'EXACT_STATIC_HELPER_AND_FRESH_CASE_RELATION')
    for name,raw in rendered.items():
        c.need(c.read_ref({'path':PREBUILT_ROOT+'/source/'+name,**PREBUILT_MEMBERS['source/'+name]})==raw,
            'NORMAL_HELPER_RENDER_DIFFERS:'+name)
    c.need(c.parse(c.read_ref({'path':PREBUILT_ROOT+'/SOURCE.json',**PREBUILT_MEMBERS['SOURCE.json']}))
        ==source['helper_manifest'],'NORMAL_HELPER_SOURCE_MANIFEST_DIFFERS')
    return value


def verify_prebuilt_binding(c,v,ref,source,baseline,names,prep_ref):
    fields={'schema','source','source_preparation','baseline','qualification','prebuilt_helper','normal_source',
        'package','run_id','version_code','apk','signer_certificate_sha256','actual_main','actual_application',
        'installed','Android_UI_actions','Main_mutations','whole_app_business_accepted','automatic_retry'}
    c.need(set(v)==fields and v['schema']=='droidloom.documents-prebuilt-binding.v2'
        and source['schema']==PREBUILT_SOURCE_SCHEMA,'EXPLICIT_PREBUILT_DOCUMENTS_BINDING_SCHEMA')
    material=read_prebuilt(c,source['prebuilt_helper']);root=Path(ref['path']).parent
    c.need(Path(ref['path']).name=='build-result.json' and root.parent==c.QUALIFICATION
        and re.fullmatch("business-documents-saf-helper-build-[0-9a-f]{32}",root.name)
        and v['source_preparation']==prep_ref and v['baseline']==source['baseline']
        and v['qualification']==source['qualification'] and v['prebuilt_helper']==source['prebuilt_helper']
        and v['normal_source']=={'path':PREBUILT_ROOT+'/SOURCE.json',**PREBUILT_MEMBERS['SOURCE.json']}
        and v['package']==names.PACKAGE==material['contract']['package']
        and v['run_id']==names.RUN==material['contract']['run_id'] and v['version_code']==1
        and v['signer_certificate_sha256']==material['certificate_sha256']
        and v['installed'] is False and v['Android_UI_actions']==v['Main_mutations']==0
        and v['whole_app_business_accepted'] is False and v['automatic_retry'] is False
        and v['actual_main']==baseline.value['native_owner']['main']
        and v['actual_application']==baseline.value['native_owner']['application'],
        'NORMAL_BUILD_AND_THIS_ACTUAL_MAIN_BINDING')
    expected={'path':str(root/"owned-saf.apk"),**material['apk']}
    c.need(v['apk']==expected and c.read_ref(expected,1048576)==c.read_ref(
        {'path':PREBUILT_ROOT+'/helper.apk',**material['apk']},1048576),
        'PUBLIC_NORMAL_APK_COPY_MUST_MATCH_HELD_INSTALLED_BUNDLE')
    baseline.guard();return v


def verify_build(c,ref,prep_ref):
    v=c.parse(c.read_ref(ref,1048576));p=planner(c,prep_ref)
    source,baseline,_,packet,_,names=p.validate_source(c,v['source'],prep_ref);root=Path(ref['path']).parent
    if source['schema']==PREBUILT_SOURCE_SCHEMA:
        c.need(v.get('schema')=='droidloom.documents-prebuilt-binding.v2','PREBUILT_SOURCE_REQUIRES_NORMAL_BINDING_V2')
        return verify_prebuilt_binding(c,v,ref,source,baseline,names,prep_ref)
    c.need(v.get('schema')!='droidloom.documents-prebuilt-binding.v2','V1_SOURCE_CANNOT_BORROW_V2_BUILD')
    c.need(Path(ref['path']).name=='build-result.json' and root.parent==c.QUALIFICATION
        and re.fullmatch('business-documents-saf-helper-build-[0-9a-f]{32}',root.name)
        and v.get('schema')=='pocket4-documents-saf-actual-helper-build-v1' and v['source_preparation']==prep_ref
        and v['state']=='BUILT_SIGNED_VERIFIED_UNINSTALLED' and v['package']==names.PACKAGE and v['run_id']==names.RUN
        and v['error'] is None and v['installed'] is False and v['Android_UI_actions']==v['Main_mutations']==0
        and v['whole_app_business_accepted'] is False and v['automatic_retry'] is False and v['compiler_and_signing_UID']==1000
        and v['permissions']==[] and v['launcher'] is False and v['source_and_dependencies_unchanged'] is True
        and v['Main_before']==v['Main_after']==baseline.guard(),'ACTUAL_COMPLETE_DOCUMENTS_BUILD_AND_CURRENT_MAIN')
    tools=dependencies(c,packet);c.need(v['tools_before']==v['tools_after']==tools,'ACTUAL_UNCHANGED_ORIGINAL_BUILD_TOOLS')
    for data in (v['own_resources_before'],v['own_resources_after']):
        c.need(all(data[k]==x for k,x in LIMITS.items()) and len(data['affinity'])==1,'ORIGINAL_BUILD_RESOURCE_ENVELOPE')
    plan=command_plan(root,names,tools);c.need([r['name'] for r in v['commands']]==COMMAND_NAMES,'COMPLETE_ORIGINAL_BUILD_CHAIN')
    environment={'PATH':str(Path(tools['java']['resolved_path']).parent)+':/usr/bin:/bin',
        'JAVA_HOME':str(Path(tools['java']['resolved_path']).parent.parent),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
    outputs={}
    for item,argv in zip(v['commands'],plan):
        r=c.parse(c.read_ref(item['result']));actual=['/usr/bin/sudo','-n','-u','#1000','--','/usr/bin/env','-i']+[k+'='+environment[k] for k in sorted(environment)]+argv
        c.need(item['logical_argv']==argv and r['argv']==actual and Path(item['result']['path'])==root/'observer'/(item['name']+'.result.json')
            and r['host_retirement_proved'] is True and r['evidence_complete'] is True and r['returncode']==0
            and r['timed_out'] is False and r['errors']==[] and r.get('first_error') is None,'ACTUAL_ORIGINAL_RETIRED_COMPILER_COMMAND')
        outputs[item['name']]=c.read_ref(r['stdout']);c.read_ref(r['stderr'])
    c.need(c.regular(root/'owned-saf.apk',1048576,contents=False)==v['apk'],'ACTUAL_BUILD_APK_BYTES_CHANGED')
    c.need(validate_artifact_outputs(c,names,root,outputs)==v['signer_certificate_sha256'],'ACTUAL_CURRENT_APK_SIGNATURE_CHAIN')
    classes=class_paths(root,names.PACKAGE)
    c.need(sorted((root/'classes').rglob('*.class'))==classes and v['classes']=={x.relative_to(root/'classes').as_posix():pin(c,x,262144) for x in classes},
        'ACTUAL_COMPILED_CLASS_MEMBERSHIP_AND_BYTES')
    for rel,row in source['helper_files'].items():c.need(c.regular(root/'source'/rel,1048576)[0]==c.read_ref(row),'ACTUAL_COMPILER_SOURCE_CHANGED')
    baseline.guard();return v
