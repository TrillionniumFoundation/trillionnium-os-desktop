#!/usr/bin/env python3
"""Produce a new, review-only source proposal from pinned local evidence."""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
INPUTS = {
    'current_launcher_inventory_r3/INVENTORY.json': (1703185, '8932d7b7f18218717de09a2b05860f29d0f3d80f646127d89b6959bd60cc1ea9'),
    'official_source_scripts/s44_international_delivery_metadata/international14-delivery-evidence.json': (40247, 'eb1777bbd1db0aedec55ad55fca5089206d73361ada603543349c04a198ea3d9'),
    'reference/rail-zbj-delivery-research-r1/findings.json': (15588, '75ca411856d8bee35364f4e0b998080575d687debad6439093f0d0d0f92f5666'),
    'reference/rail-zbj-delivery-research-r1/derive_delivery_findings.py': (18184, 'd9256227e02ce7a7dbeacabb0a19a943189ff689b5d111e2dba34b6b3adf50b4'),
    'successor_install/source-r4-zbj-full48/candidate-r1/install_successor_native.py': (62386, '9148d312410c1a9d54ccdc95c32fcaa2c594027e07b223cac35ca5b1eb1991c7'),
    'successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/app-scope-after.private.json': (59259, '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a'),
    'official_source_scripts/s38_szzc_operator_signature/actual/stdout.original.json': (25448, '3ba6894d1d084f8d95b4ebfb342a3710990ce3b0aadf0e17710e9f608f8228a6'),
    'official_source_scripts/s39_szzc_operator_manifest/local-reinterpretation-r1/derived-result.json': (35952, '9e3c0258dae647cb6f6af0ba0f0d02bd0d42e20ca23c4907c777a8ab46d873e2'),
}


