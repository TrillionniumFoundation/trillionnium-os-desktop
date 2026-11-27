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

# Only the exact compiled original dependency declaration can be relocated.
ORIGINAL_DEPENDENCY_PATHS = {'aapt': '/usr/lib/android-sdk/build-tools/debian/aapt', 'android_jar': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/sdk/31/public/android.jar', 'apksigner_jar': '/usr/share/java/apksigner.jar', 'java': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/bin/java', 'java_security': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/conf/security/java.security', 'javac': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/bin/javac', 'jdk_modules': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/modules', 'jdk_release': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/release', 'jvm_cfg': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/jvm.cfg', 'libjava': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjava.so', 'libjimage': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjimage.so', 'libjli': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjli.so', 'libjvm': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/server/libjvm.so', 'r8': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/cmdline-tools/tools/lib/r8.jar', 'zipalign': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/build-tools/linux-x86/bin/zipalign'}
INSTALLED_DEPENDENCY_PATHS = {'aapt': '/usr/lib/android-sdk/build-tools/debian/aapt', 'android_jar': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/sdk/31/public/android.jar', 'apksigner_jar': '/usr/share/java/apksigner.jar', 'java': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/bin/java', 'java_security': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/conf/security/java.security', 'javac': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/bin/javac', 'jdk_modules': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/lib/modules', 'jdk_release': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/release', 'jvm_cfg': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/lib/jvm.cfg', 'libjava': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/lib/libjava.so', 'libjimage': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/lib/libjimage.so', 'libjli': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/lib/libjli.so', 'libjvm': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86/lib/server/libjvm.so', 'r8': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/cmdline-tools/tools/lib/r8.jar', 'zipalign': '/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/build-tools/linux-x86/bin/zipalign'}

def _installed_dependency_paths(expected):
    if type(expected) is not dict or set(expected) != set(ORIGINAL_DEPENDENCY_PATHS):
        raise RuntimeError('EXACT_COMPILED_DEPENDENCY_ROSTER_REQUIRED')
    if any(type(expected[name]) is not dict or
           expected[name].get('declared_path') != path
           for name, path in ORIGINAL_DEPENDENCY_PATHS.items()):
        raise RuntimeError('EXACT_ORIGINAL_DEPENDENCY_PATH_REQUIRED')
    return dict(INSTALLED_DEPENDENCY_PATHS)



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
    expected=c.parse(c.read_ref(rows[0],16384))
    working=c.working_runtime_root() is not None
    locations=(_installed_dependency_paths(expected) if working else
               {name:row['declared_path'] for name,row in expected.items()})
    actual={name:pin(c,path) for name,path in locations.items()}
    if working:
        c.need(all(actual[name]['resolved_path']==path for name,path in locations.items()
                   if path.startswith('/usr/lib/droidloom-native-leaf-toolchain/')),
               'INSTALLED_TOOLCHAIN_CANNOT_RESOLVE_BACK_TO_WORKSPACE')
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


def validate_resources(c,values):
    if c.working_runtime_root() is not None:
        limits=values.get('effective_limits',{})
        c.need(values.get('working_resource_scope')=='actual-owned-probe-ancestors' and
            values.get('path')=='/sys/fs/cgroup/system.slice/droidloom-working-qualification.service/owned-probe' and
            type(values.get('cgroup_ancestors')) is list and len(values['cgroup_ancestors'])>=3 and
            set(limits)=={'cpu_quota','cpu_period','memory_max','memory_swap_max','pids_max'} and
            all(type(v) is int for v in limits.values()) and
            0<limits['cpu_quota']<=limits['cpu_period'] and
            0<limits['memory_max']<=536870912 and limits['memory_swap_max']==0 and
            0<limits['pids_max']<=128 and len(values['affinity'])==1 and values['nice']>=10,
            'ACTUAL_EFFECTIVE_ONE_CPU_512M_SWAP0_PIDS128_NICE10_REQUIRED')
    else:
        c.need(all(values[k]==v for k,v in LIMITS.items()) and len(values['affinity'])==1,
               'ORIGINAL_BUILD_RESOURCE_ENVELOPE')
    return values


def resources(c):
    if c.working_runtime_root() is not None:
        return validate_resources(c,c.support()[1]['business_commands.py'].working_build_resources())
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
    root=Path(output);c.need(c.input_root_matches(root,'documents-saf','helper-build','business-documents-saf-helper-build-[0-9a-f]{32}')
        and root.parent.resolve()==root.parent,'NEW_HELPER_BUILD_ROOT')
    resource_before=resources(c);c.need(int(resource_before['memory.current'])<134217728,'HOST_BUILD_HEADROOM')
    tools=dependencies(c,packet);plan=command_plan(root,names,tools)
    os.umask(0o077);root.mkdir(mode=0o700);os.chown(root,1000,1000)
    observer=c.private_dir(root/'observer',create=True)
    c.write_new(observer/'once.claim.json',{'source':source_ref,'source_preparation':prep_ref,'automatic_retry':False})
    deadline=time.monotonic()+240
    runtime=p.named(c,packet,'app_runtime.py');commands=runtime.PhaseCommands(c.support(c.SUPPORT_REF)[1]['business_commands.py'],types.SimpleNamespace(c=c,deadline=deadline))
    working_build=commands.working_build_context(root)
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
        value=commands.run_recorded(name,argv if working_build is not None else actual,90,observer,guard,
            protected_pids=baseline.protected_pids,
            host_env=environment if working_build is not None else c.HOST_ENV,working_build=working_build)
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
        if working_build is not None:working_build.close()
        c.write_new(root/'build-result.json',result)
    c.need(result['state']=='BUILT_SIGNED_VERIFIED_UNINSTALLED','BUILD_NOT_COMPLETE')
    return c.regular(root/'build-result.json',contents=False)


def verify_build(c,ref,prep_ref):
    v=c.parse(c.read_ref(ref,1048576));p=planner(c,prep_ref)
    source,baseline,_,packet,_,names=p.validate_source(c,v['source'],prep_ref);root=Path(ref['path']).parent
    c.need(Path(ref['path']).name=='build-result.json' and c.input_root_matches(root,'documents-saf','helper-build','business-documents-saf-helper-build-[0-9a-f]{32}')
        and v.get('schema')=='pocket4-documents-saf-actual-helper-build-v1' and v['source_preparation']==prep_ref
        and v['state']=='BUILT_SIGNED_VERIFIED_UNINSTALLED' and v['package']==names.PACKAGE and v['run_id']==names.RUN
        and v['error'] is None and v['installed'] is False and v['Android_UI_actions']==v['Main_mutations']==0
        and v['whole_app_business_accepted'] is False and v['automatic_retry'] is False and v['compiler_and_signing_UID']==1000
        and v['permissions']==[] and v['launcher'] is False and v['source_and_dependencies_unchanged'] is True
        and v['Main_before']==v['Main_after']==baseline.guard(),'ACTUAL_COMPLETE_DOCUMENTS_BUILD_AND_CURRENT_MAIN')
    tools=dependencies(c,packet);c.need(v['tools_before']==v['tools_after']==tools,'ACTUAL_UNCHANGED_ORIGINAL_BUILD_TOOLS')
    for data in (v['own_resources_before'],v['own_resources_after']):
        validate_resources(c,data)
    plan=command_plan(root,names,tools);c.need([r['name'] for r in v['commands']]==COMMAND_NAMES,'COMPLETE_ORIGINAL_BUILD_CHAIN')
    environment={'PATH':str(Path(tools['java']['resolved_path']).parent)+':/usr/bin:/bin',
        'JAVA_HOME':str(Path(tools['java']['resolved_path']).parent.parent),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
    outputs={}
    for item,argv in zip(v['commands'],plan):
        r=c.parse(c.read_ref(item['result']));actual=['/usr/bin/sudo','-n','-u','#1000','--','/usr/bin/env','-i']+[k+'='+environment[k] for k in sorted(environment)]+argv
        argv_checked=(c.support()[1]['business_commands.py'].verify_working_build_record(r,argv,root,environment)
                      if c.working_runtime_root() is not None else r['argv']==actual)
        c.need(item['logical_argv']==argv and argv_checked and Path(item['result']['path'])==root/'observer'/(item['name']+'.result.json')
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
