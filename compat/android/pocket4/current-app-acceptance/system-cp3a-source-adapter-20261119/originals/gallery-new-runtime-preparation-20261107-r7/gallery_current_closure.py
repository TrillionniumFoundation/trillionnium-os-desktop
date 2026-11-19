"""Fresh Gallery and ART input closure for the qualified final Main.

Historical Gallery metadata is retained as a preservation obligation. Runtime
code identities are observed from the new Main and its actual qualified native
contract; they are never substituted with the historical ART17 code closure.
"""
from pathlib import Path
import copy
import json
import os
import re
import stat
import xml.etree.ElementTree as ET

PACKAGE = 'com.android.gallery3d'
OLD_APK = '/product/app/Gallery2/Gallery2.apk'
OLD_SHA = '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
SERVICES_SHA = 'bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86'
FRAMEWORK_SHA = 'bc8a175a95dcb50b5ae62a03a0ec2ba0fdea34169f83b2aab3c8bf2790707587'
QPR1_FRAMEWORK_FILES = {'/system/framework/framework.jar': {'bytes': 49754098, 'sha256': 'bc8a175a95dcb50b5ae62a03a0ec2ba0fdea34169f83b2aab3c8bf2790707587'}, '/system/framework/services.jar': {'bytes': 25716529, 'sha256': 'bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86'}, '/system/framework/android.test.base.jar': {'bytes': 33874, 'sha256': '3cecbad9dcc8c1e6beb6f022b97725424fa6f76d95787f30c6645d9202d80326'}, '/system/framework/android.hidl.manager-V1.0-java.jar': {'bytes': 29978, 'sha256': 'ec1db5553d86156892cbd8b691fde7fbd2315dfd76747ec87eea94306340f52e'}, '/system/framework/android.hidl.base-V1.0-java.jar': {'bytes': 12902, 'sha256': 'd063d361a05e2b647f6aa610cb26eadf86864b8115c84c0f2a1f424f4ea5d25e'}, '/system/framework/org.apache.http.legacy.jar': {'bytes': 490630, 'sha256': '42f79c598dec15505535b600af718ffc8c9928858d5f3ad87d806cfad165a246'}}
QPR1_BOOTCLASSPATH_MEMBERS = ['/apex/com.android.adservices/javalib/framework-adservices.jar', '/apex/com.android.adservices/javalib/framework-sdksandbox.jar', '/apex/com.android.appsearch/javalib/framework-appsearch.jar', '/apex/com.android.art/javalib/apache-xml.jar', '/apex/com.android.art/javalib/bouncycastle.jar', '/apex/com.android.art/javalib/core-libart.jar', '/apex/com.android.art/javalib/core-oj.jar', '/apex/com.android.art/javalib/okhttp.jar', '/apex/com.android.bt/javalib/framework-bluetooth.jar', '/apex/com.android.configinfrastructure/javalib/framework-configinfrastructure.jar', '/apex/com.android.conscrypt/javalib/conscrypt.jar', '/apex/com.android.conscrypt/javalib/framework-conscrypt-nsc.jar', '/apex/com.android.crashrecovery/javalib/framework-crashrecovery.jar', '/apex/com.android.devicelock/javalib/framework-devicelock.jar', '/apex/com.android.healthfitness/javalib/framework-healthfitness.jar', '/apex/com.android.i18n/javalib/core-icu4j.jar', '/apex/com.android.ipsec/javalib/android.net.ipsec.ike.jar', '/apex/com.android.media/javalib/updatable-media.jar', '/apex/com.android.mediaprovider/javalib/framework-mediaprovider.jar', '/apex/com.android.mediaprovider/javalib/framework-pdf-v.jar', '/apex/com.android.mediaprovider/javalib/framework-pdf.jar', '/apex/com.android.mediaprovider/javalib/framework-photopicker.jar', '/apex/com.android.nfcservices/javalib/framework-nfc.jar', '/apex/com.android.npumanager/javalib/framework-npumanager.jar', '/apex/com.android.ondevicepersonalization/javalib/framework-ondevicepersonalization.jar', '/apex/com.android.os.statsd/javalib/framework-statsd.jar', '/apex/com.android.permission/javalib/framework-permission-s.jar', '/apex/com.android.permission/javalib/framework-permission.jar', '/apex/com.android.profiling/javalib/framework-anomaly-detector.jar', '/apex/com.android.profiling/javalib/framework-profiling.jar', '/apex/com.android.scheduling/javalib/framework-scheduling.jar', '/apex/com.android.sdkext/javalib/framework-sdkextensions.jar', '/apex/com.android.telephonycore/javalib/framework-telecom.jar', '/apex/com.android.telephonycore/javalib/framework-telephony.jar', '/apex/com.android.tethering/javalib/framework-connectivity-b.jar', '/apex/com.android.tethering/javalib/framework-connectivity-t.jar', '/apex/com.android.tethering/javalib/framework-connectivity.jar', '/apex/com.android.tethering/javalib/framework-tethering.jar', '/apex/com.android.uprobestats/javalib/framework-uprobestats.jar', '/apex/com.android.uwb/javalib/framework-ranging.jar', '/apex/com.android.uwb/javalib/framework-uwb.jar', '/apex/com.android.virt/javalib/framework-virtualization.jar', '/apex/com.android.webapp/javalib/framework-webapp.jar', '/apex/com.android.wifi/javalib/framework-wifi.jar', '/system/framework/ext.jar', '/system/framework/framework-graphics.jar', '/system/framework/framework-location.jar', '/system/framework/framework-ondeviceintelligence-platform.jar', '/system/framework/framework.jar', '/system/framework/ims-common.jar', '/system/framework/telephony-common.jar', '/system/framework/voip-common.jar']
HOME_RESOLVE = ['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0',
                '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.HOME']
