#!/usr/bin/env python3
"""Bind a completed candidate06 source-composition receipt to a new local profile."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLACEHOLDER = 'ACTUAL_CANDIDATE06_COMPOSITION_REPORT_SHA_REQUIRED'

def need(value, why):
    if not value:
        raise RuntimeError(why)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()

def read(name):
    pins = json.loads((HERE / 'TEMPLATE_PINS.json').read_bytes())['files']
    need(name in pins, 'unlisted frozen template')
    raw = (HERE / name).read_bytes()
    need(len(raw) == pins[name]['bytes'] and sha(raw) == pins[name]['sha256'], 'template changed: ' + name)
    return raw

def replace_one(value, before, after):
    need(value.count(before) == 1, 'ambiguous binding substitution: ' + before)
    return value.replace(before, after)

def validate(raw, expected_sha):
    need(len(expected_sha) == 64 and all(c in '0123456789abcdef' for c in expected_sha) and
         sha(raw) == expected_sha, 'explicit actual composition SHA mismatch')
    result = json.loads(raw)
    expected = json.loads(read('expected-source-integration.json'))
    for key, value in expected.items():
        need(result[key] == value, 'actual candidate06 composition differs: ' + key)
    need(result['state'] == 'CANDIDATE06_COMPOSED_SOURCE_NOT_BUILT' and
         result['parent_and_authority_unchanged_after'] is True and
         result['all_11_tested_production_inputs_exact'] is True and
         all(result[key] is False for key in ('matched_candidate05_gates_rerun_for06',
             'feature_default_enabled','full_engine_built','ART_built','factory_built',
             'installed','services_started','production_ready')) and
         result['Main_actions'] == result['Android_actions'] == 0,
         'actual composition completion or scope differs')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition')
    parser.add_argument('--composition-sha256')
    parser.add_argument('--out')
    args = parser.parse_args()
    if not any((args.composition, args.composition_sha256, args.out)):
        print(json.dumps({'state': 'PLAN_ONLY', 'actual_candidate06_composition_required': True,
                          'source_prepare_or_build_started': False, 'remote_actions': 0}))
        return
    need(all((args.composition, args.composition_sha256, args.out)), 'all explicit binding arguments required')
    raw = Path(args.composition).read_bytes()
    actual = validate(raw, args.composition_sha256)
    original = read('combined_build_streaming.template.py').decode()
    controller = replace_one(original, PLACEHOLDER, args.composition_sha256)
    csha = sha(controller.encode())
    fence = replace_one(read('fenced_build_streaming.unbound.py').decode(),
                        'BOUND_CANDIDATE06_CONTROLLER_SHA_REQUIRED', csha)
    generator = replace_one(read('make_requests.unbound.py').decode(),
                            'BOUND_CANDIDATE06_CONTROLLER_SHA_REQUIRED', csha)
    generator = replace_one(generator, 'BOUND_CANDIDATE06_FENCE_SHA_REQUIRED', sha(fence.encode()))
    for value in (controller, fence, generator):
        ast.parse(value)
    output = {
        'combined_build_streaming.py': controller.encode(),
        'fenced_build_streaming.template.py': fence.encode(),
        'make_requests.py': generator.encode(),
        'main_snapshot.py': read('main_snapshot.py'),
        'expected-runtime-builder-source-manifest.json': read('expected-runtime-builder-source-manifest.json'),
        '0008-soong-leaf-go-memory-budget.patch': read('0008-soong-leaf-go-memory-budget.patch'),
        'actual-candidate06-composition-report.json': raw,
        'template-to-actual-composition.patch': ''.join(difflib.unified_diff(
            original.splitlines(True), controller.splitlines(True),
            fromfile='a/combined_build_streaming.template.py', tofile='b/combined_build_streaming.py')).encode(),
    }
    root = Path(args.out)
    need(root.is_absolute() and not root.exists() and not root.is_symlink(), 'fresh local profile directory required')
    root.mkdir(mode=0o700)
    rows = {}
    for name, value in output.items():
        with (root / name).open('xb') as stream:
            stream.write(value)
        (root / name).chmod(0o444)
        rows[name] = {'bytes': len(value), 'sha256': sha(value)}
    pins = {'schema': 1, 'state': 'ACTUAL_SOURCE_COMPOSITION_BOUND_PREPARATION_NOT_SUBMITTED',
            'files': rows, 'template_pins_sha256': sha((HERE / 'TEMPLATE_PINS.json').read_bytes()),
            'actual_composition_sha256': args.composition_sha256,
            'candidate06_manifest_sha256': actual['manifest_sha256'],
            'actual_new_full_build_completed': False, 'remote_actions': 0,
            'Main_snapshot_source_unchanged': True, 'production_ready': False}
    with (root / 'BOUND_PINS.json').open('xb') as stream:
        stream.write(encoded(pins))
    (root / 'BOUND_PINS.json').chmod(0o444)
    print(json.dumps({'root': str(root), 'controller_sha256': csha,
                      'pins_sha256': sha((root / 'BOUND_PINS.json').read_bytes()),
                      'source_preparation_started': False, 'remote_actions': 0}))

if __name__ == '__main__':
    main()
