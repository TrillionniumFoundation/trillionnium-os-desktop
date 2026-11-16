"""Content-bound, SDK-37 APK identity verification. No installation or account access."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
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


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--build-tools', type=Path, required=True)
    parser.add_argument('--expected-package')
    parser.add_argument('--expected-certificate-sha256', action='append')
    args = parser.parse_args()
    print(json.dumps(verify(args.apk, args.build_tools, args.expected_package,
                            args.expected_certificate_sha256), indent=2))
