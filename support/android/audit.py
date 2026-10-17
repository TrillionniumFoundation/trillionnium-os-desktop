#!/usr/bin/env python3
"""Fail-closed AOSP manifest/source/product-out inventory for the A08 reference.

Does NOT validate Android's VINTF runtime compatibility or Android-on-Asterinas.
The only accepted manifest uses pinned, resolved project revisions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

EXPECTED = {
    'build/make': 'd9611a86f6614b2d8b0367f81a825858dfd2207f',
    'frameworks/base': '396d32905ded85c082232bc510b525c9e372e585',
    'system/core': '00c7fec1bb09f3284aad6a6f96d2f63dfc3650ad',
    'bionic': '8d67ca893c1523eb926b9080dbe4e2ffd2a27ba1',
    'frameworks/native': 'cdca1e2000347ce2f2b25ab5d0f2dffa81f30e01',
}
REQUIRED_SOURCE = {
    'bionic': 'bionic/libc/bionic/libc_init_common.cpp',
    'init': 'system/core/init/main.cpp',
    'binder_userspace': 'frameworks/native/libs/binder/IPCThreadState.cpp',
    'art': 'art/runtime/runtime.cc',
    'zygote': 'frameworks/base/core/jni/com_android_internal_os_Zygote.cpp',
    'system_server': 'frameworks/base/services/java/com/android/server/SystemServer.java',
    'lmkd': 'system/memory/lmkd/lmkd.cpp',
    'surfaceflinger': 'frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp',
    'cuttlefish_product': 'device/google/cuttlefish/vsoc_x86_64/phone/aosp_cf.mk',
    'cuttlefish_product_registry': 'device/google/cuttlefish/AndroidProducts.mk',
}
REQUIRED_IMAGE = {
    'system_img': 'system.img',
    'vendor_img': 'vendor.img',
    'bionic_libc': 'system/lib64/libc.so',
    'bionic_linker': 'system/bin/linker64',
    'zygote_executable': 'system/bin/app_process64',
    'binder_service_manager': 'system/bin/servicemanager',
    'system_server_code': 'system/framework/services.jar',
    'surfaceflinger': 'system/bin/surfaceflinger',
    'lmkd': 'system/bin/lmkd',
}
REV = re.compile(r'^[a-f0-9]{40}$')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict:
    return {'bytes': path.stat().st_size, 'sha256': sha256(path)}


def audit_manifest(path: Path) -> dict:
    root = ET.parse(path).getroot()
    projects = root.findall('project')
    revisions = {}
    errors = []
    if root.tag != 'manifest':
        errors.append('root element must be <manifest>')
    for project in projects:
        name = project.get('path') or project.get('name')
        revision = project.get('revision')
        if not name or name in revisions:
            errors.append(f'missing or duplicate project path: {name}')
            continue
        revisions[name] = revision
        if not revision or not REV.fullmatch(revision):
            errors.append(f'{name}: not a 40-hex resolved commit: {revision}')
    for name, expected in EXPECTED.items():
        if revisions.get(name) != expected:
            errors.append(f'{name}: expected {expected}; got {revisions.get(name)}')
    if 'device/google/cuttlefish' not in revisions:
        errors.append('missing device/google/cuttlefish project')
    if len(projects) < 100:
        errors.append(f'manifest has only {len(projects)} projects; incomplete')
    return {'kind': 'resolved_manifest', 'source': str(path),
            'source_sha256': sha256(path), 'project_count': len(projects),
            'checked_project_commits': {k: revisions.get(k) for k in EXPECTED},
            'cuttlefish_project_commit': revisions.get('device/google/cuttlefish'),
            'status': 'pass' if not errors else 'fail', 'errors': errors}


def git_rev(path: Path) -> str | None:
    proc = subprocess.run(['git', '-C', str(path), 'rev-parse', '--verify', 'HEAD'],
                          text=True, capture_output=True, check=False, timeout=10)
    return proc.stdout.strip() if proc.returncode == 0 else None


def audit_source(base: Path) -> dict:
    errors = []
    files = {}
    if not (base / '.repo').is_dir():
        errors.append('not an initialized AOSP repo checkout (.repo missing)')
    for key, rel in REQUIRED_SOURCE.items():
        path = base / rel
        if path.is_file():
            files[key] = {'path': rel, **file_record(path)}
        else:
            errors.append(f'missing required source {rel}')
    product = base / REQUIRED_SOURCE['cuttlefish_product']
    if product.is_file() and not re.search(r'^PRODUCT_NAME\s*:?=\s*aosp_cf_x86_64_phone\s*$',
                                           product.read_text(errors='replace'), re.M):
        errors.append('Cuttlefish product makefile does not set locked PRODUCT_NAME')
    commits = {}
    for project in EXPECTED:
        got = git_rev(base / project) if (base / project).is_dir() else None
        commits[project] = got
        if got != EXPECTED[project]:
            errors.append(f'{project} checkout HEAD does not match lock: {got}')
    return {'kind': 'aosp_source', 'source': str(base), 'files': files,
            'checkout_commits': commits, 'errors': errors,
            'status': 'pass' if not errors else 'fail',
            'warning': 'Source inventory only; platform components NOT built or executed.'}


def hal_entries(xml_path: Path) -> list[dict]:
    root = ET.parse(xml_path).getroot()
    entries = []
    for hal in root.findall('./hal'):
        fmt = hal.get('format', 'hidl')
        name = hal.findtext('name')
        versions = [v.text for v in hal.findall('version') if v.text]
        for fqname in hal.findall('fqname'):
            entries.append({'format': fmt, 'name': name, 'version': versions,
                            'fqname': fqname.text})
        for interface in hal.findall('interface'):
            for instance in interface.findall('instance'):
                entries.append({'format': fmt, 'name': name, 'version': versions,
                                'interface': interface.findtext('name'),
                                'instance': instance.text})
        if not hal.findall('fqname') and not hal.findall('interface'):
            entries.append({'format': fmt, 'name': name, 'version': versions,
                            'instance': None})
    return entries


def audit_image(base: Path) -> dict:
    files = {}
    errors = []
    for key, rel in REQUIRED_IMAGE.items():
        path = base / rel
        if path.is_file() and path.stat().st_size > 0:
            files[key] = {'path': rel, **file_record(path)}
        else:
            errors.append(f'missing or empty required build artifact: {rel}')
    apex_paths = sorted(set((base / 'system/apex').glob('com.android.art.*')) |
                        set((base / 'system/apex').glob('com.android.art')))
    files['art_apex'] = [{'path': str(p.relative_to(base)), **file_record(p)}
                         for p in apex_paths if p.is_file() and p.stat().st_size]
    if not files['art_apex']:
        errors.append('missing ART APEX artifact (com.android.art.*)')

    vintf = []
    for partition in ('system', 'system_ext', 'product', 'vendor', 'odm'):
        folder = base / partition / 'etc/vintf'
        for pattern in ('manifest*.xml', 'manifest/*.xml',
                        'compatibility_matrix*.xml', 'compatibility_matrix/*.xml'):
            vintf.extend(folder.glob(pattern))
    vintf = sorted(set(vintf))
    device_manifests = [p for p in vintf if p.relative_to(base).parts[0] in ('vendor', 'odm')
                        and ('manifest' in p.name or 'manifest' in p.parts)]
    framework_matrices = [p for p in vintf if p.relative_to(base).parts[0] in ('system', 'system_ext')
                          and ('compatibility_matrix' in p.name or 'compatibility_matrix' in p.parts)]
    if not device_manifests:
        errors.append('missing vendor/odm VINTF device manifest XML')
    if not framework_matrices:
        errors.append('missing system/system_ext VINTF framework compatibility matrix XML')
    hals = []
    files['vintf'] = []
    for path in vintf:
        rec = {'path': str(path.relative_to(base)), **file_record(path)}
        try:
            root = ET.parse(path).getroot()
            if root.tag not in ('manifest', 'compatibility-matrix'):
                errors.append(f'invalid VINTF root <{root.tag}> in {path}')
            rec['root_type'] = root.get('type')
            rec['hal'] = hal_entries(path)
            if root.tag == 'manifest':
                hals.extend(rec['hal'])
        except ET.ParseError as ex:
            rec['parse_error'] = str(ex)
            errors.append(f'bad VINTF XML {path}: {ex}')
        files['vintf'].append(rec)
    aidl = [h for h in hals if h['format'] == 'aidl']
    # Only extract declared instances. Compare compatibility via checkvintf later.
    return {'kind': 'aosp_product_out', 'source': str(base), 'files': files,
            'hal_instances': hals, 'aidl_hal_instances': aidl,
            'status': 'pass' if not errors else 'fail', 'errors': errors,
            'warning': 'VINTF files parsed, not a checkvintf/boot/driver compatibility test.'}


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in ('manifest', 'source', 'image'):
        print('usage: audit.py manifest|source|image INPUT OUTPUT.json', file=sys.stderr)
        return 2
    _, mode, raw, output = argv
    try:
        path = Path(raw)
        result = {'manifest': audit_manifest, 'source': audit_source,
                  'image': audit_image}[mode](path)
    except (OSError, ET.ParseError, ValueError, subprocess.TimeoutExpired) as ex:
        result = {'kind': mode, 'source': raw, 'status': 'fail', 'errors': [str(ex)]}
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(f"{result['kind']}: {result['status']} ({len(result.get('errors', []))} errors) -> {out}")
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