ROLE_PATHS = {
    'engine': '/system/lib64/libberberis_arm64.so',
    'art_apex': '/system/apex/com.android.art.apex',
    'libart': '/apex/com.android.art/lib64/libart.so',
    'libnativebridge': '/apex/com.android.art/lib64/libnativebridge.so',
    'owner': '/system/bin/droidloom-proc-maps-owner',
    'factory': '/system/bin/droidloom-proc-maps-factory-v2',
    'readiness': '/system/bin/droidloom-proc-maps-readiness',
    'pair': '/system/etc/droidloom-native-generation-pair.json',
    'bridge_profile': '/system/etc/droidloom-native-bridge.json',
}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def canonical_component(value):
    need(type(value) is str and re.fullmatch(r'[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+', value),
         'EXACT_ANDROID_COMPONENT_REQUIRED')
    package, activity = value.split('/')
    return package + '/' + (package + activity if activity.startswith('.') else activity)


def fresh_home(session, original_identity):
    resolve = session.android(HOME_RESOLVE, 15).decode('utf-8', 'strict').splitlines()
    components = [line for line in resolve if re.fullmatch(r'[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+', line)]
    need(len(components) == 1, 'EXACT_RESOLVED_HOME_COMPONENT_REQUIRED')
    home = canonical_component(components[0])
    raw = session.android(['/system/bin/cmd', 'activity', 'stack', 'list'], 15).decode('utf-8', 'strict')
    roots = {}; tasks = []
    for block in re.split(r'(?=^RootTask id=)', raw, flags=re.M):
        if not block.startswith('RootTask id='):
            continue
        header = block.splitlines()[0]
        match = re.fullmatch(r'RootTask id=(\d+)\b.*', header)
        display = re.search(r'\bdisplayId=(\d+)\b', header)
        user = re.search(r'\buserId=(\d+)\b', header)
        need(match is not None and display and user and match[1] not in roots, 'EXACT_HOME_ROOT_HEADER')
        children = []
        for line in block.splitlines()[1:]:
            if not re.match(r'\s*taskId=', line):
                continue
            item = re.fullmatch(r'\s*taskId=(\d+):\s+(\S+)\s+.*?\buserId=(\d+)\b.*', line)
            need(item is not None and int(item[1]) not in tasks, 'EXACT_UNIQUE_TASK_HEADER')
            need(int(item[3]) == 0 and canonical_component(item[2]) == home,
                 'ONLY_ACTUAL_RESOLVED_HOME_TASK_ADMITTED')
            tasks.append(int(item[1])); children.append({'id': int(item[1]), 'component': item[2], 'user': 0})
        roots[match[1]] = {'display': int(display[1]), 'user': int(user[1]), 'children': children}
    need(len(tasks) == 1 and roots, 'ONE_FRESH_ACTUAL_HOME_TASK_REQUIRED')
    # A second real observation uses the original exact all-root preservation
    # parser; no historical task ID, root ID, or foreground state is reused.
    checked = original_identity.home_snapshot(session, roots)
    return {'roots': roots, 'task_ids': tasks, 'resolved_home_component': home,
            'first_stack_sha256': session.common.sha(raw.encode()), 'second_snapshot': checked}


