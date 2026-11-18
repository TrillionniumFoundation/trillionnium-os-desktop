"""Content-bound, SDK-37 APK identity verification. No installation or account access."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
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
_CANDIDATE_LIMIT = 16 * 1024
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
    _fields(candidate, ('schema', 'package', 'version_name', 'version_code',
                       'version_code_major', 'min_sdk_version', 'target_sdk_version',
                       'apk', 'native_abis', 'signer_certificate_sha256', 'source'), 'Candidate')
    if candidate['schema'] != _CANDIDATE_SCHEMA:
        raise ValueError('Unsupported candidate schema')
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
    source = candidate['source']
    _fields(source, ('apk_url', 'version_metadata_url', 'publisher_certificate_url',
                    'observed_utc', 'observed_stable_version', 'sha256_kind'), 'Candidate source')
    for key in ('apk_url', 'version_metadata_url', 'publisher_certificate_url'):
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
    if source['observed_stable_version'] != version or source['sha256_kind'] != 'observed_whole_file_digest_not_publisher_published_checksum':
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
        for name in names:
            if not name.startswith('lib/') or not name.endswith('.so'):
                continue
            parts = name.split('/')
            if len(parts) != 3 or parts[1] not in candidate['native_abis']:
                raise ValueError('Native library path differs from candidate ABI')
            with apk.open(name) as stream:
                header = stream.read(20)
            elf_class, machine = _ABI_ELF[parts[1]]
            if len(header) != 20 or header[:4] != b'\x7fELF' or header[4] != elf_class or header[5] != 1 or int.from_bytes(header[18:20], 'little') != machine:
                raise ValueError('Native ELF header differs from candidate ABI')
            libraries.append({'path': name, 'elf_class': elf_class, 'elf_machine': machine})
        if sorted({item['path'].split('/')[1] for item in libraries}) != candidate['native_abis']:
            raise ValueError('Candidate native libraries are missing')
    return {'min_sdk_version': candidate['min_sdk_version'],
            'target_sdk_version': candidate['target_sdk_version'], 'native_libraries': libraries}


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
