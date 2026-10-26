#!/usr/bin/env python3
"""Local read/build qualification only; never install, elevate or send an effect.

Invoke through the already authorized original operator on its selected host.
This script cannot establish that external host/peer authority itself.
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import types
import zipfile

if __package__:
    from . import build_receiver
else:
    import build_receiver


PACKAGE = 'local.pocket4.actions.v2'
HELPER = '/usr/local/libexec/android-digitalis-observe-helper'
CONTROL = '/usr/bin/droidloomctl'


def require(condition, code):
    if not condition:
        raise ValueError(code)


def pinned_file(path, expected, owner):
    require(re.fullmatch('[0-9a-f]{64}', expected) is not None, 'INVALID_EXPECTED_SHA256')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == owner
                and not info.st_mode & 0o022 and info.st_mode & 0o111
                and info.st_size <= 64 * 1024 * 1024, 'UNTRUSTED_TOOL_FILE')
        raw = source.read(64 * 1024 * 1024 + 1)
        after = os.fstat(source.fileno())
    require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            'TOOL_CHANGED_DURING_MEASUREMENT')
    require(hashlib.sha256(raw).hexdigest() == expected, 'TOOL_PIN_MISMATCH')
    return raw


def candidate_build_identity(candidate, build_record, expected_record_sha256):
    """Bind a signed APK to the current strict receiver's recorded build.

    Signer equality alone also accepts the legacy APK. A reviewed build receipt
    is required to associate the candidate DEX with the generated source; this
    is an identity check, not a replay of compilation or an Android effect.
    """
    require(isinstance(expected_record_sha256, str)
            and re.fullmatch('[0-9a-f]{64}', expected_record_sha256), 'INVALID_BUILD_RECORD_PIN')
    with Path(build_record).open('rb') as source:
        raw = source.read(128 * 1024 + 1)
    require(len(raw) <= 128 * 1024 and hashlib.sha256(raw).hexdigest() == expected_record_sha256,
            'BUILD_RECORD_PIN_MISMATCH')
    def unique_fields(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'DUPLICATE_BUILD_RECORD_FIELD')
            value[key] = item
        return value
    record = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=unique_fields)
    require(isinstance(record, dict) and type(record.get('schema_version')) is int and record['schema_version'] == 1
            and record.get('package') == PACKAGE, 'INVALID_RECEIVER_BUILD_RECORD')
    with tempfile.TemporaryDirectory(prefix='receiver-source-identity-') as scratch:
        _, current = build_receiver.sources(Path(scratch) / 'generated')
    require(record.get('original_source_sha256') == current['original_source_sha256']
            and record.get('source_sha256') == current['source_sha256'], 'RECEIVER_BUILD_SOURCE_MISMATCH')
    require(record.get('compile_sdk') == 35
            and record.get('android_jar_sha256') == build_receiver.ANDROID_JAR_SHA256
            and record.get('original_apk_sha256') == build_receiver.ORIGINAL_APK_SHA256
            and record.get('signer_identity_matches_original') is True
            and record.get('signing_required_for_deployment') is False,
            'SIGNED_RECEIVER_BUILD_REQUIRED')
    require(record.get('candidate_apk_sha256') == build_receiver.sha(candidate), 'CANDIDATE_BUILD_HASH_MISMATCH')
    with zipfile.ZipFile(candidate) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        require(len(names) == len(set(names)) and names.count('classes.dex') == 1
                and not any(name.startswith('classes') and name.endswith('.dex') and name != 'classes.dex'
                            for name in names), 'AMBIGUOUS_CANDIDATE_DEX')
        entry = archive.getinfo('classes.dex')
        require(0 < entry.file_size <= 4 * 1024 * 1024, 'CANDIDATE_DEX_SIZE_UNQUALIFIED')
        dex_sha256 = hashlib.sha256(archive.read(entry)).hexdigest()
    require(dex_sha256 == record.get('classes_dex_sha256'), 'CANDIDATE_DEX_BUILD_MISMATCH')
    return {'build_record_sha256': expected_record_sha256, 'classes_dex_sha256': dex_sha256,
            'candidate_apk_sha256': record['candidate_apk_sha256'],
            'generated_source_sha256': current['source_sha256'],
            'build_record_original_signer_sha256': record.get('original_signer_sha256'),
            'build_record_candidate_signer_sha256': record.get('candidate_signer_sha256'),
            'current_receiver_build_inputs_bound': True}


def check_apks(sdk, original, candidate, build_record, expected_record_sha256):
    built = candidate_build_identity(candidate, build_record, expected_record_sha256)
    tools = Path(sdk).resolve() / 'build-tools/35.0.1'
    require(build_receiver.sha(original) == build_receiver.ORIGINAL_APK_SHA256, 'ORIGINAL_APK_PIN_MISMATCH')
    baseline = build_receiver.certificates(tools / 'apksigner', original)
    candidate_certs = build_receiver.certificates(tools / 'apksigner', candidate)
    require(baseline == candidate_certs, 'ORIGINAL_SIGNER_IDENTITY_MISMATCH')
    require(built['build_record_original_signer_sha256'] == baseline
            and built['build_record_candidate_signer_sha256'] == candidate_certs, 'BUILD_SIGNER_RECORD_MISMATCH')
    metadata = build_receiver.run([tools / 'aapt', 'dump', 'badging', candidate])
    package = re.search(r"^package: name='([^']+)' versionCode='([^']+)'", metadata, re.M)
    require(package is not None and package.group(1) == PACKAGE, 'CANDIDATE_PACKAGE_MISMATCH')
    require(not re.search(r'^uses-permission(?:-sdk-\d+)?:', metadata, re.M), 'UNREVIEWED_CANDIDATE_PERMISSIONS')
    manifest = build_receiver.run([tools / 'aapt', 'dump', 'xmltree', candidate, 'AndroidManifest.xml'])
    require('local.pocket4.actions.v2.ActionRunner' in manifest or '.ActionRunner' in manifest,
            'ORIGINAL_INSTRUMENTATION_MISSING')
    require('E: activity ' not in manifest and 'E: service ' not in manifest
            and 'E: provider ' not in manifest and 'E: receiver ' not in manifest,
            'UNREVIEWED_CANDIDATE_COMPONENT')
    require(build_receiver.sha(candidate) == built['candidate_apk_sha256']
            and build_receiver.sha(original) == build_receiver.ORIGINAL_APK_SHA256,
            'APK_CHANGED_DURING_QUALIFICATION')
    return {**built,
        'package': PACKAGE, 'version_code': package.group(2),
        'original_apk_sha256': build_receiver.sha(original),
        'candidate_apk_sha256': build_receiver.sha(candidate),
        'original_signer_sha256': baseline, 'candidate_signer_sha256': candidate_certs,
        'signer_identity_matches_original': True,
    }


def installed(args):
    require(os.geteuid() == 0, 'ORIGINAL_ROOT_INSPECTION_CAPABILITY_REQUIRED')
    require(args.droidloomctl_owner_uid >= 0, 'INVALID_CONTROL_OWNER')
    baseline = check_apks(args.sdk, args.original_apk, args.candidate_apk,
                          args.build_record, args.expected_build_record_sha256)
    require(args.expected_helper_sha256 == baseline['generated_source_sha256']['android-digitalis-observe-helper'],
            'HELPER_RECEIVER_BUILD_MISMATCH')
    # Read the already deployed helper bytes through a no-follow, explicitly
    # pinned root-owned file. Compile those verified bytes directly in memory;
    # do not reopen an unmeasured source or accept an arbitrary command hook.
    source = pinned_file(HELPER, args.expected_helper_sha256, 0)
    control = pinned_file(CONTROL, args.droidloomctl_sha256, args.droidloomctl_owner_uid)
    module = types.ModuleType('original_android_receiver_qualification')
    exec(compile(source, HELPER, 'exec'), module.__dict__)
    require(hasattr(module, '_OrganCell'), 'BOUND_ORIGINAL_RECEIVER_NOT_DEPLOYED')
    lock = os.open('/run/lock/android-digitalis-actions.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cell = module._OrganCell()
        try:
            lines = cell.run(['/system/bin/pm', 'path', PACKAGE], timeout=15).decode('utf-8', 'strict').splitlines()
            require(len(lines) == 1 and lines[0].startswith('package:'), 'INSTALLED_APK_NOT_UNIQUE')
            path = lines[0][len('package:'):]
            require(re.fullmatch(r'/data/app/[A-Za-z0-9_+~=/.-]+/base\.apk', path) is not None
                    and '..' not in path.split('/'), 'UNEXPECTED_INSTALLED_APK_PATH')
            # Fixed read operation through the exact original namespace FDs.
            # No APK installation, package stop, launch or UI command occurs.
            raw = cell.run(['/system/bin/cat', path], timeout=15)
            require(0 < len(raw) <= 4 * 1024 * 1024, 'INSTALLED_APK_SIZE_UNQUALIFIED')
            require(hashlib.sha256(raw).hexdigest() == baseline['candidate_apk_sha256'], 'INSTALLED_APK_HASH_MISMATCH')
            with tempfile.TemporaryDirectory(prefix='original-android-apk-check-') as scratch:
                copy = Path(scratch) / 'installed.apk'
                copy.write_bytes(raw)
                installed_certs = build_receiver.certificates(Path(args.sdk) / 'build-tools/35.0.1/apksigner', copy)
            require(installed_certs == baseline['original_signer_sha256'], 'INSTALLED_APK_SIGNER_MISMATCH')
            require(pinned_file(HELPER, args.expected_helper_sha256, 0) == source
                    and pinned_file(CONTROL, args.droidloomctl_sha256, args.droidloomctl_owner_uid) == control,
                    'ORIGINAL_TOOL_CHANGED_DURING_QUALIFICATION')
            return {**baseline, 'installed_apk_sha256': hashlib.sha256(raw).hexdigest(),
                    'installed_signer_sha256': installed_certs, 'installed_source_matches_candidate': True,
                    'helper_sha256': args.expected_helper_sha256, 'cell_generation': cell.generation,
                    'scope': 'point-in-time original installed bytes; no native UI/effect or production authority qualification'}
        finally:
            cell.close()
    finally:
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    java = sub.add_parser('java', help='generate and javac only; no manifest/key or Android required')
    java.add_argument('--output', required=True)
    java.add_argument('--sdk', default='/opt/android-sdk')
    for mode in ('apk', 'installed'):
        command = sub.add_parser(mode)
        command.add_argument('--sdk', default='/opt/android-sdk')
        command.add_argument('--original-apk', default='/opt/pocket4-android-controls/actions-v2.apk')
        command.add_argument('--candidate-apk', required=True)
        command.add_argument('--build-record', required=True, help='reviewed signed receiver build-record.json')
        command.add_argument('--expected-build-record-sha256', required=True,
                             help='trusted digest of the selected signed build record')
        if mode == 'installed':
            command.add_argument('--expected-helper-sha256', required=True)
            command.add_argument('--droidloomctl-sha256', required=True)
            command.add_argument('--droidloomctl-owner-uid', type=int, required=True)
    args = parser.parse_args()
    if args.mode == 'java':
        output, record = build_receiver.sources(args.output)
        android = Path(args.sdk).resolve() / 'platforms/android-35/android.jar'
        require(build_receiver.sha(android) == build_receiver.ANDROID_JAR_SHA256, 'ORIGINAL_SDK_JAR_PIN_MISMATCH')
        classes = output / 'classes'
        classes.mkdir()
        build_receiver.run(['/usr/bin/javac', '-encoding', 'UTF-8', '-source', '8', '-target', '8',
                            '-bootclasspath', android, '-d', classes, *sorted((output / 'src').rglob('*.java'))])
        record.update(scope='actual original SDK35 javac only; no APK/deployment/native effect qualification',
                      java_compilation_passed=True, android_jar_sha256=build_receiver.sha(android),
                      class_sha256={str(p.relative_to(output)): build_receiver.sha(p) for p in sorted(classes.rglob('*.class'))})
        (output / 'javac-record.json').write_text(json.dumps(record, indent=2) + '\n')
    elif args.mode == 'apk':
        record = check_apks(args.sdk, args.original_apk, args.candidate_apk,
                            args.build_record, args.expected_build_record_sha256)
        record['scope'] = 'signed APK identity only; no installed-package or native effect qualification'
    else:
        record = installed(args)
    record.update(observed_unix_ms=time.time_ns() // 1000000,
                  inspector_sha256=build_receiver.sha(__file__), device_mutation_attempts=0,
                  host_binding_verified_by_inspector=False, original_operator_target_record_required=True)
    print(json.dumps(record, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