def preserve_historical_identity(session, identity, current):
    expected = copy.deepcopy(identity.EXPECTED)
    proof = session.baseline.value['data_continuity']
    need(proof['package_uids'][PACKAGE] == 10064,
         'REAL_PREDEPLOYMENT_GALLERY_UID_CONTINUITY_REQUIRED')
    for label, kind in (('ce', 'user'), ('de', 'user_de')):
        live = proof['directories'][kind + '/0/' + PACKAGE]
        old = expected['directories'][label]
        need(live['inode'] == old['st_ino'] and live['uid'] == old['st_uid']
             and live['gid'] == old['st_gid'] and live['device'] == proof['live_device']['device'],
             'ORIGINAL_GALLERY_DIRECTORY_IDENTITY_MUST_SURVIVE_NEW_MAIN')
        # A fresh loop device can have a different st_dev. Its actual UUID,
        # backing-image identity and both original inodes were independently
        # qualified by BusinessBaseline; all other historical fields stay exact.
        expected['directories'][label]['st_dev'] = live['device']
    need(current['protected'] == expected, 'EXACT_ORIGINAL_29_PERMISSIONS_AND_GALLERY_STATE_REQUIRED')
    need(current['apk']['sha256'] == OLD_SHA and current['apk']['path'] == OLD_APK,
         'EXACT_ORIGINAL_INSTALLED_GALLERY_REQUIRED')
    return {'all_29_permission_rows_preserved': True, 'historical_protected_fields_equal': True,
        'fresh_device_bound_to_original_data_image': True, 'filesystem_uuid': proof['filesystem_uuid'],
        'same_original_ce_de_inodes': True, 'no_private_app_contents_read': True}


def native_contract(session):
    common = session.common; post = session.baseline.docs['post_start_receipt']
    plan_ref = post['qualification_plan']
    plan_raw, actual_plan_ref = common.regular(plan_ref['path'])
    need(actual_plan_ref['sha256'] == plan_ref['sha256'], 'ACTUAL_FINAL_QUALIFICATION_PLAN_CHANGED')
    plan = common.parse(plan_raw)
    need(plan['ready'] is True, 'ACTUAL_DEPLOYED_QUALIFICATION_PLAN_REQUIRED')
    contract_ref = plan['component_inputs']['native']['contract']
    raw, actual_contract_ref = common.regular(contract_ref['path'])
    need(actual_contract_ref['sha256'] == contract_ref['sha256'], 'QUALIFIED_NATIVE_CONTRACT_CHANGED')
    contract = common.parse(raw)
    need(contract['schema'] == 'pocket4-native-runtime-contract-v1'
         and contract['protocol'] == 'DLOOMGE1-PROCMET2'
         and set(contract['files']) == set(ROLE_PATHS), 'EXACT_CURRENT_COMPLETE_NATIVE_PAIR_REQUIRED')
    for role, path in ROLE_PATHS.items():
        need(contract['files'][role]['guest_path'] == path, 'NATIVE_ROLE_PATH_CHANGED')
    found = []
    for proof in post['proofs']:
        proof_raw, actual_proof = common.regular(proof['path'])
        need(actual_proof['sha256'] == proof['sha256'], 'POST_START_PROOF_CHANGED')
        value = common.parse(proof_raw)
        if value.get('schema') == 'pocket4-final-native-runtime-result-v1':
            found.append((value, actual_proof))
    need(len(found) == 1, 'ONE_ACTUAL_NATIVE_RUNTIME_QUALIFICATION_REQUIRED')
    value, proof_ref = found[0]
    need(value['state'] == 'PASS' and value['original_APK05_tests_passed'] == 12
         and value['original_APK05_tests_failed'] == 0
         and value['complete_pair_mapped_in_actual_test_process'] is True
         and value['fresh_Main_epoch_unchanged'] is True
         and value['native_contract']['path'] == actual_contract_ref['path']
         and value['native_contract']['sha256'] == actual_contract_ref['sha256']
         and value['baseline_input']['sha256'] == session.baseline.plan['final_baseline']['sha256']
         and value['transaction_id'] == post['transaction_id'], 'SAME_FINAL_MAIN_NATIVE_PAIR_MUST_HAVE_PASSED')
    return contract, {'contract': actual_contract_ref, 'native_runtime': proof_ref,
                       'final_qualification_plan': actual_plan_ref}


