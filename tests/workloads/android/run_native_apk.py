#!/usr/bin/env python3
"""Android 15 x86_64 JNI APK lifecycle on an explicit disposable Linux Cuttlefish.

NOT an Asterinas conformance test. No CPU translation/Native Bridge is presumed.
The on-device UI reports success only after calling two real JNI exports from
liba08jni.so and checking that native PID == Android Process.myPid().
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

from run_apk import (Adb, TestFailure, apk_metadata, bounds_center, check_device,
                     load_preflight_evidence)

PACKAGE = 'org.trillionnium.a08native'
ACTIVITY = PACKAGE + '/.MainActivity'
LIBRARY = 'lib/x86_64/liba08jni.so'
VALUE = 'A08NativePersist42'


def inspect_native_apk(apk: Path) -> dict:
    """Validate DEX and an actual x86_64 ELF JNI library, not just an ABI name."""
    record = apk_metadata(apk)
    with zipfile.ZipFile(apk) as archive:
        names = [item.filename for item in archive.infolist()]
        if names.count(LIBRARY) != 1 or record['native_libraries'] != [LIBRARY]:
            raise TestFailure('exactly one embedded lib/x86_64/liba08jni.so is required')
        if not record['classes_dex']:
            raise TestFailure('native APK missing DEX classes')
        with archive.open(LIBRARY) as lib:
            header = lib.read(20)
        if (len(header) < 20 or header[:4] != b'\x7fELF' or header[4] != 2 or
                header[5] != 1 or struct.unpack_from('<H', header, 18)[0] != 62):
            raise TestFailure('embedded .so is not ELF64 little-endian EM_X86_64')
    record['package'] = PACKAGE
    record['version_from_fixture_source'] = '1.0'
    record['expected_jni_exports'] = [
        'Java_org_trillionnium_a08native_MainActivity_nativeIsa',
        'Java_org_trillionnium_a08native_MainActivity_nativePid',
    ]
    return record


def snapshot(adb: Adb) -> str:
    adb.cmd('shell', 'uiautomator', 'dump', '/sdcard/a08-native-window.xml', timeout=45)
    return adb.cmd('exec-out', 'cat', '/sdcard/a08-native-window.xml', timeout=45)


def wait_node(adb: Adb, resource: str, text: str | None = None,
              absent: bool = False, timeout: float = 15.0):
    deadline = time.monotonic() + timeout
    last = ''
    while time.monotonic() < deadline:
        try:
            raw = snapshot(adb)
            root = ET.fromstring(raw)
            node = next((n for n in root.iter('node')
                         if n.get('resource-id') == PACKAGE + ':id/' + resource), None)
            if absent and node is None:
                return None
            if not absent and node is not None and (text is None or node.get('text') == text):
                return node
            last = raw[-300:]
        except (ET.ParseError, TestFailure) as exc:
            last = str(exc)
        time.sleep(0.3)
    raise TestFailure('native UI timeout: ' + resource + ' ' + str(text) + '; ' + last)


def tap(adb: Adb, resource: str):
    point = bounds_center(wait_node(adb, resource).get('bounds'))
    adb.cmd('shell', 'input', 'tap', str(point[0]), str(point[1]))


def launch(adb: Adb):
    output = adb.cmd('shell', 'am', 'start', '-W', '--user', '0', '-n', ACTIVITY)
    if 'Status: ok' not in output or PACKAGE not in output:
        raise TestFailure('Native Activity launch unconfirmed: ' + output[-500:])


def stop(adb: Adb):
    adb.cmd('shell', 'am', 'force-stop', PACKAGE)
    for _ in range(20):
        if not adb.cmd('shell', 'pidof', PACKAGE, allow_failure=True).strip():
            return
        time.sleep(0.1)
    raise TestFailure('Native package process still running after force-stop')


def run_native(apk: Path, adb: Adb, out: Path,
               expected_sha256: str | None = None,
               preflight_evidence: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    report = {'kind': 'a08_linux_cuttlefish_x86_64_native_apk', 'status': 'not_executed',
              'native_asterinas_qualified': False, 'native_bridge_used': False,
              'steps': [], 'classification': None}
    phase = 'host_precondition'
    guest_checked = False

    def step(name, action):
        nonlocal phase
        phase = name
        started = time.monotonic()
        result = action()
        report['steps'].append({'name': name, 'status': 'pass',
                                'elapsed_s': round(time.monotonic() - started, 3)})
        return result

    try:
        report['apk'] = inspect_native_apk(apk)
        if expected_sha256 and report['apk']['sha256'] != expected_sha256.lower():
            raise TestFailure('native APK hash mismatch before ADB writes')
        if preflight_evidence is not None:
            report['preflight'] = load_preflight_evidence(preflight_evidence)
        report['guest'] = step('device_identity', lambda: check_device(adb))
        guest_checked = True

        def install():
            result = adb.cmd('install', '-r', '-t', str(apk), timeout=180)
            if 'Success' not in result:
                raise TestFailure('native APK installation not confirmed')
        step('install', install)
        step('package_manager', lambda: ensure_package(adb))
        step('clear_prior_data', lambda: ensure_clear(adb))
        step('launch', lambda: launch(adb))
        step('jni_isa_and_pid', lambda: wait_node(adb, 'native_status', 'JNI:x86_64:PID_MATCH'))
        step('initial_empty', lambda: wait_node(adb, 'saved_value', 'SAVED:EMPTY'))

        def enter():
            tap(adb, 'input_value')
            adb.cmd('shell', 'input', 'text', VALUE)
            tap(adb, 'save_button')
            wait_node(adb, 'saved_value', 'SAVED:' + VALUE)
        step('input_and_save', enter)
        def background():
            adb.cmd('shell', 'input', 'keyevent', 'KEYCODE_HOME')
            wait_node(adb, 'native_status', absent=True)
        step('background', background)
        step('foreground', lambda: launch(adb))
        step('foreground_native_and_state', lambda: (
            wait_node(adb, 'native_status', 'JNI:x86_64:PID_MATCH'),
            wait_node(adb, 'saved_value', 'SAVED:' + VALUE)))
        step('force_stop', lambda: stop(adb))
        step('relaunch', lambda: launch(adb))
        step('relaunch_native_and_persistence', lambda: (
            wait_node(adb, 'native_status', 'JNI:x86_64:PID_MATCH'),
            wait_node(adb, 'saved_value', 'SAVED:' + VALUE)))
        step('exit', lambda: stop(adb))
        report['status'] = 'pass'
    except (OSError, TestFailure, zipfile.BadZipFile, subprocess.TimeoutExpired,
            ET.ParseError, ValueError) as exc:
        report['status'] = 'fail'; report['classification'] = phase
        report['error'] = str(exc)
    finally:
        if guest_checked:
            try:
                (out / 'native-logcat.txt').write_text(adb.cmd(
                    'logcat', '-d', '-v', 'threadtime', '-t', '1500', timeout=45))
            except (OSError, subprocess.TimeoutExpired, TestFailure) as exc:
                report['logcat_error'] = str(exc)
        (out / 'result.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def ensure_package(adb: Adb):
    if ('package:' not in adb.cmd('shell', 'pm', 'path', PACKAGE)):
        raise TestFailure('Native APK not registered by PackageManager')


def ensure_clear(adb: Adb):
    if 'Success' not in adb.cmd('shell', 'pm', 'clear', PACKAGE):
        raise TestFailure('Unable to clear native APK prior data')


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--apk', type=Path, required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--expected-sha256')
    p.add_argument('--preflight-evidence', required=True, type=Path,
                   help='passing run_reference_cuttlefish preflight bundle')
    args = p.parse_args(argv)
    result = run_native(args.apk, Adb(args.serial), args.out, args.expected_sha256,
                        args.preflight_evidence)
    print(json.dumps({'status': result['status'], 'classification': result['classification']}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
