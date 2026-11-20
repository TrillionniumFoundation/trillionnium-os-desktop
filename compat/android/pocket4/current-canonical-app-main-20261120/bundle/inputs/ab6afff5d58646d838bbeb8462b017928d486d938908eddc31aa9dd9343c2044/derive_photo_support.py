#!/usr/bin/python3
"""Derive the new Camera task only from pinned, already reviewed source bytes.

This script edits this private preparation directory. It never opens an Android
namespace, imports a source module, or uses any prior runtime authority.
"""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = Path('/dev/shm/p4-business-system-cases-dbba/frozen-r1/source')
OUT = HERE / 'candidate'
PINS = {
    'app_common.py': (38268, '166e75e326b9d75dc4401a709acccd4f9c415926bf75b59885fa68edf3b640c7'),
    'app_flow.py': (14631, '926793aabf5610fc32f6b94bd772c660c7e24bc992641f8b2ca4ae257bfa59bb'),
    'app_runtime.py': (20904, '095578d7d998019cdf20173cc803546dfdaff52245471d5ba3a766d7cd88a0ef'),
    'system_transport.py': (5072, '31ab63c91aef5b9db901cd92d16d35bbdebe7463e5d4d9a4ad52cbccad66e207'),
    'system_ui.py': (11407, 'c0f431942857047f5540dc9dc66d5f992aefb436b60bbb5e7417e0e1ac0b58c8'),
    'system_guard.py': (2052, '068a1c04f7113be4df67b61018151fcdb694ffccdc7885a3cf8f876dd1a6ab4f'),
    'system_flow.py': (4297, '53fc6356f06986adb69896217446ca4e319c452fcda03d6082f57dc4cf96b51c'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def original(name):
    path = SOURCE / name
    raw = path.read_bytes()
    if (len(raw), sha(raw)) != PINS[name]:
        raise RuntimeError('FROZEN_SYSTEM_SOURCE_CHANGED:' + name)
    ast.parse(raw)
    return raw, {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def emit(name, data):
    raw = data if type(data) is bytes else data.encode()
    ast.parse(raw)
    path = OUT / name
    path.write_bytes(raw)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def main():
    records = []
    for source, target in [('app_common.py', 'app_common.py'), ('app_flow.py', 'app_flow.py'),
                           ('app_runtime.py', 'app_runtime.py'),
                           ('system_transport.py', 'camera_transport.py'),
                           ('system_ui.py', 'camera_ui.py')]:
        raw, ref = original(source)
        result = emit(target, raw)
        records.append({'input': ref, 'output': result, 'byte_identical': True})
    for source, target in [('system_guard.py', 'camera_guard.py'),
                           ('system_flow.py', 'camera_flow.py')]:
        raw, ref = original(source)
        text = raw.decode()
        replacements = [('system_runtime.py', 'camera_runtime.py'),
                        ('system_plan.py', 'camera_plan.py'),
                        ('system_transport.py', 'camera_transport.py')]
        for before, after in replacements:
            text = text.replace(before, after)
        if source == 'system_flow.py':
            text = text.replace('class SystemFlow(base.Flow):', 'class CameraFlow(base.Flow):')
            text = text.replace('return SystemFlow', 'return CameraFlow')
        result = emit(target, text)
        reversed_text = text
        for before, after in reversed(replacements):
            reversed_text = reversed_text.replace(after, before)
        if source == 'system_flow.py':
            reversed_text = reversed_text.replace('class CameraFlow(base.Flow):', 'class SystemFlow(base.Flow):')
            reversed_text = reversed_text.replace('return CameraFlow', 'return SystemFlow')
        if reversed_text.encode() != raw:
            raise RuntimeError('UNDECLARED_SUPPORT_DERIVATION')
        records.append({'input': ref, 'output': result,
                        'only_task_module_names_and_new_class_name_changed': True})
    receipt = {'schema': 'pocket4-camera-photo-support-derivation-v1', 'files': records,
               'Main_actions': 0, 'Android_actions': 0,
               'historical_runtime_authority_transferred': False,
               'qualified_for_execution': False}
    path = HERE / 'support-derivation-r2.json'
    path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'files': len(records), 'path': str(path),
                      'sha256': sha(path.read_bytes()), 'Main_actions': 0, 'Android_actions': 0}))


if __name__ == '__main__':
    main()