def pin(path, base=BASE):
    raw = (base / path).read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def emit(name, value):
    raw = value.encode() if isinstance(value, str) else (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    target = HERE / name
    with target.open('xb') as handle:
        handle.write(raw)
    return pin(name, HERE)


def main():
    actual = []
    for path, (size, sha) in INPUTS.items():
        p = pin(path)
        assert (p['bytes'], p['sha256']) == (size, sha), path
        actual.append(p)
    inv = json.loads((BASE / 'current_launcher_inventory_r3/INVENTORY.json').read_bytes())
    previous = json.loads((BASE / 'official_source_scripts/s44_international_delivery_metadata/international14-delivery-evidence.json').read_bytes())
    web = json.loads((HERE / 'WEB_OBSERVATIONS.json').read_bytes())
    international = {row['package']: row for row in previous['apps']}
    assert len(international) == 14 and len(inv['apps']) == 46
    assert len({row['package'] for row in inv['apps']}) == 46
    ihg = next(row for row in inv['apps'] if row['package'] == 'com.ihg.apps.android')
    mirror = next(row for row in web['sources'] if row['id'] == 'ihg_mirror_variant')
    assert ihg['current_installed_identity']['package_manager_certificate_sha256'] == [mirror['claims']['certificate_sha256']]
    assert ihg['effective_version_code'] == 50023219 and mirror['claims']['version_code'] == 50023496
    source = (HERE / 'read_ihg_public_pages_once.py').read_bytes()
    request = {
        'host': 'pocket4', 'executable': '/usr/bin/python3',
        'args': ['-I', '-B', '-c', source.decode(), '--observe-two-public-pages-no-apk'],
        'cwd': '/home/alex/work',
        'idempotency_key': 'sidecar-evidence-20261106-ihg-public-page-literal-r1',
        'timeout_seconds': 180, 'cpu_quota_percent': 100,
        'memory_max_bytes': 268435456, 'nice': 10,
    }
    request_pin = emit('exact-page-process-request.review-only.json', request)
    candidate = {
        'schema': 'pocket4-ihg-public-third-party-candidate-v1',
        'state': 'PUBLIC_METADATA_CANDIDATE_ONLY_NO_APK_OBTAINED',
        'distribution_class': 'public-third-party-distribution',
        'publisher_endorsement_of_mirror_proved': False,
        'publisher_direct_APK': False, 'package': ihg['package'],
        'installed_identity_reference': ihg['current_installed_identity'],
        'installed_version_name': ihg['version_name'],
        'current_48_scope_reference': next(p for p in actual if p['path'].endswith('app-scope-after.private.json')),
        'current_scope_is_not_fresh_runtime_or_install_authority': True,
        'publisher_identity_URL': next(s['url'] for s in web['sources'] if s['id'] == 'ihg_publisher'),
        'official_store_URL': next(s['url'] for s in web['sources'] if s['id'] == 'ihg_play'),
        'official_prior_version_reference': international[ihg['package']]['baseline_public_Play_metadata'],
        'fresh_official_page_versionName': None, 'fresh_official_page_versionCode': None,
        'fresh_official_page_update_date': '2026-11-03',
        'mirror_metadata_URL': mirror['url'], 'mirror_unverified_claims': mirror['claims'],
        'mirror_certificate_label_equals_current_PM_record': True,
        'actual_candidate_signature_verified': False, 'candidate_bytes_obtained': False,
        'candidate_ABI_or_split_completeness_verified': False,
        'official_global_latest_or_latest_usable_proved': False,
        'page_acquisition_request': request_pin,
        'APK_acquisition_request': None, 'APK_acquisition_missing_field': 'fresh literal delivery URL and its normal redirect destinations',
        'normal_verification_prerequisites': [
            'A separate exact ordinary HTTPS request must be bound to the fresh literal URL; do not replay the old observed nonce.',
            'One complete monolithic APK: exactly 47668450 bytes and SHA256 f6be54a948d96c34579f280b75d3e139bc3d430847173e14197e208331351f2f; disagreement rejects this candidate.',
            'Keep unchanged APK bytes and use existing pinned normal aapt/aapt2 and apksigner dependencies; preserve all stdout, stderr and warnings.',
            'Actual package com.ihg.apps.android; versionName 5.110.0; longVersionCode 50023496; no downgrade from 50023219.',
            'Actual complete manifest must have no split attribute, uses-split, or required-split declaration; verify the whole ZIP and all native ABIs, including arm64-v8a.',
            'Normal APK signature verification must succeed and current signer equal 1448dc9480a27e52b06c886b3f6386f2b122b115b1df1f156b81b9aebcc73163; no resigning or skipped integrity check.',
            'Resolve the official version association independently; the mirror latest label is not official latest-usability evidence.',
            'Any later installation needs an independent explicit source boundary and current scope/UID/CE-DE/native/runtime binding; do not modify or borrow the old installer ALLOWED.',
        ],
        'proposed_later_APK_transfer_bounds': {'maximum_payload_bytes': 47668450, 'maximum_wall_seconds': 240,
            'attempts': 1, 'automatic_retry': False, 'Range_resume': False, 'normal_TLS': True,
            'default_identity': True, 'challenge_or_403_or_expiry_action': 'STOP_PRESERVE_ORIGINAL',
            'new_root_only': True, 'Main_or_install_actions': 0},
        'new_downloads': 0, 'new_upgrades': 0, 'production_ready': False, 'cleanup_eligible': False,
    }
    emit('IHG_CANDIDATE.json', candidate)
    rows = []
    for app in inv['apps']:
        package = app['package']
        classification = app['classification']
        upgraded = app['upgrade']['state'] == 'INSTALLED_AND_CURRENT_BYTES_REOBSERVED_BUSINESS_QA_PENDING'
        row = {
            'package': package, 'label_reference': app['label_reference'], 'classification': classification,
            'current_version_name': app['version_name'], 'current_effective_version_code': app['effective_version_code'],
            'current_APK_count': len(app['current_installed_identity']['apks']),
            'current_PM_certificate_sha256': app['current_installed_identity']['package_manager_certificate_sha256'],
            'completed_upgrade_in_this_round': upgraded,
            'latest_usable_version_qualified': False, 'production_ready': False, 'cleanup_eligible': False,
            'absence_of_all_legal_public_delivery_proved': False,
        }
        if upgraded:
            row.update(publisher_direct_APK_state='SEE_ORIGINAL_QUALIFIED_DELIVERY_REFERENCE_NOT_RECLASSIFIED',
                public_same_package_delivery_state='ACTUAL_COMPLETE_VENDOR_SIGNED_ARTIFACT_INSTALLED',
                gap='已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。',
                next_channel='按当前已装版本推进业务回归；保留原实际来源和旧版本。',
                actual_upgrade_job=app['upgrade']['job_id'],
                qualification_reference=app['upgrade'].get('official_verifier_reference'),
                official_observed_version_name=app['version_name'])
        elif package in international:
            prior = international[package]
            row.update(publisher_direct_APK_state='NOT_VERIFIED_IN_EXAMINED_PUBLISHER_PAGES',
                public_same_package_delivery_state='UNKNOWN_NOT_EXCLUDED',
                official_observed_version_name=prior['baseline_public_Play_metadata']['version_name'],
                official_version_reference_kind='INHERITED_S22_METADATA_VIA_S44_NOT_CURRENT_ARTIFACT',
                official_store_url=prior['baseline_public_Play_metadata']['url'],
                inherited_source_evidence=prior['sources'],
                gap='厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。',
                next_channel='正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。')
            if package == 'com.ihg.apps.android':
                row.update(public_same_package_delivery_state='SELECTED_PUBLIC_MIRROR_SINGLE_APK_METADATA_CANDIDATE',
                    gap='公开单体候选5.110.0/code50023496；47,668,450B/ABI/签名标签仅页面声明。新Play正文未给code。',
                    next_channel='固定页面请求→一次fresh literal链接→独立完整下载与普通验签。',
                    new_evidence='IHG_CANDIDATE.json')
            elif package == 'com.amazon.mShop.android.shopping':
                row.update(public_same_package_delivery_state='PUBLIC_MIRROR_BUNDLE_METADATA_ONLY_NORMAL_LINK_EXPIRED',
                    gap='公开32.20.0.100候选为base+3 splits；普通下载页已报nonce失效，未重放。中国版包名不同。',
                    next_channel='新的正常公开交付需版本关联和完整split集合，不能用中国版替换。')
            elif package == 'com.hilton.android.hhonors':
                row['gap'] = '已查中国官网/商店为cn.hilton.android.hhonors，不能更新当前com包；其他同包公开交付未知。'
            elif package == 'com.marriott.mrt':
                row['gap'] = 'S44普通UID1000页面请求HTTP403，已停且保留失败；其他合法交付未被排除。'
                row['actual_failed_public_request'] = inv['Marriott_actual_public_delivery']
            elif package == 'com.enflick.android.TextNow':
                row['gap'] = '完整同包新包未取得；官方说明北美资格，目标真实账户/设备/地区资格未知，不规避。'
        elif package == 'com.MobileTicket':
            row.update(publisher_direct_APK_state='PUBLISHER_NAVIGATION_OBSERVED_NO_FRESH_COMPLETE_URL',
                public_same_package_delivery_state='KNOWN_TENCENT_CANDIDATE_INCOMPLETE_TLS_FAILURE_PRESERVED',
                official_observed_version_name='5.9.6.8',
                gap='5.9.6.8已知交付只有105119744B已验证前缀；两个TLS失败保留，未重试相同端点。',
                next_channel='厂商新发布的正常完整同包交付，或正常商店/新公开分发路径；完整验签前不升级。',
                historical_evidence='reference/rail-zbj-delivery-research-r1/findings.json')
        elif package == 'com.sankuai.meituan.takeoutnew':
            row.update(publisher_direct_APK_state='NOT_RECLASSIFIED_FROM_PRIOR_CANDIDATE_SOURCE',
                public_same_package_delivery_state='PRIOR_CANDIDATE_SIGNER_MISMATCH_OTHER_DELIVERY_UNKNOWN',
                official_observed_version_name=app['official_source'].get('reference', {}).get('candidate_version_name'),
                gap='已取得候选与当前合法签名不匹配；不能绕过检查、卸载替换或主动开位置权限。',
                next_channel='正常同包当前合法签名/有效签名轮换交付；实际完整性仍必须通过。',
                prior_reference=app['official_source'])
        elif package == 'com.szzc':
            row.update(publisher_direct_APK_state='PUBLIC_STORE_ARTIFACT_NORMAL_SIGNATURE_VERIFIED',
                public_same_package_delivery_state='COMPLETE_SAME_VERSION_VENDOR_SIGNED_ARTIFACT_AVAILABLE',
                official_observed_version_name='9.6.1',
                gap='S36完整220579134B，S38实际同签名正常验签，S39原文解释为9.6.1/code327，与当前同版本且字节不同。',
                next_channel='不为增加升级计数重装同版；等待正常新版本或按当前版本做真实回归。',
                additional_evidence=[p for p in actual if '/s38_' in p['path'] or '/s39_' in p['path']],
                newer_candidate_qualified=False)
        elif classification == 'upstream_open_source_service_or_IME':
            row.update(publisher_direct_APK_state='OFFICIAL_PROJECT_RELEASE_ASSET_REFERENCE',
                public_same_package_delivery_state='CURRENT_BYTES_EQUAL_PRIOR_OFFICIAL_RELEASE_ASSET',
                official_observed_version_name=('0.3.17.252432' if package == 'com.google.android.gms' else '0.1.3'),
                gap='本次公开latest导航仍是当前release；已装字节与原官方asset引用匹配，运行回归仍待完成。',
                next_channel=('保持当前服务，验证业务兼容性。' if package == 'com.google.android.gms' else '保持当前x86_64 code114输入法；ARM64同release code112不是升级。'),
                prior_reference=app['official_source'])
        elif classification.startswith('framework_owned'):
            row.update(publisher_direct_APK_state='MATCHING_FRAMEWORK_SOURCE_BUILD_REQUIRED',
                public_same_package_delivery_state='NOT_AN_INDEPENDENT_STORE_UPGRADE',
                official_observed_version_name=None,
                gap='需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。',
                next_channel='继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。')
        elif classification == 'local_owner_built_QA':
            row.update(publisher_direct_APK_state='OWNER_SOURCE_AND_FIXED_BUILD_CONTRACT',
                public_same_package_delivery_state='NOT_A_PUBLIC_STORE_PRODUCT',
                official_observed_version_name=None,
                gap='本地QA/fixture以固定源码、正常签名及真实身份合同为准，不虚构商店最新版。',
                next_channel='保留当前复现源码和有效合同；只按明确QA需求生成后继。')
        else:
            assert package == 'com.example.ndk_tests' and classification == 'OWNER_AND_SOURCE_UNKNOWN'
            row.update(publisher_direct_APK_state='UNKNOWN', public_same_package_delivery_state='UNKNOWN',
                official_observed_version_name=None,
                gap='实际NDK APK已正常审计，版本属性未声明/PM有效code0；所有者与原始来源仍未知。',
                next_channel='先取得真实owner/source/build来源，不将测试入口误认商店产品。')
        rows.append(row)
    counts = dict(collections.Counter(row['classification'] for row in rows))
    assert sum(row['completed_upgrade_in_this_round'] for row in rows) == 12
    assert sum(row['classification'] == 'third_party_commercial' and not row['completed_upgrade_in_this_round'] for row in rows) == 17
    table = {'schema': 'pocket4-all46-public-source-gaps-v1', 'state': 'LOCAL_RESEARCH_ONLY',
        'inventory_input': actual[0], 'scope': '46 membership rows from last native/framework resolver observation; latest installed identities from post-ZBJ scope',
        'membership_requeried_by_this_research': False, 'counts_by_classification': counts,
        'summary': {'Launcher_rows': 46, 'commercial_apps': 29, 'actual_completed_upgrades': 12,
            'commercial_not_upgraded': 17, 'selected_new_metadata_candidates': 1,
            'new_APK_downloads': 0, 'new_upgrades': 0, 'production_ready': 0, 'deleted_bytes': 0},
        'inherited_references_are_not_fresh_queries': True,
        'no_publisher_direct_URL_does_not_imply_no_legal_public_distribution': True,
        'rows': rows}
    emit('SOURCE_GAPS_46.json', table)
    emit('INPUT_PINS.json', {'schema': 'pocket4-public-delivery-input-pins-v1', 'files': actual,
        'web_observations': pin('WEB_OBSERVATIONS.json', HERE), 'historical_original_S22_available_locally': False})
    lines = ['# 全46项来源缺口与 IHG 公开交付候选', '',
        '选择 **IHG 5.110.0 / code50023496** 作为下一条公开交付候选。它是第三方公开分发页面列出的单体 APK，当前未下载、未验签、未安装。厂商官网和 Play 只用于核对应用身份；没有声称厂商授权 APKMirror。', '',
        '当前已装 IHG 为 **5.108.1 / code50023219 / UID10137**，单APK44,999,052B、SHA256 `c12bb3bae3514c94caaca0a4ef6e8f1ad4491cbce57fd2a15be48b83b4c85b90`。页面候选47,668,450B、SHA256 `f6be54a948d96c34579f280b75d3e139bc3d430847173e14197e208331351f2f`，列出 ARM64及另外四ABI。页面证书摘要与当前PM记录相同，只构成待核线索。', '',
        '官方先前S22记录为5.110.0，但本地只保留S44/原矩阵的派生引用，没有重取S22原文；本次新打开的Play正文只显示2026-11-03更新，不显示版本号/code。不能据此宣称官方全球最新版或目标上可用最新版已经证明。', '',
        '## 精确来源链', '',
        *['- ' + next(s['url'] for s in web['sources'] if s['id'] == key) for key in ['ihg_publisher','ihg_play','ihg_mirror_release','ihg_mirror_variant']], '',
        '官网→Play 是官方身份链；variant→普通下载中间页是独立的第三方分发链。现已见的临时key不会进入执行请求。', '',
        '## 待审唯一宿主请求', '',
        '`exact-page-process-request.review-only.json` 固定普通UID1000、两次HTML GET、每次2MiB、总120秒/外层180秒、256MiB、nice10。先从variant完整HTML选唯一literal中间页链接，至少等15秒，再取该HTML；只记录其中唯一here链接，不抓APK。默认urllib身份/系统TLS，不跟重定向、不自动重试，403/挑战/过期/格式歧义即失败保留。最终原始stdout、durable exit0和完整FD身份恢复共同证明这个有限观察完成，不能用页面result单独升级候选资格。', '',
        '实际最终URL未知，因此当前没有伪造一个可执行的APK下载URL。待新literal返回后才能封单次完整GET与普通验签；该后续请求仍为独立新来源范围，旧ALLOWED和Main/安装权限不变。', '',
        '## 46项完整来源差距', '',
        '以下“直链未核实”不等同于“无法获得任何合法公开同包签名包”。12项已实际正常升级仍缺业务验收；17项尚未升级的商业应用中，IHG是本轮新增的具体公开单体候选。11个AOSP组件/演示、WebView测试壳、两个自有QA、NDK未知来源和两个开源服务/输入法分别保留各自构建或发布约束。', '',
        '| App / 包名 | 当前版本 / 有效code | 来源现状与缺口 | 正常下一步 |',
        '|---|---|---|---|']
    for row in rows:
        version = row['current_version_name'] if row['current_version_name'] is not None else '未声明'
        label = row['label_reference'] or 'NDK测试入口（标签未提取）'
        lines.append('| ' + label + '<br>`' + row['package'] + '` | ' + str(version) + ' / ' + str(row['current_effective_version_code']) + ' | ' + row['gap'] + ' | ' + row['next_channel'] + ' |')
    lines += ['', '## 保留的失败与语义边界', '',
        '- Amazon中国版与已装Shopping包名不同；公开32.20候选为APKM集合且本次普通下载页nonce失效，没有重放。',
        '- Hilton中国渠道包名不同。12306原不完整传输/TLS失败、Marriott原HTTP403、美团签名不匹配全部保留，不通过换身份或签名绕过。',
        '- 神州完整同签名9.6.1/code327候选已由S38/S39实际证据说明，不能再写成只有不完整文件；它与当前同版本，不是已完成升级。',
        '- 公开页面、来源标签、普通验签、安装成功和生产可用是不同层证据；本研究新增下载0、升级0、生产验收0、删除0。',
        '- 此新目录不修改 `current_launcher_inventory_r3/`、`CURRENT_STATUS`、旧失败账本或任何已冻结安装器来源白名单。', '',
        '详细当前身份、原证据pin、各渠道状态和限制见JSON；公开网页ref只作本次工具观察索引，未伪称raw HTTP正文。', '']
    emit('README.md', '\n'.join(lines))
    # Pin every prepared output without rewriting older records.
    for path, expected in INPUTS.items():
        p = pin(path)
        assert (p['bytes'], p['sha256']) == expected
    validation = {'schema': 'pocket4-public-delivery-local-preparation-v1', 'ok': True,
        'input_pins_verified': len(actual), 'rows': len(rows), 'classifications': counts,
        'completed_upgrade_rows': 12, 'commercial_not_upgraded_rows': 17,
        'candidate_page_claims_are_not_actual_APK_proof': True,
        'same_installed_certificate_label_only': True, 'prior_nonce_absent_from_worker': b'b0b3cbac8065608f28b9e64014b145770202a52a' not in source,
        'old_installer_and_inventory_unchanged': True, 'remote_processes': 0,
        'APK_downloads': 0, 'Main_actions': 0, 'installs': 0, 'permission_changes': 0,
        'source': pin('read_ihg_public_pages_once.py', HERE), 'page_request': request_pin}
    emit('LOCAL_VALIDATION.json', validation)
    files = [pin(p.name, HERE) for p in sorted(HERE.iterdir()) if p.is_file() and p.name != 'SOURCE_PINS.json']
    seal = emit('SOURCE_PINS.json', {'schema': 'pocket4-public-delivery-review-source-v1', 'files': files})
    print(json.dumps({'ok': True, 'files': len(files), 'seal': seal, 'page_request': request_pin,
                      'worker': pin('read_ihg_public_pages_once.py', HERE), 'rows': 46}, sort_keys=True))


if __name__ == '__main__':
    main()
