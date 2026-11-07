#!/usr/bin/env python3
"""Build local-only two-candidate research and one unsubmitted National HTML request."""
import ast
import copy
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


def pin(path):
    path = Path(path)
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def expected(path, size, digest):
    row = pin(PROJECT / path)
    assert row['bytes'] == size and row['sha256'] == digest, row
    return row


def write(name, value):
    raw = value if isinstance(value, bytes) else (
        value.encode() if isinstance(value, str) else
        (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())
    fd = os.open(HERE / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            assert count > 0
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    assert (HERE / name).read_bytes() == raw
    return pin(HERE / name)


def main():
    inputs = [
        expected('launcher_public_delivery_r1/read_ihg_public_pages_once.py', 12399,
                 'a01a751548b7e323dbcaf39a028cb6879ee65ce3ff02c2e897a35122b5e73115'),
        expected('launcher_public_delivery_r1/SOURCE_GAPS_46.json', 90249,
                 '8d5b1c370cff2fc12663f74f64afd0a28659b687eec5730b49049d6e8cc0e529'),
        expected('current_launcher_inventory_r3/INVENTORY.json', 1703185,
                 '8932d7b7f18218717de09a2b05860f29d0f3d80f646127d89b6959bd60cc1ea9'),
        expected('launcher_public_delivery_r1/actual/stdout.original.json', 4757,
                 'acf3430ad2b4c759e54afe06a17c0b3ff71da0cbd945fcf13e4972a16db63260'),
        expected('launcher_public_delivery_r1/actual/terminal.original.json', 728,
                 '9ba6041290ae4b9479fa5edc16040f9aa32849af8115fcd143da719ad6e3eff0'),
        expected('launcher_public_delivery_r1/actual/root-validation.json', 997,
                 '0ad0b1a0ddfd8e21161970f974354029af1efbaf284f331dc03ac11e37979b1b'),
        expected('official_source_scripts/s44_international_delivery_metadata/international14-delivery-evidence.json', 40247,
                 'eb1777bbd1db0aedec55ad55fca5089206d73361ada603543349c04a198ea3d9'),
        expected('launcher_public_delivery_r1/SOURCE_RULE_REVIEW.md', 2200,
                 '492760c0853fffc3f881d51cf3aa8ebf09c92c8bc340ad77c04d1d5bf924e733'),
    ]
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    inventory = json.loads((PROJECT / inputs[2]['path']).read_bytes())
    by_package = {x['package']: x for x in inventory['apps']}
    assert len(by_package) == 46
    ihg = json.loads((PROJECT / inputs[3]['path']).read_bytes())
    terminal = json.loads((PROJECT / inputs[4]['path']).read_bytes())
    assert terminal['job_id'] == '1a1b3437276-fc05-818f'
    assert terminal['state'] == 'failed' and terminal['exit_code'] == 1
    assert all(terminal[k] is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed'))
    assert ihg['ok'] is False and len(ihg['requests']) == 1
    assert ihg['requests'][0]['status'] == 403
    assert dict((k.lower(), v) for k, v in ihg['requests'][0]['headers'])['cf-mitigated'] == 'challenge'
    assert ihg['original_descriptor_identities_restored'] is True

    profiles = {
        'national': {
            'package': 'com.ehi.national.mobile',
            'url': 'https://national-car-rental.en.softonic.com/android/download',
            'output_root': '/home/alex/work/pocket4-national-public-distribution-page-20261107-r1',
            'expected_web_version_label': '6.16.0.9403',
            'expected_web_container_sha256': 'a901bc4949fe241750cd7ea3fb5df690d00b21e217b2212be813bbd51e5a36bb',
            'literal_control_label': 'free xapk download for android',
            'literal_control_meaning': 'published standalone XAPK download control; destination still unfetched',
        },
        'uber': {
            'package': 'com.ubercab',
            'url': 'https://uber.en.uptodown.com/android/download',
            'output_root': '/home/alex/work/pocket4-uber-public-distribution-page-20261107-r1',
            'expected_web_version_label': '4.655.10001',
            'expected_web_container_sha256': '1250b932a610e3830fb78d9382ae1b5faecd347b5f19db0b76644c58498aa41e',
            'literal_control_label': 'all variants',
            'literal_control_meaning': 'published manual separate-XAPK selector; not the default store-installer button',
        },
    }
    web = [
        {'id': 'national_play', 'url': 'https://play.google.com/store/apps/details?id=com.ehi.national.mobile',
         'refs': ['turn187view0', 'turn189view0'], 'authority': 'publisher_listing_on_official_store',
         'observed': {'publisher': 'EAN Services, LLC', 'release_notes_series': '6.16',
                      'rendered_updated_on': '2026-09-25', 'exact_version_code': None,
                      'exact_full_version_name_in_rendered_body': None}},
        {'id': 'national_softonic', 'url': profiles['national']['url'],
         'refs': ['turn187view2', 'turn188view3'], 'authority': 'public_third_party_distribution',
         'observed': {'package_in_filename': 'com.ehi.national.mobile', 'version_name_label': '6.16.0.9403',
                      'file_name': 'com.ehi.national.mobile_6.16.0.9403.xapk', 'file_type': 'XAPK',
                      'size_label': '65.97 MB', 'exact_bytes': None, 'ABI': None, 'version_code': None,
                      'container_sha256_label': profiles['national']['expected_web_container_sha256'],
                      'updated_label': '2026-10-28', 'standalone_control': 'Free XAPK Download for Android',
                      'separate_installer_controls_not_selected': ['Softonic Helper', 'LDPlayer']}},
        {'id': 'uber_official', 'url': 'https://www.uber.com/us/en/download/',
         'refs': ['turn189view1'], 'authority': 'publisher',
         'observed': {'rider_download_control': True, 'redirect_destination_not_followed': 'rides.sng.link',
                      'direct_complete_APK_observed': False}},
        {'id': 'uber_play', 'url': 'https://play.google.com/store/apps/details?id=com.ubercab',
         'refs': ['turn187view1', 'turn188view2'], 'authority': 'publisher_listing_on_official_store',
         'observed': {'publisher': 'Uber Technologies, Inc.', 'rendered_updated_on': '2026-10-30',
                      'exact_version_code': None, 'exact_version_name_in_rendered_body': None}},
        {'id': 'uber_uptodown', 'url': profiles['uber']['url'],
         'refs': ['turn187view3'], 'authority': 'public_third_party_distribution',
         'observed': {'package': 'com.ubercab', 'version_name_label': '4.655.10001',
                      'ABI_labels': ['armeabi-v7a', 'arm64-v8a'], 'file_type': 'XAPK',
                      'size_label': '130.1 MB', 'exact_bytes': None, 'version_code': None,
                      'container_sha256_label': profiles['uber']['expected_web_container_sha256'],
                      'certificate_label_not_SHA256': '6a9521c9111f1ff0a35c48ecb41460b5',
                      'date_label': '2026-11-05', 'default_button_delivers_store_installer': True,
                      'documented_separate_file_selector': 'All variants',
                      'literal_separate_file_URL_not_yet_exposed': True}},
    ]
    candidates = []
    for key, profile in profiles.items():
        app = by_package[profile['package']]
        candidates.append({
            'candidate_id': key,
            'package': app['package'], 'label': app['label_reference'],
            'current_version_name_from_fixed_inventory': app['version_name'],
            'current_effective_version_code_from_fixed_inventory': app['effective_version_code'],
            'current_identity_from_fixed_inventory': copy.deepcopy(app['current_installed_identity']),
            'baseline_identity_is_not_a_new_live_observation': True,
            'distribution_class': 'public-third-party-distribution',
            'publisher_endorsement_of_distributor_proved': False,
            'candidate_web_profile': profile,
            'normal_complete_delivery_state': 'PUBLIC_SEPARATE_FILE_OPTION_ONLY_LITERAL_AND_CONTAINER_PENDING',
            'candidate_APK_or_XAPK_obtained': False,
            'candidate_complete_split_set_observed': False,
            'candidate_ordinary_signature_verified': False,
            'candidate_matches_current_signer': 'UNKNOWN',
            'candidate_effective_version_code': None,
            'candidate_latest_official_version_qualified': False,
            'candidate_ARM64_full_set_verified': False,
            'production_ready': False, 'cleanup_eligible': False,
            'new_install_authority': False,
        })
    candidates[0]['version_association'] = {
        'fresh_official_rendered_series': '6.16',
        'inherited_S22_full_version_label': '6.16.0.9403',
        'inherited_S22_original_raw_locally_available': False,
        'inherited_reference': by_package['com.ehi.national.mobile']['official_source']['reference']['evidence_ref'],
        'exact_candidate_code_and_all_split_versions_still_pending': True,
    }
    candidates[1]['version_association'] = {
        'fresh_official_exact_version_label': None,
        'older_web_observation_not_overwritten': {'ref': 'turn185view2', 'label': '4.654.10002',
            'container_sha256_label': 'a9717d252466e38cbfd6f67a743b7a1746db20bfaed027a4c24f858eeebf89d4'},
        'fresh_distribution_label_changed_to': '4.655.10001',
        'distributor_matches_Google_Play_statement_is_not_publisher_release_proof': True,
    }
    exclusions = [
        {'package': 'com.ihg.apps.android', 'channel': 'APKMirror original lane',
         'reason': 'ACTUAL_HTTP403_CF_MITIGATED_CHALLENGE_STOP',
         'job_id': terminal['job_id'], 'actual_inputs': inputs[3:6],
         'alternate_browser_identity_endpoint_CDN_proxy_TLS_DNS_or_nonce_action_allowed': False},
        {'package': 'com.enflick.android.TextNow', 'channel': 'Malavida',
         'url': 'https://www.malavida.com/en/soft/textnow/android/', 'ref': 'turn178view3',
         'reason': 'PUBLIC_WEB_FETCH_HTTP403_STOP_NO_ALTERNATIVE_IDENTITY'},
        {'package': 'com.marriott.mrt', 'channel': 'original S44 host page lane',
         'reason': 'ACTUAL_FIRST_PAGE_403_ALREADY_CLOSED_NO_RETRY'},
        {'package': 'com.marriott.mrt', 'channel': 'Uptodown',
         'url': 'https://marriott.en.uptodown.com/android/download', 'ref': 'turn184view1',
         'reason': '10.79.0_EQUALS_CURRENT_NOT_AN_UPGRADE'},
        {'package': 'com.hertz.android.digital', 'channel': 'APKPure',
         'url': 'https://apkpure.net/hertz-car-rental/com.hertz.android.digital', 'ref': 'turn178view2',
         'reason': '4.84.0_OLDER_THAN_CURRENT_5.6.0'},
        {'package': 'com.pinger.textfree', 'channel': 'Softonic',
         'url': 'https://text-free-free-text-calls.en.softonic.com/android/download', 'ref': 'turn186search0',
         'reason': '13.28.1_METADATA_BUT_GOOGLE_PLAY_ONLY_NO_STANDALONE_DOWNLOAD'},
        {'package': 'com.pinger.textfree', 'channel': 'Aptoide',
         'url': 'https://textfree.en.aptoide.com/app', 'refs': ['turn179view0', 'turn179view1'],
         'reason': 'VERSION_PAGE_CONFLICT_AND_NO_OBSERVED_STANDALONE_LITERAL_URL'},
        {'package': 'com.ubercab', 'channel': 'APKPure',
         'url': 'https://apkpure.net/uber-rides-eats-hotels/com.ubercab', 'ref': 'turn184view0',
         'reason': 'REQUEST_APK_VIA_TELEGRAM_IS_NOT_PUBLIC_FILE_DELIVERY_NO_MESSAGE_SENT'},
        {'package': 'com.Hyatt.hyt', 'channel': 'Softonic',
         'url': 'https://world-of-hyatt.en.softonic.com/android', 'ref': 'turn186search2',
         'reason': '26.9.0_SAME_AS_CURRENT_PLAY_ONLY'},
        {'package': 'com.szzc', 'channel': 'existing official delivery',
         'reason': 'EXISTING_S39_SAME_VERSION327_NOT_A_NEW_UPGRADE_NO_REPEAT_DOWNLOAD'},
    ]
    research = {'schema': 'pocket4-independent-public-delivery-candidates-v2',
        'prepared_utc': timestamp, 'state': 'LOCAL_RESEARCH_AND_UNSUBMITTED_PAGE_REQUESTS',
        'candidates': candidates, 'web_observations': web, 'excluded_or_stopped_lanes': exclusions,
        'scope': 'All 46 previous launcher rows retained; two independent commercial candidates selected',
        'no_existing_global_vendor_direct_only_rule_found_in_examined_material': True,
        'old_install_allowlists_and_guards_unchanged': True,
        'APK_downloads': 0, 'remote_process_submissions': 0, 'Android_commands': 0,
        'UI_actions': 0, 'installs': 0, 'permission_changes': 0,
        'new_upgrades': 0, 'production_ready': 0, 'deleted_bytes': 0,
        'limits': ['Public web retrieval is not target HTTP or APK evidence.',
                   'Page file hashes are untrusted container labels until the full delivered bytes are observed.',
                   'No publisher direct URL does not prove absence of all legal public same-package deliveries.',
                   'XAPK is not accepted as a single APK; actual base and every required split must be qualified.',
                   'No distributor app/installer will be installed to acquire these files.',
                   'Normal PackageManager split delivery capability must be separately confirmed before any installation.']}
    write('RESEARCH.json', research)
    write('INPUT_PINS.json', {'schema': 'pocket4-independent-public-research-inputs-v1', 'files': inputs})
    gaps = copy.deepcopy(json.loads((PROJECT / inputs[1]['path']).read_bytes()))
    gaps.update(schema='pocket4-all46-public-source-gaps-v2', prepared_utc=timestamp,
                prior_full46_reference=inputs[1], current_inventory_reference=inputs[2],
                state='LOCAL_RESEARCH_ONLY_NO_NEW_ARTIFACT_OR_MAIN_OBSERVATION')
    gaps['summary']['selected_new_metadata_candidates'] = 2
    for row in gaps['rows']:
        package = row['package']
        if package in {p['package'] for p in profiles.values()}:
            key = next(k for k, p in profiles.items() if p['package'] == package)
            row['public_same_package_delivery_state'] = 'PUBLIC_SEPARATE_XAPK_OPTION_NORMAL_LITERAL_REQUEST_PENDING'
            row['gap'] = '公开分发页列出独立XAPK选项；尚无实际完整文件、split集合、code或正常签名证明。'
            row['next_channel'] = '只读固定公开页面取得原始HTML/literal控制；另审完整交付，不安装分发商应用。'
            row['new_evidence'] = {'candidate_id': key, 'research': 'RESEARCH.json',
                                   'page': profiles[key]['url'], 'no_artifact_obtained': True}
        elif package == 'com.ihg.apps.android':
            row['previous_candidate_reference'] = {'path': inputs[1]['path'], 'sha256': inputs[1]['sha256']}
            row['public_same_package_delivery_state'] = 'ACTUAL_403_CHALLENGE_LANE_TERMINATED'
            row['gap'] = '普通UID1000首次GET实际403/Cf-Mitigated:challenge；第二页未请求；没有APK。'
            row['next_channel'] = '当前APKMirror路径终止；不得通过浏览器、身份、端点、CDN、代理、TLS/DNS或nonce调整处理挑战。'
            row['new_evidence'] = {'job_id': terminal['job_id'], 'inputs': inputs[3:6], 'no_retry': True}
    assert len(gaps['rows']) == 46 and sum(r['completed_upgrade_in_this_round'] for r in gaps['rows']) == 12
    write('SOURCE_GAPS_46.json', gaps)

    original = (PROJECT / inputs[0]['path']).read_text()
    source = original.replace('Observe two ordinary public HTML pages; never fetch an APK or enter Android.',
                              'Observe one fixed independent public HTML page; never follow a delivery URL or enter Android.')
    start = source.index('ROOT = ')
    stop = source.index('\n\ndef need')
    source = source[:start] + ('PROFILES = ' + repr({'national': profiles['national']}) + '\n'
        "ROOT = Path(PROFILES['national']['output_root'])\n"
        'MAX_BODY = 2 * 1024 * 1024\nMAX_ERROR_BODY = 65536\nTOTAL_SECONDS = 120\n'
        'TLS = ssl.create_default_context()\n') + source[stop:]
    start, stop = source.index('def select_intermediate('), source.index('def deadline_signal(')
    source = source[:start] + '''def observe_unfollowed_controls(raw, profile):
    parser, title = parse_html(raw)
    literal_controls = []
    candidate_control_urls = set()
    ignored_non_https_controls = 0
    for anchor in parser.rows:
        label = ' '.join(anchor['text'].split())
        href = anchor['href']
        if not href or not any(word in label.casefold() for word in ('download', 'variant', 'xapk', 'apk')):
            continue
        absolute = urllib.parse.urljoin(profile['url'], href)
        parsed = urllib.parse.urlsplit(absolute)
        if parsed.scheme != 'https' or parsed.fragment:
            ignored_non_https_controls += 1
            continue
        normal_https_url(absolute)
        need(len(literal_controls) < 64 and len(label) <= 512, 'BOUNDED_PUBLIC_CONTROL_OBSERVATION')
        literal_controls.append({'literal_label': label, 'literal_url': absolute,
                                 'followed': False, 'file_or_installer_identity_verified': False})
        if label.casefold() == profile['literal_control_label']:
            candidate_control_urls.add(absolute)
    text = raw.decode('utf-8', 'strict')
    return {
        'title': title,
        'literal_download_or_variant_anchors': literal_controls,
        'ignored_non_https_or_fragment_controls': ignored_non_https_controls,
        'expected_web_literals_present_in_HTML_not_verified_metadata': {
            'package': profile['package'] in text,
            'version_label': profile['expected_web_version_label'] in text,
            'container_sha256_label': profile['expected_web_container_sha256'] in text,
        },
        'candidate_control_urls': sorted(candidate_control_urls),
        'candidate_control_state': ('ONE_LITERAL_UNFOLLOWED_CONTROL' if len(candidate_control_urls) == 1
                                    else 'UNRESOLVED_OR_AMBIGUOUS_NO_INFERRED_URL'),
        'automatic_script_execution': False, 'all_links_followed': 0,
        'APK_or_container_obtained': False, 'direct_binary_delivery_qualified': False,
        'a_complete_HTML_observation_is_not_download_or_signature_success': True,
    }


''' + source[stop:]
    start = source.index('def main():')
    source = source[:start] + '''def main():
    global ROOT
    flags = {'--observe-national-page-only': 'national'}
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000
         and len(sys.argv) == 2 and sys.argv[1] in flags, 'EXACT_ORDINARY_OWNER_CLOSED_PAGE_ENTRY')
    key = flags[sys.argv[1]]
    profile = PROFILES[key]
    ROOT = Path(profile['output_root'])
    need(ROOT.parent.resolve(strict=True) == ROOT.parent, 'EXISTING_NORMAL_PARENT_REQUIRED')
    os.umask(0o077)
    before = census()
    ROOT.mkdir(mode=0o700)
    result = {
        'schema': 'pocket4-independent-public-single-page-observation-v2',
        'ok': False, 'candidate_id': key, 'package': profile['package'],
        'meaning_of_ok': 'one complete ordinary public HTML response and bounded untrusted control observation only',
        'distribution_class': 'public-third-party-distribution', 'publisher_direct_APK': False,
        'started_utc': now(), 'requests': [], 'errors': [], 'ordinary_uid': os.getuid(),
        'maximum_HTTP_GET_requests': 1, 'maximum_bytes_per_HTML': MAX_BODY,
        'maximum_total_seconds': TOTAL_SECONDS,
        'user_agent_policy': 'urllib default unmodified', 'TLS_policy': 'system trust/default verification',
        'automatic_redirects': False, 'automatic_retry': False, 'challenge_solving': False,
        'DNS_IP_proxy_TLS_modifications': False, 'ordinary_resolver_internal_attempts_not_instrumented': True,
        'APK_downloads': 0, 'APK_signature_verified': False, 'APK_candidate_qualified': False,
        'delivery_link_requests': 0, 'distributor_installer_used': False,
        'existing_private_files_read': 0, 'subprocesses_started': 0,
        'Main_actions': 0, 'Android_commands': 0, 'UI_actions': 0, 'installs': 0,
        'permission_changes': 0, 'production_ready': False, 'cleanup_eligible': False,
        'before_descriptor_identities': before,
        'artifact_pin_semantics': 'hash of bytes written; no separate disk readback or directory crash-persistence proof',
    }
    previous_handler = signal.signal(signal.SIGALRM, deadline_signal)
    try:
        end = time.monotonic() + TOTAL_SECONDS
        signal.setitimer(signal.ITIMER_REAL, TOTAL_SECONDS, 0)
        raw, row = fetch_html_once(1, profile['url'], end, result)
        need(not any(name.lower() == 'cf-mitigated' and value.casefold() == 'challenge'
                     for name, value in row['headers']), 'PUBLIC_CHALLENGE_STOP_NO_SOLVING_OR_ALTERNATE_IDENTITY')
        row['parsed_observation'] = observe_unfollowed_controls(raw, profile)
        result['ok'] = len(result['requests']) == 1 and row['complete'] is True
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
        result['ok'] = False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    result['after_descriptor_identities'] = census()
    result['original_descriptor_identities_restored'] = result['after_descriptor_identities'] == before
    result['ok'] = result['ok'] and result['original_descriptor_identities_restored'] and not result['errors']
    result['ended_utc'] = now()
    raw = (json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\\n').encode()
    save('result.json', raw)
    need(census() == before, 'FINAL_PUBLICATION_DESCRIPTOR_SET_CHANGED')
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
'''
    compile(source, 'observe_independent_public_page.py', 'exec')
    write('observe_independent_public_page.py', source)
    write('worker-against-ihg-frozen.diff', ''.join(difflib.unified_diff(
        original.splitlines(True), source.splitlines(True), fromfile=inputs[0]['path'],
        tofile='launcher_public_delivery_independent_r2/observe_independent_public_page.py')))
    original_defs = {n.name: ast.get_source_segment(original, n) for n in ast.parse(original).body
                     if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    new_defs = {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body
                if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    inherited = ['need', 'now', 'census', 'save', 'NoAutomaticRedirect', 'Anchors', 'parse_html',
                 'normal_https_url', 'deadline_signal', 'fetch_html_once']
    assert all(original_defs[n] == new_defs[n] for n in inherited)
    ns = {'__name__': 'source_review_without_runtime_entry'}
    exec(compile(source, 'observe_independent_public_page.py', 'exec'), ns)
    before = ns['census']()
    controls = []
    national = profiles['national']
    raw = ('<title>National</title><p>' + national['package'] + ' ' + national['expected_web_version_label']
           + ' ' + national['expected_web_container_sha256'] + '</p>'
           + '<a href="https://en.softonic.com/test-path">Free XAPK Download for Android</a>'
           + '<a href="https://en.softonic.com/installer">Install with Softonic Helper</a>').encode()
    observed = ns['observe_unfollowed_controls'](raw, national)
    assert observed['candidate_control_urls'] == ['https://en.softonic.com/test-path']
    assert observed['all_links_followed'] == 0 and observed['direct_binary_delivery_qualified'] is False
    controls.append('national_literal_is_observed_only_not_installer_or_download')
    observed = ns['observe_unfollowed_controls'](
        b'<title>Uber</title><a href="https://uber.en.uptodown.com/store-installer">Download</a>'
        b'<p>All variants offers a separate XAPK.</p>', profiles['uber'])
    assert observed['candidate_control_state'] == 'UNRESOLVED_OR_AMBIGUOUS_NO_INFERRED_URL'
    assert observed['candidate_control_urls'] == []
    controls.append('uber_default_installer_does_not_become_separate_file_url')
    try:
        ns['observe_unfollowed_controls'](b'<title>Just a moment</title>', national)
    except RuntimeError as e:
        assert str(e) == 'PUBLIC_CHALLENGE_STOP_NO_SOLVING_OR_ALTERNATE_IDENTITY'
    else:
        raise AssertionError('challenge was accepted')
    controls.append('public_challenge_stops_without_identity_change')
    try:
        ns['observe_unfollowed_controls'](
            b'<title>National</title><a href="https://user:pass@example.invalid/file.xapk">Free XAPK Download for Android</a>', national)
    except RuntimeError as e:
        assert str(e) == 'LITERAL_HTTPS_URL_REQUIRED'
    else:
        raise AssertionError('credential URL accepted')
    controls.append('credential_URL_rejected_without_request')
    after = ns['census']()
    assert before == after
    write('LOCAL_VALIDATION.json', {'schema': 'pocket4-independent-public-page-local-controls-v1',
        'ok': True, 'compile': True, 'unchanged_original_definitions': inherited,
        'controls': [{'name': x, 'passed': True} for x in controls],
        'original_descriptor_identities_restored': True, 'before': before, 'after': after,
        'HTTP_requests': 0, 'remote_processes': 0, 'Main_actions': 0,
        'actual_target_HTML_or_APK_success_inferred': False})
    requests = []
    for key in ['national']:
        request = {'host': 'pocket4', 'executable': '/usr/bin/python3',
            'args': ['-I', '-B', '-c', source, '--observe-' + key + '-page-only'],
            'cwd': '/home/alex/work', 'timeout_seconds': 180, 'cpu_quota_percent': 100,
            'memory_max_bytes': 268435456, 'nice': 10,
            'idempotency_key': 'sidecar-evidence-20261106-independent-' + key + '-public-page-r2'}
        row = write('exact-' + key + '-page-request.review-only.json', request)
        requests.append({'candidate_id': key, 'request': row, 'submitted': False,
                         'exact_source_bytes_match': request['args'][3].encode() == source.encode()})
    write('PAGE_READ_PLAN.json', {'schema': 'pocket4-independent-national-page-plan-v1',
        'state': 'UNSUBMITTED_REVIEW_ONLY', 'only_national_has_executable_request': True,
        'uber_is_research_only_no_request_or_source_entry': True,
        'root_submits_the_single_request_once_after_review': True,
        'no_other_URL_is_authorized_by_either_request': True,
        'requests': requests, 'artifact_delivery_request': None,
        'why_no_binary_request_yet': 'No fresh ordinary target-observed literal standalone-file URL exists yet.',
        'ordinary_HTML_success_does_not_admit_APK_install': True})
    readme = '''# 独立公开交付候选：National 与 Uber

本次只做本地证据联接和公开网页研究，没有发起目标机任务、下载 APK、安装、UI、权限操作或清理。候选来源均为第三方公开分发；官网和 Play 证明产品身份，不证明厂商为分发站背书。两条路径均不使用已经失败的 IHG/APKMirror 通道。

## 两个候选

| 应用／当前实际身份 | 正常公开页面的新线索 | 尚未证明 |
|---|---|---|
| National `com.ehi.national.mobile`；6.15.0.9354 / code9354；UID10141；原4个APK | [Softonic 下载页](https://national-car-rental.en.softonic.com/android/download)列6.16.0.9403、独立XAPK控制、65.97MB和容器SHA。新[Play正文](https://play.google.com/store/apps/details?id=com.ehi.national.mobile)确有6.16系列说明。 | 真实literal文件URL、完整字节、ABI和全部split、code、每件正常签名；官方完整6.16.0.9403标签仍只继承原S22引用。 |
| Uber `com.ubercab`；4.651.10003 / code316108；UID10139；原10个APK | [Uptodown下载页](https://uber.en.uptodown.com/android/download)现列4.655.10001、arm64-v8a/armeabi-v7a、130.1MB XAPK；明示“All variants”可取单独XAPK。 | 精确手动URL、完整split/code/签名，以及该版本的独立官方版本关联；[Play](https://play.google.com/store/apps/details?id=com.ubercab)没有展示版本号。默认Download是商店安装器，不能采用。 |

National当前PM证书SHA256为 `bef72da965ea0b91d0d69aae9aae41bcc232fad8643adefcc85e5870db405cfa`；Uber为 `4003231ab42feb8d955e62fdfaa4fad59567054b9c6bbc3d950299ddfc268392`。将来的每个base/split都必须正常验签并与各自合法当前签名关联。当前身份来自已固定r3清单，本研究没有重新观察Main。

National分发页容器SHA标签为 `a901bc4949fe241750cd7ea3fb5df690d00b21e217b2212be813bbd51e5a36bb`；Uber为 `1250b932a610e3830fb78d9382ae1b5faecd347b5f19db0b76644c58498aa41e`。它们是网页声明，尚未用完整文件重算。XAPK不等同于完整单体APK，也不能直接交给旧单APK安装worker。必须先核清manifest、split依赖、arm64选择、相同versionCode及signer，再核原native多包安装能力；普通PM完整性校验保持有效。

## 固定的最小下一步

优先仅封 National：`exact-national-page-request.review-only.json`只允许一次普通UID1000 GET已列固定页面。默认urllib身份、正常TLS/解析器、最多2MiB正文、120秒内预算／180秒执行预算、256MiB内存。不跟随重定向，不请求任何binary、installer、API、后继链接或登录；403、挑战、超限、超时均失败终止，无重试或替代身份。新的key沿原任务前缀，输出目录日期反映2026-11-07。Uber仅保留研究，没有执行入口或第二份请求。

结果只报告完整HTML pin和有界literal控制。即使返回ok，也仅意味着页面观察完整；找不到普通链接必须保持UNRESOLVED。Uptodown的“All variants”如果是动态控制，本请求不会执行脚本、猜测API或用默认安装器代替。取得真实原文后才能独立准备正常文件交付请求。

10个原read/save/FD/HTTP定义逐字继承；唯一入口是National，新控制仅作未跟随控制提取及不把默认安装器当文件。4个本地实际控制通过，未运行网络。写入pin是本次写入bytes计算值，不声称另做过远端文件回读或目录断电持久性证明。

## 被保留的失败与未选线索

IHG job `1a1b3437276-fc05-818f` 实际failed1：首GET403、`Cf-Mitigated: challenge`，第二页未请求，0 APK/Main操作，FD恢复。完整原文和terminal在原目录，绝不改写。该lane终止，不能用浏览器、身份、端点/CDN、代理、TLS/DNS或旧nonce处理挑战。

TextNow/Malavida公开web请求也遇403，停止。Marriott原S44路径403不重试，另一个正常Uptodown页仍为已装10.79.0；Hertz另一页4.84.0更旧。TextFree Softonic仅导向Play，Aptoide版本页冲突且未取得独立URL；没有为第三个候选硬凑可交付结论。神州同版327既有候选不再下载。未找到某条厂商直链，不等于不存在任何合法公开同包签名包。

## 全46范围与证据限度

`SOURCE_GAPS_46.json`在原46行基础上保留每个包的已装版本、来源差距及12项实际升级，只更新两个新候选和IHG真实失败。46成员来自既有native/framework observation；本研究没有重新枚举，也不将后续helper安装等同于Launcher成员变化。29商业App中仍有17项未实际升级；2项此轮候选尚无APK资格。全部业务就绪为0，清理为0。

`RESEARCH.json`记录精确URL、web refs、原始输入pins、当前全部APK身份及停止路径。网页来源不是target HTTP回执，缓存/页面版本变化已经分开记录；不将分发站“latest”当官方最新版。原allowlist、guard、历史失败和授权边界都不变。
'''
    write('README.md', readme)
    write('SOURCE_PINS.json', {'schema': 'pocket4-independent-public-delivery-review-source-v2',
        'state': 'FROZEN_LOCAL_REVIEW_ONLY_NOT_SUBMITTED',
        'files': [pin(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name != 'SOURCE_PINS.json']})
    print(json.dumps({'ok': True, 'source': pin(HERE / 'observe_independent_public_page.py'),
          'requests': requests, 'manifest': pin(HERE / 'SOURCE_PINS.json'),
          'files': len(list(HERE.iterdir())), 'HTTP_requests': 0, 'remote_submissions': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
