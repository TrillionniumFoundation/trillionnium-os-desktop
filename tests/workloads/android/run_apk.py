#!/usr/bin/env python3
"""Read-only guest identity gate, then isolated A08Smoke APK lifecycle via ADB.

The target MUST be a disposable x86_64 Cuttlefish Android/Linux reference
instance. The resulting report is NEVER Android-on-Asterinas validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

PACKAGE = 'org.trillionnium.a08smoke'
ACTIVITY = PACKAGE + '/.MainActivity'
VALUE = 'A08Persist42'
EXPECTED = {'ro.product.name': 'aosp_cf_x86_64_phone',
            'ro.product.device': 'vsoc_x86_64',
            'ro.product.cpu.abi': 'x86_64',
            'ro.build.id': 'BP1A.250505.005.D1',
            'ro.build.version.release': '15'}
PREFLIGHT_KIND = 'a08_cuttlefish_reference_launch_integrity'
PREFLIGHT_KERNEL = 'Linux Cuttlefish reference, NOT Asterinas'
PREFLIGHT_AUDITS = (
    'manifest-audit.json',
    'source-audit.json',
    'product-source-launch-audit.json',
    'image-audit.json',
    'vintf-compatibility.json',
)


class TestFailure(Exception):
    pass


def checksum(path: Path) -> str:
    dig = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            dig.update(data)
    return dig.hexdigest()


def load_preflight_evidence(path: Path) -> dict:
    """Validate the immutable launch-preflight bundle before any ADB write.

    The bundle is metadata from ``run_reference_cuttlefish.sh``.  Its
    ``preflight_only`` status does not prove that a guest booted; the device
    identity and framework boot gates remain separate checks.
    """
    path = path.resolve()
    if not path.is_file():
        raise TestFailure(f'launch preflight evidence is missing: {path}')
    try:
        record = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TestFailure(f'invalid launch preflight evidence: {path}') from exc
    if not isinstance(record, dict):
        raise TestFailure(f'invalid launch preflight evidence: {path}')
    if (record.get('kind') != PREFLIGHT_KIND or
            record.get('kernel') != PREFLIGHT_KERNEL or
            record.get('status') != 'preflight_only' or
            record.get('guest_boot_verified') is not False or
            record.get('android_on_asterinas_verified') is not False or
            record.get('errors') != []):
        raise TestFailure('launch preflight evidence is not a passing reference-only bundle')
    audits = record.get('audit_reports')
    if not isinstance(audits, dict):
        raise TestFailure('launch preflight evidence has no audit report inventory')
    bundle = path.parent
    observed = {}
    for filename in PREFLIGHT_AUDITS:
        expected = audits.get(filename)
        audit_path = bundle / filename
        if (not isinstance(expected, str) or
                not re.fullmatch(r'[0-9a-f]{64}', expected) or
                not audit_path.is_file()):
            raise TestFailure(f'launch preflight audit is missing or malformed: {filename}')
        actual = checksum(audit_path)
        if actual != expected:
            raise TestFailure(f'launch preflight audit changed after verification: {filename}')
        observed[filename] = actual
    launcher_sha = record.get('launcher_sha256')
    if not isinstance(launcher_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', launcher_sha):
        raise TestFailure('launch preflight launcher hash is missing or malformed')
    return {
        'path': str(path),
        'sha256': checksum(path),
        'status': record['status'],
        'kernel': record['kernel'],
        'guest_boot_verified': False,
        'android_on_asterinas_verified': False,
        'audit_reports': observed,
        'launcher_sha256': launcher_sha,
    }


def apk_metadata(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        dex = sorted(n for n in names if re.fullmatch(r'classes\d*\.dex', n))
        libraries = sorted(n for n in names if re.fullmatch(r'lib/[^/]+/[^/]+\.so', n))
        return {'path': str(path), 'sha256': checksum(path), 'bytes': path.stat().st_size,
                'classes_dex': dex, 'native_libraries': libraries,
                'abis': sorted({n.split('/')[1] for n in libraries}),
                'expected_package_from_fixture_source': PACKAGE,
                'expected_version_from_fixture_source': '1.0',
                'declared_manifest_runtime_verified': False,
                'source': 'tests/workloads/android/apk-smoke'}


def bounds_center(raw: str) -> tuple[int, int]:
    m = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', raw or '')
    if not m:
        raise TestFailure('UI element bounds missing/invalid')
    left, top, right, bottom = map(int, m.groups())
    if right <= left or bottom <= top:
        raise TestFailure('UI element has empty bounds')
    return (left + right) // 2, (top + bottom) // 2


def find_node(xml: str, resource: str):
    tree = ET.fromstring(xml)
    return next((node for node in tree.iter('node')
                 if node.get('resource-id') == PACKAGE + ':id/' + resource), None)


class Adb:
    def __init__(self, serial: str):
        if not serial or any(c.isspace() for c in serial):
            raise TestFailure('explicit ADB serial must be non-empty and contain no whitespace')
        self.serial = serial

    def cmd(self, *args: str, timeout: int = 60, allow_failure: bool = False) -> str:
        run = subprocess.run(['adb', '-s', self.serial, *args], text=True,
                             capture_output=True, timeout=timeout, check=False)
        if run.returncode and not allow_failure:
            raise TestFailure(f'adb {args!r}: rc={run.returncode}; stderr={run.stderr[-500:]}')
        return run.stdout


def check_device(adb: Adb) -> dict:
    # An ADB TCP transport selector (e.g. localhost:6520) is NOT necessarily
    # the guest-reported serial number. The selector is already enforced with
    # `adb -s`, so reject offline/unknown state rather than comparing strings.
    if adb.cmd('get-state').strip() != 'device':
        raise TestFailure('selected ADB transport is not online')
    reported_serial = adb.cmd('get-serialno').strip()
    if reported_serial in ('', 'unknown', 'offline'):
        raise TestFailure('selected ADB transport has no valid guest serial')
    measured = {key: adb.cmd('shell', 'getprop', key).strip() for key in EXPECTED}
    measured['adb_transport_selector'] = adb.serial
    measured['guest_reported_serial'] = reported_serial
    measured['ro.hardware'] = adb.cmd('shell', 'getprop', 'ro.hardware').strip()
    measured['ro.build.fingerprint'] = adb.cmd('shell', 'getprop', 'ro.build.fingerprint').strip()
    measured['ro.build.version.sdk'] = adb.cmd('shell', 'getprop', 'ro.build.version.sdk').strip()
    measured['page_size'] = adb.cmd('shell', 'getconf', 'PAGESIZE').strip()
    measured['kernel_uname'] = adb.cmd('shell', 'uname', '-a').strip()
    for prop, expected in EXPECTED.items():
        if measured[prop] != expected:
            raise TestFailure(f'refusing non-Cuttlefish target: {prop}={measured[prop]!r}')
    if measured['page_size'] != '4096':
        raise TestFailure(f'unsupported page size: {measured["page_size"]}')
    if not measured['ro.hardware'].startswith(('cutf', 'vsoc')):
        raise TestFailure('unexpected Cuttlefish hardware identifier; refusing install')
    if not measured['kernel_uname'].startswith('Linux '):
        raise TestFailure('reference is not a Linux guest; this runner is Linux-only')
    if not measured['ro.build.version.sdk'].isdigit() or int(measured['ro.build.version.sdk']) != 35:
        raise TestFailure('reference guest is not Android 15 (SDK 35)')
    return measured


def ui_snapshot(adb: Adb) -> str:
    adb.cmd('shell', 'uiautomator', 'dump', '/sdcard/a08-window.xml', timeout=45)
    return adb.cmd('exec-out', 'cat', '/sdcard/a08-window.xml', timeout=45)


def until_ui(adb: Adb, resource: str, expected_text: str | None = None,
             absent: bool = False, timeout: float = 12.0):
    deadline = time.monotonic() + timeout
    last = ''
    while time.monotonic() < deadline:
        try:
            last = ui_snapshot(adb)
            node = find_node(last, resource)
            if absent and node is None:
                return None
            if not absent and node is not None and (
                    expected_text is None or node.get('text') == expected_text):
                return node
        except (TestFailure, ET.ParseError) as ex:
            last = str(ex)
        time.sleep(0.3)
    raise TestFailure(f'UI timeout resource={resource} expected={expected_text!r} absent={absent}; last={last[-300:]}')


def tap(adb: Adb, resource: str):
    element = until_ui(adb, resource)
    x, y = bounds_center(element.get('bounds'))
    adb.cmd('shell', 'input', 'tap', str(x), str(y))


def launch(adb: Adb):
    output = adb.cmd('shell', 'am', 'start', '-W', '--user', '0', '-n', ACTIVITY)
    if 'Status: ok' not in output or PACKAGE not in output:
        raise TestFailure('Activity launch not confirmed: ' + output[-500:])


def run_workload(apk: Path, adb: Adb, out: Path, expected_sha256: str | None = None,
                 preflight_evidence: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    report = {'kind': 'a08_linux_cuttlefish_reference_apk',
              'native_asterinas_qualified': False, 'status': 'not_executed',
              'classification': None, 'steps': [], 'guest': {}}
    phase = 'host_precondition'
    device_checked = False

    def step(name, action):
        nonlocal phase
        phase = name
        start = time.monotonic()
        res = action()
        report['steps'].append({'name': name, 'status': 'pass',
                                'elapsed_s': round(time.monotonic() - start, 3)})
        return res

    try:
        if not apk.is_file():
            raise TestFailure(f'APK missing: {apk}')
        report['apk'] = apk_metadata(apk)
        if not report['apk']['classes_dex'] or report['apk']['native_libraries']:
            raise TestFailure('A08Smoke APK must contain DEX and no native .so libraries')
        if expected_sha256 and report['apk']['sha256'] != expected_sha256.lower():
            raise TestFailure('expected APK SHA256 mismatch; refusing install')
        if preflight_evidence is not None:
            report['preflight'] = load_preflight_evidence(preflight_evidence)
        report['guest'] = step('device_identity', lambda: check_device(adb))
        device_checked = True
        # No writes happen before the disposable-guest identity gate above.
        def install():
            result = adb.cmd('install', '-r', '-t', str(apk), timeout=180)
            if 'Success' not in result:
                raise TestFailure('adb install did not report success: ' + result[-400:])
        step('install', install)
        def verify_installed():
            if ('package:' not in adb.cmd('shell', 'pm', 'path', PACKAGE)):
                raise TestFailure('PackageManager does not resolve installed test package')
        step('package_manager', verify_installed)
        def reset():
            result = adb.cmd('shell', 'pm', 'clear', PACKAGE)
            if 'Success' not in result:
                raise TestFailure('failed to clear prior test-only app data')
        step('clear_prior_app_data', reset)
        step('launch', lambda: launch(adb))
        step('verify_empty_initial_state', lambda: until_ui(adb, 'saved_value', 'SAVED:EMPTY'))
        def enter_and_save():
            tap(adb, 'input_value')
            adb.cmd('shell', 'input', 'text', VALUE)
            tap(adb, 'save_button')
            until_ui(adb, 'saved_value', 'SAVED:' + VALUE)
        step('input_and_persist', enter_and_save)
        def background():
            adb.cmd('shell', 'input', 'keyevent', 'KEYCODE_HOME')
            until_ui(adb, 'saved_value', absent=True)
        step('background_verified', background)
        step('foreground', lambda: launch(adb))
        step('foreground_state', lambda: until_ui(adb, 'saved_value', 'SAVED:' + VALUE))
        def stop_and_check():
            adb.cmd('shell', 'am', 'force-stop', PACKAGE)
            pid = None
            for _ in range(20):
                pid = adb.cmd('shell', 'pidof', PACKAGE, allow_failure=True).strip()
                if not pid:
                    return
                time.sleep(0.1)
            raise TestFailure('A08Smoke still running after force-stop: ' + str(pid))
        step('force_stop', stop_and_check)
        step('relaunch', lambda: launch(adb))
        step('persist_across_restart', lambda: until_ui(adb, 'saved_value', 'SAVED:' + VALUE))
        step('final_exit', stop_and_check)
        report['status'] = 'pass'
    except (OSError, subprocess.TimeoutExpired, TestFailure, zipfile.BadZipFile,
            ET.ParseError) as ex:
        report['status'] = 'fail'
        report['classification'] = phase
        report['error'] = str(ex)
    finally:
        if device_checked:
            try:
                (out / 'logcat.txt').write_text(adb.cmd('logcat', '-d', '-v', 'threadtime',
                                                       '-t', '1500', timeout=45))
            except (OSError, subprocess.TimeoutExpired, TestFailure) as ex:
                report['logcat_error'] = str(ex)
        (out / 'result.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apk', required=True, type=Path)
    parser.add_argument('--serial', required=True, help='explicit disposable Cuttlefish ADB serial')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--expected-sha256', help='optional strict verified artifact hash')
    parser.add_argument('--preflight-evidence', required=True, type=Path,
                        help='passing run_reference_cuttlefish preflight bundle')
    args = parser.parse_args(argv)
    report = run_workload(args.apk, Adb(args.serial), args.out, args.expected_sha256,
                          args.preflight_evidence)
    print(json.dumps({'status': report['status'],
                      'classification': report['classification'], 'out': str(args.out)}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
