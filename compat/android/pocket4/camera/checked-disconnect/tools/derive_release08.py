#!/usr/bin/env python3
"""Compile the reviewed release08 source once to freeze its reproducible output pins.

No signing, installation, Android entry, UI operation or source modification.
The separately pinned normal builder must reproduce these outputs afterward.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('/home/alex/work/pocket4-camera-source-20261104')
AOSP = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
spec = importlib.util.spec_from_file_location('pinned_builder', ROOT / 'tools/build_release08_unsigned.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
sha = builder.sha
require = builder.require

def main():
    lock = json.loads((ROOT / 'dependencies.template.json').read_text())
    paths = {}
    for key, item in lock['inputs'].items():
        logical = item['logical_path']
        if logical.startswith('local-build/'):
            path = BASE / logical.removeprefix('local-build/')
        elif logical.startswith('aosp/'):
            path = AOSP / logical.removeprefix('aosp/')
        else:
            raise RuntimeError('Unknown locked logical root: ' + key)
        path = path.resolve(strict=True)
        require(path.is_file() and path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], 'Locked input mismatch: ' + key)
        paths[key] = path
    source = ROOT / 'source/packages/apps/Camera2/src/com/android/camera/one/v2/Camera2OneCameraManagerImpl.java'
    require(sha(source) == lock['expected']['source_sha256'], 'Reviewed source mismatch')
    out = ROOT / 'derive-01'
    out.mkdir(mode=0o700, exist_ok=False)
    for name in ('classes', 'empty-sourcepath'):
        (out / name).mkdir()
    values = {key: str(path) for key, path in paths.items()}
    values.update(source=str(source), classes=str(out / 'classes'), empty_sourcepath=str(out / 'empty-sourcepath'))
    argv = [part.format_map(values) for part in lock['commands']['javac']]
    started = time.monotonic()
    with (out / 'javac.stdout').open('wb') as stdout, (out / 'javac.stderr').open('wb') as stderr:
        process = subprocess.run(argv, stdout=stdout, stderr=stderr, timeout=90)
    require(process.returncode == 0, 'Full manager compile failed; retained javac logs')
    overlay = {str(path.relative_to(out / 'classes')): path.read_bytes() for path in (out / 'classes').rglob('*.class')}
    expected = lock['expected']['class_entry']
    require(set(overlay) == {expected}, 'Unexpected class outputs')
    lock['expected']['class_after_sha256'] = hashlib.sha256(overlay[expected]).hexdigest()
    program = out / 'program.jar'
    with zipfile.ZipFile(paths['original_program']) as previous, zipfile.ZipFile(program, 'w', compression=zipfile.ZIP_DEFLATED) as revised:
        names = previous.namelist()
        require(len(names) == len(set(names)) and expected in names, 'Invalid original class inventory')
        require(hashlib.sha256(previous.read(expected)).hexdigest() == lock['expected']['class_before_sha256'], 'Current manager class mismatch')
        for name in names:
            builder.zwrite(revised, name, overlay[name] if name in overlay else previous.read(name))
    with zipfile.ZipFile(paths['original_program']) as previous, zipfile.ZipFile(program) as revised:
        require(previous.namelist() == revised.namelist(), 'Program entry inventory changed')
        require([name for name in names if previous.read(name) != revised.read(name)] == [expected], 'An unreviewed class changed')
    lock['expected']['program_sha256'] = sha(program)
    for key, path in paths.items():
        require(sha(path) == lock['inputs'][key]['sha256'], 'Input changed during derivation: ' + key)
    require(sha(source) == lock['expected']['source_sha256'], 'Source changed during derivation')
    (ROOT / 'inputs.private.json').write_text(json.dumps({key: str(path) for key, path in paths.items()}, indent=2) + '\n')
    os.chmod(ROOT / 'inputs.private.json', 0o600)
    (ROOT / 'dependencies.lock.json').write_text(json.dumps(lock, indent=2) + '\n')
    result = {'success': True, 'scope': 'Genuine Android SDK compile and deterministic one-class program derivation; unsigned build remains next', 'external_inputs_verified': len(paths), 'source_sha256': sha(source), 'class_sha256': lock['expected']['class_after_sha256'], 'program_sha256': sha(program), 'one_changed_class': expected, 'elapsed_seconds': time.monotonic() - started, 'javac_returncode': process.returncode, 'lock_sha256': sha(ROOT / 'dependencies.lock.json'), 'runtime_execution': False, 'installed': False, 'production_ready': False}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
