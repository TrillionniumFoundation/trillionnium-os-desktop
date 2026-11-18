"""Verify current Google Play delivery APKs, with explicit local set assembly.

No account access, installation, native execution, or device qualification occurs.
The existing standalone/set schemas and their historical-source meanings are unchanged.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import base64
import hashlib
import json
import os
import re
import stat
import struct
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_apk as single
import verify_apk_set as sets

SET_SCHEMA = 'pocket4-publisher-delivery-apk-set-candidate-v1'
SINGLE_SCHEMA = 'pocket4-publisher-delivery-standalone-candidate-v1'
RECEIPT_SCHEMA = 'pocket4-verified-publisher-delivery-source-receipt-v1'
BUNDLE_LIMIT = 1024 * 1024 * 1024
EVIDENCE_LIMIT = 1024 * 1024
NO_CREDIT = {'installed': False, 'runtime_qualified': False, 'production_ready': False}
ORIGIN_SET = 'local_zip_stored_from_publisher_delivery_members_v1'
ORIGIN_SINGLE = 'original_publisher_delivery_apk'
# An observation of these legacy bytes is not a supported execution ABI.
OBSERVED_ELF = {**single._ABI_ELF, 'armeabi': (1, 40)}
need = sets._need


def fields(value, keys, label):
    single._fields(value, keys, label)


def sha1_value(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{40}', value) is not None


def absolute_file(value):
    return (type(value) is str and 0 < len(value.encode()) <= 4096
            and value.startswith('/') and '\x00' not in value
            and all(p not in ('', '.', '..') for p in value[1:].split('/')))


def pin_fields(value, label, limit, path=True):
    fields(value, ('path', 'bytes', 'sha256') if path else ('bytes', 'sha256'), label)
    need(type(value['bytes']) is int and 0 < value['bytes'] <= limit
         and single._sha(value['sha256']), 'Invalid ' + label + ' bytes/hash')
    if path:
        need(absolute_file(value['path']), 'Invalid ' + label + ' path')


def utc(value):
    need(type(value) is str and len(value) <= 64, 'Invalid observation time')
    try:
        observed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError('Invalid observation time') from error
    need(observed.utcoffset() is not None and observed.utcoffset().total_seconds() == 0,
         'Observation must have an explicit UTC offset')
    return observed


def validate_candidate(candidate):
    fields(candidate, ('schema', 'package', 'version_name', 'version_code',
                       'version_code_major', 'min_sdk_version', 'target_sdk_version',
                       'signer_certificate_sha256', 'selected_abi', 'container',
                       'apks', 'source'), 'Publisher delivery candidate')
    need(candidate['schema'] in (SET_SCHEMA, SINGLE_SCHEMA), 'Unsupported delivery schema')
    need(type(candidate['package']) is str and re.fullmatch(
        r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+', candidate['package']),
        'Invalid package identity')
    need(type(candidate['version_name']) is str
         and 0 < len(candidate['version_name'].encode()) <= 256
         and all(ord(c) >= 32 and ord(c) != 127 for c in candidate['version_name']),
         'Invalid version name')
    for name, low, high in [('version_code', 1, 0xffffffff),
                            ('version_code_major', 0, 0x7fffffff),
                            ('min_sdk_version', 1, 37), ('target_sdk_version', 1, 1000)]:
        need(type(candidate[name]) is int and low <= candidate[name] <= high,
             'Invalid ' + name)
    certs = candidate['signer_certificate_sha256']
    need(type(certs) is list and 1 <= len(certs) <= 8
         and all(single._sha(c) for c in certs) and certs == sorted(set(certs)),
         'Invalid external signer set')
    need(candidate['selected_abi'] == 'arm64-v8a', 'This gate selects only ARM64 input')
    is_set = candidate['schema'] == SET_SCHEMA
    if is_set:
        pin_fields(candidate['container'], 'locally assembled container', BUNDLE_LIMIT, False)
    else:
        need(candidate['container'] is None, 'Standalone cannot claim a set container')
    apks = candidate['apks']
    need(type(apks) is list and ((2 <= len(apks) <= 64) if is_set else len(apks) == 1),
         'Wrong complete delivery member count')
    names, splits, paths, total = [], [], [], 0
    observed_abis = set()
    for apk in apks:
        fields(apk, ('member', 'split_name', 'bytes', 'sha256', 'sha1',
                     'native_abis', 'delivery_path'), 'Publisher delivery member')
        split = apk['split_name']
        need(split is None or sets._name(split), 'Invalid literal split name')
        need(apk['member'] == sets.normalized_name(split), 'Noncanonical local member name')
        need(type(apk['bytes']) is int and 0 < apk['bytes'] <= sets.APK_LIMIT
             and single._sha(apk['sha256']) and sha1_value(apk['sha1']),
             'Invalid delivery member digest')
        need(absolute_file(apk['delivery_path']), 'Invalid original delivery path')
        abis = apk['native_abis']
        need(type(abis) is list and len(abis) <= 8
             and all(type(a) is str and a in OBSERVED_ELF for a in abis)
             and abis == sorted(set(abis)), 'Invalid observed native ABI set')
        # The old set ELF model remains unmodified. Legacy observation is standalone only.
        need(not is_set or 'armeabi' not in abis, 'Legacy ABI observation is standalone only')
        observed_abis.update(abis)
        total += apk['bytes']
        names.append(apk['member'])
        splits.append(split)
        paths.append(apk['delivery_path'])
    need(total <= BUNDLE_LIMIT and len(set(names)) == len(names)
         and len(set(splits)) == len(splits) and len(set(paths)) == len(paths)
         and splits.count(None) == 1
         and splits == sorted(splits, key=lambda s: '' if s is None else s),
         'Delivery is oversized, duplicate, unordered, or missing its base')
    need('arm64-v8a' in observed_abis, 'Selected ARM64 payload is absent')
    source = candidate['source']
    fields(source, ('distribution', 'signer_reference_kind', 'container_origin',
                    'publisher_archive_obtained', 'observed_utc',
                    'metadata', 'delivery', 'transaction'), 'Delivery source')
    need(source['distribution'] == 'google_play_publisher_delivery'
         and source['signer_reference_kind'] == 'current_get_items_certificate_set'
         and source['publisher_archive_obtained'] is False
         and source['container_origin'] == (ORIGIN_SET if is_set else ORIGIN_SINGLE),
         'Source provenance does not describe the actual delivery/local assembly')
    utc(source['observed_utc'])
    paths = []
    for key in ('metadata', 'delivery', 'transaction'):
        pin_fields(source[key], key, EVIDENCE_LIMIT)
        paths.append(source[key]['path'])
    need(len(set(paths)) == 3, 'Source evidence files alias')
    return candidate


def certificate_digest(value, size):
    need(type(value) is str and len(value) == (43 if size == 32 else 27)
         and re.fullmatch('[A-Za-z0-9_-]+', value), 'Invalid external certificate encoding')
    body = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    need(len(body) == size and base64.urlsafe_b64encode(body).decode().rstrip('=') == value,
         'Noncanonical external certificate encoding')
    return body.hex()


def validate_source(candidate, metadata, delivery, transaction):
    fields(metadata, ('package', 'version_name', 'version_code', 'source',
                      'restriction', 'restriction_code', 'is_free', 'offer_type',
                      'certificate_sets', 'certificate_sha1_base64url'), 'GET_ITEMS metadata')
    long_version = (candidate['version_code_major'] << 32) | candidate['version_code']
    need(metadata['package'] == candidate['package']
         and metadata['version_name'] == candidate['version_name']
         and type(metadata['version_code']) is int and metadata['version_code'] == long_version,
         'External metadata package/version differs')
    need(metadata['source'] == 'GET_ITEMS' and metadata['restriction'] == 'AVAILABLE'
         and type(metadata['restriction_code']) is int and metadata['restriction_code'] == 1
         and metadata['is_free'] is True
         and type(metadata['offer_type']) is int and metadata['offer_type'] == 1,
         'External metadata does not authorize the observed free delivery')
    cert_sets = metadata['certificate_sets']
    need(type(cert_sets) is list and 1 <= len(cert_sets) <= 8, 'Missing external certificates')
    certs, cert_sha1 = [], []
    for item in cert_sets:
        fields(item, ('sha1_base64url', 'sha256_base64url'), 'External certificate')
        certs.append(certificate_digest(item['sha256_base64url'], 32))
        cert_sha1.append(certificate_digest(item['sha1_base64url'], 20))
    need(len(certs) == len(set(certs))
         and sorted(certs) == candidate['signer_certificate_sha256'],
         'External metadata signer differs from candidate')
    legacy = metadata['certificate_sha1_base64url']
    need(type(legacy) is list and len(legacy) <= 8, 'Invalid auxiliary certificate digests')
    for item in legacy:
        certificate_digest(item, 20)
    fields(delivery, ('package', 'status', 'version_name', 'version_code',
                      'official_signer_certificate_sha256', 'files',
                      'installed', 'runtime_qualified', 'production_ready'), 'Delivery record')
    need(delivery['package'] == candidate['package']
         and delivery['version_name'] == candidate['version_name']
         and type(delivery['version_code']) is int and delivery['version_code'] == long_version
         and delivery['official_signer_certificate_sha256'] == sorted(certs)
         and delivery['status'] == 'transport_complete_requires_apk_gate'
         and all(delivery[k] is False for k in NO_CREDIT),
         'Delivery identity or claim differs')
    files = delivery['files']
    need(type(files) is list and len(files) == len(candidate['apks']),
         'Complete original delivery inventory differs')
    by_path = {}
    for item in files:
        fields(item, ('path', 'role', 'bytes', 'sha256', 'sha1', 'delivery_sha256',
                      'delivery_sha1', 'source_host', 'redirect_count'), 'Delivery file')
        need(absolute_file(item['path']) and item['path'] not in by_path,
             'Duplicate or invalid original delivery path')
        need(item['role'] in ('BASE', 'SPLIT') and type(item['bytes']) is int
             and 0 < item['bytes'] <= sets.APK_LIMIT
             and single._sha(item['sha256']) and sha1_value(item['sha1'])
             and item['delivery_sha256'] == item['sha256']
             and item['delivery_sha1'] == item['sha1'],
             'Publisher delivery digest is absent or differs')
        need(type(item['source_host']) is str and len(item['source_host']) <= 253
             and re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.gvt1\.com', item['source_host'])
             and type(item['redirect_count']) is int and 0 <= item['redirect_count'] <= 4,
             'Unexpected recorded delivery host/redirect bound')
        by_path[item['path']] = item
    need(set(by_path) == {x['delivery_path'] for x in candidate['apks']},
         'Candidate omits or adds original delivery members')
    for pin in candidate['apks']:
        item = by_path[pin['delivery_path']]
        need(all(item[k] == pin[k] for k in ('bytes', 'sha256', 'sha1'))
             and item['role'] == ('BASE' if pin['split_name'] is None else 'SPLIT'),
             'Candidate member differs from original publisher delivery')
    fields(transaction, ('schema', 'finished_utc', 'results', 'transport', 'auth_requests',
                         'purchase_requests', 'android_starts', 'installed_apps',
                         'production_ready'), 'Original transaction')
    need(transaction['schema'] == 'pocket4-aurora-official-client-result-v1'
         and transaction['finished_utc'] == candidate['source']['observed_utc']
         and transaction['production_ready'] is False
         and all(type(transaction[k]) is int and transaction[k] == 0
                 for k in ('auth_requests', 'purchase_requests', 'android_starts', 'installed_apps')),
         'Original transaction has incompatible identity/claims')
    utc(transaction['finished_utc'])
    transport = transaction['transport']
    need(type(transport) is dict and transport.get('stopped', 'absent') is None,
         'Original transaction stopped at a provider boundary')
    results = transaction['results']
    need(type(results) is list and 1 <= len(results) <= 64
         and all(type(x) is dict and type(x.get('package')) is str for x in results),
         'Invalid transaction result inventory')
    packages = [x['package'] for x in results]
    need(len(set(packages)) == len(packages), 'Duplicate transaction packages')
    matches = [x for x in results if x['package'] == candidate['package']]
    need(matches == [delivery], 'Original transaction and per-package record differ')
    return {'metadata_origin': 'original_current_GET_ITEMS',
            'metadata_certificate_sha256': sorted(certs),
            'metadata_certificate_sha1_observed_not_independently_verified': sorted(cert_sha1),
            'original_delivery_members': len(files),
            'publisher_delivery_sha256_and_sha1_required': True,
            'authenticated_transport_replayed': False,
            'source_evidence_external_sha256_pinned': True}


def stream_hash1(stream):
    stream.seek(0)
    h = hashlib.sha1()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(block)
    stream.seek(0)
    return h.hexdigest()


def copy_member(source, target, pin):
    h, h1, count = hashlib.sha256(), hashlib.sha1(), 0
    with target.open('xb') as output:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            count += len(block)
            need(count <= pin['bytes'], 'Extracted member exceeds its publisher pin')
            h.update(block)
            h1.update(block)
            output.write(block)
    need(count == pin['bytes'] and h.hexdigest() == pin['sha256']
         and h1.hexdigest() == pin['sha1'], 'Extracted member differs from publisher delivery')


def assemble_local_set(apks, destination):
    """Create a local transport container; it is not a publisher archive."""
    destination = Path(destination)
    need(destination.is_absolute() and not os.path.lexists(destination),
         'Local container must be a new absolute file')
    with ExitStack() as held:
        inputs = []
        for pin in apks:
            stream, _ = held.enter_context(sets._held(pin['delivery_path'], sets.APK_LIMIT, pin))
            need(stream_hash1(stream) == pin['sha1'], 'Original delivery SHA-1 differs')
            inputs.append(stream)
        with destination.open('xb') as raw:
            with zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_STORED) as archive:
                for pin, stream in zip(apks, inputs):
                    item = zipfile.ZipInfo(pin['member'], (1980, 1, 1, 0, 0, 0))
                    item.compress_type = zipfile.ZIP_STORED
                    item.create_system = 3
                    item.external_attr = (stat.S_IFREG | 0o600) << 16
                    stream.seek(0)
                    with archive.open(item, 'w', force_zip64=True) as output:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            output.write(block)
            raw.flush()
            os.fsync(raw.fileno())
    return {'bytes': destination.stat().st_size, 'sha256': single.digest(destination)}


def local_container_files(stream, archive, candidate):
    """Check the exact locally assembled ZIP_STORED envelope, including local headers."""
    files = sets.safe_members(archive, count_limit=64, expansion_limit=BUNDLE_LIMIT)
    expected_names = [p['member'] for p in candidate['apks']]
    items = archive.infolist()
    need(archive.comment == b'' and [x.filename for x in items] == expected_names
         and list(files) == expected_names, 'Local container complete inventory/order differs')
    offset = 0
    for item, pin in zip(items, candidate['apks']):
        name = item.filename.encode('ascii')
        need(item.file_size == pin['bytes'] and item.compress_size == pin['bytes']
             and item.compress_type == zipfile.ZIP_STORED and item.flag_bits == 0
             and item.date_time == (1980, 1, 1, 0, 0, 0) and item.create_system == 3
             and item.external_attr == (stat.S_IFREG | 0o600) << 16
             and item.create_version == 45 and item.extract_version == 45
             and item.internal_attr == 0 and item.volume == 0
             and item.extra == b'' and item.comment == b'' and item.header_offset == offset,
             'Local container member is not the declared deterministic assembly')
        stream.seek(offset)
        raw = stream.read(30)
        need(len(raw) == 30, 'Truncated local ZIP header')
        header = struct.unpack('<4s5H3I2H', raw)
        need(header == (b'PK\x03\x04', 45, 0, 0, 0, 33, item.CRC,
                        0xffffffff, 0xffffffff, len(name), 20),
             'Local ZIP header differs from the exact assembly')
        need(stream.read(len(name)) == name
             and stream.read(20) == struct.pack('<HHQQ', 1, 16, pin['bytes'], pin['bytes']),
             'Local ZIP name or ZIP64 sizes differ')
        offset += 30 + len(name) + 20 + pin['bytes']
    need(archive.start_dir == offset, 'Local container has an undeclared gap or prefix')
    central_size = sum(46 + len(x.filename.encode('ascii')) for x in items)
    stream.seek(offset + central_size)
    end = stream.read()
    need(end == struct.pack('<4s4H2IH', b'PK\x05\x06', 0, 0, len(items), len(items),
                            central_size, offset, 0),
         'Local container central-directory boundary or trailer differs')
    return files


def full_zip_integrity(path):
    """Bounded complete decompression/CRC; retain exact hashes for every native member."""
    aggregate = hashlib.sha256()
    natives, total, count = [], 0, 0
    with zipfile.ZipFile(path) as archive:
        files = sets.safe_members(archive)
        for name, item in sorted(files.items()):
            h, size = hashlib.sha256(), 0
            with archive.open(item) as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    size += len(block)
                    total += len(block)
                    need(size <= item.file_size and total <= sets.SET_LIMIT,
                         'APK actual expansion exceeds its declared bound')
                    h.update(block)
            need(size == item.file_size, 'APK member is truncated')
            record = {'path': name, 'bytes': size, 'crc32': item.CRC, 'sha256': h.hexdigest()}
            aggregate.update((json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n').encode())
            if name.startswith('lib/'):
                natives.append(record)
            count += 1
    return {'all_member_crc_verified': True, 'file_count': count,
            'expanded_bytes': total, 'sorted_member_identity_sha256': aggregate.hexdigest(),
            'native_members': natives}


def standalone_binary(path, result, candidate, pin):
    """Exact standalone metadata plus bounded native observations, including legacy ARM."""
    with zipfile.ZipFile(path) as archive:
        files = sets.safe_members(archive)
        need('AndroidManifest.xml' in files
             and 0 < files['AndroidManifest.xml'].file_size <= 1024 * 1024,
             'Standalone manifest is absent or exceeds bound')
        manifest = archive.read(files['AndroidManifest.xml'])
        need(hashlib.sha256(manifest).hexdigest() == result['manifest_binary_sha256'],
             'Standalone manifest changed after signature verification')
        raw = sets.manifest_observation(manifest)
        for key in ('package', 'version_name', 'version_code', 'version_code_major'):
            need(raw[key] == candidate[key] and result[key] == candidate[key],
                 'Standalone signed/tool identity differs: ' + key)
        for key in ('min_sdk_version', 'target_sdk_version'):
            need(raw[key] is not None and int(raw[key], 0) == candidate[key],
                 'Standalone signed SDK differs')
        need(raw['split_name'] is None and result['split_name'] is None
             and not raw['is_feature_split'] and not raw['is_split_required']
             and not raw['isolated_splits'] and raw['uses_split'] is None
             and raw['config_for_split'] is None and not raw['required_split_types']
             and not raw['split_types'], 'Standalone has a split dependency or split identity')
        libraries = []
        for name, item in sorted(files.items()):
            if not name.startswith('lib/'):
                continue
            parts = name.split('/')
            need(len(parts) == 3 and parts[1] in pin['native_abis'] and name.endswith('.so'),
                 'Undeclared standalone native payload')
            cls, machine = OBSERVED_ELF[parts[1]]
            with archive.open(item) as source:
                header = source.read(64)
            minimum = 52 if cls == 1 else 64
            need(len(header) >= minimum and header[:4] == b'\x7fELF'
                 and header[4] == cls and header[5:7] == b'\x01\x01'
                 and int.from_bytes(header[16:18], 'little') == 3
                 and int.from_bytes(header[18:20], 'little') == machine,
                 'Standalone ELF class/machine/type differs from observed ABI')
            libraries.append({'path': name, 'bytes': item.file_size,
                              'elf_class': cls, 'elf_machine': machine,
                              'legacy_armeabi_observation_only': parts[1] == 'armeabi',
                              'selected_for_input': parts[1] == candidate['selected_abi']})
        actual = sorted({x['path'].split('/')[1] for x in libraries})
        need(actual == pin['native_abis'] == result['native_abis'],
             'Standalone native ABI inventory differs')
        need(any(x['selected_for_input'] for x in libraries), 'Actual ARM64 payload is absent')
    return {'manifest': raw, 'native_libraries': libraries,
            'native_code_absence_proved': False, 'native_compatibility_qualified': False,
            'legacy_armeabi_execution_supported': False}


def verify_delivery(input_path, tools, candidate_path, expected_sha256, receipt_path):
    input_path, candidate_path, receipt_path = map(Path, (input_path, candidate_path, receipt_path))
    need(single._sha(expected_sha256), 'Invalid external candidate SHA-256')
    need(receipt_path.is_absolute() and not os.path.lexists(receipt_path),
         'Receipt output must be a new absolute file')
    identities, binaries, integrity, original_pins = [], [], [], []
    container_pin = None
    with ExitStack() as held:
        candidate_stream, candidate_pin = held.enter_context(
            sets._held(candidate_path, sets.CANDIDATE_LIMIT))
        need(candidate_pin['sha256'] == expected_sha256, 'External candidate SHA-256 differs')
        candidate = validate_candidate(sets._json(candidate_stream.read()))
        evidence, evidence_pins = {}, {}
        for key in ('metadata', 'delivery', 'transaction'):
            wanted = candidate['source'][key]
            stream, pin = held.enter_context(sets._held(wanted['path'], EVIDENCE_LIMIT, wanted))
            evidence[key], evidence_pins[key] = sets._json(stream.read()), pin
        source_check = validate_source(candidate, **evidence)
        streams = []
        for pin in candidate['apks']:
            stream, original_pin = held.enter_context(
                sets._held(pin['delivery_path'], sets.APK_LIMIT, pin))
            need(stream_hash1(stream) == pin['sha1'], 'Actual original delivery SHA-1 differs')
            original_pins.append({**original_pin, 'sha1': pin['sha1']})
            streams.append(stream)
        is_set = candidate['schema'] == SET_SCHEMA
        with tempfile.TemporaryDirectory(prefix='publisher-delivery-verified-') as directory:
            directory = Path(directory)
            if is_set:
                stream, container_pin = held.enter_context(
                    sets._held(input_path, BUNDLE_LIMIT, candidate['container']))
                with zipfile.ZipFile(stream) as archive:
                    files = local_container_files(stream, archive, candidate)
                    for pin in candidate['apks']:
                        with archive.open(files[pin['member']]) as source:
                            copy_member(source, directory / pin['member'], pin)
            else:
                need(str(input_path) == candidate['apks'][0]['delivery_path'],
                     'Standalone input is not the original delivery path')
                streams[0].seek(0)
                copy_member(streams[0], directory / 'base.apk', candidate['apks'][0])
            for pin in candidate['apks']:
                path = directory / pin['member']
                result = single.verify(path, tools, candidate['package'],
                                       candidate['signer_certificate_sha256'])
                need(result['bytes'] == pin['bytes'] and result['sha256'] == pin['sha256']
                     and result['signer_certificate_sha256'] == candidate['signer_certificate_sha256']
                     and result['signature_verified'] is True and not any(result['tool_exits'].values())
                     and result['long_version_code'] ==
                         ((candidate['version_code_major'] << 32) | candidate['version_code']),
                     'Verified SDK identity differs from publisher delivery')
                binary = (sets._binary_observation(path, result, candidate, pin) if is_set else
                          standalone_binary(path, result, candidate, pin))
                complete = full_zip_integrity(path)
                need({x['path'] for x in complete['native_members']} ==
                     {x['path'] for x in binary['native_libraries']},
                     'Full native member hashes differ from the structural inventory')
                need(single.digest(path) == pin['sha256'], 'Verified APK changed during inspection')
                identities.append(result)
                binaries.append(binary)
                integrity.append(complete)
            closure = (sets.validate_closure([b['manifest'] for b in binaries]) if is_set else {
                'base_count': 1, 'split_count': 0, 'standalone_dependency_absence_verified': True,
                'manifest_dependency_closure_verified': True,
                'device_configuration_match_qualified': False})
            arm64 = [{'member': p['member'], **n} for p, c in zip(candidate['apks'], integrity)
                     for n in c['native_members'] if n['path'].startswith('lib/arm64-v8a/')]
            need(arm64, 'Actual selected ARM64 library inventory is empty')
        # Every original candidate/evidence/APK/container hash and inode bookend finishes here.
    receipt = {'schema': RECEIPT_SCHEMA, 'verified_utc': datetime.now(timezone.utc).isoformat(),
               'candidate': candidate_pin, 'source_observation': candidate['source'],
               'original_evidence': evidence_pins, 'source_validation': source_check,
               'original_delivery_apks': original_pins,
               'local_container': container_pin, 'publisher_archive_obtained': False,
               'all_original_delivery_apks_verified': True,
               'identities': identities, 'binary_metadata': binaries,
               'complete_zip_integrity': integrity, 'split_closure': closure,
               'selected_abi': 'arm64-v8a', 'selected_abi_native_members': arm64,
               'legacy_armeabi_execution_supported': False,
               'device_profile_match_qualified': False,
               'native_compatibility_qualified': False,
               'exclusive_content_directory_removed': True, **NO_CREDIT}
    body = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode()
    sets._publish(receipt_path, body)
    receipt_pin = {'path': str(receipt_path), 'bytes': len(body),
                   'sha256': hashlib.sha256(body).hexdigest()}
    return {'application': {'package': candidate['package'], 'expected_input': {
        'version_code': (candidate['version_code_major'] << 32) | candidate['version_code'],
        'apks': [{'name': p['member'], 'bytes': p['bytes'], 'sha256': p['sha256']}
                 for p in candidate['apks']], 'source_receipt': receipt_pin}},
        'candidate': candidate_pin, **NO_CREDIT}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--build-tools', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--expect-candidate-sha256', required=True)
    parser.add_argument('--receipt-output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_delivery(args.input, args.build_tools, args.candidate,
                                    args.expect_candidate_sha256, args.receipt_output), indent=2))
