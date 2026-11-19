#!/usr/bin/env python3
"""Parse retained public responses. No network, APK, Android, or profile access."""
import datetime
import gzip
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import resource
import stat
import sys
import urllib.parse

ROOT = Path('/home/qq/work/p4-source-freshness-check-5cd1-20261119-r1')
PLAN_SHA = '570b4ee5f0796f94066752b388dec66066a489dd21c5e2fd38356b4044cac725'
GSI_FILENAME = 'aosp_x86_64-exp-CP3A.260905.010-16176746-81e37ae9.zip'
GSI_ARCHIVE_SHA = '81e37ae9e9280497c92fbda758b998a7dfab91ab9de000021622afa868a43b70'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_pinned(path, expected_sha, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.getuid() or st.st_size > maximum):
            raise ValueError('not bounded single-link owned file')
        with os.fdopen(fd, 'rb', closefd=False) as src:
            data = src.read(maximum + 1)
        end = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
                  'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (len(data) != st.st_size or sha(data) != expected_sha
                or any(getattr(st, k) != getattr(end, k) for k in fields)):
            raise ValueError('full source identity mismatch')
        return data
    finally:
        os.close(fd)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def visible(source):
    p = VisibleText()
    p.feed(source)
    return ' '.join(' '.join(p.parts).split())


def require_one(items, label):
    if len(items) != 1:
        raise ValueError(label + ': expected exactly one, saw ' + str(len(items)))
    return items[0]


def parse_play(source, package):
    markers = list(re.finditer(r"AF_initDataCallback\(\s*\{\s*key:\s*['\"]ds:5['\"]", source))
    marker = require_one(markers, 'Play primary detail block')
    tail = source[marker.end():]
    field = re.search(r'\bdata\s*:', tail)
    if not field:
        raise ValueError('Play data field absent')
    data, _ = json.JSONDecoder().raw_decode(tail[field.end():].lstrip())
    if data[1][2][77][0] != package:
        raise ValueError('Play primary package identity mismatch')
    version = data[1][2][140][0][0][0]
    if not isinstance(version, str) or not re.fullmatch(r'[0-9][A-Za-z0-9._+-]{0,79}', version):
        raise ValueError('unexpected version string')
    return {'version': version, 'package_identity': data[1][2][77][0],
            'package_identity_field': 'ds:5 data[1][2][77][0]',
            'version_field': 'ds:5 data[1][2][140][0][0][0]',
            'title': data[1][2][0][0], 'public_locale': 'en-US',
            'authoritative_GET_ITEMS_revalidation': False}


def parse_xiaomi(source, package):
    blocks = re.findall(r'<div\b[^>]*class=["\'][^"\']*\bdetail-version\b[^"\']*["\'][^>]*>(.*?)</div>', source, re.S)
    text = visible(require_one(blocks, 'Xiaomi detail-version'))
    version = require_one(re.findall(r'版本号\s*[：:]\s*([0-9][A-Za-z0-9._+-]*)', text), 'Xiaomi version')
    dates = re.findall(r'更新日期\s*[：:]\s*([0-9-]+)', text)
    return {'version': version, 'listed_update_date': require_one(dates, 'Xiaomi date'),
            'version_field': 'single detail-version div / 版本号',
            'package_identity_scope': 'exact request URL id; page has no manifest/package identity proof',
            'metadata_excerpt': text}


def parse_360(source, package):
    text = visible(source)
    version = require_one(re.findall(r'版本\s*[：:]\s*([0-9][A-Za-z0-9._+-]*)', text), '360 version')
    dates = re.findall(r'更新时间\s*[：:]\s*([0-9-]+\s+[0-9:]+)', text)
    return {'version': version, 'listed_update_date': require_one(dates, '360 date'),
            'version_field': 'single visible 版本 field',
            'package_identity_scope': 'exact request URL pname; not APK identity proof'}


def parse_tencent(source, package):
    assignments = list(re.finditer(r'\bwindow\.systemData\s*=', source))
    assignment = require_one(assignments, 'Tencent systemData literal')
    tree, _ = json.JSONDecoder().raw_decode(source[assignment.end():].lstrip())
    item = tree['appDetail']
    if item.get('packageName') != package:
        raise ValueError('Tencent primary appDetail packageName mismatch')
    version = item.get('versionName')
    if version is None and isinstance(item.get('version'), dict):
        version = item['version'].get('name')
    if not isinstance(version, str) or not re.fullmatch(r'[0-9][A-Za-z0-9._+-]*', version):
        raise ValueError('Tencent exact app object version field absent')
    return {'version': version, 'package_identity': item['packageName'],
            'package_identity_field': 'window.systemData.appDetail.packageName',
            'version_field': 'window.systemData.appDetail.versionName or version.name',
            'developer': item.get('developer'), 'title': item.get('appName'),
            'unrelated_store_package_versions_excluded': True}


