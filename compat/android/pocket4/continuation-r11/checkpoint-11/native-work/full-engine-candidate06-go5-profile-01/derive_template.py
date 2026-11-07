#!/usr/bin/env python3
"""Derive an unbound candidate06 profile; only actual composition may bind it."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'full-engine-streaming-go5-profile-01'
OLD = '4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba'
NEW = '3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376'
PLACEHOLDER = 'ACTUAL_CANDIDATE06_COMPOSITION_REPORT_SHA_REQUIRED'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def exact(text, a, b):
    if text.count(a) != 1:
        raise RuntimeError('unexpected template preimage: ' + a[:120])
    return text.replace(a, b)

def put(name, raw):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)

def delta(a, b, name):
    return ''.join(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                      fromfile='a/candidate05/' + name, tofile='b/candidate06/' + name))

def main():
    old = (BASE / 'combined_build_streaming.py').read_bytes()
    assert sha(old) == 'acf81b5192a4832061d6feb442f40aefd42df9c95c213d62cec71c57cf3158dd'
    text = old.decode()
    text = exact(text, 'COMPOSITION = OWNER / "overlay-reconstruction-09"',
                 'COMPOSITION = OWNER / "overlay-reconstruction-10"')
    text = exact(text, 'CANDIDATE = COMPOSITION / "candidate-05"', 'CANDIDATE = COMPOSITION / "candidate-06"')
    text = exact(text, 'MANIFEST = COMPOSITION / "candidate-05-source-manifest.json"',
                 'MANIFEST = COMPOSITION / "candidate-06-source-manifest.json"')
    text = exact(text, 'MANIFEST_SHA = "' + OLD + '"', 'MANIFEST_SHA = "' + NEW + '"\n' + '''PARENT_MANIFEST_SHA = "''' + OLD + '''"
COMPOSITION_REPORT = COMPOSITION / "candidate-06-composition-report.json"
COMPOSITION_REPORT_SHA = "''' + PLACEHOLDER + '''"
COMPOSER_SOURCE = P("/home/alex/work/pocket4-candidate06-nofile-composition-source-01-20261105/compose.py")
COMPOSER_SHA = "b489e8ac7353c09c90f7c2f65b0b53c10cd0619c13308add7653dec56ba8d642"
NOFILE_ANDROID_SHA = "fbc3ca4d6e861b50da8ee537c90908b5308249015a31220acdd2d09b00f42b13"
NOFILE_HOST_SHA = "b0a03b1b95e3292131105dcb22fd59f4a767e63017197e29f4482036976a4ac2"''')
    text = exact(text, 'MATCHED_GATE = COMPOSITION / "combined-ancillary-controls-07/report.json"',
                 'MATCHED_GATE = OWNER / "overlay-reconstruction-09/combined-ancillary-controls-07/report.json"')
    text = text.replace('full-build-combined05-go5-streaming-01', 'full-build-combined06-go5-streaming-01')
    text = exact(text, 'gate["source_manifest_sha256"] == MANIFEST_SHA and',
                 'gate["source_manifest_sha256"] == PARENT_MANIFEST_SHA and')
    text = exact(text, '"matched candidate05 gate is not complete")',
                 '"original matched candidate05 gate is not complete")\n    candidate06_composition_contract()')
    helper = '''def candidate06_composition_contract():
    require(len(COMPOSITION_REPORT_SHA) == 64 and
            all(c in "0123456789abcdef" for c in COMPOSITION_REPORT_SHA),
            "new actual candidate06 composition receipt must be bound")
    no_alias(COMPOSER_SOURCE.parent)
    regular(COMPOSER_SOURCE)
    require(digest(COMPOSER_SOURCE) == COMPOSER_SHA and
            digest(COMPOSITION_REPORT) == COMPOSITION_REPORT_SHA,
            "actual candidate06 composer or receipt changed")
    scope = {"__name__": "frozen_composition_evidence_only", "__file__": str(COMPOSER_SOURCE)}
    exec(compile(COMPOSER_SOURCE.read_bytes(), str(COMPOSER_SOURCE), "exec"), scope, scope)
    report = json.loads(COMPOSITION_REPORT.read_bytes())
    parent = json.loads(scope["pinned"](scope["PARENT_MANIFEST"], PARENT_MANIFEST_SHA, 524288))
    manifest, raw = scope["derive"](parent)
    require(raw == scope["pinned"](MANIFEST, MANIFEST_SHA, 524288),
            "candidate06 source or preserved ancestry differs from the exact derivation")
    tested = scope["verify_11_sources"](manifest, scope["proof_contract"]())
    require(report["state"] == "CANDIDATE06_COMPOSED_SOURCE_NOT_BUILT" and
            report["candidate"] == str(CANDIDATE) and report["manifest"] == str(MANIFEST) and
            report["manifest_sha256"] == MANIFEST_SHA and report["parent_manifest_sha256"] == PARENT_MANIFEST_SHA and
            report["source_files"] == 948 and report["engine_files"] == 925 and
            report["changed_files"] == sorted(scope["DELTA"]) and
            report["unchanged_total_files"] == 945 and report["unchanged_engine_files"] == 922 and
            report["parent_and_authority_unchanged_after"] is True and
            report["all_11_tested_production_inputs_exact"] is True and
            report["tested_production_input_hashes"] == tested and
            report["actual_Android_build_sha256"] == scope["ANDROID_BUILD_SHA"] and
            report["actual_Android_runtime_sha256"] == NOFILE_ANDROID_SHA and
            report["actual_host_runtime_sha256"] == NOFILE_HOST_SHA and
            report["source_proof_files_root"] == str(COMPOSER_SOURCE.parent) and
            report["original_candidate05_matched_gate_sha256"] == MATCHED_GATE_SHA,
            "actual candidate06 source/evidence composition qualification differs")
    require(all(report[key] is False for key in (
            "matched_candidate05_gates_rerun_for06", "feature_default_enabled", "full_engine_built",
            "ART_built", "factory_built", "installed", "services_started", "production_ready")) and
            report["Main_actions"] == report["Android_actions"] == 0,
            "candidate06 source composition scope widened")
    return report


'''
    text = exact(text, 'def memory_admission(memory):\n', helper + 'def memory_admission(memory):\n')
    text = exact(text, '"candidate_manifest_sha256": MANIFEST_SHA, "candidate_files": 948, "engine_files": 925,',
                 '"candidate_manifest_sha256": MANIFEST_SHA, "candidate_files": 948, "engine_files": 925,\n            "parent_candidate_manifest_sha256": PARENT_MANIFEST_SHA,\n            "actual_candidate06_composition_sha256": COMPOSITION_REPORT_SHA,\n            "actual_NOFILE_Android_runtime_sha256": NOFILE_ANDROID_SHA,\n            "actual_NOFILE_host_runtime_sha256": NOFILE_HOST_SHA,')
    text = exact(text, '"candidate_manifest_sha256": MANIFEST_SHA,\n                   "builder_manifest_sha256":',
                 '"candidate_manifest_sha256": MANIFEST_SHA,\n                   "parent_candidate_manifest_sha256": PARENT_MANIFEST_SHA,\n                   "actual_candidate06_composition_sha256": COMPOSITION_REPORT_SHA,\n                   "actual_NOFILE_Android_runtime_sha256": NOFILE_ANDROID_SHA,\n                   "actual_NOFILE_host_runtime_sha256": NOFILE_HOST_SHA,\n                   "builder_manifest_sha256":')
    text = exact(text, 'require(receipt["state"] == "PREPARED_NOT_BUILT" and receipt["candidate_manifest_sha256"] == MANIFEST_SHA,',
                 'require(receipt["state"] == "PREPARED_NOT_BUILT" and receipt["candidate_manifest_sha256"] == MANIFEST_SHA and\n            receipt["parent_candidate_manifest_sha256"] == PARENT_MANIFEST_SHA and\n            receipt["actual_candidate06_composition_sha256"] == COMPOSITION_REPORT_SHA and\n            receipt["actual_NOFILE_Android_runtime_sha256"] == NOFILE_ANDROID_SHA and\n            receipt["actual_NOFILE_host_runtime_sha256"] == NOFILE_HOST_SHA,')
    text = text.replace('STARTING_COMBINED05_GO5_STREAMING_FLAG0_COLD_BUILD', 'STARTING_COMBINED06_GO5_STREAMING_FLAG0_COLD_BUILD')
    assert text.count(PLACEHOLDER) == 1
    ast.parse(text)
    put('combined_build_streaming.template.py', text.encode())
    put('controller-candidate05-to06.patch', delta(old.decode(), text, 'combined_build_streaming.py').encode())
    put('references/candidate05-combined_build_streaming.py', old)

    old_fence = (BASE / 'fenced_build_streaming.template.py').read_text()
    fence = exact(old_fence, 'acf81b5192a4832061d6feb442f40aefd42df9c95c213d62cec71c57cf3158dd',
                  'BOUND_CANDIDATE06_CONTROLLER_SHA_REQUIRED')
    fence = fence.replace('full-build-combined05-go5-streaming-01', 'full-build-combined06-go5-streaming-01')
    put('fenced_build_streaming.unbound.py', fence.encode())
    put('fence-candidate05-to06.patch', delta(old_fence, fence, 'fenced_build_streaming.template.py').encode())

    old_make = (BASE / 'make_requests.py').read_text()
    make = old_make.replace('combined05-go5-streaming', 'combined06-go5-streaming')
    make = exact(make, 'acf81b5192a4832061d6feb442f40aefd42df9c95c213d62cec71c57cf3158dd',
                 'BOUND_CANDIDATE06_CONTROLLER_SHA_REQUIRED')
    make = exact(make, 'edaa591199edc02309ab75cc6d112c15feb83e630a61e181e4ac122e272090f2',
                 'BOUND_CANDIDATE06_FENCE_SHA_REQUIRED')
    make = exact(make, 'CANDIDATE_SHA = "' + OLD + '"', 'CANDIDATE_SHA = "' + NEW + '"')
    make = make.replace('candidate05_manifest_sha256', 'candidate06_manifest_sha256')
    make = exact(make, 'require(preparation["plan"] == expected_scope["plan"](), "actual prepared plan differs from frozen profile")',
                 'require(preparation["plan"] == expected_scope["plan"](), "actual prepared plan differs from frozen profile")\n    require(preparation["parent_candidate_manifest_sha256"] == "' + OLD + '" and\n            preparation["actual_candidate06_composition_sha256"] == expected_scope["COMPOSITION_REPORT_SHA"] and\n            preparation["actual_NOFILE_Android_runtime_sha256"] == expected_scope["NOFILE_ANDROID_SHA"] and\n            preparation["actual_NOFILE_host_runtime_sha256"] == expected_scope["NOFILE_HOST_SHA"],\n            "actual candidate06 composition/probe binding differs")')
    ast.parse(make)
    put('make_requests.unbound.py', make.encode())
    put('request-generator-candidate05-to06.patch', delta(old_make, make, 'make_requests.py').encode())
    for name in ('main_snapshot.py', 'expected-runtime-builder-source-manifest.json',
                 '0008-soong-leaf-go-memory-budget.patch'):
        put(name, (BASE / name).read_bytes())
    put('references/compiled-builder-source-manifest.json', (BASE / 'references/compiled-builder-source-manifest.json').read_bytes())
    print(json.dumps({'state': 'UNBOUND_PROFILE_TEMPLATE_ONLY', 'template_sha256': sha(text.encode()),
                      'candidate06_manifest_sha256': NEW, 'actual_composition_binding_required': True,
                      'full_build_request_available': False, 'remote_actions': 0}, indent=2))

if __name__ == '__main__':
    main()
