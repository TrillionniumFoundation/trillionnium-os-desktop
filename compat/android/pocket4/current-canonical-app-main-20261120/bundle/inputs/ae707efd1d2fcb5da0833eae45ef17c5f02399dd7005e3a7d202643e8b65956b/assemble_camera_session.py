#!/usr/bin/python3
"""Assemble only the private Camera draft from frozen current-system helpers."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = Path('/dev/shm/p4-business-system-cases-dbba/frozen-r1/source/system_session.py')
NAMES = ['deadline', 'environment', 'verify_runtime', 'original_caller',
    'consume_original_intent', 'android', 'begin_cleanup', 'verify_final_consumers',
    'ui_guard', 'validate_internal_capture', 'record_native_return', 'admit_ui_android',
    'ui_android', 'ui_readiness', 'validate_snapshot_request', 'finish_ui_api']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    raw = SOURCE.read_bytes(); text = raw.decode(); lines = text.splitlines()
    if (len(raw), sha(raw)) != (31884, '9855c4744b71065ed263b72ff7fa69b4ea9dec93e3439962b456b9fe6cd59401'):
        raise RuntimeError('FROZEN_CURRENT_SYSTEM_SESSION_CHANGED')
    cls = next(x for x in ast.parse(raw).body if isinstance(x, ast.ClassDef) and x.name == 'Session')
    template = HERE / 'camera_session_new_methods.py.txt'; out = template.read_text(); records = []
    for name in NAMES:
        fn = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == name)
        start = min([fn.lineno] + [d.lineno for d in fn.decorator_list]) - 1
        segment = '\n'.join(lines[start:fn.end_lineno]) + '\n'; change = None
        if name == 'validate_internal_capture':
            old = "request.get('accessibility_mode') == 'none'"
            if segment.count(old) != 1:
                raise RuntimeError('EXACT_ORIGINAL_DEFAULT_ACCESSIBILITY_CHECK')
            segment = segment.replace(old, "request.get('accessibility_mode', 'none') == 'none'")
            change = 'Respect the original Camera request default none; never enable touch exploration.'
        out += '\n' + segment
        records.append({'method': name, 'original_AST_sha256': sha(ast.dump(fn, include_attributes=False).encode()),
                        'declared_change': change, 'otherwise_identical': True})
    ast.parse(out); path = HERE / 'candidate/camera_session.py'; path.write_text(out)
    result = {'schema': 'pocket4-camera-session-assembly-v2',
        'source': {'path': str(SOURCE), 'bytes': len(raw), 'sha256': sha(raw)},
        'new_template': {'path': str(template), 'bytes': template.stat().st_size, 'sha256': sha(template.read_bytes())},
        'selected_methods': records, 'new_guard_adds_current_physical_device_and_manager_identity': True,
        'output': {'path': str(path), 'bytes': len(out.encode()), 'sha256': sha(out.encode())},
        'Main_actions': 0, 'Android_actions': 0, 'qualified_for_execution': False}
    (HERE / 'session-derivation-r2.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps(result['output']))


if __name__ == '__main__':
    main()
