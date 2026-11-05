#!/usr/bin/env python3
"""Merge retained App evidence and a complete inventory; never operate a device.

Inventory and progress summaries cannot pass a production gate. Optional gate
reviews must bind current inventory/epoch/UID/version, exact APK, checklist and
hash-verified evidence. Historical failures remain visible after a newer review.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
HEX = re.compile(r'[0-9a-f]{64}')
PACKAGE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+')
RETAIN = {'com.android.camera2', 'com.android.settings', 'local.pocket4.fixture',
          'org.chromium.webview_shell', 'org.droidloom.qa.editorcontract',
          'com.android.threadnetwork.demoapp', 'com.google.android.gms'}


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path):
    raw = Path(path).read_bytes()
    need(len(raw) <= 4 * 1024 * 1024, 'input exceeds 4 MiB')
    return json.loads(raw, object_pairs_hook=unique_pairs), {
        'file': Path(path).name, 'sha256': sha(raw), 'bytes': len(raw)}


def stamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.tzinfo is not None, 'timestamp must include timezone')
    return parsed


def inventory_data(value):
    if 'inventory' in value:
        need(value.get('ok') is True, 'inventory wrapper did not succeed')
        value = value['inventory']
    complete = (value.get('complete_package_manager_queries') is True or
                (value.get('all_package_manager_queries_succeeded') is True
                 and value.get('complete_launcher_parsing') is True
                 and value.get('complete_package_manager_inventory') is True))
    need(value.get('read_only') is True and complete,
         'fresh inventory is incomplete or not a read-only receipt')
    need(HEX.fullmatch(value.get('framework_epoch_sha256', '')), 'inventory epoch missing')
    stamp(value['observed_at_utc'])
    rows = value['installed_packages']
    installed = {}
    for row in rows:
        package = row['package']
        need(package == 'android' or PACKAGE.fullmatch(package), 'invalid inventory package')
        need(package not in installed, 'duplicate inventory package')
        need(type(row['version_code']) is int and row['version_code'] >= 0
             and type(row['uid']) is int and row['uid'] >= 0, 'invalid inventory identity')
        installed[package] = row
    launchers = value['launcher_packages']
    components = value['launcher_components']
    need(len(set(launchers)) == len(launchers) and set(launchers) <= set(installed),
         'invalid or duplicated launcher packages')
    need(len(set(components)) == len(components) and all(
        re.fullmatch(r'[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+', c) for c in components),
        'invalid or duplicated launcher components')
    need({c.split('/')[0] for c in components} == set(launchers), 'launcher/package coverage differs')
    need(value['installed_package_count'] == len(installed)
         and value['launcher_package_count'] == len(launchers)
         and value['launcher_component_count'] == len(components), 'inventory counts differ')
    for field in ('third_party_packages', 'disabled_packages'):
        need(len(set(value[field])) == len(value[field]) and set(value[field]) <= set(installed),
             'invalid inventory subset: ' + field)
    return value, installed


def history_index(history, baseline):
    aliases = {row['app']: row['package'] for row in baseline}
    result = {row['package']: [] for row in baseline}
    arrays = ('latest_manual_updates', 'dated_app_observations', 'dated_guest_business_results',
              'current_business_flows')
    for array in arrays:
        for index, row in enumerate(history.get(array, [])):
            packages = [row.get('package') or aliases.get(row.get('app'))]
            packages += [aliases.get(name) for name in row.get('apps', [])]
            for package in set(packages) & set(result):
                item = {'source': 'historical', 'pointer': '/' + array + '/' + str(index)}
                for key in ('status', 'evidence_run', 'evidence_at_utc', 'observation_utc',
                            'evidence_date_utc', 'flow', 'notes', 'visual_issue', 'newer_regression'):
                    if key in row and row[key]:
                        item[key] = row[key]
                item['gate_credit'] = False
                result[package].append(item)
    return result


def checked_reviews(path):
    if path is None:
        return [], None
    document, pin = read_json(path)
    need(document.get('schema') == 'pocket4-reviewed-app-gates-v1', 'unknown gate-review schema')
    root = Path(path).resolve().parent
    reviews = document['reviews']
    seen = set()
    for row in reviews:
        need(row['id'] not in seen and isinstance(row.get('reviewer'), str) and row['reviewer'],
             'duplicate review or missing reviewer')
        seen.add(row['id'])
        need(row.get('scope') in ('scoped', 'whole_app_release'), 'review scope missing')
        need(HEX.fullmatch(row.get('apk_sha256', '')), 'review exact APK missing')
        need(row.get('evidence'), 'review requires evidence files')
        for evidence in row['evidence']:
            relative = Path(evidence['path'])
            need(not relative.is_absolute() and '..' not in relative.parts, 'evidence path must stay in review bundle')
            actual = (root / relative).resolve()
            need(actual.is_relative_to(root), 'evidence symlink escaped review bundle')
            need(sha(actual.read_bytes()) == evidence['sha256'], 'review evidence hash differs')
        row['_evidence_verified'] = True
    return reviews, pin


def build_matrix(baseline, historical, plans, progress, inventory=None, reviews=(), sources=None):
    old = baseline['apps']
    old_by_package = {row['package']: row for row in old}
    need(len(old) == len(old_by_package) == baseline['launcher_package_count'] == 45,
         'the immutable 45-App baseline must be retained in full')
    need(RETAIN <= set(old_by_package), 'system or support entries disappeared from baseline')
    need(set(old_by_package) <= set(plans['packages']), 'baseline App has no concrete checklist')
    current, installed = (inventory_data(inventory) if inventory is not None else (None, {}))
    launchers = set(current['launcher_packages']) if current else set()
    tracked = set(old_by_package) | launchers
    epoch = current['framework_epoch_sha256'] if current else baseline['framework_epoch_sha256']
    history = history_index(historical, old)
    by_progress = {}
    for row in progress.get('apps', []):
        need(row['package'] in tracked, 'progress names an App outside retained/current scope')
        by_progress.setdefault(row['package'], []).append(row)
    by_review = {}
    for row in reviews:
        need(row.get('_evidence_verified') is True, 'unverified gate-review evidence')
        need(row['package'] in tracked, 'review names an untracked App')
        by_review.setdefault(row['package'], []).append(row)
    common = plans['common_gates']
    output, ignored = [], []
    for package in sorted(tracked):
        prior = old_by_package.get(package)
        plan = plans['packages'].get(package, {
            'app': package, 'kind': 'new_unclassified_launcher', 'profile': 'unclassified',
            'prerequisites': ['Define and review this exact App release checklist.']})
        profile = plans['profiles'][plan['profile']]
        required = list(common) + list(profile['checks'])
        gates = {key: 'pending' for key in required}
        gate_evidence = {}
        accepted, full_release_review = [], None
        current_review_apk = None
        last_failure = None
        for observation in by_progress.get(package, []):
            expected_version = installed.get(package, {}).get('version_code',
                prior['installed_version_code'] if prior else None)
            if (observation.get('framework_epoch_sha256') == epoch
                    and observation.get('version_code') == expected_version):
                for key, state in observation.get('unpassed_checks', {}).items():
                    need(key in gates and state in ('failed', 'blocked', 'pending'),
                         'progress can only retain known unpassed gates')
                    gates[key] = state
                    gate_evidence[key] = observation['id']
                if observation.get('unpassed_checks'):
                    # Some retained summaries have no event timestamp. Their
                    # explicitly labelled review time is a conservative cutoff.
                    observed = stamp(observation.get('observed_at_utc') or observation['reviewed_at_utc'])
                    last_failure = max(last_failure, observed) if last_failure else observed
        for review in sorted(by_review.get(package, []), key=lambda r: stamp(r['observed_at_utc'])):
            expected = installed.get(package)
            valid = bool(current and expected and review['framework_epoch_sha256'] == epoch
                         and review['version_code'] == expected['version_code'] and review['uid'] == expected['uid']
                         and stamp(review['observed_at_utc']) >= stamp(current['observed_at_utc'])
                         and (last_failure is None or stamp(review['observed_at_utc']) >= last_failure))
            if not valid:
                ignored.append({'id': review['id'], 'reason': 'stale_or_different_inventory_epoch_uid_version'})
                continue
            if current_review_apk is not None and current_review_apk != review['apk_sha256']:
                # A same-version replacement still invalidates every old binary's gate.
                gates = {key: 'pending' for key in required}
                gate_evidence = {}
                accepted, full_release_review = [], None
            current_review_apk = review['apk_sha256']
            need(set(review['checks']) <= set(required), 'review has unknown gate IDs')
            for key, state in review['checks'].items():
                need(state in ('passed', 'failed', 'blocked', 'pending'), 'unknown gate state')
                if key == 'release_scope' and state == 'passed':
                    need(review['scope'] == 'whole_app_release'
                         and review.get('all_features_reviewed') is True
                         and review.get('retained_failures_reconciled') is True
                         and review.get('unresolved_findings') == [], 'scoped results cannot pass full release scope')
                    full_release_review = review['id']
                gates[key] = state
                gate_evidence[key] = review['id']
            if review.get('unresolved_findings'):
                gates['release_scope'] = 'blocked'
                full_release_review = None
            accepted.append(review['id'])
        if plan['profile'] == 'unclassified':
            gates['release_scope'] = 'pending'
        present = package in installed if current else None
        enabled = package not in current['disabled_packages'] if current and present else None
        ready = bool(current and present and enabled and full_release_review
                     and all(state == 'passed' for state in gates.values()))
        row = {'package': package, 'app': plan['app'], 'kind': plan['kind'],
               'retained_from_baseline': prior is not None, 'profile': plan['profile'],
               'inventory_state': ('baseline_only' if current is None else
                   'not_installed' if not present else 'disabled' if not enabled else
                   'installed_launcher' if package in launchers else 'installed_without_launcher'),
               'current_identity': installed.get(package),
               'baseline_version_code': prior['installed_version_code'] if prior else None,
               'baseline_status': prior['status'] if prior else None,
               'prior_evidence': history.get(package, []), 'progress': by_progress.get(package, []),
               'gate_results': gates, 'unpassed_gates': [key for key, state in gates.items() if state != 'passed'],
               'gate_evidence': gate_evidence, 'accepted_reviews': accepted,
               'reviewed_apk_sha256': current_review_apk,
               'prerequisites': plan.get('prerequisites', []),
               'production_ready': ready}
        if prior and prior.get('evidence'):
            row['baseline_evidence'] = prior['evidence']
        if current and prior:
            row['installed_version_changed'] = present and installed[package]['version_code'] != prior['installed_version_code']
        output.append(row)
    ready_count = sum(row['production_ready'] for row in output)
    return {
        'schema': 'pocket4-all-tracked-app-readiness-v2', 'read_only_generated': True,
        'framework_epoch_sha256': epoch, 'sources': sources or {},
        'baseline_observed_at_utc': baseline['observed_at_utc'],
        'inventory_observed_at_utc': current['observed_at_utc'] if current else None,
        'inventory_complete': current is not None, 'baseline_tracked_count': 45,
        'tracked_app_count': len(output), 'current_launcher_count': len(launchers) if current else None,
        'current_installed_package_count': len(installed) if current else None,
        'current_third_party_package_count': len(current['third_party_packages']) if current else None,
        'new_launcher_packages': sorted(launchers - set(old_by_package)),
        'retained_baseline_packages_not_current_launchers': sorted(set(old_by_package) - launchers) if current else [],
        'production_ready_count': ready_count, 'not_production_ready_count': len(output) - ready_count,
        'all_apps_production_ready': bool(current and ready_count == len(output)),
        'kind_counts': dict(sorted(Counter(row['kind'] for row in output).items())),
        'status_rule': 'Inventory, launch, build, and scoped progress never grant gate credit; full release scope requires an explicit current evidence review.',
        'common_gates': common, 'business_profiles': plans['profiles'],
        'platform_workstreams': progress.get('platform_workstreams', []),
        'ignored_reviews': ignored, 'apps': output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=HERE / 'inputs/launcher-matrix-baseline-20261104.json')
    parser.add_argument('--historical', type=Path, default=HERE / 'inputs/historical-readiness-20261104.json')
    parser.add_argument('--plans', type=Path, default=HERE / 'app-gates.json')
    parser.add_argument('--progress', type=Path, default=HERE / 'progress.json')
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--gate-reviews', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    values, sources = {}, {}
    for name in ('baseline', 'historical', 'plans', 'progress', 'inventory'):
        path = getattr(args, name)
        if path is not None:
            values[name], sources[name] = read_json(path)
    reviews, review_pin = checked_reviews(args.gate_reviews)
    if review_pin:
        sources['gate_reviews'] = review_pin
    matrix = build_matrix(values['baseline'], values['historical'], values['plans'], values['progress'],
                          values.get('inventory'), reviews, sources)
    # Inputs are immutable; each invocation creates a distinct reviewable output.
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(matrix, out, indent=2, ensure_ascii=False)
        out.write('\n')
    print(json.dumps({key: matrix[key] for key in ('tracked_app_count', 'current_launcher_count',
        'current_installed_package_count', 'production_ready_count', 'all_apps_production_ready')}))


if __name__ == '__main__':
    main()
