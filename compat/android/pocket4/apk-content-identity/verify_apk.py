"""Content-bound, SDK-37 APK identity verification. No installation or account access."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from urllib.parse import urlsplit
from axml_metadata import metadata as axml_metadata, signing_block_certificates, verified_scheme_certificates


def verify(path, tools, expected_package=None, expected_certificate_sha256=None):
    result = inspect_apk(Path(path), Path(tools))
    if expected_package is not None and result['package'] != expected_package:
        raise ValueError('APK package differs from expected identity')
    if expected_certificate_sha256 is not None and result['signer_certificate_sha256'] != sorted(expected_certificate_sha256):
        raise ValueError('APK signer differs from expected identity')
    if not result['signature_verified'] or any(result['tool_exits'].values()):
        raise ValueError('APK parsing or signature verification failed')
    return result

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(2 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def application_signer_certificates(output):
    # Distribution Source Stamp certificates are separate from the app signing identity.
    return sorted(set(re.findall(r"^(?:Signer #\d+|V[\d.]+ Signer:) certificate SHA-256 digest: ([a-fA-F0-9]{64})$", output, re.M)))

def inspect_apk(path, tools):
    original_digest = digest(path)
    original_size = path.stat().st_size
    with tempfile.TemporaryDirectory(prefix="official-APK-content-") as temporary:
        target = Path(temporary) / (original_digest + ".apk")
        shutil.copyfile(path, target)
        if digest(target) != original_digest:
            raise ValueError("Candidate copy differs from original APK")
        result = inspect_apk_content(target, tools)
    if digest(path) != original_digest or path.stat().st_size != original_size:
        raise ValueError("Original candidate changed during inspection")
    result["filename"] = path.name
    result["exclusive_content_directory_removed"] = not Path(temporary).exists()
    return result

def inspect_apk_content(path, tools):
    original_digest = digest(path)
    with zipfile.ZipFile(path) as apk:
        manifest_bytes = apk.read("AndroidManifest.xml")
    raw = axml_metadata(manifest_bytes)
    signing_block = signing_block_certificates(path)
    commands = {
        "badging": [str(tools / "aapt2"), "dump", "badging", str(path)],
        "manifest": [str(tools / "aapt2"), "dump", "xmltree", str(path), "--file", "AndroidManifest.xml"],
        "signature": ["java", "-XX:ActiveProcessorCount=1", "-Xmx192m", "-jar", str(tools / "lib/apksigner.jar"), "verify", "--min-sdk-version", "37", "--max-sdk-version", "37", "--verbose", "--print-certs", str(path)],
    }
    output, exits = {}, {}
    for key, argv in commands.items():
        run = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        output[key], exits[key] = run.stdout + run.stderr, run.returncode
    attrs = dict(re.findall(r"(\w+)='([^']*)'", next((l for l in output["badging"].splitlines() if l.startswith("package:")), "")))
    code = int(attrs["versionCode"]) if attrs.get("versionCode", "").isdigit() else None
    major = int(attrs.get("versionCodeMajor", "0"))
    certs = application_signer_certificates(output["signature"])
    manifest_package = re.search(r'\bA: package="([^"]+)"', output["manifest"])
    if attrs.get("name") != raw["package"] or not manifest_package or manifest_package.group(1) != raw["package"]:
        raise ValueError("Tool metadata is not bound to actual APK binary Manifest package")
    if code != raw["version_code"] or major != raw["version_code_major"] or (attrs.get("split") or None) != raw["split_name"]:
        raise ValueError("Tool version or split identity differs from actual APK binary Manifest")
    selected_signing_scheme = verified_scheme_certificates(output["signature"], signing_block)
    if not certs or certs != selected_signing_scheme["certificate_sha256"]:
        raise ValueError("Tool signer identity differs from actual APK public signing block")
    if digest(path) != original_digest:
        raise ValueError("APK bytes changed during metadata inspection")
    requires, config_for, in_uses_split = [], None, False
    for line in output["manifest"].splitlines():
        if re.match(r"\s*E: ", line):
            in_uses_split = bool(re.match(r"\s*E: uses-split\b", line))
        if in_uses_split and re.search(r"android:name\(", line):
            match = re.search(r'=\"([^\"]+)\"', line)
            if match:
                requires.append(match.group(1))
        if re.search(r"configForSplit(?:\(|=)", line):
            match = re.search(r'=\"([^\"]+)\"', line)
            if match:
                config_for = match.group(1)
    with zipfile.ZipFile(path) as apk:
        native_abis = sorted({n.split("/")[1] for n in apk.namelist() if n.startswith("lib/") and n.count("/") >= 2 and n.endswith(".so")})
    return {
        "filename": path.name, "bytes": path.stat().st_size, "sha256": digest(path),
        "package": attrs.get("name"), "version_name": attrs.get("versionName"),
        "version_code": code, "version_code_major": major,
        "long_version_code": (major << 32) | code if code is not None else None,
        "split_name": attrs.get("split") or None, "uses_splits": requires,
        "config_for_split": config_for, "native_abis": native_abis,
        "signer_certificate_sha256": certs,
        "source_stamp_certificate_sha256": re.findall(r"^Source Stamp Signer certificate SHA-256 digest: ([a-fA-F0-9]{64})$", output["signature"], re.M),
        "public_signing_block": signing_block,
        "selected_verified_signing_scheme": selected_signing_scheme,
        "verification_SDK_range": [37, 37],
        "manifest_binary_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "metadata_outputs_bound_to_apk_sha256": original_digest,
        "tool_identities": {str(p): {"sha256": digest(p), "bytes": p.stat().st_size}
                            for p in [tools / "aapt2", tools / "lib/apksigner.jar", Path(shutil.which("java")).resolve()]},
        "signature_verified": exits["signature"] == 0 and "Verifies" in output["signature"],
        "tool_exits": exits,
        "tool_output_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in output.items()},
        "manifest_split_fields": [l.strip() for l in output["manifest"].splitlines() if re.search(r"\b(?:split|uses-split|isSplitRequired|splitTypes|requiredSplitTypes|configForSplit)\b", l)],
        "executed": False,
    }


_CANDIDATE_SCHEMA = 'pocket4-official-apk-candidate-v1'
_CROSS_ARCH_SCHEMA = 'pocket4-official-apk-candidate-v2'
_CANDIDATE_LIMIT = 16 * 1024
_SHARED_LIBRARY_LIMIT = 16 * 1024 * 1024
_ABI_ELF = {'armeabi-v7a': (1, 40), 'arm64-v8a': (2, 183),
            'x86': (1, 3), 'x86_64': (2, 62), 'riscv64': (2, 243)}


def _fields(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(label + ' fields differ from the candidate schema')


def _sha(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate candidate JSON key: ' + key)
        result[key] = value
    return result


def _cross_arch_pins(candidate):
    """A literal reviewed layout, never a filename pattern or loading permission."""
    values = candidate['cross_arch_shared_libraries']
    if type(values) is not list or len(values) != 4:
        raise ValueError('Candidate v2 requires exactly four cross-architecture shared libraries')
    paths = []
    for item in values:
        _fields(item, ('path', 'kind', 'bytes', 'sha256', 'elf_class', 'elf_machine',
                       'elf_type', 'soname', 'entry_point', 'has_interpreter'), 'Cross-architecture library')
        path = item['path']
        if type(path) is not str or len(path.encode('utf-8')) > 256:
            raise ValueError('Invalid cross-architecture library path')
        parts = path.split('/')
        if (len(parts) != 3 or parts[0] != 'lib' or parts[1] not in candidate['native_abis']
                or not re.fullmatch(r'lib[A-Za-z0-9_.+-]+\.so', parts[2])):
            raise ValueError('Cross-architecture library requires a literal native-library path')
        if item['kind'] != 'cross_arch_shared_library' or type(item['elf_type']) is not int or item['elf_type'] != 3:
            raise ValueError('Cross-architecture payload must be an ET_DYN shared library')
        if (type(item['bytes']) is not int or not 52 <= item['bytes'] <= _SHARED_LIBRARY_LIMIT
                or not _sha(item['sha256'])):
            raise ValueError('Cross-architecture library requires bounded bytes and SHA-256')
        if (type(item['elf_class']) is not int or type(item['elf_machine']) is not int
                or (item['elf_class'], item['elf_machine']) not in _ABI_ELF.values()
                or (item['elf_class'], item['elf_machine']) == _ABI_ELF[parts[1]]):
            raise ValueError('Cross-architecture library must declare its actual different ELF architecture')
        if (type(item['entry_point']) is not int
                or not 0 <= item['entry_point'] < 1 << (32 if item['elf_class'] == 1 else 64)
                or item['has_interpreter'] is not False):
            raise ValueError('Cross-architecture shared library requires a bounded entry and no PT_INTERP')
        if (type(item['soname']) is not str or len(item['soname']) > 128
                or not re.fullmatch(r'lib[A-Za-z0-9_.+-]+\.so', item['soname'])):
            raise ValueError('Cross-architecture shared library requires an exact SONAME')
        paths.append(path)
    if paths != sorted(set(paths)):
        raise ValueError('Cross-architecture library paths must be distinct and sorted')
    return {item['path']: item for item in values}


def load_candidate(path, expected_sha256):
    """Read an independently pinned observation, without fetching its URLs."""
    if not _sha(expected_sha256):
        raise ValueError('An external lowercase candidate SHA-256 is required')
    with path.open('rb') as stream:
        raw = stream.read(_CANDIDATE_LIMIT + 1)
    if len(raw) > _CANDIDATE_LIMIT or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Candidate size or external SHA-256 pin differs')
    def reject_constant(value):
        raise ValueError('Non-finite candidate JSON number: ' + value)
    candidate = json.loads(raw, object_pairs_hook=_unique_json, parse_constant=reject_constant)
    if type(candidate) is not dict or candidate.get('schema') not in (_CANDIDATE_SCHEMA, _CROSS_ARCH_SCHEMA):
        raise ValueError('Unsupported candidate schema')
    cross_arch = candidate['schema'] == _CROSS_ARCH_SCHEMA
    fields = ('schema', 'package', 'version_name', 'version_code', 'version_code_major',
              'min_sdk_version', 'target_sdk_version', 'apk', 'native_abis',
              'signer_certificate_sha256', 'source')
    _fields(candidate, fields + (('cross_arch_shared_libraries',) if cross_arch else ()), 'Candidate')
    if type(candidate['package']) is not str or not re.fullmatch(
            r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+', candidate['package']):
        raise ValueError('Invalid candidate package')
    version = candidate['version_name']
    if type(version) is not str or not 1 <= len(version.encode('utf-8')) <= 256:
        raise ValueError('Invalid candidate version name')
    for key, lower, upper in [('version_code', 1, 0xffffffff), ('version_code_major', 0, 0x7fffffff),
                              ('min_sdk_version', 1, 37), ('target_sdk_version', 1, 1000)]:
        if type(candidate[key]) is not int or not lower <= candidate[key] <= upper:
            raise ValueError('Invalid candidate ' + key)
    if candidate['target_sdk_version'] < candidate['min_sdk_version']:
        raise ValueError('Candidate SDK interval is reversed')
    apk = candidate['apk']
    _fields(apk, ('name', 'bytes', 'sha256'), 'Candidate APK')
    if apk['name'] != 'base.apk' or type(apk['bytes']) is not int or not 0 < apk['bytes'] <= 1 << 30 or not _sha(apk['sha256']):
        raise ValueError('Candidate must pin one bounded base.apk')
    for key, check in [('native_abis', lambda item: type(item) is str and item in _ABI_ELF),
                       ('signer_certificate_sha256', _sha)]:
        values = candidate[key]
        if type(values) is not list or not 1 <= len(values) <= 8 or not all(check(v) for v in values) or values != sorted(set(values)):
            raise ValueError('Invalid or duplicate candidate ' + key)
    if cross_arch:
        _cross_arch_pins(candidate)
    source = candidate['source']
    source_fields = ('apk_url', 'version_metadata_url', 'observed_utc', 'observed_stable_version', 'sha256_kind')
    signer_url = 'signer_reference_url' if cross_arch else 'publisher_certificate_url'
    _fields(source, source_fields + ((signer_url, 'signer_reference_kind', 'version_metadata_kind')
                                    if cross_arch else (signer_url,)), 'Candidate source')
    if cross_arch and (source['signer_reference_kind'] != 'public_historical_candidate'
                       or source['version_metadata_kind'] != 'signed_apk_android_manifest'):
        raise ValueError('Candidate v2 must distinguish its historical signer pin and signed-APK version metadata')
    for key in ('apk_url', 'version_metadata_url', signer_url):
        if type(source[key]) is not str or len(source[key]) > 2048:
            raise ValueError('Invalid candidate source URL')
        url = urlsplit(source[key])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError('Candidate source must be an HTTPS public URL')
    if type(source['observed_utc']) is not str:
        raise ValueError('Candidate observation must have a UTC timestamp')
    observed = datetime.fromisoformat(source['observed_utc'])
    if observed.utcoffset() is None or observed.utcoffset().total_seconds() != 0:
        raise ValueError('Candidate observation must have a UTC timestamp')
    if source['observed_stable_version'] != version or source['sha256_kind'] not in (
            'observed_whole_file_digest_not_publisher_published_checksum', 'observed_whole_file_digest'):
        raise ValueError('Candidate source observation differs from its pinned version or digest kind')
    return candidate, {'path': str(path.absolute()), 'bytes': len(raw), 'sha256': expected_sha256}


def _match_candidate(result, candidate):
    for key in ('package', 'version_name', 'version_code', 'version_code_major',
                'native_abis', 'signer_certificate_sha256'):
        if result[key] != candidate[key]:
            raise ValueError('Verified APK differs from candidate ' + key)
    for key in ('bytes', 'sha256'):
        if result[key] != candidate['apk'][key]:
            raise ValueError('Verified APK differs from candidate ' + key)
    if result['long_version_code'] != (candidate['version_code_major'] << 32) | candidate['version_code']:
        raise ValueError('Verified APK long version differs from candidate')
    if result['split_name'] is not None or result['uses_splits'] or result['config_for_split'] is not None or result['manifest_split_fields']:
        raise ValueError('Candidate input requires a standalone base APK without split declarations')


def _shared_elf_metadata(body):
    """Read bounded ELF load/dynamic structure without loading or executing it."""
    if (not 52 <= len(body) <= _SHARED_LIBRARY_LIMIT or body[:4] != b'\x7fELF'
            or body[4] not in (1, 2) or body[5:7] != b'\x01\x01'):
        raise ValueError('Invalid cross-architecture ELF encoding')
    elf_class = body[4]
    header_size, program_size, dynamic_size = (64, 56, 16) if elf_class == 2 else (52, 32, 8)
    if len(body) < header_size:
        raise ValueError('Truncated cross-architecture ELF header')
    header = struct.unpack_from('<HHIQQQIHHHHHH' if elf_class == 2 else '<HHIIIIIHHHHHH', body, 16)
    elf_type, machine, version, entry, phoff, _, _, ehsize, phsize, phnum, _, _, _ = header
    if (elf_type != 3 or version != 1 or ehsize != header_size or phsize != program_size
            or not 1 <= phnum <= 128 or phoff < header_size or phoff + phnum * phsize > len(body)):
        raise ValueError('Invalid cross-architecture ET_DYN program table')
    programs = []
    for index in range(phnum):
        row = struct.unpack_from('<IIQQQQQQ' if elf_class == 2 else '<IIIIIIII', body, phoff + index * phsize)
        if elf_class == 2:
            kind, flags, offset, address, _, file_size, memory_size, _ = row
        else:
            kind, offset, address, _, file_size, memory_size, flags, _ = row
        if offset + file_size > len(body) or (kind == 1 and file_size > memory_size):
            raise ValueError('Cross-architecture ELF segment exceeds its file')
        if kind == 3:
            raise ValueError('Cross-architecture shared library must have no PT_INTERP')
        programs.append((kind, flags, offset, address, file_size))
    loads = [p for p in programs if p[0] == 1]
    if not loads or (entry and not any(p[1] & 1 and p[3] <= entry < p[3] + p[4] for p in loads)):
        raise ValueError('Cross-architecture ELF entry is outside executable file-backed loads')

    def file_offset(address, size):
        matches = [p[2] + address - p[3] for p in loads
                   if p[3] <= address and address + size <= p[3] + p[4]]
        if len(matches) != 1:
            raise ValueError('Cross-architecture dynamic pointer lacks one file-backed load')
        return matches[0]

    dynamic = [p for p in programs if p[0] == 2]
    if (len(dynamic) != 1 or not 0 < dynamic[0][4] <= 4096 * dynamic_size
            or dynamic[0][4] % dynamic_size or file_offset(dynamic[0][3], dynamic[0][4]) != dynamic[0][2]):
        raise ValueError('Invalid cross-architecture dynamic segment')
    tags, needed, terminated = {}, [], False
    start, size = dynamic[0][2], dynamic[0][4]
    for position in range(start, start + size, dynamic_size):
        tag, value = struct.unpack_from('<qQ' if elf_class == 2 else '<iI', body, position)
        if tag == 0:
            terminated = True
            break
        if tag == 1:
            needed.append(value)
        elif tag in (5, 10, 14, 30, 0x6ffffffb):
            if tag in tags:
                raise ValueError('Duplicate cross-architecture dynamic identity tag')
            tags[tag] = value
    if (not terminated or not {5, 10, 14} <= set(tags) or not 0 < tags[10] <= 1024 * 1024
            or len(needed) > 64 or tags.get(0x6ffffffb, 0) & 0x08000000):
        raise ValueError('Cross-architecture shared library needs bounded strings, SONAME and no DF_1_PIE')
    start = file_offset(tags[5], tags[10])
    strings = body[start:start + tags[10]]

    def dynamic_string(offset):
        if offset >= len(strings):
            raise ValueError('Cross-architecture dynamic string is out of bounds')
        end = strings.find(b'\0', offset)
        if end < offset or end - offset > 256:
            raise ValueError('Cross-architecture dynamic string is not bounded and terminated')
        return strings[offset:end].decode('utf-8', 'strict')

    return {'elf_class': elf_class, 'elf_machine': machine, 'elf_type': elf_type,
            'soname': dynamic_string(tags[14]), 'entry_point': entry, 'has_interpreter': False,
            'dynamic_needed': [dynamic_string(offset) for offset in needed],
            'program_header_count': phnum}


def _candidate_binary_metadata(path, result, candidate):
    """Bind version name/SDK and actual ELF headers as well as library directory names."""
    with zipfile.ZipFile(path) as apk:
        names = apk.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate APK ZIP members are ambiguous')
        manifest = apk.read('AndroidManifest.xml')
        if hashlib.sha256(manifest).hexdigest() != result['manifest_binary_sha256']:
            raise ValueError('Candidate manifest changed after signature verification')
        raw = axml_metadata(manifest)
        for key in ('package', 'version_name', 'version_code', 'version_code_major'):
            if raw[key] != candidate[key]:
                raise ValueError('Binary manifest differs from candidate ' + key)
        for key in ('min_sdk_version', 'target_sdk_version'):
            if int(raw[key], 0) != candidate[key]:
                raise ValueError('Binary manifest differs from candidate ' + key)
        libraries = []
        pins = _cross_arch_pins(candidate) if candidate['schema'] == _CROSS_ARCH_SCHEMA else {}
        observed_cross_arch = []
        for name in names:
            if not name.startswith('lib/') or not name.endswith('.so'):
                continue
            parts = name.split('/')
            if len(parts) != 3 or parts[1] not in candidate['native_abis']:
                raise ValueError('Native library path differs from candidate ABI')
            with apk.open(name) as stream:
                header = stream.read(20)
            elf_class, machine = _ABI_ELF[parts[1]]
            if name in pins:
                pin = pins[name]
                if apk.getinfo(name).file_size != pin['bytes']:
                    raise ValueError('Cross-architecture library differs from its pinned bytes')
                with apk.open(name) as stream:
                    body = stream.read(pin['bytes'] + 1)
                if len(body) != pin['bytes'] or hashlib.sha256(body).hexdigest() != pin['sha256']:
                    raise ValueError('Cross-architecture library differs from its pinned SHA-256')
                actual = _shared_elf_metadata(body)
                for key in ('elf_class', 'elf_machine', 'elf_type', 'soname', 'entry_point', 'has_interpreter'):
                    if actual[key] != pin[key]:
                        raise ValueError('Cross-architecture library differs from its pinned ' + key)
                if (actual['elf_class'], actual['elf_machine']) == (elf_class, machine):
                    raise ValueError('Pinned cross-architecture library actually matches the directory ABI')
                observed_cross_arch.append({**pin, **actual})
                libraries.append({'path': name, 'elf_class': actual['elf_class'],
                                  'elf_machine': actual['elf_machine'], 'kind': pin['kind']})
                continue
            if len(header) != 20 or header[:4] != b'\x7fELF' or header[4] != elf_class or header[5] != 1 or int.from_bytes(header[18:20], 'little') != machine:
                raise ValueError('Native ELF header differs from candidate ABI')
            libraries.append({'path': name, 'elf_class': elf_class, 'elf_machine': machine})
        if sorted({item['path'].split('/')[1] for item in libraries}) != candidate['native_abis']:
            raise ValueError('Candidate native libraries are missing')
        if {item['path'] for item in observed_cross_arch} != set(pins):
            raise ValueError('Candidate cross-architecture library set is incomplete')
    result = {'min_sdk_version': candidate['min_sdk_version'],
              'target_sdk_version': candidate['target_sdk_version'], 'native_libraries': libraries}
    if candidate['schema'] == _CROSS_ARCH_SCHEMA:
        result.update(cross_arch_shared_libraries=sorted(observed_cross_arch, key=lambda item: item['path']),
                      native_compatibility_qualified=False, dispatch_runtime_observed=False)
    return result


def verify_candidate(path, tools, candidate_path, expected_sha256, receipt_path):
    """Produce one native ApplicationPlan fragment only after fresh local verification."""
    path, candidate_path, receipt_path = Path(path), Path(candidate_path), Path(receipt_path)
    candidate, candidate_pin = load_candidate(candidate_path, expected_sha256)
    if not receipt_path.is_absolute():
        raise ValueError('Receipt output must be an absolute new file path')
    if os.path.lexists(receipt_path):
        raise ValueError('Receipt output already exists')
    result = verify(path, tools, candidate['package'], candidate['signer_certificate_sha256'])
    _match_candidate(result, candidate)
    binary_metadata = _candidate_binary_metadata(path, result, candidate)
    if digest(path) != result['sha256'] or path.stat().st_size != result['bytes'] or digest(candidate_path) != expected_sha256:
        raise ValueError('APK or candidate changed before receipt publication')
    receipt = {'schema': 'pocket4-verified-apk-source-receipt-v1',
               'verified_utc': datetime.now(timezone.utc).isoformat(),
               'candidate': candidate_pin, 'source_observation': candidate['source'],
               'identity': result, 'binary_metadata': binary_metadata,
               'installed': False, 'runtime_qualified': False, 'production_ready': False}
    raw = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    with receipt_path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    receipt_pin = {'path': str(receipt_path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return {'application': {'package': result['package'],
                            'expected_input': {'version_code': result['long_version_code'],
                                               'apks': [{'name': 'base.apk', 'bytes': result['bytes'], 'sha256': result['sha256']}],
                                               'source_receipt': receipt_pin}},
            'candidate': candidate_pin, 'installed': False, 'runtime_qualified': False,
            'production_ready': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--build-tools', type=Path, required=True)
    parser.add_argument('--expected-package')
    parser.add_argument('--expected-certificate-sha256', action='append')
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--expect-candidate-sha256')
    parser.add_argument('--receipt-output', type=Path)
    args = parser.parse_args()
    candidate_mode = (args.candidate is not None, args.expect_candidate_sha256 is not None,
                      args.receipt_output is not None)
    if any(candidate_mode):
        if not all(candidate_mode) or args.expected_package is not None or args.expected_certificate_sha256 is not None:
            parser.error('Use --candidate, --expect-candidate-sha256 and --receipt-output together, without legacy expected identity flags')
        result = verify_candidate(args.apk, args.build_tools, args.candidate,
                                  args.expect_candidate_sha256, args.receipt_output)
    else:
        result = verify(args.apk, args.build_tools, args.expected_package, args.expected_certificate_sha256)
    print(json.dumps(result, indent=2))