def parse_release(source, package):
    value = json.loads(source)
    if value.get('draft') is not False or value.get('prerelease') is not False:
        raise ValueError('not a published stable release')
    version = value['tag_name'].removeprefix('v')
    return {'version': version, 'version_field': 'GitHub releases/latest tag_name',
            'published_at': value['published_at'], 'draft': False, 'prerelease': False,
            'release_url': value['html_url'], 'assets': [
                {k: a[k] for k in ('name', 'size', 'browser_download_url')}
                for a in value.get('assets', []) if a['name'].startswith(package + '-')],
            'asset_bodies_downloaded': False}


def parse_gsi(source, package):
    if package == 'system-gsi-release-list':
        headings = []
        for level, body in re.findall(r'<h([1-6])\b[^>]*>(.*?)</h\1>', source, re.S):
            text = visible(body)
            if 'Android' in text and ('stable' in text.lower() or 'Beta' in text):
                headings.append(text)
        text = visible(source)
        if 'Android 17 QPR1 (stable release)' not in text:
            raise ValueError('pinned stable release classification absent')
        return {'stable_selected_release': 'Android 17 QPR1',
                'release_classification_observed': 'stable release',
                'observed_release_headings': headings,
                'newer_beta_versions_not_selected': True,
                'version': 'CP3A.260905.010'}
    rows = [x for x in re.findall(r'<tr\b[^>]*>.*?</tr>', source, re.S) if GSI_FILENAME in x]
    row = require_one(rows, 'GSI exact x86_64 non-GMS table row')
    hashes = re.findall(r'(?<![A-Za-z0-9])[0-9a-f]{64}(?![A-Za-z0-9])', visible(row))
    archive_sha = require_one(hashes, 'GSI published archive SHA')
    if archive_sha != GSI_ARCHIVE_SHA:
        raise ValueError('published GSI archive identity drift')
    return {'version': 'CP3A.260905.010', 'build_id': '16176746',
            'architecture': 'x86_64', 'variant': 'AOSP without GMS',
            'archive_filename': GSI_FILENAME, 'archive_sha256': archive_sha,
            'archive_or_image_body_read': False}


def parse(source, row):
    host = urllib.parse.urlsplit(row['url']).hostname
    package = row['package']
    if host == 'play.google.com':
        return parse_play(source, package)
    if host == 'm.app.mi.com':
        return parse_xiaomi(source, package)
    if host == 'm.app.so.com':
        return parse_360(source, package)
    if host == 'a.app.qq.com':
        return parse_tencent(source, package)
    if host == 'api.github.com':
        return parse_release(source, package)
    if host == 'product-details.mozilla.org':
        value = json.loads(source)
        return {'version': value['version'], 'version_field': 'official stable version',
                'beta_version': value['beta_version'], 'nightly_version': value['nightly_version'],
                'beta_or_nightly_selected': False}
    if host == 'developer.android.com':
        return parse_gsi(source, package)
    raise ValueError('unrecognized fixed metadata host')


def compare(row, observation):
    if row['package'].startswith('system-gsi-'):
        return 'CURRENT_GSI_PUBLICATION_MATCH'
    selected = row['selected_version']
    found = observation['version']
    if found == selected:
        return 'PUBLIC_VERSION_MATCHES_SELECTED_SOURCE'
    if row['package'] == 'org.fcitx.fcitx5.android':
        expected = {row['package'] + '-' + selected + '-' + abi + '-release.apk'
                    for abi in ('arm64-v8a', 'armeabi-v7a', 'x86', 'x86_64')}
        seen = {a['name'] for a in observation['assets']}
        if found == selected.split('-0-g')[0] and expected.issubset(seen):
            observation['exact_selected_build_asset_names'] = sorted(expected)
            return 'STABLE_RELEASE_AND_EXACT_SELECTED_BUILD_ASSETS_MATCH'
    if re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', selected) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', found):
        a = [int(x) for x in selected.split('.')]
        b = [int(x) for x in found.split('.')]
        width = max(len(a), len(b))
        a.extend([0] * (width - len(a)))
        b.extend([0] * (width - len(b)))
        if b < a:
            return 'PUBLIC_CHANNEL_VERSION_BELOW_SELECTED_NO_DOWNGRADE'
        if b > a:
            return 'NEW_PUBLIC_VERSION_REQUIRES_SOURCE_QUALIFICATION'
    return 'VERSION_DIFFERENCE_REQUIRES_REVIEW'


