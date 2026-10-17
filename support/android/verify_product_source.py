#!/usr/bin/env python3
"""Verify actual AOSP Cuttlefish source checkout matches repo manifest -r.

This is a source-only product gate. It does not build, boot, or certify Android.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

PROJECTS = (
    'device/google/cuttlefish',
    'device/google/cuttlefish_prebuilts',
    'device/google/cuttlefish_vmm',
)
PRODUCT = 'aosp_cf_x86_64_phone'
LUNCH = 'aosp_cf_x86_64_phone-trunk_staging-userdebug'
PRODUCT_PATH = 'vsoc_x86_64/phone/aosp_cf.mk'
HEX_SHA = re.compile(r'^[0-9a-f]{40}$')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def git_head(path: Path) -> str:
    command = ['git', '-C', str(path), 'rev-parse', '--verify', 'HEAD']
    result = subprocess.run(command, capture_output=True, text=True, check=False,
                            timeout=15)
    return result.stdout.strip() if result.returncode == 0 else ''


def verify(aosp_root: Path, resolved_manifest: Path) -> dict:
    root = aosp_root.resolve()
    result = {
        'schema': 1,
        'kind': 'a08_cuttlefish_product_source_contract',
        'aosp_root': str(root),
        'resolved_manifest': str(resolved_manifest.resolve()),
        'product': PRODUCT,
        'lunch': LUNCH,
        'status': 'blocked',
        'product_source_verified': False,
        'aosp_build_verified': False,
        'cuttlefish_boot_verified': False,
        'android_on_asterinas_verified': False,
        'projects': {},
        'errors': [],
    }
    errors = result['errors']
    try:
        if not (root / '.repo').is_dir():
            raise ValueError('missing .repo checkout')
        manifest = resolved_manifest.resolve(strict=True)
        result['resolved_manifest_sha256'] = sha256(manifest)
        tree = ET.parse(manifest).getroot()
        if tree.tag != 'manifest':
            raise ValueError('resolved manifest root must be <manifest>')
        revisions = {}
        for project in tree.findall('project'):
            path = project.get('path') or project.get('name')
            if path in PROJECTS:
                revisions.setdefault(path, []).append(project.get('revision'))
        for project in PROJECTS:
            values = revisions.get(project, [])
            if len(values) != 1 or not values[0] or not HEX_SHA.fullmatch(values[0]):
                errors.append(f'{project}: expected unique resolved 40-hex project revision')
                continue
            checkout = (root / project).resolve()
            if not checkout.is_relative_to(root):
                errors.append(f'{project}: project path escapes AOSP checkout')
                continue
            if not checkout.is_dir():
                errors.append(f'{project}: source directory absent')
                continue
            commit = git_head(checkout)
            result['projects'][project] = {
                'manifest_commit': values[0],
                'checkout_commit': commit,
                'matches_manifest': commit == values[0],
            }
            if commit != values[0]:
                errors.append(f'{project}: checkout HEAD mismatch against manifest')
        cuttlefish = root / PROJECTS[0]
        registry = cuttlefish / 'AndroidProducts.mk'
        product_mk = cuttlefish / PRODUCT_PATH
        for file, label in ((registry, 'AndroidProducts.mk'), (product_mk, PRODUCT_PATH)):
            if not file.is_file():
                errors.append(f'missing Cuttlefish product source: {label}')
            else:
                result.setdefault('product_files', {})[label] = {
                    'sha256': sha256(file), 'bytes': file.stat().st_size,
                }
        if registry.is_file():
            text = registry.read_text(errors='replace')
            entry = re.escape(PRODUCT) + r':\$\(LOCAL_DIR\)/' + re.escape(PRODUCT_PATH)
            if not re.search(entry + r'(?=\s|\\|$)', text):
                errors.append('AndroidProducts.mk does not register locked product file')
            if LUNCH not in text:
                errors.append('AndroidProducts.mk does not advertise locked lunch target')
        if product_mk.is_file():
            text = product_mk.read_text(errors='replace')
            for name, value in (('PRODUCT_NAME', PRODUCT), ('PRODUCT_DEVICE', 'vsoc_x86_64')):
                exp = r'^\s*' + name + r'\s*:?=\s*' + value + r'\s*(?:#.*)?$'
                if not re.search(exp, text, flags=re.MULTILINE):
                    errors.append(f'{PRODUCT_PATH} missing expected {name}={value}')
    except (ValueError, OSError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        errors.append(str(exc))
    if not errors:
        result['status'] = 'pass_source_checkout_only'
        result['product_source_verified'] = True
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--aosp-root', type=Path, required=True)
    p.add_argument('--resolved-manifest', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    result = verify(args.aosp_root, args.resolved_manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status':result['status'], 'errors':result['errors'],
                      'android_on_asterinas_verified':False}))
    return 0 if result['product_source_verified'] else 1


if __name__ == '__main__':
    sys.exit(main())