def directory_names(session, path):
    fd = session.target.open_root(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd); names = sorted(os.listdir(fd)); after = os.fstat(fd)
        need((before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
             == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns),
             'CODE_DIRECTORY_CHANGED_DURING_ENUMERATION')
        need(len(names) <= 512 and all(re.fullmatch(r'[A-Za-z0-9_.@+-]+', name) for name in names),
             'BOUNDED_CODE_DIRECTORY_REQUIRED')
        return names
    finally:
        os.close(fd)


def gallery_context(session, original_context, original_identity):
    current = original_identity.snapshot(session, OLD_SHA)
    preservation = preserve_historical_identity(session, original_identity, current)
    config = {'roots': {}, 'declarations': {}}
    for root in original_context.CONFIG_ROOTS:
        try:
            names = directory_names(session, root)
        except FileNotFoundError:
            config['roots'][root] = {'exists': False}
            continue
        selected = [name for name in names if name in original_context.CONFIG_NAMES]
        files = {}
        for name in selected:
            path = root + '/' + name; pin, raw = session.paired_file(path, contents=True, maximum=262144)
            xml = ET.fromstring(raw)
            declarations = [dict(node.attrib) for node in xml.iter('library')
                            if node.attrib.get('name') in original_context.REQUIRED + original_context.OPTIONAL]
            files[path] = {'pin': pin, 'selected_declarations': declarations}
            for row in declarations:
                config['declarations'].setdefault(row['name'], []).append({
                    'source_path': path, 'attributes': row, 'source_file_sha256': pin['sha256']})
        config['roots'][root] = {'exists': True, 'selected_files': files}
    load_raw = session.android(['/system/bin/cmd', 'overlay', 'lookup', '--user', '0', 'android',
        'android:array/config_sharedLibrariesLoadedAfterApp'], 15)
    need(load_raw == b'', 'ORIGINAL_EMPTY_AFTER_APP_LIBRARY_GRAPH_REQUIRED')
    package = {'package': PACKAGE, 'uid': 10064, **current['protected']['shared_library_configuration']}
    value = {'package': package, 'configuration': config, 'load_after': {'values': []}}
    graph, context = original_context.graph_and_context(value)
    # The complete dumpsys output is already retained by MainView's owned read
    # journal. Its unselected diagnostic sections are observations, not package
    # identity. Keep every parsed protected/code field and the complete APK pin.
    stable_gallery = {key: value for key, value in current.items()
                      if key not in ('dump_sha256', 'selected_block_sha256')}
    return {'gallery': stable_gallery, 'preservation': preservation, 'configuration': config,
        'graph': graph, 'class_loader_context': context, 'load_after_sha256': session.common.sha(load_raw),
        'factory_and_manifest_are_exact_original_APK': True,
        'live_App_classloader_heap_observed': False}


