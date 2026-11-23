"""Bind the immutable seven-package publication to its explicit current successor.

This is source-evidence replay. No APK, device, account or referenced host path
is opened, and metadata freshness for a new activation is never established.
"""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import PurePosixPath

CONFIG_SHA256 = '00407dfb5bb66dd839a7b6dd5b3c8f214617fb31f62dedb1e1df1c84ea7bf158'
PREFIX = 'compat/android/pocket4/'
PACKET = PREFIX + 'current-publisher-delivery-source/'
CLOSURE = PREFIX + 'current-app-input-closure/'
INPUTS = PREFIX + 'current-app-acceptance/current-source-inputs.json'
FRESHNESS = PREFIX + 'current-app-acceptance/current-source-freshness.json'
GATE = PREFIX + 'apk-content-identity/'
DOCUMENTATION = frozenset(('README.md', 'VALIDATION.json', 'SOURCE_MANIFEST.json'))
RETAINED = frozenset(('com.bestbuy.android', 'com.ehi.national.mobile', 'com.hertz.android.digital'))
ADDED = RETAINED | {'com.xunmeng.pinduoduo', 'com.sankuai.meituan.takeoutnew', 'com.ss.android.ugc.aweme'}
EXEMPT = ['com.enflick.android.TextNow', 'com.pinger.textfree', 'com.ubercab']
NO_CREDIT = frozenset(('installed', 'runtime_qualified', 'business_qualified',
    'native_compatibility_qualified', 'production_ready', 'device_profile_match_qualified',
    'abi_compatibility_verified', 'dispatch_runtime_observed', 'inner_code_executed', 'executed'))


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def decode(body):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('non-finite JSON number: ' + value)
    return json.loads(body.decode('utf-8', 'strict'), object_pairs_hook=pairs, parse_constant=constant)


