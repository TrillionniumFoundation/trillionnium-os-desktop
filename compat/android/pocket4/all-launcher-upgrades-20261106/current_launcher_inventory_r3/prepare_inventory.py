#!/usr/bin/env python3
"""Derive only a new r3 generator from the unchanged r2 generator."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    path = HERE / name
    if path.exists():
        assert path.read_bytes() == raw, name
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    return {'path': name, 'bytes': len(raw), 'sha256': sha(raw)}


def replace_once(text, before, after):
    assert text.count(before) == 1, before[:120]
    return text.replace(before, after, 1)


def main():
    parent_path = PROJECT / 'current_launcher_inventory_r2/build_inventory.py'
    original = parent_path.read_bytes()
    assert len(original) == 13502 and sha(original) == '887fa5c8b7821f100adb7735c0ccf4e105be94339c782e8088b887b0c4ab52cc'
    parent = original.decode()
    helper = (HERE / 'current_evidence.py.inc').read_text()
    source = replace_once(parent, '"""Build a compact, evidence-linked current Launcher inventory; no target calls."""',
        '"""Build r3 using exact current48, NDK normal audit and signed ZBJ update evidence; no target calls."""')
    source = replace_once(source, '    (HERE / name).write_bytes(raw)\n',
        '    path = HERE / name\n    if path.exists():\n        assert path.read_bytes() == raw, "refuse differing existing inventory artifact: " + name\n    else:\n        with path.open("xb") as stream:\n            stream.write(raw)\n')
    source = replace_once(source, '\ndef main():\n', '\n' + helper + '\n\ndef main():\n')
    source = replace_once(source, 'def main():\n    matrix_path',
        'def main():\n    read_raw("current_launcher_inventory_r2/build_inventory.py", "887fa5c8b7821f100adb7735c0ccf4e105be94339c782e8088b887b0c4ab52cc")\n    matrix_path')
    source = replace_once(source,
        'memory-observation-after-native46-r1/actual/summary.derived.json',
        'memory-observation-after-zbj-r4-r1/actual/summary.derived.json')
    source = replace_once(source, '    memory = read(memory_path)\n',
        '    memory = read(memory_path, "184c2ef9cc197130d1bf9765fe7307196d317dc769af0962c0c61317d7c1a719")\n')
    source = replace_once(source,
        '    assert len(rows) == 46 and sum(r["original_eight"] for r in rows) == 8\n',
        '    assert len(rows) == 46 and sum(r["original_eight"] for r in rows) == 8\n    current = apply_current_observations(rows, audits, discovery, joint)\n')
    source = replace_once(source, '    assert len(installed) == 11\n', '    assert len(installed) == 12\n')
    source = replace_once(source, '"schema": "pocket4-current-launcher-inventory-v2"', '"schema": "pocket4-current-launcher-inventory-v3"')
    source = replace_once(source, '"current_scope_job": joint["job_id"]', '"membership_observation_job": joint["job_id"]')
    source = replace_once(source,
        '"summary": {"Launcher_apps": 46, "non_APEX_APK_packages": 206, "normal_APK_audit_apps": 45,\n            "normal_APK_audit_APKs": 85, "new_identity_only_apps": 1, "completed_upgrades": 11,',
        '"summary": {"Launcher_apps": 46, "non_APEX_APK_packages": 206, "normal_APK_audit_apps": 46,\n            "normal_APK_audit_APKs": 86, "new_identity_only_apps": 0, "completed_upgrades": 12,\n            "protected_scope_packages": 48, "protected_scope_APKs": 88, "membership_requeried_after_latest_install": False,')
    source = replace_once(source, '    index = save("INVENTORY.json", output)\n',
        '    output.update(current)\n    output["limitations"].extend([\n        "Membership comes from the latest complete native46/PM206 observation; the ZBJ install did not re-enumerate global membership.",\n        "Current normal metadata coverage is independently linked evidence: 44 unchanged prior audits, the direct NDK audit and same-byte S43/ZBJ installation.",\n        "The prior retention scan predates the ZBJ update; combined retained receipt logical bytes are not current allocated or reclaimable space."\n    ])\n    text = render_current_inventory(rows, output)\n    index = save("INVENTORY.json", output)\n')
    start = source.index('    text = ["# 当前全部 Launcher App 清单与修复状态"')
    stop = source.index('    print(json.dumps({"summary": output["summary"]', start)
    source = source[:start] + ('    path = HERE / "README.md"\n'
        '    raw = text.encode("utf-8")\n'
        '    if path.exists():\n'
        '        assert path.read_bytes() == raw, "refuse differing README"\n'
        '    else:\n'
        '        with path.open("xb") as stream:\n'
        '            stream.write(raw)\n') + source[stop:]
    compile(source, str(HERE / 'build_inventory.py'), 'exec')
    source_pin = put('build_inventory.py', source)
    diff = ''.join(difflib.unified_diff(parent.splitlines(True), source.splitlines(True),
        fromfile='unchanged-current-launcher-inventory-r2', tofile='new-current-launcher-inventory-r3'))
    diff_pin = put('generator-against-r2.diff', diff)
    plan = {'schema': 'pocket4-current-launcher-inventory-r3-source-plan-v1',
        'parent_generator': {'path': 'current_launcher_inventory_r2/build_inventory.py', 'bytes': len(original), 'sha256': sha(original)},
        'new_generator': source_pin, 'diff': diff_pin, 'current_status_or_r2_mutated': False,
        'required_new_actual_sources': [
            'successor_install/source-r4-zbj-full48/candidate-r1/actual-install/stdout.original.jsonl',
            'successor_install/source-r4-zbj-full48/candidate-r1/actual-install/status-01.original.json',
            'successor_install/source-r4-zbj-full48/candidate-r1/actual-install/root-validation.actual.json',
            'successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/app-scope-after.private.json',
            'successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/root-validation.actual.json',
            'successor_audit_requests/ndk_signature_metadata_r1/actual/artifact.original.json',
            'successor_audit_requests/ndk_signature_metadata_r1/actual/root-validation.actual.json',
            'successor_qa/search_click_tree_analysis_r1/CURRENT_PREINSPECTION_COMPARISON.derived.json',
            'retention_inventory_r1/observer-candidate-r2/actual-public/artifact.original.json',
            'retention_inventory_r1/recorded_entries_summary_r1/actual/stdout.original.json',
            'framework_provider_repair/normal06/current470-authorization-r1/memory-observation-after-zbj-r4-r1/actual/summary.derived.json'],
        'refuse_missing_or_hash_mismatched_actual_scope': True,
        'new_target_or_remote_calls': 0, 'private_UI_or_permission_raw_read': False,
        'normal_current_metadata_counts_expected_only_after_actual_linkage': {'apps': 46, 'APKs': 86},
        'membership_provenance_is_last_native46_observation_not_new_global_resolver': True,
        'NDK_missing_version_raw_empty_and_declared_null_preserved': True,
        'ZBJ_candidate_metadata_requires_installed_bytes_same_as_actual_S43': True,
        'latest_version_business_production_or_cleanup_qualification_added': False}
    put('SOURCE_PLAN.json', (json.dumps(plan, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps({'ok': True, 'generator': source_pin, 'diff': diff_pin, 'remote_calls': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
