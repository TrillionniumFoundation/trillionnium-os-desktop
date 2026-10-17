#!/usr/bin/env python3
"""Capture evidence for real Android framework boot on disposable Linux Cuttlefish.

This does not assert Rust-kernel Android compatibility. The service list tool
exercises Binder userspace->kernel->servicemanager; pids alone are insufficient.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from run_apk import Adb, TestFailure, check_device


def measured(name: str, command: tuple, output: str, passed: bool, note: str = '') -> dict:
    return {'gate': name, 'command': list(command), 'status': 'pass' if passed else 'fail',
            'output_sha256': hashlib.sha256(output.encode()).hexdigest(),
            'output_sample': output[:256], 'note': note}


def run_boot_gates(adb: Adb, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    report = {'kind': 'a08_linux_cuttlefish_framework_boot',
              'native_asterinas_qualified': False, 'status': 'not_executed',
              'kernel_guest': 'Linux reference (not Asterinas)', 'gates': []}
    checked = False
    try:
        report['device'] = check_device(adb)
        checked = True
        def gate(name, argv, condition, note=''):
            output = adb.cmd(*argv, allow_failure=True)
            passed = bool(condition(output))
            report['gates'].append(measured(name, argv, output, passed, note))
            return output if passed else ''

        gate('init_pid_1', ('shell','cat','/proc/1/comm'),
             lambda value: value.strip() == 'init', 'PID 1 identified; init properties and mounts still need tests')
        gate('binder_servicemanager_roundtrip', ('shell','service','list'),
             lambda value: bool(re.search(r'\bactivity:\s*\[',value)) and
                           bool(re.search(r'\bpackage:\s*\[',value)),
             'Actual Binder service-manager IPC; does not prove fd/death/MAC conformance')
        gate('zygote64_process', ('shell','pidof','zygote64'),
             lambda value: bool(re.fullmatch(r'\d+(?:\s+\d+)*', value.strip())))
        gate('system_server_process', ('shell','pidof','system_server'),
             lambda value: bool(re.fullmatch(r'\d+(?:\s+\d+)*', value.strip())))
        # apex_manifest.json is an APEX package-input manifest, not a reliable
        # file in the *mounted payload*. Verify the actual runtime libart ELF.
        gate('art_runtime_library_accessible',
             ('shell','sh','-c',
              'test -r /apex/com.android.art/lib64/libart.so && echo A08_ART_LIB_PRESENT'),
             lambda value: value.strip() == 'A08_ART_LIB_PRESENT',
             'Mounted ART library accessible; does NOT prove ART/JIT execution')
        gate('package_manager_query', ('shell','cmd','package','list','packages'),
             lambda value: 'package:com.android.shell' in value,
             'Requires system_server PackageManager binder roundtrip')
        gate('surfaceflinger_process', ('shell','pidof','surfaceflinger'),
             lambda value: bool(re.fullmatch(r'\d+(?:\s+\d+)*',value.strip())),
             'Process existence does not prove graphics buffers/HWC/IME/display usability')
        gate('lmkd_process', ('shell','pidof','lmkd'),
             lambda value: bool(re.fullmatch(r'\d+(?:\s+\d+)*',value.strip())),
             'Process existence does not prove PSI/cgroups, freezer or reclamation')
        gate('framework_boot_completed', ('shell','getprop','sys.boot_completed'),
             lambda value: value.strip() == '1',
             'Framework reported boot complete; application/JNI still require separate tests')
        gate('selinux_enforcing', ('shell','getenforce'),
             lambda value: value.strip() == 'Enforcing',
             'Policy effectiveness and negative MAC tests are still required')
        report['status'] = 'pass' if all(g['status']=='pass' for g in report['gates']) else 'fail'
        report['classification'] = None if report['status']=='pass' else next(
            g['gate'] for g in report['gates'] if g['status']!='pass')
    except (OSError, TestFailure, subprocess.TimeoutExpired) as ex:
        report['status'] = 'fail';report['classification'] = 'device_identity' if not checked else 'transport'
        report['error'] = str(ex)
    finally:
        if checked:
            try:
                raw = adb.cmd('logcat','-d','-v','threadtime','-t','2000',timeout=45)
                (out/'android-boot-logcat.txt').write_text(raw)
                report['logcat_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
            except (OSError, TestFailure, subprocess.TimeoutExpired) as ex:
                report['logcat_error'] = str(ex)
        (out/'boot-gates.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


def main(argv=None) -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--serial',required=True)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args(argv)
    report=run_boot_gates(Adb(args.serial),args.out)
    print(json.dumps({'status':report['status'], 'classification':report.get('classification'),
                      'gates':len(report['gates'])}))
    return 0 if report['status']=='pass' else 1

if __name__=='__main__':
    sys.exit(main())
