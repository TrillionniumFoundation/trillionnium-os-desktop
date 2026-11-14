"""Unprivileged owned-helper compiler children under the verified host reaper.

Call build(common, source_ref, output) only for actual generated final-Main
sources. Root observes/records; all compiler, signing and inspection commands
run as UID 1000. No install or Android command exists in this module.
"""
import hashlib
import os
from pathlib import Path
import re
import secrets
import stat
import time
import xml.etree.ElementTree as ET
import zipfile

PACKAGE = 'org.droidloom.qa.ihg.finalmain.r1'
JDK = '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86'
SDK_BASE = '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts'
TOOLS = {
    'java': (JDK + '/bin/java', 'cfa21aeadd00925925c9e1287f5c08f3e04ee7f26a9e23d9dbfb16149153d842'),
    'javac': (JDK + '/bin/javac', '18351d7a271f6b8bd17f9e8fef6bb04baa7cf008cbc8a3a782a93a2f5c48ecfa'),
    'android_jar': (SDK_BASE + '/sdk/31/public/android.jar', '2e71327d66d43cb85a6ac11029376c19067ccc0f15e73c90f2f6777f3be70fb5'),
    'r8': (SDK_BASE + '/cmdline-tools/tools/lib/r8.jar', '33cab360b273b46ad47c3356cf1fb2ac715870fd3eecc55cbd9d508a7f609ce7'),
    'aapt': ('/usr/lib/android-sdk/build-tools/debian/aapt', 'd9c0d90fc4bcf03d57cbf4fe19ca66c80280ac760c53245c8678b9837844b972'),
    'zipalign': (SDK_BASE + '/build-tools/linux-x86/bin/zipalign', 'fd9663d5f0ac858ccbd6a2aa414536dc878266748de2e6afa9a5146c72950758'),
    'apksigner': ('/usr/lib/android-sdk/build-tools/debian/apksigner', '52947059a664b85f0475bcdc3dbbe6089b50f8f59e3aa051e6e74cf0ba7db70f')}
BUILD_COMMANDS = ['javac', 'd8', 'aapt-package', 'align', 'create-owned-signing-key', 'sign',
                  'signature', 'alignment', 'badging', 'permissions', 'manifest']
ATTR = '{http://schemas.android.com/apk/res/android}'


def manifest_contract(common, raw):
    require = common.need; manifest = ET.fromstring(raw)
    require(manifest.tag == 'manifest' and manifest.attrib == {'package': PACKAGE,
        ATTR + 'versionCode': '1', ATTR + 'versionName': '1'}, 'MANIFEST_PACKAGE_VERSION_CHANGED')
    require([x.tag for x in manifest] == ['uses-sdk', 'queries', 'application', 'instrumentation'],
            'UNEXPECTED_MANIFEST_COMPONENT_OR_PERMISSION')
    sdk, queries, application, instrument = list(manifest)
    require(sdk.attrib == {ATTR + 'minSdkVersion': '31', ATTR + 'targetSdkVersion': '33'}, 'SDK_CONTRACT_CHANGED')
    require(len(queries) == 1 and queries[0].tag == 'package' and
            queries[0].attrib == {ATTR + 'name': 'com.ihg.apps.android'}, 'PACKAGE_VISIBILITY_SCOPE_CHANGED')
    require(len(application) == 0 and application.attrib == {ATTR + 'label': 'Owned IHG QA',
        ATTR + 'debuggable': 'false', ATTR + 'testOnly': 'true', ATTR + 'allowBackup': 'false',
        ATTR + 'hasCode': 'true'}, 'APPLICATION_PRIVILEGES_OR_COMPONENTS_CHANGED')
    require(instrument.attrib == {ATTR + 'name': PACKAGE + '.ActionRunner', ATTR + 'targetPackage': PACKAGE,
        ATTR + 'functionalTest': 'true', ATTR + 'handleProfiling': 'false'}, 'SELF_INSTRUMENTATION_REQUIRED')
    return {'package': PACKAGE, 'instrumentation': PACKAGE + '.ActionRunner', 'target_package': PACKAGE,
        'compile_sdk_api': 31, 'min_sdk': 31, 'target_sdk': 33, 'debuggable': False, 'test_only': True,
        'permissions': [], 'activities': [], 'services': [], 'receivers': [], 'providers': [], 'native_libraries': []}


