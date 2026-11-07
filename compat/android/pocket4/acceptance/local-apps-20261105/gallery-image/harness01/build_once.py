#!/usr/bin/python3 -I
"""Compile/package/sign this isolated MediaStore fixture once; never install or touch UI."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, secrets, signal, stat, subprocess, time
import xml.etree.ElementTree as ET
import zipfile

HERE=Path(__file__).resolve().parent
OUTPUT=Path('/home/alex/work/pocket4-gallery-fixture-build-20261105-r12-01')
PACKAGE='org.droidloom.qa.media.r12.na1d407c85b3e6f92'
JDK=Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86')
LIMITS={'cpu.max':'100000 100000','memory.max':'536870912','memory.swap.max':'0','pids.max':'128'}
ATTR='{http://schemas.android.com/apk/res/android}'


def need(value, reason):
    if not value:raise RuntimeError(reason)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def pin(declared, maximum=268435456):
    path=Path(declared).resolve(strict=True)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd);digest=hashlib.sha256();count=0
        need(stat.S_ISREG(before.st_mode) and 0<before.st_size<=maximum,'BOUNDED_REGULAR_INPUT_REQUIRED')
        while True:
            raw=os.read(fd,65536)
            if not raw:break
            count+=len(raw);need(count<=maximum,'INPUT_GREW');digest.update(raw)
        after=os.fstat(fd)
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
        need(count==before.st_size and all(getattr(before,k)==getattr(after,k) for k in fields),'INPUT_CHANGED')
        return {'declared_path':str(declared),'resolved_path':str(path),'bytes':count,'sha256':digest.hexdigest()}
    finally:os.close(fd)


def write_new(path, value):
    raw=value if isinstance(value,bytes) else (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())


def source_pins(expected):
    raw=(HERE/'SOURCE_PINS.json').read_bytes();need(sha(raw)==expected,'SOURCE_MANIFEST_CHANGED')
    files=json.loads(raw)['files']
    required={'AndroidManifest.xml','res/values/ids.xml','contract.json','dependencies.json','build_once.py',
        'src/'+PACKAGE.replace('.','/')+'/MediaFixture.java'}
    need(set(files)==required,'EXACT_SOURCE_MEMBERSHIP_REQUIRED')
    actual={name:pin(HERE/name,1048576) for name in sorted(required)}
    need(all(actual[n]['sha256']==files[n]['sha256'] and actual[n]['bytes']==files[n]['bytes']
        for n in files),'SOURCE_FILE_CHANGED')
    root=ET.fromstring((HERE/'AndroidManifest.xml').read_bytes())
    need(root.tag=='manifest' and root.get('package')==PACKAGE and root.get(ATTR+'versionCode')=='1'
        and [n.tag for n in root]==['uses-sdk','queries','application','instrumentation'],'MANIFEST_CONTRACT_CHANGED')
    app=root.find('application');activities=app.findall('activity')
    need(app.get(ATTR+'debuggable')=='false' and app.get(ATTR+'allowBackup')=='false'
        and app.get(ATTR+'testOnly')=='true' and len(app)==0 and not activities
        and len(root.findall('instrumentation'))==1
        and root.find('instrumentation').get(ATTR+'name')=='.MediaFixture'
        and root.find('instrumentation').get(ATTR+'targetPackage')==PACKAGE,'COMPONENT_OR_PRIVILEGE_CHANGED')
    need('android.intent.category.LAUNCHER' not in (HERE/'AndroidManifest.xml').read_text(),
        'LAUNCHER_NOT_ALLOWED')
    return actual


def dependencies():
    expected=json.loads((HERE/'dependencies.json').read_bytes())
    actual={name:pin(row['declared_path']) for name,row in expected.items()}
    need(all(actual[n]['sha256']==row['sha256'] for n,row in expected.items()),'DEPENDENCY_PIN_CHANGED')
    # Debian's signer may name companion JARs in its manifest. Freeze their actual
    # identities before use and compare after. Only this system Java directory is allowed.
    pending=[Path(actual['apksigner_jar']['resolved_path'])];seen=set()
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path);need(len(seen)<=8,'SIGNER_CLASSPATH_BOUND')
        with zipfile.ZipFile(path) as jar:
            manifest=jar.read('META-INF/MANIFEST.MF').decode('utf-8')
        manifest=re.sub(r'\r?\n ', '', manifest)
        lines=[line[len('Class-Path: '):] for line in manifest.splitlines() if line.startswith('Class-Path: ')]
        need(len(lines)<=1,'SIGNER_CLASSPATH_AMBIGUOUS')
        for name in (lines[0].split() if lines else []):
            need(':' not in name and not name.startswith('//'),'NON_FILE_SIGNER_DEPENDENCY')
            declared=Path(name) if name.startswith('/') else path.parent/name
            resolved=declared.resolve(strict=True)
            need(resolved.parent==Path('/usr/share/java') and resolved.suffix=='.jar',
                'SIGNER_DEPENDENCY_OUT_OF_SYSTEM_DIRECTORY')
            actual['signer_companion_'+resolved.name]=pin(declared,64*1024*1024);pending.append(resolved)
    return actual


def own_resources():
    rows=Path('/proc/self/cgroup').read_text().splitlines()
    prefix='0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'
    need(len(rows)==1 and rows[0].startswith(prefix) and rows[0].endswith('.service'),'OWN_RUNTIME_CGROUP_REQUIRED')
    cg=Path('/sys/fs/cgroup')/rows[0][3:].lstrip('/')
    need(str(os.getpid()) in (cg/'cgroup.procs').read_text().split(),'SELF_CGROUP_REQUIRED')
    return cg


def resources(cg):
    need(own_resources()==cg,'OWN_CGROUP_CHANGED')
    data={'path':str(cg),'affinity':sorted(os.sched_getaffinity(0))}
    for name in [*LIMITS,'memory.current','memory.peak','memory.events','cpu.stat']:
        data[name]=(cg/name).read_text().strip()
    need(all(data[n]==v for n,v in LIMITS.items()) and len(data['affinity'])==1,'RESOURCE_LIMIT_DRIFT')
    return data


def build(expected):
    need(os.getuid()==os.geteuid()==1000,'UNPRIVILEGED_BUILD_UID_REQUIRED')
    need(OUTPUT.parent.resolve()==OUTPUT.parent and not os.path.lexists(OUTPUT),'FRESH_BUILD_ROOT_REQUIRED')
    cg=own_resources();need(int((cg/'memory.current').read_text())<134217728,'OWN_JOB_ALREADY_TOO_LARGE')
    for name,value in LIMITS.items():(cg/name).write_text(value)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10)
    available=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()
        if x.startswith('MemAvailable:'))
    need(available>=805306368,'INSUFFICIENT_BUILD_HEADROOM')
    os.umask(0o077);OUTPUT.mkdir(mode=0o700)
    result={'state':'BUILD_FAILED','package':PACKAGE,'source_manifest_sha256':expected,'commands':[],
        'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'installed':False,
        'ui_actions':0,'own_resources_before':resources(cg),'error':None,
        'whole_app_production_ready':False,'system_native_shared_libraries_fully_frozen':False}
    deadline=time.monotonic()+240
    environment={'PATH':str(JDK/'bin')+':/usr/bin:/bin','JAVA_HOME':str(JDK),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
    def command(name,argv):
        remaining=min(90,deadline-time.monotonic());need(remaining>0,'BUILD_DEADLINE')
        row={'name':name,'argv':argv,'returncode':None,'joined':False,'timed_out':False};result['commands'].append(row)
        process=None
        with (OUTPUT/(name+'.stdout')).open('xb') as out,(OUTPUT/(name+'.stderr')).open('xb') as err:
            try:
                process=subprocess.Popen(argv,cwd=OUTPUT,env=environment,stdout=out,stderr=err,
                    close_fds=True,start_new_session=True)
                row['returncode']=process.wait(timeout=remaining);row['joined']=True
            except BaseException as exc:
                row['timed_out']=isinstance(exc,subprocess.TimeoutExpired)
                if process is not None:
                    if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
                    row['returncode']=process.wait(timeout=5);row['joined']=True
                raise
            finally:
                out.flush();err.flush();os.fsync(out.fileno());os.fsync(err.fileno())
        raw={}
        for stream in ('stdout','stderr'):
            data=(OUTPUT/(name+'.'+stream)).read_bytes();need(len(data)<=1048576,'LOG_BOUND')
            row[stream]={'bytes':len(data),'sha256':sha(data)};raw[stream]=data
        need(row['returncode']==0 and row['joined'],'TOOL_FAILED:'+name)
        return raw['stdout']
    try:
        result['sources_before']=source_pins(expected);result['dependencies_before']=dependencies()
        dep={n:row['resolved_path'] for n,row in result['dependencies_before'].items()}
        for name in ('generated','classes','dex','private-signing'):(OUTPUT/name).mkdir(mode=0o700)
        java=[dep['java'],'-XX:ActiveProcessorCount=1','-XX:+UseSerialGC','-Xmx256m']
        signer=java+['-jar',dep['apksigner_jar']]
        command('aapt-package',[dep['aapt'],'package','-f','-m','-M',str(HERE/'AndroidManifest.xml'),
            '-S',str(HERE/'res'),'-I',dep['android_jar'],'-J',str(OUTPUT/'generated'),'-F',str(OUTPUT/'unsigned.apk')])
        source=HERE/'src'/Path(PACKAGE.replace('.','/'))/'MediaFixture.java'
        generated=list((OUTPUT/'generated').rglob('R.java'));need(len(generated)==1,'ONE_GENERATED_R_REQUIRED')
        command('javac',[dep['javac'],'-J-XX:ActiveProcessorCount=1','-J-XX:+UseSerialGC','-J-Xmx192m',
            '-proc:none','-encoding','UTF-8','-source','8','-target','8','-bootclasspath',dep['android_jar'],
            '-d',str(OUTPUT/'classes'),str(source),str(generated[0])])
        classes=sorted((OUTPUT/'classes').rglob('*.class'));need(1<=len(classes)<=16,'JAVA_CLASS_COUNT_BOUND')
        result['classes']={p.relative_to(OUTPUT/'classes').as_posix():pin(p,262144) for p in classes}
        command('d8',java+['-cp',dep['r8'],'com.android.tools.r8.D8','--lib',dep['android_jar'],
            '--min-api','31','--output',str(OUTPUT/'dex'),*[str(x) for x in classes]])
        need(sorted(x.name for x in (OUTPUT/'dex').iterdir())==['classes.dex'],'SINGLE_DEX_REQUIRED')
        with zipfile.ZipFile(OUTPUT/'unsigned.apk','a',compression=zipfile.ZIP_DEFLATED) as archive:
            need('classes.dex' not in archive.namelist(),'NO_PREEXISTING_DEX')
            archive.write(OUTPUT/'dex/classes.dex','classes.dex')
        command('align',[dep['zipalign'],'-f','4',str(OUTPUT/'unsigned.apk'),str(OUTPUT/'aligned.apk')])
        password=OUTPUT/'private-signing/password.txt';key=OUTPUT/'private-signing/owned.p12'
        write_new(password,(secrets.token_hex(32)+'\n').encode())
        command('create-owned-key',java+['-m','java.base/sun.security.tools.keytool.Main','-genkeypair','-noprompt',
            '-storetype','PKCS12','-keystore',str(key),'-storepass:file',str(password),'-alias','owned-media-r12',
            '-keyalg','RSA','-keysize','3072','-validity','3650','-dname','CN=Pocket4 Owned Media a1d407c8,O=Owned Test,C=US'])
        command('sign',signer+['sign','--ks',str(key),'--ks-pass','file:'+str(password),
            '--ks-key-alias','owned-media-r12','--min-sdk-version','31','--v1-signing-enabled','false',
            '--v2-signing-enabled','true','--v3-signing-enabled','true','--out',str(OUTPUT/'owned-media.apk'),str(OUTPUT/'aligned.apk')])
        signature=command('signature',signer+['verify','--verbose','--print-certs','--min-sdk-version','31',str(OUTPUT/'owned-media.apk')])
        certs=re.findall(rb'^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})\r?$',signature,re.M)
        need(len(certs)==1 and b'Number of signers: 1' in signature and
            b'Verified using v3 scheme (APK Signature Scheme v3): true' in signature,'ONE_VERIFIED_V3_SIGNER_REQUIRED')
        command('alignment',[dep['zipalign'],'-c','4',str(OUTPUT/'owned-media.apk')])
        badge=command('badging',[dep['aapt'],'dump','badging',str(OUTPUT/'owned-media.apk')])
        permissions=command('permissions',[dep['aapt'],'dump','permissions',str(OUTPUT/'owned-media.apk')])
        xml=command('manifest',[dep['aapt'],'dump','xmltree',str(OUTPUT/'owned-media.apk'),'AndroidManifest.xml'])
        need(("package: name='"+PACKAGE+"' versionCode='1'").encode() in badge and
            b"sdkVersion:'31'" in badge and b"targetSdkVersion:'33'" in badge,'APK_IDENTITY_MISMATCH')
        need(b'uses-permission' not in permissions and b'uses-permission' not in xml and
            b'application-debuggable' not in badge and b'launchable-activity' not in badge,'APK_PRIVILEGE_MISMATCH')
        need(len(re.findall(rb'E: instrumentation\s',xml))==1 and all(n not in xml for n in
            (b'E: service ',b'E: receiver ',b'E: provider ',b'E: activity ',b'E: activity-alias ')),
            'EXACT_SINGLE_INSTRUMENTATION_REQUIRED')
        with zipfile.ZipFile(OUTPUT/'owned-media.apk') as archive:
            names=archive.namelist()
            need(len(names)==len(set(names)) and set(names)=={'AndroidManifest.xml','classes.dex','resources.arsc'},
                'APK_MEMBERSHIP_CHANGED')
        result['sources_after']=source_pins(expected);result['dependencies_after']=dependencies()
        need(result['sources_before']==result['sources_after'] and
            result['dependencies_before']==result['dependencies_after'],'BUILD_INPUT_DRIFT')
        result.update(state='BUILT_SIGNED_VERIFIED_UNINSTALLED',apk=pin(OUTPUT/'owned-media.apk',1048576),
            signer_certificate_sha256=certs[0].decode(),permissions=[],launcher=False,instrumentation=True,
            source_and_dependencies_unchanged=True,private_signer_publicly_exported=False)
    except BaseException as exc:result['error']={'type':type(exc).__name__,'message':str(exc)}
    finally:
        result['own_resources_after']=resources(cg)
        result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_new(OUTPUT/'build-result.json',result)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result['state']=='BUILT_SIGNED_VERIFIED_UNINSTALLED' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build-once',action='store_true')
    parser.add_argument('--source-manifest-sha256');args=parser.parse_args()
    if not args.build_once:
        print(json.dumps({'state':'PLAN_ONLY','package':PACKAGE,'output':str(OUTPUT),
            'resource_limits':LIMITS,'android_actions':0,'installs':0}));return 0
    need(bool(re.fullmatch('[0-9a-f]{64}',args.source_manifest_sha256 or '')),'EXTERNAL_SOURCE_PIN_REQUIRED')
    return build(args.source_manifest_sha256)


if __name__=='__main__':raise SystemExit(main())
