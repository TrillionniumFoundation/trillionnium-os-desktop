#!/usr/bin/env python3
"""Pure local review packaging; no network, Android or remote execution."""
import ast
import datetime
import hashlib
import json
from pathlib import Path
import runpy

PROJECT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
CANDIDATE = BASE / 'candidate-r1'


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def write(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError('EXISTING_DIFFERENT_REVIEW_ARTIFACT:' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as output:
            output.write(raw)
    return pin(path)


def source(url, refs, observed):
    return {'url': url, 'web_reference_ids': refs, 'observed': observed,
            'authority': 'publisher_or_official_store', 'APK_obtained': False}


def main():
    baseline_path = PROJECT / 'reference/remaining34-source-actions.json'
    baseline = json.loads(baseline_path.read_bytes())
    selected = {row['package']: row for row in baseline['apps']
                if row['category'] == 'OFFICIAL_PUBLIC_METADATA_NO_COMPLETE_ELIGIBLE_APK'}
    assert len(selected) == 14
    observations = {
        'com.amazon.mShop.android.shopping': {
            'status': 'NO_VERIFIED_PUBLIC_SAME_PACKAGE_APK_CHAIN',
            'sources': [
                source('https://www.amazon.com/androidapp', ['turn138view1'],
                       'The web tool returned DisabledError, not an observed HTTP 403 and not a download URL.'),
                source('https://developer.amazon.com/apps-and-games/blogs/2025/02/upcoming-changes-to-amazon-appstore-for-android-devices-and-coins-program', ['turn137search1'],
                       'Amazon states ordinary Android Appstore support ended August 20, 2025; Fire tablet/TV distribution is separate.'),
                source('https://sj.qq.com/appdetail/com.amazon.mShop.android.shopping', ['turn146view0'],
                       'Not accessible through this web tool; no complete same-package delivery was observed.'),
            ],
            'minimum_next_action': 'Use the normal Amazon Shopping Play entry in an eligible authorized store/device context; any supplied publisher package must first be complete and match package, current vendor signer and applicable version code.',
            'specific_gap': 'No published complete Shopping APK URL has been verified. Amazon Appstore com.amazon.venezia is a different package and its ordinary Android service ended; substituting its old APK cannot update Shopping.',
        },
        'com.enflick.android.TextNow': {
            'status': 'OFFICIAL_PLAY_PATH_WITH_PUBLISHER_DOWNLOAD_PAGE_403',
            'sources': [
                source('https://www.textnow.com/downloads', ['turn138view0'], 'The normal page request returned HTTP 403 Forbidden; no retry or client alteration was attempted.'),
                source('https://help.textnow.com/hc/en-us/articles/360042573174-How-to-update-the-TextNow-app', ['turn136search3', 'turn137search5', 'turn149view3'], 'The publisher instructs Android updates through Google Play; Google account sign-in may be required.'),
                source('https://help.textnow.com/hc/en-us/articles/360042529194-Is-TextNow-available-in-my-country/', ['turn137search6'], 'The publisher says download/use is currently in North America and new registration is not available outside North America. This is not a measurement of the Pocket4 account or location.'),
                source('https://help.textnow.com/hc/en-us/articles/360042572274-TextNow-Supported-Platforms', ['turn136search4', 'turn137search4'], 'The publisher states Android 9 or later; an acquired APK manifest is still required for candidate qualification.'),
            ],
            'minimum_next_action': 'Use the normal Play update path only if the authorized account, device and region qualify; obtain and verify the complete delivered APK/split set without bypassing the observed publisher refusal.',
            'specific_gap': 'No complete same-package public APK endpoint was obtained. Account/region/store eligibility on the target is unknown, not an observed failure.',
        },
        'com.united.mobile.android': {
            'status': 'OFFICIAL_PAGE_JS_ONLY_AND_FALSE_STORE_CANDIDATE_REJECTED',
            'sources': [
                source('https://www.united.com/en/us/fly/travel-experience/united-app.html', ['turn145view3'], 'Only a JavaScript-required shell was available to this text retrieval; no Android APK URL was exposed.'),
                source('https://www.united.com/web/en-US/content/travel/wireless/download-apk/default.aspx', ['turn138view2'], 'The official legacy path was not accessible through this web tool; its present download service is unverified.'),
                source('https://sj.qq.com/appdetail/com.united.mobile.android', ['turn146view2'], 'The actual rendered page is recommendations, including 中国联合航空 and other apps, rather than a United same-package APK listing.'),
            ],
            'minimum_next_action': 'Use normal United Play delivery in an eligible authorized store context, or a publisher-supplied current URL. The legacy path or a recommendations page is insufficient for a download candidate.',
            'specific_gap': 'No complete official United APK delivery chain was verified; the apparent Tencent route is demonstrably not the requested artifact.',
        },
        'com.ubercab': {
            'status': 'OFFICIAL_ANDROID_STORE_LINK_WITHOUT_PUBLIC_APK',
            'sources': [
                source('https://www.uber.com/global/en/ride/app/', ['turn138view3'], 'The publisher provides Google Play and App Store buttons routed through rides.sng.link.'),
                source('https://rides.sng.link/Aw5zn/o4sf?_dl=uber%3A%2F%2Fhome&_forward_params=1&_smtype=3&pcn=ubercom-ride-app-page&pscn=wb_uber_chameleon_UBRdc2zsnpx54r68hu6kt50', ['turn139view0'], 'The web tool reported a non-retryable 500/access failure after the ordinary publisher redirect; no APK was returned.'),
                source('https://help.uber.com/riders/article/downloading-the-rider-app-?nodeId=bd546eae-73e0-49e3-a2da-0dbfa2a1d526', ['turn140search0'], 'The rider help page specifies Android 8 or later and Google Play installation. Driver-app requirements are a different product.'),
            ],
            'minimum_next_action': 'Use the normal rider Play listing under valid account/device/region conditions and retain the actual delivered package set for full signature and compatibility verification.',
            'specific_gap': 'No complete public APK URL or verified applicable version code. The baseline public version label is itself unknown.',
        },
        'com.marriott.mrt': {
            'status': 'NEW_PUBLISHER_LINKED_SAME_PACKAGE_STORE_METADATA_PROBE_PROPOSED',
            'sources': [
                source('https://www.marriott.com.cn/mobileapp.mi', ['turn145view0'], 'The actual official Chinese page Android button links to a.app.qq.com/o/simple.jsp?pkgname=com.marriott.mrt.'),
                source('https://a.app.qq.com/o/simple.jsp?pkgname=com.marriott.mrt', ['turn146view4'], 'The same-package public market page displays version 11.15.0 and 231.37 MB. It also advertises the separate Tencent Appstore bootstrap; the latter is not a Marriott artifact.'),
                source('https://sj.qq.com/appdetail/com.marriott.mrt', ['turn149view0'], 'The official market page displays 11.15.0, updated 2026-10-30, Marriott developer and 上海姜根酒店管理有限公司 operator, but the rendered download control exposes no complete APK URL.'),
            ],
            'minimum_next_action': 'Run only the separately reviewed S44 two-HTML-page metadata probe once. Review a literal public delivery field if present; any later APK download needs a fixed bounded new request and complete same-package/current-vendor signature/version-code validation.',
            'specific_gap': '11.15.0 on the China channel and 10.81.0 on the prior Play page are labels from different channels. Neither establishes a newer applicable candidate without the complete APK manifest, version code and signer.',
            'new_public_version_metadata': {'value': '11.15.0', 'channel': 'publisher-linked Tencent China market', 'artifact_obtained': False},
        },
        'com.hilton.android.hhonors': {
            'status': 'PUBLISHER_TO_OFFICIAL_PLAY_CHAIN_CONFIRMED_METADATA_ONLY',
            'sources': [
                source('https://www.hilton.com/en/hilton-honors/mobile-app/', ['turn139search0', 'turn145view1'], 'The official Android button follows hilton.app.link.'),
                source('https://hilton.app.link/cZEMfpKruJb?cid=OH,WW,AppDownloadGoogle,MULTIPR,imageHeadliner1,', ['turn146view5'], 'The normal publisher link presents Google Play; following that link reaches the exact com.hilton.android.hhonors Play listing.'),
                source('https://play.google.com/store/apps/details?id=com.hilton.android.hhonors', ['turn149view5'], 'Normal publisher-link traversal reaches the correct official Play package. This is not an APK delivery.'),
            ],
            'minimum_next_action': 'Use that normal Play path in the authorized eligible environment, then verify the complete delivered APK/split set.',
            'specific_gap': 'No public complete publisher APK URL was found; store delivery/eligibility has not been observed.',
        },
        'com.ihg.apps.android': {
            'status': 'PUBLISHER_PLAY_LINK_WITHOUT_PUBLIC_APK',
            'sources': [source('https://www.ihg.com/content/cn/zh/support/mobile?scmisc=applestore', ['turn144search3', 'turn145view2'], 'The current official Chinese support page is readable and expressly offers Android Google Play; no APK URL appears in retrieved content. This does not erase the earlier US-page access failure.')],
            'minimum_next_action': 'Use the normal Google Play entry under valid account/device/region conditions; retain any complete delivery for candidate verification.',
            'specific_gap': 'No complete normal APK/split delivery was obtained.',
        },
        'com.Hyatt.hyt': {
            'status': 'PUBLISHER_INFORMATION_AVAILABLE_NO_COMPLETE_ANDROID_DELIVERY',
            'sources': [
                source('https://world.hyatt.com/content/gp/en/rewards/mobile.html?language=en', ['turn149view1'], 'This round retrieved the public benefits/member information page but no complete Android binary link; the previous HTTP 403 in baseline evidence is kept separately.'),
                source('https://www.hyatt.com/zh-CN/info/chromecast', ['turn140search5'], 'Publisher instructions identify App Store or Google Play for the World of Hyatt app.'),
            ],
            'minimum_next_action': 'Use the normal Hyatt Play listing in an eligible authorized store context. Complete artifact and current-version equivalence remain to be established.',
            'specific_gap': 'The same 26.9.0 public/historical version label does not show current installed bytes equal a complete applicable official release.',
        },
        'com.ehi.national.mobile': {
            'status': 'PUBLISHER_DOWNLOAD_PAGE_CTA_UNRESOLVED',
            'sources': [source('https://www.nationalcar.com/en/emerald-club/national-mobile-app.html', ['turn148view0'], 'The normal official page is readable this round, with Download the App imagery; text retrieval exposes no complete APK URL. Earlier baseline access failures are not rewritten.')],
            'minimum_next_action': 'Follow the normal publisher app-store button in an authorized eligible environment, or request an actual publisher-supplied complete delivery URL; do not guess asset paths.',
            'specific_gap': 'Dynamic/image download control not resolved into an Android delivery URL; no complete APK.',
        },
        'com.hertz.android.digital': {
            'status': 'PUBLISHER_DOWNLOAD_PAGE_CTA_UNRESOLVED',
            'sources': [source('https://www.hertz.com/us/en/products-and-services/hertz-mobile-app', ['turn148view1'], 'The official page is readable and describes download, but retrieved content exposes no complete Android binary URL.')],
            'minimum_next_action': 'Use the normal publisher/Play channel under valid eligibility, or an actual publisher-provided complete URL; do not synthesize asset URLs.',
            'specific_gap': 'No resolved complete APK or verified applicable store delivery.',
        },
        'jp.co.ana.android.tabidachi': {
            'status': 'PUBLISHER_TO_EXACT_PLAY_PACKAGE_CONFIRMED_METADATA_ONLY',
            'sources': [
                source('https://www.ana.co.jp/en/jp/serviceinfo/mobile/ana_app/', ['turn148view2'], 'The current official ANA app page links to the normal Google Play entry.'),
                source('https://play.google.com/store/apps/details?hl=en&id=jp.co.ana.android.tabidachi', ['turn149view4'], 'Following the actual publisher link reaches the exact target package; no full APK is exposed.'),
            ],
            'minimum_next_action': 'Use the exact ANA app Play entry in the authorized eligible environment; independently verify all delivered splits and the manifest.',
            'specific_gap': 'No complete APK/split delivery. Statements about the separate ANA Mileage Club app do not establish restrictions for this package.',
        },
        'com.bestbuy.android': {
            'status': 'OFFICIAL_PLAY_INSTALL_INSTRUCTIONS_NO_PUBLIC_APK',
            'sources': [
                source('https://www.bestbuy.com/discover-learn/benefits-of-the-best-buy-app/pcmcat1674162066016/', ['turn147search1'], 'The official page identifies Google Play for Android; an optional SMS route exists but no SMS was sent.'),
                source('https://www.bestbuy.com/site/misc/best-buy-drops/pcmcat1714764109320.c?id=pcmcat1714764109320%2F', ['turn147search3'], 'The current official page points to App Store or Google Play.'),
            ],
            'minimum_next_action': 'Use ordinary Play delivery in the authorized eligible environment; no need to send a message to request a link.',
            'specific_gap': 'No complete normal public APK URL found; actual store delivery unknown.',
        },
        'com.pinger.textfree': {
            'status': 'PUBLISHER_ANDROID_PAGE_NO_PUBLIC_APK',
            'sources': [source('https://textfree.com/', ['turn148view3'], 'textfree.us normally redirects here. The vendor page describes Android/Play availability and QR download controls, but no complete APK URL appears in retrieved content.')],
            'minimum_next_action': 'Use the normal TextFree com.pinger.textfree Play channel with eligible authorized conditions; verify actual delivered artifacts.',
            'specific_gap': 'No full APK. TextMe and other similarly named calling apps are not replacements for this package.',
        },
        'com.zillow.android.streeteasy': {
            'status': 'OBSERVED_PUBLISHER_ROUTE_TO_IOS_NOT_ANDROID_DELIVERY',
            'sources': [
                source('https://streeteasy.com/mobile', ['turn149view2'], 'The normal observed client request redirects to the iOS StreetEasy store page, which is not an Android artifact.'),
                source('https://streeteasy.com/blog/streeteasy-mobile-app-updates/', ['turn147search11'], 'An older official page identifies Android Google Play; this is a normal channel reference, not current APK bytes.'),
            ],
            'minimum_next_action': 'Use the existing exact consumer StreetEasy Play package entry in the eligible authorized environment; do not substitute Agent Tools or the iOS artifact.',
            'specific_gap': 'No complete current Android public delivery URL; observed mobile-page routing resolves only to iOS.',
        },
    }
    assert set(observations) == set(selected)
    apps = []
    for package, observation in observations.items():
        old = selected[package]
        public = old['official_source']
        apps.append({'package': package, 'label': old['launcher_label_observed'],
                     'baseline_public_Play_metadata': {
                         'copied_from_matrix_not_original_s22_reread': True,
                         'original_s22_locally_present_during_this_research': (PROJECT / public['evidence_ref']['path']).exists(),
                         'original_s22_reference': public['evidence_ref'],
                         'observed_utc': public['observed_utc'],
                         'url': public['official_store_url'],
                         'version_name': public['public_version_name'],
                         'version_code': None, 'artifact_qualification': False},
                     **observation,
                     'complete_APK_or_split_set_obtained': False,
                     'normal_complete_signature_verified': False,
                     'same_package_current_vendor_signer_verified': False,
                     'applicable_latest_version_qualified': False,
                     'normal_store_account_device_region_eligibility_on_target': 'UNKNOWN_NOT_OBSERVED',
                     'production_ready': False, 'cleanup_eligible': False})
    web_files = [pin(p) for p in sorted((BASE / 'research-web').glob('*.tool-result.json'))]
    research = {
        'schema': 'pocket4-international14-normal-public-delivery-research-s44-v1',
        'date_utc': '2026-11-06', 'state': 'PRIMARY_SOURCE_RESEARCH_NO_NEW_APK_NO_RUNTIME_OBSERVATION',
        'baseline_matrix_pin': pin(baseline_path),
        'web_tool_result_object_snapshots': web_files,
        'raw_web_snapshot_semantics': 'JSON snapshots of returned web-tool objects, not byte-identical HTTP bodies. Search noise from third-party mirrors may appear in raw responses but was excluded from evidence and actions.',
        'reference_ids_without_original_tool_payload_saved': ['turn136search3', 'turn136search4', 'turn138view0', 'turn138view1', 'turn138view2', 'turn138view3'],
        'scope': {'international_packages': 14, 'all_current_launcher_inventory_proved_by_this_research': False,
                  'older_remaining34_matrix_retained_unchanged': True,
                  'no_new_current_scope_or_installed_version_claim': True},
        'actions': {'web_primary_source_reads': True, 'remote_process_submissions': 0,
                    'new_APK_downloads': 0, 'Android_commands': 0, 'Main_actions': 0,
                    'installs': 0, 'permission_changes': 0, 'SMS_sent': 0,
                    'ADB_added': False, 'account_region_integrity_access_bypasses': 0,
                    'retries_of_HTTP_403_or_429': 0},
        'new_actionable_delivery_lead': 'Publisher-linked Marriott same-package Tencent public metadata; two-page read-only probe is prepared but not executed.',
        'limits': ['A Play/public-store version label is not a complete APK or split set.',
                   'No finding claims that every lawful store path is impossible.',
                   'Account, region, hardware and certification prerequisites are not bypassed.',
                   'No official-current version assertion follows from matching version-name strings alone.',
                   'No new scope, production readiness or cleanup eligibility is asserted.'],
        'apps': apps,
    }
    research_pin = write(BASE / 'international14-delivery-evidence.json', research)
    worker = CANDIDATE / 'read_public_marriott_metadata_once.py'
    raw = worker.read_bytes()
    compile(raw, str(worker), 'exec')
    definitions = runpy.run_path(str(worker), run_name='s44_local_parser_definitions_only')
    parse = definitions['observe_public_fields']
    sample = b'<script id="__NEXT_DATA__" type="application/json">{"items":[{"pkgName":"com.marriott.mrt","versionName":"11.15.0","downloadUrl":"https://example.invalid/m.apk"},{"pkgName":"com.tencent.android.qqdownloader","downloadUrl":"https://example.invalid/store.apk"}]}</script>'
    seen = parse(sample)
    links = seen['unfetched_https_delivery_fields']
    assert len(links) == 2
    assert links[0]['target_package_explicit_match'] is True
    assert links[1]['target_package_explicit_match'] is False
    inherited = parse(b'<script type="application/json">{"pkgName":"com.marriott.mrt","recommendations":[{"downloadUrl":"https://example.invalid/unknown.apk"}]}</script>')
    child = inherited['unfetched_https_delivery_fields'][0]
    assert child['target_package_explicit_match'] is False and child['target_package_inherited_context_only'] is True
    controls = {
        'schema': 'pocket4-s44-local-public-metadata-parser-controls-v1',
        'worker_pin': pin(worker), 'syntax_compile_only': True,
        'two_meaningful_parser_controls': [
            {'name': 'target_and_tencent_bootstrap_kept_separate', 'passed': True},
            {'name': 'inherited_package_context_not_direct_target_match', 'passed': True}],
        'fixture_URLs': 'example.invalid, synthetic and never requested',
        'remote_or_network_execution': False, 'probe_main_called': False,
        'APKs_downloaded': 0, 'runtime_or_business_PASS': False,
    }
    controls_pin = write(CANDIDATE / 'local-controls.json', controls)
    request = {
        'host': 'pocket4', 'executable': '/usr/bin/python3',
        'args': ['-I', '-B', '-c', raw.decode(), '--read-two-published-store-pages-once'],
        'cwd': '/home/alex/work',
        'idempotency_key': 'pocket4-marriott-official-public-delivery-metadata-20261106-s44-r1',
        'cpu_quota_percent': 100, 'memory_max_bytes': 268435456, 'nice': 10,
        'timeout_seconds': 180,
    }
    request_pin = write(CANDIDATE / 'exact-process-request.review-only.json', request)
    assert request['args'][3].encode() == raw
    plan = {
        'schema': 'pocket4-s44-two-published-HTML-pages-review-plan-v1',
        'state': 'PREPARED_NOT_SUBMITTED', 'worker_pin': pin(worker),
        'request_pin': request_pin, 'research_pin': research_pin,
        'ordinary_uid_euid_gid_egid_required': 1000,
        'fixed_entries': list(definitions['URLS']), 'redirect_hosts': sorted(definitions['HOSTS']),
        'maximum_entry_requests': 2, 'maximum_redirects_per_entry': 4,
        'maximum_success_body_bytes_per_page': definitions['MAX_BODY'],
        'maximum_HTTP_error_body_bytes': definitions['MAX_ERROR_BODY'],
        'own_default_SIGALRM_seconds': definitions['MAX_TOTAL_SECONDS'],
        'outer_process_timeout_seconds': 180, 'socket_timeout_at_most_seconds': 20,
        'application_retry_count': 0,
        'normal_OS_resolver_internal_retries_unknown': True,
        'failure_behavior': 'Stop on first HTTP/network/redirect/size/encoding/deadline error; retain result/raw response if available. Respect 403/429 and Retry-After; no alternate URL or client retry. A SIGALRM or outer timeout has no successful result.',
        'network_behavior': 'Default Python urllib user agent and default certificate/hostname validation. No cookies/authentication, no DNS/IP/proxy/TLS overrides, no JavaScript execution.',
        'delivery_fields': 'Only public structured JSON script fields and literal APK anchors are recorded. Target package direct and inherited contexts remain separate. No delivery field is fetched or treated as a qualified APK.',
        'source_contract': 'Standalone narrow metadata reader; it does not inherit or replace Android/installer/build qualification contracts.',
        'new_output_root': str(definitions['ROOT']),
        'output_names': ['page-01.html', 'page-02.html', 'page-01.error-body', 'page-02.error-body', 'result.json'],
        'new_files_only': True, 'existing_root_collision_stops': True,
        'result_success_meaning': 'Both bounded public-page captures completed with descriptor identities restored; no candidate or business qualification.',
        'APK_downloads': 0, 'APK_signature_verified': False, 'APK_candidate_qualified': False,
        'Android_Main_locks_namespaces_UI_install_permission_or_business_reads': 0,
        'calls_to_other_remote_jobs': 0, 'python_full_file_identity_verified_by_probe': False,
        'future_APK_download_requires_separate_fixed_source_review': True,
        'fresh_same_package_current_vendor_signer_versionCode_ABI_minSdk_required_before_install': True,
        'production_ready': False, 'cleanup_eligible': False,
        'local_controls_pin': controls_pin,
    }
    plan_pin = write(CANDIDATE / 'execution-plan.json', plan)
    pins = {
        'schema': 'pocket4-s44-local-review-source-pins-v1',
        'inputs': [pin(baseline_path), *web_files],
        'outputs': [pin(worker), pin(Path(__file__)), research_pin, controls_pin, request_pin, plan_pin],
        'process_request_source_byte_exact': True, 'remote_submissions': 0,
    }
    pins_pin = write(CANDIDATE / 'SOURCE_PINS.json', pins)
    print(json.dumps({'research': research_pin, 'worker': pin(worker), 'request': request_pin,
                      'plan': plan_pin, 'pins': pins_pin, 'local_controls': controls_pin,
                      'remote_submissions': 0}, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
