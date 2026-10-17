#!/usr/bin/env python3
"""Read-only Cuttlefish launch audit: reject stale source, VINTF or image bytes.

This program never boots Android or qualifies Asterinas. Status "preflight_only"
means source/image hashes still match the measured *Linux guest* reference.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

CHECKS = (
    ('manifest-audit.json', 'resolved_manifest', 'pass'),
    ('source-audit.json', 'aosp_source', 'pass'),
    ('product-source-launch-audit.json', 'a08_cuttlefish_product_source_contract', 'pass_source_checkout_only'),
    ('image-audit.json', 'aosp_product_out', 'pass'),
    ('vintf-compatibility.json', 'a08_aosp_vintf_metadata_compatibility', 'pass_vintf_metadata_only'),
)
HEX = re.compile(r'^[0-9a-f]{64}$')


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def git_head(folder: Path) -> str:
    p = subprocess.run(['git', '-C', str(folder), 'rev-parse', '--verify', 'HEAD'],
                       capture_output=True, text=True, check=False, timeout=15)
    return p.stdout.strip() if p.returncode == 0 else ''


def check_record(root: Path, relative: str, expected: dict, failures: list[str],
                 *, allowed_symlink_root: Path | None = None) -> None:
    label = expected.get('path') if isinstance(expected, dict) else None
    raw_sha = expected.get('sha256') if isinstance(expected, dict) else None
    if not isinstance(label, str) or not isinstance(raw_sha, str) or not HEX.fullmatch(raw_sha):
        failures.append(f'{relative}: malformed recorded artifact entry')
        return
    relative_path = Path(label)
    # The inventoried name must remain under PRODUCT_OUT lexically. AOSP's
    # Soong-built image may legitimately be a symlink into the SAME out/ tree.
    # Never accept an absolute name, '..', or a symlink outside AOSP out/.
    if relative_path.is_absolute() or '..' in relative_path.parts:
        failures.append(f'{relative}: path escaped audited root')
        return
    path = (root / relative_path).resolve()
    safe_root = (allowed_symlink_root or root).resolve()
    if not path.is_relative_to(safe_root):
        failures.append(f'{relative}: path escaped audited root')
    elif not path.is_file():
        failures.append(f'{relative}: file missing at preflight')
    elif hash_file(path) != raw_sha:
        failures.append(f'{relative}: bytes changed since audit')


def verify(root: Path, evidence: Path, product: Path, launcher: Path) -> dict:
    root, evidence, product, launcher = (p.resolve() for p in (root, evidence, product, launcher))
    report = {
        'schema': 1, 'kind': 'a08_cuttlefish_reference_launch_integrity',
        'kernel': 'Linux Cuttlefish reference, NOT Asterinas',
        'status': 'blocked', 'guest_boot_verified': False,
        'android_on_asterinas_verified': False, 'audit_reports': {}, 'errors': [],
    }
    errors = report['errors']
    try:
        if not product.is_relative_to(root / 'out'):
            raise ValueError('PRODUCT_OUT must be inside AOSP out')
        if not launcher.is_relative_to(root / 'out/host'):
            raise ValueError('launcher must come from AOSP host out')
        if not launcher.is_file():
            raise ValueError('same-build Cuttlefish launcher missing')
        expected_sources = (evidence/'manifest-resolved.xml', root, root, product, product)
        audits = {}
        for (filename, kind, expected_status), source in zip(CHECKS, expected_sources):
            path = evidence/filename
            data = json.loads(path.read_text())
            if data.get('kind') != kind or data.get('status') != expected_status:
                raise ValueError(f'{filename} does not carry a passing {kind} audit')
            origin = (data.get('aosp_root') if kind == 'a08_cuttlefish_product_source_contract'
                      else data.get('product_out') if kind == 'a08_aosp_vintf_metadata_compatibility'
                      else data.get('source'))
            if not isinstance(origin, str) or Path(origin).resolve() != source.resolve():
                raise ValueError(f'{filename} refers to another checkout/input')
            audits[kind] = data
            report['audit_reports'][filename] = hash_file(path)
        manifest = audits['resolved_manifest']
        if hash_file(evidence/'manifest-resolved.xml') != manifest.get('source_sha256'):
            errors.append('resolved manifest changed since audit')
        sources = audits['aosp_source']
        for label, item in sources.get('files', {}).items():
            check_record(root, 'source:'+label, item, errors)
        for project, commit in sources.get('checkout_commits', {}).items():
            folder = (root/project).resolve()
            if not folder.is_relative_to(root) or git_head(folder) != commit:
                errors.append('platform project HEAD changed: '+project)
        prod = audits['a08_cuttlefish_product_source_contract']
        for project, entry in prod.get('projects', {}).items():
            folder = (root/project).resolve()
            if not folder.is_relative_to(root) or git_head(folder) != entry.get('manifest_commit'):
                errors.append('Cuttlefish project HEAD changed: '+project)
        cuttlefish = root/'device/google/cuttlefish'
        for name, item in prod.get('product_files', {}).items():
            check_record(cuttlefish, 'product:'+name, {'path':name, **item}, errors)
        images = audits['aosp_product_out'].get('files', {})
        for mandatory in ('system_img', 'vendor_img'):
            if mandatory not in images:
                errors.append('required build image missing from audit: '+mandatory)
        for name, artifact in images.items():
            if isinstance(artifact, dict):
                check_record(product, 'image:'+name, artifact, errors,
                             allowed_symlink_root=root/'out')
            elif isinstance(artifact, list):
                for index, entry in enumerate(artifact):
                    check_record(product, f'image:{name}[{index}]', entry, errors,
                                 allowed_symlink_root=root/'out')
        # Independent VINTF compatibility evidence must come from the SAME
        # staged partitions and AOSP-built tool, and still match current bytes.
        vintf = audits['a08_aosp_vintf_metadata_compatibility']
        checked_tool = Path(vintf.get('tool', '')).resolve()
        if (not checked_tool.is_file() or
                not checked_tool.is_relative_to(root / 'out/host') or
                hash_file(checked_tool) != vintf.get('tool_sha256')):
            errors.append('AOSP checkvintf host binary changed/missing since verification')
        recorded_vintf = vintf.get('vintf_files', {})
        if not isinstance(recorded_vintf, dict) or not recorded_vintf:
            errors.append('missing VINTF compatibility source file inventory')
        else:
            for name, item in recorded_vintf.items():
                check_record(product, 'vintf:'+name, item, errors,
                             allowed_symlink_root=root/'out')
        if 'apex_info_sha256' in vintf:
            path_text = vintf.get('apex_info_path', '')
            command = vintf.get('command', [])
            mapped = vintf.get('mapped_partitions', {})
            apex_path = Path(path_text).resolve() if path_text else None
            if (apex_path is None or not apex_path.is_file() or
                    apex_path.name != 'apex-info-list.xml' or
                    not apex_path.is_relative_to(root/'out') or
                    hash_file(apex_path) != vintf['apex_info_sha256']):
                errors.append('APEX info bytes changed since VINTF check')
            else:
                # The Android 15 tool reads APEX info under --dirmap /apex;
                # do not allow replay of a report that used removed flags or
                # whose dirmap is not the audited directory.
                mapping = '/apex:' + str(apex_path.parent)
                pairs = list(zip(command, command[1:])) if isinstance(command, list) else []
                if (mapped.get('/apex') != str(apex_path.parent) or
                        ('--dirmap', mapping) not in pairs or
                        '--apex-info-file' in command):
                    errors.append('APEX mapping not bound to audited checkvintf invocation')
        report['launcher_sha256'] = hash_file(launcher)
        if not errors:
            report['status'] = 'preflight_only'
    except (ValueError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        errors.append(str(exc))
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--aosp-root', required=True, type=Path)
    p.add_argument('--evidence', required=True, type=Path)
    p.add_argument('--product-out', required=True, type=Path)
    p.add_argument('--launcher', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args(argv)
    result = verify(args.aosp_root, args.evidence, args.product_out, args.launcher)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'status':result['status'],'errors':result['errors'],
                      'android_on_asterinas_verified':False}))
    return 0 if result['status']=='preflight_only' else 1


if __name__ == '__main__':
    sys.exit(main())
