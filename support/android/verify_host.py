#!/usr/bin/env python3
"""One-command, read-only host gate; never claims Android/Asterinas success.

Runs real Linux ABI probes and actual Java/JNI host loading in temporary files.
Captures subprocess exit codes and SHA256 transcripts for later review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / 'tests/workloads/android'


def record(name: str, command: list[str], *, cwd=ROOT, timeout=120) -> dict:
    try:
        run = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                             timeout=timeout, check=False)
        return {'name': name, 'command': command, 'exit': run.returncode,
                'stdout': run.stdout[-3000:], 'stderr': run.stderr[-3000:],
                'stdout_sha256': hashlib.sha256(run.stdout.encode()).hexdigest(),
                'stderr_sha256': hashlib.sha256(run.stderr.encode()).hexdigest()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'name': name, 'command': command, 'exit': None,
                'status': 'execution_blocked', 'error': str(exc)}


def analyze_probe(test: dict, *, allow_binder_block: bool = False) -> str:
    if test['exit'] is None:
        return 'blocked_environment'
    if allow_binder_block and test['exit'] == 77 and 'binder_device_open\tBLOCKED' in test['stdout']:
        return 'binder_blocked_no_device'
    return 'passed' if test['exit'] == 0 else 'failed'


def run_host() -> dict:
    report = {
        'schema': 1,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'host': {'platform': platform.platform(), 'machine': platform.machine(),
                 'python': sys.version.split()[0]},
        'scope': 'LINUX_HOST_ONLY',
        'native_asterinas_qualified': False,
        'android_reference_boot': 'not_executed',
        'android_apk_runtime': 'not_executed',
        'aosp_product_build': 'not_executed',
        'operations': [],
    }

    def add(operation, status=None):
        operation['status'] = status or analyze_probe(operation)
        report['operations'].append(operation)
        return operation['status']

    with tempfile.TemporaryDirectory(prefix='a08-host-') as td:
        tmp = Path(td)
        add(record('source_integrity', [sys.executable,
                   str(ROOT/'support/android/verify_source_integrity.py')]))
        unit = record('offline_unit_tests', [sys.executable, '-m', 'unittest', 'discover',
                     '-s', str(TESTS), '-p', 'test_*.py', '-v'])
        add(unit)
        unit_result = re.search(r'Ran (\d+) tests?', unit.get('stderr', ''))
        report['unit_test_count'] = int(unit_result.group(1)) if unit_result else None

        for name, file, extra in (
            ('kernel_abi', TESTS/'kernel_abi_probe.c', ['-pthread']),
            ('binder_abi', TESTS/'binder_abi_probe.c', []),
            ('binder_uapi_layout', TESTS/'binder_uapi_layout.c', []),
            ('seccomp_abi', TESTS/'seccomp_abi_probe.c', []),
        ):
            target = tmp/name
            compile_result = record('compile_'+name,
                ['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',*extra,str(file),'-o',str(target)])
            status = add(compile_result)
            if status != 'passed':
                continue
            probe = record('execute_'+name, [str(target)])
            add(probe, analyze_probe(probe, allow_binder_block=name == 'binder_abi'))

        javac = shutil.which('javac')
        java = shutil.which('java')
        if javac and java:
            java_home = Path(javac).resolve().parent.parent
            headers = [java_home/'include', java_home/'include/linux']
            if all((hdr if hdr.name != 'include' else hdr/'jni.h').exists() for hdr in headers):
                lib = tmp/'liba08jni.so'
                jni = record('compile_host_jni', ['cc','-std=c11','-O2','-Wall','-Wextra',
                    '-Werror','-fPIC','-shared',
                    *[f'-I{x}' for x in headers],
                    str(TESTS/'apk-smoke/native-smoke/jni/a08jni.c'),'-o',str(lib)])
                if add(jni) == 'passed':
                    classes = tmp/'classes'
                    classes.mkdir()
                    jcomp = record('compile_java_jni_harness',
                        [javac,'-d',str(classes),str(TESTS/'host_jni/MainActivity.java')])
                    if add(jcomp) == 'passed':
                        java_run = record('execute_real_host_jni', [java,
                            f'-Djava.library.path={tmp}', '-cp', str(classes),
                            'org.trillionnium.a08native.MainActivity'])
                        status = analyze_probe(java_run)
                        if status == 'passed' and 'HOST_JNI_INTEGRATION_PASS' not in java_run.get('stdout',''):
                            status = 'failed_missing_jni_success_marker'
                        add(java_run, status)
            else:
                report['operations'].append({'name':'java_jni', 'status':'blocked_missing_jni_headers'})
        else:
            report['operations'].append({'name':'java_jni', 'status':'blocked_missing_java_tools'})

    # The imported Asterinas source gate is an independently classified RED
    # target contract. A successful Linux-host probe never closes a Binder,
    # seccomp, MAC, or Android-on-Asterinas requirement.
    kernel_root = ROOT / 'kernel/asterinas'
    kernel_lock = ROOT / 'support/upstream-lock.json'
    if (kernel_root / 'kernel/core/src/syscall/mod.rs').is_file() and kernel_lock.is_file():
        with tempfile.TemporaryDirectory(prefix='a08-contract-') as td:
            evidence = Path(td) / 'kernel-source.json'
            invocation = record('kernel_source_contract',
                [sys.executable, str(ROOT/'support/android/kernel_contract.py'),
                 '--kernel-root', str(kernel_root),
                 '--lock', str(kernel_lock), '--out', str(evidence)])
            if evidence.is_file():
                doc = json.loads(evidence.read_text())
                report['asterinas_source_gate'] = {
                    'status': doc.get('status'),
                    'blocking_requirements': doc.get('blocking_requirements', []),
                    'source_scan_exit': invocation['exit'],
                    'kernel_runtime_verified': False,
                    'android_runtime_verified': False,
                }
            else:
                report['asterinas_source_gate'] = {
                    'status': 'source_scan_failed_or_unavailable',
                    'source_scan_exit': invocation['exit'],
                    'kernel_runtime_verified': False,
                    'android_runtime_verified': False,
                }
    else:
        report['asterinas_source_gate'] = {
            'status': 'kernel_checkout_not_available',
            'kernel_runtime_verified': False,
            'android_runtime_verified': False,
        }

    statuses = [op['status'] for op in report['operations']]
    report['host_gates_passed'] = all(status == 'passed' or status == 'binder_blocked_no_device'
                                      for status in statuses)
    report['unqualified_or_blocked'] = [op['name'] for op in report['operations']
                                         if op['status'] != 'passed']
    # A completely successful host gate is NOT an Android runtime pass.
    report['status'] = 'host_passed_only' if report['host_gates_passed'] else 'host_failed_or_blocked'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    report = run_host()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'scope': report['scope'], 'status': report['status'],
                      'unit_test_count': report['unit_test_count'],
                      'not_passed_gates': report['unqualified_or_blocked']}))
    return 0 if report['host_gates_passed'] else 1

if __name__ == '__main__':
    sys.exit(main())
