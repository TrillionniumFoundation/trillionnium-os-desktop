#!/usr/bin/env python3
"""A08 artifact identity + complete Linux-Cuttlefish APK acceptance driver.

This only accepts the two Android 15 A08 smoke APKs produced by the same AOSP
checkout. It refuses incomplete, mismatched or swapped build artifacts BEFORE
invoking ADB. It does not qualify Android-on-Asterinas.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile
import subprocess
import sys

PKGS = {
    "dex_only": ("org.trillionnium.a08smoke", "A08Smoke"),
    "x86_64_jni": ("org.trillionnium.a08native", "A08NativeSmoke"),
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fd:
        for buf in iter(lambda: fd.read(1024 * 1024), b''):
            h.update(buf)
    return h.hexdigest()


def parse_badging(text: str) -> tuple[str, str, str]:
    line = next((x for x in text.splitlines() if x.startswith('package: ')), '')
    fields = {}
    for key in ('name', 'versionCode', 'versionName'):
        match = re.search(r"(?<!\w)" + key + r"='([^']+)'", line)
        if not match:
            raise ValueError('missing or malformed aapt2 package field ' + key)
        fields[key] = match.group(1)
    return fields['name'], fields['versionCode'], fields['versionName']


def validate_artifacts(manifest: Path, checkout: Path, aapt2: Path) -> dict:
    """Pure artifact checking; no ADB, Cuttlefish or kernel code is called."""
    out_root = (checkout.resolve() / 'out').resolve()
    if not out_root.is_dir():
        raise ValueError('AOSP out directory is absent; a real build is required')
    if not aapt2.is_file() or not aapt2.stat().st_mode & 0o111:
        raise ValueError('built host AAPT2 executable is absent')
    record = json.loads(manifest.read_text())
    if record.get('status') != 'artifacts_verified_NOT_installed_or_executed':
        raise ValueError('artifact manifest is not from completed build verification')
    if record.get('target_kernel') != 'Linux Cuttlefish reference, NOT Asterinas':
        raise ValueError('artifact manifest kernel scope inconsistent')
    validated = {}
    for key, (package, module) in PKGS.items():
        expected = record.get(key)
        if not isinstance(expected, dict):
            raise ValueError('missing required artifact: ' + key)
        path_value = expected.get('path')
        expected_sha = expected.get('sha256')
        if not isinstance(path_value, str) or not isinstance(expected_sha, str):
            raise ValueError('artifact path/hash absent for ' + key)
        path = Path(path_value)
        if not path.is_absolute():
            raise ValueError('artifact path must be absolute: ' + key)
        real = path.resolve()
        if not real.is_relative_to(out_root) or not real.is_file() or real.suffix != '.apk':
            raise ValueError('APK must be an existing regular file in this AOSP out tree')
        actual_sha = digest(real)
        if not re.fullmatch(r'[0-9a-f]{64}', expected_sha) or actual_sha != expected_sha:
            raise ValueError('artifact SHA256 mismatch for ' + key)
        # Verify actual APK ZIP/DEX and embedded ELF machine, independently
        # of the artifact JSON or the AAPT2 package name.
        try:
            with zipfile.ZipFile(real) as archive:
                names = archive.namelist()
                dex = [n for n in names if re.fullmatch(r"classes[0-9]*\.dex", n)]
                native = [n for n in names if re.fullmatch(r"lib/[^/]+/[^/]+\.so", n)]
                if not dex:
                    raise ValueError('APK missing DEX classes for ' + key)
                if key == 'dex_only':
                    if native:
                        raise ValueError('DEX-only artifact contains native ELF')
                else:
                    if native != ['lib/x86_64/liba08jni.so']:
                        raise ValueError('exactly one x86_64 JNI .so is required')
                    header = archive.read(native[0])[:20]
                    if (len(header) < 20 or header[:4] != b"\x7fELF" or
                            header[4] != 2 or header[5] != 1 or
                            struct.unpack_from('<H', header, 18)[0] != 62):
                        raise ValueError('JNI .so is not x86_64 ELF64 little-endian')
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ValueError('APK ZIP/native structure invalid for ' + key) from exc
        result = subprocess.run([str(aapt2), 'dump', 'badging', str(real)],
                                text=True, capture_output=True, timeout=30, check=False)
        if result.returncode:
            raise ValueError('aapt2 failed for ' + key + ': ' + result.stderr[-200:])
        observed = parse_badging(result.stdout)
        if observed != (package, '1', '1.0'):
            raise ValueError('package/version mismatch for ' + key + ': ' + str(observed))
        validated[key] = {'module': module, 'package': package, 'version': '1.0',
                          'path': str(real), 'sha256': actual_sha}
    if validated['dex_only']['sha256'] == validated['x86_64_jni']['sha256']:
        raise ValueError('distinct DEX and native APKs must not be identical')
    return {'scope': 'artifact_provenance_only', 'android_runtime_passed': False,
            'asterinas_runtime_passed': False, 'artifacts': validated}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--aosp-root', type=Path, required=True)
    p.add_argument('--aapt2', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--serial', help='ADB selector of disposable Cuttlefish ONLY')
    p.add_argument('--preflight-evidence', type=Path,
                   help='passing run_reference_cuttlefish preflight JSON (required for guest execution)')
    p.add_argument('--check-only', action='store_true', help='never invoke ADB')
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    output = {'schema': 1, 'scope': 'Linux Cuttlefish reference, NOT Asterinas',
              'status': 'not_executed', 'android_runtime_passed': False,
              'asterinas_runtime_passed': False, 'stages': []}
    report = args.out / 'result.json'
    try:
        stage = validate_artifacts(args.manifest, args.aosp_root, args.aapt2)
        output['artifacts'] = stage['artifacts']
        output['stages'].append({'name': 'artifact_identity', 'status': 'pass'})
        if args.check_only:
            output['status'] = 'artifacts_verified_no_guest_execution'
            return_code = 0
        else:
            if not args.serial or any(c.isspace() for c in args.serial):
                raise ValueError('explicit disposable Cuttlefish ADB transport required')
            if args.preflight_evidence is None:
                raise ValueError('passing --preflight-evidence is required for guest execution')
            preflight = args.preflight_evidence.resolve()
            if not preflight.is_file():
                raise ValueError('launch preflight evidence file is missing: ' + str(preflight))
            output['preflight_evidence'] = {'path': str(preflight),
                                            'sha256': digest(preflight)}
            tests_root = Path(__file__).resolve().parents[2] / 'tests/workloads/android'
            commands = [
                ('framework_boot', ['--serial', args.serial, '--out', str(args.out/'framework')],
                 'boot_gates.py'),
                ('dex_only', ['--serial', args.serial,
                              '--apk', stage['artifacts']['dex_only']['path'],
                              '--expected-sha256', stage['artifacts']['dex_only']['sha256'],
                              '--preflight-evidence', str(preflight),
                              '--out', str(args.out/'dex')], 'run_apk.py'),
                ('x86_64_jni', ['--serial', args.serial,
                                '--apk', stage['artifacts']['x86_64_jni']['path'],
                                '--expected-sha256', stage['artifacts']['x86_64_jni']['sha256'],
                                '--preflight-evidence', str(preflight),
                                '--out', str(args.out/'native')], 'run_native_apk.py'),
            ]
            for name, flags, script in commands:
                result = subprocess.run([sys.executable, str(tests_root/script), *flags],
                                        text=True, capture_output=True, timeout=900,
                                        check=False)
                stage = {'name': name, 'status': 'pass' if result.returncode == 0 else 'fail',
                         'exit': result.returncode,
                         'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(),
                         'stderr_sha256': hashlib.sha256(result.stderr.encode()).hexdigest()}
                output['stages'].append(stage)
                (args.out/(name+'-runner.log')).write_text(result.stdout + '\nSTDERR:\n' + result.stderr)
                if result.returncode:
                    raise RuntimeError(name+' failed with exit '+str(result.returncode))
            output['status'] = 'linux_reference_apks_passed_only'
            output['android_runtime_passed'] = True
            return_code = 0
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        output['status'] = 'blocked_or_failed'
        output['error'] = str(exc)
        return_code = 1
    finally:
        report.write_text(json.dumps(output, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'status': output['status'], 'scope': output['scope'],
                      'asterinas_runtime_passed': False, 'evidence': str(report)}))
    return return_code


if __name__ == '__main__':
    sys.exit(main())
