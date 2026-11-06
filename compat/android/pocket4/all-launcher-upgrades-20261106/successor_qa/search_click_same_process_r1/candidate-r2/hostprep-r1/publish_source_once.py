#!/usr/bin/env python3
"""Publish only this new fixed helper source, then call the unchanged stager.

No build, Main read, Android command, installation, permission, or UI action.
The old helper, flow, source, and failure records are never opened or modified.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types

sys.dont_write_bytecode = True
ROOT = Path('/home/alex/work/pocket4-beike-fixed-search-source-20261106-362bdb6f45eeb344b3584aa998cb03e1')
OUTPUT = Path('/home/alex/work/pocket4-successor-qa-build-source-362bdb6f45eeb344b3584aa998cb03e1')
MANIFEST_SHA = '0bd7c10043f46063fdbf46e19a48e40430c02f3373d697ad7a44af8ad64b8489'
STAGER_SHA = '745e0f15f8619c2b00a7d54c890837de826eb04e192bcbf273eb3687b6baeac6'
PAYLOAD_BYTES = 303060
PAYLOAD_SHA = '56f993aa2cc27a31d6890cce5af089b04a802275a5bc3fc0be5ec49ea438d024'


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def validated_payload(raw):
    need(len(raw) == PAYLOAD_BYTES <= 524288 and sha(raw) == PAYLOAD_SHA, 'EXACT_BOUNDED_SOURCE_PAYLOAD')
    value = json.loads(raw)
    need(type(value) is dict and set(value) == {'schema', 'manifest_text', 'files', 'stage_source'} and
         value['schema'] == 'pocket4-fixed-search-helper-source-payload-v1' and canonical(value) + b'\n' == raw,
         'EXACT_CANONICAL_SOURCE_PAYLOAD')
    manifest_raw = value['manifest_text'].encode('utf-8')
    need(len(manifest_raw) == 3259 and sha(manifest_raw) == MANIFEST_SHA, 'EXACT_FINAL_HELPER_MANIFEST')
    manifest = json.loads(manifest_raw)
    need(manifest['helper_package'] == 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2' and
         manifest['allowed_operations'] == ['state', 'inspect', 'search_click'] and
         manifest['UI_admitted'] is False and manifest['build_performed'] is False and
         manifest['old_helper_qualification_inherited'] is False, 'NEW_UNBUILT_FIXED_HELPER_ONLY')
    files = value['files']
    need(type(files) is dict and set(files) == set(manifest['files']) and len(files) == 15,
         'EXACT_FIFTEEN_SOURCE_MEMBERS')
    bodies = {}
    for name, text in files.items():
        rel = Path(name)
        need(type(text) is str and not rel.is_absolute() and str(rel) == name and
             all(part not in ('', '.', '..') for part in name.split('/')), 'CANONICAL_SOURCE_MEMBER')
        body = text.encode('utf-8')
        need(manifest['files'][name] == {'bytes': len(body), 'sha256': sha(body)}, 'EXACT_SOURCE_MEMBER_PIN')
        bodies[name] = body
    stage_raw = value['stage_source'].encode('utf-8')
    need(len(stage_raw) == 5608 and sha(stage_raw) == STAGER_SHA, 'ORIGINAL_STAGER_BYTES')
    return manifest_raw, bodies, stage_raw


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    try:
        remaining = memoryview(raw)
        while remaining:
            count = os.write(fd, remaining)
            need(count > 0, 'SOURCE_WRITE_PROGRESS')
            remaining = remaining[count:]
        os.fsync(fd)
        meta = os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and meta.st_uid == 0 and
             meta.st_size == len(raw) and stat.S_IMODE(meta.st_mode) == 0o400, 'NEW_PRIVATE_SOURCE_IDENTITY')
    finally:
        os.close(fd)


def main():
    need(os.getuid() == os.geteuid() == 0 and sys.argv == ['-c'], 'EXACT_ROOT_SOURCE_PUBLICATION_ENTRY')
    os.umask(0o077)
    result = {'schema': 'pocket4-fixed-search-helper-host-source-publication-v1', 'ok': False,
              'Android_commands': 0, 'Main_reads': 0, 'build_performed': False, 'installs': 0,
              'UI_admitted': False, 'existing_files_modified': False, 'production_ready': False,
              'automatic_retry': False, 'errors': []}
    try:
        raw = sys.stdin.buffer.read(524289)
        manifest_raw, files, stage_raw = validated_payload(raw)
        need(ROOT.parent.resolve() == ROOT.parent and OUTPUT.parent == ROOT.parent, 'CANONICAL_PUBLICATION_PARENT')
        ROOT.mkdir(mode=0o700)
        source = ROOT / 'helper'; source.mkdir(mode=0o700)
        directories = {ROOT, source}
        for name, body in sorted(files.items()):
            path = source / name
            missing, parent = [], path.parent
            while parent != source:
                missing.append(parent); parent = parent.parent
            for folder in reversed(missing):
                if folder not in directories:
                    folder.mkdir(mode=0o700); directories.add(folder)
            write_new(path, body)
        write_new(source / 'SOURCE_PINS.json', manifest_raw)
        write_new(ROOT / 'stage_helper_source.py', stage_raw)
        write_new(ROOT / 'source-payload.original.json', raw)
        for path in sorted(directories, key=lambda p: len(p.parts), reverse=True):
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        stage = types.ModuleType('unchanged_reviewed_helper_source_stager')
        stage.__file__ = str(ROOT / 'stage_helper_source.py')
        exec(compile(stage_raw, stage.__file__, 'exec'), stage.__dict__)
        receipt = stage.stage(source, MANIFEST_SHA, OUTPUT)
        result.update(ok=True, original_stager_receipt=receipt, source_publication=str(ROOT),
                      manifest_sha256=MANIFEST_SHA, source_payload_bytes=len(raw), source_payload_sha256=sha(raw))
        write_new(ROOT / 'publication-result.json', canonical(result) + b'\n')
    except BaseException as error:
        result['ok'] = False
        result['errors'].append({'type': type(error).__name__, 'code': str(error)[:256]})
    print(canonical(result).decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
