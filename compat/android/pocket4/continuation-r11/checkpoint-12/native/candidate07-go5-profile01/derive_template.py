#!/usr/bin/env python3
"""Derive a fresh candidate07 profile without submitting a remote request."""
import ast
import difflib
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
BASE = WORK / 'full-engine-candidate06-go5-profile-01'
OLD = '3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376'
NEW = 'e10024548a5b2b5a391ecc9ddb3ea2f19b95a6fea3437f40207a0f4721745a93'
PLACEHOLDER = 'ACTUAL_CANDIDATE07_COMPOSITION_REPORT_SHA_REQUIRED'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError('ambiguous preimage: ' + before[:160])
    return text.replace(before, after)


def put(name, raw):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        assert stream.write(raw) == len(raw)


def patch(before, after, name):
    return ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                       fromfile='candidate06/' + name, tofile='candidate07/' + name)).encode()


def main():
    original = (WORK / 'full-engine-candidate06-go5-bound-01/combined_build_streaming.py').read_bytes()
    assert sha(original) == 'b42ee9229dfac7b62bb04472e39568867fc53d695389b2214c8bbfd9e0f83619'
    text = original.decode()
    text = exact(text, 'COMPOSITION = OWNER / "overlay-reconstruction-10"',
                 'COMPOSITION = OWNER / "overlay-reconstruction-11"')
    text = text.replace('candidate-06', 'candidate-07').replace('candidate06', 'candidate07')
    text = text.replace('combined06', 'combined07').replace('COMBINED06', 'COMBINED07')
    text = exact(text, 'MANIFEST_SHA = "' + OLD + '"', 'MANIFEST_SHA = "' + NEW + '"')
    text = exact(text, 'COMPOSITION_REPORT_SHA = "f49173e0527e336f5d5ff5af489a2dfa97ceaba247f0fc3657c9a68ca242922a"',
                 'COMPOSITION_REPORT_SHA = "' + PLACEHOLDER + '"\n'
                 'CANDIDATE06_MANIFEST_SHA = "' + OLD + '"\n'
                 'CANDIDATE06_COMPOSITION_SHA = "f49173e0527e336f5d5ff5af489a2dfa97ceaba247f0fc3657c9a68ca242922a"\n'
                 'UAPI_TU_GATE_SHA = "5a09aa094c960a2bcc2d357fa732aac0cdb95203d25d3b690ced62497bb1c1d1"')
    text = exact(text, '/home/alex/work/pocket4-candidate07-nofile-composition-source-01-20261105/compose.py',
                 '/home/alex/work/pocket4-candidate07-host-uapi-composition-source-01-20261105/compose.py')
    text = exact(text, 'COMPOSER_SHA = "b489e8ac7353c09c90f7c2f65b0b53c10cd0619c13308add7653dec56ba8d642"',
                 'COMPOSER_SHA = "8466ad04f84e84b6297687402350b0d1e35e9f2b1ece2ce113748b5df8e7b157"')
    begin = text.index('def candidate07_composition_contract():')
    end = text.index('def memory_admission(memory):', begin)
    helper = '''def candidate07_composition_contract():
    require(len(COMPOSITION_REPORT_SHA) == 64 and
            all(c in "0123456789abcdef" for c in COMPOSITION_REPORT_SHA),
            "new actual candidate07 composition receipt must be bound")
    no_alias(COMPOSER_SOURCE.parent)
    regular(COMPOSER_SOURCE)
    require(digest(COMPOSER_SOURCE) == COMPOSER_SHA and
            digest(COMPOSITION_REPORT) == COMPOSITION_REPORT_SHA,
            "actual candidate07 composer or receipt changed")
    scope = {"__name__": "frozen_composition_evidence_only", "__file__": str(COMPOSER_SOURCE)}
    exec(compile(COMPOSER_SOURCE.read_bytes(), str(COMPOSER_SOURCE), "exec"), scope, scope)
    report = json.loads(COMPOSITION_REPORT.read_bytes())
    parent = json.loads(scope["pinned"](scope["PARENT_MANIFEST"], CANDIDATE06_MANIFEST_SHA, 524288))
    parent_contract = scope["load_source"]("references/base-source-contract.py", scope["BASE_CONTRACT_SHA"])
    require(parent_contract["source_contract"]()[0] == parent["files"],
            "candidate06 source and preserved original NOFILE proof changed")
    manifest, raw = scope["derive"](parent)
    require(raw == scope["pinned"](MANIFEST, MANIFEST_SHA, 524288),
            "candidate07 source or ancestry differs from its exact derivation")
    gate = scope["proof_contract"]()
    require(report["state"] == "CANDIDATE07_COMPOSED_SOURCE_NOT_BUILT" and
            report["candidate"] == str(CANDIDATE) and report["manifest"] == str(MANIFEST) and
            report["manifest_sha256"] == MANIFEST_SHA and
            report["parent_manifest_sha256"] == CANDIDATE06_MANIFEST_SHA and
            report["parent_composition_sha256"] == CANDIDATE06_COMPOSITION_SHA and
            report["source_files"] == 949 and report["engine_files"] == 926 and
            report["changed_files"] == sorted(name for name, row in scope["DELTA"].items() if row[0] is not None) and
            report["added_files"] == sorted(name for name, row in scope["DELTA"].items() if row[0] is None) and
            report["unchanged_total_files"] == 944 and report["unchanged_engine_files"] == 921 and
            report["parent_and_authority_unchanged_after"] is True and
            report["parent_NOFILE_host_and_Android_proof_revalidated"] is True and
            report["actual_complete_TU_gate_sha256"] == UAPI_TU_GATE_SHA == scope["GATE_SHA"] and
            report["actual_original_missing_header_failure_reproduced"] is True and
            report["actual_complete_candidate_TUs"] == len(gate["compiled_TUs"]) == 5 and
            report["original_host_warning_target_and_sysroot_flags_preserved"] is True and
            report["all_five_composition_inputs_in_actual_compiled_dependencies"] is True and
            report["source_proof_files_root"] == str(COMPOSER_SOURCE.parent) and
            report["original_candidate05_matched_gate_sha256"] == MATCHED_GATE_SHA,
            "actual candidate07 source or complete TU qualification differs")
    require(all(report[key] is False for key in (
            "matched_candidate05_gates_rerun_for07", "NOFILE_Android_runtime_rerun_after_header_delta",
            "feature_default_enabled", "full_engine_built", "ART_built", "factory_built", "installed",
            "services_started", "production_ready")) and report["Main_actions"] == report["Android_actions"] == 0,
            "candidate07 composition scope widened")
    return report


'''
    text = text[:begin] + helper + text[end:]
    text = re.sub(r'\b948\b', '949', text)
    text = re.sub(r'\b925\b', '926', text)
    text = text.replace('"parent_candidate_manifest_sha256": PARENT_MANIFEST_SHA,',
                        '"parent_candidate_manifest_sha256": CANDIDATE06_MANIFEST_SHA,\n'
                        '            "actual_complete_TU_gate_sha256": UAPI_TU_GATE_SHA,')
    text = exact(text, '                   "parent_candidate_manifest_sha256": CANDIDATE06_MANIFEST_SHA,\n'
                 '            "actual_complete_TU_gate_sha256": UAPI_TU_GATE_SHA,',
                 '                   "parent_candidate_manifest_sha256": CANDIDATE06_MANIFEST_SHA,\n'
                 '                   "actual_complete_TU_gate_sha256": UAPI_TU_GATE_SHA,')
    text = exact(text, 'receipt["parent_candidate_manifest_sha256"] == PARENT_MANIFEST_SHA and',
                 'receipt["parent_candidate_manifest_sha256"] == CANDIDATE06_MANIFEST_SHA and\n'
                 '            receipt["actual_complete_TU_gate_sha256"] == UAPI_TU_GATE_SHA and')
    assert text.count(PLACEHOLDER) == 1
    ast.parse(text)
    put('combined_build_streaming.template.py', text.encode())
    put('references/candidate06-combined_build_streaming.py', original)
    put('controller-candidate06-to07.patch', patch(original.decode(), text, 'combined_build_streaming.py'))

    old_fence = (BASE / 'fenced_build_streaming.unbound.py').read_text()
    fence = old_fence.replace('CANDIDATE06', 'CANDIDATE07').replace('combined06', 'combined07')
    ast.parse(fence)
    put('fenced_build_streaming.unbound.py', fence.encode())
    put('fence-candidate06-to07.patch', patch(old_fence, fence, 'fenced_build_streaming.unbound.py'))

    old_make = (BASE / 'make_requests.unbound.py').read_text()
    make = old_make.replace('CANDIDATE06', 'CANDIDATE07').replace('candidate06', 'candidate07').replace('combined06', 'combined07')
    make = exact(make, 'CANDIDATE_SHA = "' + OLD + '"', 'CANDIDATE_SHA = "' + NEW + '"')
    make = re.sub(r'\b925\b', '926', make)
    make = exact(make, 'preparation["parent_candidate_manifest_sha256"] == "4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba" and',
                 'preparation["parent_candidate_manifest_sha256"] == "' + OLD + '" and\n'
                 '            preparation["actual_complete_TU_gate_sha256"] == expected_scope["UAPI_TU_GATE_SHA"] and')
    ast.parse(make)
    put('make_requests.unbound.py', make.encode())
    put('request-generator-candidate06-to07.patch', patch(old_make, make, 'make_requests.py'))

    binder = (BASE / 'bind_composition.py').read_text()
    binder_old = binder
    binder = binder.replace('candidate06', 'candidate07').replace('CANDIDATE06', 'CANDIDATE07')
    binder = exact(binder, "result['all_11_tested_production_inputs_exact'] is True and", "result['parent_NOFILE_host_and_Android_proof_revalidated'] is True and\n         result['actual_original_missing_header_failure_reproduced'] is True and\n         result['all_five_composition_inputs_in_actual_compiled_dependencies'] is True and")
    binder = exact(binder, "('matched_candidate05_gates_rerun_for06',", "('matched_candidate05_gates_rerun_for07','NOFILE_Android_runtime_rerun_after_header_delta',")
    ast.parse(binder)
    put('bind_composition.py', binder.encode())
    put('binder-candidate06-to07.patch', patch(binder_old, binder, 'bind_composition.py'))

    for name in ('main_snapshot.py', 'expected-runtime-builder-source-manifest.json',
                 '0008-soong-leaf-go-memory-budget.patch', 'references/compiled-builder-source-manifest.json'):
        put(name, (BASE / name).read_bytes())
    spec = json.loads((WORK / 'candidate07-host-uapi-integration-01/SOURCE_DELTA.json').read_bytes())
    expected = {
        'schema': 1,
        'candidate': '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/overlay-reconstruction-11/candidate-07',
        'manifest': '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/overlay-reconstruction-11/candidate-07-source-manifest.json',
        'manifest_sha256': NEW, 'parent_manifest_sha256': OLD,
        'parent_composition_sha256': 'f49173e0527e336f5d5ff5af489a2dfa97ceaba247f0fc3657c9a68ca242922a',
        'source_files': 949, 'engine_files': 926,
        'changed_files': sorted('engine/' + row['path'] for row in spec['changes'] if row['before_sha256'] is not None),
        'added_files': sorted('engine/' + row['path'] for row in spec['changes'] if row['before_sha256'] is None),
        'unchanged_total_files': 944, 'unchanged_engine_files': 921,
        'actual_complete_TU_gate_sha256': '5a09aa094c960a2bcc2d357fa732aac0cdb95203d25d3b690ced62497bb1c1d1',
        'actual_complete_candidate_TUs': 5,
        'original_host_warning_target_and_sysroot_flags_preserved': True,
        'source_proof_files_root': '/home/alex/work/pocket4-candidate07-host-uapi-composition-source-01-20261105',
        'original_candidate05_matched_gate_sha256': 'e53c3e9e5846d36f971bae6140c394b837fa54525c0e2df4ac153c9ef5540803'}
    put('expected-source-integration.json', (json.dumps(expected, indent=2) + '\n').encode())
    # Compare all functions, including those intentionally changed. This is an
    # implementation inventory check, not a substitute for the real build.
    a = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(original).body if isinstance(n, ast.FunctionDef)}
    z = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    unchanged = sorted(k for k in a.keys() & z.keys() if a[k] == z[k])
    changed = sorted(k for k in a.keys() & z.keys() if a[k] != z[k])
    assert set(changed) == {'build','matched_gate_contract','source_contract','plan','prepare','verify_prepared'}
    assert a.keys() - z.keys() == {'candidate06_composition_contract'}
    assert z.keys() - a.keys() == {'candidate07_composition_contract'}
    put('LOCAL_SOURCE_DERIVATION.json', (json.dumps({
        'schema': 1, 'state': 'UNBOUND_SOURCE_PROFILE', 'parent_controller_sha256': sha(original),
        'template_sha256': sha(text.encode()), 'unchanged_functions': unchanged,
        'changed_functions': changed, 'new_composition_contract': True,
        'same_builder_ELF': 'ea80146d5fc47f9927dd16a1ad91b6b48f0b30f0ce043d4eaef53f0e84f482b6',
        'same_compiled_450_manifest': '6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4',
        'same_runtime_450_manifest': '776435c88ca6ddb983456c639ca051e586731140394756f33abe53dc478357e3',
        'memory_max_GiB': 10, 'swap_max_GiB': 1, 'minimum_fresh_available_GiB': 13,
        'minimum_fresh_swap_free_GiB': 2, 'cpu_cores': 2, 'jobs': 1,
        'complete_build_targets_and_warnings_unchanged': True,
        'Main_snapshot_unchanged': True, 'normal_projection_recovery_unchanged': True,
        'fresh_out_and_attempt': True, 'actual_composition_bound': False,
        'full_build_started': False, 'remote_actions': 0, 'production_ready': False}, indent=2) + '\n').encode())
    print(json.dumps({'template_sha256': sha(text.encode()), 'unmodified_functions': len(unchanged),
                      'changed_functions': changed, 'requires_actual_composition': True, 'remote_actions': 0}))


if __name__ == '__main__':
    main()
