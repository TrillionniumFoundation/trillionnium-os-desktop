#!/usr/bin/env python3
"""Extract selected official GSI metadata read-only; never qualify a runtime."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile

BASE = Path('/home/alex/work/pocket4-audio-qpr1-compat-20261109-2840-r1')
OUT = BASE / 'evidence-r1'
IMAGE = Path('/home/alex/work/pocket4-android-final/cohorts/qpr1-cp3a-16176746-20261108-8b88-r1/official/system.img')
EXPECTED = 'dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4'

def own_output(path):
    account = pwd.getpwnam('alex')
    st = path.lstat()
    if (st.st_uid, st.st_gid) != (account.pw_uid, account.pw_gid):
        os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)

def need(value, message):
    if not value:
        raise RuntimeError(message)

def identity(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid, st.st_nlink,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def ref(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as f:
        before = os.fstat(f.fileno())
        need(stat.S_ISREG(before.st_mode), 'not a regular file: ' + str(path))
        sha = hashlib.sha256()
        total = 0
        while data := f.read(1024 * 1024):
            total += len(data)
            sha.update(data)
        need(identity(before) == identity(os.fstat(f.fileno())) == identity(path.lstat()), 'file changed: ' + str(path))
    return {'path': str(path), 'bytes': total, 'sha256': sha.hexdigest(), 'identity': identity(before)}

def create(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(data)
    own_output(path)
    path.chmod(0o400)
    return ref(path)

def dump(source, cap):
    dest = OUT / 'official-files' / source.lstrip('/')
    need(not dest.exists(), 'destination already exists')
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = ['/usr/sbin/debugfs', '-R', 'dump ' + source + ' ' + str(dest), str(IMAGE)]
    proc = subprocess.run(command, capture_output=True, timeout=120)
    need(proc.returncode == 0 and dest.is_file() and 0 < dest.stat().st_size <= cap,
         'debugfs selected file extraction failed: ' + source + ': ' + proc.stderr.decode(errors='replace'))
    own_output(dest)
    dest.chmod(0o400)
    row = ref(dest)
    row.update(image_path=source, command=command, debugfs_stderr=proc.stderr.decode())
    return dest, row

def wire(data):
    pos = 0
    rows = []
    def varint():
        nonlocal pos
        value = 0
        for shift in range(0, 70, 7):
            need(pos < len(data), 'truncated protobuf varint')
            b = data[pos]
            pos += 1
            value |= (b & 127) << shift
            if not b & 128:
                return value
        raise RuntimeError('oversize protobuf varint')
    while pos < len(data):
        key = varint()
        number, kind = key >> 3, key & 7
        need(number > 0, 'zero protobuf field')
        if kind == 0:
            value = varint()
        elif kind == 2:
            length = varint()
            need(length <= len(data) - pos, 'truncated protobuf bytes')
            chunk = data[pos:pos + length]
            pos += length
            try:
                value = chunk.decode('utf-8')
            except UnicodeDecodeError:
                value = {'hex': chunk.hex()}
        else:
            raise RuntimeError('unexpected manifest wire type ' + str(kind))
        rows.append({'field': number, 'wire': kind, 'value': value})
    return rows

def apex_metadata(path, label):
    result = {'container': ref(path), 'signature_verified': False}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        need(len(names) == len(set(names)), 'duplicate ZIP names')
        result['entries'] = [{'name': z.filename, 'bytes': z.file_size, 'compressed_bytes': z.compress_size}
                             for z in archive.infolist()]
        result['metadata'] = {}
        for name in ('apex_manifest.pb', 'apex_pubkey', 'AndroidManifest.xml'):
            need(name in names, 'missing APEX metadata: ' + name)
            entry = archive.getinfo(name)
            need(entry.file_size <= 1024 * 1024, 'oversize APEX metadata')
            raw = archive.read(name)
            result['metadata'][name] = create(OUT / 'apex-metadata' / label / name, raw)
            if name == 'apex_manifest.pb':
                fields = wire(raw)
                result['manifest_wire_fields'] = fields
                mapping = {1: 'name', 2: 'version', 5: 'versionName', 6: 'noCode', 7: 'provideNativeLibs',
                           8: 'requireNativeLibs', 9: 'jniLibs', 10: 'requireSharedApexLibs',
                           11: 'provideSharedApexLibs', 13: 'supportsRebootlessUpdate', 14: 'vndkVersion',
                           15: 'vendorBootstrap', 16: 'bootstrap'}
                result['manifest'] = {}
                for field in fields:
                    if field['field'] in mapping:
                        result['manifest'].setdefault(mapping[field['field']], []).append(field['value'])
        if 'original_apex' in names:
            entry = archive.getinfo('original_apex')
            need(entry.file_size <= 256 * 1024**2, 'oversize compressed original APEX')
            inner = OUT / 'apex-metadata' / label / 'original.apex'
            with archive.open(entry) as source, inner.open('xb') as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
            own_output(inner)
            inner.chmod(0o400)
            need(inner.stat().st_size == entry.file_size, 'compressed APEX size differs')
            result['original'] = apex_metadata(inner, label + '-original')
    return result

def main():
    need(os.getuid() == 0 and not OUT.exists(), 'expected root read-only-image access and new private output')
    OUT.mkdir(mode=0o700)
    result = {'schema': 'pocket4-official-qpr1-audio-metadata-v1', 'started_ns': time.time_ns(),
              'runtime_qualified': False, 'full_audio_build_qualified': False, 'production_ready': False,
              'source_image_writes': 0, 'mounts': 0, 'cell_actions': 0, 'files': {}, 'apexes': {}}
    account = pwd.getpwnam('alex')
    try:
        source = ref(IMAGE)
        need(source['bytes'] == 2294853632 and source['sha256'] == EXPECTED, 'selected official image digest differs')
        result['source_image'] = source
        receipt = ref(IMAGE.parent / 'verification.json')
        need(receipt['sha256'] == 'bd867013617453a04ddc753a9ee811d604efe0c195be78f3590c78037cadcb58', 'official image receipt changed')
        result['source_receipt'] = receipt
        result['audio_matrices'] = []
        for level in ('7', '8', '202404', '202504', '202604', 'device'):
            image_path = '/system/etc/vintf/compatibility_matrix.' + level + '.xml'
            path, row = dump(image_path, 256 * 1024)
            result['files'][image_path] = row
            root = ET.fromstring(path.read_bytes())
            audio = [ET.tostring(hal, encoding='unicode') for hal in root.findall('hal')
                     if (hal.findtext('name') or '').startswith('android.hardware.audio')]
            result['audio_matrices'].append({'image_path': image_path, 'root_attributes': root.attrib, 'audio_entries': audio})
        for image_path, cap in (
                ('/system/etc/vintf/manifest.xml', 64 * 1024),
                ('/system/etc/llndk.libraries.txt', 64 * 1024),
                ('/system/etc/public.libraries.txt', 64 * 1024),
                ('/system/etc/linker.config.pb', 64 * 1024),
                ('/system/lib64/libbinder_ndk.so', 32 * 1024**2),
                ('/system/lib64/liblog.so', 32 * 1024**2)):
            path, row = dump(image_path, cap)
            result['files'][image_path] = row
            if path.suffix == '.txt':
                result[path.name] = path.read_text().splitlines()
            if path.suffix == '.so':
                for operation, args in (('dynamic', ['-W', '-d']), ('symbols', ['-W', '--dyn-syms'])):
                    proc = subprocess.run(['/usr/bin/readelf', *args, str(path)], capture_output=True, timeout=30)
                    need(proc.returncode == 0 and len(proc.stdout) <= 2 * 1024**2, 'readelf failed or oversized')
                    row[operation] = create(OUT / 'elf-metadata' / (path.name + '.' + operation + '.txt'), proc.stdout)
        for name, cap in (('com.android.art.capex', 20357120), ('com.android.runtime.apex', 11583488)):
            path, row = dump('/system/apex/' + name, cap)
            need(row['bytes'] == cap, 'official APEX container size differs')
            result['files'][row['image_path']] = row
            result['apexes'][name] = apex_metadata(path, name)
        need(source['identity'] == identity(IMAGE.lstat()), 'official image changed during extraction')
        result['source_image_identity_unchanged'] = True
        result['state'] = 'OFFICIAL_METADATA_EXTRACTED_READ_ONLY_UNQUALIFIED'
    except BaseException as error:
        result['state'] = 'FAILED_METADATA_EXTRACTION'
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        result['finished_ns'] = time.time_ns()
        report = create(OUT / 'RESULT.json', (json.dumps(result, indent=2, sort_keys=True) + '\n').encode())
        for directory, dirs, files in os.walk(OUT):
            own_output(Path(directory))
            for name in dirs + files:
                own_output(Path(directory) / name)
        print(json.dumps({'state': result['state'], 'report': report,
                          'audio_matrices': result.get('audio_matrices'),
                          'apex_manifests': {k: {'manifest': v.get('manifest'),
                             'original_manifest': v.get('original', {}).get('manifest')}
                             for k, v in result['apexes'].items()}, 'error': result.get('error')}), flush=True)

if __name__ == '__main__':
    main()