def mapped_boot_files(session):
    raw = session.held.read_at(session.peer.proc_fd, 'maps', 16 * 1024 * 1024, session.deadline)
    selected = {}
    patterns = (
        r'/system/framework/x86_64/boot[A-Za-z0-9_.@+-]*\.(?:art|oat|vdex)',
        r'/apex/com\.android\.art/javalib/x86_64/boot[A-Za-z0-9_.@+-]*\.(?:art|oat|vdex)',
        r'/data/misc/apexdata/com\.android\.art/dalvik-cache/x86_64/boot[A-Za-z0-9_.@+-]*\.(?:art|oat|vdex)',
        r'/data/dalvik-cache/x86_64/[A-Za-z0-9_.@+-]*boot[A-Za-z0-9_.@+-]*\.(?:art|oat|vdex)',
    )
    for line in raw.decode('utf-8', 'strict').splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6:
            continue
        path = fields[5]
        if not any(re.fullmatch(pattern, path) for pattern in patterns):
            continue
        need(len(selected) <= 128 and fields[4].isdigit(), 'MAPPED_BOOT_FILE_BOUND')
        row = {'path': path, 'device': fields[3], 'inode': int(fields[4])}
        need(path not in selected or selected[path] == row, 'MAPPED_BOOT_FILE_BACKING_CONFLICT')
        selected[path] = row
    need(selected and any(path.endswith('.art') for path in selected), 'ACTUAL_SYSTEMSERVER_BOOT_ART_MAPPINGS_REQUIRED')
    return [selected[path] for path in sorted(selected)]


def snapshot(session, original_context, original_identity):
    before = session.guard(); contract, contract_proofs = native_contract(session)
    context = gallery_context(session, original_context, original_identity)
    cp = session.baseline.value['classpath']
    bootclasspath = session.environment['BOOTCLASSPATH'].split(':')
    need(len(bootclasspath) == 52 and len(set(bootclasspath)) == 52
         and session.environment['BOOTCLASSPATH'] == cp['values']['BOOTCLASSPATH']
         and set(bootclasspath) == set(QPR1_BOOTCLASSPATH_MEMBERS),
         'ACTUAL_COMPLETE_52_BOOTCLASSPATH_FILES_REQUIRED')
    directories = {'ART_lib64': directory_names(session, '/apex/com.android.art/lib64'),
                   'system_boot': directory_names(session, '/system/framework/x86_64')}
    active_boot = mapped_boot_files(session)
    paths = set(bootclasspath) | {row['path'] for row in cp['files']} | set(ROLE_PATHS.values())
    paths.update(original_context.FILES)
    paths.update('/apex/com.android.art/lib64/' + name for name in directories['ART_lib64'] if name.endswith('.so'))
    paths.update('/system/framework/x86_64/' + name for name in directories['system_boot']
                 if name.startswith('boot') and name.endswith(('.art', '.oat', '.vdex')))
    paths.update(row['path'] for row in active_boot)
    paths.update({'/system/framework/framework.jar', '/system/framework/services.jar',
        '/apex/com.android.art/bin/dexoptanalyzer', '/apex/com.android.art/bin/dex2oat64',
        '/apex/com.android.art/bin/oatdump', '/apex/apex-info-list.xml', '/system/bin/linker64',
        '/system/bin/env', '/system/xbin/su', '/system/bin/timeout', '/system/bin/sh',
        '/system/bin/toybox', '/system/bin/id', '/system/bin/cat'})
    for row in context['configuration']['roots'].values():
        if row.get('exists'):
            paths.update(row['selected_files'])
    need(len(paths) <= 256, 'BOUNDED_COMPLETE_CURRENT_CODE_CLOSURE')
    files = {}; total = 0
    for path in sorted(paths):
        pin = session.paired_file(path); files[path] = pin; total += pin['bytes']
        need(total <= 2 * 1024**3, 'CURRENT_CODE_CLOSURE_BYTE_BOUND')
    for role, path in ROLE_PATHS.items():
        need(files[path]['sha256'] == contract['files'][role]['sha256']
             and files[path]['bytes'] == contract['files'][role]['bytes'], 'ACTUAL_CURRENT_NATIVE_ROLE_CHANGED:' + role)
    need(files['/system/framework/services.jar']['sha256'] == SERVICES_SHA
         and files['/system/framework/framework.jar']['sha256'] == FRAMEWORK_SHA,
         'FINAL_STORAGE_AND_FRAMEWORK_PAYLOAD_MUST_BE_PRESERVED')
    for path, expected in QPR1_FRAMEWORK_FILES.items():
        need(files[path]['sha256'] == expected['sha256'] and files[path]['bytes'] == expected['bytes'],
             'EXACT_CURRENT_QPR1_FRAMEWORK_OR_CONTEXT_LIBRARY_REQUIRED:' + path)
    for row in cp['files']:
        need(files[row['path']]['sha256'] == row['sha256'] and files[row['path']]['bytes'] == row['bytes'],
             'ACTUAL_FINAL_CLASSPATH_CODE_CHANGED')
    for row in active_boot:
        identity = files[row['path']]['identity']; device = identity['st_dev']
        expected_device = '%02x:%02x' % (os.major(device), os.minor(device))
        need(row['inode'] == identity['st_ino'] and row['device'] == expected_device,
             'SYSTEMSERVER_BOOT_MAPPING_NOT_SAME_HELD_FILE')
    need(mapped_boot_files(session) == active_boot, 'SYSTEMSERVER_BOOT_MAPPINGS_CHANGED')
    need(session.guard() == before, 'CURRENT_MAIN_CHANGED_DURING_CODE_SNAPSHOT')
    return {'schema': 'pocket4-gallery-current-code-closure-v1', 'main_guard': before,
        'native_contract_proofs': contract_proofs, 'bootclasspath': bootclasspath,
        'classpath_values': cp['values'], 'code_directories': directories, 'code_files': files,
        'total_code_bytes': total, 'system_server_mapped_boot_files': active_boot,
        'gallery_context': context, 'same_historical_ART17_code_closure_claimed': False,
        'compiler_boot_image_argument': '/system/framework/boot.art',
        'current_boot_mappings_recorded_separately_from_compiler_input_location': True}


