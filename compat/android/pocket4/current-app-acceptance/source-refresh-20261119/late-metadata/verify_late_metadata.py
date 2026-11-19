#!/usr/bin/env python3
"""Consume frozen public metadata receipts; never revalidate APKs or activation."""
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

ROOT = Path(__file__).resolve().parent
EXCLUDED = ['com.enflick.android.TextNow', 'com.pinger.textfree', 'com.ubercab']
EXPIRY = '2026-11-19T17:44:09.086253+00:00'
TTL_PACKAGES = {'com.bestbuy.android', 'com.ehi.national.mobile', 'com.hertz.android.digital'}
TIMEOUTS = {'com.lianjia.beike', 'tv.danmaku.bili'}
MIRRORS = {'com.amazon.mShop.android.shopping', 'com.rytong.airchina'}
SYSTEM_OBSERVATIONS = {'system-gsi-release-list', 'system-gsi-cp3a-details'}
REMOTE = '/home/qq/work/p4-source-freshness-check-5cd1-20261119-r1/actual/'
INPUT_NAMES = {'PLAN.json','FRESHNESS-GATE-AUDIT.json','PRIMARY-IDENTITY-CONTROLS.json',
    'public_metadata_fetch.py','parse_public_metadata.py','retry_two_timeouts.py',
    'check_selected_origins.py','observe_publisher_redirect_head.py'} | {
    'actual/'+name for name in ('HTTP-OBSERVATIONS.json','PARSED-OBSERVATIONS.json',
    'TWO-TIMEOUT-RETRY.json','SELECTED-ORIGIN-SUPPLEMENT.json','PUBLISHER-REDIRECT-HEAD.json',
    'fetch-execution.json','parse-execution.json','retry-execution.json','origins-execution.json',
    'publisher-head-execution.json','metadata-units-retirement.json','RECORDED-LAUNCH-ARGUMENTS.json')}
FORBIDDEN_CREDIT = {'installed','runtime_qualified','business_qualified','production_ready',
    'all39_latest_qualified','activation_metadata_revalidated','source_inputs_changed',
    'source_identity_requalified','authoritative_play_metadata_TTL_renewed',
    'account_or_credentials_accessed','authentication_used','cookies_used'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def strict_json(body):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'duplicate metadata key')
            value[key] = item
        return value
    return json.loads(body, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def pin(body):
    return {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}


def read(name):
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and '..' not in relative.parts, 'fixed relative metadata member')
    path = ROOT/name
    info = path.lstat()
    require(path.resolve() == path and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and info.st_size <= 1024*1024, 'bounded ordinary metadata member')
    body = path.read_bytes()
    require(len(body) == info.st_size, 'complete metadata member')
    return body