def main():
    if os.getuid() == 0 or os.sched_getaffinity(0) != {31}:
        raise RuntimeError('requires ordinary account and explicit CPU31 affinity')
    resource.setrlimit(resource.RLIMIT_AS, (224 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)
    if len(sys.argv) != 2 or not re.fullmatch('[0-9a-f]{64}', sys.argv[1]):
        raise ValueError('exact original HTTP receipt SHA argument required')
    plan = json.loads(read_pinned(ROOT / 'PLAN.json', PLAN_SHA, 16384))
    receipt_bytes = read_pinned(ROOT / 'actual/HTTP-OBSERVATIONS.json', sys.argv[1], 128 * 1024)
    receipt = json.loads(receipt_bytes)
    if [x['package'] for x in receipt['rows']] != [x['package'] for x in plan['requests']]:
        raise ValueError('request roster changed')
    rows = []
    for request, http in zip(plan['requests'], receipt['rows']):
        row = dict(request, metadata_completed_utc=http['completed_utc'],
                   http_status=http.get('http_status'), body_sha256=http.get('body_sha256'))
        try:
            if http['status'] != 'PUBLIC_METADATA_BODY_RETAINED_PARSE_PENDING':
                raise ValueError('HTTP collection did not retain a complete public response: ' + http['status'])
            expected_path = ROOT / 'actual/public-response-bodies' / (row['package'] + '.http-body.gz')
            pin = http['retained_body']
            if pin['path'] != str(expected_path):
                raise ValueError('body path outside fixed collection')
            compressed = read_pinned(expected_path, pin['sha256'], 3 * 1024 * 1024)
            body = gzip.decompress(compressed)
            if len(body) != http['body_bytes'] or sha(body) != http['body_sha256']:
                raise ValueError('uncompressed full HTTP body identity mismatch')
            observed = parse(body.decode('utf-8'), row)
            row.update(status='PUBLIC_METADATA_PARSED', observation=observed,
                       comparison=compare(row, observed))
        except Exception as exc:
            row.update(status='NO_CURRENT_VERSION_CLAIM',
                       error=type(exc).__name__ + ': ' + str(exc)[:500], comparison='UNRESOLVED')
        rows.append(row)
        print(json.dumps({'package': row['package'], 'comparison': row['comparison'],
                          'version': row.get('observation', {}).get('version'),
                          'error': row.get('error')}, sort_keys=True), flush=True)
    completed = datetime.datetime.now(datetime.timezone.utc)
    expiry = datetime.datetime.fromisoformat(plan['original_GET_ITEMS_expires_utc'])
    result = {'schema': 'pocket4-public-source-version-refresh-v1',
              'completed_utc': completed.isoformat(),
              'collection_started_utc': receipt['started_utc'],
              'collection_completed_utc': receipt['completed_utc'],
              'HTTP_receipt': {'bytes': len(receipt_bytes), 'sha256': sha(receipt_bytes)},
              'required_non_system_count': 29, 'system_cohort_app_count': 10,
              'public_metadata_requests': 31,
              'parsed_public_observations': sum(x['status'] == 'PUBLIC_METADATA_PARSED' for x in rows),
              'new_public_version_candidates': [x['package'] for x in rows if x['comparison'] == 'NEW_PUBLIC_VERSION_REQUIRES_SOURCE_QUALIFICATION'],
              'unresolved_public_observations': [x['package'] for x in rows if x['comparison'] == 'UNRESOLVED'],
              'original_GET_ITEMS_expires_utc': expiry.isoformat(),
              'original_GET_ITEMS_seconds_remaining_at_this_observation': (expiry - completed).total_seconds(),
              'authoritative_play_metadata_TTL_renewed': False,
              'activation_metadata_revalidated': False,
              'APK_bytes_read_or_downloaded': 0, 'SDK_or_Android_calls': 0,
              'source_inputs_changed': False, 'account_or_credentials_accessed': False,
              'excluded_packages': plan['excluded_packages'],
              'Meituan_existing_userdata_signer_migration': 'PENDING',
              'latest_recheck_required_before_activation': True,
              'all39_latest_qualified': False, 'installed': False,
              'runtime_qualified': False, 'business_qualified': False,
              'production_ready': False, 'rows': rows}
    data = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
    path = ROOT / 'actual/PARSED-OBSERVATIONS.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    print(json.dumps({'path': str(path), 'bytes': len(data), 'sha256': sha(data),
                      'new_public_version_candidates': result['new_public_version_candidates'],
                      'unresolved': result['unresolved_public_observations']}, sort_keys=True))


if __name__ == '__main__':
    main()