def no_credit(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in NO_CREDIT:
                need(item is False, 'source evidence cannot grant ' + key)
            no_credit(item)
    elif isinstance(value, list):
        for item in value:
            no_credit(item)


def pin_matches(body, pin):
    need(type(pin['bytes']) is int and len(body) == pin['bytes'] and sha(body) == pin['sha256'],
         'complete pinned bytes differ')


def rows_by_package(rows):
    need(type(rows) is list, 'application rows must be a list')
    result = {}
    for row in rows:
        package = row['package']
        need(type(package) is str and package not in result, 'duplicate application package')
        result[package] = row
    return result


def assess(inputs, freshness, historical_inputs, historical_freshness, bodies):
    """Check current semantics separately from exact externally reviewed file pins."""
    old_apps = historical_inputs['applications']
    need(len(old_apps) == 24 and sum(x['required39_member'] is True for x in old_apps) == 23,
         'exact historical 23 required plus one dependency')
    need(inputs['applications'][:24] == old_apps, 'all previous 24 custody records remain unchanged')
    for key in ('archives', 'storage_formats', 'schema'):
        need(inputs[key] == historical_inputs[key], 'previous custody field changed: ' + key)
    old_batches = historical_inputs['source_evidence_batches']
    need(inputs['source_evidence_batches'][:len(old_batches)] == old_batches,
         'historical publication batch changed')
    apps = rows_by_package(inputs['applications'])
    need(len(apps) == 30 and set(apps) - set(rows_by_package(old_apps)) == ADDED,
         'exact six added source inputs and retained dependency')
    required = {p for p, a in apps.items() if a['required39_member'] is True}
    need(len(required) == 29 and not (required & set(EXEMPT)), '29 unique required non-system inputs')
    scope = inputs['scope']
    for key, value in historical_inputs['scope'].items():
        if key not in ('current_verified_third_party_source_input_count',
                       'remaining_current_compatible_third_party_input_count'):
            need(scope[key] == value, 'original 42/39 scope changed: ' + key)
    need(scope['selected_application_count'] == 42 and scope['required_application_count'] == 39
         and scope['required_third_party_count'] == 29 and scope['required_system_count'] == 10
         and scope['excluded_packages'] == EXEMPT and scope['extra_dependency_count'] == 1
         and scope['current_verified_third_party_source_input_count'] == 29
         and scope['remaining_current_compatible_third_party_input_count'] == 0,
         'explicit 29 obtained / zero missing source count')
    current_rows = rows_by_package(freshness['rows'])
    previous_rows = rows_by_package(historical_freshness['rows'])
    need(set(current_rows) == set(previous_rows) == required, 'complete exact 29 freshness rows')
    need(freshness['excluded_packages'] == EXEMPT
         and freshness['selected_current_source_input_count'] == 29
         and freshness['remaining_current_source_input_count'] == 0
         and sum(x['source_input_selected'] is True for x in current_rows.values()) == 29,
         'freshness scope and selected source counts')
    for package, row in current_rows.items():
        previous = previous_rows[package]
        if package not in ADDED:
            need(row == previous, 'unrelated freshness observation changed')
            continue
        need(row['source_input_selected'] is True and row['input_blocker'] is None
             and row['previous_input_blocker'] == previous['input_blocker'], 'selected input provenance')
        for key in ('version_observations', 'source_availability_observations'):
            need(row.get(key) == previous.get(key), 'historical source observation changed')
        old_complete = previous.get('complete_inputs', [])
        need(row['complete_inputs'][:len(old_complete)] == old_complete,
             'previous partial or older input observations removed')
    no_credit(inputs)
    no_credit(freshness)
    summary = decode(bodies[CLOSURE + 'SOURCE-INPUT-SUMMARY.json'])
    need(summary['new_source_input_count'] == 6 and set(summary['new_required_inputs']) == ADDED
         and summary['current_required_third_party_inputs'] == 29
         and summary['remaining_required_source_inputs'] == []
         and summary['user_exempt_packages'] == EXEMPT, 'current successor summary')
    for package in sorted(ADDED):
        app = apps[package]
        candidate_path = CLOSURE + 'candidates/' + package + '.json'
        receipt_path = CLOSURE + 'receipts/' + package + '.json'
        native_path = CLOSURE + 'native-inputs/' + package + '.json'
        candidate = decode(bodies[candidate_path])
        receipt = decode(bodies[receipt_path])
        native = decode(bodies[native_path])
        for proof in app['proofs'].values():
            if proof['path'].startswith(CLOSURE):
                pin_matches(bodies[proof['path']], proof)
            else:
                need(package in RETAINED and proof == previous_rows[package]
                     ['source_availability_observations'][0]['metadata'], 'original public metadata pin changed')
        need(app['proofs'] == summary['source_records'][package], 'summary source records differ')
        need(candidate['package'] == native['application']['package'] == package,
             'candidate and native package mismatch')
        need(candidate['version_name'] == app['version_name']
             and candidate['version_code'] == app['version_code'], 'candidate version mismatch')
        need(native['application']['expected_input'] == app['expected_input'], 'native expected input differs')
        pin_matches(bodies[candidate_path], receipt['candidate'])
        pin_matches(bodies[candidate_path], native['candidate'])
        pin_matches(bodies[receipt_path], app['expected_input']['source_receipt'])
        need(receipt['source_observation'] == candidate['source'], 'candidate source differs from actual receipt')
        need(app['storage']['fresh_destination_custody_required_before_installation'] is True,
             'destination custody remains required')
        no_credit(candidate)
        no_credit(receipt)
        no_credit(native)
        identities = receipt.get('identities', [receipt.get('identity')])
        expected = app['expected_input']['apks']
        pins = {x['sha256']: x for x in expected}
        need(len(pins) == len(expected) == len(identities), 'complete distinct actual APK set')
        actual_hashes = {x['sha256'] for x in identities}
        need(len(actual_hashes) == len(identities) and actual_hashes == set(pins),
             'every expected APK has exactly one actual signed identity')
        for identity in identities:
            allowed_names = (app['version_name'],) if identity['split_name'] is None else ('', app['version_name'])
            need(identity['package'] == package and identity['long_version_code'] == app['version_code']
                 and identity['version_name'] in allowed_names and identity['signature_verified'] is True
                 and identity['signer_certificate_sha256'] == candidate['signer_certificate_sha256'],
                 'actual APK package/version/signer mismatch')
            need(identity['sha256'] in pins and identity['bytes'] == pins[identity['sha256']]['bytes']
                 and all(x == 0 for x in identity['tool_exits'].values()), 'actual signed APK pins and SDK exits')
        if package in RETAINED:
            current = receipt['current_source_validation']
            need(current['current_metadata_restriction'] == 'UNAVAILABLE_COUNTRY'
                 and current['current_metadata_restriction_code'] == 4
                 and current['current_delivery_obtained'] is False
                 and receipt['current_delivery_obtained'] is False
                 and receipt['publisher_archive_obtained'] is False
                 and receipt['authenticated_transport_replayed'] is False,
                 'retained source cannot become a new available delivery')
            observed = datetime.fromisoformat(current['latest_release_identity_observed_utc'].replace('Z', '+00:00'))
            due = datetime.fromisoformat(current['metadata_revalidation_due_utc'])
            verified = datetime.fromisoformat(receipt['verified_utc'])
            need(observed.tzinfo is not None and due.tzinfo is not None and verified.tzinfo is not None
                 and due == observed + timedelta(hours=24) and observed <= verified <= due,
                 'metadata was fresh at historical receipt publication')
            need(receipt['split_closure']['manifest_dependency_closure_verified'] is True
                 and receipt['split_closure']['base_count'] == 1
                 and all(x['all_member_crc_verified'] is True for x in receipt['complete_zip_integrity']),
                 'retained split and ZIP integrity closure')
    migration = current_rows['com.sankuai.meituan.takeoutnew']['signer_migration_gate']
    need(migration['state'] == 'PENDING' and migration['old_app_or_data_uninstalled'] is False
         and migration['same_package_data_preserving_upgrade_qualified'] is False
         and migration['recorded_installed_signers'] != migration['current_candidate_signers']
         and apps['com.sankuai.meituan.takeoutnew']['signer_migration_qualified'] is False,
         'Meituan signer migration is not qualified by source evidence')
    need(apps['com.ss.android.ugc.aweme']['version_code'] == 410201
         and apps['com.ss.android.ugc.aweme']['distribution'] == 'public_mirror',
         'formal Douyin release and explicit public-mirror distribution')
    return {'current_required_third_party_inputs': 29, 'remaining_required_third_party_inputs': 0,
            'new_source_inputs': 6, 'activation_requires_fresh_metadata_and_destination_custody': True,
            'latest_versions_verified_by_replay': False, 'installed': False,
            'runtime_qualified': False, 'business_qualified': False,
            'native_compatibility_qualified': False, 'production_ready': False}


class Successor:
    def __init__(self, read, historical_manifest_body):
        self.read = read
        raw = read(PACKET + 'CURRENT-SUCCESSOR.json')
        need(sha(raw) == CONFIG_SHA256, 'externally fixed successor definition')
        config = decode(raw)
        need(config['schema'] == 'pocket4-publisher-source-current-successor-v1'
             and config['historical_publication_manifest_sha256'] == sha(historical_manifest_body),
             'exact original publication retained')
        self.history = config['historical_registry_bindings']
        need(set(self.history) == {INPUTS, FRESHNESS}, 'only two exact historical registry snapshots')
        self.bodies = {}
        for pin in config['current_files']:
            path = pin['path']
            parts = PurePosixPath(path)
            need(not parts.is_absolute() and '..' not in parts.parts and path not in self.bodies,
                 'unique relative current source pin')
            body = read(path)
            pin_matches(body, pin)
            self.bodies[path] = body
        need(len(self.bodies) == 37, 'complete independently reviewed 37-file successor')
        for row in decode(self.bodies[CLOSURE + 'MANIFEST.json'])['files']:
            pin_matches(self.bodies[row['path']], row)

    def historical_registry(self, path):
        pin = self.history[path]
        need(pin['path'].startswith(PACKET + 'historical-registry/'), 'explicit historical registry location')
        body = self.read(pin['path'])
        pin_matches(body, pin)
        return body

    def check_documentation(self, name):
        need(name in DOCUMENTATION, 'only three superseded documentation records')
        need(self.read(GATE + name) == self.bodies[GATE + name], 'exact reviewed current documentation')

    def verify(self):
        return assess(decode(self.bodies[INPUTS]), decode(self.bodies[FRESHNESS]),
                      decode(self.historical_registry(INPUTS)), decode(self.historical_registry(FRESHNESS)),
                      self.bodies)
