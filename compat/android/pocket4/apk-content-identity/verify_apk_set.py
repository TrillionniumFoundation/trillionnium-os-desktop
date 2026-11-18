"""Verify a complete, externally pinned APK set. No installation or execution."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile

import verify_apk as single
from axml_metadata import ANDROID, decode_axml, metadata as axml_metadata

SCHEMA = 'pocket4-apk-set-candidate-v1'
CANDIDATE_LIMIT = 256 * 1024
APK_LIMIT = 1024 * 1024 * 1024
SET_LIMIT = 4 * APK_LIMIT
RECEIPT_LIMIT = 8 * 1024 * 1024
_SPLIT = re.compile(r'[A-Za-z0-9_]+(?:[.][A-Za-z0-9_]+)*')
_NO_CREDIT = {'installed': False, 'runtime_qualified': False, 'production_ready': False}


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _f9(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _hash(stream):
    stream.seek(0)
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(block)
    stream.seek(0)
    return h.hexdigest()


@contextmanager
def _held(path, limit, expected=None):
    path = Path(path)
    _need(path.is_absolute(), 'Source path must be absolute')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        first = _f9(os.fstat(stream.fileno()))
        _need(stat.S_ISREG(first[2]) and first[5] == 1 and 0 < first[6] <= limit,
              'Source is not a bounded, single-link regular file')
        sha = _hash(stream)
        if expected is not None:
            _need(first[6] == expected['bytes'] and sha == expected['sha256'],
                  'Source bytes or SHA-256 differ from the external pin')
        pin = {'path': str(path), 'bytes': first[6], 'sha256': sha,
               'f9': list(first)}
        yield stream, pin
        _need(_hash(stream) == sha and _f9(os.fstat(stream.fileno())) == first
              and _f9(os.stat(path, follow_symlinks=False)) == first,
              'Original source changed during APK-set verification')


def _json(raw):
    def constant(value):
        raise ValueError('Non-finite JSON value: ' + value)
    return json.loads(raw, object_pairs_hook=single._unique_json, parse_constant=constant)


def _name(value):
    return (type(value) is str and 0 < len(value.encode()) <= 256
            and _SPLIT.fullmatch(value) is not None)


def normalized_name(split):
    return 'base.apk' if split is None else 'split_' + split + '.apk'


def _member_name(name):
    parts = (name[:-1] if isinstance(name, str) and name.endswith('/') else name)
    _need(type(name) is str and 0 < len(name.encode()) <= 4096
          and not name.startswith('/') and '\\' not in name
          and not re.match(r'^[A-Za-z]:', name)
          and all(32 <= ord(c) != 127 for c in name)
          and all(p not in ('', '.', '..') for p in parts.split('/')),
          'Invalid ZIP member path')


def safe_members(archive, count_limit=100000, expansion_limit=SET_LIMIT):
    members = archive.infolist()
    _need(0 < len(members) <= count_limit, 'ZIP member count exceeds its bound')
    names, files, canonical = set(), {}, {}
    total = 0
    for item in members:
        name = item.filename
        _member_name(name)
        _need(name == item.orig_filename and name not in names,
              'ZIP member names are duplicate or truncated')
        names.add(name)
        isdir = item.is_dir()
        key = name.rstrip('/')
        _need(key not in canonical, 'ZIP file and directory names alias')
        canonical[key] = isdir
        kind = stat.S_IFMT(item.external_attr >> 16)
        _need(kind in (0, stat.S_IFREG, stat.S_IFDIR)
              and (kind != stat.S_IFDIR or isdir)
              and (kind != stat.S_IFREG or not isdir),
              'ZIP member is a link or special file')
        _need(not item.flag_bits & 1 and item.compress_type in (zipfile.ZIP_STORED,
                                                               zipfile.ZIP_DEFLATED),
              'Encrypted or unsupported ZIP compression')
        if isdir:
            _need(item.file_size == 0 and item.CRC == 0,
                  'ZIP directory contains file data')
        else:
            _need(0 <= item.file_size <= APK_LIMIT, 'ZIP member exceeds the size bound')
            total += item.file_size
            _need(total <= expansion_limit, 'ZIP expansion exceeds the total bound')
            files[name] = item
    for name in canonical:
        parts = name.split('/')
        for end in range(1, len(parts)):
            _need(canonical.get('/'.join(parts[:end])) is not False,
                  'ZIP file is also a parent directory')
    return files


def load_candidate(path, expected_sha256):
    _need(single._sha(expected_sha256), 'Invalid external candidate SHA-256')
    with _held(path, CANDIDATE_LIMIT) as (stream, pin):
        _need(pin['sha256'] == expected_sha256, 'External candidate SHA-256 differs')
        candidate = _json(stream.read())
    single._fields(candidate, ('schema', 'package', 'version_name', 'version_code',
                              'version_code_major', 'min_sdk_version', 'target_sdk_version',
                              'signer_certificate_sha256', 'container', 'apks', 'source'),
                   'APK-set candidate')
    _need(candidate['schema'] == SCHEMA, 'Unsupported APK-set schema')
    _need(type(candidate['package']) is str and re.fullmatch(
        r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+', candidate['package']),
        'Invalid candidate package')
    _need(type(candidate['version_name']) is str
          and 0 < len(candidate['version_name'].encode()) <= 256,
          'Invalid candidate version name')
    for key, low, high in [('version_code', 1, 0xffffffff),
                           ('version_code_major', 0, 0x7fffffff),
                           ('min_sdk_version', 1, 37), ('target_sdk_version', 1, 1000)]:
        _need(type(candidate[key]) is int and low <= candidate[key] <= high,
              'Invalid candidate ' + key)
    # targetSdkVersion is a compatibility level, not a maximum runtime API.
    # The independently bounded values must still match the signed base manifest.
    certs = candidate['signer_certificate_sha256']
    _need(type(certs) is list and 1 <= len(certs) <= 8 and all(single._sha(c) for c in certs)
          and certs == sorted(set(certs)), 'Invalid candidate signer set')
    container = candidate['container']
    single._fields(container, ('bytes', 'sha256'), 'Container')
    _need(type(container['bytes']) is int and 0 < container['bytes'] <= SET_LIMIT
          and single._sha(container['sha256']), 'Invalid complete container pin')
    apks = candidate['apks']
    _need(type(apks) is list and 2 <= len(apks) <= 64,
          'APK set requires 2 through 64 complete APKs')
    names, splits, total = [], [], 0
    for apk in apks:
        single._fields(apk, ('member', 'split_name', 'bytes', 'sha256', 'native_abis'),
                       'APK-set member')
        _member_name(apk['member'])
        _need(apk['member'].endswith('.apk'), 'APK member must end in .apk')
        split = apk['split_name']
        _need(split is None or _name(split), 'Invalid literal split name')
        _need(type(apk['bytes']) is int and 0 < apk['bytes'] <= APK_LIMIT
              and single._sha(apk['sha256']), 'Invalid APK member byte pin')
        abis = apk['native_abis']
        _need(type(abis) is list and len(abis) <= 8
              and all(type(a) is str and a in single._ABI_ELF for a in abis)
              and abis == sorted(set(abis)), 'Invalid per-APK native ABI set')
        total += apk['bytes']
        names.append(apk['member'])
        splits.append(split)
    _need(total <= SET_LIMIT and len(set(names)) == len(names)
          and len(set(splits)) == len(splits) and splits.count(None) == 1
          and splits == sorted(splits, key=lambda s: '' if s is None else s),
          'APK set is overbound, duplicate, unordered or lacks exactly one base')
    source = candidate['source']
    single._fields(source, ('archive_url', 'version_metadata_url', 'signer_reference_url',
                            'signer_reference_kind', 'distribution', 'observed_utc',
                            'observed_stable_version', 'sha256_kind'), 'APK-set source')
    for key in ('archive_url', 'version_metadata_url', 'signer_reference_url'):
        value = source[key]
        _need(type(value) is str and len(value) <= 2048, 'Invalid source URL')
        url = urlsplit(value)
        _need(url.scheme == 'https' and url.hostname and not url.username
              and not url.password and not url.fragment, 'Source must be a public HTTPS URL')
    _need(source['distribution'] in ('publisher', 'public_mirror')
          and source['signer_reference_kind'] in ('publisher_certificate',
                                                 'public_historical_candidate')
          and source['observed_stable_version'] == candidate['version_name']
          and source['sha256_kind'] == 'observed_whole_file_digest',
          'Source provenance fields differ from their explicit meanings')
    _need(type(source['observed_utc']) is str, 'Source needs a UTC observation')
    observed = datetime.fromisoformat(source['observed_utc'])
    _need(observed.utcoffset() is not None and observed.utcoffset().total_seconds() == 0,
          'Source needs a UTC observation')
    return candidate, pin


def _boolean(value, field):
    _need(value in (None, 'true', 'false'), 'Ambiguous manifest boolean ' + field)
    return value == 'true'


def _types(value):
    if value is None or value == '':
        return []
    _need(type(value) is str and len(value) <= 2048, 'Unbounded split types')
    items = [part.strip() for part in value.split(',')]
    _need(0 < len(items) <= 64 and all(_name(x) for x in items)
          and len(items) == len(set(items)), 'Ambiguous or duplicate split types')
    return sorted(items)


def manifest_observation(manifest):
    root = decode_axml(manifest)
    raw = axml_metadata(manifest)
    a = lambda element, name: element.get('{' + ANDROID + '}' + name)
    _need(len(root.findall('uses-sdk')) <= 1 and len(root.findall('application')) <= 1,
          'Repeated manifest SDK or application')
    uses = root.findall('uses-split')
    _need(len(uses) <= 1, 'Repeated uses-split dependency')
    dependency = a(uses[0], 'name') if uses else None
    _need(dependency is None or _name(dependency), 'Invalid named split dependency')
    config = root.get('configForSplit')
    _need(config is None or _name(config), 'Invalid configForSplit dependency')
    _need(a(root, 'configForSplit') is None, 'Misnamespaced configForSplit is ambiguous')
    required = _boolean(a(root, 'isSplitRequired'), 'isSplitRequired')
    app = root.find('application')
    if app is not None:
        for name in ('debuggable', 'testOnly'):
            _need(not _boolean(a(app, name), name), 'Production candidate is debuggable or test-only')
        markers = [m for m in app.findall('meta-data')
                   if a(m, 'name') == 'com.android.vending.splits.required']
        _need(len(markers) <= 1, 'Repeated store split requirement')
        if markers:
            required = required or _boolean(a(markers[0], 'value'), 'store splits.required')
    raw.pop('xml')
    raw.update(is_feature_split=_boolean(a(root, 'isFeatureSplit'), 'isFeatureSplit'),
               is_split_required=required, isolated_splits=_boolean(a(root, 'isolatedSplits'),
                                                                   'isolatedSplits'),
               uses_split=dependency, config_for_split=config,
               required_split_types=_types(a(root, 'requiredSplitTypes')),
               split_types=_types(a(root, 'splitTypes')))
    return raw


def validate_closure(observations):
    _need(2 <= len(observations) <= 64, 'A complete split set needs base and splits')
    by_name = {}
    for item in observations:
        name = item['split_name']
        _need(name not in by_name, 'Duplicate actual split name')
        by_name[name] = item
    _need(None in by_name, 'Actual set lacks its base')
    base = by_name[None]
    _need(not base['is_feature_split'] and base['uses_split'] is None
          and base['config_for_split'] is None, 'Base cannot be a feature or config dependency')
    parents = {}
    offered = set()
    for name, item in by_name.items():
        offered.update(item['split_types'])
        if name is None:
            continue
        if item['is_feature_split']:
            _need(item['config_for_split'] is None, 'Feature split has a config target')
            target = item['uses_split']
        else:
            _need(item['uses_split'] is None, 'Configuration split declares a feature dependency')
            target = item['config_for_split']
        if target is not None:
            _need(target in by_name and by_name[target]['is_feature_split'],
                  'Missing or non-feature split dependency')
            _need(target != name, 'Self-referencing split dependency')
        parents[name] = target
    for name in parents:
        current, seen = name, set()
        while current is not None:
            _need(current not in seen, 'Cycle in feature split dependencies')
            seen.add(current)
            current = parents[current]
    required = {kind for item in observations for kind in item['required_split_types']}
    _need(required <= offered, 'Complete APK set is missing required split types')
    return {'base_count': 1, 'split_count': len(observations) - 1,
            'required_split_types': sorted(required), 'offered_split_types': sorted(offered),
            'dependencies': [{'split': n, 'target': parents[n]} for n in sorted(parents)],
            'manifest_dependency_closure_verified': True,
            'device_configuration_match_qualified': False}


def _binary_observation(path, result, candidate, pin):
    with zipfile.ZipFile(path) as apk:
        files = safe_members(apk)
        _need('AndroidManifest.xml' in files
              and 0 < files['AndroidManifest.xml'].file_size <= 1024 * 1024,
              'APK binary manifest is absent or exceeds bound')
        manifest = apk.read(files['AndroidManifest.xml'])
        _need(hashlib.sha256(manifest).hexdigest() == result['manifest_binary_sha256'],
              'Manifest changed after signing verification')
        raw = manifest_observation(manifest)
        for key in ('package', 'version_code', 'version_code_major'):
            _need(raw[key] == candidate[key] and result[key] == candidate[key],
                  'APK-set member differs from common ' + key)
        _need(raw['split_name'] == pin['split_name'] == result['split_name'],
              'Binary split identity differs from its external pin')
        if pin['split_name'] is None:
            _need(raw['version_name'] == candidate['version_name']
                  and result['version_name'] == candidate['version_name'],
                  'Base version name differs')
            for key in ('min_sdk_version', 'target_sdk_version'):
                _need(raw[key] is not None and int(raw[key], 0) == candidate[key],
                      'Base binary SDK differs from candidate')
        else:
            _need(raw['version_name'] in (None, candidate['version_name']),
                  'Split declares a different version name')
            _need(result['version_name'] in (None, '', candidate['version_name']),
                  'Tool split version name differs')
            for key in ('min_sdk_version', 'target_sdk_version'):
                value = raw[key]
                if value is not None:
                    number = int(value, 0)
                    _need(1 <= number <= (37 if key == 'min_sdk_version' else 1000),
                          'Split SDK is incompatible or invalid')
        libraries = []
        for name, item in files.items():
            if not name.startswith('lib/'):
                continue
            parts = name.split('/')
            _need(len(parts) == 3 and parts[1] in pin['native_abis']
                  and name.endswith('.so'), 'Undeclared APK-set native payload')
            with apk.open(item) as stream:
                header = stream.read(20)
            cls, machine = single._ABI_ELF[parts[1]]
            _need(len(header) == 20 and header[:4] == b'\x7fELF'
                  and header[4] == cls and header[5:7] == b'\x01\x01'
                  and int.from_bytes(header[16:18], 'little') == 3
                  and int.from_bytes(header[18:20], 'little') == machine,
                  'APK-set payload is not its declared ELF ABI')
            libraries.append({'path': name, 'bytes': item.file_size,
                              'elf_class': cls, 'elf_machine': machine})
        abis = sorted({item['path'].split('/')[1] for item in libraries})
        _need(abis == pin['native_abis'] == result['native_abis'],
              'APK-set native ABI inventory differs')
    return {'manifest': raw, 'native_libraries': libraries,
            'native_code_absence_proved': False, 'native_compatibility_qualified': False}


def _publish(path, body):
    _need(len(body) <= RECEIPT_LIMIT, 'APK-set receipt exceeds consumer bound')
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix='.apk-set-receipt-', dir=path.parent)
        with os.fdopen(fd, 'wb') as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            os.unlink(temporary)


def verify_set(container_path, tools, candidate_path, expected_sha256, receipt_path):
    container_path, candidate_path, receipt_path = map(Path,
        (container_path, candidate_path, receipt_path))
    candidate, candidate_pin = load_candidate(candidate_path, expected_sha256)
    _need(receipt_path.is_absolute() and not os.path.lexists(receipt_path),
          'Receipt output must be an absolute new file')
    results, binaries = [], []
    with _held(container_path, SET_LIMIT, candidate['container']) as (stream, container_pin):
        with zipfile.ZipFile(stream) as archive:
            files = safe_members(archive, count_limit=128)
            _need(set(files) == {a['member'] for a in candidate['apks']},
                  'Complete container APK inventory differs from the candidate')
            with tempfile.TemporaryDirectory(prefix='apk-set-content-') as directory:
                for pin in candidate['apks']:
                    item = files[pin['member']]
                    _need(item.file_size == pin['bytes'], 'Container APK size differs from its pin')
                    name = normalized_name(pin['split_name'])
                    path = Path(directory) / name
                    h, count = hashlib.sha256(), 0
                    with archive.open(item) as source, path.open('xb') as target:
                        for block in iter(lambda: source.read(1024 * 1024), b''):
                            count += len(block)
                            _need(count <= pin['bytes'], 'Extracted APK exceeds pin')
                            h.update(block)
                            target.write(block)
                    _need(count == pin['bytes'] and h.hexdigest() == pin['sha256'],
                          'Extracted APK bytes differ from their external pin')
                    result = single.verify(path, tools, candidate['package'],
                                           candidate['signer_certificate_sha256'])
                    _need(result['bytes'] == count and result['sha256'] == pin['sha256']
                          and result['signer_certificate_sha256'] ==
                              candidate['signer_certificate_sha256']
                          and result['long_version_code'] == (
                              candidate['version_code_major'] << 32) | candidate['version_code'],
                          'Verified SDK identity differs from the complete input')
                    binary = _binary_observation(path, result, candidate, pin)
                    _need(single.digest(path) == pin['sha256'],
                          'Verified APK changed during binary inspection')
                    results.append(result)
                    binaries.append(binary)
                closure = validate_closure([b['manifest'] for b in binaries])
        # Both held-source hash/F9 bookends run before any receipt publication.
    with _held(candidate_path, CANDIDATE_LIMIT) as (_, current_pin):
        _need(current_pin == candidate_pin, 'Candidate changed during APK-set verification')
    receipt = {'schema': 'pocket4-verified-apk-set-source-receipt-v1',
               'verified_utc': datetime.now(timezone.utc).isoformat(),
               'candidate': candidate_pin, 'container': container_pin,
               'source_observation': candidate['source'], 'identities': results,
               'binary_metadata': binaries, 'split_closure': closure,
               'all_container_apks_verified': True, 'exclusive_content_directory_removed': True,
               'native_compatibility_qualified': False, **_NO_CREDIT}
    body = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode()
    _publish(receipt_path, body)
    receipt_pin = {'path': str(receipt_path), 'bytes': len(body),
                   'sha256': hashlib.sha256(body).hexdigest()}
    return {'application': {'package': candidate['package'], 'expected_input': {
        'version_code': (candidate['version_code_major'] << 32) | candidate['version_code'],
        'apks': [{'name': normalized_name(p['split_name']), 'bytes': p['bytes'],
                 'sha256': p['sha256']} for p in candidate['apks']],
        'source_receipt': receipt_pin}}, 'candidate': candidate_pin, **_NO_CREDIT}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('container', type=Path)
    parser.add_argument('--build-tools', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--expect-candidate-sha256', required=True)
    parser.add_argument('--receipt-output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_set(args.container, args.build_tools, args.candidate,
                               args.expect_candidate_sha256, args.receipt_output), indent=2))
