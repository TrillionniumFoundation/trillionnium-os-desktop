#!/usr/bin/env python3
"""Rebind only Camera display source constants to the CP3A photo preparation.

The original supervisor functions and execution gates remain byte-for-byte.
Inspection and negative controls never execute its runtime mode.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import types

ROOT = Path('/home/alex/work/p4-cp3a-bootstrap-20261120-runtimeaudit-r1')
HELPER_SHA = '5981eda642b2cc35a18979fddb2fd98e7a7ae0ba038a92f5f37370e2a808b401'
MANIFEST_SHA = '0f6d48ca590a9e0f7951f383361bcaeafced5dbd4e7f2ac9e74b5efbbc061baf'
OLD_PREPARATION = {
    'path': '/home/alex/work/pocket4-android-final/qualification/camera-photo-display-preparation-resume-20261107-r4/preparation.json',
    'bytes': 6152, 'sha256': 'bc90ee546748dc5405ce4f0a354b4e5eb5d44af416dd041009f5af73e5f6b468',
}
NAMES = {'PHOTO_PREPARED', 'PREPARATION_REF', 'SOURCES'}


def replace(source, replacements):
    tree = ast.parse(source)
    found = []
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in replacements:
                found.append((node, name))
    h.need({name for _, name in found} == set(replacements) and len(found) == len(replacements),
           'EXACT_THREE_ORIGINAL_REBIND_ASSIGNMENTS')
    for node, name in sorted(found, key=lambda pair: pair[0].lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [name + ' = ' + replacements[name] + '\n']
    value = ''.join(lines)
    def stripped(raw):
        t = ast.parse(raw)
        t.body = [n for n in t.body if not (isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name) and n.targets[0].id in NAMES)]
        return ast.dump(t, include_attributes=False)
    h.need(stripped(source) == stripped(value), 'UNRELATED_AST_OR_RUNTIME_GATE_CHANGED')
    before = ast.parse(source); after = ast.parse(value)
    original_methods = [n for c in before.body if isinstance(c, ast.ClassDef) and c.name == 'Supervisor' for n in c.body if isinstance(n, ast.FunctionDef)]
    new_methods = [n for c in after.body if isinstance(c, ast.ClassDef) and c.name == 'Supervisor' for n in c.body if isinstance(n, ast.FunctionDef)]
    h.need(len(original_methods) == len(new_methods) == 20, 'TWENTY_ORIGINAL_SUPERVISOR_METHODS')
    h.need([ast.get_source_segment(source, n) for n in original_methods]
           == [ast.get_source_segment(value, n) for n in new_methods], 'SUPERVISOR_METHOD_BYTES_CHANGED')
    return value


def inspect(path, extra=()):
    run = subprocess.run(['/usr/bin/python3', '-I', '-B', str(path), 'inspect-source', *extra],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, check=False)
    h.need(len(run.stdout) + len(run.stderr) < 65536, 'INSPECTION_OUTPUT_BOUND')
    return {'returncode': run.returncode, 'stdout': run.stdout.decode(), 'stderr': run.stderr.decode()}


def main():
    os.umask(0o077)
    destination = ROOT / 'camera-display'
    h.need(not destination.exists(), 'CREATE_ONLY_CAMERA_DISPLAY_ALREADY_EXISTS')
    raw, manifest_ref, _ = h.read(ROOT / 'candidate/MANIFEST.json')
    h.need(manifest_ref['sha256'] == MANIFEST_SHA, 'EXACT_PHOTO_SOURCE_MANIFEST_PIN')
    manifest = json.loads(raw)
    photo = next(row for row in manifest['preparations'] if row['group'].startswith('camera-app-photo'))
    h.read(photo['preparation']['path'], photo['preparation'])
    h.read(photo['entry']['path'], photo['entry'])
    raw, old_prep_ref, old_prep_f9 = h.read(OLD_PREPARATION['path'], OLD_PREPARATION)
    preparation = json.loads(raw)
    old_source, old_source_ref, old_source_f9 = h.read(preparation['source']['path'], preparation['source'])
    original_bookends = [{'ref': old_prep_ref, 'f9': old_prep_f9}, {'ref': old_source_ref, 'f9': old_source_f9}]
    for row in preparation['source_dependencies']:
        pin = {key: row[key] for key in ('path', 'bytes', 'sha256')}
        _, actual, f9 = h.read(pin['path'], pin)
        original_bookends.append({'ref': actual, 'f9': f9})
    sources = "{\n" + "    'holder': (PREPARED / 'display_holder.py', '68fef3e0a46ab2f1b5d783ab5640add6d2f6625c9655a803efb25409ad79917f', 16384),\n" + "    'lease': (PREPARED / 'display_lease.py', '81f34cdbc75a2cf4e092a961fe4dce5d23522842c0ec54cdcff4fc9c99e4dbfd', 32768),\n" + "    'camera': (PHOTO_PREPARED / 'camera_entry.py', " + repr(photo['entry']['sha256']) + ", 65536),\n" + "    'preparation': (Path(PREPARATION_REF['path']), PREPARATION_REF['sha256'], 131072),\n" + "    'lifecycle': (ROOT.parent / 'framework/runtime_support/capture_lifecycle.py', '6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877', 32768),\n}"
    replacements = {
        'PHOTO_PREPARED': 'Path(' + repr(str(Path(photo['entry']['path']).parent)) + ')',
        'PREPARATION_REF': repr(photo['preparation']), 'SOURCES': sources,
    }
    source = replace(old_source.decode(), replacements)
    h.mkdir(destination)
    source_ref = h.write(destination / 'source/photo_display_wrapper.py', source.encode())
    positive = inspect(Path(source_ref['path']))
    h.need(positive['returncode'] == 0, 'REBOUND_DISPLAY_INSPECTION_FAILED:' + positive['stderr'])
    observed = json.loads(positive['stdout'])
    h.need(observed['schema'] == 'pocket4-camera-photo-display-source-inspection-v1'
           and observed['photo_source_files'] == 17
           and observed['Main_actions'] == observed['DBus_actions'] == observed['Android_UI_actions'] == 0
           and observed['whole_app_business_accepted'] is False, 'INSPECTION_SCOPE_CHANGED')
    for role, expected in (('camera', photo['entry']), ('preparation', photo['preparation'])):
        actual = next(row for row in observed['sources'] if row['role'] == role)
        h.need({key: actual[key] for key in ('path', 'bytes', 'sha256')} == expected, 'PHOTO_BINDING_NOT_CURRENT')
    negative = []
    for name, field, invalid, error in (
        ('wrong-preparation-sha', 'sha256', '0' * 64, 'source/input SHA differs:'),
        ('wrong-preparation-size', 'bytes', photo['preparation']['bytes'] + 1, 'photo preparation size changed'),
    ):
        pin = dict(photo['preparation']); pin[field] = invalid
        altered = replace(source, {'PREPARATION_REF': repr(pin)})
        negative_ref = h.write(destination / 'negative-controls' / (name + '.py'), altered.encode())
        run = inspect(Path(negative_ref['path']))
        h.need(run['returncode'] != 0 and error in run['stderr'] and not run['stdout'], 'NEGATIVE_FAILED:' + name)
        negative.append({'name': name, 'expected_error': error, 'source': negative_ref, **run})
    run = inspect(Path(source_ref['path']), ['--input', str(destination / 'not-a-runtime-input')])
    error = 'photo wrapper inspection has no live input'
    h.need(run['returncode'] != 0 and error in run['stderr'] and not run['stdout'], 'LIVE_INPUT_MUST_BE_REFUSED_IN_INSPECTION')
    negative.append({'name': 'inspection-refuses-live-input', 'expected_error': error, **run})
    new_preparation = copy.deepcopy(preparation)
    new_preparation.update({
        'state': 'SOURCE_REBOUND_INSPECTION_PASSED_RUNTIME_AND_VISUAL_PENDING',
        'source': source_ref, 'program': ['/usr/bin/python3', '-I', '-B', source_ref['path']],
        'frozen_photo_preparation': photo['preparation'], 'source_dependencies': observed['sources'],
        'source_only': True, 'runtime_qualified': False, 'production_ready': False,
        'unchanged_supervisor_methods': 20,
        'source_rebind': {'source_manifest': manifest_ref, 'original_preparation': old_prep_ref,
            'only_assignments_changed': sorted(NAMES), 'supervisor_methods_byte_identical': 20,
            'all_other_AST_unchanged': True, 'historical_runtime_credit_transferred': False},
    })
    new_preparation['support_migration'] = {
        'prior_preparation': old_prep_ref, 'photo_preparation': photo['preparation'],
        'only_assignments_changed': sorted(NAMES), 'all_supervisor_methods_AST_unchanged': True,
        'historical_controls_apply_to_original_sources': True,
        'actual_source_inspection_recorded_separately': True,
    }
    preparation_ref = h.write(destination / 'preparation.json', h.encoded(new_preparation))
    h.bookend(original_bookends)
    h.bookend(manifest['original_input_bookends'])
    result = {'schema': 'pocket4-cp3a-camera-display-source-rebind-verification-v1',
        'preparation': preparation_ref, 'source': source_ref, 'source_manifest': manifest_ref,
        'original_input_bookends': original_bookends, 'original_inputs_unchanged': True,
        'source_only': True, 'positive': positive, 'negative': negative,
        'only_assignments_changed': sorted(NAMES), 'supervisor_methods_byte_identical': 20,
        'all_other_AST_unchanged': True, 'Android_actions': 0, 'DBus_actions': 0,
        'runtime_qualified': False, 'production_ready': False, 'current_or_selector_updated': False}
    result_ref = h.write(destination / 'verification.json', h.encoded(result))
    print(json.dumps({'preparation': preparation_ref, 'source': source_ref,
        'verification': result_ref, 'positive_count': 1, 'negative_count': len(negative),
        'source_only': True, 'Android_actions': 0}, sort_keys=True))


if __name__ == '__main__':
    helper_path = ROOT / 'prepare_bootstrap.py'
    code = helper_path.read_bytes()
    if hashlib.sha256(code).hexdigest() != HELPER_SHA:
        raise RuntimeError('REVIEWED_SOURCE_PREPARATION_HELPER_PIN_REQUIRED')
    h = types.ModuleType('source_preparation_helper'); h.__file__ = str(helper_path)
    exec(compile(code, str(helper_path), 'exec'), h.__dict__)
    main()