def no_credit(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_CREDIT:
                require(item is False, 'public metadata cannot promote '+key)
            no_credit(item)
    elif isinstance(value, list):
        for item in value:
            no_credit(item)


def roster(rows):
    result = {row['package']: row for row in rows}
    require(len(result) == len(rows), 'unique package roster')
    return result


def check_execution(value):
    raw = value['text'].encode()
    require(value['host'] == 'ai395' and value['offset'] == 0 and value['output_complete'] is True
        and value['text_is_lossy'] is False and value['truncated_before_offset'] is False
        and value['next_offset'] == value['available_end'] == len(raw)
        and value['chunk_sha256'] == hashlib.sha256(raw).hexdigest()
        and value['status']['state'] == 'exited' and value['status']['exit_code'] == 0
        and value['status']['output_complete'] is True and value['status']['capture_error'] is None
        and value['status']['bytes_seen'] == value['status']['bytes_stored'] == len(raw),
        'complete actual original metadata client output and exit')
    rows = [strict_json(line) for line in value['text'].splitlines() if line.startswith('{')]
    return rows


def load_inputs():
    manifest_raw = read('INPUTS.json')
    require(pin(manifest_raw) == INPUT_MANIFEST_PIN, 'fixed complete metadata input manifest')
    expected = strict_json(manifest_raw)
    require(set(expected) == {'inputs/'+name for name in INPUT_NAMES}, 'fixed twenty evidence members')
    documents = {}
    for name, wanted in expected.items():
        raw = read(name)
        require(pin(raw) == wanted, 'complete metadata input pin: '+name)
        if name.endswith('.json'):
            documents[name.removeprefix('inputs/')] = strict_json(raw)
    return documents, expected


def derive(d, expected, source_blobs, business_pin):
    plan = d['PLAN.json']; audit = d['FRESHNESS-GATE-AUDIT.json']
    http = d['actual/HTTP-OBSERVATIONS.json']; parsed = d['actual/PARSED-OBSERVATIONS.json']
    retry = d['actual/TWO-TIMEOUT-RETRY.json']; origins = d['actual/SELECTED-ORIGIN-SUPPLEMENT.json']
    head = d['actual/PUBLISHER-REDIRECT-HEAD.json']
    for document in (plan,audit,http,parsed,retry,origins,head):
        no_credit(document)
        for key in ('APK_or_delivery_requests','Android_or_SDK_calls','APK_bytes_read_or_downloaded',
                    'SDK_or_Android_calls','APK_body_downloads','APK_body_bytes_read','HTTP_body_read_calls'):
            if key in document:
                require(type(document[key]) is int and document[key] == 0,
                        'metadata execution performed no payload/SDK/Android action')
    require(plan['excluded_packages'] == parsed['excluded_packages'] == http['excluded_packages']
        == audit['excluded_packages'] == EXCLUDED, 'same three original exclusions')
    require(plan['original_GET_ITEMS_expires_utc'] == http['original_GET_ITEMS_expires_utc']
        == parsed['original_GET_ITEMS_expires_utc'] == EXPIRY, 'original Play expiry is never renewed')
    require(audit['Meituan_existing_userdata_signer_migration'] == parsed['Meituan_existing_userdata_signer_migration']
        == 'PENDING' and audit['every_required_app_latest_recheck_required_before_activation'] is True
        and parsed['latest_recheck_required_before_activation'] is True,
        'original signer migration and fresh activation gates remain')
    require(set(source_blobs) == {'current_source_state','current_registry','current_freshness'}, 'three frozen basis documents')
    state = strict_json(source_blobs['current_source_state'])
    registry = strict_json(source_blobs['current_registry'])
    freshness = strict_json(source_blobs['current_freshness'])
    require(pin(source_blobs['current_freshness']) == audit['current_freshness'] == plan['current_freshness']
        and pin(source_blobs['current_source_state']) == audit['source_state']
        and pin(source_blobs['current_registry'])['sha256'] == origins['current_registry_source_sha256']
        and pin(source_blobs['current_freshness'])['sha256'] == origins['current_freshness_source_sha256']
        and {k:business_pin[k] for k in ('bytes','sha256')} == audit['current_business_plan'],
        'public observations are bound to the exact selected source snapshot at collection')
    fresh = roster(freshness['rows']); selected = roster(registry['applications']); states = roster(state['applications'])
    requests = roster(plan['requests']); collected = roster(http['rows']); observations = roster(parsed['rows'])
    require(len(fresh) == 29 and len(selected) == 30 and len(states) == 39
        and len(requests) == 31 and set(requests) == set(fresh)|SYSTEM_OBSERVATIONS
        and set(collected) == set(observations) == set(requests)
        and not set(EXCLUDED)&set(states), 'complete original 29 plus system10 roster and companion')
    for package,row in fresh.items():
        require(requests[package]['selected_version'] == row['selected_input_version']
            == selected[package]['version_name'], 'exact selected version basis')
    require({k:http['plan'][k] for k in ('bytes','sha256')} == expected['inputs/PLAN.json']
        and {k:http['worker'][k] for k in ('bytes','sha256')} == expected['inputs/public_metadata_fetch.py']
        and parsed['HTTP_receipt'] == retry['original_HTTP_receipt'] == expected['inputs/actual/HTTP-OBSERVATIONS.json']
        and retry['frozen_parser'] == expected['inputs/parse_public_metadata.py']
        and origins['frozen_parser_sha256'] == expected['inputs/parse_public_metadata.py']['sha256']
        and head['parent_receipt'] == expected['inputs/actual/SELECTED-ORIGIN-SUPPLEMENT.json'],
        'complete fixed collection/parser/supplement receipt chain')
    require(http['source_bookends_unchanged'] is True and retry['original_failure_evidence_unchanged'] is True,
        'actual original source and failure bookends retained')
    failed = set(); body_bytes = 0
    for package,request in requests.items():
        col=collected[package]; obs=observations[package]
        require(all(col[key] == value and obs[key] == value for key,value in request.items()), 'fixed exact request and selection')
        require(obs['http_status'] == col.get('http_status') and obs['body_sha256'] == col.get('body_sha256'), 'parsed response identity link')
        if col['status'] == 'ERROR_NO_LATEST_CLAIM':
            require(col['error'] == 'TimeoutError: The read operation timed out'
                and obs['comparison'] == 'UNRESOLVED' and obs['status'] == 'NO_CURRENT_VERSION_CLAIM',
                'original timeout stays a failure')
            failed.add(package)
        else:
            require(col['http_status'] == 200 and col['status'] == 'PUBLIC_METADATA_BODY_RETAINED_PARSE_PENDING'
                and obs['status'] == 'PUBLIC_METADATA_PARSED' and 0 < col['body_bytes'] <= 2*1024*1024,
                'actual complete bounded metadata response')
            body_bytes += col['body_bytes']
            if col['url'].startswith('https://play.google.com/') or col['url'].startswith('https://a.app.qq.com/'):
                require(obs['observation']['package_identity'] == package, 'exact primary public application identity')
    require(failed == TIMEOUTS and http['request_count'] == 31 and body_bytes == http['total_metadata_body_bytes']
        and body_bytes <= 64*1024*1024 and set(parsed['unresolved_public_observations']) == TIMEOUTS,
        'all original collection results accounted for')
    require(parsed['parsed_public_observations'] == 29 and parsed['public_metadata_requests'] == 31
        and parsed['new_public_version_candidates'] == [], 'exact original parsed observation totals')
    effective = {p:dict(observations[p]) for p in fresh}
    retried = roster(retry['rows'])
    require(set(retried) == TIMEOUTS and retry['requests'] == 2, 'only the two observed timeouts retried')
    for package,row in retried.items():
        require(row['original_failure_preserved'] is True and row['original_failure_completed_utc'] == collected[package]['completed_utc']
            and row['http_status'] == 200 and row['status'] == 'PUBLIC_METADATA_PARSED'
            and row['comparison'] == 'PUBLIC_VERSION_MATCHES_SELECTED_SOURCE'
            and row['url'] == requests[package]['url'] and row['selected_version'] == requests[package]['selected_version']
            and row['observation']['version'] == row['selected_version'], 'successful bounded retry preserves original failure')
        effective[package] = row
    supplements = roster(origins['rows'])
    require(set(supplements) == MIRRORS|{'com.szzc'}, 'only exact selected mirror and publisher observations')
    for package in MIRRORS:
        row = supplements[package]
        require(observations[package]['comparison'] == 'PUBLIC_CHANNEL_VERSION_BELOW_SELECTED_NO_DOWNGRADE'
            and row['http_status'] == 200 and row['method'] == 'GET'
            and row['comparison'] == 'PUBLIC_VERSION_MATCHES_SELECTED_SOURCE'
            and row['observed_version'] == row['selected_version'] == requests[package]['selected_version']
            and row['mirror_metadata_is_not_publisher_or_signature_verification'] is True
            and row['primary_package_manifest_checked'] is False, 'matching original mirror is metadata only')
        effective[package] = {**row,'observation':{'version':row['observed_version']}}
    fcitx = effective['org.fcitx.fcitx5.android']
    assets = {a['name'] for a in fcitx['observation']['assets']}
    wanted = {'org.fcitx.fcitx5.android-'+fcitx['selected_version']+'-'+abi+'-release.apk'
              for abi in ('arm64-v8a','armeabi-v7a','x86','x86_64')}
    require(fcitx['comparison'] == 'STABLE_RELEASE_AND_EXACT_SELECTED_BUILD_ASSETS_MATCH'
        and wanted.issubset(assets) and fcitx['observation']['exact_selected_build_asset_names'] == sorted(wanted)
        and fcitx['observation']['version'] == fcitx['selected_version'].split('-0-g')[0], 'exact Fcitx build assets')
    sz = selected['com.szzc']; previous_head = supplements['com.szzc']
    require(previous_head['http_status'] == 301 and previous_head['method'] == head['method'] == 'HEAD'
        and previous_head['redirect_location'] == head['request_url']
        == 'https://edfs.zuchecdn.com/android-package/SZZC.apk'
        and head['http_status'] == 200 and head['automatic_redirects_followed'] == 0
        and head['HTTP_body_read_calls'] == head['APK_body_bytes_read'] == 0
        and head['selected_APK_bytes'] == sz['input']['bytes'] == 220522994
        and head['selected_APK_sha256'] == sz['input']['sha256']
        and head['content_length'] == '220498418' and head['content_length_matches_selected_APK'] is False
        and head['version_observed_from_headers'] is None and head['source_identity_requalified'] is False,
        'actual publisher size drift has no inferred version or signature qualification')
    require(effective['com.szzc']['comparison'] == 'PUBLIC_CHANNEL_VERSION_BELOW_SELECTED_NO_DOWNGRADE', 'no lower-channel downgrade')
    rows=[]
    for package,row in sorted(effective.items()):
        if package == 'com.szzc':
            rows.append({'package':package,'selected_version':row['selected_version'],
                'observed_public_channel_version':row['observation']['version'],
                'publisher_content_length':int(head['content_length']), 'selected_body_bytes_at_observation':head['selected_APK_bytes'],
                'publisher_minus_selected_bytes':int(head['content_length'])-head['selected_APK_bytes'],
                'status':'PUBLISHER_BODY_IDENTITY_REQUALIFICATION_PENDING_AT_OBSERVATION',
                'source_identity_requalified':False})
        else:
            require(package == 'org.fcitx.fcitx5.android' or (row['comparison'] == 'PUBLIC_VERSION_MATCHES_SELECTED_SOURCE'
                and row['observation']['version'] == row['selected_version']), 'matching public observation for selected version')
            rows.append({'package':package,'selected_version':row['selected_version'],
                'observed_version':row['observation']['version'],'url':row['url'],
                'status':'MATCHING_PUBLIC_METADATA_ONLY','original_mirror_metadata':package in MIRRORS,
                'exact_build_assets_matched':package == 'org.fcitx.fcitx5.android','source_identity_requalified':False})
    require(all(observations[p]['comparison'] == 'CURRENT_GSI_PUBLICATION_MATCH'
        and observations[p]['observation']['version'] == 'CP3A.260905.010' for p in SYSTEM_OBSERVATIONS), 'two matching GSI publications')
    require(observations['system-gsi-cp3a-details']['observation']['archive_sha256']
        == '81e37ae9e9280497c92fbda758b998a7dfab91ab9de000021622afa868a43b70', 'exact published CP3A archive')
    system = {p:r for p,r in states.items() if r['kind'] == 'system'}
    system_audit = roster(audit['system_cohort_apps'])
    require(set(system) == set(system_audit) and len(system) == 10, 'original coherent system10 cohort')
    for package,row in system_audit.items():
        original=system[package]['unchanged_original_system_record']
        require(row['source_receipt'] == original['source_receipt'] and row['APK_sha256'] == original['apk']['sha256']
            and row['version'] == original['version_name'] and row['version_code'] == original['version_code']
            and row['individual_APK_install_authorized'] is False, 'system source identity retained without individual install')
    ttl=roster(audit['fixed_expiry_gates'])
    require(set(ttl) == TTL_PACKAGES, 'only the original three explicit Play TTL gates')
    for row in ttl.values():
        require(row['historical_expiry'] == EXPIRY and row['restriction'] == 'UNAVAILABLE_COUNTRY'
            and row['public_listing_cannot_renew_this_gate'] is True and row['new_delivery_obtained'] is False,
            'original Play transaction restriction and expiry unchanged')
    executions=[('fetch','HTTP-OBSERVATIONS.json'),('parse','PARSED-OBSERVATIONS.json'),
                ('retry','TWO-TIMEOUT-RETRY.json'),('origins','SELECTED-ORIGIN-SUPPLEMENT.json'),
                ('publisher-head','PUBLISHER-REDIRECT-HEAD.json')]
    expected_units = {'fetch':'p4-source-freshness-public-5cd1-r1.service',
        'parse':'p4-source-freshness-parse-5cd1-r1.service',
        'retry':'p4-source-freshness-retry-5cd1-r1.service',
        'origins':'p4-source-freshness-origins-5cd1-r1.service',
        'publisher-head':'p4-source-freshness-publisher-head-5cd1-r1.service'}
    units=[];sessions=[]
    for name,receipt in executions:
        value=d['actual/'+name+'-execution.json']; lines=check_execution(value)
        result=lines[-1].get('result',lines[-1]); target=expected['inputs/actual/'+receipt]
        require(result['path'] == REMOTE+receipt and {k:result[k] for k in ('bytes','sha256')} == target,
            'actual original client emitted the exact retained receipt')
        match=re.search(r'Running as unit: ([a-z0-9.-]+); invocation ID: ([0-9a-f]{32})',value['text'])
        require(match is not None and match.group(1) == expected_units[name],
            'exact original unit and invocation observed')
        units.append(match.group(1));sessions.append(value['session_id'])
        if name == 'origins':require(lines[:-1] == origins['rows'], 'actual three origin observations')
        if name == 'publisher-head':require(lines[-1]['observation'] == head, 'actual publisher HEAD observation')
    require(len(set(units)) == len(set(sessions)) == 5, 'five distinct actual metadata executions')
    retired=d['actual/metadata-units-retirement.json']; retirement=check_execution(retired)[0]
    require(retirement['all_original_units_retired'] is True and [r['unit'] for r in retirement['units']] == units,
        'all five exact original metadata units retired')
    for row in retirement['units']:
        require(row['retired'] is True and row['exit'] == 0 and row['stderr'] == ''
            and row['cgroup_exists'] is False and row['stdout']
            == 'LoadState=not-found\nActiveState=inactive\nSubState=dead\nExecMainPID=0\nControlGroup=\n',
            'actual exact unit and cgroup absence')
        require(row['expected_original_cgroup'] == '/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/'+row['unit'],
            'exact original cgroup path')
    require(datetime.fromisoformat(retirement['observed_utc']) >= datetime.fromisoformat(head['completed_utc']), 'retirement follows collection')
    controls=d['PRIMARY-IDENTITY-CONTROLS.json']
    require(controls['parser_sha256'] == expected['inputs/parse_public_metadata.py']['sha256']
        and all(controls[k] is True for k in ('positive_Play_primary_package_and_version',
        'positive_Tencent_primary_version_ignores_unrelated_store','wrong_Play_primary_package_rejected',
        'wrong_Tencent_primary_package_rejected')), 'actual parser identity controls')
    return {'schema':'pocket4-late-public-source-observation-summary-v1',
        'state':'PASS_PUBLIC_METADATA_EVIDENCE_ONLY','collection_started_utc':http['started_utc'],
        'last_observation_completed_utc':head['completed_utc'],'required_apps':39,'third_party_apps':29,
        'matching_public_version_or_exact_build_observations':28,'publisher_body_identity_pending_at_observation':['com.szzc'],
        'new_public_version_candidates':parsed['new_public_version_candidates'],
        'system_GSI_publication_observations':2,'system_apps_bound_to_original_CP3A':10,
        'actual_metadata_executions':5,'actual_metadata_units_retired':5,
        'original_two_timeouts_preserved_and_resolved_by_separate_receipts':True,
        'original_Play_expiry':EXPIRY,'original_Play_expiry_packages':sorted(TTL_PACKAGES),
        'authoritative_play_metadata_TTL_renewed':False,'activation_metadata_revalidated':False,
        'Meituan_existing_userdata_signer_migration':'PENDING','excluded_packages':EXCLUDED,
        'HTTP_bodies_reparsed_by_this_consumer':False,'source_body_identity_reverified_by_this_consumer':False,
        'SDK_commands':0,'Android_actions':0,'all39_latest_qualified':False,'installed':False,
        'runtime_qualified':False,'business_qualified':False,'production_ready':False,'rows':rows}


def verify(source_blobs, business_pin):
    documents, expected=load_inputs()
    result=derive(documents,expected,source_blobs,business_pin)
    actual=read('OBSERVATION-SUMMARY.json')
    require((json.dumps(result,indent=2,sort_keys=True)+'\n').encode() == actual,
        'complete deterministic public observation summary reconstruction')
    return result


INPUT_MANIFEST_PIN = {'bytes':2980, 'sha256':'f9331ef88b0c105dc6e9cecef5274288bdbd1d8983c224123fdc7de9ee9eb96f'}
