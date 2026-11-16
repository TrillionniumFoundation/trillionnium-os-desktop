"""Real signed-APK controls. The provided reference is retained unchanged."""
from pathlib import Path
import argparse
import json
import shutil
import struct
import tempfile
import zipfile
from verify_apk import application_signer_certificates, digest, verify


def rejection(call):
    try:
        call()
    except (ValueError, RuntimeError, zipfile.BadZipFile):
        return True
    return False


def run(reference, tools, expected_sha):
    if digest(reference) != expected_sha:
        raise ValueError('Control reference differs from expected public artifact SHA')
    positive = verify(reference, tools)
    wrong_package = rejection(lambda: verify(reference, tools, 'invalid.example.identity'))
    first, second = 'a' * 64, 'b' * 64
    stamp_fixture = ('Signer #1 certificate SHA-256 digest: ' + first + '\n'
                     'Source Stamp Signer certificate SHA-256 digest: ' + second + '\n')
    source_stamp_separated = application_signer_certificates(stamp_fixture) == [first]
    with tempfile.TemporaryDirectory(prefix='APK-identity-counterexamples-') as temporary:
        reused_path = Path(temporary) / 'same-input-name.apk'
        shutil.copyfile(reference, reused_path)
        valid_reused_path = verify(reused_path, tools)['sha256'] == expected_sha
        with zipfile.ZipFile(reused_path) as apk:
            entry = next(x for x in apk.infolist() if x.filename.endswith('.dex') and x.compress_size > 64)
        with reused_path.open('r+b') as stream:
            stream.seek(entry.header_offset)
            local = stream.read(30)
            if local[:4] != b'PK\x03\x04':
                raise ValueError('APK local entry header is not ZIP')
            name_len, extra_len = struct.unpack_from('<HH', local, 26)
            stream.seek(entry.header_offset + 30 + name_len + extra_len + 17)
            before = stream.read(1)
            stream.seek(-1, 1)
            stream.write(bytes([before[0] ^ 1]))
        changed_signed_bytes_rejected = rejection(lambda: verify(reused_path, tools))
    result = {'valid_reference_passed': positive['signature_verified'],
              'wrong_expected_package_rejected': wrong_package,
              'source_stamp_separate_from_application_signer': source_stamp_separated,
              'valid_reused_external_filename_passed': valid_reused_path,
              'same_external_filename_with_changed_signed_bytes_rejected': changed_signed_bytes_rejected,
              'reference_bytes_unchanged': digest(reference) == expected_sha,
              'temporary_counterexamples_removed': not Path(temporary).exists(),
              'reference_sha256': expected_sha, 'applications_installed_or_executed': 0}
    if not all(v for k, v in result.items() if isinstance(v, bool)):
        raise RuntimeError('A content-association control failed: ' + json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-apk', type=Path, required=True)
    parser.add_argument('--reference-sha256', required=True)
    parser.add_argument('--build-tools', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.reference_apk, args.build_tools, args.reference_sha256), indent=2))
