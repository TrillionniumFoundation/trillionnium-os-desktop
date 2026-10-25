#!/usr/bin/env python3
"""Explicit, identity-bound physical Android smoke; default is host-only.

Never starts/kills an ADB server, unlocks a device, replaces an existing package,
or upgrades Android application evidence to Asterinas/Hepta production authority.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile

import build_physical_smoke_apk as build

PACKAGE = 'org.trillionnium.a08smoke'
COMPONENT = PACKAGE + '/.MainActivity'
VALUE = 'A08Persist42'


class Refused(RuntimeError):
    pass


class Recorder(build.Recorder):
    def run(self, args, timeout=120):
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            return super().run(args, timeout)
        finally:
            self.commands[-1]['started_utc'] = started
            (self.out / 'commands.json').write_text(json.dumps(self.commands, indent=2) + '\n')


def require(condition, message):
    if not condition:
        raise Refused(message)


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value),
            'expected digests must be full lowercase SHA-256')
    return value


def sdk_badging(badging):
    # Current AAPT2 uses minSdkVersion; older versions print sdkVersion.
    # Match complete fields and reject conflicting/duplicated declarations.
    require(re.findall(r"^(?:minSdkVersion|sdkVersion):'([^']+)'$", badging,
                       re.MULTILINE) == ['28'] and
            re.findall(r"^targetSdkVersion:'([^']+)'$", badging,
                       re.MULTILINE) == ['35'], 'compiled min/target SDK mismatch')


def host_gate(args, recorder):
    require(build.checksum(args.build_manifest) == sha(args.expected_manifest_sha256),
            'build manifest digest mismatch')
    manifest = json.loads(args.build_manifest.read_text())
    require(manifest.get('kind') == build.PROFILE and
            manifest.get('status') == 'built_not_executed', 'unexpected build profile')
    require(all(manifest.get(key) is False for key in
                ('native_asterinas_qualified', 'production_owner_qualified',
                 'mobile_organ_qualified', 'aosp_soong_build')), 'invalid qualification claims')
    commit, tree, hashes, _ = build.source_inventory(args.repo, manifest['source']['commit'])
    require(manifest['source'] == {'commit': commit, 'tree': tree, 'files': hashes,
                                  'inventory_sha256': build.source_digest(hashes)},
            'source inventory differs from immutable Git blobs')
    require(sha(args.expected_source_sha256) == build.ORIGINAL_SOURCE_SHA256,
            'source digest differs from reviewed original application')
    expected_apk = sha(args.expected_apk_sha256)
    require(build.checksum(args.apk) == expected_apk == manifest['apk']['sha256'],
            'APK digest mismatch')
    require(sha(args.expected_certificate_sha256) == manifest['apk']['certificate_sha256'],
            'certificate digest mismatch')
    with zipfile.ZipFile(args.apk) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'duplicate APK ZIP members')
        require([n for n in names if re.fullmatch(r'classes\d*\.dex', n)] == ['classes.dex'],
                'expected exactly the original single DEX')
        require(not any(n.startswith('lib/') or n.endswith('.so') for n in names),
                'native APK is outside physical DEX scope')
    tools = manifest['tools']
    for name in ('aapt2', 'apksigner', 'apksigner.jar'):
        require(build.checksum(tools[name]['path']) == tools[name]['sha256'],
                f'{name} changed since build')
    signature = recorder.run([tools['apksigner']['path'], 'verify', '--verbose',
                              '--print-certs', args.apk])
    certs = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})$',
                       signature, re.MULTILINE)
    require(certs == [args.expected_certificate_sha256], 'verified APK signer mismatch')
    badging = recorder.run([tools['aapt2']['path'], 'dump', 'badging', args.apk])
    require(re.search(r"^package: name='" + re.escape(PACKAGE) +
                      r"' versionCode='1' versionName='1.0'", badging, re.MULTILINE),
            'compiled package/version mismatch')
    sdk_badging(badging)
    require("launchable-activity: name='" + PACKAGE + ".MainActivity'" in badging,
            'compiled launcher mismatch')
    require(not re.search(r'^uses-permission', badging, re.MULTILINE),
            'compiled application requests permissions')
    xml = recorder.run([tools['aapt2']['path'], 'dump', 'xmltree', args.apk,
                        '--file', 'AndroidManifest.xml'])
    require(not re.search(r'E: (uses-permission[^ ]*|permission|service|receiver|provider)\b', xml),
            'unexpected permission or component in compiled manifest')
    require(len(re.findall(r'E: activity\b', xml)) == 1, 'unexpected activity inventory')
    # Install a private, hash-checked copy, not a mutable input path.
    frozen = recorder.out / 'verified.apk'
    shutil.copyfile(args.apk, frozen)
    frozen.chmod(0o400)
    require(build.checksum(frozen) == expected_apk, 'APK changed during verification')
    return {'source': manifest['source'], 'apk_sha256': expected_apk,
            'certificate_sha256': args.expected_certificate_sha256,
            'build_manifest_sha256': args.expected_manifest_sha256,
            'frozen_apk': str(frozen)}


def endpoint(value):
    match = re.fullmatch(r'tcp:127\.0\.0\.1:([0-9]{1,5})', value)
    require(match and 1 <= int(match[1]) <= 65535,
            'explicit existing loopback ADB endpoint required')
    return int(match[1])


def existing_server(port):
    # Read the existing ADB smart-socket version; never issue start/kill/connect.
    with socket.create_connection(('127.0.0.1', port), timeout=3) as sock:
        sock.settimeout(3)
        def receive(count):
            data = b''
            while len(data) < count:
                part = sock.recv(count - len(data))
                require(part, 'ADB server closed the version query')
                data += part
            return data
        request = b'host:version'
        sock.sendall(f'{len(request):04x}'.encode() + request)
        require(receive(4) == b'OKAY', 'existing endpoint is not a ready ADB server')
        length = int(receive(4), 16)
        require(0 < length <= 64, 'invalid ADB server version response')
        return receive(length).decode('ascii')


class Adb:
    def __init__(self, args, recorder):
        self.port = endpoint(args.adb_endpoint)
        require(re.fullmatch(r'[A-Za-z0-9_.:-]+', args.serial or ''), 'invalid explicit serial')
        require(args.adb.is_absolute() and build.checksum(args.adb) == sha(args.expected_adb_sha256),
                'ADB executable digest mismatch')
        self.args, self.recorder = args, recorder
        self.server_version = existing_server(self.port)
        version = recorder.run([args.adb, 'version'])
        client = re.search(r'^Android Debug Bridge version 1\.0\.(\d+)$', version, re.MULTILINE)
        require(client and int(client[1]) == int(self.server_version, 16),
                'ADB client/server protocol mismatch; refusing automatic server replacement')

    def cmd(self, *parts, timeout=60, allow_failure=False):
        # A remote-host selector and live handshake prevent the client from
        # starting a local default server when the selected endpoint is absent.
        require(existing_server(self.port) == self.server_version, 'ADB server version changed')
        require(build.checksum(self.args.adb) == self.args.expected_adb_sha256, 'ADB executable changed')
        command = [self.args.adb, '-H', '127.0.0.1', '-P', str(self.port),
                   '-s', self.args.serial, *parts]
        try:
            return self.recorder.run(command, timeout=timeout)
        except RuntimeError:
            if not allow_failure:
                raise
            record = self.recorder.commands[-1]
            # Only the expected empty-result pidof exit is tolerated, not timeouts.
            require(parts == ('shell', 'pidof', PACKAGE) and record.get('returncode') == 1
                    and not (self.recorder.out / record['stderr']['file']).read_bytes(),
                    'unexpected ADB failure')
            return (self.recorder.out / record['stdout']['file']).read_text()


def unlocked(policy):
    require(re.search(r'^\s*showing=false\s*$', policy, re.MULTILINE) and
            re.search(r'^\s*inputRestricted=false\s*$', policy, re.MULTILINE),
            'device is locked or unlocked state cannot be proven; never unlock automatically')
    require(not re.search(r'\b(?:showing|mShowingLockscreen|isStatusBarKeyguard)=true\b', policy),
            'keyguard is showing')


def current_user(adb, user):
    require(adb.cmd('shell', 'am', 'get-current-user').strip() == str(user),
            'current Android user changed or does not match explicit target user')


def absent_all_users(adb, target_user):
    output = adb.cmd('shell', 'pm', 'list', 'users')
    users = re.findall(r'UserInfo\{(\d+):', output)
    require(users and str(target_user) in users, 'cannot enumerate target Android user')
    for user in users:
        packages = adb.cmd('shell', 'pm', 'list', 'packages', '-u', '--user', user, PACKAGE)
        require(not re.search(r'^package:' + re.escape(PACKAGE) + r'(?:\s|$)', packages, re.MULTILINE),
                'test package or retained data already exists; refusing overwrite/clear')
        require(not re.search(r'(?i)error|exception|denied|failure', packages),
                'cannot prove package absence for every Android user')
    return users


def device_gate(adb, args):
    require(adb.cmd('get-state').strip() == 'device', 'selected transport is not online')
    require(adb.cmd('get-serialno').strip() == args.serial, 'USB serial mismatch')
    require(args.expected_fingerprint and '\n' not in args.expected_fingerprint,
            'exact expected device fingerprint required')
    props = {key: adb.cmd('shell', 'getprop', key).strip() for key in
             ('ro.build.fingerprint', 'ro.product.model', 'ro.product.device',
              'ro.product.name', 'ro.product.cpu.abi', 'ro.build.version.release',
              'ro.build.version.sdk', 'sys.boot_completed')}
    require(props['ro.build.fingerprint'] == args.expected_fingerprint, 'device fingerprint mismatch')
    require(props['sys.boot_completed'] == '1' and props['ro.build.version.sdk'].isdigit() and
            int(props['ro.build.version.sdk']) >= 28, 'boot incomplete or Android SDK below fixture minimum')
    current_user(adb, args.user)
    unlocked(adb.cmd('shell', 'dumpsys', 'window', 'policy'))
    props['users_checked_for_absence'] = absent_all_users(adb, args.user)
    props['kernel'] = adb.cmd('shell', 'uname', '-a').strip()
    props['page_size'] = adb.cmd('shell', 'getconf', 'PAGESIZE').strip()
    props['selinux'] = adb.cmd('shell', 'getenforce').strip()
    props['adb_server_version'] = adb.server_version
    return props


def installed_identity(adb, user, expected_sha):
    paths = adb.cmd('shell', 'pm', 'path', '--user', str(user), PACKAGE).splitlines()
    require(len(paths) == 1 and paths[0].startswith('package:/data/app/'),
            'installed package is absent, split, or outside app data')
    path = paths[0].removeprefix('package:')
    require(re.fullmatch(r'/data/app/[A-Za-z0-9_./+=~-]+/base\.apk', path), 'unsafe installed APK path')
    digest = adb.cmd('shell', 'sha256sum', path).split()
    require(digest and digest[0] == expected_sha, 'installed APK changed; refusing further effects/cleanup')
    packages = adb.cmd('shell', 'pm', 'list', 'packages', '-U', '--user', str(user), PACKAGE)
    matches = re.findall(r'^package:' + re.escape(PACKAGE) + r' uid:(\d+)\s*$', packages, re.MULTILINE)
    require(len(matches) == 1, 'cannot identify newly installed package UID')
    return {'path': path, 'uid': matches[0], 'apk_sha256': digest[0]}


def owned_foreground(adb, args, identity):
    current_user(adb, args.user)
    require(installed_identity(adb, args.user, args.expected_apk_sha256) == identity,
            'installed package identity changed')
    unlocked(adb.cmd('shell', 'dumpsys', 'window', 'policy'))
    activities = adb.cmd('shell', 'dumpsys', 'activity', 'activities')
    component = re.escape(PACKAGE) + r'/(?:\.MainActivity|' + re.escape(PACKAGE) + r'\.MainActivity)'
    user_component = r'\bu' + str(args.user) + r'\s+' + component + r'\b'
    require(any(re.search(user_component, line) for line in activities.splitlines()
                if re.search(r'(?:topResumedActivity|mResumedActivity)\s*[:=]', line)),
            'owned MainActivity is not resumed')
    # Android 17's windows subsection lists individual windows but omits the
    # per-display current input focus. Require the actual display owner state.
    displays = adb.cmd('shell', 'dumpsys', 'window', 'displays')
    focused = [line for line in displays.splitlines() if 'mCurrentFocus=' in line]
    require(len(focused) == 1 and re.search(user_component, focused[0]),
            'current input focus does not belong to owned MainActivity')
    pids = adb.cmd('shell', 'pidof', PACKAGE).split()
    require(len(pids) == 1 and pids[0].isdigit(), 'expected one live original app process')
    return pids[0]


def screen_size(adb):
    output = adb.cmd('shell', 'wm', 'size')
    sizes = re.findall(r'(Physical|Override) size: (\d+)x(\d+)', output)
    require(sizes, 'display bounds unavailable')
    selected = next((entry for entry in sizes if entry[0] == 'Override'), sizes[0])
    return int(selected[1]), int(selected[2])


def node_center(node, size):
    match = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
    require(match, 'resource bounds malformed')
    left, top, right, bottom = map(int, match.groups())
    require(0 <= left < right <= size[0] and 0 <= top < bottom <= size[1],
            'resource bounds outside current screen')
    require(node.get('package') == PACKAGE and node.get('enabled') == 'true',
            'resource is not an enabled owned-app node')
    return (left + right) // 2, (top + bottom) // 2


def fresh_ui(adb, args, identity, dump_path):
    owned_foreground(adb, args, identity)
    output = adb.cmd('shell', 'uiautomator', 'dump', dump_path, timeout=45)
    require('dumped' in output and dump_path in output, 'fresh UI dump was not confirmed')
    xml = adb.cmd('exec-out', 'cat', dump_path, timeout=45)
    # Reject a focus switch during the hierarchy capture, before interpreting it.
    owned_foreground(adb, args, identity)
    tree = ET.fromstring(xml)
    require(tree.tag == 'hierarchy', 'unexpected UI hierarchy')
    return tree


def resource(tree, name, text=None):
    nodes = [node for node in tree.iter('node')
             if node.get('resource-id') == PACKAGE + ':id/' + name]
    require(len(nodes) == 1 and nodes[0].get('package') == PACKAGE, 'owned resource missing/ambiguous')
    if text is not None:
        require(nodes[0].get('text') == text, 'fresh UI persisted value does not match')
    return nodes[0]


def lifecycle(adb, args, apk, report):
    identity = None
    installed = False
    dump_paths = []
    report['steps'] = []
    def mark(name, **data):
        report['steps'].append({'step': name, 'observed_utc': datetime.datetime.now(
            datetime.timezone.utc).isoformat(), **data})
    def ui():
        # A new path for every snapshot prevents a successful-looking failed
        # dump from reusing an earlier hierarchy or saved-value marker.
        dump_path = '/data/local/tmp/a08-physical-' + uuid.uuid4().hex + '.xml'
        dump_paths.append(dump_path)
        return fresh_ui(adb, args, identity, dump_path)
    def launch(expected):
        output = adb.cmd('shell', 'am', 'start', '-W', '--user', str(args.user), '-n', COMPONENT)
        require('Status: ok' in output and PACKAGE in output, 'original Activity launch failed')
        pid = owned_foreground(adb, args, identity)
        resource(ui(), 'saved_value', 'SAVED:' + expected)
        mark('launch_and_fresh_saved_value', pid=pid, saved_value=expected)
    try:
        report['device'] = device_gate(adb, args)
        # Recheck immediately before the first write. Install has no -r/-d/-g.
        current_user(adb, args.user)
        absent_all_users(adb, args.user)
        require(adb.cmd('shell', 'getprop', 'ro.build.fingerprint').strip() ==
                args.expected_fingerprint, 'device changed before install')
        require(build.checksum(apk) == args.expected_apk_sha256, 'verified APK changed before install')
        result = adb.cmd('install', '--user', str(args.user), str(apk), timeout=120)
        require(result.strip().endswith('Success'), 'new package install not confirmed')
        installed = True
        identity = installed_identity(adb, args.user, args.expected_apk_sha256)
        report['installed_identity'] = identity
        mark('new_install', **identity)
        launch('EMPTY')
        tree = ui()
        node = resource(tree, 'input_value')
        x, y = node_center(node, screen_size(adb))
        owned_foreground(adb, args, identity)
        adb.cmd('shell', 'input', 'tap', str(x), str(y))
        focused = resource(ui(), 'input_value')
        require(focused.get('focused') == 'true', 'owned input did not gain focus')
        owned_foreground(adb, args, identity)
        adb.cmd('shell', 'input', 'text', VALUE)
        tree = ui()
        resource(tree, 'input_value', VALUE)
        node = resource(tree, 'save_button', 'SAVE')
        x, y = node_center(node, screen_size(adb))
        owned_foreground(adb, args, identity)
        adb.cmd('shell', 'input', 'tap', str(x), str(y))
        resource(ui(), 'saved_value', 'SAVED:' + VALUE)
        mark('original_shared_preferences_commit', saved_value=VALUE)
        adb.cmd('shell', 'am', 'force-stop', '--user', str(args.user), PACKAGE)
        require(not adb.cmd('shell', 'pidof', PACKAGE, allow_failure=True).strip(),
                'original app process remained after force-stop')
        mark('process_absent_after_force_stop')
        launch(VALUE)
        report['status'] = 'application_smoke_passed'
        report['android_application_smoke_qualified'] = True
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
    finally:
        if installed:
            try:
                current_user(adb, args.user)
                require(identity is not None and installed_identity(
                    adb, args.user, args.expected_apk_sha256) == identity,
                    'cleanup refused: installed package identity changed or was not established')
                adb.cmd('shell', 'am', 'force-stop', '--user', str(args.user), PACKAGE)
                result = adb.cmd('uninstall', '--user', str(args.user), PACKAGE)
                require(result.strip() == 'Success', 'new test package uninstall failed')
                absent_all_users(adb, args.user)
                mark('new_test_package_removed')
                report['cleanup'] = 'removed_verified_new_install'
            except Exception as exc:
                report['cleanup'] = 'refused_or_failed'
                report['cleanup_error'] = str(exc)
                report['status'] = 'failed'
                report['android_application_smoke_qualified'] = False
        for dump_path in dump_paths:
            try:
                adb.cmd('shell', 'rm', '-f', dump_path)
            except Exception as exc:
                report['ui_dump_cleanup_error'] = str(exc)
                report['status'] = 'failed'
                report['android_application_smoke_qualified'] = False
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=build.ROOT)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--apk', type=Path, required=True)
    for field in ('manifest', 'apk', 'source', 'certificate', 'adb'):
        parser.add_argument('--expected-' + field + '-sha256', required=True)
    parser.add_argument('--adb', type=Path, required=True)
    parser.add_argument('--adb-endpoint', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--expected-fingerprint', required=True)
    parser.add_argument('--user', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execute', action='store_true', help='install/run/clean up the new owned test app')
    args = parser.parse_args(argv)
    require(args.user >= 0, 'explicit nonnegative Android user required')
    endpoint(args.adb_endpoint)
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    recorder = Recorder(args.out)
    report = {'kind': 'a08_physical_android_original_dex', 'status': 'failed',
              'native_asterinas_qualified': False, 'production_owner_qualified': False,
              'mobile_organ_qualified': False, 'android_application_smoke_qualified': False,
              'device_os_classification': 'existing Android; not an Asterinas kernel qualification',
              'execute_requested': args.execute, 'serial': args.serial,
              'expected_fingerprint': args.expected_fingerprint, 'user': args.user,
              'adb_endpoint': args.adb_endpoint, 'runner_sha256': build.checksum(__file__)}
    try:
        report['host'] = host_gate(args, recorder)
        require(args.adb.is_absolute() and build.checksum(args.adb) == sha(args.expected_adb_sha256),
                'ADB executable digest mismatch')
        report['adb'] = {'path': str(args.adb), 'sha256': args.expected_adb_sha256}
        report['status'] = 'host_verified_not_executed'
        if args.execute:
            lifecycle(Adb(args, recorder), args, Path(report['host']['frozen_apk']), report)
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
    (args.out / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['status'] in ('application_smoke_passed', 'host_verified_not_executed') else 1


if __name__ == '__main__':
    sys.exit(main())
