"""V4 source identity for signed standalone APKs with literal publisher payloads.

This is a source gate. All installation, execution, ABI compatibility and
production qualification remain false. Old candidate schemas are unchanged.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata
from urllib.parse import urlsplit
import zipfile

import verify_apk as single
from verify_apk_set import _held, _publish, safe_members, manifest_observation
from native_publisher_payloads import inspect_native_publisher_payload
from seven_zip04_payload import inspect_seven_zip04_single_lzma2
from native_resource_payloads import inspect_interpreter_tagged_et_dyn
from dual_dynamic_elf import parse_dual_dynamic_shared_library


SCHEMA = 'pocket4-official-apk-candidate-v4'
CANDIDATE_LIMIT = 256 * 1024
APK_LIMIT = 1024 * 1024 * 1024
NATIVE_LIMIT = 256 * 1024 * 1024
OBSERVATION_LIMIT = 2 * 1024 * 1024
# runtime_plan::pinned accepts at most 8 MiB for every source receipt.
RECEIPT_LIMIT = 8 * 1024 * 1024
FORMATS = frozenset(('embedded_zip_v1', 'ascii_version_marker_v1',
                     'wechat_csop_zstd_v1', 'wechat_csos_stub_v1',
                     'wechat_cso_offset_table_v1', 'dex035_layout_v1',
                     'meituan_versioned_container_observation_v1',
                     'seven_zip04_single_lzma2_v1',
                     'interpreter_tagged_et_dyn_source_v1',
                     'dual_dynamic_shared_library_source_v1'))
_MIXED_ISA_FORMATS = frozenset(('interpreter_tagged_et_dyn_source_v1',
                              'dual_dynamic_shared_library_source_v1'))
_BASENAME = re.compile(r'lib[A-Za-z0-9_.$+\-]+\.so\Z')
_MTGUARD = {'libmtguard_1.so': ('1.1.4', 28736),
            'libmtguard_2.so': ('1.1.8', 29632),
            'libmtguard_3.so': ('1.1.1', 5216)}
_NO_CREDIT = {'installed': False, 'runtime_qualified': False,
              'production_ready': False, 'native_compatibility_qualified': False,
              'abi_compatibility_verified': False, 'dispatch_runtime_observed': False}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def observation_sha256(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=False, allow_nan=False).encode('utf-8')
    _need(len(raw) <= OBSERVATION_LIMIT, 'Publisher observation exceeds its size bound')
    return _sha(raw)


def _native_path(path, abis):
    _need(type(path) is str and len(path.encode('utf-8')) <= 256,
          'Publisher payload path is invalid')
    parts = path.split('/')
    _need(len(parts) == 3 and parts[0] == 'lib' and parts[1] in abis
          and _BASENAME.fullmatch(parts[2]), 'Publisher payload path is not a literal lib/ABI/name.so')
    return parts[1], parts[2]


def _payload_pins(candidate):
    rows = candidate['publisher_payloads']
    _need(type(rows) is list and 1 <= len(rows) <= 64,
          'V4 needs one through 64 literal publisher payloads')
    paths = []
    for pin in rows:
        single._fields(pin, ('path', 'format', 'bytes', 'sha256', 'observation_sha256'),
                       'Publisher payload pin')
        _, name = _native_path(pin['path'], candidate['native_abis'])
        _need(type(pin['format']) is str and pin['format'] in FORMATS,
              'Unknown publisher payload format')
        _need(type(pin['bytes']) is int and 0 < pin['bytes'] <= 128 * 1024 * 1024
              and single._sha(pin['sha256']) and single._sha(pin['observation_sha256']),
              'Publisher payload pin lacks bounded bytes and hashes')
        if pin['format'] == 'meituan_versioned_container_observation_v1':
            _need(candidate['package'] == 'com.sankuai.meituan.takeoutnew'
                  and name in _MTGUARD and pin['bytes'] == _MTGUARD[name][1],
                  'Versioned container observation is not one of the three explicit Meituan inputs')
        paths.append(pin['path'])
    _need(paths == sorted(set(paths)), 'Publisher payload pins must be unique and sorted')
    return {pin['path']: pin for pin in rows}


def load_candidate(path, expected_sha256):
    _need(single._sha(expected_sha256), 'Invalid external candidate SHA-256')
    with _held(Path(path), CANDIDATE_LIMIT) as (stream, identity):
        _need(identity['sha256'] == expected_sha256, 'External candidate SHA-256 differs')
        raw = stream.read()
    def constant(value):
        raise ValueError('Non-finite candidate JSON value: ' + value)
    candidate = json.loads(raw, object_pairs_hook=single._unique_json, parse_constant=constant)
    single._fields(candidate, ('schema', 'package', 'version_name', 'version_code',
                              'version_code_major', 'min_sdk_version', 'target_sdk_version',
                              'apk', 'native_abis', 'signer_certificate_sha256',
                              'source', 'publisher_payloads'), 'V4 candidate')
    _need(candidate['schema'] == SCHEMA, 'Unsupported publisher candidate schema')
    _need(type(candidate['package']) is str and re.fullmatch(
        r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+', candidate['package']),
        'Invalid candidate package')
    _need(type(candidate['version_name']) is str
          and 1 <= len(candidate['version_name'].encode('utf-8')) <= 256,
          'Invalid candidate version name')
    for key, low, high in [('version_code', 1, 0xffffffff),
                           ('version_code_major', 0, 0x7fffffff),
                           ('min_sdk_version', 1, 37), ('target_sdk_version', 1, 1000)]:
        _need(type(candidate[key]) is int and low <= candidate[key] <= high,
              'Invalid candidate ' + key)
    # targetSdkVersion selects compatibility behavior; it is not maxSdkVersion.
    apk = candidate['apk']
    single._fields(apk, ('name', 'bytes', 'sha256'), 'Candidate APK')
    _need(apk['name'] == 'base.apk' and type(apk['bytes']) is int
          and 0 < apk['bytes'] <= APK_LIMIT and single._sha(apk['sha256']),
          'Candidate must pin one complete bounded base.apk')
    for key, check in [('native_abis', lambda v: type(v) is str and v in single._ABI_ELF),
                       ('signer_certificate_sha256', single._sha)]:
        values = candidate[key]
        _need(type(values) is list and 1 <= len(values) <= 8
              and all(check(v) for v in values) and values == sorted(set(values)),
              'Invalid candidate ' + key)
    _payload_pins(candidate)
    source = candidate['source']
    single._fields(source, ('apk_url', 'version_metadata_url', 'observed_utc',
                            'observed_stable_version', 'sha256_kind', 'distribution',
                            'signer_reference_url', 'signer_reference_kind',
                            'version_metadata_kind'), 'V4 source')
    for key in ('apk_url', 'version_metadata_url', 'signer_reference_url'):
        value = source[key]
        _need(type(value) is str and 0 < len(value) <= 2048, 'Invalid source URL')
        url = urlsplit(value)
        _need(url.scheme == 'https' and url.hostname and not url.username
              and not url.password and not url.fragment, 'Source must be a public HTTPS URL')
    _need(source['distribution'] in ('publisher', 'public_mirror')
          and source['signer_reference_kind'] in ('publisher_certificate', 'public_historical_candidate')
          and source['version_metadata_kind'] == 'signed_apk_android_manifest'
          and source['sha256_kind'] == 'observed_whole_file_digest'
          and source['observed_stable_version'] == candidate['version_name'],
          'Source fields do not have their explicit provenance meanings')
    _need(type(source['observed_utc']) is str, 'Source needs a UTC observation')
    observed = datetime.fromisoformat(source['observed_utc'])
    _need(observed.utcoffset() is not None and observed.utcoffset().total_seconds() == 0,
          'Source needs a UTC observation')
    return candidate, identity


def inspect_mtguard_observation(data, entry_name, package):
    """Observe only three exact versioned envelopes; the body format stays unknown."""
    abi, name = _native_path(entry_name, ('arm64-v8a',))
    _need(package == 'com.sankuai.meituan.takeoutnew' and name in _MTGUARD,
          'Unknown Meituan versioned container name or package')
    version, size = _MTGUARD[name]
    header = version.encode('ascii').ljust(16, b'\0')
    _need(type(data) is bytes and len(data) == size and data[:16] == header
          and (len(data) - 16) % 16 == 0, 'Unknown Meituan versioned container extent or header')
    return {'entry_name': entry_name, 'directory_abi_label': abi,
            'format': 'meituan_versioned_container_observation_v1',
            'bytes': len(data), 'sha256': _sha(data), 'header_bytes': 16,
            'header_hex': header.hex(), 'observed_version_label': version,
            'body_bytes': len(data) - 16, 'body_sha256': _sha(data[16:]),
            'body_block_alignment_bytes': 16, 'body_format_verified': False,
            'decryption_performed': False, 'native_execution_verified': False,
            'abi_compatibility_verified': False, 'inner_code_executed': False}


def inspect_payload(data, entry_name, package, expected_format):
    if expected_format == 'meituan_versioned_container_observation_v1':
        return inspect_mtguard_observation(data, entry_name, package)
    if expected_format == 'seven_zip04_single_lzma2_v1':
        abi, _ = _native_path(entry_name, single._ABI_ELF)
        observed = inspect_seven_zip04_single_lzma2(data)
        return {'entry_name': entry_name, 'directory_abi_label': abi, **observed}
    if expected_format in _MIXED_ISA_FORMATS:
        abi, _ = _native_path(entry_name, single._ABI_ELF)
        # Reuse the unchanged V3 structural checkers. Directory labels never
        # replace their actual ELF class, machine, dynamic tables, or interpreter.
        if expected_format == 'interpreter_tagged_et_dyn_source_v1':
            actual = inspect_interpreter_tagged_et_dyn(data)
        else:
            actual = parse_dual_dynamic_shared_library(data)
        _need((actual['elf_class'], actual['elf_machine']) != single._ABI_ELF[abi],
              'Mixed-ISA source payload actually matches its directory ABI')
        canonical = json.dumps(actual['layout'], sort_keys=True, separators=(',', ':'),
                               ensure_ascii=False, allow_nan=False).encode('utf-8')
        _need(len(canonical) <= OBSERVATION_LIMIT
              and _sha(canonical) == actual['layout_sha256'],
              'Mixed-ISA source model canonical layout differs')
        return {'entry_name': entry_name, 'directory_abi_label': abi,
                'format': expected_format, 'bytes': len(data), 'sha256': _sha(data),
                'actual_elf_class': actual['elf_class'],
                'actual_elf_machine': actual['elf_machine'],
                'source_model': actual, 'crosses_directory_abi': True,
                'counted_as_directory_native_library': False,
                'native_execution_verified': False, 'abi_compatibility_verified': False,
                'inner_code_executed': False, **_NO_CREDIT}
    return inspect_native_publisher_payload(data, entry_name)


def _cso_relationships(candidate, natives, observations):
    related = {path: item for path, item in observations.items()
               if item['format'].startswith('wechat_')}
    if not related:
        return []
    _need(candidate['package'] == 'com.tencent.mm', 'CSO observations require the explicit WeChat package')
    checked = set()
    groups = []
    for abi in candidate['native_abis']:
        prefix = 'lib/' + abi + '/'
        items = {path: item for path, item in related.items() if path.startswith(prefix)}
        if not items:
            continue
        meta_name = prefix + 'libcso.meta.so'
        _need(meta_name in items and items[meta_name]['format'] == 'wechat_cso_offset_table_v1',
              'CSO payloads are missing the exact metadata table')
        meta = items[meta_name]
        covered = {meta_name}
        ordinary_names, pairs = set(), []
        for index, record in enumerate(meta['records']):
            name = prefix + record['strings'][0]
            ordinary_names.add(name)
            _need(name in natives, 'CSO metadata names a missing native-directory entry')
            if record['raw_u32_at_8'] == 0:
                item = natives[name]
                _need(item['kind'] == 'elf_header' and item['bytes'] == record['raw_u64_at_0'],
                      'CSO raw-size relation differs from its ordinary ELF entry')
                continue
            packed_name = name[:-3] + '.$cso.so'
            _need(name in items and packed_name in items
                  and items[name]['format'] == 'wechat_csos_stub_v1'
                  and items[packed_name]['format'] == 'wechat_csop_zstd_v1',
                  'CSO metadata compressed row lacks the exact CSOP/CSOS pair')
            stub, packed = items[name], items[packed_name]
            _need(stub['observed_token_hex'] == packed['observed_token_hex']
                  and stub['abi_label'] == abi
                  and packed['zstd']['declared_content_bytes'] == record['raw_u64_at_0'],
                  'CSO token/ABI/declared-size pairing differs')
            covered.update((name, packed_name))
            pairs.append({'stub': name, 'packed': packed_name, 'metadata_row': index,
                          'observed_token_hex': stub['observed_token_hex'],
                          'declared_content_bytes': record['raw_u64_at_0']})
        all_names = {name for name in natives if name.startswith(prefix)}
        packed_names = {name for name, item in items.items() if item['format'] == 'wechat_csop_zstd_v1'}
        # The observed metadata omits exactly libcso.so itself. Record this
        # concrete ELF separately; no arbitrary unlisted native entries pass.
        non_metadata = prefix + 'libcso.so'
        _need(non_metadata in natives and natives[non_metadata]['kind'] == 'elf_header'
              and non_metadata not in ordinary_names, 'CSO metadata exclusion lacks its exact libcso.so ELF')
        _need(ordinary_names == all_names - packed_names - {meta_name, non_metadata},
              'CSO metadata does not cover the exact observed ordinary native entry set')
        _need(covered == set(items), 'CSO observations contain an unpaired or unaccounted payload')
        checked.update(covered)
        groups.append({'abi_label': abi, 'metadata': meta_name, 'record_count': len(meta['records']),
                       'pairs': pairs, 'observed_byte_relationships_verified': True,
                       'non_metadata_elf_entries': [non_metadata],
                       'field_semantics': 'observed_raw_layout_only',
                       'dependency_resolution_verified': False, 'loader_semantics_verified': False})
    _need(checked == set(related), 'CSO observation set is not exactly paired')
    return groups


def binary_observation(path, identity, candidate):
    pins = _payload_pins(candidate)
    with zipfile.ZipFile(path) as apk:
        files = safe_members(apk, expansion_limit=4 * APK_LIMIT)
        _need('AndroidManifest.xml' in files and 0 < files['AndroidManifest.xml'].file_size <= 1024 * 1024,
              'Manifest is absent or exceeds its bound')
        _need(all(name == unicodedata.normalize('NFC', name) for name in files),
              'APK contains a noncanonical Unicode path')
        manifest = apk.read(files['AndroidManifest.xml'])
        _need(_sha(manifest) == identity['manifest_binary_sha256'],
              'Manifest changed after signing verification')
        raw = manifest_observation(manifest)
        for key in ('package', 'version_name', 'version_code', 'version_code_major'):
            _need(raw[key] == candidate[key], 'Binary manifest differs from candidate ' + key)
        for key in ('min_sdk_version', 'target_sdk_version'):
            _need(raw[key] is not None and int(raw[key], 0) == candidate[key],
                  'Binary manifest differs from candidate ' + key)
        _need(raw['split_name'] is None and raw['uses_split'] is None
              and raw['config_for_split'] is None and not raw['is_feature_split']
              and not raw['is_split_required'] and not raw['isolated_splits']
              and not raw['required_split_types'] and not raw['split_types'],
              'V4 input is not a standalone base APK')
        natives, payloads, libraries, seen = {}, {}, [], set()
        member_count, total = 0, 0
        for name, info in files.items():
            native = name.startswith('lib/')
            if native:
                abi, _ = _native_path(name, candidate['native_abis'])
                _need(0 < info.file_size <= NATIVE_LIMIT, 'Native-directory input exceeds its bound')
            # Stream every outer member to EOF: zipfile verifies each CRC. No extraction.
            h, size, body, head = hashlib.sha256(), 0, [], b''
            pin = pins.get(name)
            if pin is not None:
                _need(info.file_size == pin['bytes'], 'Publisher payload size differs from its literal pin')
            with apk.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    size += len(block)
                    _need(size <= info.file_size, 'ZIP member exceeds its declared size')
                    h.update(block)
                    if len(head) < 64:
                        head += block[:64 - len(head)]
                    if pin is not None:
                        body.append(block)
            _need(size == info.file_size, 'ZIP member size differs from its directory')
            member_count += 1
            total += size
            if not native:
                continue
            digest = h.hexdigest()
            if pin is not None:
                _need(size == pin['bytes'] and digest == pin['sha256'],
                      'Publisher payload differs from its literal size or SHA-256 pin')
                actual = inspect_payload(b''.join(body), name, candidate['package'], pin['format'])
                _need(actual['format'] == pin['format'] and actual['bytes'] == size
                      and actual['sha256'] == digest,
                      'Publisher payload observed identity or format differs from its pin')
                _need(actual['native_execution_verified'] is False
                      and actual['abi_compatibility_verified'] is False,
                      'Publisher payload observation cannot award execution or ABI credit')
                _need(observation_sha256(actual) == pin['observation_sha256'],
                      'Publisher payload canonical observation differs from its external pin')
                seen.add(name)
                payloads[name] = actual
                natives[name] = {'kind': 'publisher_payload', 'bytes': size, 'sha256': digest}
                continue
            elf_class, machine = single._ABI_ELF[abi]
            _need(len(head) >= (64 if elf_class == 2 else 52) and head[:7] == b'\x7fELF' + bytes((elf_class, 1, 1))
                  and int.from_bytes(head[16:18], 'little') == 3
                  and int.from_bytes(head[18:20], 'little') == machine,
                  'Unpinned native payload or ELF header differs from candidate ABI')
            item = {'path': name, 'bytes': size, 'sha256': digest,
                    'kind': 'elf_header', 'elf_class': elf_class, 'elf_machine': machine,
                    'elf_type': 3, 'elf_load_semantics_verified': False}
            libraries.append(item)
            natives[name] = item
        _need(seen == set(pins), 'Publisher payload set is incomplete')
        _need(sorted({item['path'].split('/')[1] for item in libraries}) == candidate['native_abis'],
              'Candidate lacks an actual ELF header in each declared ABI; payload labels are not ABI witnesses')
        relationships = _cso_relationships(candidate, natives, payloads)
    return {'min_sdk_version': candidate['min_sdk_version'],
            'target_sdk_version': candidate['target_sdk_version'],
            'standalone_manifest_verified': True, 'outer_zip_member_count': member_count,
            'outer_zip_expanded_bytes': total, 'outer_zip_all_member_crc_verified': True,
            'native_libraries': sorted(libraries, key=lambda row: row['path']),
            'publisher_payloads': [payloads[name] for name in sorted(payloads)],
            'mixed_isa_source_payloads': [name for name in sorted(payloads)
                                        if payloads[name]['format'] in _MIXED_ISA_FORMATS],
            'cso_observed_relationships': relationships, 'inner_code_executed': False,
            **_NO_CREDIT}


def verify_candidate(path, tools, candidate_path, expected_sha256, receipt_path):
    path, tools = Path(path), Path(tools)
    candidate_path, receipt_path = Path(candidate_path), Path(receipt_path)
    candidate, candidate_pin = load_candidate(candidate_path, expected_sha256)
    _need(receipt_path.is_absolute(), 'Receipt output must be an absolute new file path')
    _need(not os.path.lexists(receipt_path), 'Receipt output already exists')
    with _held(candidate_path, CANDIDATE_LIMIT, candidate_pin) as (_, held_candidate), \
            _held(path, APK_LIMIT, candidate['apk']) as (stream, source_pin):
        _need(held_candidate == candidate_pin, 'Candidate file identity changed after loading')
        with tempfile.TemporaryDirectory(prefix='publisher-APK-content-') as directory:
            target = Path(directory) / 'base.apk'
            with target.open('xb') as output:
                shutil.copyfileobj(stream, output, 1024 * 1024)
            _need(single.digest(target) == candidate['apk']['sha256']
                  and target.stat().st_size == candidate['apk']['bytes'], 'Private APK copy differs from its pin')
            identity = single.verify(target, tools, candidate['package'], candidate['signer_certificate_sha256'])
            _need(identity.get('signature_verified') is True
                  and identity.get('tool_exits') == {'badging': 0, 'manifest': 0, 'signature': 0},
                  'Actual SDK signature or metadata verification failed')
            for key in ('package', 'version_name', 'version_code', 'version_code_major',
                        'native_abis', 'signer_certificate_sha256'):
                _need(identity[key] == candidate[key], 'Verified ' + key + ' differs from candidate')
            for key in ('bytes', 'sha256'):
                _need(identity[key] == candidate['apk'][key], 'Verified ' + key + ' differs from candidate')
            _need(identity['long_version_code'] ==
                  (candidate['version_code_major'] << 32) | candidate['version_code'],
                  'Verified long version code differs from candidate')
            # Standalone status below comes from structural binary AXML. A service
            # class such as com.alibaba.android.split.service.SplitInstallService
            # is not a root split attribute or a uses-split dependency declaration.
            binary = binary_observation(target, identity, candidate)
            _need(single.digest(target) == candidate['apk']['sha256'], 'Private APK changed during inspection')
            identity['filename'] = path.name
        _need(not Path(directory).exists(), 'Private APK copy was not removed')
    receipt = {'schema': 'pocket4-verified-apk-source-receipt-v1',
               'verified_utc': datetime.now(timezone.utc).isoformat(),
               'candidate_schema': SCHEMA, 'candidate': candidate_pin,
               'source_file': source_pin, 'source_observation': candidate['source'],
               'identity': identity, 'binary_metadata': binary,
               'source_identity_verified': True, 'exclusive_content_directory_removed': True,
               **_NO_CREDIT}
    encoded = (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    _need(len(encoded) <= RECEIPT_LIMIT, 'Publisher receipt exceeds its size bound')
    _publish(receipt_path, encoded)
    receipt_pin = {'path': str(receipt_path), 'bytes': len(encoded), 'sha256': _sha(encoded)}
    return {'application': {'package': identity['package'],
                            'expected_input': {'version_code': identity['long_version_code'],
                                               'apks': [candidate['apk']],
                                               'source_receipt': receipt_pin}},
            'candidate': candidate_pin, 'source_identity_verified': True, **_NO_CREDIT}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--build-tools', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--expect-candidate-sha256', required=True)
    parser.add_argument('--receipt-output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_candidate(args.apk, args.build_tools, args.candidate,
                                     args.expect_candidate_sha256, args.receipt_output), indent=2))
