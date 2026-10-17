#!/usr/bin/env python3
"""Read-only VINTF compatibility check with the *built* AOSP checkvintf tool.

Success is scoped to the recorded partition metadata. It is not a Binder,
HAL service, kernel driver, Android boot, CTS, or Asterinas qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PARTITIONS = ('system', 'vendor', 'odm', 'product', 'system_ext')
HEX = re.compile(r'^[0-9a-f]{64}$')


def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inventory(root: Path, *, allowed_root: Path | None = None,
              required_framework_levels: tuple[str, ...] = ()) -> tuple[dict, list[str]]:
    """Select VINTF XML under explicit partitions, without following escapes."""
    files: dict[str, dict] = {}
    errors = []
    for name in PARTITIONS:
        folder = root / name / 'etc' / 'vintf'
        if not folder.exists():
            continue
        if not folder.is_dir():
            errors.append(f'not a VINTF directory: {name}')
            continue
        for pattern in ('manifest*.xml', 'manifest/*.xml',
                        'compatibility_matrix*.xml', 'compatibility_matrix/*.xml'):
            for entry in folder.glob(pattern):
                real = entry.resolve()
                if not real.is_relative_to((allowed_root or root).resolve()):
                    errors.append(f'VINTF symlink escapes PRODUCT_OUT: {entry}')
                    continue
                if not real.is_file():
                    errors.append(f'VINTF entry is not a file: {entry}')
                    continue
                rel = entry.relative_to(root).as_posix()
                files[rel] = {'path': rel, 'sha256': checksum(real),
                              'bytes': real.stat().st_size}
    vendor = [x for x in files if x.startswith(('vendor/', 'odm/')) and
              ('/manifest' in x)]
    framework = [x for x in files if x.startswith(('system/', 'system_ext/')) and
                 '/compatibility_matrix' in x]
    if not vendor:
        errors.append('vendor or odm device VINTF manifest is missing')
    if not framework:
        errors.append('framework VINTF compatibility matrix is missing')
    for level in required_framework_levels:
        suffix = f'compatibility_matrix.{level}.xml'
        if not any(path.endswith(suffix) for path in framework):
            errors.append(f'required framework VINTF compatibility matrix {level} is missing')
    return dict(sorted(files.items())), errors


def verify(aosp_root: Path, product_out: Path, tool: Path,
           apex_info_file: Path | None = None,
           required_framework_levels: tuple[str, ...] = ()) -> dict:
    root = aosp_root.resolve()
    product = product_out.resolve()
    executable = tool.resolve()
    report = {
        'schema': 1, 'kind': 'a08_aosp_vintf_metadata_compatibility',
        'status': 'blocked_or_failed',
        'aosp_root': str(root), 'product_out': str(product),
        'tool': str(executable), 'scope': 'AOSP_BUILT_PARTITION_METADATA_ONLY',
        'android_framework_boot_verified': False,
        'kernel_vintf_requirements_verified': False,
        'aidl_hal_services_running_verified': False,
        'android_on_asterinas_verified': False,
        'errors': [], 'vintf_files': {}, 'mapped_partitions': {},
        'apex_metadata_included': False,
        'required_framework_matrix_levels': list(required_framework_levels),
    }
    errors: list[str] = report['errors']
    try:
        if not root.is_dir() or not (root / '.repo').is_dir():
            raise ValueError('not an initialized AOSP checkout')
        if not product.is_relative_to(root / 'out' / 'target' / 'product'):
            raise ValueError('PRODUCT_OUT must be under checkout/out/target/product')
        if not executable.is_relative_to(root / 'out' / 'host'):
            raise ValueError('checkvintf executable must originate under same-source AOSP out/host')
        if not executable.is_file() or not executable.stat().st_mode & 0o111:
            raise ValueError('checkvintf host binary is missing or not executable')
        report['tool_sha256'] = checksum(executable)
        files, problems = inventory(product, allowed_root=root / 'out',
                                    required_framework_levels=required_framework_levels)
        report['vintf_files'] = files
        errors.extend(problems)
        for partition in PARTITIONS:
            candidate = product / partition
            if candidate.is_dir():
                path = candidate.resolve()
                if not path.is_relative_to(root / 'out'):
                    errors.append(f'{partition} partition escaped build out/ directory')
                    continue
                report['mapped_partitions']['/' + partition] = str(path)
        if '/vendor' not in report['mapped_partitions'] or '/system' not in report['mapped_partitions']:
            errors.append('system and vendor partition directories are required')
        if apex_info_file is not None:
            # android-15 checkvintf reads /apex/apex-info-list.xml through its
            # --dirmap filesystem. --apex-info-file was removed upstream, so
            # the wrapper accepts this input path but NEVER forwards that flag.
            apex_info = apex_info_file.resolve()
            if (not apex_info.is_file() or
                    not apex_info.is_relative_to(root / 'out') or
                    apex_info.name != 'apex-info-list.xml'):
                errors.append('APEX info file must be apex-info-list.xml within AOSP build out')
            else:
                report['apex_info_path'] = str(apex_info)
                report['apex_info_sha256'] = checksum(apex_info)
                report['apex_metadata_included'] = True
                report['mapped_partitions']['/apex'] = str(apex_info.parent)
        if errors:
            return report
        command = [str(executable), '--check-compat']
        for partition, directory in sorted(report['mapped_partitions'].items()):
            command += ['--dirmap', partition + ':' + directory]
        # Intentionally NO --apex-info-file here: it is not supported by
        # Android 15's checkvintf; /apex is already in mapped_partitions.
        report['command'] = command
        proc = subprocess.run(command, capture_output=True, text=True,
                              check=False, timeout=120)
        report['exit_code'] = proc.returncode
        report['stdout'] = proc.stdout
        report['stderr'] = proc.stderr
        report['stdout_sha256'] = hashlib.sha256(proc.stdout.encode()).hexdigest()
        report['stderr_sha256'] = hashlib.sha256(proc.stderr.encode()).hexdigest()
        if proc.returncode != 0:
            errors.append(f'checkvintf returned nonzero exit code {proc.returncode}')
            return report
        if re.search(r'\bINCOMPATIBLE\b', proc.stdout + "\n" + proc.stderr):
            errors.append('checkvintf explicitly reported INCOMPATIBLE')
            return report
        # checkvintf prints COMPATIBLE on success. A shell command that merely
        # exits 0, or outputs arbitrary text, is not compatibility evidence.
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if not lines or lines[-1] != 'COMPATIBLE':
            errors.append('checkvintf exit 0 without terminal COMPATIBLE verdict')
            return report
        report['status'] = 'pass_vintf_metadata_only'
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        errors.append(str(exc))
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--aosp-root', required=True, type=Path)
    p.add_argument('--product-out', required=True, type=Path)
    p.add_argument('--checkvintf', required=True, type=Path)
    p.add_argument('--apex-info-file', type=Path,
                   help='wrapper-only input; mapped to /apex, NOT forwarded as a checkvintf flag')
    p.add_argument('--framework-level', action='append', default=[],
                   help='required framework matrix level; repeat for active release set')
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args(argv)
    report = verify(a.aosp_root, a.product_out, a.checkvintf, a.apex_info_file,
                    tuple(a.framework_level))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': report['status'], 'errors': report['errors'],
                      'android_on_asterinas_verified': False}))
    return 0 if report['status'] == 'pass_vintf_metadata_only' else 1


if __name__ == '__main__':
    sys.exit(main())