def recheck_runtime_code(session, expected):
    """Re-read every runtime file after the one package update.

    Gallery's new code path is checked separately by the original package
    preservation parser. All OS/ART/boot/library inputs must stay identical.
    """
    before = session.guard(); unused, proofs = native_contract(session)
    need(proofs == expected['native_contract_proofs'], 'FINAL_NATIVE_PROOF_CHANGED_AFTER_INSTALL')
    directories = {'ART_lib64': directory_names(session, '/apex/com.android.art/lib64'),
                   'system_boot': directory_names(session, '/system/framework/x86_64')}
    need(directories == expected['code_directories'], 'CURRENT_CODE_DIRECTORY_SET_CHANGED')
    observed = {path: session.paired_file(path) for path in expected['code_files']}
    need(observed == expected['code_files'], 'CURRENT_RUNTIME_CODE_CHANGED_AFTER_INSTALL')
    mapped = mapped_boot_files(session)
    need(mapped == expected['system_server_mapped_boot_files'], 'CURRENT_BOOT_MAPPINGS_CHANGED_AFTER_INSTALL')
    need(session.environment['BOOTCLASSPATH'].split(':') == expected['bootclasspath']
         and session.baseline.value['classpath']['values'] == expected['classpath_values'],
         'CURRENT_CLASSPATH_CHANGED_AFTER_INSTALL')
    after = session.guard()
    need(after == before == expected['main_guard'], 'FINAL_MAIN_CHANGED_AFTER_INSTALL')
    return {'schema': 'pocket4-gallery-current-code-post-install-v1',
        'native_contract_proofs': proofs, 'code_directories': directories,
        'code_files': observed, 'system_server_mapped_boot_files': mapped,
        'main_guard': after, 'all_runtime_code_files_identical': True}