def tool_file(common, path):
    declared = Path(path); actual = declared.resolve(strict=True)
    fd = os.open(actual, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd); common.need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 256 * 1024 * 1024,
                                          'BOUNDED_ORIGINAL_TOOL_FILE_REQUIRED')
        h = hashlib.sha256(); count = 0
        while True:
            data = os.read(fd, 65536)
            if not data:
                break
            count += len(data); common.need(count <= 256 * 1024 * 1024, 'TOOL_FILE_GREW')
            h.update(data)
        common.need(count == before.st_size and common.metadata(before) == common.metadata(os.fstat(fd))
                    and declared.resolve(strict=True) == actual, 'TOOL_CHANGED_DURING_READ')
        return {'path': str(actual), 'declared_path': path, 'bytes': count, 'sha256': h.hexdigest()}
    finally:
        os.close(fd)


def verify_source(common, source_ref):
    source = common.parse(common.read_ref(source_ref))
    common.need(source['schema'] == 'pocket4-final-ihg-helper-source-v1' and
        source['state'] == 'SOURCE_GENERATED_ANDROID_UNRUN' and source['package'] == PACKAGE and
        source['target_package'] == 'com.ihg.apps.android' and source['target_uid'] == 10137 and
        source['old_runtime_authority_transferred'] is False and source['APK'] is None and source['installed_UID'] is None,
        'ACTUAL_SEPARATE_GENERATED_HELPER_SOURCE_REQUIRED')
    for ref in source['files'].values():
        common.read_ref(ref)
    packet = common.parse(common.read_ref(source['source_packet']))
    common.need(packet['schema'] == 'pocket4-final-app-preparation-source-v1'
        and packet['code_entrypoints_complete'] is True and packet['Android_execution_authorized_by_publication'] is False,
        'COMPLETE_ACTUAL_PREPARATION_PACKET_REQUIRED')
    copied = ('ihg_helper_build.py', 'ihg_helper_controls.py', 'ihg_session.py', 'app_runtime.py',
              'ihg_check_baseline.py', 'ihg_check_input.py')
    common.need(set(source['files']) == set(copied) | {'qa_contract.py', 'ActionRunner.java', 'AndroidManifest.xml'},
                'EXACT_GENERATED_HELPER_FILE_SET_REQUIRED')
    for name in copied:
        rows = [r for r in packet['files'] if Path(r['path']).name == name]
        row = source['files'][name]
        common.need(len(rows) == 1 and row['bytes'] == rows[0]['bytes'] and row['sha256'] == rows[0]['sha256']
            and Path(row['path']) == Path(source_ref['path']).parent / name, 'EXACT_FROZEN_HELPER_SUPPORT_COPY_REQUIRED')
        common.read_ref(rows[0])
    factory_ref = [r for r in packet['files'] if Path(r['path']).name == 'ihg_helper_factory.py']
    common.need(len(factory_ref) == 1, 'EXACT_REVIEWED_HELPER_FACTORY_REQUIRED')
    factory = common.module(factory_ref[0], 'actual_final_helper_factory')
    _, modules = common.support()
    baseline = modules['business_baseline.py'].BusinessBaseline(source['baseline'], source['qualification'])
    originals = {}
    for name, (size, digest) in factory.ORIGINALS.items():
        rel = 'src/org/droidloom/qa/ihg/r4/ActionRunner.java' if name == 'ActionRunner.java' else name
        originals[name] = common.read_ref({'path': factory.ORIGINAL_ROOT + '/' + rel, 'bytes': size, 'sha256': digest})
    rendered, changes = factory.render(originals, factory.actual_values(baseline))
    common.need(changes == source['declared_transformations'] and all(
        common.read_ref(source['files'][k]) == value for k, value in rendered.items()),
        'GENERATED_HELPER_DIFFERS_FROM_ACTUAL_MAIN_AND_ORIGINAL_BODY')
    common.need(source['framework_epoch_sha256'] == baseline.value['framework_epoch']['sha256'],
                'GENERATED_HELPER_MAIN_EPOCH_CHANGED')
    baseline.guard()
    return source, baseline, modules


