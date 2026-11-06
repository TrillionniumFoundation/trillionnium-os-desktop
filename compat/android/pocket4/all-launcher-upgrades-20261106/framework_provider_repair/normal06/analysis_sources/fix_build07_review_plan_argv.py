#!/usr/bin/env python3
"""Correct an unbound review document; sealed build07 request stays byte-exact."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'source-r4'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def new(path, raw):
    if path.exists():
        assert path.read_bytes() == raw, str(path)
    else:
        path.write_bytes(raw)


def main():
    plan_path, manifest_path = OUT / 'execution-plan.json', OUT / 'SOURCE_PINS.json'
    old_plan_path = OUT / 'execution-plan.before-document-correction.json'
    old_manifest_path = OUT / 'SOURCE_PINS.before-document-correction.json'
    old_plan = old_plan_path.read_bytes() if old_plan_path.exists() else plan_path.read_bytes()
    old_manifest = old_manifest_path.read_bytes() if old_manifest_path.exists() else manifest_path.read_bytes()
    assert pin(old_plan) == {'bytes': 7196, 'sha256': 'aaa0ca64935390321de20ddee0a5d1604a4da8ffb4f82aeb46c2f4c9c6c8bd6f'}
    assert pin(old_manifest) == {'bytes': 11703, 'sha256': '302a6d8495f68a137c910ef8741dbe70c1cabd743ed76a150e0004d8e6697b60'}
    manifest = json.loads(old_manifest)
    for name, expected in manifest['files'].items():
        assert pin((OUT / name).read_bytes()) == expected, name
    request = (OUT / 'exact-request.json').read_bytes()
    assert pin(request) == {'bytes': 320416, 'sha256': 'bd60060c5a1bd329b3c05bfa5309f192c42168d48397f4bcdcfc674fc889054b'}
    scope = {'__name__': 'local_review_document_plan_only', '__file__': '<local-plan-only>'}
    exec(compile((OUT / 'framework_build.py').read_bytes(), '<source-plan-only>', 'exec'), scope, scope)
    actual = scope['plan']()
    document = json.loads(old_plan)
    differing = [key for key in actual if key in document and actual[key] != document[key]]
    assert differing == ['state', 'argv'], differing
    assert actual['argv'][-2:] == ['--out', str(scope['ROOT'] / 'android-out')]
    assert '/typed-ingress-framework-systemui-provider-build-07-20261106/android-out' in actual['argv'][-1]
    document['argv'] = actual['argv']
    new_plan = dump(document)
    note = {'schema': 1, 'state': 'REVIEW_DOCUMENT_ONLY_CORRECTION',
        'cause': 'Review plan copied source-r3 argv while root/out were already updated; executable framework_build.py derives argv from actual ROOT/OUT build07.',
        'changed_document_field': 'execution-plan.json argv', 'before': pin(old_plan), 'after': pin(new_plan),
        'old_argv': json.loads(old_plan)['argv'], 'corrected_argv': actual['argv'],
        'source_plan_executed_only_as_pure_data_function': True,
        'all_30_source_members_byte_unchanged': True, 'exact_request_unchanged': pin(request),
        'runtime_or_remote_operations': 0, 'runtime_controls_rerun': False,
        'reproduction': ['analysis_sources/prepare_build07_source_r4.py', 'analysis_sources/fix_build07_review_plan_argv.py']}
    note_raw = dump(note)
    manifest['review_documents'] = {'execution-plan.json': pin(new_plan), 'review-document-correction.json': pin(note_raw)}
    manifest['original_review_manifest_before_document_correction'] = pin(old_manifest)
    new_manifest = dump(manifest)
    new(old_plan_path, old_plan)
    new(old_manifest_path, old_manifest)
    new(OUT / 'review-document-correction.json', note_raw)
    assert plan_path.read_bytes() in [old_plan, new_plan]
    assert manifest_path.read_bytes() in [old_manifest, new_manifest]
    plan_path.write_bytes(new_plan)
    manifest_path.write_bytes(new_manifest)
    assert (OUT / 'exact-request.json').read_bytes() == request
    print(json.dumps({'execution_plan': pin(new_plan), 'SOURCE_PINS': pin(new_manifest),
        'correction_note': pin(note_raw), 'exact_request_unchanged': pin(request), 'remote_operations': 0}))


if __name__ == '__main__':
    main()
