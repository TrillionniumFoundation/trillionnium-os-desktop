"""Build one new owned Java-only QA APK. Default prints a plan; never installs."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
PACKAGE = 'org.droidloom.qa.united.r1'
OUTPUT = Path('/home/alex/work/pocket4-owned-united-qa-r1-build-01')
JDK = '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86'
SDK_BASE = '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts'
TOOLS = {
    'java': (JDK + '/bin/java', 'cfa21aeadd00925925c9e1287f5c08f3e04ee7f26a9e23d9dbfb16149153d842'),
    'javac': (JDK + '/bin/javac', '18351d7a271f6b8bd17f9e8fef6bb04baa7cf008cbc8a3a782a93a2f5c48ecfa'),
    'android_jar': (SDK_BASE + '/sdk/31/public/android.jar', '2e71327d66d43cb85a6ac11029376c19067ccc0f15e73c90f2f6777f3be70fb5'),
    'r8': (SDK_BASE + '/cmdline-tools/tools/lib/r8.jar', '33cab360b273b46ad47c3356cf1fb2ac715870fd3eecc55cbd9d508a7f609ce7'),
    'aapt': ('/usr/lib/android-sdk/build-tools/debian/aapt', 'd9c0d90fc4bcf03d57cbf4fe19ca66c80280ac760c53245c8678b9837844b972'),
    'zipalign': (SDK_BASE + '/build-tools/linux-x86/bin/zipalign', 'fd9663d5f0ac858ccbd6a2aa414536dc878266748de2e6afa9a5146c72950758'),
    'apksigner': ('/usr/lib/android-sdk/build-tools/debian/apksigner', '52947059a664b85f0475bcdc3dbbe6089b50f8f59e3aa051e6e74cf0ba7db70f'),
}
R21_INPUT_RECEIPT_SHA = '2a8cb152f9dea378ffc180c95ee4cbab1eb2b527c0dc9e176fd89bcee46119c6'
ATTR = '{http://schemas.android.com/apk/res/android}'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(info):
    return tuple(getattr(info, key) for key in ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns'))


def file_pin(path, maximum=256 * 1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum, 'bounded regular input required: ' + str(path))
        hasher = hashlib.sha256(); size = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            size += len(chunk); require(size <= maximum, 'input grew'); hasher.update(chunk)
        require(size == before.st_size and metadata(before) == metadata(os.fstat(fd)), 'input changed during hash')
        return {'path': str(path), 'bytes': size, 'sha256': hasher.hexdigest()}
    finally:
        os.close(fd)


def source_contract(expected):
    require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'external source manifest pin required')
    raw = (HERE / 'SOURCE_PINS.json').read_bytes()
    require(len(raw) <= 131072 and digest(raw) == expected, 'source manifest changed')
    manifest = json.loads(raw); files = manifest['files']
    require(isinstance(files, dict) and 4 <= len(files) <= 32, 'source set bound')
    for name, row in files.items():
        path = Path(name)
        require(not path.is_absolute() and '..' not in path.parts and path.as_posix() == name, 'source relative path')
        actual = file_pin(HERE / name, 1024 * 1024)
        require(actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes'], 'source differs: ' + name)
    require({'AndroidManifest.xml', 'src/org/droidloom/qa/united/r1/ActionRunner.java', 'qa_contract.py', 'build_candidate.py'} <= set(files), 'required sources missing')
    return files


def manifest_contract():
    manifest = ET.fromstring((HERE / 'AndroidManifest.xml').read_bytes())
    require(manifest.tag == 'manifest' and manifest.attrib == {'package':PACKAGE,
            ATTR+'versionCode':'2', ATTR+'versionName':'2'}, 'manifest package/version')
    require([x.tag for x in manifest] == ['uses-sdk','queries','application','instrumentation'], 'unexpected manifest component or permission')
    sdk, queries, application, instrument = list(manifest)
    require(sdk.attrib == {ATTR+'minSdkVersion':'31', ATTR+'targetSdkVersion':'33'}, 'sdk contract')
    require(len(queries) == 1 and queries[0].tag == 'package' and queries[0].attrib == {ATTR+'name':'com.united.mobile.android'}, 'package visibility scope')
    require(len(application) == 0 and application.attrib == {
        ATTR+'label':'Owned United QA', ATTR+'debuggable':'false', ATTR+'testOnly':'true',
        ATTR+'allowBackup':'false', ATTR+'hasCode':'true'}, 'application privileges or components changed')
    require(instrument.attrib == {ATTR+'name':PACKAGE+'.ActionRunner', ATTR+'targetPackage':PACKAGE,
        ATTR+'functionalTest':'true', ATTR+'handleProfiling':'false'}, 'self instrumentation required')
    return {'package': PACKAGE, 'instrumentation': PACKAGE+'.ActionRunner', 'target_package': PACKAGE,
            'compile_sdk_api':31, 'min_sdk':31, 'target_sdk':33, 'debuggable':False, 'test_only':True, 'permissions':[],
            'activities':[], 'services':[], 'receivers':[], 'providers':[], 'native_libraries':[]}


def write_new(path, data, mode=0o600):
    raw = data if isinstance(data, bytes) else (json.dumps(data, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def run_command(output, environment, rows, name, argv, timeout=60):
    """Retain the first failure and close both logs after joining our child."""
    stdout, stderr = output/(name+'.stdout'), output/(name+'.stderr')
    primary = None; process = None; joined = True; rc = None; secondary_errors = []; streams = []

    def remember(phase, error):
        nonlocal primary
        record = {'phase':phase, 'type':type(error).__name__, 'message':str(error)}
        if primary is None:
            primary = error
        else:
            secondary_errors.append(record)

    try:
        out = stdout.open('xb'); streams.append(out)
        err = stderr.open('xb'); streams.append(err)
        process = subprocess.Popen(argv, cwd=output, env=environment, stdout=out, stderr=err,
                                   close_fds=True, start_new_session=True)
        joined = False; rc = process.wait(timeout=timeout); joined = True
        require(rc == 0, 'tool failed: '+name+' returncode='+str(rc))
    except BaseException as error:
        remember('command_open_spawn_or_wait', error)
        if process is not None and not joined:
            try:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
            except BaseException as secondary:
                remember('owned_command_group_stop', secondary)
            try:
                rc = process.wait(timeout=5); joined = True
            except BaseException as secondary:
                remember('owned_command_join', secondary)
    finally:
        for stream in streams:
            try:
                stream.flush(); os.fsync(stream.fileno())
            except BaseException as secondary:
                remember('output_sync', secondary)
            try:
                stream.close()
            except BaseException as secondary:
                remember('output_close', secondary)
    observed = {}
    for label, path in (('stdout', stdout), ('stderr', stderr)):
        try:
            require(path.stat().st_size <= 1048576, 'bounded tool output exceeded: '+label)
            observed[label] = path.read_bytes()
        except BaseException as secondary:
            observed[label] = b''
            remember('output_read_'+label, secondary)
    rows.append({'name':name, 'argv':argv, 'returncode':rc, 'owned_child_joined':joined,
                 'stdout_sha256':digest(observed['stdout']), 'stderr_sha256':digest(observed['stderr']),
                 'error':None if primary is None else {'type':type(primary).__name__, 'message':str(primary)},
                 'secondary_errors':secondary_errors})
    if primary is not None:
        raise primary
    require(joined and rc == 0, 'tool completion unverified: '+name)
    return observed['stdout']


def build_once(expected):
    source = source_contract(expected); contract = manifest_contract()
    # Debian tool names may be package-managed symlinks. Resolve each known
    # name once, hash the regular target, and recheck that mapping after the
    # build. Execute the declared pinned name to preserve script $0/relative-JAR
    # behavior of the existing packaged tools. Source files do not use this.
    resolved = {label: str(Path(path).resolve(strict=True)) for label, (path, _) in TOOLS.items()}
    tool_before = {label: {**file_pin(resolved[label]), 'declared_path': path}
                   for label, (path, wanted) in TOOLS.items()}
    for label, (_, wanted) in TOOLS.items():
        require(tool_before[label]['sha256'] == wanted, 'tool pin changed: ' + label)
    require(os.getuid() == os.geteuid() == 1000, 'unprivileged build operator required')
    require(OUTPUT.parent == Path('/home/alex/work') and OUTPUT.parent.resolve() == OUTPUT.parent, 'fixed output parent')
    os.umask(0o077); OUTPUT.mkdir(mode=0o700)
    write_new(OUTPUT/'once.claim.json', {'source_manifest_sha256':expected, 'automatic_retry':False, 'package':PACKAGE})
    result = {'schema':1, 'state':'BUILD_FAILED', 'package':PACKAGE, 'source_manifest_sha256':expected,
              'source_sha256':{k:v['sha256'] for k,v in source.items()}, 'tools_before':tool_before,
              'tools_baseline_receipt_sha256':R21_INPUT_RECEIPT_SHA, 'commands':[], 'error':None,
              'android_installed':False, 'Android_UI_actions':0, 'Main_mutations':0,
              'source_or_permissions_gate_relaxed':False, 'whole_app_production_ready':False}
    env = {'PATH':JDK+'/bin:/usr/bin:/bin', 'LANG':'C', 'LC_ALL':'C', 'JAVA_HOME':JDK}
    tool = {name: value[0] for name, value in TOOLS.items()}
    java = [tool['java'], '-XX:ActiveProcessorCount=1', '-XX:+UseSerialGC', '-Xmx256m']
    deadline = time.monotonic() + 230

    def command(name, argv, timeout=60):
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'owned build deadline before '+name)
        return run_command(OUTPUT, env, result['commands'], name, argv, min(timeout, remaining))

    try:
        for name in ('classes','dex','res','private-signing'):
            (OUTPUT/name).mkdir(mode=0o700)
        baseline_scope={'__file__':str(HERE/'check_current_baseline.py'),'__name__':'owned_current_baseline_scope_controls'}
        exec(compile((HERE/'check_current_baseline.py').read_bytes(),str(HERE/'check_current_baseline.py'),'exec'),baseline_scope)
        baseline_controls=baseline_scope['run_controls']()
        require(baseline_controls['all_passed'] is True and baseline_controls['count']==32 and
                len(baseline_controls['cases'])==32 and all(x['passed'] is True for x in baseline_controls['cases']) and
                baseline_controls['production_contract_sha256']==source['qa_contract.py']['sha256'] and
                baseline_controls['production_adapter_sha256']==source['qa_adapter.py']['sha256'] and
                baseline_controls['host_recorder_manifest_sha256']=='002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff' and
                baseline_controls['main_epoch_sha256']=='7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c' and
                baseline_controls['main_baseline_schema']=='pocket4-main-current-baseline-v2' and
                baseline_controls['main_baseline_sha256']=='633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364' and
                baseline_controls['main_baseline_qualification_sha256']=='ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e',
                'ACTUAL_CURRENT_BASELINE_SCOPE_CONTROLS_REQUIRED')
        result['current_baseline_scope_controls']={'source_sha256':source['check_current_baseline.py']['sha256'],'report':baseline_controls}
        source_java = HERE/'src/org/droidloom/qa/united/r1/ActionRunner.java'
        command('javac', [tool['javac'], '-J-XX:ActiveProcessorCount=1', '-J-XX:+UseSerialGC', '-J-Xmx256m',
            '-proc:none','-Xmaxerrs','20','-Xmaxwarns','20','-source','8','-target','8','-bootclasspath',resolved['android_jar'],
            '-d',str(OUTPUT/'classes'),str(source_java)])
        controls = json.loads(command('deep-tree-contract',
            [sys.executable, '-I', '-B', str(HERE/'controls/check_deep_tree.py')], 20))
        require(controls.get('state') == 'PASS_PROTOCOL_CONTROLS_ONLY' and
                controls.get('cases') == 16 and controls.get('max_depth') == 128 and
                controls.get('Java_scanner_executed') is False and controls.get('Android_actions') == 0,
                'actual complete-tree protocol controls did not finish')
        result['deep_tree_protocol_controls'] = controls
        classes = sorted((OUTPUT/'classes').rglob('*.class'))
        require(1 <= len(classes) <= 32 and all(x.is_file() and x.stat().st_size <= 262144 for x in classes), 'class output bound')
        command('d8', java+['-cp',resolved['r8'],'com.android.tools.r8.D8','--lib',resolved['android_jar'],
            '--min-api','31','--output',str(OUTPUT/'dex'),*[str(x) for x in classes]])
        require(sorted(x.name for x in (OUTPUT/'dex').iterdir()) == ['classes.dex'], 'single DEX required')
        require((OUTPUT/'dex/classes.dex').stat().st_size <= 1048576, 'DEX bound')
        command('aapt-package', [tool['aapt'],'package','-f','-M',str(HERE/'AndroidManifest.xml'),
            '-S',str(OUTPUT/'res'),'-I',resolved['android_jar'],'-F',str(OUTPUT/'unsigned.apk')])
        with zipfile.ZipFile(OUTPUT/'unsigned.apk', 'a', compression=zipfile.ZIP_DEFLATED) as archive:
            require('classes.dex' not in archive.namelist(), 'unexpected preexisting DEX')
            archive.write(OUTPUT/'dex/classes.dex', 'classes.dex')
        command('align', [tool['zipalign'],'-f','4',str(OUTPUT/'unsigned.apk'),str(OUTPUT/'aligned.apk')])
        password = OUTPUT/'private-signing/password.txt'; store = OUTPUT/'private-signing/owned.p12'
        write_new(password, (secrets.token_hex(32)+'\n').encode())
        # The standard JDK keytool implementation is launched by the already
        # pinned Java runtime. No platform/commercial signing key is consumed.
        command('create-owned-signing-key', java+['-m','java.base/sun.security.tools.keytool.Main',
            '-genkeypair','-noprompt','-storetype','PKCS12','-keystore',str(store),'-storepass:file',str(password),
            '-alias','owned-united-qa-r1','-keyalg','RSA','-keysize','3072','-validity','3650',
            '-dname','CN=Pocket4 Owned United QA R1,O=Owned Test,C=US'])
        command('sign', [tool['apksigner'],'sign','--ks',str(store),'--ks-pass','file:'+str(password),
            '--ks-key-alias','owned-united-qa-r1','--min-sdk-version','31','--v1-signing-enabled','false',
            '--v2-signing-enabled','true','--v3-signing-enabled','true','--out',str(OUTPUT/'owned-united-qa.apk'),
            str(OUTPUT/'aligned.apk')])
        signature = command('signature', [tool['apksigner'],'verify','--verbose','--print-certs','--min-sdk-version','31',str(OUTPUT/'owned-united-qa.apk')])
        certs = re.findall(rb'^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})\r?$', signature, re.M)
        require(len(certs) == 1 and b'Number of signers: 1' in signature, 'one verified owned signer required')
        command('alignment', [tool['zipalign'],'-c','4',str(OUTPUT/'owned-united-qa.apk')])
        badging = command('badging', [tool['aapt'],'dump','badging',str(OUTPUT/'owned-united-qa.apk')])
        permissions = command('permissions', [tool['aapt'],'dump','permissions',str(OUTPUT/'owned-united-qa.apk')])
        xml = command('manifest', [tool['aapt'],'dump','xmltree',str(OUTPUT/'owned-united-qa.apk'),'AndroidManifest.xml'])
        require(b"package: name='org.droidloom.qa.united.r1' versionCode='2'" in badging and
                b"sdkVersion:'31'" in badging and b"targetSdkVersion:'33'" in badging, 'actual APK package/SDK differs')
        require(b'uses-permission' not in permissions and b'uses-permission' not in xml and
                b'application-debuggable' not in badging and b'launchable-activity' not in badging, 'actual APK privilege/component differs')
        for forbidden in (b'E: activity ',b'E: activity-alias ',b'E: service ',b'E: receiver ',b'E: provider '):
            require(forbidden not in xml, 'unexpected actual APK component')
        require(re.search(rb'A: android:targetPackage\([^\n]*="' + re.escape(PACKAGE.encode()) + rb'"',xml) is not None,
                'actual self instrumentation target required')
        require(len(re.findall(rb'E: instrumentation(?:\s|$)',xml)) == 1 and
                len(re.findall(rb'A: android:name\([^\n]*="' + re.escape(PACKAGE.encode()) + rb'\.ActionRunner"',xml)) == 1,
                'one exact actual instrumentation component required')
        require(re.search(rb'A: android:testOnly\([^\n]*=\(type 0x12\)0xffffffff',xml) is not None and
                re.search(rb'A: android:debuggable\([^\n]*=\(type 0x12\)0x0\b',xml) is not None,
                'actual testOnly/nondebug flags required')
        with zipfile.ZipFile(OUTPUT/'owned-united-qa.apk') as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)) and set(names) <= {'AndroidManifest.xml','classes.dex','resources.arsc'}, 'APK members changed')
            require(archive.read('classes.dex') == (OUTPUT/'dex/classes.dex').read_bytes(), 'APK DEX differs')
        require(source_contract(expected) == source, 'source changed during build')
        require({label: str(Path(path).resolve(strict=True)) for label,(path,_) in TOOLS.items()} == resolved,
                'tool name-to-target mapping changed during build')
        tool_after = {label:{**file_pin(resolved[label]), 'declared_path':path} for label,(path,_) in TOOLS.items()}
        require(tool_after == tool_before, 'tool inputs changed during build')
        result.update(state='BUILT_STATIC_VERIFIED_ANDROID_UNRUN', APK=file_pin(OUTPUT/'owned-united-qa.apk', 2097152),
                      signer_certificate_sha256=certs[0].decode(), manifest_contract=contract,
                      source_unchanged=True, tools_unchanged=True, tools_after=tool_after,
                      private_signing_material_not_public=['private-signing/password.txt','private-signing/owned.p12'])
    except BaseException as error:
        result['error'] = {'type':type(error).__name__,'message':str(error),'notes':getattr(error,'__notes__',[])}
    finally:
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_new(OUTPUT/'build-result.json', result)
    print(json.dumps({'state':result['state'],'result':str(OUTPUT/'build-result.json'),
                      'result_sha256':digest((OUTPUT/'build-result.json').read_bytes()),'Android_actions':0}))
    return 0 if result['state'] == 'BUILT_STATIC_VERIFIED_ANDROID_UNRUN' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-once', action='store_true')
    parser.add_argument('--source-manifest-sha256')
    args = parser.parse_args()
    if not args.build_once:
        print(json.dumps({'state':'PLAN_ONLY','package':PACKAGE,'output':str(OUTPUT),
              'tools':TOOLS,'tool_baseline_receipt_sha256':R21_INPUT_RECEIPT_SHA,
              'compile_sdk_api':31,'min_sdk':31,'target_sdk':33,
              'new_private_owned_signer':True,'install_or_Android_actions':0,'UI_admitted':False}))
        return 0
    return build_once(args.source_manifest_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