def build(common, source_ref, output):
    common.need(os.getuid() == os.geteuid() == 0, 'ROOT_OBSERVER_REQUIRED')
    source, baseline, modules = verify_source(common, source_ref)
    contract = manifest_contract(common, common.read_ref(source['files']['AndroidManifest.xml']))
    root = Path(output)
    common.need(root.parent == Path('/home/alex/work') and root.parent.resolve() == root.parent and
                re.fullmatch(r'pocket4-final-ihg-helper-build-[0-9a-f]{32}', root.name), 'NEW_PRIVATE_BUILD_ROOT_REQUIRED')
    pins = {name: tool_file(common, path) for name, (path, _) in TOOLS.items()}
    common.need(all(pins[name]['sha256'] == digest for name, (_, digest) in TOOLS.items()), 'ORIGINAL_BUILD_TOOL_PIN_CHANGED')
    os.umask(0o077); root.mkdir(mode=0o700); os.chown(root, 1000, 1000)
    # Compiler work remains UID 1000; the qualified host recorder requires its
    # own root-private evidence directory rather than the compiler-owned root.
    journal = common.private_dir(root / 'observer', create=True)
    common.write_new(root / 'once.claim.json', {'source': source_ref, 'automatic_retry': False, 'package': PACKAGE})
    result = {'schema': 'pocket4-final-ihg-helper-build-v1', 'state': 'BUILD_FAILED', 'source': source_ref,
        'package': PACKAGE, 'commands': [], 'tools_before': pins, 'error': None,
        'android_installed': False, 'Android_UI_actions': 0, 'Main_mutations': 0,
        'whole_app_business_accepted': False, 'automatic_retry': False,
        'compiler_and_signing_UID': 1000, 'host_tree_retirement_is_not_Binder_cleanup': True}
    deadline = time.monotonic() + 230
    runtime = common.module(source['files']['app_runtime.py'], 'actual_helper_build_deadline')
    import types
    commands = runtime.PhaseCommands(modules['business_commands.py'], types.SimpleNamespace(c=common, deadline=deadline))
    environment = {'PATH': JDK + '/bin:/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'JAVA_HOME': JDK}
    tool = {k: v[0] for k, v in TOOLS.items()}; java = [tool['java'], '-XX:ActiveProcessorCount=1', '-XX:+UseSerialGC', '-Xmx256m']
    def guard(*, action_attempted=False):
        common.read_ref(source_ref)
        for ref in source['files'].values():
            common.read_ref(ref)
        return baseline.guard(action_attempted=False)
    def command(name, argv, timeout=60):
        common.need(name == BUILD_COMMANDS[len(result['commands'])], 'ORIGINAL_BUILD_COMMAND_ORDER_REQUIRED')
        remaining = deadline - time.monotonic(); common.need(remaining > 0, 'ORIGINAL_BUILD_DEADLINE')
        actual = ['/usr/bin/sudo', '-n', '-u', '#1000', '--', '/usr/bin/env', '-i'] + [
            k + '=' + environment[k] for k in sorted(environment)] + list(argv)
        value = commands.run_recorded(name, actual, timeout, journal, guard,
            protected_pids=baseline.protected_pids, host_env=common.HOST_ENV)
        result['commands'].append({'name': name, 'logical_argv': list(argv),
            'result': common.regular(journal / (name + '.result.json'), contents=False)})
        return value.stdout
    def owned_file(path, raw):
        ref = common.write_new(path, raw); os.chown(path, 1000, 1000)
        return ref
    try:
        result['Main_before'] = guard()
        controls = common.module(source['files']['ihg_helper_controls.py'], 'actual_generated_helper_controls')
        control_result = controls.run_controls(common, source)
        common.need(control_result['all_passed'] is True, 'ACTUAL_GENERATED_PROTOCOL_CONTROLS_REQUIRED')
        result['protocol_controls'] = common.write_new(root / 'protocol-controls.json', control_result)
        for name in ('classes', 'dex', 'res', 'private-signing', 'source'):
            (root / name).mkdir(mode=0o700); os.chown(root / name, 1000, 1000)
        for name in ('ActionRunner.java', 'AndroidManifest.xml'):
            owned_file(root / 'source' / name, common.read_ref(source['files'][name]))
        command('javac', [tool['javac'], '-J-XX:ActiveProcessorCount=1', '-J-XX:+UseSerialGC', '-J-Xmx256m',
            '-proc:none', '-Xmaxerrs', '20', '-Xmaxwarns', '20', '-source', '8', '-target', '8',
            '-bootclasspath', pins['android_jar']['path'], '-d', str(root / 'classes'), str(root / 'source/ActionRunner.java')])
        classes = sorted((root / 'classes').rglob('*.class'))
        common.need(1 <= len(classes) <= 32 and all(p.is_file() and p.stat().st_size <= 262144 for p in classes), 'CLASS_OUTPUT_BOUND')
        command('d8', java + ['-cp', pins['r8']['path'], 'com.android.tools.r8.D8', '--lib', pins['android_jar']['path'],
            '--min-api', '31', '--output', str(root / 'dex'), *[str(p) for p in classes]])
        common.need(sorted(p.name for p in (root / 'dex').iterdir()) == ['classes.dex'] and
                    (root / 'dex/classes.dex').stat().st_size <= 1048576, 'SINGLE_BOUNDED_DEX_REQUIRED')
        command('aapt-package', [tool['aapt'], 'package', '-f', '-M', str(root / 'source/AndroidManifest.xml'),
            '-S', str(root / 'res'), '-I', pins['android_jar']['path'], '-F', str(root / 'unsigned.apk')])
        with zipfile.ZipFile(root / 'unsigned.apk', 'a', compression=zipfile.ZIP_DEFLATED) as archive:
            common.need('classes.dex' not in archive.namelist(), 'UNEXPECTED_PREEXISTING_DEX')
            archive.write(root / 'dex/classes.dex', 'classes.dex')
        command('align', [tool['zipalign'], '-f', '4', str(root / 'unsigned.apk'), str(root / 'aligned.apk')])
        password = root / 'private-signing/password.txt'; key = root / 'private-signing/owned.p12'
        owned_file(password, (secrets.token_hex(32) + '\n').encode())
        command('create-owned-signing-key', java + ['-m', 'java.base/sun.security.tools.keytool.Main', '-genkeypair', '-noprompt',
            '-storetype', 'PKCS12', '-keystore', str(key), '-storepass:file', str(password), '-alias', 'owned-ihg-final-main',
            '-keyalg', 'RSA', '-keysize', '3072', '-validity', '3650', '-dname', 'CN=Pocket4 Owned IHG Final Main,O=Owned Test,C=US'])
        apk = root / 'owned-ihg-qa.apk'
        command('sign', [tool['apksigner'], 'sign', '--ks', str(key), '--ks-pass', 'file:' + str(password), '--ks-key-alias',
            'owned-ihg-final-main', '--min-sdk-version', '31', '--v1-signing-enabled', 'false', '--v2-signing-enabled', 'true',
            '--v3-signing-enabled', 'true', '--out', str(apk), str(root / 'aligned.apk')])
        signature = command('signature', [tool['apksigner'], 'verify', '--verbose', '--print-certs', '--min-sdk-version', '31', str(apk)])
        certs = re.findall(rb'^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})\r?$', signature, re.M)
        common.need(len(certs) == 1 and b'Number of signers: 1' in signature and
            b'Verified using v3 scheme (APK Signature Scheme v3): true' in signature, 'ONE_ACTUAL_V3_OWNED_SIGNER_REQUIRED')
        command('alignment', [tool['zipalign'], '-c', '4', str(apk)])
        badging = command('badging', [tool['aapt'], 'dump', 'badging', str(apk)])
        permissions = command('permissions', [tool['aapt'], 'dump', 'permissions', str(apk)])
        xml = command('manifest', [tool['aapt'], 'dump', 'xmltree', str(apk), 'AndroidManifest.xml'])
        common.need(("package: name='" + PACKAGE + "' versionCode='1'").encode() in badging and
            b"sdkVersion:'31'" in badging and b"targetSdkVersion:'33'" in badging, 'ACTUAL_APK_PACKAGE_SDK_CHANGED')
        common.need(b'uses-permission' not in permissions and b'uses-permission' not in xml and
            b'application-debuggable' not in badging and b'launchable-activity' not in badging, 'ACTUAL_APK_PRIVILEGE_CHANGED')
        common.need(all(x not in xml for x in (b'E: activity ', b'E: activity-alias ', b'E: service ', b'E: receiver ', b'E: provider ')),
                    'UNEXPECTED_ACTUAL_APK_COMPONENT')
        common.need(re.search(rb'A: android:targetPackage\([^\n]*="' + re.escape(PACKAGE.encode()) + rb'"', xml) is not None and
            len(re.findall(rb'E: instrumentation(?:\s|$)', xml)) == 1 and
            len(re.findall(rb'A: android:name\([^\n]*="' + re.escape(PACKAGE.encode()) + rb'\.ActionRunner"', xml)) == 1,
            'ONE_EXACT_ACTUAL_SELF_INSTRUMENTATION_REQUIRED')
        common.need(re.search(rb'A: android:testOnly\([^\n]*=\(type 0x12\)0xffffffff', xml) is not None and
            re.search(rb'A: android:debuggable\([^\n]*=\(type 0x12\)0x0\b', xml) is not None, 'ACTUAL_TEST_ONLY_NONDEBUG_FLAGS_REQUIRED')
        with zipfile.ZipFile(apk) as archive:
            names = archive.namelist()
            common.need(len(names) == len(set(names)) and set(names) <= {'AndroidManifest.xml', 'classes.dex', 'resources.arsc'} and
                archive.read('classes.dex') == (root / 'dex/classes.dex').read_bytes(), 'ACTUAL_APK_CONTENTS_CHANGED')
        common.need(all(common.read_ref(source['files'][name]) == (root / 'source' / name).read_bytes()
                        for name in ('ActionRunner.java', 'AndroidManifest.xml')), 'COMPILER_INPUT_COPY_CHANGED')
        result['tools_after'] = {name: tool_file(common, path) for name, (path, _) in TOOLS.items()}
        common.need(result['tools_after'] == pins, 'BUILD_TOOLS_CHANGED')
        result['Main_after'] = guard(); common.need(result['Main_before'] == result['Main_after'], 'MAIN_CHANGED_DURING_HELPER_BUILD')
        result.update(state='BUILT_STATIC_VERIFIED_ANDROID_UNRUN', APK=common.regular(apk, 2097152, contents=False),
            signer_certificate_sha256=certs[0].decode(), manifest_contract=contract, source_unchanged=True, tools_unchanged=True)
    except BaseException as error:
        result['state'] = 'UNKNOWN' if getattr(error, 'command_observation', {}).get('host_retirement_proved') is False else 'BUILD_FAILED'
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'notes': getattr(error, '__notes__', [])}
        raise
    finally:
        common.write_new(root / 'build-result.json', result)
    return common.regular(root / 'build-result.json', contents=False)


def verify_build(common, build_ref):
    """Verify the actual compiled artifact and recorded compiler/signature chain."""
    value = common.parse(common.read_ref(build_ref)); source, baseline, modules = verify_source(common, value['source'])
    common.need(value['schema'] == 'pocket4-final-ihg-helper-build-v1' and
        value['state'] == 'BUILT_STATIC_VERIFIED_ANDROID_UNRUN' and value['package'] == PACKAGE and
        value['error'] is None and value['android_installed'] is False and
        value['Android_UI_actions'] == value['Main_mutations'] == 0 and
        value['source_unchanged'] is True and value['tools_unchanged'] is True and
        value['tools_before'] == value['tools_after'] and value['compiler_and_signing_UID'] == 1000 and
        value['Main_before'] == value['Main_after'] and
        value['manifest_contract'] == manifest_contract(common, common.read_ref(source['files']['AndroidManifest.xml'])),
        'COMPLETED_ACTUAL_NEW_HELPER_BUILD_REQUIRED')
    common.need(set(value['tools_before']) == set(TOOLS), 'ORIGINAL_BUILD_TOOL_SET_CHANGED')
    for name, (path, digest) in TOOLS.items():
        common.need(value['tools_before'][name]['declared_path'] == path and
                    value['tools_before'][name]['sha256'] == digest, 'ACTUAL_BUILD_TOOL_PIN_CHANGED')
    common.need([r['name'] for r in value['commands']] == BUILD_COMMANDS, 'EXACT_ACTUAL_BUILD_COMMAND_SET_REQUIRED')
    root = Path(build_ref['path']).parent
    for item in value['commands']:
        row = common.parse(common.read_ref(item['result']))
        common.need(Path(item['result']['path']) == root / 'observer' / (item['name'] + '.result.json') and
            row['host_retirement_proved'] is True and row['evidence_complete'] is True and
            row['returncode'] == 0 and row['timed_out'] is False and row['errors'] == [] and row.get('first_error') is None and
            row['argv'][:7] == ['/usr/bin/sudo', '-n', '-u', '#1000', '--', '/usr/bin/env', '-i'] and
            row['argv'][-len(item['logical_argv']):] == item['logical_argv'], 'ACTUAL_UNPRIVILEGED_RETIRED_BUILD_COMMAND_REQUIRED')
        common.read_ref(row['stdout']); common.read_ref(row['stderr'])
    common.need(common.regular(value['APK']['path'], 2097152, contents=False) == value['APK'] and
                Path(value['APK']['path']) == root / 'owned-ihg-qa.apk', 'ACTUAL_SIGNED_HELPER_APK_CHANGED')
    signature_item = next(r for r in value['commands'] if r['name'] == 'signature')
    common.need(signature_item['logical_argv'] == [TOOLS['apksigner'][0], 'verify', '--verbose', '--print-certs',
        '--min-sdk-version', '31', value['APK']['path']], 'SIGNATURE_COMMAND_NOT_THIS_ACTUAL_APK')
    signed = common.parse(common.read_ref(signature_item['result']))
    text = common.read_ref(signed['stdout'])
    certs = re.findall(rb'^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})\r?$', text, re.M)
    common.need(certs == [value['signer_certificate_sha256'].encode()] and b'Number of signers: 1' in text and
        b'Verified using v3 scheme (APK Signature Scheme v3): true' in text, 'ACTUAL_NEW_OWNED_APK_SIGNATURE_REQUIRED')
    for name in ('ActionRunner.java', 'AndroidManifest.xml'):
        common.need(common.regular(root / 'source' / name)[0] == common.read_ref(source['files'][name]),
                    'ACTUAL_COMPILER_SOURCE_COPY_CHANGED')
    javac = value['commands'][0]['logical_argv']
    common.need(javac[0] == TOOLS['javac'][0] and javac[-1] == str(root / 'source/ActionRunner.java'),
                'ACTUAL_JAVAC_DID_NOT_REFERENCE_GENERATED_SOURCE')
    report = common.parse(common.read_ref(value['protocol_controls']))
    common.need(report['all_passed'] is True and report['count'] == 77 and
                report['Java_runtime_executed'] is False and report['Android_commands'] == report['UI_actions'] == 0,
                'ACTUAL_GENERATED_HOST_PROTOCOL_CONTROL_RECEIPT_REQUIRED')
    baseline.guard()
    return value, source, baseline, modules
